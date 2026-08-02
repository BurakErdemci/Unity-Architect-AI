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

/** Okuma kapısının kararı ve o kararın DAYANDIĞI çözülmüş yol. */
export type OkumaKarari = { izinli: boolean; cozulmusYol: string }

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
export function okumaKarariVer(filePath: string, workspacePath: string): OkumaKarari {
  const reddet = (yol: string): OkumaKarari => ({ izinli: false, cozulmusYol: yol })
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

    return {
      izinli: TEXT_FILE_EXTENSIONS.includes(path.extname(cozulmus).toLowerCase()),
      cozulmusYol: cozulmus,
    }
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
