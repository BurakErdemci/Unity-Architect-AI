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

# ── Kütük CLI'ının çıkış kodu SINIFLARI ───────────────────────────────
# Sözleşme scripts/pinned_assets.py docstring'inde yazılı ve tek kaynağı orası:
#   0 = tamam
#   1 = BÜTÜNLÜK arızası - indirilen baytlar pinle uyuşmuyor. ASLA tekrar denenmez.
#   2 = kullanım / ORTAM hatası - yanlış argüman, desteklenmeyen Python sürümü.
#   3 = İŞLETİM arızası - anahtar kütükte yok, dosya okunamadı, kütük bozuk.
#
# Sınıfları ayırmak ZORUNLU. "sıfır değil -> anahtar kütükte yok" indirgemesi
# denetimde ölçüldü (2026-07-28): Python sürüm kapısına takılan koşu (kod 2)
# operatöre "bu anahtar kütükte yok" diyor, yani var olmayan bir kütük sorunu
# aratıp gerçek sebebi (yorumlayıcı sürümü) gizliyordu.
#
# Bu betikte HİÇBİR sınıf build'i kırmıyor: sözleşme en iyi çaba (dosya başındaki
# uzun nota bak). Ama sınıf başına mesaj ayrı, çünkü operatörün yapacağı iş değişiyor.
#
# $script:PinnedFailLabel: sondaki "EKSİK KALAN BİNARY'LER" özetinde kullanılıyor.
# Sebebin özette de görünmesi bilinçli - denetimde ölçülen arıza sınıfı tam olarak
# "özet ile ayrıntı ayrışıyor"du.
$script:PinnedFailLabel = ''

function Write-PinnedFailure {
    # Sınıfı raporlar; ASLA throw etmez (en iyi çaba sözleşmesi).
    # Python'un kendi çıktısı ($Detail) YUTULMUYOR: asıl teşhis orada.
    param([int]$Code, [string]$Key, [string]$Stage, [string]$Detail)
    switch ($Code) {
        1 {
            $script:PinnedFailLabel = 'bütünlük uyuşmazlığı'
            Write-Warning ("$Key DOĞRULANAMADI ($Stage) - indirme başarılı ama baytlar " +
                "sabitlenmiş özetle uyuşmuyor. KURULMUYOR ve tekrar DENENMİYOR: 'birkaç " +
                "kez dene' bir saldırgana yalnızca birkaç şans daha verir.")
        }
        2 {
            $script:PinnedFailLabel = 'ortam hatası'
            Write-Warning ("$Key ORTAM HATASI ($Stage) - Python sürümü ya da çağrı biçimi " +
                "uygun değil. Bu bir BÜTÜNLÜK arızası DEĞİL: hiçbir asset doğrulanmadı, " +
                "hiçbir özet uyuşmazlığı bulunmadı. En az Python 3.10 gerekiyor.")
        }
        3 {
            $script:PinnedFailLabel = 'işletim hatası'
            Write-Warning ("$Key İŞLETİM HATASI ($Stage) - anahtar kütükte yok, dosya " +
                "okunamadı ya da kütük ayrıştırılamadı. Düzeltilebilir bir durum; bütünlük " +
                "arızasıyla ilgisi YOK. ('yazım hatası' ile 'kütüğe henüz eklenmedi' " +
                "dışarıdan aynı görünür, ikisi de görünür olmalı.)")
        }
        default {
            $script:PinnedFailLabel = "beklenmedik çıkış kodu $Code"
            Write-Warning ("$Key - BEKLENMEDİK ÇIKIŞ KODU $Code ($Stage). Sözleşme yalnız " +
                "0/1/2/3 tanımlıyor; bilinmeyen bir kod sözleşmenin değiştiğine işaret " +
                "eder. Bilinen bir sınıfa SOKULMUYOR: yanlış sınıflandırma, " +
                "sınıflandırmamaktan pahalıya geliyor.")
        }
    }
    if (-not [string]::IsNullOrWhiteSpace($Detail)) { Write-Host $Detail }
}

function Get-PinnedUrl {
    param([string]$Key)
    $r = Invoke-PinnedCli @('url', $Key)
    if ($r.Code -ne 0) {
        Write-PinnedFailure -Code $r.Code -Key $Key -Stage 'adres okuma' -Detail $r.Output
        Write-Warning "$Key ATLANIYOR."
        return $null
    }
    return $r.Output
}

