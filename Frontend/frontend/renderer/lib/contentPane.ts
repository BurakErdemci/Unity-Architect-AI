export type ContentPane = 'preview' | 'editor' | 'hero';

/**
 * Which of the three mutually exclusive things the single content area shows.
 *
 * A pending diff outranks an open preview. `diffFile` is set while the user is
 * being ASKED to approve a file change; with a preview open that diff rendered
 * nowhere, so the approval card asked about content the user could not see.
 * The guard lives on the render side rather than at every `setDiffFile` call
 * site because it also reverses itself: when the approval clears, the preview
 * the user had open is still there.
 */
export const contentPane = (
  previewFile: unknown,
  diffFile: unknown,
  openedFilePath: string | null,
): ContentPane => {
  if (diffFile) return 'editor';
  if (previewFile) return 'preview';
  return openedFilePath ? 'editor' : 'hero';
};
