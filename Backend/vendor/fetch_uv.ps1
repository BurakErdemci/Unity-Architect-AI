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

# Windows'ta yorumlayıcının adı `python` (bash tarafında `python3`); CI'da
# actions/setup-python bu adımdan önce koştuğu için ikisi de mevcut.
# Native komutun çıkış kodu ErrorActionPreference'a takılmayabilir, o yüzden
# $LASTEXITCODE ELLE kontrol ediliyor.
$url = & python $pinned url $key
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($url)) {
    throw "'$key' sabitlenmiş kütükten okunamadı ($pinned)."
}

$zip = Join-Path $env:TEMP "uv-win-x64.zip"
Write-Output "uv indiriliyor: $url"
Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing

# Bütünlük kapısı ÇIKARMADAN ÖNCE ve İNDİRİLEN ARŞİV üzerinde: çıkarılmış dosyaya
# bakmak, bozuk arşivi zaten açtıktan sonra kontrol etmek olurdu.
# Uyuşmazlıkta build KIRILIR, atlanmaz: uv olmadan Unity MCP hiç çalışmıyor, yani
# "uyarı verip devam et" son kullanıcıya sessizce bozuk bir installer göndermektir.
& python $pinned verify $key $zip
if ($LASTEXITCODE -ne 0) {
    Remove-Item $zip -Force -ErrorAction SilentlyContinue
    throw "$key bütünlük doğrulaması başarısız — build durduruldu."
}

Expand-Archive -Path $zip -DestinationPath $dest -Force
Remove-Item $zip -Force
Remove-Item (Join-Path $dest "uvw.exe") -Force -ErrorAction SilentlyContinue
Write-Output "Tamam → $dest"
Get-ChildItem $dest | Select-Object Name, Length
