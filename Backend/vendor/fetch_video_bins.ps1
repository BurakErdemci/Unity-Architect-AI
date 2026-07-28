# Video araç zinciri — ffmpeg (LGPL) + yt-dlp indirir → Backend/vendor/bin/win/
# Frozen build (backend.spec) bunları otomatik gömer. İkililer repoda tutulmaz (~126MB);
# bu script ile çekilir (vendor/uv ile aynı mantık).
#
# SÜRÜM SABİT: adres ve beklenen özet scripts/pinned_assets.json'da ('yt-dlp/win',
# 'ffmpeg/win'); buradaki hiçbir adres 'latest'/rolling değil. Doğrulama İNDİRİLEN
# dosya üzerinde, arşiv AÇILMADAN ÖNCE yapılır — çıkarılmış exe'nin özeti kütükteki
# değerle karşılaştırılamaz, ve zararlı bir arşiv zaten çıkarma anında iş yapmış olur.
# Anahtar kütükte yoksa o binary sessizce değil, UYARI ile atlanır.
#
# EN İYİ ÇABA, KASITLI: bir binary alınamazsa build kırılmaz, o binary'siz devam edilir
# (CI'da bu adım continue-on-error ile koşuyor). Doğrulama başarısızlığı da AYNI yola
# düşer: dosya KURULMAZ ama build kırılmaz. Gerekçe: doğrulanmamış bir ffmpeg'i pakete
# koymak, ffmpeg'siz paket göndermekten kötüdür — biri bir özelliği kaybettirir, diğeri
# her kullanıcıda kimliği bilinmeyen kod çalıştırır. Buna karşılık fetch_uv.ps1'de aynı
# hata build'i KIRMALI: uv olmadan Unity MCP hiç çalışmaz. Fark bilinçli; biri
# "tutarlılık" adına birini diğerine benzetmeye kalkmasın diye buraya yazılı.
#
# Kullanım: pwsh Backend/vendor/fetch_video_bins.ps1
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$dir = Join-Path $PSScriptRoot 'bin\win'
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$script:PinnedCli = Join-Path $PSScriptRoot '..\..\scripts\pinned_assets.py'

function Invoke-PinnedCli {
    # Kütük CLI'ını çağırır; çıkış kodunu ve çıktısını döndürür.
    # $ErrorActionPreference burada FONKSİYON KAPSAMINDA 'Continue'ye çekiliyor:
    # dosyanın başındaki 'Stop', python sıfırdan farklı dönünce (PS 7.4+ varsayılanı
    # $PSNativeCommandUseErrorActionPreference = $true) betiği TÜMDEN öldürürdü.
    # İstenen davranış ise "o binary atlanır, diğerine devam" — o yüzden çıkış kodu
    # istisna olarak değil, elle okunuyor.
    param([string[]]$CliArgs)
    $ErrorActionPreference = 'Continue'
    $PSNativeCommandUseErrorActionPreference = $false
    $out = & python $script:PinnedCli @CliArgs 2>&1
    return [pscustomobject]@{
        Code   = $LASTEXITCODE
        Output = ($out | Out-String).Trim()
    }
}

function Get-PinnedUrl {
    param([string]$Key)
    $r = Invoke-PinnedCli @('url', $Key)
    if ($r.Code -ne 0) {
        # "yazım hatası" ile "kütüğe henüz eklenmedi" dışarıdan aynı görünür; ikisi de görünsün.
        Write-Warning "'$Key' kütükten okunamadı (scripts/pinned_assets.json) - atlanıyor. $($r.Output)"
        return $null
    }
    return $r.Output
}

