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


def _action_list(entry: Mapping[str, Any], key: str) -> tuple[str, ...]:
    """
    An action list from the ledger, or empty when the row is the wrong shape.

    ``action in entry["read_actions"]`` reads naturally and is a trap: if that
    field is a plain string instead of a list, ``in`` silently becomes a
    SUBSTRING test, so ``"list_packages"`` exempts the actions ``"list"``,
    ``"list_p"`` and even ``"s"``. Measured 2026-07-29 during an external audit
    of the ledger's trust assumptions. The ledger is hand-edited data granting
    exemptions from a security gate, so a wrong shape has to land on the write
    side rather than becoming a wildcard.
    """
    value = entry.get(key)
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _normalize_key(key: str) -> str:
    """``autoRepair`` -> ``auto_repair``, mirroring the server's own normaliser."""
    out: list[str] = []
    for index, char in enumerate(key):
        if char.isupper():
            if index:
                out.append("_")
            out.append(char.lower())
        else:
            out.append(char)
    return "".join(out)


def _param_value(params: Mapping[str, Any], param: str) -> Any:
    """
    The value of ``param`` under ANY spelling the server would accept.

    The gate classifies the payload as the model sent it, but
    ``ParamNormalizerMiddleware`` converts camelCase to snake_case before
    FastMCP ever validates it - so the server and this classifier were looking
    at two different key sets. An exact-key lookup therefore misses
    ``autoRepair`` while the C# side happily reads it, and a missing key is the
    READ side of every rule we have: a pure spelling change turned a gated call
    into an exempt one. Found by an external audit 2026-07-29 on
    ``manage_scene validate autoRepair=true``, which reached ValidateScene(true).
    That particular row is gone (manage_scene is now write throughout), but the
    mechanism was not, and it would have come back with the next multi-word
    pivot parameter.

    Any spelling that carries a value wins, because "cannot prove absent" must
    land on the write side.
    """
    if params.get(param) is not None:
        return params[param]
    target = _normalize_key(param)
    for key, value in params.items():
        if isinstance(key, str) and value is not None and _normalize_key(key) == target:
            return value
    return None


def _is_read_by_param(rule: Mapping[str, Any], params: Mapping[str, Any]) -> bool:
    """Evaluate one ``param_dependent`` rule against a call's parameters."""
    param = rule.get("param")
    if not isinstance(param, str) or not param:
        # A rule with no usable pivot cannot prove anything.
        return False
    when = rule.get("read_when", "omitted")
    value = _param_value(params, param)
    if when == "omitted":
        return value is None
    if when == "falsy":
        return not value
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

    if action in _action_list(entry, "read_actions"):
        return READ
    if action in _action_list(entry, "write_actions"):
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
        # Shape first. classify() already fails closed on a wrong shape, but a
        # silently degraded row is a ledger nobody notices is broken - and the
        # string-instead-of-list case turns membership into a substring match.
        for key in ("read_actions", "write_actions"):
            value = entry.get(key, [])
            if not isinstance(value, (list, tuple)):
                problems.append(
                    f"{name}: {key} is {type(value).__name__}, expected a list -- "
                    "membership would degrade to a substring test"
                )
            elif any(not isinstance(item, str) for item in value):
                problems.append(f"{name}: {key} contains a non-string entry")
        for rule in entry.get("param_dependent", []):
            if not isinstance(rule.get("param"), str) or not rule.get("param"):
                problems.append(f"{name}: a param_dependent rule has no usable 'param'")

        reads = set(_action_list(entry, "read_actions"))
        writes = set(_action_list(entry, "write_actions"))
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
