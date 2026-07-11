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
        ext = _EXT.get(media, "png")
        p = os.path.join(turn_dir, f"img_{i}.{ext}")
        try:
            with open(p, "wb") as f:
                f.write(base64.b64decode(b64))
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
