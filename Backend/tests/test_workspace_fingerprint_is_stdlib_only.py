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

    Also walks every `ast.Call` node for the ordinary dynamic-import
    spellings that a syntactic `Import`/`ImportFrom` check cannot see:
    `__import__(...)`, `importlib.import_module(...)`, and the direct-import
    sibling `import_module(...)` reached via
    `from importlib import import_module`. See AUDIT R8-02 and R9-03
    (31 Aug 2026) below for why this matters and why parts of it were
    missing.
    """
    tree = ast.parse(source)
    violations: list[str] = []
    import_module_aliases = _collect_import_module_aliases(tree)

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
        elif isinstance(node, ast.Call):
            violation = _check_dynamic_import_call(node, import_module_aliases)
            if violation is not None:
                violations.append(violation)

    return violations


def _collect_import_module_aliases(tree: ast.AST) -> set[str]:
    """Return local names bound to `importlib.import_module` via
    `from importlib import import_module as <alias>`.

    AUDIT R9-03 (31 Aug 2026): the previous round only recognised a bare
    `ast.Name` callee named `__import__` and an `ast.Attribute` callee named
    `import_module` (i.e. `importlib.import_module(...)`). It missed the
    ordinary direct-import sibling `from importlib import import_module` /
    `import_module(...)`, where the callee is an `ast.Name` named
    `import_module`, not an `Attribute` — the same "sibling call site"
    pattern as R8-02: the earlier repair covered the shapes it was told
    about and left the third on the old rule. The bare (unaliased) name is
    handled unconditionally in `_is_dynamic_import_call` below; this
    function additionally resolves an *aliased* import
    (`import_module as im`) because, unlike a general alias, that alias
    name is knowable statically straight off the `ImportFrom` node.

    NOT handled, and left as a documented gap rather than a silent one: a
    name bound to `importlib.import_module` by a plain assignment (e.g.
    `im = importlib.import_module`) instead of an import statement. That
    would require dataflow analysis this syntactic, AST-shape-based guard
    does not attempt.
    """
    aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "importlib":
            for alias in node.names:
                if alias.name == "import_module" and alias.asname:
                    aliases.add(alias.asname)
    return aliases


def _is_dynamic_import_call(node: ast.Call, import_module_aliases: set[str]) -> bool:
    """True if `node` calls `__import__(...)`, `<x>.import_module(...)`,
    the bare `import_module(...)` reached via
    `from importlib import import_module`, or one of its aliased forms.

    The `__import__` check matches a bare `ast.Name` callee by id. The
    `importlib.import_module` check matches on the attribute name alone
    (not on the value being literally `importlib`), because the module
    could be imported under an alias — matching the attribute name is the
    robust part, per AUDIT R8-02. The bare-name `import_module` check is
    the same idea applied to the direct-import sibling, per AUDIT R9-03:
    it matches on the name alone, so it also covers a re-export or a
    `from x import import_module` where `x` merely re-exports importlib's
    function under that name, not only the literal
    `from importlib import import_module`.
    """
    func = node.func
    if isinstance(func, ast.Name) and func.id == "__import__":
        return True
    if isinstance(func, ast.Name) and (
        func.id == "import_module" or func.id in import_module_aliases
    ):
        return True
    if isinstance(func, ast.Attribute) and func.attr == "import_module":
        return True
    return False


def _check_dynamic_import_call(
    node: ast.Call, import_module_aliases: set[str]
) -> str | None:
    """Return a violation message for a dynamic-import call, or None.

    AUDIT R8-02 (31 Aug 2026): `find_non_stdlib_imports` originally only
    recognised `ast.Import` and `ast.ImportFrom`, so `__import__('fastapi')`
    and `importlib.import_module('fastapi')` slipped straight through even
    though the test's own title claims to enforce "stdlib only" — the
    recurring defect class in this repository, where a test's name promises
    more than its implementation checks. Found by the auditor's probe, which
    got `[]` from the old helper for both call shapes. AUDIT R9-03
    (31 Aug 2026): the direct-import sibling `from importlib import
    import_module` / `import_module('fastapi')` slipped through the same
    way, for the same reason — see `_is_dynamic_import_call` above.
    """
    if not _is_dynamic_import_call(node, import_module_aliases):
        return None

    if not node.args:
        return None

    first_arg = node.args[0]
    if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
        top_level = first_arg.value.split(".")[0]
        if top_level and top_level not in sys.stdlib_module_names:
            return _violation_message(top_level)
        return None

    # The module name is not a string literal (a variable, an f-string, a
    # concatenation, ...) so it cannot be resolved statically. Report it as
    # its own violation kind: an undecidable dynamic import in this module
    # defeats the bare-interpreter guarantee just as surely as a known
    # non-stdlib one would, because nobody can prove at review time what it
    # will import at runtime.
    return (
        "undecidable dynamic import in workspace_fingerprint.py: the "
        "module name passed to {!r} is not a string literal, so it cannot "
        "be checked against the standard library at all. The parity test "
        "in Frontend/frontend/__tests__/workspace-fingerprint-parity.test.ts "
        "runs this module through a bare interpreter with no dependencies "
        "installed, so an unresolvable dynamic import defeats that "
        "guarantee outright. This module was split out of "
        "Backend/app/routes/auth_routes.py (which imports FastAPI) "
        "precisely to keep it importable with no dependencies.".format(
            ast.dump(node.func)
        )
    )


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


def test_guard_catches_dynamic_import_forms():
    """AUDIT R8-02: `__import__` and `importlib.import_module` slip past a
    guard that only recognises `ast.Import`/`ast.ImportFrom`. Prove the
    extended guard catches both spellings, still catches the undecidable
    case, and still lets a stdlib dynamic import through as legal.

    AUDIT R9-03: also prove the guard catches the direct-import sibling
    `from importlib import import_module` / `import_module(...)`, that it
    still lets a stdlib dynamic import through that way too, and that it
    catches the aliased form `import_module as im`.
    """
    dunder_import_source = "__import__('fastapi')\n"
    violations = find_non_stdlib_imports(dunder_import_source)
    assert any("fastapi" in v for v in violations), (
        "expected the guard to flag `__import__('fastapi')`, "
        "got: {}".format(violations)
    )

    import_module_source = "import importlib\nimportlib.import_module('fastapi')\n"
    violations = find_non_stdlib_imports(import_module_source)
    assert any("fastapi" in v for v in violations), (
        "expected the guard to flag `importlib.import_module('fastapi')`, "
        "got: {}".format(violations)
    )

    undecidable_source = (
        "import importlib\n"
        "name = 'fastapi'\n"
        "importlib.import_module(name)\n"
    )
    violations = find_non_stdlib_imports(undecidable_source)
    assert any("undecidable dynamic import" in v for v in violations), (
        "expected a non-literal `importlib.import_module(name)` to be "
        "flagged as undecidable, got: {}".format(violations)
    )

    stdlib_dunder_import_source = "__import__('os')\n"
    violations = find_non_stdlib_imports(stdlib_dunder_import_source)
    assert not any("__import__" in v or "'os'" in v for v in violations), (
        "a stdlib dynamic import like `__import__('os')` must stay legal, "
        "otherwise the guard is just noise; got: {}".format(violations)
    )

    # AUDIT R9-03: the direct-import sibling of `importlib.import_module`.
    direct_import_module_source = (
        "from importlib import import_module\nimport_module('fastapi')\n"
    )
    violations = find_non_stdlib_imports(direct_import_module_source)
    assert any("fastapi" in v for v in violations), (
        "expected the guard to flag `import_module('fastapi')` reached via "
        "`from importlib import import_module`, got: {}".format(violations)
    )

    stdlib_direct_import_module_source = (
        "from importlib import import_module\nimport_module('os')\n"
    )
    violations = find_non_stdlib_imports(stdlib_direct_import_module_source)
    assert not any("'os'" in v for v in violations), (
        "a stdlib dynamic import via the direct-import sibling, "
        "`import_module('os')`, must stay legal; got: {}".format(violations)
    )

    aliased_import_module_source = (
        "from importlib import import_module as im\nim('fastapi')\n"
    )
    violations = find_non_stdlib_imports(aliased_import_module_source)
    assert any("fastapi" in v for v in violations), (
        "expected the guard to flag `im('fastapi')` where `im` is bound by "
        "`from importlib import import_module as im`, got: {}".format(
            violations
        )
    )
