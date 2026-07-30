/**
 * `useAIConfig`'in Unity MCP durum sözleşmesi — `blocked` DAHİL.
 *
 * Arıza sınıfı (ölçüldü 2026-07-30): backend `b4065f1`'den beri beşinci bir
 * durum döndürüyor — `blocked`, yani "8080 bizim olmayan bir sunucuda". Hook
 * bunu hiç tanımıyordu: tip dört değerliydi, `reason` alanı okunmuyordu,
 * `turningOn` hesabı `blocked`'da KAPATMA isteği yolluyordu (backend sessizce
 * 200 `{"status":"stopped"}` dönüyor → kullanıcı butona basıyor, hiçbir şey
 * olmuyor, hata da görünmüyor), ve 500 yanıtının `detail`'i — sebebin taşındığı
 * tek yer — sabit bir metinle değiştiriliyordu.
 *
 * Testler durum ADLARINA değil DAVRANIŞA bakıyor: hangi istek gitti, kullanıcıya
 * hangi metin ulaştı, hata sonrası durum tahmin mi edildi yoksa ölçüldü mü.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, waitFor, cleanup } from '@testing-library/react'
import axios from 'axios'

import { useAIConfig } from '../renderer/hooks/home/useAIConfig'

vi.mock('axios', () => {
  const get = vi.fn()
  const post = vi.fn()
  const del = vi.fn()
  return { default: { get, post, delete: del }, get, post, delete: del }
})

const mockedAxios = axios as unknown as {
  get: ReturnType<typeof vi.fn>
  post: ReturnType<typeof vi.fn>
}

const API = 'http://127.0.0.1:8000'

// Backend'in gerçek metni (`unity_mcp_manager._blocked_reason` →
// `mcp_port_guard.port_busy_message`). Testin bu metne bağlı olması kasıtlı:
// kullanıcının okuyacağı şey bu, ve süreç ADI olmadan sebep eyleme dönmüyor.
const BLOCKED_REASON =
  '8080 portu bize ait olmayan bir süreç tarafından kullanılıyor ' +
  '(node · PID 4242). O süreci kapatıp tekrar deneyin.'

const statusPayload = (status: string, reason: string | null = null) => ({
  data: { status, pid: null, port: 8080, instances: [], reason },
})

// Hook'un beklediği imzayla mock: tipsiz `vi.fn()` `showToast` parametresine
// atanamıyor ve `as any` ile susturmak testin kendi ölçüm aracını körleştirir.
type ShowToast = (msg: string, type: unknown) => void

let showToast: ReturnType<typeof vi.fn<ShowToast>>

const mountHook = () => renderHook(() => useAIConfig(API, null, showToast))

beforeEach(() => {
  showToast = vi.fn<ShowToast>()
  mockedAxios.get.mockReset()
  mockedAxios.post.mockReset()
})

afterEach(() => {
  cleanup()
})

describe('useAIConfig — blocked durumu', () => {
  it('blocked yanıtı durum olarak geçiyor', async () => {
    mockedAxios.get.mockResolvedValue(statusPayload('blocked', BLOCKED_REASON))
    const { result } = mountHook()
    await waitFor(() => expect(result.current.unityMcpStatus).toBe('blocked'))
  })

  it('sebep (reason) state e alınıyor — kullanıcı toggle a basmadan önce görebilsin', async () => {
    mockedAxios.get.mockResolvedValue(statusPayload('blocked', BLOCKED_REASON))
    const { result } = mountHook()
    await waitFor(() => expect(result.current.unityMcpStatus).toBe('blocked'))
    // Süreç adı ve PID sebebin eyleme dönüşen kısmı; onları kaybetmek
    // "port meşgul" demekle aynı şey, yani hiçbir şey söylememek.
    expect(result.current.unityMcpReason).toContain('node')
    expect(result.current.unityMcpReason).toContain('4242')
  })

  it('durum blocked degilse sebep TAŞINMIYOR — bayat sebep gösterilmez', async () => {
    mockedAxios.get.mockResolvedValueOnce(statusPayload('blocked', BLOCKED_REASON))
    const { result } = mountHook()
    await waitFor(() => expect(result.current.unityMcpReason).toContain('4242'))

    // Kullanıcı yabancı süreci kapattı → sonraki yoklama 'off' diyor.
    mockedAxios.get.mockResolvedValue(statusPayload('off', null))
    await act(async () => { await result.current.refreshUnityMcpStatus() })
    expect(result.current.unityMcpStatus).toBe('off')
    expect(result.current.unityMcpReason).toBeNull()
  })

  it('off yanıtı DOLU bir sebep taşısa bile sunulmuyor — sözleşmeye güvenilmiyor', async () => {
    // Backend `reason`'ı yalnız `blocked` dalında dolduruyor, yani bu senaryo
    // bugün oluşmuyor. Test yine de gerekli: mutasyonla ölçüldü (2026-07-30),
    // sebebi koşulsuz taşıyan bir mutant yalnız `reason: null` gelen
    // senaryolarla sınandığında KAÇIYOR — çünkü null'u taşımak da null yazmak.
    // İddianın ayırt edici biçimi bu: durum blocked değilse sebep YOK.
    mockedAxios.get.mockResolvedValue(statusPayload('off', BLOCKED_REASON))
    const { result } = mountHook()
    await waitFor(() => expect(result.current.unityMcpStatus).toBe('off'))
    expect(result.current.unityMcpReason).toBeNull()
  })

  it('blocked ta toggle AÇMA isteği yolluyor — kapatma DEĞİL', async () => {
    mockedAxios.get.mockResolvedValue(statusPayload('blocked', BLOCKED_REASON))
    const { result } = mountHook()
    await waitFor(() => expect(result.current.unityMcpStatus).toBe('blocked'))

    mockedAxios.post.mockResolvedValue({ data: { status: 'started', port: 8080 } })
    await act(async () => { await result.current.toggleUnityMcp() })

    // `enabled:false` giderse backend yabancı süreci öldürmüyor ve sessizce
    // 200 `{"status":"stopped"}` dönüyor: kullanıcı için hiçbir şey olmuyor.
    expect(mockedAxios.post).toHaveBeenCalledTimes(1)
    expect(mockedAxios.post.mock.calls[0][0]).toContain('/mcp/unity/toggle')
    expect(mockedAxios.post.mock.calls[0][1]).toMatchObject({ enabled: true })
  })

  it('connected ta toggle KAPATMA isteği yolluyor — yön korunuyor', async () => {
    // İki yönü de sınamak şart: yalnız "blocked açıyor" iddiası, her durumda
    // `enabled:true` yollayan bir mutasyonu yeşil bırakırdı.
    mockedAxios.get.mockResolvedValue(statusPayload('connected', null))
    const { result } = mountHook()
    await waitFor(() => expect(result.current.unityMcpStatus).toBe('connected'))

    mockedAxios.post.mockResolvedValue({ data: { status: 'stopped' } })
    await act(async () => { await result.current.toggleUnityMcp() })
    expect(mockedAxios.post.mock.calls[0][1]).toMatchObject({ enabled: false })
  })
})

describe('useAIConfig — toggle hatasının kullanıcıya ulaşması', () => {
  const settleOff = async (result: { current: { unityMcpStatus: string } }) => {
    await waitFor(() => expect(result.current.unityMcpStatus).toBe('off'))
  }

  it('500 yanıtının detail i mesaja geçiyor — sebep sabit metinle EZİLMİYOR', async () => {
    mockedAxios.get.mockResolvedValue(statusPayload('off', null))
    const { result } = mountHook()
    await settleOff(result as any)

    mockedAxios.post.mockRejectedValue({
      response: { status: 500, data: { detail: BLOCKED_REASON } },
    })
    await act(async () => { await result.current.toggleUnityMcp() })

    expect(showToast).toHaveBeenCalledTimes(1)
    expect(String(showToast.mock.calls[0][0])).toContain('4242')
    expect(result.current.unityMcpError).toContain('4242')
  })

  it('409 un detail i de geçiyor ve yokluğunda Türkçe yedek metin var', async () => {
    mockedAxios.get.mockResolvedValue(statusPayload('off', null))
    const { result } = mountHook()
    await settleOff(result as any)

    mockedAxios.post.mockRejectedValue({ response: { status: 409, data: {} } })
    await act(async () => { await result.current.toggleUnityMcp() })
    expect(String(showToast.mock.calls[0][0])).toContain('Unity')
  })

  it('detail metin DEĞİLSE sabit metne düşüyor (422 dizisi React e basılamaz)', async () => {
    // FastAPI doğrulama hatası `detail`'i bir DİZİ döndürüyor. Doğrudan
    // render edilirse React "Objects are not valid as a React child" atıyor;
    // yani tip kontrolü kozmetik değil, çökme kapısı.
    mockedAxios.get.mockResolvedValue(statusPayload('off', null))
    const { result } = mountHook()
    await settleOff(result as any)

    mockedAxios.post.mockRejectedValue({
      response: { status: 422, data: { detail: [{ loc: ['body'], msg: 'field required' }] } },
    })
    await act(async () => { await result.current.toggleUnityMcp() })

    expect(typeof result.current.unityMcpError).toBe('string')
    expect(result.current.unityMcpError).not.toContain('[object')
    expect(result.current.unityMcpError).toContain('başarısız')
  })

  it('hata sonrası durumu TAHMİN etmiyor, yeniden ÖLÇÜYOR', async () => {
    // Eski davranış: catch içinde koşulsuz `setUnityMcpStatus('off')`.
    // blocked bir portta bu YANLIŞ bilgi — kullanıcı gri "kapalı" görüp
    // tekrar deniyor, oysa sebep duruyor.
    mockedAxios.get.mockResolvedValue(statusPayload('blocked', BLOCKED_REASON))
    const { result } = mountHook()
    await waitFor(() => expect(result.current.unityMcpStatus).toBe('blocked'))

    mockedAxios.post.mockRejectedValue({
      response: { status: 500, data: { detail: BLOCKED_REASON } },
    })
    await act(async () => { await result.current.toggleUnityMcp() })

    expect(result.current.unityMcpStatus).toBe('blocked')
  })
})
