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


def test_opus_5_is_additive_in_api_and_claude_code_catalogs():
    router = create_config_router(MagicMock())
    route = next(route for route in router.routes if route.path == "/available-models")
    catalog = asyncio.run(route.endpoint())

    cloud = {model["id"]: model for model in catalog["cloud"]}
    subscription = {model["id"]: model for model in catalog["subscription"]}

    assert "claude-opus-5" in cloud
    assert "claude-opus-4-8" in cloud
    assert cloud["claude-opus-5"]["provider"] == "anthropic"
    assert "openrouter_id" not in cloud["claude-opus-5"]

    assert "claude-opus-5" in subscription
    assert "claude-opus-4-8" in subscription
    assert subscription["claude-opus-5"]["provider"] == "subscription"
