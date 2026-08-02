import {
  screen,
  shell,
  BrowserWindow,
  BrowserWindowConstructorOptions,
  Rectangle,
} from 'electron'
import Store from 'electron-store'
import { isOwnOrigin } from './ipc-trust'

// Origin tanımı bilerek burada DEĞİL: aynı kural IPC kapısında da gerekiyor ve
// iki kopya zamanla ayrışır (bu denetimde onay kapısının üç kopyası tam olarak
// böyle ayrışmıştı). Tek kaynak helpers/ipc-trust.ts.

// shell.openExternal işletim sistemine URL'i olduğu gibi verir: `file:` yerel bir
// dosyayı/exe'yi, özel şemalar da kayıtlı bir protokol handler'ını çalıştırabilir.
// O yüzden dışarı yalnızca http(s) çıkıyor — şema kontrolü pazarlık konusu değil.
const isExternallyOpenable = (rawUrl: string): boolean => {
  try {
    const protocol = new URL(rawUrl).protocol
    return protocol === 'http:' || protocol === 'https:'
  } catch {
    return false
  }
}

/**
 * İki adres AYNI BELGEYİ mi gösteriyor — yani navigasyon sayfayı boşaltır mı?
 *
 * ⚠️ Dışa aktarılmasının sebebi ölçülmüş: bu karşılaştırma `will-navigate`
 * handler'ının içinde satır içiydi ve ana süreç jsdom'da koşmadığı için hiçbir
 * test onu çalıştıramıyordu — doğrulama yalnız kaynak metnine regex atmaktan
 * ibaretti. Aynı arıza sınıfı bu turda backend'de de çıktı
 * (`test-double-divergence`). Satır içi mantık testten kaçıyor.
 *
 * Ölçüt "aynı yol" DEĞİL "aynı belge": sorgu dizesi değişen bir tam navigasyon
 * belgeyi yine boşaltıyor ve ilk sürüm buna izin veriyordu (dış denetim
 * bulgusu, probe ile üretildi).
 *
 * Hash BİLEREK dışarıda — `#bolum` belgeyi boşaltmıyor.
 * Sondaki eğik çizgi normalleştiriliyor: `next.config.js` `trailingSlash: true`
 * kullanıyor, yani `/home` ile `/home/` aynı sayfanın iki yazımı.
 *
 * Ayrıştırılamayan bir adreste FIRLATIR; çağıran onu fail-closed yorumluyor.
 *
 * ⚠️ `u.origin` KULLANILMIYOR (doğrulama turu bulgusu
 * `naive-origin-equality-reintroduced`). `origin`, kayıtlı olmayan her şema için
 * — üründe ÜRETİMDE kullanılan `app:` dahil — sabit `"null"` dizgesini
 * döndürüyor. Yani `origin`'e bakan bir karşılaştırma üretimde `app:///home` ile
 * `app://./home`'u, dahası `app://evil/home`'u da "aynı belge" sayıyordu; o
 * durumda navigasyonu durduran tek şey `isOwnOrigin` kalıyor ve ikincil savunma
 * hiç savunma olmuyordu. `protocol` + `host` açıkça karşılaştırılıyor —
 * `ipc-trust.ts` de aynı sebeple aynı şeyi yapıyor.
 */
export const ayniBelgeMi = (a: string, b: string): boolean => {
  const kimlik = (ham: string): string => {
    const u = new URL(ham)
    const yol = u.pathname.endsWith('/') ? u.pathname.slice(0, -1) : u.pathname
    return `${u.protocol}//${u.host}${yol}${u.search}`
  }
  return kimlik(a) === kimlik(b)
}

const openExternally = (rawUrl: string) => {
  if (!isExternallyOpenable(rawUrl)) return
  shell.openExternal(rawUrl).catch((err) => {
    console.error('[nav-policy] harici link açılamadı:', err?.message || err)
  })
}

/**
 * Pencerenin gezinme politikası. Sebebi somut bir zincir: model çıktısı Markdown
 * olarak render ediliyor, `[x](https://attacker/)` sıradan bir <a href> oluyor ve
 * tıklanınca TEK BrowserWindow uzak sayfaya gidiyordu. preload `window.ipc`'yi
 * koşulsuz expose ettiği için uzak sayfa terminal-spawn/write-file uçlarını
 * devralıp kullanıcı yetkisiyle kod çalıştırabiliyordu. Kapı burada kapanıyor.
 */
