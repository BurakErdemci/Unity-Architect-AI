/**
 * Onay kartlarının backend yanıtını gerçekten OKUDUĞUNU sınar.
 *
 * Arıza (ölçüldü 2026-07-28): backend onay kapısı bir süre sonra gate kaydını
 * düşürüyor ve geç gelen onaya `{"status":"gate_not_found"}` dönüyor. Frontend
 * yanıt gövdesini hiç okumadan kartı kapatıyordu — kullanıcı onayladığını
 * sanırken işlem çoktan reddedilmişti. Sessiz veri kaybı.
 *
 * Bu testler timeout süresinden BAĞIMSIZ: pencere ne kadar büyürse büyüsün,
 * kaçırıldığında kullanıcının bunu görmesi gerekir.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'

import { useChat } from '../renderer/hooks/home/useChat'
import { useMCPApproval } from '../renderer/hooks/home/useMCPApproval'
import { postMcpDecision, decisionToast, gateFailure } from '../renderer/hooks/home/gateResponse'
import axios from 'axios'

vi.mock('axios', () => {
  const post = vi.fn()
  const get = vi.fn()
  return { default: { post, get }, post, get }
})

const mockedAxios = axios as unknown as { post: ReturnType<typeof vi.fn>; get: ReturnType<typeof vi.fn> }

const API = 'http://127.0.0.1:8000'

/** fetch yanıtını taklit eder: HTTP durumu + JSON gövdesi ayrı ayrı verilebilir. */
const fetchResponse = (body: unknown, httpStatus = 200) => ({
  ok: httpStatus >= 200 && httpStatus < 300,
  status: httpStatus,
  json: async () => body,
})

const setupChat = () => {
  const showToast = vi.fn()
  const { result } = renderHook(() =>
    useChat(
      API,
      { id: 1, sessionToken: 'tok' } as any,
      { provider_type: 'api' } as any,
      null,
      showToast,
      vi.fn(),
      (n: string) => n,
    ),
  )
  return { result, showToast }
}

beforeEach(() => {
  vi.restoreAllMocks()
  mockedAxios.post.mockReset()
  mockedAxios.get.mockReset()
  vi.spyOn(console, 'warn').mockImplementation(() => {})
  window.localStorage.clear()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('approveCommand — kayıp gate sessizce yutulmaz', () => {
  it('gate_not_found gelince kullanıcı uyarılır', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(fetchResponse({ status: 'gate_not_found' })))
    const { result, showToast } = setupChat()

    await act(async () => { await result.current.approveCommand('g1', true) })

    expect(showToast).toHaveBeenCalledTimes(1)
    const [msg, type] = showToast.mock.calls[0]
    expect(String(msg).length).toBeGreaterThan(0)
    expect(['warning', 'error']).toContain(type)
  })

  it('REDDET yolunda da (approved=false) aynı uyarı çıkar', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(fetchResponse({ status: 'gate_not_found' })))
    const { result, showToast } = setupChat()

    await act(async () => { await result.current.approveCommand('g1', false) })

    expect(showToast).toHaveBeenCalledTimes(1)
  })

  it('non-2xx HTTP yanıtı da uyarı üretir', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(fetchResponse({ detail: 'nope' }, 503)))
    const { result, showToast } = setupChat()

    await act(async () => { await result.current.approveCommand('g1', true) })

    expect(showToast).toHaveBeenCalledTimes(1)
  })

  it('ağ hatası (fetch throw) uyarı üretir', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('ECONNREFUSED')))
    const { result, showToast } = setupChat()

    await act(async () => { await result.current.approveCommand('g1', true) })

    expect(showToast).toHaveBeenCalledTimes(1)
  })

  it('BAŞARILI yolda gereksiz uyarı ÇIKMAZ', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(fetchResponse({ status: 'ok', approved: true })))
    const { result, showToast } = setupChat()

    await act(async () => { await result.current.approveCommand('g1', true) })

    expect(showToast).not.toHaveBeenCalled()
  })

  it('kart her durumda kapanır — asılı kalmaz', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(fetchResponse({ status: 'gate_not_found' })))
    const { result } = setupChat()

    act(() => { result.current.setPendingCommand({ command: 'rm -rf /', gateId: 'g1', messageId: 1 }) })
    expect(result.current.pendingCommand).not.toBeNull()

    await act(async () => { await result.current.approveCommand('g1', true) })
    expect(result.current.pendingCommand).toBeNull()
  })
})

