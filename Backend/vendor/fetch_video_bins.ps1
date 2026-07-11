# Video araç zinciri — ffmpeg (LGPL) + yt-dlp indirir → Backend/vendor/bin/win/
# Frozen build (backend.spec) bunları otomatik gömer. İkililer repoda tutulmaz (~126MB);
# bu script ile çekilir (vendor/uv ile aynı mantık).
# Kullanım: pwsh Backend/vendor/fetch_video_bins.ps1
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$dir = Join-Path $PSScriptRoot 'bin\win'
New-Item -ItemType Directory -Force -Path $dir | Out-Null

Write-Host 'yt-dlp.exe indiriliyor...'
Invoke-WebRequest -Uri 'https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe' `
  -OutFile (Join-Path $dir 'yt-dlp.exe')

Write-Host 'ffmpeg (LGPL, win64) indiriliyor...'
$tmp = Join-Path $env:TEMP 'ffmpeg_lgpl.zip'
Invoke-WebRequest -Uri 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-lgpl.zip' `
  -OutFile $tmp
$ext = Join-Path $env:TEMP 'ffmpeg_ext'
if (Test-Path $ext) { Remove-Item $ext -Recurse -Force }
Expand-Archive -Path $tmp -DestinationPath $ext -Force
$exe = Get-ChildItem $ext -Recurse -Filter ffmpeg.exe | Select-Object -First 1
Copy-Item $exe.FullName (Join-Path $dir 'ffmpeg.exe') -Force
Remove-Item $tmp -Force; Remove-Item $ext -Recurse -Force

Write-Host 'Tamam:'
Get-ChildItem $dir -Filter *.exe |
  Select-Object Name, @{ N = 'MB'; E = { [math]::Round($_.Length / 1MB, 1) } }
