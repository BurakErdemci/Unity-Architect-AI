import { useState, useCallback, useEffect, useRef } from 'react';
import axios from 'axios';
import { Message, Conversation, UserData, AIConfig, GenerationMode, ChatActivity } from '../../components/home/types';
import { PendingFile } from '../../components/home/FileCreationApproval';
import { Task } from '../../components/ui/agent-plan';
import { confirmDialog } from '../../components/ui/ConfirmDialog';
import { deliveryFromFetch, gateFailure } from './gateResponse';
import { cevir } from '../../lib/i18n';

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
  const [pendingCommand, setPendingCommand] = useState<{ command: string; gateId: string; messageId: number; kind?: 'shell' | 'unity' } | null>(null);
  const [pendingQuestion, setPendingQuestion] = useState<{ questions: any[]; gateId: string; messageId: number } | null>(null);
  // Canlı aktivite: Claude'un o an ne yaptığı (düşünüyor/araç/subagent) + token sayacı.
  // Backend status event'lerinden beslenir; done/error/stop'ta temizlenir.
  const [activity, setActivity] = useState<ChatActivity | null>(null);
  // Auto/Adım seçimi uygulama yeniden açılınca kaybolmamalı. SSR ile istemci
  // arasında hydration farkı üretmemek için ilk render Auto, kayıt hydrate edilir.
  const [generationMode, setGenerationModeState] = useState<GenerationMode>('auto');
  const [editingId, setEditingId] = useState<number | null>(null);
  const [tempTitle, setTempTitle] = useState('');

  useEffect(() => {
    const stored = window.localStorage.getItem('unityai-generation-mode');
    if (stored === 'auto' || stored === 'step') {
      setGenerationModeState(stored);
    }
  }, []);

  const setGenerationMode = useCallback((mode: GenerationMode) => {
    setGenerationModeState(mode);
    window.localStorage.setItem('unityai-generation-mode', mode);
  }, []);
  
  const abortControllerRef = useRef<AbortController | null>(null);
  // Paralel araç çağrılarında (ör. Bash + Write, ya da iki Write) birden fazla
  // onay/soru aynı anda gelebilir. Tek state'te tutarsak ikincisi birincisini EZER
  // ve ezilen gate 300sn bekleyip tıkanır ("düşünüyor"da kalır). Bu yüzden bekleyen
  // ek onay/soruları kuyruğa alıp tek tek gösteririz; biri çözülünce sıradaki açılır.
  const pendingCommandQueueRef = useRef<Array<{ command: string; gateId: string; messageId: number; kind?: 'shell' | 'unity' }>>([]);
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
      // Bağlam halkası/compact butonu eski sohbet açılınca da görünsün: backend'in
      // tur sonunda gönderdiği context_usage ile aynı formül (total_chars / 200k).
      const msgs: Message[] = res.data || [];
      const totalChars = msgs.reduce((s, m) => s + (m.content?.length || 0), 0);
      const pct = Math.min(100, Math.round((totalChars / 200000) * 100));
      setContextUsage({ percent: pct, should_compact: pct >= 85, message_count: msgs.length });
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
    if (!(await confirmDialog(cevir('chat.deleteConfirm')))) return;
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

  const createNewConversation = useCallback(async (title?: string) => {
    const baslik = title ?? cevir('sidebar.newChat');
    if (!user || !API) return null;
    try {
      const res = await axios.post(`${API}/conversations`, { user_id: user.id, title: baslik });
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
    thinkingLevel: 'auto' | 'off' | 'none' | 'minimal' | 'low' | 'medium' | 'high' | 'xhigh' | 'max',
    setPendingGenFiles: (val: any) => void,
    setPendingDelete: (val: any) => void,
    images?: string[],
    ultracode: boolean = false,    // Claude-only; mesaja keyword enjekte edilir
    videos?: any[]                 // [{kind:'path',path} | {kind:'url',url}] → backend kareye çevirir
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
          // thinking_level: geriye-uyum alanı (use_thinking türetimi için).
          // off dışındaki her şey (auto dahil) → 'medium' nötr değeri; gerçek
          // seviye effort_level'da gider, backend kayıtçısı (effort_caps) eşler.
          thinking_level: (thinkingLevel === 'off' ? 'off'
            : ['low', 'medium', 'high'].includes(thinkingLevel) ? thinkingLevel : 'medium'),
          generation_mode: genMode, generation_confirmed: false,
          images: images,
          videos: videos,
          // effort_level: birleşik seçicinin TAM değeri (auto/off/minimal/low..max).
          // Backend her provider dalında effort_caps kayıtçısıyla gerçek parametreye çevirir.
          effort_level: thinkingLevel,
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
                  else if (data.type === 'error' && data.message) {
                    // Hata artık chat'te GÖRÜNÜR (eskiden sessizce yutuluyordu → "boş baloncuk")
                    updated.content += (updated.content ? '\n\n' : '') + `❌ ${data.message}`;
                  }
                  else if (data.type === 'turn_usage') {
                    updated.usage = { input_tokens: data.input_tokens, output_tokens: data.output_tokens, cost_usd: data.cost_usd, duration_ms: data.duration_ms };
                  }
                  else if (data.type === 'tool_call') {
                    const args = typeof data.arguments === 'string' ? JSON.parse(data.arguments) : data.arguments;
                    (updated.tool_calls ||= []).push({ tool: data.tool, args: args, summary: data.summary || undefined, id: data.tool_id || undefined });
                  }
                  else if (data.type === 'tool_result') {
                    updated.tool_calls ||= [];
                    // 1) tool_id ile birebir eşle (en güvenilir); 2) sondan geriye ilk
                    // sonuçsuz aynı-isimli chip; 3) hiçbiri yoksa ayrı chip (örn. arka plan görevi).
                    let tc = data.tool_id ? updated.tool_calls.find(t => t.id === data.tool_id) : undefined;
                    if (!tc) {
                      for (let i = updated.tool_calls.length - 1; i >= 0; i--) {
                        const c = updated.tool_calls[i];
                        if (c.tool === data.tool && c.success === undefined) { tc = c; break; }
                      }
                    }
                    if (tc) {
                      tc.summary = data.summary ?? tc.summary;
                      tc.success = data.success;
                      if (data.output) tc.output = data.output;
                    } else {
                      updated.tool_calls.push({ tool: data.tool, summary: data.summary, success: data.success, output: data.output || undefined });
                    }
                  }
                  currentAiMsg = updated;
                  return updated;
                }
                return msg;
              }));
              // Canlı aktivite göstergesi: status event'leri + türev sinyaller.
              if (data.type === 'status') {
                setActivity(prev => ({
                  detail: data.detail || prev?.detail || cevir('activity.working'),
                  tokens: (typeof data.tokens === 'number' && data.tokens > 0) ? data.tokens : prev?.tokens,
                }));
              } else if (data.type === 'thinking') {
                setActivity(prev => ({ detail: cevir('activity.thinking'), tokens: prev?.tokens }));
              } else if (data.type === 'text') {
                setActivity(prev => ({ detail: cevir('activity.writing'), tokens: prev?.tokens }));
              } else if (data.type === 'tool_call' && data.tool !== 'TodoWrite') {
                const s = data.summary ? ` — ${String(data.summary).slice(0, 60)}` : '';
                setActivity(prev => ({ detail: `🔧 ${data.tool}${s}`, tokens: prev?.tokens }));
              } else if (data.type === 'done' || data.type === 'error' || data.type === 'response') {
                setActivity(null);
              }
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
      if (err?.name !== 'AbortError') setMessages(prev => [...prev, { id: Date.now() + 2, role: 'assistant', content: cevir('chat.errorOccurred'), smells: [], timestamp: new Date().toISOString() }]);
    } finally { setLoading(false); setActivity(null); }
  }, [API, activeConvId, aiConfig.provider_type, createNewConversation, fetchConversations, loading, suggestFilePath, user, workspacePath]);

  const clearHistory = useCallback(async () => {
    if (!activeConvId) return;
    try {
      // session-clear IPC channel removed; session management now handled by auth layer
      setMessages([]);
      showToast(cevir('chat.historyCleared'), 'info');
    } catch (err) { showToast(cevir('chat.historyClearFailed'), 'error'); }
  }, [activeConvId, showToast]);

  const analyzeProject = useCallback(async (silent = false) => {
    if (!user || !API) return;

    // Aktif sohbet yoksa Projeyi Öğren tek tıkla çalışsın diye yenisini açıyoruz.
    let targetConvId = activeConvId;
    if (!targetConvId) {
      targetConvId = await createNewConversation(cevir('chat.projectAnalysisTitle'));
      if (!targetConvId) return;
    }

    setIsAnalyzingProject(true);
    try {
      const res = await axios.post(`${API}/conversations/${targetConvId}/analyze-project`, {}, {
        headers: { 'X-Session-Token': user.sessionToken }, timeout: 120000
      });
      if (res.data.status === 'success') {
        if (!silent) {
          showToast(cevir('memory.learned', { sayi: res.data.file_count }), 'success');
          setMessages(prev => [...prev, { id: Date.now(), role: 'assistant', content: `${cevir('memory.analysisReport')}\n\n${res.data.summary}`, timestamp: new Date().toISOString(), smells: [] }]);
        }
      }
    } catch (err: any) { if (!silent) showToast(cevir('memory.analysisError'), 'error'); }
    finally { setIsAnalyzingProject(false); }
  }, [API, activeConvId, createNewConversation, showToast, user]);

  const exportMemory = useCallback(async () => {
    if (!activeConvId || !user || !API) return;
    try {
      const res = await axios.get(`${API}/conversations/${activeConvId}/export-memory`, { headers: { 'X-Session-Token': user.sessionToken } });
      if (!res.data.content) { showToast(cevir('memory.none'), 'error'); return; }
      const out = await ipc?.invoke('export-text-file', `wisdom_${activeConvId}.md`, res.data.content);
      if (out?.canceled) return;
      if (out?.success) showToast(cevir('memory.saved'), 'success');
      else showToast(cevir('memory.saveFailed', { hata: out?.error || cevir('common.unknownError') }), 'error');
    } catch { showToast(cevir('memory.exportError'), 'error'); }
  }, [API, activeConvId, showToast, user]);

  const importMemory = useCallback(async () => {
    if (!activeConvId || !user || !API) return;
    try {
      const res = await ipc?.invoke('import-text-file', { filters: [{ name: 'Markdown', extensions: ['md'] }] });
      if (res?.canceled) return;
      if (res?.content) {
        await axios.post(`${API}/conversations/${activeConvId}/import-memory`, { content: res.content }, { headers: { 'X-Session-Token': user.sessionToken } });
        showToast(cevir('memory.imported'), 'success');
        setMessages(prev => [...prev, { id: Date.now(), role: 'assistant', content: cevir('memory.importedHeading'), timestamp: new Date().toISOString(), smells: [] }]);
      }
    } catch { showToast(cevir('memory.importError'), 'error'); }
  }, [API, activeConvId, showToast, user]);

  const compactConversation = useCallback(async () => {
    if (!activeConvId || !API || !user) return;
    setIsCompacting(true);
    showToast(cevir('compact.running'), 'info');
    try {
      // Timeout ŞART: backend'de AI özetleme takılırsa buton sonsuza dek kilitli
      // kalıyordu ("basınca bir şey olmuyor" bug'ı). Backend 120s'de fallback'e düşer.
      const res = await axios.post(`${API}/conversations/${activeConvId}/compact`, {}, {
        headers: { 'X-Session-Token': user.sessionToken }, timeout: 150000,
      });
      if (res.data.status === 'success') {
        if (res.data.summary) {
          const msgRes = await axios.get(`${API}/conversations/${activeConvId}/messages`);
          setMessages(msgRes.data);
          setContextUsage({ percent: 5, should_compact: false, message_count: 1 });
          showToast(cevir('compact.done'), 'success');
        } else {
          // Backend'in `message`'ı sabit TÜRKÇE — İngilizce arayüzde Türkçe toast
          // çıkıyordu. Metin sözlükten geliyor; backend yalnız hangi dal olduğunu söylüyor.
          showToast(cevir('compact.tooShort'), 'info');
        }
      }
    } catch { showToast(cevir('compact.error'), 'error'); } finally { setIsCompacting(false); }
  }, [API, activeConvId, showToast, user]);

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
    activity,
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
      setActivity(null);
      setLoading(false);
    },
    clearHistory, analyzeProject, exportMemory, importMemory, compactConversation,
    // Kararı backend'e iletir ve İLETİLDİĞİNİ DOĞRULAR. Yanıt gövdesi eskiden
    // hiç okunmuyordu: gate düşmüşse backend {"status":"gate_not_found"} dönüyor,
    // kart yine de kapanıyor ve kullanıcı onayladığını sanıyordu (sessiz veri
    // kaybı, ölçüldü 2026-07-28). Kart yine kapanır — asılı kalması daha kötü —
    // ama kullanıcı ne olduğunu görür.
    approveCommand: async (gateId: string, approved: boolean) => {
      let failure = null as ReturnType<typeof gateFailure>;
      try {
        const res = await fetch(`${API}/command-approval/${gateId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-Session-Token': user?.sessionToken ?? '' },
          body: JSON.stringify({ approved }),
        });
        failure = gateFailure('command', await deliveryFromFetch(res));
      } catch (err) {
        console.warn('approveCommand fetch failed', err);
        failure = gateFailure('command', { httpOk: false, error: err });
      }
      if (failure) showToast(failure.message, failure.type);
      // Çözüldü → kuyrukta sıradaki onayı göster (yoksa kapat)
      setPendingCommand(pendingCommandQueueRef.current.shift() || null);
      // Sonucu ÇAĞIRANA da ver: kart, "Komut onaylandı — çalışıyor..." yeşil
      // toast'ını koşulsuz basıyordu; kullanıcı sarı "iletilemedi" ile yeşili
      // aynı anda görüyordu (Toast.tsx:32 toast'ları diziye ekliyor).
      // Mesajı burada basmaya devam ediyoruz — bu fonksiyonun kart olmadan da
      // (kuyruk yolu) çağrıldığı yerler var.
      return failure;
    },
    // AskUserQuestion (A/B/C) cevabı: { "<soru metni>": "<seçilen label>" }
    answerQuestion: async (gateId: string, answers: Record<string, string>) => {
      let failure = null as ReturnType<typeof gateFailure>;
      try {
        const res = await fetch(`${API}/question-answer/${gateId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-Session-Token': user?.sessionToken ?? '' },
          body: JSON.stringify({ answers }),
        });
        failure = gateFailure('question', await deliveryFromFetch(res));
      } catch (err) {
        console.warn('answerQuestion fetch failed', err);
        failure = gateFailure('question', { httpOk: false, error: err });
      }
      if (failure) showToast(failure.message, failure.type);
      // Çözüldü → kuyrukta sıradaki soruyu göster (yoksa kapat)
      setPendingQuestion(pendingQuestionQueueRef.current.shift() || null);
    },
  };
};
