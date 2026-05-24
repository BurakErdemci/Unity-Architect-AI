import React from 'react';
import { motion } from 'framer-motion';
import { AlertTriangle, Trash2, X, Check } from 'lucide-react';
import { useLang } from '../../lib/i18n';

interface FileDeleteApprovalProps {
  path: string;
  onConfirm: () => Promise<void>;
  onCancel: () => void;
}

export const FileDeleteApproval: React.FC<FileDeleteApprovalProps> = ({
  path,
  onConfirm,
  onCancel
}) => {
  const { t } = useLang();
  const fileName = path.split('/').pop();

  return (
    <motion.div 
      initial={{ opacity: 0, y: 10, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      className="mt-3 rounded-xl border border-rose-500/30 bg-rose-950/10 overflow-hidden shadow-lg shadow-rose-950/20"
    >
      <div className="flex items-center justify-between px-4 py-2.5 bg-rose-500/10 border-b border-rose-500/20">
        <div className="flex items-center gap-2 text-rose-400 font-bold text-[11px] uppercase tracking-wider">
          <AlertTriangle size={14} />
          {t('deleteApproval.title')}
        </div>
        <button onClick={onCancel} className="text-slate-500 hover:text-white transition-colors">
          <X size={14} />
        </button>
      </div>
      
      <div className="p-4">
        <div className="flex items-start gap-3 mb-4">
          <div className="w-10 h-10 rounded-full bg-rose-500/20 flex items-center justify-center shrink-0">
            <Trash2 size={20} className="text-rose-500" />
          </div>
          <div>
            <p className="text-[13px] text-white font-medium leading-tight">
              "<span className="text-rose-400 font-bold">{fileName}</span>" {t('deleteApproval.confirm')}
            </p>
            <p className="text-[11px] text-slate-500 mt-1 font-mono break-all">
              {path}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button 
            onClick={onConfirm}
            className="flex-1 flex items-center justify-center gap-2 py-2 bg-rose-600 hover:bg-rose-500 text-white rounded-lg text-[12px] font-bold transition-all shadow-lg shadow-rose-900/20 active:scale-[0.98]"
          >
            <Check size={14} className="stroke-[3px]" />
            {t('deleteApproval.yes')}
          </button>
          <button 
            onClick={onCancel}
            className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-[12px] font-bold transition-all"
          >
            {t('deleteApproval.cancel')}
          </button>
        </div>
      </div>
      
      <div className="px-4 py-2 bg-black/40 border-t border-rose-500/10">
        <p className="text-[10px] text-slate-600 italic">
          * {t('deleteApproval.warning')}
        </p>
      </div>
    </motion.div>
  );
};
