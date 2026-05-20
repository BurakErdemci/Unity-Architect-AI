import React, { useEffect, useRef, useState, useCallback } from 'react';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css';
import axios from 'axios';
import {
  X, Maximize2, Minimize2, Trash2,
  Plus, ChevronRight, AlertCircle, Search,
  Info, AlertTriangle, WifiOff, RefreshCw
} from 'lucide-react';
import { motion } from 'framer-motion';

interface TerminalPanelProps {
  id: string;
  isOpen: boolean;
  onClose: () => void;
  workspacePath: string | null;
  problems?: any[];
  onProblemClick?: (problem: any) => void;
  apiUrl?: string;
  sessionToken?: string;
  unityConnected?: boolean;
}

const ipc = typeof window !== 'undefined' ? (window as any).ipc : null;

// ── Output Tab ────────────────────────────────────────────────────────────────
const OutputTab: React.FC<{ apiUrl?: string; sessionToken?: string }> = ({ apiUrl, sessionToken }) => {
  const [logs, setLogs] = useState<any[]>([]);
  const [since, setSince] = useState(0);
  const bottomRef = useRef<HTMLDivElement>(null);
  const autoScrollRef = useRef(true);

  useEffect(() => {
    if (!apiUrl || !sessionToken) return;
    const fetch = async () => {
      try {
        const res = await axios.get(`${apiUrl}/logs`, {
          params: { since },
          headers: { 'X-Session-Token': sessionToken }
        });
        const incoming = res.data.logs || [];
        if (incoming.length > 0) {
          setLogs(prev => [...prev.slice(-500), ...incoming]);
          setSince(incoming[incoming.length - 1].ts);
        }
      } catch { /* backend kapalı olabilir */ }
    };
    fetch();
    const interval = setInterval(fetch, 1500);
    return () => clearInterval(interval);
  }, [apiUrl, sessionToken, since]);

  useEffect(() => {
    if (autoScrollRef.current) bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  const levelColor = (level: string) => {
    if (level === 'ERROR') return 'text-red-400';
    if (level === 'WARNING') return 'text-amber-400';
    if (level === 'DEBUG') return 'text-slate-600';
    return 'text-slate-400';
  };

  return (
    <div className="flex-1 overflow-y-auto font-mono text-[11px] bg-[#0a0a0a] p-2 custom-scrollbar"
      onScroll={e => {
        const el = e.currentTarget;
        autoScrollRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
      }}>
      {logs.length === 0 ? (
        <div className="h-full flex items-center justify-center text-slate-700 text-xs">Backend logları bekleniyor...</div>
      ) : logs.map((log, i) => (
        <div key={i} className="flex gap-2 hover:bg-white/3 px-1 py-0.5 rounded leading-relaxed">
          <span className="text-slate-700 shrink-0 w-16">
            {new Date(log.ts * 1000).toLocaleTimeString('tr', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
          </span>
          <span className={`shrink-0 w-14 ${levelColor(log.level)}`}>{log.level}</span>
          <span className="text-slate-500 shrink-0 max-w-[120px] truncate">{log.logger}</span>
          <span className="text-slate-300 break-all">{log.message}</span>
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  );
};

// ── Debug Console Tab ─────────────────────────────────────────────────────────
const DebugConsoleTab: React.FC<{ apiUrl?: string; sessionToken?: string; unityConnected?: boolean }> = ({ apiUrl, sessionToken, unityConnected }) => {
  const [entries, setEntries] = useState<any[]>([]);
  const [filter, setFilter] = useState<'all' | 'log' | 'warning' | 'error'>('all');
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!apiUrl || !sessionToken || !unityConnected) return;
    const fetch = async () => {
      try {
        const res = await axios.get(`${apiUrl}/mcp/unity/console`, {
          headers: { 'X-Session-Token': sessionToken }
        });
        if (res.data.connected && Array.isArray(res.data.logs)) {
          setEntries(res.data.logs.slice(-200));
          bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
        }
      } catch { /* Unity bağlı değil */ }
    };
    fetch();
    const interval = setInterval(fetch, 3000);
    return () => clearInterval(interval);
  }, [apiUrl, sessionToken, unityConnected]);

  const filtered = filter === 'all' ? entries : entries.filter(e => {
    const t = (e.type || e.logType || '').toLowerCase();
    if (filter === 'error') return t.includes('error') || t.includes('exception');
    if (filter === 'warning') return t.includes('warn');
    return t === 'log' || t === 'info' || !t;
  });

  const iconFor = (type: string) => {
    const t = (type || '').toLowerCase();
    if (t.includes('error') || t.includes('exception')) return <AlertCircle size={12} className="text-red-400 shrink-0 mt-0.5" />;
    if (t.includes('warn')) return <AlertTriangle size={12} className="text-amber-400 shrink-0 mt-0.5" />;
    return <Info size={12} className="text-blue-400 shrink-0 mt-0.5" />;
  };

  return (
    <div className="flex-1 flex flex-col bg-[#0a0a0a] overflow-hidden">
      {!unityConnected && (
        <div className="mx-3 mt-3 p-3 rounded-lg bg-yellow-500/10 border border-yellow-500/20 flex items-start gap-2.5 text-yellow-300">
          <AlertTriangle size={14} className="shrink-0 mt-0.5" />
          <div className="flex flex-col gap-0.5">
            <span className="text-[11px] font-bold uppercase tracking-wider">Unity Bağlantısı Yok</span>
            <span className="text-[10px] text-slate-400">Unity MCP aktif değil. Canlı konsol akışını başlatmak için üst menüden Unity MCP bağlantısını açın.</span>
          </div>
        </div>
      )}
      <div className="flex items-center gap-1 px-3 py-1.5 border-b border-white/5 shrink-0">
        {(['all', 'log', 'warning', 'error'] as const).map(f => (
          <button key={f} onClick={() => setFilter(f)}
            className={`px-2 py-0.5 rounded text-[10px] font-medium uppercase tracking-wider transition-colors ${filter === f ? 'bg-blue-600/20 text-blue-300' : 'text-slate-600 hover:text-slate-400'}`}>
            {f}
          </button>
        ))}
        <span className="ml-auto text-[9px] text-slate-700">{filtered.length} giriş</span>
      </div>
      <div className="flex-1 overflow-y-auto font-mono text-[11px] p-2 custom-scrollbar">
        {filtered.length === 0 ? (
          <div className="h-full flex items-center justify-center text-slate-700 text-xs">Unity Console boş</div>
        ) : filtered.map((entry, i) => (
          <div key={i} className="flex gap-2 hover:bg-white/3 px-1 py-0.5 rounded leading-relaxed">
            {iconFor(entry.type || entry.logType || '')}
            <span className="text-slate-300 break-all">{entry.message || entry.text || JSON.stringify(entry)}</span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
};

// ── Ports Tab ─────────────────────────────────────────────────────────────────
const PortsTab: React.FC<{ apiUrl?: string; sessionToken?: string; unityConnected?: boolean }> = ({ apiUrl, sessionToken, unityConnected }) => {
  const [backendOk, setBackendOk] = useState<boolean | null>(null);
  const [mcpOk, setMcpOk] = useState<boolean | null>(null);

  const check = useCallback(async () => {
    try {
      await axios.get(`${apiUrl}/health`);
      setBackendOk(true);
    } catch { setBackendOk(false); }
    try {
      await axios.get('http://localhost:8080/health', { timeout: 1000 });
      setMcpOk(true);
    } catch { setMcpOk(false); }
  }, [apiUrl]);

  useEffect(() => { check(); }, [check]);

  const StatusDot = ({ ok }: { ok: boolean | null }) => (
    <div className={`w-2 h-2 rounded-full ${ok === null ? 'bg-slate-600' : ok ? 'bg-emerald-500 shadow-[0_0_6px_rgba(16,185,129,0.6)]' : 'bg-red-500'}`} />
  );

  const ports = [
    { name: 'Backend API', port: apiUrl ? new URL(apiUrl).port || '8000' : '8000', ok: backendOk, desc: 'FastAPI · Unity Architect AI' },
    { name: 'Unity MCP', port: '8080', ok: mcpOk, desc: 'MCP Server · Unity Editor bağlantısı' },
  ];

  return (
    <div className="flex-1 p-4 bg-[#0a0a0a] flex flex-col gap-2">
      <div className="flex items-center justify-between mb-1">
        <span className="text-[10px] text-slate-600 uppercase tracking-widest font-medium">Aktif Portlar</span>
        <button onClick={check} className="text-slate-600 hover:text-slate-400 transition-colors">
          <RefreshCw size={11} />
        </button>
      </div>
      {ports.map(p => (
        <div key={p.port} className="flex items-center gap-3 p-2.5 rounded-lg bg-white/3 border border-white/5">
          <StatusDot ok={p.ok} />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-semibold text-slate-300">{p.name}</span>
              <span className="text-[9px] px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-400 font-mono">:{p.port}</span>
            </div>
            <span className="text-[9px] text-slate-600">{p.desc}</span>
          </div>
          <span className={`text-[9px] font-bold uppercase ${p.ok === null ? 'text-slate-600' : p.ok ? 'text-emerald-500' : 'text-red-500'}`}>
            {p.ok === null ? 'Kontrol...' : p.ok ? 'Online' : 'Offline'}
          </span>
        </div>
      ))}
    </div>
  );
};

interface TerminalSession {
  id: string;
  name: string;
  cwd: string | null;
}

// ── Main TerminalPanel ────────────────────────────────────────────────────────
export const TerminalPanel: React.FC<TerminalPanelProps> = ({
  id, isOpen, onClose, workspacePath, problems = [], onProblemClick,
  apiUrl, sessionToken, unityConnected
}) => {
  const [isMaximized, setIsMaximized] = useState(false);
  const [terminalHeight, setTerminalHeight] = useState(320);
  const [sidebarWidth, setSidebarWidth] = useState(200);
  const [isResizingH, setIsResizingH] = useState(false);
  const [isResizingV, setIsResizingV] = useState(false);
  const [activeTab, setActiveTab] = useState('Terminal');

  // Multi-session Terminal State
  const [sessions, setSessions] = useState<TerminalSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string>('');

  const terminalRefs = useRef<{ [id: string]: HTMLDivElement | null }>({});
  const terminalInstancesRef = useRef<{ [id: string]: Terminal }>({});
  const fitAddonsRef = useRef<{ [id: string]: FitAddon }>({});
  const [initializedIds, setInitializedIds] = useState<Set<string>>(new Set());

  const startResizingV = (e: React.MouseEvent) => { e.preventDefault(); setIsResizingV(true); };
  const startResizingH = (e: React.MouseEvent) => { e.preventDefault(); setIsResizingH(true); };
  const stopResizing = useCallback(() => { setIsResizingV(false); setIsResizingH(false); }, []);

  const resize = useCallback((e: MouseEvent) => {
    if (isResizingV) {
      const h = window.innerHeight - e.clientY;
      if (h > 100 && h < window.innerHeight * 0.9) setTerminalHeight(h);
    }
    if (isResizingH) {
      const w = window.innerWidth - e.clientX;
      if (w > 100 && w < 500) setSidebarWidth(w);
    }
  }, [isResizingV, isResizingH]);

  useEffect(() => {
    window.addEventListener('mousemove', resize);
    window.addEventListener('mouseup', stopResizing);
    return () => { window.removeEventListener('mousemove', resize); window.removeEventListener('mouseup', stopResizing); };
  }, [resize, stopResizing]);

  // Default session initialization
  useEffect(() => {
    if (isOpen && sessions.length === 0) {
      const initialId = id || `term-${Date.now()}`;
      setSessions([
        { id: initialId, name: 'zsh', cwd: workspacePath }
      ]);
      setActiveSessionId(initialId);
    }
  }, [isOpen, workspacePath, sessions.length, id]);

  // Dynamic initialization for each session
  useEffect(() => {
    if (!isOpen || !ipc) return;

    sessions.forEach(session => {
      const { id: sId, cwd } = session;
      if (initializedIds.has(sId) || !terminalRefs.current[sId]) return;

      // Mark as initialized
      setInitializedIds(prev => {
        const next = new Set(prev);
        next.add(sId);
        return next;
      });

      const term = new Terminal({
        cursorBlink: true,
        fontSize: 13,
        fontFamily: 'Menlo, Monaco, "Courier New", monospace',
        theme: { background: '#0d0d0d', foreground: '#cccccc', cursor: '#3b82f6', selectionBackground: 'rgba(59,130,246,0.3)' },
        allowProposedApi: true,
        scrollback: 5000,
      });

      const fitAddon = new FitAddon();
      term.loadAddon(fitAddon);
      term.open(terminalRefs.current[sId]!);

      terminalInstancesRef.current[sId] = term;
      fitAddonsRef.current[sId] = fitAddon;

      // Spawn PTY process via Electron background helper
      ipc.invoke('terminal-spawn', { id: sId, cwd }).then((res: any) => {
        if (res.success) {
          ipc.invoke('terminal-write', { id: sId, data: '\r' });
        }
      });

      // IPC listeners
      const unsubscribeData = ipc.on(`terminal-data-${sId}`, (data: string) => {
        term.write(data);
      });

      term.onData((data) => {
        ipc.invoke('terminal-write', { id: sId, data });
      });

      const unsubscribeExit = ipc.on(`terminal-exit-${sId}`, () => {
        term.write('\r\n[İşlem sonlandırıldı]\r\n');
      });

      const handleResize = () => {
        try {
          fitAddon.fit();
          ipc.invoke('terminal-resize', { id: sId, cols: term.cols, rows: term.rows });
        } catch {}
      };

      // Store cleanup routines
      (term as any)._cleanups = [
        unsubscribeData,
        unsubscribeExit,
        () => {
          window.removeEventListener('resize', handleResize);
          term.dispose();
        }
      ];

      window.addEventListener('resize', handleResize);

      setTimeout(() => {
        try {
          fitAddon.fit();
          if (sId === activeSessionId) term.focus();
        } catch {}
      }, 150);
    });
  }, [sessions, initializedIds, isOpen, activeSessionId]);

  // Cleanup removed sessions
  useEffect(() => {
    const sessionIds = new Set(sessions.map(s => s.id));
    initializedIds.forEach(sId => {
      if (!sessionIds.has(sId)) {
        const term = terminalInstancesRef.current[sId];
        if (term) {
          if ((term as any)._cleanups) {
            (term as any)._cleanups.forEach((c: any) => c());
          }
          delete terminalInstancesRef.current[sId];
        }
        delete fitAddonsRef.current[sId];
        delete terminalRefs.current[sId];
        setInitializedIds(prev => {
          const next = new Set(prev);
          next.delete(sId);
          return next;
        });
      }
    });
  }, [sessions, initializedIds]);

  // Clean up all on unmount
  useEffect(() => {
    return () => {
      Object.keys(terminalInstancesRef.current).forEach(sId => {
        const term = terminalInstancesRef.current[sId];
        if (term) {
          if ((term as any)._cleanups) {
            (term as any)._cleanups.forEach((c: any) => c());
          }
        }
      });
      terminalInstancesRef.current = {};
      fitAddonsRef.current = {};
      terminalRefs.current = {};
    };
  }, []);

  // Layout resizing
  useEffect(() => {
    sessions.forEach(session => {
      const fitAddon = fitAddonsRef.current[session.id];
      if (fitAddon) {
        setTimeout(() => {
          try {
            fitAddon.fit();
          } catch {}
        }, 100);
      }
    });
  }, [terminalHeight, sidebarWidth, isMaximized, sessions]);

  // Active tab switching
  useEffect(() => {
    if (activeTab === 'Terminal' && activeSessionId && fitAddonsRef.current[activeSessionId]) {
      setTimeout(() => {
        try {
          fitAddonsRef.current[activeSessionId]?.fit();
          terminalInstancesRef.current[activeSessionId]?.focus();
        } catch {}
      }, 100);
    }
  }, [activeTab, activeSessionId]);

  const addSession = () => {
    const newId = `term-${Date.now()}`;
    const newSession = {
      id: newId,
      name: `zsh (${sessions.length + 1})`,
      cwd: workspacePath,
    };
    setSessions(prev => [...prev, newSession]);
    setActiveSessionId(newId);
    setActiveTab('Terminal');
  };

  const nextSession = () => {
    if (sessions.length <= 1) return;
    const currentIndex = sessions.findIndex(s => s.id === activeSessionId);
    const nextIndex = (currentIndex + 1) % sessions.length;
    const nextId = sessions[nextIndex].id;
    setActiveSessionId(nextId);
    setActiveTab('Terminal');
  };

  const removeSession = (sessionIdToRemove?: string) => {
    const targetId = sessionIdToRemove || activeSessionId;
    if (!targetId) return;

    // Send exit command to the terminal process
    ipc?.invoke('terminal-write', { id: targetId, data: 'exit\r' });

    setSessions(prev => {
      if (prev.length <= 1) {
        // Clear instead of removing if it's the last active session
        const term = terminalInstancesRef.current[targetId];
        term?.clear();
        return prev;
      }

      const filtered = prev.filter(s => s.id !== targetId);

      if (targetId === activeSessionId) {
        const deletedIndex = prev.findIndex(s => s.id === targetId);
        const newActiveIndex = deletedIndex === prev.length - 1 ? deletedIndex - 1 : deletedIndex;
        setTimeout(() => {
          setActiveSessionId(filtered[newActiveIndex].id);
        }, 0);
      }

      return filtered;
    });
  };

  if (!isOpen) return null;

  const tabs = ['Problems', 'Output', 'Debug Console', 'Terminal', 'Ports'];

  return (
    <motion.div
      initial={{ y: 400, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 400, opacity: 0 }}
      style={{ height: isMaximized ? '98vh' : `${terminalHeight}px` }}
      className="fixed bottom-0 left-0 right-0 z-[60] bg-[#0d0d0d] border-t border-white/5 flex flex-col shadow-[0_-20px_50px_-20px_rgba(0,0,0,0.8)]"
    >
      <div onMouseDown={startResizingV} className="absolute -top-1 left-0 right-0 h-2 cursor-ns-resize z-[70] hover:bg-blue-500/20 transition-colors" />

      {/* Header */}
      <div className="flex items-center justify-between px-4 h-9 bg-[#111111] border-b border-white/5 select-none shrink-0">
        <div className="flex items-center gap-6 h-full">
          {tabs.map(tab => (
            <button key={tab} onClick={() => setActiveTab(tab)}
              className={`h-full text-[11px] font-medium px-1 relative transition-colors ${activeTab === tab ? 'text-slate-200' : 'text-slate-500 hover:text-slate-300'}`}>
              {tab}
              {tab === 'Problems' && problems.length > 0 && (
                <span className="ml-1 text-[9px] px-1 py-0 rounded-full bg-red-500/20 text-red-400 font-bold">{problems.length}</span>
              )}
              {activeTab === tab && <div className="absolute bottom-0 left-0 right-0 h-[2px] bg-blue-500" />}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1 bg-white/5 rounded-md p-1 mr-2">
            <Plus size={12} className="text-slate-400 cursor-pointer hover:text-white" onClick={addSession} />
            <ChevronRight size={12} className="text-slate-400 cursor-pointer hover:text-white" onClick={nextSession} />
            <Trash2 size={12} className="text-slate-400 cursor-pointer hover:text-white" onClick={() => removeSession()} />
          </div>
          <button onClick={() => setIsMaximized(!isMaximized)} className="text-slate-500 hover:text-white">
            {isMaximized ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          </button>
          <button onClick={onClose} className="text-slate-500 hover:text-red-400"><X size={16} /></button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 flex overflow-hidden">
        <div className="flex-1 relative bg-black overflow-hidden flex flex-col">
          {sessions.map(session => (
            <div 
              key={session.id}
              className="flex-1 p-2 overflow-hidden flex flex-col" 
              style={{ display: (activeTab === 'Terminal' && activeSessionId === session.id) ? 'flex' : 'none' }}
              onClick={() => {
                terminalInstancesRef.current[session.id]?.focus();
              }}
            >
              <div ref={(el) => { terminalRefs.current[session.id] = el; }} className="w-full h-full" />
            </div>
          ))}

          {activeTab === 'Problems' && (
            <div className="flex-1 overflow-y-auto p-3 custom-scrollbar bg-[#0a0a0a]">
              {problems.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center text-slate-600 gap-2">
                  <Search size={28} strokeWidth={1.5} opacity={0.5} />
                  <span className="text-xs uppercase tracking-widest font-medium">No problems detected</span>
                </div>
              ) : (
                <div className="space-y-0.5">
                  {problems.map((prob, i) => (
                    <div key={i} onClick={() => onProblemClick?.(prob)}
                      className="flex items-start gap-3 p-2 rounded hover:bg-white/5 cursor-pointer border border-transparent hover:border-white/5 transition-all">
                      <AlertCircle size={13} className={`${prob.severity === 'error' ? 'text-red-500' : 'text-amber-500'} mt-0.5 shrink-0`} />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-[11px] font-semibold text-slate-200">{prob.message}</span>
                          {prob.file && <span className="text-[9px] px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-400 font-mono">{prob.file}</span>}
                        </div>
                        <div className="flex items-center gap-2 mt-0.5">
                          <span className="text-[10px] text-slate-500 font-mono">Ln {prob.line}, Col {prob.column}</span>
                          <span className="text-[9px] px-1 py-0 rounded bg-white/5 text-slate-600 uppercase tracking-tighter font-bold">C#</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
          {activeTab === 'Output' && <OutputTab apiUrl={apiUrl} sessionToken={sessionToken} />}
          {activeTab === 'Debug Console' && <DebugConsoleTab apiUrl={apiUrl} sessionToken={sessionToken} unityConnected={unityConnected} />}
          {activeTab === 'Ports' && <PortsTab apiUrl={apiUrl} sessionToken={sessionToken} unityConnected={unityConnected} />}
        </div>

        {/* Right Sidebar */}
        <div style={{ width: `${sidebarWidth}px` }}
          className="bg-[#111111] border-l border-white/5 flex flex-col relative shrink-0">
          <div onMouseDown={startResizingH} className="absolute top-0 bottom-0 -left-1 w-2 cursor-ew-resize z-[70] hover:bg-blue-500/10" />
          <div className="p-2 space-y-1 overflow-y-auto">
            {sessions.map((inst) => (
              <div 
                key={inst.id}
                onClick={() => {
                  setActiveSessionId(inst.id);
                  setActiveTab('Terminal');
                }}
                className={`group flex items-center gap-2 px-2 py-1.5 rounded text-[11px] cursor-pointer transition-colors ${activeSessionId === inst.id ? 'bg-blue-600/20 text-blue-400 border border-blue-500/20' : 'text-slate-500 hover:bg-white/5'}`}
              >
                <div className="w-3.5 h-3.5 rounded flex items-center justify-center text-[8px] font-bold bg-slate-700 text-slate-300">&gt;_</div>
                <span className="truncate flex-1 font-mono">{inst.name}</span>
                {activeSessionId === inst.id && <div className="w-1.5 h-1.5 rounded-full bg-blue-500 shadow-[0_0_6px_rgba(59,130,246,0.6)]" />}
                {sessions.length > 1 && (
                  <X
                    size={10}
                    className="opacity-0 group-hover:opacity-100 text-slate-500 hover:text-red-400 ml-1 transition-opacity cursor-pointer shrink-0"
                    onClick={(e) => {
                      e.stopPropagation();
                      removeSession(inst.id);
                    }}
                  />
                )}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="h-5 bg-[#0d0d0d] border-t border-white/5 flex items-center px-3 justify-between shrink-0">
        <div className="flex items-center gap-3 text-[9px] text-slate-600 uppercase tracking-widest">
          <div className="flex items-center gap-1.5">
            <div className={`w-1.5 h-1.5 rounded-full ${unityConnected ? 'bg-emerald-500' : 'bg-slate-700'}`} />
            <span>{unityConnected ? 'Unity Bağlı' : 'Unity Bağlı Değil'}</span>
          </div>
        </div>
        <span className="text-[9px] text-slate-700 font-mono">PTY v5.9</span>
      </div>
    </motion.div>
  );
};
