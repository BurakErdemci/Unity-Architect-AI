/**
 * `parseModel` routing, one real file per supported extension. What is measured
 * is the OUTCOME of the dispatch — geometry, material, clips — not that a
 * switch case exists, so a rewrite that keeps the behaviour keeps the test.
 *
 * Every fixture is a hand-written triangle. Six of the seven are text and
 * readable in the diff; `triangle.glb` is 476 bytes of binary, generated from
 * the same JSON as `triangle.gltf` with the buffer moved into a BIN chunk.
 */
import { describe, it, expect, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import * as THREE from 'three'
import { parseModel, ModelParseError, FALLBACK_MATERIAL_COLOR } from '../renderer/components/model-viewer/loaders'

// MEASURED here, 31 Aug 2026: every parse in this file finishes in single-digit
// milliseconds once three is imported, but one run of the FULL suite had one of
// them charged 7.3s and time out at the 5s default — 54 files' worth of jsdom
// workers starving the event loop, not the parser. A raised ceiling is the
// honest fix; shrinking the fixtures would not have touched the cause.
vi.setConfig({ testTimeout: 30_000 })

/**
 * The copy is not waste. `readFileSync` hands back a Buffer backed by an
 * ArrayBuffer from NODE's realm, and jsdom installs its own `ArrayBuffer`
 * global — so `data instanceof ArrayBuffer` inside GLTFLoader is FALSE for a
 * Node-realm buffer, and the loader silently treats the bytes as an already
 * parsed JSON object ("Unsupported asset"). Allocating here puts the buffer in
 * the same realm the renderer's IPC reply would arrive in.
 */
const fixture = (name: string): ArrayBuffer => {
  const buf = readFileSync(resolve(__dirname, 'fixtures', name))
  const out = new ArrayBuffer(buf.byteLength)
  new Uint8Array(out).set(buf)
  return out
}

const meshes = (root: THREE.Object3D): THREE.Mesh[] => {
  const out: THREE.Mesh[] = []
  root.traverse(o => { if ((o as THREE.Mesh).isMesh) out.push(o as THREE.Mesh) })
  return out
}

const onlyMesh = async (ext: string, name: string): Promise<THREE.Mesh> => {
  const { object } = await parseModel(ext, fixture(name))
  const found = meshes(object)
  expect(found).toHaveLength(1)
  return found[0]
}

const positions = (mesh: THREE.Mesh): number =>
  mesh.geometry.getAttribute('position').count

describe('parseModel dispatch', () => {
  it('loads a self-contained .glb', async () => {
    const mesh = await onlyMesh('.glb', 'triangle.glb')
    expect(positions(mesh)).toBe(3)
  })

  it('loads a .gltf whose buffer is an embedded data URI', async () => {
    const mesh = await onlyMesh('.gltf', 'triangle.gltf')
    expect(positions(mesh)).toBe(3)
  })

  it('loads a .dae', async () => {
    const mesh = await onlyMesh('.dae', 'triangle.dae')
    expect(positions(mesh)).toBe(3)
  })

  it('loads an .obj', async () => {
    const mesh = await onlyMesh('.obj', 'triangle.obj')
    expect(positions(mesh)).toBe(3)
  })

  it('loads an ASCII .stl', async () => {
    const mesh = await onlyMesh('.stl', 'triangle.stl')
    expect(positions(mesh)).toBe(3)
  })

  it('loads an ASCII .ply', async () => {
    const mesh = await onlyMesh('.ply', 'triangle.ply')
    expect(positions(mesh)).toBe(3)
  })

  it('routes on the extension, not on the bytes', async () => {
    // The dispatch is the only thing standing between an .obj and the STL
    // parser; hand it the wrong extension and it must not quietly succeed.
    await expect(parseModel('.stl', fixture('triangle.obj'))).rejects.toThrow()
  })

  it('accepts an uppercase extension for every format', async () => {
    for (const [ext, name] of [
      ['.GLB', 'triangle.glb'], ['.GLTF', 'triangle.gltf'], ['.DAE', 'triangle.dae'],
      ['.OBJ', 'triangle.obj'], ['.STL', 'triangle.stl'], ['.PLY', 'triangle.ply'],
    ]) {
      await expect(parseModel(ext, fixture(name))).resolves.toBeTruthy()
    }
  })
})

describe('parseModel materials', () => {
  it('gives the geometry-only formats the neutral gray material', async () => {
    for (const [ext, name] of [['.stl', 'triangle.stl'], ['.ply', 'triangle.ply']]) {
      const material = (await onlyMesh(ext, name)).material as THREE.MeshStandardMaterial
      expect(material.isMeshStandardMaterial).toBe(true)
      expect(material.color.getHex()).toBe(FALLBACK_MATERIAL_COLOR)
    }
  })

  it('normals a .ply that ships positions only', async () => {
    // Without them every lit material draws the mesh black, which on screen is
    // indistinguishable from a load that failed.
    const mesh = await onlyMesh('.ply', 'triangle.ply')
    expect(mesh.geometry.getAttribute('normal')).toBeTruthy()
  })

  it('replaces the .obj placeholder material — the real one lives in a .mtl we never fetch', async () => {
    const material = (await onlyMesh('.obj', 'triangle.obj')).material as THREE.MeshStandardMaterial
    expect(material.color.getHex()).toBe(FALLBACK_MATERIAL_COLOR)
  })

  it("replaces glTF's shared default material, which is white at metalness 1", async () => {
    const material = (await onlyMesh('.glb', 'triangle.glb')).material as THREE.MeshStandardMaterial
    expect(material.color.getHex()).toBe(FALLBACK_MATERIAL_COLOR)
  })

  it('keeps a material the .gltf actually authored', async () => {
    // The counterweight to the test above: the placeholder rule must not eat
    // real materials, so this file names one and it has to survive.
    const material = (await onlyMesh('.gltf', 'triangle-material.gltf')).material as THREE.MeshStandardMaterial
    expect(material.name).toBe('Painted')
    expect(material.color.getHex()).not.toBe(FALLBACK_MATERIAL_COLOR)
  })
})

describe('parseModel clips', () => {
  it('reports no clips for the static formats', async () => {
    for (const [ext, name] of [
      ['.obj', 'triangle.obj'], ['.stl', 'triangle.stl'],
      ['.ply', 'triangle.ply'], ['.dae', 'triangle.dae'], ['.glb', 'triangle.glb'],
    ]) {
      const { clips } = await parseModel(ext, fixture(name))
      // The panel hides its transport bar on an empty array, so undefined here
      // would be a crash rather than a hidden bar.
      expect(clips).toEqual([])
    }
  })
})

describe('a .gltf that is only half the file', () => {
  it('fails with the external-resources code rather than a loader message', async () => {
    const err = await parseModel('.gltf', fixture('triangle-external.gltf')).catch(e => e)
    expect(err).toBeInstanceOf(ModelParseError)
    expect((err as ModelParseError).code).toBe('external-resources')
  })

  it('names the file it could not reach', async () => {
    await expect(parseModel('.gltf', fixture('triangle-external.gltf'))).rejects.toThrow(/triangle\.bin/)
  })

  it('does not flag a data-URI buffer as external', async () => {
    await expect(parseModel('.gltf', fixture('triangle.gltf'))).resolves.toBeTruthy()
  })

  it('leaves a malformed .gltf as an ordinary parse failure', async () => {
    // Only the missing-sibling case earns the dedicated wording; broken JSON
    // must keep printing the parser's own one-liner.
    const junk = new TextEncoder().encode('{ not json').buffer as ArrayBuffer
    const err = await parseModel('.gltf', junk).catch(e => e)
    expect(err).toBeInstanceOf(Error)
    expect(err).not.toBeInstanceOf(ModelParseError)
  })
})
