"""`GET /health/workspace` — the answer Electron compares against its own tree.

WHICH ARIZA THIS COMES FROM
    FINDING D4-03, 31 Aug 2026. A container's bind source is fixed when the
    container is CREATED, and `restart: unless-stopped` keeps one alive across
    the shell that started it. So exporting a new `GAMACHINE_WORKSPACE` and
    relaunching Electron changed what Electron BELIEVED was mounted and nothing
    about what actually was: the app mapped project B onto `/workspace`
    successfully while the live backend read and wrote project A, both halves
    reporting success. `/health/auth` does not cover it — a shared token says
    nothing about which tree is behind the mount.

WHAT IS PINNED HERE
    The gate (a wrong token gets nothing), the exact digest for a known tree
    against an INDEPENDENTLY written expected line list rather than against the
    implementation's own helper, the two-level depth that makes sibling Unity
    projects distinguishable, the deliberate blindness inside build/cache
    directories, and that the call writes nothing into the workspace.

WHAT IS NOT PINNED
    That a matching digest means the same directory. It does not, and the
    endpoint's own docstring says so: two copies of one project hash alike.
    A digest MISMATCH is the strong half of this check; a match is weak.
"""

import hashlib
import os
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes import auth_routes

TOKEN = "workspace-identity-token-77b1"


@pytest.fixture(autouse=True)
def _real_token(monkeypatch):
    """The suite-wide conftest fixture runs this API token-less on purpose.

    This file is about the gate, so it opts back IN to a configured token —
    otherwise `_check_token` returns early for every caller and the rejection
    test would pass without a gate existing at all.
    """
    monkeypatch.delenv("UNITYAI_ALLOW_NO_TOKEN", raising=False)
    monkeypatch.setenv("LOCAL_APP_TOKEN", TOKEN)


@pytest.fixture
def client():
    """Only the auth router, so importing `main` (DB + token file) is not needed.

    That the router is actually mounted on the app, and that its gate is really
    invoked, is proven by `test_authz_matrix.py` walking the live route table.
    """
    app = FastAPI()
    app.include_router(auth_routes.create_auth_router(None))
    return TestClient(app)


def _build_tree(root, names):
    """`names` maps a relative POSIX path to None (directory) or file text."""
    for rel, content in names.items():
        target = os.path.join(root, *rel.split("/"))
        if content is None:
            os.makedirs(target, exist_ok=True)
        else:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "w", encoding="utf-8") as fh:
                fh.write(content)


PROJECT_A = {
    "Assets": None,
    "Assets/Scripts": None,
    "Assets/Art": None,
    "Packages": None,
    "Packages/manifest.json": "{}",
    "Library": None,
    "Library/junk.tmp": "x",
    "ProjectA.sln": "sln",
}

# Written out by hand from the algorithm's stated rules, NOT produced by calling
# `_fingerprint_lines`. A test that derives its expectation from the code under
# test cannot fail when that code is wrong — and the depth rule is exactly the
# part a well-meaning simplification would flatten.
#
# Order is by UTF-8 BYTES of the whole line, tab included: `Assets\td` sorts
# before `Assets/Art\td` because 0x09 < 0x2F.
EXPECTED_A_LINES = [
    "Assets\td",
    "Assets/Art\td",
    "Assets/Scripts\td",
    "Library\td",            # listed, but NOT descended into: junk.tmp is absent
    "Packages\td",
    "Packages/manifest.json\tf",
    "ProjectA.sln\tf",
]


def _digest(lines):
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def _ask(client, monkeypatch, root, token=TOKEN):
    monkeypatch.setattr(auth_routes, "CONTAINER_WORKSPACE_MOUNT", str(root))
    return client.get("/health/workspace", headers={"X-Session-Token": token})


# ── the gate ─────────────────────────────────────────────────────────────────

