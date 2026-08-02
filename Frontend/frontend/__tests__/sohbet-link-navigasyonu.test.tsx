/**
 * Sohbetteki bir dosya linki UYGULAMAYI BOŞALTMIYOR — kullanıcı bildirimi
 * 2 Ağu 2026.
 *
 * Arıza zinciri (ölçüldü): asistan `[test-dosyasi.txt](test-dosyasi.txt)` diye
 * link veriyor → `react-markdown`'da `a` override'ı olmadığı için ham
 * `<a href>` DOM'a giriyor → tarayıcı göreli adresi uygulamanın KENDİ
 * origin'ine çözüyor → Electron'un `will-navigate` politikası origin-içi
 * adresleri koşulsuz geçiriyor → tek pencere o adrese gidiyor, SPA unload
 * oluyor. Kullanıcının gördüğü: "uygulama resetleniyor, dosya açılmıyor".
 *
 * ⭐ Bu bir ÇÖKME DEĞİL, NAVİGASYON. Ayrım pahalıya mal oldu: React ağacı
 * hatasız yok olduğu için hata sınırı devreye girmiyor ve render yolunda
 * fırlatan bir nokta aranarak bulunamıyor. Testler bu yüzden "hata atmadı"
 * demiyor — VARSAYILAN DAVRANIŞIN İPTAL EDİLDİĞİNİ ölçüyor.
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, cleanup, fireEvent } from '@testing-library/react'

import { MarkdownRenderer } from '../renderer/components/home/MarkdownRenderer'
import { linkTuru, chatUrlTransform } from '../renderer/lib/chatLink'

afterEach(() => cleanup())

/**
 * Modelin GERÇEKTEN ürettiği markdown — üründeki veritabanından okundu
 * (sohbet 62, mesaj 667, 2026-08-02 12:31:40), uydurulmadı.
 *
 * ⚠️ İlk düzeltmem GÖRELİ yol varsaymıştı (`[a.txt](a.txt)`) ve testleri de o
 * varsayımla yazmıştım: testler YEŞİLDİ, arıza DURUYORDU. Ölçüm varsayımı
 * çürüttü — model mutlak Windows yolu üretiyor, üstelik boşluklu, ASCII
 * olmayan karakterli ve açılı parantezli.
 */
const GERCEK_MESAJ =
  'Buraya tıklayabilirsin:\n\n[test-dosyasi.txt](<C:\\Unity Projeler\\Körebe\\test-dosyasi.txt>)'
const GERCEK_YOL = 'C:\\Unity Projeler\\Körebe\\test-dosyasi.txt'

/** Tıklamayı iptal edilebilir biçimde gönderir ve `defaultPrevented`i döner. */
const tiklaVeIptalMi = (el: Element): boolean => {
  const olay = new MouseEvent('click', { bubbles: true, cancelable: true })
  fireEvent(el, olay)
  return olay.defaultPrevented
}

describe('linkTuru — sınıflandırma', () => {
  it('http ve https DIŞ sayılıyor', () => {
    expect(linkTuru('http://example.com')).toBe('dis')
    expect(linkTuru('https://example.com/a/b')).toBe('dis')
    // Şema büyük harfli gelirse de dış: küçük harfe indirgemeyi atlayan bir
    // mutant, `HTTPS://` linkini yerel dosya sanıp açmaya çalışırdı.
    expect(linkTuru('HTTPS://example.com')).toBe('dis')
  })

  it('mailto DIŞ sayılıyor', () => {
    expect(linkTuru('mailto:a@b.com')).toBe('dis')
  })

  it('salt çapa ÇAPA sayılıyor — dosya açmaya kalkmıyor', () => {
    expect(linkTuru('#bolum')).toBe('capa')
  })

  it('BOŞ href çapadan AYRI sınıflandırılıyor', () => {
    // Ayrım kozmetik değil: boş `href` tarayıcıda MEVCUT dokümana çözülür,
    // yani tıklama sayfayı yeniden yükler. Arızanın ölçülen son hâli buydu.
    // İkisini aynı sınıfa koyan ilk sürümüm boş href'i "zararsız çapa" sanıp
    // `preventDefault` uygulamıyordu.
    expect(linkTuru('')).toBe('bos')
    expect(linkTuru('   ')).toBe('bos')
    expect(linkTuru(undefined)).toBe('bos')
  })

  it('yol biçimlerinin HEPSİ yerel dosya sayılıyor', () => {
    // Ölçüt "dış olanı say, gerisi yerel". Ters kurgu (yerel biçimleri
    // saymak) her yeni biçimde sessizce açılırdı — bu depoda ölçülmüş sınıf.
    for (const y of [
      'test-dosyasi.txt',
      './Assets/Scripts/A.cs',
      '../ust/klasor.md',
      '/mutlak/posix/yol.txt',
      'C:\\Users\\burcu\\a.cs',
      'file:///C:/a.txt',
      'Assets/Scripts/Player.cs',
    ]) {
      expect(linkTuru(y)).toBe('yerel-dosya')
    }
  })
})