describe('answerQuestion — kayıp gate sessizce yutulmaz', () => {
  it('gate_not_found gelince kullanıcı uyarılır', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(fetchResponse({ status: 'gate_not_found' })))
    const { result, showToast } = setupChat()

    await act(async () => { await result.current.answerQuestion('q1', { 'Soru?': 'A' }) })

    expect(showToast).toHaveBeenCalledTimes(1)
  })

  it('invalid (gövde şeması reddedildi) da uyarı üretir', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(fetchResponse({ status: 'invalid', error: 'answers (dict) gerekli.' })))
    const { result, showToast } = setupChat()

    await act(async () => { await result.current.answerQuestion('q1', {} as any) })

    expect(showToast).toHaveBeenCalledTimes(1)
  })

  it('BAŞARILI yolda gereksiz uyarı ÇIKMAZ', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(fetchResponse({ status: 'ok' })))
    const { result, showToast } = setupChat()

    await act(async () => { await result.current.answerQuestion('q1', { 'Soru?': 'A' }) })

    expect(showToast).not.toHaveBeenCalled()
  })

  it('kart her durumda kapanır', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(fetchResponse({ status: 'gate_not_found' })))
    const { result } = setupChat()

    act(() => { result.current.setPendingQuestion({ questions: [], gateId: 'q1', messageId: 1 }) })
    expect(result.current.pendingQuestion).not.toBeNull()

    await act(async () => { await result.current.answerQuestion('q1', { 'Soru?': 'A' }) })
    expect(result.current.pendingQuestion).toBeNull()
  })
})

describe('useMCPApproval.respond — kayıp gate sessizce yutulmaz', () => {
  const setupMCP = () => {
    const showToast = vi.fn()
    const { result } = renderHook(() =>
      useMCPApproval({
        API,
        enabled: false,
        workspacePath: '/ws',
        setPendingGenFiles: vi.fn(),
        setPendingDelete: vi.fn(),
        setPendingCommand: vi.fn(),
        setPendingFix: vi.fn(),
        showToast,
      }),
    )
    return { result, showToast }
  }

  it('gate_not_found gelince kullanıcı uyarılır', async () => {
    mockedAxios.post.mockResolvedValue({ data: { status: 'gate_not_found' } })
    const { result, showToast } = setupMCP()

    await act(async () => { await result.current.approveMCPFile('m1') })

    expect(showToast).toHaveBeenCalledTimes(1)
  })

  it('reddet yolunda da uyarı çıkar', async () => {
    mockedAxios.post.mockResolvedValue({ data: { status: 'gate_not_found' } })
    const { result, showToast } = setupMCP()

    await act(async () => { await result.current.rejectMCPFile('m1') })

    expect(showToast).toHaveBeenCalledTimes(1)
  })

  it('ağ hatası uyarı üretir', async () => {
    mockedAxios.post.mockRejectedValue(new Error('ECONNREFUSED'))
    const { result, showToast } = setupMCP()

    await act(async () => { await result.current.approveMCPFile('m1') })

    expect(showToast).toHaveBeenCalledTimes(1)
  })

  it('BAŞARILI yolda gereksiz uyarı ÇIKMAZ', async () => {
    mockedAxios.post.mockResolvedValue({ data: { status: 'ok' } })
    const { result, showToast } = setupMCP()

    await act(async () => { await result.current.approveMCPFile('m1') })

    expect(showToast).not.toHaveBeenCalled()
  })

  it('silme onayında gate yoksa istek hiç gitmez, uyarı da çıkmaz', async () => {
    const { result, showToast } = setupMCP()

    // Gate kimliği artık `window` global'inde değil kartın kendi kaydında
    // taşınıyor; "gate yok" durumu boş string ile ifade ediliyor.
    await act(async () => { await result.current.approveMCPDelete('') })

    expect(mockedAxios.post).not.toHaveBeenCalled()
    expect(showToast).not.toHaveBeenCalled()
  })
})

