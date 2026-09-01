import * as THREE from 'three';

import { boneBounds } from './loaders';

/**
 * A procedural white mannequin built ON the file's own bones, so any clip from
 * any source drives it with no retargeting. Pure three.js object math: no DOM,
 * no renderer, constructible under jsdom.
 */

export type BoneRole =
  | 'head'
  | 'neck'
  | 'spine'
  | 'shoulder'
  | 'upperArm'
  | 'forearm'
  | 'hand'
  | 'finger'
  | 'upperLeg'
  | 'lowerLeg'
  | 'foot'
  | 'toe'
  | 'other';

/**
 * First match wins, so the order is the specification. Every entry below sits
 * where it does because a later entry's keyword is a substring of one of its
 * names — "forearm" contains "arm", "upleg" and "lowerleg" contain "leg",
 * "LeftHandThumb1" contains "hand", "SpineMiddle" contains "middle", and
 * Unreal's toe bone "ball_l" collides with an "eyeball" bone. Reordering this
 * table silently reclassifies whole limbs.
 */
const ROLE_KEYWORDS: readonly (readonly [BoneRole, readonly string[]])[] = [
  // 'hip' not 'hips': generic rigs name the bone `Hip` as often as `Hips`.
  ['spine', ['spine', 'chest', 'hip', 'pelvis', 'torso']],
  ['shoulder', ['shoulder', 'clavicle']],
  ['forearm', ['forearm', 'lowerarm', 'lower_arm']],
  ['upperArm', ['upperarm', 'upper_arm', 'arm']],
  ['finger', ['thumb', 'index', 'middle', 'ring', 'pinky', 'finger']],
  ['hand', ['hand']],
  ['neck', ['neck']],
  ['head', ['head']],
  ['other', ['eye']],
  ['toe', ['toe', 'ball']],
  ['foot', ['foot', 'ankle']],
  ['upperLeg', ['upleg', 'upperleg', 'upper_leg', 'thigh']],
  ['lowerLeg', ['lowerleg', 'lower_leg', 'shin', 'calf', 'leg']],
];

/**
 * Case-insensitive substring classification of a bone name. Covers Mixamo
 * (`mixamorig:LeftForeArm`), Unreal (`upperarm_l`), Blender rigify
 * (`forearm.L`) and generic (`LeftLeg`) naming without a per-rig mapping.
 */
export const classifyBone = (name: string): BoneRole => {
  const lower = name.toLowerCase();
  for (const [role, keywords] of ROLE_KEYWORDS) {
    if (keywords.some(keyword => lower.includes(keyword))) return role;
  }
  return 'other';
};

/**
 * The single calibration point for the figure's shape — tuned by eye, not
 * derived. Radii are FRACTIONS OF SKELETON HEIGHT so a rig authored in
 * centimetres and one authored in metres both come out human-shaped.
 *
 * `head` is the radius of the neck-to-head capsule only; the head's actual
 * volume is `headEllipsoid`, so that capsule is deliberately neck-width.
 */
export const MANNEQUIN_PROPORTIONS = {
  radii: {
    head: 0.025,
    neck: 0.025,
    // Tuned by eye against a Mixamo goalkeeper clip (1 Sep 2026): thicker
    // forearms/shins so extremities don't read as sticks, slimmer spine so
    // short torso bones don't degrade into a chain of balls.
    spine: 0.048,
    shoulder: 0.03,
    upperArm: 0.038,
    forearm: 0.034,
    hand: 0.016,
    finger: 0.006,
    upperLeg: 0.05,
    lowerLeg: 0.042,
    foot: 0.018,
    toe: 0.01,
    other: 0.02,
  } satisfies Record<BoneRole, number>,
  headEllipsoid: { x: 0.075, y: 0.095, z: 0.08 },
} as const;

const MATERIAL_COLOR = 0xd8d8d8;

