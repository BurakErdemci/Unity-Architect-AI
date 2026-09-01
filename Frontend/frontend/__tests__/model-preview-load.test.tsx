/**
 * The panel's load path under jsdom: which channel call goes out, which of the
 * states the user is left looking at, and — for the files that succeed — what
 * actually reached the scene.
 *
 * Wording is pulled from the i18n table rather than typed in, so a copy edit
 * does not turn into a red test.
 *
 * `WebGLRenderer` is replaced by a canvas-owning stand-in, as in
 * webgl-context-loss-unhandled.test.tsx. Without it `new WebGLRenderer()`
 * throws under jsdom, `stageRef` stays null and every success case exits at
 * `if (!stage)` — which left the happy paths asserting nothing but the ABSENCE
 * of an error label, a condition a fabricated parse result satisfies just as
 * well as a real one (AUDIT `no-op-test`). The stand-in keeps the scene the
 * panel builds, so the assertions below can name what is in it.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
// Type-only: the value side of `three` is mocked below, and nothing here needs
// a constructor from it.
import type * as THREE from 'three'

const stage = vi.hoisted(() => ({ scene: null as unknown }))

vi.mock('three', async importOriginal => {
  const actual = await importOriginal<typeof import('three')>()
  class FakeWebGLRenderer {
    domElement = document.createElement('canvas')
    setPixelRatio() {}
    setSize() {}
    // The scene object is captured, not copied: the panel mounts into the same
    // instance for the panel's whole lifetime, so holding the reference is what
    // lets a test read the graph as it stands after the load settles.
    render(scene: unknown) { stage.scene = scene }
    forceContextLoss() {}
    dispose() {}
  }
  return { ...actual, WebGLRenderer: FakeWebGLRenderer }
})

const { cevir, translations } = await import('../renderer/lib/i18n')
const { ModelPreviewPanel } = await import('../renderer/components/model-viewer/ModelPreviewPanel')
const { parseModel } = await import('../renderer/components/model-viewer/loaders')

const invoke = vi.fn()
;(globalThis as any).window.ipc = { invoke }

/** Everything drawable the panel put on its stage, by the file's own naming. */
const onStage = (): THREE.Object3D[] => {
  const found: THREE.Object3D[] = []
  ;(stage.scene as THREE.Scene | null)?.traverse(o => found.push(o))
  return found
}

const meshesOnStage = (): THREE.Mesh[] =>
  onStage().filter((o): o is THREE.Mesh => (o as THREE.Mesh).isMesh === true)

const bonesOnStage = (): THREE.Bone[] =>
  onStage().filter((o): o is THREE.Bone => (o as THREE.Bone).isBone === true)

const vertexCount = (mesh: THREE.Mesh): number =>
  mesh.geometry.getAttribute('position')?.count ?? 0

// The copy puts the bytes in jsdom's realm, where an `instanceof ArrayBuffer`
// inside three actually holds; see model-format-dispatch.test.ts for the
// measurement.
const bytes = (name: string): ArrayBuffer => {
  const buf = readFileSync(resolve(__dirname, 'fixtures', name))
  const out = new ArrayBuffer(buf.byteLength)
  new Uint8Array(out).set(buf)
  return out
}

const fbxBytes = (): ArrayBuffer => bytes('animated-triangle.fbx')

const draw = (name = 'hero.fbx', workspacePath: string | null = 'C:\\proj') =>
  render(
    <ModelPreviewPanel
      file={{ path: `C:\\proj\\Assets\\${name}`, name }}
      workspacePath={workspacePath}
    />,
  )

const LOAD_ERROR = cevir('preview.loadError')

