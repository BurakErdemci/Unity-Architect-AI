"""
Read/write classification for MCP tool calls, backed by ``tool_actions.json``.

The approval gate needs one answer per call: does this mutate anything? Tool
names alone cannot answer it -- most tools switch between reading and writing on
their ``action`` parameter, and four ``manage_build`` actions switch on a
*sibling* parameter instead. This module is the only place that decides.

Two properties are load-bearing:

* **Fail-closed.** Anything not positively proven to be a read is a write, so an
  unrecognised tool or action produces an approval card rather than a silent
  bypass. An upstream addition degrades into an extra prompt, never into a hole.
* **Recursive.** ``batch_execute`` carries arbitrary sub-calls, so classifying
  the outer name would let a whole batch of mutations through as one opaque
  call. The batch is a read only when every command inside it is a read.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

LEDGER_PATH = Path(__file__).with_name("tool_actions.json")

READ = "read"
WRITE = "write"

# Depth limit for batch_execute nesting. A batch inside a batch inside a batch is
# not a real workflow; refusing to recurse further and returning WRITE keeps a
# hand-crafted deep payload from exhausting the stack before the gate ever runs.
_MAX_DEPTH = 8

_ledger_cache: dict[str, Any] | None = None


def load_ledger(*, refresh: bool = False) -> dict[str, Any]:
    """Load and cache the ledger. ``refresh=True`` re-reads from disk (tests)."""
    global _ledger_cache
    if _ledger_cache is None or refresh:
        with LEDGER_PATH.open(encoding="utf-8") as handle:
            _ledger_cache = json.load(handle)
    return _ledger_cache


def ledger_tool_names() -> set[str]:
    """Every tool name the ledger classifies."""
    return set(load_ledger()["tools"].keys())


def tool_entry(tool_name: str) -> dict[str, Any] | None:
    """The ledger row for a tool, or None when it is not classified."""
    return load_ledger()["tools"].get(tool_name)


def _is_read_by_param(rule: Mapping[str, Any], params: Mapping[str, Any]) -> bool:
    """Evaluate one ``param_dependent`` rule against a call's parameters."""
    param = rule["param"]
    when = rule.get("read_when", "omitted")
    if when == "omitted":
        return params.get(param) is None
    if when == "falsy":
        return not params.get(param)
    # An unknown rule kind must not silently read as a permission. Treat it as
    # "cannot prove read" so the call is gated.
    return False


def classify(tool_name: str, params: Mapping[str, Any] | None = None, *, _depth: int = 0) -> str:
    """
    Return ``"read"`` or ``"write"`` for a single tool call.

    ``"write"`` is the answer whenever the call cannot be *proven* harmless:
    unknown tool, unknown action, missing action with no declared default,
    malformed batch payload, or nesting past ``_MAX_DEPTH``.
    """
    params = params or {}
    entry = tool_entry(tool_name)
    if entry is None:
        return WRITE

    # batch_execute and anything else that carries nested calls.
    recursive_field = entry.get("recursive_field")
    if recursive_field:
        if _depth >= _MAX_DEPTH:
            return WRITE
        commands = params.get(recursive_field)
        # A non-list or empty payload proves nothing about what will run.
        if not isinstance(commands, (list, tuple)) or not commands:
            return WRITE
        tool_key = entry.get("recursive_tool_key", "tool")
        params_key = entry.get("recursive_params_key", "params")
        for command in commands:
            if not isinstance(command, Mapping):
                return WRITE
            inner_name = command.get(tool_key)
            if not isinstance(inner_name, str):
                return WRITE
            inner_params = command.get(params_key) or {}
            if not isinstance(inner_params, Mapping):
                return WRITE
            if classify(inner_name, inner_params, _depth=_depth + 1) == WRITE:
                return WRITE
        return READ

    # Tools with no action parameter are classified whole.
    tool_level = entry.get("tool_level")
    if tool_level in (READ, WRITE):
        return tool_level

    action_param = entry.get("action_param")
    if not action_param:
        return WRITE

    action = params.get(action_param)
    if action is None:
        action = entry.get("default_action")
    if not isinstance(action, str):
        return WRITE

    # Parameter-dependent actions are checked first: they appear in neither
    # read_actions nor write_actions, because the action name alone does not
    # determine the answer.
    for rule in entry.get("param_dependent", []):
        if rule.get("action") == action:
            return READ if _is_read_by_param(rule, params) else WRITE

    if action in entry.get("read_actions", []):
        return READ
    if action in entry.get("write_actions", []):
        return WRITE
    return WRITE


def is_read_only(tool_name: str, params: Mapping[str, Any] | None = None) -> bool:
    """Convenience wrapper for gate code that only wants a boolean."""
    return classify(tool_name, params) == READ


def _self_check() -> list[str]:
    """
    Internal consistency of the ledger itself, independent of the live registry.

    The registry cross-check (does every registered tool appear here, and does
    every declared action still exist upstream) lives in
    ``tests/test_tool_actions_ledger.py`` because it needs to import the tools.
    """
    problems: list[str] = []
    ledger = load_ledger(refresh=True)
    for name, entry in ledger["tools"].items():
        reads = set(entry.get("read_actions", []))
        writes = set(entry.get("write_actions", []))
        overlap = reads & writes
        if overlap:
            problems.append(f"{name}: action in both read and write: {sorted(overlap)}")

        has_actions = bool(reads or writes or entry.get("param_dependent"))
        if entry.get("action_param") and not has_actions:
            problems.append(f"{name}: declares action_param but classifies no actions")
        if not entry.get("action_param") and entry.get("tool_level") not in (READ, WRITE):
            problems.append(f"{name}: no action_param and no tool_level -- unclassifiable")
        if entry.get("action_param") and entry.get("tool_level") is not None:
            problems.append(f"{name}: has both action_param and tool_level -- ambiguous")

        for rule in entry.get("param_dependent", []):
            action = rule.get("action")
            if action in reads or action in writes:
                problems.append(
                    f"{name}: '{action}' is param-dependent but also listed as a fixed action"
                )
            if rule.get("read_when") not in ("omitted", "falsy"):
                problems.append(f"{name}: '{action}' has unsupported read_when {rule.get('read_when')!r}")

        default_action = entry.get("default_action")
        if default_action is not None and default_action not in reads | writes:
            problems.append(f"{name}: default_action '{default_action}' is not a declared action")

        if not entry.get("evidence"):
            problems.append(f"{name}: no evidence reference")
    return problems