/**
 * ChatPanel'deki sekiz doğrudan çağrı yerinin ortak motoru. Oradaki hata sadece
 * "sessizce yut" değil, "yuttuktan sonra YEŞİL başarı toast'ı bas"tı.
 */
describe('postMcpDecision + decisionToast — yanlış başarı iddiası üretmez', () => {
  it('gate_not_found → başarı mesajı DEĞİL uyarı gösterilir', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(fetchResponse({ status: 'gate_not_found' })))

    const failure = await postMcpDecision(API, 'g1', true, 'tok')
    expect(failure).not.toBeNull()

    const toast = decisionToast(failure, '✅ Dosya oluşturuldu')
    expect(toast.type).not.toBe('success')
    expect(toast.message).not.toContain('✅')
  })

  it('non-2xx → uyarı gösterilir', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(fetchResponse({ detail: 'x' }, 401)))
    const failure = await postMcpDecision(API, 'g1', false, 'tok')
    expect(failure).not.toBeNull()
    expect(decisionToast(failure, '🗑️ Dosya silindi').type).toBe('error')
  })

  it('ağ hatası → uyarı gösterilir', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))
    const failure = await postMcpDecision(API, 'g1', true, 'tok')
    expect(failure).not.toBeNull()
  })

  it('TESLİMAT yolunda mesaj AYNEN korunur — ama tip "success" DEĞİL', async () => {
    // ⚠️ Bu test 2026-07-29'da SIKILAŞTIRILDI. Eskiden
    // `toEqual({..., type: 'success'})` bekliyordu; dış doğrulama turu
    // (`mcp-write-premature-success`) o beklentinin kendisinin hatalı olduğunu
    // gösterdi: `failure === null` yalnız backend'in onayı KAYDETTİĞİNİ
    // kanıtlıyor, dosya işlemi bundan sonra köprüde oluyor ve düşebiliyor.
    // Ölçülen yol: hedefin üst dizini normal bir dosyaysa `os.makedirs`
    // FileExistsError atıyor, dosya diske hiç yazılmıyor.
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(fetchResponse({ status: 'ok' })))

    const failure = await postMcpDecision(API, 'g1', true, 'tok')
    expect(failure).toBeNull()

    const toast = decisionToast(failure, 'Onayınız gönderildi — dosya yazılıyor')
    expect(toast).toEqual({ message: 'Onayınız gönderildi — dosya yazılıyor', type: 'info' })
  })

  it('teslimat mesajı hiçbir çağrı yerinden "success" yapılamaz', async () => {
    // `successType` parametresi kaldırıldı: dursaydı tek bir çağrı yeri
    // `'success'` geçerek kapıyı geri açardı. Bu test o parametrenin geri
    // gelmesini de yakalar (TS derlemesi + davranış).
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(fetchResponse({ status: 'ok' })))
    const failure = await postMcpDecision(API, 'g1', false, 'tok')
    expect(decisionToast(failure, 'Komut iptal edildi')).toEqual({
      message: 'Komut iptal edildi', type: 'info',
    })
    expect((decisionToast as (...a: any[]) => unknown).length).toBe(2)
  })

  it('ağ hatasında belirsizlik postMcpDecision üzerinden de taşınır', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))
    const failure = await postMcpDecision(API, 'g1', true, 'tok')
    expect(failure?.uncertain).toBe(true)
  })

  it('gövde JSON değilse (2xx + bozuk gövde) yine başarı SAYILMAZ', () => {
    // Beyaz liste sözleşmesi: yalnız status==='ok' başarıdır. Kara liste
    // kullansaydık backend yeni bir başarısızlık durumu eklediğinde sessizce
    // başarı sayılırdı — düzelttiğimiz hatanın aynısı geri gelirdi.
    expect(gateFailure('mcp', { httpOk: true, httpStatus: 200, body: undefined })).not.toBeNull()
    expect(gateFailure('mcp', { httpOk: true, httpStatus: 200, body: { status: 'yepyeni_hata' } })).not.toBeNull()
  })
})

