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
  /**
   * Teslimatın GERÇEKLEŞİP gerçekleşmediği bilinmiyor mu?
   *
   * `false`/tanımsız = kesin başarısızlık: sunucudan bir yanıt ALINDI ve o yanıt
   * işlemin yapılmadığını söylüyor.
   * `true` = yanıt hiç alınamadı; işlem yapılmış da olabilir yapılmamış da.
   *
   * Neden ayrı bir alan ve neden mesaja gömülmedi: çağrı yerlerinin bu ayrımı
   * programatik olarak görmesi gerekiyor (ör. otomatik yeniden gönderme ASLA
   * belirsiz durumda yapılmamalı). Mesajı ayrıştırmak, uyuşması gereken ikinci
   * bir yer üretirdi.
   */
  uncertain?: boolean;
}

const readStatus = (body: unknown): string | null => {
  if (typeof body === 'object' && body !== null && 'status' in body) {
    const s = (body as { status?: unknown }).status;
    return typeof s === 'string' ? s : null;
  }
  return null;
};

/**
 * ÜÇ durum döner, iki değil:
 *   null                      → teslimat başarılı (yanıt alındı, `status === 'ok'`)
 *   { uncertain: true, … }    → yanıt HİÇ alınamadı; işlem yapılmış olabilir
 *   { uncertain: yok, … }     → yanıt alındı ve işlemin yapılmadığı kesin
 *
 * Üçüncü durumu ikinciye katlamak, kanıtı olmayan bir iddiadır ve kullanıcıyı
 * aynı komutu iki kez çalıştırmaya iter — bu tam olarak 2026-07-28 bulgusuydu.
 *
 * Sözleşme kasıtlı olarak "beyaz liste": yalnız `status === 'ok'` başarıdır.
 * Backend ileride yeni bir başarısızlık durumu eklerse (kara liste kullansaydık)
 * sessizce başarı sayılırdı — düzelttiğimiz hatanın aynısı geri gelirdi.
 */
