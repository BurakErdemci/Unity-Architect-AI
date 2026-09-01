/**
 * Class: stale-content-race.
 *
 * The editor and the 3D preview share one content area. `openFile` awaits a
 * `read-file` round trip and then writes the editor and clears `previewFile`,
 * so a slow read landing after the user has already chosen something else
 * reverses that choice: the model the user just selected vanishes and the older
 * text file takes the screen, with nothing indicating why.
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

// Which paths were actually read. Each race case below ends in a state that
// `openPreview` or the newer `openFile` establishes on its own, so without
// checking that the SUPERSEDED read really was issued a green run cannot tell
// "the late result was refused" from "no late result ever existed" — and an
// `openFile` that stopped reading altogether would keep every assertion happy.
const okunanYollar = () =>
  invoke.mock.calls.filter(([kanal]: any[]) => kanal === 'read-file').map(([, yol]: any[]) => yol)

describe('stale-content-race', () => {
  beforeEach(() => { invoke.mockReset() })

  it('does not let an older text read replace a newer preview', async () => {
    const okuma = ertelenmis<unknown>()
    invoke.mockImplementation((channel: string) => {
      if (channel === 'read-file') return okuma.sozu
      throw new Error(`unexpected IPC channel: ${channel}`)
    })

    const { result } = mount()
    const aciliyor = result.current.openFile('/workspace/Assets/old.cs')
    await Promise.resolve()

    act(() => { result.current.openPreview('/workspace/Assets/hero.fbx') })

    await act(async () => {
      okuma.coz({ path: '/workspace/Assets/old.cs', content: 'class Old {}' })
      await aciliyor
    })

    expect(okunanYollar()).toEqual(['/workspace/Assets/old.cs'])
    expect(result.current.previewFile?.path).toBe('/workspace/Assets/hero.fbx')
    expect(result.current.openedFilePath).toBeNull()
    expect(result.current.code).toBe('')
  })

  it('does not let an older text read replace a newer text file', async () => {
    const eski = ertelenmis<unknown>()
    invoke.mockImplementation((channel: string, filePath: string) => {
      if (channel !== 'read-file') throw new Error(`unexpected IPC channel: ${channel}`)
      if (filePath === '/workspace/Assets/old.cs') return eski.sozu
      return Promise.resolve({ path: filePath, content: 'class New {}' })
    })

    const { result } = mount()
    const eskiAciliyor = result.current.openFile('/workspace/Assets/old.cs')
    await Promise.resolve()

    await act(async () => { await result.current.openFile('/workspace/Assets/new.cs') })

    await act(async () => {
      eski.coz({ path: '/workspace/Assets/old.cs', content: 'class Old {}' })
      await eskiAciliyor
    })

    expect(okunanYollar()).toEqual(['/workspace/Assets/old.cs', '/workspace/Assets/new.cs'])
    expect(result.current.openedFilePath).toBe('/workspace/Assets/new.cs')
    expect(result.current.code).toBe('class New {}')
  })

  it('does not warn about a read the user already abandoned', async () => {
    const okuma = ertelenmis<unknown>()
    invoke.mockImplementation((channel: string) => {
      if (channel === 'read-file') return okuma.sozu
      throw new Error(`unexpected IPC channel: ${channel}`)
    })

    const bildirimler: string[] = []
    const { result } = renderHook(() => useFileSystem('', null, (m: string) => { bildirimler.push(m) }))
    const aciliyor = result.current.openFile('/workspace/Assets/old.cs')
    await Promise.resolve()

    act(() => { result.current.openPreview('/workspace/Assets/hero.fbx') })

    await act(async () => {
      okuma.coz(null)
      await aciliyor
    })

    expect(okunanYollar()).toEqual(['/workspace/Assets/old.cs'])
    expect(bildirimler).toEqual([])
    expect(result.current.previewFile?.path).toBe('/workspace/Assets/hero.fbx')
  })

  // The file dialog is the slowest await in the hook and is dismissed by the OS,
  // not by this component: whatever the user does in the content area meanwhile
  // is newer than the picker's answer.
  it('does not let a late file-picker result replace a newer preview', async () => {
    const secici = ertelenmis<any>()
    invoke.mockImplementation((channel: string) => {
      if (channel === 'open-file-dialog') return secici.sozu
      throw new Error(`unexpected IPC channel: ${channel}`)
    })

    const { result } = mount()
    const seciliyor = result.current.openFilePicker()
    await Promise.resolve()

    act(() => { result.current.openPreview('/workspace/Assets/new.fbx') })

    await act(async () => {
      secici.coz({ path: '/workspace/old.cs', content: 'class Old {}' })
      await seciliyor
    })

    expect(result.current.previewFile?.path).toBe('/workspace/Assets/new.fbx')
    expect(result.current.openedFilePath).toBeNull()
    expect(result.current.code).toBe('')
  })

  it('a picked file nothing superseded still reaches the editor', async () => {
    invoke.mockImplementation(async (channel: string) => {
      if (channel === 'open-file-dialog') return { path: '/workspace/Player.cs', content: 'class Player {}' }
      throw new Error(`unexpected IPC channel: ${channel}`)
    })

    const { result } = mount()
    await act(async () => { await result.current.openFilePicker() })

    expect(result.current.openedFilePath).toBe('/workspace/Player.cs')
    expect(result.current.code).toBe('class Player {}')
    expect(result.current.previewFile).toBeNull()
  })

  it('a read nothing superseded still opens the file', async () => {
    invoke.mockImplementation(async (channel: string, filePath: string) => {
      if (channel === 'read-file') return { path: filePath, content: 'class Player {}' }
      throw new Error(`unexpected IPC channel: ${channel}`)
    })

    const { result } = mount()
    await act(async () => { await result.current.openFile('/workspace/Assets/Player.cs') })

    expect(result.current.openedFilePath).toBe('/workspace/Assets/Player.cs')
    expect(result.current.code).toBe('class Player {}')
  })

  // The other direction of the same race. Above, a newer content choice must
  // survive an older read; here a filesystem operation removes or relocates the
  // very path a read is still out for. Nothing has been committed yet, so there
  // is no stale state for the content helper to correct — the read arrives into
  // an empty content area afterwards and fills it with a path that is gone.
  describe('a successful path change supersedes a read of that path', () => {
    const eskiYol = '/workspace/Assets/old.cs'
    let okuma: ReturnType<typeof ertelenmis<any>>

    const yarisIpc = (channel: string) => {
      if (channel === 'path-exists') return Promise.resolve(true)
      if (channel === 'read-directory') return Promise.resolve([])
      if (channel === 'git-status') return Promise.resolve({ isRepo: false, files: {}, dirs: {} })
      if (channel === 'read-file') return okuma.sozu
      if (channel === 'delete-file' || channel === 'delete-entry') return Promise.resolve({ success: true })
      if (channel === 'rename-entry') return Promise.resolve({ success: true, newPath: '/workspace/Assets/new.cs' })
      if (channel === 'move-entry') return Promise.resolve({ success: true, newPath: '/workspace/Moved/old.cs' })
      throw new Error(`unexpected IPC channel: ${channel}`)
    }

    const girdi = (yol: string) => ({ name: yol.split('/').pop() as string, path: yol, isDirectory: false, extension: '.cs' })
    const klasor = (yol: string) => ({ name: yol.split('/').pop() as string, path: yol, isDirectory: true, extension: '' })
    const surukle = async (result: any, kaynak: any, hedef: any) => {
      act(() => {
        result.current.handleTreeDragStart(
          { stopPropagation() {}, dataTransfer: { effectAllowed: '', setData() {} } }, kaynak,
        )
      })
      await act(async () => {
        await result.current.handleTreeDrop({ preventDefault() {}, stopPropagation() {} }, hedef)
      })
    }

    // Start a read of `eskiYol` and hand back the call that finishes it. The
    // pending read is returned wrapped in a function on purpose: an async helper
    // that RETURNED it would await it, and it is meant to stay in flight.
    const okumayaBasla = async (result: any) => {
      const aciliyor = result.current.openFile(eskiYol)
      await Promise.resolve()
      return async () => {
        await act(async () => {
          okuma.coz({ path: eskiYol, content: 'class Old {}' })
          await aciliyor
        })
      }
    }

    beforeEach(() => {
      okuma = ertelenmis<any>()
      invoke.mockImplementation(yarisIpc)
    })

    const hazirla = async () => {
      const { result } = mount()
      await act(async () => { await result.current.selectWorkspace('/workspace') })
      return result
    }

    it('a direct delete stops the read from reopening the deleted path', async () => {
      const result = await hazirla()
      const okumayiBitir = await okumayaBasla(result)

      await act(async () => { await result.current.deleteFile(eskiYol) })
      await okumayiBitir()

      expect(okunanYollar()).toEqual([eskiYol])
      expect(result.current.openedFilePath).toBeNull()
    })

    it('a tree delete stops the read from reopening the deleted path', async () => {
      const result = await hazirla()
      const okumayiBitir = await okumayaBasla(result)

      await act(async () => { await result.current.handleTreeDelete(girdi(eskiYol)) })
      await okumayiBitir()

      expect(okunanYollar()).toEqual([eskiYol])
      expect(result.current.openedFilePath).toBeNull()
    })

    it('a rename stops the read from reopening the stale source path', async () => {
      const result = await hazirla()
      const okumayiBitir = await okumayaBasla(result)

      act(() => {
        result.current.setRenamingPath(eskiYol)
        result.current.setRenameValue('new.cs')
      })
      await act(async () => { await result.current.submitRename() })
      await okumayiBitir()

      expect(okunanYollar()).toEqual([eskiYol])
      expect(result.current.openedFilePath).not.toBe(eskiYol)
    })

    it('a tree move stops the read from reopening the stale source path', async () => {
      const result = await hazirla()
      const okumayiBitir = await okumayaBasla(result)

      await surukle(result, girdi(eskiYol), klasor('/workspace/Moved'))
      await okumayiBitir()

      expect(okunanYollar()).toEqual([eskiYol])
      expect(result.current.openedFilePath).not.toBe(eskiYol)
    })

    // The mirror defect, and the reason the read is not simply cancelled on
    // every path change: deleting one file says nothing about a read of another
    // one, and dropping that read would empty a content area the user is
    // legitimately waiting on.
    it('a delete of a different file leaves the pending read alone', async () => {
      const result = await hazirla()
      const okumayiBitir = await okumayaBasla(result)

      await act(async () => { await result.current.deleteFile('/workspace/Assets/other.cs') })
      await okumayiBitir()

      expect(result.current.openedFilePath).toBe(eskiYol)
      expect(result.current.code).toBe('class Old {}')
    })

    // A folder deletion takes the pending read's file with it even though the
    // read names no path the operation mentions.
    it('deleting an ancestor folder stops the read for a file beneath it', async () => {
      const result = await hazirla()
      const okumayiBitir = await okumayaBasla(result)

      await act(async () => { await result.current.handleTreeDelete(klasor('/workspace/Assets')) })
      await okumayiBitir()

      expect(result.current.openedFilePath).toBeNull()
    })
  })
})
