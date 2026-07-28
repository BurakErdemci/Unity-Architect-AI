/**
 * Onay/soru kapısı (gate) yanıtlarının TEK yorumlayıcısı.
 *
 * Neden ayrı dosya: aynı "yanıtı okumadan kartı kapat" hatası üç ayrı yolda
 * vardı — komut onayı, AskUserQuestion cevabı ve MCP onayı. Yorumlama tek yerde
 * durmazsa biri düzeltilip diğeri unutuluyor; bu deponun 2026-07-28 bulgusu tam
 * olarak buydu.
 *
 * Neden bu düzeltme timeout ayarından bağımsız: backend gate'i bir süre sonra
 * DÜŞÜRÜYOR ve geç gelen onaya `{"status": "gate_not_found"}` dönüyor. Pencere
 * ne kadar büyütülürse büyütülsün kaçırılabilir; kaçırıldığında kullanıcının
 * bunu görmesi gerekir. Pencereyi büyütmek ile kaçırıldığında dürüst davranmak
 * birbirinin yerine geçmez.
 *
 * Backend'in döndürdüğü durumlar (Backend/app/routes/conversation_routes.py —
 * salt okundu):
 *   - /command-approval/{gate_id}      → {"status":"ok","approved":bool} | {"status":"gate_not_found"}   (:550, :551)
 *   - /question-answer/{gate_id}       → {"status":"ok"} | {"status":"invalid",...} | {"status":"gate_not_found"} (:563, :567, :568)
 *   - /mcp-approval-respond/{gate_id}  → {"status":"ok"} | {"status":"gate_not_found"}                   (:718, :721)
 * Ayrıca her üçü de `_check_token` çağırıyor; token yoksa/yanlışsa HTTP 503/401
 * atıyor (Backend/app/auth_utils.py:29) — yani non-2xx gerçek bir yol.
 */

export type GateAction = 'command' | 'question' | 'mcp';

/** Kullanıcıya "ne iletilmedi" diye söylerken kullanılacak ad. */
const ACTION_LABELS: Record<GateAction, string> = {
  command: 'Komut onayınız',
  question: 'Cevabınız',
  mcp: 'Onayınız',
};

/** Bir gate çağrısının ham sonucu. Transport'tan (fetch/axios) bağımsız. */
export interface GateDelivery {
  /** HTTP 2xx mi. fetch non-2xx'te throw ETMEZ, o yüzden ayrıca taşınır. */
  httpOk: boolean;
  httpStatus?: number;
  /** Ayrıştırılmış JSON gövdesi; ayrıştırılamadıysa undefined. */
  body?: unknown;
  /** Ağ hatası / istisna (varsa gövde anlamsızdır). */
  error?: unknown;
}

export interface GateFailure {
  message: string;
  type: 'warning' | 'error';
}

const readStatus = (body: unknown): string | null => {
  if (typeof body === 'object' && body !== null && 'status' in body) {
    const s = (body as { status?: unknown }).status;
    return typeof s === 'string' ? s : null;
  }
  return null;
};

/**
 * Teslimat başarılıysa null döner. Başarısızsa kullanıcıya gösterilecek mesaj.
 *
 * Sözleşme kasıtlı olarak "beyaz liste": yalnız `status === 'ok'` başarıdır.
 * Backend ileride yeni bir başarısızlık durumu eklerse (kara liste kullansaydık)
 * sessizce başarı sayılırdı — düzelttiğimiz hatanın aynısı geri gelirdi.
 */
export function gateFailure(action: GateAction, delivery: GateDelivery): GateFailure | null {
  const label = ACTION_LABELS[action];

  if (delivery.error !== undefined && delivery.error !== null) {
    return {
      message: `${label} sunucuya ULAŞMADI (bağlantı hatası). İşlem yapılmadı — tekrar deneyin.`,
      type: 'error',
    };
  }

  if (!delivery.httpOk) {
    const code = delivery.httpStatus ? ` (HTTP ${delivery.httpStatus})` : '';
    return {
      message: `${label} sunucu tarafından reddedildi${code}. İşlem yapılmadı.`,
      type: 'error',
    };
  }

  const status = readStatus(delivery.body);
  if (status === 'ok') return null;

  if (status === 'gate_not_found') {
    return {
      // Sebebi de yazıyoruz: kullanıcı "bastım ama olmadı"yı bir hataya değil
      // süre aşımına bağlayabilsin, ve isteği yeniden tetiklemesi gerektiğini
      // bilsin. Backend gate'i düşürdüğünde işlem zaten REDDEDİLMİŞ durumda.
      message: `${label} iletilemedi: istek zaman aşımına uğramış ve reddedilmiş. İşlem YAPILMADI — isteği yeniden gönderin.`,
      type: 'warning',
    };
  }

  if (status === 'invalid') {
    return { message: `${label} geçersiz bulundu. İşlem yapılmadı.`, type: 'error' };
  }

  return {
    message: `${label} iletilemedi (sunucu yanıtı: ${status ?? 'boş'}). İşlem yapılmadı.`,
    type: 'error',
  };
}

/**
 * `fetch` yanıtını GateDelivery'ye çevirir. Gövde JSON değilse (ör. HTML hata
 * sayfası) ayrıştırma hatası teslimatı başarısız SAYMAZ — httpOk zaten yanlışsa
 * mesajı o üretir; 2xx + bozuk gövde ise status okunamadığı için yine uyarı çıkar.
 */
export async function deliveryFromFetch(res: Response): Promise<GateDelivery> {
  let body: unknown;
  try {
    body = await res.json();
  } catch {
    body = undefined;
  }
  return { httpOk: res.ok, httpStatus: res.status, body };
}

/**
 * MCP onay kararını gönderir ve teslim edilmediyse mesajı döner (edildiyse null).
 *
 * ChatPanel'deki sekiz çağrı yeri bunu tek tek kuruyordu ve hepsi `.catch(() => {})`
 * ile yutuyordu; yutmanın da ötesinde ardından "✅ Dosya oluşturuldu" gibi bir
 * BAŞARI toast'ı basıyorlardı. Yani gate düştüğünde kullanıcıya sessizlik değil
 * yanlış bilgi veriliyordu — sessizlikten daha kötü.
 */
export async function postMcpDecision(
  apiBase: string,
  gateId: string,
  approved: boolean,
  sessionToken: string,
): Promise<GateFailure | null> {
  try {
    const res = await fetch(`${apiBase}/mcp-approval-respond/${gateId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Session-Token': sessionToken },
      body: JSON.stringify({ approved }),
    });
    return gateFailure('mcp', await deliveryFromFetch(res));
  } catch (err) {
    return gateFailure('mcp', { httpOk: false, error: err });
  }
}

/**
 * "Başarı mesajını ancak gerçekten başarılıysa göster" kuralını tek yerde tutar.
 * Çağrı yerlerinin `if (failure) … else …` yazmasını beklemek, sekiz yerden
 * birinin unutulmasına açık kapı bırakıyordu.
 */
export function decisionToast(
  failure: GateFailure | null,
  successMessage: string,
  successType: 'success' | 'info' = 'success',
): { message: string; type: 'success' | 'info' | 'warning' | 'error' } {
  if (failure) return { message: failure.message, type: failure.type };
  return { message: successMessage, type: successType };
}
