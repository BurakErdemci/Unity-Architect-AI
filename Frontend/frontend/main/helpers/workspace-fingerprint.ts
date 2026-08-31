/**
 * The `gamachine-ws-fp-1` workspace fingerprint, host side.
 *
 * Split out of `background.ts` so a test can RUN it. There are two
 * implementations of this algorithm — this one and `_fingerprint_lines` in
 * `Backend/app/routes/auth_routes.py` — and they are compared at Docker startup
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
// Mirrors `_NO_DESCEND` in Backend/app/routes/auth_routes.py. Both sides list
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

export function direntKind(dir: Buffer, entry: fs.Dirent<Buffer>): string {
  // Link-ness is NOT part of the fingerprint — see `_kind` in
  // Backend/app/routes/auth_routes.py for the full reasoning. Short version,
  // measured 31 Aug 2026 by the parity test: `isSymbolicLink()` is true for any
  // Windows reparse point, so a directory junction read `l` here and `d` on the
  // Python side, and in production the container sees that same junction as an
  // ordinary directory through Docker Desktop's translation layer. Encoding it
  // made the guard refuse a correct setup.
  const full = Buffer.concat([dir, FP_PATH_SEP, entry.name])
  if (entry.isSymbolicLink()) {
    // Follow it, the way `os.DirEntry.is_dir()` does by default.
    try {
      const st = fs.statSync(full)
      if (st.isDirectory()) return 'd'
      if (st.isFile()) return 'f'
    } catch {
      // A broken link resolves to nothing on either side.
    }
    return 'o'
  }
  if (entry.isDirectory()) return 'd'
  if (entry.isFile()) return 'f'
  // A dirent can come back UNKNOWN on filesystems that do not fill d_type, and
  // Node does not stat to resolve it while Python's os.scandir does. Without
  // this fallback the two sides would classify the same entry differently and
  // report a mismatch for the correct tree.
  try {
    // `stat`, not `lstat`: same "classify by behaviour" rule as above, and the
    // same reason. An lstat here could still answer `l`, which is the one
    // answer the two sides are not allowed to disagree about.
    const st = fs.statSync(full)
    if (st.isDirectory()) return 'd'
    if (st.isFile()) return 'f'
  } catch {
    // Unreadable; 'o' on both sides is the same answer Python reaches.
  }
  return 'o'
}

/**
 * Does `full` resolve to something still under `rootReal`?
 *
 * This is the descent rule, and it is phrased in terms of the RESOLVED TARGET
 * rather than link-ness on purpose. Measured 31 Aug 2026, on one Windows
 * directory junction, with the two shipped runtimes:
 *
 *     Node   isSymbolicLink() -> true
 *     Python is_symlink()     -> False
 *
 * So the two sides do not agree on what a link IS, and any rule of the form
 * "if it is a link, do not descend" makes them walk different trees and report
 * a mismatch for a correct setup — the very failure this guard exists to
 * prevent, reintroduced by its own fix. The earlier `l` kind died of the same
 * cause. Containment is the one question both runtimes answered identically in
 * that measurement (in-root junction: inside on both; out-of-root junction:
 * outside on both), because both resolve reparse points and both canonicalise
 * case, so the rule is built on containment.
 *
 * What this buys (AUDIT R6-01): once `direntKind` began following links, a
 * top-level junction pointing out of the workspace was classified `d` and then
 * descended into, so files outside the mount entered a fingerprint whose whole
 * claim is to describe the workspace, with unbounded breadth — a link to a
 * large external tree was enumerated on every Docker start.
 *
 * Boundary, stated rather than pretended: for a link whose target leaves the
 * mount the two sides are NOT guaranteed to agree, because the container may
 * see that same path as an ordinary directory through Docker Desktop's
 * translation layer and descend. That case could not be measured (no daemon
 * was reachable on 31 Aug 2026), so it is documented as outside the guarantee
 * rather than claimed either way. Its failure mode is a loud mismatch at
 * startup, not a wrong tree accepted in silence.
 *
 * Kept in bytes like everything else here, and `realpath` is asked only for
 * level-1 directories we are about to descend into — a handful per project,
 * not once per entry.
 */
function staysInside(rootReal: Buffer, full: Buffer): boolean {
  let target: Buffer
  try {
    target = fs.realpathSync.native(full, 'buffer') as Buffer
  } catch {
    // Unresolvable: contributes no children, the same as a directory we cannot
    // list below.
    return false
  }
  if (target.equals(rootReal)) return true
  const sepAt = rootReal.length
  return target.length > sepAt + FP_PATH_SEP.length
    && target.subarray(0, sepAt).equals(rootReal)
    && target.subarray(sepAt, sepAt + FP_PATH_SEP.length).equals(FP_PATH_SEP)
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
  // Without a resolved root there is nothing to be inside of, so no descent is
  // possible; the level-1 listing is still meaningful. Mirrors `root_real =
  // None` in Backend/app/workspace_fingerprint.py.
  let rootReal: Buffer | null = null
  try {
    rootReal = fs.realpathSync.native(rootBuf, 'buffer') as Buffer
  } catch {
    rootReal = null
  }
  for (const entry of top) {
    const kind = direntKind(rootBuf, entry)
    lines.push(Buffer.concat([entry.name, FP_TAB, Buffer.from(kind)]))
    // The skip list is ASCII, so a lossy decode cannot invent a match here; the
    // bytes that would decode differently are not in the set either way.
    if (kind !== 'd' || FINGERPRINT_NO_DESCEND.has(entry.name.toString('utf8'))) continue
    const childDir = Buffer.concat([rootBuf, FP_PATH_SEP, entry.name])
    if (rootReal === null || !staysInside(rootReal, childDir)) continue
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
