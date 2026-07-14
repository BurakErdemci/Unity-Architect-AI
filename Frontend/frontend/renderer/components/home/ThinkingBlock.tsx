import { AnimatePresence, motion } from 'framer-motion';
import { ChevronRight, Sparkles } from 'lucide-react';
import { useState } from 'react';

interface ThinkingBlockProps {
  thinking: string;
  durationMs?: number | null;
}

export const ThinkingBlock = ({ thinking, durationMs }: ThinkingBlockProps) => {
  const [open, setOpen] = useState(false);

  const seconds = durationMs ? Math.round(durationMs / 1000) : null;
  const label = seconds ? `${seconds} saniye düşündü` : 'Düşündü';

  return (
    <div className="mb-2.5">
      <button
        onClick={() => setOpen(v => !v)}
        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-white/[0.07] bg-white/[0.02] hover:bg-white/[0.05] hover:border-white/[0.12] text-[11px] text-slate-500 hover:text-slate-300 transition-colors select-none group"
      >
        <Sparkles size={10.5} className="text-violet-400/70" />
        <span>{label}</span>
        <motion.span
          animate={{ rotate: open ? 90 : 0 }}
          transition={{ duration: 0.15 }}
          className="flex items-center"
        >
          <ChevronRight size={11} />
        </motion.span>
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="mt-2 pl-3 border-l border-white/[0.08] max-h-[320px] overflow-y-auto custom-scrollbar">
              <p className="text-[11px] text-slate-500 whitespace-pre-wrap leading-relaxed font-mono">
                {thinking}
              </p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