/**
 * Dış denetim bulgusu (2026-07-28): POST backend tarafından İŞLENDİKTEN SONRA
 * yanıt yolda kaybolursa `fetch` yine istisna atar. UI bunu kesin biçimde
 * "sunucuya ulaşmadı, işlem YAPILMADI — tekrar deneyin" diye raporluyordu.
 * Komut gerçekte çalışmış olabilir; kullanıcı tekrar gönderip aynı komutu İKİ
 * KEZ çalıştırabilir.
 *
 * Önceki düzeltme bir aşırı iddiayı (sessizce başarı say) tersiyle (kesinlikle
 * başarısız say) değiştirmişti. İkisi de yanlış: elde olan bilgi "başarısız"
 * değil, "BİLİNMİYOR". Bu blok üç durumun BİRBİRİNDEN AYIRT EDİLEBİLİR olmasını
 * ölçüyor — üçünün de mesaj üretmesi yetmez.
 */
describe('gateFailure — belirsiz teslimat kesin başarısızlıktan ayrılır', () => {
  /**
   * "İşlem yapılmadı" iddiası mesajda var mı?
   *
   * Neden düz `/yapılmadı/i` DEĞİL: JS'in `i` bayrağı basit case-folding yapıyor
   * ve noktasız `ı` (U+0131) ile ASCII `I`'yı EŞLEŞTİRMİYOR — mesaj "İşlem
   * YAPILMADI" yazdığı için regex sessizce hiçbir şey bulmuyordu (bu testi
   * yazarken ölçüldü). `tr` yerelinde küçültmek doğru eşlemeyi (`I` → `ı`) yapar.
   */
  const yapilmadiIddiasi = (m: string) => m.toLocaleLowerCase('tr').includes('yapılmadı')

  /** Yanıt ALINDI, backend gate'i bulamadı: işlemin yapılmadığı KESİN. */
  const kesin = () => gateFailure('command', {
    httpOk: true, httpStatus: 200, body: { status: 'gate_not_found' },
  })
  /** Yanıt HİÇ alınamadı: işlemin yapılıp yapılmadığı bilinmiyor. */
  const belirsiz = () => gateFailure('command', {
    httpOk: false, error: new Error('ECONNREFUSED'),
  })

  it('ağ istisnası belirsiz olarak işaretlenir', () => {
    expect(belirsiz()?.uncertain).toBe(true)
  })

  it('belirsiz mesaj "işlem yapılmadı" DEMEZ — yapılmış olabilir', () => {
    expect(yapilmadiIddiasi(belirsiz()!.message)).toBe(false)
  })

  it('belirsiz mesaj kullanıcıyı körlemesine tekrar göndermeye çağırmaz', () => {
    // "tekrar deneyin" tek başına, çift çalıştırmanın tam olarak nedeni.
    // Beklenti: önce durum kontrolü istensin.
    expect(belirsiz()!.message).toMatch(/kontrol/i)
  })

  it('yanıt alınmış başarısızlık KESİN kalır: belirsiz işaretlenmez', () => {
    // Karşı yön. Her şeyi "belirsiz" saymak, çözdüğümüz sorunun aynadaki hâli
    // olurdu: gerçekten yapılmamış bir işlem için kullanıcı boşuna durum arar.
    expect(kesin()?.uncertain).toBeFalsy()
    expect(yapilmadiIddiasi(kesin()!.message)).toBe(true)
  })

  it('iki durum kullanıcıya AYNI cümleyi göstermez', () => {
    // Testin asıl noktası. İkisi de mesaj üretiyor diye geçen bir test,
    // ayrımın var olduğunu ölçmezdi.
    expect(belirsiz()!.message).not.toBe(kesin()!.message)
  })

  it("status==='ok' hâlâ sessiz — yeni durum başarı yolunu kirletmedi", () => {
    expect(gateFailure('command', { httpOk: true, httpStatus: 200, body: { status: 'ok' } })).toBeNull()
    expect(gateFailure('mcp', { httpOk: true, httpStatus: 200, body: { status: 'ok' } })).toBeNull()
  })

  it('non-2xx yanıt da KESİN başarısızlıktır (yanıt alınmıştır)', () => {
    // Backend yerel (127.0.0.1) ve araya proxy girmiyor: 401/503 doğrudan
    // FastAPI'nin kendi reddi, yani istek işlenmedi. Bunu belirsiz saymak
    // bilgiyi atmak olurdu.
    const f = gateFailure('question', { httpOk: false, httpStatus: 401, body: { detail: 'x' } })
    expect(f?.uncertain).toBeFalsy()
    expect(yapilmadiIddiasi(f!.message)).toBe(true)
  })
})

