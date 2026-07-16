import React from 'react';
import { 
  Folder, 
  FolderOpen, 
  FileCode, 
  Database, 
  Sparkles, 
  Settings, 
  File as FileIcon, 
  ChevronRight as ChevronR, 
  Plus, 
  FolderPlus, 
  Pencil, 
  Trash2 
} from "lucide-react";
import { FileEntry } from './types';

interface FileTreeProps {
  entries: FileEntry[];
  depth?: number;
  openedFilePath: string | null;
  expandedDirs: Set<string>;
  dirContents: Record<string, FileEntry[]>;
  toggleDir: (path: string) => void;
  openFile: (path: string) => void;
  treeDragSource: FileEntry | null;
  treeDragTarget: string | null;
  renamingPath: string | null;
  renameValue: string;
  setRenameValue: (val: string) => void;
  submitRename: () => void;
  setRenamingPath: (path: string | null) => void;
  handleTreeDragStart: (e: React.DragEvent, entry: FileEntry) => void;
  handleTreeDragOver: (e: React.DragEvent, entry: FileEntry) => void;
  handleTreeDragLeave: (e: React.DragEvent) => void;
  handleTreeDrop: (e: React.DragEvent, entry: FileEntry) => void;
  handleTreeContextMenu: (e: React.MouseEvent, entry: FileEntry) => void;
  startTreeCreate: (parentPath: string, type: 'file' | 'folder') => void;
  startRename: (entry: FileEntry) => void;
  handleTreeDelete: (entry: FileEntry) => void;
  treeCreating: { parentPath: string; type: 'file' | 'folder' } | null;
  treeCreateValue: string;
  setTreeCreateValue: (val: string) => void;
  submitTreeCreate: () => void;
  setTreeCreating: (val: any) => void;
  gitStatus?: { isRepo: boolean; files: Record<string, string>; dirs: Record<string, string> };
}

// VSCode renkleri: modified sarı, untracked/added yeşil, deleted kırmızı
const GIT_BADGE: Record<string, { letter: string; text: string }> = {
  modified:  { letter: 'M', text: 'text-[#E2C08D]' },
  untracked: { letter: 'U', text: 'text-[#73C991]' },
  added:     { letter: 'A', text: 'text-[#73C991]' },
  deleted:   { letter: 'D', text: 'text-[#F14C4C]' },
};

