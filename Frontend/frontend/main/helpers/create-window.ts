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
const applyNavigationPolicy = (win: BrowserWindow) => {
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
    try {
      const hedef = new URL(url)
      const mevcut = new URL(win.webContents.getURL())
      if (hedef.pathname === mevcut.pathname) return
      event.preventDefault()
      console.warn(
        '[nav-policy] origin-içi ama BAŞKA yola gitmeye çalışan navigasyon engellendi:',
        hedef.pathname,
      )
    } catch {
      // Mevcut URL henüz yoksa (ilk yükleme) karşılaştıracak bir şey yok;
      // engellemek açılışı kırardı.
    }
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
