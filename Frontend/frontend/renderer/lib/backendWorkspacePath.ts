/**
 * Translates a workspace path from THIS process's view of the disk into the
 * backend's view of it.
 *
 * On the normal path the two views are identical and this returns the argument
 * untouched. In Docker mode they are not: the folder picker yields a host path
 * (`C:\Users\me\Game`, `/home/me/game`) and the backend lives in a container
 * where only the bind mount exists. Sending the host path is what an audit
 * caught on 31 Aug 2026 — the mount was configured, the contract test was
 * green, and every backend file operation addressed a path nothing in the
 * container could resolve.
 *
 * The main process owns the answer because it is the only side that knows how
 * the backend was started.
 */
const ipc = typeof window !== 'undefined' ? (window as any).ipc : null;

export async function backendWorkspacePath(hostPath: string): Promise<string> {
  if (!hostPath || !ipc) return hostPath;
  try {
    const mapped = await ipc.invoke('backend-workspace-path', hostPath);
    return typeof mapped === 'string' && mapped ? mapped : hostPath;
  } catch {
    // Falling back to the host path is right for the normal case and wrong for
    // Docker mode, but the channel is whitelisted and its handler is registered
    // before any window exists, so a throw here means something far more broken
    // than a workspace path. Failing closed would break the app everyone uses
    // to protect the mode almost nobody runs.
    return hostPath;
  }
}

/**
 * The reverse: a path the backend stored, turned back into something this
 * process can open. Returns '' when Docker mode cannot know the host side,
 * which callers must treat as "no last workspace" rather than a valid path.
 */
export async function hostWorkspacePath(backendPath: string): Promise<string> {
  if (!backendPath || !ipc) return backendPath;
  try {
    const mapped = await ipc.invoke('host-workspace-path', backendPath);
    return typeof mapped === 'string' ? mapped : backendPath;
  } catch {
    return backendPath;
  }
}
