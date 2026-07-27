"""Log'a giden metinden sırları silen TEK kaynak.

Neden gerekli: `subprocess.run(..., check=True)` başarısız olduğunda fırlattığı
`CalledProcessError`'ın `str()`'i KOMUT LİSTESİNİN TAMAMINI taşıyor. O listede
Unity MCP transport URL'i var ve paylaşımlı sır o URL'in yol segmentinde. Yani
tek bir başarısız MCP kayıt denemesi sırrı düz metin olarak log dosyasına
yazıyordu — 2026-07-27 denetiminde probe ile üretildi.

Neden hata metni tamamen atılmıyor: kaydın NEDEN başarısız olduğu teşhis için
gerekli bilgi. Metin korunuyor, yalnız sır maskeleniyor.

Neden ayrı modül: ilk düzeltmede aynı fonksiyon üç sağlayıcı dosyasına
kopyalanmıştı. Aynı oturumda kapatılan bulguların en sık tekrarlayan sınıfı
"güvenlik kararının kopyalanması" idi — kopya, düzeltmenin kopyalardan yalnız
birine uygulanması demek.
"""

import re

# token_urlsafe(32) → [A-Za-z0-9_-] alfabesinde ~43 karakter. Alt sınır 20:
# daha kısa bir yol segmenti sır değil, gerçek bir rota adıdır ("/mcp/hub").
_MCP_PATH_SECRET = re.compile(r"(/mcp/)[A-Za-z0-9_\-]{20,}")
# LOCAL_APP_TOKEN=..., ANTHROPIC_API_KEY=..., X_API_SECRET=... gibi atamalar
_ENV_ASSIGNMENT = re.compile(r"((?:TOKEN|KEY|SECRET)[A-Z_]*=)\S+")


def redact_secrets(text: str) -> str:
    if not text:
        return text
    text = _MCP_PATH_SECRET.sub(r"\1<REDACTED>", text)
    return _ENV_ASSIGNMENT.sub(r"\1<REDACTED>", text)
