import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { HelpCircle, Check } from 'lucide-react';
import { useLang } from '../../lib/i18n';

interface QuestionOption { label: string; description?: string; }
interface QuestionItem {
  question: string;
  header?: string;
  multiSelect?: boolean;
  options: QuestionOption[];
}

interface QuestionApprovalProps {
  questions: QuestionItem[];
  // answers: { "<soru metni>": "<seçilen label>" }
  onSubmit: (answers: Record<string, string>) => void;
}

/**
 * Claude'un AskUserQuestion (A/B/C) sorusunu chat içinde seçilebilir kart olarak gösterir.
 * Kullanıcı her soru için bir seçenek seçer; "Gönder" cevabı session'a iletir.
 */
export const QuestionApproval: React.FC<QuestionApprovalProps> = ({ questions, onSubmit }) => {
  const { t } = useLang();
  const [selected, setSelected] = useState<Record<string, string>>({});
  const allAnswered = questions.length > 0 && questions.every((q) => selected[q.question]);

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
        {questions.map((q, qi) => (
          <div key={qi}>
            {q.header && (
              <div className="text-[10px] uppercase tracking-wider text-indigo-400/70 font-bold mb-1">{q.header}</div>
            )}
            <p className="text-[13px] text-white font-medium leading-tight mb-2.5">{q.question}</p>
            <div className="grid gap-2">
              {q.options.map((opt, oi) => {
                const isSel = selected[q.question] === opt.label;
                return (
                  <button
                    key={oi}
                    onClick={() => setSelected((s) => ({ ...s, [q.question]: opt.label }))}
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
                          'w-5 h-5 rounded-full flex items-center justify-center shrink-0 text-[10px] font-bold ' +
                          (isSel ? 'bg-indigo-500 text-white' : 'bg-slate-700 text-slate-300')
                        }
                      >
                        {String.fromCharCode(65 + oi)}
                      </span>
                      <span className="text-[12px] text-white font-medium">{opt.label}</span>
                    </div>
                    {opt.description && (
                      <p className="text-[11px] text-slate-400 mt-1 ml-7 leading-snug">{opt.description}</p>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        ))}

        <button
          onClick={() => onSubmit(selected)}
          disabled={!allAnswered}
          className={
            'w-full flex items-center justify-center gap-2 py-2 rounded-lg text-[12px] font-bold transition-all ' +
            (allAnswered
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
