import React from 'react';
import { AlertTriangle } from 'lucide-react';
import { useLang } from '../../lib/i18n';
import { MessageNotice } from './types';

/**
 * Non-error notices under an assistant message: a run that hit its iteration
 * cap, or a side pipeline (video download/extract) that broke while the run
 * itself carried on.
 *
 * Own component rather than inline JSX in `ChatPanel` so it can be rendered in a
 * test without dragging in Monaco through `DiffViewer` — "the function was
 * called" is not "the user saw it", and this repo has already paid for that
 * (`ToastContainer` was defined, exported and mounted nowhere).
 *
 * Amber and no ❌: the red/❌ look is reserved for a turn that actually failed.
 * A capped run did real work, so dressing it as a crash sends the user looking
 * for a bug that is not there.
 */
export const MessageNotices: React.FC<{ notices?: MessageNotice[] }> = ({ notices }) => {
  const { t } = useLang();
  if (!notices || notices.length === 0) return null;
  return (
    <div className="mt-3 space-y-2">
      {notices.map((notice, i) => (
        <div key={i} className="rounded-lg border border-amber-500/25 bg-amber-500/[0.07] p-2.5">
          <div className="flex items-start gap-2">
            <AlertTriangle size={12} className="text-amber-400 shrink-0 mt-0.5" />
            <div className="min-w-0">
              <div className="text-[10px] font-semibold text-amber-400 uppercase tracking-wider mb-1">{notice.title}</div>
              <div className="text-[12px] text-slate-300 leading-relaxed">{notice.message}</div>
              {notice.detail && (
                <details className="mt-1.5">
                  <summary className="text-[10.5px] text-slate-500 hover:text-slate-300 cursor-pointer select-none">
                    {t('notice.detail')}
                  </summary>
                  <pre className="mt-1 text-[10.5px] text-slate-500 whitespace-pre-wrap break-all font-mono">{notice.detail}</pre>
                </details>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
};
