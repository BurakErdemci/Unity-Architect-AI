"""
Keeps ``services/registry/tool_actions.json`` honest against the live tool surface.

The ledger tells the approval gate which calls mutate Unity. A ledger that
silently drifts from the code is worse than no ledger: the gate keeps answering
confidently with stale data. Every check here exists because drift in that
direction is invisible at runtime -- a tool added upstream simply stops being
classified, and nothing complains.

The dead-entry check (``test_no_dead_ledger_entries``) is not hypothetical. The
Backend gate exempts ``manage_scene`` action ``get_info``, an action that does
not exist and never has, so that exemption has never matched anything. This test
makes that class of mistake a red build.
"""
import inspect
import sys
import typing
from pathlib import Path

import pytest

from services.registry import get_registered_tools
from services.registry.tool_actions import (
    READ,
    WRITE,
    classify,
    ledger_tool_names,
    load_ledger,
    tool_entry,
    _self_check,
)
from utils.module_discovery import discover_modules

# Tools whose action list cannot be read out of the source automatically: the
# action parameter is free text and the module exposes no single ALL_ACTIONS
# constant. Frozen on purpose -- if a tool gains or loses a closed action set,
# this list stops matching and the test says so, instead of quietly checking
# fewer tools than it used to.
#
# Currently empty: every action-taking tool declares either a Literal or an
# enforced ALL_ACTIONS, so all 45 are cross-checked. Keeping the mechanism (and
# this comment) means the day one of them goes free-text, the test demands an
# explicit decision instead of silently skipping it.
UNVERIFIABLE_ACTION_SETS: set[str] = set()


@pytest.fixture(scope="module", autouse=True)
def _load_all_tools():
    """Import every tool module so the decorators populate the registry."""
    tools_dir = Path(__file__).parent.parent / "src" / "services" / "tools"
    list(discover_modules(tools_dir, "services.tools"))


def _registered() -> dict[str, dict]:
    return {tool["name"]: tool for tool in get_registered_tools()}


def _literal_members(annotation) -> set[str] | None:
    """
    Pull the members out of a Literal, however it is wrapped.

    Tools declare the action parameter in three different shapes across this
    codebase -- ``Annotated[Literal[...], "doc"]``,
    ``Optional[Annotated[Literal[...], "doc"]]`` and a named Literal alias --
    so the unwrapping has to survive Union and Annotated layers in any order.
    Handling only the first shape silently skipped two tools when this test was
    first written, which is the same "checks less than it appears to" failure
    the test exists to prevent.
    """
    seen = 0
    while seen < 8:
        seen += 1
        origin = typing.get_origin(annotation)
        if origin is typing.Literal:
            return {member for member in typing.get_args(annotation) if isinstance(member, str)}
        if origin is typing.Annotated or hasattr(annotation, "__metadata__"):
            annotation = typing.get_args(annotation)[0]
            continue
        if origin is typing.Union:
            candidates = [arg for arg in typing.get_args(annotation) if arg is not type(None)]
            if len(candidates) != 1:
                return None
            annotation = candidates[0]
            continue
        return None
    return None


def _closed_action_set(tool_name: str, tool_info: dict) -> set[str] | None:
    """
    The exhaustive action set declared by the source, or None if it is not
    machine-readable. Two shapes are supported: a Literal on the action
    parameter, and a module-level ALL_ACTIONS constant enforced at call time.
    """
    entry = tool_entry(tool_name) or {}
    action_param = entry.get("action_param")
    if not action_param:
        return None

    func = tool_info["func"]
    try:
        hints = typing.get_type_hints(func, include_extras=True)
    except Exception:
        hints = {}
    annotation = hints.get(action_param, inspect.Parameter.empty)

    literal_members = _literal_members(annotation)
    if literal_members is not None:
        return literal_members

    module = sys.modules.get(func.__module__)
    all_actions = getattr(module, "ALL_ACTIONS", None)
    if isinstance(all_actions, (list, tuple, set, frozenset)):
        return set(all_actions)
    return None


def _ledger_actions(tool_name: str) -> set[str]:
    entry = tool_entry(tool_name) or {}
    actions = set(entry.get("read_actions", [])) | set(entry.get("write_actions", []))
    actions |= {rule["action"] for rule in entry.get("param_dependent", [])}
    return actions


def test_ledger_is_self_consistent():
    assert _self_check() == []


def test_every_registered_tool_is_classified():
    missing = sorted(set(_registered()) - ledger_tool_names())
    assert not missing, (
        f"Tools reachable through MCP but absent from tool_actions.json: {missing}. "
        "They currently classify as 'write' (fail-closed), so the gate will card them, "
        "but the classification is a guess until it is written down."
    )


