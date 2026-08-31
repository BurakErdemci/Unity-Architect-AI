/**
 * The `gamachine-ws-fp-2` workspace fingerprint, host side.
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

export const WORKSPACE_FINGERPRINT_ALGO = 'gamachine-ws-fp-2'

// Docker Desktop cannot store a name containing a character NTFS forbids, so it
// shifts each one into the private use area by exactly 0xF000. Measured 31 Aug
// 2026 by creating one file per candidate inside the container on a real
// Windows-backed mount and reading the directory back from here: all 39
// affected characters — the C0 controls 0x01-0x1F plus `" * : < > ? \ |` —
// moved, every one by the same 0xF000, and nothing else moved.
//
// Both sides undo it, so both hash the same name (AUDIT R9-01). Undoing on one
// side only would leave this side hashing `ab` while the container hashes
// `a<TAB>b` for the SAME file — a refused correct mount.
//
// It is a real conflation: a name genuinely containing U+F009 hashes like a
// name containing a tab. Deliberate, and it follows the rule this file already
// lives by — NTFS stores both as U+F009, so this side CANNOT tell them apart
// and the distinction is not one both sides can make.
//
// Done in bytes because that is what everything here handles. U+F000..U+F07F
// encodes as EF 80 80 .. EF 81 BF, and the low seven bits of the result live in
// the last two bytes, so every measured replacement is a single byte.
//
// Keep the measured offsets as an explicit list, not a range. The previous
// range generalized a concrete measurement and swallowed `/`, manufacturing a
// path separator from the legal filename character U+F02F.
function unproject(name: Buffer): Buffer {
  let ilk = -1
  for (let i = 0; i + 2 < name.length; i++) {
    if (name[i] === 0xEF && (name[i + 1] === 0x80 || name[i + 1] === 0x81)) { ilk = i; break }
  }
  if (ilk < 0) return name
  const projectedOffsets = new Set([
    0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
    0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x10,
    0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18,
    0x19, 0x1A, 0x1B, 0x1C, 0x1D, 0x1E, 0x1F,
    0x22, 0x2A, 0x3A, 0x3C, 0x3E, 0x3F, 0x5C, 0x7C,
  ])
  const out = Buffer.alloc(name.length)
  let w = 0
  for (let i = 0; i < name.length;) {
    if (i + 2 < name.length && name[i] === 0xEF
      && (name[i + 1] === 0x80 || name[i + 1] === 0x81)
      && (name[i + 2] & 0xC0) === 0x80) {
      const n = ((name[i + 1] & 0x03) << 6) | (name[i + 2] & 0x3F)
      if (projectedOffsets.has(n)) {
        out[w++] = n
        i += 3
        continue
      }
    }
    out[w++] = name[i++]
  }
  return out.subarray(0, w)
}
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
// NUL, not a tab, and the records are concatenated with nothing between them.
// NUL is the one byte a filename cannot contain on either platform, so
// `<relpath>\0<kind>` records parse back one way only and the digest is
// injective.
//
// The previous encoding used a tab between path and kind and a newline between
// records, and neither was escaped while both are legal in a POSIX filename.
// Measured 31 Aug 2026 (AUDIT R9-01) on a real bind mount: one file named
// `a<TAB>f<LF>b` hashed identically to two files named `a` and `b`, and
// `background.ts` accepts on digest equality alone — so a wrong mount passed.
const FP_NUL = Buffer.from([0])
const FP_SLASH = Buffer.from('/')
const FP_PATH_SEP = Buffer.from(path.sep)

/**
 * `d` plain directory, `f` plain file, `o` anything else. Mirrors `kind` in
 * Backend/app/workspace_fingerprint.py, which carries the full reasoning.
 *
 * THE RULE: the fingerprint encodes only distinctions BOTH SIDES CAN MAKE.
 * Anything that is not a plain directory or a plain file collapses into `o`,
 * and `o` is never descended into.
 *
 * A separate `l` kind was tried and measured against a real container on 31 Aug
 * 2026. It agreed for symlinks and junctions and FAILED for a FIFO and a Unix
 * socket: this side answered `l` for both while the container answered `o`, so
 * a workspace containing either was refused. The cause is that Windows cannot
 * tell those objects apart at all — Docker Desktop stores symlinks, FIFOs and
 * sockets alike as reparse points, and `Dirent.isSymbolicLink()` collapses
 * every reparse tag into "link". Merging into `o` is the symmetric answer and
 * holds on a Linux host too, where a FIFO reaches `o` through the fallback
 * below rather than through the link check.
 *
 * Link TARGETS are absent on purpose: the same junction is spelled `C:\...`
 * here and arrives in the container as an unreachable `/mnt/host/c/...`, so
 * hashing targets would guarantee the mismatch this check exists to prevent.
 */
export function direntKind(dir: Buffer, entry: fs.Dirent<Buffer>): string {
  // Asked FIRST. `isDirectory()` on a dirent does not follow, but the fallback
  // below would, and a link answering `d` is a link that gets descended into.
  if (entry.isSymbolicLink()) return 'o'
  if (entry.isDirectory()) return 'd'
  if (entry.isFile()) return 'f'
  // A dirent can come back UNKNOWN on filesystems that do not fill d_type,
  // while Python's `os.scandir` resolves it. Without this fallback the two
  // sides would classify the same entry differently for a correct tree.
  const full = Buffer.concat([dir, FP_PATH_SEP, entry.name])
  try {
    // `lstat`, NOT `stat`: `stat` follows the link and reports the TARGET's
    // type, so an UNKNOWN dirent that is really a link to a directory would be
    // recorded as `d` and then descended into — the defect this file removed,
    // surviving in the one branch nobody looks at.
    const st = fs.lstatSync(full)
    if (st.isSymbolicLink()) return 'o'
    if (st.isDirectory()) return 'd'
    if (st.isFile()) return 'f'
  } catch {
    // Unreadable; `o` is the answer the container reaches for it too.
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
    lines.push(Buffer.concat([unproject(entry.name), FP_NUL, Buffer.from(kind)]))
    // The skip list is ASCII, so a lossy decode cannot invent a match here; the
    // bytes that would decode differently are not in the set either way.
    if (kind !== 'd' || FINGERPRINT_NO_DESCEND.has(entry.name.toString('utf8'))) continue
    // Only a plain directory is descended into, so a link cannot be followed
    // and nothing outside the mount is reachable — no `realpath` is needed to
    // prove it. An earlier version resolved every candidate against
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
        unproject(entry.name), FP_SLASH, unproject(child.name),
        FP_NUL, Buffer.from(direntKind(childDir, child)),
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
  // Concatenated with NOTHING between records: each already ends `\0<kind>`,
  // and NUL cannot occur in a name, so the stream parses back one way only.
  // Mirrors `fingerprint_digest` in Backend/app/workspace_fingerprint.py.
  const digest = createHash('sha256').update(Buffer.concat(lines)).digest('hex')
  return { entries: lines.length, fingerprint: digest }
}
