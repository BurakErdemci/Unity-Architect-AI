import { AnimatePresence, motion } from 'framer-motion';
import { ChevronRight, Wrench, FileSearch, Search, FolderOpen, FileEdit, Bot } from 'lucide-react';
import { useState } from 'react';

interface ToolBlockProps {
  tool: string;
  args?: any;
  summary?: string;
  success?: boolean;
  output?: string;
}

export const ToolBlock = ({ tool, args, summary, success, output }: ToolBlockProps) => {
  const [open, setOpen] = useState(false);

  // Tool ismine göre ikon ve etiket belirle (Claude Code built-in + eski MCP isimleri)
  const TOOL_META: Record<string, { icon: any; label: string }> = {
    // Claude Code built-in araçları (SDK session)
    Read:      { icon: FileSearch, label: 'Dosya okuyor' },
    Glob:      { icon: Search,     label: 'Dosya arıyor' },
    Grep:      { icon: Search,     label: 'Kod içinde arıyor' },
    Bash:      { icon: Wrench,     label: 'Komut çalıştırıyor' },
    Edit:      { icon: FileEdit,   label: 'Dosya düzenliyor' },
    MultiEdit: { icon: FileEdit,   label: 'Dosya düzenliyor' },
    Write:     { icon: FileEdit,   label: 'Dosya yazıyor' },
    TodoWrite: { icon: Wrench,     label: 'Plan yapıyor' },
    Subagent:  { icon: Bot,        label: 'Subagent' },
    WebSearch: { icon: Search,     label: "Web'de arıyor" },
    WebFetch:  { icon: Search,     label: 'Sayfa getiriyor' },
    // eski MCP isimleri (geçmiş sohbet kayıtları)
    read_file:         { icon: FileSearch, label: 'Dosya okundu' },
    search_in_project: { icon: Search,     label: 'Projede arandı' },
    list_directory:    { icon: FolderOpen, label: 'Klasör listelendi' },
    write_file:        { icon: FileEdit,   label: 'Dosya yazıldı' },
    find_files:        { icon: Search,     label: 'Dosyalar arandı' },
  };

  let Icon = Wrench;
  let label = tool;
  const meta = TOOL_META[tool];
  if (meta) {
    Icon = meta.icon;
    label = meta.label;
  } else if (tool.startsWith('mcp__')) {
    label = 'Unity aracı: ' + tool.replace('mcp__unityMCP__', '').replace('mcp__', '');
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
            <div className="mt-2 pl-3 border-l border-slate-800 max-h-[300px] overflow-y-auto bg-slate-900/30 p-2 rounded-r-md space-y-2">
              {(() => {
                const hasArgs = args != null && (typeof args !== 'object' || Object.keys(args).length > 0);
                const hasOutput = !!(output && output.trim());
                if (!hasArgs && !hasOutput) {
                  return <div className="text-[10.5px] text-slate-500 font-mono">Bu adım için detay kaydedilmedi.</div>;
                }
                return (
                  <>
                    {hasArgs && (
                      <div>
                        <div className="text-[10px] text-slate-400 font-mono mb-1">PARAMETRELER:</div>
                        <pre className="text-[11px] text-slate-300 whitespace-pre-wrap font-mono m-0 break-all">
                          {JSON.stringify(args, null, 2)}
                        </pre>
                      </div>
                    )}
                    {hasOutput && (
                      <div>
                        <div className={`text-[10px] font-mono mb-1 ${isSuccess ? 'text-emerald-500/80' : 'text-red-400'}`}>ÇIKTI:</div>
                        <pre className="text-[11px] text-slate-300 whitespace-pre-wrap font-mono m-0 break-all">
                          {output}
                        </pre>
                      </div>
                    )}
                  </>
                );
              })()}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
