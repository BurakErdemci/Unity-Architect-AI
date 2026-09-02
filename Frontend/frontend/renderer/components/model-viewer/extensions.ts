export type FileRoute = 'text' | 'model' | 'blocked-model' | 'image' | 'blocked-image';

export const MODEL_EXTENSIONS: readonly string[] = ['.fbx', '.glb', '.gltf', '.dae', '.obj', '.stl', '.ply'];

// Formats the viewer recognises as 3D but cannot render: they are authoring
// formats with no loader in three.js.
export const BLOCKED_MODEL_EXTENSIONS: readonly string[] = ['.blend', '.3ds'];

// Mirror of the main process's IMAGE_FILE_EXTENSIONS; a test asserts the two
// stay set-equal, because two copies of one decision is this repo's named
// defect class and the main module cannot be imported from the renderer bundle.
export const IMAGE_EXTENSIONS: readonly string[] = ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg'];

// Image formats Unity projects are full of but Chromium has no decoder for.
// They route to the preview anyway so the click gets an explanation instead of
// opening binary bytes in the text editor.
export const BLOCKED_IMAGE_EXTENSIONS: readonly string[] = ['.tga', '.psd', '.exr', '.tif', '.tiff'];

/** Lowercase extension including the dot, or '' when there is none. */
export const extensionOf = (path: string): string => {
  // Only the basename can carry the extension — a directory may contain a dot
  // ("Assets/v1.2/Readme"), and on Windows the separator is '\'.
  const name = path.split(/[\/]/).pop() ?? '';
  const dot = name.lastIndexOf('.');
  // dot === 0 is a dotfile (".gitignore"), not an extension.
  return dot <= 0 ? '' : name.slice(dot).toLowerCase();
};

export const routeForFile = (path: string): FileRoute => {
  const ext = extensionOf(path);
  if (!ext) return 'text';
  if (BLOCKED_MODEL_EXTENSIONS.includes(ext)) return 'blocked-model';
  if (MODEL_EXTENSIONS.includes(ext)) return 'model';
  if (BLOCKED_IMAGE_EXTENSIONS.includes(ext)) return 'blocked-image';
  if (IMAGE_EXTENSIONS.includes(ext)) return 'image';
  return 'text';
};
