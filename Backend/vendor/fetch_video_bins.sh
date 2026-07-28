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

# note_missing <rapor-etiketi> <hedef-dosya>
# Raporu yazar VE hedefteki eski kopyayı siler. İkisi bilerek TEK fonksiyonda:
# ayrı bırakıldıklarında ayrışıyorlar, ve denetimde ölçülen arıza tam olarak buydu
# (verification-failure-preserves-final-artifact) — özet "EKSİK KALAN BİNARY'LER"
# derken hemen altındaki `ls` dosyayı listeliyordu.
#
# Neden silmek şart: backend.spec bu dizini tarayıp ne bulursa pakete gömüyor. N.
# koşuda iyi bir ffmpeg kurulduysa, N+1. koşuda bozuk/kurcalanmış bir indirme
# doğrulamayı geçemediğinde ESKİ dosya yerinde kalıyor ve yine paketleniyordu; yani
# doğrulamanın reddettiği duruma rağmen ürün eski baytlarla çıkıyordu.
#
# Şiddeti neden daha yüksek değil: CI temiz checkout'ta koşuyor, dizin her seferinde
# boş başlıyor. Bu yüzden risk YEREL geliştirici build'lerine ve self-hosted
# runner'lara özgü. Gelecekte okuyan biri "CI'da olmuyormuş" diye bu satırları
# gereksiz görmesin — build makinesi kalıcı diskliyse arıza aynen geri gelir.
#
# Silmek build'i KIRMAK değildir: sözleşme hâlâ "en iyi çaba", betik yine 0 dönüyor,
# yalnızca pakete doğrulanmamış bayt sızmıyor.
note_missing() {
  missing="${missing}  - $1"$'\n'
  if [ -e "$2" ] && ! rm -f "$2"; then
    # Silinemezse rapor yine yalan söyler; o zaman en azından yüksek sesle söylensin.
    echo "UYARI: eski kopya SİLİNEMEDİ: $2 — doğrulanmamış haliyle pakete girebilir"
  fi
}

# Doğrulayamıyorsak hiç indirmiyoruz (fail-closed). Doğrulamasız indirme, bu betiğin
# kapatmak için var olduğu riskin ta kendisi; "en iyi çaba" sessizce eski davranışa
# düşmek anlamına gelmemeli.
#
# Ama bu iki dalda dizindeki mevcut dosyalara DOKUNULMUYOR, ve bu bilinçli bir ayrım:
# doğrulama başarısızlığı bir KANIT'tır (elimizdeki baytlar pinle uyuşmuyor),
# python3'ün yokluğu ise kanıtın YOKLUĞU. Dizindeki dosya bu betiğin daha önceki bir
# koşusundan geliyor, yani o gün doğrulamayı geçmişti; onu bugün silmek geçici bir
# ortam eksiğini iyi bir artefaktın imhasına çevirir ve python3'ü olmayan her
# makinede ffmpeg'siz paket üretir — güvenlik kazancı olmadan build regresyonu.
# Karşılığında dürüstlük borcu var: burada "bugün doğrulanmadı" açıkça yazılıyor,
# çünkü sessiz kalırsak okuyan kişi dizindekini bu koşunun ürünü sanar.
if ! command -v python3 >/dev/null 2>&1; then
  echo "UYARI: python3 yok — bütünlük doğrulaması yapılamaz, HİÇBİR binary kurulmuyor"
  echo "       ($dir'de eskiden kalan dosya varsa DURUYOR ve bu koşuda doğrulanmadı)"
  exit 0
fi
if [ ! -f "$pinned" ]; then
  echo "UYARI: doğrulama aracı bulunamadı ($pinned) — HİÇBİR binary kurulmuyor"
  echo "       ($dir'de eskiden kalan dosya varsa DURUYOR ve bu koşuda doğrulanmadı)"
  exit 0
fi

pinned_url() { python3 "$pinned" url "$1"; }

