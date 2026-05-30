import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  ChevronDown,
  Sparkles,
  Cpu,
  ChevronRight,
  Key
} from 'lucide-react';
import { ModelAvatar } from './ModelAvatar';
import { AIConfig, AvailableModels, UserData } from './types';
import { useLang } from '../../lib/i18n';

interface ModelSelectorProps {
  aiConfig: AIConfig;
  setAiConfig: (cfg: AIConfig) => void;
  availableModels: AvailableModels;
  providersWithKeys: string[];
  effectiveProvider: string;
  displayModelName: string;
  isModelDropdownOpen: boolean;
  setIsModelDropdownOpen: (open: boolean) => void;
  modelOrToggles: Record<string, boolean>;
  setModelOrToggles: (toggles: any) => void;
  user: UserData | null;
  fetchAvailableModels: () => void;
  setShowSettings: (show: boolean) => void;
  API: string;
  axios: any;
  showToast: (msg: string, type: 'success' | 'error' | 'warning' | 'info') => void;
}

const CLI_GROUPS = [
  {
    key: 'claude',
    label: 'Claude',
    color: 'orange',
    ids: ['claude-opus-4-8', 'claude-sonnet-4-6', 'claude-opus-4-7', 'claude-haiku-4-5'],
  },
  {
    key: 'codex',
    label: 'Codex',
    color: 'green',
    ids: ['gpt-5.5', 'gpt-5.4', 'gpt-5.4-mini'],
  },
  {
    key: 'gemini',
    label: 'Antigravity CLI',
    color: 'blue',
    ids: ['gemini-3.5-flash', 'gemini-3.5-flash-medium', 'gemini-3.1-pro-preview', 'gemini-3.1-pro-low', 'gemini-3-flash-preview', 'gemini-3.1-flash-lite-preview', 'gemini-2.5-pro', 'gemini-2.5-flash', 'agy-claude-sonnet-4-6', 'agy-claude-opus-4-6', 'agy-gpt-oss-120b'],
  },
];

