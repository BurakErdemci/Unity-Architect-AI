import fs from 'fs'
import path from 'path'
import { app, IpcMainInvokeEvent } from 'electron'

/**
 * IPC güven katmanı — 2026-07-27 denetiminin D grubu bulguları.
 *
 * Denetimde ölçülen sorun tek bir kökten çıkıyordu: main süreç HER IPC
 * çağıranını meşru arayüz sayıyordu. Somut sonuçları:
 *
 *   - `app-token-get` backend bearer'ını soran her belgeye veriyordu
 *   - `terminal-spawn` + `terminal-write` kullanıcının kabuğunu açıp içine
 *     keyfi byte yazıyordu; gönderen, cwd ya da onay hiç kontrol edilmiyordu
 *   - Dosya uçlarında sınırın KENDİSİ (`workspacePath`) çağırandan geliyordu;
 *     saldırgan `read-file($HOME/.codex/auth.json, $HOME)` diyerek kimlik
 *     bilgisi okuyabiliyordu — hapis, hapsedilenin seçtiği bir hapisti
 *
 * İki bağımsız savunma var, çünkü tek başına ikisi de yetmiyor:
 *
 *   1. KAYNAK KAPISI (`isOwnFrame`): çağrı bizim sayfamızdan mı geliyor?
 *      Uzak bir belgenin renderer'a girmesini gezinme politikası zaten
 *      engelliyor (bkz. create-window.ts); bu, o politikanın delindiği
 *      durumda ikinci kilit.
 *   2. YETKİLİ KÖK KÜTÜĞÜ (`isTrustedRoot`): workspace kökü yalnızca
 *      kullanıcının NATIVE diyalogla seçtiği bir yol olabilir. Renderer ele
 *      geçse bile daha geniş bir kök uyduramaz.
 */

const isProd = process.env.NODE_ENV === 'production'

// Nextron dev'de pencereyi `electron . <port>` diye başlatır. Prod'da argv[2]
// port değil (OS'un geçirdiği herhangi bir argüman olabilir), o yüzden yalnızca
// sayıysa ve yalnızca dev'de kabul ediliyor.
const devPort = /^\d+$/.test(process.argv[2] || '') ? process.argv[2] : null

/**
 * Uygulamanın kendi origin'i: prod'da electron-serve'ün `app://./home` adresi
 * (host '.'), dev'de Next dev sunucusu.
 *
 * Neden `url.origin` ile karşılaştırılmıyor: `app:` non-special bir şema ve
 * `new URL('app://./home').origin` JavaScript'te "null" STRING'ini döndürüyor.
 * Naif bir origin eşitliği bu yüzden her `app:` URL'ini birbirine — ve saldırgan
 * bir `app://evil/` adresini bize — eşit sayardı. Protokol ve host ayrı bakılıyor.
 */
export const isOwnOrigin = (rawUrl: string): boolean => {
  let url: URL
  try {
    url = new URL(rawUrl)
  } catch {
    return false
  }

  if (isProd) {
    return url.protocol === 'app:' && (url.host === '.' || url.host === '')
  }

  if (url.protocol !== 'http:') return false
  if (url.hostname !== 'localhost' && url.hostname !== '127.0.0.1') return false
  // Port bilinmiyorsa (argv[2] verilmeden elle başlatılan dev oturumu) loopback'in
  // tamamına izin ver; aksi halde HMR reload'ları engellenir. Prod'a sızmaz çünkü
  // bu dal yalnızca dev'de çalışıyor.
  return devPort === null || url.port === devPort
}

/**
 * IPC çağrısı bizim sayfamızdan mı geldi?
 *
 * `senderFrame` iframe dahil gerçek gönderen çerçeveyi verir; `sender.getURL()`
 * üst çerçeveyi döndürdüğü için gömülü bir üçüncü-taraf çerçeve onunla ayırt
 * edilemezdi. Çerçeve yoksa (destroyed) reddediyoruz — bilinmeyen gönderen,
 * güvenilmeyen gönderendir.
 */