# ── Kütük CLI'ının çıkış kodu SINIFLARI ───────────────────────────────
# Sözleşme scripts/pinned_assets.py docstring'inde yazılı ve tek kaynağı orası:
#   0 = tamam
#   1 = BÜTÜNLÜK arızası — indirilen baytlar pinle uyuşmuyor. ASLA tekrar denenmez.
#   2 = kullanım / ORTAM hatası — yanlış argüman, desteklenmeyen Python sürümü.
#   3 = İŞLETİM arızası — anahtar kütükte yok, dosya okunamadı, kütük bozuk.
#
# Sınıfları ayırmak ZORUNLU. "sıfır değil → anahtar kütükte yok" indirgemesi denetimde
# ölçüldü (2026-07-28): Python 3.9'da modül import kapısında patlıyor (kod 2) ve bu
# betik operatöre "bu anahtar kütükte yok" diyordu — yani var olmayan bir kütük
# sorunu aratıyor, gerçek sebebi (yorumlayıcı sürümü) gizliyordu.
#
# Bu betikte HİÇBİR sınıf build'i kırmıyor: sözleşme en iyi çaba (dosya başındaki
# uzun nota bak, `set -e` bilerek YOK). Ama sınıf başına mesaj ayrı, çünkü operatörün
# yapacağı iş değişiyor: pin'i incele / Python'u değiştir / kütüğü onar.
#
# pinned_fail_label: sondaki "EKSİK KALAN BİNARY'LER" özetinde kullanılıyor. Özetin
# sebebi tekrar etmesi bilinçli — denetimde ölçülen arıza sınıfı tam olarak "özet ile
# ayrıntı ayrışıyor"du; sınıfı iki yerde birden yazmak ayrışmayı görünür kılıyor.
pinned_fail_label=""

report_pinned_failure() {
  local rc="$1" key="$2" stage="$3"
  case "$rc" in
    1)
      pinned_fail_label="bütünlük uyuşmazlığı"
      echo "UYARI: $key DOĞRULANAMADI ($stage) — indirme başarılı ama baytlar sabitlenmiş"
      echo "       özetle uyuşmuyor. KURULMUYOR ve tekrar DENENMİYOR: 'birkaç kez dene'"
      echo "       bir saldırgana yalnızca birkaç şans daha verir. Ayrıntı yukarıda."
      ;;
    2)
      pinned_fail_label="ortam hatası"
      echo "UYARI: $key ORTAM HATASI ($stage) — Python sürümü ya da çağrı biçimi uygun değil."
      echo "       Bu bir BÜTÜNLÜK arızası DEĞİL: hiçbir asset doğrulanmadı, hiçbir özet"
      echo "       uyuşmazlığı bulunmadı. Çözüm yukarıda Python'un kendi mesajında yazıyor"
      echo "       (stok macOS python3 3.9.6 yetmiyor; en az 3.10 gerekiyor)."
      ;;
    3)
      pinned_fail_label="işletim hatası"
      echo "UYARI: $key İŞLETİM HATASI ($stage) — anahtar kütükte yok, dosya okunamadı ya da"
      echo "       kütük ayrıştırılamadı ($pinned). Düzeltilebilir bir durum; bütünlük"
      echo "       arızasıyla ilgisi YOK. Ayrıntı yukarıdaki [pinned] satırında."
      echo "       ('yazım hatası' ile 'kütüğe henüz eklenmedi' dışarıdan aynı görünür.)"
      ;;
    *)
      pinned_fail_label="beklenmedik çıkış kodu $rc"
      echo "UYARI: $key — BEKLENMEDİK ÇIKIŞ KODU $rc ($stage)."
      echo "       $pinned sözleşmesi yalnız 0/1/2/3 tanımlıyor; bilinmeyen bir kod o"
      echo "       sözleşmenin değiştiğine işaret eder. Bilinen bir sınıfa SOKULMUYOR:"
      echo "       yanlış sınıflandırma, sınıflandırmamaktan pahalıya geliyor."
      ;;
  esac
}

# ORTAM kapısı, indirmelerden ÖNCE ve TEK yerde.
# Neden burada: kod 2 ("yorumlayıcı bu modülü koşturamıyor") anahtardan bağımsız,
# yani her anahtarda birebir tekrar eder — dört kez aynı uyarıyı basmak operatörü
# dört ayrı arıza var sanmaya iter.
# Neden `exit 0` ve neden hedef dizine DOKUNULMUYOR: bu, yukarıdaki "python3 yok" ve
# "kütük yok" dallarıyla AYNI sınıf — kanıtın YOKLUĞU. Doğrulama başarısızlığı bir
# KANIT'tır (baytlar pinle uyuşmuyor) ve orada eski kopya siliniyor; burada silmek,
# geçici bir ortam eksiğini iyi bir artefaktın imhasına çevirirdi.
# `keys` seçildi çünkü ağa çıkmıyor ve sürüm kapısı zaten modül IMPORT anında işliyor.
python3 "$pinned" keys >/dev/null; preflight_rc=$?
if [ "$preflight_rc" -eq 2 ]; then
  echo "UYARI: ORTAM HATASI — python3 bu kütük aracını koşturamıyor (çıkış kodu 2)."
  echo "       Sebep yukarıda Python'un kendi mesajında; bu bir bütünlük arızası DEĞİL."
  echo "       HİÇBİR binary kurulmuyor, hedef dizine DOKUNULMUYOR."
  echo "       ($dir'de eskiden kalan dosya varsa DURUYOR ve bu koşuda doğrulanmadı)"
  exit 0
