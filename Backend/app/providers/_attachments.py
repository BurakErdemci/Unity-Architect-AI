"""Sohbet eklerini (görsel, ileride video kareleri) CLI ajanlarına ulaştırmak için
paylaşılan yardımcılar.

- Claude Code: native SATIR-İÇİ görsel DESTEKLEMEZ (SDK ContentBlock union'ında ImageBlock
  yok → blok sessizce düşer). agy gibi dosya yaz + mesaja yol enjekte → Claude Read ile açar.
- Codex: app-server `input` dizisine `{"type":"localImage","path":...}` → dosya YOLU gerekir.
- agy: native görsel desteği YOK → dosya yaz + prompt'a yol enjekte (ajan kendi Read'iyle açar).

Üç CLI de dosya-yolu istediğinden `materialize_images` görselleri workspace altındaki gizli, tura özel bir
klasöre yazar (izin sorunlarını önlemek için workspace-altı; Unity Assets/ dışında ve nokta
ile başladığı için asset importer'ı tetiklemez, VCS'de görünmez). Tur bitince `cleanup_dir`.

Video işi geldiğinde: kareler de `data:image/...` listesi olarak aynı hatta verilecek.
"""
import base64
import logging
import os
import shutil
import uuid
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

_EXT = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif", "image/webp": "webp"}

_TMP_SUBDIR = os.path.join(".unity_architect_tmp", "attachments")

# Bu iki sayının sebebi diskte değil, ajanın CEVAP yolunda.
#
# Buraya yazılan dosyayı ajan `Read` ile açıyor ve `Read`'in sonucu görseli
# base64 olarak CLI'ın stdout'una TEK bir NDJSON satırı hâlinde geri koyuyor.
# O satırın bir tavanı var (`claude_sdk_session._SDK_STDOUT_LIMIT_BYTES`) ve
# aşılınca oturum komple düşüyor — kırpma yok. Yani buraya sınırsız bir görsel
# yazmak, sonraki adımda sohbeti öldürüyor.
#
# base64 ham boyutun ~4/3'ü. Denetim turu bunu ölçtü: 25.165.824 baytlık bir
# görsel tam 33.554.432 karakter base64 üretiyor ve JSON zarfıyla birlikte
# 32 MiB tavanını AŞIYOR (probe `accepted_24mib_image_exceeds_sdk_ceiling`).
# Yani tavanı yükseltmek sınıfı kapatmıyor, yalnız eşiği ötelemişti.
#
# Küçültme eşiği tavandan çok daha düşük tutuldu, çünkü asıl maliyet çökme
# değil token: 4 MiB'lik bir fotoğraf ajana hiçbir şey kazandırmadan pahalıya
# okunuyor. Ekran görüntüsü yolunda zaten aynı karar verilmiş durumda
# (`tools/screenshot_tool.py`: 1280 px + JPEG q82).
_KUCULTME_ESIGI_BAYT = 4 * 1024 * 1024
# Küçültme mümkün olmazsa (PIL yok, bozuk/desteklenmeyen içerik) bunu aşan
# görsel YAZILMAZ. Tek bir eki atlamak, kullanıcının bütün sohbet bağlamını
# öldürmekten iyidir — fail-closed tarafı burada budur.
_MUTLAK_TAVAN_BAYT = 16 * 1024 * 1024
_KUCULTME_KENARI = 2048
_KUCULTME_KALITESI = 85


def parse_data_uri(uri: str) -> Optional[Tuple[str, str]]:
    """'data:image/png;base64,XXXX' → ('image/png', 'XXXX').

    Header'sız düz base64 gelirse ('image/jpeg', uri) varsayılır. Ayrıştırılamazsa None.
    """
    try:
        if not uri:
            return None
        if uri.startswith("data:") and "," in uri:
            header, data = uri.split(",", 1)
            media = header.split(":", 1)[1].split(";", 1)[0] or "image/jpeg"
            return media, data
        return "image/jpeg", uri
    except Exception:
        logger.warning("[attachments] data-uri ayrıştırılamadı", exc_info=True)
        return None


def _uzanti(veri: bytes) -> Optional[str]:
    """Sihirli baytlardan gerçek biçimi çöz; tanınmazsa None."""
    if veri.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if veri.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if veri.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if veri[:4] == b"RIFF" and veri[8:12] == b"WEBP":
        return "webp"
    return None


def _sonucu_dogrula(ham: bytes, kucuk: bytes) -> Optional[bytes]:
    """Küçültme İDDİASINI çıktının kendisiyle sına.

    "Küçülttüm" demek küçüldüğünü göstermez: zaten JPEG olan devasa bir fotoğraf
    yeniden kodlandığında büyüyebilir de. Ölçüt her zaman çıkan bayt.
    """
    if len(kucuk) > _MUTLAK_TAVAN_BAYT:
        logger.warning(
            f"[attachments] görsel küçültmeden sonra da {len(kucuk)} bayt — atlandı"
        )
        return None
    logger.info(f"[attachments] görsel küçültüldü: {len(ham)} → {len(kucuk)} bayt")
    return kucuk


