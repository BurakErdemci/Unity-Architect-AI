import { DiffEditor } from '@monaco-editor/react';
import { AnimatePresence, motion } from 'framer-motion';
import { Check, CheckCircle2, ChevronRight, FileCode, SkipForward, Zap } from 'lucide-react';
import { useState, useEffect } from 'react';

import { defineUnityTheme, THEME_NAME } from './monaco-theme';

export interface PendingFile {
  name: string;
  code: string;
  suggestedPath: string;
  originalCode?: string;
}

interface FileCreationApprovalProps {
  files: PendingFile[];
  onAcceptOne: (file: PendingFile) => Promise<void>;
  onSkipOne: (file: PendingFile) => void;
  onAcceptAll: (files: PendingFile[]) => Promise<void>;
  onDone: () => void;
  onOpenFile?: (path: string) => void;
  autoAccept?: boolean; // Eğer true ise otomatik onaylayıp özeti gösterir
}

export const FileCreationApproval = ({
  files,
  onAcceptOne,
  onSkipOne,
  onAcceptAll,
  onDone,
  onOpenFile,
  autoAccept,
}: FileCreationApprovalProps) => {
  const [currentIdx, setCurrentIdx] = useState(0);
  const [done, setDone] = useState<Set<number>>(new Set());
  const [skipped, setSkipped] = useState<Set<number>>(new Set());
  const [processing, setProcessing] = useState(false);
  const [allDone, setAllDone] = useState(false);

  const current = files[currentIdx];
  const remaining = files.length - done.size - skipped.size;

  useEffect(() => {
    const processAuto = async () => {
      if (autoAccept && !allDone && !processing && files.length > 0) {
        setProcessing(true);
        for (const file of files) {
          await onAcceptOne(file);
        }
        setDone(new Set(files.map((_, i) => i)));
        setProcessing(false);
        setAllDone(true);
      }
    };
    processAuto();
  }, [autoAccept, files]);

  const handleAccept = async (idx: number) => {
    const file = files[idx];
    if (!file || processing || done.has(idx)) return;
    setProcessing(true);
    await onAcceptOne(file);
    setDone(prev => new Set([...prev, idx]));
    setProcessing(false);
    
    // Eğer hala yapılmamış dosya varsa sonrakine geç
    const next = files.findIndex((_, i) => !done.has(i) && !skipped.has(i) && i !== idx);
    if (next !== -1) setCurrentIdx(next);
    else if (done.size + skipped.size + 1 === files.length) setAllDone(true);
  };

  const handleSkip = (idx: number) => {
    const file = files[idx];
    if (!file || done.has(idx)) return;
    onSkipOne(file);
    setSkipped(prev => new Set([...prev, idx]));
    
    const next = files.findIndex((_, i) => !done.has(i) && !skipped.has(i) && i !== idx);
    if (next !== -1) setCurrentIdx(next);
    else if (done.size + skipped.size + 1 === files.length) setAllDone(true);
  };

  const handleAcceptAll = async () => {
    if (processing) return;
    setProcessing(true);
    await onAcceptAll(files);
    setDone(new Set(files.map((_, i) => i)));
    setProcessing(false);
    setAllDone(true);
  };

  if (allDone) {
    const createdFiles = files.filter((_, i) => done.has(i));
    const hasUpdates = createdFiles.some(f => 
      f.originalCode && 
      typeof f.originalCode === 'string' && 
      f.originalCode.trim().length > 0
    );

    return (
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="rounded-xl border border-emerald-500/30 bg-[#0a0a0a] px-5 py-4 mt-3 shadow-lg shadow-emerald-500/5"
      >
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-emerald-500/20 flex items-center justify-center">
              <CheckCircle2 size={18} className="text-emerald-400" />
            </div>
            <div>
              <h3 className="text-[13px] font-bold text-white leading-none">İşlem Tamamlandı</h3>
              <p className="text-[11px] text-slate-500 mt-1">{createdFiles.length} dosya başarıyla {hasUpdates ? 'güncellendi' : 'oluşturuldu'}.</p>
            </div>
          </div>
          <button 
            onClick={onDone}
            className="px-4 py-1.5 bg-slate-800 hover:bg-slate-700 text-white rounded-lg text-[11px] font-semibold transition-colors"
          >
            Kapat
          </button>
        </div>
        
        <div className="grid grid-cols-2 gap-2">
          {createdFiles.map((file) => (
            <button 
              key={file.suggestedPath} 
              onClick={() => onOpenFile?.(file.suggestedPath)}
              className="flex items-center gap-2 p-2 rounded-lg bg-slate-900/50 border border-slate-800/40 hover:bg-slate-800/60 hover:border-emerald-500/30 transition-all text-left group"
            >
              <FileCode size={12} className="text-blue-400 shrink-0" />
              <span className="text-[11px] text-slate-300 truncate flex-1 group-hover:text-white">{file.name}</span>
              <Check size={12} className="text-emerald-400" />
            </button>
          ))}
        </div>
      </motion.div>
    );
  }

  return (
    <div className="rounded-xl border border-slate-700/60 overflow-hidden bg-[#0a0a0a] mt-4 flex flex-col shadow-2xl">
      {/* Top Header / Stats */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-slate-800/60 bg-[#0d0d0d]">
        <div className="flex items-center gap-2">
          <Zap size={14} className="text-yellow-400 animate-pulse" />
          <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Ajan Değişiklik Paneli</span>
        </div>
        <div className="flex items-center gap-3">
          <button 
            onClick={handleAcceptAll}
            disabled={processing}
            className="text-[11px] text-blue-400 hover:text-blue-300 font-bold transition-colors disabled:opacity-50"
          >
            Tümünü Onayla
          </button>
          <div className="h-3 w-[1px] bg-slate-800" />
          <span className="text-[11px] text-slate-500 font-mono">{remaining} dosya kaldı</span>
        </div>
      </div>

      <div className="flex h-[400px]">
        {/* Sidebar Dosya Listesi */}
        <div className="w-[200px] border-r border-slate-800/60 bg-[#0d0d0d] overflow-y-auto p-2 space-y-1">
          {files.map((file, i) => {
            const isDone = done.has(i);
            const isSkipped = skipped.has(i);
            const isActive = i === currentIdx;

            return (
              <button
                key={i}
                onClick={() => setCurrentIdx(i)}
                className={`w-full flex items-center gap-2 px-2 py-2 rounded-lg transition-all text-left group ${
                  isActive ? 'bg-blue-600/20 border border-blue-500/30' : 'hover:bg-slate-800/40 border border-transparent'
                }`}
              >
                {isDone ? <CheckCircle2 size={12} className="text-emerald-500" /> :
                 isSkipped ? <SkipForward size={12} className="text-slate-600" /> :
                 <div className={`w-1.5 h-1.5 rounded-full ${isActive ? 'bg-blue-400' : 'bg-slate-700'}`} />}
                
                <span className={`text-[11px] flex-1 truncate ${
                  isActive ? 'text-blue-200 font-bold' : 'text-slate-400 group-hover:text-slate-200'
                } ${isDone || isSkipped ? 'opacity-50' : ''}`}>
                  {file.name}
                </span>
                
                {isActive && <ChevronRight size={10} className="text-blue-400" />}
              </button>
            );
          })}
        </div>

        {/* Main Diff Area */}
        <div className="flex-1 flex flex-col bg-black">
          <div className="flex items-center justify-between px-3 py-1.5 bg-slate-900/30 border-b border-slate-800/40">
            <span className="text-[10px] font-mono text-slate-500 truncate max-w-[300px]">
              {current?.suggestedPath}
            </span>
            <div className="flex items-center gap-2">
               {!done.has(currentIdx) && !skipped.has(currentIdx) && (
                 <>
                  <button 
                    onClick={() => handleSkip(currentIdx)}
                    className="p-1 hover:bg-rose-500/20 text-slate-500 hover:text-rose-400 rounded transition-colors"
                    title="Bu dosyayı atla"
                  >
                    <SkipForward size={14} />
                  </button>
                  <button 
                    onClick={() => handleAccept(currentIdx)}
                    className="flex items-center gap-1 px-3 py-1 bg-emerald-600 hover:bg-emerald-500 text-white rounded-md text-[11px] font-bold transition-all"
                  >
                    <Check size={12} />
                    Uygula
                  </button>
                 </>
               )}
               {(done.has(currentIdx) || skipped.has(currentIdx)) && (
                 <span className="text-[10px] text-slate-500 italic">Bu dosya işlendi.</span>
               )}
            </div>
          </div>
          
          <div className="flex-1 relative">
            <DiffEditor
              height="100%"
              language="csharp"
              original={current?.originalCode || ""}
              modified={current?.code || ''}
              theme={THEME_NAME}
              onMount={(_, monaco) => defineUnityTheme(monaco)}
              options={{
                readOnly: true,
                renderSideBySide: true,
                minimap: { enabled: false },
                fontSize: 11,
                fontFamily: "'JetBrains Mono', 'Fira Code', 'Consolas', monospace",
                lineHeight: 1.4,
                scrollBeyondLastLine: false,
                padding: { top: 10, bottom: 10 },
                renderOverviewRuler: false,
                scrollbar: {
                  vertical: 'hidden',
                  horizontal: 'hidden'
                }
              }}
            />
          </div>
        </div>
      </div>
    </div>
  );
};
