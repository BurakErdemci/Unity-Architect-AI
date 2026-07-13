import React, { useState, useEffect, useMemo, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  ChevronDown,
  ChevronRight,
  Sparkles,
  Cpu,
  Key,
  Search,
  Check,
  AlertTriangle,
  Loader2
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

interface CliGroupDef {
  key: string;
  label: string;
  brand: string;               // ModelAvatar/ModelLogo marka anahtarı
  availKey: string;            // /cli-availability yanıtındaki anahtar
  cliLabel: string;            // "kurulu değil" uyarısında insan-okur ad
  matches: (id: string) => boolean;
  dynamic?: 'cursor' | 'opencode'; // /cli-models/{cli} ile canlı liste
  accent: string;              // aktif model rengi (tailwind text sınıfı)
  dot: string;                 // aktif nokta rengi (tailwind bg sınıfı)
  badge?: string;              // grup başlığı yanındaki küçük rozet
}

const CLI_GROUPS: CliGroupDef[] = [
  {
    key: 'claude', label: 'Claude Code', brand: 'claude', availKey: 'claude', cliLabel: 'Claude Code',
    matches: id => id.startsWith('claude-'),
    accent: 'text-orange-400', dot: 'bg-orange-400',
  },
  {
    key: 'codex', label: 'Codex', brand: 'openai', availKey: 'codex', cliLabel: 'Codex',
    matches: id => id.startsWith('gpt-'),
    accent: 'text-emerald-400', dot: 'bg-emerald-400',
  },
  {
    key: 'gemini', label: 'Antigravity', brand: 'gemini', availKey: 'agy', cliLabel: 'Antigravity (agy)',
    matches: id => id.startsWith('gemini') || id.startsWith('agy-'),
    accent: 'text-blue-400', dot: 'bg-blue-400',
  },
  {
    key: 'copilot', label: 'GitHub Copilot', brand: 'copilot', availKey: 'copilot', cliLabel: 'GitHub Copilot CLI',
    matches: id => id.startsWith('copilot-'),
    accent: 'text-violet-300', dot: 'bg-violet-300',
  },
  {
    key: 'cursor', label: 'Cursor', brand: 'cursor', availKey: 'cursor', cliLabel: 'Cursor CLI (agent)',
    matches: id => id.startsWith('cursor-'),
    dynamic: 'cursor',
    accent: 'text-slate-100', dot: 'bg-slate-100',
  },
  {
    key: 'opencode', label: 'OpenCode', brand: 'opencode', availKey: 'opencode', cliLabel: 'OpenCode',
    matches: id => id.startsWith('opencode:'),
    dynamic: 'opencode',
    accent: 'text-teal-300', dot: 'bg-teal-300',
    badge: 'ücretsiz',
  },
];

type ModelItem = { id: string; name: string; provider?: string; openrouter_id?: string };

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
  const activeGroupKey = CLI_GROUPS.find(g => g.matches(aiConfig.model_name || ''))?.key ?? null;
  const [expandedGroup, setExpandedGroup] = useState<string | null>(activeGroupKey);
  const [query, setQuery] = useState('');
  const searchRef = useRef<HTMLInputElement>(null);

  // CLI binary'leri gömülü değil — kurulu olmayanları işaretle.
  const [cliAvail, setCliAvail] = useState<Record<string, boolean> | null>(null);
  useEffect(() => {
    if (!isModelDropdownOpen || !API) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await axios.get(`${API}/cli-availability`);
        if (!cancelled) setCliAvail(res.data || {});
      } catch { /* best-effort */ }
    })();
    setQuery('');
    setTimeout(() => searchRef.current?.focus(), 60);
    return () => { cancelled = true; };
  }, [isModelDropdownOpen, API]);

  // Cursor/OpenCode: hesaba/kuruluma göre CANLI model listesi (grup ilk açılınca çekilir).
  const [dynModels, setDynModels] = useState<Record<string, ModelItem[]>>({});
  const [dynLoading, setDynLoading] = useState<Record<string, boolean>>({});
  const fetchDynModels = async (cli: 'cursor' | 'opencode') => {
    if (dynModels[cli] || dynLoading[cli]) return;
    setDynLoading(prev => ({ ...prev, [cli]: true }));
    try {
      const res = await axios.get(`${API}/cli-models/${cli}`);
      setDynModels(prev => ({ ...prev, [cli]: res.data?.models || [] }));
    } catch {
      setDynModels(prev => ({ ...prev, [cli]: [] }));
    } finally {
      setDynLoading(prev => ({ ...prev, [cli]: false }));
    }
  };

  const isGroupInstalled = (g: CliGroupDef): boolean => {
    if (!cliAvail) return true; // henüz yüklenmedi → uyarı gösterme
    return cliAvail[g.availKey] !== false;
  };

  const groupModels = (g: CliGroupDef): ModelItem[] => {
    if (g.dynamic) return dynModels[g.dynamic] || [];
    return (availableModels.subscription || []).filter(m => g.matches(m.id));
  };

  const selectCliModel = async (g: CliGroupDef, m: ModelItem) => {
    const newCfg = { ...aiConfig, provider_type: 'subscription', model_name: m.id, api_key: 'CLI_SESSION' };
    setAiConfig(newCfg);
    setIsModelDropdownOpen(false);
    if (user) await axios.post(`${API}/save-ai-config`, { ...newCfg, user_id: user.id });
    showToast(`${m.name} seçildi.`, 'info');
    if (cliAvail && cliAvail[g.availKey] === false) {
      showToast(`${g.cliLabel} bu bilgisayarda bulunamadı. Bu modeli kullanmak için önce CLI'ı kurman gerekiyor.`, 'warning');
    }
  };

  const selectCloudModel = async (m: ModelItem, orToggle: boolean) => {
    const effectiveModelId = (orToggle && m.openrouter_id) ? m.openrouter_id : m.id;
    const cloudProvider = (orToggle && m.openrouter_id) ? 'openrouter' : (m.provider || '');
    const hasKey = providersWithKeys.includes(cloudProvider);
    // Optimistic: tıklama HER ZAMAN modele geçer; key yoksa Ayarlar açılır.
    const newCfg = { ...aiConfig, provider_type: cloudProvider, model_name: effectiveModelId };
    setAiConfig(newCfg);
    setIsModelDropdownOpen(false);
    if (user) await axios.post(`${API}/save-ai-config`, { ...newCfg, user_id: user.id });
    if (!hasKey) {
      setShowSettings(true);
      showToast(`${orToggle ? 'OpenRouter' : m.provider} API key gerekli — Ayarlar'dan ekle.`, 'warning');
    }
  };

  const selectLocalModel = async (m: ModelItem) => {
    const newCfg = { ...aiConfig, provider_type: 'ollama', model_name: m.id, api_key: '' };
    setAiConfig(newCfg);
    setIsModelDropdownOpen(false);
    if (user) await axios.post(`${API}/save-ai-config`, { ...newCfg, user_id: user.id });
  };

  // ── Arama: tüm kaynaklarda düz filtre ──────────────────────────
  const q = query.trim().toLowerCase();
  const searchResults = useMemo(() => {
    if (!q) return null;
    const hit = (s?: string) => (s || '').toLowerCase().includes(q);
    const cli = CLI_GROUPS.flatMap(g =>
      groupModels(g).filter(m => hit(m.name) || hit(m.id) || hit(g.label))
        .map(m => ({ g, m }))
    );
    const cloud = availableModels.cloud.filter(m => hit(m.name) || hit(m.id) || hit(m.provider));
    const local = availableModels.local.filter(m => hit(m.name) || hit(m.id));
    return { cli, cloud, local };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, availableModels, dynModels]);

  // Arama açıkken dinamik listeleri de getir (sonuç tam olsun)
  useEffect(() => {
    if (q) { fetchDynModels('cursor'); fetchDynModels('opencode'); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  const isActive = (id: string, orToggle?: boolean, m?: ModelItem) => {
    if (orToggle && m?.openrouter_id) return aiConfig.model_name === m.openrouter_id;
    return aiConfig.model_name === id;
  };

  const sectionLabel = (icon: React.ReactNode, text: string) => (
    <div className="px-4 pt-3 pb-1.5 text-[9.5px] font-bold tracking-[0.14em] text-slate-500 uppercase flex items-center gap-1.5 select-none">
      {icon} {text}
    </div>
  );

  const cliModelRow = (g: CliGroupDef, m: ModelItem, indent = true) => {
    const active = isActive(m.id);
    return (
      <button
        key={m.id}
        onClick={() => selectCliModel(g, m)}
        className={`w-full text-left ${indent ? 'pl-[46px]' : 'pl-4'} pr-3 py-[7px] text-[12px] flex items-center justify-between rounded-lg transition-colors hover:bg-white/[0.05] group/row`}
      >
        <span className={`truncate font-medium ${active ? g.accent : 'text-slate-300'}`}>{m.name}</span>
        {active && <Check size={13} className={`${g.accent} shrink-0 ml-2`} />}
      </button>
    );
  };

  const cloudModelRow = (m: ModelItem) => {
    const orToggle = modelOrToggles[m.id] ?? false;
    const effectiveModelId = (orToggle && m.openrouter_id) ? m.openrouter_id : m.id;
    const cloudProvider = (orToggle && m.openrouter_id) ? 'openrouter' : (m.provider || '');
    const hasKey = providersWithKeys.includes(cloudProvider);
    const active = isActive(effectiveModelId);

    return (
      <div key={m.id} className={`flex items-center gap-1 rounded-lg transition-colors hover:bg-white/[0.05] ${active ? 'bg-blue-500/[0.08]' : ''}`}>
        <button
          onClick={() => selectCloudModel(m, orToggle)}
          className={`flex-1 min-w-0 text-left pl-3 pr-1 py-[7px] flex items-center gap-2.5 ${!hasKey ? 'opacity-60' : ''}`}
        >
          <ModelAvatar provider={orToggle ? 'openrouter' : m.provider} size={11} containerSize="h-5 w-5" />
          <span className="flex flex-col min-w-0">
            <span className={`text-[12px] font-medium truncate flex items-center gap-1.5 ${active ? 'text-blue-400' : 'text-slate-300'}`}>
              {m.name}
              {hasKey
                ? <Key size={9} className="text-blue-400/70 shrink-0" />
                : <span className="text-[8px] text-amber-400/90 bg-amber-500/10 border border-amber-500/30 rounded px-1 leading-tight shrink-0">key yok</span>}
            </span>
            <span className="text-[9.5px] text-slate-500 truncate">{orToggle ? 'via OpenRouter' : m.provider}</span>
          </span>
        </button>
        {active && <Check size={13} className="text-blue-400 shrink-0" />}
        {m.openrouter_id && (
          <button
            onClick={e => {
              e.stopPropagation();
              setModelOrToggles({ ...modelOrToggles, [m.id]: !orToggle });
            }}
            title={orToggle && !providersWithKeys.includes('openrouter') ? "OpenRouter key yok — Ayarlar'dan ekle" : 'OpenRouter üzerinden çağır'}
            className={`mr-2 px-1.5 py-0.5 rounded-md text-[8px] font-semibold border transition-colors ${
              orToggle
                ? (providersWithKeys.includes('openrouter') ? 'border-purple-500/70 text-purple-300 bg-purple-500/10' : 'border-amber-500/70 text-amber-300 bg-amber-500/10')
                : 'border-slate-700 text-slate-500 hover:border-slate-500'
            }`}
          >
            OR
          </button>
        )}
      </div>
    );
  };

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
        <ModelAvatar provider={activeGroupKey ? CLI_GROUPS.find(g => g.key === activeGroupKey)!.brand : aiConfig.provider_type} size={14} />
        <div className="flex flex-col min-w-0">
          <span className="text-[12px] font-semibold text-slate-300 leading-tight whitespace-nowrap truncate">
            {displayModelName}
          </span>
          <span className="text-[9px] text-slate-500 leading-tight capitalize whitespace-nowrap truncate">
            {activeGroupKey ? CLI_GROUPS.find(g => g.key === activeGroupKey)!.label : effectiveProvider}
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
              initial={{ opacity: 0, y: -8, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -8, scale: 0.98 }}
              transition={{ duration: 0.16, ease: 'easeOut' }}
              className="absolute top-10 left-0 w-[340px] rounded-2xl z-50 overflow-hidden border border-white/10 bg-[#0B0D12]/95 backdrop-blur-xl shadow-[0_24px_64px_-16px_rgba(0,0,0,0.9)]"
            >
              {/* Arama */}
              <div className="p-2 border-b border-white/[0.06]">
                <div className="flex items-center gap-2 px-2.5 py-[7px] rounded-xl bg-white/[0.05] border border-white/[0.06] focus-within:border-white/20 transition-colors">
                  <Search size={12} className="text-slate-500 shrink-0" />
                  <input
                    ref={searchRef}
                    value={query}
                    onChange={e => setQuery(e.target.value)}
                    placeholder={t('models.search')}
                    className="w-full bg-transparent outline-none text-[12px] text-slate-200 placeholder:text-slate-600"
                  />
                  {query && (
                    <button onClick={() => setQuery('')} className="text-slate-500 hover:text-slate-300 text-[11px] leading-none">✕</button>
                  )}
                </div>
              </div>

              <div className="max-h-[62vh] overflow-y-auto custom-scrollbar pb-1">
                {searchResults ? (
                  /* ── ARAMA SONUÇLARI (düz liste) ── */
                  <div className="p-1">
                    {searchResults.cli.length === 0 && searchResults.cloud.length === 0 && searchResults.local.length === 0 && (
                      <div className="px-4 py-6 text-center text-[11.5px] text-slate-500">{t('models.noResults')}</div>
                    )}
                    {searchResults.cli.map(({ g, m }) => (
                      <div key={m.id} className="flex items-center">
                        <div className="pl-3 shrink-0"><ModelAvatar provider={g.brand} size={11} containerSize="h-5 w-5" /></div>
                        <div className="flex-1 min-w-0">{cliModelRow(g, m, false)}</div>
                      </div>
                    ))}
                    {searchResults.cloud.map(m => cloudModelRow(m))}
                    {searchResults.local.map(m => (
                      <button
                        key={m.id}
                        onClick={() => selectLocalModel(m)}
                        className={`w-full text-left px-4 py-[7px] text-[12px] rounded-lg hover:bg-white/[0.05] ${isActive(m.id) ? 'text-emerald-400' : 'text-slate-300'}`}
                      >
                        {m.name}
                      </button>
                    ))}
                  </div>
                ) : (
                  <>
                    {/* ── CLI ABONELİKLERİ ── */}
                    <div className="p-1">
                      {sectionLabel(<Key size={9} />, t('models.subscription'))}
                      {CLI_GROUPS.map(g => {
                        const models = groupModels(g);
                        const isOpen = expandedGroup === g.key;
                        const installed = isGroupInstalled(g);
                        const isGroupActive = g.key === activeGroupKey;
                        const loading = g.dynamic ? dynLoading[g.dynamic] : false;
                        return (
                          <div key={g.key} className={`rounded-xl transition-colors ${isOpen ? 'bg-white/[0.03]' : ''}`}>
                            <button
                              onClick={() => {
                                const next = isOpen ? null : g.key;
                                setExpandedGroup(next);
                                if (next && g.dynamic) fetchDynModels(g.dynamic);
                              }}
                              className="w-full text-left px-3 py-2 flex items-center gap-2.5 rounded-xl hover:bg-white/[0.04] transition-colors"
                            >
                              <ModelAvatar provider={g.brand} size={12} containerSize="h-6 w-6" />
                              <span className={`flex-1 min-w-0 text-[12.5px] font-semibold truncate ${isGroupActive ? g.accent : 'text-slate-200'}`}>
                                {g.label}
                              </span>
                              {isGroupActive && <span className={`h-1.5 w-1.5 rounded-full ${g.dot} shrink-0`} />}
                              {g.badge && installed && (
                                <span className="text-[8px] font-semibold text-emerald-300 bg-emerald-500/10 border border-emerald-500/30 rounded-md px-1.5 py-0.5 uppercase tracking-wide shrink-0">
                                  {g.badge}
                                </span>
                              )}
                              {!installed && (
                                <span
                                  title={`${g.cliLabel} bu bilgisayarda kurulu değil. Kullanmak için önce kurman gerekiyor.`}
                                  className="flex items-center gap-1 text-amber-300 bg-amber-500/15 border border-amber-500/40 rounded-md px-1.5 py-0.5 text-[8.5px] font-semibold uppercase tracking-wide shrink-0"
                                >
                                  <AlertTriangle size={10} /> {t('models.notInstalled')}
                                </span>
                              )}
                              <ChevronDown size={12} className={`text-slate-500 transition-transform duration-200 shrink-0 ${isOpen ? 'rotate-180' : ''}`} />
                            </button>
                            <AnimatePresence initial={false}>
                              {isOpen && (
                                <motion.div
                                  initial={{ height: 0, opacity: 0 }}
                                  animate={{ height: 'auto', opacity: 1 }}
                                  exit={{ height: 0, opacity: 0 }}
                                  transition={{ duration: 0.15 }}
                                  className="overflow-hidden pb-1"
                                >
                                  {loading && (
                                    <div className="pl-[46px] py-2 flex items-center gap-2 text-[11px] text-slate-500">
                                      <Loader2 size={11} className="animate-spin" /> {t('models.loading')}
                                    </div>
                                  )}
                                  {!loading && models.length === 0 && (
                                    <div className="pl-[46px] pr-3 py-2 text-[10.5px] text-slate-500 leading-snug">
                                      {installed ? t('models.emptyGroup') : `${g.cliLabel} ${t('models.installFirst')}`}
                                    </div>
                                  )}
                                  {!loading && models.map(m => cliModelRow(g, m))}
                                </motion.div>
                              )}
                            </AnimatePresence>
                          </div>
                        );
                      })}
                    </div>

                    {/* ── BULUT API ── */}
                    {availableModels.cloud.length > 0 && (
                      <div className="p-1 border-t border-white/[0.06]">
                        {sectionLabel(<Sparkles size={9} />, t('models.cloud'))}
                        {availableModels.cloud.map(m => cloudModelRow(m))}
                      </div>
                    )}

                    {/* ── YEREL ── */}
                    <div className="p-1 border-t border-white/[0.06]">
                      {sectionLabel(<Cpu size={9} />, t('models.local'))}
                      {availableModels.local.length === 0 && (
                        <div className="px-4 pb-2 text-[10.5px] text-slate-600">{t('models.noLocal')}</div>
                      )}
                      {availableModels.local.map(m => (
                        <button
                          key={m.id}
                          onClick={() => selectLocalModel(m)}
                          className={`w-full text-left px-4 py-[7px] text-[12px] rounded-lg hover:bg-white/[0.05] flex items-center justify-between ${isActive(m.id) ? 'text-emerald-400' : 'text-slate-300'}`}
                        >
                          <span className="truncate">{m.name}</span>
                          {isActive(m.id) && <Check size={13} className="text-emerald-400 shrink-0 ml-2" />}
                        </button>
                      ))}
                    </div>
                  </>
                )}
              </div>

              <button
                onClick={() => { setIsModelDropdownOpen(false); setShowSettings(true); }}
                className="w-full text-left px-4 py-3 text-[11px] text-slate-400 border-t border-white/[0.06] hover:bg-white/[0.04] transition-colors flex items-center justify-between group"
              >
                {t('models.settings')}
                <ChevronRight size={12} className="opacity-0 group-hover:opacity-100 transition-opacity" />
              </button>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
};
