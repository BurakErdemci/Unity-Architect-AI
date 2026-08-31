/**
 * The `gamachine-ws-fp-1` workspace fingerprint, host side.
 *
 * Split out of `background.ts` so a test can RUN it. There are two
 * implementations of this algorithm — this one and `fingerprint_lines` in
 * `Backend/app/workspace_fingerprint.py` — and they are compared at Docker startup
 * to refuse a container still serving an older bind mount. If they ever
 * disagree about a tree that is in fact the same, the app refuses a correct
 * setup; if they agree about trees that differ, the guard is worthless.
 *
 * They HAVE already diverged once, during development, while every test stayed
 * green and `tsc` was clean (31 Aug 2026): a descent condition lost a clause
 * here while the Python side kept it, and nothing in either suite could see it
 * because nothing executed both. `__tests__/workspace-fingerprint-parity.test.ts`
 * now runs this module and that module over the same trees and compares digests.
 *
 * Nothing here touches Electron, on purpose: the moment it does, the parity test
 * cannot import it and the gap comes back.
 */
import fs from 'fs'
import path from 'path'
import { createHash } from 'crypto'

export const WORKSPACE_FINGERPRINT_ALGO = 'gamachine-ws-fp-1'
// There is deliberately no entry cap. The previous `lines.slice(0, 4096)` was
// applied AFTER the walk and the sort, so it saved no traversal, and the digest
// rather than the lines goes over the wire, so it saved no payload — while two
// trees agreeing on their first 4096 byte-sorted lines hashed identically and
// this function's caller accepts on digest equality alone. One late-sorting file
// in a project that exceeds 4096 entries (an ordinary Unity project does, across
// the root and one descended level) was enough to pass a wrong mount.
// Mirrors `NO_DESCEND` in Backend/app/workspace_fingerprint.py. Both sides list
// these directories at level 1 and do not descend: the Editor and the compilers
// rewrite them continuously, and the two samples are taken milliseconds apart.
const FINGERPRINT_NO_DESCEND = new Set([
  'Library', 'Temp', 'Logs', 'obj', 'bin', 'Build', 'Builds',
  '.git', '.vs', 'node_modules',
])

// Every line is assembled and compared as BYTES, never as a JavaScript string.
// A POSIX filename is a byte string with no encoding guarantee: decoding it to
// UTF-16 replaces undecodable bytes with U+FFFD and that loss is not reversible,
// while the backend keeps the original bytes (os.scandir's surrogateescape,
// re-encoded with the same handler). Decoding here would therefore make the two
// sides disagree about a tree that is in fact identical — a false "wrong mount"
// refusal at startup instead of the crash that used to happen on the Python
// side. Reading dirents with `encoding: 'buffer'` keeps the on-disk bytes, which
// is exactly what the backend hashes.
const FP_TAB = Buffer.from('\t')
const FP_NEWLINE = Buffer.from('\n')
const FP_SLASH = Buffer.from('/')
const FP_PATH_SEP = Buffer.from(path.sep)

/**
 * `l` link, `d` directory, `f` file, `o` other. Mirrors `kind` in
 * Backend/app/workspace_fingerprint.py, which carries the full reasoning.
 *
 * A link is `l` whatever it points at, and is never followed. The target is
 * deliberately not in the fingerprint: the same junction is spelled `C:\...`
 * here and arrives inside the container as an unreachable `/mnt/host/c/...`,
 * so hashing targets would guarantee the mismatch this check exists to avoid.
 *
 * The previous version classified by behaviour, following the link and
 * answering `d`. Measured 31 Aug 2026 against a real container over a real
 * bind mount: the container sees a junction as a dangling symlink, so it
 * answered `o` while this side answered `d` and enumerated the children. Any
 * workspace containing a junction — including one pointing at its OWN
 * subdirectory — therefore failed Docker startup, which is precisely the
 * failure the guard exists to prevent.
 */
export function direntKind(dir: Buffer, entry: fs.Dirent<Buffer>): string {
  if (entry.isSymbolicLink()) return 'l'
  if (entry.isDirectory()) return 'd'
  if (entry.isFile()) return 'f'
  // A dirent can come back UNKNOWN on filesystems that do not fill d_type,
  // while Python's `os.scandir` resolves it. Without this fallback the two
  // sides would classify the same entry differently for a correct tree.
  const full = Buffer.concat([dir, FP_PATH_SEP, entry.name])
  try {
    // `lstat`, NOT `stat`: the answer has to be able to come back `l`. A
    // `stat` here follows the link and reports the target's type, so an
    // UNKNOWN dirent that is really a link would be recorded as a directory
    // and then descended into — the same defect this file just removed,
    // surviving in the one branch nobody looks at.
    const st = fs.lstatSync(full)
    if (st.isSymbolicLink()) return 'l'
    if (st.isDirectory()) return 'd'
    if (st.isFile()) return 'f'
  } catch {
    // Unreadable; 'o' on both sides is the answer Python reaches too.
  }
  return 'o'
}

/** `<relpath>\t<kind>` lines for a root's children and its children's children. */
export function fingerprintLines(root: string): Buffer[] {
  const lines: Buffer[] = []
  const rootBuf = Buffer.from(root)
  let top: fs.Dirent<Buffer>[]
  try {
    top = fs.readdirSync(rootBuf, { withFileTypes: true, encoding: 'buffer' })
  } catch {
    return lines
  }
  for (const entry of top) {
    const kind = direntKind(rootBuf, entry)
    lines.push(Buffer.concat([entry.name, FP_TAB, Buffer.from(kind)]))
    // The skip list is ASCII, so a lossy decode cannot invent a match here; the
    // bytes that would decode differently are not in the set either way.
    if (kind !== 'd' || FINGERPRINT_NO_DESCEND.has(entry.name.toString('utf8'))) continue
    // `l` is excluded by this gate as much as `f` and `o` are: a link is never
    // followed, so nothing outside the mount is reachable and no `realpath` is
    // needed to prove it. An earlier version resolved every candidate against
    // the resolved root; that machinery existed only because links counted as
    // directories, and it carried a defect of its own — a workspace at a
    // filesystem root keeps its trailing separator here and does not in the
    // container, so this side refused every descent while the backend
    // performed them (AUDIT R7-02). Not following links removes the question.
    const childDir = Buffer.concat([rootBuf, FP_PATH_SEP, entry.name])
    let children: fs.Dirent<Buffer>[]
    try {
      children = fs.readdirSync(childDir, { withFileTypes: true, encoding: 'buffer' })
    } catch {
      // Contributes no children, matching the backend's own behaviour for a
      // directory it cannot list.
      continue
    }
    for (const child of children) {
      lines.push(Buffer.concat([
        entry.name, FP_SLASH, child.name, FP_TAB, Buffer.from(direntKind(childDir, child)),
      ]))
    }
  }
  // Byte order, not the default sort. JavaScript compares UTF-16 code units and
  // Python compares code points; they disagree above the BMP, so an emoji-named
  // asset folder would sort differently on the two sides and hash differently.
  lines.sort(Buffer.compare)
  return lines
}

export function hostWorkspaceFingerprint(root: string): { entries: number; fingerprint: string } {
  const lines = fingerprintLines(root)
  const parts: Buffer[] = []
  for (const line of lines) {
    if (parts.length) parts.push(FP_NEWLINE)
    parts.push(line)
  }
  const digest = createHash('sha256').update(Buffer.concat(parts)).digest('hex')
  return { entries: lines.length, fingerprint: digest }
}
