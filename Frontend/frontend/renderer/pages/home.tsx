import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import Head from 'next/head';
import axios from 'axios';
import { motion } from 'framer-motion';
import {
  ChevronLeft, ChevronRight, Terminal as TerminalIcon,
  Code2, Activity, X, PanelRightClose,
  Zap, Code, Layout, MessageSquare
} from 'lucide-react';
import { LangContext, translations, type Lang } from '../lib/i18n';

import { Sidebar } from '../components/home/Sidebar';
import { EditorPanel } from '../components/home/EditorPanel';
import { TerminalPanel } from '../components/home/TerminalPanel';
import { ChatPanel } from '../components/home/ChatPanel';
import { SettingsModal } from '../components/home/SettingsModal';
import { ExportModal } from '../components/home/ExportModal';
import { ModelSelector } from '../components/home/ModelSelector';
import { WorkspaceScreen } from '../components/home/WorkspaceScreen';
import { ControlPanel } from '../components/home/ControlPanel';
import { AnimatedChatInput } from '../components/ui/animated-ai-chat';

import { useAppInitialization } from '../hooks/home/useAppInitialization';
import { useAuth } from '../hooks/home/useAuth';
import { useFileSystem } from '../hooks/home/useFileSystem';
import { useChat } from '../hooks/home/useChat';
import { useAIConfig } from '../hooks/home/useAIConfig';
import { useMCPApproval } from '../hooks/home/useMCPApproval';

const ipc = typeof window !== 'undefined' ? (window as any).ipc : null;
const globalStyles = `
  .custom-scrollbar::-webkit-scrollbar { width: 6px; height: 6px; }
  .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
  .custom-scrollbar::-webkit-scrollbar-thumb { background: #334155; border-radius: 10px; }
  .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: #475569; }
  .monaco-editor, .monaco-editor .margin, .monaco-editor-background { background-color: #000000 !important; }
  .no-scrollbar::-webkit-scrollbar { display: none; }
`;

const getRelativePath = (absolutePath: string, workspacePath: string | null): string => {
  if (!workspacePath) return absolutePath.split('/').pop() || '';
  if (absolutePath.startsWith(workspacePath)) {
    let rel = absolutePath.substring(workspacePath.length);
    if (rel.startsWith('/') || rel.startsWith('\\')) {
      rel = rel.substring(1);
    }
    return rel;
  }
  return absolutePath.split('/').pop() || '';
};

