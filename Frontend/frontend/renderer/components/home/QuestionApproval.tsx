import React, { useRef, useState } from 'react';
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
 *
 * STATE IS KEYED BY ROW INDEX, NOT BY QUESTION TEXT. The rows are rendered by
 * index, and nothing stops the model from asking two questions with identical
 * text (different option sets, e.g. "Which transport?" twice). Keyed by text,
 * the first row's answer silently resolved the second: Send lit up while a row
 * still had no selection on screen. Only the payload keys stay textual, because
 * the SDK matches them against the text it sent (see WIRE SHAPE above).
 */
const QuestionGateCard: React.FC<QuestionApprovalProps> = ({ questions, onSubmit }) => {
  const { t } = useLang();
  const [picks, setPicks] = useState<Record<number, string[]>>({});
  const [custom, setCustom] = useState<Record<number, string>>({});
  const [skipped, setSkipped] = useState<Record<number, boolean>>({});

  const answerFor = (qi: number): string => {
    const parts = [...(picks[qi] || [])];
    const typed = (custom[qi] || '').trim();
    if (typed) parts.push(typed);
    return parts.join(', ');
  };

  // Presence, not truthiness. The old gate tested `selected[q.question]`, so an
  // answer of "" — reachable the moment a text box exists — read as unanswered
  // and disabled Send with nothing on screen explaining why.
  const isResolved = (qi: number) => !!skipped[qi] || answerFor(qi).length > 0;
  const allResolved = questions.length > 0 && questions.every((_, qi) => isResolved(qi));

  // A skipped question's controls are `disabled`, so neither of the two
  // functions below can run while it is skipped. Undo therefore goes through
  // the skip toggle alone — deliberately, so "skipped" reads as one state
  // rather than something a stray click can silently reverse. Anyone removing
  // the `disabled` props has to add the un-skip side effect back here.
  const togglePick = (qi: number, q: QuestionItem, label: string) => {
    if (!q.multiSelect) {
      // Single select: a pick and typed text would contradict each other, so
      // each clears the other. Re-clicking the pick clears it — the only way
      // back out of a misclick when there is no radio group to reset.
      setCustom((c) => ({ ...c, [qi]: '' }));
    }
    setPicks((p) => {
      const cur = p[qi] || [];
      if (q.multiSelect) {
        return {
          ...p,
          [qi]: cur.includes(label) ? cur.filter((x) => x !== label) : [...cur, label],
        };
      }
      return { ...p, [qi]: cur[0] === label ? [] : [label] };
    });
  };

  const typeCustom = (qi: number, q: QuestionItem, value: string) => {
    if (!q.multiSelect && value.trim()) setPicks((p) => ({ ...p, [qi]: [] }));
    setCustom((c) => ({ ...c, [qi]: value }));
  };

  const toggleSkip = (qi: number) =>
    setSkipped((s) => ({ ...s, [qi]: !s[qi] }));

  const submit = () => {
    const answers: Record<string, string> = {};
    questions.forEach((q, qi) => {
      if (skipped[qi]) return;
      const a = answerFor(qi);
      if (!a) return;
      // Two rows CAN carry the same question text, but the payload is keyed by
      // that text (SDK contract, see WIRE SHAPE) so their answers have to share
      // one key. They are joined with the same ", " the SDK documents for
      // multi-select answers — losing the second answer to an overwrite would
      // be the one outcome the user cannot detect.
      answers[q.question] = answers[q.question] ? `${answers[q.question]}, ${a}` : a;
    });
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
          const isSkipped = !!skipped[qi];
          const chosen = picks[qi] || [];
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
                      onClick={() => togglePick(qi, q, label)}
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
                value={custom[qi] || ''}
                onChange={(e) => typeCustom(qi, q, e.target.value)}
                placeholder={t('question.otherPlaceholder')}
                className="mt-2 w-full px-3 py-2 rounded-lg bg-black/30 border border-white/10 text-[12px] text-white placeholder:text-slate-500 focus:outline-none focus:border-indigo-400/60 focus:ring-1 focus:ring-indigo-400/30 disabled:cursor-not-allowed"
              />

              <button
                data-testid="question-skip"
                onClick={() => toggleSkip(qi)}
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

/**
 * WHAT IDENTIFIES A GATE: the `questions` array itself (audit
 * `question-gate-state-reuse`, 30 Aug 2026).
 *
 * Question gates are QUEUED (useChat.ts: a second `question_needed` while one
 * is on screen is pushed onto `pendingQuestionQueueRef`, and answering shifts
 * the next one into the same `pendingQuestion` slot). The chat renders the card
 * at the same position for every gate, so React kept ONE component instance
 * alive across the whole queue and the second gate inherited the first gate's
 * picks, typed text and skip flags: Send was already enabled, and one click
 * submitted an answer the user never chose under the next gate's question text.
 *
 * Each gate carries its own `questions` array — built once from that gate's
 * payload and stored in state, never rebuilt per render — so array identity IS
 * gate identity, and it stays distinct even when two gates ask literally the
 * same thing. Serialising the contents would have merged those two into one
 * key, which is the same bug wearing a hash.
 *
 * The reset is a REMOUNT rather than an effect that clears the three state
 * buckets, because an effect has to be kept in step with the state it clears:
 * a fourth bucket added later would silently leak across gates again. A `key`
 * change discards whatever state the card holds, including state that does not
 * exist yet.
 */
export const QuestionApproval: React.FC<QuestionApprovalProps> = ({ questions, onSubmit }) => {
  // Array references cannot be React keys, so map each one to a number the
  // first time it is seen. Compared by reference, so a re-render with the same
  // gate keeps the same key and the user's half-filled answers survive.
  const gate = useRef<{ questions: QuestionItem[]; key: number } | null>(null);
  if (!gate.current || gate.current.questions !== questions) {
    gate.current = { questions, key: (gate.current?.key ?? 0) + 1 };
  }

  return <QuestionGateCard key={gate.current.key} questions={questions} onSubmit={onSubmit} />;
};