/**
 * Marks a mesh this module owns.
 *
 * NOT what teardown runs on, and the comment here used to claim it was: the
 * panel frees these volumes through `MannequinHandle.dispose()`, and the handle
 * is deliberately their single owner — `clearContent` disposes it BEFORE the
 * scene traversal precisely so no second code path ever has to recognise them.
 * Giving teardown a marker test as well would put two owners on the same
 * geometries, which is the double-dispose the current ordering exists to avoid.
 *
 * So what the mark is for is IDENTIFICATION, by anything holding a scene graph
 * and asking which of these meshes came out of the file and which this module
 * drew: today that is the mount and mannequin suites. It survives as an export
 * on those terms rather than as a teardown hook.
 */
export const MANNEQUIN_MARKER = 'gamachineMannequin';

/** True for a mesh `buildMannequin` created. See `MANNEQUIN_MARKER`. */
export const isMannequinMesh = (object: THREE.Object3D): boolean =>
  object.userData?.[MANNEQUIN_MARKER] === true;

export interface MannequinHandle {
  /** Every mesh added to the rig, in creation order. */
  meshes: THREE.Mesh[];
  /** Detach the meshes and free their geometries and the shared material. Idempotent. */
  dispose(): void;
}

const isBone = (object: THREE.Object3D | null): object is THREE.Bone =>
  (object as THREE.Bone | null)?.isBone === true;

const UP = new THREE.Vector3(0, 1, 0);

/**
 * Skeleton height in WORLD units — the scale every radius is a fraction of.
 * Height is the honest measure of a humanoid rig; a rig lying flat (Y extent
 * ~0, e.g. an unposed T-pose exported Z-up) has none, so the bone box's
 * diagonal stands in, and a rig whose bones all share one point falls back to
 * the whole object's diagonal before 1.
 */
const rigHeight = (root: THREE.Object3D, bones: THREE.Box3): number => {
  const size = bones.getSize(new THREE.Vector3());
  if (size.y > 1e-6) return size.y;
  const diagonal = size.length();
  if (diagonal > 1e-6) return diagonal;
  const overall = new THREE.Box3().setFromObject(root).getSize(new THREE.Vector3()).length();
  return overall > 1e-6 ? overall : 1;
};

/**
 * Divisor that carries a world-space length into `object`'s local space.
 *
 * Radii come from a WORLD measurement (`boneBounds` reads `matrixWorld`) but
 * every mesh here is a child of a bone, so its numbers are read in that bone's
 * LOCAL space — the same space `bone.position`, and therefore the capsule
 * length, already lives in. Mixing the two silently distorts the figure by the
 * accumulated ancestor scale: a Blender-exported FBX with a 0.01 unit
 * conversion on its root (or on `mixamorig:Hips`, which is just as common)
 * renders 100x too thin.
 *
 * Non-uniform scale has no single right answer for a radius; the geometric
 * mean is the uniform scale with the same volume factor.
 */
const localFromWorld = (object: THREE.Object3D, out: THREE.Vector3): number => {
  object.getWorldScale(out);
  const volume = Math.abs(out.x * out.y * out.z);
  return volume > 1e-12 ? Math.cbrt(volume) : 1;
};

/**
 * three's CapsuleGeometry `length` is the CYLINDER MID-SECTION only: total
 * extent is `length + 2 * radius`. Passing the bone length verbatim overshoots
 * the joint at both ends by a radius — measured 66% over on a spine segment —
 * which pushes the foot through the floor plane. A bone shorter than its own
 * diameter collapses to a ball rather than a negative length.
 */
const cylinderLength = (boneLength: number, radius: number): number =>
  Math.max(boneLength - 2 * radius, 1e-6);

