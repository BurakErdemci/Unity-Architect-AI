import fs from 'fs'
import path from 'path'

/**
 * Symlink-safe path resolver.
 * An existing path is canonicalised; a path that does not exist yet is resolved
 * down to its nearest existing ancestor, with the missing segments appended, so
 * that writing a NEW file under a symlinked directory is caught as well.
 *
 * ⚠️ `realpathSync.native`, not `realpathSync`. The JS implementation resolves
 * links but leaves an NTFS 8.3 short name as it found it — measured on this
 * repo's Windows: `<ws>\HARVES~1.GLB` came back as itself, while the native call
 * returned `<ws>\harvested-credentials.glbx`. Every caller here decides on the
 * resolved string and then opens it, so the two spellings have to collapse into
 * one before the decision. It cut both ways: the extension whitelist judged the
 * alias (`.GLB`) while `openSync` opened the real `.glbx`, and a workspace named
 * through its OWN short path was refused because it no longer matched itself.
 * The two calls throw the same errors, so the surrounding fallbacks are unchanged.
 */
function safeResolve(filePath: string): string {
  try {
    const absolutePath = path.resolve(filePath)
    if (fs.existsSync(absolutePath)) {
      return fs.realpathSync.native(absolutePath)
    }

    let currentPath = absolutePath
    const missingSegments: string[] = []

    while (!fs.existsSync(currentPath)) {
      const parentPath = path.dirname(currentPath)
      if (parentPath === currentPath) {
        return absolutePath
      }
      missingSegments.unshift(path.basename(currentPath))
      currentPath = parentPath
    }

    const resolvedExistingPath = fs.realpathSync.native(currentPath)
    return path.join(resolvedExistingPath, ...missingSegments)
  } catch {
    // realpath failed — fall through to the plain resolve below
  }
  return path.resolve(filePath)
}

/**
 * Uygulama içinden okunup yazılabilen metin dosyası uzantıları.
 * Editörde açma/kaydetme izni bu listeye bakar (dosya ağacı ise artık HER
 * dosyayı listeler; binary'ler görünür ama açılamaz). Unity'nin YAML tabanlı
 * asset formatları (prefab/anim/scene/mat…) metindir — editörde açılabilir.
 * Çalıştırılabilir/binary türler (fbx, png, dll…) bilerek dışarıda.
 */
export const TEXT_FILE_EXTENSIONS = [
  '.cs', '.shader', '.json', '.txt', '.md', '.xml', '.yaml', '.yml',
  '.compute', '.asmdef', '.asmref', '.cginc', '.hlsl', '.uss', '.uxml',
  // Unity YAML asset formatları
  '.anim', '.prefab', '.unity', '.mat', '.asset', '.controller',
  '.overridecontroller', '.physicmaterial', '.physicsmaterial2d', '.mixer',
  '.rendertexture', '.spriteatlas', '.terrainlayer', '.playable', '.signal',
  '.preset', '.guiskin', '.fontsettings', '.flare', '.giparams',
  '.shadervariants', '.mask', '.brush', '.meta',
  // Diğer metin türleri
  '.inputactions', '.csv', '.html', '.css', '.js', '.ini', '.cfg', '.rsp',
]

/**
 * Extension whitelist for the 3D model read channel.
 *
 * Whitelist, not blacklist: a model channel that could also hand back `.env` or
 * `.pem` is an exfiltration surface even when the file sits inside the
 * workspace, so the model gate names what it accepts instead of what it refuses.
 * Renderer keeps a mirror of this list (`MODEL_EXTENSIONS`); a test asserts the
 * two stay set-equal.
 */
export const MODEL_FILE_EXTENSIONS = [
  '.fbx', '.glb', '.gltf', '.dae', '.obj', '.stl', '.ply',
]

/**
 * The model channel's own size cap, independent of the 8 MiB text cap.
 *
 * The bytes cross IPC as an ArrayBuffer, which is *copied* into the renderer
 * heap; an unbounded read therefore inflates both Electron processes at once.
 */
