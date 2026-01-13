
import React, { useState } from 'react';
import Head from 'next/head';
import axios from 'axios';
import { Activity, AlertTriangle, CheckCircle, Code2, Cpu, Sparkles, Languages, ChevronDown } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/cjs/styles/prism';

export default function HomePage() {
  const [code, setCode] = useState('');
  const [lang, setLang] = useState('tr');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);

  const analyzeCode = async () => {
    if (!code) return;
    setLoading(true);
    setResult(null);
    try {
      const response = await axios.post('http://127.0.0.1:8000/analyze', { code, language: lang });
      setResult(response.data);
    } catch (error) {
      console.error("Analiz hatası:", error);
      alert("Backend'e bağlanılamadı. Python terminalini kontrol et!");
    }
    setLoading(false);
  };

  return (
    <div className="min-h-screen bg-[#0a0c10] text-slate-200 font-sans p-6 md:p-10">
      <Head>
        <title>Unity Architect AI | Smart Advisor</title>
      </Head>

      <main className="max-w-7xl mx-auto">
        {/* Header */}
        <header className="flex flex-col md:flex-row items-center justify-between mb-10 border-b border-slate-800/50 pb-8 gap-6">
          <div className="flex items-center gap-4 text-center md:text-left">
            <div className="bg-gradient-to-br from-blue-600 to-indigo-700 p-3 rounded-2xl shadow-lg shadow-blue-900/20">
              <Code2 size={28} className="text-white" />
            </div>
            <div>
              <h1 className="text-3xl font-extrabold tracking-tight text-white italic">
                Unity Architect <span className="text-blue-500 not-italic">AI</span>
              </h1>
              <p className="text-slate-500 text-sm mt-1 uppercase tracking-widest font-bold">M4 Optimized Advisor</p>
            </div>
          </div>

          <div className="flex items-center gap-4">
            {/* DÜZELTİLMİŞ DİL SEÇİCİ */}
            <div className="relative group">
              <div className="absolute inset-y-0 left-3 flex items-center pointer-events-none text-blue-500">
                <Languages size={16} />
              </div>
              <select 
                value={lang} 
                onChange={(e) => setLang(e.target.value)}
                className="appearance-none bg-slate-900 border border-slate-700 text-slate-300 text-sm rounded-xl pl-10 pr-10 py-2.5 focus:ring-2 focus:ring-blue-600 focus:outline-none cursor-pointer hover:border-slate-500 transition-all font-medium"
              >
                <option value="tr">Türkçe</option>
                <option value="en">English</option>
                <option value="de">Deutsch</option>
              </select>
              <div className="absolute inset-y-0 right-3 flex items-center pointer-events-none text-slate-500">
                <ChevronDown size={14} />
              </div>
            </div>

            <div className="h-10 w-[1px] bg-slate-800 hidden md:block"></div>
            <Activity size={20} className="text-green-500 animate-pulse" />
          </div>
        </header>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-10">
          {/* Sol Kolon: Kod Girişi */}
          <section className="space-y-4">
            <div className="flex items-center justify-between px-2">
              <h2 className="text-[11px] font-black uppercase text-slate-500 tracking-[0.2em]">C# Script Editor</h2>
              <button 
                onClick={analyzeCode}
                disabled={loading || !code}
                className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-800 text-white px-8 py-3 rounded-xl font-bold transition-all transform hover:scale-[1.02] active:scale-95 shadow-xl shadow-blue-900/20"
              >
                {loading ? <div className="h-4 w-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <Sparkles size={18} />}
                <span>{loading ? "Analiz Ediliyor..." : "Mimarini Analiz Et"}</span>
              </button>
            </div>
            <div className="relative">
              <textarea
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="// Unity C# Scriptinizi buraya yapıştırın..."
                className="w-full h-[600px] bg-[#0d1117] border border-slate-800 rounded-2xl p-6 font-mono text-[14px] leading-relaxed focus:ring-2 focus:ring-blue-500/50 focus:outline-none transition-all resize-none text-slate-300 shadow-2xl"
              />
            </div>
          </section>

          {/* Sağ Kolon: Analiz Sonuçları */}
          <section className="space-y-6">
            <h2 className="text-[11px] font-black uppercase text-slate-500 tracking-[0.2em] px-2">Architectural Dashboard</h2>
            
            <AnimatePresence mode="wait">
              {!result && !loading ? (
                <motion.div 
                  initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                  className="h-[600px] border-2 border-dashed border-slate-800/50 rounded-3xl flex flex-col items-center justify-center text-slate-600 space-y-4 bg-slate-900/20"
                >
                  <Code2 size={48} className="opacity-10" />
                  <p className="text-sm font-medium">Analiz başlatmak için kod yapıştırın.</p>
                </motion.div>
              ) : loading ? (
                <motion.div 
                   initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                   className="h-[600px] flex flex-col items-center justify-center space-y-4"
                >
                   <div className="relative">
                      <div className="h-16 w-16 border-4 border-blue-900/30 border-t-blue-500 rounded-full animate-spin"></div>
                      <Cpu className="absolute inset-0 m-auto text-blue-500 animate-pulse" size={24} />
                   </div>
                   <p className="text-blue-500 font-bold animate-pulse tracking-widest text-xs">DEEPSEEK-R1 IS REASONING...</p>
                </motion.div>
              ) : (
                <motion.div 
                  initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
                  className="space-y-6 overflow-y-auto h-[600px] pr-4 custom-scrollbar"
                >
                  {/* Bulgular */}
                  <div className="bg-[#161b22] border border-slate-800 rounded-2xl p-6">
                    <h3 className="flex items-center gap-2 font-bold mb-4 text-orange-400 uppercase text-[10px] tracking-[0.2em]">
                      <AlertTriangle size={14} /> Statik Bulgular
                    </h3>
                    <div className="space-y-3">
                      {result?.static_results?.smells?.length > 0 ? (
                        result.static_results.smells.map((smell: any, idx: number) => (
                          <div key={idx} className="bg-[#0d1117] p-4 rounded-xl border-l-4 border-orange-600 flex gap-4 transition-all hover:bg-slate-900">
                            <div className="text-orange-500 font-mono text-[10px] mt-1 shrink-0">L{smell.line || "?"}</div>
                            <p className="text-slate-300 text-sm leading-snug">{smell.msg}</p>
                          </div>
                        ))
                      ) : (
                        <div className="flex items-center gap-3 text-green-500 bg-green-500/5 p-4 rounded-xl border border-green-500/20 text-sm">
                          <CheckCircle size={18} /> Kod statik açıdan temiz görünüyor.
                        </div>
                      )}
                    </div>
                  </div>

                  {/* AI Önerisi (MARKDOWN + HIGHLIGHTER) */}
                  <div className="bg-[#161b22] border border-slate-800 rounded-2xl p-6 relative overflow-hidden">
                    <h3 className="flex items-center gap-2 font-bold mb-6 text-blue-400 uppercase text-[10px] tracking-[0.2em]">
                      <Cpu size={14} /> Mimari Yol Haritası
                    </h3>
                    <div className="prose prose-invert max-w-none text-slate-300">
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
                                className="rounded-xl border border-slate-800 !bg-[#0d1117] my-4 shadow-2xl"
                                {...props}
                              >
                                {String(children).replace(/\n$/, '')}
                              </SyntaxHighlighter>
                            ) : (
                              <code className="bg-slate-800 px-1.5 py-0.5 rounded text-blue-400 font-mono text-sm" {...props}>
                                {children}
                              </code>
                            );
                          }
                        }}
                      >
                        {result?.ai_suggestion}
                      </ReactMarkdown>
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </section>
        </div>
      </main>
   {/* home.tsx dosyasının en altındaki stil kısmını bununla değiştir */}
<style dangerouslySetInnerHTML={{ __html: `
  .custom-scrollbar::-webkit-scrollbar { width: 6px; }
  .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
  .custom-scrollbar::-webkit-scrollbar-thumb { background: #1e293b; border-radius: 10px; }
  .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: #334155; }
  pre { background: transparent !important; padding: 0 !important; }
` }} />
    </div>
  );
}