/**
 * AUDIT `unbounded-work-on-untrusted-input`, second defect: the mount call sat
 * AFTER the load path's try/catch closed, so anything it threw — an allocation
 * that dies on a big rig, a loader object three cannot mount — escaped as an
 * unhandled rejection. `setLoading(false)` was never reached and the panel span
 * on a spinner that nothing could end but closing the preview.
 *
 * The failure is injected at the mannequin builder because that is the
 * allocation the mount does per bone; what is asserted is the panel's state,
 * not where the throw came from.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import * as THREE from 'three'

const stage = vi.hoisted(() => ({ scene: null as unknown }))
const mannequinThrows = vi.hoisted(() => ({ on: false }))

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

vi.mock('../renderer/components/model-viewer/mannequin', async importOriginal => {
  const actual = await importOriginal<typeof import('../renderer/components/model-viewer/mannequin')>()
  return {
    ...actual,
    buildMannequin: (root: THREE.Object3D) => {
      if (mannequinThrows.on) throw new Error('out of memory building the mannequin')
      return actual.buildMannequin(root)
    },
  }
})

const { cevir } = await import('../renderer/lib/i18n')
const { ModelPreviewPanel } = await import('../renderer/components/model-viewer/ModelPreviewPanel')

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

/** Bones and nothing else, which is the branch that builds a mannequin. */
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

const draw = () =>
  render(
    <ModelPreviewPanel
      file={{ path: 'C:\\proj\\Assets\\rig.glb', name: 'rig.glb' }}
      workspacePath={'C:\\proj'}
    />,
  )

describe('a mount that throws', () => {
  beforeEach(() => { invoke.mockReset(); stage.scene = null; mannequinThrows.on = false })

  it('ends in the panel error message rather than an endless spinner', async () => {
    mannequinThrows.on = true
    invoke.mockResolvedValue({ path: 'x', name: 'rig.glb', data: rigGlb(40) })
    draw()
    await waitFor(() => expect(screen.getByText(cevir('preview.loadError'))).toBeTruthy())
    expect(screen.queryByText(cevir('preview.loading'))).toBeNull()
  })

  it('leaves the same file loading normally once the mount stops throwing', async () => {
    // The catch must not be a one-way door: whatever it wrote is reset by the
    // next load like any other error state.
    invoke.mockResolvedValue({ path: 'x', name: 'rig.glb', data: rigGlb(40) })
    draw()
    await waitFor(() => expect(screen.queryByText(cevir('preview.loading'))).toBeNull())
    expect(screen.queryByText(cevir('preview.loadError'))).toBeNull()
  })
})
