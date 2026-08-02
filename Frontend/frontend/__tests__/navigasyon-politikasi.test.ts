/**
 * Gezinme politikası — DIŞ DENETİM bulgularından (2 Ağu 2026) terfi eden testler.
 *
 * Denetçi iki mutasyon üretti ve ikisi de 377 testin hepsini geçti:
 *   - `applyNavigationPolicy(win)` çağrısı silindi   → suite yeşil
 *   - `isOwnOrigin` koşulsuz `true` yapıldı          → suite yeşil
 *
 * Yani uygulamanın gezinme güvenliğinin tamamı ölçüsüzdü: var olduğu
 * varsayılıyor, hiçbir yerde çalıştırılmıyordu. Bu dosyanın tek işi o boşluğu
 * kapatmak — politikayı GERÇEKTEN çağırarak, kaynağına bakarak değil.
 */
import fs from 'fs'
import path from 'path'

import { describe, it, expect, vi, beforeEach } from 'vitest'

// Politika dış linkleri işletim sistemine veriyor; testte gerçek tarayıcı
// açılmamalı. Mock yalnız bunun için — politika mantığı ürünün kendisi.
const acilanDisLinkler: string[] = []
vi.mock('electron', () => ({
  shell: { openExternal: (u: string) => { acilanDisLinkler.push(u); return Promise.resolve() } },
  app: { getPath: () => '/tmp' },
  dialog: {},
  screen: {},
  BrowserWindow: class {},
}))

import { applyNavigationPolicy } from '../main/helpers/create-window'
import { isOwnOrigin } from '../main/helpers/ipc-trust'

/** `webContents`in politikanın dokunduğu yüzeyi kadarını taklit ediyor. */
const sahtePencere = (mevcutUrl: string) => {
  const kancalar: Record<string, Function> = {}
  let pencereAcmaKancasi: Function | null = null
  return {
    kancalar,
    get pencereAcmaKancasi() { return pencereAcmaKancasi },
    win: {
      webContents: {
        setWindowOpenHandler: (cb: Function) => { pencereAcmaKancasi = cb },
        on: (olay: string, cb: Function) => { kancalar[olay] = cb },
        getURL: () => mevcutUrl,
      },
    } as any,
  }
}

/** `event.preventDefault()` çağrıldı mı? */
const olay = () => {
  const o = { engellendi: false, preventDefault() { o.engellendi = true } }
  return o
}

const SAYFA = 'http://localhost:8888/home/'

describe('politika DÖRT yüzeyin hepsine kuruluyor', () => {
  it('will-navigate, will-redirect, will-attach-webview ve pencere açma kancası', () => {
    const p = sahtePencere(SAYFA)
    applyNavigationPolicy(p.win)
    expect(Object.keys(p.kancalar).sort()).toEqual(
      ['will-attach-webview', 'will-navigate', 'will-redirect'],
    )
    expect(p.pencereAcmaKancasi).toBeTypeOf('function')
  })
})

