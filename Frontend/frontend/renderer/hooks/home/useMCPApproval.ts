/**
 * useMCPApproval — MCP server'dan gelen onay isteklerini dinler ve
 * mevcut approval UI'larına (DiffViewer, FileCreationApproval,
 * FileDeleteApproval, CommandApproval) yönlendirir.
 *
 * Polling: /mcp-pending endpoint'ini 1 saniyede bir kontrol eder.
 * Kullanıcı onaylarsa/reddederse /mcp-approval-respond/{gate_id} çağrılır.
 *
 * ⚠️ Bu yol SSE DEĞİL, polling — backend tarafında da öyle. Bunu yazmaya değer
 * çünkü tersini iddia eden yorumlar vardı ve bir tasarım tartışmasında "zaten
 * SSE var" diye okundu. SSE'nin neden seçilmediği polling aralığının yanında.
 *
 * ⚠️ AYNI ANDA TEK KART. Bekleyen istek kuyruğu backend'in `_mcp_pending`
 * sözlüğü; bu hook oradan bir seferde bir tane alır ve karar verilene kadar
 * yenisini almaz. Gerekçesi ölçülmüş bir arıza (2026-07-29 denetimi): eskiden
 * her yoklamada bekleyenlerin HEPSİ işleniyordu, hepsi aynı tek kart slotuna
 * yazıyordu ve sonuncusu öncekilerin üstüne biniyordu. Üstü çizilen istek
 * "görüldü" işaretlendiği için bir daha hiç gösterilmiyor, köprüde 180 sn
 * bekleyip reddediliyordu.
 */
import { useEffect, useRef, useCallback, useState } from 'react';
import axios from 'axios';
import { PendingFile } from '../../components/home/FileCreationApproval';

/**
 * Ekranda karar bekleyen MCP isteği. Kartı çizen taraf gate kimliğini ve
 * isteğin GELDİĞİ workspace'i buradan okur.
 */
export interface McpActiveGate {
  gateId: string;
  tool: string;
  /**
   * İsteği açan tarafın çalışma dizini (`_mcp_pending[...].workspace_path`).
   * Boş olabilir: köprü bu alanı göndermek zorunda değil ve eski sürümler
   * göndermiyordu. Boşluk "eşleşiyor" diye okunmamalı — bkz `workspaceMismatch`.
   */
  workspacePath: string;
}

interface MCPApprovalHookParams {
  API: string;
  /**
   * "Backend hazır ve oturum token'ı axios'a kuruldu" demek — SAĞLAYICI DEĞİL.
   *
   * Eskiden `effectiveProvider === 'subscription'` bağlanıyordu ve yanına
   * `loading: chat.loading` koşulu vardı. İkisi de 2026-07-29'da kaldırıldı:
   * onay kartı üreten köprü (`approval_bridge.py`) sağlayıcıyı hiç bilmiyor ve
   * 9 sağlayıcının 9'u da aynı uca gidiyor, yani kartı sağlayıcıya bağlamak
   * kartı 8 yolda yok ediyordu. `loading` de yanlıştı: CLI sağlayıcıları sohbet
   * "idle" görünürken araç çağırabiliyor.
   *
   * Token kurulmadan yoklamak anlamsız: `/mcp-pending` `X-Session-Token`
   * istiyor (`auth_utils._check_token`) ve token `useAuth` içinde IPC'den
   * geldikten sonra `axios.defaults`'a yazılıyor. Öncesinde her saniye sessizce
   * yutulan bir 401 üretilirdi.
   */
  enabled: boolean;
  /**
   * ÜRÜNDE açık olan workspace. Gate'in kendi workspace'iyle karşılaştırılıp
   * kullanıcıya gösterilir; kartı GİZLEMEK için kullanılmaz (karar 2026-07-29,
   * kullanıcı: eşleşmeyen kart gösterilsin ama hangi projeye ait olduğu yazsın).
   *
   * Gizlememenin gerekçesi: unityMCP'yi doğrudan başka bir istemciye (Cursor
   * vb.) bağlamış kullanıcı üründe o projeyi açmamış olabilir; kartı gizlemek
   * onu 180 sn'lik sessiz bir redde kilitlerdi. Bedeli açıkça kabul edildi:
   * koruma, kullanıcının banner'ı OKUMASINA bağlı.
   */
  workspacePath: string | null;
  setPendingGenFiles: (val: { files: PendingFile[]; messageId: number } | null) => void;
  setPendingDelete: (val: { path: string; messageId: number } | null) => void;
  setPendingCommand: (val: { command: string; gateId: string; messageId: number; kind?: 'shell' | 'unity' } | null) => void;
  setPendingFix: (val: any) => void;
  // Kararın backend'e ULAŞMADIĞINI kullanıcıya bildirmek için. Opsiyonel:
  // hook'u test/başka bağlamda toast'sız kurmak mümkün kalsın.
  showToast?: (msg: string, type: any) => void;
}

