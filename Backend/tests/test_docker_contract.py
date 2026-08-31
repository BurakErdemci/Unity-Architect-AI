"""The Docker dev container is a four-file contract, and it had never held.

Docker mode existed in the tree since the web era and was measured broken on
31 Aug 2026: the container refused every request, because Electron mints a
per-launch `LOCAL_APP_TOKEN` and hands it to the backend process it *spawns* —
and in Docker mode it spawns nothing. Compose demanded the token
(`REQUIRE_LOCAL_APP_TOKEN=1`) without ever supplying it.

Nothing executes these files in CI (no Docker daemon on the runner), so nothing
would notice them rotting again. These are source-scan assertions: cheap, and
they fail on exactly the four things that were individually wrong.
"""
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _read(*parts: str) -> str:
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(scope="module")
def compose() -> str:
    return _read("docker-compose.yml")


@pytest.fixture(scope="module")
def dockerfile() -> str:
    return _read("Backend", "Dockerfile")


@pytest.fixture(scope="module")
def electron_main() -> str:
    return _read("Frontend", "frontend", "main", "background.ts")


def test_compose_supplies_the_token_it_demands(compose):
    """The original defect. Demanding a credential without passing one means a
    container that starts, reports healthy, and then 401s every call."""
    assert "REQUIRE_LOCAL_APP_TOKEN=1" in compose
    assert re.search(r"LOCAL_APP_TOKEN=\$\{LOCAL_APP_TOKEN", compose), \
        "compose must pass LOCAL_APP_TOKEN through from the environment"


def test_a_missing_token_stops_compose_instead_of_starting_a_dead_container(compose):
    # `:?` is what turns "silently broken at request time" into "refuses to
    # start, with a reason". Plain `${LOCAL_APP_TOKEN}` would expand to empty.
    assert re.search(r"LOCAL_APP_TOKEN=\$\{LOCAL_APP_TOKEN:\?", compose)


def test_the_container_binds_beyond_loopback(dockerfile):
    """The app defaults to 127.0.0.1. Inside a container that publishes the port
    but makes it unreachable from the host — a second, independent reason Docker
    mode could never have worked."""
    assert re.search(r"^ENV HOST=0\.0\.0\.0", dockerfile, re.M)


def test_the_image_python_matches_what_the_project_targets(dockerfile):
    # CONTRIBUTING.md says Python 3.13+; the image said 3.11 until 31 Aug 2026.
    assert re.search(r"^FROM python:3\.1[3-9]", dockerfile, re.M), \
        "image must be built on the Python the project targets"


def test_the_unity_address_is_not_the_container_own_localhost(compose):
    # The Editor runs on the host; `localhost` inside the container is the
    # container. Overridable, because Linux and Docker Desktop differ.
    assert "UNITY_MCP_URL=${UNITY_MCP_URL:-http://host.docker.internal" in compose
    assert "host.docker.internal:host-gateway" in compose, \
        "Linux needs the host-gateway alias declared; Docker Desktop does not"


def test_the_workspace_is_mounted(compose):
    """Without a mount the file tools operate on an empty image and report
    success — the failure shape this repo keeps paying for."""
    assert re.search(r"\$\{GAMACHINE_WORKSPACE:-\.\}:/workspace", compose)


def test_electron_takes_the_token_from_the_environment_only_in_docker_mode(electron_main):
    """Both halves matter. Reading the env var is what makes Docker mode work;
    restricting it to Docker mode is what keeps the normal path's per-launch
    randomness — a token that leaks into a shell profile must not silently
    become every future session's credential."""
    m = re.search(r"const localAppToken = ([^\n]*(?:\n[^\n]*){0,3}?randomUUID\(\))",
                  electron_main)
    assert m, "token derivation not found in its expected shape"
    ifade = m.group(1)
    assert "useDockerBackend" in ifade, \
        "the env var must be honoured only when the backend is a container"
    assert "process.env.LOCAL_APP_TOKEN" in ifade
    assert "randomUUID()" in ifade, "the non-Docker path must stay random per launch"


def test_docker_mode_refuses_to_start_without_a_shared_token(electron_main):
    # The counterpart of the compose `:?` guard, on the Electron side.
    assert re.search(r"if \(!process\.env\.LOCAL_APP_TOKEN\)", electron_main)