fi
# 1/3 ya da beklenmedik kodlar burada tüketilmiyor: onlar anahtara özgü olabilir ve
# asıl teşhis aşağıda, ilgili binary'nin yanında basılıyor.

# --retry yalnız AĞ hatası için: yeniden deneme bozuk bağlantıya karşı işe yarar.
# Özet uyuşmazlığında ASLA tekrar denenmiyor (bkz. pinned_assets.IntegrityError):
# "birkaç kez dene" bir saldırgana yalnızca birkaç şans daha verir.
download_once() { curl -fL --retry 3 --retry-delay 2 -o "$2" "$1"; }

# fetch_pinned <anahtar> <hedef-dosya> [yedek-adres]
# 0 → dosya indi VE doğrulandı. 1 → dosya yok, çağıran o binary'yi atlamalı.
# Çağıran ayrıca $pinned_fail_label'ı okuyup özet raporunda kullanıyor.
#
# Kod `komut; rc=$?` ile YAKALANIYOR, `if ! komut` ile DEĞİL: `if !` yalnız
# "sıfır mı, değil mi" bırakıyor ve sınıf bilgisi tam orada kayboluyordu — bu
# dosyadaki yanlış teşhisin kaynağı buydu. `rc=$?` doğrudan komuttan SONRA geliyor,
# bir pipe'tan sonra değil (bu depoda ölçüldü: pipe'tan sonraki `$?` yanlış komutu
# ölçüyor). `pinned_url` bir kabuk fonksiyonu ve son komutunun kodunu aynen döndürüyor,
# yani sarmalama kodu kaybetmiyor.
fetch_pinned() {
  local key="$1" out="$2" fallback="${3:-}"
  local url rc
  pinned_fail_label=""
  url="$(pinned_url "$key")"; rc=$?
  if [ "$rc" -ne 0 ]; then
    report_pinned_failure "$rc" "$key" "adres okuma"
    echo "       $key ATLANIYOR."
    return 1
  fi
  echo "$key indiriliyor: $url"
  if ! download_once "$url" "$out"; then
    if [ -n "$fallback" ]; then
      echo "  ... adres yanıt vermedi; yedek adres deneniyor: $fallback"
      if ! download_once "$fallback" "$out"; then
        echo "UYARI: $key İNDİRİLEMEDİ (ağ/HTTP; yedek adres de olmadı) — atlanıyor"
        pinned_fail_label="ağ/HTTP"
        rm -f "$out"
        return 1
      fi
    else
      echo "UYARI: $key İNDİRİLEMEDİ (ağ/HTTP hatası) — atlanıyor"
      pinned_fail_label="ağ/HTTP"
      rm -f "$out"
      return 1
    fi
  fi
  # Bu aşamanın sınıfları ağ hatasından bilerek AYRI: "indiremedim" ile "indirdim ama
  # beklenen baytlar değil" bambaşka iki teşhis — biri bağlantı, diğeri upstream'de
  # değişmiş ya da araya girilmiş bir asset. Üstelik burada 1 (uyuşmazlık) ile
  # 3 (dosya okunamadı) da ayrılıyor: ikisi de "doğrulanamadı" diye raporlanırken
  # okunamayan bir dosya, doktrini gereği asla tekrar denenmemesi gereken bir arıza
  # gibi görünüyordu.
  python3 "$pinned" verify "$key" "$out"; rc=$?
  if [ "$rc" -ne 0 ]; then
    report_pinned_failure "$rc" "$key" "bütünlük doğrulaması"
    rm -f "$out"
    return 1
  fi
  return 0
}

# ── yt-dlp (tek dosya, doğrudan binary) ───────────────────────────────
# cp/chmod da denetleniyor: yarım kalan bir kopyalama (disk dolu, izin) hedefte
# bozuk bir dosya bırakır ve backend.spec onu yine gömerdi — "rapor ile dizin
# uyuşmuyor" arızasının aynısı, yalnız başka sebepten.
if fetch_pinned "yt-dlp/$key_os" "$tmp/yt-dlp"; then
  if ! (cp "$tmp/yt-dlp" "$dir/yt-dlp" && chmod +x "$dir/yt-dlp"); then
    echo "UYARI: yt-dlp hedefe kopyalanamadı — atlanıyor"
    note_missing "yt-dlp (kopyalama)" "$dir/yt-dlp"
  fi
