import React, { useState, useEffect, useRef, useCallback } from 'react';
import Head from 'next/head';
import axios from 'axios';
import Editor from '@monaco-editor/react';
import { AnimatedChatInput, ThinkingIndicator } from "../components/ui/animated-ai-chat";
import { ToastContainer, useToast } from "../components/ui/Toast";
import {
  Activity,
  AlertTriangle,
  Bot,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronRight as ChevronR,
  Code2,
  Cpu,
  Database,
  Edit3,
  File as FileIcon,
  FileCode,
  Folder,
  FolderOpen,
  Languages,
  LogOut,
  MessageSquare,
  PanelRightClose,
  PanelRightOpen,
  Plus,
  Settings,
  Sparkles,
  Trash2,
  Upload,
  X,
  HelpCircle,
  Brain,
} from "lucide-react";
import { motion, AnimatePresence } from 'framer-motion';
import AgentPlan, { Task } from '../components/ui/agent-plan';
import { AuthScreen } from '../components/home/AuthScreen';
import { DiffViewer, DiffData } from '../components/home/DiffViewer';
import { FileCreationApproval, PendingFile } from '../components/home/FileCreationApproval';
import { ThinkingBlock } from '../components/home/ThinkingBlock';
import { ToolBlock } from '../components/home/ToolBlock';
import { GenerationModeSelector, GenerationMode } from '../components/home/GenerationModeSelector';
import { ExportModal } from '../components/home/ExportModal';
import { MarkdownRenderer } from '../components/home/MarkdownRenderer';
import { ModelAvatar } from '../components/home/ModelAvatar';
import { SettingsModal } from '../components/home/SettingsModal';
import { WorkspaceScreen } from '../components/home/WorkspaceScreen';
import { parseGeneratedFiles, splitCodeIntoFiles } from '../components/home/export-utils';
import { defineUnityTheme, THEME_NAME } from '../components/home/monaco-theme';
import { AIConfig, AvailableModels, Conversation, ExportModalState, FileEntry, Message, UserData } from '../components/home/types';

let API = '';

// IPC helper (Electron preload)
const ipc = typeof window !== 'undefined' ? (window as any).ipc : null;

const setSessionTokenHeader = (token: string | null) => {
  if (token) {
    axios.defaults.headers.common['X-Session-Token'] = token;
  } else {
    delete axios.defaults.headers.common['X-Session-Token'];
  }
};

