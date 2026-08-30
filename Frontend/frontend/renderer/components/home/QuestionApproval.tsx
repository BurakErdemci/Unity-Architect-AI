import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { HelpCircle, Check } from 'lucide-react';
import { useLang } from '../../lib/i18n';
import { stripBidi } from '../../lib/modelText';

interface QuestionOption { label: string; description?: string; }
interface QuestionItem {
  question: string;
  header?: string;
  multiSelect?: boolean;
  options: QuestionOption[];
}

interface QuestionApprovalProps {
  questions: QuestionItem[];
  // answers: { "<question text>": "<answer string>" } — see WIRE SHAPE below.
  onSubmit: (answers: Record<string, string>) => void;
}

/**
 * The card behind the SDK's AskUserQuestion tool.
 *
 * WIRE SHAPE, measured 30 Aug 2026 from the bundled `claude.exe` the SDK ships:
 * "The answers provided by the user (question text -> answer string;
 * multi-select answers are comma-separated)". So the payload stays
 * Record<string, string> and multiple picks are joined — widening it to an
 * array would have been a guess against a contract we can actually read.
 *
 * WHY FREE TEXT AND SKIP ARE NOT OPTIONAL. The same binary instructs the model:
 * "AskUserQuestion always includes a Skip button and a free-text input box for
 * custom answers, so do not include `None` or `Other` as options." The model
 * therefore omits an escape hatch ON PURPOSE, trusting the host UI to supply
 * one. This card supplied neither until 30 Aug 2026, so a user who agreed with
 * none of the options could only kill the turn. That is a broken contract, not
 * a missing nicety — which is why Skip is per question rather than a single
 * card-level opt-out: the model asks up to four independent questions and
 * "I have no opinion on this one" is a per-question answer.
 *
 * A skipped question is OMITTED from the payload rather than sent as an empty
 * string: absence says "no answer", "" says "the answer is nothing".
 */
