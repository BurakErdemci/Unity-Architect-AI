"""The Docker dev container is a multi-file contract, and it had never held.

Docker mode existed in the tree since the web era and was measured broken on
31 Aug 2026: the container refused every request, because Electron mints a
per-launch `LOCAL_APP_TOKEN` and hands it to the backend process it *spawns* —
and in Docker mode it spawns nothing.

The first version of this file asserted on raw file text and an audit took it
apart the same day: every assertion could stay green while the property it named
was false — the pattern matched inside a comment, on the wrong service, or in a
Dockerfile stage a later stage overrode. So the rules here are:

1. Where Compose can answer, **ask Compose**. `docker compose config` resolves
   interpolation, defaults and overrides; its output is behaviour, not text.
   Without a daemon these still work — `config` is a parser, not a run.
2. Where only a file can answer, **evaluate it the way its consumer does**:
   comments stripped, last directive wins, correct stage.
3. What remains genuinely textual says so in its own docstring, so nobody reads
   more assurance out of it than it carries.
"""
import json
import os
import re
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOKEN = "contract-test-token-4f2a"


def _read(*parts: str) -> str:
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


# `#` for the Dockerfile, `//` for TypeScript. Both are anchored to
# start-of-line-or-whitespace so a URL scheme survives: `http://host` has no
# space before the slashes, `  // dead code` does. Without the `//` half a
# mutation that merely COMMENTED OUT the startup token check left this suite
# green — measured 31 Aug 2026, and it is the very class the audit flagged.
_COMMENT_RE = re.compile(r"(^|\s)(#|//).*$")


def _strip_line_comments(text: str) -> str:
    """Drop comments so a promise written in prose cannot satisfy a test.

    Deliberately naive about comment markers inside quotes: no line these tests
    read needs one, and a cleverer parser here would be untested code guarding
    tested code.
    """
    out = []
    for line in text.splitlines():
        stripped = _COMMENT_RE.sub("", line)
        if stripped.strip():
            out.append(stripped)
    return "\n".join(out)


def _compose_env() -> dict:
    return {
        **os.environ,
        "LOCAL_APP_TOKEN": TOKEN,
        "GAMACHINE_WORKSPACE": os.path.join(ROOT, "Backend"),
    }


def _compose(*args: str, env: dict = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "compose", *args],
        cwd=ROOT, capture_output=True, text=True, env=env or _compose_env(),
    )


@pytest.fixture(scope="module")
def resolved() -> dict:
    """The Compose model as Compose itself resolves it."""
    if not shutil.which("docker"):
        pytest.skip("docker CLI absent; the resolved-model assertions cannot run")
    cp = _compose("config", "--format", "json")
    if cp.returncode != 0:
        pytest.fail(f"docker compose config failed: {cp.stderr.strip()[:400]}")
    return json.loads(cp.stdout)["services"]["backend"]


@pytest.fixture(scope="module")
def dockerfile_effective() -> str:
    return _strip_line_comments(_read("Backend", "Dockerfile"))


@pytest.fixture(scope="module")
def electron_main() -> str:
    return _strip_line_comments(_read("Frontend", "frontend", "main", "background.ts"))


# ── the credential, which is what was actually broken ────────────────────────

def test_the_backend_service_receives_the_token_it_demands(resolved):
    env = resolved["environment"]
    assert env.get("REQUIRE_LOCAL_APP_TOKEN") == "1"
    # The resolved value, not the presence of a string somewhere in the file.
    assert env.get("LOCAL_APP_TOKEN") == TOKEN


def test_a_missing_token_makes_compose_refuse_rather_than_start(resolved):
    """`:?` is what turns "silently broken at request time" into "refuses to
    start, with a reason". Asserted by running Compose without the variable."""
    env = {k: v for k, v in _compose_env().items() if k != "LOCAL_APP_TOKEN"}
    cp = _compose("config", env=env)
    assert cp.returncode != 0, "compose accepted a configuration with no token"
    assert "LOCAL_APP_TOKEN" in cp.stderr


def test_a_missing_workspace_makes_compose_refuse(resolved):
    """The default used to be `.`, which mounted the product's own source tree
    writable into the container. A workspace is chosen, never inherited."""
    env = {k: v for k, v in _compose_env().items() if k != "GAMACHINE_WORKSPACE"}
    cp = _compose("config", env=env)
    assert cp.returncode != 0, "compose accepted a configuration with no workspace"
    assert "GAMACHINE_WORKSPACE" in cp.stderr


# ── reachability and mounts ──────────────────────────────────────────────────

def test_the_port_is_published_to_loopback_only(resolved):
    ports = resolved.get("ports") or []
    assert ports, "no published port in the resolved model"
    for p in ports:
        assert p.get("host_ip") in ("127.0.0.1", "::1"), \
            f"port published beyond loopback: {p}"


def test_the_workspace_lands_on_the_path_the_app_sends(resolved):
    """The container path here and `DOCKER_WORKSPACE_MOUNT` in the Electron main
    process must be the same string. When they drifted, the mount existed and
    the backend still addressed a path nothing in the container could resolve."""
    targets = {v.get("target") for v in resolved.get("volumes") or []}
    assert "/workspace" in targets, f"workspace not mounted at /workspace: {targets}"