describe('chatUrlTransform — yolun override a SAĞLAM ulaşması', () => {
  it('mutlak Windows yolu SİLİNMİYOR', () => {
    // `defaultUrlTransform` `C:`'yi güvensiz bir protokol sanıp `''` döndürüyor
    // (ilk iki nokta protokol sayılıyor, güvenli liste `https?|ircs?|mailto|xmpp`).
    // Ölçüldü: override'a boş dizge ulaşıyordu ve link `<a href="">` oluyordu.
    expect(chatUrlTransform(GERCEK_YOL)).toBe(GERCEK_YOL)
    expect(chatUrlTransform('D:/Projeler/a.cs')).toBe('D:/Projeler/a.cs')
  })

  it('YÜZDE-KODLANMIŞ sürücü yolu da siliniyordu — artık geçiyor', () => {
    // ⚠️ Gerçekte `urlTransform`'a gelen biçim BU: mdast-util-to-hast dönüşümden
    // ÖNCE kodluyor. `C:\` arayan ilk desenim eşleşmiyordu ve düzeltme sessizce
    // etkisiz kalıyordu — testlerim yeşilken arıza duruyordu.
    const kodlu = 'C:%5CUnity%20Projeler%5CK%C3%B6rebe%5Ctest-dosyasi.txt'
    expect(chatUrlTransform(kodlu)).toBe(kodlu)
  })

  it('UNC ve file: de geçiyor', () => {
    expect(chatUrlTransform('\\\\sunucu\\pay\\a.txt')).toBe('\\\\sunucu\\pay\\a.txt')
    expect(chatUrlTransform('file:///C:/a.txt')).toBe('file:///C:/a.txt')
  })

  it('TEHLİKELİ şemalar HÂLÂ siliniyor — güvenlik gevşetilmedi', () => {
    // Bu testin sebebi doğrudan bir risk: `urlTransform`'u kendimiz yazsaydık
    // react-markdown'ın koruma davranışını kopyalamış olurduk. Sarmalıyoruz,
    // yeniden yazmıyoruz — ve bunun tutduğunu ölçüyoruz.
    expect(chatUrlTransform('javascript:alert(1)')).toBe('')
    expect(chatUrlTransform('vbscript:msgbox')).toBe('')
    expect(chatUrlTransform('data:text/html,<script>')).toBe('')
  })

  it('sıradan dış linkler bozulmuyor', () => {
    expect(chatUrlTransform('https://unity.com/a?b=1#c')).toBe('https://unity.com/a?b=1#c')
    expect(chatUrlTransform('./gorece/yol.md')).toBe('./gorece/yol.md')
  })
})

describe('GERÇEK mesaj — uçtan uca', () => {
  it('modelin ürettiği link tıklanınca navigasyon İPTAL ediliyor', () => {
    render(<MarkdownRenderer content={GERCEK_MESAJ} onOpenFile={vi.fn()} />)
    expect(tiklaVeIptalMi(screen.getByText('test-dosyasi.txt'))).toBe(true)
  })

  it('href BOŞ DEĞİL — yol override a sağlam ulaşıyor', () => {
    // Bu iddia ayrı: `preventDefault` boş href'te de çalışıyor, yani yalnız
    // "iptal edildi" demek yolun ulaştığını KANITLAMAZ. İlk düzeltmemin
    // yeşil test verip arızayı bırakmasının sebebi tam olarak buydu.
    render(<MarkdownRenderer content={GERCEK_MESAJ} onOpenFile={vi.fn()} />)
    expect(screen.getByText('test-dosyasi.txt').getAttribute('href')).toBeTruthy()
  })

  it('dosya, DİSKTE KULLANILABİLİR yoluyla açılmak üzere geçiriliyor', () => {
    const onOpenFile = vi.fn()
    render(<MarkdownRenderer content={GERCEK_MESAJ} onOpenFile={onOpenFile} />)
    fireEvent.click(screen.getByText('test-dosyasi.txt'))
    expect(onOpenFile).toHaveBeenCalledTimes(1)

    // ⚠️ ASIL İDDİA: yol ÇÖZÜLMÜŞ gelmeli. `href` yüzde-kodlu
    // (`C:%5CUnity%20Projeler%5C…`) ve o hâliyle `read-file` IPC'sine
    // verilseydi dosya diskte bulunamazdı — link "çalışır" görünüp hiçbir şey
    // açmazdı. Yani navigasyonu durdurmak TEK BAŞINA yeterli değil.
    const yol = onOpenFile.mock.calls[0][0] as string
    expect(yol).toBe(GERCEK_YOL)
    expect(yol).not.toContain('%')
  })
})

