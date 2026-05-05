import { Editor, DiffEditor } from '@monaco-editor/react';
import { motion } from 'framer-motion';
import { Plus, Activity, Cpu, Sparkles } from 'lucide-react';
import { defineUnityTheme, THEME_NAME } from './monaco-theme';

interface EditorPanelProps {
  code: string;
  setCode: (code: string) => void;
  openedFilePath: string | null;
  isEditorFocused: boolean;
  setIsEditorFocused: (focused: boolean) => void;
  includeEditorCode: boolean;
  setIncludeEditorCode: (include: boolean) => void;
  workspacePath: string | null;
  // Diff Mode Props
  diffFile: { name: string; code: string; originalCode?: string; suggestedPath: string } | null;
}

export const EditorPanel: React.FC<EditorPanelProps> = ({
  code,
  setCode,
  openedFilePath,
  isEditorFocused,
  setIsEditorFocused,
  includeEditorCode,
  setIncludeEditorCode,
  diffFile
}) => {
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
                  Düzenlemek için bir dosya aç<br />ya da sağdaki chat'ten direkt bir şey iste
                </p>
              </div>
              <div className="mt-10 flex gap-6 text-[10px] font-mono text-slate-700 font-semibold uppercase tracking-widest pointer-events-none">
                <span className="flex items-center gap-1.5"><Activity size={14} /> Bug Fix</span>
                <span className="flex items-center gap-1.5"><Cpu size={14} /> Kod Üretim</span>
                <span className="flex items-center gap-1.5"><Sparkles size={14} /> Analiz</span>
              </div>
            </div>
          )}

          <div
            className={`flex-1 relative z-10 transition-opacity duration-200 ${(code || openedFilePath || isEditorFocused) ? 'opacity-100' : 'opacity-0 pointer-events-none'}`}
          >
            {(code || openedFilePath) && (
              <motion.div
                initial={{ opacity: 0, scale: 0.8, x: -20 }}
                animate={{ opacity: 1, scale: 1, x: 0 }}
                className="absolute top-4 left-4 z-30 flex items-center gap-2"
              >
                <div className="relative group">
                  <button
                    onClick={() => setIncludeEditorCode(!includeEditorCode)}
                    className={`w-8 h-8 rounded-full flex items-center justify-center transition-all shadow-lg backdrop-blur-md border ${includeEditorCode
                        ? 'bg-blue-500 border-blue-400 text-white shadow-blue-500/40 rotate-45'
                        : 'bg-slate-900/80 border-slate-700 text-slate-400 hover:text-white hover:border-blue-500/50 hover:shadow-blue-500/20'
                      }`}
                  >
                    <Plus size={18} />
                  </button>

                  <div className="absolute left-10 top-1/2 -translate-y-1/2 px-3 py-1.5 bg-[#000000] border border-slate-800 rounded-lg text-[11px] text-slate-300 whitespace-nowrap opacity-0 group-hover:opacity-100 translate-x-2 group-hover:translate-x-0 transition-all pointer-events-none shadow-2xl z-50">
                    {includeEditorCode ? 'Kodu Çıkar' : 'Kodu AI\'ya Ekle'}
                    <div className="absolute right-full top-1/2 -translate-y-1/2 border-8 border-transparent border-r-slate-800" />
                  </div>
                </div>
              </motion.div>
            )}

            <Editor
              height="100%"
              defaultLanguage="csharp"
              theme={THEME_NAME}
              value={code}
              onChange={(val) => setCode(val || '')}
              onMount={(editor, monaco) => {
                defineUnityTheme(monaco);
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
