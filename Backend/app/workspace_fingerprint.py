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


def kind(entry) -> str:
    """One character per entry, classified by what it BEHAVES as.

    Link-ness is deliberately not part of the fingerprint, and the reason is
    that the two sides look at the same tree through different filesystems.
    Measured 31 Aug 2026 by the cross-language parity test, on a Windows host:
    a directory junction is reported as a link by Node (`isSymbolicLink()` is
    true for any reparse point) and as a plain directory by Python. In the real
    deployment the split is wider still — the host walks NTFS while the
    container walks the same tree through Docker Desktop's translation layer,
    which presents a junction as an ordinary directory. So encoding link-ness
    made the two sides disagree about a tree that IS the same, and startup
    refused a CORRECT setup while telling the user to `docker compose down`,
    which cannot help.

    An earlier version resolved without following, on the argument that a link
    classified by its target hides cross-tree confusion. That argument belongs
    to a containment check, and this is not one: containment is enforced by
    `workspace-mapping` plus realpath in the main process. This function answers
    only "are these two directories the same tree", and for that question a
    junction and the directory it names are the same answer.
    """
    if entry.is_dir():
        return "d"
    if entry.is_file():
        return "f"
    return "o"


def stays_inside(root_real: str, path: str) -> bool:
    """Does `path` resolve to something still under `root_real`?

    This is the descent rule, and it is phrased in terms of the RESOLVED TARGET
    rather than link-ness on purpose. Measured 31 Aug 2026, on one Windows
    directory junction, with the two shipped runtimes:

        Node   isSymbolicLink() -> true
        Python is_symlink()     -> False

    So the two sides do not agree on what a link IS, and any rule of the form
    "if it is a link, do not descend" makes them walk different trees and
    report a mismatch for a correct setup — which is the failure this whole
    guard exists to avoid, reintroduced by its own fix. The earlier `l` kind
    died of the same cause.

    Containment is the one question both runtimes answered identically in that
    same measurement (in-root junction: inside on both; out-of-root junction:
    outside on both), because both resolve reparse points and both canonicalise
    case. So the rule is built on containment.

    What this buys (AUDIT R6-01): once `kind` began following links, a
    top-level junction pointing out of the workspace was classified `d` and
    then DESCENDED INTO, so files outside the mount entered a fingerprint whose
    entire claim is to describe the workspace. Breadth was unbounded — a link
    to a large external tree was enumerated on every Docker start.

    Boundary, stated rather than pretended: for a link whose target leaves the
    mount, the two sides are NOT guaranteed to agree. The host stops here,
    while the container may see the same path as an ordinary directory through
    Docker Desktop's translation layer and descend. That case could not be
    measured (no daemon was reachable on 31 Aug 2026), so it is documented as
    outside the guarantee instead of being claimed either way. The failure mode
    is a loud mismatch at startup, not a wrong tree accepted silently.
    """
    try:
        target = os.path.realpath(path, strict=True)
    except (OSError, ValueError):
        # Unresolvable: contributes no children, which is also what an
        # unlistable directory does below.
        return False
    return target == root_real or target.startswith(root_real + os.sep)


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
    try:
        root_real = os.path.realpath(root, strict=True)
    except (OSError, ValueError):
        # Without a resolved root there is nothing to be inside of, so no
        # descent is possible. The level-1 listing is still meaningful.
        root_real = None
    for entry in top:
        entry_kind = kind(entry)
        lines.append(f"{entry.name}\t{entry_kind}")
        if entry_kind != "d" or entry.name in NO_DESCEND:
            continue
        if root_real is None or not stays_inside(root_real, entry.path):
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
