"""Regression test for the `unpinned-transitive-dependency` finding class.

Measured 3 Sep 2026: `vosk==0.3.45` was pinned together with its direct runtime
dependencies, but `tqdm`'s own Windows-only dependency `colorama` was not. An
unpinned name still enters the frozen installer, so its version could move with
no diff in this repository at all.

The walk is deliberately metadata-only: no network, no pip, no resolver. It reads
the distributions already installed in the venv, which is the same set PyInstaller
freezes -- asking the index instead would test the index, not the build.
"""

import re
from importlib import metadata
from pathlib import Path

import pytest

REQUIREMENTS = Path(__file__).resolve().parents[1] / "requirements.txt"

# Both are walked because the two installers are built on different machines and
# a marker-gated dependency is invisible from the other side.
ENVIRONMENTS = (
    {"platform_system": "Windows", "sys_platform": "win32"},
    {"platform_system": "Darwin", "sys_platform": "darwin"},
)

# If the walk ever breaks (renamed metadata key, missing dist-info) it would reach
# nothing and the test would pass while measuring nothing.
ANCHORS = {"vosk", "srt", "tqdm", "colorama"}


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _requirement_parser():
    try:
        from packaging.requirements import Requirement
    except ImportError:  # pragma: no cover - packaging ships with the venv
        pytest.skip("packaging is not importable; cannot parse requirement markers")
    return Requirement


def reachable_distributions(Requirement) -> set[str]:
    """Names reachable from `vosk` through installed metadata, on either OS."""
    queue = ["vosk"]
    seen: set[str] = set()
    reached: set[str] = set()
    while queue:
        name = queue.pop()
        key = normalize(name)
        if key in seen:
            continue
        seen.add(key)
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            # A declared dependency that is not installed cannot be walked further,
            # but it is still part of the closure and must be pinned.
            continue
        reached.add(key)
        for raw in dist.requires or ():
            dep = Requirement(raw)
            marker = dep.marker
            # `extra == "..."` gates optional extras; nothing installs them here.
            if marker is not None and "extra ==" in str(marker):
                continue
            if marker is not None and not any(marker.evaluate(env) for env in ENVIRONMENTS):
                continue
            reached.add(normalize(dep.name))
            queue.append(dep.name)
    return reached


def exact_pins(Requirement) -> set[str]:
    """Names carrying an exact `name==version` pin in requirements.txt."""
    pinned: set[str] = set()
    for raw in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        req = Requirement(line)
        specs = list(req.specifier)
        if len(specs) == 1 and specs[0].operator == "==":
            pinned.add(normalize(req.name))
    return pinned


def test_vosk_runtime_closure_is_fully_pinned():
    try:
        metadata.distribution("vosk")
    except metadata.PackageNotFoundError:
        pytest.skip("vosk is not installed in this interpreter; closure cannot be walked")

    Requirement = _requirement_parser()
    reached = reachable_distributions(Requirement)

    assert ANCHORS <= reached, (
        "the dependency walk did not reach the known Vosk runtime names "
        f"{sorted(ANCHORS - reached)} -- the test would otherwise pass vacuously"
    )

    missing = sorted(reached - exact_pins(Requirement))
    assert not missing, (
        "Vosk runtime dependencies without an exact `name==version` pin in "
        f"Backend/requirements.txt: {missing}"
    )
