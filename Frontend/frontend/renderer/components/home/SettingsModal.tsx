import { LogOut, Settings, Trash2, X, Gamepad2, Loader2 } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";

import { AIConfig } from "./types";
import { UnityMCPStatus } from "../../hooks/home/useAIConfig";


const DEFAULT_MODELS: Record<string, string> = {
  anthropic: "claude-sonnet-4-6",
  openai: "gpt-5.4",
  openrouter: "moonshotai/kimi-k2.6",
  google: "gemini-3-flash-preview",
  groq: "llama-3.3-70b-versatile",
  deepseek: "deepseek-chat",
  moonshot: "kimi-k2.6",
  ollama: "qwen2.5-coder:7b",
  kb: "unity-kb-v1",
  subscription: "claude-sonnet-4-6",
};

const MODEL_HINTS: Record<string, { label: string; value: string }[]> = {
  anthropic: [
    { label: "Sonnet 4.6 (Önerilen)", value: "claude-sonnet-4-6" },
    { label: "Opus 4.7 (En Güçlü)", value: "claude-opus-4-7" },
    { label: "Opus 4.6", value: "claude-opus-4-6" },
    { label: "Haiku 4.5", value: "claude-haiku-4-5" },
  ],
  openai: [
    { label: "GPT-5.5 (Frontier)", value: "gpt-5.5" },
    { label: "GPT-5.5 Pro", value: "gpt-5.5-pro" },
    { label: "GPT-5.4 (Önerilen)", value: "gpt-5.4" },
    { label: "GPT-5.4 Mini", value: "gpt-5.4-mini" },
  ],
  openrouter: [
    { label: "Kimi K2.6 (Önerilen)", value: "moonshotai/kimi-k2.6" },
    { label: "Kimi K2 Thinking", value: "moonshotai/kimi-k2-thinking" },
    { label: "GPT-5.5 (Frontier)", value: "openai/gpt-5.5" },
    { label: "GPT-5.5 Pro (Elite)", value: "openai/gpt-5.5-pro" },
    { label: "Claude Opus 4.7 (Elite)", value: "anthropic/claude-opus-4-7" },
    { label: "Claude Sonnet 4.6", value: "anthropic/claude-sonnet-4-6" },
    { label: "Gemini 3 Flash", value: "google/gemini-3-flash-preview" },
  ],
  google: [
    { label: "Gemini 3 Flash (Önerilen)", value: "gemini-3-flash-preview" },
    { label: "Gemini 3.1 Pro", value: "gemini-3.1-pro-preview" },
    { label: "Gemini 3.1 Flash Lite", value: "gemini-3.1-flash-lite-preview" },
    { label: "Gemini 2.5 Pro", value: "gemini-2.5-pro" },
    { label: "Gemini 2.5 Flash", value: "gemini-2.5-flash" },
  ],
  moonshot: [
    { label: "Kimi K2.6 (En Yeni)", value: "kimi-k2.6" },
    { label: "Kimi K2", value: "kimi-k2" },
  ],
  groq: [
    { label: "Llama 3.3 70B (Önerilen)", value: "llama-3.3-70b-versatile" },
    { label: "Llama 3.1 8B (Hızlı)", value: "llama-3.1-8b-instant" },
  ],
  deepseek: [
    { label: "DeepSeek Chat", value: "deepseek-chat" },
    { label: "DeepSeek R1 (Reasoning)", value: "deepseek-reasoner" },
  ],
  subscription: [
    { label: "Claude Sonnet 4.6 (Önerilen)", value: "claude-sonnet-4-6" },
    { label: "Claude Opus 4.7 (En Güçlü)", value: "claude-opus-4-7" },
    { label: "Claude Haiku 4.5 (Hızlı)", value: "claude-haiku-4-5" },
    { label: "Codex GPT-5.5 (Frontier)", value: "gpt-5.5" },
    { label: "Codex GPT-5.4", value: "gpt-5.4" },
    { label: "Codex GPT-5.4 Mini", value: "gpt-5.4-mini" },
    { label: "Gemini 3.1 Pro (En Zeki)", value: "gemini-3.1-pro-preview" },
    { label: "Gemini 3 Flash (Önerilen)", value: "gemini-3-flash-preview" },
    { label: "Gemini 3.1 Flash Lite (Hızlı)", value: "gemini-3.1-flash-lite-preview" },
    { label: "Gemini 2.5 Pro (Stabil)", value: "gemini-2.5-pro" },
    { label: "Gemini 2.5 Flash (Stabil)", value: "gemini-2.5-flash" },
  ],
};


