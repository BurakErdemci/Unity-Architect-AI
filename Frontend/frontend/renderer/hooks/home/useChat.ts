import { useState, useCallback, useRef } from 'react';
import axios from 'axios';
import { Message, Conversation, UserData, AIConfig, GenerationMode } from '../../components/home/types';
import { PendingFile } from '../../components/home/FileCreationApproval';
import { Task } from '../../components/ui/agent-plan';

const ipc = typeof window !== 'undefined' ? (window as any).ipc : null;

export const useChat = (
  API: string,
  user: UserData | null,
  aiConfig: AIConfig,
  workspacePath: string | null,
  showToast: (msg: string, type: any) => void,
  refreshFileTree: () => void,
  suggestFilePath: (name: string) => string
) => {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConvId, setActiveConvId] = useState<number | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [chatInput, setChatInput] = useState('');
  const [wisdomSummary, setWisdomSummary] = useState<string | null>(null);
  const [isWisdomExpanded, setIsWisdomExpanded] = useState(true);
  const [currentPlan, setCurrentPlan] = useState<Task[]>([]);
  const [contextUsage, setContextUsage] = useState({ percent: 0, should_compact: false, message_count: 0 });
  const [isCompacting, setIsCompacting] = useState(false);
  const [isAnalyzingProject, setIsAnalyzingProject] = useState(false);
  const [pendingPlan, setPendingPlan] = useState<{ content: string; originalMessage: string; mode: GenerationMode } | null>(null);
  const [pendingFix, setPendingFix] = useState<{ data: any; messageId?: number; applied?: boolean } | null>(null);
  const [pendingCommand, setPendingCommand] = useState<{ command: string; gateId: string; messageId: number } | null>(null);
  const [generationMode, setGenerationMode] = useState<GenerationMode>('step');
  const [editingId, setEditingId] = useState<number | null>(null);
  const [tempTitle, setTempTitle] = useState('');
  
  const abortControllerRef = useRef<AbortController | null>(null);

  const fetchConversations = useCallback(async (userId: number) => {
    if (!API) return;
    try {
      const res = await axios.get(`${API}/conversations/${userId}`);
      setConversations(res.data);
    } catch (err) { console.error("Sohbet listesi hatası:", err); }
  }, [API]);

  const fetchMessages = useCallback(async (convId: number) => {
    if (!API) return;
    try {
      const res = await axios.get(`${API}/conversations/${convId}/messages`);
      setMessages(res.data);
      setWisdomSummary(null);
      try {
        const memRes = await axios.get(`${API}/conversations/${convId}/export-memory`, {
          headers: { 'X-Session-Token': user?.sessionToken }
        });
        if (memRes.data.content) {
          const match = memRes.data.content.match(/\[USER_SUMMARY\]\n([\s\S]*?)\n\[TECHNICAL_WISDOM\]/);
          setWisdomSummary(match ? match[1].trim() : memRes.data.content.substring(0, 500) + "...");
        }
      } catch { }
    } catch (err) { console.error("Mesaj hatası:", err); }
  }, [API, user?.sessionToken]);

  const selectConversation = useCallback(async (conv: Conversation) => {
    if (editingId) return;
    setActiveConvId(conv.id);
    setContextUsage({ percent: 0, should_compact: false, message_count: 0 });
    await fetchMessages(conv.id);
  }, [editingId, fetchMessages]);

  const deleteConversation = useCallback(async (e: React.MouseEvent, convId: number) => {
    e.stopPropagation();
    if (!user || !confirm("Bu sohbet silinsin mi?")) return;
    try {
      await axios.delete(`${API}/conversations/${convId}`);
      if (activeConvId === convId) {
        setActiveConvId(null);
        setMessages([]);
      }
      fetchConversations(user.id);
    } catch (err) { console.error("Sohbet silme hatası:", err); }
  }, [API, activeConvId, fetchConversations, user]);

  const saveRename = useCallback(async (convId: number) => {
    if (!tempTitle.trim()) { setEditingId(null); return; }
    try {
      await axios.put(`${API}/conversations/${convId}`, { title: tempTitle });
      setEditingId(null);
      if (user) fetchConversations(user.id);
    } catch (err) { console.error("Yeniden adlandırma hatası:", err); }
  }, [API, fetchConversations, tempTitle, user]);

  const createNewConversation = useCallback(async (title = 'Yeni Sohbet') => {
    if (!user || !API) return null;
    try {
      const res = await axios.post(`${API}/conversations`, { user_id: user.id, title });
      await fetchConversations(user.id);
      setActiveConvId(res.data.id);
      setMessages([]);
      return res.data.id;
    } catch (err) { console.error("Yeni sohbet hatası:", err); return null; }
  }, [API, fetchConversations, user]);

  const sendMessage = useCallback(async (
    messageContent: string, 
    code: string, 
    lang: string, 
    genMode: GenerationMode, 
    thinkingLevel: 'low' | 'medium' | 'high' | 'off',
    setPendingGenFiles: (val: any) => void,
    setPendingDelete: (val: any) => void,
    images?: string[]
  ) => {
    if (loading || !user || !API) return;
    setLoading(true);

    let targetConvId = activeConvId;
    if (!targetConvId) {
      targetConvId = await createNewConversation();
      if (!targetConvId) { setLoading(false); return; }
    }

    const userMsg: Message = { 
      id: Date.now(), 
      role: 'user', 
      content: messageContent, 
      smells: [], 
      timestamp: new Date().toISOString(),
      images: images 
    };
    setMessages(prev => [...prev, userMsg]);
    setChatInput('');

    const aiMsgId = Date.now() + 1;
    let currentAiMsg: Message = { id: aiMsgId, role: 'assistant', content: '', smells: [], timestamp: new Date().toISOString(), thinking: null, tool_calls: [] };
    setMessages(prev => [...prev, currentAiMsg]);

    try {
      abortControllerRef.current = new AbortController();
      const response = await fetch(`${API}/chat-stream`, {
        method: 'POST',
        signal: abortControllerRef.current.signal,
        headers: { 'Content-Type': 'application/json', 'X-Session-Token': user.sessionToken },
        body: JSON.stringify({
          conversation_id: targetConvId, message: messageContent, language: lang, user_id: user.id,
          use_kb: aiConfig.provider_type === 'kb', editor_code: code || '', 
          thinking_level: thinkingLevel,
          generation_mode: genMode, generation_confirmed: false,
          images: images
        }),
      });

      const reader = response.body?.getReader();
      const decoder = new TextDecoder('utf-8');
      if (reader) {
        let buffer = '';
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n\n');
          buffer = lines.pop() || '';
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const data = JSON.parse(line.slice(6));
              setMessages(prev => prev.map(msg => {
                if (msg.id === aiMsgId) {
                  const updated = { ...msg };
                  if (data.type === 'thinking') updated.thinking = (updated.thinking || '') + (data.text || '');
                  else if (data.type === 'text') updated.content += data.content;
                  else if (data.type === 'response') updated.content = data.content || updated.content;
                  else if (data.type === 'tool_call') {
                    const args = typeof data.arguments === 'string' ? JSON.parse(data.arguments) : data.arguments;
                    (updated.tool_calls ||= []).push({ tool: data.tool, args: args });
                    
                  }
                  else if (data.type === 'tool_result' && updated.tool_calls?.length) {
                    const last = updated.tool_calls[updated.tool_calls.length - 1];
                    if (last.tool === data.tool) { last.summary = data.summary; last.success = data.success; }
                  }
                  currentAiMsg = updated;
                  return updated;
                }
                return msg;
              }));
              if (data.type === 'context_usage') setContextUsage({ percent: data.percent, should_compact: data.should_compact, message_count: data.message_count });
              if (data.type === 'command_approval_needed') setPendingCommand({ command: data.command, gateId: data.gate_id, messageId: aiMsgId });
              if (data.type === 'pending_delete' && data.path) setPendingDelete({ path: data.path, messageId: aiMsgId });
              if (data.type === 'refresh_file_tree') refreshFileTree();
              if (data.type === 'done') refreshFileTree();
              if (data.type === 'done' || data.type === 'response') {
                const { parseGeneratedFiles } = await import('../../components/home/export-utils');
                // currentAiMsg o anki en güncel mesaj içeriğini tutmalı
                const parsed = parseGeneratedFiles(currentAiMsg.content);
                if (workspacePath && parsed.length > 0) {
                  const withPaths: PendingFile[] = [];
                  for (const f of parsed) {
                    const suggestedPath = suggestFilePath(f.name);
                    const res = await ipc?.invoke('read-file', suggestedPath, workspacePath);
                    withPaths.push({ 
                      name: f.name, 
                      code: f.code, 
                      suggestedPath, 
                      originalCode: (res && res.content) ? res.content : "" 
                    });
                  }
                  // Message ID'yi state'ten doğrula veya doğrudan kullan
                  setPendingGenFiles({ files: withPaths, messageId: aiMsgId });
                }
              }
            }
          }
        }
      }
      fetchConversations(user.id);
    } catch (err: any) {
      if (err?.name !== 'AbortError') setMessages(prev => [...prev, { id: Date.now() + 2, role: 'assistant', content: '❌ Hata oluştu.', smells: [], timestamp: new Date().toISOString() }]);
    } finally { setLoading(false); }
  }, [API, activeConvId, aiConfig.provider_type, createNewConversation, fetchConversations, loading, suggestFilePath, user, workspacePath]);

  const clearHistory = useCallback(async () => {
    if (!activeConvId) return;
    try {
      await ipc?.invoke('session-clear').catch(() => undefined);
      setMessages([]);
      showToast('Sohbet geçmişi temizlendi', 'info');
    } catch (err) { showToast('Geçmiş temizlenemedi', 'error'); }
  }, [activeConvId, showToast]);

  const confirmPlan = useCallback(async (
    originalMsg: string, 
    mode: GenerationMode, 
    lang: string, 
    code: string, 
    setPendingGenFiles: (val: any) => void,
    setPendingDelete: (val: any) => void
  ) => {
    setPendingPlan(null);
    setLoading(true);
    try {
      const res = await axios.post(`${API}/chat`, {
        conversation_id: activeConvId, message: originalMsg, language: lang, user_id: user?.id,
        use_kb: aiConfig.provider_type === 'kb',
        editor_code: code || '', use_thinking: false, generation_mode: mode, generation_confirmed: true,
      }, { timeout: 900000 });
      
      const aiMsgId = Date.now() + 5;
      const aiMsg: Message = {
        id: aiMsgId, role: 'assistant', content: res.data.content, smells: res.data.static_results?.smells || [],
        timestamp: new Date().toISOString(),
        thinking: res.data.thinking || null, thinking_duration_ms: res.data.thinking_duration_ms || null,
        tool_calls: res.data.tool_calls || []
      };
      setMessages(prev => [...prev, aiMsg]);

      
      if (res.data.content) {
        const { parseGeneratedFiles } = await import('../../components/home/export-utils');
        const genFiles = parseGeneratedFiles(res.data.content);
        if (genFiles.length > 0) {
          const withPaths: PendingFile[] = [];
          for (const f of genFiles) {
            const suggestedPath = suggestFilePath(f.name);
            const exists = await ipc?.invoke('read-file', suggestedPath, workspacePath);
            withPaths.push({ name: f.name, code: f.code, suggestedPath, originalCode: (exists && exists.content) ? exists.content : "" });
          }

          if (mode === 'step') {
            setPendingGenFiles({ files: withPaths, messageId: aiMsgId });
          } else {
            for (const f of withPaths) if (ipc && workspacePath) await ipc.invoke('write-file', f.suggestedPath, f.code, workspacePath);
            refreshFileTree();
          }
        }
      }
    } catch (err) { showToast('Plan başlatılamadı', 'error'); } finally { setLoading(false); }
  }, [API, activeConvId, aiConfig.provider_type, refreshFileTree, suggestFilePath, user?.id, workspacePath, showToast]);

  const analyzeProject = useCallback(async (silent = false) => {
    if (!activeConvId || !user || !API) return;
    setIsAnalyzingProject(true);
    try {
      const res = await axios.post(`${API}/conversations/${activeConvId}/analyze-project`, {}, {
        headers: { 'X-Session-Token': user.sessionToken }, timeout: 120000
      });
      if (res.data.status === 'success') {
        if (!silent) {
          showToast(`🧠 Proje hafızaya alındı! (${res.data.file_count} dosya)`, 'success');
          setMessages(prev => [...prev, { id: Date.now(), role: 'assistant', content: `🧠 **Analiz Raporu**\n\n${res.data.summary}`, timestamp: new Date().toISOString(), smells: [] }]);
        }
        setWisdomSummary(res.data.summary);
      }
    } catch (err: any) { if (!silent) showToast('Analiz hatası.', 'error'); }
    finally { setIsAnalyzingProject(false); }
  }, [API, activeConvId, showToast, user]);

  const exportMemory = useCallback(async () => {
    if (!activeConvId || !user || !API) return;
    try {
      const res = await axios.get(`${API}/conversations/${activeConvId}/export-memory`, { headers: { 'X-Session-Token': user.sessionToken } });
      if (res.data.content) {
        const filePath = await ipc?.invoke('save-file-dialog', { title: 'Hafıza Kaydet', defaultPath: `wisdom_${activeConvId}.md`, filters: [{ name: 'Markdown', extensions: ['md'] }] });
        if (filePath) await ipc?.invoke('write-file', filePath, res.data.content, "");
        showToast('Hafıza kaydedildi.', 'success');
      }
    } catch { showToast('Export hatası.', 'error'); }
  }, [API, activeConvId, showToast, user]);

  const importMemory = useCallback(async () => {
    if (!activeConvId || !user || !API) return;
    try {
      const res = await ipc?.invoke('read-file-dialog', { filters: [{ name: 'Markdown', extensions: ['md'] }] });
      if (res?.content) {
        await axios.post(`${API}/conversations/${activeConvId}/import-memory`, { content: res.content }, { headers: { 'X-Session-Token': user.sessionToken } });
        showToast('Hafıza aktarıldı!', 'success');
        setMessages(prev => [...prev, { id: Date.now(), role: 'assistant', content: `📤 **Hafıza İçe Aktarıldı**`, timestamp: new Date().toISOString(), smells: [] }]);
      }
    } catch { showToast('Import hatası.', 'error'); }
  }, [API, activeConvId, showToast, user]);

  const compactConversation = useCallback(async () => {
    if (!activeConvId || !API) return;
    setIsCompacting(true);
    try {
      const res = await axios.post(`${API}/conversations/${activeConvId}/compact`);
      if (res.data.status === 'success') {
        const msgRes = await axios.get(`${API}/conversations/${activeConvId}/messages`);
        setMessages(msgRes.data);
        setContextUsage({ percent: 5, should_compact: false, message_count: 1 });
        showToast('Sohbet özetlendi!', 'success');
      }
    } catch { showToast('Özetleme hatası.', 'error'); } finally { setIsCompacting(false); }
  }, [API, activeConvId, showToast]);

  return {
    conversations, setConversations,
    activeConvId, setActiveConvId,
    messages, setMessages,
    loading, setLoading,
    chatInput, setChatInput,
    wisdomSummary, setWisdomSummary,
    isWisdomExpanded, setIsWisdomExpanded,
    currentPlan, setCurrentPlan,
    contextUsage, setContextUsage,
    isCompacting, setIsCompacting,
    isAnalyzingProject, setIsAnalyzingProject,
    pendingPlan, setPendingPlan,
    pendingFix, setPendingFix,
    pendingCommand, setPendingCommand,
    generationMode, setGenerationMode,
    editingId, setEditingId,
    tempTitle, setTempTitle,
    fetchConversations, fetchMessages, createNewConversation,
    selectConversation, deleteConversation, saveRename,
    sendMessage, stopMessage: () => {
      abortControllerRef.current?.abort();
      fetch(`${API}/mcp-abort-all`, { method: 'POST' }).catch(() => {});
    },
    clearHistory, confirmPlan, analyzeProject, exportMemory, importMemory, compactConversation,
    approveCommand: async (gateId: string, approved: boolean) => {
      try {
        await fetch(`${API}/command-approval/${gateId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ approved }),
        });
      } catch (err) { console.warn('approveCommand fetch failed', err); }
    },
  };
};