/**
 * Pencerenin gezinme politikasını kurar.
 *
 * ⚠️ Dışa aktarılmasının sebebi ölçülmüş (dış denetim, 2 Ağu 2026,
 * `navigation-policy-wiring-mutation` + `isownorigin-behavior-mutation`):
 * bu gövde `create-window.ts` içinde kapalıydı ve TAMAMEN silinebiliyordu —
 * `applyNavigationPolicy(win)` çağrısı kaldırıldığında 377 testin hepsi yeşil
 * kalıyordu. Aynı şekilde `isOwnOrigin` koşulsuz `true` yapıldığında da.
 * Yani uygulamanın gezinme güvenliğinin TAMAMI test kapsamı dışındaydı.
 *
 * `win` olarak yalnız `webContents.{setWindowOpenHandler,on,getURL}` kullanan
 * herhangi bir nesne yeterli; testler gerçek bir BrowserWindow'a muhtaç değil.
 */
export const applyNavigationPolicy = (win: BrowserWindow) => {
  // Yeni pencere/popup asla açılmaz: açılsaydı aynı preload'u ve dolayısıyla
  // window.ipc'yi miras alırdı. Dış linkler işletim sisteminin tarayıcısına gider.
  win.webContents.setWindowOpenHandler(({ url }) => {
    openExternally(url)
    return { action: 'deny' }
  })

  win.webContents.on('will-navigate', (event, url) => {
    if (!isOwnOrigin(url)) {
      event.preventDefault()
      openExternally(url)
      return
    }

    // ⚠️ Origin-içi olmak YETMİYOR (ölçülmüş arıza, 2 Ağu 2026). Sohbetteki
    // `[test.txt](test-dosyasi.txt)` gibi GÖRELİ bir link tarayıcı tarafından
    // uygulamanın kendi origin'ine çözülüyor (`app://./test-dosyasi.txt`), yani
    // `isOwnOrigin` true dönüyordu ve koşulsuz `return` navigasyonu geçiriyordu.
    // Sonuç: tek BrowserWindow o adrese gidiyor, SPA unload oluyor, kullanıcı
    // "uygulama resetlendi" diyor. Çökme olmadığı için hata sınırı da
    // yakalayamıyordu — bu yüzden arıza uzun süre yanlış sınıfta arandı.
    //
    // Ölçüm: ürün açılışta YALNIZ `/home` yüklüyor (background.ts) ve oradan
    // başka bir sayfaya giden tam navigasyon YOK (`next.tsx` erişilemez
    // boilerplate). Dolayısıyla meşru origin-içi navigasyon = AYNI sayfanın
    // yeniden yüklenmesi. Farklı bir yol istenmişse bu bir bağ/link kazasıdır.
    //
    // Bu İKİNCİL savunma: asıl düzeltme `MarkdownRenderer`'ın `a` override'ı.
    // Buranın işi, gözden kaçan başka bir `<a>`nın pencereyi boşaltamaması.
    //
    // ⚠️ ÖLÇÜT İKİ KEZ DEĞİŞTİ, ikisi de dış denetimin bulgusu:
    //
    //   1. İlk sürüm yalnız `pathname` karşılaştırıyordu. Ölçüldü: `?x=1` aynı
    //      pathname'e sahip, yani GEÇİYORDU — ve sorgu dizesi değişen bir tam
    //      navigasyon belgeyi yine boşaltıyor. Muhafız, var olma sebebi olan
    //      sınıfa açık kalmıştı. Doğru ölçüt "aynı yol" değil, **"aynı belge"**.
    //   2. `catch` dalı `preventDefault` ÇAĞIRMIYORDU, yani ayrıştırılamayan
    //      bir durumu izne çeviriyordu — fail-OPEN. Gerekçesi de yanlıştı:
    //      "ilk yükleme" diyordu, oysa açılış `loadURL` ile oluyor ve `loadURL`
    //      bu olayı hiç tetiklemiyor.
    //
    // Hash BİLEREK dışarıda: `#bolum` belgeyi boşaltmıyor ve zaten çoğu durumda
    // `will-navigate` değil sayfa-içi navigasyon üretiyor.
    // Sondaki eğik çizgi normalleştiriliyor: `next.config.js` `trailingSlash:
    // true` kullanıyor, yani `/home` ile `/home/` aynı sayfanın iki yazımı.
    try {
      if (ayniBelgeMi(url, win.webContents.getURL())) return
    } catch (err) {
      // ⚠️ FAIL-CLOSED. Karşılaştıramıyorsak izin VERMİYORUZ. Bilinmeyen bir
      // durumu izne çevirmek, muhafızı olmadığı hâle döndürür.
      event.preventDefault()
      console.warn('[nav-policy] navigasyon adresi karşılaştırılamadı, engellendi:', err)
      return
    }
    event.preventDefault()
    console.warn('[nav-policy] belgeyi boşaltacak navigasyon engellendi:', url)
  })

  // Sunucu tarafı yönlendirme AYRI bir olay: `will-navigate` yalnız ilk adresi
  // görüyor, 302 sonrası hedef denetlenmeden takip edilebiliyordu (dış denetim
  // bulgusu). İlk adrese verilen izin, görülmemiş bir son adrese izin değildir.
  //
  // ⚠️ KAPSAM DAR TUTULUYOR — ve bu bir arıza vakasından geliyor (2 Ağu 2026).
  // İlk hâli origin-İÇİ yönlendirmeleri de engelliyordu ve uygulama HİÇ
  // AÇILMADI: `next.config.js` `trailingSlash: true` kullandığı için dev
  // sunucusu `/home` → `/home/` kanonikleştirmesini bir 302 ile yapıyor, yani
  // ürünün kendi açılışı bu olaydan geçiyor. Beş deneme de engellendi, pencere
  // beyaz kaldı.
  //
  // Bulgunun gerçek çekirdeği zaten dış hedefti ("izin verilen bir origin-içi
  // navigasyon, dışarıya 302 ile çıkabiliyor") ve onu `isOwnOrigin` kapatıyor.
  // Origin-içi yönlendirme sunucumuzun kendi kanonikleştirmesi; onu kesmek
  // korumadan çok ürünü kırıyor.
  //
  // ⭐ Ders: fail-closed sertleştirmenin de bir kapsamı olmalı. "Daha çok
  // engelle" güvenlik değil, çalışmayan bir ürün — ve çalışmayan bir ürünün
  // güvenlik vaadi de yok.
  win.webContents.on('will-redirect', (event, url) => {
    if (isOwnOrigin(url)) return
    event.preventDefault()
    openExternally(url)
    console.warn('[nav-policy] dışarı çıkan yönlendirme engellendi:', url)
  })

  // Uygulama hiç <webview> kullanmıyor; enjekte edilen bir webview politikayı
  // atlatan ikinci bir webContents açacağı için baştan reddediliyor.
  win.webContents.on('will-attach-webview', (event) => {
    event.preventDefault()
  })
}

