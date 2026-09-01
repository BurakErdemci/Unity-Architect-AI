import fs from 'fs'
import os from 'os'
import path from 'path'
import { afterAll, expect, it, vi } from 'vitest'
import { TEXT_MAX_BYTES } from '../main/helpers/file-security'

/**
 * Growth race on the text read channel, from an external audit probe.
 *
 * The handler checked the descriptor size and then read until EOF, so bytes
 * appended between the two came back with the rest and the returned string
 * could exceed the cap the check had just enforced. The model path never had
 * this: it reads exactly the size it checked. The test drives the REGISTERED
 * handler, because the cap and the read live there.
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

const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'text-growth-'))
afterAll(() => { try { fs.rmSync(dir, { recursive: true, force: true }) } catch { /* best effort */ } })

it('returns no bytes appended after the text size check', async () => {
  // The main process rewires console.* onto a log file at import; keeping that
  // append out of the real filesystem is the only reason for this spy.
  const originalAppend = fs.appendFileSync.bind(fs)
  vi.spyOn(fs, 'appendFileSync').mockImplementation(((file: fs.PathOrFileDescriptor, data: any, options?: any) => {
    if (typeof file === 'string' && file.endsWith('gamachine.log')) return
    return originalAppend(file, data, options)
  }) as typeof fs.appendFileSync)

  await import('../main/background')
  const listener = handlers.get('read-file')
  expect(listener).toBeTypeOf('function')

  const file = path.join(dir, 'growing.txt')
  fs.writeFileSync(file, 'x')

  // Another local writer appends 9 MiB in the window between the size check and
  // the read — the exact interleaving the handler has no lock against.
  const originalFstat = fs.fstatSync.bind(fs)
  let grown = false
  vi.spyOn(fs, 'fstatSync').mockImplementation(((fd: number, options?: any) => {
    const stat = originalFstat(fd, options)
    if (!grown) {
      grown = true
      originalAppend(file, Buffer.alloc(9 * 1024 * 1024, 0x61))
    }
    return stat
  }) as typeof fs.fstatSync)

  const result = await listener!({ senderFrame: { url: 'app://./home' } }, file, dir)

  expect(result.content.length).toBeLessThanOrEqual(TEXT_MAX_BYTES)
  // Exactly the size the cap was checked against, not "whatever is there now".
  expect(result.content).toBe('x')
})
