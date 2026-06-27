import React, { useMemo, useState, useRef, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Search, Sparkles, Terminal, Puzzle, X } from 'lucide-react';

export interface CommandMeta {
  name: string;
  description?: string;
  argumentHint?: string;
  insert?: string;        // tıklanınca girdiye yazılacak metin (Codex skill'leri: defaultPrompt)
  displayName?: string;   // Codex skill'lerinin insanca adı (varsa name yerine gösterilir)
}

interface Props {
  meta: CommandMeta[];
  skills: string[];          // yetkili skill isim listesi (system/init'ten; cold-start'ta boş olabilir)
  provider?: string;         // 'claude' | 'codex' | ... — gösterim/insert davranışı için
  onSelect: (insertText: string) => void;
  onClose: () => void;
}

interface Group { key: string; label: string; icon: React.ReactNode; items: CommandMeta[]; }

/**
 * Açıklamalı, aranabilir komut & skill galerisi. Backend /slash-commands'ın `meta`
 * alanından beslenir (her komutun açıklaması get_server_info'dan gelir). Bir öğeye
 * tıklayınca '/<isim>' chat girdisine yazılır (argüman gerektiriyorsa kullanıcı
 * tamamlar) — yanlışlıkla yıkıcı komut tetiklenmesini önlemek için doğrudan
 * gönderilmez. Skill'ler ✨ ile en üstte; eklentiler prefix'e göre gruplanır.
 */
export const SkillsGallery: React.FC<Props> = ({ meta, skills, provider, onSelect, onClose }) => {
  const [query, setQuery] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const isClaude = provider !== 'codex';  // Codex skill'leri '/' ile çağrılmaz (defaultPrompt/$ ile)

  useEffect(() => { inputRef.current?.focus(); }, []);

  const skillSet = useMemo(() => new Set(skills || []), [skills]);

  const groups = useMemo<Group[]>(() => {
    const q = query.trim().toLowerCase();
    const filtered = (meta || []).filter(c =>
      !q || c.name.toLowerCase().includes(q) || (c.description || '').toLowerCase().includes(q)
    );

    const skillItems: CommandMeta[] = [];
    const pluginMap: Record<string, CommandMeta[]> = {};
    const general: CommandMeta[] = [];

    for (const c of filtered) {
      if (skillSet.has(c.name)) { skillItems.push(c); continue; }
      const colon = c.name.indexOf(':');
      if (colon > 0) {
        const pfx = c.name.slice(0, colon);
        (pluginMap[pfx] ||= []).push(c);
      } else {
        general.push(c);
      }
    }

    const out: Group[] = [];
    if (skillItems.length) out.push({ key: 'skills', label: 'Skills', icon: <Sparkles size={12} className="text-violet-300" />, items: skillItems });
    Object.keys(pluginMap).sort().forEach(pfx =>
      out.push({ key: 'plugin:' + pfx, label: pfx, icon: <Puzzle size={12} className="text-sky-300" />, items: pluginMap[pfx] })
    );
    if (general.length) out.push({ key: 'general', label: 'Komutlar', icon: <Terminal size={12} className="text-slate-400" />, items: general });
    return out;
  }, [meta, skillSet, query]);

  const total = useMemo(() => groups.reduce((n, g) => n + g.items.length, 0), [groups]);

  return (
    <motion.div
      className="absolute left-4 right-4 bottom-full mb-2 backdrop-blur-xl bg-black rounded-xl z-50 shadow-2xl border border-white/10 overflow-hidden"
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 6 }}
    >
      {/* Başlık + arama */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-white/10 bg-white/[0.02]">
        <Sparkles size={13} className="text-violet-300 shrink-0" />
        <span className="text-[11px] font-semibold text-white/80 uppercase tracking-wider shrink-0">Skills & Komutlar</span>
        <div className="relative flex-1 ml-1">
          <Search size={11} className="absolute left-2 top-1/2 -translate-y-1/2 text-white/30" />
          <input
            ref={inputRef}
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Ara…"
            className="w-full bg-white/[0.04] border border-white/10 rounded-md pl-7 pr-2 py-1 text-[11px] text-white/80 placeholder:text-white/25 focus:outline-none focus:border-white/25"
          />
        </div>
        <button onClick={onClose} className="p-1 rounded text-white/40 hover:text-white/90 hover:bg-white/10 transition-colors shrink-0">
          <X size={13} />
        </button>
      </div>

      <div className="max-h-[340px] overflow-y-auto custom-scrollbar py-1">
        {total === 0 ? (
          <div className="px-3 py-6 text-center text-[11px] text-white/30">Eşleşen komut yok</div>
        ) : (
          groups.map(g => (
            <div key={g.key} className="px-1 py-1">
              <div className="flex items-center gap-1.5 px-2 py-1">
                {g.icon}
                <span className="text-[9px] font-semibold uppercase tracking-wider text-white/40">{g.label}</span>
                <span className="text-[9px] text-white/25">({g.items.length})</span>
              </div>
              {g.items.map(c => {
                const needsArgs = !!(c.argumentHint && c.argumentHint.trim());
                const insertText = c.insert || ('/' + c.name + ' ');
                const label = isClaude ? '/' + c.name : (c.displayName || c.name);
                return (
                  <button
                    key={c.name}
                    onClick={() => onSelect(insertText)}
                    className="w-full text-left flex flex-col gap-0.5 px-2.5 py-1.5 rounded-lg hover:bg-white/[0.06] transition-colors group"
                  >
                    <div className="flex items-baseline gap-2">
                      <span className="text-[12px] font-medium text-white/85 group-hover:text-white">{label}</span>
                      {needsArgs && (
                        <span className="text-[9px] text-amber-300/70 font-mono">{c.argumentHint}</span>
                      )}
                    </div>
                    {c.description && (
                      <span className="text-[10.5px] text-white/40 leading-snug line-clamp-2">{c.description}</span>
                    )}
                  </button>
                );
              })}
            </div>
          ))
        )}
      </div>
    </motion.div>
  );
};
