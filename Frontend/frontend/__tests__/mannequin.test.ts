/**
 * The procedural mannequin replaces the SkeletonHelper stick figure for
 * animation-only rigs. Everything here is plain three.js object math, so it
 * runs under jsdom with no renderer — which is the whole reason the module is
 * kept free of DOM and WebGL references.
 */
import { describe, it, expect, vi } from 'vitest'
import * as THREE from 'three'

import {
  buildMannequin,
  classifyBone,
  isMannequinMesh,
  MANNEQUIN_MARKER,
  MANNEQUIN_PROPORTIONS,
  type BoneRole,
} from '../renderer/components/model-viewer/mannequin'

const bone = (name: string, x: number, y: number, z: number, scale: number): THREE.Bone => {
  const b = new THREE.Bone()
  b.name = name
  b.position.set(x * scale, y * scale, z * scale)
  return b
}

/**
 * A Mixamo-shaped rig: 14 bones, one arm and one leg chain, hung off a Group
 * exactly as a loaded FBX hangs its root bone. `scale` multiplies every offset,
 * which is how the "radii follow rig height" claim is measured.
 */
const mixamoRig = (scale = 1): { root: THREE.Object3D; boneCount: number } => {
  const chain = (parent: THREE.Object3D, ...bones: THREE.Bone[]) => {
    let node: THREE.Object3D = parent
    for (const b of bones) {
      node.add(b)
      node = b
    }
  }

  const root = new THREE.Group()
  const hips = bone('mixamorig:Hips', 0, 1, 0, scale)
  root.add(hips)

  const spine = bone('mixamorig:Spine', 0, 0.1, 0, scale)
  const spine1 = bone('mixamorig:Spine1', 0, 0.2, 0, scale)
  chain(hips, spine, spine1)
  chain(
    spine1,
    bone('mixamorig:Neck', 0, 0.2, 0, scale),
    bone('mixamorig:Head', 0, 0.1, 0, scale),
    bone('mixamorig:HeadTop_End', 0, 0.15, 0, scale),
  )
  chain(
    spine1,
    bone('mixamorig:LeftShoulder', 0.05, 0.15, 0, scale),
    bone('mixamorig:LeftArm', 0.15, 0, 0, scale),
    bone('mixamorig:LeftForeArm', 0.25, 0, 0, scale),
    bone('mixamorig:LeftHand', 0.25, 0, 0, scale),
  )
  chain(
    hips,
    bone('mixamorig:LeftUpLeg', 0.1, -0.05, 0, scale),
    bone('mixamorig:LeftLeg', 0, -0.45, 0, scale),
    bone('mixamorig:LeftFoot', 0, -0.45, 0, scale),
    bone('mixamorig:LeftToeBase', 0, -0.05, 0.1, scale),
  )
  root.updateMatrixWorld(true)
  return { root, boneCount: 14 }
}

const meshesOf = (root: THREE.Object3D): THREE.Mesh[] => {
  const found: THREE.Mesh[] = []
  root.traverse(child => {
    if ((child as THREE.Mesh).isMesh) found.push(child as THREE.Mesh)
  })
  return found
}

const capsules = (meshes: THREE.Mesh[]) =>
  meshes.filter(m => m.geometry.type === 'CapsuleGeometry')
const spheres = (meshes: THREE.Mesh[]) =>
  meshes.filter(m => m.geometry.type === 'SphereGeometry')

/** Capsule radius as authored, read back off the geometry's own parameters. */
const radiusOf = (mesh: THREE.Mesh): number =>
  (mesh.geometry as THREE.CapsuleGeometry).parameters.radius

const byBone = (handle: { meshes: THREE.Mesh[] }, boneName: string): THREE.Mesh => {
  const mesh = handle.meshes.find(m => m.name === `mannequin:${boneName}`)
  if (!mesh) throw new Error(`no mannequin mesh for ${boneName}`)
  return mesh
}

