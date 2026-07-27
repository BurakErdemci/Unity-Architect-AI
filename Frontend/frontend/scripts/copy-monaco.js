#!/usr/bin/env node
/**
 * Monaco'yu node_modules'tan renderer/public/monaco/vs'e kopyalar.
 *
 * NEDEN VAR: `@monaco-editor/react` bir `vs` yolu yapılandırılmadığında
 * `@monaco-editor/loader`'ın gömülü varsayılanına düşüyor ve editörün TÜM kodunu
 * her açılışta cdn.jsdelivr.net'ten çekiyor. İki bedeli vardı: (a) `window.ipc`
 * görebilen bir bağlamda hash pinlemesi olmayan uzak JS çalışıyordu,
 * (b) editör çevrimdışı hiç açılmıyordu. Varlık artık uygulamanın kendi
 * origin'inden servis ediliyor (bkz. renderer/components/home/monaco-loader.ts).
 *
 * NEDEN NODE, PYTHON DEĞİL: repodaki diğer varlık-indirme script'i Python
 * (scripts/fetch_omnisharp.py) ve prebuild'de `python || python3` diye iki kez
 * deneniyor — yani python'un adının bile garanti olmadığı biliniyor. Bu script
 * npm lifecycle hook'undan (predev/prebuild) koşuyor; orada node'un var olduğu
 * tanım gereği garanti, python değil. Windows'ta python yoksa build kırılmasın.
 *
 * NEDEN REPOYA GİRMİYOR: ~15 MB üretilmiş varlık. .gitignore'da
 * `renderer/public/monaco/` var; kaynak zaten package.json'da sabitli
 * (`monaco-editor: ^0.55.1`), yani dosyalar değil sürüm versiyonlanıyor.
 */

const fs = require('fs')
const path = require('path')

const root = path.resolve(__dirname, '..')
const srcDir = path.join(root, 'node_modules', 'monaco-editor', 'min', 'vs')
const destRoot = path.join(root, 'renderer', 'public', 'monaco')
const destDir = path.join(destRoot, 'vs')
const stampFile = path.join(destRoot, '.stamp')

/**
 * Bir ağacın parmak izi: dosya sayısı + toplam bayt.
 * Sadece sürüme bakmak yarım kalmış bir kopyayı "güncel" sayardı (kopyalama
 * ortasında kesilen bir build'in tam olarak yaşattığı arıza); mtime'a bakmak ise
 * temiz checkout'ta her seferinde yeniden kopyalatırdı.
 *
 * Hem KAYNAĞA hem HEDEFE uygulanıyor. İlk hâli yalnız kaynağa bakıyordu ve
 * denetimde ölçüldü (2026-07-27): damga kaynakla eşleştiği sürece hedef bozuk
 * olsa bile "güncel, atlandı" deniyordu. Somut arıza — `loader.js` silinip
 * script yeniden koşturulunca çıkış 0 veriyor, sonraki Next export'u başarıyor,
 * ve editör ÇALIŞMA ANINDA ölüyor. CDN izinleri kaldırıldığı için eskiden
 * kurtarabilecek olan uzak varsayılan da artık CSP tarafından reddediliyor.
 */
const fingerprint = (dir) => {
  let files = 0
  let bytes = 0
  const walk = (current) => {
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      const full = path.join(current, entry.name)
      if (entry.isDirectory()) {
        walk(full)
      } else if (entry.isFile()) {
        files += 1
        bytes += fs.statSync(full).size
      }
    }
  }
  walk(dir)
  return { files, bytes }
}