export const MODEL_MAX_BYTES = 64 * 1024 * 1024

/**
 * Yazma/okuma izni sadece workspace içindeki Assets/Scripts/*.cs dosyalarına verilir.
 * Path traversal, symlink ve dışarı çıkış girişimlerini engeller.
 */
export function isAllowedUnityScriptPath(filePath: string, workspacePath: string): boolean {
  try {
    if (!filePath || !workspacePath) return false

    // Eğer yol absolute değilse, önce workspace ile birleştirip öyle kontrol etmeliyiz
    const absoluteFilePath = path.isAbsolute(filePath) ? filePath : path.resolve(workspacePath, filePath)

    const resolvedFile = safeResolve(absoluteFilePath)
    const resolvedWorkspace = safeResolve(workspacePath)
    const relativePath = path.relative(resolvedWorkspace, resolvedFile)

    // Workspace dışına çıkış kontrolü
    if (!relativePath || relativePath.startsWith('..') || path.isAbsolute(relativePath)) {
      return false
    }

    const parts = relativePath.split(path.sep).filter(Boolean)
    if (parts.length < 3 || parts[0] !== 'Assets' || parts[1] !== 'Scripts') {
      return false
    }

    // Sadece Assets/Scripts altındaki .cs dosyalarına yazma izni ver
    return path.extname(resolvedFile).toLowerCase() === '.cs'
  } catch {
    return false
  }
}

/**
 * Workspace dosya ağacını gezerken yalnızca seçili workspace içindeki yol okunabilir.
 * Symlink çözümü dahildir.
 */
export function isAllowedWorkspacePath(targetPath: string, workspacePath: string): boolean {
  try {
    if (!targetPath || !workspacePath) return false

    const resolvedTarget = safeResolve(targetPath)
    const resolvedWorkspace = safeResolve(workspacePath)
    const relativePath = path.relative(resolvedWorkspace, resolvedTarget)

    if (!relativePath) {
      return true
    }

    return !relativePath.startsWith('..') && !path.isAbsolute(relativePath)
  } catch {
    return false
  }
}

/** Çözülmüş iki yol arasında kapsama kontrolü — ikisi de ÇÖZÜLMÜŞ olmalı. */
function icerideMi(cozulmusHedef: string, cozulmusWorkspace: string): boolean {
  const rel = path.relative(cozulmusWorkspace, cozulmusHedef)
  if (!rel) return true
  return !rel.startsWith('..') && !path.isAbsolute(rel)
}

/**
 * Yol bir NTFS alternatif veri akışını mı adlandırıyor?
 *
 * Windows `host.exe:notes.txt` yazımını `host.exe`'nin `notes.txt` akışı olarak
 * okuyor, ama `path.extname` sondaki `.txt`'yi dosyanın uzantısı sanıyor.
 * Sonuç: uzantı beyaz listesi, aslında `.exe` olan bir dosyanın baytlarını
 * yetkilendiriyordu — ve o akış dizin listesinde hiç görünmüyor (dış denetim
 * bulgusu, probe ile üretildi). Sürücü harfindeki iki nokta (`C:\`) meşru, o
 * yüzden yalnız ondan SONRAKİ kısma bakılıyor.
 *
 * ⚠️ YALNIZ Windows (doğrulama turu bulgusu
 * `ads-check-rejects-legitimate-posix-paths`): POSIX'te iki nokta sıradan bir
 * dosya adı karakteri, üstelik macOS Finder'da `/` içeren bir klasör adı disk
 * üzerinde `:` olarak saklanıyor. Platform koşulu olmadan bu kontrol orada
 * meşru dosyaları sessizce açılamaz yapıyordu.
 *
 * `platform` parametre: `process.platform` test koşumunda değiştirilemiyor, ve
 * platforma bağlı bir dalı sınayamamak bu depoda ölçülmüş bir arıza sınıfı.
 */
