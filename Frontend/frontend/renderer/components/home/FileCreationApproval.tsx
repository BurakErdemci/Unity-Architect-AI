import { DiffEditor } from '@monaco-editor/react';
import { AnimatePresence, motion } from 'framer-motion';
import { Check, CheckCircle2, ChevronRight, FileCode, SkipForward, Zap } from 'lucide-react';
import { useState } from 'react';

import { defineUnityTheme, THEME_NAME } from './monaco-theme';

export interface PendingFile {
  name: string;
  code: string;
  suggestedPath: string;
}

interface FileCreationApprovalProps {
  files: PendingFile[];
  onAcceptOne: (file: PendingFile) => Promise<void>;
  onSkipOne: (file: PendingFile) => void;
  onAcceptAll: (files: PendingFile[]) => Promise<void>;
  onDone: () => void;
}

export const FileCreationApproval = ({
  files,
  onAcceptOne,
  onSkipOne,
  onAcceptAll,
  onDone,
}: FileCreationApprovalProps) => {
  const [currentIdx, setCurrentIdx] = useState(0);
  const [done, setDone] = useState<Set<number>>(new Set());
  const [skipped, setSkipped] = useState<Set<number>>(new Set());
  const [autoMode, setAutoMode] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [allDone, setAllDone] = useState(false);

  const current = files[currentIdx];
  const remaining = files.length - done.size - skipped.size;

  const handleAccept = async () => {
    if (!current || processing) return;
    setProcessing(true);
    await onAcceptOne(current);
    setDone(prev => new Set([...prev, currentIdx]));
    setProcessing(false);
    advance();
  };

  const handleSkip = () => {
    if (!current) return;
    onSkipOne(current);
    setSkipped(prev => new Set([...prev, currentIdx]));
    advance();
  };

  const advance = () => {
    const next = files.findIndex((_, i) => i > currentIdx && !done.has(i) && !skipped.has(i));
    if (next === -1) {
      setAllDone(true);
    } else {
      setCurrentIdx(next);
    }
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
    const createdCount = done.size;
    return (
      <motion.div
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        className="rounded-xl border border-emerald-700/40 bg-emerald-950/20 px-4 py-3 mt-3 flex items-start gap-3"
      >
        <CheckCircle2 size={16} className="text-emerald-400 shrink-0 mt-0.5" />
        <div>
          <p className="text-[12px] font-semibold text-emerald-300">
            {createdCount} dosya oluşturuldu
          </p>
          <p className="text-[11px] text-slate-400 mt-0.5">
            {skipped.size > 0 && `${skipped.size} dosya atlandı. `}
            Workspace'e yazıldı.
          </p>
        </div>
      </motion.div>
    );
  }

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={currentIdx}
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -8 }}
        className="rounded-xl border border-slate-700/60 overflow-hidden bg-[#0a0a0a] mt-3"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-slate-800/60 bg-[#0d0d0d]">
          <div className="flex items-center gap-2">
            <FileCode size={14} className="text-emerald-400" />
            <span className="text-[12px] font-semibold text-slate-300">{current?.name}</span>
            <span className="text-[10px] text-slate-600 font-mono truncate max-w-[180px]">
              {current?.suggestedPath}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-slate-500">
              {currentIdx + 1} / {files.length}
            </span>
            {/* Progress dots */}
            <div className="flex gap-1">
              {files.map((_, i) => (
                <div
                  key={i}
                  className={`w-1.5 h-1.5 rounded-full transition-colors ${
                    done.has(i) ? 'bg-emerald-500' :
                    skipped.has(i) ? 'bg-slate-700' :
                    i === currentIdx ? 'bg-blue-400' : 'bg-slate-800'
                  }`}
                />
              ))}
            </div>
          </div>
        </div>

        {/* Code preview — diff against empty */}
        <div className="h-[280px]">
          <DiffEditor
            height="100%"
            language="csharp"
            original=""
            modified={current?.code || ''}
            theme={THEME_NAME}
            onMount={(_, monaco) => defineUnityTheme(monaco)}
            options={{
              readOnly: true,
              renderSideBySide: false,
              minimap: { enabled: false },
              fontSize: 12,
              fontFamily: "'JetBrains Mono', 'Fira Code', 'Consolas', monospace",
              lineHeight: 1.5,
              scrollBeyondLastLine: false,
              padding: { top: 12, bottom: 12 },
            }}
          />
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 px-4 py-3 border-t border-slate-800/60 bg-[#0d0d0d]">
          <button
            onClick={handleAccept}
            disabled={processing}
            className="flex items-center gap-1.5 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white rounded-lg text-[12px] font-semibold transition-colors"
          >
            <Check size={13} />
            Oluştur
          </button>
          <button
            onClick={handleSkip}
            disabled={processing}
            className="flex items-center gap-1.5 px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-400 rounded-lg text-[12px] font-semibold transition-colors"
          >
            <SkipForward size={13} />
            Atla
          </button>
          <button
            onClick={handleAcceptAll}
            disabled={processing}
            className="flex items-center gap-1.5 px-3 py-2 bg-blue-600/20 hover:bg-blue-600/30 border border-blue-500/30 text-blue-300 rounded-lg text-[12px] font-semibold transition-colors"
          >
            <Zap size={13} />
            Tümünü Oluştur
          </button>
          <div className="ml-auto flex items-center gap-1.5">
            <ChevronRight size={12} className="text-slate-600" />
            <span className="text-[10px] text-slate-600">{remaining} dosya kaldı</span>
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  );
};
