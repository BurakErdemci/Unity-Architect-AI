import React from 'react';
import { motion } from 'framer-motion';
import { Terminal, Check, X, AlertCircle } from 'lucide-react';

interface CommandApprovalProps {
  command: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export const CommandApproval: React.FC<CommandApprovalProps> = ({ command, onConfirm, onCancel }) => {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="my-3 overflow-hidden rounded-xl border border-blue-500/30 bg-blue-950/10 backdrop-blur-sm"
    >
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-blue-500/20 bg-blue-500/5">
        <Terminal size={14} className="text-blue-400" />
        <span className="text-[11px] font-bold text-blue-300 uppercase tracking-widest">Terminal Komutu Onayı</span>
      </div>
      
      <div className="p-4">
        <div className="bg-black/40 rounded-lg p-3 border border-white/5 mb-4 group relative">
          <code className="text-[12px] text-emerald-400 font-mono break-all leading-relaxed">
            <span className="text-slate-500 mr-2">$</span>
            {command}
          </code>
        </div>
        
        <div className="flex items-center gap-3 text-[11px] text-slate-400 mb-4 bg-orange-500/5 border border-orange-500/10 rounded-lg p-2.5">
          <AlertCircle size={14} className="text-orange-500 shrink-0" />
          <p>Bu komut sisteminizde doğrudan çalıştırılacaktır. Lütfen güvenliğinden emin olun.</p>
        </div>

        <div className="flex gap-2">
          <button
            onClick={onConfirm}
            className="flex-1 flex items-center justify-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-[12px] font-semibold transition-all active:scale-95 shadow-lg shadow-blue-600/20"
          >
            <Check size={14} />
            Komutu Çalıştır
          </button>
          <button
            onClick={onCancel}
            className="flex items-center justify-center gap-1.5 px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-[12px] font-semibold transition-all active:scale-95"
          >
            <X size={14} />
            İptal
          </button>
        </div>
      </div>
    </motion.div>
  );
};