else
  # Etikete sınıf giriyor: özet satırı ile yukarıdaki ayrıntı aynı sebebi göstersin.
  note_missing "yt-dlp ($pinned_fail_label)" "$dir/yt-dlp"
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
        if ! (cp "$f" "$dir/ffmpeg" && chmod +x "$dir/ffmpeg"); then
          echo "UYARI: ffmpeg (mac) hedefe kopyalanamadı — atlanıyor"
          note_missing "ffmpeg (kopyalama)" "$dir/ffmpeg"
        fi
      else
        echo "UYARI: ffmpeg (mac) arşivinde ffmpeg bulunamadı — atlanıyor"
        note_missing "ffmpeg (arşiv içeriği)" "$dir/ffmpeg"
      fi
    else
      echo "UYARI: ffmpeg (mac) arşivi açılamadı — atlanıyor"
      note_missing "ffmpeg (arşiv açma)" "$dir/ffmpeg"
    fi
  else
    note_missing "ffmpeg ($pinned_fail_label)" "$dir/ffmpeg"
  fi
else
  # linux statik (johnvansickle).
  # YOL TUZAĞI (ölçülmüş, teorik değil): sürümlü dosya zamanla releases/ altından
  # old-releases/ altına TAŞINIYOR ve yönlendirme konmuyor — bugün çalışan bir pin
  # ileride sessizce 404 olur. Aynı dosya adı ikinci yolda da denenir; beklenen özet
  # değişmediği için doğrulama iki yol için de aynı.
  # Bu ÖN yoklamanın stderr'i bilerek susturuluyor — ve yalnız burada. Aynı çağrı
  # birkaç satır aşağıda fetch_pinned içinde tekrarlanıyor ve teşhis ORADA sınıfıyla
  # birlikte tam olarak basılıyor; iki kez basmak operatöre iki ayrı arıza varmış
  # gibi görünüyor. Kod da yutulmuyor: başarısızlıkta yedek adres üretilmiyor, karar
  # aşağıdaki fetch_pinned'e kalıyor.
  ff_url="$(pinned_url "ffmpeg/linux" 2>/dev/null)" || ff_url=""
  # sed kullanılıyor, ${var/…/…} DEĞİL: bash 3.2'de (macOS'un varsayılanı) değiştirme
  # metnindeki ters bölüler harfi harfine kalıyor ve bozuk bir adres üretiyor — ölçüldü.
  ff_old="$(printf '%s' "$ff_url" | sed 's#/releases/#/old-releases/#')"
  [ "$ff_old" = "$ff_url" ] && ff_old=""   # adres kalıba uymuyorsa boşuna ikinci istek atma
  if fetch_pinned "ffmpeg/linux" "$tmp/ff.tar.xz" "$ff_old"; then
    if mkdir -p "$tmp/ff" && tar -xf "$tmp/ff.tar.xz" -C "$tmp/ff"; then
      f="$(find "$tmp/ff" -name ffmpeg -type f | head -1)"
      if [ -n "$f" ]; then
        if ! (cp "$f" "$dir/ffmpeg" && chmod +x "$dir/ffmpeg"); then
          echo "UYARI: ffmpeg (linux) hedefe kopyalanamadı — atlanıyor"
          note_missing "ffmpeg (kopyalama)" "$dir/ffmpeg"
        fi
      else
        echo "UYARI: ffmpeg (linux) arşivinde ffmpeg bulunamadı — atlanıyor"
        note_missing "ffmpeg (arşiv içeriği)" "$dir/ffmpeg"
      fi
    else
      echo "UYARI: ffmpeg (linux) arşivi açılamadı — atlanıyor"
      note_missing "ffmpeg (arşiv açma)" "$dir/ffmpeg"
    fi
  else
    note_missing "ffmpeg ($pinned_fail_label)" "$dir/ffmpeg"
  fi
fi

echo "Tamam ($dir):"; ls -la "$dir" 2>/dev/null || true

if [ -n "$missing" ]; then
  echo ""
  echo "!!! EKSİK KALAN BİNARY'LER — paket bunlarsız üretilecek:"
  printf '%s' "$missing"
  echo "    Sebep parantez içinde ve yukarıdaki UYARI satırlarında. Sınıflar AYRI şeydir:"
  echo "      ağ/HTTP              → adres yanıt vermedi; tekrar denenebilir."
  echo "      bütünlük uyuşmazlığı → baytlar pinle uyuşmuyor; ASLA tekrar denenmez."
  echo "      ortam hatası         → Python sürümü/çağrı biçimi; hiçbir bayt doğrulanmadı."
  echo "      işletim hatası       → anahtar/dosya/kütük sorunu; düzeltilebilir."
  echo "    Bu dosyalar hedef dizinden de KALDIRILDI: önceki bir koşudan kalan kopya"
  echo "    doğrulanmadan paketlenmesin diye. Yukarıdaki liste ile bu liste uyuşur."
fi

# Eksik olsa bile 0 dönülüyor: bu adımın sözleşmesi "elde edebildiğini topla, kalanı
# gürültülü biçimde bildir". Kırılma kararı build'in kendisine ait, buraya değil.
exit 0