export default function HomePage() {
  // --- AUTH ---
  const [user, setUser] = useState<UserData | null>(null);
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login');
  const [authForm, setAuthForm] = useState({ username: '', password: '' });
  const [authNotice, setAuthNotice] = useState<string | null>(null);

  // --- CONVERSATIONS ---
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConvId, setActiveConvId] = useState<number | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);

  // --- UI STATE ---
  const [code, setCode] = useState('');
  const [chatInput, setChatInput] = useState('');
  const [lang, setLang] = useState('tr');
  const [useThinking, setUseThinking] = useState(false);
  const [generationMode, setGenerationMode] = useState<GenerationMode>('auto');
  const [pendingPlan, setPendingPlan] = useState<{ content: string; originalMessage: string; mode: GenerationMode } | null>(null);
  const [loading, setLoading] = useState(false);
  const [backendReady, setBackendReady] = useState(false);
  const [backendError, setBackendError] = useState(false);
  const [currentPlan, setCurrentPlan] = useState<Task[]>([]);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [isChatOpen, setIsChatOpen] = useState(true);
  const [sidebarTab, setSidebarTab] = useState<'chats' | 'files'>('chats');
  const [isDragging, setIsDragging] = useState(false);
  const [dragRejectMsg, setDragRejectMsg] = useState('');
  const appMode = 'auto';
  const [isEditorFocused, setIsEditorFocused] = useState(false);
  const [includeEditorCode, setIncludeEditorCode] = useState(false);

  // --- WORKSPACE ---
  const [workspacePath, setWorkspacePath] = useState<string | null>(null);
  const [lastWorkspacePath, setLastWorkspacePath] = useState<string | null>(null);

  // --- FILE BROWSER ---
  const [rootFolderPath, setRootFolderPath] = useState<string | null>(null);
  const [fileTree, setFileTree] = useState<FileEntry[]>([]);
  const [expandedDirs, setExpandedDirs] = useState<Set<string>>(new Set());
  const [dirContents, setDirContents] = useState<Record<string, FileEntry[]>>({});
  const [openedFilePath, setOpenedFilePath] = useState<string | null>(null);

  // --- SETTINGS ---
  const [showSettings, setShowSettings] = useState(false);
  const [aiConfig, setAiConfig] = useState<AIConfig>({
    provider_type: 'kb', api_key: '', model_name: 'unity-kb-v1', use_multi_agent: true, force_claude_coder: false
  });

  // Aktif provider: multi-agent modda her zaman Claude (orchestrator), single-agent modda seçili provider
  const effectiveProvider = aiConfig.use_multi_agent ? 'anthropic' : aiConfig.provider_type;

  const [availableModels, setAvailableModels] = useState<AvailableModels>({ local: [], cloud: [] });
  const [oauthProviders, setOauthProviders] = useState({ google: false, github: false });
  const [isModelDropdownOpen, setIsModelDropdownOpen] = useState(false);
  // Her model için ayrı OpenRouter modu: { [modelId]: true/false }
  const [modelOrToggles, setModelOrToggles] = useState<Record<string, boolean>>({});
  const [providersWithKeys, setProvidersWithKeys] = useState<string[]>([]);

  // Multi-agent'ta Anthropic için kullanılacak gerçek Claude modeli
  // (aiConfig.model_name GPT gibi yanlış bir değer tutabilir — claude içermiyorsa opus'a düşer)
  const claudeModelForMA = aiConfig.model_name?.includes('claude')
    ? aiConfig.model_name
    : 'claude-opus-4-6';

  // Multi-agent'ta kodlama için hangi provider kullanılıyor
  // GPT-5.4'te OR toggle açıksa OpenRouter tercih edilir; kapalıysa OpenAI native öncelikli
  const gpt54OrToggled = modelOrToggles['gpt-5.4'] ?? false;
  const maCoderProvider =
    gpt54OrToggled && providersWithKeys.includes('openrouter') ? 'openrouter'
      : providersWithKeys.includes('openai') ? 'openai'
        : providersWithKeys.includes('openrouter') ? 'openrouter'
          : null;
  const [showMultiAgentInfo, setShowMultiAgentInfo] = useState(false);

  // Header'da gösterilecek model adı — yüklü model listesinden isim arar, bulamazsa ID gösterir
  const displayModelName = (() => {
    if (aiConfig.use_multi_agent) return 'Multi-Agent';
    if (!aiConfig.model_name) return 'Model Seçin';
    const found = availableModels.cloud.find(m =>
      m.id === aiConfig.model_name || m.openrouter_id === aiConfig.model_name
    );
    if (found) return found.name;
    // Fallback: openrouter prefix'ini sil (openai/gpt-5.4 → gpt-5.4)
    const name = aiConfig.model_name;
    if (name.includes('/')) return name.split('/').slice(1).join('/');
    return name;
  })();

  // --- EDITING ---
  const [editingId, setEditingId] = useState<number | null>(null);
  const [tempTitle, setTempTitle] = useState('');

  // --- EXPORT MODAL ---
  const [exportModal, setExportModal] = useState<ExportModalState | null>(null);
  const [exportFileName, setExportFileName] = useState('');

  // --- DIFF VIEWER (FIX pipeline) ---
  const [pendingFix, setPendingFix] = useState<{ data: DiffData; messageId?: number; applied?: boolean } | null>(null);

  // --- FILE CREATION APPROVAL (kod üretim pipeline) ---
  const [pendingGenFiles, setPendingGenFiles] = useState<{ files: PendingFile[]; messageId: number } | null>(null);

  // --- CONTEXT USAGE (Hafıza Barı) ---
  const [contextUsage, setContextUsage] = useState<{ percent: number; should_compact: boolean; message_count: number }>({ percent: 0, should_compact: false, message_count: 0 });
  const [isCompacting, setIsCompacting] = useState(false);

  // --- REFS ---
  const chatEndRef = useRef<HTMLDivElement>(null);
  const chatInputRef = useRef<HTMLTextAreaElement>(null);
  const userRef = useRef<UserData | null>(null);
  const authAlertShownRef = useRef(false);
  const errorAlertShownRef = useRef(false);

  // --- TOAST ---
  const { toasts, showToast, dismissToast } = useToast();

  const persistSessionToken = useCallback(async (sessionToken: string) => {
    const persisted = await ipc?.invoke('session-set', sessionToken).catch(() => false);
    if (persisted !== true) {
      showToast(
        "Oturum güvenli şekilde bu cihaza kaydedilemedi. Uygulamayı kapatırsanız tekrar giriş yapmanız gerekebilir.",
        'warning'
      );
      return false;
    }
    return true;
  }, [showToast]);

  const performLogout = (showMessage = false, message = "Oturumunuz sona erdi. Lütfen tekrar giriş yapın.") => {
    if (userRef.current?.sessionToken) {
      axios.post(`${API}/logout`).catch(() => undefined);
    }
    setUser(null);
    userRef.current = null;
    setSessionTokenHeader(null);
    ipc?.invoke('session-clear').catch(() => undefined);
    setWorkspacePath(null);
    setLastWorkspacePath(null);
    setRootFolderPath(null);
    setFileTree([]);
    setConversations([]);
    setMessages([]);
    setActiveConvId(null);
    setCode('');
    setAuthNotice(null);
    if (showMessage) {
      showToast(message, 'warning');
    }
  };

  // --- Auto scroll chat ---
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  useEffect(() => {
    userRef.current = user;
  }, [user]);

  useEffect(() => {
    const interceptorId = axios.interceptors.response.use(
      response => response,
      error => {
        const status = error?.response?.status;
        if (status === 401 && userRef.current) {
          if (!authAlertShownRef.current) {
            authAlertShownRef.current = true;
            performLogout(true);
            setTimeout(() => {
              authAlertShownRef.current = false;
            }, 1000);
          }
        } else if (status === 403) {
          if (!authAlertShownRef.current) {
            authAlertShownRef.current = true;
            showToast(error?.response?.data?.detail || "Bu işlem için yetkiniz yok.", 'warning');
            setTimeout(() => {
              authAlertShownRef.current = false;
            }, 1000);
          }
        } else if (!error?.response && userRef.current) {
          if (!errorAlertShownRef.current) {
            errorAlertShownRef.current = true;
            showToast("Sunucuya ulaşılamadı. Backend çalışıyor mu kontrol edin.", 'error');
            setTimeout(() => {
              errorAlertShownRef.current = false;
            }, 1000);
          }
        }

        return Promise.reject(error);
      }
    );

    return () => {
      axios.interceptors.response.eject(interceptorId);
    };
  }, []);

  useEffect(() => {
    const loadBackendBaseUrl = async () => {
      try {
        const baseUrl = ipc ? await ipc.invoke('get-backend-base-url') : '';
        if (!baseUrl || typeof baseUrl !== 'string') {
          throw new Error('Backend URL alınamadı.')
        }
        API = baseUrl;
        setBackendReady(true);
        await Promise.all([fetchAuthProviders(), fetchAvailableModels()]);
      } catch (err) {
        console.error("Backend URL alınamadı:", err);
        setBackendReady(false);
        setBackendError(true);
      }
    };

    loadBackendBaseUrl();
  }, [showToast]);

  // --- Session Persistence ---
  useEffect(() => {
    const restoreSession = async () => {
      if (!backendReady || !API) return;
      // Migration: eski localStorage session'ı safeStorage'a taşı
      const oldSaved = localStorage.getItem('unityArchitectUser');
      if (oldSaved) {
        try {
          const parsed = JSON.parse(oldSaved);
          if (parsed?.sessionToken) {
            await persistSessionToken(parsed.sessionToken);
          }
        } catch { }
        localStorage.removeItem('unityArchitectUser');
      }

      // safeStorage'dan session token oku
      const token: string | null = ipc ? await ipc.invoke('session-get').catch(() => null) : null;
      if (token) {
        hydrateSession(token, true).catch(() => undefined);
      }
    };
    restoreSession();
  }, [backendReady]);

  // --- Fetch on login ---
  useEffect(() => {
    if (backendReady && user) {
      fetchConversations(user.id);
      fetchAIConfig(user.id);
      fetchAvailableModels();
      fetchLastWorkspace(user.id);
      fetchProvidersWithKeys(user.id);
    }
  }, [user, backendReady]);

  // --- API CALLS ---
  const fetchConversations = async (userId: number) => {
    try {
      const res = await axios.get(`${API}/conversations/${userId}`);
      setConversations(res.data);
    } catch (err) { console.error("Sohbet listesi hatası:", err); }
  };

  const fetchMessages = async (convId: number) => {
    try {
      const res = await axios.get(`${API}/conversations/${convId}/messages`);
      setMessages(res.data);
    } catch (err) { console.error("Mesaj hatası:", err); }
  };

  const fetchAIConfig = async (userId: number) => {
    try {
      const res = await axios.get(`${API}/get-ai-config/${userId}`);
      if (res.data) {
        // Key'i UI'da gösterme — kasada güvenli duruyor
        setAiConfig({ ...res.data, api_key: '' });
      }
    } catch (err) { console.error("Config hatası:", err); }
  };

  const fetchProvidersWithKeys = async (userId: number) => {
    try {
      const res = await axios.get(`${API}/api-keys/${userId}`);
      if (res.data?.providers_with_keys) setProvidersWithKeys(res.data.providers_with_keys);
    } catch (err) { console.error("API keys hatası:", err); }
  };

  const fetchAvailableModels = async () => {
    try {
      const res = await axios.get(`${API}/available-models`);
      if (res.data) setAvailableModels(res.data);
    } catch (err) { console.error("Modeller alınamadı:", err); }
  };

  const fetchAuthProviders = async () => {
    try {
      const res = await axios.get(`${API}/auth/providers`);
      if (res.data) setOauthProviders({
        google: Boolean(res.data.google),
        github: Boolean(res.data.github),
      });
    } catch (err) {
      setOauthProviders({ google: false, github: false });
      console.error("OAuth provider bilgisi alınamadı:", err);
    }
  };

  const hydrateSession = useCallback(async (sessionToken: string, persistSession: boolean) => {
    setSessionTokenHeader(sessionToken);
    try {
      const res = await axios.get(`${API}/me`);
      const userData = {
        id: res.data.user_id,
        name: res.data.username,
        sessionToken,
      };
      setUser(userData);
      setAuthNotice(null);
      if (persistSession) {
        await persistSessionToken(sessionToken);
      } else {
        await ipc?.invoke('session-clear').catch(() => undefined);
      }
      return userData;
    } catch (err) {
      setSessionTokenHeader(null);
      ipc?.invoke('session-clear').catch(() => undefined);
      setUser(null);
      throw err;
    }
  }, [persistSessionToken]);

  // --- WORKSPACE FUNCTIONS ---
  const fetchLastWorkspace = async (userId: number) => {
    try {
      const res = await axios.get(`${API}/last-workspace/${userId}`);
      if (res.data?.path) setLastWorkspacePath(res.data.path);
    } catch (err) { console.error("Last workspace hatası:", err); }
  };

  const selectWorkspace = async (path: string) => {
    setWorkspacePath(path);
    setRootFolderPath(path);
    if (ipc) {
      const entries = await ipc.invoke('read-directory', path, path);
      setFileTree(entries || []);
    }
    setExpandedDirs(new Set());
    setDirContents({});
    setSidebarTab('files');
    if (user) {
      try { await axios.post(`${API}/save-workspace`, { user_id: user.id, path }); } catch { }
    }
  };

  const closeWorkspace = () => {
    setWorkspacePath(null);
    setRootFolderPath(null);
    setFileTree([]);
    setExpandedDirs(new Set());
    setDirContents({});
    setOpenedFilePath(null);
    setCode('');
  };

  const handleLogout = () => {
    performLogout(false);
  };

  const saveAIConfig = async () => {
    try {
      const configToSave = { ...aiConfig, user_id: user?.id };
      const isCloud = !['ollama', 'kb'].includes(configToSave.provider_type);

      if (!isCloud) {
        configToSave.api_key = '';
      }

      // Yeni key girilmişse kasaya kaydet
      if (configToSave.api_key && isCloud) {
        await axios.post(`${API}/api-keys/save`, {
          user_id: user?.id,
          provider_type: configToSave.provider_type,
          api_key: configToSave.api_key
        });
      }

      // Cloud provider ama ne yeni key var ne kasada key var → uyar
      if (isCloud && !configToSave.api_key && !providersWithKeys.includes(configToSave.provider_type)) {
        showToast(`${configToSave.provider_type} için API key girilmedi. Bu provider'ı kullanabilmek için bir API key girmelisiniz.`, 'warning');
        return;
      }

      await axios.post(`${API}/save-ai-config`, configToSave);
      setAiConfig({ ...aiConfig, api_key: '' }); // UI'da key gösterme
      if (user) await fetchProvidersWithKeys(user.id);
      showToast("Ayarlar kaydedildi!", 'success');
      setShowSettings(false);
    } catch (err) { showToast("Kaydedilemedi.", 'error'); }
  };

  const createNewConversation = async (preserveCode = false) => {
    if (!user) return;
    try {
      const fileName = openedFilePath ? openedFilePath.split('/').pop() : 'Yeni Sohbet';
      const res = await axios.post(`${API}/conversations`, { user_id: user.id, title: fileName });
      await fetchConversations(user.id);
      setActiveConvId(res.data.id);
      setMessages([]);
      if (!preserveCode) {
        setCode('');
        setOpenedFilePath(null);
      }
      return res.data.id;
    } catch (err) { console.error("Yeni sohbet hatası:", err); }
  };

  const selectConversation = async (conv: Conversation) => {
    if (editingId) return;
    setActiveConvId(conv.id);
    setContextUsage({ percent: 0, should_compact: false, message_count: 0 });
    await fetchMessages(conv.id);
  };

  const deleteConversation = async (e: React.MouseEvent, convId: number) => {
    e.stopPropagation();
    if (confirm("Bu sohbet silinsin mi?")) {
      await axios.delete(`${API}/conversations/${convId}`);
      if (activeConvId === convId) {
        setActiveConvId(null);
        setMessages([]);
      }
      fetchConversations(user!.id);
    }
  };

  const saveRename = async (convId: number) => {
    if (!tempTitle.trim()) { setEditingId(null); return; }
    await axios.put(`${API}/conversations/${convId}`, { title: tempTitle });
    setEditingId(null);
    fetchConversations(user!.id);
  };

  // ===================== DOSYA İŞLEMLERİ =====================
  const openFolder = async () => {
    if (!ipc) return;
    const folderPath = await ipc.invoke('open-folder-dialog');
    if (folderPath) {
      await selectWorkspace(folderPath);
    }
  };

  const openFilePicker = async () => {
    if (!ipc) return;
    const result = await ipc.invoke('open-file-dialog');
    if (result) {
      setCode(result.content);
      setOpenedFilePath(result.path);
    }
  };

  const toggleDir = async (dirPath: string) => {
    const next = new Set(expandedDirs);
    if (next.has(dirPath)) {
      next.delete(dirPath);
    } else {
      next.add(dirPath);
      if (!dirContents[dirPath]) {
        const entries = await ipc.invoke('read-directory', dirPath, workspacePath);
        setDirContents(prev => ({ ...prev, [dirPath]: entries || [] }));
      }
    }
    setExpandedDirs(next);
  };

  const openFile = async (filePath: string) => {
    if (!ipc) return;
    const result = await ipc.invoke('read-file', filePath, workspacePath);
    if (result) {
      setCode(result.content);
      setOpenedFilePath(result.path);
    }
  };

  // Sürükle-bırak
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    const files = e.dataTransfer.files;
    if (files.length > 0) {
      const file = files[0];
      if (!file.name.endsWith('.cs')) {
        setDragRejectMsg('Lütfen sadece C# (.cs) dosyası sürükleyin');
        setTimeout(() => setDragRejectMsg(''), 2500);
        return;
      }
      const text = await file.text();
      setCode(text);
      setOpenedFilePath(file.name);
    }
  };

  const getFileIcon = (ext: string) => {
    if (['cs', 'txt', 'md', 'json'].includes(ext)) return <FileCode size={13} className="text-blue-400" />;
    return <FileIcon size={13} className="text-slate-500" />;
  };

  const renderTree = (entries: FileEntry[], depth = 0): React.ReactNode => {
    return entries.map(entry => (
      <div key={entry.path}>
        <div
          onClick={() => entry.isDirectory ? toggleDir(entry.path) : openFile(entry.path)}
          className={`flex items-center gap-1.5 px-2 py-1 rounded cursor-pointer text-[12px] hover:bg-slate-800/40 transition-colors ${openedFilePath === entry.path ? 'bg-slate-800/60 text-white' : 'text-slate-400'
            }`}
          style={{ paddingLeft: `${8 + depth * 14}px` }}
        >
          {entry.isDirectory ? (
            <>
              <ChevronR size={11} className={`transition-transform ${expandedDirs.has(entry.path) ? 'rotate-90' : ''}`} />
              {expandedDirs.has(entry.path)
                ? <FolderOpen size={13} className="text-blue-400" />
                : <Folder size={13} className="text-slate-500" />}
            </>
          ) : getFileIcon(entry.extension)}
          <span className="truncate">{entry.name}</span>
        </div>
        {entry.isDirectory && expandedDirs.has(entry.path) && dirContents[entry.path] && (
          renderTree(dirContents[entry.path], depth + 1)
        )}
      </div>
    ));
  };

  // ===================== UNITY EXPORT FONKSİYONLARI =====================

  const checkFileExists = async (filePath: string): Promise<boolean> => {
    if (!ipc || !workspacePath) return false;
    try {
      const result = await ipc.invoke('file-exists', filePath, workspacePath);
      return result === true;
    } catch { return false; }
  };

  const handleExportToUnity = useCallback(async (codeString: string) => {
    if (!workspacePath) return;
    const targetDir = `${workspacePath}/Assets/Scripts`;

    // Sınıf adını regex ile bul
    const classMatch = codeString.match(/class\s+(\w+)/);
    const className = classMatch ? classMatch[1] : 'NewScript';
    const suggestedName = `${className}.cs`;

    // Çoklu sınıf kontrolü
    const allClasses = [...codeString.matchAll(/class\s+(\w+)/g)];

    if (allClasses.length > 1) {
      // Çoklu dosya modu
      const files = splitCodeIntoFiles(codeString, workspacePath);
      setExportFileName(suggestedName);
      setExportModal({
        isOpen: true,
        codeString,
        suggestedName,
        targetDir,
        existingFile: false,
        multiFile: true,
        files,
        exportResult: null,
      });
    } else {
      // Tek dosya modu
      const targetPath = `${targetDir}/${suggestedName}`;
      const exists = await checkFileExists(targetPath);
      setExportFileName(suggestedName);
      setExportModal({
        isOpen: true,
        codeString,
        suggestedName,
        targetDir,
        existingFile: exists,
        multiFile: false,
        files: [{ name: suggestedName, code: codeString, path: targetPath }],
        exportResult: null,
      });
    }
  }, [workspacePath]);

  // Workspace tree'ye bakarak dosya için en uygun path'i öner
  const suggestFilePath = (fileName: string): string => {
    if (!workspacePath) return fileName;
    const base = `${workspacePath}/Assets/Scripts`;
    if (!fileTree || fileTree.length === 0) return `${base}/${fileName}`;

    // Mevcut .cs dosyalarının bulunduğu klasörleri topla
    const csDirs: Record<string, number> = {};
    const collectDirs = (entries: typeof fileTree) => {
      for (const e of entries) {
        if (!e.isDirectory && e.extension === '.cs') {
          const dir = e.path.substring(0, e.path.lastIndexOf('/'));
          csDirs[dir] = (csDirs[dir] || 0) + 1;
        }
      }
    };
    collectDirs(fileTree);

    // Dosya adıyla semantik eşleşme (örn. EnemyAI.cs → Enemy klasörü)
    const nameLower = fileName.replace('.cs', '').toLowerCase();
    for (const dir of Object.keys(csDirs)) {
      const dirName = dir.split('/').pop()?.toLowerCase() || '';
      if (nameLower.includes(dirName) || dirName.includes(nameLower.slice(0, 4))) {
        return `${dir}/${fileName}`;
      }
    }

    // En çok .cs dosyası olan klasörü seç
    const topDir = Object.entries(csDirs).sort((a, b) => b[1] - a[1])[0]?.[0];
    return topDir ? `${topDir}/${fileName}` : `${base}/${fileName}`;
  };

  const exportSingleFile = async (fileName: string, content: string) => {
    if (!ipc || !exportModal || !workspacePath) return;
    const filePath = `${exportModal.targetDir}/${fileName}`;
    const result = await ipc.invoke('write-file', filePath, content, workspacePath);
    if (result?.success) {
      setExportModal(prev => prev ? {
        ...prev,
        exportResult: { success: true, message: `✅ ${fileName} başarıyla oluşturuldu!` }
      } : null);
      // Dosya ağacını yenile
      refreshFileTree();
    } else {
      setExportModal(prev => prev ? {
        ...prev,
        exportResult: { success: false, message: `❌ Hata: ${result?.error || 'Bilinmeyen hata'}` }
      } : null);
    }
  };

  const exportMultipleFiles = async () => {
    if (!ipc || !exportModal || !workspacePath) return;
    const filesToWrite = exportModal.files.map(f => ({ path: f.path, content: f.code }));
    const results = await ipc.invoke('write-multiple-files', filesToWrite, workspacePath);
    const successCount = results.filter((r: any) => r.success).length;
    const failCount = results.filter((r: any) => !r.success).length;

    let message = `✅ ${successCount} dosya başarıyla oluşturuldu!`;
    if (failCount > 0) {
      const errors = results.filter((r: any) => !r.success).map((r: any) => r.error).join(', ');
      message += `\n❌ ${failCount} dosya yazılamadı: ${errors}`;
    }

    setExportModal(prev => prev ? {
      ...prev,
      exportResult: { success: failCount === 0, message }
    } : null);
    refreshFileTree();
  };

  const refreshFileTree = async () => {
    if (!ipc || !workspacePath) return;
    const entries = await ipc.invoke('read-directory', workspacePath, workspacePath);
    setFileTree(entries || []);
    // Genişletilmiş dizinleri de yenile
    const newDirContents = { ...dirContents };
    for (const dir of expandedDirs) {
      try {
        const dirEntries = await ipc.invoke('read-directory', dir, workspacePath);
        newDirContents[dir] = dirEntries || [];
      } catch { }
    }
    setDirContents(newDirContents);
  };

  const changeExportDir = async () => {
    if (!ipc || !exportModal) return;
    const folderPath = await ipc.invoke('open-folder-dialog');
    if (folderPath) {
      // Dosya path'lerini yeni dizine göre güncelle
      const updatedFiles = exportModal.files.map(f => ({
        ...f,
        path: `${folderPath}/${f.name}`
      }));
      setExportModal(prev => prev ? {
        ...prev,
        targetDir: folderPath,
        files: updatedFiles,
      } : null);
    }
  };

  const sendMessage = async (overrideMessage?: string) => {
    const inputToUse = (overrideMessage || chatInput).trim();
    if (!inputToUse || !user) return;

    // Key kontrolü: cloud provider seçili ama key yoksa gönderme
    const activeProvider = aiConfig.use_multi_agent ? 'anthropic' : aiConfig.provider_type;
    const cloudProviders = ['anthropic', 'google', 'openai', 'deepseek', 'groq', 'openrouter', 'moonshot'];
    if (cloudProviders.includes(activeProvider) && !providersWithKeys.includes(activeProvider)) {
      const providerLabel = activeProvider.charAt(0).toUpperCase() + activeProvider.slice(1);
      showToast(`${providerLabel} için API key girilmedi. Ayarlar'dan key ekleyin.`, 'warning');
      setShowSettings(true);
      return;
    }

    // Eğer aktif sohbet yoksa yeni bir tane oluştur ve devam et
    let targetConvId = activeConvId;
    if (!targetConvId) {
      const newConvId = await createNewConversation();
      if (!newConvId) return;
      targetConvId = newConvId;
    }

    // Kodu manuel olarak attach etme mantığı
    const shouldIncludeCode = includeEditorCode && code.trim();
    const messageContent = shouldIncludeCode
      ? `${inputToUse}\n\n\`\`\`csharp\n${code}\n\`\`\``
      : inputToUse;

    // Kodu gönderdikten sonra toggle'ı kapat, böylece sonraki sohbete otomatik yapışmasın
    if (includeEditorCode) setIncludeEditorCode(false);

    // Optimistic UI: kullanıcı mesajını hemen göster
    const userMsg: Message = {
      id: Date.now(),
      role: 'user',
      content: messageContent,
      smells: [],
      timestamp: new Date().toISOString()
    };
    setMessages(prev => [...prev, userMsg]);
    setChatInput('');
    setLoading(true);
    setCurrentPlan([]);

    // SSE Streaming ile mesajı gönder
    const aiMsgId = Date.now() + 1;
    let currentAiMsg: Message = {
      id: aiMsgId,
      role: 'assistant',
      content: '',
      smells: [],
      timestamp: new Date().toISOString(),
      thinking: null,
      tool_calls: [],
    };

    // AI mesajını ekrana boş olarak ekle (yavaş yavaş dolacak)
    setMessages(prev => [...prev, currentAiMsg]);

    try {
      const response = await fetch(`${API}/chat-stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Session-Token': user.sessionToken,
        },
        body: JSON.stringify({
          conversation_id: targetConvId,
          message: messageContent,
          language: lang,
          user_id: user.id,
          mode: appMode,
          use_kb: aiConfig.provider_type === 'kb',
          use_or_for_coder: gpt54OrToggled,
          editor_code: code || '',
          use_thinking: useThinking,
          generation_mode: generationMode,
          generation_confirmed: false,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      // Bağlantı kuruldu, akış başladı. Geçici yükleme animasyonunu kaldır.
      setLoading(false);

      const reader = response.body?.getReader();
      const decoder = new TextDecoder('utf-8');

      if (reader) {
        let buffer = '';
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n\n');
          buffer = lines.pop() || ''; // Son tamamlanmamış parçayı buffer'da bırak

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6));

                // SSE Event İşleme
                setMessages(prevMessages => {
                  return prevMessages.map(msg => {
                    if (msg.id === aiMsgId) {
                      const updatedMsg = { ...msg };

                      if (data.type === 'thinking') {
                        updatedMsg.thinking = (updatedMsg.thinking || '') + (data.text || '');
                        if (data.duration_ms) updatedMsg.thinking_duration_ms = data.duration_ms;
                      }
                      else if (data.type === 'tool_call') {
                        if (!updatedMsg.tool_calls) updatedMsg.tool_calls = [];
                        updatedMsg.tool_calls.push({
                          tool: data.tool,
                          args: data.arguments,
                        });
                      }
                      else if (data.type === 'tool_result') {
                        if (updatedMsg.tool_calls && updatedMsg.tool_calls.length > 0) {
                          // En son eklenen tool'u bul ve sonucunu yaz
                          const lastTool = updatedMsg.tool_calls[updatedMsg.tool_calls.length - 1];
                          if (lastTool.tool === data.tool) {
                            lastTool.summary = data.summary;
                            lastTool.success = data.success;
                          }
                        }
                      }
                      else if (data.type === 'text' || data.type === 'response') {
                        updatedMsg.content += data.content;
                      }

                      currentAiMsg = updatedMsg;
                      return updatedMsg;
                    }
                    return msg;
                  });
                });

                // Context Usage İşleme
                if (data.type === 'context_usage') {
                  setContextUsage({
                    percent: data.percent,
                    should_compact: data.should_compact,
                    message_count: data.message_count
                  });
                }

                // Kod üretim kontrolü (Final response sonrası)
                if (data.type === 'done' || data.type === 'response') {
                  // Final içeriği garantilemek için state dışındaki biriken içeriği kullanabiliriz
                  // Veya mevcutta biriken içeriği parametre olarak alabiliriz
                  const finalContent = currentAiMsg?.content || "";
                  if (workspacePath && finalContent) {
                    const parsed = parseGeneratedFiles(finalContent);
                    if (parsed.length > 0) {
                      // Dosyaları hazırla ve eski hallerini (diff için) oku
                      const prepareFiles = async () => {
                        const withPaths: PendingFile[] = [];
                        for (const f of parsed) {
                          const suggestedPath = f.path || suggestFilePath(f.name);
                          let originalCode = "";
                          if (ipc) {
                            try {
                              // Dosya varsa eski içeriğini oku
                              const res = await ipc.invoke('read-file', suggestedPath, workspacePath);
                              originalCode = res ? res.content : null;
                            } catch (err) {
                              // Dosya yoksa boş string (yeni dosya)
                              originalCode = "";
                            }
                          }
                          withPaths.push({
                            name: f.name,
                            code: f.code,
                            suggestedPath: suggestedPath,
                            originalCode: originalCode
                          });
                        }

                        if (generationMode === 'auto' && ipc) {
                          // Otomatik modda dosyaları yaz ama özeti göster
                          for (const file of withPaths) {
                            await ipc.invoke('write-file', file.suggestedPath, file.code, workspacePath);
                          }
                          showToast(`✅ ${withPaths.length} dosya güncellendi.`, 'success');
                          refreshFileTree();
                          setPendingGenFiles({ files: withPaths, messageId: aiMsgId });
                        } else {
                          // Adım adım modda sadece listeye ekle
                          setPendingGenFiles({ files: withPaths, messageId: aiMsgId });
                        }
                      };
                      prepareFiles();
                    }
                  }
                }

              } catch (err) {
                console.error("SSE parse hatası:", err, line);
              }
            }
          }
        }
      }

      fetchConversations(user.id);
    } catch (err: any) {
      const errorMsg: Message = {
        id: Date.now() + 1,
        role: 'assistant',
        content: '❌ Bir hata oluştu veya bağlantı koptu. Backend çalışıyor mu kontrol edin.',
        smells: [],
        timestamp: new Date().toISOString()
      };
      setMessages(prev => [...prev, errorMsg]);
    }
    setLoading(false);
  };

  const compactConversation = async () => {
    if (!activeConvId || isCompacting) return;
    setIsCompacting(true);
    try {
      const res = await axios.post(`${API}/conversations/${activeConvId}/compact`);
      if (res.data.status === 'success') {
        // Mesajları yeniden yükle (artık sadece özet mesajı olacak)
        const msgRes = await axios.get(`${API}/conversations/${activeConvId}/messages`);
        setMessages(msgRes.data.map((m: any) => ({
          id: m.id,
          role: m.role,
          content: m.content,
          smells: m.smells || [],
          timestamp: m.timestamp,
        })));
        setContextUsage({ percent: 5, should_compact: false, message_count: 1 });
        showToast('Sohbet özetlendi! Hafıza korunarak temiz bir sayfadan devam ediyorsun.', 'success');
      } else {
        showToast(res.data.reason || 'Özetlenemedi.', 'warning');
      }
    } catch {
      showToast('Özetleme sırasında hata oluştu.', 'error');
    }
    setIsCompacting(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  // =====================================================================
  //                        GİRİŞ EKRANI (NEW MODERN UI)
  // =====================================================================
  if (backendError) {
    return (
      <div className="h-screen bg-[#000000] flex items-center justify-center">
        <div className="text-center max-w-md px-6">
          <div className="text-red-500 text-5xl mb-6">⚠</div>
          <h2 className="text-white text-xl font-semibold mb-3">Uygulama başlatılamadı</h2>
          <p className="text-slate-400 text-sm mb-6">
            Arka plan servisi çalışmıyor. Uygulamayı kapatıp yeniden açmayı deneyin.
            Sorun devam ederse lütfen destek ile iletişime geçin.
          </p>
          <button
            onClick={() => { if (typeof window !== 'undefined') window.location.reload(); }}
            className="px-5 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-sm rounded-lg transition-colors"
          >
            Yeniden Dene
          </button>
        </div>
      </div>
    );
  }

  if (!user) {
    const handleAuthSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      const formData = new FormData(event.currentTarget);
      const username = formData.get('username') as string;
      const password = formData.get('password') as string;
      const rememberMe = formData.get('rememberMe') === 'on';

      if (!username || !password) {
        setAuthNotice("Kullanıcı adı ve şifre alanlarını doldurun.");
        return;
      }

      if (!backendReady || !API) {
        setAuthNotice("Backend henüz hazır değil. Lütfen birkaç saniye sonra tekrar deneyin.");
        return;
      }

      setAuthForm({ username, password });
      setAuthNotice(null);

      const url = authMode === 'login' ? '/login' : '/register';
      try {
        const res = await axios.post(`${API}${url}`, { username, password });
        if (authMode === 'login') {
          await hydrateSession(res.data.session_token, rememberMe);
        } else {
          setAuthNotice("Kayıt oluşturuldu. Şimdi giriş yapabilirsiniz.");
          setAuthMode('login');
        }
      } catch (err: any) {
        const status = err?.response?.status;
        if (status === 429) {
          setAuthNotice("Çok fazla giriş denemesi yapıldı. Lütfen kısa bir süre sonra tekrar deneyin.");
        } else if (authMode === 'login') {
          setAuthNotice("Giriş yapılamadı. Bilgilerinizi kontrol edip tekrar deneyin.");
        } else {
          setAuthNotice("Kayıt işlemi tamamlanamadı. Bilgilerinizi kontrol edip tekrar deneyin.");
        }
      }
    };

    const handleOAuth = async (provider: 'google' | 'github') => {
      setAuthNotice(null);
      if (!backendReady || !API) {
        setAuthNotice("Backend henüz hazır değil. Lütfen birkaç saniye sonra tekrar deneyin.");
        return;
      }
      try {
        const res = await axios.get(`${API}/auth/${provider}/url`);
        const oauthUrl = res.data.url;
        const popup = window.open(oauthUrl, `${provider}_oauth`, 'width=500,height=700,menubar=no,toolbar=no');
        if (!popup) {
          setAuthNotice("Harici giriş penceresi açılamadı. Tarayıcı engeli olup olmadığını kontrol edin.");
          return;
        }

        const handler = (event: MessageEvent) => {
          if (event.origin !== API || event.source !== popup) {
            return;
          }

          if (event.data?.type === 'oauth-complete' && typeof event.data.code === 'string') {
            window.removeEventListener('message', handler);
            axios.post(`${API}/auth/complete/${event.data.code}`)
              .then(async (completeRes) => {
                await hydrateSession(completeRes.data.session_token, true);
              })
              .catch(() => {
                setAuthNotice("Harici giriş işlemi tamamlanamadı. Lütfen tekrar deneyin.");
              });
          } else if (event.data?.type === 'oauth-error') {
            setAuthNotice("Harici giriş işlemi tamamlanamadı. Lütfen tekrar deneyin.");
            window.removeEventListener('message', handler);
          }
        };
        window.addEventListener('message', handler);

        const checkClosed = setInterval(() => {
          if (popup?.closed) {
            clearInterval(checkClosed);
            window.removeEventListener('message', handler);
          }
        }, 1000);

      } catch (err: any) {
        setAuthNotice("Harici giriş şu anda başlatılamıyor. Lütfen daha sonra tekrar deneyin.");
      }
    };

    return (
      <AuthScreen
        authMode={authMode}
        notice={authNotice}
        oauthProviders={oauthProviders}
        onSubmit={handleAuthSubmit}
        onOAuth={handleOAuth}
        onToggleMode={() => {
          setAuthNotice(null);
          setAuthMode(authMode === 'login' ? 'register' : 'login');
        }}
      />
    );
  }

  // =====================================================================
  //                   WORKSPACE SEÇİM EKRANI
  // =====================================================================
  if (!workspacePath) {
    const openWorkspaceDialog = async () => {
      if (!ipc) return;
      const folderPath = await ipc.invoke('open-folder-dialog');
      if (folderPath) {
        await selectWorkspace(folderPath);
      }
    };

    return (
      <WorkspaceScreen
        userName={user.name}
        lastWorkspacePath={lastWorkspacePath}
        onOpenWorkspaceDialog={openWorkspaceDialog}
        onSelectLastWorkspace={() => selectWorkspace(lastWorkspacePath!)}
        onLogout={handleLogout}
      />
    );
  }

  // =====================================================================
  //                       ANA UYGULAMA
  // =====================================================================
  return (
    <div className="flex h-screen bg-[#000000] text-slate-200 font-sans overflow-hidden">
      <Head><title>Unity Architect AI | {user.name}</title></Head>

      <SettingsModal
        open={showSettings}
        aiConfig={aiConfig}
        providersWithKeys={providersWithKeys}
        onChange={setAiConfig}
        onClose={() => setShowSettings(false)}
        onSave={saveAIConfig}
        onLogout={() => {
          setShowSettings(false);
          handleLogout();
        }}
        onDeleteKey={async (provider) => {
          if (!window.confirm(`"${provider}" API key'i silmek istediğinize emin misiniz?\n\nBu işlem geri alınamaz.`)) return;
          try {
            await axios.delete(`${API}/api-keys/${user.id}/${provider}`);
            await fetchProvidersWithKeys(user.id);
            setAiConfig(prev => ({ ...prev, api_key: '' }));
          } catch (err) {
            showToast('Key silinirken bir hata oluştu.', 'error');
          }
        }}
      />

      <ExportModal
        exportModal={exportModal}
        exportFileName={exportFileName}
        workspacePath={workspacePath}
        onFileNameChange={setExportFileName}
        onClose={() => setExportModal(null)}
        onChangeExportDir={changeExportDir}
        onExportSingleFile={exportSingleFile}
        onExportMultipleFiles={exportMultipleFiles}
      />

      {/* =================== SOL SIDEBAR =================== */}
      <motion.aside
        animate={{ width: isSidebarOpen ? 260 : 0, opacity: isSidebarOpen ? 1 : 0 }}
        transition={{ duration: 0.2 }}
        className="bg-[#000000] border-r border-slate-800/50 flex flex-col overflow-hidden z-20 shrink-0"
      >
        {/* Workspace Header */}
        <div className="flex items-center justify-between px-3 py-2 border-b border-slate-800/50 min-w-[260px] bg-[#000000]">
          <div className="flex items-center gap-2 flex-1 min-w-0">
            <Folder size={13} className="text-blue-500 shrink-0" />
            <span className="text-[11px] text-slate-300 font-medium truncate">
              {workspacePath?.split('/').pop() || 'Workspace'}
            </span>
          </div>
          <button
            onClick={closeWorkspace}
            className="p-1 hover:bg-red-900/30 rounded text-slate-600 hover:text-red-400 transition-all"
            title="Çalışma alanını kapat"
          >
            <X size={13} />
          </button>
        </div>

        {/* Sidebar Tabs */}
        <div className="flex border-b border-slate-800/50 min-w-[260px]">
          <button
            onClick={() => setSidebarTab('chats')}
            className={`flex-1 py-2.5 text-[10px] font-semibold tracking-wider uppercase transition-colors ${sidebarTab === 'chats' ? 'text-blue-500 border-b-2 border-blue-500' : 'text-slate-500 hover:text-slate-300'
              }`}
          >
            Sohbetler
          </button>
          <button
            onClick={() => setSidebarTab('files')}
            className={`flex-1 py-2.5 text-[10px] font-semibold tracking-wider uppercase transition-colors ${sidebarTab === 'files' ? 'text-blue-500 border-b-2 border-blue-500' : 'text-slate-500 hover:text-slate-300'
              }`}
          >
            Dosyalar
          </button>
        </div>

        {/* Tab İçerikleri */}
        <div className="flex-1 overflow-y-auto custom-scrollbar min-w-[260px]">
          {sidebarTab === 'chats' ? (
            /* ====== SOHBET LİSTESİ ====== */
            <div className="p-1.5 space-y-0.5">
              <button
                onClick={() => createNewConversation()}
                className="w-full flex items-center gap-2 px-3 py-2 text-[11px] text-blue-500 hover:bg-blue-600/10 rounded-lg transition-all font-medium"
              >
                <Plus size={14} /> Yeni Sohbet
              </button>
              {conversations.map((conv) => (
                <div
                  key={conv.id}
                  onClick={() => selectConversation(conv)}
                  className={`group relative px-3 py-2.5 rounded-lg transition-all cursor-pointer ${activeConvId === conv.id
                    ? 'bg-slate-800/60 text-white'
                    : 'text-slate-400 hover:bg-slate-800/30 hover:text-slate-200'
                    }`}
                >
                  <div className="flex items-center gap-2.5">
                    <MessageSquare size={14} className={activeConvId === conv.id ? "text-blue-500" : "text-slate-600"} />
                    <div className="flex-1 overflow-hidden pr-6">
                      {editingId === conv.id ? (
                        <input
                          autoFocus
                          style={{ backgroundColor: '#000000', color: 'white' }}
                          className="bg-[#000000] text-white text-xs w-full px-2 py-1 rounded border border-blue-500 outline-none"
                          value={tempTitle}
                          onChange={e => setTempTitle(e.target.value)}
                          onBlur={() => saveRename(conv.id)}
                          onKeyDown={e => e.key === 'Enter' && saveRename(conv.id)}
                          onClick={e => e.stopPropagation()}
                        />
                      ) : (
                        <div className="text-[13px] font-medium truncate">{conv.title}</div>
                      )}
                    </div>
                  </div>
                  {editingId !== conv.id && (
                    <div className="absolute right-1.5 top-2 flex gap-0.5 opacity-0 group-hover:opacity-100 transition-all">
                      <button
                        onClick={(e) => { e.stopPropagation(); setEditingId(conv.id); setTempTitle(conv.title); }}
                        className="p-1 hover:bg-slate-700 rounded text-slate-500 hover:text-slate-300"
                      >
                        <Edit3 size={11} />
                      </button>
                      <button
                        onClick={(e) => deleteConversation(e, conv.id)}
                        className="p-1 hover:bg-red-900/30 rounded text-slate-500 hover:text-red-400"
                      >
                        <Trash2 size={11} />
                      </button>
                    </div>
                  )}
                </div>
              ))}
              {conversations.length === 0 && (
                <div className="text-center py-8 text-slate-600">
                  <MessageSquare size={24} className="mx-auto mb-2 opacity-30" />
                  <p className="text-[11px]">Henüz sohbet yok</p>
                </div>
              )}
            </div>
          ) : (
            /* ====== DOSYA GEZGİNİ ====== */
            <div className="p-1.5">
              <div className="flex gap-1 mb-2">
                <button
                  onClick={openFolder}
                  className="flex-1 flex items-center justify-center gap-1.5 px-2 py-2 text-[10px] text-blue-500 hover:bg-blue-600/10 rounded-lg transition-all font-semibold"
                >
                  <FolderOpen size={13} /> Klasör Aç
                </button>
                <button
                  onClick={openFilePicker}
                  className="flex-1 flex items-center justify-center gap-1.5 px-2 py-2 text-[10px] text-emerald-500 hover:bg-emerald-600/10 rounded-lg transition-all font-semibold"
                >
                  <FileIcon size={13} /> Dosya Aç
                </button>
              </div>
              {rootFolderPath ? (
                <div>
                  <div className="px-2 py-1.5 text-[9px] font-bold text-slate-500 uppercase tracking-wider truncate mb-1">
                    {rootFolderPath.split('/').pop()}
                  </div>
                  {renderTree(fileTree)}
                </div>
              ) : (
                <div className="text-center py-8 text-slate-600">
                  <FolderOpen size={24} className="mx-auto mb-2 opacity-20" />
                  <p className="text-[11px]">Bir klasör açarak başlayın</p>
                  <p className="text-[9px] text-slate-700 mt-1">veya editöre dosya sürükleyin</p>
                </div>
              )}
            </div>
          )}
        </div>

        {/* User Footer */}
        <div className="p-3 border-t border-slate-800/50 flex items-center justify-between min-w-[260px]">
          <div className="flex items-center gap-2.5">
            <div className="h-8 w-8 bg-gradient-to-br from-blue-600 to-violet-600 rounded-lg flex items-center justify-center font-bold text-xs text-white shadow">
              {user.name[0].toUpperCase()}
            </div>
            <div className="flex flex-col">
              <span className="text-[12px] font-semibold text-slate-300">{user.name}</span>
              <span className="text-[9px] text-emerald-500 font-medium">Online</span>
            </div>
          </div>
          <div className="flex gap-0.5">
            <button onClick={() => setShowSettings(true)} className="p-2 hover:bg-slate-800 text-slate-500 hover:text-white rounded-lg transition-all">
              <Settings size={14} />
            </button>
            <button onClick={handleLogout} className="p-2 hover:bg-red-950/30 text-slate-500 hover:text-red-400 rounded-lg transition-all">
              <LogOut size={14} />
            </button>
          </div>
        </div>
      </motion.aside>

      {/* =================== ORTA: KOD EDİTÖRÜ =================== */}
      <div className="flex-1 flex flex-col min-w-0 border-r border-slate-800/50">
        {/* Editor Header */}
        <div className="h-11 border-b border-slate-800/50 flex items-center justify-between px-4 bg-[#000000]/50 shrink-0">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setIsSidebarOpen(!isSidebarOpen)}
              className="p-1.5 hover:bg-slate-800 rounded-lg text-slate-500 transition-all"
            >
              {isSidebarOpen ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
            </button>

            {/* Açık Dosya Göstergesi */}
            <div className="flex items-center gap-2 border-l border-slate-800/50 pl-3 ml-1">
              <Code2 size={14} className="text-blue-500" />
              <span className="text-[12px] font-semibold text-slate-400">
                {openedFilePath ? openedFilePath.split('/').pop() : 'C# Editor'}
              </span>
              {openedFilePath && (
                <button onClick={() => { setOpenedFilePath(null); setCode(''); }} className="p-0.5 hover:bg-slate-700 rounded text-slate-500">
                  <X size={12} />
                </button>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <div
              className="flex items-center gap-1.5 bg-[#000000] border border-slate-800 rounded-lg px-3 py-1.5"
              title="AI yanıt dili — kod editörünün dilini değil, yapay zekanın sana hangi dilde cevap vereceğini belirler"
            >
              <Languages size={12} className="text-blue-500" />
              <select
                value={lang}
                onChange={(e) => setLang(e.target.value)}
                className="bg-transparent text-slate-300 text-[11px] font-medium outline-none cursor-pointer border-none appearance-none"
                style={{ backgroundColor: 'transparent', color: '#cbd5e1' }}
              >
                <option value="tr" className="bg-[#000000]">TR</option>
                <option value="en" className="bg-[#000000]">EN</option>
              </select>
            </div>
            <Activity size={14} className="text-emerald-500 animate-pulse" />
          </div>
        </div>

        {/* Code Area — Drag & Drop destekli */}
        <div
          className={`flex-1 overflow-hidden flex flex-col relative transition-colors ${isDragging ? 'ring-2 ring-blue-500/40 ring-inset bg-blue-500/5' : ''}`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          {/* Drag overlay */}
          {isDragging && (
            <div className="absolute inset-0 flex items-center justify-center z-10 pointer-events-none">
              <div className="bg-blue-600/20 border-2 border-dashed border-blue-500/50 rounded-2xl px-8 py-6 flex flex-col items-center gap-2">
                <Upload size={32} className="text-blue-400" />
                <span className="text-[13px] font-semibold text-blue-400">C# dosyasını bırakın</span>
              </div>
            </div>
          )}
          {/* Rejection warning */}
          {dragRejectMsg && (
            <div className="absolute top-3 left-1/2 -translate-x-1/2 z-20 bg-red-950/90 border border-red-500/30 rounded-xl px-4 py-2.5 flex items-center gap-2 animate-pulse">
              <AlertTriangle size={14} className="text-red-400" />
              <span className="text-[12px] text-red-300 font-medium">{dragRejectMsg}</span>
            </div>
          )}

          <div className="flex-1 relative flex flex-col bg-[#000000]">
            {/* Empty State Overlay */}
            {!code && !openedFilePath && !isEditorFocused && (
              <div
                onClick={() => setIsEditorFocused(true)}
                className="absolute inset-0 flex flex-col items-center justify-center cursor-text z-20 hover:bg-slate-900/10 transition-colors"
              >
                <div className="w-20 h-20 mb-6 rounded-3xl bg-slate-900/30 border border-slate-800/50 flex items-center justify-center shadow-2xl relative overflow-hidden group">
                  <div className="absolute inset-0 bg-gradient-to-br from-blue-500/5 to-violet-500/5 animate-pulse" />
                  <Code2 size={32} className="text-slate-600" />
                </div>
                <h3 className="text-lg font-semibold text-slate-300 tracking-tight">C# Editörü</h3>
                <div className="mt-3 text-center space-y-1.5 pointer-events-none">
                  <p className="text-[13px] text-slate-500 font-medium tracking-wide">
                    Kodu buraya yapıştır veya sol panelden bir .cs dosyası seç
                  </p>
                  <p className="text-[12px] text-slate-600">
                    ya da sağdaki chat'ten direkt bir şey iste
                  </p>
                </div>
                <div className="mt-10 flex gap-6 text-[10px] font-mono text-slate-700 font-semibold uppercase tracking-widest pointer-events-none">
                  <span className="flex items-center gap-1.5"><Activity size={14} /> Bug Fix</span>
                  <span className="flex items-center gap-1.5"><Cpu size={14} /> Kod Üretim</span>
                  <span className="flex items-center gap-1.5"><Sparkles size={14} /> Analiz</span>
                </div>
              </div>
            )}

            {/* Monaco Editor wrapper */}
            <div
              className={`flex-1 relative z-10 transition-opacity duration-200 ${(code || openedFilePath || isEditorFocused) ? 'opacity-100' : 'opacity-0 pointer-events-none'}`}
            >
              {/* FLOATING ATTACHMENT BUTTON (+) */}
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

                    {/* Tooltip */}
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
          </div>
        </div>{/* end drag-drop wrapper */}
      </div>

      {/* =================== SAĞ: AI CHAT PANELİ =================== */}
      <motion.div
        animate={{ width: isChatOpen ? 420 : 0, opacity: isChatOpen ? 1 : 0 }}
        transition={{ duration: 0.2 }}
        className="bg-[#000000] flex flex-col overflow-hidden shrink-0"
      >
        {/* Chat Header */}
        <div className="h-11 border-b border-slate-800/50 flex items-center justify-between px-4 min-w-[420px] shrink-0">
          <div className="flex items-center gap-2">
            <ModelAvatar provider={effectiveProvider} size={14} />
            {/* MODEL SELECTOR DROPDOWN */}
            <div className="relative">
              <button
                onClick={() => {
                  const opening = !isModelDropdownOpen;
                  setIsModelDropdownOpen(opening);
                  if (opening) {
                    fetchAvailableModels();
                    // Mevcut seçili model OpenRouter üzerinden çalışıyorsa o modelin toggle'ını aç
                    if (aiConfig.provider_type === 'openrouter') {
                      setModelOrToggles(prev => ({ ...prev, [aiConfig.model_name]: true }));
                    }
                  }
                }}
                className="flex items-center gap-1.5 hover:bg-slate-800 px-2 py-1 rounded transition-all text-left"
              >
                <div className="flex flex-col">
                  <span className="text-[12px] font-semibold text-slate-300 leading-tight">
                    {displayModelName}
                  </span>
                  <span className="text-[9px] text-slate-500 leading-tight capitalize">
                    {aiConfig.use_multi_agent ? 'Claude + GPT' : aiConfig.provider_type}
                  </span>
                </div>
                <ChevronDown size={14} className="text-slate-500" />
              </button>

              {/* DROPDOWN MENU */}
              <AnimatePresence>
                {isModelDropdownOpen && (
                  <>
                    <div
                      className="fixed inset-0 z-40"
                      onClick={() => setIsModelDropdownOpen(false)}
                    />
                    <motion.div
                      initial={{ opacity: 0, y: -10 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -10 }}
                      className="absolute top-10 left-0 w-64 bg-[#000000] border border-slate-700 shadow-2xl rounded-xl z-50"
                    >
                      {/* TABS: TEK AJAN / MULTI-AGENT */}
                      <div className="flex border-b border-slate-800/80">
                        <button
                          onClick={async () => {
                            const newCfg = { ...aiConfig, use_multi_agent: false };
                            setAiConfig(newCfg);
                            setShowMultiAgentInfo(false);
                            if (user) await axios.post(`${API}/save-ai-config`, { ...newCfg, user_id: user.id });
                          }}
                          className={`flex-1 py-2 text-[11px] font-semibold transition-colors ${!aiConfig.use_multi_agent ? 'text-blue-400 border-b-2 border-blue-500' : 'text-slate-500 hover:text-slate-300'}`}
                        >
                          Tek Ajan
                        </button>
                        <div className="flex-1 flex items-center justify-center">
                          <button
                            onClick={async () => {
                              const newCfg = { ...aiConfig, use_multi_agent: true, provider_type: 'anthropic' };
                              setAiConfig(newCfg);
                              setShowMultiAgentInfo(false);
                              if (user) await axios.post(`${API}/save-ai-config`, { ...newCfg, user_id: user.id });
                            }}
                            className={`py-2 text-[11px] font-semibold transition-colors ${aiConfig.use_multi_agent ? 'text-blue-400 border-b-2 border-blue-500' : 'text-slate-500 hover:text-slate-300'}`}
                          >
                            Multi-Agent
                          </button>
                          <button
                            onClick={(e) => { e.stopPropagation(); setShowMultiAgentInfo(v => !v); }}
                            className="ml-1 text-slate-600 hover:text-slate-400 transition-colors"
                            title="Multi-Agent hakkında bilgi"
                          >
                            <HelpCircle size={12} />
                          </button>
                        </div>
                      </div>

                      {/* INFO PANEL — inline, no overflow clipping */}
                      {showMultiAgentInfo && (
                        <div className="mx-2 mt-2 mb-1 bg-[#0a0a0f] border border-blue-900/60 rounded-xl p-3">
                          <p className="text-[11px] font-bold text-blue-400 mb-2">
                            🤖 Multi-Agent Pipeline
                          </p>
                          {/* Model özeti */}
                          <div className="mb-2 px-2 py-1.5 rounded-lg bg-slate-900/60 border border-slate-800/60 flex flex-col gap-0.5">
                            <div className="flex items-center justify-between">
                              <span className="text-[9px] text-slate-500">Mimar / Orkestratör</span>
                              <span className="text-[9px] font-mono text-orange-400">{claudeModelForMA}</span>
                            </div>
                            <div className="flex items-center justify-between">
                              <span className="text-[9px] text-slate-500">Kodlama Ajanı</span>
                              <span className={`text-[9px] font-mono ${aiConfig.force_claude_coder || !maCoderProvider ? 'text-orange-400' : maCoderProvider === 'openrouter' ? 'text-purple-400' : 'text-emerald-400'}`}>
                                {aiConfig.force_claude_coder
                                  ? claudeModelForMA
                                  : maCoderProvider === 'openrouter'
                                    ? 'openai/gpt-5.4 (OR)'
                                    : maCoderProvider === 'openai'
                                      ? 'gpt-5.4 (OpenAI)'
                                      : claudeModelForMA}
                              </span>
                            </div>
                          </div>
                          <div className="space-y-1.5 text-[10px] text-slate-400">
                            <div className="flex gap-2"><span className="shrink-0">🎯</span><span><span className="text-slate-300 font-semibold">Orchestrator:</span> İsteği analiz eder, plan çıkarır.</span></div>
                            <div className="flex gap-2"><span className="shrink-0">🔧</span><span><span className="text-slate-300 font-semibold">Unity Expert / Coder:</span> {aiConfig.force_claude_coder ? 'Claude kodu yazar.' : 'GPT key varsa GPT, yoksa Claude yazar.'}</span></div>
                            <div className="flex gap-2"><span className="shrink-0">⚖️</span><span><span className="text-slate-300 font-semibold">Critic:</span> Teknik kaliteyi puanlar.</span></div>
                            <div className="flex gap-2"><span className="shrink-0">🎮</span><span><span className="text-slate-300 font-semibold">Game Feel:</span> Claude oyun hissiyatını değerlendirir.</span></div>
                            <div className="flex gap-2"><span className="shrink-0">🔁</span><span><span className="text-slate-300 font-semibold">Reflexive Loop:</span> Skor 8/10 altındaysa otomatik yeniden yazar.</span></div>
                            <div className="mt-2 pt-2 border-t border-amber-900/40 bg-amber-900/10 rounded-lg px-2 py-1.5">
                              <p className="text-amber-400 font-semibold text-[10px] mb-0.5">⚠️ Token Kullanımı</p>
                              <p className="text-slate-500">Her istek 4–5 ayrı AI çağrısı yapar. Tek ajan moduna kıyasla 4–5× daha fazla token harcar.</p>
                            </div>
                          </div>
                        </div>
                      )}

                      {/* TEK AJAN İÇERİĞİ */}
                      {!aiConfig.use_multi_agent && (
                        <div className="max-h-[60vh] overflow-y-auto custom-scrollbar">
                          {/* YEREL BİLGİ BANKASI (KB) — Varsayılan Sistem */}
                          <div className="p-1">
                            <div className="px-2 py-1.5 text-[10px] font-bold text-slate-500 uppercase tracking-wider flex items-center gap-2 mt-1">
                              <Database size={10} /> Yerleşik Sistem
                            </div>
                            <button
                              onClick={async () => {
                                const newCfg = { ...aiConfig, provider_type: 'kb', model_name: 'unity-kb-v1', api_key: '' };
                                setAiConfig(newCfg);
                                setIsModelDropdownOpen(false);
                                if (user) await axios.post(`${API}/save-ai-config`, { ...newCfg, user_id: user.id });
                              }}
                              className={`w-full text-left px-3 py-2 text-[12px] flex flex-col hover:bg-emerald-600/10 rounded-lg transition-colors
                              ${aiConfig.provider_type === 'kb' ? 'bg-emerald-600/10 text-emerald-400' : 'text-slate-300'}`}
                            >
                              <span className="font-medium flex items-center gap-1.5">Unity Bilgi Bankası
                                <span className="text-[9px] bg-emerald-500/20 text-emerald-400 px-1.5 py-0.5 rounded-full">Ücretsiz</span>
                              </span>
                              <span className="text-[10px] text-slate-500">Temel Unity konuları • 0ms • API key gerektirmez</span>
                            </button>
                          </div>

                          {/* BULUT MODELLER */}
                          {availableModels.cloud.length > 0 && (
                            <div className="p-1">
                              <div className="px-2 py-1.5 text-[10px] font-bold text-slate-500 uppercase tracking-wider flex items-center gap-2 mt-1">
                                <Sparkles size={10} /> Bulut API Modelleri
                              </div>
                              {availableModels.cloud.map(m => {
                                // OpenRouter-only model (ör. Kimi): her zaman openrouter kullanır
                                const isOrOnly = m.provider === 'openrouter' && !m.openrouter_id;
                                const orToggle = isOrOnly ? true : (modelOrToggles[m.id] ?? false);
                                const effectiveModelId = (orToggle && m.openrouter_id) ? m.openrouter_id : m.id;
                                const effectiveProvider = (orToggle && m.openrouter_id) ? 'openrouter' : m.provider;
                                const hasKey = providersWithKeys.includes(effectiveProvider);
                                const isActive = aiConfig.model_name === effectiveModelId || aiConfig.model_name === m.id;
                                return (
                                  <div key={m.id} className={`flex items-center gap-1 rounded-lg transition-colors hover:bg-blue-600/10 ${isActive ? 'bg-blue-600/10' : ''}`}>
                                    {/* Model seçim butonu */}
                                    <button
                                      onClick={async () => {
                                        if (!hasKey) {
                                          setAiConfig({ ...aiConfig, provider_type: effectiveProvider, model_name: effectiveModelId });
                                          setIsModelDropdownOpen(false);
                                          setShowSettings(true);
                                          const keyLabel = orToggle ? 'OpenRouter' : m.provider.charAt(0).toUpperCase() + m.provider.slice(1);
                                          showToast(`${keyLabel} için API key girilmedi. Lütfen Ayarlar'dan API key'inizi girin.`, 'warning');
                                          return;
                                        }
                                        const newCfg = { ...aiConfig, provider_type: effectiveProvider, model_name: effectiveModelId };
                                        setAiConfig(newCfg);
                                        setIsModelDropdownOpen(false);
                                        if (user) await axios.post(`${API}/save-ai-config`, { ...newCfg, user_id: user.id });
                                      }}
                                      className={`flex-1 text-left px-3 py-2 text-[12px] flex items-center justify-between ${isActive ? 'text-blue-400' : 'text-slate-300'}`}
                                    >
                                      <div className="flex flex-col">
                                        <span className="font-medium flex items-center gap-1">
                                          {m.name}
                                          {m.paid && (
                                            <span className="text-[8px] font-bold px-1 py-0.5 rounded bg-amber-500/15 text-amber-400 border border-amber-500/30">
                                              Pro
                                            </span>
                                          )}
                                        </span>
                                        <span className={`text-[10px] capitalize ${orToggle ? 'text-purple-500' : m.paid && !orToggle ? 'text-amber-600' : 'text-slate-500'}`}>
                                          {orToggle ? 'via OpenRouter' : m.paid ? 'ücretli — OR önerilir' : m.provider}
                                        </span>
                                      </div>
                                      {hasKey ? (
                                        <span className={`text-[9px] px-1.5 py-0.5 rounded-full ${orToggle ? 'bg-purple-500/20 text-purple-400' : 'bg-emerald-500/20 text-emerald-400'}`}>
                                          {orToggle ? 'OR ✓' : 'Key ✓'}
                                        </span>
                                      ) : (
                                        <span className="text-[9px] bg-amber-500/20 text-amber-400 px-1.5 py-0.5 rounded-full">Key Yok</span>
                                      )}
                                    </button>
                                    {/* OR toggle — sadece openrouter_id olan modellerde göster */}
                                    {m.openrouter_id && (
                                      <button
                                        onClick={async e => {
                                          e.stopPropagation();
                                          const newOrState = !modelOrToggles[m.id];
                                          setModelOrToggles(prev => ({ ...prev, [m.id]: newOrState }));
                                          // Eğer bu model şu an seçiliyse, aiConfig'i de hemen güncelle
                                          if (isActive && user) {
                                            const newModelId = (newOrState && m.openrouter_id) ? m.openrouter_id : m.id;
                                            const newProvider = (newOrState && m.openrouter_id) ? 'openrouter' : m.provider;
                                            const newCfg = { ...aiConfig, provider_type: newProvider, model_name: newModelId };
                                            setAiConfig(newCfg);
                                            await axios.post(`${API}/save-ai-config`, { ...newCfg, user_id: user.id });
                                          }
                                        }}
                                        title={orToggle ? 'Native API\'ye geç' : m.paid ? 'OpenRouter önerilir — free tier\'da mevcut değil' : 'OpenRouter üzerinden kullan'}
                                        className={`mr-2 shrink-0 text-[8px] font-bold px-1.5 py-0.5 rounded border transition-colors ${orToggle
                                            ? 'border-purple-500/60 text-purple-400 bg-purple-500/15'
                                            : m.paid
                                              ? 'border-amber-600/50 text-amber-600 hover:text-amber-400 hover:border-amber-500/60'
                                              : 'border-slate-700 text-slate-600 hover:text-slate-400 hover:border-slate-600'
                                          }`}
                                      >
                                        OR
                                      </button>
                                    )}
                                  </div>
                                );
                              })}
                            </div>
                          )}

                          {/* YEREL MODELLER */}
                          <div className="p-1 border-t border-slate-800/80">
                            <div className="px-2 py-1.5 text-[10px] font-bold text-slate-500 uppercase tracking-wider flex items-center gap-2 mt-1">
                              <Cpu size={10} /> Yerel (Ollama) Modeller
                            </div>
                            {availableModels.local.length > 0 ? (
                              availableModels.local.map(m => (
                                <button
                                  key={m.id}
                                  onClick={async () => {
                                    const newCfg = { ...aiConfig, provider_type: 'ollama', model_name: m.id, api_key: '' };
                                    setAiConfig(newCfg);
                                    setIsModelDropdownOpen(false);
                                    if (user) await axios.post(`${API}/save-ai-config`, { ...newCfg, user_id: user.id });
                                  }}
                                  className={`w-full text-left px-3 py-2 text-[12px] flex flex-col hover:bg-emerald-600/10 rounded-lg transition-colors
                                  ${aiConfig.model_name === m.id ? 'bg-emerald-600/10 text-emerald-400' : 'text-slate-300'}`}
                                >
                                  <span className="font-medium">{m.name}</span>
                                  <span className="text-[10px] text-slate-500">{m.id}</span>
                                </button>
                              ))
                            ) : (
                              <div className="px-3 py-2 text-[11px] text-slate-500 italic">Ollama modeli bulunamadı.</div>
                            )}
                          </div>
                        </div>
                      )}

                      {/* MULTI-AGENT İÇERİĞİ */}
                      {aiConfig.use_multi_agent && (
                        <div className="p-3 space-y-2">
                          {/* Anthropic — Zorunlu */}
                          <div className={`flex items-center justify-between px-3 py-2.5 rounded-xl border ${providersWithKeys.includes('anthropic') ? 'border-emerald-800/50 bg-emerald-900/10' : 'border-red-800/50 bg-red-900/10'}`}>
                            <div>
                              <p className="text-[11px] font-semibold text-slate-300 flex items-center gap-1.5">
                                <span>Anthropic</span>
                                <span className="text-[9px] bg-red-500/20 text-red-400 px-1.5 py-0.5 rounded-full">Zorunlu</span>
                              </p>
                              <p className="text-[9px] text-slate-500 mt-0.5">
                                Architect, Orchestrator, Game Feel
                                <span className="ml-1 font-mono text-orange-400/70">{claudeModelForMA}</span>
                              </p>
                            </div>
                            {providersWithKeys.includes('anthropic') ? (
                              <span className="text-[10px] text-emerald-400 font-semibold">✓ Kayıtlı</span>
                            ) : (
                              <button onClick={() => { setIsModelDropdownOpen(false); setShowSettings(true); }} className="text-[9px] text-red-400 hover:text-red-300 underline">Key Ekle</button>
                            )}
                          </div>

                          {/* OpenRouter / OpenAI — Opsiyonel */}
                          <div className={`flex items-center justify-between px-3 py-2.5 rounded-xl border ${maCoderProvider === 'openrouter' ? 'border-purple-800/50 bg-purple-900/10'
                              : maCoderProvider === 'openai' ? 'border-emerald-800/50 bg-emerald-900/10'
                                : 'border-slate-800/50 bg-slate-900/20'
                            }`}>
                            <div>
                              <p className="text-[11px] font-semibold text-slate-300 flex items-center gap-1.5">
                                <span>OpenRouter / OpenAI</span>
                                <span className="text-[9px] bg-slate-700 text-slate-400 px-1.5 py-0.5 rounded-full">Opsiyonel</span>
                              </p>
                              <p className="text-[9px] text-slate-500 mt-0.5">
                                Expert, Critic —{' '}
                                {maCoderProvider === 'openrouter'
                                  ? <span className="font-mono text-purple-400/80">openai/gpt-5.4 via OpenRouter</span>
                                  : maCoderProvider === 'openai'
                                    ? <span className="font-mono text-emerald-400/80">gpt-5.4 via OpenAI</span>
                                    : <span className="text-slate-600">key yok, Claude kullanılacak</span>}
                              </p>
                            </div>
                            {maCoderProvider === 'openrouter' ? (
                              <span className="text-[10px] text-purple-400 font-semibold">OpenRouter key seçili</span>
                            ) : maCoderProvider === 'openai' ? (
                              <span className="text-[10px] text-emerald-400 font-semibold">OpenAI key seçili</span>
                            ) : (
                              <button onClick={() => { setIsModelDropdownOpen(false); setShowSettings(true); }} className="text-[9px] text-slate-500 hover:text-slate-300 underline">Key Ekle</button>
                            )}
                          </div>

                          {/* Coder seçimi — sadece GPT key varsa göster */}
                          {(providersWithKeys.includes('openrouter') || providersWithKeys.includes('openai')) && (
                            <div className="flex items-center justify-between px-3 py-2 rounded-xl border border-slate-800/50 bg-slate-900/20">
                              <div>
                                <p className="text-[11px] font-semibold text-slate-300">Coder Ajanı</p>
                                <p className="text-[9px] text-slate-500 mt-0.5">
                                  {aiConfig.force_claude_coder ? '💜 Claude yazacak' : '🤖 GPT yazacak'}
                                </p>
                              </div>
                              <label className="relative inline-flex items-center cursor-pointer" title="Aktif: GPT yazar · Kapalı: Claude yazar">
                                <input
                                  type="checkbox"
                                  className="sr-only peer"
                                  checked={!aiConfig.force_claude_coder}
                                  onChange={async (e) => {
                                    const newCfg = { ...aiConfig, force_claude_coder: !e.target.checked };
                                    setAiConfig(newCfg);
                                    if (user) await axios.post(`${API}/save-ai-config`, { ...newCfg, user_id: user.id });
                                  }}
                                />
                                <div className="w-9 h-5 bg-slate-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-purple-600"></div>
                              </label>
                            </div>
                          )}
                          {!(providersWithKeys.includes('openrouter') || providersWithKeys.includes('openai')) && (
                            <p className="text-[9px] text-slate-600 text-center px-2">💜 Coder: Claude kullanacak</p>
                          )}
                        </div>
                      )}

                      {/* SETTINGS KISAYOLU */}
                      <button
                        onClick={() => { setIsModelDropdownOpen(false); setShowSettings(true); }}
                        className="w-full text-left p-3 text-[11px] text-slate-400 bg-[#000000] hover:bg-slate-800 transition-colors flex items-center justify-between group"
                      >
                        API Key Ekle / Ayarlar
                        <ChevronRight size={12} className="opacity-0 group-hover:opacity-100 transition-opacity" />
                      </button>
                    </motion.div>
                  </>
                )}
              </AnimatePresence>
            </div>
          </div>
        </div>
        {/* Chat Alanı */}
        <div className="flex-1 relative flex flex-col min-h-0 bg-[#000000]">
          <button
            onClick={() => setIsChatOpen(false)}
            className="p-1.5 hover:bg-slate-800 rounded-lg text-slate-500 transition-all absolute top-4 right-4 z-10"
          >
            <PanelRightClose size={16} />
          </button>
          {/* Chat Messages */}
          <div className="flex-1 overflow-y-auto custom-scrollbar p-4 space-y-4 min-w-[420px]">
            {!activeConvId ? (
              <div className="flex flex-col items-center justify-center h-full text-slate-600 gap-3">
                <Bot size={32} className="opacity-20" />
                <p className="text-[11px] text-center">
                  Sohbet başlatmak için soldan<br />bir sohbet seçin veya oluşturun
                </p>
              </div>
            ) : messages.length === 0 && !loading ? (
              <div className="flex items-center justify-center h-full">
                <Sparkles size={20} className="opacity-10 text-blue-500" />
              </div>
            ) : (
              <>
                {messages.map((msg, msgIdx) => (
                  <div key={msg.id} className={`chat-message-enter ${msg.role === 'user' ? 'flex justify-end' : ''}`}>
                    {msg.role === 'assistant' ? (
                      // AI Mesajı
                      <div className="flex gap-2.5 max-w-full">
                        <ModelAvatar provider={effectiveProvider} size={13} className="mt-0.5" />
                        <div className="flex-1 min-w-0">
                          {/* Statik Bulgular */}
                          {msg.smells && msg.smells.length > 0 && (
                            <div className="mb-3 bg-[#000000] rounded-lg border border-orange-500/20 p-3">
                              <div className="flex items-center gap-1.5 mb-2">
                                <AlertTriangle size={12} className="text-orange-400" />
                                <span className="text-[10px] font-semibold text-orange-400 uppercase tracking-wider">Static Analysis</span>
                              </div>
                              <div className="space-y-1.5">
                                {msg.smells.map((s: any, i: number) => (
                                  <div key={i} className="text-[11px] text-slate-400 flex items-start gap-2">
                                    <span className="bg-orange-500/10 text-orange-500 px-1.5 py-0.5 rounded text-[9px] font-bold shrink-0">
                                      L{s.line || "?"}
                                    </span>
                                    <span>{s.msg}</span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                          {/* Pipeline Skor Badge */}
                          {msg.pipeline && (
                            <div className="mb-3 space-y-3">
                              <div className="bg-[#000000] rounded-lg border border-blue-500/20 p-3">
                                <div className="flex items-center justify-between mb-2">
                                  <div className="flex items-center gap-2">
                                    <div className="w-6 h-6 rounded bg-blue-500/20 flex items-center justify-center">
                                      <Sparkles size={12} className="text-blue-400" />
                                    </div>
                                    <span className="text-xs font-bold text-slate-200">AI Kalite Skoru</span>
                                  </div>
                                  <div className="px-2 py-0.5 rounded text-[10px] font-bold bg-blue-500/20 text-blue-400">
                                    {msg.pipeline.score.toFixed(1)}/10
                                  </div>
                                </div>
                                <div className="flex items-center gap-2 text-[10px] mb-2">
                                  {msg.pipeline.severity_counts?.critical > 0 && (
                                    <span className="text-red-400">🔴 {msg.pipeline.severity_counts.critical}</span>
                                  )}
                                  {msg.pipeline.severity_counts?.warning > 0 && (
                                    <span className="text-yellow-400">🟡 {msg.pipeline.severity_counts.warning}</span>
                                  )}
                                  {msg.pipeline.severity_counts?.info > 0 && (
                                    <span className="text-blue-400">🔵 {msg.pipeline.severity_counts.info}</span>
                                  )}
                                </div>
                                <div className="text-[10px] text-slate-400 leading-relaxed max-h-24 overflow-y-auto custom-scrollbar pr-2">
                                  {msg.pipeline.summary}
                                </div>
                                <div className="text-[9px] text-slate-600 flex items-center gap-1 mt-2 border-t border-slate-800 pt-2">
                                  <span>⚡ {(msg.pipeline.total_duration_ms / 1000).toFixed(1)}s</span>
                                </div>
                              </div>
                            </div>
                          )}
                          {/* Thinking Block */}
                          {msg.thinking && (
                            <ThinkingBlock
                              thinking={msg.thinking}
                              durationMs={msg.thinking_duration_ms}
                            />
                          )}

                          {/* Tool Blocks (Agentic) */}
                          {msg.tool_calls && msg.tool_calls.length > 0 && (
                            <div className="flex flex-col gap-1 mb-3">
                              {msg.tool_calls.map((tc, idx) => (
                                <ToolBlock
                                  key={idx}
                                  tool={tc.tool}
                                  args={tc.args}
                                  summary={tc.summary}
                                  success={tc.success}
                                />
                              ))}
                            </div>
                          )}

                          <div className="prose prose-invert max-w-none text-[13px] leading-relaxed prose-p:my-2 prose-headings:my-3 prose-ul:my-2 prose-li:my-0.5 prose-pre:bg-slate-900 prose-pre:border prose-pre:border-slate-800 prose-a:text-emerald-400">
                            <MarkdownRenderer content={msg.content.replace('<!-- SCOPE_WARNING_ACTIVE -->', '')} workspacePath={workspacePath} onExportToUnity={handleExportToUnity} />
                          </div>
                          {/* Scope Warning Butonları */}
                          {msg.content.includes('SCOPE_WARNING_ACTIVE') && msgIdx === messages.length - 1 && !loading && (
                            <div className="flex gap-2 mt-3">
                              <button
                                onClick={() => sendMessage('Tam Sistemi Üret')}
                                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600/20 border border-blue-500/30 text-blue-300 text-[12px] font-medium hover:bg-blue-600/35 transition-colors"
                              >
                                ✅ Tam Sistemi Üret
                              </button>
                              <button
                                onClick={() => sendMessage('Basit Versiyon')}
                                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-700/40 border border-slate-600/30 text-slate-300 text-[12px] font-medium hover:bg-slate-700/60 transition-colors"
                              >
                                ⚡ Basit Versiyon
                              </button>
                            </div>
                          )}
                          {/* Plan Kartı — plan modu onay bekliyor */}
                          {pendingPlan && msgIdx === messages.length - 1 && msg.role === 'assistant' && (
                            <motion.div
                              initial={{ opacity: 0, y: 6 }}
                              animate={{ opacity: 1, y: 0 }}
                              className="mt-3 rounded-xl border border-blue-500/20 bg-blue-950/10 overflow-hidden"
                            >
                              <div className="flex items-center justify-between px-4 py-2.5 border-b border-blue-500/10">
                                <span className="text-[11px] font-semibold text-blue-300">Onaylıyor musun?</span>
                                <span className="text-[10px] text-slate-600">{pendingPlan.mode === 'step' ? 'Adım Adım' : 'Plan Modu'}</span>
                              </div>
                              <div className="flex gap-2 px-4 py-3">
                                <button
                                  onClick={async () => {
                                    const originalMsg = pendingPlan.originalMessage;
                                    const mode = pendingPlan.mode;
                                    setPendingPlan(null);
                                    setLoading(true);
                                    try {
                                      const res = await axios.post(`${API}/chat`, {
                                        conversation_id: activeConvId,
                                        message: originalMsg,
                                        language: lang,
                                        user_id: user?.id,
                                        mode: appMode,
                                        use_kb: aiConfig.provider_type === 'kb',
                                        use_or_for_coder: gpt54OrToggled,
                                        editor_code: code || '',
                                        use_thinking: false,
                                        generation_mode: mode,
                                        generation_confirmed: true,
                                      }, { timeout: 900000 });
                                      const aiMsgId = Date.now() + 1;
                                      const aiMsg: Message = {
                                        id: aiMsgId, role: 'assistant',
                                        content: res.data.content,
                                        smells: res.data.static_results?.smells || [],
                                        timestamp: new Date().toISOString(),
                                        pipeline: res.data.pipeline || null,
                                        thinking: res.data.thinking || null,
                                        thinking_duration_ms: res.data.thinking_duration_ms || null,
                                      };
                                      setMessages(prev => [...prev, aiMsg]);
                                      if (mode === 'step' && res.data.content) {
                                        const { parseGeneratedFiles } = await import('../components/home/export-utils');
                                        const genFiles = parseGeneratedFiles(res.data.content);
                                        if (genFiles.length > 0) {
                                          setPendingGenFiles({ files: genFiles.map(f => ({ name: f.name, code: f.code, suggestedPath: suggestFilePath(f.name) })), messageId: aiMsgId });
                                        }
                                      } else if (mode === 'plan' && res.data.content) {
                                        const { parseGeneratedFiles } = await import('../components/home/export-utils');
                                        const genFiles = parseGeneratedFiles(res.data.content);
                                        for (const f of genFiles) {
                                          if (ipc && workspacePath) await ipc.invoke('write-file', suggestFilePath(f.name), f.code, workspacePath);
                                        }
                                        if (genFiles.length > 0) refreshFileTree();
                                      }
                                    } finally {
                                      setLoading(false);
                                    }
                                  }}
                                  className="flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-[12px] font-semibold transition-colors"
                                >
                                  Başlat
                                </button>
                                <button
                                  onClick={() => setPendingPlan(null)}
                                  className="px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-400 rounded-lg text-[12px] font-semibold transition-colors"
                                >
                                  İptal
                                </button>
                              </div>
                            </motion.div>
                          )}

                          {/* File Creation Approval — kod üretim sonucu */}
                          {pendingGenFiles && pendingGenFiles.messageId === msg.id && (
                            <FileCreationApproval
                              files={pendingGenFiles.files}
                              autoAccept={generationMode === 'auto'}
                              onAcceptOne={async (file) => {
                                if (!ipc || !workspacePath) return;
                                await ipc.invoke('write-file', file.suggestedPath, file.code, workspacePath);
                                refreshFileTree();
                              }}
                              onSkipOne={() => { }}
                              onAcceptAll={async (files) => {
                                if (!ipc || !workspacePath) return;
                                for (const file of files) {
                                  await ipc.invoke('write-file', file.suggestedPath, file.code, workspacePath);
                                }
                                refreshFileTree();
                              }}
                              onDone={() => setPendingGenFiles(null)}
                              onOpenFile={(path) => openFile(path)}
                            />
                          )}

                          {/* Diff Viewer — FIX pipeline sonucu */}
                          {pendingFix && pendingFix.messageId === msg.id && (
                            <DiffViewer
                              diffData={pendingFix.data}
                              filename={openedFilePath ? openedFilePath.split('/').pop() : undefined}
                              applied={pendingFix.applied}
                              onAccept={async (fixedCode) => {
                                setCode(fixedCode);
                                setPendingFix(prev => prev ? { ...prev, applied: true } : null);
                                if (ipc && openedFilePath && workspacePath) {
                                  await ipc.invoke('write-file', openedFilePath, fixedCode, workspacePath);
                                  refreshFileTree();
                                }
                                showToast(`✅ ${openedFilePath ? openedFilePath.split('/').pop() : 'Dosya'} güncellendi`, 'success');
                              }}
                              onReject={() => setPendingFix(null)}
                            />
                          )}
                        </div>
                      </div>
                    ) : (
                      // Kullanıcı Mesajı
                      <div className="max-w-[85%]">
                        <div className="bg-blue-600/15 border border-blue-500/20 rounded-xl rounded-tr-sm px-3.5 py-2.5">
                          <div className="text-[13px] text-slate-200 whitespace-pre-wrap break-words">
                            <MarkdownRenderer content={msg.content} />
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                ))}

                {/* Typing Indicator */}
                {loading && (
                  <div className="flex gap-2.5 chat-message-enter mb-6">
                    <ModelAvatar provider={effectiveProvider} size={13} />
                    <div className="flex-1 min-w-0">
                      {currentPlan.length > 0 && (
                        <div className="mb-4">
                          <AgentPlan tasks={currentPlan} />
                        </div>
                      )}
                      <div className="bg-[#000000] rounded-lg px-4 py-3 border border-slate-800 inline-flex items-center gap-2.5">
                        <div className="flex items-center gap-1.5">
                          <div className="typing-dot h-2 w-2 bg-blue-500 rounded-full" />
                          <div className="typing-dot h-2 w-2 bg-blue-500 rounded-full" />
                          <div className="typing-dot h-2 w-2 bg-blue-500 rounded-full" />
                        </div>
                        {useThinking && (
                          <span className="text-[11px] text-violet-400 animate-pulse">düşünüyor...</span>
                        )}
                      </div>
                    </div>
                  </div>
                )}
                <div ref={chatEndRef} />
              </>
            )}
          </div>

          {/* Chat Input - Animated Version */}
          <div className="p-4 border-t border-slate-800/50 bg-[#000000]/80 backdrop-blur-md">
            {/* File Chip (sadece dosya yüklüyse ve eklenmişse göster) */}
            {includeEditorCode && code.trim() && (
              <div className="mb-3">
                <div className="inline-flex items-center gap-2 bg-blue-500/10 border border-blue-500/20 rounded-lg px-2.5 py-1.5 max-w-full group">
                  <Code2 size={13} className="text-blue-400 shrink-0" />
                  <span className="text-[11px] text-slate-300 font-medium truncate">
                    {openedFilePath ? openedFilePath.split('/').pop() : 'kod.cs'}
                  </span>
                  <button
                    onClick={() => setIncludeEditorCode(false)}
                    className="p-1 hover:bg-slate-800 rounded text-slate-500 hover:text-slate-300 transition-all"
                  >
                    <X size={10} />
                  </button>
                </div>
              </div>
            )}
            <AnimatedChatInput
              value={chatInput}
              setValue={setChatInput}
              onSendMessage={(msg) => sendMessage(msg)}
              isLoading={loading}
              placeholder={code.trim() ? "Bu kodu analiz et, düzelt, veya bir şey sor..." : "Kod yaz, analiz et, hata düzelt — ne istersen..."}
              className="border-slate-800/50"
              includeEditorCode={includeEditorCode}
              onToggleIncludeCode={() => setIncludeEditorCode(!includeEditorCode)}
            />
            <div className="flex items-center gap-2 px-1 mt-1.5">
              <GenerationModeSelector value={generationMode} onChange={setGenerationMode} />
              <div className="w-px h-3 bg-slate-800" />
              <button
                onClick={() => setUseThinking(v => !v)}
                className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-medium transition-colors ${useThinking
                    ? 'bg-violet-500/15 border border-violet-500/30 text-violet-400'
                    : 'text-slate-600 hover:text-slate-400'
                  }`}
                title="Modelin düşünce sürecini göster"
              >
                <Brain size={11} />
                Thinking {useThinking ? 'Açık' : 'Kapalı'}
              </button>

              {/* Yeni Dairesel (Circular) Hafıza Butonu */}
              {activeConvId && contextUsage?.percent > 0 && (
                <>
                  <div className="w-px h-3 bg-slate-800" />
                  <button
                    onClick={compactConversation}
                    disabled={isCompacting}
                    title={`Hafıza Kullanımı: %${contextUsage.percent} (${contextUsage.message_count} mesaj)\nTıkla ve özetle`}
                    className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-medium transition-colors group relative ${contextUsage.percent >= 90 ? 'bg-red-500/10 border border-red-500/30 text-red-400 hover:bg-red-500/20'
                        : contextUsage.percent >= 75 ? 'bg-amber-500/10 border border-amber-500/30 text-amber-400 hover:bg-amber-500/20'
                          : 'text-slate-500 hover:text-slate-300 border border-transparent hover:border-slate-800/50 hover:bg-slate-800/30'
                      }`}
                  >
                    <div className="relative w-3.5 h-3.5 flex items-center justify-center">
                      <svg className="w-full h-full transform -rotate-90" viewBox="0 0 36 36">
                        <path
                          className="text-slate-800"
                          d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="4"
                        />
                        <path
                          className={`${contextUsage.percent >= 90 ? 'text-red-500'
                              : contextUsage.percent >= 75 ? 'text-amber-500'
                                : 'text-blue-500'
                            } transition-all duration-500`}
                          strokeDasharray={`${contextUsage.percent}, 100`}
                          d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="4"
                        />
                      </svg>
                      {contextUsage.should_compact && (
                        <span className="absolute -top-1 -right-1 w-1.5 h-1.5 bg-red-500 rounded-full animate-ping" />
                      )}
                    </div>
                    <span>{isCompacting ? 'Özetleniyor...' : 'Hafıza'}</span>
                  </button>
                </>
              )}
            </div>
          </div>
        </div>

        <AnimatePresence>
          {loading && <ThinkingIndicator />}
        </AnimatePresence>
      </motion.div >

      {/* Chat panel toggle (when closed) */}
      {
        !isChatOpen && (
          <button
            onClick={() => setIsChatOpen(true)}
            className="absolute right-3 top-3 p-2 bg-[#000000] border border-slate-800 rounded-lg text-slate-400 hover:text-blue-500 hover:border-blue-500/30 transition-all z-30"
          >
            <PanelRightOpen size={16} />
          </button>
        )
      }

      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </div >
  );
}
