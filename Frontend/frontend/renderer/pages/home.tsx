import React, { useState, useEffect, useRef } from 'react';
import Head from 'next/head';
import axios from 'axios';
import Editor from '@monaco-editor/react';
import { AnimatedChatInput, ThinkingIndicator } from "../components/ui/animated-ai-chat";
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
} from "lucide-react";
import { motion, AnimatePresence } from 'framer-motion';
import AgentPlan, { Task } from '../components/ui/agent-plan';
import { AuthScreen } from '../components/home/AuthScreen';
import { ExportModal } from '../components/home/ExportModal';
import { MarkdownRenderer } from '../components/home/MarkdownRenderer';
import { ModelAvatar } from '../components/home/ModelAvatar';
import { SettingsModal } from '../components/home/SettingsModal';
import { WorkspaceScreen } from '../components/home/WorkspaceScreen';
import { splitCodeIntoFiles } from '../components/home/export-utils';
import { AIConfig, AvailableModels, Conversation, ExportModalState, FileEntry, Message, UserData } from '../components/home/types';

const API = 'http://127.0.0.1:8000';

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
  const [loading, setLoading] = useState(false);
  const [currentPlan, setCurrentPlan] = useState<Task[]>([]);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [isChatOpen, setIsChatOpen] = useState(true);
  const [sidebarTab, setSidebarTab] = useState<'chats' | 'files'>('chats');
  const [isDragging, setIsDragging] = useState(false);
  const [dragRejectMsg, setDragRejectMsg] = useState('');
  const [appMode, setAppMode] = useState<'analysis' | 'generation'>('analysis');
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
    provider_type: 'kb', api_key: '', model_name: 'unity-kb-v1', use_multi_agent: true
  });
  const [availableModels, setAvailableModels] = useState<AvailableModels>({ local: [], cloud: [] });
  const [isModelDropdownOpen, setIsModelDropdownOpen] = useState(false);
  const [providersWithKeys, setProvidersWithKeys] = useState<string[]>([]);

  // --- EDITING ---
  const [editingId, setEditingId] = useState<number | null>(null);
  const [tempTitle, setTempTitle] = useState('');

  // --- EXPORT MODAL ---
  const [exportModal, setExportModal] = useState<ExportModalState | null>(null);
  const [exportFileName, setExportFileName] = useState('');

  // --- REFS ---
  const chatEndRef = useRef<HTMLDivElement>(null);
  const chatInputRef = useRef<HTMLTextAreaElement>(null);
  const userRef = useRef<UserData | null>(null);
  const authAlertShownRef = useRef(false);
  const errorAlertShownRef = useRef(false);

  const performLogout = (showMessage = false, message = "Oturumunuz sona erdi. Lütfen tekrar giriş yapın.") => {
    if (userRef.current?.sessionToken) {
      axios.post(`${API}/logout`).catch(() => undefined);
    }
    setUser(null);
    userRef.current = null;
    setSessionTokenHeader(null);
    localStorage.removeItem('unityArchitectUser');
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
      alert(message);
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
            alert(error?.response?.data?.detail || "Bu işlem için yetkiniz yok.");
            setTimeout(() => {
              authAlertShownRef.current = false;
            }, 1000);
          }
        } else if (!error?.response && userRef.current) {
          if (!errorAlertShownRef.current) {
            errorAlertShownRef.current = true;
            alert("Sunucuya ulaşılamadı. Backend çalışıyor mu kontrol edin.");
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

  // --- Modelleri uygulama açılışında yükle (user gerekmez) ---
  useEffect(() => {
    fetchAvailableModels();
  }, []);

  // --- Session Persistence ---
  useEffect(() => {
    const savedUser = localStorage.getItem('unityArchitectUser');
    if (savedUser) {
      try {
        const parsedUser = JSON.parse(savedUser);
        if (!parsedUser?.sessionToken) {
          localStorage.removeItem('unityArchitectUser');
          setSessionTokenHeader(null);
          return;
        }
        setSessionTokenHeader(parsedUser.sessionToken);
        setUser(parsedUser);
      } catch (e) {
        localStorage.removeItem('unityArchitectUser');
        setSessionTokenHeader(null);
      }
    }
  }, []);

  // --- Fetch on login ---
  useEffect(() => {
    if (user) {
      fetchConversations(user.id);
      fetchAIConfig(user.id);
      fetchAvailableModels();
      fetchLastWorkspace(user.id);
      fetchProvidersWithKeys(user.id);
    }
  }, [user]);

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
      const entries = await ipc.invoke('read-directory', path);
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
        alert(`⚠️ ${configToSave.provider_type} için API key girilmedi. Bu provider'ı kullanabilmek için bir API key girmelisiniz.`);
        return;
      }

      await axios.post(`${API}/save-ai-config`, configToSave);
      setAiConfig({ ...aiConfig, api_key: '' }); // UI'da key gösterme
      if (user) await fetchProvidersWithKeys(user.id);
      alert("Ayarlar kaydedildi!");
      setShowSettings(false);
    } catch (err) { alert("Kaydedilemedi."); }
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
      // Otomatik yeni sohbet oluştur
      if (user) {
        const fileName = result.path.split('/').pop() || 'Dosya';
        const res = await axios.post(`${API}/conversations`, { user_id: user.id, title: fileName });
        await fetchConversations(user.id);
        setActiveConvId(res.data.id);
        setMessages([]);
      }
    }
  };

  const toggleDir = async (dirPath: string) => {
    const next = new Set(expandedDirs);
    if (next.has(dirPath)) {
      next.delete(dirPath);
    } else {
      next.add(dirPath);
      if (!dirContents[dirPath]) {
        const entries = await ipc.invoke('read-directory', dirPath);
        setDirContents(prev => ({ ...prev, [dirPath]: entries || [] }));
      }
    }
    setExpandedDirs(next);
  };

  const openFile = async (filePath: string) => {
    if (!ipc) return;
    const result = await ipc.invoke('read-file', filePath);
    if (result) {
      setCode(result.content);
      setOpenedFilePath(result.path);
      // Otomatik yeni sohbet oluştur
      if (user) {
        const fileName = result.path.split('/').pop() || 'Dosya';
        const res = await axios.post(`${API}/conversations`, { user_id: user.id, title: fileName });
        await fetchConversations(user.id);
        setActiveConvId(res.data.id);
        setMessages([]);
      }
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
      if (user && !activeConvId) {
        const res = await axios.post(`${API}/conversations`, { user_id: user.id, title: file.name });
        await fetchConversations(user.id);
        setActiveConvId(res.data.id);
        setMessages([]);
      }
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

  const handleExportToUnity = async (codeString: string) => {
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
    const entries = await ipc.invoke('read-directory', workspacePath);
    setFileTree(entries || []);
    // Genişletilmiş dizinleri de yenile
    const newDirContents = { ...dirContents };
    for (const dir of expandedDirs) {
      try {
        const dirEntries = await ipc.invoke('read-directory', dir);
        newDirContents[dir] = dirEntries || [];
      } catch {}
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

    // Polling interval
    const progressInterval = setInterval(async () => {
      try {
        const res = await axios.get(`${API}/chat-progress/${targetConvId}`);
        if (res.data && res.data.length > 0) {
          setCurrentPlan(res.data);
        }
      } catch (e) {}
    }, 1000);

    try {
      const res = await axios.post(`${API}/chat`, {
        conversation_id: targetConvId,
        message: messageContent,
        language: lang,
        user_id: user.id,
        mode: appMode,
        use_kb: aiConfig.provider_type === 'kb'
      }, { timeout: 310000 }); // 310 saniye timeout (Opus yavaş olabilir)

      clearInterval(progressInterval);
      setCurrentPlan([]);

      // AI yanıtını ekle
      const aiMsg: Message = {
        id: Date.now() + 1,
        role: 'assistant',
        content: res.data.content,
        smells: res.data.static_results?.smells || [],
        timestamp: new Date().toISOString(),
        pipeline: res.data.pipeline || null
      };
      setMessages(prev => [...prev, aiMsg]);
      fetchConversations(user.id); // Başlık güncellenmiş olabilir
    } catch (err: any) {
      clearInterval(progressInterval);
      setCurrentPlan([]);
      
      const errorText = err.code === 'ECONNABORTED'
        ? '⏱️ Yanıt zaman aşımına uğradı. AI Sağlayıcısı kod üretirken veya analiz ederken çok uzun sürdü. Daha basit bir işlem deneyin.'
        : '❌ Bir hata oluştu. Backend çalışıyor mu kontrol edin.';
      const errorMsg: Message = {
        id: Date.now() + 1,
        role: 'assistant',
        content: errorText,
        smells: [],
        timestamp: new Date().toISOString()
      };
      setMessages(prev => [...prev, errorMsg]);
    }
    setLoading(false);
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

      setAuthForm({ username, password });
      setAuthNotice(null);

      const url = authMode === 'login' ? '/login' : '/register';
      try {
        const res = await axios.post(`${API}${url}`, { username, password });
        if (authMode === 'login') {
          const userData = { id: res.data.user_id, name: res.data.username, sessionToken: res.data.session_token };
          setSessionTokenHeader(userData.sessionToken);
          setUser(userData);
          setAuthNotice(null);
          if (rememberMe) {
            localStorage.setItem('unityArchitectUser', JSON.stringify(userData));
          }
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
      try {
        const res = await axios.get(`${API}/auth/${provider}/url`);
        const oauthUrl = res.data.url;
        const popup = window.open(oauthUrl, `${provider}_oauth`, 'width=500,height=700,menubar=no,toolbar=no');

        const handler = (event: MessageEvent) => {
          if (event.data?.type === 'oauth-success') {
            const userData = { id: event.data.user_id, name: event.data.username, sessionToken: event.data.session_token };
            setSessionTokenHeader(userData.sessionToken);
            setUser(userData);
            setAuthNotice(null);
            localStorage.setItem('unityArchitectUser', JSON.stringify(userData));
            window.removeEventListener('message', handler);
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
            
            {/* MODE TOGGLE */}
            <div className="flex bg-[#000000] p-1 rounded-lg border border-slate-800/50 hidden sm:flex">
              <button 
                onClick={() => setAppMode('analysis')}
                className={`flex items-center gap-1.5 px-3 py-1 rounded text-[11px] font-semibold transition-all ${appMode === 'analysis' ? 'bg-blue-600/20 text-blue-400' : 'text-slate-500 hover:text-slate-300'}`}
              >
                🔍 Kodu İncele
              </button>
              <button 
                onClick={() => setAppMode('generation')}
                className={`flex items-center gap-1.5 px-3 py-1 rounded text-[11px] font-semibold transition-all ${appMode === 'generation' ? 'bg-emerald-600/20 text-emerald-400' : 'text-slate-500 hover:text-slate-300'}`}
              >
                ✨ Sıfırdan Üret
              </button>
            </div>

            {appMode === 'analysis' && (
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
            )}
          </div>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1.5 bg-[#000000] border border-slate-800 rounded-lg px-3 py-1.5">
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
          
          {appMode === 'generation' ? (
            <div className="flex-1 flex flex-col items-center justify-center text-slate-600 gap-4 bg-[#000000]">
              <div className="bg-emerald-500/10 border border-emerald-500/20 p-6 rounded-3xl">
                <Sparkles size={48} className="text-emerald-500/50" />
              </div>
              <div className="text-center">
                <h3 className="text-lg font-bold text-slate-300">Sıfırdan Kod Üretim Modu</h3>
                <p className="text-[13px] text-slate-500 mt-2 max-w-sm">
                  Bu modda kod yapıştırmanıza gerek yok. Sadece sağ taraftaki sohbet alanından ne istediğinizi (örn: "Basit bir Karakter Kontrolcüsü yaz") söyleyin. Mimar ajanımız oyun hissiyatını (Game Feel) gözeterek sizin için en uygun C# mimarisini kurup yazıp teslim edecektir.
                </p>
              </div>
            </div>
          ) : (
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
                      Analiz için Unity kodunuzu buraya yapıştırın
                    </p>
                    <p className="text-[12px] text-slate-600">
                      veya bir .cs dosyasını bu alana sürükleyip bırakın
                    </p>
                  </div>
                  <div className="mt-10 flex gap-6 text-[10px] font-mono text-slate-700 font-semibold uppercase tracking-widest pointer-events-none">
                    <span className="flex items-center gap-1.5"><Activity size={14}/> Statik Analiz</span>
                    <span className="flex items-center gap-1.5"><Cpu size={14}/> Mimari Değerlendirme</span>
                    <span className="flex items-center gap-1.5"><Sparkles size={14}/> Best Practices</span>
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
                        className={`w-8 h-8 rounded-full flex items-center justify-center transition-all shadow-lg backdrop-blur-md border ${
                          includeEditorCode 
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
                  theme="vs-dark"
                  value={code}
                  onChange={(val) => setCode(val || '')}
                  onMount={(editor, monaco) => {
                    // 1. Tema Özelleştirmesi (Siyah arkaplana tam uyuşum)
                    monaco.editor.defineTheme('unityArchitectDark', {
                      base: 'vs-dark',
                      inherit: true,
                      rules: [
                        { token: 'class', foreground: '4EC9B0' },
                        { token: 'method', foreground: 'DCDCAA' },
                        { token: 'property', foreground: '9CDCFE' }
                      ],
                      colors: {
                        'editor.background': '#000000',
                        'editorLineNumber.foreground': '#334155',
                      }
                    });
                    monaco.editor.setTheme('unityArchitectDark');

                    // 2. Muazzam C# Semantic Tokenizer (VS Code Dark+ Taklidi)
                    // C# Monarch tokenları Unity class'larını ve IEnumerator'u renklendiremediği için 
                    // bu custom kod Semantic Tokenlar ekleyerek Sınıfları Cyan, Metotları Sarı yapıyor.
                    monaco.languages.registerDocumentSemanticTokensProvider('csharp', {
                      getLegend: function () {
                        return { tokenTypes: ['class', 'method', 'property'], tokenModifiers: [] };
                      },
                      provideDocumentSemanticTokens: function (model, lastResultId, token) {
                        const lines = model.getLinesContent();
                        const data: number[] = [];
                        let prevLine = 0; let prevChar = 0;

                        for (let i = 0; i < lines.length; i++) {
                          const line = lines[i];
                          const tokensInLine: { index: number, length: number, type: number }[] = [];
                          
                          // Metotlar (Örn: GetComponent, SendMessage) -> Yellow
                          const methodRegex = /\b([a-zA-Z_]\w*)\s*\(/g;
                          let match;
                          while ((match = methodRegex.exec(line)) !== null) {
                            const word = match[1];
                            if (!['if', 'while', 'for', 'switch', 'catch', 'typeof', 'sizeof'].includes(word)) {
                              tokensInLine.push({ index: match.index, length: word.length, type: 1 });
                            }
                          }
                          
                          // Sınıflar (Örn: ZombieEnemy, Rigidbody, IEnumerator) -> Cyan
                          const classRegex = /\b([A-Z][a-zA-Z0-9_]*)\b/g;
                          while ((match = classRegex.exec(line)) !== null) {
                            const word = match[1];
                            if (!tokensInLine.some(t => t.index === match.index)) {
                               tokensInLine.push({ index: match.index, length: word.length, type: 0 });
                            }
                          }

                          // Property/Değişkenler (Örn: speed, player, rb) -> Light Blue
                          const propRegex = /\b([a-z_][a-zA-Z0-9_]*)\b/g;
                          const keywords = ['public','private','protected','class','void','float','int','bool','var','new','return','if','else','while','for','foreach','in','using','namespace','yield', 'true', 'false', 'null', 'string'];
                          while ((match = propRegex.exec(line)) !== null) {
                            const word = match[1];
                            if (!keywords.includes(word) && !tokensInLine.some(t => t.index === match.index)) {
                               tokensInLine.push({ index: match.index, length: word.length, type: 2 });
                            }
                          }

                          tokensInLine.sort((a, b) => a.index - b.index);
                          
                          for (const t of tokensInLine) {
                            const deltaLine = i - prevLine;
                            const deltaStart = deltaLine === 0 ? t.index - prevChar : t.index;
                            data.push(deltaLine, deltaStart, t.length, t.type, 0);
                            prevLine = i; prevChar = t.index;
                          }
                        }
                        return { data: new Uint32Array(data) };
                      },
                      releaseDocumentSemanticTokens: function (resultId) {}
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
            </div>
          )}
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
            <ModelAvatar provider={aiConfig.provider_type} size={14} />
            {/* MODEL SELECTOR DROPDOWN */}
            <div className="relative">
              <button
                onClick={() => { setIsModelDropdownOpen(!isModelDropdownOpen); if (!isModelDropdownOpen) fetchAvailableModels(); }}
                className="flex items-center gap-1.5 hover:bg-slate-800 px-2 py-1 rounded transition-all text-left"
              >
                <div className="flex flex-col">
                  <span className="text-[12px] font-semibold text-slate-300 leading-tight">
                    {aiConfig.model_name || 'Model Seçin'}
                  </span>
                  <span className="text-[9px] text-slate-500 leading-tight capitalize">
                    {aiConfig.provider_type}
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
                      className="absolute top-10 left-0 w-64 bg-[#000000] border border-slate-700 shadow-2xl rounded-xl z-50 overflow-hidden"
                    >
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
                              const hasKey = providersWithKeys.includes(m.provider);
                              return (
                              <button
                                key={m.id}
                                onClick={async () => {
                                  if (!hasKey) {
                                    // Key yoksa settings'e yönlendir
                                    setAiConfig({ ...aiConfig, provider_type: m.provider, model_name: m.id });
                                    setIsModelDropdownOpen(false);
                                    setShowSettings(true);
                                    alert(`⚠️ ${m.provider.charAt(0).toUpperCase() + m.provider.slice(1)} için API key girilmedi.\nLütfen Ayarlar'dan API key'inizi girin.`);
                                    return;
                                  }
                                  const newCfg = { ...aiConfig, provider_type: m.provider, model_name: m.id };
                                  setAiConfig(newCfg);
                                  setIsModelDropdownOpen(false);
                                  if (user) await axios.post(`${API}/save-ai-config`, { ...newCfg, user_id: user.id });
                                }}
                                className={`w-full text-left px-3 py-2 text-[12px] flex items-center justify-between hover:bg-blue-600/10 rounded-lg transition-colors
                                  ${aiConfig.model_name === m.id ? 'bg-blue-600/10 text-blue-400' : 'text-slate-300'}`}
                              >
                                <div className="flex flex-col">
                                  <span className="font-medium">{m.name}</span>
                                  <span className="text-[10px] text-slate-500 capitalize">{m.provider}</span>
                                </div>
                                {hasKey ? (
                                  <span className="text-[9px] bg-emerald-500/20 text-emerald-400 px-1.5 py-0.5 rounded-full">Key ✓</span>
                                ) : (
                                  <span className="text-[9px] bg-amber-500/20 text-amber-400 px-1.5 py-0.5 rounded-full">Key Yok</span>
                                )}
                              </button>
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

                      {/* MULTI-AGENT TOGGLE (ONLY FOR ANTHROPIC) */}
                      {aiConfig.provider_type === 'anthropic' && (
                        <div className="px-3 py-2.5 border-t border-slate-800/80 bg-blue-900/10 flex items-center justify-between">
                          <div>
                            <p className="text-[11px] font-semibold text-blue-400">Multi-Agent Modu</p>
                            <p className="text-[9px] text-slate-500 mt-0.5">Mimar + Uzman + Eleştirmen</p>
                          </div>
                          <label className="relative inline-flex items-center cursor-pointer">
                            <input 
                              type="checkbox" 
                              className="sr-only" 
                              checked={aiConfig.use_multi_agent}
                              onChange={async (e) => {
                                const newCfg = { ...aiConfig, use_multi_agent: e.target.checked };
                                setAiConfig(newCfg);
                                if (user) await axios.post(`${API}/save-ai-config`, { ...newCfg, user_id: user.id });
                              }}
                            />
                            <div className={`w-9 h-5 rounded-full flex items-center transition-colors relative ${aiConfig.use_multi_agent ? 'bg-blue-500' : 'bg-slate-700'}`}>
                              <div className={`absolute w-3.5 h-3.5 bg-white rounded-full transition-transform ${aiConfig.use_multi_agent ? 'translate-x-[18px]' : 'translate-x-[3px]'}`}></div>
                            </div>
                          </label>
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
          <button
            onClick={() => setIsChatOpen(false)}
            className="p-1.5 hover:bg-slate-800 rounded-lg text-slate-500 transition-all"
          >
            <PanelRightClose size={16} />
          </button>
        </div>

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
            <div className="flex flex-col items-center justify-center h-full text-slate-600 gap-3">
              <Sparkles size={28} className="opacity-20 text-blue-500" />
              <div className="text-center">
                <p className="text-[12px] font-medium text-slate-400">Merhaba! 👋</p>
                <p className="text-[11px] text-slate-600 mt-1">
                  Unity kodunuzu ortadaki editöre yapıştırın,<br />
                  sonra buradan analiz isteyin.
                </p>
              </div>
            </div>
          ) : (
            <>
              {messages.map((msg, msgIdx) => (
                <div key={msg.id} className={`chat-message-enter ${msg.role === 'user' ? 'flex justify-end' : ''}`}>
                  {msg.role === 'assistant' ? (
                    // AI Mesajı
                    <div className="flex gap-2.5 max-w-full">
                      <ModelAvatar provider={aiConfig.provider_type} size={13} className="mt-0.5" />
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
                        {/* AI Yanıt İçeriği */}
                        <div className="prose prose-invert max-w-none text-[13px] leading-relaxed prose-p:my-2 prose-headings:my-3 prose-ul:my-2 prose-li:my-0.5">
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
                  <ModelAvatar provider={aiConfig.provider_type} size={13} />
                  <div className="flex-1 min-w-0">
                    {currentPlan.length > 0 && (
                      <div className="mb-4">
                        <AgentPlan tasks={currentPlan} />
                      </div>
                    )}
                    <div className="bg-[#000000] rounded-lg px-4 py-3 border border-slate-800 inline-block">
                      <div className="flex items-center gap-1.5">
                        <div className="typing-dot h-2 w-2 bg-blue-500 rounded-full" />
                        <div className="typing-dot h-2 w-2 bg-blue-500 rounded-full" />
                        <div className="typing-dot h-2 w-2 bg-blue-500 rounded-full" />
                      </div>
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
              placeholder={code.trim() ? "Bu kodu analiz et..." : "Unity hakkında bir şey sor..."}
              className="border-slate-800/50"
              includeEditorCode={includeEditorCode}
              onToggleIncludeCode={() => setIncludeEditorCode(!includeEditorCode)}
           />
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
    </div >
  );
}
