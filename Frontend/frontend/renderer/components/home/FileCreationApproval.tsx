import { motion } from 'framer-motion';
import { useLang } from '../../lib/i18n';
import { 
  Check, 
  CheckCircle2, 
  ChevronRight, 
  FileCode, 
  SkipForward, 
  Zap, 
  XCircle,
  Eye
} from 'lucide-react';
import { useState, useEffect } from 'react';

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
  autoAccept?: boolean;
  setDiffFile: (file: PendingFile | null) => void;
}

export const FileCreationApproval = ({
  files,
  onAcceptOne,
  onSkipOne,
  onAcceptAll,
  onDone,
  onOpenFile,
  autoAccept,
  setDiffFile
}: FileCreationApprovalProps) => {
  const { t } = useLang();
  const [currentIdx, setCurrentIdx] = useState(0);
  const [done, setDone] = useState<Set<number>>(new Set());
  const [skipped, setSkipped] = useState<Set<number>>(new Set());
  const [processing, setProcessing] = useState(false);
  const [allDone, setAllDone] = useState(false);

  const remaining = files.length - done.size - skipped.size;

  // Dosya değiştiğinde ana editörü güncelle
  useEffect(() => {
    if (!allDone && files[currentIdx]) {
      setDiffFile(files[currentIdx]);
    }
    return () => setDiffFile(null);
  }, [currentIdx, allDone, files]);

  useEffect(() => {
    if (autoAccept && !allDone && !processing && files.length > 0) {
      handleAcceptAll();
    }
  }, [autoAccept]);

  const handleAccept = async (idx: number) => {
    const file = files[idx];
    if (!file || processing || done.has(idx)) return;
    setProcessing(true);
    await onAcceptOne(file).catch(err => console.error(err));
    setDone(prev => new Set([...prev, idx]));
    setProcessing(false);
    
    // Sıradaki bekleyen dosyayı bul
    const next = files.findIndex((_, i) => !done.has(i) && !skipped.has(i) && i !== idx);
    if (next !== -1) setCurrentIdx(next);
    else if (done.size + skipped.size + 1 === files.length) {
      setAllDone(true);
      setDiffFile(null);
    }
  };

  const handleSkip = (idx: number) => {
    const file = files[idx];
    if (!file || done.has(idx)) return;
    onSkipOne(file);
    setSkipped(prev => new Set([...prev, idx]));
    
    const next = files.findIndex((_, i) => !done.has(i) && !skipped.has(i) && i !== idx);
    if (next !== -1) setCurrentIdx(next);
    else if (done.size + skipped.size + 1 === files.length) {
      setAllDone(true);
      setDiffFile(null);
    }
  };

  const handleAcceptAll = async () => {
    if (processing) return;
    setProcessing(true);
    await onAcceptAll(files).catch(err => console.error(err));
    setDone(new Set(files.map((_, i) => i)));
    setProcessing(false);
    setAllDone(true);
    setDiffFile(null);
  };

  if (allDone) {
    const createdFiles = files.filter((_, i) => done.has(i));
    return (
      <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className="rounded-xl border border-emerald-500/30 bg-[#0a0a0a] px-4 py-3 mt-3">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <CheckCircle2 size={16} className="text-emerald-400" />
            <span className="text-[12px] font-bold text-white">{t('approval.done')}</span>
          </div>
          <button onClick={onDone} className="text-[11px] text-slate-500 hover:text-white transition-colors">{t('approval.close')}</button>
        </div>
        <div className="space-y-1">
          {createdFiles.map((file) => (
            <div key={file.suggestedPath} className="flex items-center gap-2 text-[11px] text-slate-400">
              <FileCode size={12} className="text-blue-500" />
              <span className="truncate">{file.name}</span>
            </div>
          ))}
        </div>
      </motion.div>
    );
  }

  return (
    <div className="rounded-xl border border-slate-700/50 bg-[#0d0d0d] mt-4 flex flex-col shadow-xl overflow-hidden">
      {/* HEADER */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-slate-800/60 bg-black/40">
        <div className="flex items-center gap-2">
          <Zap size={14} className="text-yellow-400 animate-pulse" />
          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">{t('approval.title')}</span>
        </div>
        <span className="text-[10px] text-slate-500 font-mono">{remaining} {t('approval.pending')}</span>
      </div>

      {/* COMPACT LIST */}
      <div className="p-2 space-y-1 max-h-[250px] overflow-y-auto custom-scrollbar">
        {files.map((file, i) => {
          const isDone = done.has(i);
          const isSkipped = skipped.has(i);
          const isActive = i === currentIdx;
          const isPending = !isDone && !isSkipped;

          return (
            <div 
              key={i} 
              onClick={() => isPending && setCurrentIdx(i)}
              className={`group flex items-center gap-2 p-2 rounded-lg border transition-all cursor-pointer ${
                isActive ? 'bg-blue-600/20 border-blue-500/40' : 
                isPending ? 'bg-slate-900/20 border-slate-800/60 hover:bg-slate-900/40' : 
                'bg-black/20 border-transparent opacity-50'
              }`}
            >
              <div className="shrink-0">
                {isDone ? <CheckCircle2 size={13} className="text-emerald-500" /> :
                 isSkipped ? <SkipForward size={13} className="text-slate-600" /> :
                 <FileCode size={13} className={isActive ? 'text-blue-400' : 'text-slate-500'} />}
              </div>
              
              <div className="flex-1 min-w-0">
                <p className={`text-[11px] truncate ${isActive ? 'text-blue-200 font-bold' : 'text-slate-300'}`}>
                  {file.name}
                </p>
              </div>

              {isPending && isActive && (
                <div className="flex items-center gap-1 shrink-0">
                  <button 
                    onClick={(e) => { e.stopPropagation(); handleSkip(i); }} 
                    className="p-1 hover:bg-rose-500/20 text-rose-400 rounded transition-all"
                  >
                    <SkipForward size={12} />
                  </button>
                  <button 
                    onClick={(e) => { e.stopPropagation(); handleAccept(i); }} 
                    className="px-2 py-0.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded text-[10px] font-bold"
                  >
                    {t('approval.apply')}
                  </button>
                </div>
              )}
              
              {isPending && !isActive && (
                <Eye size={12} className="text-slate-600 opacity-0 group-hover:opacity-100 transition-opacity" />
              )}
            </div>
          );
        })}
      </div>

      {/* FOOTER */}
      <div className="flex items-center justify-between px-3 py-2 border-t border-slate-800/60 bg-black/20">
        <button onClick={onDone} className="text-[10px] font-bold text-rose-500 hover:text-rose-400 flex items-center gap-1">
          <XCircle size={12} /> {t('approval.cancel')}
        </button>
        <button 
          onClick={handleAcceptAll} 
          disabled={processing}
          className="flex items-center gap-1 px-3 py-1 bg-blue-600/20 border border-blue-500/40 text-blue-400 hover:bg-blue-600/30 rounded-lg text-[10px] font-bold transition-all disabled:opacity-50"
        >
          <CheckCircle2 size={12} /> {t('approval.approveAll')}
        </button>
      </div>
    </div>
  );
};
