import { LogOut, Settings, Trash2, X, Gamepad2, Loader2, Globe, Key, Check } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";

import { AIConfig } from "./types";
import { ModelAvatar } from "./ModelAvatar";
import { UnityMCPStatus } from "../../hooks/home/useAIConfig";
import { useLang, type Lang } from "../../lib/i18n";


const DEFAULT_MODELS: Record<string, string> = {
  anthropic: "claude-sonnet-5",
  openai: "gpt-5.6-terra",
  openrouter: "z-ai/glm-5.2",
  google: "gemini-3.6-flash",
  groq: "llama-3.3-70b-versatile",
  deepseek: "deepseek-v4-pro",
  moonshot: "kimi-k3",
  "z-ai": "glm-5.2",
  nvidia: "z-ai/glm-5.2",
  ollama: "qwen2.5-coder:7b",
  kb: "unity-kb-v1",
  subscription: "claude-sonnet-5",
};

// Sağlayıcı seçim ızgarası (marka avatarlı — native <select> yerine).
// brand: ModelAvatar/ModelLogo anahtarı; badge: küçük rozet.
// ⚠️ `label` marka adı (çevrilmez), `labelKey`/`badge` ise SÖZLÜK ANAHTARIDIR.
// Bu liste modül düzeyinde sabit olduğu için `t()` burada çağrılamaz — anahtar
// saklanıp render anında çevriliyor. Eskiden burada düz Türkçe metin duruyordu
// ("ücretsiz", "yerel", "Abonelik (CLI)") ve dil EN yapılsa bile Türkçe kalıyordu.
const PROVIDER_TILES: { value: string; label: string; labelKey?: string; brand: string; badge?: string }[] = [
  { value: "anthropic",    label: "Claude",     brand: "anthropic" },
  { value: "openai",       label: "OpenAI",     brand: "openai" },
  { value: "google",       label: "Gemini",     brand: "google" },
  { value: "deepseek",     label: "DeepSeek",   brand: "deepseek" },
  { value: "moonshot",     label: "Kimi",       brand: "moonshot" },
  { value: "z-ai",         label: "GLM",        brand: "z-ai" },
  { value: "nvidia",       label: "NVIDIA",     brand: "nvidia", badge: "provider.badge.free" },
  { value: "groq",         label: "Groq",       brand: "groq" },
  { value: "openrouter",   label: "OpenRouter", brand: "openrouter" },
  { value: "ollama",       label: "Ollama",     brand: "ollama", badge: "provider.badge.local" },
  { value: "subscription", label: "Subscription (CLI)", labelKey: "provider.subscriptionCli", brand: "subscription" },
];




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
  lang: Lang;
  onLangChange: (l: Lang) => void;
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
  lang,
  onLangChange,
}: SettingsModalProps) => {
  const { t } = useLang();
  const UNITY_STATUS_CONFIG: Record<UnityMCPStatus, { label: string; dot: string; bg: string; border: string }> = {
    off:       { label: t('unity.off'),       dot: "bg-slate-600",                bg: "bg-slate-900/50",   border: "border-slate-700/50" },
    // `blocked` satırının yokluğu ÇALIŞMA ANINDA çökme üretiyordu: aşağıda
    // `UNITY_STATUS_CONFIG[unityMcpStatus].border` okunuyor ve backend bu değeri
    // `b4065f1`'den beri döndürüyor, yani yabancı bir sunucu 8080'i tutarken
    // Ayarlar'ı açmak `undefined.border` demekti.
    blocked:   { label: t('unity.blocked'),   dot: "bg-red-500",                  bg: "bg-red-500/5",      border: "border-red-500/30" },
    starting:  { label: t('unity.starting'),  dot: "bg-yellow-400 animate-pulse", bg: "bg-yellow-500/5",   border: "border-yellow-500/20" },
    running:   { label: t('unity.running'),   dot: "bg-yellow-400 animate-pulse", bg: "bg-yellow-500/5",   border: "border-yellow-500/20" },
    connected: { label: t('unity.connected'), dot: "bg-emerald-400",              bg: "bg-emerald-500/5",  border: "border-emerald-500/20" },
    // Gri ve nabızsız: durum bilinmiyor, "çalışıyor" da denmiyor. Yeşil
    // bırakmak bulgu I-2'nin ta kendisiydi — yoklama başarısızken gösterge
    // süresiz `connected` kalıyordu.
    unknown:   { label: t('unity.unknown'),   dot: "bg-slate-500",                bg: "bg-slate-900/50",   border: "border-slate-700/50" },
  };
  // Anahtarın AÇIK görünmesi için sunucunun BİZİM olması gerekiyor. Eski koşul
  // `!== 'off'` idi ve `blocked`'ı açık sayıyordu — oysa o durumda 8080'de duran
  // sunucu bizim değil, yani kapalıdan daha kötü bir hal. Durumları tek tek
  // saymak bilinçli: yeni bir durum eklendiğinde varsayılan "açık" olmasın.
  const unityMcpAcik =
    unityMcpStatus === 'starting' || unityMcpStatus === 'running' || unityMcpStatus === 'connected';
  const MODEL_HINTS: Record<string, { label: string; value: string }[]> = {
    anthropic: [
      { label: `Sonnet 5 (${t('hint.recommended')})`, value: "claude-sonnet-5" },
      { label: "Fable 5", value: "claude-fable-5" },
      { label: `Opus 5 (${t('hint.strongest')})`, value: "claude-opus-5" },
      { label: "Opus 4.8", value: "claude-opus-4-8" },
      { label: "Sonnet 4.6", value: "claude-sonnet-4-6" },
      { label: "Haiku 4.5", value: "claude-haiku-4-5" },
    ],
    openai: [
      { label: `GPT-5.6 Terra (${t('hint.recommended')})`, value: "gpt-5.6-terra" },
      { label: "GPT-5.6 Sol (Frontier)", value: "gpt-5.6-sol" },
      { label: "GPT-5.6 Luna (Fast)", value: "gpt-5.6-luna" },
      { label: "GPT-5.5 (Frontier)", value: "gpt-5.5" },
      { label: "GPT-5.5 Pro", value: "gpt-5.5-pro" },
      { label: "GPT-5.4", value: "gpt-5.4" },
      { label: "GPT-5.4 Mini", value: "gpt-5.4-mini" },
    ],
    openrouter: [
      { label: `GLM 5.2 (${t('hint.recommended')})`, value: "z-ai/glm-5.2" },
      { label: "GPT-5.6 Sol", value: "openai/gpt-5.6-sol" },
      { label: "GPT-5.6 Terra", value: "openai/gpt-5.6-terra" },
      { label: "GPT-5.6 Luna", value: "openai/gpt-5.6-luna" },
      { label: "Gemini 3.6 Flash", value: "google/gemini-3.6-flash" },
      { label: "Kimi K3", value: "moonshotai/kimi-k3" },
      { label: "Kimi K2.7 Code", value: "moonshotai/kimi-k2.7-code" },
      { label: "DeepSeek V4 Pro", value: "deepseek/deepseek-v4-pro" },
      { label: "DeepSeek V4 Flash", value: "deepseek/deepseek-v4-flash" },
      { label: "GPT-5.5 (Frontier)", value: "openai/gpt-5.5" },
      { label: "GPT-5.5 Pro (Elite)", value: "openai/gpt-5.5-pro" },
      { label: "Claude Sonnet 5", value: "anthropic/claude-sonnet-5" },
      { label: "Claude Opus 4.8", value: "anthropic/claude-opus-4-8" },
      { label: "Gemini 3 Flash", value: "google/gemini-3-flash-preview" },
    ],
    google: [
      { label: `Gemini 3.6 Flash (${t('hint.recommended')})`, value: "gemini-3.6-flash" },
      { label: "Gemini 3.5 Flash", value: "gemini-3.5-flash" },
      { label: `Gemini 3.5 Flash Lite (${t('hint.fast')})`, value: "gemini-3.5-flash-lite" },
      { label: "Gemini 3 Flash", value: "gemini-3-flash-preview" },
      { label: "Gemini 3.1 Pro", value: "gemini-3.1-pro-preview" },
      { label: "Gemini 3.1 Flash Lite", value: "gemini-3.1-flash-lite-preview" },
    ],
    moonshot: [
      { label: `Kimi K3 (${t('hint.newest')})`, value: "kimi-k3" },
      { label: "Kimi K2.7 Code", value: "kimi-k2.7-code" },
      { label: "Kimi K2.6", value: "kimi-k2.6" },
    ],
    "z-ai": [
      { label: `GLM 5.2 (${t('hint.recommended')})`, value: "glm-5.2" },
    ],
    groq: [
      { label: `Llama 3.3 70B (${t('hint.recommended')})`, value: "llama-3.3-70b-versatile" },
      { label: `Llama 3.1 8B (${t('hint.fast')})`, value: "llama-3.1-8b-instant" },
    ],
    deepseek: [
      { label: `DeepSeek V4 Pro (${t('hint.recommended')})`, value: "deepseek-v4-pro" },
      { label: "DeepSeek V4 Flash", value: "deepseek-v4-flash" },
    ],
    nvidia: [
      { label: `GLM 5.2 (${t('hint.recommended')})`, value: "z-ai/glm-5.2" },
      { label: `Nemotron 3 Ultra 550B (${t('hint.strongest')})`, value: "nvidia/nemotron-3-ultra-550b-a55b" },
      { label: "Nemotron 3 Super 120B", value: "nvidia/nemotron-3-super-120b-a12b" },
      { label: "Qwen3 Coder 480B", value: "qwen/qwen3-coder-480b-a35b-instruct" },
      { label: "Qwen 3.5 397B", value: "qwen/qwen3.5-397b-a17b" },
      { label: "Mistral Large 3 675B", value: "mistralai/mistral-large-3-675b-instruct-2512" },
      { label: "MiniMax M3", value: "minimaxai/minimax-m3" },
      { label: "DeepSeek V4 Pro", value: "deepseek-ai/deepseek-v4-pro" },
      { label: "Kimi K2.6", value: "moonshotai/kimi-k2.6" },
    ],
    subscription: [
      { label: "Claude Fable 5", value: "claude-fable-5" },
      { label: `Claude Opus 5 (${t('hint.strongest')})`, value: "claude-opus-5" },
      { label: "Claude Opus 4.8", value: "claude-opus-4-8" },
      { label: `Claude Sonnet 4.6 (${t('hint.recommended')})`, value: "claude-sonnet-4-6" },
      { label: `Claude Haiku 4.5 (${t('hint.fast')})`, value: "claude-haiku-4-5" },
      { label: "Codex GPT-5.6 Terra", value: "gpt-5.6-terra" },
      { label: "Codex GPT-5.6 Sol", value: "gpt-5.6-sol" },
      { label: "Codex GPT-5.6 Luna", value: "gpt-5.6-luna" },
      { label: "Codex GPT-5.5 (Frontier)", value: "gpt-5.5" },
      { label: "Codex GPT-5.4", value: "gpt-5.4" },
      { label: "Codex GPT-5.4 Mini", value: "gpt-5.4-mini" },
      { label: `Gemini 3.6 Flash (${t('hint.recommended')})`, value: "gemini-3.6-flash" },
      { label: "Gemini 3.6 Flash (Medium)", value: "gemini-3.6-flash-medium" },
      { label: "Gemini 3.5 Flash", value: "gemini-3.5-flash" },
      { label: `Gemini 3.1 Pro (${t('hint.smartest')})`, value: "gemini-3.1-pro-preview" },
    ],
  };
  return (
  <AnimatePresence>
    {open && (
      <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-[100]">
        <motion.div
          initial={{ scale: 0.96, opacity: 0, y: 8 }}
          animate={{ scale: 1, opacity: 1, y: 0 }}
          exit={{ scale: 0.96, opacity: 0, y: 8 }}
          transition={{ duration: 0.16, ease: 'easeOut' }}
          className="bg-[#0B0D12]/95 backdrop-blur-xl border border-white/10 rounded-2xl max-w-lg w-full shadow-[0_24px_64px_-16px_rgba(0,0,0,0.9)] flex flex-col max-h-[88vh] overflow-hidden"
        >
          <div className="flex items-center justify-between px-5 pt-5 pb-4 border-b border-white/[0.06] shrink-0">
            <div className="flex items-center gap-2.5">
              <div className="p-1.5 bg-blue-500/10 rounded-lg text-blue-500"><Settings size={18} /></div>
              <h2 className="text-base font-bold text-white">{t('settings.title')}</h2>
            </div>
            <button onClick={onClose} className="p-1.5 hover:bg-white/[0.06] rounded-lg transition-colors text-slate-400">
              <X size={18} />
            </button>
          </div>
          <div className="space-y-4 px-5 py-4 overflow-y-auto custom-scrollbar">
            <div>
              <label className="block text-[9.5px] font-bold text-slate-500 uppercase tracking-[0.14em] mb-2">{t('settings.provider')}</label>
              <div className="grid grid-cols-3 gap-1.5">
                {PROVIDER_TILES.map(tile => {
                  const selected = aiConfig.provider_type === tile.value;
                  const hasKey = providersWithKeys.includes(tile.value);
                  return (
                    <button
                      key={tile.value}
                      type="button"
                      onClick={() => onChange({ ...aiConfig, provider_type: tile.value, api_key: '', model_name: DEFAULT_MODELS[tile.value] || '' })}
                      className={`relative flex items-center gap-2 px-2 py-2 rounded-xl border text-left transition-all ${
                        selected
                          ? 'border-blue-500/60 bg-blue-500/10 shadow-[0_0_0_1px_rgba(59,130,246,0.25)]'
                          : 'border-white/[0.07] bg-white/[0.03] hover:bg-white/[0.06] hover:border-white/15'
                      } ${tile.value === 'subscription' ? 'col-span-2' : ''}`}
                    >
                      <ModelAvatar provider={tile.brand} size={11} containerSize="h-5 w-5" />
                      <span className={`text-[11px] font-semibold truncate ${selected ? 'text-blue-300' : 'text-slate-300'}`}>
                        {tile.labelKey ? t(tile.labelKey as any) : tile.label}
                      </span>
                      {tile.badge && (
                        <span className="absolute -top-1.5 -right-1 text-[7px] font-bold text-emerald-300 bg-emerald-500/15 border border-emerald-500/40 rounded px-1 uppercase tracking-wide">
                          {t(tile.badge as any)}
                        </span>
                      )}
                      {!tile.badge && hasKey && tile.value !== 'subscription' && tile.value !== 'ollama' && (
                        <Key size={8} className="absolute top-1.5 right-1.5 text-blue-400/60" />
                      )}
                      {selected && <Check size={11} className="ml-auto text-blue-400 shrink-0" />}
                    </button>
                  );
                })}
              </div>
            </div>
            {aiConfig.provider_type !== 'ollama' && aiConfig.provider_type !== 'subscription' && (
              <div>
                <label className="block text-[9.5px] font-bold text-slate-500 uppercase tracking-[0.14em] mb-1.5">
                  {t('settings.apiKey')}
                  {providersWithKeys.includes(aiConfig.provider_type) && !aiConfig.api_key && (
                    <span className="ml-2 text-emerald-400 normal-case tracking-normal">{t('settings.savedKey')}</span>
                  )}
                </label>
                <input
                  type="password"
                  value={aiConfig.api_key}
                  onChange={e => onChange({ ...aiConfig, api_key: e.target.value })}
                  className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl p-3 text-white text-sm outline-none focus:border-blue-500/60 focus:bg-white/[0.06] transition-colors placeholder:text-slate-600"
                  placeholder={providersWithKeys.includes(aiConfig.provider_type) ? t('settings.savedKeyPlaceholder') : t('settings.apiKeyPlaceholder')}
                />
                {providersWithKeys.includes(aiConfig.provider_type) && !aiConfig.api_key && (
                  <button
                    onClick={() => onDeleteKey(aiConfig.provider_type)}
                    className="mt-2 flex items-center gap-1.5 text-[11px] text-red-500/70 hover:text-red-400 transition-colors"
                  >
                    <Trash2 size={12} /> {t('settings.deleteKey')}
                  </button>
                )}
              </div>
            )}
            {aiConfig.provider_type === 'subscription' && (
              <div className="p-3 rounded-xl border border-purple-500/30 bg-purple-500/5">
                <p className="text-[10px] text-purple-300 font-medium">{t('settings.subscriptionActive')}</p>
                <p className="text-[9px] text-purple-400/70 mt-0.5">
                  {t('settings.subscriptionDesc')}
                </p>
              </div>
            )}
            <div>
              <label className="block text-[9.5px] font-bold text-slate-500 uppercase tracking-[0.14em] mb-1.5">{t('settings.modelName')}</label>
              <input
                value={aiConfig.model_name}
                onChange={e => onChange({ ...aiConfig, model_name: e.target.value })}
                className="w-full bg-white/[0.04] border border-white/[0.08] rounded-xl p-3 text-white text-sm outline-none focus:border-blue-500/60 focus:bg-white/[0.06] transition-colors placeholder:text-slate-600"
                placeholder={DEFAULT_MODELS[aiConfig.provider_type] || t('settings.modelPlaceholder')}
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
                          : 'bg-white/[0.03] border-white/[0.08] text-slate-500 hover:text-slate-300 hover:border-white/20'
                      }`}
                    >
                      {hint.label}
                    </button>
                  ))}
                </div>
              )}
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
                  unityMcpAcik ? 'bg-purple-600' : 'bg-slate-700'
                }`}
              >
                <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform duration-200 flex items-center justify-center ${
                  unityMcpAcik ? 'translate-x-5' : 'translate-x-0'
                }`}>
                  {unityMcpToggling && <Loader2 size={10} className="text-purple-600 animate-spin" />}
                </span>
              </button>
            </div>

            {/* Language */}
            <div className="flex items-center justify-between p-3 rounded-xl border border-white/[0.07] bg-white/[0.03]">
              <div className="flex items-center gap-2.5">
                <Globe size={15} className="text-slate-400 shrink-0" />
                <p className="text-xs font-semibold text-slate-200">{t('settings.language')}</p>
              </div>
              <div className="flex gap-1">
                {(['tr', 'en'] as Lang[]).map(l => (
                  <button
                    key={l}
                    onClick={() => onLangChange(l)}
                    className={`px-3 py-1 rounded-lg text-[11px] font-bold transition-all border ${
                      lang === l
                        ? 'bg-blue-600/20 border-blue-500/40 text-blue-300'
                        : 'bg-white/[0.04] border-white/[0.08] text-slate-500 hover:text-slate-300 hover:border-white/20'
                    }`}
                  >
                    {l === 'tr' ? '🇹🇷 TR' : '🇬🇧 EN'}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex gap-3 pt-2 mt-2 border-t border-white/[0.06]">
              <button
                onClick={onSave}
                className="flex-1 bg-blue-600 hover:bg-blue-500 text-white p-3 rounded-xl font-bold text-xs tracking-wide transition-all"
              >
                {t('settings.save')}
              </button>
              <button
                onClick={onLogout}
                className="bg-red-500/10 hover:bg-red-500/20 text-red-500 border border-red-500/20 px-4 py-3 rounded-xl font-bold text-xs tracking-wide transition-all flex items-center justify-center gap-2"
              >
                <LogOut size={14} /> {t('settings.logout')}
              </button>
            </div>
          </div>
        </motion.div>
      </div>
    )}
  </AnimatePresence>
  );
};