export const createWindow = (
  windowName: string,
  options: BrowserWindowConstructorOptions
): BrowserWindow => {
  const key = 'window-state'
  const name = `window-state-${windowName}`
  const store = new Store<Rectangle>({ name })
  const defaultSize = {
    width: options.width,
    height: options.height,
  }
  let state = {}

  const restore = () => store.get(key, defaultSize)

  const getCurrentPosition = () => {
    const position = win.getPosition()
    const size = win.getSize()
    return {
      x: position[0],
      y: position[1],
      width: size[0],
      height: size[1],
    }
  }

  const windowWithinBounds = (windowState, bounds) => {
    return (
      windowState.x >= bounds.x &&
      windowState.y >= bounds.y &&
      windowState.x + windowState.width <= bounds.x + bounds.width &&
      windowState.y + windowState.height <= bounds.y + bounds.height
    )
  }

  const resetToDefaults = () => {
    const bounds = screen.getPrimaryDisplay().bounds
    return Object.assign({}, defaultSize, {
      x: (bounds.width - defaultSize.width) / 2,
      y: (bounds.height - defaultSize.height) / 2,
    })
  }

  const ensureVisibleOnSomeDisplay = (windowState) => {
    const visible = screen.getAllDisplays().some((display) => {
      return windowWithinBounds(windowState, display.bounds)
    })
    if (!visible) {
      // Window is partially or fully not visible now.
      // Reset it to safe defaults.
      return resetToDefaults()
    }
    return windowState
  }

  const saveState = () => {
    if (!win.isMinimized() && !win.isMaximized()) {
      Object.assign(state, getCurrentPosition())
    }
    store.set(key, state)
  }

  state = ensureVisibleOnSomeDisplay(restore())

  const win = new BrowserWindow({
    ...state,
    ...options,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      ...options.webPreferences,
    },
  })

  // Politika createWindow'un içinde: her pencere buradan doğduğu için ileride
  // eklenecek bir pencerenin bunu unutması mümkün olmuyor.
  applyNavigationPolicy(win)

  win.on('close', saveState)

  return win
}
