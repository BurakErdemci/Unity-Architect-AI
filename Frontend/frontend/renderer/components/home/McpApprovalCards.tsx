/**
 * McpApprovalCards — unityMCP köprüsünden gelen onay kartlarının TEK çizim yeri.
 *
 * Neden ayrı bileşen (2026-07-29 denetimi, `approval-card-hidden-by-view-state`):
 * kartlar ChatPanel'in içinde çiziliyordu, ChatPanel ise yalnız bir workspace
 * AÇIKKEN mount ediliyor (`home.tsx`, `if (!fs.workspacePath) return
 * <WorkspaceScreen/>`). Köprü ürünün görünüm durumundan bağımsız çalıştığı için
 * workspace seçilmemişken gelen istek state'e giriyor, ekrana hiç çıkmıyor ve
 * 180 sn sonra reddediliyordu. Kartları kendi bileşenine almak, onları hem
 * sohbetin içinde hem de workspace ekranının üstünde çizilebilir kılıyor —
 * markup'ı kopyalamadan.
 *
 * ⚠️ `pendingFix` (var olan dosyayı değiştirme) burada KENDİ DiffViewer'ını
 * kuruyor; ChatPanel'deki mesaja bağlı DiffViewer'ın kopyası DEĞİL. İki akış
 * gerçekten farklı: burada karar köprüye POST'lanır, orada dosya IPC ile
 * yazılır. 2026-07-29'da bunlar "aynı eleman" diye tek yere toplanmıştı; o
 * birleştirme kopyala-yapıştır sapmasını engellemek içindi ve akışların
 * ayrılmasıyla gereksizleşti.
 */
import React, { useRef } from 'react';
import { AlertTriangle, FolderOpen } from 'lucide-react';
import { DiffViewer } from './DiffViewer';
import { FileCreationApproval, PendingFile } from './FileCreationApproval';
import { FileDeleteApproval } from './FileDeleteApproval';
import { CommandApproval } from './CommandApproval';
import { postMcpDecision, decisionToast } from '../../hooks/home/gateResponse';
import { MCP_MSG_ID, McpActiveGate } from '../../hooks/home/useMCPApproval';

interface McpApprovalCardsProps {
  /** Ekranda karar bekleyen istek. `null` ise hiçbir şey çizilmez. */
  gate: McpActiveGate | null;
  /** Gate'in workspace'i üründe açık olandan farklı mı (bilinmiyorsa false). */
  workspaceMismatch: boolean;
  /** Üründe açık olan workspace; banner'da "açık olan" satırı için. */
  openWorkspacePath: string | null;
  /** Karar verildi/kart kapandı → sıradaki isteğin gösterilmesine izin ver. */
  onResolved: () => void;

  apiBase: string;
  sessionToken: string;
  showToast: (msg: string, type: 'success' | 'error' | 'warning' | 'info') => void;
  refreshFileTree: () => void;

  pendingGenFiles: { files: PendingFile[]; messageId: number } | null;
  setPendingGenFiles: (val: any) => void;
  pendingDelete: { path: string; messageId: number } | null;
  setPendingDelete: (val: any) => void;
  pendingCommand: { command: string; gateId: string; messageId: number } | null;
  setPendingCommand: (val: any) => void;
  pendingFix: { data: any; messageId?: number; applied?: boolean; gateId?: string } | null;
  setPendingFix: (val: any) => void;

  /** Editör bağlamı. Workspace ekranının üstünde çizilirken yoktur. */
  setDiffFile?: (val: any) => void;
  onOpenFile?: (path: string) => void;
  /** Onay sonrası editör tamponunu tazelemek için; editör yoksa verilmez. */
  setCode?: (code: string) => void;
}

/**
 * İsteğin hangi projeden geldiğini yazan şerit.
 *
 * Kullanıcı kararı (2026-07-29): eşleşmeyen istek GİZLENMEZ, çünkü unityMCP'yi
 * doğrudan başka bir istemciye bağlamış kullanıcıyı 180 sn'lik sessiz bir redde
 * kilitlerdi. Bunun bedeli açıkça kabul edildi: koruma bu şeridin OKUNMASINA
 * bağlı, yani refleks onayda hiçbir şey engellemiyor.
 *
 * Şerit eşleşme durumunda da çiziliyor. Yalnız uyuşmazlıkta göstermek, kartın
 * "hangi projeye ait" bilgisini normal akışta hiç öğretmezdi; kullanıcı şeridi
 * ilk kez tam da en riskli anda görürdü ve neye baktığını bilmezdi.
 */
