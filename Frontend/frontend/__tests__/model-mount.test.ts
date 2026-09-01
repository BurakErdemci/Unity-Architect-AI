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

import { clearContent, mountParsedModel, viewableBounds, type ClearTarget } from '../renderer/components/model-viewer/ModelPreviewPanel'
import { hasDrawableSkeleton, parseModel, playableClip, type ParsedModel } from '../renderer/components/model-viewer/loaders'
import { buildMannequin, isMannequinMesh } from '../renderer/components/model-viewer/mannequin'

const fakeStage = () => {
  const stage: ClearTarget = {
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
    mannequin: null,
    frame: null,
  }
  return stage
}

/**
 * Everything the mannequin put on the stage. It is collected from the model's
 * own graph, not from `content`'s direct children: the volumes hang off the
 * bones, which is what makes a clip move them.
 */
const mannequinMeshesIn = (stage: ClearTarget): THREE.Mesh[] => {
  const found: THREE.Mesh[] = []
  stage.content.traverse(child => { if (isMannequinMesh(child)) found.push(child as THREE.Mesh) })
  return found
}

const skeletonHelperIn = (stage: ClearTarget): boolean =>
  stage.content.children.some(c => (c as THREE.SkeletonHelper).isSkeletonHelper === true)

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

  it('builds mannequin volumes on its bones and plays the clip', async () => {
    const stage = fakeStage()
    const parsed = await parseFixture()
    // The message this branch exists to avoid: a non-null bounds is what keeps
    // the panel out of "nothing visible here".
    expect(viewableBounds(parsed, boxOf(parsed))).not.toBeNull()

    const duration = mountParsedModel(stage, parsed, boundsOf(parsed))

    const meshes = mannequinMeshesIn(stage)
    expect(meshes.length).toBeGreaterThan(0)
    expect(stage.mannequin?.meshes).toEqual(meshes)
    // The stick figure it replaced is gone, not drawn underneath.
    expect(skeletonHelperIn(stage)).toBe(false)
    // Attached to the rig itself, which is the whole retargeting-free premise.
    for (const mesh of meshes) expect(mesh.parent).not.toBe(stage.content)
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
    expect(mannequinMeshesIn(stage).length).toBeGreaterThan(0)
    expect(stage.playback).toBeNull()
    expect(stage.playing).toBe(false)
    expect(stage.render).toHaveBeenCalled()
  })

  it('frees the volumes when the panel switches file, and stays free on unmount', async () => {
    const stage = fakeStage()
    const parsed = await parseFixture()
    mountParsedModel(stage, parsed, boundsOf(parsed))
    const meshes = mannequinMeshesIn(stage)
    const geometries = meshes.map(mesh => vi.spyOn(mesh.geometry, 'dispose'))
    // One material is shared by every volume, so the count is the assertion:
    // disposing it twice is what a wrong teardown ORDER looks like.
    const material = vi.spyOn(meshes[0].material as THREE.Material, 'dispose')

    clearContent(stage)

    for (const geometry of geometries) expect(geometry).toHaveBeenCalledTimes(1)
    expect(material).toHaveBeenCalledTimes(1)
    expect(stage.mannequin).toBeNull()
    for (const mesh of meshes) expect(mesh.parent).toBeNull()
    expect(mannequinMeshesIn(stage)).toHaveLength(0)

    // The panel's unmount runs the same teardown after a switch already ran it.
    clearContent(stage)
    expect(material).toHaveBeenCalledTimes(1)
  })
})

/**
 * The retargeting-free premise: the volumes are children of the file's own
 * bones, so a clip that poses the rig poses them, with nothing mapping one to
 * the other. A rotation drives it here because that is what a real humanoid
 * clip is made of — the bones-only fixture animates a bone TRANSLATION, which
 * moves the joint the capsule already spans and so proves nothing about this.
 */
describe('a posed rig', () => {
  const rig = (): ParsedModel => {
    const root = new THREE.Group()
    const hips = new THREE.Bone()
    hips.name = 'Hips'
    const spine = new THREE.Bone()
    spine.name = 'Spine'
    spine.position.set(0, 10, 0)
    hips.add(spine)
    root.add(hips)
    root.updateMatrixWorld(true)
    const turn = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), Math.PI / 2)
    return {
      object: root,
      clips: [new THREE.AnimationClip('take', 1, [
        new THREE.QuaternionKeyframeTrack('Hips.quaternion', [0, 1], [0, 0, 0, 1, ...turn.toArray()]),
      ])],
    }
  }

  it('moves the volumes with the clip, including a paused seek', () => {
    const stage = fakeStage()
    const parsed = rig()
    mountParsedModel(stage, parsed, boundsOf(parsed))
    const mesh = mannequinMeshesIn(stage)[0]

    const at = () => {
      // Stands in for the traversal the real renderer performs each frame.
      stage.content.updateMatrixWorld(true)
      return mesh.getWorldPosition(new THREE.Vector3())
    }

    const atStart = at().clone()
    // Mid-clip, not the end: the clip loops, so time 1 wraps back to the
    // opening pose and would prove nothing.
    stage.playback!.seek(0.5)
    const atHalf = at()

    expect(atStart.y).toBeCloseTo(5, 3)
    expect(atHalf.distanceTo(atStart)).toBeGreaterThan(1)
  })
})

/**
 * A file that brought its own meshes is already its own silhouette. Capsules
 * over it would be an overlay nobody asked for, and on a skinned character
 * they would sit INSIDE the body and poke through it.
 */
