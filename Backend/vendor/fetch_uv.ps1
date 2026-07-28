# Unity MCP için gerekli uv araç zincirini (uv.exe + uvx.exe) indirir.
# Bu ikililer installer'a gömülür (electron-builder.yml → extraResources: uv),
# böylece kullanıcının PC'sinde uv kurulu olmasa da Unity MCP çalışır.
# Boyutları büyük olduğu için git'e konmaz (.gitignore); build öncesi bunu çalıştır.
#
# Sürüm SABİT, `latest` değil: adres ve beklenen sha256 scripts/pinned_assets.json
# içinde (anahtar uv/win-x64). `latest` kullanmak, her build'in o anda yayında olan
# farklı bir ikiliyi installer'a gömmesi demekti — ne tekrar üretilebilir bir çıktı
# ne de doğrulanacak bir beklenti kalıyordu.
# Sürüm yükseltmek için: `python scripts/pinned_assets.py refresh`, sonra diff'i incele.
#
# Kullanım:  pwsh Backend/vendor/fetch_uv.ps1
$ErrorActionPreference = "Stop"
$dest = Join-Path $PSScriptRoot "uv"
New-Item -ItemType Directory -Force $dest | Out-Null

# Betik Backend/vendor/ altında; repo kökü iki üstü.
$pinned = Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) "scripts/pinned_assets.py"
$key = "uv/win-x64"

# ── Kütük CLI'ının çıkış kodu SINIFLARI ───────────────────────────────
# Sözleşme scripts/pinned_assets.py docstring'inde yazılı ve tek kaynağı orası:
#   0 = tamam
#   1 = BÜTÜNLÜK arızası - indirilen baytlar pinle uyuşmuyor. ASLA tekrar denenmez.
#   2 = kullanım / ORTAM hatası - yanlış argüman, desteklenmeyen Python sürümü.
#   3 = İŞLETİM arızası - anahtar kütükte yok, dosya okunamadı, kütük bozuk.
#
# Sınıfları ayırmak ZORUNLU. "sıfır değil -> uyuşmazlık" indirgemesi denetimde iki
# yanlış teşhis üretti (2026-07-28): okunamayan bir dosya (3) operatöre "baytlar
# pinle uyuşmuyor" diye raporlanıyordu - projenin doktrini "uyuşmazlık asla tekrar
# denenmez" olduğu için en pahalı yanlış yönlendirme buydu.
#
# Bu betikte HER sınıf build'i KIRIYOR (hepsi `throw`): uv olmadan Unity MCP hiç
# çalışmıyor. Sonuç aynı olsa da MESAJ ayrı, çünkü operatörün yapacağı iş sınıfa
# göre değişiyor: pin'i incele / Python'u değiştir / kütüğü onar.

function Invoke-PinnedCli {
    # Kütük CLI'ını çağırır; çıkış kodunu ve çıktısını döndürür.
    # Windows'ta yorumlayıcının adı `python` (bash tarafında `python3`); CI'da
    # actions/setup-python bu adımdan önce koştuğu için ikisi de mevcut.
    #
    # $LASTEXITCODE yalnız native komuttan SONRA anlamlı, o yüzden hemen bir sonraki
    # satırda okunuyor; araya başka bir komut girerse başkasının kodu ölçülür.
    #
    # $ErrorActionPreference burada FONKSİYON KAPSAMINDA 'Continue'ye çekiliyor:
    # dosyanın başındaki 'Stop', python sıfırdan farklı dönünce (PS 7.4+ varsayılanı
    # $PSNativeCommandUseErrorActionPreference = $true) betiği GENEL bir istisnayla
    # öldürürdü ve sınıf bilgisi tam orada kaybolurdu. Build yine kırılacak - ama
    # aşağıda, doğru mesajla.
    param([string[]]$CliArgs)
    $ErrorActionPreference = 'Continue'
    $PSNativeCommandUseErrorActionPreference = $false
    $out = & python $script:pinned @CliArgs 2>&1
    return [pscustomobject]@{
        Code   = $LASTEXITCODE
        Output = ($out | Out-String).Trim()
    }
}

