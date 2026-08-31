/**
 * The panel's POST-PARSE path — framing, orbit reseat, playback — had zero
 * automated coverage: under jsdom `new THREE.WebGLRenderer()` throws, the
 * setup effect returns early, `stageRef` stays null, and every panel test
 * takes the `if (!stage)` exit before reaching any of this.
 *
 * `mountParsedModel` is the seam that fixes it. It takes the stage as a plain
 * shape, so the real panel and this test drive the SAME function; what stands
 * in for the renderer here is a fake with spies on `render` and `wake`.
 */
import { describe, it, expect, vi } from 'vitest'
import * as THREE from 'three'

import { mountParsedModel, type MountTarget } from '../renderer/components/model-viewer/ModelPreviewPanel'
import type { ParsedModel } from '../renderer/components/model-viewer/loaders'

const fakeStage = () => {
  const stage: MountTarget = {
    camera: new THREE.PerspectiveCamera(50, 1.5, 0.1, 1000),
    controls: {
      enableDamping: true,
      target: new THREE.Vector3(),
      minDistance: 0,
      maxDistance: Infinity,
      update: vi.fn(() => false),
    },
    content: new THREE.Group(),
    grid: new THREE.GridHelper(10, 20),
    render: vi.fn(),
    playback: null,
    playing: false,
    wake: vi.fn(),
  }
  return stage
}

/** A 2-unit cube whose centre sits at (0, 5, 0), i.e. a box far off the origin. */
const cube = (): THREE.Mesh => {
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(2, 2, 2), new THREE.MeshBasicMaterial())
  mesh.position.set(0, 5, 0)
  mesh.updateMatrixWorld(true)
  return mesh
}

const clip = (duration: number) =>
  new THREE.AnimationClip('take', duration, [
    new THREE.VectorKeyframeTrack('.position', [0, duration], [0, 5, 0, 0, 6, 0]),
  ])

const parsedOf = (clips: THREE.AnimationClip[] = []): ParsedModel => ({ object: cube(), clips })

const boxOf = (parsed: ParsedModel) => new THREE.Box3().setFromObject(parsed.object)

describe('mountParsedModel', () => {
  it('hangs the parsed object on the content group', () => {
    const stage = fakeStage()
    const parsed = parsedOf()
    mountParsedModel(stage, parsed, boxOf(parsed))
    expect(stage.content.children).toContain(parsed.object)
  })

  it('frames the model: camera aimed at the box centre from far enough to see it', () => {
    const stage = fakeStage()
    const parsed = parsedOf()
    const box = boxOf(parsed)
    const center = box.getCenter(new THREE.Vector3())

    mountParsedModel(stage, parsed, box)

    // Radius of a 2-unit cube is sqrt(3); the camera must stand clear of it.
    const distance = stage.camera.position.distanceTo(center)
    expect(distance).toBeGreaterThan(Math.sqrt(3))
    // Clip planes are derived from that distance, so the model sits inside them.
    expect(stage.camera.near).toBeLessThan(distance)
    expect(stage.camera.far).toBeGreaterThan(distance)
  })

  it('puts the grid under the model rather than at the origin', () => {
    const stage = fakeStage()
    const parsed = parsedOf()
    const box = boxOf(parsed)

    mountParsedModel(stage, parsed, box)

    expect(stage.grid.position.y).toBeCloseTo(box.min.y, 5)
    expect(stage.grid.position.x).toBeCloseTo(0, 5)
    expect(stage.grid.scale.x).toBeGreaterThan(0)
  })

  it('reseats the orbit rig on the new centre and leaves damping back on', () => {
    const stage = fakeStage()
    const parsed = parsedOf()
    const box = boxOf(parsed)
    const center = box.getCenter(new THREE.Vector3())

    mountParsedModel(stage, parsed, box)

    expect(stage.controls.target.equals(center)).toBe(true)
    expect(stage.controls.update).toHaveBeenCalled()
    // Damping is switched off only for the settling update; leaving it off
    // would kill the camera's inertia for the rest of the session.
    expect(stage.controls.enableDamping).toBe(true)
    expect(stage.controls.minDistance).toBeGreaterThan(0)
    expect(stage.controls.maxDistance).toBeGreaterThan(stage.controls.minDistance)
  })

  it('creates playback and starts the loop for a playable clip', () => {
    const stage = fakeStage()
    const parsed = parsedOf([clip(1.5)])

    const duration = mountParsedModel(stage, parsed, boxOf(parsed))

    expect(duration).toBeCloseTo(1.5, 5)
    expect(stage.playback).not.toBeNull()
    expect(stage.playback?.duration).toBeCloseTo(1.5, 5)
    expect(stage.playing).toBe(true)
    expect(stage.wake).toHaveBeenCalled()
  })

  it('creates no playback for a file with no clips, and draws the one still frame', () => {
    const stage = fakeStage()
    const parsed = parsedOf()

    const duration = mountParsedModel(stage, parsed, boxOf(parsed))

    expect(duration).toBe(0)
    expect(stage.playback).toBeNull()
    expect(stage.playing).toBe(false)
    // Nothing will animate, so without this single draw the panel stays empty.
    expect(stage.render).toHaveBeenCalled()
    expect(stage.wake).not.toHaveBeenCalled()
  })

  it('treats a zero-length clip as nothing to play', () => {
    const stage = fakeStage()
    const parsed = parsedOf([clip(0)])

    expect(mountParsedModel(stage, parsed, boxOf(parsed))).toBe(0)
    expect(stage.playback).toBeNull()
    expect(stage.render).toHaveBeenCalled()
  })
})
