import fs from 'fs'
import path from 'path'

/**
 * Symlink-safe path çözücü.
 * Yol mevcutsa fs.realpathSync ile gerçek yolu çözer.
 * Yol henüz mevcut değilse, en yakın mevcut parent dizini realpath ile çözüp
 * kalan path segmentlerini onun üzerine ekler. Böylece symlink klasör altına
 * yeni dosya yazma girişimleri de doğru şekilde yakalanır.
 */
function safeResolve(filePath: string): string {
  try {
    const absolutePath = path.resolve(filePath)
    if (fs.existsSync(absolutePath)) {
      return fs.realpathSync(absolutePath)
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

    const resolvedExistingPath = fs.realpathSync(currentPath)
    return path.join(resolvedExistingPath, ...missingSegments)
  } catch {
    // realpathSync başarısız olursa fallback
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

/**
 * Dosya okuma izni workspace içindeki metin dosyaları (TEXT_FILE_EXTENSIONS) için verilir
 * — dosya ağacının listelediği her tür (md, json, shader…) editörde de açılabilir.
 * Symlink çözümü dahildir.
 */
/**
 * Kapının ONAYLADIĞI yolu döndürür — açılacak olan bu olmalı, ham yol değil.
 *
 * ⚠️ Doğrulama turu bulgusu (`path-check-open-race`, probe ile üretildi):
 * kapı `safeResolve` ile çözülmüş yol üzerinde karar veriyor, ama çağıran ham
 * yolu açıyordu. Aradaki pencerede bir ARA BİLEŞEN (`pivot/note.txt`'teki
 * `pivot`) junction'a çevrilirse, açılan tanıtıcı workspace dışındaki dosyayı
 * gösteriyor ve tanıtıcı üzerindeki tüm kontrollerden (düzenli dosya, tek ad,
 * boyut) geçiyordu.
 *
 * Çözülmüş yolu açmak bu pencereyi kapatıyor: ara bileşenler zaten çözülmüş
 * durumda, dolayısıyla sonradan takılan bir junction o mutlak yolu artık
 * etkilemiyor.
 */
export function resolvedReadPath(filePath: string): string {
  return safeResolve(filePath)
}

export function isAllowedWorkspaceReadFile(filePath: string, workspacePath: string): boolean {
  try {
    if (!isAllowedWorkspacePath(filePath, workspacePath)) {
      return false
    }

    const resolved = safeResolve(filePath)

    // ⚠️ NTFS alternatif veri akışı (dış denetim bulgusu, probe ile üretildi).
    // Windows `host.exe:notes.txt` yazımını `host.exe`'nin `notes.txt` akışı
    // olarak okuyor, ama `path.extname` sondaki `.txt`'yi dosyanın uzantısı
    // sanıyor. Sonuç: uzantı beyaz listesi, aslında `.exe` olan bir dosyanın
    // baytlarını yetkilendiriyordu — ve o akış dizin listesinde hiç görünmüyor.
    // Sürücü harfindeki iki nokta (`C:\`) meşru, o yüzden yalnız ondan SONRAKİ
    // kısma bakılıyor.
    const surucusuz = resolved.length > 2 && resolved[1] === ':'
      ? resolved.slice(2)
      : resolved
    if (surucusuz.includes(':')) {
      return false
    }

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
      const st = fs.lstatSync(resolved)
      if (st.isFile() && st.nlink > 1) {
        return false
      }
    } catch {
      /* yol henüz yok ya da okunamıyor — kararı fd üzerindeki kontrol verecek */
    }

    return TEXT_FILE_EXTENSIONS.includes(path.extname(resolved).toLowerCase())
  } catch {
    return false
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