describe('classifyBone', () => {
  const cases: [string, BoneRole][] = [
    // Mixamo
    ['mixamorig:Hips', 'spine'],
    ['mixamorig:Spine2', 'spine'],
    ['mixamorig:Neck', 'neck'],
    ['mixamorig:Head', 'head'],
    ['mixamorig:LeftShoulder', 'shoulder'],
    ['mixamorig:LeftArm', 'upperArm'],
    ['mixamorig:LeftForeArm', 'forearm'],
    ['mixamorig:LeftHand', 'hand'],
    ['mixamorig:LeftHandThumb1', 'finger'],
    ['mixamorig:LeftHandIndex3', 'finger'],
    ['mixamorig:LeftUpLeg', 'upperLeg'],
    ['mixamorig:LeftLeg', 'lowerLeg'],
    ['mixamorig:LeftFoot', 'foot'],
    ['mixamorig:LeftToeBase', 'toe'],
    // Unreal
    ['pelvis', 'spine'],
    ['spine_03', 'spine'],
    ['clavicle_l', 'shoulder'],
    ['upperarm_l', 'upperArm'],
    ['lowerarm_l', 'forearm'],
    ['hand_r', 'hand'],
    ['thigh_l', 'upperLeg'],
    ['calf_l', 'lowerLeg'],
    ['foot_l', 'foot'],
    ['ball_l', 'toe'],
    ['neck_01', 'neck'],
    // Blender rigify
    ['upper_arm.L', 'upperArm'],
    ['forearm.L', 'forearm'],
    ['shoulder.R', 'shoulder'],
    ['thigh.L', 'upperLeg'],
    ['shin.L', 'lowerLeg'],
    ['foot.R', 'foot'],
    ['spine.001', 'spine'],
    // Generic
    ['LeftLeg', 'lowerLeg'],
    ['RightArm', 'upperArm'],
    ['Head', 'head'],
    ['Chest', 'spine'],
    ['SomeGizmo', 'other'],
  ]

  it.each(cases)('classifies %s as %s', (name, role) => {
    expect(classifyBone(name)).toBe(role)
  })

  it('is case-insensitive', () => {
    expect(classifyBone('MIXAMORIG:LEFTFOREARM')).toBe('forearm')
    expect(classifyBone('leftupleg')).toBe('upperLeg')
  })

  it('resolves the substring collisions that would swallow a limb', () => {
    // "forearm" contains "arm", "upleg"/"lowerleg" contain "leg", a finger bone
    // contains "hand", a spine bone can contain "middle", and Unreal's toe bone
    // "ball_l" collides with an eyeball bone.
    expect(classifyBone('LeftForeArm')).not.toBe(classifyBone('LeftArm'))
    expect(classifyBone('LeftUpLeg')).not.toBe(classifyBone('LeftLeg'))
    expect(classifyBone('lowerleg_l')).toBe('lowerLeg')
    expect(classifyBone('LeftHandMiddle2')).toBe('finger')
    expect(classifyBone('SpineMiddle')).toBe('spine')
    expect(classifyBone('eyeball_l')).not.toBe('toe')
  })
})

