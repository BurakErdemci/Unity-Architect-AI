import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  ChevronDown, 
  HelpCircle, 
  Database, 
  Sparkles, 
  Cpu, 
  ChevronRight,
  Key
} from 'lucide-react';
import { ModelAvatar } from './ModelAvatar';
import { AIConfig, AvailableModels, UserData } from './types';

interface ModelSelectorProps {
  aiConfig: AIConfig;
  setAiConfig: (cfg: AIConfig) => void;
  availableModels: AvailableModels;
  providersWithKeys: string[];
  effectiveProvider: string;
  displayModelName: string;
  isModelDropdownOpen: boolean;
  setIsModelDropdownOpen: (open: boolean) => void;
  showMultiAgentInfo: boolean;
  setShowMultiAgentInfo: (show: boolean) => void;
  modelOrToggles: Record<string, boolean>;
  setModelOrToggles: (toggles: any) => void;
  claudeModelForMA: string;
  maCoderProvider: string | null;
  user: UserData | null;
  fetchAvailableModels: () => void;
  setShowSettings: (show: boolean) => void;
  API: string;
  axios: any;
  showToast: (msg: string, type: 'success' | 'error' | 'warning' | 'info') => void;
}

export const ModelSelector: React.FC<ModelSelectorProps> = ({
  aiConfig,
  setAiConfig,
  availableModels,
  providersWithKeys,
  effectiveProvider,
  displayModelName,
  isModelDropdownOpen,
  setIsModelDropdownOpen,
  showMultiAgentInfo,
  setShowMultiAgentInfo,
  modelOrToggles,
  setModelOrToggles,
  claudeModelForMA,
  maCoderProvider,
  user,
  fetchAvailableModels,
  setShowSettings,
  API,
  axios,
  showToast
}) => {
  return (
    <div className="relative">
      <button
        onClick={() => {
          const opening = !isModelDropdownOpen;
          setIsModelDropdownOpen(opening);
          if (opening) {
            fetchAvailableModels();
            if (aiConfig.provider_type === 'openrouter') {
              setModelOrToggles((prev: any) => ({ ...prev, [aiConfig.model_name]: true }));
            }
          }
        }}
        className="flex items-center gap-1.5 hover:bg-slate-800 px-2 py-1 rounded transition-all text-left"
      >
        <ModelAvatar provider={effectiveProvider} size={14} />
        <div className="flex flex-col">
          <span className="text-[12px] font-semibold text-slate-300 leading-tight">
            {displayModelName}
          </span>
          <span className="text-[9px] text-slate-500 leading-tight capitalize">
            {aiConfig.use_multi_agent ? 'Claude + GPT' : aiConfig.provider_type}
          </span>
        </div>
        <ChevronDown size={14} className="text-slate-500" />
      </button>

      <AnimatePresence>
        {isModelDropdownOpen && (
          <>
            <div
              className="fixed inset-0 z-40"
              onClick={() => setIsModelDropdownOpen(false)}
            />
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="absolute top-10 left-0 w-64 bg-[#000000] border border-slate-700 shadow-2xl rounded-xl z-50"
            >
              {/* TABS: TEK AJAN / MULTI-AGENT */}
              <div className="flex border-b border-slate-800/80">
                <button
                  onClick={async () => {
                    const newCfg = { ...aiConfig, use_multi_agent: false };
                    setAiConfig(newCfg);
                    setShowMultiAgentInfo(false);
                    if (user) await axios.post(`${API}/save-ai-config`, { ...newCfg, user_id: user.id });
                  }}
                  className={`flex-1 py-2 text-[11px] font-semibold transition-colors ${!aiConfig.use_multi_agent ? 'text-blue-400 border-b-2 border-blue-500' : 'text-slate-500 hover:text-slate-300'}`}
                >
                  Tek Ajan
                </button>
                <div className="flex-1 flex items-center justify-center">
                  <button
                    onClick={async () => {
                      const newCfg = { ...aiConfig, use_multi_agent: true, provider_type: 'anthropic' };
                      setAiConfig(newCfg);
                      setShowMultiAgentInfo(false);
                      if (user) await axios.post(`${API}/save-ai-config`, { ...newCfg, user_id: user.id });
                    }}
                    className={`py-2 text-[11px] font-semibold transition-colors ${aiConfig.use_multi_agent ? 'text-blue-400 border-b-2 border-blue-500' : 'text-slate-500 hover:text-slate-300'}`}
                  >
                    Multi-Agent
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); setShowMultiAgentInfo(!showMultiAgentInfo); }}
                    className="ml-1 text-slate-600 hover:text-slate-400 transition-colors"
                  >
                    <HelpCircle size={12} />
                  </button>
                </div>
              </div>

              {showMultiAgentInfo && (
                <div className="mx-2 mt-2 mb-1 bg-[#0a0a0f] border border-blue-900/60 rounded-xl p-3">
                  <p className="text-[11px] font-bold text-blue-400 mb-2">🤖 Multi-Agent Pipeline</p>
                  <div className="mb-2 px-2 py-1.5 rounded-lg bg-slate-900/60 border border-slate-800/60 flex flex-col gap-0.5">
                    <div className="flex items-center justify-between">
                      <span className="text-[9px] text-slate-500">Orkestratör</span>
                      <span className="text-[9px] font-mono text-orange-400">{claudeModelForMA}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-[9px] text-slate-500">Kodlama Ajanı</span>
                      <span className="text-[9px] font-mono text-orange-400">{maCoderProvider || 'Claude'}</span>
                    </div>
                  </div>
                  <p className="text-[10px] text-slate-400 leading-tight">Gelişmiş analiz ve kalite kontrol için birden fazla AI modeli birlikte çalışır.</p>
                </div>
              )}

              {!aiConfig.use_multi_agent && (
                <div className="max-h-[60vh] overflow-y-auto custom-scrollbar">
                  <div className="p-1">
                    <div className="px-2 py-1.5 text-[10px] font-bold text-slate-500 uppercase flex items-center gap-2 mt-1">
                      <Database size={10} /> Yerleşik Sistem
                    </div>
                    <button
                      onClick={async () => {
                        const newCfg = { ...aiConfig, provider_type: 'kb', model_name: 'unity-kb-v1', api_key: '' };
                        setAiConfig(newCfg);
                        setIsModelDropdownOpen(false);
                        if (user) await axios.post(`${API}/save-ai-config`, { ...newCfg, user_id: user.id });
                      }}
                      className={`w-full text-left px-3 py-2 text-[12px] flex flex-col rounded-lg hover:bg-emerald-600/10 ${aiConfig.provider_type === 'kb' ? 'text-emerald-400' : 'text-slate-300'}`}
                    >
                      <span className="font-medium">Unity Bilgi Bankası</span>
                      <span className="text-[10px] text-slate-500">API key gerektirmez</span>
                    </button>
                  </div>

                  {availableModels.cloud.length > 0 && (
                    <div className="p-1">
                      <div className="px-2 py-1.5 text-[10px] font-bold text-slate-500 uppercase flex items-center gap-2 mt-1">
                        <Sparkles size={10} /> Bulut API Modelleri
                      </div>
                      {availableModels.cloud.map(m => {
                        const orToggle = modelOrToggles[m.id] ?? false;
                        const effectiveModelId = (orToggle && m.openrouter_id) ? m.openrouter_id : m.id;
                        const effectiveProvider = (orToggle && m.openrouter_id) ? 'openrouter' : m.provider;
                        const hasKey = providersWithKeys.includes(effectiveProvider);
                        const isActive = aiConfig.model_name === effectiveModelId;

                        return (
                          <div key={m.id} className={`flex items-center gap-1 rounded-lg transition-colors hover:bg-blue-600/10 ${isActive ? 'bg-blue-600/10' : ''}`}>
                            <button
                              onClick={async () => {
                                if (!hasKey) {
                                  setShowSettings(true);
                                  showToast(`${effectiveProvider} key eksik!`, 'warning');
                                  return;
                                }
                                const newCfg = { ...aiConfig, provider_type: effectiveProvider, model_name: effectiveModelId };
                                setAiConfig(newCfg);
                                setIsModelDropdownOpen(false);
                                if (user) await axios.post(`${API}/save-ai-config`, { ...newCfg, user_id: user.id });
                              }}
                              className={`flex-1 text-left px-3 py-2 text-[12px] ${isActive ? 'text-blue-400' : 'text-slate-300'}`}
                            >
                              <div className="flex flex-col">
                                <div className="flex items-center gap-1.5">
                                  <span className="font-medium">{m.name}</span>
                                  {hasKey && <Key size={10} className="text-blue-400 opacity-70" />}
                                </div>
                                <span className="text-[10px] text-slate-500">{orToggle ? 'via OpenRouter' : m.provider}</span>
                              </div>
                            </button>
                            {m.openrouter_id && (
                              <button
                                onClick={e => {
                                  e.stopPropagation();
                                  setModelOrToggles({ ...modelOrToggles, [m.id]: !orToggle });
                                }}
                                className={`mr-2 px-1.5 py-0.5 rounded text-[8px] border ${orToggle ? 'border-purple-500 text-purple-400' : 'border-slate-700 text-slate-500'}`}
                              >
                                OR
                              </button>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}

                  <div className="p-1 border-t border-slate-800/80">
                    <div className="px-2 py-1.5 text-[10px] font-bold text-slate-500 uppercase flex items-center gap-2 mt-1">
                      <Cpu size={10} /> Yerel (Ollama) Modeller
                    </div>
                    {availableModels.local.map(m => (
                      <button
                        key={m.id}
                        onClick={async () => {
                          const newCfg = { ...aiConfig, provider_type: 'ollama', model_name: m.id, api_key: '' };
                          setAiConfig(newCfg);
                          setIsModelDropdownOpen(false);
                          if (user) await axios.post(`${API}/save-ai-config`, { ...newCfg, user_id: user.id });
                        }}
                        className={`w-full text-left px-3 py-2 text-[12px] rounded-lg hover:bg-emerald-600/10 ${aiConfig.model_name === m.id ? 'text-emerald-400' : 'text-slate-300'}`}
                      >
                        {m.name}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {aiConfig.use_multi_agent && (
                <div className="p-3 space-y-2">
                  <div className={`p-2.5 rounded-xl border ${providersWithKeys.includes('anthropic') ? 'border-emerald-800/50 bg-emerald-900/10' : 'border-red-800/50 bg-red-900/10'}`}>
                    <p className="text-[11px] font-semibold text-slate-300">Anthropic (Zorunlu)</p>
                    <p className="text-[9px] text-slate-500 mt-1">Orkestratör ve Game Feel ajanları için gereklidir.</p>
                  </div>
                </div>
              )}

              <button
                onClick={() => { setIsModelDropdownOpen(false); setShowSettings(true); }}
                className="w-full text-left p-3 text-[11px] text-slate-400 bg-[#000000] hover:bg-slate-800 transition-colors flex items-center justify-between group"
              >
                Ayarlar / API Keys
                <ChevronRight size={12} className="opacity-0 group-hover:opacity-100" />
              </button>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
};
