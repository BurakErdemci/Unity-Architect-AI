export type FileRoute = 'text' | 'model' | 'blocked-model';

export const MODEL_EXTENSIONS: readonly string[] = ['.fbx', '.glb', '.gltf', '.dae', '.obj', '.stl', '.ply'];

// Formats the viewer recognises as 3D but cannot render: they are authoring
// formats with no loader in three.js.
export const BLOCKED_MODEL_EXTENSIONS: readonly string[] = ['.blend', '.3ds'];

/** Lowercase extension including the dot, or '' when there is none. */
export const extensionOf = (path: string): string => {
  // Only the basename can carry the extension — a directory may contain a dot
  // ("Assets/v1.2/Readme"), and on Windows the separator is '\'.
  const name = path.split(/[\\/]/).pop() ?? '';
  const dot = name.lastIndexOf('.');
  // dot === 0 is a dotfile (".gitignore"), not an extension.
  return dot <= 0 ? '' : name.slice(dot).toLowerCase();
};

export const routeForFile = (path: string): FileRoute => {
  const ext = extensionOf(path);
  if (!ext) return 'text';
  if (BLOCKED_MODEL_EXTENSIONS.includes(ext)) return 'blocked-model';
  if (MODEL_EXTENSIONS.includes(ext)) return 'model';
  return 'text';
};