describe('will-navigate', () => {
  beforeEach(() => { acilanDisLinkler.length = 0 })

  it('AYNI belgeye navigasyon geçiyor — meşru yeniden yükleme kesilmiyor', () => {
    // Ters yön: her şeyi engelleyen bir muhafız ErrorBoundary'nin "yeniden
    // yükle" düğmesini de öldürürdü. Bu depoda bir sertleştirme tam olarak
    // böyle davranıp uygulamayı hiç açılamaz yapmıştı.
    const p = sahtePencere(SAYFA); applyNavigationPolicy(p.win)
    const e = olay()
    p.kancalar['will-navigate'](e, SAYFA)
    expect(e.engellendi).toBe(false)
  })

  it('BAŞKA belgeye origin-içi navigasyon ENGELLENİYOR', () => {
    // Sohbetteki göreli bir `<a href>` uygulamanın kendi origin'ine çözülüyor;
    // `isOwnOrigin` true diyor ama o navigasyon SPA'yı boşaltıyordu.
    const p = sahtePencere(SAYFA); applyNavigationPolicy(p.win)
    const e = olay()
    p.kancalar['will-navigate'](e, 'http://localhost:8888/test-dosyasi.txt')
    expect(e.engellendi).toBe(true)
    expect(acilanDisLinkler).toEqual([]) // origin-içi dışarı AÇILMAMALI
  })

  it('SORGU DİZESİ farkı da engelleniyor', () => {
    const p = sahtePencere(SAYFA); applyNavigationPolicy(p.win)
    const e = olay()
    p.kancalar['will-navigate'](e, 'http://localhost:8888/home/?conversation=63')
    expect(e.engellendi).toBe(true)
  })

  it('DIŞ adres engelleniyor ve işletim sistemine veriliyor', () => {
    // ⚠️ Bu iddia `isOwnOrigin`'i GERÇEKTEN çalıştırıyor. Denetçinin
    // "isOwnOrigin → return true" mutantı tam burada ölüyor: mutant altında
    // dış adres aynı belge sayılmayıp yine engellenirdi ama DIŞARI AÇILMAZDI.
    const p = sahtePencere(SAYFA); applyNavigationPolicy(p.win)
    const e = olay()
    p.kancalar['will-navigate'](e, 'https://evil.example/giris')
    expect(e.engellendi).toBe(true)
    expect(acilanDisLinkler).toEqual(['https://evil.example/giris'])
  })

  it('AYRIŞTIRILAMAYAN adres FAIL-CLOSED', () => {
    const p = sahtePencere('bozuk adres'); applyNavigationPolicy(p.win)
    const e = olay()
    p.kancalar['will-navigate'](e, SAYFA)
    expect(e.engellendi).toBe(true)
  })
})

describe('will-redirect', () => {
  beforeEach(() => { acilanDisLinkler.length = 0 })

  it('origin-İÇİ yönlendirme GEÇİYOR — ürünün kendi açılışı buradan geçiyor', () => {
    // ⚠️ YAŞANMIŞ ARIZA: `trailingSlash: true` yüzünden dev sunucusu
    // `/home` → `/home/` kanonikleştirmesini 302 ile yapıyor. İlk sürüm bunu
    // da kesti ve uygulama HİÇ AÇILMADI.
    const p = sahtePencere(SAYFA); applyNavigationPolicy(p.win)
    const e = olay()
    p.kancalar['will-redirect'](e, 'http://localhost:8888/home/')
    expect(e.engellendi).toBe(false)
  })

  it('DIŞARI çıkan yönlendirme engelleniyor', () => {
    const p = sahtePencere(SAYFA); applyNavigationPolicy(p.win)
    const e = olay()
    p.kancalar['will-redirect'](e, 'https://evil.example/')
    expect(e.engellendi).toBe(true)
    expect(acilanDisLinkler).toEqual(['https://evil.example/'])
  })
})

describe('webview ve yeni pencere', () => {
  beforeEach(() => { acilanDisLinkler.length = 0 })

  it('webview eklenmesi koşulsuz reddediliyor', () => {
    const p = sahtePencere(SAYFA); applyNavigationPolicy(p.win)
    const e = olay()
    p.kancalar['will-attach-webview'](e)
    expect(e.engellendi).toBe(true)
  })

  it('yeni pencere DENY ediliyor, http dışarı gidiyor', () => {
    const p = sahtePencere(SAYFA); applyNavigationPolicy(p.win)
    expect(p.pencereAcmaKancasi!({ url: 'https://ornek.com' })).toEqual({ action: 'deny' })
    expect(acilanDisLinkler).toEqual(['https://ornek.com'])
  })

  it('http OLMAYAN şema dışarı VERİLMİYOR', () => {
    // `shell.openExternal` bir `file:`/özel şemayı işletim sistemine
    // çalıştırtabilir; şema kontrolü pazarlık konusu değil.
    const p = sahtePencere(SAYFA); applyNavigationPolicy(p.win)
    expect(p.pencereAcmaKancasi!({ url: 'file:///C:/Windows/System32/calc.exe' }))
      .toEqual({ action: 'deny' })
    expect(acilanDisLinkler).toEqual([])
  })
})