def test_the_backend_source_is_mounted_so_a_host_edit_is_what_runs(resolved):
    vols = {v.get("target"): v for v in resolved.get("volumes") or []}
    assert "/app" in vols, "backend source not mounted; the container runs a build snapshot"
    assert vols["/app"].get("read_only") is True, "the source mount must be read-only"
    assert resolved["environment"].get("UVICORN_RELOAD"), \
        "a mounted source without reload still does not reach the running process"


def test_the_unity_address_is_not_the_container_own_localhost(resolved):
    url = resolved["environment"].get("UNITY_MCP_URL", "")
    assert "host.docker.internal" in url, f"Unity URL points into the container: {url!r}"
    aliases = resolved.get("extra_hosts") or {}
    joined = json.dumps(aliases)
    assert "host.docker.internal" in joined and "host-gateway" in joined, \
        "Linux needs the host-gateway alias; Docker Desktop does not"


def test_the_service_does_not_run_as_root(resolved):
    user = str(resolved.get("user") or "")
    assert user and not user.startswith("0:") and user != "0", \
        f"backend runs as root over a bind mount of the developer's tree: {user!r}"


# ── the image, evaluated the way Docker evaluates it ─────────────────────────

def test_the_final_stage_python_matches_what_the_project_targets(dockerfile_effective):
    """Last `FROM` wins. The earlier version matched the FIRST one, so a second
    stage on 3.11 would have kept it green."""
    froms = re.findall(r"^FROM\s+(\S+)", dockerfile_effective, re.M)
    assert froms, "no FROM directive"
    final = froms[-1]
    m = re.match(r"python:3\.(\d+)", final)
    assert m and int(m.group(1)) >= 13, \
        f"final stage is {final!r}; the project targets Python 3.13+"


def test_the_effective_bind_host_reaches_beyond_loopback(dockerfile_effective, resolved):
    """Last `ENV HOST=` wins in the image, and Compose can override it after
    that — so both layers are checked, not just the first line in the file."""
    envs = re.findall(r"^ENV\s+HOST=(\S+)", dockerfile_effective, re.M)
    assert envs, "the image never sets HOST; the app defaults to 127.0.0.1"
    assert envs[-1] == "0.0.0.0", f"last HOST in the image is {envs[-1]!r}"
    override = resolved["environment"].get("HOST")
    assert override in (None, "0.0.0.0"), f"compose puts HOST back to {override!r}"


def test_the_image_declares_a_non_root_user(dockerfile_effective):
    users = re.findall(r"^USER\s+(\S+)", dockerfile_effective, re.M)
    assert users, "no USER directive; the image runs as root"
    assert users[-1] not in ("root", "0"), f"final USER is {users[-1]!r}"


# ── the Electron side ────────────────────────────────────────────────────────
#
# These stay textual: exercising them for real needs an Electron main process
# and this suite is Python. They read the comment-stripped source, so prose
# cannot satisfy them, and they are labelled here rather than trusted silently.

def test_electron_takes_the_token_from_the_environment_only_in_docker_mode(electron_main):
    """Both halves matter. Reading the env var is what makes Docker mode work;
    restricting it to Docker mode is what keeps the normal path's per-launch
    randomness."""
    m = re.search(r"const localAppToken = ([^\n]*(?:\n[^\n]*){0,3}?randomUUID\(\))",
                  electron_main)
    assert m, "token derivation not found in its expected shape"
    ifade = m.group(1)
    assert "useDockerBackend" in ifade
    assert "process.env.LOCAL_APP_TOKEN" in ifade
    assert "randomUUID()" in ifade, "the non-Docker path must stay random per launch"


def test_docker_mode_refuses_to_start_without_a_shared_token(electron_main):
    assert re.search(r"if \(!process\.env\.LOCAL_APP_TOKEN\)", electron_main)


def test_startup_proves_the_backend_holds_the_same_token(electron_main):
    """`/health` is unauthenticated, so reaching it says nothing about WHICH
    secret the backend holds. A container left running by `restart:
    unless-stopped` answered it happily and then 401'd every real call."""
    assert "assertBackendSharesOurToken" in electron_main
    assert "/health/auth" in electron_main
    dal = re.search(r"if \(useDockerBackend\) \{(.*?)\n  \}", electron_main, re.S)
    assert dal and "assertBackendSharesOurToken" in dal.group(1), \
        "the token check must run on the Docker startup path, not merely exist"


def test_the_mount_point_agrees_with_compose(electron_main):
    """The one string that has to be identical on both sides of the boundary."""
    assert re.search(r"DOCKER_WORKSPACE_MOUNT\s*=\s*'/workspace'", electron_main)


def test_the_workspace_path_is_translated_before_the_backend_sees_it(electron_main):
    assert "'backend-workspace-path'" in electron_main
    assert "'host-workspace-path'" in electron_main, \
        "without the reverse mapping the stored path cannot be reopened on the host"
