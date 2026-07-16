import type * as Monaco from 'monaco-editor';

export const THEME_NAME = 'unityArchitectDark';

// JetBrains Mono webfont'u (globals.css @import) Monaco'nun font ölçümünden SONRA
// yüklenebiliyor → ölçüm bayat kalınca tıklanan piksel yanlış kolona düşüyor
// (satır sonuna tıkla, imleç ortaya gelir). Font(lar) hazır olunca yeniden ölçtür.
let _fontRemeasureHooked = false;
const hookFontRemeasure = (monaco: typeof Monaco) => {
  if (_fontRemeasureHooked || typeof document === 'undefined') return;
  _fontRemeasureHooked = true;
  const remeasure = () => monaco.editor.remeasureFonts();
  const fonts: any = (document as any).fonts;
  fonts?.ready?.then(remeasure).catch(() => {});
  // Geç yüklenen font batch'leri için (ready bir kez çözülür, bu her batch'te tetiklenir)
  fonts?.addEventListener?.('loadingdone', remeasure);
};

export const defineUnityTheme = (monaco: typeof Monaco) => {
  hookFontRemeasure(monaco);
  monaco.editor.defineTheme(THEME_NAME, {
    base: 'vs-dark',
    inherit: true,
    rules: [
      { token: 'keyword',           foreground: '569CD6' },
      { token: 'keyword.control',   foreground: 'C586C0' },
      { token: 'type',              foreground: '4EC9B0' },
      { token: 'type.identifier',   foreground: '4EC9B0' },
      { token: 'identifier',        foreground: '9CDCFE' },
      { token: 'number',            foreground: 'B5CEA8' },
      { token: 'string',            foreground: 'CE9178' },
      { token: 'string.escape',     foreground: 'D7BA7D' },
      { token: 'comment',           foreground: '6A9955', fontStyle: 'italic' },
      { token: 'delimiter',         foreground: 'D4D4D4' },
      { token: 'attribute.name',    foreground: '9CDCFE' },
      { token: 'attribute.value',   foreground: 'CE9178' },
      { token: 'annotation',        foreground: 'DCDCAA' },
    ],
    colors: {
      'editor.background':                  '#000000',
      'editor.foreground':                  '#D4D4D4',
      'editorLineNumber.foreground':        '#334155',
      'editorLineNumber.activeForeground':  '#858585',
      'editor.selectionBackground':         '#264F78',
      'editor.lineHighlightBackground':     '#0A0A0A',
      'diffEditor.insertedTextBackground':  '#00ff0015',
      'diffEditor.removedTextBackground':   '#ff000015',
      'diffEditor.insertedLineBackground':  '#00ff0010',
      'diffEditor.removedLineBackground':   '#ff000010',
    },
  });
  monaco.editor.setTheme(THEME_NAME);
};
