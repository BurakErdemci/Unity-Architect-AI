/**
 * useMCPApproval — MCP server'dan gelen onay isteklerini dinler ve
 * mevcut approval UI'larına (DiffViewer, FileCreationApproval,
 * FileDeleteApproval, CommandApproval) yönlendirir.
 *
 * Polling: /mcp-pending endpoint'ini 1 saniyede bir kontrol eder.
 * Her yeni istek geldiğinde ilgili state setter'ı çağırır.
 * Kullanıcı onaylarsa/reddederse /mcp-approval-respond/{gate_id} çağrılır.
 */
import { useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import { PendingFile } from '../../components/home/FileCreationApproval';
import { gateFailure } from './gateResponse';

interface MCPApprovalHookParams {
  API: string;
  enabled: boolean;  // Sadece subscription provider'da aktif
  loading?: boolean; // Sadece AI işlem yaparken poll et — idle'da CPU harcama
  setPendingGenFiles: (val: { files: PendingFile[]; messageId: number } | null) => void;
  setPendingDelete: (val: { path: string; messageId: number } | null) => void;
  setPendingCommand: (val: { command: string; gateId: string; messageId: number } | null) => void;
  setPendingFix: (val: any) => void;
  // Kararın backend'e ULAŞMADIĞINI kullanıcıya bildirmek için. Opsiyonel:
  // hook'u test/başka bağlamda toast'sız kurmak mümkün kalsın.
  showToast?: (msg: string, type: any) => void;
}

// MCP onay isteği için sanal mesaj ID'si (gerçek chat mesajına bağlı değil)
const MCP_MSG_ID = -999;

/**
 * MCP onay kimliklerinin (gate id) tek saklama/okuma yeri.
 *
 * Neden `window` üstünde: kart bileşenleri (ChatPanel) hook'un dönüşünü değil
 * `pendingDelete`/`pendingGenFiles` state'ini görüyor; gate id o state'in içinde
 * taşınmıyor. Bu bir tasarım borcu, ama düzeltilmesi bu şeridin kapsamı değil —
 * burada yapılan, borcu TEK yere hapsetmek.
 *
 * Neden `take` (oku VE sil): karar verildikten sonra global bayat değeriyle
 * duruyordu. Sıradaki kart gate id'siz gelirse (ör. yazma yolunda hata) eski id
 * okunur ve karar YANLIŞ gate'e bildirilirdi.
 */
export type McpGateKind = 'write' | 'delete';
const GATE_KEYS: Record<McpGateKind, string> = {
  write: '__mcpWriteGate',
  delete: '__mcpDeleteGate',
};

export const setMcpGate = (kind: McpGateKind, gateId: string): void => {
  (window as any)[GATE_KEYS[kind]] = gateId;
};

/** Okur ve siler. Gate yoksa `''` döner — `undefined` sızdırmaz, çünkü
 *  `postMcpDecision` boş string'i "istek gönderme, başarısızlık bildir" diye
 *  yorumluyor ve bu ayrımın tek yerde durması gerekiyor. */
export const takeMcpGate = (kind: McpGateKind): string => {
  const key = GATE_KEYS[kind];
  const value = (window as any)[key];
  delete (window as any)[key];
  return typeof value === 'string' ? value : '';
};

export const useMCPApproval = ({
  API,
  enabled,
  loading = false,
  setPendingGenFiles,
  setPendingDelete,
  setPendingCommand,
  setPendingFix,
  showToast,
}: MCPApprovalHookParams) => {
  const seenGates = useRef<Set<string>>(new Set());
  const pollingRef = useRef<NodeJS.Timeout | null>(null);

  // Yanıt gövdesi eskiden okunmuyordu: gate TTL ile süpürüldüyse backend
  // {"status":"gate_not_found"} dönüyor, kart yine kapanıyor ve kullanıcı
  // onayladığını sanıyordu. Bridge o gate'i fail-closed reddediyor — yani
  // dosya yazılmıyor/komut çalışmıyor ama ekranda hiçbir iz yok.
  const respond = useCallback(async (gateId: string, approved: boolean) => {
    let failure = null as ReturnType<typeof gateFailure>;
    try {
      const res = await axios.post(`${API}/mcp-approval-respond/${gateId}`, { approved });
      // axios non-2xx'te zaten throw eder; buraya düşen yanıt 2xx'tir.
      failure = gateFailure('mcp', { httpOk: true, httpStatus: res.status, body: res.data });
    } catch (err) {
      console.warn('[MCP] respond error', err);
      failure = gateFailure('mcp', { httpOk: false, error: err });
    }
    if (failure) showToast?.(failure.message, failure.type);
  }, [API, showToast]);

  const poll = useCallback(async () => {
    if (!API) return;
    try {
      const res = await axios.get(`${API}/mcp-pending`);
      const pending: Record<string, any> = res.data?.pending ?? {};

      for (const [gateId, req] of Object.entries(pending)) {
        if (seenGates.current.has(gateId)) continue;
        seenGates.current.add(gateId);

        const { tool, params } = req as { tool: string; params: any };

        if (tool === 'write_file') {
          const { path, content, original } = params;
          // Gate kimliği kart state'inden ÖNCE yazılır: kart render olup
          // kullanıcı butona bastığında kimlik hazır olmalı. (Aynı sınıf hata
          // `delete_file` yolunda vardı ve yalnız React batching kurtarıyordu.)
          setMcpGate('write', gateId);

          if (!original) {
            // Yeni dosya → FileCreationApproval
            const file: PendingFile = {
              name: path.split('/').pop() || path,
              code: content,
              suggestedPath: path,
              originalCode: '',
            };
            setPendingGenFiles({ files: [file], messageId: MCP_MSG_ID });
          } else {
            // Değişiklik → DiffViewer
            setPendingFix({
              messageId: MCP_MSG_ID,
              applied: false,
              data: {
                original_code: original,
                fixed_code: content,
                explanation: `MCP: ${path} güncelleniyor`,
                editor_hint: path,
              },
              gateId,
            });
          }
        } else if (tool === 'delete_file') {
          // SIRA ÖNEMLİ: gate kimliği kartı gösteren state'ten ÖNCE yazılır.
          // Ters sırada yalnız React batching kurtarıyordu — batching'e bağlı
          // doğruluk doğruluk değildir (bir refactor ya da bir `await`
          // uzaklıkta kırılır ve kullanıcı gate'siz bir karta basar).
          setMcpGate('delete', gateId);
          setPendingDelete({ path: params.path, messageId: MCP_MSG_ID });
        } else if (tool === 'bash') {
          setPendingCommand({
            command: params.command,
            gateId,
            messageId: MCP_MSG_ID,
          });
        }
      }
    } catch {
      // Backend erişilemez, sessizce devam
    }
  }, [API, setPendingGenFiles, setPendingDelete, setPendingCommand, setPendingFix]);

  // Polling başlat/durdur — sadece subscription provider'da VE loading sırasında aktif
  useEffect(() => {
    if (!API || !enabled || !loading) {
      if (pollingRef.current) { clearInterval(pollingRef.current); pollingRef.current = null; }
      return;
    }
    pollingRef.current = setInterval(poll, 1000);
    return () => {
      if (pollingRef.current) { clearInterval(pollingRef.current); pollingRef.current = null; }
    };
  }, [API, enabled, loading, poll]);

  // Onay/red fonksiyonları — mevcut UI'lardan çağrılır
  const approveMCPFile = useCallback(async (gateId: string) => {
    await respond(gateId, true);
    setPendingGenFiles(null);
    setPendingFix(null);
  }, [respond, setPendingGenFiles, setPendingFix]);

  const rejectMCPFile = useCallback(async (gateId: string) => {
    await respond(gateId, false);
    setPendingGenFiles(null);
    setPendingFix(null);
  }, [respond, setPendingGenFiles, setPendingFix]);

  const approveMCPDelete = useCallback(async () => {
    const gateId = takeMcpGate('delete');
    if (gateId) await respond(gateId, true);
    setPendingDelete(null);
  }, [respond, setPendingDelete]);

  const rejectMCPDelete = useCallback(async () => {
    const gateId = takeMcpGate('delete');
    if (gateId) await respond(gateId, false);
    setPendingDelete(null);
  }, [respond, setPendingDelete]);

  // `poll` dışarı da veriliyor: polling'in kendisi zamanlayıcıya bağlı, ama
  // "gate kimliği kart state'inden önce yazılıyor mu" sorusu zamanlayıcıdan
  // bağımsız bir DOĞRULUK sorusu ve deterministik ölçülebilmeli.
  return { respond, poll, approveMCPFile, rejectMCPFile, approveMCPDelete, rejectMCPDelete };
};
