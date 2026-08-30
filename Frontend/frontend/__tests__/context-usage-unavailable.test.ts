/**
 * BAŞARISIZ BİR ÖLÇÜM, SIFIR ÖLÇÜM DEĞİLDİR.
 *
 * Arıza (denetim `gauge-failed-request-zero`, 30 Ağu 2026): `contextUsage`
 * doğruluğu TRUE olan bir `{percent: 0, estimated: true}` ile başlıyordu ve
 * `GET /conversations/{id}/context-usage` hata verdiğinde olduğu gibi
 * kalıyordu. Gösterge `~%0` ve "yaklaşık doluluk" açıklamasını çiziyordu:
 * tek gerçek yanıt bir HATA iken kullanıcı ölçülmüş, neredeyse boş bir bağlam
 * okuyordu. Sessiz ve kendinden emin — en pahalı yanlış türü.
 *
 * SÖZLEŞME: `null` = "veri yok", `{percent: 0}` = "ölçtük, sıfır". İkisi ayrı
 * şeyler ve gösterge ikisini ayrı çiziyor (`usage.noData`; çizim tarafının
 * ölçümü `context-gauge.test.tsx`'te).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import axios from 'axios'

vi.mock('axios', () => {
  const get = vi.fn()
  const post = vi.fn().mockResolvedValue({ data: {} })
  return { __esModule: true, default: { get, post }, get, post }
})
const mockedAxios = axios as unknown as { get: ReturnType<typeof vi.fn> }

import { useChat } from '../renderer/hooks/home/useChat'

const API = 'http://x'
const USER = { id: 1, name: 'b', sessionToken: 'tok' } as any
const OLCUM = { percent: 42, should_compact: false, message_count: 8, estimated: true }

/** `/messages` her zaman boş liste; bağlam isteğini çağıran belirliyor. */
const baglamIstegi = (yanit: () => Promise<any>) => {
  mockedAxios.get.mockImplementation(async (url: string) => {
    if (String(url).endsWith('/messages')) return { data: [] }
    if (String(url).endsWith('/context-usage')) return yanit()
    return { data: [] }
  })
}

const kanca = () =>
  renderHook(() => useChat(API, USER, { provider_type: 'api' } as any, null, vi.fn(), vi.fn(), (n: string) => n))

describe('bağlam göstergesi — ölçülemeyen şeye sayı uydurulmuyor', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('hiç istek yapılmadan önce veri YOK — sıfır değil', () => {
    const { result } = kanca()
    expect(result.current.contextUsage).toBeNull()
  })

  it('istek başarısızsa gösterge veri yok durumuna düşüyor', async () => {
    baglamIstegi(async () => { throw new Error('context endpoint unavailable') })
    const { result } = kanca()
    await act(async () => { await result.current.selectConversation({ id: 7 } as any) })
    expect(mockedAxios.get).toHaveBeenCalledWith(`${API}/conversations/7/context-usage`)
    expect(result.current.contextUsage).toBeNull()
  })

  it('istek başarılıysa gerçek ölçüm yazılıyor — kanca sürekli null demiyor', async () => {
    // Karşı kutup: `null` sabiti de bu testleri yeşil yapardı.
    baglamIstegi(async () => ({ data: OLCUM }))
    const { result } = kanca()
    await act(async () => { await result.current.selectConversation({ id: 7 } as any) })
    expect(result.current.contextUsage).toEqual(OLCUM)
  })

  it('önceki başarılı ölçüm, sonraki hatanın üstünde ASILI KALMIYOR', async () => {
    // Eski sayıyı tutmak, hata veren isteğe bir değer atfetmek olurdu — üstelik
    // başka bir sohbetin değerini.
    baglamIstegi(async () => ({ data: OLCUM }))
    const { result } = kanca()
    await act(async () => { await result.current.selectConversation({ id: 7 } as any) })
    expect(result.current.contextUsage).toEqual(OLCUM)

    baglamIstegi(async () => { throw new Error('context endpoint unavailable') })
    await act(async () => { await result.current.selectConversation({ id: 8 } as any) })
    expect(result.current.contextUsage).toBeNull()
  })
})
