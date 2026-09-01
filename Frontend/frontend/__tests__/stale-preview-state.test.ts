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
vi.mock('../renderer/components/ui/ConfirmDialog', () => ({
  confirmDialog: vi.fn().mockResolvedValue(true),
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

const ertelenmis = <T,>() => {
  let coz!: (v: T) => void
  const sozu = new Promise<T>(r => { coz = r })
  return { sozu, coz }
}

const agacGirdisi = (yol: string) => ({
  name: yol.split('/').pop() as string,
  path: yol,
  isDirectory: false,
  extension: `.${yol.split('.').pop()}`,
})

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

  // The tree context menu is the OTHER way to delete. It was left out when the
  // direct `deleteFile` path was closed, so the preview stayed mounted on a file
  // that no longer existed — reachable from the same right-click that deleted it.
  it('clears the preview when its file is deleted from the tree context menu', async () => {
    invoke.mockImplementation(async (channel: string) => {
      if (channel === 'path-exists') return true
      if (channel === 'read-directory') return []
      if (channel === 'git-status') return { isRepo: false, files: {}, dirs: {} }
      if (channel === 'delete-entry') return { success: true }
      throw new Error(`unexpected IPC channel: ${channel}`)
    })

    const { result } = mount()
    await act(async () => { await result.current.selectWorkspace('/workspace') })
    const yol = '/workspace/Assets/hero.fbx'
    act(() => { result.current.openPreview(yol) })

    await act(async () => { await result.current.handleTreeDelete(agacGirdisi(yol)) })

    expect(result.current.previewFile).toBeNull()
  })

  // Unlike the direct delete, this entry point can remove a FOLDER, and every
  // path beneath it goes with it.
  it('clears a preview sitting under a folder deleted from the tree', async () => {
    invoke.mockImplementation(async (channel: string) => {
      if (channel === 'path-exists') return true
      if (channel === 'read-directory') return []
      if (channel === 'git-status') return { isRepo: false, files: {}, dirs: {} }
      if (channel === 'delete-entry') return { success: true }
      throw new Error(`unexpected IPC channel: ${channel}`)
    })

    const { result } = mount()
    await act(async () => { await result.current.selectWorkspace('/workspace') })
    act(() => { result.current.openPreview('/workspace/Assets/hero.fbx') })

    await act(async () => {
      await result.current.handleTreeDelete({
        name: 'Assets', path: '/workspace/Assets', isDirectory: true, extension: '',
      })
    })

    expect(result.current.previewFile).toBeNull()
  })

  it('leaves an unrelated preview alone when another entry is deleted from the tree', async () => {
    invoke.mockImplementation(async (channel: string) => {
      if (channel === 'path-exists') return true
      if (channel === 'read-directory') return []
      if (channel === 'git-status') return { isRepo: false, files: {}, dirs: {} }
      if (channel === 'delete-entry') return { success: true }
      throw new Error(`unexpected IPC channel: ${channel}`)
    })

    const { result } = mount()
    await act(async () => { await result.current.selectWorkspace('/workspace') })
    act(() => { result.current.openPreview('/workspace/Assets/hero.fbx') })

    await act(async () => {
      await result.current.handleTreeDelete(agacGirdisi('/workspace/Assets/other.fbx'))
    })

    expect(result.current.previewFile?.path).toBe('/workspace/Assets/hero.fbx')
  })

  // A refused delete leaves the file on disk, so clearing the preview would hide
  // a model that is still there.
  it('keeps the preview when the tree delete reports failure', async () => {
    invoke.mockImplementation(async (channel: string) => {
      if (channel === 'path-exists') return true
      if (channel === 'read-directory') return []
      if (channel === 'git-status') return { isRepo: false, files: {}, dirs: {} }
      if (channel === 'delete-entry') return { success: false, error: 'locked' }
      throw new Error(`unexpected IPC channel: ${channel}`)
    })

    const { result } = mount()
    await act(async () => { await result.current.selectWorkspace('/workspace') })
    const yol = '/workspace/Assets/hero.fbx'
    act(() => { result.current.openPreview(yol) })

    await act(async () => { await result.current.handleTreeDelete(agacGirdisi(yol)) })

    expect(result.current.previewFile?.path).toBe(yol)
  })

  it('keeps the preview when the direct delete reports failure', async () => {
    invoke.mockImplementation(async (channel: string) => {
      if (channel === 'path-exists') return true
      if (channel === 'read-directory') return []
      if (channel === 'git-status') return { isRepo: false, files: {}, dirs: {} }
      if (channel === 'delete-file') return { success: false, error: 'locked' }
      throw new Error(`unexpected IPC channel: ${channel}`)
    })

    const { result } = mount()
    await act(async () => { await result.current.selectWorkspace('/workspace') })
    const yol = '/workspace/Assets/hero.fbx'
    act(() => { result.current.openPreview(yol) })

    await act(async () => { await result.current.deleteFile(yol) })

    expect(result.current.previewFile?.path).toBe(yol)
  })

  // Failing to open a replacement workspace is not a reason to keep the previous
  // one's content area: the missing-path branch used to return leaving the old
  // preview mounted under no workspace at all, so nothing could reload it and
  // nothing said why.
  it('drops the old preview when the replacement workspace turns out to be missing', async () => {
    const yavasB = ertelenmis<boolean>()
    invoke.mockImplementation((channel: string, target: string) => {
      if (channel === 'path-exists') {
        if (target === '/workspace-b') return yavasB.sozu
        if (target === '/workspace-c') return Promise.resolve(false)
        return Promise.resolve(true)
      }
      if (channel === 'read-directory') return Promise.resolve([])
      if (channel === 'git-status') return Promise.resolve({ isRepo: false, files: {}, dirs: {} })
      throw new Error(`unexpected IPC channel: ${channel}`)
    })

    const { result } = mount()
    await act(async () => { await result.current.selectWorkspace('/workspace-a') })
    act(() => { result.current.openPreview('/workspace-a/Assets/hero.fbx') })

    const seciliyor = result.current.selectWorkspace('/workspace-b')
    await Promise.resolve()
    await act(async () => { await result.current.selectWorkspace('/workspace-c') })
    await act(async () => {
      yavasB.coz(true)
      await seciliyor
    })

    expect(result.current.workspacePath).toBeNull()
    expect(result.current.previewFile).toBeNull()
    expect(result.current.fileTree).toEqual([])
  })
})