def test_a_wrong_token_is_refused_and_learns_nothing(client, monkeypatch, tmp_path):
    _build_tree(str(tmp_path), PROJECT_A)
    response = _ask(client, monkeypatch, tmp_path, token="not-the-token")
    assert response.status_code == 401
    # A directory listing of the developer's project is not public, so the
    # refusal must not carry the answer in its body.
    assert "fingerprint" not in response.text


def test_no_token_at_all_is_refused(client, monkeypatch, tmp_path):
    _build_tree(str(tmp_path), PROJECT_A)
    monkeypatch.setattr(auth_routes, "CONTAINER_WORKSPACE_MOUNT", str(tmp_path))
    response = client.get("/health/workspace")
    assert response.status_code == 401


# ── the answer ───────────────────────────────────────────────────────────────

def test_the_right_token_gets_the_digest_of_the_mounted_tree(client, monkeypatch, tmp_path):
    _build_tree(str(tmp_path), PROJECT_A)
    response = _ask(client, monkeypatch, tmp_path)
    assert response.status_code == 200
    body = response.json()
    assert body["mounted"] is True
    assert body["algo"] == auth_routes.WORKSPACE_FINGERPRINT_ALGO
    assert body["truncated"] is False
    assert body["entries"] == len(EXPECTED_A_LINES)
    assert body["fingerprint"] == _digest(EXPECTED_A_LINES)


def test_two_sibling_projects_do_not_share_a_digest(client, monkeypatch, tmp_path):
    """The reported failure is "project B selected, project A mounted", and both
    are Unity projects — so identical top-level names (Assets, Library,
    Packages) are the NORM. A root-only listing cannot tell them apart; the
    second level, where the user's own asset folders live, can."""
    a, b = tmp_path / "a", tmp_path / "b"
    _build_tree(str(a), PROJECT_A)
    _build_tree(str(b), {**{k: v for k, v in PROJECT_A.items()
                            if not k.startswith("Assets/")},
                         "Assets/Enemies": None,
                         "Assets/Levels": None})
    first = _ask(client, monkeypatch, a).json()
    second = _ask(client, monkeypatch, b).json()
    assert first["fingerprint"] != second["fingerprint"], \
        "two projects differing only below the root hashed the same"


def test_churn_inside_build_directories_does_not_move_the_digest(client, monkeypatch, tmp_path):
    """Deliberate blindness, and it has a reason: the Editor and the compilers
    rewrite these while the app starts, and the two sides sample the tree
    milliseconds apart — disagreement there would mean "busy", not "wrong
    tree", and would refuse a correct setup."""
    _build_tree(str(tmp_path), PROJECT_A)
    before = _ask(client, monkeypatch, tmp_path).json()["fingerprint"]
    _build_tree(str(tmp_path), {"Library/ScriptAssemblies": None,
                                "Library/another.tmp": "y"})
    after = _ask(client, monkeypatch, tmp_path).json()["fingerprint"]
    assert before == after


def test_removing_a_build_directory_is_still_visible(client, monkeypatch, tmp_path):
    """The exclusion is about DESCENDING, not about ignoring. `Library` itself
    is still an entry, so a tree that has one and a tree that does not are
    distinguishable."""
    _build_tree(str(tmp_path), PROJECT_A)
    with_library = _ask(client, monkeypatch, tmp_path).json()["fingerprint"]
    import shutil
    shutil.rmtree(os.path.join(str(tmp_path), "Library"))
    without = _ask(client, monkeypatch, tmp_path).json()["fingerprint"]
    assert with_library != without


def test_an_absent_mount_is_reported_not_raised(client, monkeypatch, tmp_path):
    """The caller has to tell "nothing mounted" from "wrong tree mounted": the
    fixes differ, and this endpoint also answers on the non-Docker path where
    there is no `/workspace` and nothing is wrong."""
    response = _ask(client, monkeypatch, tmp_path / "does-not-exist")
    assert response.status_code == 200
    body = response.json()
    assert body["mounted"] is False
    assert body["fingerprint"] == ""