export function alternatifVeriAkisiMi(
  cozulmusYol: string,
  platform: string = process.platform,
): boolean {
  if (platform !== 'win32') return false
  const surucusuz = cozulmusYol.length > 2 && cozulmusYol[1] === ':'
    ? cozulmusYol.slice(2)
    : cozulmusYol
  return surucusuz.includes(':')
}

/**
 * Which kind of read the gate is deciding on.
 * The gates are identical; only the extension whitelist differs.
 */
export type OkumaTuru = 'metin' | 'model'

/**
 * Why the gate refused. `unsupported` is the extension whitelist alone; the
 * path-level gates (containment, ADS, hardlink) get their own code so a caller
 * can tell "wrong file type" apart from "this file is out of bounds".
 */
export type RedSebebi = 'unsupported' | 'denied'

/** Okuma kapısının kararı ve o kararın DAYANDIĞI çözülmüş yol. */
export type OkumaKarari = {
  izinli: boolean
  cozulmusYol: string
  sebep?: RedSebebi
}

/**
 * Okuma kapısının tek karar noktası: yolu BİR KEZ çözer, kararı o çözülmüş yol
 * üzerinde verir ve açılması gereken yolu da geri döndürür.
 *
 * ⚠️ Doğrulama turu bulgusu (`check-open-resolve-divergence`): bir önceki
 * düzeltme "ham yol yerine çözülmüş yolu aç" diyordu, ama kapı kendi içinde bir
 * kez, çağıran ikinci kez çözüyordu. İki çözüm arasında bir ara bileşen
 * junction'a çevrilince kontrol edilen dosya ile açılan dosya yine ayrışıyordu —
 * yani düzeltme, kapattığını SANDIĞI yarışı kapatmamıştı. Karar ile açış artık
 * aynı dizgeye bakıyor.
 *
 * ⚠️ Tek çözüm yarışı DARALTIR, kapatmaz: bu yolun bir bileşeni açıştan hemen
 * önce de değiştirilebilir. Sınıfı kapatan kontrol çağırandaki AÇILMIŞ TANITICI
 * doğrulaması (`background.ts`) — o yola değil inode'a bakıyor, dolayısıyla
 * açıştan sonra yapılan bir takas kararı geriye dönük bozamıyor.
 */
export function okumaKarariVer(
  filePath: string,
  workspacePath: string,
  tur: OkumaTuru = 'metin',
): OkumaKarari {
  const reddet = (yol: string, sebep: RedSebebi = 'denied'): OkumaKarari =>
    ({ izinli: false, cozulmusYol: yol, sebep })
  try {
    if (!filePath || !workspacePath) return reddet('')

    const cozulmus = safeResolve(filePath)
    const cozulmusWs = safeResolve(workspacePath)

    if (!icerideMi(cozulmus, cozulmusWs)) return reddet(cozulmus)

    // Gerekçesi `alternatifVeriAkisiMi`'nin başında.
    if (alternatifVeriAkisiMi(cozulmus)) return reddet(cozulmus)

    // ⚠️ SABİT BAĞ (dış denetim bulgusu, probe ile üretildi). `realpathSync`
    // sembolik bağı ve junction'ı çözüyor, ama sabit bağ bir bağ DEĞİL — ikinci
    // bir addır. Gerçek yolu workspace içinde kalır, baytları dışarıdaki
    // dosyanındır, dolayısıyla kapsama kontrolü onu kabul ediyordu.
    //
    // ⭐ Aynı sınıf backend'de ZATEN kapalıydı (`safe_paths._dogrula_kimlik`,
    // `st_nlink > 1`). Yani bu, güvenlik kararının iki kopyasının ayrışmasıydı —
    // bu depoda adı konmuş bir arıza sınıfı. Karar burada tekrar ediliyor çünkü
    // iki süreç ayrı: Python backend'in kontrolü Electron ana sürecini kapsamaz.
    //
    // Dizinler muaf: NTFS'te dizinlerin bağlantı sayısı alt dizin sayısıyla
    // birlikte artıyor, yani onlarda `> 1` normaldir.
    //
    // ⚠️ EN İYİ ÇABA, varlık ŞARTI DEĞİL. Bu fonksiyon saf bir yol politikası
    // olarak da çağrılıyor (var olmayan yollarla; testleri buna dayanıyor),
    // dolayısıyla "dosya yok" burada bir RED sebebi olamaz. Sınıfı kapatan
    // KESİN kontrol zaten `read-file` handler'ında, AÇILMIŞ TANITICI üzerinde
    // koşuyor — yola değil inode'a bakıyor, yani kontrol/kullanım yarışına da
    // kapalı. Buradaki erken eleme onu tamamlıyor, yerine geçmiyor.
    try {
      const st = fs.lstatSync(cozulmus)
      if (st.isFile() && st.nlink > 1) {
        return reddet(cozulmus)
      }
    } catch {
      /* yol henüz yok ya da okunamıyor — kararı fd üzerindeki kontrol verecek */
    }

    // Only the whitelist differs between the two read kinds; every gate above
    // this line is shared, so the two decisions cannot drift apart.
    const beyazListe = tur === 'model' ? MODEL_FILE_EXTENSIONS : TEXT_FILE_EXTENSIONS
    if (!beyazListe.includes(path.extname(cozulmus).toLowerCase())) {
      return reddet(cozulmus, 'unsupported')
    }

    return { izinli: true, cozulmusYol: cozulmus }
  } catch {
    return reddet('')
  }
}

