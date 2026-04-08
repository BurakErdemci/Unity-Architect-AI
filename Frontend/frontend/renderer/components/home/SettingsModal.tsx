import { LogOut, Settings, X } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";

import { AIConfig } from "./types";


const DEFAULT_MODELS: Record<string, string> = {
  anthropic: "claude-sonnet-4-6",
  openai: "gpt-5.4",
  openrouter: "openai/gpt-5.4",
  google: "gemini-2.5-flash",
  groq: "llama-3.3-70b-versatile",
  deepseek: "deepseek-chat",
  ollama: "qwen2.5-coder:7b",
  kb: "unity-kb-v1",
};


interface SettingsModalProps {
  open: boolean;
  aiConfig: AIConfig;
  providersWithKeys: string[];
  onChange: (nextConfig: AIConfig) => void;
  onClose: () => void;
  onSave: () => Promise<void>;
  onLogout: () => void;
}


export const SettingsModal = ({
  open,
  aiConfig,
  providersWithKeys,
  onChange,
  onClose,
  onSave,
  onLogout,
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
                <option value="openrouter">OpenRouter (Kimi, vb.)</option>
              </select>
            </div>
            {aiConfig.provider_type !== 'ollama' && aiConfig.provider_type !== 'kb' && (
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
              </div>
            )}
            <div className="flex items-center justify-between p-3 rounded-xl border border-slate-800/80 bg-slate-900/30">
              <div>
                <p className="text-xs font-semibold text-slate-300">Multi-Agent Sistemi</p>
                <p className="text-[10px] text-slate-500 mt-0.5">Model seçiciden de açılabilir • Anthropic key zorunlu</p>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  className="sr-only peer"
                  checked={aiConfig.use_multi_agent}
                  onChange={(e) => onChange({
                    ...aiConfig,
                    use_multi_agent: e.target.checked,
                    ...(e.target.checked ? { provider_type: 'anthropic' } : {})
                  })}
                />
                <div className="w-9 h-5 bg-slate-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-blue-600"></div>
              </label>
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
