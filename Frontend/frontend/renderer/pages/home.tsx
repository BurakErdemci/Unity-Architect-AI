import React, { useState, useEffect, useRef } from 'react';
import Head from 'next/head';
import axios from 'axios';
import {
  Activity, AlertTriangle, CheckCircle, Code2, Cpu, Sparkles,
  Languages, ChevronDown, MessageSquare, Plus, FileText, Clock,
  Trash2, Edit3, ChevronLeft, ChevronRight, LogOut, User, Lock,
  Settings, X, Send, Bot, UserCircle, PanelRightClose, PanelRightOpen,
  FolderOpen, Folder, File, ChevronRight as ChevronR, Upload
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/cjs/styles/prism';

const API = 'http://127.0.0.1:8000';

// =====================================================================
//                          TIPLER
// =====================================================================
interface UserData { id: number; name: string; }
interface Conversation { id: number; title: string; created_at: string; updated_at: string; }
interface Message { id: number; role: string; content: string; smells: any[]; timestamp: string; }
interface FileEntry { name: string; path: string; isDirectory: boolean; extension: string; }

// IPC helper (Electron preload)
const ipc = typeof window !== 'undefined' ? (window as any).ipc : null;

// =====================================================================
//                       MARKDOWN RENDERER
// =====================================================================
const MarkdownRenderer = ({ content }: { content: string }) => (
  <ReactMarkdown
    remarkPlugins={[remarkGfm]}
    components={{
      code({ node, inline, className, children, ...props }: any) {
        const match = /language-(\w+)/.exec(className || '');
        return !inline && match ? (
          <SyntaxHighlighter
            style={vscDarkPlus}
            language={match[1]}
            PreTag="div"
            className="rounded-xl !bg-[#0a0c10] border border-slate-800 !my-4 shadow-lg"
            {...props}
          >
            {String(children).replace(/\n$/, '')}
          </SyntaxHighlighter>
        ) : (
          <code className="bg-blue-500/10 px-1.5 py-0.5 rounded text-blue-400 font-mono text-xs font-semibold" {...props}>
            {children}
          </code>
        );
      },
    }}
  >
    {content}
  </ReactMarkdown>
);

// =====================================================================
//                       ANA KOMPONENT
// =====================================================================
export default function HomePage() {
  // --- AUTH ---
  const [user, setUser] = useState<UserData | null>(null);
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login');
  const [authForm, setAuthForm] = useState({ username: '', password: '' });

  // --- CONVERSATIONS ---
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConvId, setActiveConvId] = useState<number | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);

  // --- UI STATE ---
  const [code, setCode] = useState('');
  const [chatInput, setChatInput] = useState('');
  const [lang, setLang] = useState('tr');
  const [loading, setLoading] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [isChatOpen, setIsChatOpen] = useState(true);
  const [sidebarTab, setSidebarTab] = useState<'chats' | 'files'>('chats');
  const [isDragging, setIsDragging] = useState(false);

  // --- FILE BROWSER ---
  const [rootFolderPath, setRootFolderPath] = useState<string | null>(null);
  const [fileTree, setFileTree] = useState<FileEntry[]>([]);
  const [expandedDirs, setExpandedDirs] = useState<Set<string>>(new Set());
  const [dirContents, setDirContents] = useState<Record<string, FileEntry[]>>({});
  const [openedFilePath, setOpenedFilePath] = useState<string | null>(null);

  // --- SETTINGS ---
  const [showSettings, setShowSettings] = useState(false);
  const [aiConfig, setAiConfig] = useState({
    provider_type: 'ollama', api_key: '', model_name: 'qwen2.5-coder:7b'
  });

  // --- EDITING ---
  const [editingId, setEditingId] = useState<number | null>(null);
  const [tempTitle, setTempTitle] = useState('');

  // --- REFS ---
  const chatEndRef = useRef<HTMLDivElement>(null);
  const chatInputRef = useRef<HTMLTextAreaElement>(null);

  // --- Auto scroll chat ---
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  // --- Fetch on login ---
  useEffect(() => {
    if (user) {
      fetchConversations(user.id);
      fetchAIConfig(user.id);
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
      if (res.data) setAiConfig(res.data);
    } catch (err) { console.error("Config hatası:", err); }
  };

  const handleAuth = async () => {
    const url = authMode === 'login' ? '/login' : '/register';
    try {
      const res = await axios.post(`${API}${url}`, authForm);
      if (authMode === 'login') {
        setUser({ id: res.data.user_id, name: res.data.username });
      } else {
        alert("Kayıt başarılı! Giriş yapabilirsiniz.");
        setAuthMode('login');
      }
    } catch (err: any) { alert(err.response?.data?.detail || "Auth hatası."); }
  };

  const saveAIConfig = async () => {
    try {
      await axios.post(`${API}/save-ai-config`, { ...aiConfig, user_id: user?.id });
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
      setRootFolderPath(folderPath);
      const entries = await ipc.invoke('read-directory', folderPath);
      setFileTree(entries || []);
      setExpandedDirs(new Set());
      setDirContents({});
      setSidebarTab('files');
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
      const text = await file.text();
      setCode(text);
      setOpenedFilePath(file.name);
      // Otomatik yeni sohbet oluştur
      if (user && !activeConvId) {
        const res = await axios.post(`${API}/conversations`, { user_id: user.id, title: file.name });
        await fetchConversations(user.id);
        setActiveConvId(res.data.id);
        setMessages([]);
      }
    }
  };

  const getFileIcon = (ext: string) => {
    const codeExts = ['.cs', '.js', '.ts', '.py', '.cpp', '.h', '.java'];
    if (codeExts.includes(ext)) return <Code2 size={13} className="text-blue-400" />;
    return <File size={13} className="text-slate-500" />;
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

  const sendMessage = async () => {
    if (!chatInput.trim() || !user || !activeConvId) return;

    // İlk mesajda kodu ekle, sonraki mesajlarda sadece chat gönder
    const isFirstMessage = messages.length === 0;
    const messageContent = (isFirstMessage && code.trim())
      ? `${chatInput}\n\n\`\`\`csharp\n${code}\n\`\`\``
      : chatInput.trim();

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

    try {
      const res = await axios.post(`${API}/chat`, {
        conversation_id: activeConvId,
        message: messageContent,
        language: lang,
        user_id: user.id
      }, { timeout: 130000 }); // 130 saniye timeout (Ollama yavaş olabilir)

      // AI yanıtını ekle
      const aiMsg: Message = {
        id: Date.now() + 1,
        role: 'assistant',
        content: res.data.content,
        smells: res.data.static_results?.smells || [],
        timestamp: new Date().toISOString()
      };
      setMessages(prev => [...prev, aiMsg]);
      fetchConversations(user.id); // Başlık güncellenmiş olabilir
    } catch (err: any) {
      const errorText = err.code === 'ECONNABORTED'
        ? '⏱️ Yanıt zaman aşımına uğradı. Ollama çok uzun sürdü. Daha kısa bir kod deneyin.'
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
  //                        GİRİŞ EKRANI
  // =====================================================================
  if (!user) {
    return (
      <div className="h-screen flex items-center justify-center bg-[#0e0e10] text-white">
        <Head><title>Unity Architect AI</title></Head>
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-[#18181b] p-10 rounded-2xl border border-slate-800/60 w-[420px] shadow-2xl"
        >
          <div className="flex flex-col items-center gap-4 mb-8 text-center">
            <div className="bg-gradient-to-br from-blue-600 to-violet-600 p-4 rounded-2xl shadow-lg shadow-blue-900/30">
              <Code2 size={36} />
            </div>
            <div>
              <h1 className="text-2xl font-extrabold tracking-tight">
                Unity Architect <span className="text-blue-500">AI</span>
              </h1>
              <p className="text-slate-500 text-[10px] font-semibold tracking-[0.3em] uppercase mt-1">
                Professional Code Auditor
              </p>
            </div>
          </div>
          <div className="space-y-3">
            <div className="relative group">
              <User className="absolute left-3.5 top-3.5 text-slate-600 group-focus-within:text-blue-500 transition-colors" size={16} />
              <input
                style={{ backgroundColor: '#0e0e10', color: 'white' }}
                className="w-full bg-[#0e0e10] border border-slate-800 p-3.5 pl-11 rounded-xl outline-none focus:border-blue-500/50 text-sm transition-colors"
                placeholder="Kullanıcı Adı"
                onChange={(e) => setAuthForm({ ...authForm, username: e.target.value })}
                onKeyDown={(e) => e.key === 'Enter' && handleAuth()}
              />
            </div>
            <div className="relative group">
              <Lock className="absolute left-3.5 top-3.5 text-slate-600 group-focus-within:text-blue-500 transition-colors" size={16} />
              <input
                style={{ backgroundColor: '#0e0e10', color: 'white' }}
                type="password"
                className="w-full bg-[#0e0e10] border border-slate-800 p-3.5 pl-11 rounded-xl outline-none focus:border-blue-500/50 text-sm transition-colors"
                placeholder="Şifre"
                onChange={(e) => setAuthForm({ ...authForm, password: e.target.value })}
                onKeyDown={(e) => e.key === 'Enter' && handleAuth()}
              />
            </div>
            <button
              onClick={handleAuth}
              className="w-full bg-blue-600 hover:bg-blue-500 text-white p-3.5 rounded-xl font-bold text-xs tracking-wide transition-all active:scale-[0.98] uppercase mt-1"
            >
              {authMode === 'login' ? 'Oturum Aç' : 'Kayıt Ol'}
            </button>
            <button
              onClick={() => setAuthMode(authMode === 'login' ? 'register' : 'login')}
              className="w-full text-[11px] font-medium text-slate-500 hover:text-blue-400 transition-colors py-1"
            >
              {authMode === 'login' ? "Hesabın yok mu? Kaydol" : "Zaten üye misin? Giriş yap"}
            </button>
          </div>
        </motion.div>
      </div>
    );
  }

  // =====================================================================
  //                       ANA UYGULAMA
  // =====================================================================
  return (
    <div className="flex h-screen bg-[#0e0e10] text-slate-200 font-sans overflow-hidden">
      <Head><title>Unity Architect AI | {user.name}</title></Head>

      {/* =================== SETTINGS MODAL =================== */}
      <AnimatePresence>
        {showSettings && (
          <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-[100]">
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="bg-[#18181b] border border-slate-800 rounded-2xl p-6 max-w-md w-full shadow-2xl"
            >
              <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-2.5">
                  <div className="p-1.5 bg-blue-500/10 rounded-lg text-blue-500"><Settings size={18} /></div>
                  <h2 className="text-base font-bold text-white">AI Yapılandırması</h2>
                </div>
                <button onClick={() => setShowSettings(false)} className="p-1.5 hover:bg-slate-800 rounded-lg transition-colors text-slate-400">
                  <X size={18} />
                </button>
              </div>
              <div className="space-y-4">
                <div>
                  <label className="block text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1.5">Provider</label>
                  <select
                    style={{ backgroundColor: '#0e0e10', color: 'white' }}
                    value={aiConfig.provider_type}
                    onChange={e => setAiConfig({ ...aiConfig, provider_type: e.target.value })}
                    className="w-full bg-[#0e0e10] border border-slate-800 rounded-xl p-3 text-white text-sm outline-none focus:border-blue-500 transition-colors"
                  >
                    <option value="ollama">Ollama (Yerel)</option>
                    <option value="openai">OpenAI (Bulut)</option>
                    <option value="google">Google Gemini (Bulut)</option>
                    <option value="deepseek">DeepSeek (Reasoning)</option>
                  </select>
                </div>
                {aiConfig.provider_type !== 'ollama' && (
                  <div>
                    <label className="block text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1.5">API Key</label>
                    <input
                      style={{ backgroundColor: '#0e0e10', color: 'white' }}
                      type="password"
                      value={aiConfig.api_key}
                      onChange={e => setAiConfig({ ...aiConfig, api_key: e.target.value })}
                      className="w-full bg-[#0e0e10] border border-slate-800 rounded-xl p-3 text-white text-sm outline-none focus:border-blue-500 transition-colors"
                      placeholder="sk-..."
                    />
                  </div>
                )}
                <div>
                  <label className="block text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1.5">Model İsmi</label>
                  <input
                    style={{ backgroundColor: '#0e0e10', color: 'white' }}
                    value={aiConfig.model_name}
                    onChange={e => setAiConfig({ ...aiConfig, model_name: e.target.value })}
                    className="w-full bg-[#0e0e10] border border-slate-800 rounded-xl p-3 text-white text-sm outline-none focus:border-blue-500 transition-colors"
                    placeholder="qwen2.5-coder:7b"
                  />
                </div>
                <button
                  onClick={saveAIConfig}
                  className="w-full bg-blue-600 hover:bg-blue-500 text-white p-3 rounded-xl font-bold text-xs tracking-wide transition-all"
                >
                  KAYDET
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* =================== SOL SIDEBAR =================== */}
      <motion.aside
        animate={{ width: isSidebarOpen ? 260 : 0, opacity: isSidebarOpen ? 1 : 0 }}
        transition={{ duration: 0.2 }}
        className="bg-[#18181b] border-r border-slate-800/50 flex flex-col overflow-hidden z-20 shrink-0"
      >
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
                          style={{ backgroundColor: '#0e0e10', color: 'white' }}
                          className="bg-[#0e0e10] text-white text-xs w-full px-2 py-1 rounded border border-blue-500 outline-none"
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
                  <File size={13} /> Dosya Aç
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
            <button onClick={() => setUser(null)} className="p-2 hover:bg-red-950/30 text-slate-500 hover:text-red-400 rounded-lg transition-all">
              <LogOut size={14} />
            </button>
          </div>
        </div>
      </motion.aside>

      {/* =================== ORTA: KOD EDİTÖRÜ =================== */}
      <div className="flex-1 flex flex-col min-w-0 border-r border-slate-800/50">
        {/* Editor Header */}
        <div className="h-11 border-b border-slate-800/50 flex items-center justify-between px-4 bg-[#18181b]/50 shrink-0">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setIsSidebarOpen(!isSidebarOpen)}
              className="p-1.5 hover:bg-slate-800 rounded-lg text-slate-500 transition-all"
            >
              {isSidebarOpen ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
            </button>
            <div className="flex items-center gap-2">
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
            <div className="flex items-center gap-1.5 bg-[#0e0e10] border border-slate-800 rounded-lg px-3 py-1.5">
              <Languages size={12} className="text-blue-500" />
              <select
                value={lang}
                onChange={(e) => setLang(e.target.value)}
                className="bg-transparent text-slate-300 text-[11px] font-medium outline-none cursor-pointer border-none appearance-none"
                style={{ backgroundColor: 'transparent', color: '#cbd5e1' }}
              >
                <option value="tr" className="bg-[#0e0e10]">TR</option>
                <option value="en" className="bg-[#0e0e10]">EN</option>
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
                <span className="text-[13px] font-semibold text-blue-400">Dosyayı bırakın</span>
              </div>
            </div>
          )}
          {(activeConvId || code || openedFilePath) ? (
            <textarea
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder={'// Unity C# kodunuzu buraya yapıştırın...\n// veya dosya sürükleyip bırakın\n// Kod yapıştırıp sağdaki chat\'ten analiz isteyin.'}
              className="flex-1 bg-[#0e0e10] p-5 font-mono text-[13px] leading-relaxed outline-none resize-none text-slate-300 placeholder:text-slate-700"
              spellCheck={false}
            />
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-slate-600 gap-4">
              <div className="bg-slate-800/20 p-6 rounded-2xl">
                <Code2 size={48} className="opacity-20" />
              </div>
              <div className="text-center">
                <p className="text-[13px] font-medium text-slate-500">Unity Architect AI</p>
                <p className="text-[11px] text-slate-600 mt-1">
                  Yeni bir sohbet oluşturun veya mevcut bir sohbeti seçin
                </p>
              </div>
              <button
                onClick={() => createNewConversation()}
                className="mt-2 bg-blue-600 hover:bg-blue-500 text-white px-5 py-2.5 rounded-xl text-[11px] font-semibold transition-all flex items-center gap-2"
              >
                <Plus size={14} /> Yeni Sohbet
              </button>
            </div>
          )}
        </div>{/* end drag-drop wrapper */}
      </div>

      {/* =================== SAĞ: AI CHAT PANELİ =================== */}
      <motion.div
        animate={{ width: isChatOpen ? 420 : 0, opacity: isChatOpen ? 1 : 0 }}
        transition={{ duration: 0.2 }}
        className="bg-[#18181b] flex flex-col overflow-hidden shrink-0"
      >
        {/* Chat Header */}
        <div className="h-11 border-b border-slate-800/50 flex items-center justify-between px-4 min-w-[420px] shrink-0">
          <div className="flex items-center gap-2">
            <div className="h-6 w-6 bg-gradient-to-br from-blue-500 to-violet-500 rounded-md flex items-center justify-center">
              <Bot size={13} className="text-white" />
            </div>
            <span className="text-[12px] font-semibold text-slate-300">AI Architect</span>
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
              {messages.map((msg) => (
                <div key={msg.id} className={`chat-message-enter ${msg.role === 'user' ? 'flex justify-end' : ''}`}>
                  {msg.role === 'assistant' ? (
                    // AI Mesajı
                    <div className="flex gap-2.5 max-w-full">
                      <div className="h-6 w-6 bg-gradient-to-br from-blue-500 to-violet-500 rounded-md flex items-center justify-center shrink-0 mt-0.5">
                        <Bot size={13} className="text-white" />
                      </div>
                      <div className="flex-1 min-w-0">
                        {/* Statik Bulgular */}
                        {msg.smells && msg.smells.length > 0 && (
                          <div className="mb-3 bg-[#0e0e10] rounded-lg border border-orange-500/20 p-3">
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
                        {/* AI Yanıt İçeriği */}
                        <div className="prose prose-invert max-w-none text-[13px] leading-relaxed prose-p:my-2 prose-headings:my-3 prose-ul:my-2 prose-li:my-0.5">
                          <MarkdownRenderer content={msg.content} />
                        </div>
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
                <div className="flex gap-2.5 chat-message-enter">
                  <div className="h-6 w-6 bg-gradient-to-br from-blue-500 to-violet-500 rounded-md flex items-center justify-center shrink-0">
                    <Bot size={13} className="text-white" />
                  </div>
                  <div className="bg-[#0e0e10] rounded-lg px-4 py-3 border border-slate-800">
                    <div className="flex items-center gap-1.5">
                      <div className="typing-dot h-2 w-2 bg-blue-500 rounded-full" />
                      <div className="typing-dot h-2 w-2 bg-blue-500 rounded-full" />
                      <div className="typing-dot h-2 w-2 bg-blue-500 rounded-full" />
                    </div>
                  </div>
                </div>
              )}
              <div ref={chatEndRef} />
            </>
          )}
        </div>

        {/* Chat Input */}
        {activeConvId && (
          <div className="p-3 border-t border-slate-800/50 min-w-[420px] shrink-0">
            {!code.trim() ? (
              /* Dosya yüklenmemiş — uyarı göster */
              <div className="bg-[#0e0e10] border border-slate-800/60 rounded-xl px-4 py-3 flex items-center gap-3">
                <Upload size={16} className="text-slate-600 shrink-0" />
                <span className="text-[12px] text-slate-500 flex-1">Önce bir C# dosyası yükleyin</span>
                <button
                  onClick={openFilePicker}
                  className="text-[10px] bg-blue-600/20 text-blue-400 px-3 py-1.5 rounded-lg hover:bg-blue-600/30 font-semibold transition-colors"
                >
                  Dosya Seç
                </button>
              </div>
            ) : (
              /* Dosya yüklü — file chip + chat input */
              <div className="bg-[#0e0e10] border border-slate-800 rounded-xl transition-colors focus-within:border-blue-500/30">
                {/* File Chip */}
                <div className="px-3 pt-2.5 pb-1">
                  <div className="inline-flex items-center gap-2 bg-slate-800/60 border border-slate-700/50 rounded-lg px-2.5 py-1.5 max-w-[280px] group">
                    <Code2 size={13} className="text-blue-400 shrink-0" />
                    <span className="text-[11px] text-slate-300 font-medium truncate">
                      {openedFilePath ? openedFilePath.split('/').pop() : 'kod.cs'}
                    </span>
                    <span className="text-[9px] text-slate-600 font-mono">
                      {code.split('\n').length} satır
                    </span>
                    <button
                      onClick={() => { setCode(''); setOpenedFilePath(null); }}
                      className="p-0.5 hover:bg-slate-600 rounded text-slate-500 hover:text-slate-300 opacity-0 group-hover:opacity-100 transition-all"
                    >
                      <X size={10} />
                    </button>
                  </div>
                </div>
                {/* Chat textarea */}
                <div className="flex items-end">
                  <textarea
                    ref={chatInputRef}
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder={messages.length === 0 ? 'Bu kodu analiz et...' : 'Devam mesajı yazın...'}
                    rows={1}
                    className="flex-1 bg-transparent px-3.5 py-2.5 text-[13px] outline-none resize-none text-slate-200 placeholder:text-slate-600 max-h-32"
                    style={{ color: 'white' }}
                  />
                  <button
                    onClick={sendMessage}
                    disabled={loading || !chatInput.trim()}
                    className="p-2.5 m-1 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:bg-slate-800 disabled:text-slate-600 text-white transition-all"
                  >
                    <Send size={14} />
                  </button>
                </div>
              </div>
            )}
          </div>
        )
        }
      </motion.div >

      {/* Chat panel toggle (when closed) */}
      {
        !isChatOpen && (
          <button
            onClick={() => setIsChatOpen(true)}
            className="absolute right-3 top-3 p-2 bg-[#18181b] border border-slate-800 rounded-lg text-slate-400 hover:text-blue-500 hover:border-blue-500/30 transition-all z-30"
          >
            <PanelRightOpen size={16} />
          </button>
        )
      }
    </div >
  );
}