/**
 * Saf yol politikası — çağıranın açacağı yolu ÖĞRENMESİ gerekmiyorsa bu yeter.
 * Okuyup açacak olan `okumaKarariVer`'i çağırmalı: yalnız o, kararın hangi
 * çözülmüş yola dayandığını söylüyor.
 */
export function isAllowedWorkspaceReadFile(filePath: string, workspacePath: string): boolean {
  return okumaKarariVer(filePath, workspacePath).izinli
}

/**
 * AÇILMIŞ bir tanıtıcının hâlâ workspace içindeki bir dosyayı gösterdiğini
 * doğrular. Okuma kapısında sınıfı asıl kapatan kontrol budur.
 *
 * Yolu bir kez çözmek yarışı DARALTIR ama kapatmaz — açılacak yolun bir bileşeni
 * `openSync` çağrısından hemen önce de takas edilebilir. Bu yüzden açıştan
 * SONRA iki şey birlikte soruluyor:
 *   (1) yol şu an hâlâ workspace içinde bir dosyayı adlandırıyor mu,
 *   (2) elimizdeki tanıtıcı gerçekten O dosya mı (aygıt + inode).
 * Yalnız (1) olsaydı saldırgan açıştan sonra geri takas edip kontrolü
 * kandırırdı; yalnız (2) olsaydı dışarıdaki bir dosya kendisiyle eşleşip
 * geçerdi. İkisi birlikte açılmış tanıtıcıyı kapsama kararına bağlıyor — ve bir
 * tanıtıcının hangi dosyayı gösterdiği, açıldıktan sonra artık değiştirilemez.
 *
 * ⚠️ Bu mantık bilerek `background.ts` içinde SATIR İÇİ bırakılmadı: ana süreç
 * test koşumunda yüklenmiyor, dolayısıyla orada kalan her kontrol sınanamaz
 * oluyor. Aynı ders bu depoda aynı denetim turunda iki kez ödendi.
 *
 * @param acilanStat açılmış tanıtıcının `fstatSync` sonucu — yolun değil.
 */
export function taniticiKapsamdaMi(
  acilanStat: fs.Stats,
  acilanYol: string,
  workspacePath: string,
): boolean {
  try {
    // Ayrıca `realpathSync` ÇAĞRILMIYOR: aşağıdaki ikisi de yolu kendi içinde
    // zaten çözüyor (`isAllowedWorkspacePath` → `safeResolve`, `statSync` →
    // bağları takip eder). Fazladan bir çözüm adımı mutasyonla ölçüldüğünde
    // hiçbir mutantı yakalamıyordu — yani davranışa katkısı yok, yalnız
    // "burada bir şey yapılıyor" izlenimi veriyordu.
    if (!isAllowedWorkspacePath(acilanYol, workspacePath)) return false
    const kimlik = fs.statSync(acilanYol)
    return kimlik.ino === acilanStat.ino && kimlik.dev === acilanStat.dev
  } catch {
    return false
  }
}

