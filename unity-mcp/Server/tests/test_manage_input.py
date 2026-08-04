from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from services.tools.manage_input import (
    manage_input,
    ALL_ACTIONS,
    MAX_SEQUENCE_SECONDS,
    SEQUENCE_TIMEOUT_SECONDS,
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


# ---------------------------------------------------------------------------
# Denetimden (4 Ağu 2026) terfi eden nöbetçiler.
# Bunlar bir probe'un kalıcı hâli: her biri o gün GERÇEKTEN üremiş bir arızayı
# tutuyor, "olabilir" diye yazılmış değil.
# ---------------------------------------------------------------------------

def test_forwarded_window_actually_covers_the_ceiling(mock_unity):
    """Nöbetçi, SABİTLERİ değil GÖNDERİLEN değeri ölçmeli.

    ⚠️ Doğrulama turunda ölçüldü (4 Ağu 2026): bu dosyadaki ilk hâliyle iki test,
    `timeout_seconds` iletimi TAMAMEN silindiğinde bile yeşil kalıyordu — çünkü
    biri manage_input'u hiç çağırmıyor, diğeri yalnız bir `key` çağrısında alanın
    yokluğuna bakıyordu. Bir mutasyon probe'u bunu koşturarak kanıtladı.
    Kendi kuralımı ihlal etmişim: işaretlemek ölçmek değildir.

    Bu test gerçekten çağırıyor, gönderileni okuyor ve taşımanın sabitiyle
    karşılaştırıyor — üçü birden olmadan nöbetçinin dişi olmuyor.
    """
    from transport.plugin_hub import PluginHub

    asyncio.run(
        manage_input(SimpleNamespace(), action="sequence",
                     properties={"steps": [{"type": "wait", "ms": 1000}]})
    )

    forwarded = mock_unity["params"].get("timeout_seconds")
    assert forwarded is not None, (
        "sequence çağrısı taşımaya süre talebi İLETMEDİ; varsayılan "
        f"{PluginHub.COMMAND_TIMEOUT}s sessizce uygulanır."
    )
    assert forwarded > MAX_SEQUENCE_SECONDS, (
        f"İletilen pencere {forwarded}s, tavan {MAX_SEQUENCE_SECONDS}s. "
        "Pencere tavandan büyük olmalı."
    )
    assert MAX_SEQUENCE_SECONDS < float(PluginHub.COMMAND_TIMEOUT), (
        f"Tavan {MAX_SEQUENCE_SECONDS}s, taşımanın varsayılanı "
        f"{PluginHub.COMMAND_TIMEOUT}s. Tavan varsayılanın altında kalmalı ki "
        "iletim başarısız olsa bile yetim bir Unity işi kalmasın."
    )


def test_sequence_forwards_a_timeout_request(mock_unity):
    """Dizi çağrısı taşımaya süre talebini İLETMELİ.

    `timeout_seconds` mekanizması taşımada vardı ama denetim gününe kadar hiçbir
    araç kullanmıyordu; iletilmediğinde varsayılan 30s sessizce uygulanıyordu.
    """
    asyncio.run(
        manage_input(SimpleNamespace(), action="sequence",
                     properties={"steps": [{"type": "wait", "ms": 1000}]})
    )
    assert mock_unity["params"]["timeout_seconds"] == SEQUENCE_TIMEOUT_SECONDS


def test_a_single_key_call_does_not_ask_for_the_long_window(mock_unity):
    """Tek tuşluk bir çağrı uzun pencere istememeli — istese, gerçekten asılı
    kalan bir çağrı 40 saniye boyunca fark edilmezdi.

    ⚠️ Adı bilerek daraltıldı. Önceki adı (`test_only_sequence_...`) iletimin
    KENDİSİNİ koruduğunu ima ediyordu, oysa yalnız bu tek dalı ölçüyor; iletim
    tamamen silinse bu test yine yeşil kalır. İletimi koruyan nöbetçi
    `test_forwarded_window_actually_covers_the_ceiling`.
    """
    asyncio.run(manage_input(SimpleNamespace(), action="key",
                             properties={"key": "W", "state": "down"}))
    assert "timeout_seconds" not in mock_unity["params"]


def test_declared_ceiling_matches_the_csharp_constant():
    """Python'un ilan ettiği tavan ile C#'ın uyguladığı tavan ayrışamaz.

    Ayrışırlarsa model açıklamaya güvenip 60s'lik bir dizi kurar ve C# onu
    reddeder; ya da tersi, açıklama olduğundan dar görünür. İki sabit iki ayrı
    dosyada yaşıyor ve onları bağlayan tek şey bu satır.
    """
    import pathlib
    import re

    cs = pathlib.Path(__file__).resolve().parents[2] / (
        "MCPForUnity/Editor/Tools/Input/ManageInput.cs"
    )
    if not cs.exists():
        pytest.skip(f"C# kaynağı bulunamadı: {cs}")

    match = re.search(
        r"MaxSequenceSeconds\s*=\s*([0-9]+(?:\.[0-9]+)?)", cs.read_text(encoding="utf-8")
    )
    assert match, "ManageInput.cs içinde MaxSequenceSeconds sabiti bulunamadı."
    assert float(match.group(1)) == MAX_SEQUENCE_SECONDS, (
        f"C# tavanı {match.group(1)}s, Python {MAX_SEQUENCE_SECONDS}s. "
        "İkisi aynı olmak zorunda."
    )


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
