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
import { ControlPanel, ThinkingLevel, EffortCaps } from '../components/home/ControlPanel';
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
  .monaco-editor, .monaco-editor .margin, .monaco-editor-background { background-color: #0B0D12 !important; }
  .no-scrollbar::-webkit-scrollbar { display: none; }
`;

// Aktif modelin marka rengi (r,g,b) — imza "ambient ışık" bunu kullanır:
// copilot panelindeki üst süzülme + hero glow, hangi zekayla konuşulduğunu
// renkle hissettirir (Claude turuncu, Gemini mavi, Copilot menekşe...).
const BRAND_RGB: Record<string, string> = {
  claude: '251, 146, 60',
  openai: '52, 211, 153',
  gemini: '96, 165, 250',
  copilot: '196, 181, 253',
  cursor: '226, 232, 240',
  opencode: '94, 234, 212',
};
const getBrandRgb = (modelName?: string, provider?: string): string => {
  const m = (modelName || '').toLowerCase();
  if (m.startsWith('claude-')) return BRAND_RGB.claude;
  if (m.startsWith('gpt-')) return BRAND_RGB.openai;
  if (m.startsWith('gemini') || m.startsWith('agy-')) return BRAND_RGB.gemini;
  if (m.startsWith('copilot-')) return BRAND_RGB.copilot;
  if (m.startsWith('cursor-')) return BRAND_RGB.cursor;
  if (m.startsWith('opencode:')) return BRAND_RGB.opencode;
  return BRAND_RGB[(provider || '').toLowerCase()] || '96, 165, 250';
};

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
  // Tek kavramsal effort skalası — GÖSTERİLEN seviyeler backend kayıtçısından gelir
  // (/effort-capabilities): provider+model neyi destekliyorsa o. 'auto' = model
  // varsayılanı, hiçbir parametre gönderilmez.
  const [thinkingLevel, setThinkingLevel] = useState<ThinkingLevel>('auto');
  const [effortCaps, setEffortCaps] = useState<EffortCaps | null>(null);
  // Claude-only kontrol (ultracode). Sadece subscription + claude-* modelde.
  const [ultracode, setUltracode] = useState(false);
  const isClaudeSub = ai.effectiveProvider === 'subscription' && (ai.aiConfig?.model_name || '').startsWith('claude-');
  useEffect(() => {
    if (!isClaudeSub) setUltracode(false);
  }, [isClaudeSub]);
  // Provider/model değişince yetenekleri çek; mevcut seçim yeni listede yoksa auto'ya kıstır.
  useEffect(() => {
    if (!API || !auth.user) return;
    const provider = ai.effectiveProvider || '';
    const model = ai.aiConfig?.model_name || '';
    axios.get(`${API}/effort-capabilities`, {
      params: { provider, model },
      headers: { 'X-Session-Token': auth.user?.sessionToken },
    }).then(r => {
      const caps = r.data as EffortCaps;
      setEffortCaps(caps);
      setThinkingLevel(prev => (caps?.levels || []).includes(prev) ? prev : 'auto');
    }).catch(() => setEffortCaps(null));
  }, [API, auth.user, ai.effectiveProvider, ai.aiConfig?.model_name]);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [isChatOpen, setIsChatOpen] = useState(true);
  const [sidebarTab, setSidebarTab] = useState<'chats' | 'files'>('chats');
  const [isEditorFocused, setIsEditorFocused] = useState(false);
  const [isTerminalOpen, setIsTerminalOpen] = useState(false);
  const [projectProblems, setProjectProblems] = useState<Record<string, any[]>>({});
  // OmniSharp sidecar durumu (starting → üst barda "C# analizi hazırlanıyor…" rozeti)
  const [lspStatus, setLspStatus] = useState<{ state: string; detail: string } | null>(null);
  // Chat'te '/' autocomplete için Claude Code slash komutları + skill'ler (backend'den)
  const [slashCommands, setSlashCommands] = useState<string[]>([]);
  const [skills, setSkills] = useState<string[]>([]);
  const [commandMeta, setCommandMeta] = useState<{ name: string; description?: string; argumentHint?: string; insert?: string; displayName?: string }[]>([]);
  // Hangi provider'ın komut/skill kataloğu çekilecek? (backend buna göre kaynak seçer)
  //   gpt-* → codex (app-server skills/list), gemini/agy-* → agy (boş, headless),
  //   diğer subscription → claude (Claude Code slash + skill). subscription değilse katalog yok.
  const slashProvider = (() => {
    if (ai.effectiveProvider !== 'subscription') return 'other';
    const m = (ai.aiConfig?.model_name || '').toLowerCase();
    if (m.startsWith('gpt-')) return 'codex';
    if (m.startsWith('gemini') || m.startsWith('agy-')) return 'agy';
    return 'claude';
  })();
  useEffect(() => {
    if (!API || slashProvider === 'other') { setSlashCommands([]); setSkills([]); setCommandMeta([]); return; }
    axios.get(`${API}/slash-commands`, { params: { provider: slashProvider }, headers: { 'X-Session-Token': auth.user?.sessionToken } })
      .then(r => { setSlashCommands(r.data?.commands || []); setSkills(r.data?.skills || []); setCommandMeta(r.data?.meta || []); })
      .catch(() => {});
  }, [API, chat.loading, slashProvider]);  // mesaj bitince session dolar + provider değişince yeniden çek
  const chatEndRef = useRef<HTMLDivElement>(null);
  const lintTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const openedFileRef = useRef<string | null>(null);

  useEffect(() => {
    openedFileRef.current = fs.openedFilePath;
  }, [fs.openedFilePath]);

  // --- Canlı diagnostics (OmniSharp sidecar) ---
  useEffect(() => {
    if (!API || !auth.user || !fs.openedFilePath) return;
    // C# analizi yalnızca .cs için — md/json/shader gibi dosyalar da açılabiliyor.
    if (!fs.openedFilePath.toLowerCase().endsWith('.cs')) return;

    if (lintTimeoutRef.current) clearTimeout(lintTimeoutRef.current);

    lintTimeoutRef.current = setTimeout(async () => {
      try {
        const relativeFile = getRelativePath(fs.openedFilePath!, fs.workspacePath);
        const res = await axios.post(`${API}/lsp/change`,
          { path: relativeFile, text: fs.code },
          { headers: { 'X-Session-Token': auth.user?.sessionToken } });
        setLspStatus(res.data?.status || null);
        if (res.data?.problems) {
          setProjectProblems(prev => ({ ...prev, [relativeFile]: res.data.problems }));
        }
      } catch { /* sidecar kapalıysa sessiz */ }
    }, 700);

    return () => { if (lintTimeoutRef.current) clearTimeout(lintTimeoutRef.current); };
  }, [fs.code, fs.openedFilePath, API, auth.user]);

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
        await fs.saveFile();
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

  const handleSendMessage = async (msg?: string, images?: string[], videos?: any[]) => {
    let input = (msg || chat.chatInput).trim();
    if (!input && (!images || images.length === 0) && (!videos || videos.length === 0)) return;

    // Send-gate: aktif bulut sağlayıcının API key'i yoksa göndermeyi engelle (net uyarı +
    // Ayarlar). Optimistic model seçimiyle beraber → keyless modele geçilse bile sessizce
    // yanlış sağlayıcıya düşmek yerine kullanıcı net yönlendirilir.
    const _pt = ai.aiConfig.provider_type;
    if (!['subscription', 'ollama', 'kb'].includes(_pt) && !ai.providersWithKeys.includes(_pt)) {
      showToast(`Bu model için ${_pt} API key gerekli — Ayarlar'dan ekle.`, 'warning');
      ai.setShowSettings(true);
      return;
    }

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
    chat.sendMessage(input, fs.code, lang, chat.generationMode, thinkingLevel, fs.setPendingGenFiles, fs.setPendingDelete, images, ultracode, videos);
  };

  const langCtxValue = { lang, setLang, t: (k: string) => translations[lang][k] ?? k };

  // İmza ambient ışık: aktif modelin marka rengi
  const brandRgb = getBrandRgb(ai.aiConfig?.model_name, ai.effectiveProvider);

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
    <div className="flex h-screen bg-[#0B0D12] text-slate-200 font-sans overflow-hidden">
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
        gitStatus={fs.gitStatus}
        user={auth.user} setShowSettings={ai.setShowSettings} handleLogout={handleLogout}
      />

      <div className="flex-1 flex flex-col min-w-0 border-r border-white/[0.06]">
        <div className="h-12 border-b border-white/[0.06] flex items-center justify-between px-4 bg-white/[0.015] shrink-0">
          <div className="flex items-center gap-3 min-w-0">
            <button onClick={() => setIsSidebarOpen(!isSidebarOpen)} className="p-1.5 hover:bg-white/[0.06] rounded-lg text-slate-500 hover:text-slate-300 transition-all shrink-0">
              {isSidebarOpen ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
            </button>
            <button onClick={() => setIsTerminalOpen(!isTerminalOpen)} className={`p-1.5 hover:bg-white/[0.06] rounded-lg transition-all shrink-0 ${isTerminalOpen ? 'text-blue-400 bg-blue-500/10' : 'text-slate-500 hover:text-slate-300'}`}>
              <TerminalIcon size={16} />
            </button>
            <div className="flex items-center gap-2 border-l border-white/[0.06] pl-3 ml-1 min-w-0" title={fs.openedFilePath || undefined}>
              <Code2 size={14} className="text-blue-500 shrink-0" />
              <div className="flex items-center gap-1.5 min-w-0">
                {/* Windows yolları '\' kullanır — her iki ayraçta da böl; dar ekranda kırp */}
                <span className="text-[12px] font-semibold text-slate-400 truncate">
                  {fs.openedFilePath ? fs.openedFilePath.split(/[\\/]/).pop() : 'C# Editor'}
                </span>
                {fs.isDirty && <div className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse shrink-0" />}
              </div>
              {fs.openedFilePath && (
                <div className="flex items-center gap-1 shrink-0">
                  <button onClick={async () => { await fs.saveFile(); }} disabled={!fs.isDirty} className={`p-1 rounded hover:bg-slate-800 ${fs.isDirty ? 'text-blue-400' : 'text-slate-600 opacity-50'}`}>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"></path><polyline points="17 21 17 13 7 13 7 21"></polyline><polyline points="7 3 7 8 15 8"></polyline></svg>
                  </button>
                  <button onClick={() => { fs.setOpenedFilePath(null); fs.setCode(''); }} className="p-0.5 hover:bg-slate-700 rounded text-slate-500"><X size={12} /></button>
                </div>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2 relative shrink-0">
            {/* Unity MCP Hata Banner'ı */}
            {ai.unityMcpError && (
              <div className="absolute top-full right-0 mt-2 z-50 px-3 py-2 rounded-lg border border-red-500/40 bg-red-500/10 text-red-300 text-[11px] font-medium shadow-lg whitespace-nowrap flex items-center gap-2 animate-in fade-in slide-in-from-top-1">
                <span className="w-1.5 h-1.5 rounded-full bg-red-400 animate-pulse" />
                {ai.unityMcpError}
              </div>
            )}
            {/* C# analizi (OmniSharp) hazırlanıyor rozeti */}
            {lspStatus?.state === 'starting' && (
              <span className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-white/[0.08] bg-white/[0.03] text-[10px] font-semibold text-slate-400 whitespace-nowrap">
                <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
                C# analizi hazırlanıyor…
              </span>
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
                'bg-white/[0.03] border-white/[0.08] text-slate-500 hover:bg-white/[0.06] hover:text-slate-300'
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

        <div className="flex-1 overflow-hidden relative flex flex-col bg-[#0B0D12]">
          {(fs.openedFilePath || diffFile) ? (
            <EditorPanel
              code={fs.code} setCode={fs.setCode} openedFilePath={fs.openedFilePath} isEditorFocused={isEditorFocused} setIsEditorFocused={setIsEditorFocused}
              workspacePath={fs.workspacePath} problems={flattenedProblems} diffFile={diffFile}
              apiUrl={API} sessionToken={auth.user?.sessionToken} openFile={fs.openFile}
            />
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-center p-8 relative overflow-hidden">
              {/* Marka renkli ambient zemin — hangi zekayla çalışıldığını hissettirir */}
              <div
                className="pointer-events-none absolute inset-0 transition-all duration-700"
                style={{ background: `radial-gradient(ellipse 55% 42% at 50% 36%, rgba(${brandRgb}, 0.06), transparent 70%)` }}
              />
              <div className="relative mb-8">
                <div
                  className="absolute inset-0 blur-[80px] rounded-full animate-pulse transition-colors duration-700"
                  style={{ backgroundColor: `rgba(${brandRgb}, 0.16)` }}
                />
                <Zap size={48} className="relative z-10 opacity-60 transition-colors duration-700" style={{ color: `rgb(${brandRgb})` }} />
              </div>
              <h2 className="text-2xl font-bold text-slate-100 mb-3 tracking-tight relative">UNITY ARCHITECT ENGINE</h2>
              <p className="text-slate-500 text-sm max-w-md leading-relaxed mb-8 relative">{t("home.editorHint")}</p>
              <div className="grid grid-cols-3 gap-3 max-w-lg w-full mb-10 relative">
                {[ {icon:<Activity size={14}/>, label: t('home.bugfix')}, {icon:<Code size={14}/>, label: t('home.codegen')}, {icon:<Layout size={14}/>, label: t('home.analyze')} ].map((item, i) => (
                  <div key={i} className="px-4 py-3 bg-white/[0.03] border border-white/[0.07] rounded-xl flex items-center justify-center gap-2 text-[11px] font-semibold text-slate-400 hover:bg-white/[0.06] hover:border-white/[0.12] hover:text-slate-200 transition-all cursor-default">
                    {item.icon} {item.label}
                  </div>
                ))}
              </div>
              {/* Son sohbetler — boş ekran gerçek bir karşılamaya dönüşsün */}
              {chat.conversations.length > 0 && (
                <div className="w-full max-w-lg relative">
                  <div className="text-[10px] uppercase tracking-widest text-slate-600 font-semibold mb-2 text-left">
                    {lang === 'tr' ? 'Son sohbetler' : 'Recent chats'}
                  </div>
                  <div className="space-y-1.5">
                    {chat.conversations.slice(0, 3).map((conv) => (
                      <button
                        key={conv.id}
                        onClick={() => { chat.selectConversation(conv); setIsChatOpen(true); }}
                        className="w-full flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl border border-white/[0.06] bg-white/[0.02] hover:bg-white/[0.05] hover:border-white/[0.1] text-left transition-colors group"
                      >
                        <MessageSquare size={13} className="text-slate-600 group-hover:text-slate-400 shrink-0 transition-colors" />
                        <span className="text-[12px] text-slate-400 group-hover:text-slate-200 truncate transition-colors">{conv.title}</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
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

      <motion.div animate={{ width: isChatOpen ? 450 : 0, opacity: isChatOpen ? 1 : 0 }} transition={{ duration: 0.2 }} className="bg-[#0B0D12] flex flex-col overflow-hidden shrink-0 border-l border-white/[0.06]">
        <div className="flex-1 relative flex flex-col min-h-0">
          {/* İmza: aktif modelin markası panelin tepesinden içeri süzülen ışık */}
          <div
            className="pointer-events-none absolute top-0 inset-x-0 h-36 transition-all duration-700"
            style={{ background: `linear-gradient(180deg, rgba(${brandRgb}, 0.05), transparent)` }}
          />
          <div className="h-12 border-b border-white/[0.06] flex items-center justify-between px-4 shrink-0 relative">
            <div className="flex items-center gap-2">
              <span
                className="w-1.5 h-1.5 rounded-full transition-colors duration-700"
                style={{ backgroundColor: `rgba(${brandRgb}, 0.9)` }}
              />
              <span className="text-[11px] font-bold text-slate-400 uppercase tracking-widest">Architect Copilot</span>
            </div>
            <button onClick={() => setIsChatOpen(false)} className="p-1 hover:bg-white/[0.06] rounded transition-all text-slate-500 hover:text-slate-300"><PanelRightClose size={16} /></button>
          </div>

          <div className="flex-1 overflow-y-auto custom-scrollbar relative">
            <ChatPanel 
              messages={chat.messages} activeConvId={chat.activeConvId} user={auth.user} loading={chat.loading} clearHistory={chat.clearHistory} lang={lang}
              effectiveProvider={ai.effectiveProvider}
              modelName={ai.aiConfig?.model_name}
              thinkingLevel={thinkingLevel} workspacePath={fs.workspacePath} handleExportToUnity={fs.handleExportToUnity}
              pendingGenFiles={fs.pendingGenFiles} setPendingGenFiles={fs.setPendingGenFiles} pendingFix={chat.pendingFix} setPendingFix={chat.setPendingFix} openedFilePath={fs.openedFilePath}
              setCode={fs.setCode} refreshFileTree={fs.refreshFileTree} analyzeProject={chat.analyzeProject} openFile={fs.openFile} sendMessage={handleSendMessage}
              currentPlan={chat.currentPlan} messagesEndRef={chatEndRef} ipc={ipc} showToast={showToast as any} diffFile={diffFile} setDiffFile={setDiffFile}
              pendingDelete={fs.pendingDelete} setPendingDelete={fs.setPendingDelete} pendingCommand={chat.pendingCommand} setPendingCommand={chat.setPendingCommand} onApproveCommand={chat.approveCommand} pendingQuestion={chat.pendingQuestion} setPendingQuestion={chat.setPendingQuestion} onAnswerQuestion={chat.answerQuestion} deleteFile={fs.deleteFile} setIsTerminalOpen={setIsTerminalOpen}
              activity={chat.activity}
            />
          </div>

          <div className="p-4 border-t border-white/[0.06] bg-white/[0.015] relative">
            <ControlPanel
              thinkingLevel={thinkingLevel} setThinkingLevel={setThinkingLevel} generationMode={chat.generationMode} setGenerationMode={chat.setGenerationMode}
              isAnalyzingProject={chat.isAnalyzingProject} activeConvId={chat.activeConvId} analyzeProject={chat.analyzeProject}
              exportMemory={chat.exportMemory} importMemory={chat.importMemory} compactConversation={chat.compactConversation} isCompacting={chat.isCompacting} contextUsage={chat.contextUsage}
              isClaudeSubscription={isClaudeSub} ultracode={ultracode} setUltracode={setUltracode} effortCaps={effortCaps}
            />
            <div className="mt-3">
              <AnimatedChatInput
                value={chat.chatInput} setValue={chat.setChatInput} onSendMessage={handleSendMessage} isLoading={chat.loading}
                slashCommands={slashCommands}
                skills={skills}
                commandMeta={commandMeta}
                galleryProvider={slashProvider}
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
