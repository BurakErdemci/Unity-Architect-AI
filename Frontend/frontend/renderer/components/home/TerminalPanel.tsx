import React, { useEffect, useRef, useState, useCallback } from 'react';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css';
import { 
  X, Maximize2, Minimize2, Trash2, 
  Terminal as TerminalIcon, 
  Plus, ChevronRight, List,
  AlertCircle, Info, Search
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

interface TerminalPanelProps {
  id: string;
  isOpen: boolean;
  onClose: () => void;
  workspacePath: string | null;
  problems?: any[];
}

const ipc = typeof window !== 'undefined' ? (window as any).ipc : null;

export const TerminalPanel: React.FC<TerminalPanelProps> = ({ id, isOpen, onClose, workspacePath, problems = [] }) => {
  const terminalRef = useRef<HTMLDivElement>(null);
  const xtermRef = useRef<Terminal | null>(null);
  const fitAddonRef = useRef<FitAddon | null>(null);
  
  const [isMaximized, setIsMaximized] = useState(false);
  const [terminalHeight, setTerminalHeight] = useState(320);
  const [sidebarWidth, setSidebarWidth] = useState(200);
  const [isResizingH, setIsResizingH] = useState(false);
  const [isResizingV, setIsResizingV] = useState(false);
  const [activeTab, setActiveTab] = useState('Terminal');

  // --- Vertical Resize (Height) ---
  const startResizingV = (e: React.MouseEvent) => {
    e.preventDefault();
    setIsResizingV(true);
  };

  // --- Horizontal Resize (Sidebar Width) ---
  const startResizingH = (e: React.MouseEvent) => {
    e.preventDefault();
    setIsResizingH(true);
  };

  const stopResizing = useCallback(() => {
    setIsResizingV(false);
    setIsResizingH(false);
  }, []);

  const resize = useCallback((e: MouseEvent) => {
    if (isResizingV) {
      const newHeight = window.innerHeight - e.clientY;
      if (newHeight > 100 && newHeight < window.innerHeight * 0.9) setTerminalHeight(newHeight);
    }
    if (isResizingH) {
      const newWidth = window.innerWidth - e.clientX;
      if (newWidth > 100 && newWidth < 500) setSidebarWidth(newWidth);
    }
  }, [isResizingV, isResizingH]);

  useEffect(() => {
    window.addEventListener('mousemove', resize);
    window.addEventListener('mouseup', stopResizing);
    return () => {
      window.removeEventListener('mousemove', resize);
      window.removeEventListener('mouseup', stopResizing);
    };
  }, [resize, stopResizing]);

  useEffect(() => {
    if (!isOpen || !terminalRef.current || !ipc) return;

    const term = new Terminal({
      cursorBlink: true,
      fontSize: 13,
      fontFamily: 'Menlo, Monaco, "Courier New", monospace',
      theme: {
        background: '#0d0d0d',
        foreground: '#cccccc',
        cursor: '#3b82f6',
        selectionBackground: 'rgba(59, 130, 246, 0.3)',
      },
      allowProposedApi: true,
      scrollback: 5000,
    });

    const fitAddon = new FitAddon();
    term.loadAddon(fitAddon);
    term.open(terminalRef.current);
    
    setTimeout(() => {
      term.focus();
      fitAddon.fit();
    }, 150);

    xtermRef.current = term;
    fitAddonRef.current = fitAddon;

    // Connect to PTY
    ipc.invoke('terminal-spawn', { id, cwd: workspacePath }).then((res: any) => {
      if (res.success) {
        // Enforce prompt
        ipc.invoke('terminal-write', { id, data: '\r' });
      }
    });

    const unsubscribeData = ipc.on(`terminal-data-${id}`, (data: string) => {
      term.write(data);
    });

    term.onData((data) => {
      ipc.invoke('terminal-write', { id, data });
    });

    const handleResize = () => {
      fitAddon.fit();
      ipc.invoke('terminal-resize', { id, cols: term.cols, rows: term.rows });
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      unsubscribeData();
      term.dispose();
      xtermRef.current = null;
    };
  }, [isOpen, id, workspacePath]);

  // Handle auto-fit on size change
  useEffect(() => {
    if (fitAddonRef.current && xtermRef.current) {
      setTimeout(() => fitAddonRef.current?.fit(), 100);
    }
  }, [terminalHeight, sidebarWidth, isMaximized]);

  if (!isOpen) return null;

  const tabs = ['Problems', 'Output', 'Debug Console', 'Terminal', 'Ports'];
  const terminalInstances = [
    { name: 'zsh Frontend', active: false, icon: 'zsh' },
    { name: 'node frontend', active: false, icon: 'node' },
    { name: 'zsh backend', active: false, icon: 'zsh' },
    { name: 'zsh', active: true, icon: 'zsh' }
  ];

  return (
    <motion.div
      initial={{ y: 400, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      exit={{ y: 400, opacity: 0 }}
      style={{ height: isMaximized ? '98vh' : `${terminalHeight}px` }}
      className="fixed bottom-0 left-0 right-0 z-[60] bg-[#0d0d0d] border-t border-white/5 flex flex-col shadow-[0_-20px_50px_-20px_rgba(0,0,0,0.8)]"
    >
      {/* Top Resize Handle (Vertical) */}
      <div onMouseDown={startResizingV} className="absolute -top-1 left-0 right-0 h-2 cursor-ns-resize z-[70] hover:bg-blue-500/20 transition-colors" />

      {/* Header Tabs (VS Code Style) */}
      <div className="flex items-center justify-between px-4 h-9 bg-[#111111] border-b border-white/5 select-none shrink-0">
        <div className="flex items-center gap-6 h-full">
          {tabs.map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`h-full text-[11px] font-medium px-1 relative transition-colors ${
                activeTab === tab ? 'text-slate-200' : 'text-slate-500 hover:text-slate-300'
              }`}
            >
              {tab}
              {activeTab === tab && <div className="absolute bottom-0 left-0 right-0 h-[2px] bg-blue-500" />}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1 bg-white/5 rounded-md p-1 mr-2">
            <Plus size={12} className="text-slate-400 cursor-pointer hover:text-white" />
            <ChevronRight size={12} className="text-slate-400 cursor-pointer hover:text-white" />
            <Trash2 size={12} className="text-slate-400 cursor-pointer hover:text-white" onClick={() => xtermRef.current?.clear()} />
          </div>
          <button onClick={() => setIsMaximized(!isMaximized)} className="text-slate-500 hover:text-white">
            {isMaximized ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          </button>
          <button onClick={onClose} className="text-slate-500 hover:text-red-400">
            <X size={16} />
          </button>
        </div>
      </div>

      {/* Main Area */}
      <div className="flex-1 flex overflow-hidden">
        <div className="flex-1 relative bg-black overflow-hidden flex flex-col">
          {activeTab === 'Terminal' ? (
            <div className="flex-1 p-2 overflow-hidden" onClick={() => xtermRef.current?.focus()}>
              <div ref={terminalRef} className="w-full h-full" />
            </div>
          ) : activeTab === 'Problems' ? (
            <div className="flex-1 overflow-y-auto p-4 custom-scrollbar bg-[#0a0a0a]">
              {problems.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center text-slate-600 gap-2">
                  <Search size={32} strokeWidth={1.5} opacity={0.5} />
                  <span className="text-xs uppercase tracking-widest font-medium">No problems detected</span>
                </div>
              ) : (
                <div className="space-y-1">
                  {problems.map((prob, i) => (
                    <div key={i} className="flex items-start gap-3 p-2 rounded hover:bg-white/5 group cursor-pointer border border-transparent hover:border-white/5 transition-all">
                      <AlertCircle size={14} className={prob.severity === 'error' ? 'text-red-500 mt-0.5' : 'text-amber-500 mt-0.5'} />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-[11px] font-bold text-slate-200">{prob.message}</span>
                        </div>
                        <div className="flex items-center gap-2 mt-1">
                          <span className="text-[10px] text-slate-500 font-mono">Line {prob.line}, Col {prob.column}</span>
                          <span className="text-[9px] px-1.5 py-0.5 rounded bg-white/5 text-slate-600 uppercase tracking-tighter font-bold">C# COMPILER</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div className="flex-1 flex items-center justify-center text-slate-700 text-xs italic">
              {activeTab} content coming soon...
            </div>
          )}
        </div>

        {/* Right Sidebar (Terminal Tabs List) */}
        <div 
          style={{ width: `${sidebarWidth}px` }} 
          className="bg-[#111111] border-l border-white/5 flex flex-col relative shrink-0"
        >
          {/* Horizontal Resize Handle */}
          <div onMouseDown={startResizingH} className="absolute top-0 bottom-0 -left-1 w-2 cursor-ew-resize z-[70] hover:bg-blue-500/10" />
          
          <div className="p-2 space-y-1 overflow-y-auto">
            {terminalInstances.map((inst, i) => (
              <div 
                key={i}
                className={`flex items-center gap-2 px-2 py-1.5 rounded text-[11px] cursor-pointer transition-colors ${
                  inst.active ? 'bg-blue-600/20 text-blue-400 border border-blue-500/20' : 'text-slate-500 hover:bg-white/5'
                }`}
              >
                <div className={`w-3.5 h-3.5 rounded flex items-center justify-center text-[8px] font-bold ${
                  inst.icon === 'zsh' ? 'bg-slate-700 text-slate-300' : 'bg-green-700/50 text-green-300'
                }`}>
                  {inst.icon === 'zsh' ? '>_' : 'JS'}
                </div>
                <span className="truncate flex-1">{inst.name}</span>
                {inst.active && <div className="w-1.5 h-1.5 rounded-full bg-blue-500 shadow-[0_0_8px_rgba(59,130,246,0.6)]" />}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Footer / Status */}
      <div className="h-5 bg-[#0d0d0d] border-t border-white/5 flex items-center px-3 justify-between shrink-0">
        <div className="flex items-center gap-3 text-[9px] text-slate-600 uppercase tracking-widest">
          <div className="flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 rounded-full bg-emerald-500/40" />
            <span>Connected to PTY</span>
          </div>
          <span>zsh v5.9</span>
        </div>
        <span className="text-[9px] text-slate-700 font-mono">120x30</span>
      </div>
    </motion.div>
  );
};
