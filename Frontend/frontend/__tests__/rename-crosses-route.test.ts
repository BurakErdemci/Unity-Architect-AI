/**
 * A rename can move a path across the text/preview route boundary. Following
 * the rename blindly left the content area showing the wrong surface:
 * `previewFile` stayed set over a text path (verification probe, 2 Sep 2026)
 * and, symmetrically, the editor would keep a buffer for a path the readers
 * now route to a binary preview channel. Both directions are covered here so
 * the class closes, not just the reported path.
 */
import { expect, it, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'

vi.mock('axios', () => ({
  __esModule: true,
  default: { get: vi.fn().mockResolvedValue({ data: {} }), post: vi.fn().mockResolvedValue({ data: {} }) },
}))
vi.mock('../renderer/components/ui/ConfirmDialog', () => ({ confirmDialog: vi.fn().mockResolvedValue(true) }))
const invoke = vi.hoisted(() => {
  const fn = vi.fn()
  ;(globalThis as any).window.ipc = { invoke: fn }
  return fn
})

import { useFileSystem } from '../renderer/hooks/home/useFileSystem'

const ipcFor = (renamedTo: string) => async (channel: string) => {
  if (channel === 'path-exists') return true
  if (channel === 'read-directory') return []
  if (channel === 'git-status') return { isRepo: false, files: {}, dirs: {} }
  if (channel === 'rename-entry') return { success: true, newPath: renamedTo }
  if (channel === 'read-file') return { path: '/workspace/Assets/note.cs', name: 'note.cs', content: 'x' }
  throw new Error(`unexpected IPC channel: ${channel}`)
}

it('a previewed image renamed to a text extension leaves preview mode', async () => {
  invoke.mockImplementation(ipcFor('/workspace/Assets/inside.cs'))
  const { result } = renderHook(() => useFileSystem('', null, () => {}))
  await act(async () => { await result.current.selectWorkspace('/workspace') })
  const oldPath = '/workspace/Assets/inside.png'
  act(() => {
    result.current.openPreview(oldPath)
    result.current.setRenamingPath(oldPath)
    result.current.setRenameValue('inside.cs')
  })
  await act(async () => { await result.current.submitRename() })
  expect(result.current.previewFile).toBeNull()
})

it('a previewed image renamed to another image extension keeps the preview and follows the path', async () => {
  invoke.mockImplementation(ipcFor('/workspace/Assets/inside.webp'))
  const { result } = renderHook(() => useFileSystem('', null, () => {}))
  await act(async () => { await result.current.selectWorkspace('/workspace') })
  const oldPath = '/workspace/Assets/inside.png'
  act(() => {
    result.current.openPreview(oldPath)
    result.current.setRenamingPath(oldPath)
    result.current.setRenameValue('inside.webp')
  })
  await act(async () => { await result.current.submitRename() })
  expect(result.current.previewFile).toEqual({ path: '/workspace/Assets/inside.webp', name: 'inside.webp' })
})

it('an editor buffer renamed to a binary extension is closed rather than followed', async () => {
  invoke.mockImplementation(ipcFor('/workspace/Assets/note.png'))
  const { result } = renderHook(() => useFileSystem('', null, () => {}))
  await act(async () => { await result.current.selectWorkspace('/workspace') })
  const oldPath = '/workspace/Assets/note.cs'
  await act(async () => { await result.current.openFile(oldPath) })
  expect(result.current.openedFilePath).toBe(oldPath)
  act(() => {
    result.current.setRenamingPath(oldPath)
    result.current.setRenameValue('note.png')
  })
  await act(async () => { await result.current.submitRename() })
  expect(result.current.openedFilePath).toBeNull()
  expect(result.current.previewFile).toBeNull()
})
