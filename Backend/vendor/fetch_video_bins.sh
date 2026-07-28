#!/usr/bin/env bash
# Video araç zinciri (ffmpeg + yt-dlp) — mac/linux için Backend/vendor/bin/<os>/ altına indirir.
# Statik binary'ler seçilir (PyInstaller'a temiz gömülür). Windows için: fetch_video_bins.ps1.
#
# SÜRÜM SABİT: adres ve beklenen özet scripts/pinned_assets.json'da; buradaki hiçbir
# adres 'latest'/rolling değil. İndirilen baytlar arşiv AÇILMADAN ÖNCE doğrulanır —
# çıkarılmış binary'nin özeti kütükteki değerle karşılaştırılamaz, ve zararlı bir arşiv
# zaten çıkarma anında iş yapmış olur.
#
# EN İYİ ÇABA, KASITLI: bir binary alınamazsa build kırılmaz, o binary'siz devam edilir
# (CI'da bu adım continue-on-error ile koşuyor). Bu yüzden burada `set -e` YOK: betik
# sonuna kadar koşup neyin eksik kaldığını topluca raporlasın.
#
# Doğrulama başarısızlığı da AYNI yola düşer: dosya KURULMAZ, ama build kırılmaz.
# Gerekçe: doğrulanmamış bir ffmpeg'i pakete koymak, ffmpeg'siz paket göndermekten
# kötüdür — biri bir özelliği kaybettirir, diğeri her kullanıcıda kimliği bilinmeyen
# kod çalıştırır. Buna karşılık fetch_uv.sh `set -e` ile koşar ve orada aynı hata
# build'i KIRAR: uv olmadan Unity MCP hiç çalışmaz, yani orada eksik binary kabul
# edilebilir bir sonuç değil. Fark bilinçli; biri "tutarlılık" adına birini diğerine
# benzetmeye kalkmasın diye buraya yazılı.
#
# Kullanım: bash Backend/vendor/fetch_video_bins.sh
set -uo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
repo_root="$(cd "$here/../.." && pwd)"
pinned="$repo_root/scripts/pinned_assets.py"

case "$(uname -s)" in
  # Dizin adı ('mac') ile kütük anahtarı ('macos') aynı değil; ikisi ayrı tutuluyor
  # çünkü bin/mac yolu backend.spec ve runtime tarafında zaten sabit.
  Darwin) os="mac";   key_os="macos" ;;
  Linux)  os="linux"; key_os="linux" ;;
  *) echo "desteklenmeyen OS: $(uname -s)"; exit 0 ;;
esac
dir="$here/bin/$os"
mkdir -p "$dir"

# Her indirme geçici dizine iner, ancak doğrulandıktan sonra $dir'e kopyalanır:
# böylece yarım/yanlış bir dosya hedef dizinde bir an bile durmaz (backend.spec
# orayı tarıyor). trap ile temizlik zorunlu — betik nasıl biterse bitsin çalışır.
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

missing=""
note_missing() { missing="${missing}  - $1"$'\n'; }

# Doğrulayamıyorsak hiç indirmiyoruz (fail-closed). Doğrulamasız indirme, bu betiğin
# kapatmak için var olduğu riskin ta kendisi; "en iyi çaba" sessizce eski davranışa
# düşmek anlamına gelmemeli.
if ! command -v python3 >/dev/null 2>&1; then
  echo "UYARI: python3 yok — bütünlük doğrulaması yapılamaz, HİÇBİR binary kurulmuyor"
  exit 0
fi
if [ ! -f "$pinned" ]; then
  echo "UYARI: doğrulama aracı bulunamadı ($pinned) — HİÇBİR binary kurulmuyor"
  exit 0
fi

pinned_url() { python3 "$pinned" url "$1"; }

# --retry yalnız AĞ hatası için: yeniden deneme bozuk bağlantıya karşı işe yarar.
# Özet uyuşmazlığında ASLA tekrar denenmiyor (bkz. pinned_assets.IntegrityError):
# "birkaç kez dene" bir saldırgana yalnızca birkaç şans daha verir.
download_once() { curl -fL --retry 3 --retry-delay 2 -o "$2" "$1"; }

# fetch_pinned <anahtar> <hedef-dosya> [yedek-adres]
# 0 → dosya indi VE doğrulandı. 1 → dosya yok, çağıran o binary'yi atlamalı.
# Not: `if ! komut; then` kullanılıyor, `rc=$?` DEĞİL — bu depoda ölçüldü, `$?` bir
# pipe'tan sonra yanlış komutun kodunu okuyor.
fetch_pinned() {
  local key="$1" out="$2" fallback="${3:-}"
  local url
  if ! url="$(pinned_url "$key")"; then
    # Anahtar yoksa sessizce atlamıyoruz: "yazım hatası" ile "kütüğe henüz eklenmedi"
    # dışarıdan aynı görünür, ikisi de görünür olmalı.
    echo "UYARI: '$key' kütükte yok (scripts/pinned_assets.json) — atlanıyor"
    return 1
  fi
  echo "$key indiriliyor: $url"
  if ! download_once "$url" "$out"; then
    if [ -n "$fallback" ]; then
      echo "  ... adres yanıt vermedi; yedek adres deneniyor: $fallback"
      if ! download_once "$fallback" "$out"; then
        echo "UYARI: $key İNDİRİLEMEDİ (ağ/HTTP; yedek adres de olmadı) — atlanıyor"
        rm -f "$out"
        return 1
      fi
    else
      echo "UYARI: $key İNDİRİLEMEDİ (ağ/HTTP hatası) — atlanıyor"
      rm -f "$out"
      return 1
    fi
  fi
  if ! python3 "$pinned" verify "$key" "$out"; then
    # Bu mesaj ağ hatasından bilerek AYRI: "indiremedim" ile "indirdim ama beklenen
    # baytlar değil" bambaşka iki teşhis — biri bağlantı, diğeri upstream'de değişmiş
    # ya da araya girilmiş bir asset.
    echo "UYARI: $key DOĞRULANAMADI — indirme başarılı ama baytlar sabitlenmiş özetle"
    echo "       uyuşmuyor. KURULMUYOR (tekrar denenmiyor; ayrıntı yukarıda)."
    rm -f "$out"
    return 1
  fi
  return 0
}

