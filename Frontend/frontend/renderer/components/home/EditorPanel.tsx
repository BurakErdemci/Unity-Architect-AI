// EN ÜSTTE: modüller import sırasına göre değerlendiriliyor. Loader'ın `paths.vs`
// yapılandırması, `@monaco-editor/react` değerlendirilmeden ÖNCE yazılmalı ki
// hiçbir Editor mount'u gömülü CDN varsayılanını yakalayamasın.
import './monaco-loader';
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
  // Unity YAML asset formatları (metin — editörde yaml olarak açılır)
  '.anim': 'yaml', '.prefab': 'yaml', '.unity': 'yaml', '.mat': 'yaml',
  '.asset': 'yaml', '.controller': 'yaml', '.overridecontroller': 'yaml',
  '.physicmaterial': 'yaml', '.physicsmaterial2d': 'yaml', '.mixer': 'yaml',
  '.rendertexture': 'yaml', '.spriteatlas': 'yaml', '.terrainlayer': 'yaml',
  '.playable': 'yaml', '.signal': 'yaml', '.preset': 'yaml', '.guiskin': 'yaml',
  '.fontsettings': 'yaml', '.flare': 'yaml', '.giparams': 'yaml',
  '.shadervariants': 'yaml', '.mask': 'yaml', '.brush': 'yaml', '.meta': 'yaml',
  '.asmref': 'json', '.inputactions': 'json', '.html': 'html', '.css': 'css',
  '.js': 'javascript', '.csv': 'plaintext', '.ini': 'ini', '.cfg': 'ini',
};

function monacoLangFor(filePath: string | null): string {
  if (!filePath) return 'csharp';
  const dot = filePath.lastIndexOf('.');
  if (dot < 0) return 'plaintext';
  return MONACO_LANG[filePath.slice(dot).toLowerCase()] ?? 'plaintext';
}

// LSP CompletionItemKind → Monaco CompletionItemKind (numaraları farklı enumlar)
const LSP_TO_MONACO_KIND: Record<number, number> = {
  1: 18, 2: 0, 3: 1, 4: 2, 5: 3, 6: 4, 7: 5, 8: 7, 9: 8, 10: 9, 11: 12, 12: 13,
  13: 15, 14: 17, 15: 27, 16: 19, 17: 20, 18: 21, 19: 23, 20: 16, 21: 14,
  22: 6, 23: 10, 24: 11, 25: 24,
};

interface EditorPanelProps {
  code: string;
  setCode: (code: string) => void;
  openedFilePath: string | null;
  isEditorFocused: boolean;
  setIsEditorFocused: (focused: boolean) => void;
  workspacePath: string | null;
  problems?: any[];
  // OmniSharp IntelliSense (completion/hover/definition) için backend erişimi
  apiUrl?: string | null;
  sessionToken?: string | null;
  openFile?: (path: string) => void;
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
  apiUrl,
  sessionToken,
  openFile,
  diffFile
}) => {
  const { t } = useLang();
  const monacoRef = React.useRef<any>(null);
  const editorRef = React.useRef<any>(null);
  const [modelChangedTrigger, setModelChangedTrigger] = React.useState(0);

  // Provider closure'ları bir kez kaydedilir; güncel prop'ları ref üzerinden görsünler
  // (auth token ve açık dosya mount'tan SONRA değişiyor — closure bayat kalmasın).
  const lspCtxRef = React.useRef({ apiUrl, sessionToken, openedFilePath, openFile });
  React.useEffect(() => {
    lspCtxRef.current = { apiUrl, sessionToken, openedFilePath, openFile };
  }, [apiUrl, sessionToken, openedFilePath, openFile]);

  // Bir LSP isteğinin uçuşta kalabileceği en uzun süre. Sunucu tarafında C# analizi
  // başlatılamadığında istek uzun süre asılabiliyordu ve istemcide hiçbir üst sınır
  // yoktu: Monaco her imleç hareketinde yeni bir hover isteği ürettiği için istekler
  // birikiyor, Chromium'un host başına 6 bağlantı sınırına dayanıyor ve editör
  // tümden yanıt veremez hale geliyordu (ölçüldü 2026-07-27).
  const LSP_TIMEOUT_MS = 8000;

  const lspPost = async (ep: string, body: any, token?: any) => {
    const { apiUrl: api, sessionToken: sess } = lspCtxRef.current;
    if (!api) return null;
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), LSP_TIMEOUT_MS);
    // Monaco imleç hareket edince kendi CancellationToken'ını iptal ediyor. Bu
    // dinlenmezse iptal edilmiş bir hover'ın HTTP isteği uçuşta kalmaya devam eder.
    const onCancel = token?.onCancellationRequested?.(() => ctrl.abort());
    try {
      const r = await fetch(`${api}/lsp/${ep}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Session-Token': sess || '' },
        body: JSON.stringify(body),
        signal: ctrl.signal,
      });
      return r.ok ? r.json() : null;
    } catch { return null; }
    finally {
      clearTimeout(timer);
      onCancel?.dispose?.();
    }
  };

  const registerCsProviders = (monaco: any) => {
    // Monaco global'ine kaydolur — HMR/remount'ta çift kayıt olmasın
    if ((window as any).__csProvidersRegistered) return;
    (window as any).__csProvidersRegistered = true;

    monaco.languages.registerCompletionItemProvider('csharp', {
      triggerCharacters: ['.'],
      provideCompletionItems: async (model: any, position: any, _ctx: any, token: any) => {
        const data = await lspPost('completion', {
          path: lspCtxRef.current.openedFilePath, text: model.getValue(),
          line: position.lineNumber, column: position.column,
        }, token);
        const word = model.getWordUntilPosition(position);
        const range = { startLineNumber: position.lineNumber, endLineNumber: position.lineNumber,
                        startColumn: word.startColumn, endColumn: word.endColumn };
        return { suggestions: (data?.items || []).map((it: any) => ({
          label: it.label,
          kind: LSP_TO_MONACO_KIND[it.kind] ?? 18,
          insertText: it.insertText, detail: it.detail, range })) };
      },
    });

    monaco.languages.registerHoverProvider('csharp', {
      provideHover: async (model: any, position: any, token: any) => {
        const data = await lspPost('hover', {
          path: lspCtxRef.current.openedFilePath, text: model.getValue(),
          line: position.lineNumber, column: position.column,
        }, token);
        return data?.contents ? { contents: [{ value: data.contents }] } : null;
      },
    });

    monaco.languages.registerDefinitionProvider('csharp', {
      provideDefinition: async (model: any, position: any, token: any) => {
        const data = await lspPost('definition', {
          path: lspCtxRef.current.openedFilePath, text: model.getValue(),
          line: position.lineNumber, column: position.column,
        }, token);
        if (!data?.location) return null;
        // Cross-model çözümü yerine dosyayı uygulama içinde aç
        lspCtxRef.current.openFile?.(data.location.file);
        return null;
      },
    });
  };

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
                <h3 className="text-sm font-bold text-slate-400 tracking-[0.2em] uppercase">Gamachine Engine</h3>
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
                registerCsProviders(monaco);

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
