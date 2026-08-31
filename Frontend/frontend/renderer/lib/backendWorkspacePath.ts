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
 *
 * `null` means **there is no answer**, not "use what you had". Docker mounts
 * exactly one tree; a folder outside it cannot be named to the backend at all.
 * The first version returned the host path in that case, which aliased every
 * project onto the mounted one: the editor worked in the folder you picked
 * while every agent and file tool worked in a different one, both reporting
 * success. Callers must treat `null` as "do not tell the backend anything".
 */
// Cagri aninda okunuyor, modul yuklenirken DEGIL. Uygulamada preload her zaman
// once kosuyor, ama erken baglama koprunun ne zaman kuruldugu hakkinda sessiz
// bir varsayim; olculdu (31 Agu 2026): boyle bir testte kopru hic gorulmuyor ve
// fonksiyon ceviri yapmadan girdisini donduruyor — yani ADLANDIRAMADIGI bir
// yolu gecerli diye raporluyor, ki bu tam da kapatilmak istenen sinif.
const getIpc = () => (typeof window !== 'undefined' ? (window as any).ipc : null);

export async function backendWorkspacePath(hostPath: string): Promise<string | null> {
  if (!hostPath) return hostPath;
  const ipc = getIpc();
  if (!ipc) return hostPath;   // no Electron: nothing is containerised
  try {
    const mapped = await ipc.invoke('backend-workspace-path', hostPath);
    if (typeof mapped !== 'string') return hostPath;
    return mapped === '' ? null : mapped;
  } catch {
    // The channel is whitelisted and its handler is registered before any
    // window exists, so a throw here means something far more broken than a
    // workspace path. Failing closed would break the app everyone uses to
    // protect the mode almost nobody runs.
    return hostPath;
  }
}

/**
 * The reverse: a path the backend stored, turned back into something this
 * process can open. `null` when Docker mode cannot know the host side — an
 * unset or relative `GAMACHINE_WORKSPACE`, or a value stored before this
 * translation existed. Callers must treat it as "no last workspace" rather
 * than as a path.
 */
export async function hostWorkspacePath(backendPath: string): Promise<string | null> {
  if (!backendPath) return backendPath;
  const ipc = getIpc();
  if (!ipc) return backendPath;
  try {
    const mapped = await ipc.invoke('host-workspace-path', backendPath);
    if (typeof mapped !== 'string') return backendPath;
    return mapped === '' ? null : mapped;
  } catch {
    return backendPath;
  }
}