export default function Home() {
  const { API, backendReady, backendError, showToast } = useAppInitialization();
  const auth = useAuth(API, backendReady);
  const fs = useFileSystem(API, auth.user, showToast as any);
  const ai = useAIConfig(API, auth.user, showToast as any, fs.workspacePath);
  const hasAutoLoadedRef = useRef(false);
  
  const chat = useChat(
    API, 
    auth.user, 
    ai.aiConfig, 
    fs.workspacePath, 
    showToast as any, 
    fs.refreshFileTree, 
    fs.suggestFilePath
  );

  useMCPApproval({
    API,
    enabled: ai.effectiveProvider === 'subscription',
    loading: chat.loading,
    setPendingGenFiles: fs.setPendingGenFiles,
    setPendingDelete: fs.setPendingDelete,
    setPendingCommand: chat.setPendingCommand,
    setPendingFix: chat.setPendingFix,
  });

  // API URL'yi window'a set et — ChatPanel ve diğer bileşenler erişebilsin
  useEffect(() => { if (API) (window as any).__API__ = API; }, [API]);

  // --- Initialization ---
  useEffect(() => {
    if (auth.isLoading) return;
    if (auth.user && API) {
      ai.fetchAIConfig(auth.user.id);
      ai.fetchAvailableModels();
      ai.fetchProvidersWithKeys(auth.user.id);
      fs.fetchLastWorkspace(auth.user.id);
      chat.fetchConversations(auth.user.id); // Eksik parça buydu!
    }
  }, [auth.isLoading, auth.user, API]);

  // --- Auto-Load Last Workspace ---
  useEffect(() => {
    if (fs.lastWorkspacePath && !fs.workspacePath && backendReady && !hasAutoLoadedRef.current) {
      fs.selectWorkspace(fs.lastWorkspacePath);
      hasAutoLoadedRef.current = true;
    }
  }, [fs.lastWorkspacePath, fs.workspacePath, backendReady]);

  // --- Ensure Active Workspace Is Saved In Backend ---
  useEffect(() => {
    if (API && auth.user?.sessionToken && fs.workspacePath) {
      axios.post(`${API}/save-workspace`, 
        { user_id: auth.user.id, path: fs.workspacePath },
        { headers: { 'X-Session-Token': auth.user.sessionToken } }
      ).catch(() => {});
    }
  }, [fs.workspacePath, API, auth.user]);

  // --- Startup Full Project Lint (The "Rider" Experience) ---
  useEffect(() => {
    if (API && auth.user && fs.workspacePath && backendReady) {
      const triggerFullLint = async () => {
        try {
          const res = await axios.post(`${API}/lint`, {
            code: "", // Full project taramada koda gerek yok
            filename: "project_root",
            full_project: true
          }, {
            headers: { 'X-Session-Token': auth.user?.sessionToken }
          });
          
          if (res.data && res.data.errors) {
            // Tüm hataları dosyalarına göre grupla ve state'e bas
            const grouped: Record<string, any[]> = {};
            res.data.errors.forEach((err: any) => {
              if (!grouped[err.file]) grouped[err.file] = [];
              grouped[err.file].push(err);
            });
            setProjectProblems(prev => {
              const next = { ...grouped };
              if (openedFileRef.current) {
                const relativeFile = getRelativePath(openedFileRef.current, fs.workspacePath);
                if (relativeFile && prev[relativeFile]) {
                  next[relativeFile] = prev[relativeFile];
                }
              }
              return next;
            });
          }
        } catch (err) {
          // Sessizce devam et
        }
      };
      
      const timer = setTimeout(triggerFullLint, 2000);
      return () => clearTimeout(timer);
    }
  }, [fs.workspacePath, API, auth.user, backendReady]);

  // --- Electron Menu IPC Listeners ---
  useEffect(() => {
    if (ipc) {
      const handleToggleTerminal = () => setIsTerminalOpen(prev => !prev);
      const handleOpenTerminal = () => setIsTerminalOpen(true);
      const handleClearTerminal = () => {
        showToast("Terminal temizlendi", "info");
      };

      const off1 = ipc.on('menu-toggle-terminal', handleToggleTerminal);
      const off2 = ipc.on('menu-open-terminal', handleOpenTerminal);
      const off3 = ipc.on('menu-clear-terminal', handleClearTerminal);

      return () => {
        if (typeof off1 === 'function') off1();
        if (typeof off2 === 'function') off2();
        if (typeof off3 === 'function') off3();
      };
    }
  }, [ipc, showToast]);

  // --- UI State ---
  // Hydration uyumu: ilk render hem build/SSR hem istemcide DETERMINISTIK 'tr' olmalı.
  // localStorage'ı render sırasında okumak (SSR 'tr' vs istemci 'en') hydration mismatch
  // yaratıyordu ("Hoş geldin" vs "Welcome"). Bu yüzden kayıtlı dili mount SONRASI okuyoruz.
  const [lang, setLangState] = useState<Lang>('tr');
  useEffect(() => {
    const stored = localStorage.getItem('app-lang') as Lang | null;
    if (stored === 'tr' || stored === 'en') setLangState(stored);
  }, []);
  const setLang = (l: Lang) => { setLangState(l); localStorage.setItem('app-lang', l); };
  const t = (key: string) => translations[lang][key] ?? key;
  const [thinkingLevel, setThinkingLevel] = useState<'off' | 'low' | 'medium' | 'high'>('medium');
  // Claude-only kontroller (max effort + ultracode). Sadece subscription + claude-* modelde.
  const [effortMax, setEffortMax] = useState(false);
  const [ultracode, setUltracode] = useState(false);
  const isClaudeSub = ai.effectiveProvider === 'subscription' && (ai.aiConfig?.model_name || '').startsWith('claude-');
  // Claude dışına geçilince stale 'max'/ultracode değerleri başka sağlayıcıya gitmesin
  useEffect(() => {
    if (!isClaudeSub) { setEffortMax(false); setUltracode(false); }
  }, [isClaudeSub]);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [isChatOpen, setIsChatOpen] = useState(true);
  const [sidebarTab, setSidebarTab] = useState<'chats' | 'files'>('chats');
  const [isEditorFocused, setIsEditorFocused] = useState(false);
  const [isTerminalOpen, setIsTerminalOpen] = useState(false);
  const [projectProblems, setProjectProblems] = useState<Record<string, any[]>>({});
  // Chat'te '/' autocomplete için Claude Code slash komutları + skill'ler (backend'den)
  const [slashCommands, setSlashCommands] = useState<string[]>([]);
  const [skills, setSkills] = useState<string[]>([]);
  const [commandMeta, setCommandMeta] = useState<{ name: string; description?: string; argumentHint?: string }[]>([]);
  useEffect(() => {
    if (!API) return;
    axios.get(`${API}/slash-commands`, { headers: { 'X-Session-Token': auth.user?.sessionToken } })
      .then(r => { setSlashCommands(r.data?.commands || []); setSkills(r.data?.skills || []); setCommandMeta(r.data?.meta || []); })
      .catch(() => {});
  }, [API, chat.loading]);  // mesaj bitince session başlamış olur → liste dolar, yeniden çek
  const chatEndRef = useRef<HTMLDivElement>(null);
  const lintTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const openedFileRef = useRef<string | null>(null);

  useEffect(() => {
    openedFileRef.current = fs.openedFilePath;
  }, [fs.openedFilePath]);

  // --- Real-time Linting (Single File) ---
  useEffect(() => {
    console.log("[Linter Debug] Triggered", { API, user: !!auth.user, path: fs.openedFilePath });
    if (!API || !auth.user || !fs.openedFilePath) return;
    
    if (lintTimeoutRef.current) clearTimeout(lintTimeoutRef.current);

    lintTimeoutRef.current = setTimeout(async () => {
      try {
        const relativeFile = getRelativePath(fs.openedFilePath!, fs.workspacePath);
        console.log("[Linter Debug] Sending POST to /lint", { filename: relativeFile });
        const res = await axios.post(`${API}/lint`, {
          code: fs.code,
          filename: relativeFile,
          full_project: false
        }, {
          headers: { 'X-Session-Token': auth.user?.sessionToken }
        });
        console.log("[Linter Debug] Response received", res.data);
        if (res.data && res.data.errors) {
          setProjectProblems(prev => ({ ...prev, [relativeFile]: res.data.errors }));
        }
      } catch (err) { console.error("[Linter] Request failed:", err); }
    }, 1000);

    return () => { if (lintTimeoutRef.current) clearTimeout(lintTimeoutRef.current); };
  }, [fs.code, fs.openedFilePath, API, auth.user]);

  // --- Full Project Linting ---
  const runFullProjectLint = async () => {
    if (!API || !auth.user || !fs.workspacePath) return;
    try {
      const relativeFile = getRelativePath(fs.openedFilePath || '', fs.workspacePath);
      const res = await axios.post(`${API}/lint`, {
        code: fs.code,
        filename: relativeFile || 'dummy.cs',
        full_project: true
      }, { headers: { 'X-Session-Token': auth.user?.sessionToken } });
      
      if (res.data && res.data.errors) {
        const grouped: Record<string, any[]> = {};
        res.data.errors.forEach((err: any) => {
          const fname = err.file || 'Unknown';
          if (!grouped[fname]) grouped[fname] = [];
          grouped[fname].push(err);
        });
        setProjectProblems(prev => {
          const next = { ...grouped };
          if (openedFileRef.current) {
            const relativeFile = getRelativePath(openedFileRef.current, fs.workspacePath);
            if (relativeFile && prev[relativeFile]) {
              next[relativeFile] = prev[relativeFile];
            }
          }
          return next;
        });
      }
    } catch (err) { console.error("Full project lint failed:", err); }
  };

  const flattenedProblems = useMemo(() => {
    return Object.values(projectProblems)
      .flat()
      .filter((p: any) => !p.file || !p.file.includes('Assets/Plugins/'));
  }, [projectProblems]);

  const [diffFile, setDiffFile] = useState<any>(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chat.messages, chat.loading]);

  // --- Save Shortcut (Ctrl+S / Cmd+S) ---
  useEffect(() => {
    const handleKeyDown = async (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        const success = await fs.saveFile();
        if (success) runFullProjectLint();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [fs.saveFile, fs.workspacePath, auth.user]);

  const handleLogout = () => { fs.closeWorkspace(); };

  const handleProblemClick = (problem: any) => {
    if (problem.file && fs.workspacePath) {
      fs.openFile(problem.file);
    }
  };

  const handleSendMessage = async (msg?: string, images?: string[]) => {
    let input = (msg || chat.chatInput).trim();
    if (!input && (!images || images.length === 0)) return;

    const fileMatches = input.match(/\[File Attached: (.*?)\]/g);
    if (fileMatches && ipc) {
      for (const match of fileMatches) {
        const path = match.match(/\[File Attached: (.*?)\]/)?.[1];
        if (path) {
          try {
            const result = await ipc.invoke('read-file', path, fs.workspacePath);
            if (result && result.content) {
              const fileContent = `\n\n--- FILE: ${path} ---\n${result.content}\n--- END FILE ---`;
              input = input.replace(match, fileContent);
            }
          } catch (err) { input = input.replace(match, `(Dosya okunamadı: ${path})`); }
        }
      }
    }
    chat.sendMessage(input, fs.code, lang, chat.generationMode, thinkingLevel, fs.setPendingGenFiles, fs.setPendingDelete, images, effortMax, ultracode);
  };

  const langCtxValue = { lang, setLang, t: (k: string) => translations[lang][k] ?? k };

  if (backendError) {
    return (
      <div className="h-screen bg-black flex flex-col items-center justify-center text-center p-6">
        <div className="text-red-500 text-5xl mb-4">⚠</div>
        <h2 className="text-white text-xl font-bold mb-2">Backend Bağlantısı Başarısız</h2>
        <p className="text-slate-400 max-w-md">Backend erişilemez durumda. Lütfen uygulamayı yeniden başlatın.</p>
      </div>
    );
  }

  if (!fs.workspacePath) {
    return (
      <LangContext.Provider value={langCtxValue}>
        <WorkspaceScreen
          userName={auth.user.name} lastWorkspacePath={fs.lastWorkspacePath}
          onOpenWorkspaceDialog={fs.openFolder} onSelectLastWorkspace={() => fs.selectWorkspace(fs.lastWorkspacePath!)}
          onLogout={handleLogout}
        />
      </LangContext.Provider>
    );
  }


  return (
    <LangContext.Provider value={langCtxValue}>
    <div className="flex h-screen bg-[#000000] text-slate-200 font-sans overflow-hidden">
      <Head>
        <title>{`Unity Architect AI | ${auth.user?.name || 'Giriş'}`}</title>
        <style>{globalStyles}</style>
      </Head>

      <SettingsModal
        open={ai.showSettings} aiConfig={ai.aiConfig} providersWithKeys={ai.providersWithKeys}
        onChange={ai.setAiConfig} onClose={() => ai.setShowSettings(false)} onSave={ai.saveAIConfig}
        onLogout={handleLogout} onDeleteKey={ai.deleteApiKey}
        unityMcpStatus={ai.unityMcpStatus} unityMcpToggling={ai.unityMcpToggling} onToggleUnityMcp={ai.toggleUnityMcp}
        lang={lang} onLangChange={setLang}
      />

      <ExportModal
        exportModal={fs.exportModal} exportFileName={fs.exportFileName} workspacePath={fs.workspacePath}
        onFileNameChange={fs.setExportFileName} onClose={() => fs.setExportModal(null)}
        onChangeExportDir={fs.changeExportDir} onExportSingleFile={fs.exportSingleFile} onExportMultipleFiles={fs.exportMultipleFiles}
      />

      <Sidebar
        isSidebarOpen={isSidebarOpen} sidebarTab={sidebarTab} setSidebarTab={setSidebarTab}
        conversations={chat.conversations} activeConvId={chat.activeConvId} selectConversation={chat.selectConversation}
        createNewConversation={chat.createNewConversation} deleteConversation={chat.deleteConversation}
        editingId={chat.editingId} setEditingId={chat.setEditingId} tempTitle={chat.tempTitle} setTempTitle={chat.setTempTitle} saveRename={chat.saveRename}
        workspacePath={fs.workspacePath} closeWorkspace={fs.closeWorkspace} rootFolderPath={fs.rootFolderPath}
        openFolder={fs.openFolder} openFilePicker={fs.openFilePicker} treeCreating={fs.treeCreating}
        setTreeCreating={fs.setTreeCreating} treeCreateValue={fs.treeCreateValue} setTreeCreateValue={fs.setTreeCreateValue}
        submitTreeCreate={fs.submitTreeCreate} fileTree={fs.fileTree}
        openedFilePath={fs.openedFilePath} expandedDirs={fs.expandedDirs} dirContents={fs.dirContents}
        toggleDir={fs.toggleDir} openFile={fs.openFile} treeDragSource={fs.treeDragSource}
        treeDragTarget={fs.treeDragTarget} renamingPath={fs.renamingPath} renameValue={fs.renameValue}
        setRenameValue={fs.setRenameValue} submitRename={fs.submitRename} setRenamingPath={fs.setRenamingPath}
        handleTreeDragStart={fs.handleTreeDragStart} handleTreeDragOver={fs.handleTreeDragOver}
        handleTreeDragLeave={fs.handleTreeDragLeave} handleTreeDrop={fs.handleTreeDrop}
        handleTreeContextMenu={fs.handleTreeContextMenu} startTreeCreate={fs.startTreeCreate}
        startRename={fs.startRename} handleTreeDelete={fs.handleTreeDelete}
        treeContextMenu={fs.treeContextMenu} setTreeContextMenu={fs.setTreeContextMenu}
        user={auth.user} setShowSettings={ai.setShowSettings} handleLogout={handleLogout}
      />

      <div className="flex-1 flex flex-col min-w-0 border-r border-slate-800/50">
        <div className="h-11 border-b border-slate-800/50 flex items-center justify-between px-4 bg-[#000000]/50 shrink-0">
          <div className="flex items-center gap-3">
            <button onClick={() => setIsSidebarOpen(!isSidebarOpen)} className="p-1.5 hover:bg-slate-800 rounded-lg text-slate-500 transition-all">
              {isSidebarOpen ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
            </button>
            <button onClick={() => setIsTerminalOpen(!isTerminalOpen)} className={`p-1.5 hover:bg-slate-800 rounded-lg transition-all ${isTerminalOpen ? 'text-blue-500 bg-blue-500/10' : 'text-slate-500'}`}>
              <TerminalIcon size={16} />
            </button>
            <div className="flex items-center gap-2 border-l border-slate-800/50 pl-3 ml-1">
              <Code2 size={14} className="text-blue-500" />
              <div className="flex items-center gap-1.5">
                <span className="text-[12px] font-semibold text-slate-400">
                  {fs.openedFilePath ? fs.openedFilePath.split('/').pop() : 'C# Editor'}
                </span>
                {fs.isDirty && <div className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" />}
              </div>
              {fs.openedFilePath && (
                <div className="flex items-center gap-1">
                  <button onClick={async () => { if (await fs.saveFile()) runFullProjectLint(); }} disabled={!fs.isDirty} className={`p-1 rounded hover:bg-slate-800 ${fs.isDirty ? 'text-blue-400' : 'text-slate-600 opacity-50'}`}>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"></path><polyline points="17 21 17 13 7 13 7 21"></polyline><polyline points="7 3 7 8 15 8"></polyline></svg>
                  </button>
                  <button onClick={() => { fs.setOpenedFilePath(null); fs.setCode(''); }} className="p-0.5 hover:bg-slate-700 rounded text-slate-500"><X size={12} /></button>
                </div>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2 relative">
            {/* Unity MCP Hata Banner'ı */}
            {ai.unityMcpError && (
              <div className="absolute top-full right-0 mt-2 z-50 px-3 py-2 rounded-lg border border-red-500/40 bg-red-500/10 text-red-300 text-[11px] font-medium shadow-lg whitespace-nowrap flex items-center gap-2 animate-in fade-in slide-in-from-top-1">
                <span className="w-1.5 h-1.5 rounded-full bg-red-400 animate-pulse" />
                {ai.unityMcpError}
              </div>
            )}
            {/* Unity MCP Durum Göstergesi */}
            <button
              onClick={ai.toggleUnityMcp}
              disabled={ai.unityMcpToggling || ai.unityMcpStatus === 'starting'}
              title={
                ai.unityMcpStatus === 'connected' ? t('home.unityConnected') :
                ai.unityMcpStatus === 'running'   ? t('home.unityConnecting') :
                ai.unityMcpStatus === 'starting'  ? t('home.unityStarting') :
                t('home.unityOpen')
              }
              className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-[10px] font-bold uppercase tracking-wider transition-all disabled:opacity-50 whitespace-nowrap shrink-0 ${
                ai.unityMcpStatus === 'connected' ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/20' :
                ai.unityMcpStatus === 'running' ? 'bg-yellow-500/10 border-yellow-500/30 text-yellow-400 hover:bg-yellow-500/20' :
                ai.unityMcpStatus === 'starting' ? 'bg-yellow-500/10 border-yellow-500/30 text-yellow-400' :
                'bg-slate-800/50 border-slate-700/50 text-slate-500 hover:bg-slate-700/50 hover:text-slate-300'
              }`}
            >
              <span className={`w-1.5 h-1.5 rounded-full ${
                ai.unityMcpStatus === 'connected' ? 'bg-emerald-400' :
                ai.unityMcpStatus === 'running' || ai.unityMcpStatus === 'starting' ? 'bg-yellow-400 animate-pulse' :
                'bg-slate-600'
              }`} />
              Unity MCP
            </button>
            <ModelSelector
              aiConfig={ai.aiConfig} setAiConfig={ai.setAiConfig} availableModels={ai.availableModels} providersWithKeys={ai.providersWithKeys}
              effectiveProvider={ai.effectiveProvider} displayModelName={ai.displayModelName} isModelDropdownOpen={ai.isModelDropdownOpen} setIsModelDropdownOpen={ai.setIsModelDropdownOpen}
              modelOrToggles={ai.modelOrToggles} setModelOrToggles={ai.setModelOrToggles} user={auth.user} fetchAvailableModels={ai.fetchAvailableModels} setShowSettings={ai.setShowSettings}
              API={API} axios={axios} showToast={showToast as any}
            />
            <Activity size={14} className="text-emerald-500 animate-pulse" />
            {!isChatOpen && (
              <button 
                onClick={() => setIsChatOpen(true)} 
                className="p-1.5 bg-blue-600/10 hover:bg-blue-600/20 text-blue-500 rounded-lg transition-all flex items-center gap-2 px-3 ml-2 border border-blue-500/20"
                title={t('home.openChat')}
              >
                <MessageSquare size={14} />
                <span className="text-[10px] font-bold uppercase tracking-wider">{t('home.openChat')}</span>
              </button>
            )}
          </div>
        </div>

        <div className="flex-1 overflow-hidden relative flex flex-col bg-[#000000]">
          {(fs.openedFilePath || diffFile) ? (
            <EditorPanel
              code={fs.code} setCode={fs.setCode} openedFilePath={fs.openedFilePath} isEditorFocused={isEditorFocused} setIsEditorFocused={setIsEditorFocused}
              workspacePath={fs.workspacePath} problems={flattenedProblems} diffFile={diffFile}
            />
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-center p-8 bg-[#000000]">
              <div className="relative mb-8">
                <div className="absolute inset-0 bg-blue-500/10 blur-[80px] rounded-full animate-pulse" />
                <Zap size={48} className="text-blue-500 relative z-10 opacity-40" />
              </div>
              <h2 className="text-2xl font-bold text-slate-200 mb-3 tracking-tight">UNITY ARCHITECT ENGINE</h2>
              <p className="text-slate-500 text-sm max-w-md leading-relaxed mb-8">{t("home.editorHint")}</p>
              <div className="grid grid-cols-3 gap-4 max-w-lg w-full">
                {[ {icon:<Activity size={14}/>, label: t('home.bugfix')}, {icon:<Code size={14}/>, label: t('home.codegen')}, {icon:<Layout size={14}/>, label: t('home.analyze')} ].map((item, i) => (
                  <div key={i} className="px-4 py-3 bg-slate-900/40 border border-slate-800/50 rounded-xl flex items-center justify-center gap-2 text-[11px] font-bold text-slate-400 hover:bg-slate-800/60 hover:text-slate-200 transition-all cursor-default">
                    {item.icon} {item.label}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
        <TerminalPanel
          id="main-terminal"
          isOpen={isTerminalOpen}
          onClose={() => setIsTerminalOpen(false)}
          workspacePath={fs.workspacePath}
          problems={flattenedProblems}
          onProblemClick={handleProblemClick}
          apiUrl={API}
          sessionToken={auth.user?.sessionToken}
          unityConnected={ai.unityMcpStatus === 'connected'}
        />
      </div>

      <motion.div animate={{ width: isChatOpen ? 450 : 0, opacity: isChatOpen ? 1 : 0 }} transition={{ duration: 0.2 }} className="bg-[#000000] flex flex-col overflow-hidden shrink-0 border-l border-slate-800/50">
        <div className="flex-1 relative flex flex-col min-h-0 bg-[#000000]">
          <div className="h-11 border-b border-slate-800/50 flex items-center justify-between px-4 bg-[#000000]/50 shrink-0">
            <span className="text-[11px] font-bold text-slate-500 uppercase tracking-widest">Architect Copilot</span>
            <button onClick={() => setIsChatOpen(false)} className="p-1 hover:bg-slate-800 rounded transition-all text-slate-500"><PanelRightClose size={16} /></button>
          </div>
          
          <div className="flex-1 overflow-y-auto custom-scrollbar">
            <ChatPanel 
              messages={chat.messages} activeConvId={chat.activeConvId} user={auth.user} loading={chat.loading} clearHistory={chat.clearHistory} lang={lang}
              effectiveProvider={ai.effectiveProvider}
              modelName={ai.aiConfig?.model_name}
              thinkingLevel={thinkingLevel} workspacePath={fs.workspacePath} handleExportToUnity={fs.handleExportToUnity}
              pendingGenFiles={fs.pendingGenFiles} setPendingGenFiles={fs.setPendingGenFiles} pendingFix={chat.pendingFix} setPendingFix={chat.setPendingFix} openedFilePath={fs.openedFilePath}
              setCode={fs.setCode} refreshFileTree={fs.refreshFileTree} analyzeProject={chat.analyzeProject} openFile={fs.openFile} sendMessage={handleSendMessage}
              currentPlan={chat.currentPlan} messagesEndRef={chatEndRef} ipc={ipc} showToast={showToast as any} diffFile={diffFile} setDiffFile={setDiffFile}
              pendingDelete={fs.pendingDelete} setPendingDelete={fs.setPendingDelete} pendingCommand={chat.pendingCommand} setPendingCommand={chat.setPendingCommand} onApproveCommand={chat.approveCommand} pendingQuestion={chat.pendingQuestion} setPendingQuestion={chat.setPendingQuestion} onAnswerQuestion={chat.answerQuestion} deleteFile={fs.deleteFile} setIsTerminalOpen={setIsTerminalOpen}
            />
          </div>

          <div className="p-4 border-t border-slate-800/50 bg-[#000000]">
            <ControlPanel
              thinkingLevel={thinkingLevel} setThinkingLevel={setThinkingLevel} generationMode={chat.generationMode} setGenerationMode={chat.setGenerationMode}
              isAnalyzingProject={chat.isAnalyzingProject} activeConvId={chat.activeConvId} analyzeProject={chat.analyzeProject}
              exportMemory={chat.exportMemory} importMemory={chat.importMemory} compactConversation={chat.compactConversation} isCompacting={chat.isCompacting} contextUsage={chat.contextUsage}
              isClaudeSubscription={isClaudeSub} effortMax={effortMax} setEffortMax={setEffortMax} ultracode={ultracode} setUltracode={setUltracode}
            />
            <div className="mt-3">
              <AnimatedChatInput
                value={chat.chatInput} setValue={chat.setChatInput} onSendMessage={handleSendMessage} isLoading={chat.loading}
                slashCommands={slashCommands}
                skills={skills}
                commandMeta={commandMeta}
                onStop={chat.stopMessage}
                onFileDrop={(entry) => chat.setChatInput(prev => prev + ` [File Attached: ${entry.path}]`)}
                onCommand={(cmd) => {
                  if (cmd === '/compact') { chat.compactConversation(); return true; }
                  return false;
                }}
              />
            </div>
          </div>
        </div>
      </motion.div>
    </div>
    </LangContext.Provider>
  );
}
