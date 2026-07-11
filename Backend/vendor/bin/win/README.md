# Video binary'leri (bundle)

Video-to-chat özelliği **ffmpeg** + **yt-dlp** gerektirir. Kullanıcı hiçbir şey
indirmesin diye bunlar app'e **bundle** edilir (`backend.spec` → `_video_bins`;
frozen'da `_internal/bin/` altına düşer, `providers/video_bin.py` resolver oradan bulur).

## Bu klasöre koy (Windows)

- `ffmpeg.exe` — https://www.gyan.dev/ffmpeg/builds/ (ffmpeg-release-essentials.zip → `bin/ffmpeg.exe`)
- `yt-dlp.exe` — https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe

Yoksa: **build kırılmaz** ama frozen app'te video çalışmaz. (Dev'de PATH'teki
ffmpeg/yt-dlp kullanılır — resolver PATH'e düşer.)

## Commit stratejisi (KULLANICI KARARI — bekliyor)

Bu `.exe`'ler büyük (~80-100MB). Repo'ya nasıl gireceği netleşmeli:
- **Git LFS** ile commit (`git lfs track "Backend/vendor/bin/win/*.exe"`), veya
- **.gitignore + build-öncesi indirme script'i** (repo temiz kalır, CI/kullanıcı build'de indirir).

Karar verilene kadar `.exe`'ler repo'ya **EKLENMEDİ** (yalnız bu README + `backend.spec` wiring hazır).

## Lisans

- ffmpeg: LGPL build (redistribution serbest). NOTICE'a eklenecek.
- yt-dlp: Unlicense (serbest).
