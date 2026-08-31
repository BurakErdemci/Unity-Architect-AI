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
 *
 * Every path that is not a real answer fails CLOSED to `null`: a missing
 * bridge, a rejecting `invoke`, a non-string reply. The main process is the
 * only side that knows how the backend was started, so without its answer this
 * module knows nothing — and "nothing" must never be spelled as the host path,
 * which is precisely the value a Docker backend cannot address.
 *
 * An intermediate version returned the host path when the bridge was ABSENT,
 * on the argument that no bridge means no Electron and therefore nothing
 * containerised. That argument does not hold: an absent `window.ipc` is also
 * what a failed preload looks like inside a real Electron window, and the two
 * are indistinguishable from here. Measured 31 Aug 2026: in that state the
 * request is still sent, because `useAuth` falls back to the session token
 * `'local'`, and the only thing that stops the bad value reaching the database
 * is the backend answering 401. Relying on another layer's rejection is not a
 * guard — it is a coincidence that a config change can remove.
 *
 * The cost is stated plainly: rendering this UI outside Electron loses
 * workspace persistence. That is not a supported way to run the product (file
 * access, the terminal and the app token all come through the same bridge), so
 * the trade is a mode that does not exist against a defect that does.
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
  if (!ipc) return null;   // no bridge = no answer; see the note above
  try {
    const mapped = await ipc.invoke('backend-workspace-path', hostPath);
    if (typeof mapped !== 'string') return null;
    return mapped === '' ? null : mapped;
  } catch {
    // The bridge exists but failed to answer: unknown, not identity. Returning
    // the host path here is exactly the aliasing bug this module exists to
    // close, just reached through a different door than a missing bridge.
    return null;
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
  if (!ipc) return null;   // no bridge = no answer; see the note above
  try {
    const mapped = await ipc.invoke('host-workspace-path', backendPath);
    if (typeof mapped !== 'string') return null;
    return mapped === '' ? null : mapped;
  } catch {
    // Same reasoning as backendWorkspacePath: a failed bridge is unknown, not
    // identity, so it fails closed rather than handing back an unresolved path.
    return null;
  }
}