export const FileTree: React.FC<FileTreeProps> = (props) => {
  const {
    entries, depth = 0, openedFilePath, expandedDirs, dirContents,
    toggleDir, openFile, treeDragSource, treeDragTarget,
    renamingPath, renameValue, setRenameValue, submitRename, setRenamingPath,
    handleTreeDragStart, handleTreeDragOver, handleTreeDragLeave, handleTreeDrop,
    handleTreeContextMenu, startTreeCreate, startRename, handleTreeDelete,
    treeCreating, treeCreateValue, setTreeCreateValue, submitTreeCreate, setTreeCreating,
    gitStatus
  } = props;

  // Girdinin git durumu: dosya → files haritasından; klasör → içinde değişiklik
  // varsa 'contains' (nokta rozeti). Harita anahtarları LOWERCASE tutulur
  // (Windows sürücü-harfi/case farkları), arama da lowercase yapılır.
  const gitInfo = (entry: FileEntry): string | null => {
    if (!gitStatus?.isRepo) return null;
    const key = entry.path.toLowerCase();
    if (!entry.isDirectory) return gitStatus.files[key] || null;
    return gitStatus.dirs[key] ? 'contains' : null;
  };

  const getFileIcon = (ext: string) => {
    const e = ext.toLowerCase();
    if (e === '.cs') return <FileCode size={13} className="text-blue-400" />;
    if (e === '.prefab') return <Database size={13} className="text-orange-400" />;
    if (e === '.unity') return <Sparkles size={13} className="text-emerald-400" />;
    if (['.asset', '.preset', '.spriteatlas', '.terrainlayer'].includes(e)) return <Settings size={13} className="text-purple-400" />;
    if (['.anim', '.controller', '.overridecontroller', '.playable', '.mask'].includes(e)) return <Sparkles size={13} className="text-pink-400" />;
    if (['.mat', '.physicmaterial', '.physicsmaterial2d', '.flare', '.rendertexture'].includes(e)) return <Database size={13} className="text-cyan-400" />;
    if (['.shader', '.hlsl', '.cginc', '.compute', '.shadervariants'].includes(e)) return <FileCode size={13} className="text-fuchsia-400" />;
    if (['.png', '.jpg', '.jpeg', '.tga', '.psd', '.tif', '.tiff', '.exr', '.hdr', '.gif', '.bmp'].includes(e)) return <FileIcon size={13} className="text-amber-400/70" />;
    if (['.fbx', '.obj', '.blend', '.dae', '.3ds'].includes(e)) return <Database size={13} className="text-indigo-400/70" />;
    if (['.wav', '.mp3', '.ogg', '.aiff', '.flac'].includes(e)) return <FileIcon size={13} className="text-rose-400/70" />;
    if (['.json', '.txt', '.md'].includes(e)) return <FileIcon size={13} className="text-slate-400" />;
    return <FileIcon size={13} className="text-slate-500" />;
  };

  return (
    <>
      {entries.map(entry => (
        <div
          key={entry.path}
          onDragOver={(e) => handleTreeDragOver(e, entry)}
          onDragLeave={handleTreeDragLeave}
          onDrop={(e) => handleTreeDrop(e, entry)}
          className={treeDragTarget === entry.path ? 'bg-blue-600/20 rounded' : ''}
        >
          {renamingPath === entry.path ? (
            <div className="flex items-center gap-1.5 py-[3px]" style={{ paddingLeft: `${8 + depth * 14}px`, paddingRight: '4px' }}>
              {entry.isDirectory ? <Folder size={13} className="text-blue-400 shrink-0" /> : getFileIcon(entry.extension)}
              <input
                autoFocus value={renameValue} onChange={e => setRenameValue(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') submitRename(); if (e.key === 'Escape') setRenamingPath(null); }}
                onBlur={() => setRenamingPath(null)}
                className="flex-1 bg-slate-800 text-white text-[12px] px-1.5 py-0.5 rounded border border-blue-500 outline-none min-w-0"
              />
            </div>
          ) : (
            <div
              draggable onDragStart={(e) => handleTreeDragStart(e, entry)}
              onClick={() => entry.isDirectory ? toggleDir(entry.path) : openFile(entry.path)}
              onContextMenu={(e) => handleTreeContextMenu(e, entry)}
              className={`flex items-center gap-1.5 py-[3px] rounded cursor-pointer text-[12px] hover:bg-slate-800/40 transition-colors group select-none ${
                openedFilePath === entry.path ? 'bg-slate-800/60 text-white' : 'text-slate-400'
              } ${treeDragSource?.path === entry.path ? 'opacity-40' : ''}`}
              style={{ paddingLeft: `${8 + depth * 14}px`, paddingRight: '4px' }}
            >
              {entry.isDirectory ? (
                <>
                  <ChevronR size={11} className={`transition-transform shrink-0 ${expandedDirs.has(entry.path) ? 'rotate-90' : ''}`} />
                  {expandedDirs.has(entry.path) ? <FolderOpen size={13} className="text-blue-400 shrink-0" /> : <Folder size={13} className="text-slate-500 shrink-0" />}
                </>
              ) : <span className="w-[11px] shrink-0" />}
              {!entry.isDirectory && getFileIcon(entry.extension)}
              {(() => {
                const gs = gitInfo(entry);
                const badge = gs && gs !== 'contains' ? GIT_BADGE[gs] : null;
                return (
                  <>
                    <span className={`truncate flex-1 ${badge ? badge.text : ''} ${gs === 'deleted' ? 'line-through opacity-70' : ''}`}>
                      {entry.name}
                    </span>
                    {badge && (
                      <span className={`${badge.text} text-[10px] font-bold shrink-0 pr-1 group-hover:hidden`} title={gs === 'untracked' ? 'Yeni (untracked)' : gs === 'modified' ? 'Değiştirildi' : gs === 'added' ? 'Eklendi (staged)' : 'Silindi'}>
                        {badge.letter}
                      </span>
                    )}
                    {gs === 'contains' && (
                      <span className="text-[#E2C08D] text-[9px] shrink-0 pr-1.5 group-hover:hidden" title="Bu klasörde değişiklik var">●</span>
                    )}
                  </>
                );
              })()}
              <span className="hidden group-hover:flex items-center gap-0.5 ml-auto shrink-0">
                {entry.isDirectory && (
                  <>
                    <button onClick={(e) => { e.stopPropagation(); startTreeCreate(entry.path, 'file'); }} className="p-0.5 hover:text-white text-slate-600 rounded"><Plus size={10} /></button>
                    <button onClick={(e) => { e.stopPropagation(); startTreeCreate(entry.path, 'folder'); }} className="p-0.5 hover:text-white text-slate-600 rounded"><FolderPlus size={10} /></button>
                  </>
                )}
                <button onClick={(e) => { e.stopPropagation(); startRename(entry); }} className="p-0.5 hover:text-white text-slate-600 rounded"><Pencil size={10} /></button>
                <button onClick={(e) => { e.stopPropagation(); handleTreeDelete(entry); }} className="p-0.5 hover:text-red-400 text-slate-600 rounded"><Trash2 size={10} /></button>
              </span>
            </div>
          )}
          {entry.isDirectory && expandedDirs.has(entry.path) && (
            <div>
              {treeCreating?.parentPath === entry.path && (
                <div className="flex items-center gap-1.5 py-[3px]" style={{ paddingLeft: `${8 + (depth + 1) * 14}px`, paddingRight: '4px' }}>
                  {treeCreating.type === 'file' ? <FileCode size={13} className="text-blue-400 shrink-0" /> : <Folder size={13} className="text-emerald-400 shrink-0" />}
                  <input autoFocus value={treeCreateValue} onChange={e => setTreeCreateValue(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') submitTreeCreate(); if (e.key === 'Escape') setTreeCreating(null); }} onBlur={() => setTreeCreating(null)} className="flex-1 bg-slate-800 text-white text-[12px] px-1.5 py-0.5 rounded border border-emerald-500 outline-none min-w-0" />
                </div>
              )}
              {dirContents[entry.path] && <FileTree {...props} entries={dirContents[entry.path]} depth={depth + 1} />}
            </div>
          )}
        </div>
      ))}
    </>
  );
};