describe('a file that has both geometry and bones', () => {
  it('gets no mannequin volumes at all', () => {
    const root = new THREE.Group()
    const hips = new THREE.Bone()
    const spine = new THREE.Bone()
    spine.position.set(0, 10, 0)
    hips.add(spine)
    root.add(hips, cube())
    root.updateMatrixWorld(true)
    const parsed: ParsedModel = { object: root, clips: [] }

    const stage = fakeStage()
    // A handle left over from whatever was on the stage before. Mounting owns
    // the slot on both branches, so this must not survive into the new file —
    // and dropping it without freeing it would leak its buffers, so overwriting
    // is not enough.
    const stale = { meshes: [], dispose: vi.fn() }
    stage.mannequin = stale
    const bounds = boundsOf(parsed)
    expect(bounds.skeleton).toBe(false)
    mountParsedModel(stage, parsed, bounds)

    expect(mannequinMeshesIn(stage)).toHaveLength(0)
    expect(stage.mannequin).toBeNull()
    expect(stale.dispose).toHaveBeenCalledTimes(1)
  })
})

describe('a file with neither geometry nor bones', () => {
  it('has nothing to show, which is what the empty-file message says', () => {
    const parsed: ParsedModel = { object: new THREE.Group(), clips: [] }
    expect(viewableBounds(parsed, boxOf(parsed))).toBeNull()
  })
})

/**
 * A volume is drawn only for a bone whose parent is also a bone — the rule
 * THREE.SkeletonHelper's segment emission gave us (measured, three 0.185.1,
 * SkeletonHelper.js:44) and the mannequin kept, because a capsule needs the
 * same pair to span. Neither shape below has one, so a figure built from them
 * would be empty — an object that mounts but renders nothing, which is
 * indistinguishable on screen from a load that never finished. `viewableBounds`
 * has to treat that the same as "nothing to show" rather than route it into
 * the skeleton path.
 */
describe('a rig with no bone-to-bone segment to draw', () => {
  it('a single bone is called empty, not framed by a figure that draws nothing', () => {
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

/**
 * The contract 92ce789 was about, asserted directly instead of being left to
 * two sets of fixtures in two files that happen to agree.
 *
 * The panel decides whether a file gets the skeleton branch with
 * `hasDrawableSkeleton`; `buildMannequin` independently decides whether it has
 * anything to build. If those two ever disagree in the direction "gate says
 * yes, builder says nothing", the panel frames an empty viewport and calls it a
 * successful load — a blank panel indistinguishable from a load that hung,
 * which is the exact bug 92ce789 fixed. Both sides answer "is there a bone
 * whose parent is a bone", but they are separate traversals in separate
 * modules, so nothing except this stops one from drifting.
 */
describe('the drawable-rig gate and the mannequin builder', () => {
  const chain = (): THREE.Bone => {
    const hips = new THREE.Bone()
    hips.name = 'Hips'
    const spine = new THREE.Bone()
    spine.name = 'Spine'
    spine.position.set(0, 10, 0)
    hips.add(spine)
    return hips
  }

  const flatBones = (root: THREE.Object3D): THREE.Object3D => {
    for (let i = 0; i < 3; i++) {
      const bone = new THREE.Bone()
      bone.position.set(i + 1, 0, 0)
      root.add(bone)
    }
    return root
  }

  /**
   * `drawable`: there is a bone-to-bone segment, so both sides must say yes.
   * `skeleton`: whether the PANEL routes the file to that branch, which is a
   * strictly narrower question — a file with geometry is framed by its meshes
   * and never consults its bones at all.
   */
  const rigs: { name: string; build: () => THREE.Object3D; drawable: boolean; skeleton: boolean }[] = [
    { name: 'a bone chain', build: () => new THREE.Group().add(chain()), drawable: true, skeleton: true },
    { name: 'a chain plus stray bones hanging off the group', build: () => flatBones(new THREE.Group().add(chain())), drawable: true, skeleton: true },
    { name: 'a single bone as the root', build: () => { const b = new THREE.Bone(); b.position.set(1, 2, 3); return b }, drawable: false, skeleton: false },
    { name: 'a flat rig, every bone parented to a group', build: () => flatBones(new THREE.Group()), drawable: false, skeleton: false },
    { name: 'no bones at all', build: () => new THREE.Group(), drawable: false, skeleton: false },
    { name: 'geometry alongside a bone chain', build: () => new THREE.Group().add(chain(), cube()), drawable: true, skeleton: false },
  ]

  for (const rig of rigs) {
    it(`agrees on ${rig.name}`, () => {
      const gate = rig.build()
      gate.updateMatrixWorld(true)
      expect(hasDrawableSkeleton(gate)).toBe(rig.drawable)

      // A fresh instance: building attaches meshes to the bones, so the two
      // sides must not be asked about the same mutated graph.
      const built = rig.build()
      built.updateMatrixWorld(true)
      const handle = buildMannequin(built)
      expect(handle !== null).toBe(rig.drawable)
      // A non-null handle is never an empty one, or the branch would draw
      // nothing while reporting success.
      if (handle) expect(handle.meshes.length).toBeGreaterThan(0)
      handle?.dispose()

      const parsed: ParsedModel = { object: gate, clips: [] }
      const bounds = viewableBounds(parsed, boxOf(parsed))
      expect(bounds?.skeleton === true).toBe(rig.skeleton)
      // The property that keeps the panel off a blank viewport: whenever it
      // commits to the skeleton branch, there is something to show.
      if (bounds?.skeleton) expect(buildMannequin(rig.build())).not.toBeNull()
    })
  }
})
