import React, { useState, useEffect } from 'react';
import Head from 'next/head';
import axios from 'axios';
import { 
  Activity, AlertTriangle, CheckCircle, Code2, Cpu, Sparkles, 
  Languages, ChevronDown, History, Plus, FileText, Clock, 
  Trash2, Edit3, ChevronLeft, ChevronRight, LogOut, User, Lock, Settings, X, Save
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/cjs/styles/prism';

export default function HomePage() {
  // --- AUTH STATELERİ ---
  const [user, setUser] = useState<{id: number, name: string} | null>(null);
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login');
  const [authForm, setAuthForm] = useState({ username: '', password: '' });

  // --- UYGULAMA STATELERİ ---
  const [code, setCode] = useState('');
  const [lang, setLang] = useState('tr');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  
  // --- AYARLAR VE DÜZENLEME STATELERİ ---
  const [showSettings, setShowSettings] = useState(false);
  const [aiConfig, setAiConfig] = useState({
    provider_type: 'ollama',
    api_key: '',
    model_name: 'qwen2.5-coder:7b'
  });
  const [editingId, setEditingId] = useState<number | null>(null);
  const [tempTitle, setTempTitle] = useState('');

  // Başlangıç verilerini çek
  useEffect(() => {
    if (user) {
      fetchHistory(user.id);
      fetchAIConfig(user.id);
    }
  }, [user]);

  const fetchHistory = async (userId: number) => {
    try {
      const res = await axios.get(`http://127.0.0.1:8000/history/${userId}`);
      setHistory(res.data);
    } catch (err) { console.error("Geçmiş hatası:", err); }
  };

  const fetchAIConfig = async (userId: number) => {
    try {
      const res = await axios.get(`http://127.0.0.1:8000/get-ai-config/${userId}`);
      if (res.data) setAiConfig(res.data);
    } catch (err) { console.error("Config hatası:", err); }
  };

  const handleAuth = async () => {
    const url = authMode === 'login' ? '/login' : '/register';
    try {
      const res = await axios.post(`http://127.0.0.1:8000${url}`, authForm);
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
      await axios.post(`http://127.0.0.1:8000/save-ai-config`, { ...aiConfig, user_id: user?.id });
      alert("Ayarlar kaydedildi!");
      setShowSettings(false);
    } catch (err) { alert("Kaydedilemedi."); }
  };

  const analyzeCode = async () => {
    if (!code || !user) return;
    setLoading(true);
    setResult(null);
    try {
      const res = await axios.post('http://127.0.0.1:8000/analyze', { 
        code, language: lang, user_id: user.id 
      });
      setResult(res.data);
      fetchHistory(user.id); 
    } catch (error) { alert("Analiz hatası."); }
    setLoading(false);
  };

  const loadHistoryItem = async (id: number) => {
    if (editingId) return;
    setLoading(true);
    try {
      const res = await axios.get(`http://127.0.0.1:8000/analysis-detail/${id}`);
      setCode(res.data.code);
      setResult({ ai_suggestion: res.data.suggestion, static_results: { smells: res.data.smells } });
    } catch (err) { alert("Detay hatası."); }
    setLoading(false);
  };

  const deleteHistoryItem = async (e: React.MouseEvent, id: number) => {
    e.stopPropagation();
    if (confirm("Silinsin mi?")) {
      await axios.delete(`http://127.0.0.1:8000/history/${id}`);
      fetchHistory(user!.id);
      setResult(null);
    }
  };

  const saveRename = async (id: number) => {
    if (!tempTitle.trim()) { setEditingId(null); return; }
    await axios.put(`http://127.0.0.1:8000/history/${id}`, { title: tempTitle });
    setEditingId(null);
    fetchHistory(user!.id);
  };

  // --- GİRİŞ EKRANI UI ---
  if (!user) {
    return (
      <div className="h-screen flex items-center justify-center bg-[#0a0c10] text-white">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="bg-[#0d1117] p-12 rounded-[40px] border border-slate-800 w-[450px] shadow-2xl relative">
          <div className="flex flex-col items-center gap-6 mb-10 text-center">
            <div className="bg-blue-600 p-5 rounded-3xl shadow-lg shadow-blue-900/40 rotate-3"><Code2 size={48} /></div>
            <h1 className="text-3xl font-black tracking-tighter uppercase italic">Unity Architect <span className="text-blue-500">AI</span></h1>
            <p className="text-slate-500 text-[10px] font-bold tracking-[0.4em] uppercase">Professional Code Auditor</p>
          </div>
          <div className="space-y-4">
            <div className="relative group">
                <User className="absolute left-4 top-4 text-slate-600 group-focus-within:text-blue-500" size={18} />
                <input style={{backgroundColor: '#161b22', color: 'white'}} className="w-full bg-[#161b22] border border-slate-800 p-4 pl-12 rounded-2xl outline-none focus:border-blue-500/50 text-sm" placeholder="Kullanıcı Adı" onChange={(e) => setAuthForm({...authForm, username: e.target.value})} />
            </div>
            <div className="relative group">
                <Lock className="absolute left-4 top-4 text-slate-600 group-focus-within:text-blue-500" size={18} />
                <input style={{backgroundColor: '#161b22', color: 'white'}} type="password" className="w-full bg-[#161b22] border border-slate-800 p-4 pl-12 rounded-2xl outline-none focus:border-blue-500/50 text-sm" placeholder="Şifre" onChange={(e) => setAuthForm({...authForm, password: e.target.value})} />
            </div>
            <button onClick={handleAuth} className="w-full bg-blue-600 hover:bg-blue-500 text-white p-4 rounded-2xl font-black text-xs tracking-widest transition-all active:scale-95 uppercase mt-2">
              {authMode === 'login' ? 'Oturum Aç' : 'Kayıt Ol'}
            </button>
            <button onClick={() => setAuthMode(authMode === 'login' ? 'register' : 'login')} className="w-full text-[10px] font-bold text-slate-500 hover:text-blue-400 uppercase tracking-widest transition-colors py-2">
              {authMode === 'login' ? "Hesabın yok mu? Kaydol" : "Zaten üye misin? Giriş yap"}
            </button>
          </div>
        </motion.div>
      </div>
    );
  }

  // --- ANA UYGULAMA UI ---
  return (
    <div className="flex h-screen bg-[#0a0c10] text-slate-200 font-sans overflow-hidden">
      <Head><title>Unity Architect AI | {user.name}</title></Head>

      {/* --- SETTINGS MODAL --- */}
      <AnimatePresence>
        {showSettings && (
          <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-[100] p-4">
            <motion.div initial={{ scale: 0.9, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.9, opacity: 0 }} className="bg-[#0d1117] border border-slate-800 rounded-[32px] p-8 max-w-lg w-full shadow-2xl">
              <div className="flex items-center justify-between mb-8">
                <div className="flex items-center gap-3">
                    <div className="p-2 bg-blue-500/10 rounded-lg text-blue-500"><Settings size={20}/></div>
                    <h2 className="text-xl font-black text-white uppercase tracking-tight">AI Yapılandırması</h2>
                </div>
                <button onClick={() => setShowSettings(false)} className="p-2 hover:bg-slate-800 rounded-full transition-colors"><X size={20} /></button>
              </div>

              <div className="space-y-6">
                <div>
                  <label className="block text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">Provider</label>
                  <select 
                    style={{backgroundColor: '#161b22', color: 'white'}}
                    value={aiConfig.provider_type} 
                    onChange={e => setAiConfig({...aiConfig, provider_type: e.target.value})}
                    className="w-full bg-[#161b22] border border-slate-800 rounded-xl p-3 text-white text-sm outline-none focus:border-blue-500"
                  >
                    <option value="ollama">Ollama (Yerel)</option>
                    <option value="openai">OpenAI (Bulut)</option>
                    <option value="google">Google Gemini (Bulut)</option>
                    <option value="deepseek">DeepSeek (Reasoning)</option>
                  </select>
                </div>

                {aiConfig.provider_type !== 'ollama' && (
                  <div>
                    <label className="block text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">API Key</label>
                    <input style={{backgroundColor: '#161b22', color: 'white'}} type="password" value={aiConfig.api_key} onChange={e => setAiConfig({...aiConfig, api_key: e.target.value})} className="w-full bg-[#161b22] border border-slate-800 rounded-xl p-3 text-white text-sm outline-none focus:border-blue-500" placeholder="sk-..." />
                  </div>
                )}

                <div>
                  <label className="block text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">Model İsmi</label>
                  <input style={{backgroundColor: '#161b22', color: 'white'}} value={aiConfig.model_name} onChange={e => setAiConfig({...aiConfig, model_name: e.target.value})} className="w-full bg-[#161b22] border border-slate-800 rounded-xl p-3 text-white text-sm outline-none focus:border-blue-500" placeholder="qwen2.5-coder:7b" />
                </div>

                <button onClick={saveAIConfig} className="w-full bg-blue-600 hover:bg-blue-500 text-white p-4 rounded-2xl font-black text-xs tracking-widest transition-all shadow-xl shadow-blue-900/20">
                  AYARLARI KAYDET
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* --- SIDEBAR --- */}
      <motion.aside animate={{ width: isSidebarOpen ? 300 : 0, opacity: isSidebarOpen ? 1 : 0 }} className="bg-[#0d1117] border-r border-slate-800 flex flex-col relative overflow-hidden z-20">
        <div className="p-6 border-b border-slate-800 flex items-center justify-between min-w-[300px]">
          <div className="flex items-center gap-3">
            <History size={16} className="text-blue-500" />
            <span className="font-black text-[10px] tracking-widest uppercase text-slate-500">History</span>
          </div>
          <button onClick={() => { setCode(''); setResult(null); }} className="p-2 hover:bg-blue-600/10 text-blue-500 rounded-lg transition-all"><Plus size={18} /></button>
        </div>

        <div className="flex-1 overflow-y-auto custom-scrollbar p-3 space-y-2 min-w-[300px]">
          {history.map((item) => (
            <div key={item.id} onClick={() => loadHistoryItem(item.id)} className={`group relative p-4 rounded-2xl border transition-all cursor-pointer ${editingId === item.id ? 'bg-blue-600/10 border-blue-500/40' : 'border-transparent hover:bg-slate-800/40'}`}>
               <div className="flex items-start gap-3">
                  <FileText size={14} className={editingId === item.id ? "text-blue-500 mt-1" : "text-slate-500 mt-1"} />
                  <div className="flex-1 overflow-hidden pr-6">
                    {editingId === item.id ? (
                        <input autoFocus style={{backgroundColor: '#1e2227', color: 'white'}} className="bg-[#1e2227] text-white text-xs w-full px-2 py-1 rounded border border-blue-500 outline-none" value={tempTitle} onChange={e => setTempTitle(e.target.value)} onBlur={() => saveRename(item.id)} onKeyDown={e => e.key === 'Enter' && saveRename(item.id)} onClick={e => e.stopPropagation()} />
                    ) : (
                        <div className="text-[13px] font-bold text-slate-300 truncate group-hover:text-white transition-colors">{item.title}</div>
                    )}
                    <div className="text-[9px] text-slate-600 mt-1 uppercase tracking-tighter flex items-center gap-1 font-mono">
                      <Clock size={10}/> {item.timestamp}
                    </div>
                  </div>
               </div>
               {editingId !== item.id && (
                <div className="absolute right-2 top-4 flex gap-1 opacity-0 group-hover:opacity-100 transition-all">
                  <button onClick={(e) => { e.stopPropagation(); setEditingId(item.id); setTempTitle(item.title); }} className="p-1.5 hover:bg-slate-700 rounded-lg text-slate-400"><Edit3 size={12} /></button>
                  <button onClick={(e) => deleteHistoryItem(e, item.id)} className="p-1.5 hover:bg-red-900/40 rounded-lg text-slate-400 hover:text-red-500"><Trash2 size={12} /></button>
                </div>
               )}
            </div>
          ))}
        </div>

        <div className="p-4 bg-[#0d1117] border-t border-slate-800 flex items-center justify-between min-w-[300px]">
            <div className="flex items-center gap-3">
                <div className="h-9 w-9 bg-gradient-to-br from-blue-600 to-indigo-700 rounded-xl flex items-center justify-center font-black text-xs text-white shadow-lg">{user.name[0].toUpperCase()}</div>
                <div className="flex flex-col">
                  <span className="text-[11px] font-black text-slate-300 uppercase tracking-tighter">{user.name}</span>
                  <span className="text-[8px] text-green-500 font-bold tracking-widest uppercase">Verified Expert</span>
                </div>
            </div>
            <div className="flex gap-1">
              <button onClick={() => setShowSettings(true)} className="p-2.5 hover:bg-slate-800 text-slate-500 hover:text-white rounded-xl transition-all"><Settings size={16} /></button>
              <button onClick={() => setUser(null)} className="p-2.5 hover:bg-red-950/20 text-slate-500 hover:text-red-500 rounded-xl transition-all"><LogOut size={16} /></button>
            </div>
        </div>
      </motion.aside>

      <main className="flex-1 flex flex-col min-w-0 bg-[#0a0c10] relative">
        <header className="h-16 border-b border-slate-800/50 flex items-center justify-between px-8 bg-[#0a0c10]/40 backdrop-blur-xl z-10">
          <div className="flex items-center gap-4">
            <button onClick={() => setIsSidebarOpen(!isSidebarOpen)} className="p-2 hover:bg-slate-800 rounded-xl text-slate-400 border border-transparent hover:border-slate-700 transition-all">
                {isSidebarOpen ? <ChevronLeft size={20} /> : <ChevronRight size={20} />}
            </button>
            <h1 className="text-lg font-black tracking-tighter text-white uppercase italic">Unity Architect <span className="text-blue-500">AI</span></h1>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 bg-slate-900 border border-slate-800 rounded-xl px-4 py-2 shadow-inner">
              <Languages size={14} className="text-blue-500" />
              <select 
                value={lang} 
                onChange={(e) => setLang(e.target.value)} 
                className="bg-transparent text-slate-200 text-[10px] font-black outline-none cursor-pointer border-none appearance-none uppercase pr-2"
                style={{ backgroundColor: 'transparent', color: '#e2e8f0' }}
              >
                <option value="tr" className="bg-[#0d1117]">TR</option>
                <option value="en" className="bg-[#0d1117]">EN</option>
              </select>
            </div>
            <Activity size={18} className="text-green-500 animate-pulse" />
          </div>
        </header>

        <div className="flex-1 overflow-y-auto p-8 custom-scrollbar">
          <div className="max-w-6xl mx-auto grid grid-cols-1 xl:grid-cols-2 gap-10">
            <section className="flex flex-col gap-4">
              <div className="flex items-center justify-between px-1">
                <span className="text-[10px] font-black uppercase text-slate-600 tracking-[0.3em]">C# Input</span>
                <button onClick={analyzeCode} disabled={loading || !code} className="bg-blue-600 hover:bg-blue-500 disabled:bg-slate-800 text-white px-10 py-3 rounded-2xl text-[10px] font-black tracking-[0.2em] transition-all shadow-xl active:scale-95 shadow-blue-900/10">
                  {loading ? <div className="h-4 w-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : "ANALYZE SCRIPT"}
                </button>
              </div>
              <textarea value={code} onChange={(e) => setCode(e.target.value)} placeholder="// Paste your Unity code here..." className="w-full h-[620px] bg-[#0d1117] border border-slate-800 rounded-[32px] p-8 font-mono text-[13px] leading-relaxed focus:ring-4 focus:ring-blue-500/5 outline-none transition-all resize-none text-slate-300 shadow-2xl" />
            </section>

            <section className="flex flex-col gap-4">
              <span className="text-[10px] font-black uppercase text-slate-600 tracking-[0.3em]">Dashboard</span>
              <AnimatePresence mode="wait">
                {!result && !loading ? (
                  <div className="h-[620px] border-2 border-dashed border-slate-800/50 rounded-[40px] flex flex-col items-center justify-center text-slate-700 bg-slate-900/5">
                    <Code2 size={64} className="opacity-5 mb-6" />
                    <p className="text-[10px] font-black tracking-widest uppercase opacity-40">Ready for Analysis</p>
                  </div>
                ) : loading ? (
                  <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="h-[620px] flex flex-col items-center justify-center gap-8 bg-[#0d1117]/80 rounded-[40px] border border-slate-800 backdrop-blur-sm">
                    <div className="relative">
                        <div className="h-20 w-20 border-[6px] border-blue-900/20 border-t-blue-500 rounded-full animate-spin"></div>
                        <Cpu className="absolute inset-0 m-auto text-blue-400 animate-pulse" size={32} />
                    </div>
                    <div className="text-center space-y-2">
                        <p className="text-[11px] text-blue-500 font-black tracking-[0.5em] uppercase">QWEN 7B CODER</p>
                        <p className="text-slate-400 text-xs font-medium animate-pulse italic">Düşünce zinciri oluşturuluyor...</p>
                    </div>
                  </motion.div>
                ) : (
                  <motion.div initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }} className="space-y-6 overflow-y-auto h-[620px] pr-2 custom-scrollbar">
                    <div className="bg-[#161b22] border border-slate-800 rounded-[32px] p-8 shadow-sm">
                      <h3 className="text-orange-400 text-[10px] font-black mb-6 tracking-[0.2em] uppercase flex items-center gap-3"><AlertTriangle size={18} /> Static Code Smells</h3>
                      <div className="space-y-3">
                        {result?.static_results?.smells?.length > 0 ? result.static_results.smells.map((s: any, i: number) => (
                          <div key={i} className="text-xs bg-[#0a0c10] p-4 rounded-2xl border border-slate-800 flex items-start gap-4 transition-all hover:border-orange-500/40 group">
                            <span className="bg-orange-500/10 text-orange-500 px-2 py-1 rounded-lg text-[10px] font-black">L{s.line || "?"}</span>
                            <span className="text-slate-400 group-hover:text-slate-200 transition-colors leading-relaxed">{s.msg}</span>
                          </div>
                        )) : <div className="flex items-center gap-3 text-green-500 bg-green-500/5 p-5 rounded-2xl border border-green-500/20 text-[10px] font-black uppercase tracking-widest"><CheckCircle size={18} /> Integrity Check Passed</div>}
                      </div>
                    </div>
                    <div className="bg-[#161b22] border border-slate-800 rounded-[32px] p-8 relative overflow-hidden shadow-2xl">
                      <div className="absolute -top-10 -right-10 p-20 opacity-[0.02] text-blue-500 rotate-12"><Cpu size={250} /></div>
                      <h3 className="text-blue-400 text-[10px] font-black mb-8 tracking-[0.2em] uppercase flex items-center gap-3 relative"><Cpu size={18} /> Architectural Advisor</h3>
                      <div className="prose prose-invert max-w-none text-[14px] leading-loose relative">
                        <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
                            code({ node, inline, className, children, ...props }: any) {
                              const match = /language-(\w+)/.exec(className || '');
                              return !inline && match ? (
                                <SyntaxHighlighter style={vscDarkPlus} language={match[1]} PreTag="div" className="rounded-[24px] !bg-[#0a0c10] border border-slate-800 !my-8 shadow-2xl p-6" {...props}>{String(children).replace(/\n$/, '')}</SyntaxHighlighter>
                              ) : ( <code className="bg-blue-500/10 px-2 py-1 rounded-md text-blue-400 font-mono text-xs font-bold" {...props}>{children}</code> );
                            }
                          }}>{result?.ai_suggestion}</ReactMarkdown>
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </section>
          </div>
        </div>
      </main>

      <style dangerouslySetInnerHTML={{ __html: `
        .custom-scrollbar::-webkit-scrollbar { width: 5px; height: 5px; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: #1e293b; border-radius: 10px; }
        .prose code::before, .prose code::after { content: "" !important; }
        select option { background-color: #0d1117 !important; color: white !important; }
        input:-webkit-autofill { -webkit-text-fill-color: white !important; -webkit-box-shadow: 0 0 0px 1000px #161b22 inset !important; }
      ` }} />
    </div>
  );
}