/**
 * Beyaz ekranın kapanması — ErrorBoundary.
 *
 * Arıza (kullanıcı bildirimi, 2 Ağu 2026): dosya ağacında AI'ın düzenlediği
 * (git durumu yeşil) bir dosyaya tıklanınca pencere bomboş kalıyor ve
 * uygulamayı KAPATIP AÇMAK gerekiyor. Sebep React'in varsayılanı: yakalanmayan
 * bir render hatasında tüm ağaç unmount ediliyor. Depoda hiç hata sınırı yoktu
 * (ölçüm: `getDerivedStateFromError` sıfır eşleşme).
 *
 * Testler iki AYRI iddiayı ölçüyor ve ikisi de gerekli:
 *   1. Kurtarma — kullanıcı uygulamayı kapatmadan devam edebiliyor.
 *   2. Teşhis — hatanın METNİ ekranda. Beyaz ekranın en pahalı yanı bilgiyi
 *      yok etmesiydi; yalnız "bir şey ters gitti" diyen bir kart o kaybı
 *      tekrarlardı, sadece daha kibar biçimde.
 */
import { readFileSync } from 'fs'
import { resolve } from 'path'

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, cleanup, fireEvent } from '@testing-library/react'

import { ErrorBoundary } from '../renderer/components/ui/ErrorBoundary'

const PATLAMA = 'getLineContent çağrısı geçersiz satır numarası aldı'

const Patlayan = () => {
  throw new Error(PATLAMA)
}

beforeEach(() => {
  // React bir sınır yakaladığında kendi `console.error`'ını basıyor; testin
  // çıktısını kirletmesin. Depoda yerleşik desen.
  vi.spyOn(console, 'error').mockImplementation(() => {})
  vi.spyOn(console, 'warn').mockImplementation(() => {})
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  localStorage.clear()
})

describe('ErrorBoundary — kurtarma', () => {
  it('hata yokken çocukları OLDUĞU GİBİ geçiriyor', () => {
    // Ters yön şart: her zaman hata kartı gösteren bir mutant, aşağıdaki
    // testlerin hepsini geçerdi.
    render(
      <ErrorBoundary>
        <div>normal içerik</div>
      </ErrorBoundary>
    )
    expect(screen.getByText('normal içerik')).toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('çocuk render sırasında fırlatınca EKRAN BOŞ KALMIYOR', () => {
    render(
      <ErrorBoundary>
        <Patlayan />
      </ErrorBoundary>
    )
    // Asıl iddia bu: kullanıcı bir şey GÖRÜYOR. Arızanın kendisi "hiçbir şey
    // görünmüyor"du, dolayısıyla ölçüt de görünürlük olmalı.
    const kart = screen.getByRole('alert')
    expect(kart).toBeTruthy()
    expect(kart.textContent).toBeTruthy()
  })

  it('yeniden yükle düğmesi gerçekten tetikliyor', () => {
    // Düğmenin VARLIĞI yetmez: metni doğru ama hiçbir şey yapmayan bir düğme
    // kullanıcıyı yine uygulamayı kapatmaya bırakır.
    const onReload = vi.fn()
    render(
      <ErrorBoundary onReload={onReload}>
        <Patlayan />
      </ErrorBoundary>
    )
    fireEvent.click(screen.getByText('Yeniden Yükle'))
    expect(onReload).toHaveBeenCalledTimes(1)
  })
})

describe('ErrorBoundary — teşhis', () => {
  it('hatanın KENDİ METNİ kartta görünüyor', () => {
    // Bu testin sebebi doğrudan bir arıza: beyaz ekran, hangi bileşenin neden
    // patladığını herkesten gizliyordu. Genel bir özür metni aynı kaybı
    // tekrarlardı — kartın değeri hatayı TAŞIMASINDA.
    render(
      <ErrorBoundary>
        <Patlayan />
      </ErrorBoundary>
    )
    expect(screen.getByRole('alert').textContent).toContain(PATLAMA)
  })

  it('hata konsola da düşüyor — kart kapatılsa bile iz kalıyor', () => {
    render(
      <ErrorBoundary>
        <Patlayan />
      </ErrorBoundary>
    )
    const cagrilar = (console.error as any).mock.calls as unknown[][]
    const bizimkiler = cagrilar.filter(c => String(c[0]).includes('[ErrorBoundary]'))
    expect(bizimkiler.length).toBeGreaterThan(0)
  })
})

describe('ErrorBoundary — dil', () => {
  it('app-lang=en iken İngilizce metin gösteriyor', () => {
    // Bu bileşen `LangContext`'i GÖREMİYOR (provider `home.tsx` içinde, sınır
    // onu saran katmanda). Dil bu yüzden localStorage'dan okunuyor; test o
    // yolun gerçekten çalıştığını ölçüyor, yoksa dil sessizce hep `tr` kalırdı.
    localStorage.setItem('app-lang', 'en')
    render(
      <ErrorBoundary>
        <Patlayan />
      </ErrorBoundary>
    )
    expect(screen.getByText('Reload')).toBeTruthy()
  })

  it('anahtar yokken ham anahtarı basmıyor — Türkçe varsayılan', () => {
    localStorage.setItem('app-lang', 'tr')
    render(
      <ErrorBoundary>
        <Patlayan />
      </ErrorBoundary>
    )
    expect(screen.getByRole('alert').textContent).not.toContain('error.title')
  })
})

describe('_app.tsx sınırı gerçekten AĞACA koyuyor', () => {
  /**
   * İKİNCİL kontrol, kaynak metni okuyor. Birincil kanıt yukarıdaki DOM
   * testleri; buradaki soru farklı: "sınır uygulamanın ağacında mı". Depoda
   * ölçülmüş bir ders var — `ToastContainer` bütün birim testleri geçiyordu ve
   * hiçbir yere mount EDİLMEMİŞTİ. Sınır için aynı hata daha pahalıya gelirdi:
   * testler yeşil, kullanıcı yine beyaz ekran görür.
   */
  const src = readFileSync(resolve(__dirname, '../renderer/pages/_app.tsx'), 'utf8')

  it('ErrorBoundary sayfa bileşenini SARIYOR', () => {
    expect(src).toMatch(/<ErrorBoundary>[\s\S]{0,200}<Component\s/)
  })

  it('ConfirmDialogHost sınırın DIŞINDA kalıyor', () => {
    // Kasıtlı bir karar: içeri alınsaydı bir render hatası onay diyaloğunu da
    // unmount edip `confirmDialog()`'u native `confirm()`e düşürürdü (bilinen
    // Electron focus-kilit arızası). Karar yorumla yazılı; bu test onu
    // bağlayıcı yapıyor.
    const sinirIci = src.match(/<ErrorBoundary>([\s\S]*?)<\/ErrorBoundary>/)
    expect(sinirIci).toBeTruthy()
    expect(sinirIci![1]).not.toContain('ConfirmDialogHost')
    expect(src).toContain('<ConfirmDialogHost />')
  })
})
