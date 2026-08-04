from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from services.tools.manage_input import (
    manage_input,
    ALL_ACTIONS,
    INSPECTION_ACTIONS,
    KEYBOARD_ACTIONS,
    POINTER_ACTIONS,
    GAMEPAD_ACTIONS,
    UI_ACTIONS,
    COMPOSITE_ACTIONS,
    LIFECYCLE_ACTIONS,
)


@pytest.fixture
def mock_unity(monkeypatch):
    """Patch Unity transport layer and return captured call dict."""
    captured: dict[str, object] = {}

    async def fake_send(send_fn, unity_instance, tool_name, params):
        captured["unity_instance"] = unity_instance
        captured["tool_name"] = tool_name
        captured["params"] = params
        return {"success": True, "message": "ok"}

    monkeypatch.setattr(
        "services.tools.manage_input.get_unity_instance_from_context",
        AsyncMock(return_value="unity-instance-1"),
    )
    monkeypatch.setattr(
        "services.tools.manage_input.send_with_unity_instance",
        fake_send,
    )
    return captured


# ---------------------------------------------------------------------------
# Action list completeness
# ---------------------------------------------------------------------------

def test_all_actions_is_union_of_sub_lists():
    expected = set(
        INSPECTION_ACTIONS + KEYBOARD_ACTIONS + POINTER_ACTIONS
        + GAMEPAD_ACTIONS + UI_ACTIONS + COMPOSITE_ACTIONS + LIFECYCLE_ACTIONS
    )
    assert set(ALL_ACTIONS) == expected


def test_no_duplicate_actions():
    assert len(ALL_ACTIONS) == len(set(ALL_ACTIONS))


def test_all_actions_count():
    assert len(ALL_ACTIONS) == 9


# ---------------------------------------------------------------------------
# Invalid / missing action
# ---------------------------------------------------------------------------

def test_unknown_action_returns_error(mock_unity):
    result = asyncio.run(
        manage_input(SimpleNamespace(), action="press_any_key")
    )
    assert result["success"] is False
    assert "Unknown action" in result["message"]
    # Unity'ye HİÇ gidilmemeli: geçersiz eylem köprüyü meşgul etmemeli.
    assert "tool_name" not in mock_unity


def test_empty_action_returns_error(mock_unity):
    result = asyncio.run(manage_input(SimpleNamespace(), action=""))
    assert result["success"] is False
    assert "tool_name" not in mock_unity


def test_action_is_case_insensitive(mock_unity):
    result = asyncio.run(manage_input(SimpleNamespace(), action="DESCRIBE"))
    assert result["success"] is True
    assert mock_unity["params"]["action"] == "describe"


# ---------------------------------------------------------------------------
# Routing: every declared action must reach Unity under the right tool name
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("action", ALL_ACTIONS)
def test_every_declared_action_reaches_unity(mock_unity, action):
    result = asyncio.run(manage_input(SimpleNamespace(), action=action))
    assert result["success"] is True
    assert mock_unity["tool_name"] == "manage_input"
    assert mock_unity["params"]["action"] == action


# ---------------------------------------------------------------------------
# Parameter forwarding
# ---------------------------------------------------------------------------

def test_key_properties_are_forwarded_verbatim(mock_unity):
    props = {"key": "W", "state": "down"}
    result = asyncio.run(
        manage_input(SimpleNamespace(), action="key", properties=props)
    )
    assert result["success"] is True
    assert mock_unity["params"]["properties"] == props


def test_ui_click_forwards_target(mock_unity):
    asyncio.run(
        manage_input(SimpleNamespace(), action="ui_click", target="Canvas/StartButton")
    )
    assert mock_unity["params"]["target"] == "Canvas/StartButton"


def test_omitted_optionals_are_not_sent(mock_unity):
    """Boş alan göndermek C# tarafında 'verildi ama boş' ile 'hiç verilmedi'yi
    ayırt edilemez yapardı; ikisi farklı davranışlar."""
    asyncio.run(manage_input(SimpleNamespace(), action="describe"))
    assert "properties" not in mock_unity["params"]
    assert "target" not in mock_unity["params"]


def test_sequence_steps_survive_nesting(mock_unity):
    steps = {
        "steps": [
            {"type": "key", "key": "W", "state": "down"},
            {"type": "wait", "ms": 2000},
            {"type": "key", "key": "W", "state": "up"},
        ]
    }
    asyncio.run(
        manage_input(SimpleNamespace(), action="sequence", properties=steps)
    )
    forwarded = mock_unity["params"]["properties"]["steps"]
    assert len(forwarded) == 3
    assert forwarded[1]["ms"] == 2000


def test_properties_accepts_json_string(mock_unity):
    """Bazı istemciler dict yerine JSON dizesi gönderiyor; araç bunu C# tarafına
    olduğu gibi geçirmeli (çözümleme orada yapılıyor)."""
    asyncio.run(
        manage_input(SimpleNamespace(), action="key", properties='{"key": "Space"}')
    )
    assert mock_unity["params"]["properties"] == '{"key": "Space"}'


def test_non_dict_unity_response_is_wrapped(monkeypatch):
    async def fake_send(send_fn, unity_instance, tool_name, params):
        return "connection lost"

    monkeypatch.setattr(
        "services.tools.manage_input.get_unity_instance_from_context",
        AsyncMock(return_value="unity-instance-1"),
    )
    monkeypatch.setattr(
        "services.tools.manage_input.send_with_unity_instance", fake_send
    )

    result = asyncio.run(manage_input(SimpleNamespace(), action="describe"))
    assert result["success"] is False
    assert "connection lost" in result["message"]