function Write-PinnedFailure {
    # Sınıfı raporlar ve build'i kırar. Python'un kendi çıktısı ($Detail) ÖNCE
    # basılıyor ve YUTULMUYOR: asıl teşhis orada, buradaki satırlar yalnız sınıfı
    # ve "ne yapmalı"yı söylüyor.
    param([int]$Code, [string]$Key, [string]$Stage, [string]$Detail)
    if (-not [string]::IsNullOrWhiteSpace($Detail)) { Write-Host $Detail }
    switch ($Code) {
        1 {
            throw ("doğrulama başarısız ($Key - $Stage): indirilen baytlar sabitlenmiş " +
                   "özetle uyuşmuyor. Tekrar DENENMEZ - 'birkaç kez dene' bir saldırgana " +
                   "yalnızca birkaç şans daha verir. Build durduruldu.")
        }
        2 {
            throw ("ortam hatası ($Key - $Stage): Python sürümü ya da çağrı biçimi uygun " +
                   "değil. Bu bir BÜTÜNLÜK arızası DEĞİL: hiçbir asset doğrulanmadı, " +
                   "hiçbir özet uyuşmazlığı bulunmadı. Çözüm yukarıdaki Python mesajında " +
                   "(en az Python 3.10 gerekiyor). Build durduruldu.")
        }
        3 {
            throw ("işletim hatası ($Key - $Stage): anahtar kütükte yok, dosya okunamadı " +
                   "ya da kütük ayrıştırılamadı ($script:pinned). Düzeltilebilir bir durum " +
                   "ve bütünlük arızasıyla ilgisi YOK. Build durduruldu.")
        }
        default {
            throw ("beklenmedik çıkış kodu $Code ($Key - $Stage). $script:pinned sözleşmesi " +
                   "yalnız 0/1/2/3 tanımlıyor; bilinmeyen bir kod o sözleşmenin değiştiğine " +
                   "işaret eder. Bilinen bir sınıfa SOKULMUYOR: yanlış sınıflandırma, " +
                   "sınıflandırmamaktan pahalıya geliyor. Build durduruldu.")
        }
    }
}

$r = Invoke-PinnedCli @('url', $key)
if ($r.Code -ne 0) {
    Write-PinnedFailure -Code $r.Code -Key $key -Stage 'adres okuma' -Detail $r.Output
}
$url = $r.Output
if ([string]::IsNullOrWhiteSpace($url)) {
    # Kod 0 ama çıktı boş: sözleşmeye göre olamaz, yani sessizce geçilemez.
    # Boş bir adresle devam etmek Invoke-WebRequest'i anlamsız bir hatayla patlatırdı.
    throw "'$key' için kütük 0 döndürdü ama BOŞ adres verdi ($script:pinned) - build durduruldu."
}

$zip = Join-Path $env:TEMP "uv-win-x64.zip"
Write-Output "uv indiriliyor: $url"
Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing

# Bütünlük kapısı ÇIKARMADAN ÖNCE ve İNDİRİLEN ARŞİV üzerinde: çıkarılmış dosyaya
# bakmak, bozuk arşivi zaten açtıktan sonra kontrol etmek olurdu.
# Uyuşmazlıkta build KIRILIR, atlanmaz: uv olmadan Unity MCP hiç çalışmıyor, yani
# "uyarı verip devam et" son kullanıcıya sessizce bozuk bir installer göndermektir.
$v = Invoke-PinnedCli @('verify', $key, $zip)
if ($v.Code -ne 0) {
    Remove-Item $zip -Force -ErrorAction SilentlyContinue
    Write-PinnedFailure -Code $v.Code -Key $key -Stage 'bütünlük doğrulaması' -Detail $v.Output
}

Expand-Archive -Path $zip -DestinationPath $dest -Force
Remove-Item $zip -Force
Remove-Item (Join-Path $dest "uvw.exe") -Force -ErrorAction SilentlyContinue
Write-Output "Tamam → $dest"
Get-ChildItem $dest | Select-Object Name, Length
