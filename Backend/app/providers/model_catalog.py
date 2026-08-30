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


# ── OpenRouter açık kataloğu ────────────────────────────────────────────────
#
# Neden burada: bir modelin KÜNYESİ (düzgün ad, bağlam penceresi, fiyat,
# OpenRouter karşılığı) sağlayıcıların kendi `/v1/models` cevaplarında YOK —
# OpenAI yalnız kimlik döndürüyor. Bu bilgi 30 Ağu 2026'ya kadar elle
# yazılıyordu ve elle tutulan liste listelediğinden ayrışıyordu.
#
# ÖLÇÜLDÜ 30 Ağu 2026: `https://openrouter.ai/api/v1/models` **anahtarsız**
# çalışıyor (HTTP 200, 396 model) ve her kayıt `name`, `context_length`,
# `pricing`, `expiration_date` taşıyor. Yani künye için ücretsiz, canlı ve
# sağlayıcı-üstü bir kaynak var.
#
# Sınırı da ölçüldü: 14 kimliğin 12'si `<ad-alanı>/<kimlik>` biçiminde birebir
# tutuyor, 2'si tutmuyor (`anthropic/claude-haiku-4-5` OR'da yok; Groq'un
# modeli OR'da `meta-llama/` altında). Bu yüzden katalog LİSTENİN KAYNAĞI
# DEĞİL, yalnız künye zenginleştiricisi: eşleşme bulunamazsa model yine
# görünür, sadece künyesiz.
_OPENROUTER_URL = "https://openrouter.ai/api/v1/models"
_OR_TTL_SECONDS = 3600.0
_or_cache: tuple[float, Optional[Dict[str, dict]]] | None = None


def openrouter_catalog(force: bool = False) -> Optional[Dict[str, dict]]:
    """`{openrouter_id: {name, context_length, pricing}}`, ya da ulaşılamazsa None."""
    global _or_cache
    now = time.monotonic()
    if not force and _or_cache and (now - _or_cache[0]) < _OR_TTL_SECONDS:
        return _or_cache[1]
    sonuc: Optional[Dict[str, dict]] = None
    try:
        request = urllib.request.Request(_OPENROUTER_URL)
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS * 2) as response:
            payload = json.loads(response.read())
        kayitlar = {}
        for m in payload.get("data") or []:
            mid = (m or {}).get("id")
            if not mid:
                continue
            kayitlar[str(mid)] = {
                "name": m.get("name") or mid,
                "context_length": m.get("context_length"),
                "pricing": m.get("pricing"),
                "expiration_date": m.get("expiration_date"),
            }
        sonuc = kayitlar or None
    except Exception as exc:
        logger.warning("OpenRouter kataloğu alınamadı: %s", exc)
    _or_cache = (now, sonuc)
    return sonuc


# Sağlayıcı → OpenRouter ad alanı. Bu tablo BİLEREK elle yazılı ve elle yazılı
# model listesinden farklı: 9 satır, ve sağlayıcı adları model adları gibi her
# ay değişmiyor. `None` = ad alanı eşlemesi yok; o sağlayıcının kimlikleri
# zaten `vendor/model` biçiminde geliyor (NVIDIA NIM, Groq'un gpt-oss'ları).
_OR_NAMESPACE: Dict[str, Optional[str]] = {
    "anthropic": "anthropic",
    "openai": "openai",
    "google": "google",
    "deepseek": "deepseek",
    "z-ai": "z-ai",
    "moonshot": "moonshotai",
    "groq": None,
    "nvidia": None,
    "openrouter": "",
}

# Sohbet DIŞI modelleri eleyen desenler. ⚠️ Bu bir SEZGİ, ölçüm değil:
# sağlayıcıların ham `/v1/models` cevabı gömme, ses, görsel ve moderasyon
# modellerini de döndürüyor ve bunların sohbet seçicisinde işi yok. Yanlış
# elemek yanlış göstermekten daha az zararlı değil, o yüzden desenler dar
# tutuldu — şüphede kalan model LİSTEDE KALIR.
_SOHBET_DISI = (
    "embedding", "embed-", "tts", "whisper", "transcribe", "moderation",
    "dall-e", "image-", "-image", "audio", "realtime", "rerank", "guard",
)


def is_chat_model(model_id: str) -> bool:
    m = model_id.lower()
    return not any(p in m for p in _SOHBET_DISI)


def openrouter_id_for(provider: str, model_id: str) -> Optional[str]:
    """Yerel kimlikten OpenRouter kimliğini türet.

    Ölçüldü 30 Ağu 2026: 14 kimliğin 12'si bu kuralla tutuyor. Tutmayanlar
    künyesiz kalıyor — model yine listede görünüyor, sadece bağlam penceresi
    ve düzgün adı olmuyor. Eşleşmeyi zorlamak, YANLIŞ bir künyeyi doğru gibi
    göstermek olurdu.
    """
    if "/" in model_id:
        return model_id
    ns = _OR_NAMESPACE.get(provider)
    if ns is None:
        return None
    return f"{ns}/{model_id}" if ns else model_id


def clear_cache() -> None:
    """Testler ve `force` yolu için; süreç ömrü boyunca başka çağıranı yok."""
    global _or_cache
    _cache.clear()
    _or_cache = None