const main = () => {
  if (!fs.existsSync(path.join(srcDir, 'loader.js'))) {
    // SESSİZCE GEÇME. Eski hata tam olarak buydu: yapılandırma eksik olunca
    // kimse fark etmeden CDN'e düşülüyordu. Kaynak yoksa build durmalı.
    console.error(
      `[copy-monaco] HATA: kaynak bulunamadı → ${srcDir}\n` +
        `  monaco-editor paketi kurulu değil. Çözüm: npm install`
    )
    process.exit(1)
  }

  const version = JSON.parse(
    fs.readFileSync(path.join(root, 'node_modules', 'monaco-editor', 'package.json'), 'utf-8')
  ).version

  const src = fingerprint(srcDir)
  const stamp = `monaco-editor@${version} files=${src.files} bytes=${src.bytes}\n`

  // Damga kaynağı anlatıyor; hedefin gerçekten o hâlde olduğunu AYRICA ölç.
  // Bu iki kontrolden ikincisi olmadan bozuk bir hedef "güncel" sayılıyordu.
  const destIsIntact = () => {
    if (!fs.existsSync(stampFile)) return false
    if (fs.readFileSync(stampFile, 'utf-8') !== stamp) return false
    if (!fs.existsSync(path.join(destDir, 'loader.js'))) return false
    const dest = fingerprint(destDir)
    return dest.files === src.files && dest.bytes === src.bytes
  }

  if (destIsIntact()) {
    console.log(`[copy-monaco] güncel, atlandı (monaco-editor@${version}, ${src.files} dosya)`)
    return
  }

  // ── Kilit: aynı checkout'ta iki lifecycle komutu çakışabiliyor ────────────
  // `mkdir` dosya sisteminde atomik: ya oluşturur ya EEXIST verir. Bu yüzden
  // kilit olarak dizin kullanılıyor, dosya değil. Ölçüldü (2026-07-27): kilitsiz
  // hâlde 8 eşzamanlı kopya birbirinin dizinini silerken biri yine de damgayı
  // yazıyor ve geriye 121 dosyadan 88'i kalıyor; sonraki koşu damgaya bakıp
  // "güncel" diyor ve EKSİK ağacı paketliyor.
  const lockDir = path.join(destRoot, '.lock')
  fs.mkdirSync(destRoot, { recursive: true })
  const deadline = Date.now() + 120_000
  for (;;) {
    try {
      fs.mkdirSync(lockDir)
      break
    } catch (err) {
      if (err.code !== 'EEXIST') throw err
      // Ölmüş bir sürecin bıraktığı kilit build'i sonsuza kadar durdurmasın.
      let age = 0
      try {
        age = Date.now() - fs.statSync(lockDir).mtimeMs
      } catch {
        continue // kilit bu arada kalktı, yeniden dene
      }
      if (age > 300_000) {
        console.warn(`[copy-monaco] bayat kilit kaldırılıyor (${Math.round(age / 1000)}s)`)
        fs.rmSync(lockDir, { recursive: true, force: true })
        continue
      }
      if (Date.now() > deadline) {
        console.error(
          `[copy-monaco] HATA: kilit 120sn boyunca serbest kalmadı → ${lockDir}\n` +
            `  Başka bir kopyalama sürüyor olabilir. Sürmediğine eminsen bu dizini sil.`
        )
        process.exit(1)
      }
      Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 200) // eşzamanlı bekleme
    }
  }

  try {
    // Kilidi beklerken başka bir süreç işi bitirmiş olabilir.
    if (destIsIntact()) {
      console.log(`[copy-monaco] başka süreç tamamlamış, atlandı (monaco-editor@${version})`)
      return
    }

    // YERİNDE DEĞİL, YANA kopyala sonra taşı: `cpSync` hedefe dosya dosya yazıyor,
    // yani yarıda kesilen bir kopya geriye yarım bir `vs/` bırakıyordu. Staging
    // dizini aynı dosya sisteminde olduğu için `renameSync` atomik.
    const staging = path.join(destRoot, `.staging-${process.pid}`)
    fs.rmSync(staging, { recursive: true, force: true })
    fs.cpSync(srcDir, staging, { recursive: true })

    // Damga önce siliniyor: taşıma ile damga yazımı arasında süreç ölürse geriye
    // damgasız (yani "güncel değil" diye okunacak) bir hedef kalsın — damgalı
    // ama eksik bir hedef, tam tersine, sessizce paketlenirdi.
    fs.rmSync(stampFile, { force: true })
    fs.rmSync(destDir, { recursive: true, force: true })
    fs.renameSync(staging, destDir)
    fs.writeFileSync(stampFile, stamp)
  } finally {
    fs.rmSync(lockDir, { recursive: true, force: true })
  }

  console.log(
    `[copy-monaco] kopyalandı: monaco-editor@${version} → renderer/public/monaco/vs ` +
      `(${src.files} dosya, ${(src.bytes / 1024 / 1024).toFixed(1)} MB)`
  )
}

main()
