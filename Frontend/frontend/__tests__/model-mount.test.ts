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
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import * as THREE from 'three'

import { mountParsedModel, viewableBounds, type MountTarget } from '../renderer/components/model-viewer/ModelPreviewPanel'
import { disposeObject, parseModel, playableClip, type ParsedModel } from '../renderer/components/model-viewer/loaders'

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

/** What the panel hands the mount seam, computed the way the panel computes it. */
const boundsOf = (parsed: ParsedModel) => {
  const bounds = viewableBounds(parsed, boxOf(parsed))
  if (!bounds) throw new Error('fixture has nothing to show')
  return bounds
}

describe('mountParsedModel', () => {
  it('hangs the parsed object on the content group', () => {
    const stage = fakeStage()
    const parsed = parsedOf()
    mountParsedModel(stage, parsed, boundsOf(parsed))
    expect(stage.content.children).toContain(parsed.object)
  })

  it('frames the model: camera aimed at the box centre from far enough to see it', () => {
    const stage = fakeStage()
    const parsed = parsedOf()
    const box = boxOf(parsed)
    const center = box.getCenter(new THREE.Vector3())

    mountParsedModel(stage, parsed, { box, skeleton: false })

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

    mountParsedModel(stage, parsed, { box, skeleton: false })

    expect(stage.grid.position.y).toBeCloseTo(box.min.y, 5)
    expect(stage.grid.position.x).toBeCloseTo(0, 5)
    expect(stage.grid.scale.x).toBeGreaterThan(0)
  })

  it('reseats the orbit rig on the new centre and leaves damping back on', () => {
    const stage = fakeStage()
    const parsed = parsedOf()
    const box = boxOf(parsed)
    const center = box.getCenter(new THREE.Vector3())

    mountParsedModel(stage, parsed, { box, skeleton: false })

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

    const duration = mountParsedModel(stage, parsed, boundsOf(parsed))

    expect(duration).toBeCloseTo(1.5, 5)
    expect(stage.playback).not.toBeNull()
    expect(stage.playback?.duration).toBeCloseTo(1.5, 5)
    expect(stage.playing).toBe(true)
    expect(stage.wake).toHaveBeenCalled()
  })

  it('creates no playback for a file with no clips, and draws the one still frame', () => {
    const stage = fakeStage()
    const parsed = parsedOf()

    const duration = mountParsedModel(stage, parsed, boundsOf(parsed))

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

    expect(mountParsedModel(stage, parsed, boundsOf(parsed))).toBe(0)
    expect(stage.playback).toBeNull()
    expect(stage.render).toHaveBeenCalled()
  })
})

/**
 * The Mixamo "without skin" shape: bones and clips, not one vertex. It is what
 * a bought animation pack is made of, so it is the case the preview is pointed
 * at most often — and every one of those files used to land on the panel's
 * "nothing visible here" message.
 */