export const ModelSelector: React.FC<ModelSelectorProps> = ({
  aiConfig,
  setAiConfig,
  availableModels,
  providersWithKeys,
  effectiveProvider,
  displayModelName,
  isModelDropdownOpen,
  setIsModelDropdownOpen,
  modelOrToggles,
  setModelOrToggles,
  user,
  fetchAvailableModels,
  setShowSettings,
  API,
  axios,
  showToast
}) => {
  const { t } = useLang();
  const activeGroup = CLI_GROUPS.find(g => g.ids.includes(aiConfig.model_name))?.key ?? null;
  const [expandedCliGroup, setExpandedCliGroup] = useState<string | null>(activeGroup);

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
        className="flex items-center gap-1.5 hover:bg-slate-800 px-2 py-1 rounded transition-all text-left shrink-0 max-w-[160px]"
      >
        <ModelAvatar provider={aiConfig.provider_type} size={14} />
        <div className="flex flex-col min-w-0">
          <span className="text-[12px] font-semibold text-slate-300 leading-tight whitespace-nowrap truncate">
            {displayModelName}
          </span>
          <span className="text-[9px] text-slate-500 leading-tight capitalize whitespace-nowrap truncate">
            {effectiveProvider}
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
              <div className="max-h-[60vh] overflow-y-auto custom-scrollbar">
                {availableModels.cloud.length > 0 && (
                  <div className="p-1">
                    <div className="px-2 py-1.5 text-[10px] font-bold text-slate-500 uppercase flex items-center gap-2 mt-1">
                      <Sparkles size={10} /> {t('models.cloud')}
                    </div>
                    {availableModels.cloud.map(m => {
                      const orToggle = modelOrToggles[m.id] ?? false;
                      const effectiveModelId = (orToggle && m.openrouter_id) ? m.openrouter_id : m.id;
                      const cloudProvider = (orToggle && m.openrouter_id) ? 'openrouter' : m.provider;
                      const hasKey = providersWithKeys.includes(cloudProvider);
                      const isActive = aiConfig.model_name === effectiveModelId;

                      return (
                        <div key={m.id} className={`flex items-center gap-1 rounded-lg transition-colors hover:bg-blue-600/10 ${isActive ? 'bg-blue-600/10' : ''}`}>
                          <button
                            onClick={async () => {
                              if (!hasKey) {
                                setShowSettings(true);
                                showToast(`${cloudProvider} ${t('models.keyMissing')}`, 'warning');
                                return;
                              }
                              const newCfg = { ...aiConfig, provider_type: cloudProvider, model_name: effectiveModelId };
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

                {(availableModels.subscription?.length ?? 0) > 0 && (
                  <div className="p-1 border-t border-slate-800/80">
                    <div className="px-2 py-1.5 text-[10px] font-bold text-slate-500 uppercase flex items-center gap-2 mt-1">
                      <Key size={10} /> {t('models.subscription')}
                    </div>
                    {CLI_GROUPS.map(group => {
                      const groupModels = availableModels.subscription.filter(m => group.ids.includes(m.id));
                      if (groupModels.length === 0) return null;
                      const isOpen = expandedCliGroup === group.key;
                      const isGroupActive = groupModels.some(m => m.id === aiConfig.model_name);
                      return (
                        <div key={group.key}>
                          <button
                            onClick={() => setExpandedCliGroup(isOpen ? null : group.key)}
                            className={`w-full text-left px-3 py-2 text-[12px] flex items-center justify-between rounded-lg hover:bg-slate-800/60 ${isGroupActive ? 'text-purple-400' : 'text-slate-300'}`}
                          >
                            <span className="font-semibold">{group.label}</span>
                            <ChevronDown size={12} className={`text-slate-500 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
                          </button>
                          {isOpen && groupModels.map(m => (
                            <button
                              key={m.id}
                              onClick={async () => {
                                const newCfg = { ...aiConfig, provider_type: 'subscription', model_name: m.id, api_key: 'CLI_SESSION' };
                                setAiConfig(newCfg);
                                setIsModelDropdownOpen(false);
                                if (user) await axios.post(`${API}/save-ai-config`, { ...newCfg, user_id: user.id });
                                showToast(`${m.name} seçildi.`, 'info');
                                // CLI'ler gömülü değil — kullanıcının PC'sinde kurulu olmalı. Kurulu değilse uyar.
                                try {
                                  const cliKey = group.key === 'gemini' ? 'agy' : group.key; // Antigravity CLI grubu agy'yi kullanır
                                  const res = await axios.get(`${API}/cli-availability`);
                                  if (res.data && res.data[cliKey] === false) {
                                    const cliName = cliKey === 'agy' ? 'Antigravity (agy)' : cliKey === 'codex' ? 'Codex' : 'Claude Code';
                                    showToast(`${cliName} CLI bu bilgisayarda bulunamadı. Bu modeli kullanmak için önce CLI'ı kurman gerekiyor.`, 'warning');
                                  }
                                } catch { /* availability kontrolü best-effort, sessizce geç */ }
                              }}
                              className={`w-full text-left pl-6 pr-3 py-1.5 text-[11px] flex flex-col rounded-lg hover:bg-purple-600/10 ${aiConfig.model_name === m.id ? 'text-purple-400' : 'text-slate-400'}`}
                            >
                              <span className="font-medium">{m.name}</span>
                            </button>
                          ))}
                        </div>
                      );
                    })}
                  </div>
                )}

                <div className="p-1 border-t border-slate-800/80">
                  <div className="px-2 py-1.5 text-[10px] font-bold text-slate-500 uppercase flex items-center gap-2 mt-1">
                    <Cpu size={10} /> {t('models.local')}
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


              <button
                onClick={() => { setIsModelDropdownOpen(false); setShowSettings(true); }}
                className="w-full text-left p-3 text-[11px] text-slate-400 bg-[#000000] hover:bg-slate-800 transition-colors flex items-center justify-between group"
              >
                {t('models.settings')}
                <ChevronRight size={12} className="opacity-0 group-hover:opacity-100" />
              </button>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
};
