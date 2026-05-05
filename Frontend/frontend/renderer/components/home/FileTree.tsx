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
}

export const FileTree: React.FC<FileTreeProps> = (props) => {
  const {
    entries, depth = 0, openedFilePath, expandedDirs, dirContents,
    toggleDir, openFile, treeDragSource, treeDragTarget,
    renamingPath, renameValue, setRenameValue, submitRename, setRenamingPath,
    handleTreeDragStart, handleTreeDragOver, handleTreeDragLeave, handleTreeDrop,
    handleTreeContextMenu, startTreeCreate, startRename, handleTreeDelete,
    treeCreating, treeCreateValue, setTreeCreateValue, submitTreeCreate, setTreeCreating
  } = props;

  const getFileIcon = (ext: string) => {
    const e = ext.toLowerCase();
    if (e === '.cs') return <FileCode size={13} className="text-blue-400" />;
    if (e === '.prefab') return <Database size={13} className="text-orange-400" />;
    if (e === '.unity') return <Sparkles size={13} className="text-emerald-400" />;
    if (e === '.asset') return <Settings size={13} className="text-purple-400" />;
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
              <span className="truncate flex-1">{entry.name}</span>
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