function Get-PinnedBinary {
    # 0 değil, $true/$false döner: $true → dosya indi VE doğrulandı.
    param([string]$Key, [string]$OutFile)
    $script:PinnedFailLabel = ''
    $url = Get-PinnedUrl $Key
    if (-not $url) { return $false }
    Write-Host "$Key indiriliyor: $url"
    try {
        Invoke-WebRequest -Uri $url -OutFile $OutFile
    } catch {
        Write-Warning "$Key İNDİRİLEMEDİ (ağ/HTTP hatası) - atlanıyor: $($_.Exception.Message)"
        $script:PinnedFailLabel = 'ağ/HTTP'
        Remove-Item $OutFile -Force -ErrorAction SilentlyContinue
        return $false
    }
    # Bu aşamanın sınıfları ağ hatasından bilerek AYRI: "indiremedim" ile "indirdim ama
    # beklenen baytlar değil" bambaşka iki teşhis. Üstelik burada 1 (uyuşmazlık) ile
    # 3 (dosya okunamadı) da ayrılıyor: ikisi de "doğrulanamadı" diye raporlanırken
    # okunamayan bir dosya, doktrini gereği asla tekrar denenmemesi gereken bir arıza
    # gibi görünüyordu.
    $v = Invoke-PinnedCli @('verify', $Key, $OutFile)
    if ($v.Code -ne 0) {
        Write-PinnedFailure -Code $v.Code -Key $Key -Stage 'bütünlük doğrulaması' -Detail $v.Output
        Remove-Item $OutFile -Force -ErrorAction SilentlyContinue
        return $false
    }
    return $true
}

$missing = @()

function Add-Missing {
    # Raporu yazar VE hedefteki eski kopyayı siler. İkisi bilerek TEK fonksiyonda:
    # ayrı bırakıldıklarında ayrışıyorlar, ve denetimde ölçülen arıza tam olarak buydu
    # (verification-failure-preserves-final-artifact) - özet "EKSİK KALAN BİNARY'LER"
    # derken hemen üstündeki dosya listesi exe'yi gösteriyordu.
    #
    # Neden silmek şart: backend.spec bu dizini tarayıp ne bulursa pakete gömüyor. N.
    # koşuda iyi bir ffmpeg kurulduysa, N+1. koşuda bozuk/kurcalanmış bir indirme
    # doğrulamayı geçemediğinde ESKİ dosya yerinde kalıyor ve yine paketleniyordu.
    #
    # Şiddeti neden daha yüksek değil: GitHub-hosted CI temiz checkout'ta koşuyor,
    # dizin her seferinde boş başlıyor. Risk YEREL geliştirici build'lerine ve
    # self-hosted runner'lara özgü - kalıcı diskli bir build makinesinde arıza aynen
    # geri gelir, o yüzden "CI'da olmuyor" diye bu blok silinmesin.
    #
    # Silmek build'i KIRMAK değildir: sözleşme hâlâ "en iyi çaba", betik yine 0
    # dönüyor, yalnızca pakete doğrulanmamış bayt sızmıyor.
    param([string]$Label, [string]$Target)
    $script:missing += $Label
    if (Test-Path $Target) {
        Remove-Item $Target -Force -ErrorAction SilentlyContinue
        if (Test-Path $Target) {
            # Silinemezse rapor yine yalan söyler; o zaman en azından yüksek sesle söylensin.
            Write-Warning "eski kopya SİLİNEMEDİ: $Target - doğrulanmamış haliyle pakete girebilir"
        }
    }
}

# Doğrulayamıyorsak hiç indirmiyoruz (fail-closed): doğrulamasız indirme, bu betiğin
# kapatmak için var olduğu riskin ta kendisi.
#
# Ama bu iki dalda dizindeki mevcut dosyalara DOKUNULMUYOR, ve bu bilinçli bir ayrım:
# doğrulama başarısızlığı bir KANIT'tır (elimizdeki baytlar pinle uyuşmuyor), python'un
# yokluğu ise kanıtın YOKLUĞU. Dizindeki dosya bu betiğin daha önceki bir koşusundan
# geliyor, yani o gün doğrulamayı geçmişti; onu bugün silmek geçici bir ortam eksiğini
# iyi bir artefaktın imhasına çevirir ve python'u olmayan her makinede ffmpeg'siz paket
# üretir - güvenlik kazancı olmadan build regresyonu. Karşılığında dürüstlük borcu var:
# burada "bugün doğrulanmadı" açıkça yazılıyor, yoksa okuyan kişi dizindekini bu
# koşunun ürünü sanar.
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Warning 'python yok - bütünlük doğrulaması yapılamaz, HİÇBİR binary kurulmuyor'
    Write-Warning "($dir'de eskiden kalan dosya varsa DURUYOR ve bu koşuda doğrulanmadı)"
    exit 0
}
if (-not (Test-Path $script:PinnedCli)) {
    Write-Warning "doğrulama aracı bulunamadı ($($script:PinnedCli)) - HİÇBİR binary kurulmuyor"
    Write-Warning "($dir'de eskiden kalan dosya varsa DURUYOR ve bu koşuda doğrulanmadı)"
    exit 0
}