def test_no_dead_ledger_entries():
    stale = sorted(ledger_tool_names() - set(_registered()))
    assert not stale, (
        f"tool_actions.json classifies tools that are no longer registered: {stale}. "
        "A rule that can never match reads as protection while providing none."
    )


@pytest.mark.parametrize("tool_name", sorted(ledger_tool_names()))
def test_declared_actions_match_source(tool_name):
    tool_info = _registered().get(tool_name)
    if tool_info is None:
        pytest.skip("covered by test_no_dead_ledger_entries")

    source_actions = _closed_action_set(tool_name, tool_info)
    if source_actions is None:
        assert tool_name in UNVERIFIABLE_ACTION_SETS or not (tool_entry(tool_name) or {}).get("action_param"), (
            f"{tool_name} declares an action_param but no closed action set could be read "
            "from the source, and it is not on the frozen UNVERIFIABLE_ACTION_SETS list."
        )
        return

    assert tool_name not in UNVERIFIABLE_ACTION_SETS, (
        f"{tool_name} now exposes a machine-readable action set; remove it from "
        "UNVERIFIABLE_ACTION_SETS so it gets checked."
    )

    ledger_actions = _ledger_actions(tool_name)
    unclassified = sorted(source_actions - ledger_actions)
    invented = sorted(ledger_actions - source_actions)
    assert not unclassified, (
        f"{tool_name}: actions exist in the source but are unclassified: {unclassified}"
    )
    assert not invented, (
        f"{tool_name}: ledger classifies actions the source does not accept: {invented}"
    )


def test_unknown_tool_is_treated_as_a_mutation():
    assert classify("mcp__something__brand_new", {"action": "get"}) == WRITE


def test_unknown_action_is_treated_as_a_mutation():
    assert classify("manage_scene", {"action": "teleport_everything"}) == WRITE


def test_missing_action_without_default_is_treated_as_a_mutation():
    assert classify("manage_scene", {}) == WRITE


def test_declared_default_action_is_applied():
    # read_console defaults to "get" when action is omitted (read_console.py:52).
    assert classify("read_console", {}) == READ
    assert classify("read_console", {"action": "clear"}) == WRITE


def test_param_dependent_action_flips_on_a_sibling_parameter():
    # manage_build settings: reading a PlayerSettings property vs writing one.
    assert classify("manage_build", {"action": "settings", "property": "companyName"}) == READ
    assert classify("manage_build", {"action": "settings", "property": "companyName", "value": "x"}) == WRITE
    # manage_scene validate: report vs repair.
    assert classify("manage_scene", {"action": "validate"}) == READ
    assert classify("manage_scene", {"action": "validate", "auto_repair": True}) == WRITE


def test_batch_execute_is_a_write_when_any_inner_call_writes():
    reads_only = {"commands": [
        {"tool": "manage_scene", "params": {"action": "get_hierarchy"}},
        {"tool": "read_console", "params": {"action": "get"}},
    ]}
    assert classify("batch_execute", reads_only) == READ

    one_write = {"commands": [
        {"tool": "manage_scene", "params": {"action": "get_hierarchy"}},
        {"tool": "manage_gameobject", "params": {"action": "delete"}},
    ]}
    assert classify("batch_execute", one_write) == WRITE


def test_batch_execute_rejects_payloads_it_cannot_read():
    assert classify("batch_execute", {}) == WRITE
    assert classify("batch_execute", {"commands": []}) == WRITE
    assert classify("batch_execute", {"commands": "not-a-list"}) == WRITE
    assert classify("batch_execute", {"commands": [{"no_tool_key": 1}]}) == WRITE


def test_batch_execute_recursion_is_bounded():
    payload = {"tool": "manage_scene", "params": {"action": "get_hierarchy"}}
    for _ in range(12):
        payload = {"tool": "batch_execute", "params": {"commands": [payload]}}
    # Deeper than the recursion budget: refused rather than resolved.
    assert classify("batch_execute", payload["params"]) == WRITE


def test_execute_code_is_never_read_regardless_of_safety_checks():
    # safety_checks is model-settable and therefore not a gate input.
    assert classify("execute_code", {"action": "execute", "safety_checks": True}) == WRITE
    assert classify("execute_code", {"action": "execute", "safety_checks": False}) == WRITE
    assert classify("execute_code", {"action": "replay"}) == WRITE
    assert classify("execute_code", {"action": "get_history"}) == READ


def test_every_ledger_entry_cites_evidence():
    for name, entry in load_ledger()["tools"].items():
        assert entry.get("evidence"), f"{name} has no evidence reference"