function Get-PinnedBinary {
    # 0 değil, $true/$false döner: $true → dosya indi VE doğrulandı.
    param([string]$Key, [string]$OutFile)
    $url = Get-PinnedUrl $Key
    if (-not $url) { return $false }
    Write-Host "$Key indiriliyor: $url"
    try {
        Invoke-WebRequest -Uri $url -OutFile $OutFile
    } catch {
        Write-Warning "$Key İNDİRİLEMEDİ (ağ/HTTP hatası) - atlanıyor: $($_.Exception.Message)"
        Remove-Item $OutFile -Force -ErrorAction SilentlyContinue
        return $false
    }
    $v = Invoke-PinnedCli @('verify', $Key, $OutFile)
    if ($v.Code -ne 0) {
        # Bu mesaj ağ hatasından bilerek AYRI: "indiremedim" ile "indirdim ama beklenen
        # baytlar değil" bambaşka iki teşhis. Uyuşmazlıkta tekrar DENENMİYOR — tekrar
        # denemek bir saldırgana yalnızca birkaç şans daha verir.
        Write-Warning "$Key DOĞRULANAMADI - indirme başarılı ama baytlar sabitlenmiş özetle uyuşmuyor. KURULMUYOR."
        Write-Host $v.Output
        Remove-Item $OutFile -Force -ErrorAction SilentlyContinue
        return $false
    }
    return $true
}

$missing = @()

# Doğrulayamıyorsak hiç indirmiyoruz (fail-closed): doğrulamasız indirme, bu betiğin
# kapatmak için var olduğu riskin ta kendisi.
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Warning 'python yok - bütünlük doğrulaması yapılamaz, HİÇBİR binary kurulmuyor'
    exit 0
}
if (-not (Test-Path $script:PinnedCli)) {
    Write-Warning "doğrulama aracı bulunamadı ($($script:PinnedCli)) - HİÇBİR binary kurulmuyor"
    exit 0
}

# Her indirme geçici dizine iner, ancak doğrulandıktan sonra bin\win'e kopyalanır:
# yarım/yanlış bir dosya hedef dizinde bir an bile durmasın (backend.spec orayı tarıyor).
$tmpDir = Join-Path ([System.IO.Path]::GetTempPath()) ("video_bins_" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $tmpDir | Out-Null
try {
    # ── yt-dlp.exe (tek dosya) ────────────────────────────────────────
    $ytTmp = Join-Path $tmpDir 'yt-dlp.exe'
    if (Get-PinnedBinary -Key 'yt-dlp/win' -OutFile $ytTmp) {
        Copy-Item $ytTmp (Join-Path $dir 'yt-dlp.exe') -Force
    } else {
        $missing += 'yt-dlp.exe'
    }

    # ── ffmpeg (LGPL, win64; zip içinde) ──────────────────────────────
    $ffZip = Join-Path $tmpDir 'ffmpeg.zip'
    if (Get-PinnedBinary -Key 'ffmpeg/win' -OutFile $ffZip) {
        $ext = Join-Path $tmpDir 'ffmpeg_ext'
        try {
            Expand-Archive -Path $ffZip -DestinationPath $ext -Force
            $exe = Get-ChildItem $ext -Recurse -Filter ffmpeg.exe | Select-Object -First 1
            if ($exe) {
                Copy-Item $exe.FullName (Join-Path $dir 'ffmpeg.exe') -Force
            } else {
                Write-Warning 'ffmpeg arşivinde ffmpeg.exe bulunamadı - atlanıyor'
                $missing += 'ffmpeg.exe (arşiv içeriği)'
            }
        } catch {
            Write-Warning "ffmpeg arşivi açılamadı - atlanıyor: $($_.Exception.Message)"
            $missing += 'ffmpeg.exe (arşiv açma)'
        }
    } else {
        $missing += 'ffmpeg.exe (indirme/doğrulama)'
    }
} finally {
    # Temizlik zorunlu ve finally'de: betik nasıl biterse bitsin geçici dizin kalmasın.
    Remove-Item $tmpDir -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host 'Tamam:'
Get-ChildItem $dir -Filter *.exe |
    Select-Object Name, @{ N = 'MB'; E = { [math]::Round($_.Length / 1MB, 1) } }

if ($missing.Count -gt 0) {
    Write-Host ''
    Write-Host "!!! EKSİK KALAN BİNARY'LER - paket bunlarsız üretilecek:"
    $missing | ForEach-Object { Write-Host "  - $_" }
    Write-Host "    Sebep yukarıdaki UYARI satırlarında; 'indirilemedi' ile 'doğrulanamadı' AYRI şeydir."
}

# Eksik olsa bile 0 dönülüyor: bu adımın sözleşmesi "elde edebildiğini topla, kalanı
# gürültülü biçimde bildir". Kırılma kararı build'in kendisine ait, buraya değil.
exit 0