// ── 2xx + sonuç okunamadı: BELİRSİZ, kesin başarısızlık değil ────────────────
//
// Dış denetim (2026-07-28) `fetch` istisnası dalını belirsize çevirtti, ama bu
// dal "İşlem yapılmadı" demeye devam ediyordu — kapattığımız sınıfın ikinci
// yolu. 2xx alındıysa handler isteği İŞLEMİŞTİR; okunamayan şey sonuçtur.
describe('2xx alındı ama sonuç okunamadı', () => {
  it('gövde ayrıştırılamadığında kesin başarısızlık DEĞİL, belirsiz döner', () => {
    const f = gateFailure('command', { httpOk: true, httpStatus: 200, body: undefined });
    expect(f).not.toBeNull();
    expect(f!.uncertain).toBe(true);
    expect(f!.type).toBe('warning');
    expect(f!.message).not.toMatch(/İşlem yapılmadı/);
    expect(f!.message).toMatch(/BİLİNMİYOR/);
  });

  it('tanınmayan bir durum da belirsizdir ama BAŞARI sayılmaz', () => {
    // Beyaz liste sözleşmesi korunuyor: yalnız 'ok' başarıdır.
    const f = gateFailure('command', { httpOk: true, httpStatus: 200, body: { status: 'expired' } });
    expect(f).not.toBeNull();          // başarı DEĞİL
    expect(f!.uncertain).toBe(true);   // ama "yapılmadı" da denmiyor
    expect(f!.message).toMatch(/expired/);
  });

  it('karşı yön: bilinen kesin başarısızlıklar belirsize KAÇMAZ', () => {
    // gate_not_found ve invalid'de sunucu işlemin yapılmadığını SÖYLÜYOR;
    // onları belirsize katlamak elimizdeki bilgiyi atmak olurdu.
    for (const status of ['gate_not_found', 'invalid']) {
      const f = gateFailure('command', { httpOk: true, httpStatus: 200, body: { status } });
      expect(f!.uncertain).toBeFalsy();
    }
    const nonOk = gateFailure('command', { httpOk: false, httpStatus: 503 });
    expect(nonOk!.uncertain).toBeFalsy();
  });

  it('başarı yolu hâlâ sessiz', () => {
    expect(gateFailure('command', { httpOk: true, httpStatus: 200, body: { status: 'ok' } })).toBeNull();
  });
});
