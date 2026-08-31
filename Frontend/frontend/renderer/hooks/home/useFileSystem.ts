import { useState, useCallback, useEffect, useRef } from 'react';
import axios from 'axios';
import { FileEntry, ExportModalState, UserData } from '../../components/home/types';
import { PendingFile } from '../../components/home/FileCreationApproval';
import { splitCodeIntoFiles } from '../../components/home/export-utils';
import { confirmDialog } from '../../components/ui/ConfirmDialog';
import { cevir } from '../../lib/i18n';
import { backendWorkspacePath, hostWorkspacePath } from '../../lib/backendWorkspacePath';

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
  // The editor and the 3D preview share one content area, so at most one of
  // `openedFilePath` / `previewFile` may be set. The invariant lives here
  // because both are written here.
  const [previewFile, setPreviewFile] = useState<{ path: string; name: string } | null>(null);

  const openPreview = useCallback((filePath: string) => {
    setOpenedFilePath(null);
    setCode('');
    setOriginalCode('');
    setPreviewFile({ path: filePath, name: filePath.split(/[\\/]/).pop() || filePath });
  }, []);

  const closePreview = useCallback(() => setPreviewFile(null), []);

  // VSCode tarzı git rozetleri: mutlak yol → durum (modified/added/untracked/deleted)
  const [gitStatus, setGitStatus] = useState<{ isRepo: boolean; files: Record<string, string>; dirs: Record<string, string> }>({ isRepo: false, files: {}, dirs: {} });
  const refreshGitStatus = useCallback(async (ws?: string | null) => {
    const target = ws ?? workspacePath;
    if (!ipc || !target) return;
    try {
      const res = await ipc.invoke('git-status', target);
      setGitStatus(res || { isRepo: false, files: {}, dirs: {} });
    } catch { /* best-effort */ }
  }, [workspacePath]);

  // Periyodik tazeleme (20 sn) — dışarıda (IDE/terminal) yapılan değişiklikler de yansısın
  useEffect(() => {
    if (!workspacePath) { setGitStatus({ isRepo: false, files: {}, dirs: {} }); return; }
    refreshGitStatus(workspacePath);
    const iv = setInterval(() => refreshGitStatus(workspacePath), 20000);
    return () => clearInterval(iv);
  }, [workspacePath, refreshGitStatus]);
  
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
      showToast(cevir('file.saved'), 'success');
      return true;
    } else {
      showToast(cevir('file.saveError', { hata: res?.error || cevir('common.unknown') }), 'error');
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
  const [pendingDelete, _setPendingDelete] = useState<{ path: string; messageId: number } | null>(null);
  // Tek slot, ama istek TEK gelmiyor: paralel araç çağrılarında ikinci silme
  // isteği birincinin kartını ekrandan siliyordu ve birinci cevapsız kalıp
  // zaman aşımına düşüyordu (30 Ağu 2026 denetimi; komut ve soru kartlarında
  // aynı kuyruk zaten vardı, yalnız silmede yoktu).
  const pendingDeleteQueueRef = useRef<Array<{ path: string; messageId: number }>>([]);

  const setPendingDelete = useCallback((val: { path: string; messageId: number } | null) => {
    _setPendingDelete(prev => {
      // null = karar verildi (onay ya da iptal) → sıradakini göster
      if (val === null) return pendingDeleteQueueRef.current.shift() || null;
      if (prev) { pendingDeleteQueueRef.current.push(val); return prev; }
      return val;
    });
  }, []);

  const fetchLastWorkspace = useCallback(async (userId: number) => {
    if (!API || !user?.sessionToken) return;
    try {
      const res = await axios.get(`${API}/last-workspace/${userId}`, {
        headers: { 'X-Session-Token': user.sessionToken }
      });
      const stored = res.data?.path;
      if (stored) {
        const host = await hostWorkspacePath(stored);
        if (host) setLastWorkspacePath(host);
      }
    } catch (err) { console.error("Last workspace hatası:", err); }
  }, [API, user]);

  // The workspace the user last ASKED for. Every step of `selectWorkspace`
  // awaits something (existence check, directory read, host→backend mapping),
  // so two selections overlap freely: auto-restore starts one while the user
  // picks another, and a slow first mapping made the slower selection the LAST
  // writer — the database left on A while the UI showed B, with no error on
  // either side. Keying each awaited result to the path it was computed for is
  // the same guard `useMCPApproval` uses for its mapped workspace.
  const selectionRef = useRef<string | null>(null);

  const selectWorkspace = useCallback(async (path: string) => {
    selectionRef.current = path;
    const gecerliMi = () => selectionRef.current === path;
    // Klasör hâlâ var mı? (silinmiş/taşınmış workspace'i otomatik yüklemeyi engelle)
    if (ipc) {
      const exists = await ipc.invoke('path-exists', path);
      if (!gecerliMi()) return;
      if (!exists) {
        showToast(cevir('workspace.missing'), 'warning');
        // Geçersiz yolu temizle ki bir daha otomatik yüklenmeye çalışılmasın
        setLastWorkspacePath(null);
        setWorkspacePath(null);
        return;
      }
    }
    setWorkspacePath(path);
    setRootFolderPath(path);
    if (ipc) {
      const entries = await ipc.invoke('read-directory', path, path);
      if (!gecerliMi()) return;
      setFileTree(entries || []);
    }
    setExpandedDirs(new Set());
    setDirContents({});
    if (user?.sessionToken && API) {
      const backendPath = await backendWorkspacePath(path);
      // A mapping that arrives after the user moved on describes a workspace
      // nobody is in: neither the warning nor the write belongs to it.
      if (!gecerliMi()) return;
      // null = Docker modu bu klasörü backend'e ADLANDIRAMIYOR (mount dışında).
      // Eski yolu göndermek, düzenleyicinin bir projede, ajanların başka bir
      // projede çalışması demekti — ikisi de başarılı görünerek.
      if (backendPath === null) {
        showToast(cevir('workspace.outsideDockerMount'), 'warning');
      } else {
        try {
          await axios.post(`${API}/save-workspace`,
            { user_id: user.id, path: backendPath },
            { headers: { 'X-Session-Token': user.sessionToken } }
          );
        } catch (err) { console.error("Workspace kaydetme hatası:", err); }
      }
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
    refreshGitStatus(workspacePath);
  }, [dirContents, expandedDirs, workspacePath, refreshGitStatus]);

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
      setPreviewFile(null);
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
    setPreviewFile(null);
  }, []);

  const openFile = useCallback(async (filePath: string) => {
    if (!ipc) return;
    const result = await ipc.invoke('read-file', filePath, workspacePath);
    if (result?.error === 'unsupported') {
      showToast(cevir('file.unsupported'), 'warning');
      return;
    }
    if (result?.error === 'too-large') {
      showToast(cevir('file.tooLarge'), 'warning');
      return;
    }
    if (result && result.content != null) {
      setCode(result.content);
      setOriginalCode(result.content);
      setOpenedFilePath(result.path);
      setPreviewFile(null);
      return;
    }
    // ⚠️ Bu dal eskiden SESSİZDİ ve bu bir arıza sınıfıydı: ana süreçteki
    // handler her hatada `null` dönüyor (dosya yok, workspace dışı, okuma
    // hatası, workspace hiç seçilmemiş — hepsi aynı `null`). Dosya ağacından
    // tıklandığında bu nadirdi, ama sohbetteki bir dosya LİNKİ artık buraya
    // düşebiliyor: model olmayan ya da workspace dışında bir yol yazabilir.
    // Sessiz dönmek, kullanıcıya tıkladığı şeyin bozuk olduğunu değil
    // uygulamanın bozuk olduğunu düşündürür.
    //
    // Sebebi ayırt edemiyoruz (handler tek bir `null` döndürüyor, bunu
    // değiştirmek onay/güvenlik yüzeyine dokunan ayrı bir iş), o yüzden mesaj
    // TAHMİN ETMİYOR — ne bilmediğimizi söylüyor ve yolu gösteriyor ki
    // kullanıcı kendisi karar verebilsin.
    showToast(cevir('file.openFailed', { yol: filePath }), 'warning');
  }, [workspacePath, showToast]);

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
    if (!(await confirmDialog(cevir('file.deleteConfirm', { ad: entry.name })))) return;
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
      showToast(cevir('file.deleted'), 'success');
      refreshFileTree();
      if (openedFilePath === relativePath) {
        setOpenedFilePath(null);
        setCode('');
      }
    } else {
      showToast(cevir('file.deleteError', { hata: res.error }), 'error');
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
    e.dataTransfer.setData('application/x-gamachine-file', JSON.stringify(entry));
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
      setExportModal({ ...exportModal, exportResult: { success: true, message: cevir('export.fileDone', { ad: fileName }) } });
      refreshFileTree();
      showToast(cevir('export.toUnity'), 'success');
    } else {
      setExportModal({ ...exportModal, exportResult: { success: false, message: cevir('export.writeFailed') } });
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
    setExportModal({ ...exportModal, exportResult: { success: true, message: cevir('export.multiDone', { sayi: successCount }) } });
    refreshFileTree();
    showToast(cevir('export.multiToUnity', { sayi: successCount }), 'success');
  }, [exportModal, refreshFileTree, showToast, workspacePath]);

  return {
    workspacePath, lastWorkspacePath, fileTree, openedFilePath, code, setCode, setOpenedFilePath,
    isDirty, saveFile, previewFile, openPreview, closePreview,
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
    gitStatus, refreshGitStatus,
    rootFolderPath: workspacePath
  };
};
