import { AnimatePresence, motion } from 'framer-motion';
import { ChevronRight } from 'lucide-react';
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
    <div className="mb-2">
      <button
        onClick={() => setOpen(v => !v)}
        className="flex items-center gap-1.5 text-[11px] text-slate-500 hover:text-slate-400 transition-colors select-none group"
      >
        <span className="w-1.5 h-1.5 rounded-full bg-slate-600 group-hover:bg-slate-500 transition-colors" />
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
            <div className="mt-2 pl-3 border-l border-slate-800 max-h-[320px] overflow-y-auto">
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
