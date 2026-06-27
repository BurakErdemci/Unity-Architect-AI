import { useState, useCallback, useRef } from 'react';
import axios from 'axios';
import { Message, Conversation, UserData, AIConfig, GenerationMode } from '../../components/home/types';
import { PendingFile } from '../../components/home/FileCreationApproval';
import { Task } from '../../components/ui/agent-plan';
import { confirmDialog } from '../../components/ui/ConfirmDialog';

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
  const [currentPlan, setCurrentPlan] = useState<Task[]>([]);
  const [contextUsage, setContextUsage] = useState({ percent: 0, should_compact: false, message_count: 0 });
  const [isCompacting, setIsCompacting] = useState(false);
  const [isAnalyzingProject, setIsAnalyzingProject] = useState(false);
  const [pendingFix, setPendingFix] = useState<{ data: any; messageId?: number; applied?: boolean } | null>(null);
  const [pendingCommand, setPendingCommand] = useState<{ command: string; gateId: string; messageId: number } | null>(null);
  const [pendingQuestion, setPendingQuestion] = useState<{ questions: any[]; gateId: string; messageId: number } | null>(null);
  const [generationMode, setGenerationMode] = useState<GenerationMode>('step');
  const [editingId, setEditingId] = useState<number | null>(null);
  const [tempTitle, setTempTitle] = useState('');
  
  const abortControllerRef = useRef<AbortController | null>(null);
  // Paralel araç çağrılarında (ör. Bash + Write, ya da iki Write) birden fazla
  // onay/soru aynı anda gelebilir. Tek state'te tutarsak ikincisi birincisini EZER
  // ve ezilen gate 300sn bekleyip tıkanır ("düşünüyor"da kalır). Bu yüzden bekleyen
  // ek onay/soruları kuyruğa alıp tek tek gösteririz; biri çözülünce sıradaki açılır.
  const pendingCommandQueueRef = useRef<Array<{ command: string; gateId: string; messageId: number }>>([]);
  const pendingQuestionQueueRef = useRef<Array<{ questions: any[]; gateId: string; messageId: number }>>([]);

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
    } catch (err) { console.error("Mesaj hatası:", err); }
  }, [API]);

  const selectConversation = useCallback(async (conv: Conversation) => {
    if (editingId) return;
    setActiveConvId(conv.id);
    setContextUsage({ percent: 0, should_compact: false, message_count: 0 });
    await fetchMessages(conv.id);
  }, [editingId, fetchMessages]);

  const deleteConversation = useCallback(async (e: React.MouseEvent, convId: number) => {
    e.stopPropagation();
    if (!user) return;
    if (!(await confirmDialog("Bu sohbet silinsin mi?"))) return;
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
    images?: string[],
    effortMax: boolean = false,   // Claude-only; "max" effort
    ultracode: boolean = false    // Claude-only; mesaja keyword enjekte edilir
  ) => {
    if (loading || !user || !API) return;
    setLoading(true);
    // Yeni tur: önceki turdan kalmış olabilecek bekleyen onay/soru ve kuyrukları temizle
    pendingCommandQueueRef.current = [];
    pendingQuestionQueueRef.current = [];
    setPendingCommand(null);
    setPendingQuestion(null);

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

    // Özel kart render edilen slash komutları → asistan mesajını etiketle.
    //   /usage   → Claude (Claude Code) + Codex (app-server rateLimits kartı)
    //   /context → yalnızca Claude (Codex/agy'de yok)
    // NOT: /cost bu Claude Code sürümünde YOK (abonelikte session cost /usage'a dahil).
    const _trimmed = messageContent.trim().toLowerCase();
    const _m = (aiConfig?.model_name || '').toLowerCase();
    const _isSub = aiConfig?.provider_type === 'subscription';
    const _isCodex = _isSub && _m.startsWith('gpt-');
    const _isClaude = _isSub && !_m.startsWith('gpt-') && !(_m.startsWith('gemini') || _m.startsWith('agy-'));
    let slashCard: string | undefined;
    if (_trimmed === '/usage' && (_isClaude || _isCodex)) slashCard = 'usage';
    else if (_trimmed === '/context' && _isClaude) slashCard = 'context';

    const aiMsgId = Date.now() + 1;
    let currentAiMsg: Message = { id: aiMsgId, role: 'assistant', content: '', smells: [], timestamp: new Date().toISOString(), thinking: null, tool_calls: [], slashCommand: slashCard };
    setMessages(prev => [...prev, currentAiMsg]);

    try {
      abortControllerRef.current = new AbortController();
      const response = await fetch(`${API}/chat-stream`, {
        method: 'POST',
        signal: abortControllerRef.current.signal,
        headers: { 'Content-Type': 'application/json', 'X-Session-Token': user.sessionToken },
        body: JSON.stringify({
          conversation_id: targetConvId, message: messageContent, language: lang, user_id: user.id,
          editor_code: code || '',
          thinking_level: thinkingLevel,
          generation_mode: genMode, generation_confirmed: false,
          images: images,
          // Claude-only: backend yalnızca claude-subscription yolunda dikkate alır
          effort_level: effortMax ? 'max' : 'medium',
          ultracode: !!ultracode,
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
              if (data.type === 'command_approval_needed') {
                const item = { command: data.command, gateId: data.gate_id, messageId: aiMsgId };
                // Zaten gösterilen bir onay varsa sıraya al (paralel araçlarda ezilmesin)
                setPendingCommand(prev => { if (prev) { pendingCommandQueueRef.current.push(item); return prev; } return item; });
              }
              if (data.type === 'question_needed') {
                const item = { questions: data.questions || [], gateId: data.gate_id, messageId: aiMsgId };
                setPendingQuestion(prev => { if (prev) { pendingQuestionQueueRef.current.push(item); return prev; } return item; });
              }
              if (data.type === 'pending_delete' && data.path) setPendingDelete({ path: data.path, messageId: aiMsgId });
              if (data.type === 'refresh_file_tree') refreshFileTree();
              if (data.type === 'done') refreshFileTree();
              // Subscription (claude/codex/agy) provider'larda dosya yazımı MCP/CLI
              // gate'iyle yapılır (useMCPApproval). Bu provider'lar açıklama metninde
              // kod bloğunu da yazdığı için parseGeneratedFiles burada FAZLADAN diff
              // kartı üretir (agy kodu iki kez yazınca iki kart). O yüzden sadece
              // tool kullanmayan provider'larda (Gemini/OpenAI/Ollama API) metni ayrıştır.
              if ((data.type === 'done' || data.type === 'response') && aiConfig.provider_type !== 'subscription') {
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
      // session-clear IPC channel removed; session management now handled by auth layer
      setMessages([]);
      showToast('Sohbet geçmişi temizlendi', 'info');
    } catch (err) { showToast('Geçmiş temizlenemedi', 'error'); }
  }, [activeConvId, showToast]);

  const analyzeProject = useCallback(async (silent = false) => {
    if (!user || !API) return;

    // Aktif sohbet yoksa Projeyi Öğren tek tıkla çalışsın diye yenisini açıyoruz.
    let targetConvId = activeConvId;
    if (!targetConvId) {
      targetConvId = await createNewConversation('Proje Analizi');
      if (!targetConvId) return;
    }

    setIsAnalyzingProject(true);
    try {
      const res = await axios.post(`${API}/conversations/${targetConvId}/analyze-project`, {}, {
        headers: { 'X-Session-Token': user.sessionToken }, timeout: 120000
      });
      if (res.data.status === 'success') {
        if (!silent) {
          showToast(`🧠 Proje hafızaya alındı! (${res.data.file_count} dosya)`, 'success');
          setMessages(prev => [...prev, { id: Date.now(), role: 'assistant', content: `🧠 **Analiz Raporu**\n\n${res.data.summary}`, timestamp: new Date().toISOString(), smells: [] }]);
        }
      }
    } catch (err: any) { if (!silent) showToast('Analiz hatası.', 'error'); }
    finally { setIsAnalyzingProject(false); }
  }, [API, activeConvId, createNewConversation, showToast, user]);

  const exportMemory = useCallback(async () => {
    if (!activeConvId || !user || !API) return;
    try {
      const res = await axios.get(`${API}/conversations/${activeConvId}/export-memory`, { headers: { 'X-Session-Token': user.sessionToken } });
      if (!res.data.content) { showToast('Henüz hafıza yok.', 'error'); return; }
      const out = await ipc?.invoke('export-text-file', `wisdom_${activeConvId}.md`, res.data.content);
      if (out?.canceled) return;
      if (out?.success) showToast('Hafıza kaydedildi.', 'success');
      else showToast(`Kaydedilemedi: ${out?.error || 'bilinmeyen hata'}`, 'error');
    } catch { showToast('Export hatası.', 'error'); }
  }, [API, activeConvId, showToast, user]);

  const importMemory = useCallback(async () => {
    if (!activeConvId || !user || !API) return;
    try {
      const res = await ipc?.invoke('import-text-file', { filters: [{ name: 'Markdown', extensions: ['md'] }] });
      if (res?.canceled) return;
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
    currentPlan, setCurrentPlan,
    contextUsage, setContextUsage,
    isCompacting, setIsCompacting,
    isAnalyzingProject, setIsAnalyzingProject,
    pendingFix, setPendingFix,
    pendingCommand, setPendingCommand,
    pendingQuestion, setPendingQuestion,
    generationMode, setGenerationMode,
    editingId, setEditingId,
    tempTitle, setTempTitle,
    fetchConversations, fetchMessages, createNewConversation,
    selectConversation, deleteConversation, saveRename,
    sendMessage, stopMessage: () => {
      abortControllerRef.current?.abort();
      // Claude SDK turunu gerçekten iptal et (bekleyen onay/soru gate'lerini çöz + interrupt)
      if (activeConvId && user) {
        fetch(`${API}/chat-stop/${activeConvId}`, {
          method: 'POST',
          headers: { 'X-Session-Token': user.sessionToken },
        }).catch(() => {});
      }
      // Bekleyen onay/soru kartlarını ve kuyrukları temizle (backend gate'leri reddetti)
      pendingCommandQueueRef.current = [];
      pendingQuestionQueueRef.current = [];
      setPendingCommand(null);
      setPendingQuestion(null);
      setLoading(false);
    },
    clearHistory, analyzeProject, exportMemory, importMemory, compactConversation,
    approveCommand: async (gateId: string, approved: boolean) => {
      try {
        await fetch(`${API}/command-approval/${gateId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-Session-Token': user?.sessionToken ?? '' },
          body: JSON.stringify({ approved }),
        });
      } catch (err) { console.warn('approveCommand fetch failed', err); }
      // Çözüldü → kuyrukta sıradaki onayı göster (yoksa kapat)
      setPendingCommand(pendingCommandQueueRef.current.shift() || null);
    },
    // AskUserQuestion (A/B/C) cevabı: { "<soru metni>": "<seçilen label>" }
    answerQuestion: async (gateId: string, answers: Record<string, string>) => {
      try {
        await fetch(`${API}/question-answer/${gateId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-Session-Token': user?.sessionToken ?? '' },
          body: JSON.stringify({ answers }),
        });
      } catch (err) { console.warn('answerQuestion fetch failed', err); }
      // Çözüldü → kuyrukta sıradaki soruyu göster (yoksa kapat)
      setPendingQuestion(pendingQuestionQueueRef.current.shift() || null);
    },
  };
};
