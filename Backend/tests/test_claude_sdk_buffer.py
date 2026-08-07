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
