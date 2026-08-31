/**
 * `parseModel` is deliberately free of any WebGL reference so it can be
 * exercised for real under jsdom — FBXLoader.parse is pure JS. The fixture is a
 * hand-written ASCII FBX (see `fixtures/animated-triangle.fbx`) rather than an
 * exported binary: it is text, it is 2 KB, and every field in it is readable by
 * whoever next has to change this.
 */
import { describe, it, expect, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import * as THREE from 'three'
import { parseModel, disposeObject, playableClip, FALLBACK_MATERIAL_COLOR } from '../renderer/components/model-viewer/loaders'

const fixture = (name: string): ArrayBuffer => {
  const buf = readFileSync(resolve(__dirname, 'fixtures', name))
  return buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength) as ArrayBuffer
}

const meshes = (root: THREE.Object3D): THREE.Mesh[] => {
  const out: THREE.Mesh[] = []
  root.traverse(o => { if ((o as THREE.Mesh).isMesh) out.push(o as THREE.Mesh) })
  return out
}

describe('parseModel', () => {
  it('returns the mesh hierarchy of an FBX file', async () => {
    const { object } = await parseModel('.fbx', fixture('animated-triangle.fbx'))
    const found = meshes(object)
    expect(found).toHaveLength(1)
    expect(found[0].name).toBe('Triangle')
    expect(found[0].geometry.getAttribute('position').count).toBe(3)
  })

  it('returns the file animation clips', async () => {
    const { clips } = await parseModel('.fbx', fixture('animated-triangle.fbx'))
    expect(clips.map(c => c.name)).toEqual(['Take 001'])
    expect(clips[0].duration).toBeCloseTo(1, 3)
    expect(clips[0].tracks.length).toBeGreaterThan(0)
  })

  it('substitutes a neutral gray standard material where the file resolved none', async () => {
    // The fixture has no Material object, so the loader hands back its own
    // near-white placeholder — which reads as a blown-out surface, not as
    // "untextured", under this scene's lighting.
    const { object } = await parseModel('.fbx', fixture('animated-triangle.fbx'))
    const material = meshes(object)[0].material as THREE.MeshStandardMaterial
    expect(material.isMeshStandardMaterial).toBe(true)
    expect(material.color.getHex()).toBe(FALLBACK_MATERIAL_COLOR)
  })

  it('accepts the extension case-insensitively', async () => {
    await expect(parseModel('.FBX', fixture('animated-triangle.fbx'))).resolves.toBeTruthy()
  })

  it('rejects an extension it has no loader for, naming it', async () => {
    await expect(parseModel('.abc', new ArrayBuffer(8))).rejects.toThrow(/\.abc/)
  })

  it('surfaces the parser failure for a file that is not an FBX', async () => {
    const junk = new TextEncoder().encode('this is a text file, not a model').buffer as ArrayBuffer
    // The message is what the panel prints under its generic error line, so it
    // has to be a real one-liner and not an empty throw.
    await expect(parseModel('.fbx', junk)).rejects.toThrow(/FBXLoader/)
  })
})

describe('disposeObject', () => {
  it('releases geometry, materials and their textures', () => {
    const texture = new THREE.Texture()
    const material = new THREE.MeshStandardMaterial({ map: texture })
    const geometry = new THREE.BoxGeometry()
    const root = new THREE.Group()
    root.add(new THREE.Mesh(geometry, material))

    const spies = [geometry, material, texture].map(r => vi.spyOn(r, 'dispose'))
    disposeObject(root)
    for (const spy of spies) expect(spy).toHaveBeenCalledTimes(1)
  })

  it('disposes a texture shared by two materials exactly once', () => {
    const texture = new THREE.Texture()
    const root = new THREE.Group()
    for (let i = 0; i < 2; i++) {
      root.add(new THREE.Mesh(new THREE.BoxGeometry(), new THREE.MeshStandardMaterial({ map: texture })))
    }
    const spy = vi.spyOn(texture, 'dispose')
    disposeObject(root)
    expect(spy).toHaveBeenCalledTimes(1)
  })

  it('handles a mesh carrying a material array', () => {
    const a = new THREE.MeshStandardMaterial()
    const b = new THREE.MeshStandardMaterial()
    const root = new THREE.Group()
    root.add(new THREE.Mesh(new THREE.BoxGeometry(), [a, b]))
    const spies = [a, b].map(m => vi.spyOn(m, 'dispose'))
    disposeObject(root)
    for (const spy of spies) expect(spy).toHaveBeenCalledTimes(1)
  })

  it('frees everything a parsed FBX allocated', async () => {
    const { object } = await parseModel('.fbx', fixture('animated-triangle.fbx'))
    const mesh = meshes(object)[0]
    const geometrySpy = vi.spyOn(mesh.geometry, 'dispose')
    const materialSpy = vi.spyOn(mesh.material as THREE.Material, 'dispose')
    disposeObject(object)
    expect(geometrySpy).toHaveBeenCalled()
    expect(materialSpy).toHaveBeenCalled()
  })
})