# ORTAM kapısı (çıkış kodu 2), indirmelerden ÖNCE ve TEK yerde.
# Neden burada: kod 2 ("yorumlayıcı bu modülü koşturamıyor") anahtardan bağımsız,
# yani her anahtarda birebir tekrar eder - aynı uyarıyı iki kez basmak operatörü iki
# ayrı arıza var sanmaya iter.
# Neden `exit 0` ve neden hedef dizine DOKUNULMUYOR: bu, yukarıdaki "python yok" ve
# "kütük yok" dallarıyla AYNI sınıf - kanıtın YOKLUĞU. Doğrulama başarısızlığı bir
# KANIT'tır (baytlar pinle uyuşmuyor) ve orada eski kopya siliniyor; burada silmek,
# geçici bir ortam eksiğini iyi bir artefaktın imhasına çevirirdi.
# `keys` seçildi çünkü ağa çıkmıyor ve sürüm kapısı zaten modül IMPORT anında işliyor.
$pre = Invoke-PinnedCli @('keys')
if ($pre.Code -eq 2) {
    Write-Warning 'ORTAM HATASI - python bu kütük aracını koşturamıyor (çıkış kodu 2).'
    Write-Warning 'Bu bir bütünlük arızası DEĞİL; hiçbir asset doğrulanmadı.'
    Write-Warning "HİÇBİR binary kurulmuyor, hedef dizine DOKUNULMUYOR."
    Write-Warning "($dir'de eskiden kalan dosya varsa DURUYOR ve bu koşuda doğrulanmadı)"
    Write-Host $pre.Output
    exit 0
}
# 1/3 ya da beklenmedik kodlar burada tüketilmiyor: onlar anahtara özgü olabilir ve
# asıl teşhis aşağıda, ilgili binary'nin yanında basılıyor.

# Her indirme geçici dizine iner, ancak doğrulandıktan sonra bin\win'e kopyalanır:
# yarım/yanlış bir dosya hedef dizinde bir an bile durmasın (backend.spec orayı tarıyor).
$tmpDir = Join-Path ([System.IO.Path]::GetTempPath()) ("video_bins_" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $tmpDir | Out-Null
try {
    # ── yt-dlp.exe (tek dosya) ────────────────────────────────────────
    # Copy-Item da denetleniyor: yarım kalan bir kopyalama (disk dolu, dosya kilitli)
    # hedefte bozuk bir exe bırakır ve backend.spec onu yine gömerdi - "rapor ile
    # dizin uyuşmuyor" arızasının aynısı, yalnız başka sebepten.
    $ytOut = Join-Path $dir 'yt-dlp.exe'
    $ytTmp = Join-Path $tmpDir 'yt-dlp.exe'
    if (Get-PinnedBinary -Key 'yt-dlp/win' -OutFile $ytTmp) {
        try {
            Copy-Item $ytTmp $ytOut -Force
        } catch {
            Write-Warning "yt-dlp.exe hedefe kopyalanamadı - atlanıyor: $($_.Exception.Message)"
            Add-Missing 'yt-dlp.exe (kopyalama)' $ytOut
        }
    } else {
        # Etikete sınıf giriyor: özet satırı ile yukarıdaki ayrıntı aynı sebebi göstersin.
        Add-Missing "yt-dlp.exe ($script:PinnedFailLabel)" $ytOut
    }

    # ── ffmpeg (LGPL, win64; zip içinde) ──────────────────────────────
    $ffOut = Join-Path $dir 'ffmpeg.exe'
    $ffZip = Join-Path $tmpDir 'ffmpeg.zip'
    if (Get-PinnedBinary -Key 'ffmpeg/win' -OutFile $ffZip) {
        $ext = Join-Path $tmpDir 'ffmpeg_ext'
        try {
            Expand-Archive -Path $ffZip -DestinationPath $ext -Force
            $exe = Get-ChildItem $ext -Recurse -Filter ffmpeg.exe | Select-Object -First 1
            if ($exe) {
                Copy-Item $exe.FullName $ffOut -Force
            } else {
                Write-Warning 'ffmpeg arşivinde ffmpeg.exe bulunamadı - atlanıyor'
                Add-Missing 'ffmpeg.exe (arşiv içeriği)' $ffOut
            }
        } catch {
            Write-Warning "ffmpeg arşivi açılamadı/kopyalanamadı - atlanıyor: $($_.Exception.Message)"
            Add-Missing 'ffmpeg.exe (arşiv açma)' $ffOut
        }
    } else {
        Add-Missing "ffmpeg.exe ($script:PinnedFailLabel)" $ffOut
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
    Write-Host "    Sebep parantez içinde ve yukarıdaki UYARI satırlarında. Sınıflar AYRI şeydir:"
    Write-Host "      ağ/HTTP              -> adres yanıt vermedi; tekrar denenebilir."
    Write-Host "      bütünlük uyuşmazlığı -> baytlar pinle uyuşmuyor; ASLA tekrar denenmez."
    Write-Host "      ortam hatası         -> Python sürümü/çağrı biçimi; hiçbir bayt doğrulanmadı."
    Write-Host "      işletim hatası       -> anahtar/dosya/kütük sorunu; düzeltilebilir."
    Write-Host "    Bu dosyalar hedef dizinden de KALDIRILDI: önceki bir koşudan kalan kopya"
    Write-Host "    doğrulanmadan paketlenmesin diye. Yukarıdaki liste ile bu liste uyuşur."
}

# Eksik olsa bile 0 dönülüyor: bu adımın sözleşmesi "elde edebildiğini topla, kalanı
# gürültülü biçimde bildir". Kırılma kararı build'in kendisine ait, buraya değil.
exit 0
