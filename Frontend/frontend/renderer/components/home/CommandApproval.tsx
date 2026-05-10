import React from 'react';
import { motion } from 'framer-motion';
import { Terminal, X, Check, AlertTriangle } from 'lucide-react';

interface CommandApprovalProps {
  command: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export const CommandApproval: React.FC<CommandApprovalProps> = ({ command, onConfirm, onCancel }) => {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      className="mt-3 rounded-xl border border-amber-500/30 bg-amber-950/10 overflow-hidden shadow-lg shadow-amber-950/20"
    >
      <div className="flex items-center justify-between px-4 py-2.5 bg-amber-500/10 border-b border-amber-500/20">
        <div className="flex items-center gap-2 text-amber-400 font-bold text-[11px] uppercase tracking-wider">
          <AlertTriangle size={14} />
          Terminal Komutu Onayı
        </div>
        <button onClick={onCancel} className="text-slate-500 hover:text-white transition-colors">
          <X size={14} />
        </button>
      </div>

      <div className="p-4">
        <div className="flex items-start gap-3 mb-4">
          <div className="w-10 h-10 rounded-full bg-amber-500/20 flex items-center justify-center shrink-0">
            <Terminal size={20} className="text-amber-400" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-[13px] text-white font-medium leading-tight mb-2">
              Bu komutu çalıştırmak istediğine emin misin?
            </p>
            <div className="bg-black/50 rounded-lg px-3 py-2 border border-white/5">
              <code className="text-[11px] text-emerald-400 font-mono break-all leading-relaxed">
                <span className="text-slate-600 mr-1.5 select-none">$</span>
                {command}
              </code>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={onConfirm}
            className="flex-1 flex items-center justify-center gap-2 py-2 bg-amber-600 hover:bg-amber-500 text-white rounded-lg text-[12px] font-bold transition-all shadow-lg shadow-amber-900/20 active:scale-[0.98]"
          >
            <Check size={14} className="stroke-[3px]" />
            Komutu Çalıştır
          </button>
          <button
            onClick={onCancel}
            className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-[12px] font-bold transition-all"
          >
            İptal
          </button>
        </div>
      </div>

      <div className="px-4 py-2 bg-black/40 border-t border-amber-500/10">
        <p className="text-[10px] text-slate-600 italic">
          * Bu komut sisteminizde doğrudan çalıştırılacaktır.
        </p>
      </div>
    </motion.div>
  );
};
