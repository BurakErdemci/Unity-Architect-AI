/**
 * AUDIT `unbounded-work-on-untrusted-input`, model preview.
 *
 * The mannequin allocated one CapsuleGeometry per bone synchronously, so a file
 * that merely DECLARES joints froze the window — 20 000 joints fit in 682 KB and
 * cost 1.2 s, well under the main process's 64 MiB read cap, which therefore
 * bounded nothing. The cost is the joint count, so that is what is capped.
 *
 * Everything here is driven through the panel's own seams — the channel, the
 * mannequin builder, the i18n table — so a fix that only moves code around
 * cannot satisfy it.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import * as THREE from 'three'

const stage = vi.hoisted(() => ({ scene: null as unknown }))

vi.mock('three', async importOriginal => {
  const actual = await importOriginal<typeof import('three')>()
  class FakeWebGLRenderer {
    domElement = document.createElement('canvas')
    setPixelRatio() {}
    setSize() {}
    render(scene: unknown) { stage.scene = scene }
    forceContextLoss() {}
    dispose() {}
  }
  return { ...actual, WebGLRenderer: FakeWebGLRenderer }
})

const { cevir, translations } = await import('../renderer/lib/i18n')
const { ModelPreviewPanel } = await import('../renderer/components/model-viewer/ModelPreviewPanel')
const { buildMannequin, exceedsMannequinBudget, MAX_MANNEQUIN_JOINTS } =
  await import('../renderer/components/model-viewer/mannequin')

const invoke = vi.fn()
;(globalThis as any).window.ipc = { invoke }

/** Wrap a JSON glTF document as a binary .glb with no BIN chunk. */
const glb = (json: unknown): ArrayBuffer => {
  const encoded = new TextEncoder().encode(JSON.stringify(json))
  const padded = (encoded.length + 3) & ~3
  const out = new ArrayBuffer(20 + padded)
  const view = new DataView(out)
  view.setUint32(0, 0x46546c67, true)
  view.setUint32(4, 2, true)
  view.setUint32(8, out.byteLength, true)
  view.setUint32(12, padded, true)
  view.setUint32(16, 0x4e4f534a, true)
  const chunk = new Uint8Array(out, 20, padded)
  chunk.fill(0x20)
  chunk.set(encoded)
  return out
}

/**
 * A rig and nothing else: no meshes, no buffers, no binary chunk. GLTFLoader
 * turns every node named in a skin into a Bone, so this is a full skeleton at
 * ~32 bytes per joint — the shape of file the measurement was taken on.
 */
const rigGlb = (joints: number): ArrayBuffer => {
  const nodes: any[] = [{ name: 'Hips', children: [] as number[] }]
  for (let i = 1; i <= joints; i++) {
    nodes.push({ name: `Spine${i}`, translation: [0, 1, 0] })
    nodes[0].children.push(i)
  }
  return glb({
    asset: { version: '2.0' },
    nodes,
    skins: [{ joints: nodes.map((_, i) => i) }],
    scenes: [{ nodes: [0] }],
    scene: 0,
  })
}

/** A chain of `joints` bone-to-bone segments, built directly. */
const boneChain = (joints: number): THREE.Object3D => {
  const root = new THREE.Group()
  let node: THREE.Object3D = root
  // The first bone hangs off a Group, so it spans no segment; each of the
  // `joints` bones below it is one capsule.
  for (let i = 0; i <= joints; i++) {
    const bone = new THREE.Bone()
    bone.name = i === 0 ? 'Hips' : `Spine${i}`
    bone.position.set(0, 0.1, 0)
    node.add(bone)
    node = bone
  }
  root.updateMatrixWorld(true)
  return root
}

const draw = (name = 'rig.glb') =>
  render(
    <ModelPreviewPanel
      file={{ path: `C:\\proj\\Assets\\${name}`, name }}
      workspacePath={'C:\\proj'}
    />,
  )

const meshesOnStage = (): THREE.Mesh[] => {
  const found: THREE.Mesh[] = []
  ;(stage.scene as THREE.Scene | null)?.traverse(o => {
    if ((o as THREE.Mesh).isMesh === true) found.push(o as THREE.Mesh)
  })
  return found
}

describe('a rig with more joints than the mannequin will draw', () => {
  beforeEach(() => { invoke.mockReset(); stage.scene = null })

  it('builds no volumes at all past the cap', () => {
    // The allocation, not the wall clock: a timing assertion on a shared machine
    // is a coin flip, whereas "zero capsules" is the property that makes the
    // freeze impossible.
    expect(buildMannequin(boneChain(MAX_MANNEQUIN_JOINTS + 1))).toBeNull()
  })

  it('still draws a rig at the cap', () => {
    const handle = buildMannequin(boneChain(MAX_MANNEQUIN_JOINTS))
    expect(handle).not.toBeNull()
    expect(handle!.meshes.length).toBeGreaterThan(0)
    handle!.dispose()
  })

  it('leaves a real humanoid well clear of the cap', () => {
    // 65 joints is a Mixamo humanoid; the cap exists to stop hostile files, not
    // to reject the models this panel is for.
    expect(exceedsMannequinBudget(boneChain(65))).toBe(false)
    expect(MAX_MANNEQUIN_JOINTS).toBeGreaterThan(65)
  })

  it('tells the user the rig is too heavy instead of freezing on it', async () => {
    invoke.mockResolvedValue({ path: 'x', name: 'rig.glb', data: rigGlb(MAX_MANNEQUIN_JOINTS + 200) })
    draw()
    await waitFor(() => expect(screen.getByText(cevir('preview.rigTooHeavy'))).toBeTruthy())
    // Neither the spinner nor a blank panel: the two states this branch could
    // otherwise end in.
    expect(screen.queryByText(cevir('preview.loading'))).toBeNull()
    expect(meshesOnStage()).toEqual([])
  })

  it('does not dress the refusal up as a broken file', async () => {
    // A rig over the cap parsed perfectly well; saying the model could not be
    // opened would send the user looking for damage that is not there.
    invoke.mockResolvedValue({ path: 'x', name: 'rig.glb', data: rigGlb(MAX_MANNEQUIN_JOINTS + 200) })
    draw()
    await waitFor(() => expect(screen.getByText(cevir('preview.rigTooHeavy'))).toBeTruthy())
    expect(screen.queryByText(cevir('preview.loadError'))).toBeNull()
  })

  it('still previews a rig under the cap through the same path', async () => {
    invoke.mockResolvedValue({ path: 'x', name: 'rig.glb', data: rigGlb(40) })
    draw()
    await waitFor(() => expect(screen.queryByText(cevir('preview.loading'))).toBeNull())
    expect(screen.queryByText(cevir('preview.rigTooHeavy'))).toBeNull()
    expect(screen.queryByText(cevir('preview.loadError'))).toBeNull()
    expect(meshesOnStage().length).toBeGreaterThan(0)
  })

  it('explains the refusal in both languages', () => {
    for (const lang of ['tr', 'en'] as const) {
      expect(translations[lang]['preview.rigTooHeavy'].length).toBeGreaterThan(0)
    }
  })
})