describe('buildMannequin', () => {
  it('builds one capsule per bone-parented bone and exactly one head ellipsoid', () => {
    const { root, boneCount } = mixamoRig()
    const handle = buildMannequin(root)
    if (!handle) throw new Error('expected a mannequin')

    const meshes = meshesOf(root)
    // Every bone but the root one (whose parent is the Group) spans a segment.
    expect(capsules(meshes)).toHaveLength(boneCount - 1)
    expect(spheres(meshes)).toHaveLength(1)
    expect(handle.meshes).toHaveLength(boneCount)
  })

  it('attaches the head ellipsoid to the first head-role bone, not to HeadTop_End', () => {
    const { root } = mixamoRig()
    const handle = buildMannequin(root)!
    const skull = spheres(handle.meshes)[0]
    expect(skull.parent?.name).toBe('mixamorig:Head')
  })

  it('parents every capsule to the segment bone`s parent bone so the clip drives it', () => {
    const { root } = mixamoRig()
    const handle = buildMannequin(root)!
    for (const mesh of capsules(handle.meshes)) {
      const boneName = mesh.name.slice('mannequin:'.length)
      const segment = root.getObjectByName(boneName)
      expect(mesh.parent).toBe(segment?.parent)
      expect((mesh.parent as THREE.Bone).isBone).toBe(true)
    }
  })

  it('spans each capsule from the parent joint to the bone, along the bone offset', () => {
    const { root } = mixamoRig()
    const handle = buildMannequin(root)!
    const forearm = byBone(handle, 'mixamorig:LeftForeArm')
    const offset = root.getObjectByName('mixamorig:LeftForeArm')!.position

    expect(forearm.position.distanceTo(offset.clone().multiplyScalar(0.5))).toBeLessThan(1e-6)
    const axis = new THREE.Vector3(0, 1, 0).applyQuaternion(forearm.quaternion)
    expect(axis.distanceTo(offset.clone().normalize())).toBeLessThan(1e-6)
    expect(radiusOf(forearm)).toBeGreaterThan(0)

    // The capsule must be exactly as long as the bone, caps included. three's
    // `length` argument is the cylinder mid-section only, so the total extent
    // is `length + 2 * radius` and a verbatim bone length overshoots both joints.
    forearm.geometry.computeBoundingBox()
    const box = forearm.geometry.boundingBox!
    expect(box.max.y - box.min.y).toBeCloseTo(offset.length(), 5)
  })

  it('collapses a bone shorter than its own diameter to a ball, not a negative length', () => {
    const root = new THREE.Group()
    const hips = bone('Hips', 0, 1, 0, 1)
    // Spine radius is 0.055 of height; this segment is far shorter than 2r.
    const spine = bone('Spine', 0, 0.001, 0, 1)
    const chest = bone('Chest', 0, 0.9, 0, 1)
    root.add(hips)
    hips.add(spine)
    spine.add(chest)

    const handle = buildMannequin(root)!
    const stub = byBone(handle, 'Spine')
    stub.geometry.computeBoundingBox()
    const extent = stub.geometry.boundingBox!
    expect(Number.isFinite(extent.max.y - extent.min.y)).toBe(true)
    expect(extent.max.y - extent.min.y).toBeCloseTo(2 * radiusOf(stub), 4)
  })

  it('places a zero-length bone`s capsule at the joint without producing NaN', () => {
    const root = new THREE.Group()
    const hips = bone('Hips', 0, 1, 0, 1)
    const twin = bone('Spine', 0, 0, 0, 1)
    const chest = bone('Chest', 0, 0.9, 0, 1)
    root.add(hips)
    hips.add(twin)
    twin.add(chest)

    const handle = buildMannequin(root)!
    const mesh = byBone(handle, 'Spine')
    expect(mesh.position.lengthSq()).toBe(0)
    expect(Number.isNaN(mesh.quaternion.x + mesh.quaternion.w)).toBe(false)
    expect(radiusOf(mesh)).toBeGreaterThan(0)
  })

  it('marks every mesh and disables frustum culling on it', () => {
    const { root } = mixamoRig()
    const handle = buildMannequin(root)!
    expect(handle.meshes.length).toBeGreaterThan(0)
    for (const mesh of handle.meshes) {
      expect(isMannequinMesh(mesh)).toBe(true)
      expect(mesh.userData[MANNEQUIN_MARKER]).toBe(true)
      expect(mesh.frustumCulled).toBe(false)
    }
  })

  it('does not claim a model-owned mesh as its own', () => {
    const modelMesh = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshBasicMaterial())
    expect(isMannequinMesh(modelMesh)).toBe(false)
    expect(isMannequinMesh(new THREE.Bone())).toBe(false)
  })

  it('shares one material across every mesh', () => {
    const { root } = mixamoRig()
    const handle = buildMannequin(root)!
    const materials = new Set(handle.meshes.map(m => m.material))
    expect(materials.size).toBe(1)
  })

  it('uses the role table radius, scaled by rig height', () => {
    const { root } = mixamoRig()
    const handle = buildMannequin(root)!
    // The fixture spans y=0 to y=1.75 in bone positions.
    const height = 1.75
    const radiusFor = (name: string) => radiusOf(byBone(handle, name))

    expect(radiusFor('mixamorig:LeftForeArm')).toBeCloseTo(
      MANNEQUIN_PROPORTIONS.radii.forearm * height,
      5,
    )
    expect(radiusFor('mixamorig:LeftUpLeg')).toBeCloseTo(
      MANNEQUIN_PROPORTIONS.radii.upperLeg * height,
      5,
    )
    expect(radiusFor('mixamorig:LeftUpLeg')).toBeGreaterThan(radiusFor('mixamorig:LeftHand'))
  })

  it('doubles every radius when the rig is twice the size', () => {
    const small = buildMannequin(mixamoRig(1).root)!
    const large = buildMannequin(mixamoRig(2).root)!
    expect(radiusOf(byBone(large, 'mixamorig:LeftForeArm'))).toBeCloseTo(
      radiusOf(byBone(small, 'mixamorig:LeftForeArm')) * 2,
      5,
    )
    expect(spheres(large.meshes)[0].scale.y).toBeCloseTo(spheres(small.meshes)[0].scale.y * 2, 5)
  })

  /**
   * Bone offsets — and therefore capsule LENGTHS — are local to the parent
   * bone, while the height a radius is a fraction of is measured in world
   * space. A unit conversion carried on an ancestor node is the case where
   * those two spaces diverge, and it is common: Blender-exported FBX puts 0.01
   * on the root, Mixamo puts it on `Hips`. Same rig, same local offsets, so
   * every capsule must come out identical to the unscaled build.
   */
  it('keeps proportions when the root node carries a unit conversion scale', () => {
    const plain = buildMannequin(mixamoRig().root)!
    const { root } = mixamoRig()
    root.scale.setScalar(0.01)
    root.updateMatrixWorld(true)
    const converted = buildMannequin(root)!

    for (const mesh of capsules(converted.meshes)) {
      const twin = plain.meshes.find(m => m.name === mesh.name)!
      expect(radiusOf(mesh)).toBeCloseTo(radiusOf(twin), 9)
    }
    expect(spheres(converted.meshes)[0].scale.y).toBeCloseTo(spheres(plain.meshes)[0].scale.y, 9)
  })

  it('keeps proportions when the unit conversion sits on the root BONE', () => {
    const plain = buildMannequin(mixamoRig().root)!
    const { root } = mixamoRig()
    root.getObjectByName('mixamorig:Hips')!.scale.setScalar(0.01)
    root.updateMatrixWorld(true)
    const converted = buildMannequin(root)!

    for (const mesh of capsules(converted.meshes)) {
      const twin = plain.meshes.find(m => m.name === mesh.name)!
      expect(radiusOf(mesh)).toBeCloseTo(radiusOf(twin), 9)
    }
  })

  it('returns null for a single bone', () => {
    const root = new THREE.Group()
    root.add(bone('mixamorig:Hips', 0, 1, 0, 1))
    expect(buildMannequin(root)).toBeNull()
  })

  it('returns null for a flat rig where no bone parents another', () => {
    const root = new THREE.Group()
    root.add(bone('mixamorig:Hips', 0, 1, 0, 1))
    root.add(bone('mixamorig:Head', 0, 1.6, 0, 1))
    root.add(bone('mixamorig:LeftFoot', 0, 0, 0, 1))
    expect(buildMannequin(root)).toBeNull()
  })

  it('returns null for an object with no bones at all', () => {
    const root = new THREE.Group()
    root.add(new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshBasicMaterial()))
    expect(buildMannequin(root)).toBeNull()
  })

  it('still builds the body when the rig has no head-role bone', () => {
    const root = new THREE.Group()
    const hips = bone('Hips', 0, 1, 0, 1)
    const upLeg = bone('LeftUpLeg', 0.1, -0.1, 0, 1)
    const leg = bone('LeftLeg', 0, -0.45, 0, 1)
    root.add(hips)
    hips.add(upLeg)
    upLeg.add(leg)

    const handle = buildMannequin(root)!
    expect(capsules(handle.meshes)).toHaveLength(2)
    expect(spheres(handle.meshes)).toHaveLength(0)
  })

  it('builds a rig lying flat, where height is zero, from the bone box diagonal', () => {
    const root = new THREE.Group()
    const hips = bone('Hips', 0, 0, 0, 1)
    const spine = bone('Spine', 0, 0, 1, 1)
    root.add(hips)
    hips.add(spine)

    const handle = buildMannequin(root)!
    expect(Number.isFinite(radiusOf(handle.meshes[0]))).toBe(true)
    expect(radiusOf(handle.meshes[0])).toBeGreaterThan(0)
  })
})

