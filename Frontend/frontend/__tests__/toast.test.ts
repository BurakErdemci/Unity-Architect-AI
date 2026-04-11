import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useToast } from '../renderer/components/ui/Toast'

describe('useToast — toast ekleme', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('başlangıçta toast listesi boş', () => {
    const { result } = renderHook(() => useToast())
    expect(result.current.toasts).toHaveLength(0)
  })

  it('showToast çağrısı toast ekler', () => {
    const { result } = renderHook(() => useToast())
    act(() => { result.current.showToast('Test mesajı', 'info') })
    expect(result.current.toasts).toHaveLength(1)
    expect(result.current.toasts[0].message).toBe('Test mesajı')
    expect(result.current.toasts[0].type).toBe('info')
  })

  it('tür belirtilmezse varsayılan "info" kullanılır', () => {
    const { result } = renderHook(() => useToast())
    act(() => { result.current.showToast('Mesaj') })
    expect(result.current.toasts[0].type).toBe('info')
  })

  it('her toast benzersiz id alır', () => {
    const { result } = renderHook(() => useToast())
    act(() => {
      result.current.showToast('A', 'success')
      result.current.showToast('B', 'error')
    })
    const ids = result.current.toasts.map(t => t.id)
    expect(new Set(ids).size).toBe(2)
  })

  it('birden fazla toast aynı anda tutulur', () => {
    const { result } = renderHook(() => useToast())
    act(() => {
      result.current.showToast('A', 'success')
      result.current.showToast('B', 'error')
      result.current.showToast('C', 'warning')
    })
    expect(result.current.toasts).toHaveLength(3)
  })
})

describe('useToast — otomatik kapanma', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('varsayılan süre (4s) sonra toast silinir', () => {
    const { result } = renderHook(() => useToast())
    act(() => { result.current.showToast('Geçici', 'info') })
    expect(result.current.toasts).toHaveLength(1)

    act(() => { vi.advanceTimersByTime(4000) })
    expect(result.current.toasts).toHaveLength(0)
  })

  it('özel süre çalışır', () => {
    const { result } = renderHook(() => useToast())
    act(() => { result.current.showToast('Hızlı', 'info', 1000) })

    act(() => { vi.advanceTimersByTime(999) })
    expect(result.current.toasts).toHaveLength(1)

    act(() => { vi.advanceTimersByTime(1) })
    expect(result.current.toasts).toHaveLength(0)
  })

  it('süre dolmadan başka toast etkilenmez', () => {
    const { result } = renderHook(() => useToast())
    act(() => {
      result.current.showToast('Kısa', 'info', 1000)
      result.current.showToast('Uzun', 'success', 5000)
    })

    act(() => { vi.advanceTimersByTime(1000) })
    expect(result.current.toasts).toHaveLength(1)
    expect(result.current.toasts[0].message).toBe('Uzun')
  })
})

describe('useToast — manuel kapatma', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('dismissToast id\'ye göre siler', () => {
    const { result } = renderHook(() => useToast())
    act(() => {
      result.current.showToast('A', 'info')
      result.current.showToast('B', 'error')
    })
    const idToRemove = result.current.toasts[0].id
    act(() => { result.current.dismissToast(idToRemove) })
    expect(result.current.toasts).toHaveLength(1)
    expect(result.current.toasts[0].message).toBe('B')
  })

  it('geçersiz id ile dismiss hata fırlatmaz', () => {
    const { result } = renderHook(() => useToast())
    act(() => { result.current.showToast('Test', 'info') })
    expect(() => {
      act(() => { result.current.dismissToast(99999) })
    }).not.toThrow()
    expect(result.current.toasts).toHaveLength(1)
  })
})

describe('useToast — tüm toast tipleri', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  const types = ['success', 'error', 'warning', 'info'] as const

  for (const type of types) {
    it(`"${type}" tipi eklenir ve görünür`, () => {
      const { result } = renderHook(() => useToast())
      act(() => { result.current.showToast(`${type} mesajı`, type) })
      expect(result.current.toasts[0].type).toBe(type)
    })
  }
})

describe('useToast — uygulama senaryoları', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('ayarlar kaydedildi → success toast', () => {
    const { result } = renderHook(() => useToast())
    act(() => { result.current.showToast('Ayarlar kaydedildi!', 'success') })
    expect(result.current.toasts[0].type).toBe('success')
    expect(result.current.toasts[0].message).toBe('Ayarlar kaydedildi!')
  })

  it('oturum sona erdi → warning toast', () => {
    const { result } = renderHook(() => useToast())
    act(() => { result.current.showToast('Oturumunuz sona erdi. Lütfen tekrar giriş yapın.', 'warning') })
    expect(result.current.toasts[0].type).toBe('warning')
  })

  it('sunucuya ulaşılamadı → error toast', () => {
    const { result } = renderHook(() => useToast())
    act(() => { result.current.showToast('Sunucuya ulaşılamadı.', 'error') })
    expect(result.current.toasts[0].type).toBe('error')
  })

  it('API key eksik → warning toast', () => {
    const { result } = renderHook(() => useToast())
    act(() => { result.current.showToast('anthropic için API key girilmedi.', 'warning') })
    expect(result.current.toasts[0].type).toBe('warning')
  })

  it('key silme hatası → error toast', () => {
    const { result } = renderHook(() => useToast())
    act(() => { result.current.showToast('Key silinirken bir hata oluştu.', 'error') })
    expect(result.current.toasts[0].type).toBe('error')
  })
})
