import asyncio
import os
import sys
from unittest.mock import MagicMock, patch


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from providers.api_providers import AnthropicProvider
from routes.config_routes import create_config_router


@patch("providers.api_providers.anthropic.Anthropic")
def test_opus_5_and_4_8_keep_distinct_api_model_ids(anthropic_client):
    anthropic_client.return_value = MagicMock()

    assert AnthropicProvider("test-key", "claude-opus-5").model_name == "claude-opus-5"
    assert AnthropicProvider("test-key", "claude-opus-4-8").model_name == "claude-opus-4-8"


def test_opus_5_is_selectable_on_the_claude_code_side():
    """Abonelik (CLI) listesi hâlâ elle yazılı ve Opus 5 orada olmalı.

    Bu testin bulut yarısı 30 Ağu 2026'da KALDIRILDI: elle yazılı bulut
    kataloğu silindi ve liste artık sağlayıcının kendi `/v1/models`inden
    geliyor. "Katalogda şu model yazıyor" diye bir iddia artık ölçülebilir
    bir şey söylemiyor — o sözleşmenin yerini
    `test_available_models_merge.py` aldı.

    CLI tarafında listeleme yolu YOK (Claude Code'un `--help`inde model
    listeleyen alt komut yok, ölçüldü 30 Ağu 2026), o yüzden orası elle
    yazılı kalıyor ve bu test hâlâ bir şey koruyor.
    """
    router = create_config_router(MagicMock())
    route = next(route for route in router.routes if route.path == "/available-models")
    catalog = asyncio.run(route.endpoint())

    subscription = {model["id"]: model for model in catalog["subscription"]}

    assert "claude-opus-5" in subscription
    assert "claude-opus-4-8" in subscription
    assert subscription["claude-opus-5"]["provider"] == "subscription"
