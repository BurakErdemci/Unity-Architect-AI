/**
 * Paralel silme isteklerinde KARARIN KAYBOLMAMASI.
 *
 * Arıza (30 Ağu 2026 denetimi, ölçüldü): komut ve soru kartları için kuyruk
 * vardı, silme kartı için yoktu. Aynı turda ikinci bir `pending_delete`
 * geldiğinde birincinin kartı tek slottan siliniyor, kullanıcı onu hiç görmüyor
 * ve istek cevapsız kalıp sunucu tarafında zaman aşımına düşüyordu.
 *
 * Kuyruk, durumun SAHİBİNDE (`useFileSystem`) duruyor, `useChat`'te değil:
 * `useChat` yalnız kendisine verilen setter'ı çağırıyor, o yüzden kuyruğu
 * tüketicide tutmak "hangi setter geçirildiyse" sorusuna bağlı kalırdı.
 * Denetimin kanıt betiği tam olarak bunu yapıyor — `useChat`'e çıplak bir
 * `useState` setter'ı veriyor — o yüzden orada hâlâ kırmızı; ürünün gerçek
 * bağlantısı bu dosyada ölçülüyor.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'

vi.mock('axios', () => ({
  __esModule: true,
  default: { get: vi.fn().mockResolvedValue({ data: {} }), post: vi.fn().mockResolvedValue({ data: {} }) },
}))

import { useFileSystem } from '../renderer/hooks/home/useFileSystem'

const A = { path: 'Assets/A.cs', messageId: 1 }
const B = { path: 'Assets/B.cs', messageId: 1 }

describe('pendingDelete kuyruğu', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  const mount = () => renderHook(() => useFileSystem('http://x', null, () => {}))

  it('ikinci silme isteği birincinin kartını EZMİYOR', () => {
    const { result } = mount()
    act(() => { result.current.setPendingDelete(A) })
    act(() => { result.current.setPendingDelete(B) })
    expect(result.current.pendingDelete?.path).toBe(A.path)
  })

  it('birinci karara bağlanınca ikinci kart görünür oluyor', () => {
    const { result } = mount()
    act(() => { result.current.setPendingDelete(A) })
    act(() => { result.current.setPendingDelete(B) })
    act(() => { result.current.setPendingDelete(null) })   // kullanıcı A'ya cevap verdi
    expect(result.current.pendingDelete?.path).toBe(B.path)
  })

  it('kuyruk boşalınca kart kapanıyor', () => {
    const { result } = mount()
    act(() => { result.current.setPendingDelete(A) })
    act(() => { result.current.setPendingDelete(null) })
    expect(result.current.pendingDelete).toBeNull()
  })

  it('üç istek de sırayla gösteriliyor — kuyruk tek derinlikte değil', () => {
    const { result } = mount()
    const C = { path: 'Assets/C.cs', messageId: 1 }
    act(() => { result.current.setPendingDelete(A) })
    act(() => { result.current.setPendingDelete(B) })
    act(() => { result.current.setPendingDelete(C) })
    const seen: string[] = []
    for (let i = 0; i < 3; i++) {
      seen.push(result.current.pendingDelete!.path)
      act(() => { result.current.setPendingDelete(null) })
    }
    expect(seen).toEqual([A.path, B.path, C.path])
    expect(result.current.pendingDelete).toBeNull()
  })
})
