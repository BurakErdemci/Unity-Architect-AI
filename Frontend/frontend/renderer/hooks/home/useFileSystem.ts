import { useState, useCallback, useEffect } from 'react';
import axios from 'axios';
import { FileEntry, ExportModalState, UserData } from '../../components/home/types';
import { PendingFile } from '../../components/home/FileCreationApproval';
import { splitCodeIntoFiles } from '../../components/home/export-utils';

const ipc = typeof window !== 'undefined' ? (window as any).ipc : null;

export const useFileSystem = (API: string, user: UserData | null, showToast: (msg: string, type: any) => void) => {
  const [workspacePath, setWorkspacePath] = useState<string | null>(null);
  const [lastWorkspacePath, setLastWorkspacePath] = useState<string | null>(null);
  const [rootFolderPath, setRootFolderPath] = useState<string | null>(null);
  const [fileTree, setFileTree] = useState<FileEntry[]>([]);
  const [expandedDirs, setExpandedDirs] = useState<Set<string>>(new Set());
  const [dirContents, setDirContents] = useState<Record<string, FileEntry[]>>({});
  const [openedFilePath, setOpenedFilePath] = useState<string | null>(null);
  const [code, setCode] = useState('');
  const [originalCode, setOriginalCode] = useState('');
  const [isDirty, setIsDirty] = useState(false);
  
  // Track dirty state
  useEffect(() => {
    setIsDirty(code !== originalCode);
  }, [code, originalCode]);

  const saveFile = useCallback(async () => {
    if (!ipc || !openedFilePath || !workspacePath) return false;
    const res = await ipc.invoke('write-file', openedFilePath, code, workspacePath);
    if (res?.success) {
      setOriginalCode(code);
      setIsDirty(false);
      showToast('Dosya kaydedildi', 'success');
      return true;
    } else {
      showToast('Kaydetme hatası: ' + (res?.error || 'Bilinmiyor'), 'error');
      return false;
    }
  }, [code, openedFilePath, workspacePath, showToast]);

  const [treeContextMenu, setTreeContextMenu] = useState<{ x: number; y: number; entry: FileEntry } | null>(null);
  const [renamingPath, setRenamingPath] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const [treeCreating, setTreeCreating] = useState<{ parentPath: string; type: 'file' | 'folder' } | null>(null);
  const [treeCreateValue, setTreeCreateValue] = useState('');
  const [treeDragSource, setTreeDragSource] = useState<FileEntry | null>(null);
  const [treeDragTarget, setTreeDragTarget] = useState<string | null>(null);

  const [exportModal, setExportModal] = useState<ExportModalState | null>(null);
  const [exportFileName, setExportFileName] = useState('');
  
  // Pending Actions
  const [pendingGenFiles, setPendingGenFiles] = useState<{ files: PendingFile[]; messageId: number } | null>(null);
  const [pendingDelete, setPendingDelete] = useState<{ path: string; messageId: number } | null>(null);

  const fetchLastWorkspace = useCallback(async (userId: number) => {
    if (!API || !user?.sessionToken) return;
    try {
      const res = await axios.get(`${API}/last-workspace/${userId}`, {
        headers: { 'X-Session-Token': user.sessionToken }
      });
      if (res.data?.path) setLastWorkspacePath(res.data.path);
    } catch (err) { console.error("Last workspace hatası:", err); }
  }, [API, user]);

  const selectWorkspace = useCallback(async (path: string) => {
    setWorkspacePath(path);
    setRootFolderPath(path);
    if (ipc) {
      const entries = await ipc.invoke('read-directory', path, path);
      setFileTree(entries || []);
    }
    setExpandedDirs(new Set());
    setDirContents({});
    if (user?.sessionToken && API) {
      try {
        await axios.post(`${API}/save-workspace`, 
          { user_id: user.id, path },
          { headers: { 'X-Session-Token': user.sessionToken } }
        );
      } catch (err) { console.error("Workspace kaydetme hatası:", err); }
    }
  }, [API, user]);

  const refreshFileTree = useCallback(async () => {
    if (!ipc || !workspacePath) return;
    const entries = await ipc.invoke('read-directory', workspacePath, workspacePath);
    setFileTree(entries || []);
    const newDirContents = { ...dirContents };
    for (const dir of expandedDirs) {
      try {
        const dirEntries = await ipc.invoke('read-directory', dir, workspacePath);
        newDirContents[dir] = dirEntries || [];
      } catch { }
    }
    setDirContents(newDirContents);
  }, [dirContents, expandedDirs, workspacePath]);

  const openFolder = useCallback(async () => {
    if (!ipc) return;
    const folderPath = await ipc.invoke('open-folder-dialog');
    if (folderPath) await selectWorkspace(folderPath);
  }, [selectWorkspace]);

  const openFilePicker = useCallback(async () => {
    if (!ipc) return;
    const result = await ipc.invoke('open-file-dialog');
    if (result) {
      setCode(result.content);
      setOriginalCode(result.content);
      setOpenedFilePath(result.path);
    }
  }, []);

  const closeWorkspace = useCallback(() => {
    setWorkspacePath(null);
    setRootFolderPath(null);
    setFileTree([]);
    setExpandedDirs(new Set());
    setDirContents({});
    setOpenedFilePath(null);
    setCode('');
  }, []);

  const openFile = useCallback(async (filePath: string) => {
    if (!ipc) return;
    const result = await ipc.invoke('read-file', filePath, workspacePath);
    if (result) {
      setCode(result.content);
      setOriginalCode(result.content);
      setOpenedFilePath(result.path);
    }
  }, [workspacePath]);

  const toggleDir = useCallback(async (dirPath: string) => {
    const next = new Set(expandedDirs);
    if (next.has(dirPath)) {
      next.delete(dirPath);
    } else {
      next.add(dirPath);
      if (!dirContents[dirPath]) {
        const entries = await ipc.invoke('read-directory', dirPath, workspacePath);
        setDirContents(prev => ({ ...prev, [dirPath]: entries || [] }));
      }
    }
    setExpandedDirs(next);
  }, [dirContents, expandedDirs, workspacePath]);

  const handleTreeDelete = useCallback(async (entry: FileEntry) => {
    setTreeContextMenu(null);
    if (!window.confirm(`"${entry.name}" silinsin mi?`)) return;
    await ipc.invoke('delete-entry', entry.path, workspacePath);
    refreshFileTree();
  }, [refreshFileTree, workspacePath]);

  const submitRename = useCallback(async () => {
    if (!renamingPath || !renameValue.trim()) { setRenamingPath(null); return; }
    const res = await ipc.invoke('rename-entry', renamingPath, renameValue.trim(), workspacePath);
    setRenamingPath(null);
    if (res?.success) refreshFileTree();
  }, [refreshFileTree, renameValue, renamingPath, workspacePath]);

  const submitTreeCreate = useCallback(async () => {
    if (!treeCreating || !treeCreateValue.trim()) { setTreeCreating(null); return; }
    const { parentPath, type } = treeCreating;
    const newPath = `${parentPath}/${treeCreateValue.trim()}`;
    setTreeCreating(null);
    if (type === 'file') {
      await ipc.invoke('create-file', newPath, workspacePath);
    } else {
      await ipc.invoke('create-folder', newPath, workspacePath);
    }
    refreshFileTree();
  }, [refreshFileTree, treeCreateValue, treeCreating, workspacePath]);

  const suggestFilePath = useCallback((name: string) => {
    const ext = name.split('.').pop()?.toLowerCase();
    
    // Proje yapısını kontrol et: Script mi Scripts mi?
    let scriptDir = 'Scripts';
    if (dirContents['Assets/Script']) scriptDir = 'Script';
    else if (dirContents['Assets/Scripts']) scriptDir = 'Scripts';

    if (ext === 'cs') return `Assets/${scriptDir}/${name}`;
    if (ext === 'shader' || ext === 'compute' || ext === 'hlsl' || ext === 'cginc') return `Assets/Shaders/${name}`;
    if (ext === 'json' || ext === 'txt' || ext === 'md' || ext === 'xml') return `Assets/Resources/${name}`;
    return `Assets/${name}`;
  }, [dirContents]);

  const deleteFile = useCallback(async (relativePath: string) => {
    if (!ipc || !workspacePath) return;
    const res = await ipc.invoke('delete-file', relativePath, workspacePath);
    if (res.success) {
      showToast('Dosya silindi', 'success');
      refreshFileTree();
      if (openedFilePath === relativePath) {
        setOpenedFilePath(null);
        setCode('');
      }
    } else {
      showToast(`Silme hatası: ${res.error}`, 'error');
    }
  }, [ipc, workspacePath, showToast, refreshFileTree, openedFilePath]);

  const handleExportToUnity = useCallback(async (codeString: string) => {
    if (!workspacePath) return;
    const targetDir = `${workspacePath}/Assets/Scripts`;
    const classMatch = codeString.match(/class\s+(\w+)/);
    const suggestedName = `${classMatch ? classMatch[1] : 'NewScript'}.cs`;
    const allClasses = [...codeString.matchAll(/class\s+(\w+)/g)];

    if (allClasses.length > 1) {
      const files = splitCodeIntoFiles(codeString, workspacePath);
      setExportFileName(suggestedName);
      setExportModal({ isOpen: true, codeString, suggestedName, targetDir, existingFile: false, multiFile: true, files, exportResult: null });
    } else {
      const targetPath = `${targetDir}/${suggestedName}`;
      const exists = ipc ? await ipc.invoke('file-exists', targetPath, workspacePath) : false;
      setExportFileName(suggestedName);
      setExportModal({ isOpen: true, codeString, suggestedName, targetDir, existingFile: exists, multiFile: false, files: [{ name: suggestedName, code: codeString, path: targetPath }], exportResult: null });
    }
  }, [workspacePath]);

  const handleTreeDragStart = useCallback((e: React.DragEvent, entry: FileEntry) => {
    e.stopPropagation();
    setTreeDragSource(entry);
    e.dataTransfer.effectAllowed = 'copyMove';
    e.dataTransfer.setData('application/x-unity-architect-file', JSON.stringify(entry));
    e.dataTransfer.setData('text/plain', entry.path);
  }, []);

  const handleTreeDragOver = useCallback((e: React.DragEvent, entry: FileEntry) => {
    if (!treeDragSource || !entry.isDirectory) return;
    if (entry.path === treeDragSource.path || entry.path.startsWith(treeDragSource.path + '/')) return;
    e.preventDefault();
    e.stopPropagation();
    setTreeDragTarget(entry.path);
  }, [treeDragSource]);

  const handleTreeDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setTreeDragTarget(null);
  }, []);

  const handleTreeDrop = useCallback(async (e: React.DragEvent, targetEntry: FileEntry) => {
    e.preventDefault();
    e.stopPropagation();
    setTreeDragTarget(null);
    if (!treeDragSource || !targetEntry.isDirectory) return;
    if (targetEntry.path === treeDragSource.path || targetEntry.path.startsWith(treeDragSource.path + '/')) return;
    const sourceParent = treeDragSource.path.substring(0, treeDragSource.path.lastIndexOf('/'));
    if (sourceParent === targetEntry.path) { setTreeDragSource(null); return; }
    const res = await ipc?.invoke('move-entry', treeDragSource.path, targetEntry.path, workspacePath);
    setTreeDragSource(null);
    if (res?.success) refreshFileTree();
  }, [refreshFileTree, treeDragSource, workspacePath]);

  const handleTreeContextMenu = useCallback((e: React.MouseEvent, entry: FileEntry) => {
    e.preventDefault();
    e.stopPropagation();
    setTreeContextMenu({ x: e.clientX, y: e.clientY, entry });
  }, []);

  const startRename = useCallback((entry: FileEntry) => {
    setRenamingPath(entry.path);
    setRenameValue(entry.name);
    setTreeContextMenu(null);
  }, []);

  const startTreeCreate = useCallback((parentPath: string, type: 'file' | 'folder') => {
    setTreeContextMenu(null);
    setTreeCreating({ parentPath, type });
    setTreeCreateValue(type === 'file' ? 'NewScript.cs' : 'YeniKlasor');
    if (!expandedDirs.has(parentPath)) {
      setExpandedDirs(new Set([...expandedDirs, parentPath]));
    }
  }, [expandedDirs]);

  const changeExportDir = useCallback(async () => {
    if (!ipc || !exportModal) return;
    const newDir = await ipc.invoke('open-folder-dialog');
    if (newDir) setExportModal({ ...exportModal, targetDir: newDir });
  }, [exportModal]);

  const exportSingleFile = useCallback(async () => {
    if (!ipc || !workspacePath || !exportModal) return;
    const fileName = exportModal.suggestedName;
    const content = exportModal.codeString;
    const targetPath = `${exportModal.targetDir}/${fileName}`;
    const res = await ipc.invoke('write-file', targetPath, content, workspacePath);
    if (res?.success) {
      setExportModal({ ...exportModal, exportResult: { success: true, message: `Başarıyla dışa aktarıldı: ${fileName}` } });
      refreshFileTree();
      showToast('Dosya Unity\'ye aktarıldı.', 'success');
    } else {
      setExportModal({ ...exportModal, exportResult: { success: false, message: 'Dosya yazılamadı!' } });
    }
  }, [exportModal, refreshFileTree, showToast, workspacePath]);

  const exportMultipleFiles = useCallback(async () => {
    if (!ipc || !workspacePath || !exportModal) return;
    let successCount = 0;
    for (const f of exportModal.files) {
      const targetPath = `${exportModal.targetDir}/${f.name}`;
      const res = await ipc.invoke('write-file', targetPath, f.code, workspacePath);
      if (res?.success) successCount++;
    }
    setExportModal({ ...exportModal, exportResult: { success: true, message: `${successCount} dosya başarıyla dışa aktarıldı.` } });
    refreshFileTree();
    showToast(`${successCount} dosya Unity'ye aktarıldı.`, 'success');
  }, [exportModal, refreshFileTree, showToast, workspacePath]);

  return {
    workspacePath, lastWorkspacePath, fileTree, openedFilePath, code, setCode, setOpenedFilePath,
    isDirty, saveFile,
    fetchLastWorkspace, selectWorkspace, openFolder, closeWorkspace, openFile, refreshFileTree,
    openFilePicker, treeCreating, setTreeCreating, treeCreateValue, setTreeCreateValue,
    submitTreeCreate, expandedDirs, dirContents, toggleDir, treeDragSource, treeDragTarget,
    renamingPath, renameValue, setRenameValue, submitRename, setRenamingPath,
    handleTreeDragStart, handleTreeDragOver, handleTreeDragLeave, handleTreeDrop,
    handleTreeContextMenu, startRename, startTreeCreate, handleTreeDelete,
    treeContextMenu, setTreeContextMenu, exportModal, setExportModal, exportFileName,
    setExportFileName, changeExportDir, exportSingleFile, exportMultipleFiles,
    suggestFilePath, pendingGenFiles, setPendingGenFiles,
    pendingDelete, setPendingDelete, deleteFile, handleExportToUnity,
    rootFolderPath: workspacePath
  };
};