export const isOwnFrame = (event: IpcMainInvokeEvent): boolean => {
  const frameUrl = event.senderFrame?.url
  if (!frameUrl) return false
  return isOwnOrigin(frameUrl)
}

// ── Yetkili workspace kökleri ────────────────────────────────────────────────

/**
 * Kütük neden KALICI: kullanıcı klasörü bir kez seçiyor, sonraki açılışlarda
 * workspace backend'in "son workspace" kaydından geri yükleniyor ve o akış
 * native diyalogdan geçmiyor. Kütük diske yazılmasaydı her yeniden başlatmada
 * dosya ağacı ölürdü — yani güvenlik düzeltmesi ürünü kırardı.
 */
const registryPath = () => path.join(app.getPath('userData'), 'trusted-workspaces.json')

let trustedRoots: string[] | null = null

const normalize = (p: string): string | null => {
  try {
    if (!p) return null
    const abs = path.resolve(p)
    // Symlink'i çöz: aksi halde workspace'in içine kurulan bir bağ, kütükteki
    // kök ile karşılaştırmayı geçip başka bir ağaca işaret edebilirdi.
    return fs.existsSync(abs) ? fs.realpathSync(abs) : abs
  } catch {
    return null
  }
}

const load = (): string[] => {
  if (trustedRoots) return trustedRoots
  try {
    const raw = fs.readFileSync(registryPath(), 'utf-8')
    const parsed = JSON.parse(raw)
    trustedRoots = Array.isArray(parsed) ? parsed.filter((x) => typeof x === 'string') : []
  } catch {
    trustedRoots = []
  }
  return trustedRoots
}

const persist = () => {
  try {
    fs.writeFileSync(registryPath(), JSON.stringify(trustedRoots ?? [], null, 2), { mode: 0o600 })
  } catch (err: any) {
    console.error('[ipc-trust] kütük yazılamadı:', err?.message || err)
  }
}

/**
 * Bir kökü yetkili listesine ekler. YALNIZCA native klasör diyaloğunun sonucu
 * ve kullanıcının uygulamayı ilk kez bu sürümle açtığındaki tek seferlik devir
 * (bkz. adoptLegacyRoot) buraya girer — renderer'dan gelen bir yol asla.
 */
export const registerTrustedRoot = (rawPath: string): void => {
  const root = normalize(rawPath)
  if (!root) return
  const roots = load()
  if (!roots.includes(root)) {
    roots.push(root)
    persist()
    console.log('[ipc-trust] yetkili workspace eklendi:', root)
  }
}

/** Yol, yetkili köklerden birinin kendisi mi ya da altında mı? */
export const isTrustedRoot = (rawPath: string): boolean => {
  const target = normalize(rawPath)
  if (!target) return false
  return load().some((root) => target === root || target.startsWith(root + path.sep))
}

/**
 * Bu sürümden ÖNCE seçilmiş bir workspace kütükte yoktur; kullanıcı hiçbir şey
 * yapmadığı hâlde dosya ağacı ölürdü. Kütük tamamen boşken ilk geçerli dizin bir
 * kez devralınıyor.
 *
 * Bunun bir taviz olduğu açık yazılsın: kütük boşken ilk isteği yapan taraf kökü
 * belirler. Kabul edilebilir çünkü pencere yalnızca "hiç workspace seçilmemiş"
 * ilk açılışa kadar açık ve o an henüz saldırgan bir sayfa yüklenmiş olamaz —
 * kütük dolduktan sonra bu yol bir daha çalışmıyor. Kalıcı çözüm, kullanıcının
 * klasörü bir kez native diyalogla yeniden seçmesi.
 */
export const adoptLegacyRoot = (rawPath: string): boolean => {
  if (load().length > 0) return false
  const root = normalize(rawPath)
  if (!root) return false
  try {
    if (!fs.statSync(root).isDirectory()) return false
  } catch {
    return false
  }
  console.warn('[ipc-trust] kütük boştu, mevcut workspace bir kez devralındı:', root)
  registerTrustedRoot(root)
  return true
}
