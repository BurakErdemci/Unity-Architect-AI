import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  User, 
  Cpu, 
  History, 
  Trash2, 
  Brain, 
  ChevronDown, 
  AlertTriangle, 
  Sparkles,
  X,
  Bot
} from 'lucide-react';
import { Message, UserData, FileEntry, GenerationMode } from './types';
import { ModelAvatar } from './ModelAvatar';
import { MarkdownRenderer } from './MarkdownRenderer';
import { ThinkingBlock } from './ThinkingBlock';
import { ToolBlock } from './ToolBlock';
import { FileCreationApproval, PendingFile } from './FileCreationApproval';
import { FileDeleteApproval } from './FileDeleteApproval';
import { CommandApproval } from './CommandApproval';
import { DiffViewer, DiffData } from './DiffViewer';
import AgentPlan, { Task as AgentTask } from '../ui/agent-plan';

interface ChatPanelProps {
  messages: Message[];
  activeConvId: number | null;
  user: UserData | null;
  loading: boolean;
  clearHistory: () => void;
  lang: string;
  wisdomSummary: string | null;
  isWisdomExpanded: boolean;
  setIsWisdomExpanded: (val: boolean) => void;
  effectiveProvider: string;
  useThinking: boolean;
  workspacePath: string | null;
  handleExportToUnity: (code: string) => void;
  pendingPlan: { content: string; originalMessage: string; mode: GenerationMode } | null;
  setPendingPlan: (val: any) => void;
  pendingGenFiles: { files: PendingFile[]; messageId: number } | null;
  setPendingGenFiles: (val: any) => void;
  pendingFix: { data: DiffData; messageId?: number; applied?: boolean } | null;
  setPendingFix: (val: any) => void;
  openedFilePath: string | null;
  setCode: (code: string) => void;
  refreshFileTree: () => void;
  analyzeProject: (silent?: boolean) => void;
  openFile: (path: string) => void;
  sendMessage: (msg: string) => void;
  onConfirmPlan: (msg: string, mode: GenerationMode) => void;
  currentPlan: AgentTask[];
  messagesEndRef: React.RefObject<HTMLDivElement>;
  generationMode: GenerationMode;
  appMode: string;
  aiConfig: any;
  gpt54OrToggled: boolean;
  axios: any;
  API: string;
  ipc: any;
  suggestFilePath: (name: string) => string;
  showToast: (msg: string, type: 'success' | 'error' | 'warning' | 'info') => void;
  diffFile: any | null;
  setDiffFile: (val: any | null) => void;
  pendingDelete: { path: string; messageId: number } | null;
  setPendingDelete: (val: any | null) => void;
  pendingCommand: { command: string; messageId: number } | null;
  setPendingCommand: (val: any | null) => void;
  deleteFile: (path: string) => Promise<void>;
  setIsTerminalOpen: (val: boolean) => void;
}

