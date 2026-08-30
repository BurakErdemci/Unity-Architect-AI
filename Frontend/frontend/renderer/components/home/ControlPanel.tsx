import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useLang } from '../../lib/i18n';
import {
  Brain,
  Sparkles,
  ChevronDown,
  Download,
  Upload,
  Gauge,
  Rocket
} from 'lucide-react';
import { ContextUsage, SessionUsage } from './types';

/** 41200 → "41,2k". Uzun sayı barı taşırıyor, tam değer başlıkta duruyor. */
const kisaSayi = (n: number): string => {
  if (n < 1000) return String(n);
  const bin = n / 1000;
  return (bin < 100 ? bin.toFixed(1).replace('.', ',') : String(Math.round(bin))) + 'k';
};
import { GenerationModeSelector, GenerationMode } from './GenerationModeSelector';

// Kanonik effort skalası — hangi seviyelerin GÖSTERİLECEĞİ backend kayıtçısından
// (/effort-capabilities) gelir; provider+model gerçekte neyi destekliyorsa o.
export type ThinkingLevel =
  'auto' | 'off' | 'none' | 'minimal' | 'low' | 'medium' | 'high' | 'xhigh' | 'max';

export interface EffortCaps {
  levels: string[];
  default?: string;
  note?: string;
}

interface ControlPanelProps {
  thinkingLevel: ThinkingLevel;
  setThinkingLevel: (val: ThinkingLevel) => void;
  // Backend kayıtçısından aktif provider+model'in gerçek seviye listesi.
  effortCaps?: EffortCaps | null;
  generationMode: GenerationMode;
  setGenerationMode: (mode: GenerationMode) => void;
  isAnalyzingProject: boolean;
  activeConvId: number | null;
  analyzeProject: (silent?: boolean) => Promise<void>;
  exportMemory: () => Promise<void>;
  importMemory: () => Promise<void>;
  compactConversation: () => Promise<void>;
  isCompacting: boolean;
  contextUsage?: ContextUsage;
  sessionUsage?: SessionUsage;
  // Claude-only (subscription + claude-* model). Diğer sağlayıcılarda gizlenir.
  isClaudeSubscription?: boolean;
  ultracode?: boolean;
  setUltracode?: (v: boolean) => void;
}

