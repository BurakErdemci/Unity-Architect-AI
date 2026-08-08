import { AnimatePresence, motion } from 'framer-motion';
import { ChevronRight, Wrench, FileSearch, Search, FolderOpen, FileEdit, Bot } from 'lucide-react';
import { useState } from 'react';
import { useLang } from '../../lib/i18n';

interface ToolBlockProps {
  tool: string;
  args?: any;
  summary?: string;
  success?: boolean;
  output?: string;
}

export const ToolBlock = ({ tool, args, summary, success, output }: ToolBlockProps) => {
  const [open, setOpen] = useState(false);
  const { t } = useLang();

  // Tool ismine göre ikon ve etiket belirle (Claude Code built-in + eski MCP isimleri)
  const TOOL_META: Record<string, { icon: any; label: string }> = {
    // Claude Code built-in araçları (SDK session)
    Read:      { icon: FileSearch, label: t('tool.read') },
    Glob:      { icon: Search,     label: t('tool.glob') },
    Grep:      { icon: Search,     label: t('tool.grep') },
    Bash:      { icon: Wrench,     label: t('tool.bash') },
    Edit:      { icon: FileEdit,   label: t('tool.edit') },
    MultiEdit: { icon: FileEdit,   label: t('tool.edit') },
    Write:     { icon: FileEdit,   label: t('tool.write') },
    TodoWrite: { icon: Wrench,     label: t('tool.todo') },
    Subagent:  { icon: Bot,        label: 'Subagent' },
    WebSearch: { icon: Search,     label: t('tool.webSearch') },
    WebFetch:  { icon: Search,     label: t('tool.webFetch') },
    // eski MCP isimleri (geçmiş sohbet kayıtları)
    read_file:         { icon: FileSearch, label: t('tool.readFileDone') },
    search_in_project: { icon: Search,     label: t('tool.searchProjectDone') },
    list_directory:    { icon: FolderOpen, label: t('tool.listDirDone') },
    write_file:        { icon: FileEdit,   label: t('tool.writeFileDone') },
    find_files:        { icon: Search,     label: t('tool.findFilesDone') },
  };

  let Icon = Wrench;
  let label = tool;
  const meta = TOOL_META[tool];
  if (meta) {
    Icon = meta.icon;
    label = meta.label;
  } else if (tool.startsWith('mcp__')) {
    label = t('tool.unityPrefix') + tool.replace('mcp__unityMCP__', '').replace('mcp__', '');
  }

  const isSuccess = success ?? true;
  const colorClass = isSuccess
    ? 'text-slate-500 hover:text-slate-300 border-white/[0.07] bg-white/[0.02] hover:bg-white/[0.05] hover:border-white/[0.12]'
    : 'text-red-400 hover:text-red-300 border-red-500/20 bg-red-500/[0.04] hover:bg-red-500/[0.08]';
  const dotColor = isSuccess ? 'bg-emerald-500/60' : 'bg-red-500';

  return (
    <div className="mb-1.5">
      <button
        onClick={() => setOpen(v => !v)}
        className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[11px] transition-colors select-none group max-w-full ${colorClass}`}
      >
        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${dotColor}`} />
        <Icon size={12} className="opacity-70 shrink-0" />
        <span className="font-medium shrink-0">{label}</span>
        {summary && <span className="opacity-60 truncate max-w-[200px]">— {summary}</span>}
        <motion.span
          animate={{ rotate: open ? 90 : 0 }}
          transition={{ duration: 0.15 }}
          className="flex items-center shrink-0"
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
            <div className="mt-1.5 max-h-[300px] overflow-y-auto custom-scrollbar bg-white/[0.02] border border-white/[0.06] p-2.5 rounded-lg space-y-2">
              {(() => {
                const hasArgs = args != null && (typeof args !== 'object' || Object.keys(args).length > 0);
                const hasOutput = !!(output && output.trim());
                if (!hasArgs && !hasOutput) {
                  return <div className="text-[10.5px] text-slate-500 font-mono">{t('tool.noDetail')}</div>;
                }
                return (
                  <>
                    {hasArgs && (
                      <div>
                        <div className="text-[10px] text-slate-400 font-mono mb-1">{t('tool.params')}</div>
                        <pre className="text-[11px] text-slate-300 whitespace-pre-wrap font-mono m-0 break-all">
                          {JSON.stringify(args, null, 2)}
                        </pre>
                      </div>
                    )}
                    {hasOutput && (
                      <div>
                        <div className={`text-[10px] font-mono mb-1 ${isSuccess ? 'text-emerald-500/80' : 'text-red-400'}`}>{t('tool.output')}</div>
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
