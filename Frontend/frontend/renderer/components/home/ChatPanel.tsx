import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { useLang } from '../../lib/i18n';
import {
  User,
  Cpu,
  History,
  Trash2,
  AlertTriangle,
  Bot
} from 'lucide-react';
import { Message, UserData, FileEntry, GenerationMode, ChatActivity } from './types';
import { ModelAvatar } from './ModelAvatar';
import { MarkdownRenderer } from './MarkdownRenderer';
import { SlashCommandCard } from './SlashCommandCard';
import { ThinkingBlock } from './ThinkingBlock';
import { ToolGroup } from './ToolGroup';
import { FileCreationApproval, PendingFile } from './FileCreationApproval';
import { FileDeleteApproval } from './FileDeleteApproval';
import { CommandApproval } from './CommandApproval';
import { QuestionApproval } from './QuestionApproval';
import { DiffViewer, DiffData } from './DiffViewer';
import AgentPlan, { Task as AgentTask } from '../ui/agent-plan';

interface ChatPanelProps {
  messages: Message[];
  activeConvId: number | null;
  user: UserData | null;
  loading: boolean;
  clearHistory: () => void;
  lang: string;
  effectiveProvider: string;
  modelName?: string;
  thinkingLevel: 'low' | 'medium' | 'high' | 'off';
  workspacePath: string | null;
  handleExportToUnity: (code: string) => void;
  pendingGenFiles: { files: PendingFile[]; messageId: number } | null;
  setPendingGenFiles: (val: any) => void;
  pendingFix: { data: DiffData; messageId?: number; applied?: boolean; gateId?: string } | null;
  setPendingFix: (val: any) => void;
  openedFilePath: string | null;
  setCode: (code: string) => void;
  refreshFileTree: () => void;
  analyzeProject: (silent?: boolean) => void;
  openFile: (path: string) => void;
  sendMessage: (msg: string) => void;
  currentPlan: AgentTask[];
  messagesEndRef: React.RefObject<HTMLDivElement>;
  ipc: any;
  showToast: (msg: string, type: 'success' | 'error' | 'warning' | 'info') => void;
  diffFile: any | null;
  setDiffFile: (val: any | null) => void;
  pendingDelete: { path: string; messageId: number } | null;
  setPendingDelete: (val: any | null) => void;
  pendingCommand: { command: string; gateId: string; messageId: number } | null;
  setPendingCommand: (val: any | null) => void;
  onApproveCommand: (gateId: string, approved: boolean) => Promise<void>;
  pendingQuestion: { questions: any[]; gateId: string; messageId: number } | null;
  setPendingQuestion: (val: any | null) => void;
  onAnswerQuestion: (gateId: string, answers: Record<string, string>) => Promise<void>;
  deleteFile: (path: string) => Promise<void>;
  setIsTerminalOpen: (val: boolean) => void;
  // Canlı aktivite (status event'leri): "🤖 Subagent çalışıyor · 45.2k token" gibi.
  activity?: ChatActivity | null;
}