export const ControlPanel: React.FC<ControlPanelProps> = ({
  thinkingLevel,
  setThinkingLevel,
  effortCaps,
  generationMode,
  setGenerationMode,
  isAnalyzingProject,
  activeConvId,
  analyzeProject,
  exportMemory,
  importMemory,
  compactConversation,
  isCompacting,
  contextUsage,
  sessionUsage,
  isClaudeSubscription = false,
  ultracode = false,
  setUltracode
}) => {
  const { t } = useLang();
  const [showMemoryMenu, setShowMemoryMenu] = useState(false);
  const [showThinkingMenu, setShowThinkingMenu] = useState(false);

  const yuzde = contextUsage?.percent ?? 0;
  // `turns > 0` şart: sayaç sıfırdayken "0 tok" ile "bu model bildirmiyor"
  // ekranda aynı görünür, oysa biri ölçüm diğeri bilgi yokluğu.
  const tokenVar = !!sessionUsage && sessionUsage.turns > 0;

  // Seviye görselleri — hangi seviyelerin listeleneceğine backend kayıtçısı karar
  // verir (effortCaps.levels). Burada yalnız etiket/renk/açıklama eşlemesi var.
  const LEVEL_META: Record<string, { label: string; color: string; desc: string }> = {
    auto:    { label: t('effort.label.auto'),    color: 'text-sky-400',     desc: t('effort.desc.auto') },
    off:     { label: t('effort.label.off'),     color: 'text-slate-500',   desc: t('effort.desc.off') },
    none:    { label: t('effort.label.none'),    color: 'text-slate-500',   desc: t('effort.desc.none') },
    minimal: { label: t('effort.label.minimal'), color: 'text-teal-400',    desc: t('effort.desc.minimal') },
    low:     { label: t('effort.label.low'),     color: 'text-emerald-400', desc: t('effort.desc.low') },
    medium:  { label: t('effort.label.medium'),  color: 'text-violet-400',  desc: t('effort.desc.medium') },
    high:    { label: t('effort.label.high'),    color: 'text-fuchsia-400', desc: t('effort.desc.high') },
    xhigh:   { label: t('effort.label.xhigh'),   color: 'text-orange-400',  desc: t('effort.desc.xhigh') },
    max:     { label: t('effort.label.max'),     color: 'text-red-400',     desc: t('effort.desc.max') },
  };
  const levels = (effortCaps?.levels?.length ? effortCaps.levels : ['auto'])
    .filter((l) => LEVEL_META[l]);
  const effLevel: string = levels.includes(thinkingLevel) ? thinkingLevel : 'auto';
  const activeMeta = LEVEL_META[effLevel] || LEVEL_META.auto;
  const onlyAuto = levels.length <= 1; // model effort desteklemiyor → bilgi amaçlı panel
  const triggerLabel = isClaudeSubscription && ultracode
    ? 'Ultracode'
    : `Effort ${activeMeta.label}`;

  return (
    <div className="flex items-center gap-2 px-1 mt-1.5">
      <GenerationModeSelector value={generationMode} onChange={setGenerationMode} />
      <div className="w-px h-3 bg-slate-800" />
      
      {/* Effort Selector — dinamik segmented bar (seviyeler backend kayıtçısından) */}
      <div className="relative">
        <button
          onClick={() => setShowThinkingMenu(!showThinkingMenu)}
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-medium transition-all ${
            effLevel !== 'auto' || (isClaudeSubscription && ultracode)
              ? 'bg-violet-500/15 border border-violet-500/30 text-violet-400 shadow-[0_0_15px_rgba(139,92,246,0.1)]'
              : 'text-slate-500 hover:text-slate-300 hover:bg-slate-800/30'
          } ${showThinkingMenu ? 'bg-violet-500/20 text-violet-300' : ''}`}
          title={effortCaps?.note || t('effort.title')}
        >
          <Brain size={11} className={effLevel !== 'auto' ? 'animate-pulse' : ''} />
          <span>{triggerLabel}</span>
          {!ultracode && (effLevel === 'xhigh' || effLevel === 'max') && <Gauge size={10} className="text-orange-400" />}
          {isClaudeSubscription && ultracode && <Rocket size={10} className="text-cyan-400" />}
          <ChevronDown size={10} className={`opacity-50 transition-transform duration-200 ${showThinkingMenu ? 'rotate-180' : ''}`} />
        </button>

        {/* Segmented panel */}
        <AnimatePresence>
          {showThinkingMenu && (
            <>
              <div className="fixed inset-0 z-40" onClick={() => setShowThinkingMenu(false)} />
              <motion.div
                initial={{ opacity: 0, y: 10, scale: 0.95 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: 10, scale: 0.95 }}
                className="absolute bottom-10 left-0 w-[300px] bg-[#0a0a0f] border border-slate-800 rounded-xl shadow-2xl z-50 p-2.5 overflow-hidden"
              >
                <div className="flex items-center justify-between px-0.5 pb-2">
                  <span className="text-[8.5px] font-semibold uppercase tracking-wider text-slate-500">Effort</span>
                  <span className={`text-[8.5px] font-medium ${activeMeta.color}`}>{activeMeta.label}</span>
                </div>

                {/* Segmented bar — yalnız modelin GERÇEKTEN desteklediği seviyeler */}
                <div className="flex w-full rounded-lg border border-slate-800 bg-black/40 p-0.5 gap-0.5">
                  {levels.map((id) => {
                    const meta = LEVEL_META[id];
                    const active = effLevel === id && !(isClaudeSubscription && ultracode);
                    return (
                      <button
                        key={id}
                        onClick={() => {
                          setThinkingLevel(id as ThinkingLevel);
                          if (isClaudeSubscription && ultracode) setUltracode?.(false);
                        }}
                        title={meta.desc}
                        className={`flex-1 min-w-0 px-1 py-1.5 rounded-md text-[9px] font-semibold truncate transition-all ${
                          active
                            ? `${meta.color} bg-white/[0.07] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.08)]`
                            : 'text-slate-500 hover:text-slate-300 hover:bg-white/[0.03]'
                        }`}
                      >
                        {meta.label}
                      </button>
                    );
                  })}
                </div>

                {/* Aktif seviye açıklaması / model notu */}
                <div className="px-0.5 pt-2 text-[9px] leading-relaxed text-slate-500">
                  {isClaudeSubscription && ultracode
                    ? t('effort.ultracodeDesc')
                    : (onlyAuto && effortCaps?.note) ? effortCaps.note : activeMeta.desc}
                </div>

                {/* Claude-only: Ultracode — bağımsız mod satırı */}
                {isClaudeSubscription && (
                  <>
                    <div className="my-2 h-px bg-slate-800" />
                    <button
                      onClick={() => setUltracode?.(!ultracode)}
                      title={t('ultracode.title')}
                      className={`w-full text-left px-2 py-1.5 rounded-lg text-[10px] transition-all hover:bg-white/5 flex items-center justify-between ${
                        ultracode ? 'text-cyan-400 bg-white/5' : 'text-slate-400'
                      }`}
                    >
                      <span className="flex items-center gap-1.5 font-medium"><Rocket size={11} />Ultracode</span>
                      <span className={`w-1.5 h-1.5 rounded-full ${ultracode ? 'bg-current shadow-[0_0_8px_currentColor]' : 'bg-slate-700'}`} />
                    </button>
                  </>
                )}
              </motion.div>
            </>
          )}
        </AnimatePresence>
      </div>

      <div className="w-px h-3 bg-slate-800" />

      {/* Projeyi Öğren & Hafıza Menüsü */}
      <div className="relative flex items-center">
        <button
          onClick={() => analyzeProject()}
          disabled={isAnalyzingProject}
          className={`flex items-center gap-1.5 px-3 py-1 rounded-l-lg text-[11px] font-medium transition-all ${
            isAnalyzingProject
              ? 'bg-blue-500/20 text-blue-400 animate-pulse'
              : 'text-slate-500 hover:text-blue-400 hover:bg-blue-500/5'
          }`}
          title={t('memory.learnTitle')}
        >
          {isAnalyzingProject ? (
            <div className="flex items-center gap-2">
              <div className="w-2.5 h-2.5 border-2 border-blue-500/30 border-t-blue-500 rounded-full animate-spin" />
              <span>{t('memory.learning')}</span>
            </div>
          ) : (
            <>
              <Sparkles size={11} className="text-blue-500" />
              <span>{t('memory.learnProject')}</span>
            </>
          )}
        </button>
        <button
          onClick={() => setShowMemoryMenu(!showMemoryMenu)}
          disabled={isAnalyzingProject || !activeConvId}
          className={`px-1.5 py-1 border-l border-slate-800 rounded-r-lg text-slate-500 hover:text-blue-400 hover:bg-blue-500/5 transition-all ${
            showMemoryMenu ? 'bg-blue-500/10 text-blue-400' : ''
          }`}
        >
          <ChevronDown size={12} className={`transition-transform duration-200 ${showMemoryMenu ? 'rotate-180' : ''}`} />
        </button>

        <AnimatePresence>
          {showMemoryMenu && (
            <>
              <div className="fixed inset-0 z-40" onClick={() => setShowMemoryMenu(false)} />
              <motion.div
                initial={{ opacity: 0, y: 10, scale: 0.95 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: 10, scale: 0.95 }}
                className="absolute bottom-10 right-0 w-48 bg-[#0a0a0f] border border-slate-800 rounded-xl shadow-2xl z-50 py-1.5 overflow-hidden"
              >
                <button
                  onClick={() => { analyzeProject(); setShowMemoryMenu(false); }}
                  className="w-full flex items-center justify-between px-3 py-2 text-[11px] text-slate-300 hover:bg-blue-600/10 hover:text-blue-400 transition-all"
                >
                  <span>{t('memory.refresh')}</span>
                  <Sparkles size={11} />
                </button>
                <button
                  onClick={async () => { setShowMemoryMenu(false); await exportMemory(); }}
                  className="w-full flex items-center gap-2.5 px-3 py-2 text-[11px] text-slate-300 hover:bg-blue-600/10 hover:text-blue-400 transition-colors"
                >
                  <Download size={13} />
                  {t('memory.export')}
                </button>
                <button
                  onClick={async () => { setShowMemoryMenu(false); await importMemory(); }}
                  className="w-full flex items-center gap-2.5 px-3 py-2 text-[11px] text-slate-300 hover:bg-emerald-600/10 hover:text-emerald-400 transition-colors"
                >
                  <Upload size={13} />
                  {t('memory.import')}
                </button>
              </motion.div>
            </>
          )}
        </AnimatePresence>
      </div>

      {/* Kalıcı bağlam + kullanım göstergesi.
          Eskiden `contextUsage.percent > 0` koşuluyla çiziliyordu, yani ilk tur
          bitene kadar hiç görünmüyordu — "sürekli görünen bir yer" isteğinin tam
          tersi. Artık aktif sohbet varsa hep duruyor ve verisi yokken bunu
          SÖYLÜYOR; boş bir halka "doluluk sıfır" diye okunurdu. */}
      {activeConvId && (
        <>
          <div className="w-px h-3 bg-slate-800" />
          <button
            data-testid="context-gauge"
            onClick={() => compactConversation()}
            disabled={isCompacting}
            title={contextUsage
              ? t('usage.estimateTitle', { yuzde: contextUsage.percent, sayi: contextUsage.message_count })
              : t('usage.noData')}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-medium transition-colors group relative ${
              yuzde >= 90 ? 'bg-red-500/10 border border-red-500/30 text-red-400 hover:bg-red-500/20'
              : yuzde >= 75 ? 'bg-amber-500/10 border border-amber-500/30 text-amber-400 hover:bg-amber-500/20'
              : 'text-slate-500 hover:text-slate-300 border border-transparent hover:border-slate-800/50 hover:bg-slate-800/30'
            }`}
          >
            <div className="relative w-3.5 h-3.5 flex items-center justify-center">
              <svg className="w-full h-full transform -rotate-90" viewBox="0 0 36 36">
                <path
                  className="text-slate-800"
                  d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className={`${yuzde >= 90 ? 'text-red-500'
                      : yuzde >= 75 ? 'text-amber-500'
                        : 'text-blue-500'
                    } transition-all duration-500`}
                  strokeDasharray={`${yuzde}, 100`}
                  d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="4"
                />
              </svg>
              {contextUsage?.should_compact && (
                <span className="absolute -top-1 -right-1 w-1.5 h-1.5 bg-red-500 rounded-full animate-ping" />
              )}
            </div>
            {/* Tahmin olduğunu "~" söylüyor: yüzde ölçülmüş bir sayı değil, ve
                işaretsiz bir "%12" onu ölçüm gibi gösterir. */}
            <span data-testid="context-percent">
              {contextUsage ? `~%${yuzde}` : t('usage.noData')}
            </span>
            <span className="text-slate-600">·</span>
            <span>{isCompacting ? t('memory.compacting') : t('memory.compact')}</span>
          </button>

          {/* GERÇEK token — yalnız sağlayıcı bildirdiyse. 8 çalıştırma yolunun
              4'ü (Codex, agy, oneshot CLI'lar, basit yol) hiç bildirmiyor, ve
              orada sıfır göstermek "hiç harcamadın" demek olurdu. */}
          {tokenVar ? (
            <span
              data-testid="session-tokens"
              title={t('usage.tokensTitle', {
                giris: sessionUsage!.input_tokens.toLocaleString('tr-TR'),
                cikis: sessionUsage!.output_tokens.toLocaleString('tr-TR'),
                tur: sessionUsage!.turns,
              })}
              className="px-2 py-1 rounded-lg text-[11px] font-medium text-slate-500 border border-transparent"
            >
              {kisaSayi(sessionUsage!.input_tokens + sessionUsage!.output_tokens)} tok
              {typeof sessionUsage!.cost_usd === 'number' && (
                <span className="ml-1.5 text-slate-600" title={t('usage.costTitle', { tutar: `$${sessionUsage!.cost_usd.toFixed(2)}` })}>
                  ${sessionUsage!.cost_usd.toFixed(2)}
                </span>
              )}
            </span>
          ) : (
            <span
              data-testid="session-tokens-none"
              title={t('usage.noTokens')}
              className="px-2 py-1 rounded-lg text-[11px] font-medium text-slate-700 border border-transparent"
            >
              — tok
            </span>
          )}
        </>
      )}
    </div>
  );
};
