# Video binary'leri (bundle)

Video-to-chat özelliği **ffmpeg** + **yt-dlp** gerektirir. Kullanıcı hiçbir şey
indirmesin diye bunlar app'e **bundle** edilir (`backend.spec` → `_video_bins`;
frozen'da `_internal/bin/` altına düşer, `providers/video_bin.py` resolver oradan bulur).

## Nasıl gelir — ELLE DEĞİL, build adımı

```
Frontend/frontend » npm run build        # prebuild bunu kendisi çağırır
```

Zinciri: `prebuild` → `scripts/fetch-video-bins.js` → platforma göre
`Backend/vendor/fetch_video_bins.ps1` (Windows) ya da `.sh` (mac/linux) →
`Backend/vendor/bin/<os>/`.

Elle çağırmak istersen:

```
node Frontend/frontend/scripts/fetch-video-bins.js
```

Sarmalayıcı, sabitlenmiş özetler değişmediyse indirmeyi **atlar** (`.fetched`
damgası). Platform script'lerinin kendisinde atlama yok — her çağrıda 126 MB
yeniden iner; idempotanlık bilerek sarmalayıcıda, çünkü tekrar tekrar koşulan
şey build adımı.

⚠️ **`pwsh` VARSAYMA.** Bu depodaki eski yorumlar `pwsh Backend/vendor/...`
diyor ama PowerShell 7 kurulu olmayabilir (ölçüldü 30 Ağu 2026, bu makinede
yok). Sarmalayıcı önce `pwsh`, sonra Windows'un kendi `powershell`'ini deniyor.

## Dev modunda

`video_bin.py` çözümleyicisi `Backend/vendor/bin/<os>/` klasörüne de bakıyor,
yani indirdikten sonra `npm run dev` altında da bulunuyor — sistem PATH'ine
gerek yok. (30 Ağu 2026'ya kadar bakmıyordu: ikili indirilse bile bulunamıyor,
PATH'e düşülüyordu ve PATH'te yoksa video sessizce atlanıyordu.)

Binary yoksa **build kırılmaz**; frozen app'te video çalışmaz ve kullanıcı
`video_binary_missing` uyarısını görür.

## Commit stratejisi — KARAR VERİLDİ (30 Ağu 2026)

`.gitignore` + build-öncesi indirme. Git LFS seçilmedi: ikililer sürüm
başına ~126 MB ve `pinned_assets.json` zaten adres+özet taşıdığı için depoda
tutmanın getirdiği tek şey boyut olurdu.

Bu bölüm uzun süre "karar bekliyor" diyordu ve o yüzden **hiçbir şey indirilmedi** —
script'ler yazılmıştı, `backend.spec` wiring'i hazırdı, `.gitignore` yorumu
script'leri adıyla anıyordu, ama onları çağıran bir adım yoktu.

## Lisans

- ffmpeg: LGPL build (redistribution serbest). `THIRD-PARTY-NOTICES.md`'de.
- yt-dlp: Unlicense (serbest).