const UNITY_STATUS_CONFIG: Record<UnityMCPStatus, { label: string; dot: string; bg: string; border: string }> = {
  off:       { label: "Kapalı",                dot: "bg-slate-600",                    bg: "bg-slate-900/50",   border: "border-slate-700/50" },
  starting:  { label: "Başlatılıyor...",       dot: "bg-yellow-400 animate-pulse",     bg: "bg-yellow-500/5",   border: "border-yellow-500/20" },
  running:   { label: "Unity'ye bağlanılıyor", dot: "bg-yellow-400 animate-pulse",     bg: "bg-yellow-500/5",   border: "border-yellow-500/20" },
  connected: { label: "Unity bağlandı ✓",      dot: "bg-emerald-400",                  bg: "bg-emerald-500/5",  border: "border-emerald-500/20" },
};

interface SettingsModalProps {
  open: boolean;
  aiConfig: AIConfig;
  providersWithKeys: string[];
  onChange: (nextConfig: AIConfig) => void;
  onClose: () => void;
  onSave: () => Promise<void>;
  onLogout: () => void;
  onDeleteKey: (provider: string) => Promise<void>;
  unityMcpStatus: UnityMCPStatus;
  unityMcpToggling: boolean;
  onToggleUnityMcp: () => void;
}


export const SettingsModal = ({
  open,
  aiConfig,
  providersWithKeys,
  onChange,
  onClose,
  onSave,
  onLogout,
  onDeleteKey,
  unityMcpStatus,
  unityMcpToggling,
  onToggleUnityMcp,
}: SettingsModalProps) => (
  <AnimatePresence>
    {open && (
      <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-[100]">
        <motion.div
          initial={{ scale: 0.95, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.95, opacity: 0 }}
          className="bg-[#000000] border border-slate-800 rounded-2xl p-6 max-w-md w-full shadow-2xl"
        >
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-2.5">
              <div className="p-1.5 bg-blue-500/10 rounded-lg text-blue-500"><Settings size={18} /></div>
              <h2 className="text-base font-bold text-white">AI Yapılandırması</h2>
            </div>
            <button onClick={onClose} className="p-1.5 hover:bg-slate-800 rounded-lg transition-colors text-slate-400">
              <X size={18} />
            </button>
          </div>
          <div className="space-y-4">
            <div>
              <label className="block text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1.5">Provider</label>
              <select
                style={{ backgroundColor: '#000000', color: 'white' }}
                value={aiConfig.provider_type}
                onChange={e => onChange({ ...aiConfig, provider_type: e.target.value, api_key: '', model_name: DEFAULT_MODELS[e.target.value] || '' })}
                className="w-full bg-[#000000] border border-slate-800 rounded-xl p-3 text-white text-sm outline-none focus:border-blue-500 transition-colors"
              >
                <option value="groq">Groq (Bulut)</option>
                <option value="ollama">Ollama (Yerel)</option>
                <option value="kb">Unity Architect KB (Hızlı & Yerel)</option>
                <option value="anthropic">Anthropic (Claude)</option>
                <option value="google">Google Gemini (Bulut)</option>
                <option value="openai">OpenAI (Bulut)</option>
                <option value="deepseek">DeepSeek (Reasoning)</option>
                <option value="moonshot">Moonshot (Kimi)</option>
                <option value="openrouter">OpenRouter (Çoklu Model)</option>
                <option value="subscription">Abonelik (Claude Code / Codex / Gemini CLI)</option>
              </select>
            </div>
            {aiConfig.provider_type !== 'ollama' && aiConfig.provider_type !== 'kb' && aiConfig.provider_type !== 'subscription' && (
              <div>
                <label className="block text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1.5">
                  API Key
                  {providersWithKeys.includes(aiConfig.provider_type) && !aiConfig.api_key && (
                    <span className="ml-2 text-emerald-400 normal-case tracking-normal">✓ Kayıtlı key mevcut</span>
                  )}
                </label>
                <input
                  style={{ backgroundColor: '#000000', color: 'white' }}
                  type="password"
                  value={aiConfig.api_key}
                  onChange={e => onChange({ ...aiConfig, api_key: e.target.value })}
                  className="w-full bg-[#000000] border border-slate-800 rounded-xl p-3 text-white text-sm outline-none focus:border-blue-500 transition-colors"
                  placeholder={providersWithKeys.includes(aiConfig.provider_type) ? "Kayıtlı key kullanılacak (değiştirmek için yeni key girin)" : "API key girin..."}
                />
                {providersWithKeys.includes(aiConfig.provider_type) && !aiConfig.api_key && (
                  <button
                    onClick={() => onDeleteKey(aiConfig.provider_type)}
                    className="mt-2 flex items-center gap-1.5 text-[11px] text-red-500/70 hover:text-red-400 transition-colors"
                  >
                    <Trash2 size={12} /> API Key Sil
                  </button>
                )}
              </div>
            )}
            {aiConfig.provider_type === 'subscription' && (
              <div className="p-3 rounded-xl border border-purple-500/30 bg-purple-500/5">
                <p className="text-[10px] text-purple-300 font-medium">Abonelik Modu Aktif</p>
                <p className="text-[9px] text-purple-400/70 mt-0.5">
                  Bu modda API key gerekmez; terminalde (claude/codex) açık olan oturumunuz kullanılır.
                </p>
              </div>
            )}
            {aiConfig.provider_type !== 'kb' && (
              <div>
                <label className="block text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1.5">Model İsmi</label>
                <input
                  style={{ backgroundColor: '#000000', color: 'white' }}
                  value={aiConfig.model_name}
                  onChange={e => onChange({ ...aiConfig, model_name: e.target.value })}
                  className="w-full bg-[#000000] border border-slate-800 rounded-xl p-3 text-white text-sm outline-none focus:border-blue-500 transition-colors"
                  placeholder={DEFAULT_MODELS[aiConfig.provider_type] || "model-adı-girin"}
                />
                {MODEL_HINTS[aiConfig.provider_type] && (
                  <div className="flex flex-wrap gap-1.5 mt-2">
                    {MODEL_HINTS[aiConfig.provider_type].map(hint => (
                      <button
                        key={hint.value}
                        type="button"
                        onClick={() => onChange({ ...aiConfig, model_name: hint.value })}
                        className={`px-2 py-0.5 rounded-md text-[10px] transition-colors border ${
                          aiConfig.model_name === hint.value
                            ? 'bg-blue-500/20 border-blue-500/40 text-blue-300'
                            : 'bg-slate-900 border-slate-800 text-slate-500 hover:text-slate-300 hover:border-slate-600'
                        }`}
                      >
                        {hint.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
            <div className="flex items-start gap-3 p-3 rounded-xl border border-blue-500/30 bg-blue-500/5">
              <input
                id="use_multi_agent"
                type="checkbox"
                checked={aiConfig.use_multi_agent}
                onChange={e => onChange({ ...aiConfig, use_multi_agent: e.target.checked })}
                className="mt-0.5 h-4 w-4 rounded border-slate-700 bg-slate-950 text-blue-500 focus:ring-blue-500"
              />
              <div className="min-w-0">
                <label htmlFor="use_multi_agent" className="text-xs font-semibold text-blue-300 cursor-pointer">
                  Gelecekte uzman ajan orkestrasyonunu tercih et
                </label>
                <p className="text-[10px] text-blue-400/70 mt-0.5">
                  Bu seçenek şimdilik yalnızca tercih olarak saklanır. Mevcut chat akışı yine bugünkü agentic runtime ile çalışır.
                </p>
              </div>
            </div>
            {/* Unity MCP Toggle */}
            <div className={`flex items-center justify-between p-3 rounded-xl border ${UNITY_STATUS_CONFIG[unityMcpStatus].border} ${UNITY_STATUS_CONFIG[unityMcpStatus].bg}`}>
              <div className="flex items-center gap-2.5">
                <Gamepad2 size={15} className="text-purple-400 shrink-0" />
                <div>
                  <p className="text-xs font-semibold text-slate-200">Unity MCP</p>
                  <div className="flex items-center gap-1.5 mt-0.5">
                    <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${UNITY_STATUS_CONFIG[unityMcpStatus].dot}`} />
                    <span className="text-[10px] text-slate-400">{UNITY_STATUS_CONFIG[unityMcpStatus].label}</span>
                  </div>
                </div>
              </div>
              <button
                onClick={onToggleUnityMcp}
                disabled={unityMcpToggling || unityMcpStatus === 'starting'}
                className={`relative w-10 h-5 rounded-full transition-colors duration-200 focus:outline-none disabled:opacity-50 ${
                  unityMcpStatus !== 'off' ? 'bg-purple-600' : 'bg-slate-700'
                }`}
              >
                <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform duration-200 flex items-center justify-center ${
                  unityMcpStatus !== 'off' ? 'translate-x-5' : 'translate-x-0'
                }`}>
                  {unityMcpToggling && <Loader2 size={10} className="text-purple-600 animate-spin" />}
                </span>
              </button>
            </div>

            <div className="flex gap-3 pt-2 mt-2 border-t border-slate-800/50">
              <button
                onClick={onSave}
                className="flex-1 bg-blue-600 hover:bg-blue-500 text-white p-3 rounded-xl font-bold text-xs tracking-wide transition-all"
              >
                KAYDET
              </button>
              <button
                onClick={onLogout}
                className="bg-red-500/10 hover:bg-red-500/20 text-red-500 border border-red-500/20 px-4 py-3 rounded-xl font-bold text-xs tracking-wide transition-all flex items-center justify-center gap-2"
                title="Hesaptan çıkış yap"
              >
                <LogOut size={14} /> ÇIKIŞ YAP
              </button>
            </div>
          </div>
        </motion.div>
      </div>
    )}
  </AnimatePresence>
);
