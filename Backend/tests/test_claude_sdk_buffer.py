"""Görsel taşıyan bir stdout satırı oturumu ÖLDÜRMEMELİ.

Sahada ölçülen arıza (2026-08-07, kurulu v2.3.0): kullanıcı sohbete fotoğraf
yapıştırınca oturum bazen komple düşüyor —

    Failed to decode JSON: JSON message exceeded maximum buffer size of
    1048576 bytes

Zincir: yapıştırılan görsel diske yazılıyor ve prompt'a yalnız YOLU giriyor
(`providers/_attachments.py`, sebebi orada yazılı). Claude o yolu `Read` ile
açıyor, `Read`'in sonucu görüntüyü base64 olarak geri koyuyor, ve SDK CLI'ın
stdout'undaki o TEK NDJSON satırını `max_buffer_size` ile sınırlıyor. base64 ham
boyutun ~4/3'ü olduğundan ~750 KB'lık bir PNG 1 MiB varsayılanını aşırmaya
yetiyor. Kullanıcının tarif ettiği "iki fotoğrafla patlıyor, üçle patlamıyor"
deseninin sebebi bu: belirleyici olan ADET değil, en büyük tek satırın boyutu.

Aşım kırpmayla değil `SDKJSONDecodeError` ile sonuçlanıyor, yani tek bir görsel
bütün sohbeti düşürüyordu.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))

from providers.claude_sdk_session import _SDK_STDOUT_LIMIT_BYTES  # noqa: E402


def _olusan_secenekler():
    """`start()`'ı gerçekten koşturup SDK'ya giden `ClaudeAgentOptions`'ı yakalar.

    Kaynak taraması yerine davranış: bu depoda "fonksiyon şu dizeyi içeriyor"
    diyen testlerin mutasyona KÖR olduğu birden çok kez ölçüldü.
    """
    import claude_agent_sdk

    from providers.claude_sdk_session import ClaudeSDKSession

    yakalanan = {}

    class _SahteClient:
        def __init__(self, options=None):
            yakalanan["options"] = options

        async def __aenter__(self):
            return self

    gercek = claude_agent_sdk.ClaudeSDKClient
    claude_agent_sdk.ClaudeSDKClient = _SahteClient
    try:
        asyncio.run(ClaudeSDKSession(conversation_id=1).start())
    finally:
        claude_agent_sdk.ClaudeSDKClient = gercek

    assert "options" in yakalanan, "start() SDK istemcisini hiç kurmadı — test ölçtüğünü sanıyor"
    return yakalanan["options"]


def test_tavan_gercekten_TRANSPORT_a_ulasiyor():
    """Asıl iddia. Seçeneği kabul etmek yetmez; sınırı uygulayan yere varmalı.

    Ölçüm noktası bilerek SDK'nın kendi transport'u: hatayı fırlatan gözcü orada
    (`subprocess_cli`, `guard()`), ve `ClaudeAgentOptions.max_buffer_size=None`
    sessizce 1 MiB'ye düşüyor. Yani "seçenek nesnede var mı" diye bakan bir test
    tam da bu sessiz düşüşü kaçırırdı.
    """
    from claude_agent_sdk._internal.transport.subprocess_cli import (
        _DEFAULT_MAX_BUFFER_SIZE,
        SubprocessCLITransport,
    )

    transport = SubprocessCLITransport(prompt="x", options=_olusan_secenekler())

    assert transport._max_buffer_size > _DEFAULT_MAX_BUFFER_SIZE, (
        "SDK 1 MiB varsayılanında kalıyor — yapıştırılan tek bir fotoğraf "
        "oturumu SDKJSONDecodeError ile düşürür"
    )


def test_tavan_gercekci_bir_FOTOGRAFI_kaldiriyor():
    """Sayının gerekçesi: eşiği aşan şey egzotik değil, sıradan bir ekran görüntüsü.

    Sınır "varsayılandan büyük" olmakla yetinemez; 2 MiB seçilseydi test yeşil
    kalır ama 1.5 MB'lık bir telefon fotoğrafı yine düşürürdü. Ölçüt somut:
    ham 8 MB'lık bir görselin base64'ü (~4/3) + JSON zarfı.
    """
    ham_gorsel = 8 * 1024 * 1024
    beklenen_satir = ham_gorsel * 4 // 3

    assert _SDK_STDOUT_LIMIT_BYTES >= beklenen_satir, (
        f"tavan {_SDK_STDOUT_LIMIT_BYTES} bayt; 8 MB'lık bir görselin base64'ü "
        f"~{beklenen_satir} bayt tutuyor ve oturumu yine düşürür"
    )


def test_BUYUK_bir_satir_GERCEKTEN_ayristiriliyor():
    """Asıl kullanıcı senaryosu: 1 MiB'den büyük bir satır gelince oturum SAĞ KALMALI.

    Denetim turu, üstteki üç testin hiçbirinin transport'un gerçek okuma yolunu
    (`read_messages` → `_LineFramer` → `guard`) çalıştırmadığını ölçtü: seçenek
    alanı 32 MiB görünürken guard'ın hâlâ 1 MiB uyguladığı bir SDK regresyonunda
    üçü de yeşil kalıyordu (probe `ndjson_guard_blind`, o turda `rc=1`).

    Bu test o boşluğu kapatıyor — alan değil DAVRANIŞ ölçüyor: gerçek transport'a
    gerçek bir NDJSON satırı veriliyor ve ayrıştırıldığı görülüyor.
    """
    import json

    from claude_agent_sdk._internal.transport.subprocess_cli import SubprocessCLITransport

    # Kullanıcının vakasını temsil eden boyut: eski 1 MiB tavanının üstünde,
    # yeni tavanın altında. Tavan geri düşerse bu satır ayrıştırılamaz.
    dolgu = "x" * (2 * 1024 * 1024)
    satir = json.dumps({"type": "assistant", "payload": dolgu}) + "\n"

    class _ParcaliAkis:
        """CLI'ın stdout'u gibi davranır: satır parça parça gelir."""

        def __aiter__(self):
            async def uret():
                # Akış çözülmüş metin taşıyor (`_LineFramer` str üzerinde çalışıyor).
                for i in range(0, len(satir), 64 * 1024):
                    yield satir[i:i + 64 * 1024]
            return uret()

    class _SahteSurec:
        returncode = None

        async def wait(self):
            return 0

    transport = SubprocessCLITransport(prompt="x", options=_olusan_secenekler())
    transport._process = _SahteSurec()
    transport._stdout_stream = _ParcaliAkis()

    async def oku():
        return [m async for m in transport.read_messages()]

    mesajlar = asyncio.run(oku())

    assert len(mesajlar) == 1, "2 MiB'lik geçerli satır hiç ayrıştırılamadı"
    assert mesajlar[0]["payload"] == dolgu, "satır ayrıştırıldı ama içeriği bozuldu"


def test_diske_yazilan_gorsel_tavani_TEHDIT_EDEMEZ():
    """Zincirin diğer ucu: ekleme yolu tavanı aşabilecek bir dosya bırakmamalı.

    Denetimin asıl bulgusu buydu — tavanı 32 MiB'ye çıkarmak sınıfı KAPATMIYOR,
    erteliyordu: ~24 MiB'lik tek bir görselin base64'ü tavanı yine aşıyor ve aynı
    çökme geri geliyordu (probe `accepted_24mib_image_exceeds_sdk_ceiling`, ana
    ağaçta `rc=1`). İki sabit birbirine bağlı olmak zorunda; bağ kopar da ekleme
    tavanı yükselirse bu test kırmızıya döner.
    """
    from providers._attachments import _MUTLAK_TAVAN_BAYT

    # base64 ham boyutun 4/3'ü + zarf. En kötü hâlde bile satır tavanının altında kalmalı.
    en_kotu_satir = _MUTLAK_TAVAN_BAYT * 4 // 3

    assert en_kotu_satir < _SDK_STDOUT_LIMIT_BYTES, (
        f"diske yazılabilen azami görsel {_MUTLAK_TAVAN_BAYT} bayt; base64'ü "
        f"~{en_kotu_satir} bayt eder ve {_SDK_STDOUT_LIMIT_BYTES} baytlık satır "
        "tavanını aşar — aynı çökme geri gelir"
    )


def test_iki_CLI_yolu_ayni_tavanda_bulusmali():
    """Aynı girdide iki yolun farklı davranması bu depoda tekrarlayan arıza şekli.

    Ephemeral CLI yolu (`cli_base`) bu sınıfı çoktan görmüş ve tavanını
    yükseltmişti; SDK yolu geride kalmıştı. Ayrışmayı serbest bırakmak, düzeltmeyi
    ileride yalnız bir yolda güncellenir hâle getirir.
    """
    from providers.cli_base import BaseCLIProvider

    assert _SDK_STDOUT_LIMIT_BYTES == BaseCLIProvider._CLI_STREAM_LIMIT_BYTES, (
        "SDK yolu ile ephemeral CLI yolu farklı tavanlarda — aynı fotoğraf "
        "sağlayıcıya göre bir patlıyor bir patlamıyor"
    )
