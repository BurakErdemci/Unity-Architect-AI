import hashlib
import os

from fastapi import APIRouter, Header
from auth_utils import _check_token

# Where docker-compose.yml binds the host workspace. The container cannot learn
# its own bind SOURCE — from inside, only this path exists — so identity has to
# be established by comparing something both sides can observe.
CONTAINER_WORKSPACE_MOUNT = "/workspace"

# Identifies the algorithm below. Both sides must implement the same version;
# the Electron side sends nothing, so a bumped version here shows up there as a
# mismatched `algo` and is reported as "sides disagree", not "wrong tree".
WORKSPACE_FINGERPRINT_ALGO = "gamachine-ws-fp-1"

# Not descended into. These are rewritten continuously by the Unity Editor and
# by compilers, and the two sides sample the tree milliseconds apart, so their
# contents are the part most likely to differ for reasons that are not identity.
# Their own name and kind still count at level 1, so deleting `Library` is still
# visible.
_NO_DESCEND = frozenset({
    "Library", "Temp", "Logs", "obj", "bin", "Build", "Builds",
    ".git", ".vs", "node_modules",
})

# A ceiling on work and on response size. Applied after sorting, so both sides
# truncate the same prefix of the same list.
_MAX_ENTRIES = 4096


def _kind(entry: "os.DirEntry") -> str:
    """One character per entry, resolved WITHOUT following symlinks.

    Following them would let a link inside the tree be classified by its target,
    which is exactly the cross-tree confusion this endpoint exists to detect.
    """
    if entry.is_symlink():
        return "l"
    if entry.is_dir(follow_symlinks=False):
        return "d"
    if entry.is_file(follow_symlinks=False):
        return "f"
    return "o"


def _fingerprint_lines(root: str) -> list:
    """`<relpath>\\t<kind>` for the root's children and its children's children.

    Two levels, not one and not all. One level is too weak for the failure this
    guards: two sibling Unity projects have the SAME top-level layout (Assets,
    Library, Packages, ProjectSettings), so a root listing alone cannot tell
    them apart — and "wrong sibling project" is the reported case. Level 2
    reaches `Assets/<the user's own folders>` and `ProjectSettings/*`, which do
    differ. Full recursion is not an option: `Library/` alone is six figures of
    files on a real project.

    No sizes and no timestamps. Timestamps cross a virtualised bind mount with
    unpredictable resolution (Docker Desktop does not pass host mtimes through
    verbatim), so they produce disagreement that means nothing. Names and kinds
    change only when something is created, renamed or removed.

    A directory that cannot be listed contributes no children rather than an
    error: the caller compares digests, and a permission asymmetry between the
    host user and the container user surfaces as a mismatch either way.
    """
    lines = []
    try:
        top = list(os.scandir(root))
    except OSError:
        return lines
    for entry in top:
        kind = _kind(entry)
        lines.append(f"{entry.name}\t{kind}")
        if kind != "d" or entry.name in _NO_DESCEND:
            continue
        try:
            children = list(os.scandir(entry.path))
        except OSError:
            continue
        for child in children:
            lines.append(f"{entry.name}/{child.name}\t{_kind(child)}")
    # Sorted by UTF-8 BYTES, not by code point. Python orders `str` by code
    # point and JavaScript's default sort orders by UTF-16 code unit; the two
    # disagree above the BMP, which would make an emoji-named asset folder
    # produce a spurious mismatch on one platform only.
    lines.sort(key=lambda line: line.encode("utf-8"))
    return lines


