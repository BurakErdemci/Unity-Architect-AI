/**
 * Editor and 3D preview share one content area, and there is no tab system:
 * whichever is open must close the other. If both are set, home.tsx renders the
 * preview and the editor keeps a stale file (with its dirty flag) invisible
 * behind it — unsaved work the user can no longer see.
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

const mount = () => renderHook(() => useFileSystem('http://x', null, () => {}))

describe('preview / editor mutual exclusion', () => {
  beforeEach(() => {
    invoke.mockReset()
    invoke.mockResolvedValue({ path: 'Assets/Scripts/Player.cs', content: 'class Player {}' })
  })

  it('openPreview stores the path and the display name', async () => {
    const { result } = mount()
    act(() => { result.current.openPreview('C:\\proj\\Assets\\hero.fbx') })
    expect(result.current.previewFile).toEqual({ path: 'C:\\proj\\Assets\\hero.fbx', name: 'hero.fbx' })
  })

  it('openPreview closes an open editor file and drops its buffer', async () => {
    const { result } = mount()
    await act(async () => { await result.current.openFile('Assets/Scripts/Player.cs') })
    expect(result.current.openedFilePath).toBe('Assets/Scripts/Player.cs')

    act(() => { result.current.openPreview('Assets/Models/hero.fbx') })
    expect(result.current.openedFilePath).toBeNull()
    expect(result.current.code).toBe('')
    expect(result.current.isDirty).toBe(false)
    expect(result.current.previewFile?.name).toBe('hero.fbx')
  })

  it('openFile closes an open preview', async () => {
    const { result } = mount()
    act(() => { result.current.openPreview('Assets/Models/hero.fbx') })
    await act(async () => { await result.current.openFile('Assets/Scripts/Player.cs') })
    expect(result.current.previewFile).toBeNull()
    expect(result.current.openedFilePath).toBe('Assets/Scripts/Player.cs')
  })

  it('a failed openFile leaves the preview alone — nothing replaced it', async () => {
    const { result } = mount()
    act(() => { result.current.openPreview('Assets/Models/hero.fbx') })
    invoke.mockResolvedValue(null)
    await act(async () => { await result.current.openFile('Assets/Scripts/Gone.cs') })
    expect(result.current.previewFile?.name).toBe('hero.fbx')
    expect(result.current.openedFilePath).toBeNull()
  })

  // The file tree routes by extension before it calls anything, but it is not
  // the only door: chat file links and problem-list entries call `openFile`
  // directly. That door used to hand a .fbx to `read-file`, which answers
  // `unsupported` — a refusal for a format this app can now display.
  it('openFile routes a 3D file to the preview and never asks read-file for it', async () => {
    const { result } = mount()
    await act(async () => { await result.current.openFile('C:\\proj\\Assets\\hero.fbx') })
    expect(result.current.previewFile).toEqual({ path: 'C:\\proj\\Assets\\hero.fbx', name: 'hero.fbx' })
    expect(result.current.openedFilePath).toBeNull()
    expect(invoke).not.toHaveBeenCalled()
  })

  it('openFile routes an unrenderable 3D format to the preview too — the panel explains it', async () => {
    const { result } = mount()
    await act(async () => { await result.current.openFile('Assets/Models/scene.blend') })
    expect(result.current.previewFile?.name).toBe('scene.blend')
    expect(invoke).not.toHaveBeenCalled()
  })

  it('openFile still sends a text file down the read-file channel', async () => {
    const { result } = mount()
    await act(async () => { await result.current.openFile('Assets/Scripts/Player.cs') })
    expect(invoke).toHaveBeenCalledWith('read-file', 'Assets/Scripts/Player.cs', null)
    expect(result.current.openedFilePath).toBe('Assets/Scripts/Player.cs')
  })

  it('closePreview empties the content area', () => {
    const { result } = mount()
    act(() => { result.current.openPreview('Assets/Models/hero.fbx') })
    act(() => { result.current.closePreview() })
    expect(result.current.previewFile).toBeNull()
    expect(result.current.openedFilePath).toBeNull()
  })

  it('closeWorkspace clears the preview — its file is no longer reachable', () => {
    const { result } = mount()
    act(() => { result.current.openPreview('Assets/Models/hero.fbx') })
    act(() => { result.current.closeWorkspace() })
    expect(result.current.previewFile).toBeNull()
  })
})
