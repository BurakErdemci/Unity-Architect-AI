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
import { parseModel, disposeObject, FALLBACK_MATERIAL_COLOR } from '../renderer/components/model-viewer/loaders'

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
  it('returns the mesh hierarchy of an FBX file', () => {
    const { object } = parseModel('.fbx', fixture('animated-triangle.fbx'))
    const found = meshes(object)
    expect(found).toHaveLength(1)
    expect(found[0].name).toBe('Triangle')
    expect(found[0].geometry.getAttribute('position').count).toBe(3)
  })

  it('returns the file animation clips', () => {
    const { clips } = parseModel('.fbx', fixture('animated-triangle.fbx'))
    expect(clips.map(c => c.name)).toEqual(['Take 001'])
    expect(clips[0].duration).toBeCloseTo(1, 3)
    expect(clips[0].tracks.length).toBeGreaterThan(0)
  })

  it('substitutes a neutral gray standard material where the file resolved none', () => {
    // The fixture has no Material object, so the loader hands back its own
    // near-white placeholder — which reads as a blown-out surface, not as
    // "untextured", under this scene's lighting.
    const { object } = parseModel('.fbx', fixture('animated-triangle.fbx'))
    const material = meshes(object)[0].material as THREE.MeshStandardMaterial
    expect(material.isMeshStandardMaterial).toBe(true)
    expect(material.color.getHex()).toBe(FALLBACK_MATERIAL_COLOR)
  })

  it('accepts the extension case-insensitively', () => {
    expect(() => parseModel('.FBX', fixture('animated-triangle.fbx'))).not.toThrow()
  })

  it('rejects an extension it has no loader for, naming it', () => {
    expect(() => parseModel('.glb', new ArrayBuffer(8))).toThrow(/\.glb/)
  })

  it('surfaces the parser failure for a file that is not an FBX', () => {
    const junk = new TextEncoder().encode('this is a text file, not a model').buffer as ArrayBuffer
    // The message is what the panel prints under its generic error line, so it
    // has to be a real one-liner and not an empty throw.
    expect(() => parseModel('.fbx', junk)).toThrow(/FBXLoader/)
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

  it('frees everything a parsed FBX allocated', () => {
    const { object } = parseModel('.fbx', fixture('animated-triangle.fbx'))
    const mesh = meshes(object)[0]
    const geometrySpy = vi.spyOn(mesh.geometry, 'dispose')
    const materialSpy = vi.spyOn(mesh.material as THREE.Material, 'dispose')
    disposeObject(object)
    expect(geometrySpy).toHaveBeenCalled()
    expect(materialSpy).toHaveBeenCalled()
  })
})