def kucult(ham: bytes) -> Optional[bytes]:
    """Eşiği aşan görseli küçültür. Küçültemezse None döner (çağıran atlar).

    Şeffaflık taşıyan görsel PNG kalır (gerekçe gövdede); taşımayan JPEG'e
    çevrilir. Animasyonlu GIF'te ilk kare alınır — ajan zaten tek kare görüyor.
    """
    if len(ham) <= _KUCULTME_ESIGI_BAYT:
        return ham
    try:
        import io

        from PIL import Image

        img = Image.open(io.BytesIO(ham))
        seffaf = img.mode in ("RGBA", "LA") or (
            img.mode == "P" and "transparency" in img.info
        )
        # `thumbnail` en-boy oranını korur ve zaten küçük olanı BÜYÜTMEZ; yani
        # 3 MB'lık ama 800 px'lik bir görsel yeniden örneklenmeden geçer.
        img.thumbnail((_KUCULTME_KENARI, _KUCULTME_KENARI), Image.LANCZOS)

        if seffaf:
            # ⚠️ Buradaki ilk yazım alfayı JPEG'e çevirirken DÜŞÜRÜYORDU ve
            # doğrulama turu bunu ölçtü: bütünüyle şeffaf bir PNG çıktıda üç
            # kanalın extrema'sı da (0,0), yani ajan TAMAMEN SİYAH bir görüntü
            # görüyordu. Kullanıcının yapıştırdığı şey ile ajanın analiz ettiği
            # şey sessizce farklıydı — küçültmenin kendisinden çok daha kötü.
            # Şeffaflık varken biçim korunuyor; PNG kayıpsız olduğu için
            # küçültülmüş boyut da zaten tavanın çok altında kalıyor.
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            if len(buf.getvalue()) <= _MUTLAK_TAVAN_BAYT:
                return _sonucu_dogrula(ham, buf.getvalue())
            # PNG bile sığmıyorsa alfayı BEYAZ zemine bindir. Atmakla arasındaki
            # fark önemli: bindirme kompozisyonu korur, atmak siyaha boyar.
            zemin = Image.new("RGB", img.size, (255, 255, 255))
            zemin.paste(img.convert("RGBA"), mask=img.convert("RGBA").split()[-1])
            img = zemin
        elif img.mode != "RGB":
            img = img.convert("RGB")

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=_KUCULTME_KALITESI)
        kucuk = buf.getvalue()
    except Exception as e:
        logger.warning(f"[attachments] görsel küçültülemedi ({len(ham)} bayt): {e}")
        return None if len(ham) > _MUTLAK_TAVAN_BAYT else ham

    return _sonucu_dogrula(ham, kucuk)


def _attach_root(workspace: Optional[str]) -> str:
    base = workspace if (workspace and os.path.isdir(workspace)) else "."
    return os.path.join(base, _TMP_SUBDIR)


def materialize_images(images: Optional[List[str]], workspace: Optional[str],
                       tag: str) -> Tuple[List[str], Optional[str]]:
    """Base64 görselleri diske yazar; (mutlak_yollar, tur_klasörü) döner.

    Hatalı/temsil edilemeyen görseller sessizce atlanır (tur devam eder). Hiç yazılmazsa
    tur_klasörü None döner. `tag` klasör adını benzersizleştirmek için (ör. 'codex_conv12').
    """
    if not images:
        return [], None
    turn_id = f"{tag}_{uuid.uuid4().hex[:8]}"
    turn_dir = os.path.join(_attach_root(workspace), turn_id)
    try:
        os.makedirs(turn_dir, exist_ok=True)
    except Exception:
        logger.warning("[attachments] temp klasör oluşturulamadı", exc_info=True)
        return [], None

    paths: List[str] = []
    for i, uri in enumerate(images):
        parsed = parse_data_uri(uri)
        if not parsed:
            continue
        media, b64 = parsed
        try:
            ham = base64.b64decode(b64)
        except Exception as e:
            logger.warning(f"[attachments] görsel {i} çözülemedi (atlandı): {e}")
            continue

        veri = kucult(ham)
        if veri is None:
            logger.warning(f"[attachments] görsel {i} çok büyük ve küçültülemedi — atlandı")
            continue
        # Uzantı İÇERİKTEN okunuyor, `media` başlığından ya da "değişti mi"
        # kimlik karşılaştırmasından değil: küçültme çıktısı şeffaflığa göre PNG
        # ya da JPEG olabiliyor, ve yanlış uzantı ajanın dosyayı yanlış çözmesine
        # yol açıyor. Başlık zaten kullanıcıdan geliyor, içerikle uyuşma garantisi yok.
        ext = _uzanti(veri) or _EXT.get(media, "png")
        p = os.path.join(turn_dir, f"img_{i}.{ext}")
        try:
            with open(p, "wb") as f:
                f.write(veri)
            paths.append(os.path.abspath(p))
        except Exception as e:
            # Bozuk base64 kullanıcı kaynaklı olabilir → tam traceback yerine kısa not.
            logger.warning(f"[attachments] görsel {i} yazılamadı (atlandı): {e}")

    return paths, (turn_dir if paths else None)


def cleanup_dir(turn_dir: Optional[str]) -> None:
    """Tura ait temp klasörü best-effort sil (hata yutulur)."""
    if not turn_dir:
        return
    try:
        shutil.rmtree(turn_dir, ignore_errors=True)
    except Exception:
        pass
