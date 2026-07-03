import React from 'react';
import { Editor, DiffEditor } from '@monaco-editor/react';
import { motion } from 'framer-motion';
import { Plus, Activity, Cpu, Sparkles } from 'lucide-react';
import { defineUnityTheme, THEME_NAME } from './monaco-theme';
import { useLang } from '../../lib/i18n';

// Açık dosyanın uzantısına göre Monaco dili — .md/.json/.yaml vb. artık editörde
// açılabildiği için csharp'a sabitlemek yanlış vurgu yapıyordu.
const MONACO_LANG: Record<string, string> = {
  '.cs': 'csharp', '.md': 'markdown', '.json': 'json', '.asmdef': 'json',
  '.xml': 'xml', '.uxml': 'xml', '.yaml': 'yaml', '.yml': 'yaml',
  '.txt': 'plaintext', '.shader': 'cpp', '.hlsl': 'cpp', '.cginc': 'cpp',
  '.compute': 'cpp', '.uss': 'css',
};

function monacoLangFor(filePath: string | null): string {
  if (!filePath) return 'csharp';
  const dot = filePath.lastIndexOf('.');
  if (dot < 0) return 'plaintext';
  return MONACO_LANG[filePath.slice(dot).toLowerCase()] ?? 'plaintext';
}

interface EditorPanelProps {
  code: string;
  setCode: (code: string) => void;
  openedFilePath: string | null;
  isEditorFocused: boolean;
  setIsEditorFocused: (focused: boolean) => void;
  workspacePath: string | null;
  problems?: any[];
  // Diff Mode Props
  diffFile: { name: string; code: string; originalCode?: string; suggestedPath: string } | null;
}

