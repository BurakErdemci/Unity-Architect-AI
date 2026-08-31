"""Enforce that `app/workspace_fingerprint.py` imports only the standard library.

Why this test exists (AUDIT R6-02, 31 Aug 2026): the module's own docstring
says nothing may be imported there beyond the standard library, because the
cross-language parity test (`Frontend/frontend/__tests__/workspace-fingerprint-parity.test.ts`)
must be able to run it on a bare interpreter with no virtualenv. That
constraint was documented but NOT enforced anywhere — no test failed if
someone added an import tomorrow. The frontend CI job only catches an import
that is *unavailable* on the runner's Python; it would not catch an import
that is merely non-stdlib-but-installed, nor a repo-local module, since both
of those could still resolve inside the backend's own virtualenv where this
suite runs.

The module is parsed with `ast`, not imported: importing it proves nothing
about what a bare interpreter without extra packages would do, and the
whole point of the constraint is the bare-interpreter case.
"""

import ast
import sys
from pathlib import Path

_MODULE_PATH = (
    Path(__file__).resolve().parent.parent / "app" / "workspace_fingerprint.py"
)


def find_non_stdlib_imports(source: str) -> list[str]:
    """Parse `source` and return a violation message per disallowed import.

    Walks every `ast.Import` and `ast.ImportFrom` node found anywhere in the
    tree via `ast.walk` (not just `tree.body`), so an import nested inside a
    function or a `try:` block is still caught. A relative import
    (`ImportFrom` with `level > 0`) is always a violation: it is repo-local
    by definition, which defeats the whole point of a bare-interpreter test.
    Every other import's top-level module name (e.g. `os.path` -> `os`,
    `from x.y import z` -> `x`) must appear in `sys.stdlib_module_names` —
    the interpreter's own answer for what is standard library, so there is
    no hand-maintained allowlist to go stale.
    """
    tree = ast.parse(source)
    violations: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top_level = alias.name.split(".")[0]
                if top_level not in sys.stdlib_module_names:
                    violations.append(_violation_message(top_level))
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                violations.append(
                    "relative import (level={}) from {!r}: a relative import "
                    "is repo-local by definition and defeats the whole point "
                    "of the bare-interpreter guarantee".format(
                        node.level, node.module
                    )
                )
                continue
            top_level = (node.module or "").split(".")[0]
            if top_level and top_level not in sys.stdlib_module_names:
                violations.append(_violation_message(top_level))

    return violations


def _violation_message(module_name: str) -> str:
    return (
        "non-stdlib import {!r} in workspace_fingerprint.py: the parity "
        "test in Frontend/frontend/__tests__/workspace-fingerprint-parity.test.ts "
        "runs this module through a bare interpreter, so this import makes "
        "that suite fail on any machine and in CI where {!r} is not "
        "installed. This module was split out of "
        "Backend/app/routes/auth_routes.py (which imports FastAPI) "
        "precisely to avoid that.".format(module_name, module_name)
    )


def test_workspace_fingerprint_module_is_stdlib_only():
    source = _MODULE_PATH.read_text(encoding="utf-8")

    violations = find_non_stdlib_imports(source)

    assert violations == [], (
        "workspace_fingerprint.py must import only the standard library "
        "(see its module docstring); found violations:\n"
        + "\n".join(violations)
    )


def test_guard_actually_catches_a_non_stdlib_and_a_relative_import():
    """Prove the guard can fire — a guard nobody has seen fail is not known to work."""
    synthetic_source = (
        "import os\n"
        "import fastapi\n"
        "from . import sibling\n"
        "from typing import Any\n"
    )

    violations = find_non_stdlib_imports(synthetic_source)

    assert any("fastapi" in v for v in violations), (
        "expected the guard to flag the non-stdlib `import fastapi`, "
        "got: {}".format(violations)
    )
    assert any("relative import" in v for v in violations), (
        "expected the guard to flag the relative `from . import sibling`, "
        "got: {}".format(violations)
    )
    # `os` and `typing` are stdlib and must not be reported.
    assert not any("'os'" in v for v in violations)
    assert not any("'typing'" in v for v in violations)