describe('an animation-only file', () => {
  const fixture = (): ArrayBuffer => {
    const buf = readFileSync(resolve(__dirname, 'fixtures', 'bones-only.fbx'))
    return buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength) as ArrayBuffer
  }

  /** Real FBX bytes, real loader: two bones 10 units apart, one 1-second clip. */
  const parseFixture = async (): Promise<ParsedModel> => parseModel('.fbx', fixture())

  const helperIn = (stage: MountTarget) =>
    stage.content.children.find(c => (c as THREE.SkeletonHelper).isSkeletonHelper) as
      | THREE.SkeletonHelper
      | undefined

  it('parses to bones and a clip with an empty bounding box', async () => {
    const parsed = await parseFixture()
    const bones: THREE.Bone[] = []
    parsed.object.traverse(o => { if ((o as THREE.Bone).isBone) bones.push(o as THREE.Bone) })

    expect(bones).toHaveLength(2)
    expect(playableClip(parsed.clips)).not.toBeNull()
    // The premise of the whole branch: nothing here has geometry to measure.
    expect(boxOf(parsed).isEmpty()).toBe(true)
  })

  it('is framed by its bones instead of being called empty', async () => {
    const parsed = await parseFixture()
    const bounds = viewableBounds(parsed, boxOf(parsed))

    expect(bounds?.skeleton).toBe(true)
    expect(bounds?.box.isEmpty()).toBe(false)
  })

  it('draws the skeleton and plays the clip', async () => {
    const stage = fakeStage()
    const parsed = await parseFixture()

    const duration = mountParsedModel(stage, parsed, boundsOf(parsed))

    const helper = helperIn(stage)
    expect(helper).toBeDefined()
    // Added after the rig, because the helper reads bone world matrices during
    // the same traversal and the graph is walked in child order.
    expect(stage.content.children.indexOf(helper!)).toBeGreaterThan(
      stage.content.children.indexOf(parsed.object),
    )
    expect(duration).toBeCloseTo(1, 3)
    expect(stage.playback).not.toBeNull()
    expect(stage.playing).toBe(true)
    expect(stage.wake).toHaveBeenCalled()
  })

  it('frames it somewhere real rather than at the origin', async () => {
    const stage = fakeStage()
    const parsed = await parseFixture()

    mountParsedModel(stage, parsed, boundsOf(parsed))

    const { x, y, z } = stage.camera.position
    expect(Number.isFinite(x) && Number.isFinite(y) && Number.isFinite(z)).toBe(true)
    expect(stage.camera.position.length()).toBeGreaterThan(0)
    expect(stage.camera.near).toBeGreaterThan(0)
    expect(stage.camera.far).toBeGreaterThan(stage.camera.near)
    expect(stage.controls.target.y).toBeCloseTo(5, 3)
  })

  it('still shows the rig when there is nothing to play', async () => {
    const stage = fakeStage()
    const parsed = await parseFixture()
    // A rig with no clip is worth seeing; it just has no transport bar.
    const duration = mountParsedModel(stage, { ...parsed, clips: [] }, boundsOf(parsed))

    expect(duration).toBe(0)
    expect(helperIn(stage)).toBeDefined()
    expect(stage.playback).toBeNull()
    expect(stage.playing).toBe(false)
    expect(stage.render).toHaveBeenCalled()
  })

  it('moves the drawn skeleton with the clip, including a paused seek', async () => {
    const stage = fakeStage()
    const parsed = await parseFixture()
    mountParsedModel(stage, parsed, boundsOf(parsed))
    const helper = helperIn(stage)!

    // What a render does: walk the graph, which updates the bones and then the
    // helper's line vertices from them. `stage.render` is a spy here, so this
    // stands in for the traversal the real renderer performs.
    const drawn = () => {
      stage.content.updateMatrixWorld(true)
      return [...(helper.geometry.getAttribute('position').array as Float32Array)]
    }

    const atStart = drawn()
    // Mid-clip, not the end: the clip loops, so time 1 of a 1-second take
    // wraps back to the opening pose and would prove nothing.
    stage.playback!.seek(0.5)
    const atHalf = drawn()

    expect(atHalf).not.toEqual(atStart)
    // The pose is the clip's own: the child bone travels y 10 -> 14, so the
    // helper's first vertex sits halfway up it.
    expect(atStart[1]).toBeCloseTo(10, 3)
    expect(atHalf[1]).toBeCloseTo(12, 3)
  })

  it('lets the panel free the helper with everything else on the stage', async () => {
    const stage = fakeStage()
    const parsed = await parseFixture()
    mountParsedModel(stage, parsed, boundsOf(parsed))
    const helper = helperIn(stage)!
    const geometry = vi.spyOn(helper.geometry, 'dispose')
    const material = vi.spyOn(helper.material as THREE.Material, 'dispose')

    // clearContent's loop, which is the panel's own teardown on file change.
    for (const child of [...stage.content.children]) {
      stage.content.remove(child)
      disposeObject(child)
    }

    expect(geometry).toHaveBeenCalled()
    expect(material).toHaveBeenCalled()
  })
})

describe('a file with neither geometry nor bones', () => {
  it('has nothing to show, which is what the empty-file message says', () => {
    const parsed: ParsedModel = { object: new THREE.Group(), clips: [] }
    expect(viewableBounds(parsed, boxOf(parsed))).toBeNull()
  })
})

/**
 * THREE.SkeletonHelper (measured, three 0.185.1, SkeletonHelper.js:44) draws a
 * segment only for a bone whose parent is also a bone. Neither shape below has
 * one, so a helper built from them would have zero position vertices — an
 * object that mounts but renders nothing, which is indistinguishable on
 * screen from a load that never finished. `viewableBounds` has to treat that
 * the same as "nothing to show" rather than route it into the skeleton path.
 */
describe('a rig with no bone-to-bone segment for SkeletonHelper to draw', () => {
  it('a single bone is called empty, not framed by a helper that draws nothing', () => {
    const bone = new THREE.Bone()
    bone.position.set(1, 2, 3)
    const parsed: ParsedModel = { object: bone, clips: [] }
    expect(viewableBounds(parsed, boxOf(parsed))).toBeNull()
  })

  it('a flat rig — every bone parented to a Group, not to another bone — is called empty too', () => {
    const root = new THREE.Group()
    for (let i = 0; i < 5; i++) {
      const bone = new THREE.Bone()
      bone.position.set(i, 0, 0)
      root.add(bone)
    }
    const parsed: ParsedModel = { object: root, clips: [] }
    expect(viewableBounds(parsed, boxOf(parsed))).toBeNull()
  })
})