export const EditorPanel: React.FC<EditorPanelProps> = ({
  code,
  setCode,
  openedFilePath,
  isEditorFocused,
  setIsEditorFocused,
  workspacePath,
  problems = [],
  diffFile
}) => {
  const { t } = useLang();
  const monacoRef = React.useRef<any>(null);
  const editorRef = React.useRef<any>(null);
  const [modelChangedTrigger, setModelChangedTrigger] = React.useState(0);

  // Dosya değişince stale marker'ları temizle
  React.useEffect(() => {
    if (monacoRef.current && editorRef.current) {
      const model = editorRef.current.getModel();
      if (model) monacoRef.current.editor.setModelMarkers(model, "owner", []);
    }
  }, [openedFilePath, modelChangedTrigger]);

  React.useEffect(() => {
    if (!monacoRef.current || !editorRef.current) return;
    const model = editorRef.current.getModel();
    if (!model) return;

    if (!problems?.length || !openedFilePath) {
      monacoRef.current.editor.setModelMarkers(model, "owner", []);
      return;
    }

    // Relative path karşılaştırması — hem basename hem relative path eşleştir
    const markers = problems
      .filter(p => {
        if (!p.file) return true;
        const pNorm = p.file.replace(/\\/g, '/');
        const oNorm = openedFilePath.replace(/\\/g, '/');
        return oNorm.endsWith(pNorm) || oNorm.endsWith('/' + pNorm.split('/').pop());
      })
      .map(p => {
        // Hatanın satır içeriğini alarak sınırları belirle (Out-of-bounds koruması)
        const lineCount = model.getLineCount();
        const safeLine = Math.min(Math.max(1, p.line), lineCount);
        const lineContent = model.getLineContent(safeLine) || '';
        const maxCol = lineContent.length + 1; // Monaco'da kolonlar 1 tabanlıdır

        let startCol = p.column;
        if (startCol > maxCol) {
          startCol = Math.max(1, maxCol - 1);
        }

        let endCol = p.endColumn ?? maxCol;
        if (endCol > maxCol) {
          endCol = maxCol;
        }
        if (endCol <= startCol) {
          endCol = startCol + 1;
        }

        return {
          startLineNumber: safeLine,
          startColumn: startCol,
          endLineNumber: safeLine,
          endColumn: endCol,
          message: p.message,
          severity: p.severity?.toLowerCase() === 'error'
            ? monacoRef.current.MarkerSeverity.Error
            : monacoRef.current.MarkerSeverity.Warning
        };
      });

    monacoRef.current.editor.setModelMarkers(model, "owner", markers);
  }, [problems, openedFilePath, modelChangedTrigger]);

  return (
    <div className="flex-1 flex flex-col relative min-w-0 bg-[#000000] border-r border-slate-800/50">
      {/* Diff Mode Overlay */}
      {diffFile ? (
        <div className="flex-1 flex flex-col z-20 bg-black">
          <div className="h-9 flex items-center px-4 bg-blue-600/10 border-b border-blue-500/20">
            <Sparkles size={14} className="text-blue-400 mr-2" />
            <span className="text-[11px] font-bold text-blue-300 uppercase tracking-wider">Değişiklik İnceleme: {diffFile.name}</span>
          </div>
          <div className="flex-1 relative">
            <DiffEditor
              height="100%"
              language="csharp"
              original={diffFile.originalCode || ""}
              modified={diffFile.code}
              theme={THEME_NAME}
              onMount={(editor, monaco) => defineUnityTheme(monaco)}
              options={{
                readOnly: true,
                renderSideBySide: true,
                minimap: { enabled: true },
                fontSize: 13,
                fontFamily: "'JetBrains Mono', monospace",
                lineHeight: 1.5,
                scrollBeyondLastLine: false,
                padding: { top: 20, bottom: 20 },
                renderOverviewRuler: false,
              }}
            />
          </div>
        </div>
      ) : (
        <>
          {!(code || openedFilePath || isEditorFocused) && (
            <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none z-0">
              <div className="relative">
                <div className="absolute -inset-10 bg-blue-500/5 blur-[100px] rounded-full" />
                <img 
                  src="/images/unity-logo-dark.png" 
                  alt="Unity" 
                  className="w-24 h-24 opacity-5 mb-8 grayscale invert brightness-0"
                  onError={(e) => { (e.target as any).style.display = 'none'; }}
                />
              </div>
              <div className="text-center space-y-2 opacity-30 px-6">
                <h3 className="text-sm font-bold text-slate-400 tracking-[0.2em] uppercase">Unity Architect Engine</h3>
                <p className="text-[11px] text-slate-500 max-w-[240px] leading-relaxed">
                  {t('home.editorHint')}
                </p>
              </div>
              <div className="mt-10 flex gap-6 text-[10px] font-mono text-slate-700 font-semibold uppercase tracking-widest pointer-events-none">
                <span className="flex items-center gap-1.5"><Activity size={14} /> {t('home.bugfix')}</span>
                <span className="flex items-center gap-1.5"><Cpu size={14} /> {t('home.codegen')}</span>
                <span className="flex items-center gap-1.5"><Sparkles size={14} /> {t('home.analyze')}</span>
              </div>
            </div>
          )}

          <div
            className={`flex-1 relative z-10 transition-opacity duration-200 ${(code || openedFilePath || isEditorFocused) ? 'opacity-100' : 'opacity-0 pointer-events-none'}`}
          >

            <Editor
              height="100%"
              defaultLanguage="csharp"
              language={monacoLangFor(openedFilePath)}
              theme={THEME_NAME}
              value={code}
              onChange={(val) => setCode(val || '')}
              onMount={(editor, monaco) => {
                editorRef.current = editor;
                monacoRef.current = monaco;
                defineUnityTheme(monaco);

                // İlk açılışta marker'ları tetikle
                setModelChangedTrigger(prev => prev + 1);

                // Model değiştiğinde (yeni dosya açıldığında vb.) marker'ları tetikle
                editor.onDidChangeModel(() => {
                  setModelChangedTrigger(prev => prev + 1);
                });

                editor.onDidFocusEditorWidget(() => setIsEditorFocused(true));
                editor.onDidBlurEditorWidget(() => setIsEditorFocused(false));
              }}
              options={{
                minimap: { enabled: false },
                fontSize: 14,
                fontFamily: "'JetBrains Mono', 'Fira Code', 'Consolas', monospace",
                scrollBeyondLastLine: false,
                smoothScrolling: true,
                contextmenu: false,
                padding: { top: 24, bottom: 24 },
                lineHeight: 1.6,
                cursorBlinking: "smooth",
                cursorSmoothCaretAnimation: "on",
                formatOnPaste: true,
                "semanticHighlighting.enabled": true
              }}
            />
          </div>
        </>
      )}
    </div>
  );
};
