"""Bulut sağlayıcılardan CANLI model listesi.

Neden var: `config_routes.get_available_models`'daki bulut kataloğu elle
yazılmış. Elle tutulan liste listelediğinden ayrışıyor ve kaymış bir liste hiç
liste olmamasından kötü, çünkü güncel sanılıp okunuyor — bu depoda aynı kalıp
CLI önek tablolarında iki kez ölçüldü.

Neden elle yazılı katalog SİLİNMİYOR: canlı uç yalnız kimlik döndürüyor.
Görünen ad, OpenRouter karşılığı ve "ücretli" işareti küratörlü bilgi ve hiçbir
`/v1/models` cevabında yok. Bu yüzden tasarım "değiştir" değil BİRLEŞTİR:
katalog künye, canlı liste ise "bu hesap gerçekten neye erişiyor" sorusunun
cevabı.

Belirsizlik sessizce doldurulmuyor: çağrı başarısızsa `None` döner ve çağıran
"bilmiyoruz" durumunu ayrı bir hâl olarak taşır. Boş küme döndürmek "hesabın
hiçbir modeli yok" demek olurdu ve katalogdaki her satırı yanlışlıkla
erişilemez göstermeye yeterdi.

Bağımlılık eklenmedi: `urllib.request`, `config_routes`'un Ollama çağrısıyla
aynı desen.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.request
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Sağlayıcı → (uç, kimlik biçimi, cevap şekli).
#
# Anahtar HER ZAMAN bu sözlükteki sağlayıcı adıyla çekiliyor ve aynı adın
# ucuna gidiyor, yani bir sağlayıcının anahtarı başka bir sağlayıcının ucuna
# yapısal olarak gidemiyor. `test_model_catalog` bunu sabitliyor.
_ENDPOINTS: Dict[str, tuple[str, str, str]] = {
    "openai":     ("https://api.openai.com/v1/models",              "bearer",     "openai"),
    "deepseek":   ("https://api.deepseek.com/v1/models",            "bearer",     "openai"),
    "groq":       ("https://api.groq.com/openai/v1/models",         "bearer",     "openai"),
    "openrouter": ("https://openrouter.ai/api/v1/models",           "bearer",     "openai"),
    "moonshot":   ("https://api.moonshot.ai/v1/models",             "bearer",     "openai"),
    "z-ai":       ("https://api.z.ai/api/paas/v4/models",           "bearer",     "openai"),
    "nvidia":     ("https://integrate.api.nvidia.com/v1/models",    "bearer",     "openai"),
    "anthropic":  ("https://api.anthropic.com/v1/models?limit=100", "x-api-key",  "anthropic"),
    "google":     ("https://generativelanguage.googleapis.com/v1beta/models", "google", "google"),
}

_TTL_SECONDS = 600.0
_TIMEOUT_SECONDS = 6.0

# provider → (zaman damgası, sonuç). Sonuç `None` ise "o turda ulaşılamadı".
_cache: Dict[str, tuple[float, Optional[Dict[str, str]]]] = {}


def supported_providers() -> tuple[str, ...]:
    """Canlı listeleme ucu BİLİNEN sağlayıcılar.

    Burada olmayan bir sağlayıcı için "listeleme yolu yok" demek doğru; bir uç
    denenip başarısız olmasıyla karıştırılmamalı.
    """
    return tuple(_ENDPOINTS)


def _headers(kind: str, api_key: str) -> Dict[str, str]:
    if kind == "bearer":
        return {"Authorization": f"Bearer {api_key}"}
    if kind == "x-api-key":
        # Anthropic sürüm başlığı olmadan 400 döndürüyor.
        return {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    if kind == "google":
        return {"x-goog-api-key": api_key}
    raise ValueError(f"bilinmeyen kimlik biçimi: {kind}")


def _parse(shape: str, payload: dict) -> Dict[str, str]:
    """Cevabı `{model_id: gorunen_ad}` sözlüğüne indir."""
    out: Dict[str, str] = {}
    if shape in ("openai", "anthropic"):
        for item in payload.get("data") or []:
            mid = (item or {}).get("id")
            if mid:
                out[str(mid)] = str(item.get("display_name") or item.get("name") or mid)
    elif shape == "google":
        for item in payload.get("models") or []:
            raw = (item or {}).get("name") or ""
            # "models/gemini-3.6-flash" → "gemini-3.6-flash"
            mid = raw.split("/", 1)[1] if "/" in raw else raw
            if mid:
                out[mid] = str(item.get("displayName") or mid)
    return out


def _fetch(provider: str, api_key: str) -> Optional[Dict[str, str]]:
    url, auth_kind, shape = _ENDPOINTS[provider]
    try:
        request = urllib.request.Request(url, headers=_headers(auth_kind, api_key))
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read())
        parsed = _parse(shape, payload)
        # Şema değişmiş ya da beklenmedik bir gövde gelmişse boş sözlük çıkar.
        # Onu "hesapta model yok" diye taşımak katalogdaki her satırı
        # erişilemez gösterirdi; bilinmezlik olarak bildiriliyor.
        return parsed or None
    except Exception as exc:
        # Anahtar ASLA loglanmıyor: istisna metni URL taşıyabilir, başlık taşımaz.
        logger.warning("Model listesi alınamadı (%s): %s", provider, exc)
        return None


def list_models(provider: str, api_key: str, force: bool = False) -> Optional[Dict[str, str]]:
    """Sağlayıcının hesaba açık modelleri, ya da bilinemiyorsa `None`.

    `force` önbelleği atlar — kullanıcı "yenile" dediğinde bayat cevap vermek
    tam olarak yenilemenin var olma sebebini boşa çıkarır.
    """
    # `isinstance` şart, "truthy" yetmiyor: testlerde sahte bir veritabanı
    # anahtar yerine bir mock döndürüyor ve mock her zaman truthy. Onsuz test
    # takımı sessizce GERÇEK ağ çağrısı yapardı — hem yavaş hem kırılgan, hem
    # de dışarıya istek atan bir birim testi.
    if provider not in _ENDPOINTS or not isinstance(api_key, str) or not api_key:
        return None
    now = time.monotonic()
    if not force:
        cached = _cache.get(provider)
        if cached and (now - cached[0]) < _TTL_SECONDS:
            return cached[1]
    result = _fetch(provider, api_key)
    _cache[provider] = (now, result)
    return result


def clear_cache() -> None:
    """Testler ve `force` yolu için; süreç ömrü boyunca başka çağıranı yok."""
    _cache.clear()
