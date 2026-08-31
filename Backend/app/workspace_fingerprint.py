"""The `gamachine-ws-fp-1` workspace fingerprint, container side.

Split out of `routes/auth_routes.py` so a test can RUN it WITHOUT FastAPI.
There are two implementations of this algorithm — this one and
`main/helpers/workspace-fingerprint.ts` — and Docker startup compares their
answers to refuse a container still serving an older bind mount. If they
disagree about a tree that is in fact the same, the app refuses a correct
setup; if they agree about trees that differ, the guard is worthless.

The split has the same reason as the one on the Electron side, where the
module deliberately touches nothing from Electron. Measured 31 Aug 2026
(AUDIT R6-02): the cross-language parity test imported these functions from
`routes.auth_routes`, which imports FastAPI, so the test needed the backend's
whole virtualenv. The frontend CI job has no such venv, the test selected
`describe.skip`, and its six cases reported "skipped" while `vitest` stayed
green. A parity test that does not run in the gate is not a gate. Importing
this module needs the standard library and nothing else, which every CI job
already has.

So: nothing may be imported here beyond the standard library. The moment
something is, the parity test loses its interpreter and the gap comes back.
"""
import hashlib
import os

# Identifies the algorithm. Both sides must implement the same version; the
# Electron side sends nothing, so a bumped version here shows up there as a
# mismatched `algo` and is reported as "sides disagree", not "wrong tree".
WORKSPACE_FINGERPRINT_ALGO = "gamachine-ws-fp-1"

# Not descended into. These are rewritten continuously by the Unity Editor and
# by compilers, and the two sides sample the tree milliseconds apart, so their
# contents are the part most likely to differ for reasons that are not identity.
# Their own name and kind still count at level 1, so deleting `Library` is still
# visible.
NO_DESCEND = frozenset({
    "Library", "Temp", "Logs", "obj", "bin", "Build", "Builds",
    ".git", ".vs", "node_modules",
})

# There is deliberately NO entry cap here any more. There used to be one
# (`_MAX_ENTRIES = 4096`, applied after sorting) and it bought nothing: the walk
# and the sort had already happened, so it saved no traversal, and the response
# carries a digest rather than the lines, so it saved no payload either. What it
# cost was the whole point of the check — two trees whose first 4096 byte-sorted
# lines agreed hashed identically, and the Electron side accepts on digest
# equality alone. A Unity project passes 4096 entries across the root and one
# descended level without trying, so a single late-sorting file was enough to
# make a wrong mount pass. Hashing every collected line is what the cap was
# preventing and what identity requires.


def is_link(entry) -> bool:
    """Is this entry a link, by the only definition all three runtimes share?

    `os.path.isjunction` is not belt-and-braces, it is the whole reason this
    function exists. Measured 31 Aug 2026 on one Windows directory junction:

        Node    entry.isSymbolicLink()              -> True
        Python  entry.is_symlink()                  -> False
        Python  os.path.isjunction(entry.path)      -> True

    `is_symlink()` alone answers False for a junction, and an earlier round read
    that single measurement as proof that the two sides could never agree about
    what a link IS — so link-ness was abandoned as a rule and descent was gated
    on resolved-target containment instead. The measurement was right and the
    conclusion was wrong: Python can see a junction, just not through
    `is_symlink()`. `os.path.isjunction` arrived in 3.12 and this backend pins
    3.13. On POSIX it simply returns False, so the disjunction costs nothing
    there.
    """
    if entry.is_symlink():
        return True
    try:
        return os.path.isjunction(entry.path)
    except OSError:
        # Vanished between the listing and the question. Not a link we can
        # name; `kind` falls through to its own guarded answers.
        return False


def kind(entry) -> str:
    """One character per entry: `l` link, `d` directory, `f` file, `o` other.

    A link is `l` REGARDLESS of what it points at, and is never followed. The
    target is deliberately absent from the fingerprint: the same junction is
    spelled `C:\\...` on the host and resolves to an unreachable
    `/mnt/host/c/...` inside the container, so hashing the target would
    guarantee the mismatch this whole check exists to avoid.

    Measured 31 Aug 2026 against a REAL container over a real bind mount — the
    first round in this series where a Docker daemon was reachable — with one
    junction pointing inside the workspace and one pointing outside:

        entry            host (Windows)      container (Linux)
        ordinary dir     d + children        d + children
        junction         d + children        o          <- diverged
        junction         d                   o          <- diverged

    The container receives a junction as a symlink to `/mnt/host/...`, which
    does not exist there, so it is neither a directory nor a file. Classifying
    by behaviour therefore made ANY workspace containing a junction fail Docker
    startup — including a junction pointing INSIDE the workspace, which is an
    entirely ordinary thing for a Unity project to contain. That is the exact
    failure this guard exists to prevent, produced by the guard itself.

    With `l` on both sides the same tree measured equal on both sides, the
    outside file stayed out, and no `realpath` call is needed at all: nothing
    is ever descended into, so nothing can escape the mount by construction.
    """
    if is_link(entry):
        return "l"
    if entry.is_dir():
        return "d"
    if entry.is_file():
        return "f"
    return "o"


def fingerprint_lines(root: str) -> list:
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
        entry_kind = kind(entry)
        lines.append(f"{entry.name}\t{entry_kind}")
        # `l` is excluded here as much as `f` and `o` are: a link is never
        # followed, so nothing outside the mount can be reached and no
        # `realpath` is needed to prove it. An earlier version resolved every
        # candidate and compared it against the resolved root; that machinery
        # existed only because links were classified as directories, and it
        # brought a bug of its own — a workspace at a filesystem root kept its
        # trailing separator on the host and did not in the container, so the
        # host refused every descent while the backend performed them
        # (AUDIT R7-02). Not descending into links removes the question.
        if entry_kind != "d" or entry.name in NO_DESCEND:
            continue
        try:
            children = list(os.scandir(entry.path))
        except OSError:
            continue
        for child in children:
            lines.append(f"{entry.name}/{child.name}\t{kind(child)}")
    # Sorted by UTF-8 BYTES, not by code point. Python orders `str` by code
    # point and JavaScript's default sort orders by UTF-16 code unit; the two
    # disagree above the BMP, which would make an emoji-named asset folder
    # produce a spurious mismatch on one platform only.
    #
    # `surrogateescape` is not decoration. A Linux filename is a byte string with
    # no encoding guarantee, and `os.scandir` hands undecodable bytes back as
    # lone surrogates (b"\xff" -> "\udcff"). Encoding those with the strict
    # default raises UnicodeEncodeError, which the endpoint did not catch, so one
    # legal filename anywhere in the tree turned this into an HTTP 500 and failed
    # Docker-mode startup outright. The error handler is the exact inverse of the
    # decode, so the bytes hashed here are the bytes on disk — which is also what
    # the Electron side hashes, since it reads its dirents as raw buffers.
    lines.sort(key=lambda line: line.encode("utf-8", "surrogateescape"))
    return lines


def fingerprint_digest(lines: list) -> str:
    """sha256 over the raw on-disk bytes of the sorted lines, newline-joined."""
    return hashlib.sha256(
        "\n".join(lines).encode("utf-8", "surrogateescape")
    ).hexdigest()