describe('ModelPreviewPanel load', () => {
  beforeEach(() => { invoke.mockReset(); stage.scene = null })

  it('asks the model channel for the clicked file, scoped to the workspace', async () => {
    invoke.mockResolvedValue({ path: 'x', name: 'hero.fbx', data: fbxBytes() })
    draw()
    await waitFor(() => expect(invoke).toHaveBeenCalledWith('read-model-file', 'C:\\proj\\Assets\\hero.fbx', 'C:\\proj'))
  })

  it('shows the loading state until the answer arrives', async () => {
    let settle: (v: unknown) => void = () => {}
    invoke.mockReturnValue(new Promise(r => { settle = r }))
    draw()
    expect(screen.getByText(cevir('preview.loading'))).toBeTruthy()

    settle({ path: 'x', name: 'hero.fbx', data: fbxBytes() })
    await waitFor(() => expect(screen.queryByText(cevir('preview.loading'))).toBeNull())
  })

  it('leaves no error visible once a real FBX parses — and puts the file on the stage', async () => {
    // The absence of an error label is not evidence that anything loaded: the
    // panel shows no label at all while a load is still under way, and shows
    // none either for a result that parsed to something nobody asked for. What
    // is named here is the fixture's own geometry and its own clip, so a parse
    // result the file did not produce cannot satisfy it.
    invoke.mockResolvedValue({ path: 'x', name: 'hero.fbx', data: fbxBytes() })
    draw()
    await waitFor(() => expect(screen.queryByText(cevir('preview.loading'))).toBeNull())
    expect(screen.queryByText(LOAD_ERROR)).toBeNull()

    const triangle = meshesOnStage().find(m => m.name === 'Triangle')
    expect(triangle).toBeTruthy()
    expect(vertexCount(triangle!)).toBe(3)
    // animated-triangle.fbx carries a one-second clip, and the transport bar is
    // the panel's only visible answer to a file that has one.
    expect(screen.getByLabelText(cevir('preview.timeline'))).toBeTruthy()
  })

  it('falls back to the generic message for a containment refusal', async () => {
    // 'denied' keeps the generic wording on purpose: it is the workspace
    // boundary refusing a path, and describing the boundary to whoever probed
    // it is the one thing this message must not do.
    invoke.mockResolvedValue({ error: 'denied' })
    draw()
    await waitFor(() => expect(screen.getByText(LOAD_ERROR)).toBeTruthy())
  })

  it('says the file is over the size cap for too-large', async () => {
    invoke.mockResolvedValue({ error: 'too-large' })
    draw()
    await waitFor(() => expect(screen.getByText(cevir('preview.tooLarge'))).toBeTruthy())
    expect(screen.queryByText(LOAD_ERROR)).toBeNull()
  })

  it('names the size cap in both languages', () => {
    // The number is the contract with the main-process gate; a message that
    // omits it leaves the user guessing which files are too big.
    for (const lang of ['tr', 'en'] as const) {
      expect(translations[lang]['preview.tooLarge']).toMatch(/64 MiB/)
    }
  })

  it('says the type is not previewable for unsupported', async () => {
    invoke.mockResolvedValue({ error: 'unsupported' })
    draw()
    await waitFor(() => expect(screen.getByText(cevir('preview.unsupportedFormat'))).toBeTruthy())
  })

  it('falls back to the generic message for an error code it has never seen', async () => {
    // The gate may grow a code before this panel does; the failure mode has to
    // be a wrong-but-honest message, not a blank panel.
    invoke.mockResolvedValue({ error: 'quarantined-by-the-future' })
    draw()
    await waitFor(() => expect(screen.getByText(LOAD_ERROR)).toBeTruthy())
  })

  it('falls back to the generic message when the handler answers with nothing', async () => {
    invoke.mockResolvedValue(null)
    draw()
    await waitFor(() => expect(screen.getByText(LOAD_ERROR)).toBeTruthy())
  })

  it('prints the parser one-liner under the generic message', async () => {
    // The diagnostic is ASKED FOR rather than spelled out: naming three's own
    // wording here made a vendor rename — a change with no user-visible effect
    // — able to turn this green test red (AUDIT `third-party-error-wording`).
    // What the panel owes the user is that whatever the parser said survives to
    // the screen, so the expectation is measured from the same parser.
    const junk = () => new TextEncoder().encode('plain text').buffer as ArrayBuffer
    const failure = await parseModel('.fbx', junk()).catch((e: unknown) => e)
    const detail = String(failure instanceof Error ? failure.message : failure).split(/\r?\n/)[0]
    expect(detail.length).toBeGreaterThan(0)
    expect(detail).not.toBe(LOAD_ERROR)

    invoke.mockResolvedValue({ path: 'x', name: 'hero.fbx', data: junk() })
    draw()
    await waitFor(() => expect(screen.getByText(LOAD_ERROR)).toBeTruthy())
    expect(screen.getByText(detail)).toBeTruthy()
  })

  it('renders a .glb through the panel with no error left behind', async () => {
    invoke.mockResolvedValue({ path: 'x', name: 'hero.glb', data: bytes('triangle.glb') })
    draw('hero.glb')
    await waitFor(() => expect(screen.queryByText(cevir('preview.loading'))).toBeNull())
    expect(screen.queryByText(LOAD_ERROR)).toBeNull()
    // triangle.glb is one triangle and nothing else; a stage holding anything
    // other than that did not render this file.
    expect(meshesOnStage().map(vertexCount)).toEqual([3])
  })

  it('tells the user to export as .glb when the .gltf is only half the file', async () => {
    invoke.mockResolvedValue({ path: 'x', name: 'hero.gltf', data: bytes('triangle-external.gltf') })
    draw('hero.gltf')
    await waitFor(() => expect(screen.getByText(cevir('preview.gltfExternal'))).toBeTruthy())
    // The loader's own words would be about a failed fetch, which explains
    // nothing the user can act on.
    expect(screen.queryByText(LOAD_ERROR)).toBeNull()
  })

  it('says nothing is visible when the file parses to no geometry', async () => {
    invoke.mockResolvedValue({ path: 'x', name: 'empty.obj', data: bytes('nothing.obj') })
    draw('empty.obj')
    await waitFor(() => expect(screen.getByText(cevir('preview.emptyModel'))).toBeTruthy())
  })

  it('does not call an animation-only file empty', async () => {
    // Bones and clips, no mesh: Mixamo's "without skin" export, and the bulk of
    // a bought animation pack. It used to hit the empty-file message.
    invoke.mockResolvedValue({ path: 'x', name: 'run.fbx', data: bytes('bones-only.fbx') })
    draw('run.fbx')
    await waitFor(() => expect(screen.queryByText(cevir('preview.loading'))).toBeNull())
    expect(screen.queryByText(cevir('preview.emptyModel'))).toBeNull()
    expect(screen.queryByText(LOAD_ERROR)).toBeNull()
    // The rig itself reached the stage, and the mannequin volumes stood in for
    // the geometry the file does not have — the two things that make this file
    // viewable at all, neither of which the absence of a label can show.
    expect(bonesOnStage().length).toBeGreaterThan(1)
    expect(meshesOnStage().length).toBeGreaterThan(0)
  })

  it('re-reads when the previewed file changes', async () => {
    invoke.mockResolvedValue({ path: 'x', name: 'hero.fbx', data: fbxBytes() })
    const view = draw()
    await waitFor(() => expect(invoke).toHaveBeenCalledTimes(1))
    view.rerender(
      <ModelPreviewPanel
        file={{ path: 'C:\\proj\\Assets\\second.fbx', name: 'second.fbx' }}
        workspacePath={'C:\\proj'}
      />,
    )
    await waitFor(() => expect(invoke).toHaveBeenLastCalledWith('read-model-file', 'C:\\proj\\Assets\\second.fbx', 'C:\\proj'))
  })
})