def create_auth_router(db):
    router = APIRouter()

    @router.get("/me")
    async def get_me(x_session_token: str = Header(alias="X-Session-Token", default="")):
        _check_token(x_session_token)
        # user_id, username, name, avatar — eski frontend uyumluluğu
        return {"user_id": 1, "id": 1, "username": "local", "name": "local",
                "email": "local@localhost", "avatar": ""}

    @router.get("/health/auth")
    async def health_auth(x_session_token: str = Header(alias="X-Session-Token", default="")):
        """Liveness, but only for a caller holding the app token.

        `/health` is deliberately unauthenticated (see the authz matrix's
        whitelist), which makes it useless for the one question Docker mode has
        to ask at startup: is the backend I just reached holding the SAME secret
        I am? Measured 31 Aug 2026 — a container kept alive by `restart:
        unless-stopped` outlives the shell that exported its token, answers
        `/health` happily, and then 401s every real call. Every visible startup
        signal read as fine.

        It lives here rather than beside `/health` in `main.py` on purpose: the
        authz matrix installs its sentinel into `routes.*` modules, so a
        protected endpoint declared outside them is invisible to the one test
        that proves the gate is actually called.
        """
        _check_token(x_session_token)
        return {"status": "ok", "service": "gamachine", "auth": "ok"}

    @router.get("/health/workspace")
    async def health_workspace(x_session_token: str = Header(alias="X-Session-Token", default="")):
        """A read-only fingerprint of the tree this backend serves at `/workspace`.

        WHAT IT IS FOR
            `restart: unless-stopped` keeps a container alive across the shell
            that started it, and a container's bind source is fixed when the
            container is CREATED. So exporting a new `GAMACHINE_WORKSPACE` and
            relaunching Electron changes what Electron believes is mounted and
            changes nothing about what is actually mounted. Electron then maps
            project B onto `/workspace` successfully while the live backend
            reads and writes project A, both halves reporting success.
            `/health/auth` does not cover this: it proves the two sides share a
            token and says nothing about which tree is behind the mount.

        WHAT A COMPARISON PROVES, AND WHAT IT DOES NOT
            The Electron side computes the same fingerprint over the host
            directory it thinks is mounted and compares.

            A MISMATCH is strong: these two directories do not currently have
            the same two-level layout, so they are not the same tree — unless
            something changed in the tree between the two samples, which is why
            the caller confirms a mismatch a second time before refusing.

            A MATCH is much weaker, and this is the honest limit. It says the
            two directories agree on entry names and kinds two levels deep. It
            does NOT prove they are the same directory: two copies of one
            project, or two projects generated from the same template and not
            yet edited, hash identically. File CONTENT is not sampled at all, so
            a tree whose files all differ but whose layout matches passes.

            No stronger read-only check was available. Comparing st_dev/st_ino
            across the mount would be conclusive on a Linux bind mount, but
            Docker Desktop's virtualised filesystem synthesises inode numbers,
            so on the platforms this project is developed on it would report a
            mismatch for the correct tree. Writing a marker file into the
            workspace would be conclusive everywhere and is deliberately not
            done: a Unity project reacts to new files by importing them.

        It is read-only: `os.scandir` plus dirent kind bits, no `open`, no
        write, no mtime read. And it is behind the same gate as everything else
        — a directory listing of the developer's project is not public.
        """
        _check_token(x_session_token)
        base = {"status": "ok", "algo": WORKSPACE_FINGERPRINT_ALGO,
                "mount": CONTAINER_WORKSPACE_MOUNT}
        if not os.path.isdir(CONTAINER_WORKSPACE_MOUNT):
            # Reported rather than raised. The caller needs to tell "no mount"
            # apart from "wrong mount": they have different fixes, and this
            # endpoint also answers on the non-Docker path where there is no
            # mount and nothing is wrong.
            return {**base, "mounted": False, "entries": 0,
                    "truncated": False, "fingerprint": ""}
        lines = _fingerprint_lines(CONTAINER_WORKSPACE_MOUNT)
        truncated = len(lines) > _MAX_ENTRIES
        lines = lines[:_MAX_ENTRIES]
        digest = hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()
        return {**base, "mounted": True, "entries": len(lines),
                "truncated": truncated, "fingerprint": digest}

    @router.post("/login")
    async def login():
        # Geriye dönük uyumluluk stub (token gerektirmez)
        return {"session_token": "local",
                "user": {"user_id": 1, "username": "local", "email": "local@localhost"}}

    @router.post("/logout")
    async def logout():
        return {"ok": True}

    @router.get("/auth/providers")
    async def get_providers():
        # Eski frontend bu shape'i bekliyordu
        return {"google": False, "github": False}

    return router