def test_answering_writes_nothing_into_the_workspace(client, monkeypatch, tmp_path):
    """A Unity project reacts to new files — the Editor's asset importer picks
    them up. A marker file would be a stronger identity proof than a listing
    and is refused for exactly that reason, so the read-only property is a
    requirement and not an accident."""
    _build_tree(str(tmp_path), PROJECT_A)
    before = sorted(
        os.path.join(dirpath, name)
        for dirpath, dirnames, filenames in os.walk(str(tmp_path))
        for name in list(dirnames) + list(filenames)
    )
    assert _ask(client, monkeypatch, tmp_path).status_code == 200
    after = sorted(
        os.path.join(dirpath, name)
        for dirpath, dirnames, filenames in os.walk(str(tmp_path))
        for name in list(dirnames) + list(filenames)
    )
    assert before == after


# ── the caller ───────────────────────────────────────────────────────────────
#
# An endpoint nobody calls protects nothing, and deleting one line of the
# Electron startup path would restore FINDING D4-03 in full while every test
# above stayed green. These are TEXTUAL — exercising them for real needs an
# Electron main process and this suite is Python — and they read the source
# with comments stripped, so a promise written in prose cannot satisfy them.
# They are labelled here rather than trusted silently.

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_LINE_COMMENT = re.compile(r"(^|\s)//.*$")


def _electron_main() -> str:
    """`background.ts` as live code: block comments first, then line comments.

    Line comments are anchored to start-of-line-or-whitespace so a URL scheme
    survives — `http://host` has no space before the slashes, `  // dead` does.
    Both halves are needed: with only line stripping, a `/* ... */` block
    containing the literals below satisfies every assertion while nothing runs.
    """
    path = os.path.join(_ROOT, "Frontend", "frontend", "main", "background.ts")
    with open(path, encoding="utf-8") as fh:
        text = _BLOCK_COMMENT.sub("", fh.read())
    return "\n".join(
        stripped for stripped in (_LINE_COMMENT.sub("", l) for l in text.splitlines())
        if stripped.strip()
    )


def test_the_docker_startup_path_actually_asks_which_tree_is_mounted():
    src = _electron_main()
    block = re.search(r"if \(useDockerBackend\) \{(.*?)\n  \}", src, re.S)
    assert block and "assertBackendMountsOurWorkspace" in block.group(1), \
        "the mount check must run on the Docker startup path, not merely exist"


def test_the_mount_check_is_a_real_check_and_not_a_name():
    """Naming the helper proves nothing about its body — an early `return`
    satisfies the assertion above while startup verifies no identity at all.
    That exact hollowing-out was found in `assertBackendSharesOurToken` on
    31 Aug 2026, so the body is checked for what makes it a check."""
    src = _electron_main()
    body = re.search(
        r"async function assertBackendMountsOurWorkspace\(\)[^{]*\{(.*?)\n\}",
        src, re.S)
    assert body, "assertBackendMountsOurWorkspace not found in its expected shape"
    b = body.group(1)
    assert "canonicalHostRoot()" in b, "the check must sample THIS process's configured root"
    assert "fetchBackendWorkspaceFingerprint" in b, "the container's answer must be fetched"
    assert "fingerprint ===" in b or "=== ours.fingerprint" in b, \
        "the two fingerprints must actually be compared"

    # `in b` is satisfied by DEAD code. A mutation round proved it: prefixing the
    # body with a bare `return` left every literal above present and this test
    # green while startup checked nothing at all. So the region before the fetch
    # must contain no unconditional bail-out.
    #
    # Limit, stated rather than implied: this catches a bare `return` statement,
    # not every possible way of skipping the work.
    before_fetch = b[:b.index("fetchBackendWorkspaceFingerprint")]
    assert not any(line.strip() == "return" for line in before_fetch.splitlines()), \
        "an unconditional return before the fetch makes the whole check dead code"