describe('MarkdownRenderer — yerel dosya linki', () => {
  it('tıklama VARSAYILAN DAVRANIŞI İPTAL EDİYOR — pencere yönlenmiyor', () => {
    // Asıl iddia bu. "onOpenFile çağrıldı" demek yetmez: çağrılıp da
    // preventDefault edilmezse tarayıcı yine adrese gider ve arıza sürer.
    render(
      <MarkdownRenderer content="[test-dosyasi.txt](test-dosyasi.txt)" onOpenFile={vi.fn()} />
    )
    expect(tiklaVeIptalMi(screen.getByText('test-dosyasi.txt'))).toBe(true)
  })

  it('tıklama dosyayı EDİTÖRDE açmak için yolu geçiriyor', () => {
    const onOpenFile = vi.fn()
    render(
      <MarkdownRenderer content="[aç](./Assets/Scripts/Player.cs)" onOpenFile={onOpenFile} />
    )
    fireEvent.click(screen.getByText('aç'))
    expect(onOpenFile).toHaveBeenCalledTimes(1)
    expect(onOpenFile).toHaveBeenCalledWith('./Assets/Scripts/Player.cs')
  })

  it('onOpenFile VERİLMESE bile navigasyon iptal ediliyor', () => {
    // `SlashCommandCard` gibi editörsüz bağlamlar bu bileşeni prop'suz
    // kullanıyor. İptali `onOpenFile` varlığına bağlamak, düzeltmenin
    // kendisinde bir kenar bırakırdı: link yine pencereyi boşaltırdı.
    render(<MarkdownRenderer content="[x](bir-dosya.txt)" />)
    expect(tiklaVeIptalMi(screen.getByText('x'))).toBe(true)
  })
})

describe('MarkdownRenderer — dış linke DOKUNULMUYOR', () => {
  it('https linki iptal EDİLMİYOR ve onOpenFile çağrılmıyor', () => {
    // Ters yön şart: her linki iptal eden bir mutant yukarıdaki testlerin
    // hepsini geçer, ama dış linkleri ÖLDÜRÜRDÜ. Onları main süreçteki
    // `will-navigate` zaten `shell.openExternal`a yönlendiriyor; buradan
    // müdahale etmek çalışan bir yolu kopyalamak olurdu.
    const onOpenFile = vi.fn()
    render(<MarkdownRenderer content="[site](https://unity.com)" onOpenFile={onOpenFile} />)

    const el = screen.getByText('site')
    expect(tiklaVeIptalMi(el)).toBe(false)
    expect(onOpenFile).not.toHaveBeenCalled()
    expect(el.getAttribute('href')).toBe('https://unity.com')
  })
})

describe('will-navigate ikincil savunması kaynakta duruyor', () => {
  /**
   * Main süreç jsdom'da koşturulamıyor (Electron `BrowserWindow` gerektiriyor),
   * ölçülebilir tek biçim kaynak metni. Depoda ölçülmüş ders: bir korumanın
   * mount/bağlanma adımı sessizce düşerse birim testleri yeşil kalıyor.
   */
  it('origin-içi navigasyon KOŞULSUZ geçirilmiyor', async () => {
    const { readFileSync } = await import('fs')
    const { resolve } = await import('path')
    const src = readFileSync(
      resolve(__dirname, '../main/helpers/create-window.ts'), 'utf8'
    )
    const handler = src.match(/on\('will-navigate'[\s\S]*?\n  \}\)/)
    expect(handler).toBeTruthy()
    // Eski kusurlu biçim: `if (isOwnOrigin(url)) return` — yani origin-içi
    // her adrese izin. Bu satırın geri gelmesi arızayı da geri getirir.
    expect(handler![0]).not.toMatch(/if\s*\(\s*isOwnOrigin\(url\)\s*\)\s*return/)
    expect(handler![0]).toContain('pathname')
  })
})