describe('playableClip', () => {
  const track = () => new THREE.VectorKeyframeTrack('.position', [0, 1], [0, 0, 0, 5, 0, 0])

  it('is null when the file has no animation', () => {
    expect(playableClip([])).toBeNull()
  })

  it('picks the first clip of a multi-clip file', () => {
    const first = new THREE.AnimationClip('a', 1, [track()])
    const second = new THREE.AnimationClip('b', 1, [track()])
    expect(playableClip([first, second])).toBe(first)
  })

  it('refuses a zero-duration clip', () => {
    expect(playableClip([new THREE.AnimationClip('single-key', 0, [track()])])).toBeNull()
  })

  it('a zero-duration clip really does break the mixer — this is why', () => {
    // The guard above is not tidiness. AnimationAction wraps the loop with
    // floor(time / duration): at duration 0 that is Infinity, `pending`
    // becomes Infinity - Infinity = NaN, the "have to stop" branch never
    // fires, and the action's time is NaN from the first update onward and
    // stays there. Nothing throws and no error state exists to catch it.
    //
    // MEASURED, three 0.185.1: the NaN does NOT reach the object's transform
    // here — the interpolant clamps, so the pose freezes on the clip's last
    // keyframe instead. The action is still permanently invalid and a rAF loop
    // would burn frames forever on a clip with nothing to play.
    const object = new THREE.Object3D()
    const mixer = new THREE.AnimationMixer(object)
    const action = mixer
      .clipAction(new THREE.AnimationClip('poison', 0, [track()]))
      .setLoop(THREE.LoopRepeat, Infinity)
    action.play()
    mixer.update(0.016)
    expect(Number.isNaN(action.time)).toBe(true)
    mixer.update(0.016)
    expect(Number.isNaN(action.time)).toBe(true)
  })

  it('the same clip with a real duration leaves the object finite', () => {
    const object = new THREE.Object3D()
    const mixer = new THREE.AnimationMixer(object)
    const clip = new THREE.AnimationClip('fine', 1, [track()])
    const action = mixer.clipAction(playableClip([clip])!).setLoop(THREE.LoopRepeat, Infinity)
    action.play()
    mixer.update(0.5)
    expect(Number.isFinite(action.time)).toBe(true)
    expect(Number.isFinite(object.position.x)).toBe(true)
  })
})

describe('disposeObject beyond meshes', () => {
  it('frees a Line — FBXLoader emits one per NURBS curve', () => {
    const geometry = new THREE.BufferGeometry()
    const material = new THREE.LineBasicMaterial()
    const root = new THREE.Group()
    root.add(new THREE.Line(geometry, material))
    const spies = [geometry, material].map(r => vi.spyOn(r, 'dispose'))
    disposeObject(root)
    for (const spy of spies) expect(spy).toHaveBeenCalledTimes(1)
  })

  it('frees Points as well', () => {
    const geometry = new THREE.BufferGeometry()
    const material = new THREE.PointsMaterial()
    const root = new THREE.Group()
    root.add(new THREE.Points(geometry, material))
    const spies = [geometry, material].map(r => vi.spyOn(r, 'dispose'))
    disposeObject(root)
    for (const spy of spies) expect(spy).toHaveBeenCalledTimes(1)
  })

  it('frees the skeleton of a rigged mesh', () => {
    // Skeleton.dispose releases the bone DataTexture three allocates at render
    // time; nothing else does. A rigged FBX per file is the core scenario.
    const bone = new THREE.Bone()
    const skeleton = new THREE.Skeleton([bone])
    const mesh = new THREE.SkinnedMesh(new THREE.BufferGeometry(), new THREE.MeshStandardMaterial())
    mesh.add(bone)
    mesh.bind(skeleton)
    const root = new THREE.Group()
    root.add(mesh)

    const spy = vi.spyOn(skeleton, 'dispose')
    disposeObject(root)
    expect(spy).toHaveBeenCalledTimes(1)
  })

  it('walks past a plain Group without touching it', () => {
    const root = new THREE.Group()
    root.add(new THREE.Group())
    expect(() => disposeObject(root)).not.toThrow()
  })
})
