import React, { useState, useEffect, useRef } from 'react';
import Head from 'next/head';
import axios from 'axios';
import { motion, AnimatePresence } from 'framer-motion';
import {
  ChevronLeft,
  ChevronRight,
  Code2,
  Languages,
  Activity,
  X,
  PanelRightClose,
  PanelRightOpen,
} from "lucide-react";

import { AuthScreen } from '../components/home/AuthScreen';
import { WorkspaceScreen } from '../components/home/WorkspaceScreen';
import { SettingsModal } from '../components/home/SettingsModal';
import { ExportModal } from '../components/home/ExportModal';
import { Sidebar } from '../components/home/Sidebar';
import { EditorPanel } from '../components/home/EditorPanel';
import { ChatPanel } from '../components/home/ChatPanel';
import { ModelSelector } from '../components/home/ModelSelector';
import { ControlPanel } from '../components/home/ControlPanel';
import { ToastContainer } from "../components/ui/Toast";
import { AnimatedChatInput, ThinkingIndicator } from "../components/ui/animated-ai-chat";
import { TerminalPanel } from '../components/home/TerminalPanel';
import { Terminal as TerminalIcon } from 'lucide-react';

// Hooks
import { useAuth } from '../hooks/home/useAuth';
import { useAIConfig } from '../hooks/home/useAIConfig';
import { useFileSystem } from '../hooks/home/useFileSystem';
import { useChat } from '../hooks/home/useChat';
import { useAppInitialization } from '../hooks/home/useAppInitialization';

const ipc = typeof window !== 'undefined' ? (window as any).ipc : null;

const globalStyles = `
  @keyframes typing-bounce {
    0%, 80%, 100% { transform: translateY(0); opacity: 0.4; }
    40% { transform: translateY(-4px); opacity: 1; }
  }
  .typing-dot { animation: typing-bounce 1.4s infinite ease-in-out; }
  .typing-dot:nth-child(1) { animation-delay: 0s; }
  .typing-dot:nth-child(2) { animation-delay: 0.2s; }
  .typing-dot:nth-child(3) { animation-delay: 0.4s; }
`;

