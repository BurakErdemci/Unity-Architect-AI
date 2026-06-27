import React, { useMemo, useState } from 'react';
import { Gauge, Layers, Clock, ChevronDown, ChevronRight } from 'lucide-react';
import { MarkdownRenderer } from './MarkdownRenderer';

/**
 * Claude Code'un metin döndüren slash komutlarını düz markdown baloncuğu yerine
 * yapısal bir kart olarak gösterir:
 *   • /usage  → satır-bazlı: "X% used" → renkli progress bar, "Key: Value" →
 *               istatistik, gerisi → katlanır not. (Parse başarısızsa ham metne düşer.)
 *   • /context → markdown (tablo) döner; "**Tokens:** X / Y (Z%)" özetinden bir
 *               headline bar çıkarılır, tam markdown altta "Ayrıntı"da gösterilir.
 * NOT: `/cost` bu Claude Code sürümünde yok — session cost `/usage` içindedir.
 */

function barColor(p: number): string {
  if (p >= 80) return 'bg-red-500';
  if (p >= 50) return 'bg-amber-500';
  return 'bg-emerald-500';
}

// ── /context: markdown özeti → headline bar + tam markdown ────────────────
const ContextCard: React.FC<{ text: string; workspacePath?: string | null }> = ({ text, workspacePath }) => {
  const [open, setOpen] = useState(false);
  const head = useMemo(() => {
    const m = text.match(/\*\*Tokens:\*\*\s*([\d.]+\s*[kKmMbB]?)\s*\/\s*([\d.]+\s*[kKmMbB]?)\s*\((\d+(?:\.\d+)?)%\)/);
    const model = text.match(/\*\*Model:\*\*\s*([^\n*]+)/);
    if (!m) return null;
    return { used: m[1].replace(/\s+/g, ''), total: m[2].replace(/\s+/g, ''), pct: Math.min(100, parseFloat(m[3])), model: model?.[1]?.trim() };
  }, [text]);

  // Özet çıkmazsa ham markdown'a düş (tablolar zaten güzel render olur)
  if (!head) {
    return (
      <div className="prose prose-invert max-w-none text-[13px] leading-relaxed prose-table:text-[11px]">
        <MarkdownRenderer content={text} workspacePath={workspacePath} />
      </div>
    );
  }

  return (
    <div className="bg-[#000000] rounded-xl border border-violet-500/20 overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-violet-500/20">
        <Layers size={14} className="text-violet-400" />
        <span className="text-[11px] font-semibold uppercase tracking-wider text-violet-400">Bağlam</span>
        <span className="text-[10px] text-slate-500 ml-auto font-mono">/context</span>
      </div>
      <div className="px-4 py-3 space-y-2.5">
        {head.model && <p className="text-[11px] text-slate-500 font-mono">{head.model}</p>}
        <div>
          <div className="flex items-baseline justify-between mb-1">
            <span className="text-[12px] text-slate-200 font-medium">{head.used} / {head.total} token</span>
            <span className="text-[12px] font-semibold tabular-nums text-slate-300">{head.pct}%</span>
          </div>
          <div className="h-1.5 w-full rounded-full bg-slate-800 overflow-hidden">
            <div className={`h-full rounded-full ${barColor(head.pct)} transition-all duration-500`} style={{ width: `${Math.max(head.pct, 1)}%` }} />
          </div>
        </div>
        <button onClick={() => setOpen(v => !v)} className="flex items-center gap-1 text-[10px] text-slate-500 hover:text-slate-300 transition-colors">
          {open ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
          <span>Kategori dökümü</span>
        </button>
        {open && (
          <div className="prose prose-invert max-w-none text-[11px] leading-relaxed prose-table:text-[10.5px] prose-th:py-1 prose-td:py-0.5 border-t border-slate-800 pt-2">
            <MarkdownRenderer content={text} workspacePath={workspacePath} />
          </div>
        )}
      </div>
    </div>
  );
};

// ── /usage: satır-bazlı parser ────────────────────────────────────────────
interface ParsedBar { label: string; pct: number; reset?: string; }
interface ParsedStat { label: string; value: string; }
interface Parsed { subtitle: string; bars: ParsedBar[]; stats: ParsedStat[]; notes: string[]; }

function parseSlashOutput(text: string): Parsed {
  const lines = (text || '').split('\n').map(l => l.trim()).filter(Boolean);
  const bars: ParsedBar[] = [];
  const stats: ParsedStat[] = [];
  const notes: string[] = [];
  let subtitle = '';

  for (const line of lines) {
    // "Current session: 22% used · resets Jun 27, 11pm (Europe/Istanbul)"
    const pm = line.match(/^(.+?):\s*(\d+(?:\.\d+)?)%\s*used\b\s*(?:[·•-]\s*(resets?.+))?$/i);
    if (pm) {
      bars.push({ label: pm[1].trim(), pct: Math.min(100, parseFloat(pm[2])), reset: pm[3]?.trim() });
      continue;
    }
    // Genel "Label: değer" (URL değilse, çok uzun değilse)
    const kv = line.match(/^([A-Za-z$][\w .()\/$-]{0,38}):\s*(.+)$/);
    if (kv && !/^https?:\/\//i.test(kv[2]) && !kv[2].includes('://')) {
      stats.push({ label: kv[1].trim(), value: kv[2].trim() });
      continue;
    }
    // İlk açıklama satırı → alt başlık
    if (!subtitle && /subscription|using|cost|usage/i.test(line) && !line.endsWith('?') && line.length < 120) {
      subtitle = line;
      continue;
    }
    notes.push(line);
  }
  return { subtitle, bars, stats, notes };
}

interface Props {
  command: 'usage' | 'context' | string;
  text: string;
  workspacePath?: string | null;
}

export const SlashCommandCard: React.FC<Props> = ({ command, text, workspacePath }) => {
  if (command === 'context') return <ContextCard text={text} workspacePath={workspacePath} />;

  const { subtitle, bars, stats, notes } = useMemo(() => parseSlashOutput(text), [text]);
  const [notesOpen, setNotesOpen] = useState(false);

  // Hiçbir yapısal sinyal yoksa → ham metne düş (markdown)
  if (bars.length === 0 && stats.length === 0 && !subtitle) {
    return (
      <div className="prose prose-invert max-w-none text-[13px] leading-relaxed">
        <MarkdownRenderer content={text} workspacePath={workspacePath} />
      </div>
    );
  }

  return (
    <div className="bg-[#000000] rounded-xl border border-blue-500/20 overflow-hidden">
      {/* Başlık */}
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-blue-500/20">
        <Gauge size={14} className="text-blue-400" />
        <span className="text-[11px] font-semibold uppercase tracking-wider text-blue-400">Kullanım</span>
        <span className="text-[10px] text-slate-500 ml-auto font-mono">/{command}</span>
      </div>

      <div className="px-4 py-3 space-y-3">
        {subtitle && (
          <p className="text-[12px] text-slate-400 leading-relaxed">{subtitle}</p>
        )}

        {/* Yüzde bar'ları */}
        {bars.length > 0 && (
          <div className="space-y-2.5">
            {bars.map((b, i) => (
              <div key={i}>
                <div className="flex items-baseline justify-between mb-1">
                  <span className="text-[12px] text-slate-200 font-medium">{b.label}</span>
                  <span className="text-[12px] font-semibold tabular-nums text-slate-300">{b.pct}%</span>
                </div>
                <div className="h-1.5 w-full rounded-full bg-slate-800 overflow-hidden">
                  <div
                    className={`h-full rounded-full ${barColor(b.pct)} transition-all duration-500`}
                    style={{ width: `${Math.max(b.pct, 1)}%` }}
                  />
                </div>
                {b.reset && (
                  <div className="flex items-center gap-1 mt-1 text-[10px] text-slate-500">
                    <Clock size={9} />
                    <span>{b.reset.replace(/^resets?\s*/i, 'sıfırlanır: ')}</span>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Key: Value istatistikleri */}
        {stats.length > 0 && (
          <div className="space-y-1.5 pt-0.5">
            {stats.map((s, i) => (
              <div key={i} className="flex items-baseline justify-between gap-3 text-[12px]">
                <span className="text-slate-400 shrink-0">{s.label}</span>
                <span className="text-slate-200 font-medium text-right tabular-nums break-all">{s.value}</span>
              </div>
            ))}
          </div>
        )}

        {/* Detay notları (katlanır) */}
        {notes.length > 0 && (
          <div className="pt-1">
            <button
              onClick={() => setNotesOpen(v => !v)}
              className="flex items-center gap-1 text-[10px] text-slate-500 hover:text-slate-300 transition-colors"
            >
              {notesOpen ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
              <span>Ayrıntı ({notes.length})</span>
            </button>
            {notesOpen && (
              <div className="mt-2 space-y-1 text-[11px] text-slate-500 leading-relaxed border-l border-slate-800 pl-2.5">
                {notes.map((n, i) => <p key={i}>{n}</p>)}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