export const ChatPanel: React.FC<ChatPanelProps> = ({
  messages,
  activeConvId,
  user,
  loading,
  clearHistory,
  effectiveProvider,
  modelName,
  thinkingLevel,
  workspacePath,
  handleExportToUnity,
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
  currentPlan,
  messagesEndRef,
  ipc,
  showToast,
  diffFile,
  setDiffFile,
  pendingDelete,
  setPendingDelete,
  pendingCommand,
  setPendingCommand,
  onApproveCommand,
  pendingQuestion,
  setPendingQuestion,
  onAnswerQuestion,
  deleteFile,
  activity,
}) => {
  const { t } = useLang();

  // 12400 → "12.4k" (aktivite satırı + usage özeti için)
  const fmtTok = (n?: number | null) =>
    typeof n === 'number' && n > 0 ? (n >= 1000 ? `${(n / 1000).toFixed(1)}k` : `${n}`) : null;

  if (!activeConvId) {
    return (
      <div className="flex flex-col h-full">
        <div className="flex-1 flex flex-col items-center justify-center text-slate-600 gap-3">
          <Bot size={32} className="opacity-20" />
          <p className="text-[11px] text-center">
            {t('chat.empty').split('\n').map((line, i) => <span key={i}>{line}{i === 0 && <br />}</span>)}
          </p>
        </div>
      </div>
    );
  }

  if (messages.length === 0 && !loading) {
    return (
      <div className="flex flex-col h-full">
        <div className="flex-1 flex items-center justify-center">
          <Bot size={20} className="opacity-10 text-blue-500" />
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6 custom-scrollbar scroll-smooth">
      <div className="max-w-4xl mx-auto space-y-6">
        {messages.map((msg, msgIdx) => {
          // /usage, /context → özel kart. Canlı turda mesaj etiketli gelir (slashCommand);
          // geçmişten yüklenende etiket yok → bir önceki kullanıcı mesajından tespit et.
          let slashCmd: string | undefined = msg.slashCommand;
          if (!slashCmd && msg.role === 'assistant' && msgIdx > 0) {
            const prevC = (messages[msgIdx - 1]?.role === 'user' ? messages[msgIdx - 1].content : '').trim().toLowerCase();
            if (prevC === '/usage') slashCmd = 'usage';
            else if (prevC === '/context') slashCmd = 'context';
          }
          return (
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

                  {/* Thinking Block */}
                  {msg.thinking && (
                    <ThinkingBlock thinking={msg.thinking!} durationMs={msg.thinking_duration_ms} />
                  )}

                  {/* Tool Blocks (3'ten fazlaysa collapse grubu) */}
                  <ToolGroup tools={msg.tool_calls} />
                  <ToolGroup tools={msg.tools} />

                  {/* Content or Loading Typing */}
                  {(msg.content === "" || !msg.content) && loading && msgIdx === messages.length - 1 ? (
                    <div className="bg-[#000000] rounded-lg px-4 py-3 border border-slate-800 inline-flex items-center gap-2.5">
                      <div className="flex items-center gap-1.5">
                        <div className="typing-dot h-2 w-2 bg-blue-500 rounded-full" />
                        <div className="typing-dot h-2 w-2 bg-blue-500 rounded-full" />
                        <div className="typing-dot h-2 w-2 bg-blue-500 rounded-full" />
                      </div>
                      {activity ? (
                        <span className="text-[11px] text-violet-300">
                          {activity.detail}
                          {fmtTok(activity.tokens) && <span className="text-slate-500"> · {fmtTok(activity.tokens)} token</span>}
                        </span>
                      ) : (
                        thinkingLevel !== 'off' && <span className="text-[11px] text-violet-400 animate-pulse">{t('chat.thinking')}</span>
                      )}
                    </div>
                  ) : slashCmd ? (
                    <SlashCommandCard command={slashCmd} text={msg.content} workspacePath={workspacePath} />
                  ) : (
                    <div className="prose prose-invert max-w-none text-[13px] leading-relaxed prose-p:my-2 prose-headings:my-3 prose-ul:my-2 prose-li:my-0.5 prose-pre:bg-slate-900 prose-pre:border prose-pre:border-slate-800 prose-a:text-emerald-400">
                      <MarkdownRenderer
                        content={msg.content.replace('<!-- SCOPE_WARNING_ACTIVE -->', '')}
                        workspacePath={workspacePath}
                        onExportToUnity={handleExportToUnity}
                      />
                    </div>
                  )}

                  {/* Tur istatistiği: süre + token (backend turn_usage event'i) */}
                  {msg.usage && (msg.usage.output_tokens || msg.usage.duration_ms) ? (
                    <div className="mt-1.5 text-[10.5px] text-slate-600 select-none">
                      {msg.usage.duration_ms ? `⏱ ${Math.max(1, Math.round(msg.usage.duration_ms / 1000))}sn` : null}
                      {fmtTok(msg.usage.input_tokens) ? ` · ↑${fmtTok(msg.usage.input_tokens)}` : null}
                      {fmtTok(msg.usage.output_tokens) ? ` · ↓${fmtTok(msg.usage.output_tokens)} token` : null}
                    </div>
                  ) : null}

                  {/* Scope Warning Buttons */}
                  {msg.content.includes('SCOPE_WARNING_ACTIVE') && msgIdx === messages.length - 1 && !loading && (
                    <div className="flex gap-2 mt-3">
                      <button onClick={() => sendMessage('Tam Sistemi Üret')} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600/20 border border-blue-500/30 text-blue-300 text-[12px] font-medium hover:bg-blue-600/35 transition-colors"> ✅ {t('chat.generateFull')} </button>
                      <button onClick={() => sendMessage('Basit Versiyon')} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-700/40 border border-slate-600/30 text-slate-300 text-[12px] font-medium hover:bg-slate-700/60 transition-colors"> ⚡ {t('chat.simpleVersion')} </button>
                    </div>
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
                        // onApproveCommand kuyruktaki sıradaki onayı kendi gösterir → burada setPendingCommand(null) ÇAĞIRMA
                        await onApproveCommand(pendingCommand.gateId, true);
                        showToast('Komut onaylandı — çalışıyor...', 'success');
                      }}
                      onCancel={async () => {
                        await onApproveCommand(pendingCommand.gateId, false);
                        showToast('Komut iptal edildi', 'info');
                      }}
                    />
                  )}

                  {/* AskUserQuestion (A/B/C seçim kartı) */}
                  {pendingQuestion && pendingQuestion.messageId === msg.id && (
                    <QuestionApproval
                      questions={pendingQuestion.questions}
                      onSubmit={async (answers) => {
                        // onAnswerQuestion kuyruktaki sıradaki soruyu kendi gösterir
                        await onAnswerQuestion(pendingQuestion.gateId, answers);
                      }}
                    />
                  )}

                  {/* Diff Viewer */}
                  {pendingFix && pendingFix.messageId === msg.id && (
                    <DiffViewer
                      diffData={pendingFix.data}
                      filename={pendingFix.data?.editor_hint?.split('/').pop() || (openedFilePath ? openedFilePath.split('/').pop() : undefined)}
                      applied={pendingFix.applied}
                      onAccept={async (fixedCode) => {
                        // MCP onayı: gate varsa backend'e bildir, sonra IPC ile yaz
                        if (pendingFix.gateId) {
                          const filePath = pendingFix.data?.editor_hint || openedFilePath;
                          await fetch(`${(window as any).__API__ || ''}/mcp-approval-respond/${pendingFix.gateId}`, {
                            method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Session-Token': user?.sessionToken ?? '' },
                            body: JSON.stringify({ approved: true }),
                          }).catch(() => {});
                          // MCP server zaten dosyayı yazar, sadece editörü güncelle
                          if (filePath) setCode(fixedCode);
                          setPendingFix(null);
                          refreshFileTree();
                          showToast('✅ Değişiklik onaylandı', 'success');
                          return;
                        }
                        // Normal (API) onayı
                        setCode(fixedCode);
                        setPendingFix((prev: any) => prev ? { ...prev, applied: true } : null);
                        if (ipc && openedFilePath && workspacePath) {
                          await ipc.invoke('write-file', openedFilePath, fixedCode, workspacePath);
                          refreshFileTree();
                          setTimeout(() => analyzeProject(true), 1500);
                        }
                        showToast(`✅ Dosya güncellendi`, 'success');
                      }}
                      onReject={async () => {
                        if (pendingFix.gateId) {
                          await fetch(`${(window as any).__API__ || ''}/mcp-approval-respond/${pendingFix.gateId}`, {
                            method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Session-Token': user?.sessionToken ?? '' },
                            body: JSON.stringify({ approved: false }),
                          }).catch(() => {});
                        }
                        setPendingFix(null);
                      }}
                    />
                  )}
                </div>
              </div>
            ) : (
              // Kullanıcı Mesajı
              <div className="max-w-[85%]">
                <div className="bg-blue-600/15 border border-blue-500/20 rounded-xl rounded-tr-sm px-3.5 py-2.5">
                  {msg.images && msg.images.length > 0 && (
                    <div className="flex gap-2 mb-3 flex-wrap">
                      {msg.images.map((img, i) => (
                        <img 
                          key={i} 
                          src={img} 
                          alt="user upload" 
                          className="max-w-[200px] max-h-[200px] rounded-lg border border-white/10 shadow-lg cursor-zoom-in hover:scale-[1.02] transition-transform" 
                          onClick={() => window.open(img, '_blank')}
                        />
                      ))}
                    </div>
                  )}
                  <div className="text-[13px] text-slate-200 whitespace-pre-wrap break-words">
                    <MarkdownRenderer content={msg.content} />
                  </div>
                </div>
              </div>
            )}
          </div>
          );
        })}

        {/* Canlı aktivite şeridi: metin akmaya başladıktan sonra da Claude'un çalıştığı
            görünür kalsın (typing bubble yalnızca içerik boşken görünüyor). */}
        {loading && activity && messages.length > 0 && !!messages[messages.length - 1]?.content && (
          <div className="flex items-center gap-2 mb-6 pl-8 text-[11.5px] text-slate-400">
            <div className="flex items-center gap-1">
              <div className="typing-dot h-1.5 w-1.5 bg-violet-400 rounded-full" />
              <div className="typing-dot h-1.5 w-1.5 bg-violet-400 rounded-full" />
              <div className="typing-dot h-1.5 w-1.5 bg-violet-400 rounded-full" />
            </div>
            <span className="text-violet-300">{activity.detail}</span>
            {fmtTok(activity.tokens) && <span className="text-slate-500">· {fmtTok(activity.tokens)} token</span>}
          </div>
        )}

        {/* AgentPlan Indicator */}
        {loading && currentPlan.length > 0 && (
          <div className="flex gap-2.5 chat-message-enter mb-6">
            <ModelAvatar provider={effectiveProvider} size={13} />
            <div className="flex-1 min-w-0">
              <AgentPlan tasks={currentPlan} />
            </div>
          </div>
        )}
        {/* MCP Onay Kartları — mesaj ID'sinden bağımsız, her zaman göster */}
        {pendingGenFiles?.messageId === -999 && (
          <div className="px-4 pb-2">
            <FileCreationApproval
              files={pendingGenFiles.files}
              autoAccept={false}
              setDiffFile={setDiffFile}
              onOpenFile={openFile}
              onAcceptOne={async (file) => {
                const gateId = (window as any).__mcpWriteGate;
                if (gateId) await fetch(`${(window as any).__API__ || ''}/mcp-approval-respond/${gateId}`, {
                  method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Session-Token': user?.sessionToken ?? '' },
                  body: JSON.stringify({ approved: true }),
                }).catch(() => {});
                refreshFileTree();
                showToast(`✅ ${file.name} oluşturuldu`, 'success');
              }}
              onSkipOne={() => {}}
              onAcceptAll={async () => {
                const gateId = (window as any).__mcpWriteGate;
                if (gateId) await fetch(`${(window as any).__API__ || ''}/mcp-approval-respond/${gateId}`, {
                  method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Session-Token': user?.sessionToken ?? '' },
                  body: JSON.stringify({ approved: true }),
                }).catch(() => {});
                refreshFileTree();
                showToast('✅ Dosya oluşturuldu', 'success');
              }}
              onDone={() => setPendingGenFiles(null)}
            />
          </div>
        )}
        {pendingDelete?.messageId === -999 && (
          <div className="px-4 pb-2">
            <FileDeleteApproval
              path={pendingDelete.path}
              onConfirm={async () => {
                const gateId = (window as any).__mcpDeleteGate;
                if (gateId) {
                  await fetch(`${(window as any).__API__ || ''}/mcp-approval-respond/${gateId}`, {
                    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Session-Token': user?.sessionToken ?? '' },
                    body: JSON.stringify({ approved: true }),
                  }).catch(() => {});
                }
                setPendingDelete(null);
                // MCP server approval'ı polling ile ~500ms gecikmeli görür → dosyayı siler.
                // Refresh'i geciktirmezsek dosya henüz silinmemiş olur.
                setTimeout(() => refreshFileTree(), 900);
                showToast('🗑️ Dosya silindi', 'info');
              }}
              onCancel={async () => {
                const gateId = (window as any).__mcpDeleteGate;
                if (gateId) {
                  await fetch(`${(window as any).__API__ || ''}/mcp-approval-respond/${gateId}`, {
                    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Session-Token': user?.sessionToken ?? '' },
                    body: JSON.stringify({ approved: false }),
                  }).catch(() => {});
                }
                setPendingDelete(null);
              }}
            />
          </div>
        )}
        {pendingCommand?.messageId === -999 && (
          <div className="px-4 pb-2">
            <CommandApproval
              command={pendingCommand.command}
              onConfirm={async () => {
                const gateId = pendingCommand.gateId;
                await fetch(`${(window as any).__API__ || ''}/mcp-approval-respond/${gateId}`, {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json', 'X-Session-Token': user?.sessionToken ?? '' },
                  body: JSON.stringify({ approved: true }),
                }).catch(() => {});
                setPendingCommand(null);
                showToast('Komut onaylandı — çalışıyor...', 'success');
              }}
              onCancel={async () => {
                const gateId = pendingCommand.gateId;
                await fetch(`${(window as any).__API__ || ''}/mcp-approval-respond/${gateId}`, {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json', 'X-Session-Token': user?.sessionToken ?? '' },
                  body: JSON.stringify({ approved: false }),
                }).catch(() => {});
                setPendingCommand(null);
                showToast('Komut iptal edildi', 'info');
              }}
            />
          </div>
        )}

        <div ref={messagesEndRef} className="h-4" />
      </div>
    </div>
  );
};