export default function HomePage() {
  const { API, backendReady, backendError, toasts, showToast, dismissToast } = useAppInitialization();
  const auth = useAuth(API, backendReady);
  const ai = useAIConfig(API, auth.user, showToast);
  const fs = useFileSystem(API, auth.user, showToast);

  // --- Diff Mode State (Must be before conditional returns) ---
  const [diffFile, setDiffFile] = useState<any | null>(null);

  const chat = useChat(
    API,
    auth.user,
    ai.aiConfig,
    fs.workspacePath,
    showToast,
    fs.refreshFileTree,
    fs.suggestFilePath
  );

  // --- Initial Loads ---
  useEffect(() => {
    if (backendReady && auth.user) {
      chat.fetchConversations(auth.user.id);
      ai.fetchAIConfig(auth.user.id);
      ai.fetchAvailableModels();
      fs.fetchLastWorkspace(auth.user.id);
      ai.fetchProvidersWithKeys(auth.user.id);
      auth.fetchAuthProviders();
    }
  }, [auth.user, backendReady]);

  // --- Session Restoration ---
  useEffect(() => {
    const restoreSession = async () => {
      if (!backendReady || !API) return;
      const token = ipc ? await ipc.invoke('session-get').catch(() => null) : null;
      if (token) auth.hydrateSession(token, true).catch(() => undefined);
    };
    restoreSession();
  }, [backendReady, API]);

  // --- UI State ---
  const [lang, setLang] = useState('tr');
  const [useThinking, setUseThinking] = useState(true);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [isChatOpen, setIsChatOpen] = useState(true);
  const [sidebarTab, setSidebarTab] = useState<'chats' | 'files'>('chats');
  const [isEditorFocused, setIsEditorFocused] = useState(false);
  const [isTerminalOpen, setIsTerminalOpen] = useState(false);
  const [problems, setProblems] = useState<any[]>([]);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const lintTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // --- Real-time Linting ---
  useEffect(() => {
    if (!API || !auth.user || !fs.openedFilePath || !fs.code.trim()) {
      if (!fs.code.trim()) setProblems([]);
      return;
    }

    if (lintTimeoutRef.current) clearTimeout(lintTimeoutRef.current);

    lintTimeoutRef.current = setTimeout(async () => {
      try {
        const res = await axios.post(`${API}/lint`, {
          code: fs.code,
          filename: fs.openedFilePath!.split('/').pop() || 'script.cs'
        }, {
          headers: { 'X-Session-Token': auth.user?.sessionToken }
        });
        if (res.data && res.data.errors) {
          setProblems(res.data.errors);
        }
      } catch (err) {
        console.error("Lint hatası:", err);
      }
    }, 2000); // 2 saniye debounce

    return () => {
      if (lintTimeoutRef.current) clearTimeout(lintTimeoutRef.current);
    };
  }, [fs.code, fs.openedFilePath, API, auth.user]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chat.messages, chat.loading]);

  // --- Global Menu Listeners ---
  useEffect(() => {
    if (!ipc) return;
    const unsubscribeToggle = ipc.on('menu-toggle-terminal', () => {
      setIsTerminalOpen(prev => !prev);
    });
    const unsubscribeOpen = ipc.on('menu-open-terminal', () => {
      setIsTerminalOpen(true);
    });
    return () => {
      unsubscribeToggle();
      unsubscribeOpen();
    };
  }, []);

  const handleLogout = () => {
    auth.performLogout();
    fs.closeWorkspace();
  };

  const handleSendMessage = async (msg?: string, images?: string[]) => {
    let input = (msg || chat.chatInput).trim();
    if (!input && (!images || images.length === 0)) return;

    // Eklenti dosyalarını kontrol et ( [File Attached: path] formatındakiler )
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
          } catch (err) {
            console.error("Dosya okuma hatası:", err);
            input = input.replace(match, `(Dosya okunamadı: ${path})`);
          }
        }
      }
    }

    chat.sendMessage(input, "", lang, chat.generationMode, useThinking, fs.setPendingGenFiles, fs.setPendingDelete, images);
  };

  if (backendError) {
    return (
      <div className="h-screen bg-black flex flex-col items-center justify-center text-center p-6">
        <div className="text-red-500 text-5xl mb-4">⚠</div>
        <h2 className="text-white text-xl font-bold mb-2">Backend Bağlantısı Başarısız</h2>
        <p className="text-slate-400 max-w-md">Arka plan servisi çalışmıyor veya erişilemez durumda. Lütfen uygulamayı yeniden başlatın.</p>
      </div>
    );
  }

  if (!auth.user) {
    return (
      <AuthScreen
        authMode={auth.authMode}
        notice={auth.authNotice}
        oauthProviders={auth.oauthProviders}
        onSubmit={(e) => auth.handleAuthSubmit(e, true)}
        onOAuth={auth.handleOAuth}
        onToggleMode={() => auth.setAuthMode(auth.authMode === 'login' ? 'register' : 'login')}
      />
    );
  }

  if (!fs.workspacePath) {
    return (
      <WorkspaceScreen
        userName={auth.user.name}
        lastWorkspacePath={fs.lastWorkspacePath}
        onOpenWorkspaceDialog={fs.openFolder}
        onSelectLastWorkspace={() => fs.selectWorkspace(fs.lastWorkspacePath!)}
        onLogout={handleLogout}
      />
    );
  }

  return (
    <div className="flex h-screen bg-[#000000] text-slate-200 font-sans overflow-hidden">
      <Head><title>Unity Architect AI | {auth.user.name}</title><style>{globalStyles}</style></Head>

      <SettingsModal
        open={ai.showSettings} aiConfig={ai.aiConfig} providersWithKeys={ai.providersWithKeys}
        onChange={ai.setAiConfig} onClose={() => ai.setShowSettings(false)} onSave={ai.saveAIConfig}
        onLogout={handleLogout} onDeleteKey={ai.deleteApiKey}
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
              <span className="text-[12px] font-semibold text-slate-400">{fs.openedFilePath ? fs.openedFilePath.split('/').pop() : 'C# Editor'}</span>
              {fs.openedFilePath && <button onClick={() => { fs.setOpenedFilePath(null); fs.setCode(''); }} className="p-0.5 hover:bg-slate-700 rounded text-slate-500"><X size={12} /></button>}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1.5 bg-[#000000] border border-slate-800 rounded-lg px-3 py-1.5">
              <Languages size={12} className="text-blue-500" />
              <select value={lang} onChange={(e) => setLang(e.target.value)} className="bg-transparent text-slate-300 text-[11px] font-medium outline-none">
                <option value="tr">TR</option>
                <option value="en">EN</option>
              </select>
            </div>
            <Activity size={14} className="text-emerald-500 animate-pulse" />
          </div>
        </div>

        <div className="flex-1 overflow-hidden relative flex flex-col bg-[#000000]">
          <EditorPanel
            code={fs.code} setCode={fs.setCode} openedFilePath={fs.openedFilePath}
            isEditorFocused={isEditorFocused} setIsEditorFocused={setIsEditorFocused}
            workspacePath={fs.workspacePath}
            problems={problems}
            diffFile={diffFile}
          />
        </div>
      </div>

      <motion.div animate={{ width: isChatOpen ? 420 : 0, opacity: isChatOpen ? 1 : 0 }} transition={{ duration: 0.2 }} className="bg-[#000000] flex flex-col overflow-hidden shrink-0">
        <div className="h-11 border-b border-slate-800/50 flex items-center justify-between px-4 min-w-[420px] shrink-0">
          <ModelSelector aiConfig={ai.aiConfig} setAiConfig={ai.setAiConfig} availableModels={ai.availableModels} providersWithKeys={ai.providersWithKeys} effectiveProvider={ai.effectiveProvider} displayModelName={ai.displayModelName} isModelDropdownOpen={ai.isModelDropdownOpen} setIsModelDropdownOpen={ai.setIsModelDropdownOpen} showMultiAgentInfo={ai.showMultiAgentInfo} setShowMultiAgentInfo={ai.setShowMultiAgentInfo} modelOrToggles={ai.modelOrToggles} setModelOrToggles={ai.setModelOrToggles} claudeModelForMA={ai.claudeModelForMA} maCoderProvider={ai.maCoderProvider} user={auth.user} fetchAvailableModels={ai.fetchAvailableModels} setShowSettings={ai.setShowSettings} API={API} axios={axios} showToast={showToast} />
        </div>

        <div className="flex-1 relative flex flex-col min-h-0 bg-[#000000]">
          <button onClick={() => setIsChatOpen(false)} className="p-1.5 hover:bg-slate-800 rounded-lg text-slate-500 transition-all absolute top-4 right-4 z-10">
            <PanelRightClose size={16} />
          </button>
          <div className="flex-1 overflow-y-auto custom-scrollbar p-4 space-y-4 min-w-[420px]">
            <ChatPanel
              messages={chat.messages} activeConvId={chat.activeConvId} user={auth.user} loading={chat.loading}
              clearHistory={chat.clearHistory} lang={lang} wisdomSummary={chat.wisdomSummary}
              isWisdomExpanded={chat.isWisdomExpanded} setIsWisdomExpanded={chat.setIsWisdomExpanded}
              effectiveProvider={ai.effectiveProvider} useThinking={useThinking} workspacePath={fs.workspacePath}
              handleExportToUnity={fs.handleExportToUnity} pendingPlan={chat.pendingPlan} setPendingPlan={chat.setPendingPlan}
              pendingGenFiles={fs.pendingGenFiles} setPendingGenFiles={fs.setPendingGenFiles}
              pendingFix={chat.pendingFix} setPendingFix={chat.setPendingFix}
              openedFilePath={fs.openedFilePath} setCode={fs.setCode} refreshFileTree={fs.refreshFileTree}
              analyzeProject={chat.analyzeProject} openFile={fs.openFile} sendMessage={handleSendMessage}
              onConfirmPlan={(msg, mode) => chat.confirmPlan(msg, mode, lang, fs.code, ai.gpt54OrToggled, fs.setPendingGenFiles, fs.setPendingDelete)}
              currentPlan={chat.currentPlan} messagesEndRef={chatEndRef} generationMode={chat.generationMode}
              appMode="auto" aiConfig={ai.aiConfig} gpt54OrToggled={ai.gpt54OrToggled} axios={axios}
              API={API} ipc={ipc} suggestFilePath={fs.suggestFilePath} showToast={showToast}
              diffFile={diffFile} setDiffFile={setDiffFile}
              pendingDelete={fs.pendingDelete} setPendingDelete={fs.setPendingDelete} deleteFile={fs.deleteFile}
              pendingCommand={chat.pendingCommand} setPendingCommand={chat.setPendingCommand}
              setIsTerminalOpen={setIsTerminalOpen}
            />
          </div>

          <div className="p-4 border-t border-slate-800/50 bg-[#000000]/80 backdrop-blur-md">
            <AnimatedChatInput value={chat.chatInput} setValue={chat.setChatInput} onSendMessage={handleSendMessage} onStop={chat.stopMessage} isLoading={chat.loading} placeholder={fs.code.trim() ? "Analiz et..." : "Sor..."} className="border-slate-800/50" />
            <ControlPanel useThinking={useThinking} setUseThinking={setUseThinking} generationMode={chat.generationMode} setGenerationMode={chat.setGenerationMode} isAnalyzingProject={chat.loading} activeConvId={chat.activeConvId} analyzeProject={chat.analyzeProject} wisdomSummary={chat.wisdomSummary} exportMemory={chat.exportMemory} importMemory={chat.importMemory} compactConversation={chat.compactConversation} isCompacting={chat.isCompacting} contextUsage={chat.contextUsage} />
          </div>
        </div>
        <AnimatePresence>{chat.loading && <ThinkingIndicator />}</AnimatePresence>
      </motion.div>

      {!isChatOpen && <button onClick={() => setIsChatOpen(true)} className="absolute right-3 top-3 p-2 bg-[#000000] border border-slate-800 rounded-lg text-slate-400 hover:text-blue-500 transition-all z-30"><PanelRightOpen size={16} /></button>}

      <TerminalPanel
        id="main-terminal"
        isOpen={isTerminalOpen}
        onClose={() => setIsTerminalOpen(false)}
        workspacePath={fs.workspacePath}
        problems={problems}
      />

      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </div>
  );
}