describe('isOwnOrigin DAVRANIŞI', () => {
  // ⚠️ Denetçi bulgusu `isownorigin-behavior-mutation`: bu fonksiyonu koşulsuz
  // `true` yapan mutant tüm suite'i geçiyordu. Aşağısı onu doğrudan ölçüyor.
  it('dev: kendi loopback adresimiz', () => {
    expect(isOwnOrigin('http://localhost:8888/home/')).toBe(true)
    expect(isOwnOrigin('http://127.0.0.1:8888/home/')).toBe(true)
  })

  it('dev: yabancı host REDDEDİLİYOR', () => {
    expect(isOwnOrigin('http://evil.example/home/')).toBe(false)
    expect(isOwnOrigin('https://localhost:8888/home/')).toBe(false)
    expect(isOwnOrigin('app://./home/')).toBe(false) // dev'de app: bizim değil
  })

  it('ayrıştırılamayan adres REDDEDİLİYOR', () => {
    expect(isOwnOrigin('bozuk')).toBe(false)
    expect(isOwnOrigin('')).toBe(false)
  })

  it('PROD dalı: yalnız app:// ve host "." ya da boş', async () => {
    // `isProd` modül yüklenirken hesaplanıyor, o yüzden modül yeniden yükleniyor.
    // (`process.env.NODE_ENV`'e doğrudan atama tsc'de salt-okunur; `stubEnv` şart.)
    try {
      vi.resetModules()
      vi.stubEnv('NODE_ENV', 'production')
      const { isOwnOrigin: prodOwn } = await import('../main/helpers/ipc-trust')
      expect(prodOwn('app://./home/')).toBe(true)
      expect(prodOwn('app:///home')).toBe(true)
      // ⭐ Asıl mesele: `app://evil/` de bir `app:` adresi. `URL.origin`
      // kayıtlı olmayan şemalarda sabit "null" döndürdüğü için naif bir
      // origin eşitliği bunu BİZE eşit sayardı.
      expect(prodOwn('app://evil/home/')).toBe(false)
      expect(prodOwn('http://localhost:8888/home/')).toBe(false)
    } finally {
      vi.unstubAllEnvs()
      vi.resetModules()
    }
  })
})

describe('politika createWindow tarafından KURULUYOR', () => {
  /**
   * ⚠️ Bu tek iddia kaynak metnine bakıyor ve sınırı açıkça yazılmalı:
   * Electron ana süreci test koşumunda yüklenmiyor, dolayısıyla `createWindow`
   * gerçekten çağrılamıyor.
   *
   * Ölçüldü — yakaladıkları: çağrının silinmesi, yoruma alınması, tek satırlık
   * bir koşula sarılması (`if (false) applyNavigationPolicy(win)`).
   * Yakalayamadıkları: çağrının çok satırlı ölü bir bloğun İÇİNE alınması,
   * başka bir `webContents` üzerine kurulması, ya da politikanın kendi
   * gövdesinin boşaltılması (onu üstteki davranış testleri yakalıyor).
   *
   * Depoda canlı bir Electron test koşum ortamı yok; o AÇIK bir iş kalemi ve
   * bu testin bunu kapattığı iddia EDİLMİYOR.
   */
  it('createWindow gövdesi applyNavigationPolicy çağırıyor', () => {
    const src = fs.readFileSync(
      path.resolve(__dirname, '../main/helpers/create-window.ts'), 'utf8',
    )
    const govde = src.split('export const createWindow')[1]
    // ⚠️ `toContain` YETMİYOR — ölçüldü. Çağrıyı YORUMA ALAN bir mutant
    // (`// applyNavigationPolicy(win)`) o iddiayı geçiyordu, çünkü yorumlanmış
    // satır da aynı dizgeyi içeriyor. Denetçinin uyarısının canlı örneği:
    // kaynağa bakan bir test, kodun DAVRANIŞINI değil YAZIMINI ölçüyor.
    // Ölçüt: satır, başında yorum işareti olmadan, tek başına durmalı.
    expect(govde).toMatch(/^[ \t]*applyNavigationPolicy\(win\)[ \t]*$/m)
  })
})
