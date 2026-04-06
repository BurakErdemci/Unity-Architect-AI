import Head from "next/head";
import { ChevronRight, Clock, FolderOpen, LogOut } from "lucide-react";
import { motion } from "framer-motion";


interface WorkspaceScreenProps {
  userName: string;
  lastWorkspacePath: string | null;
  onOpenWorkspaceDialog: () => Promise<void>;
  onSelectLastWorkspace: () => Promise<void>;
  onLogout: () => void;
}


export const WorkspaceScreen = ({
  userName,
  lastWorkspacePath,
  onOpenWorkspaceDialog,
  onSelectLastWorkspace,
  onLogout,
}: WorkspaceScreenProps) => (
  <div className="h-screen flex items-center justify-center bg-[#000000] text-white">
    <Head><title>Unity Architect AI | Workspace</title></Head>
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-[#000000] p-10 rounded-2xl border border-slate-800/60 w-[480px] shadow-2xl"
    >
      <div className="flex flex-col items-center gap-4 mb-8 text-center">
        <div className="bg-gradient-to-br from-blue-600 to-violet-600 p-4 rounded-2xl shadow-lg shadow-blue-900/30">
          <FolderOpen size={36} />
        </div>
        <div>
          <h1 className="text-xl font-extrabold tracking-tight">
            Hoş geldin, <span className="text-blue-500">{userName}</span>
          </h1>
          <p className="text-slate-500 text-[11px] font-medium mt-1">
            Başlamak için çalışma alanını seç
          </p>
        </div>
      </div>

      <div className="space-y-3">
        <button
          onClick={onOpenWorkspaceDialog}
          className="w-full flex items-center justify-center gap-2.5 bg-blue-600 hover:bg-blue-500 text-white p-4 rounded-xl font-bold text-sm tracking-wide transition-all active:scale-[0.98]"
        >
          <FolderOpen size={18} />
          Klasör Seç
        </button>

        {lastWorkspacePath && (
          <button
            onClick={onSelectLastWorkspace}
            className="w-full flex items-center gap-3 bg-[#000000] hover:bg-slate-800/60 border border-slate-800 p-4 rounded-xl transition-all group"
          >
            <div className="bg-slate-800 p-2 rounded-lg group-hover:bg-blue-600/20 transition-colors">
              <Clock size={16} className="text-slate-400 group-hover:text-blue-400" />
            </div>
            <div className="text-left flex-1 min-w-0">
              <p className="text-[10px] text-slate-500 font-semibold uppercase tracking-wider">Son Açılan</p>
              <p className="text-[12px] text-slate-300 font-medium truncate mt-0.5">
                {lastWorkspacePath.split('/').slice(-2).join('/')}
              </p>
            </div>
            <ChevronRight size={14} className="text-slate-600 group-hover:text-blue-400" />
          </button>
        )}

        <button
          onClick={onLogout}
          className="w-full flex items-center justify-center gap-2 text-[11px] font-medium text-slate-500 hover:text-red-400 transition-colors py-3 mt-2"
        >
          <LogOut size={13} />
          Çıkış Yap
        </button>
      </div>
    </motion.div>
  </div>
);
