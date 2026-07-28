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
        loading: false,
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
    ;(window as any).__mcpDeleteGate = undefined

    await act(async () => { await result.current.approveMCPDelete() })

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

  it('BAŞARILI yolda başarı mesajı AYNEN korunur', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(fetchResponse({ status: 'ok' })))

    const failure = await postMcpDecision(API, 'g1', true, 'tok')
    expect(failure).toBeNull()

    const toast = decisionToast(failure, '✅ Dosya oluşturuldu')
    expect(toast).toEqual({ message: '✅ Dosya oluşturuldu', type: 'success' })
  })

  it('başarılı yolda "info" tipi de korunur (iptal mesajları için)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(fetchResponse({ status: 'ok' })))
    const failure = await postMcpDecision(API, 'g1', false, 'tok')
    expect(decisionToast(failure, 'Komut iptal edildi', 'info')).toEqual({
      message: 'Komut iptal edildi', type: 'info',
    })
  })

  it('gövde JSON değilse (2xx + bozuk gövde) yine başarı SAYILMAZ', () => {
    // Beyaz liste sözleşmesi: yalnız status==='ok' başarıdır. Kara liste
    // kullansaydık backend yeni bir başarısızlık durumu eklediğinde sessizce
    // başarı sayılırdı — düzelttiğimiz hatanın aynısı geri gelirdi.
    expect(gateFailure('mcp', { httpOk: true, httpStatus: 200, body: undefined })).not.toBeNull()
    expect(gateFailure('mcp', { httpOk: true, httpStatus: 200, body: { status: 'yepyeni_hata' } })).not.toBeNull()
  })
})
