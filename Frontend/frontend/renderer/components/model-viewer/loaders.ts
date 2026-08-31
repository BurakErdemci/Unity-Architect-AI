import * as THREE from 'three';
import { FBXLoader } from 'three/examples/jsm/loaders/FBXLoader.js';

export interface ParsedModel {
  object: THREE.Object3D;
  clips: THREE.AnimationClip[];
}

/** Neutral gray stand-in for materials the loader could not resolve. */
export const FALLBACK_MATERIAL_COLOR = 0x9aa0a6;

const isMesh = (o: THREE.Object3D): o is THREE.Mesh =>
  (o as THREE.Mesh).isMesh === true;

/**
 * Anything holding GPU buffers, not just meshes. FBXLoader emits a `Line` per
 * NURBS curve and `Points` are reachable too; both carry geometry and material
 * that an `isMesh` guard walks straight past. Structural, not by type list — a
 * renderable class we have not met yet still gets freed.
 */
type Renderable = THREE.Object3D & {
  geometry?: THREE.BufferGeometry;
  material?: THREE.Material | THREE.Material[];
};

const isRenderable = (o: THREE.Object3D): o is Renderable =>
  (o as Renderable).geometry !== undefined || (o as Renderable).material !== undefined;

const asArray = (m: THREE.Material | THREE.Material[] | null | undefined): THREE.Material[] =>
  m == null ? [] : Array.isArray(m) ? m : [m];

/**
 * A workspace FBX normally points at texture files by relative path. Those paths
 * are authored for the DCC tool, not for us: they routinely sit outside the
 * workspace, or were never exported at all. The loader keeps going either way,
 * but every miss reaches the manager as an error — silencing it here is what
 * keeps a texture-less model a viewable model instead of a console flood.
 */
const createManager = (): THREE.LoadingManager => {
  const manager = new THREE.LoadingManager();
  manager.onError = () => {};
  return manager;
};

/**
 * Swap the loader's own placeholder material for a neutral gray one. three's
 * placeholder is a near-white MeshPhongMaterial, which under this scene's
 * lighting reads as "blown out" rather than "no material" — and it is unlit-flat
 * next to the MeshStandard materials everything else uses.
 */
const applyMaterialFallback = (object: THREE.Object3D): void => {
  let fallback: THREE.MeshStandardMaterial | null = null;
  const gray = () =>
    (fallback ??= new THREE.MeshStandardMaterial({
      color: FALLBACK_MATERIAL_COLOR,
      roughness: 0.75,
      metalness: 0.05,
    }));

  object.traverse(child => {
    if (!isMesh(child)) return;
    const unresolved = (m: THREE.Material | null | undefined) =>
      m == null || m.name === THREE.Loader.DEFAULT_MATERIAL_NAME;

    if (Array.isArray(child.material)) {
      if (child.material.length === 0) { child.material = gray(); return; }
      child.material = child.material.map(m => {
        if (!unresolved(m)) return m;
        m?.dispose();
        return gray();
      });
      return;
    }
    if (unresolved(child.material)) {
      child.material?.dispose();
      child.material = gray();
    }
  });
};

const parseFbx = (buffer: ArrayBuffer): ParsedModel => {
  const group = new FBXLoader(createManager()).parse(buffer, '');
  applyMaterialFallback(group);
  return { object: group, clips: group.animations ?? [] };
};

/**
 * Parse a model file that was already read into memory. Kept free of any
 * renderer/WebGL reference so it runs — and is testable — headless.
 *
 * @param ext lowercase extension including the dot, e.g. `.fbx`
 */
export const parseModel = (ext: string, buffer: ArrayBuffer): ParsedModel => {
  switch (ext.toLowerCase()) {
    case '.fbx':
      return parseFbx(buffer);
    default:
      throw new Error(`Unsupported model format: ${ext}`);
  }
};

/**
 * The clip to play, or null when the file gives us nothing to run.
 *
 * A zero-duration clip is not merely pointless, it is poison: AnimationAction
 * computes `Math.floor(time / duration)` for its loop wrap, which is NaN at
 * duration 0, and the NaN reaches the interpolants and then the bone matrices.
 * The model silently disappears while the loop keeps spinning and no error
 * state ever fires. Files with a single keyframe produce exactly this.
 *
 * Multi-clip files play the first clip; choosing between them is UI this viewer
 * deliberately does not have.
 */
export const playableClip = (clips: THREE.AnimationClip[]): THREE.AnimationClip | null => {
  const first = clips[0];
  return first && first.duration > 0 ? first : null;
};

/**
 * Release every GPU-backed resource under `object`. The usage pattern this
 * exists for is clicking through a folder of 200 models: without it each one
 * leaves its buffers and textures live for the rest of the session.
 */
export const disposeObject = (object: THREE.Object3D): void => {
  const materials = new Set<THREE.Material>();
  const textures = new Set<THREE.Texture>();

  object.traverse(child => {
    // A SkinnedMesh owns a Skeleton, and three allocates a bone DataTexture on
    // it at first render. Nothing else frees that texture, so browsing rigged
    // FBX files — the whole point of this panel — leaks one per file.
    const skinned = child as THREE.SkinnedMesh;
    if (skinned.isSkinnedMesh) skinned.skeleton?.dispose();

    if (!isRenderable(child)) return;
    child.geometry?.dispose();
    for (const material of asArray(child.material)) materials.add(material);
  });

  for (const material of materials) {
    // Textures are shared between materials far more often than geometry is,
    // so they are collected first and disposed once.
    for (const value of Object.values(material) as unknown[]) {
      if (value && (value as THREE.Texture).isTexture) textures.add(value as THREE.Texture);
    }
    material.dispose();
  }
  for (const texture of textures) texture.dispose();
};
