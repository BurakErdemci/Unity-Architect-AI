/**
 * Pure host↔container workspace path mapping.
 *
 * Split out of `background.ts` so it can be tested by BEHAVIOUR. It used to
 * live inline in the IPC handlers, where the only reachable assertion was
 * "the source contains `return ''`" — and a mutation proved that worthless:
 * the handler had two such returns, so breaking one left the test green
 * (measured 31 Aug 2026, during the mutation round of the fix it was meant to
 * protect).
 *
 * Every function here is total and side-effect free. `''` always means **there
 * is no answer**, never "use the input".
 */
import path from 'path'

/** Where docker-compose.yml mounts the workspace inside the container. */
export const DOCKER_WORKSPACE_MOUNT = '/workspace'

/**
 * The host side of the mount, or `''` when it cannot be known.
 *
 * A relative `GAMACHINE_WORKSPACE` is refused rather than resolved: Compose
 * resolves it against the Compose project directory while Electron runs from
 * `Frontend/frontend`, so the same string names two different folders. Guessing
 * dropped the user's last workspace on every launch.
 */
export function hostRootFrom(raw: string | undefined): string {
  if (!raw || !path.isAbsolute(raw)) return ''
  return path.resolve(raw)
}

/**
 * A host path as the backend should see it, or `''` when the backend has no
 * name for it.
 *
 * Docker exposes exactly ONE host tree. Returning the mount for any folder was
 * the first version, and it aliased every project onto the mounted one: pick
 * project B while Compose mounts A, and the editor works in B while every
 * agent, command and backend file tool works in A — both halves reporting
 * success.
 */
export function toBackendPath(hostPath: string, hostRoot: string): string {
  if (!hostPath) return ''
  if (!hostRoot) return ''
  const rel = path.relative(hostRoot, path.resolve(hostPath))
  // A real child can legitimately be named `..project` — `path.relative`
  // returns `..project` for it, and a bare `rel.startsWith('..')` refused it.
  // The boundary is a `..` segment, not a `..`-prefixed string.
  if (rel === '..' || rel.startsWith(`..${path.sep}`) || rel.startsWith('../') || path.isAbsolute(rel)) return ''
  // POSIX separators: the answer is consumed inside a Linux container.
  return rel ? `${DOCKER_WORKSPACE_MOUNT}/${rel.split(path.sep).join('/')}`
             : DOCKER_WORKSPACE_MOUNT
}

/**
 * A backend path turned back into something this process can open, or `''`.
 *
 * Anything not under the mount is refused rather than passed through: such a
 * value is either from before this translation existed or from a run
 * configured against a different project, and opening it would put the editor
 * on one tree while the backend works on another.
 */
export function toHostPath(backendPath: string, hostRoot: string): string {
  if (!backendPath || !hostRoot) return ''
  if (backendPath === DOCKER_WORKSPACE_MOUNT) return hostRoot
  const prefix = `${DOCKER_WORKSPACE_MOUNT}/`
  if (!backendPath.startsWith(prefix)) return ''
  const candidate = path.join(hostRoot, ...backendPath.slice(prefix.length).split('/'))
  // `path.join` collapses `..` segments, so a suffix like `../other` (or, on
  // Windows, a host-native `\`-joined `..\other`) can land OUTSIDE hostRoot
  // while still passing the prefix check above. Confirm containment on the
  // JOINED result rather than trusting the prefix alone.
  const rel = path.relative(hostRoot, candidate)
  if (rel === '..' || rel.startsWith(`..${path.sep}`) || path.isAbsolute(rel)) return ''
  return candidate
}
