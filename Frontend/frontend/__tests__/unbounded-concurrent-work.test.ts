import fs from 'fs'
import os from 'os'
import path from 'path'
import { afterAll, describe, expect, it, vi } from 'vitest'
import { MODEL_READ_MAX_IN_FLIGHT } from '../main/helpers/file-security'

/**
 * Unbounded in-flight model reads, from an external audit probe.
 *
 * The per-file cap was the channel's only bound, so N concurrent at-the-cap
 * calls held N x 64 MiB in the main process and froze it linearly — 8 calls
 * measured at 512 MiB and 120 ms during which no other IPC call, menu action or
 * window event was served.
 *
 * The test fires the burst against the REGISTERED handler but with tiny files:
 * what has to hold is the admission bound, and allocating half a gigabyte to
 * re-observe a number already measured would only make the suite slow. The
 * measurement that chose the limit lives with the constant.
 */

const handlers = new Map<string, (...args: any[]) => any>()
vi.mock('electron', () => ({
  app: {
    getPath: vi.fn(() => os.tmpdir()), setPath: vi.fn(),
    requestSingleInstanceLock: vi.fn(() => false), quit: vi.fn(), on: vi.fn(),
  },
  ipcMain: { handle: vi.fn((channel: string, listener: (...args: any[]) => any) => handlers.set(channel, listener)) },
  dialog: {}, shell: {}, BrowserWindow: { getAllWindows: vi.fn(() => []) },
}))
vi.mock('electron-serve', () => ({ default: vi.fn() }))
vi.mock('electron-updater', () => ({ autoUpdater: {} }))
vi.mock('node-pty', () => ({ spawn: vi.fn() }))
vi.mock('../main/helpers', () => ({ createWindow: vi.fn() }))
vi.mock('../main/helpers/ipc-trust', () => ({
  confirmLegacyRoot: vi.fn(() => false), isOwnFrame: vi.fn(() => true),
  isTrustedRoot: vi.fn(() => true), registerTrustedRoot: vi.fn(),
}))
vi.mock('../main/helpers/csp', () => ({ applyContentSecurityPolicy: vi.fn() }))

const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'model-inflight-'))
afterAll(() => { try { fs.rmSync(dir, { recursive: true, force: true }) } catch { /* best effort */ } })

const BURST = 8
const event = { senderFrame: { url: 'app://./home' } }

async function registeredModelHandler() {
  const originalAppend = fs.appendFileSync.bind(fs)
  vi.spyOn(fs, 'appendFileSync').mockImplementation(((file: fs.PathOrFileDescriptor, data: any, options?: any) => {
    if (typeof file === 'string' && file.endsWith('gamachine.log')) return
    return originalAppend(file, data, options)
  }) as typeof fs.appendFileSync)
  await import('../main/background')
  const listener = handlers.get('read-model-file')
  expect(listener).toBeTypeOf('function')
  return listener!
}

function models(count: number): string[] {
  return Array.from({ length: count }, (_, i) => {
    const p = path.join(dir, `m${i}.glb`)
    fs.writeFileSync(p, Buffer.from([0x67, 0x6c, 0x54, 0x46, i]))
    return p
  })
}

describe('unbounded-concurrent-work', () => {
  it('serves no more model reads at once than the in-flight limit', async () => {
    const listener = await registeredModelHandler()
    const files = models(BURST)

    const results: any[] = await Promise.all(files.map((p) => listener(event, p, dir)))

    const served = results.filter((r) => r && r.data)
    const refused = results.filter((r) => r && r.error === 'busy')
    expect(served.length).toBe(MODEL_READ_MAX_IN_FLIGHT)
    expect(refused.length).toBe(BURST - MODEL_READ_MAX_IN_FLIGHT)
    // Nothing that WAS served came back damaged by the limiter.
    for (const r of served) expect(r.data.byteLength).toBe(5)
  })

  // A limit that never released would turn the channel off after the first
  // burst, which is a worse failure than the one being fixed.
  it('releases each slot, so sequential reads all succeed', async () => {
    const listener = await registeredModelHandler()
    const files = models(BURST)

    for (const p of files) {
      const result: any = await listener(event, p, dir)
      expect(result.error).toBeUndefined()
      expect(result.data.byteLength).toBe(5)
    }
  })
})
