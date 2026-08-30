#!/usr/bin/env node
/**
 * ffmpeg + yt-dlp'yi `Backend/vendor/bin/<os>/` altına indiren platform
 * script'ini çağırır.
 *
 * NEDEN VAR: indirme script'leri 30 Tem 2026'dan beri yazılıydı
 * (`Backend/vendor/fetch_video_bins.ps1` ve `.sh`), `backend.spec` onların
 * bıraktığı ikilileri pakete koyuyordu ve `.gitignore` yorumu bile onları
 * adıyla anıyordu — ama HİÇBİR ŞEY onları çağırmıyordu. Sonuç: `vendor/bin`
 * yalnız bir README taşıdı, hiçbir ikili paketlenmedi, ve video boru hattı
 * her kurulumda kullanıcının PATH'ine bağlı kaldı.
 *
 * Sahada ölçüldü (Burak, 30 Ağu 2026, Windows): yt-dlp kuruluydu ama `~/bin`
 * Windows PATH'inde değildi; uygulama bulamadı, video sessizce atlandı.
 *
 * ⚠️ `pwsh` VARSAYILMIYOR. README ve `.gitignore` yorumu `pwsh ...` diyor ama
 * bu makinede PowerShell 7 kurulu değil (ölçüldü 30 Ağu 2026: "pwsh is not
 * recognized"). Önce `pwsh`, sonra Windows'un kendi `powershell`'i deneniyor —
 * vaat edilen tek komuta bel bağlamak, script'i yokmuş gibi yapardı.
 *
 * EN İYİ ÇABA, KASITLI: indirme başarısız olursa build KIRILMAZ. Gerekçe
 * script'lerin kendi başlıklarında yazılı ve burada tekrarlanmıyor; tek fark,
 * sessiz kalmamak — neyin eksik kalacağı stderr'e yazılıyor.
 */
const { spawnSync } = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');

const repoRoot = path.resolve(__dirname, '..', '..', '..');
const vendorDir = path.join(repoRoot, 'Backend', 'vendor');

function run(cmd, args) {
  const r = spawnSync(cmd, args, { stdio: 'inherit', cwd: repoRoot });
  return r.error ? null : r.status;
}

// Platform script'lerinde "zaten var, atla" YOK: her çağrıda 126 MB yeniden
// iniyor. Onları değiştirmek yerine idempotanlık BURADA, çünkü tekrar tekrar
// koşulan şey build adımı — script'in kendisi elle çağrılan bir araç.
//
// Damga sabitlenmiş ÖZETLERDEN kuruluyor, sürüm numarasından değil: yayıncı
// aynı etiketi yeniden yayınlarsa sürüm eskiyi güncel gösterirdi.
const PLAT = process.platform === 'win32' ? 'win'
  : process.platform === 'darwin' ? 'mac' : 'linux';
const IKILILER = PLAT === 'win' ? ['ffmpeg.exe', 'yt-dlp.exe'] : ['ffmpeg', 'yt-dlp'];
const KUTUK_ANAHTARI = PLAT === 'mac' ? 'macos' : PLAT;
const BIN_DIR = path.join(vendorDir, 'bin', PLAT);
const DAMGA = path.join(BIN_DIR, '.fetched');

function beklenenDamga() {
  try {
    const kutuk = JSON.parse(
      fs.readFileSync(path.join(repoRoot, 'scripts', 'pinned_assets.json'), 'utf8'));
    return ['ffmpeg', 'yt-dlp']
      .map(ad => kutuk.assets[`${ad}/${KUTUK_ANAHTARI}`]?.digest || '?')
      .join(' ');
  } catch {
    return null;   // kütük okunamıyorsa atlama kararı verilemez → indir
  }
}

function zatenGuncel(damga) {
  if (!damga) return false;
  if (!IKILILER.every(e => fs.existsSync(path.join(BIN_DIR, e)))) return false;
  try {
    return fs.readFileSync(DAMGA, 'utf8').trim() === damga;
  } catch {
    return false;
  }
}

function damgala(damga) {
  try {
    if (damga) fs.writeFileSync(DAMGA, damga + '\n');
  } catch { /* damga yazılamazsa yalnız bir sonraki build tekrar iner */ }
}

function main() {
  const damga = beklenenDamga();
  if (zatenGuncel(damga)) {
    console.log(`[fetch-video-bins] ${PLAT}: ikililer zaten sabitlenmiş sürümde — atlandı.`);
    return 0;
  }
  const kod = indir();
  if (kod === 0 && IKILILER.every(e => fs.existsSync(path.join(BIN_DIR, e)))) damgala(damga);
  return kod;
}

function indir() {
  if (process.platform === 'win32') {
    const script = path.join(vendorDir, 'fetch_video_bins.ps1');
    if (!fs.existsSync(script)) return uyar(`bulunamadı: ${script}`);
    for (const kabuk of ['pwsh', 'powershell']) {
      const kod = run(kabuk, ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', script]);
      if (kod === 0) return 0;
      if (kod !== null) return uyar(`${kabuk} çıkış kodu ${kod}`);
      // kod === null → kabuk yok, sıradakini dene
    }
    return uyar('ne pwsh ne powershell çalıştırılabildi');
  }

  const script = path.join(vendorDir, 'fetch_video_bins.sh');
  if (!fs.existsSync(script)) return uyar(`bulunamadı: ${script}`);
  const kod = run('bash', [script]);
  if (kod === 0) return 0;
  return uyar(kod === null ? 'bash çalıştırılamadı' : `bash çıkış kodu ${kod}`);
}

function uyar(sebep) {
  console.error(
    `[fetch-video-bins] UYARI: ffmpeg/yt-dlp indirilemedi (${sebep}).\n` +
    '  Paket bu ikililer OLMADAN üretilecek; video işleme kullanıcının PATH\'ine\n' +
    '  bağlı kalır ve PATH\'te yoksa sohbet metne düşer.'
  );
  return 0;
}

process.exit(main());