describe('a format only Blender can read', () => {
  beforeEach(() => { invoke.mockReset() })

  it('explains .blend without ever touching the channel', async () => {
    draw('scene.blend')
    await waitFor(() => expect(screen.getByText(cevir('preview.blockedFormat'))).toBeTruthy())
    // The point of the branch. Reading the file would cost a main-process read
    // and a full buffer over IPC for bytes no loader in this app can use.
    expect(invoke).not.toHaveBeenCalled()
  })

  it('explains .3ds without ever touching the channel', async () => {
    draw('prop.3ds')
    await waitFor(() => expect(screen.getByText(cevir('preview.blockedFormat'))).toBeTruthy())
    expect(invoke).not.toHaveBeenCalled()
  })

  it('leaves no loading state hanging behind the message', async () => {
    draw('scene.blend')
    await waitFor(() => expect(screen.queryByText(cevir('preview.loading'))).toBeNull())
  })

  it('goes back to reading the channel when the next file is previewable', async () => {
    invoke.mockResolvedValue({ path: 'x', name: 'hero.fbx', data: fbxBytes() })
    const view = draw('scene.blend')
    await waitFor(() => expect(screen.getByText(cevir('preview.blockedFormat'))).toBeTruthy())
    view.rerender(
      <ModelPreviewPanel
        file={{ path: 'C:\\proj\\Assets\\hero.fbx', name: 'hero.fbx' }}
        workspacePath={'C:\\proj'}
      />,
    )
    await waitFor(() => expect(invoke).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(screen.queryByText(cevir('preview.blockedFormat'))).toBeNull())
  })

  it('points at Blender in both languages', () => {
    for (const lang of ['tr', 'en'] as const) {
      expect(translations[lang]['preview.blockedFormat']).toMatch(/Blender/)
    }
  })
})