# ── yt-dlp (tek dosya, doğrudan binary) ───────────────────────────────
if fetch_pinned "yt-dlp/$key_os" "$tmp/yt-dlp"; then
  cp "$tmp/yt-dlp" "$dir/yt-dlp" && chmod +x "$dir/yt-dlp"
else
  note_missing "yt-dlp"
fi

# ── ffmpeg (statik, arşiv içinde) ─────────────────────────────────────
if [ "$os" = "mac" ]; then
  # evermeet.cx statik ffmpeg (Intel; Apple Silicon'da Rosetta 2 ile çalışır — runner'da mevcut).
  # Kütükteki not: evermeet checksum yayınlamıyor ve istek başka bir hosta 302 atıyor;
  # doğrulamanın en çok değdiği satır bu.
  if fetch_pinned "ffmpeg/macos" "$tmp/ffmpeg.zip"; then
    if mkdir -p "$tmp/ff" && unzip -o -q "$tmp/ffmpeg.zip" -d "$tmp/ff"; then
      # Arşiv içindeki yol aranıyor, sabit varsayılmıyor: pin yükseltildiğinde düzen
      # değişirse sessiz bir atlama yerine dosya yine bulunur.
      f="$(find "$tmp/ff" -name ffmpeg -type f | head -1)"
      if [ -n "$f" ]; then
        cp "$f" "$dir/ffmpeg" && chmod +x "$dir/ffmpeg"
      else
        echo "UYARI: ffmpeg (mac) arşivinde ffmpeg bulunamadı — atlanıyor"
        note_missing "ffmpeg (arşiv içeriği)"
      fi
    else
      echo "UYARI: ffmpeg (mac) arşivi açılamadı — atlanıyor"
      note_missing "ffmpeg (arşiv açma)"
    fi
  else
    note_missing "ffmpeg (indirme/doğrulama)"
  fi
else
  # linux statik (johnvansickle).
  # YOL TUZAĞI (ölçülmüş, teorik değil): sürümlü dosya zamanla releases/ altından
  # old-releases/ altına TAŞINIYOR ve yönlendirme konmuyor — bugün çalışan bir pin
  # ileride sessizce 404 olur. Aynı dosya adı ikinci yolda da denenir; beklenen özet
  # değişmediği için doğrulama iki yol için de aynı.
  ff_url="$(pinned_url "ffmpeg/linux")" || ff_url=""
  # sed kullanılıyor, ${var/…/…} DEĞİL: bash 3.2'de (macOS'un varsayılanı) değiştirme
  # metnindeki ters bölüler harfi harfine kalıyor ve bozuk bir adres üretiyor — ölçüldü.
  ff_old="$(printf '%s' "$ff_url" | sed 's#/releases/#/old-releases/#')"
  [ "$ff_old" = "$ff_url" ] && ff_old=""   # adres kalıba uymuyorsa boşuna ikinci istek atma
  if fetch_pinned "ffmpeg/linux" "$tmp/ff.tar.xz" "$ff_old"; then
    if mkdir -p "$tmp/ff" && tar -xf "$tmp/ff.tar.xz" -C "$tmp/ff"; then
      f="$(find "$tmp/ff" -name ffmpeg -type f | head -1)"
      if [ -n "$f" ]; then
        cp "$f" "$dir/ffmpeg" && chmod +x "$dir/ffmpeg"
      else
        echo "UYARI: ffmpeg (linux) arşivinde ffmpeg bulunamadı — atlanıyor"
        note_missing "ffmpeg (arşiv içeriği)"
      fi
    else
      echo "UYARI: ffmpeg (linux) arşivi açılamadı — atlanıyor"
      note_missing "ffmpeg (arşiv açma)"
    fi
  else
    note_missing "ffmpeg (indirme/doğrulama)"
  fi
fi

echo "Tamam ($dir):"; ls -la "$dir" 2>/dev/null || true

if [ -n "$missing" ]; then
  echo ""
  echo "!!! EKSİK KALAN BİNARY'LER — paket bunlarsız üretilecek:"
  printf '%s' "$missing"
  echo "    Sebep yukarıdaki UYARI satırlarında; 'indirilemedi' ile 'doğrulanamadı' AYRI şeydir."
fi

# Eksik olsa bile 0 dönülüyor: bu adımın sözleşmesi "elde edebildiğini topla, kalanı
# gürültülü biçimde bildir". Kırılma kararı build'in kendisine ait, buraya değil.
exit 0
