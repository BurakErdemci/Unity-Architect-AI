/**
 * "Fonksiyon çağrıldı" ≠ "kullanıcı gördü".
 *
 * Ölçüldü (2026-07-29, doğrulandı 2026-07-30): `ToastContainer` tanımlı, export
 * edilmiş ve **hiçbir yerden mount edilmemişti** — `renderer/` altında tek
 * referans kendi tanımıydı. `showToast` bir state'e yazıyor, çizen kimse yoktu,
 * yani onay kapısı işinin BÜTÜN kullanıcı bildirimi görünmezdi. Mevcut
 * `toast.test.ts` bunu göremedi: 13 testin hepsi hook state'ine bakıyor,
 * biri "görünür" adını taşıyor ama iddiası `toasts[0].type`.
 *
 * Buradaki testler zincirin SON halkasını sürüyor: DOM'da metin var mı.
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import React from 'react'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react'

import { useToast, ToastContainer } from '../renderer/components/ui/Toast'

afterEach(() => cleanup())

const Harness = () => {
  const { toasts, showToast, dismissToast } = useToast()
  return (
    <>
      <button onClick={() => showToast('Ayarlar kaydedildi!', 'success')}>tetikle</button>
      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </>
  )
}

describe('ToastContainer — bildirim gerçekten çiziliyor', () => {
  it('showToast sonrası mesaj DOM da görünüyor', () => {
    render(<Harness />)
    expect(screen.queryByText('Ayarlar kaydedildi!')).toBeNull()
    fireEvent.click(screen.getByText('tetikle'))
    expect(screen.getByText('Ayarlar kaydedildi!')).toBeTruthy()
  })

  it('kapatma düğmesi mesajı DOM dan kaldırıyor', async () => {
    render(<Harness />)
    fireEvent.click(screen.getByText('tetikle'))
    const kapat = screen.getAllByRole('button').filter(b => b.textContent === '')
    expect(kapat.length).toBeGreaterThan(0)
    fireEvent.click(kapat[kapat.length - 1])
    // `AnimatePresence` çıkış animasyonu (0.18 sn) düğümü hemen sökmüyor;
    // senkron bir iddia burada YANLIŞ kırmızı verir. Beklenen şey durumun
    // düşmesi değil, düğümün gerçekten kaybolması.
    await waitFor(() => expect(screen.queryByText('Ayarlar kaydedildi!')).toBeNull())
  })

  it('hata tipi mesajı da çiziliyor — tip filtrelemesi yok', () => {
    const ErrHarness = () => {
      const { toasts, showToast, dismissToast } = useToast()
      return (
        <>
          <button onClick={() => showToast('Kaydedilemedi.', 'error')}>hata</button>
          <ToastContainer toasts={toasts} onDismiss={dismissToast} />
        </>
      )
    }
    render(<ErrHarness />)
    fireEvent.click(screen.getByText('hata'))
    expect(screen.getByText('Kaydedilemedi.')).toBeTruthy()
  })
})

describe('home.tsx bildirim kanalını bağlıyor', () => {
  /**
   * Bu iki iddia KAYNAK METNİ okuyor, yani İKİNCİL bir kontrol: birincil kanıt
   * yukarıdaki DOM testleri. Buradaki soru farklı ve DOM'dan cevaplanamıyor —
   * `home.tsx` jsdom'da render edilemiyor (Monaco, electron IPC, 6 hook), o
   * yüzden "container ağaca gerçekten konmuş mu" sorusunun ölçülebilir tek
   * biçimi bu. Mount silinirse bu test kırılır; sessizce ölmez.
   */
  const src = readFileSync(
    resolve(__dirname, '../renderer/pages/home.tsx'),
    'utf8'
  )

  it('ToastContainer mount edilmiş ve toast state i bağlanmış', () => {
    expect(src).toMatch(/<ToastContainer[\s\S]{0,120}toasts=\{/)
    expect(src).toMatch(/<ToastContainer[\s\S]{0,160}onDismiss=\{/)
  })

  it('toasts ve dismissToast useAppInitialization dan alınıyor', () => {
    // Hook ikisini de döndürüyordu; `home.tsx` yalnız `showToast`'ı alıp
    // diğer ikisini atıyordu. Kanalın kopuk halkası buydu.
    const destructure = src.match(/const \{[^}]*\} = useAppInitialization\(\)/)
    expect(destructure).toBeTruthy()
    expect(destructure![0]).toContain('toasts')
    expect(destructure![0]).toContain('dismissToast')
  })
})