export type ModelOkumaSonucu =
  | { path: string; name: string; data: ArrayBuffer }
  | { error: 'unsupported' | 'too-large' | 'denied' }

/**
 * The model read, gate chain included, from one open file descriptor.
 *
 * ⚠️ Deliberately NOT inlined in `background.ts`: the main process is not loaded
 * under the test runner, so anything left there cannot be exercised — a lesson
 * this repo has already paid for twice (see `taniticiKapsamdaMi`). The handler
 * keeps the sender-trust and workspace-trust guards and delegates the rest here.
 *
 * The fd is opened ONCE and every later question (size, hardlink, containment,
 * the read itself) is asked of that descriptor. Reopening by path after a check
 * would reintroduce the measured check/use race.
 */
export function readModelFileFromWorkspace(
  fullPath: string,
  workspacePath: string,
): ModelOkumaSonucu {
  const karar = okumaKarariVer(fullPath, workspacePath, 'model')
  if (!karar.izinli) return { error: karar.sebep ?? 'denied' }

  let fd: number | null = null
  try {
    fd = fs.openSync(karar.cozulmusYol, 'r')
    const st = fs.fstatSync(fd)
    if (!st.isFile()) return { error: 'denied' }
    if (st.size > MODEL_MAX_BYTES) return { error: 'too-large' }
    // Rechecked on the fd: catches a second name created between the gate and
    // the open.
    if (st.nlink > 1) return { error: 'denied' }
    if (!taniticiKapsamdaMi(st, karar.cozulmusYol, workspacePath)) {
      return { error: 'denied' }
    }

    // Read EXACTLY the size the cap was checked against, not "until EOF":
    // `readFileSync(fd)` would follow a file that grew after `fstatSync` and so
    // hand back more bytes than `MODEL_MAX_BYTES` allows. Reading into an
    // ArrayBuffer of our own also keeps Buffer's shared pool out of the payload.
    const data = new ArrayBuffer(st.size)
    const view = new Uint8Array(data)
    let okunan = 0
    while (okunan < st.size) {
      const n = fs.readSync(fd, view, okunan, st.size - okunan, okunan)
      if (n <= 0) break
      okunan += n
    }
    if (okunan !== st.size) return { error: 'denied' }
    // `fullPath` is returned rather than the resolved path, for the same reason
    // the text handler does it: the file tree addresses files by this name.
    return { path: fullPath, name: path.basename(fullPath), data }
  } catch {
    return { error: 'denied' }
  } finally {
    if (fd !== null) { try { fs.closeSync(fd) } catch { /* close failure does not invalidate the read */ } }
  }
}

/**
 * Dosya yazma izni: workspace içi + metin beyaz listesi.
 * - .cs için eski kural KORUNUR (yalnızca Assets/Scripts altı — AI kod üretimi oraya akar).
 * - Diğer metin türleri (md, txt, json, shader…) workspace içinde her yere yazılabilir
 *   (örn. kök dizinde CLAUDE.md oluşturma). Path traversal/symlink koruması aynen.
 */
export function isAllowedWorkspaceWriteFile(filePath: string, workspacePath: string): boolean {
  try {
    if (!filePath || !workspacePath) return false

    const absoluteFilePath = path.isAbsolute(filePath) ? filePath : path.resolve(workspacePath, filePath)
    const ext = path.extname(safeResolve(absoluteFilePath)).toLowerCase()

    if (ext === '.cs') {
      return isAllowedUnityScriptPath(filePath, workspacePath)
    }
    if (!TEXT_FILE_EXTENSIONS.includes(ext)) {
      return false
    }
    return isAllowedWorkspacePath(absoluteFilePath, workspacePath)
  } catch {
    return false
  }
}