const WorkspaceBanner: React.FC<{
  gate: McpActiveGate;
  mismatch: boolean;
  openWorkspacePath: string | null;
}> = ({ gate, mismatch, openWorkspacePath }) => {
  // Gate workspace'i boşsa iddia edilecek bir şey yok — bilinmiyor de.
  const bilinmiyor = !gate.workspacePath;
  const renk = mismatch
    ? 'border-amber-500/50 bg-amber-500/10 text-amber-300'
    : 'border-slate-700 bg-slate-800/50 text-slate-400';
  return (
    <div className={`flex items-start gap-2 rounded-t-lg border border-b-0 px-3 py-1.5 text-[11px] ${renk}`}>
      {mismatch ? <AlertTriangle size={13} className="mt-px shrink-0" />
                : <FolderOpen size={13} className="mt-px shrink-0" />}
      <div className="min-w-0">
        {mismatch && <div className="font-bold">⚠ BAŞKA PROJE</div>}
        <div className="truncate font-mono">
          {bilinmiyor ? 'Kaynak proje bildirilmedi' : gate.workspacePath}
        </div>
        {mismatch && openWorkspacePath && (
          <div className="truncate opacity-70">açık olan: {openWorkspacePath}</div>
        )}
      </div>
    </div>
  );
};

export const McpApprovalCards: React.FC<McpApprovalCardsProps> = ({
  gate,
  workspaceMismatch,
  openWorkspacePath,
  onResolved,
  apiBase,
  sessionToken,
  showToast,
  refreshFileTree,
  pendingGenFiles,
  setPendingGenFiles,
  pendingDelete,
  setPendingDelete,
  pendingCommand,
  setPendingCommand,
  pendingFix,
  setPendingFix,
  setDiffFile,
  onOpenFile,
  setCode,
}) => {
  /**
   * Bu gate için karar ZATEN gönderildi mi.
   *
   * Gerekçesi iki yönlü. (1) Kart kapatma yolları (`onDone`, `onSkipOne`) artık
   * karar gönderiyor — eskiden yalnız state'i temizliyorlardı ve köprü 180 sn
   * bekleyip reddediyordu; kullanıcı ise reddettiğini SANIYORDU (dış denetim:
   * `approval-state-cleared-without-decision`). (2) Ama `onDone` onaydan SONRA
   * da tetikleniyor; işaret olmasa onaylanmış bir gate'e ikinci kez "reddet"
   * gider ve kullanıcı sebepsiz bir "gate bulunamadı" uyarısı görürdü.
   */
  const decidedRef = useRef<string | null>(null);

  if (!gate) return null;

  const gateId = gate.gateId;

  /** Kararı gönderir; aynı gate için ikinci kez göndermez. */
  const decide = async (approved: boolean) => {
    if (decidedRef.current === gateId) return null;
    decidedRef.current = gateId;
    return postMcpDecision(apiBase, gateId, approved, sessionToken);
  };

  /**
   * Kart kapatıldı → karar verilmemişse köprüyü bekletmeden reddet.
   *
   * Koşul BURADA YOK, `decide` içinde: iki yerde aynı kontrolü yapmak
   * savunma değil fazlalıktı. Mutasyonla ölçüldü (2026-07-29): kontrollerden
   * biri kaldırıldığında öteki testi yeşil tutuyordu, yani ikisi de tek tek
   * "gereksiz" görünüyordu ve hangisinin gerçek koruma olduğu ölçülemiyordu.
   * Tek kontrol, tek mutasyon, net cevap.
   */
  const closeWithoutDecision = async () => {
    const failure = await decide(false);   // zaten karar verildiyse no-op
    if (failure) showToast(failure.message, failure.type);
    onResolved();
  };

  const banner = (
    <WorkspaceBanner gate={gate} mismatch={workspaceMismatch} openWorkspacePath={openWorkspacePath} />
  );

  return (
    <>
      {pendingGenFiles?.messageId === MCP_MSG_ID && (
        <div className="px-4 pb-2">
          {banner}
          <FileCreationApproval
            files={pendingGenFiles.files}
            autoAccept={false}
            setDiffFile={setDiffFile ?? (() => {})}
            onOpenFile={onOpenFile ?? (() => {})}
            // `gateId ? … : null` üçlemesi kaldırıldı: `null` bu sözleşmede
            // "teslim edildi" demek, yani gate yokken hiçbir istek gitmeden
            // başarı iddia ediliyordu. Kararı artık postMcpDecision veriyor.
            onAcceptOne={async (file) => {
              const failure = await decide(true);
              refreshFileTree();
              // "oluşturuldu" DEĞİL "yazılıyor": `failure === null` yalnız
              // backend'in onayı kaydettiğini kanıtlıyor. Dosyayı MCP köprüsü
              // bundan sonra `file_tools.write_file` içinde yazıyor ve orada
              // düşebiliyor (ölçüldü 2026-07-29: hedefin üst dizini normal bir
              // dosyaysa `os.makedirs` → FileExistsError, dosya diske hiç
              // yazılmıyor — ekranda ise "✅ oluşturuldu" duruyordu).
              const t = decisionToast(failure, `Onayınız gönderildi — ${file.name} yazılıyor`);
              showToast(t.message, t.type);
              // ⚠️ BİLİNEN BOŞLUK: dönen `true` FileCreationApproval'ın kartında
              // dosyayı "oluşturuldu" listesine taşıyor. O sözleşme (bkz.
              // FileCreationApproval.tsx:34) yerel IPC yolunda GERÇEKTEN
              // doğrulanmış başarı demek; burada yalnız teslimat demek. Üçüncü
              // bir durum ("teslim edildi, sonuç bilinmiyor") olmadan
              // düzeltilemez ve `false` dönmek daha kötü olurdu: hiç olmamış
              // bir başarısızlığı iddia ederdi.
              return !failure;
            }}
            // Atlamak da bir KARAR: eskiden hiçbir şey göndermiyordu ve istek
            // köprüde 180 sn asılı kalıyordu.
            onSkipOne={() => { void closeWithoutDecision(); }}
            onAcceptAll={async () => {
              const failure = await decide(true);
              refreshFileTree();
              // Kardeş satır: yukarıdaki tek-dosya yoluyla AYNI sınıf, aynı dil.
              const t = decisionToast(failure, 'Onayınız gönderildi — dosyalar yazılıyor');
              showToast(t.message, t.type);
              return !failure;
            }}
            onDone={() => { setPendingGenFiles(null); void closeWithoutDecision(); }}
          />
        </div>
      )}

      {pendingDelete?.messageId === MCP_MSG_ID && (
        <div className="px-4 pb-2">
          {banner}
          <FileDeleteApproval
            path={pendingDelete.path}
            onConfirm={async () => {
              const failure = await decide(true);
              setPendingDelete(null);
              onResolved();
              // MCP server approval'ı polling ile ~500ms gecikmeli görür → dosyayı siler.
              // Refresh'i geciktirmezsek dosya henüz silinmemiş olur.
              setTimeout(() => refreshFileTree(), 900);
              // "silindi" DEĞİL "siliniyor": onayın iletilmesi silmenin
              // yapıldığını değil, köprünün onu ~500ms sonra DENEYECEĞİNİ
              // gösteriyor (üstteki refreshFileTree gecikmesi tam bu yüzden var).
              const t = decisionToast(failure, '🗑️ Onayınız gönderildi — dosya siliniyor');
              showToast(t.message, t.type);
            }}
            onCancel={async () => {
              // Reddin iletilmemesi de sessiz kalmamalı: kullanıcı reddettiğini
              // sanırken gate düşmüş olabilir ve MCP tarafı kendi kararını verir.
              const failure = await decide(false);
              if (failure) showToast(failure.message, failure.type);
              setPendingDelete(null);
              onResolved();
            }}
          />
        </div>
      )}

      {pendingCommand?.messageId === MCP_MSG_ID && (
        <div className="px-4 pb-2">
          {banner}
          <CommandApproval
            command={pendingCommand.command}
            onConfirm={async () => {
              const failure = await decide(true);
              setPendingCommand(null);
              onResolved();
              // "çalışıyor" iddiası onay iletilse BİLE erken: komutu köprü
              // bundan sonra başlatıyor ve başlatma da düşebilir.
              const t = decisionToast(failure, 'Onayınız gönderildi — komut başlatılıyor');
              showToast(t.message, t.type);
            }}
            onCancel={async () => {
              const failure = await decide(false);
              setPendingCommand(null);
              onResolved();
              // RET tarafı ASİMETRİK ve bilerek "oldu" diyor: köprü kararı
              // fail-closed okuyor, yani iletilmiş bir ret komutun
              // ÇALIŞMAYACAĞINI garanti ediyor — onaydan farklı olarak burada
              // teslimat sonucun kendisi. (Onay tarafı bunu söyleyemez: orada
              // teslimattan sonra hâlâ yapılacak bir iş kalıyor.)
              const t = decisionToast(failure, 'Komut iptal edildi');
              showToast(t.message, t.type);
            }}
          />
        </div>
      )}

      {pendingFix?.messageId === MCP_MSG_ID && (
        <div className="px-4 pb-2">
          {banner}
          <DiffViewer
            diffData={pendingFix.data}
            filename={pendingFix.data?.editor_hint?.split('/').pop()}
            applied={pendingFix.applied}
            onAccept={async (fixedCode) => {
              const failure = await decide(true);
              // Dosyayı MCP köprüsü yazıyor; burada yalnız editör tamponu
              // tazeleniyor ve yalnız karar İLETİLDİYSE — iletilmediyse diskte
              // eski içerik kalacak, editörde yenisini göstermek yalan olurdu.
              if (!failure) setCode?.(fixedCode);
              setPendingFix(null);
              onResolved();
              refreshFileTree();
              // "Onaylandı" değil "gönderildi": dosyayı MCP köprüsü
              // BUNDAN SONRA yazıyor ve orada düşebiliyor.
              const t = decisionToast(failure, 'Onayınız gönderildi — değişiklik uygulanıyor');
              showToast(t.message, t.type);
            }}
            onReject={async () => {
              const failure = await decide(false);
              if (failure) showToast(failure.message, failure.type);
              setPendingFix(null);
              onResolved();
            }}
          />
        </div>
      )}
    </>
  );
};