const mark = (mesh: THREE.Mesh, boneName: string): THREE.Mesh => {
  // The prefix is load-bearing: animation tracks bind to nodes BY NAME
  // (three's PropertyBinding), so a volume named exactly like its bone would
  // capture the bone's tracks and the rig would silently stop animating.
  mesh.name = `mannequin:${boneName}`;
  mesh.userData[MANNEQUIN_MARKER] = true;
  // Bone-driven volumes move far from where their bounding sphere was computed;
  // culling against the bind pose makes limbs vanish mid-clip.
  mesh.frustumCulled = false;
  return mesh;
};

/**
 * Direction the head bone points in, in its OWN local space, for placing the
 * skull. A tip bone (Mixamo's `HeadTop_End`) states it directly; without one
 * the incoming neck-to-head direction is rotated into head space instead.
 */
const headDirection = (head: THREE.Bone): THREE.Vector3 => {
  const tip = head.children.find(isBone);
  const local = tip?.position.clone() ?? head.position.clone().applyQuaternion(
    head.quaternion.clone().invert(),
  );
  return local.lengthSq() > 1e-12 ? local.normalize() : UP.clone();
};

/**
 * Build capsule volumes on `root`'s bones and return a handle owning them, or
 * null when the rig has no bone-parented bone — the same gate
 * `hasDrawableSkeleton` applies, because a segment is exactly what a capsule
 * needs to span.
 *
 * Each capsule is attached AS A CHILD OF THE PARENT BONE, so the animation
 * mixer moving the skeleton moves the mannequin for free.
 */
export const buildMannequin = (root: THREE.Object3D): MannequinHandle | null => {
  const bounds = boneBounds(root);
  if (!bounds) return null;

  const bones: THREE.Bone[] = [];
  root.traverse(child => {
    if (isBone(child)) bones.push(child);
  });
  const segments = bones.filter(bone => isBone(bone.parent));
  if (segments.length === 0) return null;
  // The first head-role bone only: Mixamo names both `Head` and `HeadTop_End`,
  // and two skulls is worse than none.
  const head = bones.find(bone => classifyBone(bone.name) === 'head');

  const height = rigHeight(root, bounds);
  const material = new THREE.MeshStandardMaterial({
    color: MATERIAL_COLOR,
    roughness: 0.85,
    metalness: 0.0,
  });
  const meshes: THREE.Mesh[] = [];
  const worldScale = new THREE.Vector3();

  for (const bone of segments) {
    const offset = bone.position;
    const length = offset.length();
    const scale = height / localFromWorld(bone.parent!, worldScale);
    const radius = MANNEQUIN_PROPORTIONS.radii[classifyBone(bone.name)] * scale;
    // Low segment counts on purpose: a humanoid rig is ~65 bones, and this is a
    // silhouette, not a sculpt.
    const mesh = new THREE.Mesh(
      new THREE.CapsuleGeometry(radius, cylinderLength(length, radius), 4, 8),
      material,
    );
    mesh.position.copy(offset).multiplyScalar(0.5);
    if (length > 1e-9) {
      mesh.quaternion.setFromUnitVectors(UP, offset.clone().divideScalar(length));
    }
    bone.parent!.add(mark(mesh, bone.name));
    meshes.push(mesh);
  }

  if (head) {
    const { x, y, z } = MANNEQUIN_PROPORTIONS.headEllipsoid;
    const skull = new THREE.Mesh(new THREE.SphereGeometry(1, 12, 8), material);
    const direction = headDirection(head);
    // The skull is a child of the head bone, so it needs that bone's local space.
    const scale = height / localFromWorld(head, worldScale);
    skull.scale.set(x * scale, y * scale, z * scale);
    skull.quaternion.setFromUnitVectors(UP, direction);
    skull.position.copy(direction).multiplyScalar((y * scale) / 2);
    head.add(mark(skull, head.name));
    meshes.push(skull);
  }

  let disposed = false;
  return {
    meshes,
    dispose: () => {
      if (disposed) return;
      disposed = true;
      for (const mesh of meshes) {
        mesh.removeFromParent();
        mesh.geometry.dispose();
      }
      material.dispose();
    },
  };
};
