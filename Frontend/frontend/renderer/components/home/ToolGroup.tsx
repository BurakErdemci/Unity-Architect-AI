import { useState } from 'react';
import { motion } from 'framer-motion';
import { ChevronRight, Layers } from 'lucide-react';
import { ToolBlock } from './ToolBlock';

interface ToolItem { tool: string; args?: any; summary?: string; success?: boolean; output?: string; id?: string; }

/**
 * Araç çağrılarını gösterir. 3 veya azsa düz liste; fazlaysa "N adım" collapse grubu
 * (Claude SDK session'ında çok araç çağrısı olunca chat'i gürültüden korur).
 */
export const ToolGroup = ({ tools }: { tools?: ToolItem[] }) => {
  const [open, setOpen] = useState(false);
  if (!tools || tools.length === 0) return null;

  if (tools.length <= 3) {
    return (
      <div className="flex flex-col gap-1 mb-3">
        {tools.map((tc, idx) => (
          <ToolBlock key={idx} tool={tc.tool} args={tc.args} summary={tc.summary} success={tc.success} output={tc.output} />
        ))}
      </div>
    );
  }

  return (
    <div className="mb-3">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 text-[11px] text-slate-500 hover:text-slate-400 select-none group"
      >
        <Layers size={12} className="opacity-70" />
        <span className="font-medium">{tools.length} adım</span>
        <motion.span
          animate={{ rotate: open ? 90 : 0 }}
          transition={{ duration: 0.15 }}
          className="flex items-center ml-1"
        >
          <ChevronRight size={11} />
        </motion.span>
      </button>
      {open && (
        <div className="flex flex-col gap-1 mt-1.5 pl-2 border-l border-slate-800">
          {tools.map((tc, idx) => (
            <ToolBlock key={idx} tool={tc.tool} args={tc.args} summary={tc.summary} success={tc.success} output={tc.output} />
          ))}
        </div>
      )}
    </div>
  );
};
