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
})