describe('MannequinHandle.dispose', () => {
  it('frees every geometry and the shared material exactly once', () => {
    const { root } = mixamoRig()
    const handle = buildMannequin(root)!
    const geometrySpies = handle.meshes.map(m => vi.spyOn(m.geometry, 'dispose'))
    const materialSpy = vi.spyOn(handle.meshes[0].material as THREE.Material, 'dispose')

    handle.dispose()

    for (const spy of geometrySpies) expect(spy).toHaveBeenCalledTimes(1)
    expect(materialSpy).toHaveBeenCalledTimes(1)
  })

  it('is idempotent, so a second teardown cannot double-free the shared material', () => {
    const { root } = mixamoRig()
    const handle = buildMannequin(root)!
    const materialSpy = vi.spyOn(handle.meshes[0].material as THREE.Material, 'dispose')

    handle.dispose()
    handle.dispose()

    expect(materialSpy).toHaveBeenCalledTimes(1)
  })

  it('detaches the meshes from the rig, so a later scene teardown cannot re-free them', () => {
    const { root } = mixamoRig()
    const handle = buildMannequin(root)!
    handle.dispose()

    expect(meshesOf(root)).toHaveLength(0)
    for (const mesh of handle.meshes) expect(mesh.parent).toBeNull()
  })
})
