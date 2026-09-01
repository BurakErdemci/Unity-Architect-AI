/**
 * Class: stale-preview-state.
 *
 * `previewFile` names a file on disk, so every action that makes that name
 * wrong — switching workspace, deleting the file, renaming it — has to move the
 * preview with it. When it does not, the panel stays mounted on a path that no
 * longer resolves and each reload asks IPC for a file that is gone or belongs
 * to a workspace the user has left.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'

vi.mock('axios', () => ({
  __esModule: true,
  default: { get: vi.fn().mockResolvedValue({ data: {} }), post: vi.fn().mockResolvedValue({ data: {} }) },
}))

// The hook captures `window.ipc` at module load, so it must exist before the
// import below — hence vi.hoisted.
const invoke = vi.hoisted(() => {
  const fn = vi.fn()
  ;(globalThis as any).window.ipc = { invoke: fn }
  return fn
})

import { useFileSystem } from '../renderer/hooks/home/useFileSystem'

const mount = () => renderHook(() => useFileSystem('', null, () => {}))

describe('stale-preview-state', () => {
  beforeEach(() => { invoke.mockReset() })

  it('drops the old preview when the selected workspace changes', async () => {
    invoke.mockImplementation(async (channel: string) => {
      if (channel === 'path-exists') return true
      if (channel === 'read-directory') return []
      throw new Error(`unexpected IPC channel: ${channel}`)
    })

    const { result } = mount()
    act(() => { result.current.openPreview('/workspace-a/Assets/hero.fbx') })
    expect(result.current.previewFile?.path).toBe('/workspace-a/Assets/hero.fbx')

    await act(async () => { await result.current.selectWorkspace('/workspace-b') })

    expect(result.current.workspacePath).toBe('/workspace-b')
    expect(result.current.previewFile).toBeNull()
  })

  it('clears the preview after the previewed file is deleted', async () => {
    invoke.mockImplementation(async (channel: string) => {
      if (channel === 'path-exists') return true
      if (channel === 'read-directory') return []
      if (channel === 'delete-file') return { success: true }
      throw new Error(`unexpected IPC channel: ${channel}`)
    })

    const { result } = mount()
    await act(async () => { await result.current.selectWorkspace('/workspace') })
    act(() => { result.current.openPreview('/workspace/Assets/hero.fbx') })
    expect(result.current.previewFile?.path).toBe('/workspace/Assets/hero.fbx')

    await act(async () => { await result.current.deleteFile('/workspace/Assets/hero.fbx') })

    expect(result.current.previewFile).toBeNull()
  })

  it('leaves an unrelated preview alone when another file is deleted', async () => {
    invoke.mockImplementation(async (channel: string) => {
      if (channel === 'path-exists') return true
      if (channel === 'read-directory') return []
      if (channel === 'delete-file') return { success: true }
      throw new Error(`unexpected IPC channel: ${channel}`)
    })

    const { result } = mount()
    await act(async () => { await result.current.selectWorkspace('/workspace') })
    act(() => { result.current.openPreview('/workspace/Assets/hero.fbx') })

    await act(async () => { await result.current.deleteFile('/workspace/Assets/other.fbx') })

    expect(result.current.previewFile?.path).toBe('/workspace/Assets/hero.fbx')
  })

  // Following the rename rather than clearing it: the main handler reports the
  // exact path it renamed to, which is the path the readers accept back.
  it('follows the previewed file to the path the rename reports', async () => {
    invoke.mockImplementation(async (channel: string) => {
      if (channel === 'path-exists') return true
      if (channel === 'read-directory') return []
      if (channel === 'rename-entry') return { success: true, newPath: '/workspace/Assets/renamed.fbx' }
      throw new Error(`unexpected IPC channel: ${channel}`)
    })

    const { result } = mount()
    await act(async () => { await result.current.selectWorkspace('/workspace') })
    const oldPath = '/workspace/Assets/hero.fbx'
    act(() => { result.current.openPreview(oldPath) })
    act(() => {
      result.current.setRenamingPath(oldPath)
      result.current.setRenameValue('renamed.fbx')
    })

    await act(async () => { await result.current.submitRename() })

    expect(result.current.previewFile).toEqual({ path: '/workspace/Assets/renamed.fbx', name: 'renamed.fbx' })
  })

  // Without a reported new path there is nothing to follow, and a preview
  // pointing at a name that was renamed away is worse than an empty one.
  it('clears the preview when the rename reports no new path', async () => {
    invoke.mockImplementation(async (channel: string) => {
      if (channel === 'path-exists') return true
      if (channel === 'read-directory') return []
      if (channel === 'rename-entry') return { success: true }
      throw new Error(`unexpected IPC channel: ${channel}`)
    })

    const { result } = mount()
    await act(async () => { await result.current.selectWorkspace('/workspace') })
    const oldPath = '/workspace/Assets/hero.fbx'
    act(() => { result.current.openPreview(oldPath) })
    act(() => {
      result.current.setRenamingPath(oldPath)
      result.current.setRenameValue('renamed.fbx')
    })

    await act(async () => { await result.current.submitRename() })

    expect(result.current.previewFile).toBeNull()
  })

  // A renamed FOLDER moves its children too, but their new paths are not
  // reported, so the preview under it can only be cleared.
  it('clears a preview sitting under a renamed folder', async () => {
    invoke.mockImplementation(async (channel: string) => {
      if (channel === 'path-exists') return true
      if (channel === 'read-directory') return []
      if (channel === 'rename-entry') return { success: true, newPath: '/workspace/Models' }
      throw new Error(`unexpected IPC channel: ${channel}`)
    })

    const { result } = mount()
    await act(async () => { await result.current.selectWorkspace('/workspace') })
    act(() => { result.current.openPreview('/workspace/Assets/hero.fbx') })
    act(() => {
      result.current.setRenamingPath('/workspace/Assets')
      result.current.setRenameValue('Models')
    })

    await act(async () => { await result.current.submitRename() })

    expect(result.current.previewFile).toBeNull()
  })

  it('leaves a preview outside the renamed entry untouched', async () => {
    invoke.mockImplementation(async (channel: string) => {
      if (channel === 'path-exists') return true
      if (channel === 'read-directory') return []
      if (channel === 'rename-entry') return { success: true, newPath: '/workspace/Assets/renamed.cs' }
      throw new Error(`unexpected IPC channel: ${channel}`)
    })

    const { result } = mount()
    await act(async () => { await result.current.selectWorkspace('/workspace') })
    act(() => { result.current.openPreview('/workspace/Assets/hero.fbx') })
    act(() => {
      result.current.setRenamingPath('/workspace/Assets/Player.cs')
      result.current.setRenameValue('renamed.cs')
    })

    await act(async () => { await result.current.submitRename() })

    expect(result.current.previewFile?.path).toBe('/workspace/Assets/hero.fbx')
  })
})