def test_a_mismatch_throws_rather_than_being_logged():
    """Split out of the body check because `'throw' in body` was not an oracle
    for it — the earlier branches (no mount, algorithm drift) throw too, so
    turning the FINAL refusal into a `console.error` kept the assertion green
    while a wrong tree merely produced a warning and the app carried on. That is
    FINDING D4-03 restored in full, and it is the one line most likely to be
    softened by someone who finds the refusal inconvenient."""
    src = _electron_main()
    body = re.search(
        r"async function assertBackendMountsOurWorkspace\(\)[^{]*\{(.*?)\n\}",
        src, re.S)
    assert body, "assertBackendMountsOurWorkspace not found in its expected shape"
    b = body.group(1)
    marker = b.index("DIFFERENT tree")
    # Whichever construct sits closest ABOVE the message is the one that carries
    # it. Nearest-preceding rather than "is `throw` present somewhere".
    throw_at = b.rfind("throw new Error(", 0, marker)
    console_at = b.rfind("console.", 0, marker)
    assert throw_at != -1 and throw_at > console_at, \
        "the wrong-tree message must be thrown, not logged and ignored"


def test_the_refusal_names_the_fix_that_actually_works():
    """`up` alone reuses the existing container, so "restart it" is wrong advice
    — the service has to be RECREATED. Asserted against the shared `recreate`
    text: a mutation showed that looking for the phrase anywhere in the function
    passed on a DIFFERENT branch's message while the one the user actually sees
    had lost it."""
    src = _electron_main()
    body = re.search(
        r"async function assertBackendMountsOurWorkspace\(\)[^{]*\{(.*?)\n\}",
        src, re.S)
    assert body
    # Ends at the next statement at the function's own indent. NOT at a blank
    # line: `_electron_main` drops those along with the comments, so a `\n\n`
    # anchor matches nothing and this test failed for a reason that had nothing
    # to do with the property it names.
    recreate = re.search(r"const recreate =(.*?)\n  \w", body.group(1), re.S)
    assert recreate, "the shared fix text is not where this test can find it"
    assert "docker compose down" in recreate.group(1)


def test_the_fetch_is_authenticated():
    """The endpoint returns a directory listing of the developer's project, so
    an unauthenticated caller would be refused — an unauthenticated CALL would
    simply always fail and the gate would look green from the backend side."""
    src = _electron_main()
    fetch = re.search(
        r"async function fetchBackendWorkspaceFingerprint\(\)[^{]*\{(.*?)\n\}",
        src, re.S)
    assert fetch, "fetchBackendWorkspaceFingerprint not found in its expected shape"
    b = fetch.group(1)
    assert "/health/workspace" in b
    assert "localAppToken" in b and "X-Session-Token" in b


def test_the_check_stays_off_the_ordinary_path():
    """Docker mode OFF must cost nothing: no request, no directory walk. The
    only call site is inside the `if (useDockerBackend)` startup block."""
    src = _electron_main()
    calls = re.findall(r"await assertBackendMountsOurWorkspace\(\)", src)
    assert len(calls) == 1, f"expected exactly one call site, found {len(calls)}"


def test_both_sides_agree_on_the_algorithm_name_and_the_directories_they_skip():
    """The fingerprint is only meaningful if the two implementations are the
    same one. A rename on one side alone turns every correct setup into a
    refusal at startup."""
    src = _electron_main()
    assert f"'{auth_routes.WORKSPACE_FINGERPRINT_ALGO}'" in src, \
        "the Electron side does not use the algorithm name the backend reports"
    for name in auth_routes._NO_DESCEND:
        assert f"'{name}'" in src, f"{name!r} is skipped by the backend but not by Electron"

    # Declaring the set is not consulting it. Measured 31 Aug 2026, and by the
    # worst possible route: the descent condition lost its `NO_DESCEND` clause
    # while the set itself stayed intact, so every assertion above passed, the
    # 272-test run was green, `tsc` was clean — and the two sides silently
    # disagreed about every tree containing a `Library/`, which is every Unity
    # project. A cross-language run of the two implementations over one real
    # directory is what caught it. Presence of a constant proves nothing about
    # its use.
    assert re.search(r"FINGERPRINT_NO_DESCEND\.has\(", src), \
        "the skip list is declared but never consulted; the two sides will disagree"
