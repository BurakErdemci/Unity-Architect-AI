import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Brain, 
  Sparkles, 
  ChevronDown, 
  Download,
  Upload
} from 'lucide-react';
import { GenerationModeSelector, GenerationMode } from './GenerationModeSelector';

interface ControlPanelProps {
  useThinking: boolean;
  setUseThinking: (val: boolean) => void;
  generationMode: GenerationMode;
  setGenerationMode: (mode: GenerationMode) => void;
  isAnalyzingProject: boolean;
  activeConvId: number | null;
  analyzeProject: (silent?: boolean) => Promise<void>;
  wisdomSummary: string | null;
  exportMemory: () => Promise<void>;
  importMemory: () => Promise<void>;
  compactConversation: () => Promise<void>;
  isCompacting: boolean;
  contextUsage?: { percent: number; message_count: number; should_compact?: boolean };
}

export const ControlPanel: React.FC<ControlPanelProps> = ({
  useThinking,
  setUseThinking,
  generationMode,
  setGenerationMode,
  isAnalyzingProject,
  activeConvId,
  analyzeProject,
  wisdomSummary,
  exportMemory,
  importMemory,
  compactConversation,
  isCompacting,
  contextUsage
}) => {
  const [showMemoryMenu, setShowMemoryMenu] = useState(false);

  return (
    <div className="flex items-center gap-2 px-1 mt-1.5">
      <GenerationModeSelector value={generationMode} onChange={setGenerationMode} />
      <div className="w-px h-3 bg-slate-800" />
      
      {/* Thinking Toggle */}
      <button
        onClick={() => setUseThinking(!useThinking)}
        className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-medium transition-colors ${
          useThinking
            ? 'bg-violet-500/15 border border-violet-500/30 text-violet-400'
            : 'text-slate-600 hover:text-slate-400'
        }`}
        title="Modelin düşünce sürecini göster"
      >
        <Brain size={11} />
        Thinking {useThinking ? 'Açık' : 'Kapalı'}
      </button>

      <div className="w-px h-3 bg-slate-800" />
      
      {/* Projeyi Öğren & Hafıza Menüsü */}
      <div className="relative flex items-center">
        <button
          onClick={() => analyzeProject()}
          disabled={isAnalyzingProject || !activeConvId}
          className={`flex items-center gap-1.5 px-3 py-1 rounded-l-lg text-[11px] font-medium transition-all ${
            isAnalyzingProject 
              ? 'bg-blue-500/20 text-blue-400 animate-pulse' 
              : 'text-slate-500 hover:text-blue-400 hover:bg-blue-500/5'
          }`}
          title="Tüm projeyi tarar ve AI'nın mimariyi öğrenmesini sağlar"
        >
          {isAnalyzingProject ? (
            <div className="flex items-center gap-2">
              <div className="w-2.5 h-2.5 border-2 border-blue-500/30 border-t-blue-500 rounded-full animate-spin" />
              <span>Öğreniyorum...</span>
            </div>
          ) : (
            <>
              <Sparkles size={11} className="text-blue-500" />
              <span>Projeyi Öğren</span>
            </>
          )}
        </button>
        <button
          onClick={() => setShowMemoryMenu(!showMemoryMenu)}
          disabled={isAnalyzingProject || !activeConvId}
          className={`px-1.5 py-1 border-l border-slate-800 rounded-r-lg text-slate-500 hover:text-blue-400 hover:bg-blue-500/5 transition-all ${
            showMemoryMenu ? 'bg-blue-500/10 text-blue-400' : ''
          }`}
        >
          <ChevronDown size={12} className={`transition-transform duration-200 ${showMemoryMenu ? 'rotate-180' : ''}`} />
        </button>

        <AnimatePresence>
          {showMemoryMenu && (
            <>
              <div className="fixed inset-0 z-40" onClick={() => setShowMemoryMenu(false)} />
              <motion.div
                initial={{ opacity: 0, y: 10, scale: 0.95 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: 10, scale: 0.95 }}
                className="absolute bottom-10 right-0 w-48 bg-[#0a0a0f] border border-slate-800 rounded-xl shadow-2xl z-50 py-1.5 overflow-hidden"
              >
                <button
                  onClick={() => { analyzeProject(); setShowMemoryMenu(false); }}
                  className="w-full flex items-center justify-between px-3 py-2 text-[11px] text-slate-300 hover:bg-blue-600/10 hover:text-blue-400 transition-all"
                >
                  <span>Hafızayı Yenile (Full Scan)</span>
                  <Sparkles size={11} />
                </button>
                <button
                  onClick={async () => { setShowMemoryMenu(false); await exportMemory(); }}
                  className="w-full flex items-center gap-2.5 px-3 py-2 text-[11px] text-slate-300 hover:bg-blue-600/10 hover:text-blue-400 transition-colors"
                >
                  <Download size={13} />
                  Hafızayı Dışarı Aktar
                </button>
                <button
                  onClick={async () => { setShowMemoryMenu(false); await importMemory(); }}
                  className="w-full flex items-center gap-2.5 px-3 py-2 text-[11px] text-slate-300 hover:bg-emerald-600/10 hover:text-emerald-400 transition-colors"
                >
                  <Upload size={13} />
                  Hafıza Dosyası Yükle
                </button>
              </motion.div>
            </>
          )}
        </AnimatePresence>
      </div>

      {/* Circular Memory Compact Button */}
      {activeConvId && contextUsage && contextUsage.percent > 0 && (
        <>
          <div className="w-px h-3 bg-slate-800" />
          <button
            onClick={() => compactConversation()}
            disabled={isCompacting}
            title={`Hafıza Kullanımı: %${contextUsage.percent} (${contextUsage.message_count} mesaj)\nTıkla ve özetle`}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-medium transition-colors group relative ${
              contextUsage.percent >= 90 ? 'bg-red-500/10 border border-red-500/30 text-red-400 hover:bg-red-500/20'
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
  );
};
