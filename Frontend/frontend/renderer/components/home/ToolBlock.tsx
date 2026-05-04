import { AnimatePresence, motion } from 'framer-motion';
import { ChevronRight, Wrench, FileSearch, Search, FolderOpen, FileEdit } from 'lucide-react';
import { useState } from 'react';

interface ToolBlockProps {
  tool: string;
  args: any;
  summary?: string;
  success?: boolean;
}

export const ToolBlock = ({ tool, args, summary, success }: ToolBlockProps) => {
  const [open, setOpen] = useState(false);

  // Tool ismine göre ikon ve etiket belirle
  let Icon = Wrench;
  let label = tool;
  
  if (tool === 'read_file') {
    Icon = FileSearch;
    label = 'Dosya okundu';
  } else if (tool === 'search_in_project') {
    Icon = Search;
    label = 'Projede arandı';
  } else if (tool === 'list_directory') {
    Icon = FolderOpen;
    label = 'Klasör listelendi';
  } else if (tool === 'write_file') {
    Icon = FileEdit;
    label = 'Dosya yazıldı';
  } else if (tool === 'find_files') {
    Icon = Search;
    label = 'Dosyalar arandı';
  }

  // Eğer tool bitmediyse "okunuyor...", bittiyse "okundu" yazsın
  if (!summary) {
    label = label.replace('okundu', 'okunuyor...')
                 .replace('arandı', 'aranıyor...')
                 .replace('listelendi', 'listeleniyor...')
                 .replace('yazıldı', 'yazılıyor...');
  }

  const isSuccess = success ?? true;
  const colorClass = isSuccess ? 'text-slate-500 hover:text-slate-400' : 'text-red-500 hover:text-red-400';
  const dotColor = isSuccess ? 'bg-slate-600 group-hover:bg-slate-500' : 'bg-red-600 group-hover:bg-red-500';

  return (
    <div className="mb-2">
      <button
        onClick={() => setOpen(v => !v)}
        className={`flex items-center gap-1.5 text-[11px] transition-colors select-none group ${colorClass}`}
      >
        <span className={`w-1.5 h-1.5 rounded-full transition-colors ${dotColor}`} />
        <Icon size={12} className="opacity-70" />
        <span className="font-medium">{label}</span>
        {summary && <span className="opacity-60 ml-1 truncate max-w-[200px]">- {summary}</span>}
        <motion.span
          animate={{ rotate: open ? 90 : 0 }}
          transition={{ duration: 0.15 }}
          className="flex items-center ml-1"
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
            <div className="mt-2 pl-3 border-l border-slate-800 max-h-[250px] overflow-y-auto bg-slate-900/30 p-2 rounded-r-md">
              <div className="text-[10px] text-slate-400 font-mono mb-1">PARAMETRELER:</div>
              <pre className="text-[11px] text-slate-300 whitespace-pre-wrap font-mono m-0">
                {JSON.stringify(args, null, 2)}
              </pre>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
