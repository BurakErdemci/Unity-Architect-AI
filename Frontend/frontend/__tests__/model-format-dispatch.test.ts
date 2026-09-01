/**
 * `parseModel` routing, one real file per supported extension. What is measured
 * is the OUTCOME of the dispatch — geometry, material, clips — not that a
 * switch case exists, so a rewrite that keeps the behaviour keeps the test.
 *
 * Every fixture is a hand-written triangle. Six of the seven are text and
 * readable in the diff; `triangle.glb` is 476 bytes of binary, generated from
 * the same JSON as `triangle.gltf` with the buffer moved into a BIN chunk.
 */
import { describe, it, expect, vi, beforeAll } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import * as THREE from 'three'
import { parseModel, ModelParseError, FALLBACK_MATERIAL_COLOR } from '../renderer/components/model-viewer/loaders'
import { MODEL_EXTENSIONS } from '../renderer/components/model-viewer/extensions'

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

/**
 * An inline fixture, allocated in the same realm as `fixture()` and for the same
 * reason. MEASURED: `TextEncoder().encode(s).buffer` is a Node-realm
 * ArrayBuffer, and PLYLoader's `instanceof ArrayBuffer` is false for it under
 * jsdom — the loader then treats the bytes as an already-decoded string and
 * quietly returns a colour-less geometry.
 */
const bytes = (text: string): ArrayBuffer => {
  const encoded = new TextEncoder().encode(text)
  const out = new ArrayBuffer(encoded.byteLength)
  new Uint8Array(out).set(encoded)
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

/**
 * The gap: an extension gets added to `MODEL_EXTENSIONS` and the main-process
 * mirror, the read channel starts handing back its bytes, and `parseModel` has
 * no case for it — so every file of that type falls to the default and the user
 * sees a generic failure on a format the app claims to support. Nothing above
 * would be red, because every test above names its formats one at a time.
 */
describe('every listed extension reaches a handler', () => {
  // Not a valid file of any format on purpose: what is measured is WHICH code
  // answers, not that it succeeds. A real handler answers with its own parser's
  // complaint, or — for the tolerant ones — an empty but successful parse.
  const junk = () => bytes('not a model')

  /**
   * An extension no loader can ever exist for. It is the CONTROL: whatever the
   * dispatch answers it with IS the unsupported outcome, measured rather than
   * spelled out.
   *
   * This used to be the literal sentence the default case throws (AUDIT
   * `source-text-assertion`). Rewording that sentence changes nothing a user or
   * a caller can observe, and it turned two green tests red — so the wording was
   * pinned by tests that were not about wording. Comparing against a live
   * control keeps the property ("did this extension reach a loader") and lets
   * the sentence change freely.
   */
  const CONTROL = '.__no_loader_can_exist_for_this__'

  /**
   * How `parseModel` answered `ext`, with the extension itself spliced out —
   * that substring is the only part of an unsupported answer that legitimately
   * differs between two unsupported extensions. `null` means it resolved, which
   * only a real handler does.
   */
  const answer = async (ext: string): Promise<string | null> => {
    const outcome = await parseModel(ext, junk()).then(() => null, (e: unknown) => e)
    if (outcome === null) return null
    const message = String((outcome as Error)?.message ?? outcome)
    return message.split(ext).join('<ext>')
  }

  let unsupported = ''
  beforeAll(async () => { unsupported = (await answer(CONTROL)) ?? '' })

  it('the control extension really does fall to the default case', async () => {
    // Without this the comparisons below would all pass against an empty string.
    expect(unsupported.length).toBeGreaterThan(0)
  })

  for (const ext of MODEL_EXTENSIONS) {
    it(`${ext} is dispatched to a loader, not to the default case`, async () => {
      expect(await answer(ext)).not.toBe(unsupported)
    })
  }

  it('an extension with no handler DOES fall to the default case', async () => {
    // The counterweight: without it the loop above would pass just as happily
    // against a `parseModel` that resolved for everything.
    expect(await answer('.blend')).toBe(unsupported)
  })

  it('the list under test is not empty', () => {
    expect(MODEL_EXTENSIONS.length).toBeGreaterThan(0)
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

  /**
   * The fallback material is what a vertex-coloured file loses its colours to.
   * Both formats below store the colour on the GEOMETRY, and a material with
   * `vertexColors` off ignores that attribute silently — the model still draws,
   * just flat gray, so nothing on screen says anything was dropped.
   */
  it('carries vertexColors onto the .obj fallback material', async () => {
    const obj = 'v 0 0 0 1 0 0\nv 1 0 0 0 1 0\nv 0 1 0 0 0 1\nf 1 2 3\n'
    const mesh = meshes((await parseModel('.obj', bytes(obj))).object)[0]
    const material = mesh.material as THREE.MeshStandardMaterial

    expect(mesh.geometry.getAttribute('color')).toBeTruthy()
    expect(material.color.getHex()).toBe(FALLBACK_MATERIAL_COLOR)
    expect(material.vertexColors).toBe(true)
  })

  it('leaves vertexColors off when the .obj has no per-vertex colour', async () => {
    const material = (await onlyMesh('.obj', 'triangle.obj')).material as THREE.MeshStandardMaterial
    expect(material.vertexColors).toBe(false)
  })

  it('carries vertexColors onto the .ply fallback material', async () => {
    // PLY has no material at all, so the geometry attribute is the only signal.
    const ply = [
      'ply', 'format ascii 1.0', 'element vertex 3',
      'property float x', 'property float y', 'property float z',
      'property uchar red', 'property uchar green', 'property uchar blue',
      'element face 1', 'property list uchar int vertex_indices', 'end_header',
      '0 0 0 255 0 0', '1 0 0 0 255 0', '0 1 0 0 0 255', '3 0 1 2', '',
    ].join('\n')
    const mesh = meshes((await parseModel('.ply', bytes(ply))).object)[0]
    const material = mesh.material as THREE.MeshStandardMaterial

    expect(mesh.geometry.getAttribute('color')).toBeTruthy()
    expect(material.vertexColors).toBe(true)
  })

  it('leaves vertexColors off for a .ply without colour', async () => {
    const material = (await onlyMesh('.ply', 'triangle.ply')).material as THREE.MeshStandardMaterial
    expect(material.vertexColors).toBe(false)
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
    const err = await parseModel('.gltf', bytes('{ not json')).catch(e => e)
    expect(err).toBeInstanceOf(Error)
    expect(err).not.toBeInstanceOf(ModelParseError)
  })

  it('survives a document whose `buffers` is not a list', async () => {
    // Valid JSON, invalid glTF. The external-resource check used to SPREAD
    // whatever sat under that key, so `5` produced a TypeError from our own
    // code and the panel printed it as the model's failure. It has to stay the
    // loader's complaint about a malformed document.
    const err = await parseModel('.gltf', bytes('{"buffers": 5, "images": 7}')).catch(e => e)
    expect(err).toBeInstanceOf(Error)
    expect(err).not.toBeInstanceOf(ModelParseError)
    expect((err as Error).message).not.toMatch(/is not iterable/)
  })
})
