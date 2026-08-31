import * as THREE from 'three';
// The `.js` suffix is required by three's exports map under this tsconfig.
import { FBXLoader } from 'three/examples/jsm/loaders/FBXLoader.js';
import { GLTFLoader, type GLTF } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { ColladaLoader } from 'three/examples/jsm/loaders/ColladaLoader.js';
import { OBJLoader } from 'three/examples/jsm/loaders/OBJLoader.js';
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js';
import { PLYLoader } from 'three/examples/jsm/loaders/PLYLoader.js';

export interface ParsedModel {
  object: THREE.Object3D;
  clips: THREE.AnimationClip[];
}

/** Parse failures the panel has dedicated wording for. */
export type ModelErrorCode = 'external-resources';

/**
 * A failure the panel can explain in the user's own terms instead of printing
 * the loader's one-liner. Carrying a code rather than a matched message keeps
 * the wording in the i18n table where a copy edit cannot break the branch.
 */
export class ModelParseError extends Error {
  constructor(readonly code: ModelErrorCode, message: string) {
    super(message);
    this.name = 'ModelParseError';
  }
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
 *
 * The reach of that is also its boundary: THREE.Sprite's geometry is a
 * module-level singleton shared by every sprite in the process, so disposing
 * one would break all of them. No parsed model subtree contains a Sprite today
 * — none of these loaders emit one — but point `disposeObject` at an arbitrary
 * scene subtree and that stops being true.
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
 * @param vertexColors keep the mesh's per-vertex colour attribute in play. A
 * material with this off IGNORES a `color` attribute the geometry carries, so a
 * vertex-coloured OBJ or PLY would arrive flat gray with nothing saying its
 * colours had been dropped.
 */
const grayMaterial = (vertexColors = false): THREE.MeshStandardMaterial =>
  new THREE.MeshStandardMaterial({
    color: FALLBACK_MATERIAL_COLOR,
    roughness: 0.75,
    metalness: 0.05,
    vertexColors,
  });

/** What FBX and Collada both mark an unresolved material with. */
const namedDefault = (m: THREE.Material | null | undefined): boolean =>
  m == null || m.name === THREE.Loader.DEFAULT_MATERIAL_NAME;

/**
 * Swap the loader's own placeholder material for a neutral gray one. three's
 * placeholder is a near-white MeshPhongMaterial, which under this scene's
 * lighting reads as "blown out" rather than "no material" — and it is unlit-flat
 * next to the MeshStandard materials everything else uses.
 *
 * `unresolved` is per format because the loaders disagree on how a placeholder
 * is recognisable: FBX and Collada name theirs `__DEFAULT`, glTF hands out one
 * shared cached instance with an empty name, and OBJ's are always placeholders
 * because its materials live in a .mtl file we never fetch.
 */
const applyMaterialFallback = (
  object: THREE.Object3D,
  unresolved: (m: THREE.Material | null | undefined) => boolean = namedDefault,
): void => {
  // Two cached instances, not one: the replacement has to keep whatever the
  // replaced material said about vertex colours, and that answer differs per
  // mesh within a single file.
  let plain: THREE.MeshStandardMaterial | null = null;
  let colored: THREE.MeshStandardMaterial | null = null;
  const gray = (replaced?: THREE.Material | null) =>
    (replaced as THREE.MeshStandardMaterial | null | undefined)?.vertexColors === true
      ? (colored ??= grayMaterial(true))
      : (plain ??= grayMaterial());

  object.traverse(child => {
    if (!isMesh(child)) return;

    if (Array.isArray(child.material)) {
      if (child.material.length === 0) { child.material = gray(); return; }
      child.material = child.material.map(m => {
        if (!unresolved(m)) return m;
        const replacement = gray(m);
        m?.dispose();
        return replacement;
      });
      return;
    }
    if (unresolved(child.material)) {
      const replacement = gray(child.material);
      child.material?.dispose();
      child.material = replacement;
    }
  });
};

const decode = (buffer: ArrayBuffer): string => new TextDecoder().decode(buffer);

const parseFbx = (buffer: ArrayBuffer): ParsedModel => {
  const group = new FBXLoader(createManager()).parse(buffer, '');
  applyMaterialFallback(group);
  return { object: group, clips: group.animations ?? [] };
};

interface GltfResourceRef {
  uri?: unknown;
}

/**
 * A `.gltf` is only the JSON half of the format: its geometry lives in a
 * sibling `.bin` and its textures in sibling image files, addressed by relative
 * URI. Nothing here can fetch those: the file arrived as bytes over IPC, so the
 * loader has no base URL to resolve a sibling path against, and the workspace
 * is not served over any origin the renderer could ask.
 *
 * Reading the reference out of the JSON is what lets the panel say "export as
 * .glb". The alternative — let GLTFLoader try, then classify the rejection —
 * would mean matching on a failure message three does not author and does not
 * promise to keep.
 */
const assertSelfContained = (json: unknown): void => {
  const doc = json as { buffers?: unknown; images?: unknown };
  // A hand-edited or truncated document can put anything under these keys, and
  // `{"buffers": 5}` is not iterable: spreading it threw a TypeError from OUR
  // code, which the panel then printed as the model's failure. Reading a
  // non-array as "no references" hands the file to GLTFLoader, so a malformed
  // glTF fails as a malformed glTF.
  const refs = (value: unknown): GltfResourceRef[] =>
    (Array.isArray(value) ? value : []) as GltfResourceRef[];
  const external = [...refs(doc.buffers), ...refs(doc.images)]
    .map(ref => ref?.uri)
    // A data: URI is embedded content, not a reference to a sibling file.
    .filter((uri): uri is string => typeof uri === 'string' && !uri.startsWith('data:'));
  if (external.length === 0) return;
  throw new ModelParseError(
    'external-resources',
    `glTF references external files: ${external.slice(0, 3).join(', ')}`,
  );
};

/**
 * Recognise the material glTF hands a primitive that declares none. three keeps
 * one cached instance for that — white at metalness 1, which with no
 * environment map in this scene renders near-black, i.e. worse than no material
 * at all — but a primitive without normals gets a flat-shaded CLONE of it, so
 * identity alone misses the very files most likely to be material-less.
 *
 * Hence the field comparison against the real instance rather than a hard-coded
 * signature, and hence the outer guard: unless this document actually made a
 * default material, nothing is a placeholder and no authored material is at
 * risk of being mistaken for one.
 */
const gltfPlaceholder = (gltf: GLTF) => {
  const cache = (gltf.parser as unknown as { cache?: Record<string, THREE.Material> }).cache;
  const def = cache?.DefaultMaterial as THREE.MeshStandardMaterial | undefined;
  return (m: THREE.Material | null | undefined): boolean => {
    if (m == null) return true;
    if (def === undefined) return false;
    if (m === def) return true;
    const candidate = m as THREE.MeshStandardMaterial;
    return (
      m.type === def.type &&
      m.name === def.name &&
      candidate.map == null &&
      candidate.metalness === def.metalness &&
      candidate.roughness === def.roughness &&
      candidate.color?.equals(def.color) === true
    );
  };
};

const parseGltf = async (data: ArrayBuffer | string): Promise<ParsedModel> => {
  const loader = new GLTFLoader(createManager());
  // parse() is callback-based and stays that way even for fully embedded input,
  // because its dependency graph resolves through promises internally.
  const gltf = await new Promise<GLTF>((resolve, reject) => {
    loader.parse(data as ArrayBuffer, '', resolve, reject);
  });
  applyMaterialFallback(gltf.scene, gltfPlaceholder(gltf));
  return { object: gltf.scene, clips: gltf.animations ?? [] };
};

const parseGltfJson = (buffer: ArrayBuffer): Promise<ParsedModel> => {
  const text = decode(buffer);
  assertSelfContained(JSON.parse(text));
  return parseGltf(text);
};

const parseCollada = (buffer: ArrayBuffer): ParsedModel => {
  const { scene } = new ColladaLoader(createManager()).parse(decode(buffer), '');
  applyMaterialFallback(scene);
  return { object: scene, clips: scene.animations ?? [] };
};

const parseObj = (buffer: ArrayBuffer): ParsedModel => {
  const group = new OBJLoader(createManager()).parse(decode(buffer));
  // Every material OBJLoader.parse produces is a placeholder: real ones come
  // from a .mtl file, which only the URL-based load path fetches.
  applyMaterialFallback(group, () => true);
  return { object: group, clips: [] };
};

/** STL and PLY carry geometry alone — no material, no scene graph, no clips. */
const meshFromGeometry = (geometry: THREE.BufferGeometry): ParsedModel => {
  // PLY files routinely ship positions only; without normals every lit material
  // renders the mesh black, which looks identical to a failed load.
  if (!geometry.getAttribute('normal')) geometry.computeVertexNormals();
  // Neither format carries a material, so the geometry's own `color` attribute
  // is the only place a vertex-coloured scan's colours survive to.
  return {
    object: new THREE.Mesh(geometry, grayMaterial(geometry.getAttribute('color') != null)),
    clips: [],
  };
};

/**
 * Parse a model file that was already read into memory. Kept free of any
 * renderer/WebGL reference so it runs — and is testable — headless.
 *
 * Async for one format's sake: GLTFLoader.parse reports through callbacks, and
 * a sync-for-six/async-for-one split would put the seam in every caller.
 *
 * @param ext lowercase extension including the dot, e.g. `.fbx`
 */
export const parseModel = async (ext: string, buffer: ArrayBuffer): Promise<ParsedModel> => {
  switch (ext.toLowerCase()) {
    case '.fbx':
      return parseFbx(buffer);
    case '.glb':
      return parseGltf(buffer);
    case '.gltf':
      return parseGltfJson(buffer);
    case '.dae':
      return parseCollada(buffer);
    case '.obj':
      return parseObj(buffer);
    case '.stl':
      return meshFromGeometry(new STLLoader(createManager()).parse(buffer));
    case '.ply':
      return meshFromGeometry(new PLYLoader(createManager()).parse(buffer));
    default:
      throw new Error(`Unsupported model format: ${ext}`);
  }
};

/**
 * The clip to play, or null when the file gives us nothing to run.
 *
 * A zero-duration clip is not merely pointless, it is poison. MEASURED, three
 * 0.185.1: AnimationAction wraps its loop with `Math.floor(time / duration)`,
 * which at duration 0 is Infinity, not NaN; the NaN arrives one line later as
 * `Infinity - Infinity` and the action's time stays NaN from the first update
 * onward. The interpolant clamps, so the model FREEZES on a pose rather than
 * disappearing — no throw, no error state, and a rAF loop burning frames on a
 * clip with nothing to play. Files with a single keyframe produce exactly this.
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
