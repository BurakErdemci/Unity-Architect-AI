# Unity MCP için gerekli uv araç zincirini (uv.exe + uvx.exe) indirir.
# Bu ikililer installer'a gömülür (electron-builder.yml → extraResources: uv),
# böylece kullanıcının PC'sinde uv kurulu olmasa da Unity MCP çalışır.
# Boyutları büyük olduğu için git'e konmaz (.gitignore); build öncesi bunu çalıştır.
#
# Kullanım:  pwsh Backend/vendor/fetch_uv.ps1
$ErrorActionPreference = "Stop"
$dest = Join-Path $PSScriptRoot "uv"
New-Item -ItemType Directory -Force $dest | Out-Null
$zip = Join-Path $env:TEMP "uv-win-x64.zip"
$url = "https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip"
Write-Output "uv indiriliyor: $url"
Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
Expand-Archive -Path $zip -DestinationPath $dest -Force
Remove-Item $zip -Force
Remove-Item (Join-Path $dest "uvw.exe") -Force -ErrorAction SilentlyContinue
Write-Output "Tamam → $dest"
Get-ChildItem $dest | Select-Object Name, Length