export const QuestionApproval: React.FC<QuestionApprovalProps> = ({ questions, onSubmit }) => {
  const { t } = useLang();
  const [picks, setPicks] = useState<Record<string, string[]>>({});
  const [custom, setCustom] = useState<Record<string, string>>({});
  const [skipped, setSkipped] = useState<Record<string, boolean>>({});

  const answerFor = (q: QuestionItem): string => {
    const parts = [...(picks[q.question] || [])];
    const typed = (custom[q.question] || '').trim();
    if (typed) parts.push(typed);
    return parts.join(', ');
  };

  // Presence, not truthiness. The old gate tested `selected[q.question]`, so an
  // answer of "" — reachable the moment a text box exists — read as unanswered
  // and disabled Send with nothing on screen explaining why.
  const isResolved = (q: QuestionItem) => !!skipped[q.question] || answerFor(q).length > 0;
  const allResolved = questions.length > 0 && questions.every(isResolved);

  // A skipped question's controls are `disabled`, so neither of the two
  // functions below can run while it is skipped. Undo therefore goes through
  // the skip toggle alone — deliberately, so "skipped" reads as one state
  // rather than something a stray click can silently reverse. Anyone removing
  // the `disabled` props has to add the un-skip side effect back here.
  const togglePick = (q: QuestionItem, label: string) => {
    if (!q.multiSelect) {
      // Single select: a pick and typed text would contradict each other, so
      // each clears the other. Re-clicking the pick clears it — the only way
      // back out of a misclick when there is no radio group to reset.
      setCustom((c) => ({ ...c, [q.question]: '' }));
    }
    setPicks((p) => {
      const cur = p[q.question] || [];
      if (q.multiSelect) {
        return {
          ...p,
          [q.question]: cur.includes(label) ? cur.filter((x) => x !== label) : [...cur, label],
        };
      }
      return { ...p, [q.question]: cur[0] === label ? [] : [label] };
    });
  };

  const typeCustom = (q: QuestionItem, value: string) => {
    if (!q.multiSelect && value.trim()) setPicks((p) => ({ ...p, [q.question]: [] }));
    setCustom((c) => ({ ...c, [q.question]: value }));
  };

  const toggleSkip = (q: QuestionItem) =>
    setSkipped((s) => ({ ...s, [q.question]: !s[q.question] }));

  const submit = () => {
    const answers: Record<string, string> = {};
    for (const q of questions) {
      if (skipped[q.question]) continue;
      const a = answerFor(q);
      if (a) answers[q.question] = a;
    }
    onSubmit(answers);
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      className="mt-3 rounded-xl border border-indigo-500/30 bg-indigo-950/10 overflow-hidden shadow-lg shadow-indigo-950/20"
    >
      <div className="flex items-center gap-2 px-4 py-2.5 bg-indigo-500/10 border-b border-indigo-500/20">
        <div className="flex items-center gap-2 text-indigo-300 font-bold text-[11px] uppercase tracking-wider">
          <HelpCircle size={14} />
          {t('question.asking')}
        </div>
      </div>

      <div className="p-4 space-y-4">
        {questions.map((q, qi) => {
          const isSkipped = !!skipped[q.question];
          const chosen = picks[q.question] || [];
          return (
            <div key={qi} className={isSkipped ? 'opacity-45' : undefined}>
              {q.header && (
                <div className="text-[10px] uppercase tracking-wider text-indigo-400/70 font-bold mb-1">
                  {stripBidi(q.header)}
                </div>
              )}
              <p className="text-[13px] text-white font-medium leading-tight mb-1 break-words">
                {stripBidi(q.question)}
              </p>
              {q.multiSelect && (
                <p className="text-[10.5px] text-indigo-300/70 mb-2">{t('question.multiHint')}</p>
              )}
              <div className="grid gap-2 mt-2">
                {q.options.map((opt, oi) => {
                  // Sanitise once and use the SAME string for display and for the
                  // submitted value. Showing a cleaned label while sending the raw
                  // one would reopen the exact gap stripBidi exists to close: what
                  // the user picked would differ from what the model receives.
                  // The question text is NOT sanitised — it is the payload KEY and
                  // the SDK matches it against what it sent us.
                  const label = stripBidi(opt.label);
                  const isSel = chosen.includes(label);
                  return (
                    <button
                      key={oi}
                      data-testid="question-option"
                      disabled={isSkipped}
                      onClick={() => togglePick(q, label)}
                      className={
                        'text-left px-3 py-2 rounded-lg border transition-all active:scale-[0.99] ' +
                        (isSel
                          ? 'border-indigo-400 bg-indigo-500/20 ring-1 ring-indigo-400/40'
                          : 'border-white/10 bg-black/30 hover:bg-white/5 hover:border-white/20')
                      }
                    >
                      <div className="flex items-center gap-2">
                        <span
                          className={
                            'w-5 h-5 flex items-center justify-center shrink-0 text-[10px] font-bold ' +
                            // Square for multi-select, circle for single: the shape is the
                            // only cue that more than one pick is allowed before you try it.
                            (q.multiSelect ? 'rounded-[5px] ' : 'rounded-full ') +
                            (isSel ? 'bg-indigo-500 text-white' : 'bg-slate-700 text-slate-300')
                          }
                        >
                          {q.multiSelect
                            ? (isSel ? <Check size={11} className="stroke-[3px]" /> : null)
                            : String.fromCharCode(65 + oi)}
                        </span>
                        <span className="text-[12px] text-white font-medium break-words">
                          {label}
                        </span>
                      </div>
                      {opt.description && (
                        <p className="text-[11px] text-slate-400 mt-1 ml-7 leading-snug break-words">
                          {stripBidi(opt.description)}
                        </p>
                      )}
                    </button>
                  );
                })}
              </div>

              <input
                data-testid="question-custom"
                type="text"
                disabled={isSkipped}
                value={custom[q.question] || ''}
                onChange={(e) => typeCustom(q, e.target.value)}
                placeholder={t('question.otherPlaceholder')}
                className="mt-2 w-full px-3 py-2 rounded-lg bg-black/30 border border-white/10 text-[12px] text-white placeholder:text-slate-500 focus:outline-none focus:border-indigo-400/60 focus:ring-1 focus:ring-indigo-400/30 disabled:cursor-not-allowed"
              />

              <button
                data-testid="question-skip"
                onClick={() => toggleSkip(q)}
                className="mt-1.5 text-[11px] text-slate-400 hover:text-slate-200 underline underline-offset-2 transition-colors"
              >
                {isSkipped ? t('question.skipped') : t('question.skip')}
              </button>
            </div>
          );
        })}

        <button
          data-testid="question-send"
          onClick={submit}
          disabled={!allResolved}
          className={
            'w-full flex items-center justify-center gap-2 py-2 rounded-lg text-[12px] font-bold transition-all ' +
            (allResolved
              ? 'bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-900/20 active:scale-[0.98]'
              : 'bg-slate-800 text-slate-500 cursor-not-allowed')
          }
        >
          <Check size={14} className="stroke-[3px]" />
          {t('question.send')}
        </button>
      </div>
    </motion.div>
  );
};