/**
 * MCP onay isteği için sanal mesaj ID'si (gerçek chat mesajına bağlı değil).
 *
 * DIŞARI AÇIK olmasının sebebi ölçülmüş bir arıza sınıfı: ChatPanel bu değeri
 * `-999` diye ELLE tekrar ediyordu ve `pendingFix` dalı hiç yazılmamıştı. Bu
 * depodaki arızaların ortak biçimi "birbiriyle uyuşması gereken iki yer
 * uyuşmuyor"; sabiti tek yerden okutmak o sınıfın bu örneğini kapatıyor.
 */
export const MCP_MSG_ID = -999;

/** Yoklama aralığı (ms). Gerekçesi ve ölçümü aşağıdaki useEffect'te. */
const POLL_INTERVAL_MS = 1000;

/**
 * Kaç ardışık başarısız yoklamadan sonra kullanıcı uyarılır.
 *
 * 1 değil, çünkü backend yeniden başlarken bir-iki yoklama düşer ve her
 * düşüşte toast basmak gürültüdür. Sonsuz da değil: yoklama artık koşulsuz
 * çalıştığı için kalıcı bir 401/403 (yanlış token) hiçbir iz bırakmadan
 * ürünün onay yolunu tamamen ölü hale getiriyordu — dış denetim bulgusu
 * `silent-approval-delivery-failure` (2026-07-29). 5 × 1 sn = 5 sn, yani
 * geçici kesinti sessiz kalıyor, kalıcı arıza görünür oluyor.
 */
const POLL_FAILURE_ALERT_AFTER = 5;

/** Unity araç çağrısını kartta okunacak tek bir metne indirger.
 *
 * Onay kartının işi kullanıcıya NE onayladığını göstermek; yalnız araç adını
 * göstermek (`manage_gameobject`) "neyi siliyorum" sorusunu cevapsız bırakır.
 * Parametreler bu yüzden yazılıyor ama KIRPILIYOR: `execute_code` bütün bir C#
 * bloğu taşıyabiliyor ve kırpılmamış hali kartı ekrandan taşırır — okunamayan
 * bir kart, okunmadan onaylanan bir karttır.
 */
export const unityOzeti = (tool: string, params: any): string => {
  const satirlar = Object.entries(params || {})
    // `unity_instance` yönlendirme detayı, kullanıcının kararına girmiyor.
    .filter(([anahtar]) => anahtar !== 'unity_instance')
    .map(([anahtar, deger]) => {
      const metin = typeof deger === 'string' ? deger : JSON.stringify(deger);
      const kisa = metin && metin.length > 200 ? `${metin.slice(0, 200)}…` : metin;
      return `${anahtar}: ${kisa}`;
    });
  return satirlar.length ? `${tool}\n${satirlar.join('\n')}` : tool;
};

