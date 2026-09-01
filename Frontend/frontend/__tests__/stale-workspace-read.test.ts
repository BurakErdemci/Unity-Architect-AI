/**
 * Class: stale-workspace-read.
 *
 * `stale-workspace-selection` covers the actions that DECIDE which workspace is
 * open. This file covers the readers that merely describe the open one — the
 * tree refresh, a directory expansion, the periodic git status, and the
 * last-workspace restore. Each awaits IPC or the API and then writes state, so a
 * workspace switch landing inside one of them leaves the previous project's
 * files, expanded folders and repo colours attached to the new project's name,
 * with nothing on screen saying which workspace they came from.
 *
 * These readers are watchers, not owners: a background refresh must be droppable
 * by a newer selection without itself cancelling a selection already in flight.
 * The last case measures exactly that, because guarding them the wrong way turns
 * this class into its mirror image.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'

vi.mock('axios', () => ({
  __esModule: true,
  default: { get: vi.fn().mockResolvedValue({ data: {} }), post: vi.fn().mockResolvedValue({ data: {} }) },
}))

import axios from 'axios'

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

const girdi = (ad: string, kok: string) => ({ name: ad, path: `${kok}/${ad}`, isDirectory: false, extension: '.cs' })

describe('stale-workspace-read', () => {
  beforeEach(() => {
    invoke.mockReset()
    ;(axios.get as any).mockReset()
    ;(axios.get as any).mockResolvedValue({ data: {} })
  })

  it('does not let a late tree refresh replace the newly selected workspace', async () => {
    const gec = ertelenmis<any[]>()
    let kokOkuma = 0
    invoke.mockImplementation((channel: string, target: string) => {
      if (channel === 'path-exists') return Promise.resolve(true)
      if (channel === 'git-status') return Promise.resolve({ isRepo: false, files: {}, dirs: {} })
      if (channel !== 'read-directory') throw new Error(`unexpected IPC channel: ${channel}`)
      if (target === '/workspace-a') {
        kokOkuma += 1
        return kokOkuma === 1 ? Promise.resolve([girdi('A.cs', '/workspace-a')]) : gec.sozu
      }
      if (target === '/workspace-b') return Promise.resolve([girdi('B.cs', '/workspace-b')])
      throw new Error(`unexpected directory: ${target}`)
    })

    const { result } = mount()
    await act(async () => { await result.current.selectWorkspace('/workspace-a') })
    const taleniyor = result.current.refreshFileTree()
    await Promise.resolve()

    await act(async () => { await result.current.selectWorkspace('/workspace-b') })
    await act(async () => {
      gec.coz([girdi('A-late.cs', '/workspace-a')])
      await taleniyor
    })

    expect(result.current.workspacePath).toBe('/workspace-b')
    expect(result.current.fileTree.map((f: any) => f.name)).toEqual(['B.cs'])
  })

  it('does not let a late directory expansion refill the old workspace cache', async () => {
    const gec = ertelenmis<any[]>()
    invoke.mockImplementation((channel: string, target: string) => {
      if (channel === 'path-exists') return Promise.resolve(true)
      if (channel === 'git-status') return Promise.resolve({ isRepo: false, files: {}, dirs: {} })
      if (channel !== 'read-directory') throw new Error(`unexpected IPC channel: ${channel}`)
      if (target === '/workspace-a') return Promise.resolve([])
      if (target === '/workspace-a/Folder') return gec.sozu
      if (target === '/workspace-b') return Promise.resolve([girdi('B.cs', '/workspace-b')])
      throw new Error(`unexpected directory: ${target}`)
    })

    const { result } = mount()
    await act(async () => { await result.current.selectWorkspace('/workspace-a') })
    const aciliyor = result.current.toggleDir('/workspace-a/Folder')
    await Promise.resolve()

    await act(async () => { await result.current.selectWorkspace('/workspace-b') })
    await act(async () => {
      gec.coz([girdi('A-late.cs', '/workspace-a/Folder')])
      await aciliyor
    })

    expect(result.current.workspacePath).toBe('/workspace-b')
    expect(result.current.dirContents).toEqual({})
    // The expansion set is part of the same stale write: reopening a folder the
    // new tree does not contain is as wrong as caching its contents.
    expect(result.current.expandedDirs.size).toBe(0)
  })

  it('does not let a late git status recolor the newly selected workspace', async () => {
    const gec = ertelenmis<any>()
    let gecikmeli = false
    invoke.mockImplementation((channel: string, target: string) => {
      if (channel === 'path-exists') return Promise.resolve(true)
      if (channel === 'read-directory') return Promise.resolve([])
      if (channel !== 'git-status') throw new Error(`unexpected IPC channel: ${channel}`)
      if (target === '/workspace-a' && gecikmeli) return gec.sozu
      if (target === '/workspace-a') return Promise.resolve({ isRepo: true, files: { old: 'modified' }, dirs: {} })
      if (target === '/workspace-b') return Promise.resolve({ isRepo: false, files: {}, dirs: {} })
      throw new Error(`unexpected workspace: ${target}`)
    })

    const { result } = mount()
    await act(async () => { await result.current.selectWorkspace('/workspace-a') })
    gecikmeli = true
    const taleniyor = result.current.refreshGitStatus('/workspace-a')
    await Promise.resolve()

    await act(async () => { await result.current.selectWorkspace('/workspace-b') })
    await act(async () => {
      gec.coz({ isRepo: true, files: { stale: 'modified' }, dirs: {} })
      await taleniyor
    })

    expect(result.current.workspacePath).toBe('/workspace-b')
    expect(result.current.gitStatus.files).toEqual({})
  })

  it('does not restore the last workspace after the user closed the workspace', async () => {
    const gec = ertelenmis<any>()
    ;(axios.get as any).mockReturnValue(gec.sozu)
    invoke.mockImplementation((channel: string) => {
      if (channel === 'host-workspace-path') return Promise.resolve('/workspace-old')
      throw new Error(`unexpected IPC channel: ${channel}`)
    })

    const { result } = renderHook(() => useFileSystem('http://api', { id: 7, sessionToken: 'session' } as any, () => {}))
    const getiriliyor = result.current.fetchLastWorkspace(7)
    await Promise.resolve()

    act(() => { result.current.closeWorkspace() })
    await act(async () => {
      gec.coz({ data: { path: '/backend/old' } })
      await getiriliyor
    })

    expect(result.current.lastWorkspacePath).toBeNull()
  })

  it('a refresh running alongside a selection does not cancel that selection', async () => {
    const yavasB = ertelenmis<boolean>()
    invoke.mockImplementation((channel: string, target: string) => {
      if (channel === 'path-exists') return target === '/workspace-b' ? yavasB.sozu : Promise.resolve(true)
      if (channel === 'git-status') return Promise.resolve({ isRepo: false, files: {}, dirs: {} })
      if (channel !== 'read-directory') throw new Error(`unexpected IPC channel: ${channel}`)
      if (target === '/workspace-a') return Promise.resolve([girdi('A.cs', '/workspace-a')])
      if (target === '/workspace-b') return Promise.resolve([girdi('B.cs', '/workspace-b')])
      throw new Error(`unexpected directory: ${target}`)
    })

    const { result } = mount()
    await act(async () => { await result.current.selectWorkspace('/workspace-a') })

    const seciliyor = result.current.selectWorkspace('/workspace-b')
    await Promise.resolve()
    // A refresh of the workspace still on screen must not take ownership away
    // from the selection already in flight — that would trade this defect for
    // its mirror: the user's switch silently abandoned by a background read.
    await act(async () => { await result.current.refreshFileTree() })

    await act(async () => {
      yavasB.coz(true)
      await seciliyor
    })

    expect(result.current.workspacePath).toBe('/workspace-b')
    expect(result.current.fileTree.map((f: any) => f.name)).toEqual(['B.cs'])
  })
})