export function gateFailure(action: GateAction, delivery: GateDelivery): GateFailure | null {
  const label = ACTION_LABELS[action];

  // BELİRSİZ dal — üç durumun ortadakisi.
  //
  // Dış denetim bulgusu (2026-07-28): `fetch` istisnası "istek gitmedi" ANLAMINA
  // GELMEZ. POST backend tarafından işlendikten SONRA yanıt yolda kaybolursa
  // (süreç düştü, soket koptu, kullanıcı pencereyi kapattı) `fetch` yine hata
  // verir. Buradaki eski mesaj kesin biçimde "İşlem yapılmadı — tekrar deneyin"
  // diyordu; komut gerçekte çalışmış olabilir ve kullanıcı tekrar gönderip aynı
  // komutu İKİ KEZ çalıştırabilirdi.
  //
  // Bir önceki düzeltme bir aşırı iddiayı (sessizce başarı say) tersiyle
  // (kesinlikle başarısız say) değiştirmişti; İKİSİ DE yanlış. Elde olan bilgi
  // "başarısız" değil, "bilinmiyor" — mesaj da tam olarak onu söylemeli ve
  // kullanıcıyı körlemesine tekrara değil önce DURUM KONTROLÜNE yönlendirmeli.
  //
  // Tip `warning`, `error` değil: kırmızı bir "başarısız" rozeti, kanıtımız
  // olmayan bir sonucu iddia etmenin görsel biçimi olurdu.
  if (delivery.error !== undefined && delivery.error !== null) {
    return {
      message:
        `${label} gönderildi ama sunucudan yanıt alınamadı (bağlantı hatası). ` +
        `ULAŞIP ULAŞMADIĞI BİLİNMİYOR — işlem yapılmış olabilir. Tekrar ` +
        `göndermeden önce durumu kontrol edin.`,
      type: 'warning',
      uncertain: true,
    };
  }

  // Buradan aşağısı KESİN başarısızlık: sunucudan bir yanıt alındı.
  //
  // Neden non-2xx belirsiz sayılmıyor: backend yerelde (127.0.0.1) ve araya
  // proxy/CDN girmiyor, yani 401/503 doğrudan FastAPI'nin kendi reddi
  // (`_check_token` → Backend/app/auth_utils.py:29). Yanıtı üreten kod, isteği
  // işlemeyi reddeden kodun kendisi — bunu "bilinmiyor" saymak elimizdeki
  // bilgiyi atmak olurdu ve kullanıcı boşuna durum arardı.
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

  // 2xx alındı ama sonuç OKUNAMADI — bu da BELİRSİZ, kesin başarısızlık değil.
  //
  // Buradaki eski metin "İşlem yapılmadı" diyordu ve bu, üstteki `fetch`
  // istisnası dalında kapattığımız aşırı-iddianın aynısıydı: sınıfı değil tek
  // yolu kapatmak. Elimizdeki bilgi şu — sunucu 2xx döndü, yani handler isteği
  // İŞLEDİ; okuyamadığımız şey sonucun kendisi. "Yapılmadı" demek, kanıtımız
  // olmayan bir sonucu iddia etmek ve kullanıcıyı aynı komutu ikinci kez
  // çalıştırmaya itmektir.
  //
  // İki alt durum da aynı sınıfta:
  //   status === null  → gövde JSON değil / `status` alanı yok (bozuk yanıt)
  //   status === "..." → tanınmayan bir durum (backend yeni bir durum eklemiş)
  // İkincisi beyaz liste sözleşmesini BOZMAZ: tanınmayan durum hâlâ "başarı
  // değil" sayılıyor, yalnız "başarısız" da denmiyor.
  const gorulen = status === null ? 'okunamadı' : `tanınmadı: ${status}`;
  return {
    message:
      `${label} gönderildi ve sunucu isteği aldı, ama sonuç ${gorulen}. ` +
      `İŞLEMİN YAPILIP YAPILMADIĞI BİLİNMİYOR — tekrar göndermeden önce ` +
      `durumu kontrol edin.`,
    type: 'warning',
    uncertain: true,
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
 *
 * Boş `gateId` de bir BAŞARISIZLIKTIR, "çağırma" değil. Çağrı yerleri bunu
 * `gateId ? await postMcpDecision(...) : null` diye yazıyordu; `null` bu
 * sözleşmede "teslim edildi" demek, yani hiçbir istek gitmeden başarı iddia
 * ediliyordu (ölçüldü 2026-07-29). Kararı burada vermek, aynı üçlemenin dört
 * çağrı yerinde tekrar edilmesini ve birinde unutulmasını da bitiriyor.
 */
export async function postMcpDecision(
  apiBase: string,
  gateId: string,
  approved: boolean,
  sessionToken: string,
): Promise<GateFailure | null> {
  // KESİN başarısızlık (`uncertain` yok): istek hiç kurulmadı, dolayısıyla
  // backend'in bunu işlemiş olma ihtimali yok. Belirsize katlamak kullanıcıyı
  // boşuna durum kontrolüne yollardı.
  if (!gateId) {
    return {
      message:
        `${ACTION_LABELS.mcp} iletilemedi: bu karta ait onay kimliği (gate id) yok, ` +
        `istek hiç gönderilmedi. İşlem YAPILMADI — isteği yeniden gönderin.`,
      type: 'error',
    };
  }
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
 * Kararın TESLİMATINI raporlar — işlemin SONUCUNU değil.
 *
 * Çağrı yerlerinin `if (failure) … else …` yazmasını beklemek, sekiz yerden
 * birinin unutulmasına açık kapı bırakıyordu; karar burada duruyor.
 *
 * Neden dönen tip artık `'success'` OLAMIYOR (dış doğrulama, 2026-07-29 —
 * `mcp-write-premature-success`): `failure === null` tek bir şeyi kanıtlıyor,
 * backend'in onayı KAYDETTİĞİNİ. Asıl dosya işlemi bundan SONRA, MCP köprüsü
 * kararı sorgulayınca `file_tools.write_file` içinde oluyor ve orada
 * başarısız olabiliyor — probe bunu ana ağaca karşı üretti: hedefin üst dizini
 * normal bir dosyaysa `os.makedirs` `FileExistsError` atıyor ve dosya diske
 * hiç yazılmıyor. Kart o anda "✅ Player.cs oluşturuldu" diyordu.
 *
 * Yeşil ✅ bir toast, kanıtımız olmayan bir SONUCU iddia etmenin görsel
 * biçimidir — `gateFailure`'ın `uncertain` dalında zaten kapattığımız aşırı
 * iddianın aynısı, ters yönde. Elimizdeki bilgi "oldu" değil "gönderildi",
 * mesaj da tam olarak onu söylemeli.
 *
 * ⚠️ `successType` parametresi KALDIRILDI, varsayılanı değiştirilmedi: parametre
 * dursaydı bir çağrı yeri `'success'` geçerek kapıyı tek satırda geri açardı ve
 * bu depodaki arızaların ortak şekli tam olarak "iki yer uyuşmuyor". Sonucu
 * GERÇEKTEN doğrulayan yollar (IPC `write-file` yanıtı okunan dal) bu
 * fonksiyondan geçmiyor; onlar `showToast(..., 'success')`'ı doğrudan çağırıyor
 * ve yeşil kalmayı hak ediyor.
 */
export function decisionToast(
  failure: GateFailure | null,
  deliveredMessage: string,
): { message: string; type: 'info' | 'warning' | 'error' } {
  if (failure) return { message: failure.message, type: failure.type };
  return { message: deliveredMessage, type: 'info' };
}
