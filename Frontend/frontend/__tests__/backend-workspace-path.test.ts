/**
 * backendWorkspacePath / hostWorkspacePath — fail-open vs fail-closed.
 *
 * Finding 5 (audit, 31 Aug 2026): the translator returned the untranslated
 * host path on THREE different situations — no IPC bridge, a rejecting
 * bridge, and a non-string answer — so a caller could not tell "not Docker,
 * identity is correct" from "Docker, but the translator broke". Only the
 * first is identity; the other two are unknown and must fail closed to
 * `null`, matching the module's own contract ("`null` means there is no
 * answer, not use what you had").
 *
 * The module reads `window.ipc` at CALL time, not at module load, so
 * `(window as any).ipc` can be set per-test without re-importing.
 */
import { describe, it, expect, afterEach } from 'vitest';
import { backendWorkspacePath, hostWorkspacePath } from '../renderer/lib/backendWorkspacePath';

const HOST_PATH = 'C:\\Users\\me\\Game';
const BACKEND_PATH = '/workspace';

// `window.ipc` is undefined in the jsdom baseline; every test that sets it
// must restore that baseline so later tests see the same "no bridge" state
// they'd get from a fresh module load.
const orijinalIpc = (window as any).ipc;
afterEach(() => {
  (window as any).ipc = orijinalIpc;
});

describe('backendWorkspacePath', () => {
  it('no bridge: unknown, fails closed to null', async () => {
    // An absent `window.ipc` was read as "not Electron, so nothing is
    // containerised" and answered with identity. It is also what a failed
    // preload looks like inside a real Electron window, and the two cannot be
    // told apart from here. Measured 31 Aug 2026: in that state the request is
    // still sent (useAuth falls back to the token 'local') and only the
    // backend's 401 keeps the unaddressable path out of the database — another
    // layer's rejection, not a guard of ours.
    delete (window as any).ipc;
    await expect(backendWorkspacePath(HOST_PATH)).resolves.toBeNull();
  });

  it('rejecting bridge: unknown, fails closed to null', async () => {
    (window as any).ipc = { invoke: async () => { throw new Error('IPC kanalı çöktü'); } };
    await expect(backendWorkspacePath(HOST_PATH)).resolves.toBeNull();
  });

  it('non-string answer: unknown, fails closed to null', async () => {
    (window as any).ipc = { invoke: async () => 42 };
    await expect(backendWorkspacePath(HOST_PATH)).resolves.toBeNull();
  });

  it('normal translated case: bridge answers with a string', async () => {
    (window as any).ipc = { invoke: async (_channel: string, hostPath: string) => {
      expect(hostPath).toBe(HOST_PATH);
      return BACKEND_PATH;
    } };
    await expect(backendWorkspacePath(HOST_PATH)).resolves.toBe(BACKEND_PATH);
  });
});

describe('hostWorkspacePath', () => {
  it('no bridge: unknown, fails closed to null', async () => {
    // Same reasoning as the forward direction above.
    delete (window as any).ipc;
    await expect(hostWorkspacePath(BACKEND_PATH)).resolves.toBeNull();
  });

  it('rejecting bridge: unknown, fails closed to null', async () => {
    (window as any).ipc = { invoke: async () => { throw new Error('IPC kanalı çöktü'); } };
    await expect(hostWorkspacePath(BACKEND_PATH)).resolves.toBeNull();
  });

  it('non-string answer: unknown, fails closed to null', async () => {
    (window as any).ipc = { invoke: async () => ({ not: 'a string' }) };
    await expect(hostWorkspacePath(BACKEND_PATH)).resolves.toBeNull();
  });

  it('normal translated case: bridge answers with a string', async () => {
    (window as any).ipc = { invoke: async (_channel: string, backendPath: string) => {
      expect(backendPath).toBe(BACKEND_PATH);
      return HOST_PATH;
    } };
    await expect(hostWorkspacePath(BACKEND_PATH)).resolves.toBe(HOST_PATH);
  });
});