export const ChatPanel: React.FC<ChatPanelProps> = ({
  messages,
  activeConvId,
  user,
  loading,
  clearHistory,
  lang,
  wisdomSummary,
  isWisdomExpanded,
  setIsWisdomExpanded,
  effectiveProvider,
  useThinking,
  workspacePath,
  handleExportToUnity,
  pendingPlan,
  setPendingPlan,
  pendingGenFiles,
  setPendingGenFiles,
  pendingFix,
  setPendingFix,
  openedFilePath,
  setCode,
  refreshFileTree,
  analyzeProject,
  openFile,
  sendMessage,
  onConfirmPlan,
  currentPlan,
  messagesEndRef,
  generationMode,
  appMode,
  aiConfig,
  gpt54OrToggled,
  axios,
  API,
  ipc,
  suggestFilePath,
  showToast,
  diffFile,
  setDiffFile,
  pendingDelete,
  setPendingDelete,
  pendingCommand,
  setPendingCommand,
  deleteFile,
  setIsTerminalOpen
}) => {
  if (!activeConvId) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-slate-600 gap-3">
        <Bot size={32} className="opacity-20" />
        <p className="text-[11px] text-center">
          Sohbet başlatmak için soldan<br />bir sohbet seçin veya oluşturun
        </p>
      </div>
    );
  }

  if (messages.length === 0 && !loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Sparkles size={20} className="opacity-10 text-blue-500" />
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6 custom-scrollbar scroll-smooth">
      <div className="max-w-4xl mx-auto space-y-6">
        {/* ARCHITECT WISDOM PANEL */}
        {wisdomSummary && (
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            className="mb-8 bg-blue-500/5 border border-blue-500/20 rounded-xl overflow-hidden"
          >
            <div 
              className="px-4 py-2.5 flex items-center justify-between cursor-pointer hover:bg-blue-500/10 transition-colors"
              onClick={() => setIsWisdomExpanded(!isWisdomExpanded)}
            >
              <div className="flex items-center gap-2 text-blue-400 font-medium text-[12px]">
                <Brain size={14} />
                <span>Architect Wisdom — Proje Özeti</span>
              </div>
              <ChevronDown 
                size={14} 
                className={`text-slate-500 transition-transform duration-300 ${isWisdomExpanded ? 'rotate-180' : ''}`} 
              />
            </div>
            
            <AnimatePresence>
              {isWisdomExpanded && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  className="overflow-hidden"
                >
                  <div className="px-5 pb-5 pt-1 text-slate-300 text-[12px] leading-relaxed border-t border-blue-500/10">
                    <MarkdownRenderer content={wisdomSummary} />
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>
        )}

        {messages.map((msg, msgIdx) => (
          <div key={msg.id} className={`chat-message-enter ${msg.role === 'user' ? 'flex justify-end' : ''}`}>
            {msg.role === 'assistant' ? (
              <div className="flex gap-2.5 max-w-full group">
                <ModelAvatar provider={msg.provider || effectiveProvider} size={13} className="mt-0.5" />
                <div className="flex-1 min-w-0">
                  {/* Statik Bulgular */}
                  {msg.smells && msg.smells.length > 0 && (
                    <div className="mb-3 bg-[#000000] rounded-lg border border-orange-500/20 p-3">
                      <div className="flex items-center gap-1.5 mb-2">
                        <AlertTriangle size={12} className="text-orange-400" />
                        <span className="text-[10px] font-semibold text-orange-400 uppercase tracking-wider">Static Analysis</span>
                      </div>
                      <div className="space-y-1.5">
                        {msg.smells.map((s: any, i: number) => (
                          <div key={i} className="text-[11px] text-slate-400 flex items-start gap-2">
                            <span className="bg-orange-500/10 text-orange-500 px-1.5 py-0.5 rounded text-[9px] font-bold shrink-0">
                              L{s.line || "?"}
                            </span>
                            <span>{s.msg}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Pipeline Skor Badge */}
                  {msg.pipeline && (
                    <div className="mb-3 space-y-3">
                      <div className="bg-[#000000] rounded-lg border border-blue-500/20 p-3">
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-2">
                            <div className="w-6 h-6 rounded bg-blue-500/20 flex items-center justify-center">
                              <Sparkles size={12} className="text-blue-400" />
                            </div>
                            <span className="text-xs font-bold text-slate-200">AI Kalite Skoru</span>
                          </div>
                          <div className="px-2 py-0.5 rounded text-[10px] font-bold bg-blue-500/20 text-blue-400">
                            {msg.pipeline.score.toFixed(1)}/10
                          </div>
                        </div>
                        <div className="flex items-center gap-2 text-[10px] mb-2">
                          {msg.pipeline.severity_counts?.critical > 0 && <span className="text-red-400">🔴 {msg.pipeline.severity_counts.critical}</span>}
                          {msg.pipeline.severity_counts?.warning > 0 && <span className="text-yellow-400">🟡 {msg.pipeline.severity_counts.warning}</span>}
                          {msg.pipeline.severity_counts?.info > 0 && <span className="text-blue-400">🔵 {msg.pipeline.severity_counts.info}</span>}
                        </div>
                        <div className="text-[10px] text-slate-400 leading-relaxed max-h-24 overflow-y-auto custom-scrollbar pr-2">
                          {msg.pipeline.summary}
                        </div>
                        <div className="text-[9px] text-slate-600 flex items-center gap-1 mt-2 border-t border-slate-800 pt-2">
                          <span>⚡ {(msg.pipeline.total_duration_ms / 1000).toFixed(1)}s</span>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Thinking Block */}
                  {msg.thinking && (
                    <ThinkingBlock thinking={msg.thinking!} durationMs={msg.thinking_duration_ms} />
                  )}

                  {/* Tool Blocks */}
                  {msg.tool_calls && msg.tool_calls.length > 0 && (
                    <div className="flex flex-col gap-1 mb-3">
                      {msg.tool_calls.map((tc, idx) => (
                        <ToolBlock key={idx} tool={tc.tool} args={tc.args} summary={tc.summary} success={tc.success} />
                      ))}
                    </div>
                  )}
                  {msg.tools && msg.tools.length > 0 && (
                    <div className="flex flex-col gap-1 mb-3">
                      {msg.tools.map((tc, idx) => (
                        <ToolBlock key={idx} tool={tc.tool} args={tc.args} summary={tc.summary} success={tc.success} />
                      ))}
                    </div>
                  )}

                  {/* Content or Loading Typing */}
                  {(msg.content === "" || !msg.content) && loading && msgIdx === messages.length - 1 ? (
                    <div className="bg-[#000000] rounded-lg px-4 py-3 border border-slate-800 inline-flex items-center gap-2.5">
                      <div className="flex items-center gap-1.5">
                        <div className="typing-dot h-2 w-2 bg-blue-500 rounded-full" />
                        <div className="typing-dot h-2 w-2 bg-blue-500 rounded-full" />
                        <div className="typing-dot h-2 w-2 bg-blue-500 rounded-full" />
                      </div>
                      {useThinking && <span className="text-[11px] text-violet-400 animate-pulse">düşünüyor...</span>}
                    </div>
                  ) : (
                    <div className="prose prose-invert max-w-none text-[13px] leading-relaxed prose-p:my-2 prose-headings:my-3 prose-ul:my-2 prose-li:my-0.5 prose-pre:bg-slate-900 prose-pre:border prose-pre:border-slate-800 prose-a:text-emerald-400">
                      <MarkdownRenderer 
                        content={msg.content.replace('<!-- SCOPE_WARNING_ACTIVE -->', '')} 
                        workspacePath={workspacePath} 
                        onExportToUnity={handleExportToUnity} 
                      />
                    </div>
                  )}

                  {/* Scope Warning Buttons */}
                  {msg.content.includes('SCOPE_WARNING_ACTIVE') && msgIdx === messages.length - 1 && !loading && (
                    <div className="flex gap-2 mt-3">
                      <button onClick={() => sendMessage('Tam Sistemi Üret')} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600/20 border border-blue-500/30 text-blue-300 text-[12px] font-medium hover:bg-blue-600/35 transition-colors"> ✅ Tam Sistemi Üret </button>
                      <button onClick={() => sendMessage('Basit Versiyon')} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-700/40 border border-slate-600/30 text-slate-300 text-[12px] font-medium hover:bg-slate-700/60 transition-colors"> ⚡ Basit Versiyon </button>
                    </div>
                  )}

                  {/* Plan Approval Card */}
                  {pendingPlan && msgIdx === messages.length - 1 && msg.role === 'assistant' && (
                    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="mt-3 rounded-xl border border-blue-500/20 bg-blue-950/10 overflow-hidden">
                      <div className="flex items-center justify-between px-4 py-2.5 border-b border-blue-500/10">
                        <span className="text-[11px] font-semibold text-blue-300">Onaylıyor musun?</span>
                        <span className="text-[10px] text-slate-600">{pendingPlan.mode === 'step' ? 'Adım Adım' : 'Plan Modu'}</span>
                      </div>
                      <div className="flex gap-2 px-4 py-3">
                        <button
                          onClick={() => onConfirmPlan(pendingPlan.originalMessage, pendingPlan.mode)}
                          className="flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-[12px] font-semibold transition-colors"
                        >
                          Başlat
                        </button>
                        <button onClick={() => setPendingPlan(null)} className="px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-400 rounded-lg text-[12px] font-semibold transition-colors"> İptal </button>
                      </div>
                    </motion.div>
                  )}

                  {/* File Creation Approval */}
                  {pendingGenFiles && pendingGenFiles.messageId === msg.id && (
                    <FileCreationApproval
                      files={pendingGenFiles.files}
                      autoAccept={false}
                      onAcceptOne={async (file) => {
                        if (!ipc || !workspacePath) return;
                        await ipc.invoke('write-file', file.suggestedPath, file.code, workspacePath);
                        if (file.suggestedPath === openedFilePath) setCode(file.code);
                        refreshFileTree();
                      }}
                      onSkipOne={() => { }}
                      onAcceptAll={async (files) => {
                        if (!ipc || !workspacePath) return;
                        for (const file of files) {
                          await ipc.invoke('write-file', file.suggestedPath, file.code, workspacePath);
                          if (file.suggestedPath === openedFilePath) setCode(file.code);
                        }
                        refreshFileTree();
                        setTimeout(() => analyzeProject(true), 1500);
                      }}
                      onDone={() => {
                        setPendingGenFiles(null);
                        setDiffFile(null);
                      }}
                      setDiffFile={setDiffFile}
                      onOpenFile={(path) => openFile(path)}
                    />
                  )}

                  {/* File Deletion Approval */}
                  {pendingDelete && pendingDelete.messageId === msg.id && (
                    <FileDeleteApproval
                      path={pendingDelete.path}
                      onConfirm={async () => {
                        await deleteFile(pendingDelete.path);
                        setPendingDelete(null);
                      }}
                      onCancel={() => setPendingDelete(null)}
                    />
                  )}

                  {/* Terminal Command Approval */}
                  {pendingCommand && pendingCommand.messageId === msg.id && (
                    <CommandApproval
                      command={pendingCommand.command}
                      onConfirm={async () => {
                        if (ipc) {
                          setIsTerminalOpen(true);
                          // Komutu terminale gönder (Enter dahil)
                          await ipc.invoke('terminal-write', { 
                            id: 'main-terminal', 
                            data: pendingCommand.command + '\r' 
                          });
                          setPendingCommand(null);
                          showToast('Komut terminale gönderildi', 'success');
                        }
                      }}
                      onCancel={() => setPendingCommand(null)}
                    />
                  )}

                  {/* Diff Viewer */}
                  {pendingFix && pendingFix.messageId === msg.id && (
                    <DiffViewer
                      diffData={pendingFix.data}
                      filename={openedFilePath ? openedFilePath.split('/').pop() : undefined}
                      applied={pendingFix.applied}
                      onAccept={async (fixedCode) => {
                        setCode(fixedCode);
                        setPendingFix((prev: any) => prev ? { ...prev, applied: true } : null);
                        if (ipc && openedFilePath && workspacePath) {
                          await ipc.invoke('write-file', openedFilePath, fixedCode, workspacePath);
                          refreshFileTree();
                          setTimeout(() => analyzeProject(true), 1500);
                        }
                        showToast(`✅ Dosya güncellendi`, 'success');
                      }}
                      onReject={() => setPendingFix(null)}
                    />
                  )}
                </div>
              </div>
            ) : (
              // Kullanıcı Mesajı
              <div className="max-w-[85%]">
                <div className="bg-blue-600/15 border border-blue-500/20 rounded-xl rounded-tr-sm px-3.5 py-2.5">
                  <div className="text-[13px] text-slate-200 whitespace-pre-wrap break-words">
                    <MarkdownRenderer content={msg.content} />
                  </div>
                </div>
              </div>
            )}
          </div>
        ))}

        {/* AgentPlan Indicator */}
        {loading && currentPlan.length > 0 && (
          <div className="flex gap-2.5 chat-message-enter mb-6">
            <ModelAvatar provider={effectiveProvider} size={13} />
            <div className="flex-1 min-w-0">
              <AgentPlan tasks={currentPlan} />
            </div>
          </div>
        )}
        <div ref={messagesEndRef} className="h-4" />
      </div>
    </div>
  );
};
