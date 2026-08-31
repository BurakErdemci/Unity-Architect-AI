"""The `gamachine-ws-fp-2` workspace fingerprint, container side.

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
WORKSPACE_FINGERPRINT_ALGO = "gamachine-ws-fp-2"

# Docker Desktop cannot store a name containing a character NTFS forbids, so it
# shifts each one into the private use area by exactly 0xF000. Measured 31 Aug
# 2026 by creating one file per candidate inside the container on a real
# Windows-backed mount and reading the directory from the host: all 39 affected
# characters — the C0 controls 0x01-0x1F plus `" * : < > ? \ |` — moved, every
# one of them by the same 0xF000, and nothing else moved.
#
# Both sides undo it, so both hash the same name (AUDIT R9-01). Undoing on one
# side only would leave the host hashing `ab` while the container hashes
# `a\tb` for the SAME file, which is a refused correct mount.
#
# It is a real conflation: a name genuinely containing U+F009 hashes like a name
# containing a tab. That is deliberate and follows the rule this module already
# lives by — the host CANNOT tell those two apart, because NTFS stores both as
# U+F009, so the distinction is not one both sides can make.
#
# Capped at 0x7F because that is the whole measured set and it keeps the mapping
# a single byte on the Electron side, where names are handled as raw buffers.
_PROJECTION_BASE = 0xF000
_PROJECTION_TOP = 0xF07F


def unproject(name: str) -> str:
    """Undo Docker Desktop's private-use projection of NTFS-illegal characters."""
    if not any("\uf001" <= ch <= "\uf07f" for ch in name):
        return name
    return "".join(
        chr(ord(ch) - _PROJECTION_BASE) if "\uf001" <= ch <= "\uf07f" else ch
        for ch in name
    )

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
    """`d` plain directory, `f` plain file, `o` anything else. Three answers.

    THE RULE: the fingerprint encodes only distinctions BOTH SIDES CAN MAKE.
    Everything that is not a plain directory or a plain file collapses into
    `o`, and `o` is never descended into.

    That is not tidiness, it is the result of three measurements against a real
    container over a real bind mount (31 Aug 2026). The first two rounds of this
    question each encoded a distinction one side could not make:

        entry     rule A: behavioural    rule B: separate `l`   this rule
                  host / container       host / container       host / container
        junction  d+children / o  BAD    l / l          ok      o / o
        symlink   d+children / o  BAD    l / l          ok      o / o
        FIFO      f / o           BAD    l / o          BAD     o / o
        socket    f / o           BAD    l / o          BAD     o / o

    Rule B failed because Windows cannot tell those objects apart AT ALL:
    Docker Desktop stores a symlink, a FIFO and a socket alike as reparse
    points (tags 0x80000024 and 0x80000023 for the last two), and Node's
    `Dirent.isSymbolicLink()` collapses every tag into "link". So the host says
    "link" to all of them while the container says "link, pipe, socket" — the
    host is not withholding the distinction, it does not have it.

    The audit's proposed repair was to map FIFO and socket to `l` on this side
    to match the Windows view. That would have repaired Windows and broken
    Linux: on a Linux host Node sees a FIFO as neither link nor directory nor
    file and answers `o`, so this side answering `l` would be a NEW mismatch.
    Merging into `o` is symmetric and holds on both host platforms.

    Nothing is lost for identity. A link, a pipe and a socket are equally
    "not a tree I descend into", and their names still count at level 1, so
    creating or deleting one still moves the digest. Link TARGETS are absent on
    purpose: the same junction is spelled `C:\\...` on the host and resolves to
    an unreachable `/mnt/host/c/...` in the container, so hashing targets would
    guarantee the mismatch this check exists to prevent.

    Measured after the merge, across 10 entry shapes including FIFO, socket,
    dangling link, hardlink and a trailing-space name: zero divergence.
    """
    # Asked BEFORE `is_dir()`, which follows links by default and would answer
    # `d` for a link to a directory — and then it would be descended into.
    if is_link(entry):
        return "o"
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
        lines.append(unproject(entry.name) + "\x00" + entry_kind)
        # Only a plain directory is descended into, so a link cannot be
        # followed and nothing outside the mount is reachable — no `realpath`
        # is needed to prove it. An earlier version resolved every
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
            lines.append(unproject(entry.name) + "/"
                         + unproject(child.name) + "\x00" + kind(child))
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
    """sha256 over the sorted records, concatenated with no separator.

    None is needed. Each record is `<relpath>\\0<kind>` and NUL is the one byte
    a filename cannot contain on either platform, so the concatenation parses
    back one way only: read to the NUL for the path, take the next character as
    the kind, and the record after it begins.

    The previous encoding joined `<relpath>\\t<kind>` records with newlines, and
    neither separator was escaped while both are legal in a POSIX filename. That
    made the digest NON-INJECTIVE, which is the "agrees about trees that differ"
    failure the module docstring names. Measured 31 Aug 2026 (AUDIT R9-01), on a
    real bind mount:

        one file named  a<TAB>f<LF>b   -> record  "a\\tf\\nb\\tf"
        two files named a  and  b      -> records "a\\tf", "b\\tf"
                                       -> joined  "a\\tf\\nb\\tf"

    Same bytes, same digest, different trees — and startup accepts on digest
    equality alone, so a wrong mount passed. Entry counts differed (1 versus 2)
    and nothing compared them.
    """
    return hashlib.sha256(
        "".join(lines).encode("utf-8", "surrogateescape")
    ).hexdigest()