/**
 * Gate'in workspace'i ile üründe açık workspace uyuşmuyor mu?
 *
 * Ayrı fonksiyon ve dışarı açık: kararı hem hook (uyarı üretmek için) hem de
 * kartı çizen bileşen (banner rengi için) veriyor; iki yerde ayrı ayrı yazılan
 * bir koşul bu depoda tekrar tekrar ayrıştı.
 *
 * Bilinmeyen durum `false` döner — "uyuşmuyor" DEĞİL. Ne gate'in workspace'i
 * boşken ne de üründe workspace açık değilken bir çelişki KANITLANMIŞ olmuyor;
 * bilinmeyeni "uyuşmazlık" saymak, gerçek uyuşmazlığı fark edilmez kılacak
 * kadar çok yanlış uyarı üretirdi. Bilinmezliği kullanıcıya ayrıca banner
 * söylüyor (workspace yazılı, "açık olan" satırı yoksa bilinmiyor demek).
 */
export const workspaceMismatch = (
  gateWorkspace: string | null | undefined,
  openWorkspace: string | null | undefined,
): boolean => {
  if (!gateWorkspace || !openWorkspace) return false;
  return gateWorkspace.replace(/\/+$/, '') !== openWorkspace.replace(/\/+$/, '');
};

export const useMCPApproval = ({
  API,
  enabled,
  workspacePath,
  setPendingGenFiles,
  setPendingDelete,
  setPendingCommand,
  setPendingFix,
  showToast,
}: MCPApprovalHookParams) => {
  const [activeGate, setActiveGate] = useState<McpActiveGate | null>(null);
  const pollingRef = useRef<NodeJS.Timeout | null>(null);
  /**
   * `activeGate`'in ref ikizi. State değil ref okunuyor çünkü `poll` bir
   * `useCallback` ve state'i bağımlılığına alsaydı her kart açılışında yeni
   * kimlik alıp effect'i yeniden kurardı (interval sıfırlanır, mount anındaki
   * `poll()` tekrar koşardı). Ref, kararın SENKRON okunmasını da garanti
   * ediyor: iki yoklama üst üste bindiğinde ikincisi birincinin açtığı kartı
   * görmek zorunda.
   */
  const activeGateRef = useRef<McpActiveGate | null>(null);
  /** Açık kartın state'ini geri alan fonksiyon. Bkz `dismissActive`. */
  const clearActiveCardRef = useRef<(() => void) | null>(null);
  const failStreakRef = useRef(0);
  const alertedRef = useRef(false);

  /**
   * Açık kartı kaldırır ve sırayı serbest bırakır.
   *
   * Neden kartın state'ini TEK bir kayıtlı fonksiyonla temizliyoruz da dördünü
   * birden `null`'lamıyoruz: `pendingFix`/`pendingGenFiles` mesaja bağlı (MCP
   * dışı) akışta da kullanılıyor; hepsini körlemesine temizlemek kullanıcının
   * sohbette gördüğü ilgisiz bir kartı kapatırdı.
   */
  const dismissActive = useCallback(() => {
    clearActiveCardRef.current?.();
    clearActiveCardRef.current = null;
    activeGateRef.current = null;
    setActiveGate(null);
  }, []);

  const poll = useCallback(async () => {
    if (!API) return;

    let pending: Record<string, any>;
    try {
      const res = await axios.get(`${API}/mcp-pending`);
      pending = res.data?.pending ?? {};
      failStreakRef.current = 0;
      alertedRef.current = false;
    } catch (err) {
      // Sessiz yutmak yok: yoklama artık koşulsuz koştuğu için kalıcı bir hata
      // (yanlış token → her saniye 401) hiçbir iz bırakmadan onay yolunu ölü
      // hale getiriyordu. Kullanıcı kartı beklerken köprü 180 sn sonra
      // reddediyor ve ekranda tek bir işaret bile olmuyordu.
      failStreakRef.current += 1;
      // Geliştirici sinyali HER hatada, kullanıcı sinyali eşikten sonra. Ayrım
      // kasıtlı: konsol ucuz ve teşhis için ilk hatadan itibaren gerekli, toast
      // ise her saniye tekrarlanırsa bilgi olmaktan çıkıp gürültü olur.
      console.warn(`[MCP] /mcp-pending erişilemiyor (${failStreakRef.current}. hata)`, err);
      if (failStreakRef.current >= POLL_FAILURE_ALERT_AFTER && !alertedRef.current) {
        alertedRef.current = true;  // her saniye tekrar basmasın
        showToast?.(
          'MCP onay isteklerine ulaşılamıyor. Bir onay kartı beklediyseniz ' +
          'gelmeyecek ve istek zaman aşımıyla reddedilecek.',
          'error',
        );
      }
      return;
    }

    // Açık bir kart varsa yenisini ALMA — kuyruk backend'de bekler.
    if (activeGateRef.current) {
      // Tek istisna: açık kartın gate'i backend'de artık yoksa (TTL süpürdü ya
      // da karar başka bir yoldan verildi) kart ZOMBİ demektir. Temizlenmezse
      // `activeGateRef` sonsuza dek dolu kalır ve BÜTÜN sonraki kartlar bloke
      // olurdu — kaldırdığımız kilidin daha kötüsü.
      if (!(activeGateRef.current.gateId in pending)) dismissActive();
      return;
    }

    for (const [gateId, req] of Object.entries(pending)) {
      const { tool, params, workspace_path: gateWorkspace } = req as {
        tool: string; params: any; workspace_path?: string;
      };

      // Kartı çizen tarafın gate kimliğini ve workspace'i okuyacağı TEK kayıt.
      // Eskiden kimlik `window.__mcpWriteGate` global'inde duruyordu ve iki
      // bekleyen yazma aynı slotu paylaşıyordu: "Yeni dosya" kartına basmak
      // ÖTEKİ isteğin gate'ini onaylıyordu (dış denetim: `approval-gate-
      // misbinding`, HIGH). Kimliği kartın kendi kaydında taşımak o sınıfı
      // bir örnek yamayarak değil kökten kapatıyor.
      const gate: McpActiveGate = { gateId, tool, workspacePath: gateWorkspace || '' };
      activeGateRef.current = gate;
      setActiveGate(gate);

      if (tool === 'write_file') {
        const { path, content, original } = params;
        if (!original) {
          // Yeni dosya → FileCreationApproval
          const file: PendingFile = {
            name: path.split('/').pop() || path,
            code: content,
            suggestedPath: path,
            originalCode: '',
          };
          clearActiveCardRef.current = () => setPendingGenFiles(null);
          setPendingGenFiles({ files: [file], messageId: MCP_MSG_ID });
        } else {
          // Değişiklik → DiffViewer
          clearActiveCardRef.current = () => setPendingFix(null);
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
        clearActiveCardRef.current = () => setPendingDelete(null);
        setPendingDelete({ path: params.path, messageId: MCP_MSG_ID });
      } else if (tool === 'bash') {
        clearActiveCardRef.current = () => setPendingCommand(null);
        setPendingCommand({ command: params.command, gateId, messageId: MCP_MSG_ID });
      } else {
        // Unity araçları ve tanınmayan her şey: TEK bir genel kart.
        //
        // ⚠️ Burası eskiden kartı hiç çizmiyor, gate'i bırakıp köprünün zaman
        // aşımına terk ediyordu. K1 kapısı kurulunca o dal ürünü kullanılamaz
        // hale getirdi: kütükteki 45 Unity aracının HİÇBİRİ yukarıdaki üç
        // eski adla (`write_file`/`delete_file`/`bash`) eşleşmiyor, yani adım
        // modunda her Unity yazması 180 sn bekleyip sessizce reddediliyordu ve
        // kullanıcıya hiç sorulmuyordu. Dış denetim bunu HIGH olarak buldu.
        //
        // Genel kart bilerek "tanınmayan"ı da kapsıyor: yeni bir araç
        // eklendiğinde kart kaybolmasın. Kartsız kalmak, kapının kullanıcıya
        // ulaşmadığı ve isteğin sessizce öldüğü hal demek.
        clearActiveCardRef.current = () => setPendingCommand(null);
        setPendingCommand({
          command: unityOzeti(tool, params),
          gateId,
          messageId: MCP_MSG_ID,
          kind: 'unity',
        });
      }
      break;  // aynı anda tek kart
    }
  }, [API, dismissActive, showToast, setPendingGenFiles, setPendingDelete, setPendingCommand, setPendingFix]);

  /**
   * Yoklamayı başlat/durdur. Koşulsuz açmanın maliyeti ÖLÇÜLDÜ (2026-07-29): rota
   * katmanında `/mcp-pending` çağrı başına **0,174 ms** (2000 çağrı / 0,347 sn,
   * TestClient üzerinden — yani gerçek TCP ve renderer maliyeti HARİÇ, bu bir
   * alt sınır). 1 sn aralıkta bu tek çekirdeğin ~%0,017'si. Eski koddaki
   * "idle'da CPU harcama" gerekçesi bu ölçümün karşısında duramıyor; karşılığı
   * ise kartın 8 sağlayıcıda hiç gelmemesiydi.
   *
   * SSE (kod yorumlarının iddia ettiği ama var olmayan çözüm) BİLEREK
   * seçilmedi: `EventSource` özel başlık gönderemiyor, dolayısıyla
   * `X-Session-Token` sorguya taşınırdı — sırrı URL'den başlığa taşıyan karar
   * (unity-mcp yerel auth) tam tersi yöndeydi. Geri almak için sebep yok.
   */
  useEffect(() => {
    if (!API || !enabled) {
      if (pollingRef.current) { clearInterval(pollingRef.current); pollingRef.current = null; }
      return;
    }
    // İlk yoklama beklemeden: hook mount olmadan önce açılmış bir gate varsa
    // (köprü ürün penceresinden bağımsız çalışıyor) kart bir tam saniye geç
    // gelirdi. Açık kart kontrolü tekrar işlemeyi zaten engelliyor.
    void poll();
    pollingRef.current = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      if (pollingRef.current) { clearInterval(pollingRef.current); pollingRef.current = null; }
    };
  }, [API, enabled, poll]);

  /**
   * Karar verildikten (ya da kart kapatıldıktan) sonra çağrılır: kartı kaldırır
   * ve sıradaki isteğin gösterilmesine izin verir. Kararı GÖNDERMEZ — gönderme
   * kartın kendi handler'ında, çünkü her kartın toast metni farklı.
   */
  const resolveActiveGate = useCallback(() => { dismissActive(); }, [dismissActive]);

  /*
   * ⚠️ BURADA ESKİDEN DÖRT RESPONDER + `respond` VARDI, SİLİNDİLER (2026-07-29).
   *
   * `approveMCPFile`, `rejectMCPFile`, `approveMCPDelete`, `rejectMCPDelete` —
   * dördünün de ÜRÜNDE tek bir çağıranı yoktu (dış denetim
   * `test-only-routing-api-divergence`, depo çapında çağrı izlemesiyle
   * doğrulandı). Kartlar kararı `McpApprovalCards` içinden `postMcpDecision`
   * ile gönderiyor: farklı transport (fetch/axios), farklı sözleşme, farklı
   * kilit ömrü.
   *
   * Silinmelerinin sebebi düzen değil ÖLÇÜM: `approval-gate-feedback.test.ts`
   * bu ölü yolu MCP kart teslimi sanıp sınıyordu, dolayısıyla 230 testin hepsi
   * yeşilken gerçek kart yolundaki `stale-decision-latch` (kullanıcının gördüğü
   * ret yutuluyor, komut çalışıyor) hiç görünmüyordu. İki sözleşmeyi paralel
   * tutmak bu depodaki arızaların ortak biçimi; ikincisini silmek tek çözüm.
   */

  // `poll` dışarı da veriliyor: polling'in kendisi zamanlayıcıya bağlı, ama
  // "gate kimliği kartla birlikte taşınıyor mu" sorusu zamanlayıcıdan bağımsız
  // bir DOĞRULUK sorusu ve deterministik ölçülebilmeli.
  return {
    poll,
    activeGate,
    /** Gate'in workspace'i üründe açık olandan farklı mı (bilinmiyorsa false). */
    gateWorkspaceMismatch: workspaceMismatch(activeGate?.workspacePath, workspacePath),
    openWorkspacePath: workspacePath,
    resolveActiveGate,
  };
};
