import path from 'path'
import fs from 'fs'
import os from 'os'
import net from 'net'
import { randomUUID } from 'crypto'
import { app, ipcMain, dialog, shell } from 'electron'
import serve from 'electron-serve'
import { createWindow } from './helpers'
import { spawn, ChildProcess } from 'child_process'
import axios from 'axios'
import { autoUpdater } from 'electron-updater'
import {
  isAllowedWorkspacePath,
  isAllowedWorkspaceReadFile,
  isAllowedWorkspaceWriteFile,
  TEXT_FILE_EXTENSIONS,
} from './helpers/file-security'
import * as pty from 'node-pty'

const localAppToken = randomUUID()

const isProd = process.env.NODE_ENV === 'production'
let pyBackendProcess: ChildProcess | null = null
let backendPort: number | null = null
const BACKEND_HOST = '127.0.0.1'

// --- DOSYA LOGLAMA (paketlenmiş app'te konsol görünmez) ---
// Logları hem temp hem userData altına yazar; başka PC'de teşhis için kalıcı.
const logFilePath = path.join(os.tmpdir(), 'unity-architect-ai.log')
function fileLog(level: string, args: any[]) {
  try {
    const line = `[${new Date().toISOString()}] [${level}] ` +
      args.map(a => (typeof a === 'string' ? a : (a instanceof Error ? `${a.message}\n${a.stack}` : (() => { try { return JSON.stringify(a) } catch { return String(a) } })()))).join(' ') + '\n'
    fs.appendFileSync(logFilePath, line)
  } catch { /* log yazılamadı, sessizce geç */ }
}
{
  const origLog = console.log.bind(console)
  const origErr = console.error.bind(console)
  const origWarn = console.warn.bind(console)
  console.log = (...a: any[]) => { fileLog('INFO', a); try { origLog(...a) } catch {} }
  console.error = (...a: any[]) => { fileLog('ERROR', a); try { origErr(...a) } catch {} }
  console.warn = (...a: any[]) => { fileLog('WARN', a); try { origWarn(...a) } catch {} }
  process.on('uncaughtException', (e) => fileLog('UNCAUGHT', [e]))
  process.on('unhandledRejection', (e) => fileLog('UNHANDLED_REJECTION', [e as any]))
  fileLog('INFO', [`=== APP BAŞLADI === isProd=${isProd} resourcesPath=${process.resourcesPath} platform=${process.platform}`])
}

// --- TERMINAL YÖNETİMİ ---
const ptyProcesses: Map<string, pty.IPty> = new Map();

ipcMain.handle('terminal-spawn', (event, { id, cwd }) => {
  const isWin = process.platform === 'win32';
  
  // Profesyonel Shell Tespiti
  let shell = isWin ? 'powershell.exe' : (process.env.SHELL || '/bin/zsh');
  
  if (!isWin && !shell.startsWith('/')) {
    const commonPaths = ['/bin/zsh', '/usr/bin/zsh', '/bin/bash', '/usr/bin/bash', '/bin/sh'];
    for (const p of commonPaths) {
      if (fs.existsSync(p)) { shell = p; break; }
    }
  }

  // CWD ve Env Hazırlığı — HOME Windows'ta yok, USERPROFILE/os.homedir()'a düş
  const homeDir = process.env.HOME || process.env.USERPROFILE || os.homedir();
  let finalCwd = cwd || homeDir || '.';
  if (typeof finalCwd === 'string' && finalCwd.startsWith('~')) {
    finalCwd = path.join(homeDir || '', finalCwd.slice(1));
  }
  if (finalCwd && !fs.existsSync(finalCwd)) finalCwd = homeDir || '.';

  console.log(`[Terminal] Profesyonel Başlatma: ${shell} @ ${finalCwd}`);

  try {
    // Windows'ta PowerShell kendi ortamını kurar; Unix env değişkenleri (LANG, SHELL,
    // USER...) yalnızca POSIX shell'ler için anlamlı. Windows'ta sadece PATH/HOME geçir.
    const ptyEnv: Record<string, string> = isWin
      ? { ...process.env as Record<string, string> }
      : {
          ...process.env as Record<string, string>,
          HOME:      process.env.HOME      || homeDir,
          USER:      process.env.USER      || os.userInfo().username,
          LOGNAME:   process.env.LOGNAME   || os.userInfo().username,
          SHELL:     shell,
          PATH:      process.env.PATH      || '/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin',
          LANG:      'en_US.UTF-8',
          TERM:      'xterm-256color',
          COLORTERM: 'truecolor',
        };
    const ptyProcess = pty.spawn(shell, [], {
      name: 'xterm-256color',
      cols: 80,
      rows: 24,
      cwd: finalCwd,
      env: ptyEnv,
    });

    ptyProcesses.set(id, ptyProcess);

    ptyProcess.onData((data) => {
      event.sender.send(`terminal-data-${id}`, data);
    });

    ptyProcess.onExit(({ exitCode, signal }) => {
      event.sender.send(`terminal-exit-${id}`, { exitCode, signal });
      ptyProcesses.delete(id);
    });

    return { success: true, shell };
  } catch (err: any) {
    console.error(`[Terminal] Başlatma Hatası:`, err);
    return { success: false, error: err.message, shell };
  }
});

ipcMain.handle('terminal-write', (_event, { id, data }) => {
  const ptyProcess = ptyProcesses.get(id);
  if (ptyProcess) {
    ptyProcess.write(data);
    return { success: true };
  }
  return { success: false, error: 'Terminal bulunamadı' };
});

ipcMain.handle('terminal-resize', (_event, { id, cols, rows }) => {
  const ptyProcess = ptyProcesses.get(id);
  if (ptyProcess) {
    ptyProcess.resize(cols, rows);
    return { success: true };
  }
  return { success: false, error: 'Terminal bulunamadı' };
});

function getBackendBaseUrl(): string {
  if (!backendPort) {
    throw new Error('Backend URL henüz hazır değil.')
  }
  return `http://${BACKEND_HOST}:${backendPort}`
}

if (isProd) {
  serve({ directory: 'app' })
} else {
  app.setPath('userData', `${app.getPath('userData')} (development)`)
}

// --- IPC: DOSYA İŞLEMLERİ ---
ipcMain.handle('open-file-dialog', async () => {
  const result = await dialog.showOpenDialog({
    properties: ['openFile'],
    filters: [
      { name: 'Kod ve Metin Dosyaları', extensions: ['cs', 'shader', 'json', 'txt', 'md', 'xml', 'yaml', 'yml', 'compute', 'asmdef', 'cginc', 'hlsl', 'uss', 'uxml'] }
    ]
  })
  if (result.canceled || result.filePaths.length === 0) return null
  const filePath = result.filePaths[0]
  const content = fs.readFileSync(filePath, 'utf-8')
  return { path: filePath, name: path.basename(filePath), content }
})

// Video için: içerik OKUNMAZ (video büyük) — sadece mutlak yol(lar) döner.
// Electron 34'te File.path kaldırıldığı için renderer yolu buradan alır.
ipcMain.handle('open-video-dialog', async () => {
  const result = await dialog.showOpenDialog({
    properties: ['openFile', 'multiSelections'],
    filters: [
      { name: 'Video', extensions: ['mp4', 'mov', 'mkv', 'webm', 'avi', 'm4v'] }
    ]
  })
  if (result.canceled || result.filePaths.length === 0) return null
  return result.filePaths.map(p => ({ path: p, name: path.basename(p) }))
})

ipcMain.handle('open-folder-dialog', async () => {
  const result = await dialog.showOpenDialog({
    properties: ['openDirectory']
  })
  if (result.canceled || result.filePaths.length === 0) return null
  return result.filePaths[0]
})

ipcMain.handle('save-file-dialog', async (_event, options) => {
  const result = await dialog.showSaveDialog(options)
  if (result.canceled) return null
  return result.filePath
})

// Hafıza export/import gibi kullanıcı-tetikli akışlar için atomik dialog+yazma/okuma.
// write-file kasıtlı olarak workspace .cs dosyalarına kısıtlı; bu handler kullanıcı
// dialog'dan onayladığı path'i doğrudan kullandığı için ayrı kanaldan gidiyor.
ipcMain.handle('export-text-file', async (_event, defaultName: string, content: string) => {
  const result = await dialog.showSaveDialog({
    title: 'Hafıza Kaydet',
    defaultPath: defaultName,
    filters: [{ name: 'Markdown', extensions: ['md'] }, { name: 'Text', extensions: ['txt'] }],
  })
  if (result.canceled || !result.filePath) return { success: false, canceled: true }
  try {
    fs.writeFileSync(result.filePath, content, 'utf-8')
    return { success: true, path: result.filePath }
  } catch (err: any) {
    return { success: false, error: err.message }
  }
})

ipcMain.handle('import-text-file', async (_event, options?: { filters?: { name: string; extensions: string[] }[] }) => {
  const result = await dialog.showOpenDialog({
    title: 'Hafıza Yükle',
    properties: ['openFile'],
    filters: options?.filters ?? [{ name: 'Markdown', extensions: ['md'] }, { name: 'Text', extensions: ['txt'] }],
  })
  if (result.canceled || !result.filePaths[0]) return { canceled: true, content: '' }
  try {
    const content = fs.readFileSync(result.filePaths[0], 'utf-8')
    return { canceled: false, content, path: result.filePaths[0] }
  } catch (err: any) {
    return { canceled: false, content: '', error: err.message }
  }
})

ipcMain.handle('read-directory', async (_event, dirPath: string, workspacePath?: string) => {
  try {
    if (!workspacePath) return [];
    const fullPath = path.isAbsolute(dirPath) ? dirPath : path.join(workspacePath, dirPath);
    if (!isAllowedWorkspacePath(fullPath, workspacePath)) {
      return []
    }
    const entries = fs.readdirSync(fullPath, { withFileTypes: true })
    const items = entries
      .filter(e => !e.name.startsWith('.'))
      .filter(e => e.isDirectory() || TEXT_FILE_EXTENSIONS.includes(path.extname(e.name).toLowerCase()))
      .map(e => ({
        name: e.name,
        path: path.join(fullPath, e.name),
        isDirectory: e.isDirectory(),
        extension: e.isDirectory() ? '' : path.extname(e.name).toLowerCase()
      }))
      .sort((a, b) => {
        if (a.isDirectory && !b.isDirectory) return -1
        if (!a.isDirectory && b.isDirectory) return 1
        return a.name.localeCompare(b.name)
      })
    return items
  } catch { return [] }
})

// VSCode tarzı git durum rozetleri: workspace bir git reposuysa değişen/yeni/
// silinen dosyaların mutlak-yol → durum haritasını döner (dosya ağacı boyar).
ipcMain.handle('git-status', async (_event, workspacePath?: string) => {
  const empty = { isRepo: false, files: {}, dirs: {} }
  try {
    if (!workspacePath || !fs.existsSync(workspacePath)) return empty
    const { execFile } = require('child_process') as typeof import('child_process')
    const run = (args: string[]) => new Promise<string>((resolve, reject) => {
      execFile('git', ['-C', workspacePath, ...args], {
        timeout: 8000, maxBuffer: 8 * 1024 * 1024, windowsHide: true,
      }, (err, stdout) => err ? reject(err) : resolve(stdout))
    })

    const toplevel = (await run(['rev-parse', '--show-toplevel'])).trim()
    if (!toplevel) return empty
    // -z: NUL ayraçlı (boşluklu/unicode yollar güvenli); untracked dosyalar tek tek
    const raw = await run(['status', '--porcelain', '-z', '--untracked-files=all'])

    const files: Record<string, string> = {}
    const dirs: Record<string, string> = {}
    const parts = raw.split('\0')
    let count = 0
    for (let i = 0; i < parts.length && count < 8000; i++) {
      const p = parts[i]
      if (p.length < 4) continue
      const xy = p.slice(0, 2)
      const rel = p.slice(3)
      if (!rel) continue
      // Rename kayıtlarında sonraki eleman ESKİ yoldur → atla
      if (xy[0] === 'R' || xy[0] === 'C') i++
      let status = 'modified'
      if (xy === '??') status = 'untracked'
      else if (xy.includes('D')) status = 'deleted'
      else if (xy.includes('A')) status = 'added'
      // Anahtarlar lowercase: renderer'daki entry.path ile sürücü-harfi/case
      // farklarından bağımsız eşleşme (renderer da lowercase ile arar).
      const abs = path.normalize(path.join(toplevel, rel)).toLowerCase()
      files[abs] = status
      count++
      // Üst klasörleri işaretle (workspace köküne kadar) — klasörde nokta rozeti.
      // Windows'ta sürücü harfi büyük/küçük gelebilir (C:\ vs c:\) → karşılaştırma
      // case-insensitive, anahtarlar orijinal (path.join ile aynı) case'te tutulur.
      let dir = path.dirname(abs)
      const rootLower = path.normalize(workspacePath).toLowerCase()
      while (dir.startsWith(rootLower) && !dirs[dir]) {
        dirs[dir] = 'contains'
        const parent = path.dirname(dir)
        if (parent === dir) break
        dir = parent
      }
    }
    return { isRepo: true, files, dirs }
  } catch {
    return empty // git yok / repo değil / timeout → rozetsiz devam
  }
})

ipcMain.handle('read-file', async (_event, filePath: string, workspacePath?: string) => {
  try {
    if (!workspacePath) return null;
    const fullPath = path.isAbsolute(filePath) ? filePath : path.join(workspacePath, filePath);
    if (!isAllowedWorkspaceReadFile(fullPath, workspacePath)) {
      return null
    }
    const content = fs.readFileSync(fullPath, 'utf-8')
    return { path: fullPath, name: path.basename(fullPath), content }
  } catch { return null }
})

ipcMain.handle('write-file', async (_event, filePath: string, content: string, workspacePath?: string) => {
  try {
    const isAbsolute = path.isAbsolute(filePath);

    if (!workspacePath && !isAbsolute) return { success: false, error: 'Workspace path eksik.' };

    const fullPath = isAbsolute ? filePath : path.join(workspacePath!, filePath);

    if (!isAllowedWorkspaceWriteFile(fullPath, workspacePath || "")) {
      return { success: false, error: 'Dosya yalnızca seçili workspace içindeki kod/metin dosyalarına yazılabilir (.cs için Assets/Scripts altı).' }
    }
    const dir = path.dirname(fullPath)
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true })
    }
    fs.writeFileSync(fullPath, content, 'utf-8')
    return { success: true, path: fullPath }
  } catch (err: any) {
    return { success: false, error: err.message }
  }
})

ipcMain.handle('file-exists', async (_event, filePath: string, workspacePath?: string) => {
  if (!workspacePath) return false;
  const fullPath = path.isAbsolute(filePath) ? filePath : path.join(workspacePath, filePath);
  if (!isAllowedWorkspaceWriteFile(fullPath, workspacePath)) {
    return false
  }
  return fs.existsSync(fullPath)
})

ipcMain.handle('write-multiple-files', async (_event, files: { path: string; content: string }[], workspacePath?: string) => {
  const results: { path: string; success: boolean; error?: string }[] = []
  if (!workspacePath) return results;

  for (const file of files) {
    try {
      const fullPath = path.isAbsolute(file.path) ? file.path : path.join(workspacePath, file.path);
      if (!isAllowedWorkspaceWriteFile(fullPath, workspacePath)) {
        results.push({ path: fullPath, success: false, error: 'Dosya yalnızca seçili workspace içindeki kod/metin dosyalarına yazılabilir (.cs için Assets/Scripts altı).' })
        continue
      }
      const dir = path.dirname(fullPath)
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true })
      }
      fs.writeFileSync(fullPath, file.content, 'utf-8')
      results.push({ path: fullPath, success: true })
    } catch (err: any) {
      results.push({ path: file.path, success: false, error: err.message })
    }
  }
  return results
})

// --- IPC: DOSYA YÖNETİMİ ---
ipcMain.handle('create-file', async (_event, filePath: string, workspacePath?: string) => {
  if (!workspacePath) return { success: false, error: 'Workspace path eksik.' }
  const fullPath = path.isAbsolute(filePath) ? filePath : path.join(workspacePath, filePath)
  if (!isAllowedWorkspacePath(fullPath, workspacePath)) return { success: false, error: 'Dosya workspace dışında.' }
  if (fs.existsSync(fullPath)) return { success: false, error: 'Dosya zaten var.' }
  fs.mkdirSync(path.dirname(fullPath), { recursive: true })
  fs.writeFileSync(fullPath, '', 'utf-8')
  return { success: true, path: fullPath }
})

ipcMain.handle('delete-file', async (_event, relativePath: string, workspacePath?: string) => {
  try {
    if (!workspacePath) return { success: false, error: 'Workspace path eksik.' };
    const fullPath = path.isAbsolute(relativePath) ? relativePath : path.join(workspacePath, relativePath);
    if (!isAllowedWorkspacePath(fullPath, workspacePath)) {
      return { success: false, error: 'Dosya workspace dışında.' };
    }
    const exists = fs.existsSync(fullPath);
    if (exists) {
      fs.unlinkSync(fullPath);
      return { success: true };
    }
    return { success: false, error: 'Dosya bulunamadı' };
  } catch (err: any) {
    return { success: false, error: err.message };
  }
});

ipcMain.handle('create-folder', async (_event, folderPath: string, workspacePath?: string) => {
  if (!workspacePath) return { success: false, error: 'Workspace path eksik.' }
  const fullPath = path.isAbsolute(folderPath) ? folderPath : path.join(workspacePath, folderPath)
  if (!isAllowedWorkspacePath(fullPath, workspacePath)) return { success: false, error: 'Klasör workspace dışında.' }
  if (fs.existsSync(fullPath)) return { success: false, error: 'Klasör zaten var.' }
  fs.mkdirSync(fullPath, { recursive: true })
  return { success: true, path: fullPath }
})

ipcMain.handle('rename-entry', async (_event, oldPath: string, newName: string, workspacePath?: string) => {
  if (!workspacePath) return { success: false, error: 'Workspace path eksik.' }
  const fullOldPath = path.isAbsolute(oldPath) ? oldPath : path.join(workspacePath, oldPath)
  if (!isAllowedWorkspacePath(fullOldPath, workspacePath)) return { success: false, error: 'Dosya workspace dışında.' }
  if (!fs.existsSync(fullOldPath)) return { success: false, error: 'Dosya bulunamadı.' }
  const newPath = path.join(path.dirname(fullOldPath), newName)
  if (fs.existsSync(newPath)) return { success: false, error: 'Bu isimde bir dosya zaten var.' }
  fs.renameSync(fullOldPath, newPath)
  return { success: true, newPath }
})

ipcMain.handle('delete-entry', async (_event, entryPath: string, workspacePath?: string) => {
  if (!workspacePath) return { success: false, error: 'Workspace path eksik.' }
  const fullPath = path.isAbsolute(entryPath) ? entryPath : path.join(workspacePath, entryPath)
  if (!isAllowedWorkspacePath(fullPath, workspacePath)) return { success: false, error: 'Dosya workspace dışında.' }
  if (!fs.existsSync(fullPath)) return { success: false, error: 'Dosya bulunamadı.' }
  fs.rmSync(fullPath, { recursive: true, force: true })
  return { success: true }
})

ipcMain.handle('move-entry', async (_event, sourcePath: string, targetDir: string, workspacePath?: string) => {
  if (!workspacePath) return { success: false, error: 'Workspace path eksik.' }
  const fullSource = path.isAbsolute(sourcePath) ? sourcePath : path.join(workspacePath, sourcePath)
  const fullTarget = path.isAbsolute(targetDir) ? targetDir : path.join(workspacePath, targetDir)
  if (!isAllowedWorkspacePath(fullSource, workspacePath) || !isAllowedWorkspacePath(fullTarget, workspacePath)) {
    return { success: false, error: 'Dosya workspace dışında.' }
  }
  const newPath = path.join(fullTarget, path.basename(fullSource))
  if (fs.existsSync(newPath)) return { success: false, error: 'Hedef konumda aynı isimde bir dosya var.' }
  fs.renameSync(fullSource, newPath)
  return { success: true, newPath }
})

// Bir klasörün hâlâ var olup olmadığını kontrol eder (workspace silinmiş mi?).
ipcMain.handle('path-exists', async (_event, targetPath: string) => {
  try {
    if (!targetPath) return false
    return fs.existsSync(targetPath) && fs.statSync(targetPath).isDirectory()
  } catch {
    return false
  }
})

ipcMain.handle('app-token-get', () => localAppToken)
ipcMain.handle('get-backend-base-url', () => getBackendBaseUrl())

function findAvailablePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = net.createServer()
    server.listen(0, BACKEND_HOST, () => {
      const address = server.address()
      if (!address || typeof address === 'string') {
        server.close(() => reject(new Error('Boş port bulunamadı.')))
        return
      }

      const selectedPort = address.port
      server.close((error) => {
        if (error) {
          reject(error)
          return
        }
        resolve(selectedPort)
      })
    })
    server.on('error', reject)
  })
}

async function waitForBackendHealth(timeoutMs: number): Promise<void> {
  const interval = 500
  const maxAttempts = timeoutMs / interval

  for (let i = 0; i < maxAttempts; i++) {
    try {
      const response = await axios.get(`${getBackendBaseUrl()}/health`, { timeout: interval })
      if (response.data?.status === 'ok' && response.data?.service === 'unity-architect-ai') {
        console.log(`--- BACKEND HAZIR (${(i * interval / 1000).toFixed(1)}s) ${getBackendBaseUrl()} ---`)
        return
      }
    } catch {
      // backend henüz hazır değil
    }

    await new Promise(resolve => setTimeout(resolve, interval))
  }

  throw new Error(`Backend ${timeoutMs}ms içinde hazır olmadı.`)
}

// --- BACKEND YOLLARINI BUL ---
function getBackendPaths(): { pythonExec: string; pythonScript: string; backendDir: string; sitePackages: string } {
  const isWin = process.platform === 'win32'

  if (isProd) {
    // PyInstaller ile derlenmiş tek binary — Python kurulu olmasına gerek yok
    const resourcesPath = process.resourcesPath
    const backendDir = path.join(resourcesPath, 'Backend')
    const backendExec = isWin ? 'backend.exe' : 'backend'
    const pythonExec = path.join(backendDir, backendExec)
    // pythonScript boş: binary doğrudan çalıştırılır, script argümanı gerekmez
    return { pythonExec, pythonScript: '', backendDir, sitePackages: '' }
  } else {
    const appPath = app.getAppPath()
    const projectRoot = path.resolve(appPath, '..', '..')
    const backendDir = path.join(projectRoot, 'Backend')
    const pythonExec = isWin
      ? path.join(backendDir, 'venv', 'Scripts', 'python.exe')
      : path.join(backendDir, 'venv', 'bin', 'python3')
    const pythonScript = path.join(backendDir, 'app', 'main.py')
    return { pythonExec, pythonScript, backendDir, sitePackages: '' }
  }
}

// --- BACKEND BAŞLATMA ---
async function startPythonBackend() {
  // Docker modu: Python spawn etme, doğrudan Docker backend'e bağlan
  if (process.env.USE_DOCKER_BACKEND === 'true') {
    const dockerPort = parseInt(process.env.DOCKER_BACKEND_PORT || '8000', 10)
    console.log(`--- DOCKER BACKEND MODU: port ${dockerPort} ---`)
    backendPort = dockerPort
    await waitForBackendHealth(30000)
    return
  }

  // Port'u geçici değişkende tut — sağlıklı başlarsa backendPort'a yaz
  const selectedPort = await findAvailablePort()
  console.log(`--- BACKEND İÇİN PORT SEÇİLDİ: ${selectedPort} ---`)

  const { pythonExec, pythonScript, backendDir } = getBackendPaths()

  if (pythonScript) {
    // Dev modu: python script'i kontrol et
    if (!fs.existsSync(pythonScript)) {
      throw new Error(`Backend script bulunamadı: ${pythonScript}`)
    }
    if (!fs.existsSync(pythonExec)) {
      throw new Error(`Python bulunamadı: ${pythonExec}`)
    }
  } else {
    // Prod modu: PyInstaller binary'sini kontrol et
    if (!fs.existsSync(pythonExec)) {
      throw new Error(`Backend binary bulunamadı: ${pythonExec}`)
    }
  }

  const spawnArgs = pythonScript ? [pythonScript] : []
  console.log(`--- BACKEND BAŞLATILIYOR: ${pythonExec} ${spawnArgs.join(' ')} ---`)
  console.log(`--- BACKEND CWD: ${backendDir} ---`)

  // Port'u şimdi yaz ki waitForBackendHealth kullanabilsin
  backendPort = selectedPort

  pyBackendProcess = spawn(pythonExec, spawnArgs, {
    stdio: ['ignore', 'pipe', 'pipe'],
    cwd: backendDir,
    detached: false, // process group ile başlat — kapanırken tüm child'lar ölsün
    env: { ...process.env, PYTHONUNBUFFERED: '1', PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8', PORT: String(selectedPort), LOCAL_APP_TOKEN: localAppToken },
  });

  const safeLog = (...args: any[]) => { try { console.log(...args) } catch { /* EIO — socket kapandı */ } }
  const safeErr = (...args: any[]) => { try { console.error(...args) } catch { /* EIO — socket kapandı */ } }

  pyBackendProcess.stdout?.on('data', (data) => {
    safeLog(`[Backend] ${data.toString().trim()}`)
  })
  pyBackendProcess.stderr?.on('data', (data) => {
    safeErr(`[Backend] ${data.toString().trim()}`)
  })
  pyBackendProcess.on('error', (err) => {
    safeErr('Backend başlatılamadı:', err)
  })
  pyBackendProcess.on('exit', (code) => {
    safeLog(`--- BACKEND KAPANDI (exit code: ${code}) ---`)
  })

  try {
    await waitForBackendHealth(30000)
  } catch (err) {
    // Sağlık kontrolü başarısız — port'u sıfırla, pencere yine de açılacak
    backendPort = null
    pyBackendProcess?.kill()
    pyBackendProcess = null
    throw err
  }
}

// --- TEK INSTANCE KİLİDİ (Nextron çift restart'ı önler) ---
const gotTheLock = app.requestSingleInstanceLock()

if (!gotTheLock) {
  console.log('--- BAŞKA BİR INSTANCE ZATEN ÇALIŞIYOR, ÇIKILIYOR ---')
  app.quit()
} else {
  app.on('second-instance', () => {
    const allWindows = require('electron').BrowserWindow.getAllWindows()
    if (allWindows.length > 0) {
      const win = allWindows[0]
      if (win.isMinimized()) win.restore()
      win.focus()
    }
  })

    ; (async () => {
      await app.whenReady()

      // Windows görev çubuğu ikonu: AppUserModelId set edilmezse taskbar default
      // Electron ikonunu gösterir (window/exe ikonundan bağımsız). appId ile eşle.
      if (process.platform === 'win32') {
        app.setAppUserModelId('com.unityarchitect.ai')
      }

      try {
        await startPythonBackend()
      } catch (err) {
        console.error('--- BACKEND BAŞLATILAMADI, PENCERE YINE DE AÇILIYOR ---', err)
        backendPort = null
      }

      // Pencere ikonu: prod'da paketlenmiş resources/icon.ico, dev'de proje resources'ı.
      // (Set edilmezse dev'de + bazı Windows durumlarında eski Electron ikonu görünür.)
      const iconPath = isProd
        ? path.join(process.resourcesPath, 'icon.ico')
        : path.join(__dirname, '..', 'resources', 'icon.ico')

      const mainWindow = createWindow('main', {
        width: 1280,
        height: 850,
        icon: iconPath,
        webPreferences: {
          preload: path.join(__dirname, 'preload.js'),
        },
      })

      if (isProd) {
        await mainWindow.loadURL('app://./home')
      } else {
        const port = process.argv[2]
        const maxRetries = 5
        for (let i = 0; i < maxRetries; i++) {
          try {
            await mainWindow.loadURL(`http://localhost:${port}/home`)
            break
          } catch (err) {
            console.log(`--- SAYFA YÜKLENEMEDI (deneme ${i + 1}/${maxRetries}), 1sn bekleniyor... ---`)
            if (i === maxRetries - 1) {
              console.error('--- SAYFA YÜKLENEMEDI, son deneme de başarısız ---')
            }
            await new Promise(resolve => setTimeout(resolve, 1000))
          }
        }
      }

      // --- GLOBAL MENÜ TASARIMI ---
      const { Menu, MenuItem } = require('electron');
      const template: any[] = [
        ...(process.platform === 'darwin' ? [{
          label: app.name,
          submenu: [
            { role: 'about' },
            { type: 'separator' },
            { role: 'services' },
            { type: 'separator' },
            { role: 'hide' },
            { role: 'hideOthers' },
            { role: 'unhide' },
            { type: 'separator' },
            { role: 'quit' }
          ]
        }] : []),
        {
          label: 'File',
          submenu: [
            isProd ? { role: 'quit' } : { role: 'close' }
          ]
        },
        {
          label: 'Edit',
          submenu: [
            { role: 'undo' },
            { role: 'redo' },
            { type: 'separator' },
            { role: 'cut' },
            { role: 'copy' },
            { role: 'paste' },
            { role: 'selectAll' }
          ]
        },
        {
          label: 'Terminal',
          submenu: [
            {
              label: 'Toggle Terminal',
              accelerator: 'Control+`',
              click: () => {
                mainWindow.webContents.send('menu-toggle-terminal');
              }
            },
            {
              label: 'New Terminal',
              accelerator: 'CmdOrCtrl+Shift+`',
              click: () => {
                mainWindow.webContents.send('menu-open-terminal');
              }
            },
            { type: 'separator' },
            {
              label: 'Clear Terminal',
              click: () => {
                mainWindow.webContents.send('menu-clear-terminal');
              }
            }
          ]
        },
        {
          label: 'View',
          submenu: [
            { role: 'reload' },
            { role: 'forceReload' },
            { role: 'toggleDevTools' },
            { type: 'separator' },
            { role: 'resetZoom' },
            { role: 'zoomIn' },
            { role: 'zoomOut' },
            { type: 'separator' },
            { role: 'togglefullscreen' }
          ]
        },
        {
          role: 'window',
          submenu: [
            { role: 'minimize' },
            { role: 'close' }
          ]
        }
      ];

      const menu = Menu.buildFromTemplate(template);
      Menu.setApplicationMenu(menu);

      // --- GÜNCELLEME KONTROLÜ (BİLDİR-ONLY, electron-updater → GitHub Releases) ---
      // GÜVENLİK: Sessiz otomatik indirme/kurulum YOK. App yalnızca yeni sürümü tespit
      // edip kullanıcıya haber verir ve resmi release sayfasını açar — kurulumu kullanıcı
      // bilerek yapar (OS SmartScreen/Gatekeeper devrede). Böylece GitHub hesabı ele
      // geçse bile kimsenin makinesinde otomatik kod çalışmaz. Public repo → token gerekmez.
      if (isProd) {
        autoUpdater.autoDownload = false
        autoUpdater.autoInstallOnAppQuit = false
        autoUpdater.on('error', (err) => console.error('[updater] hata:', err?.message || err))
        autoUpdater.on('update-not-available', () => console.log('[updater] uygulama güncel'))
        autoUpdater.on('update-available', async (info) => {
          console.log('[updater] yeni sürüm mevcut:', info?.version)
          try {
            const { response } = await dialog.showMessageBox({
              type: 'info',
              buttons: ['İndirme sayfasını aç', 'Sonra'],
              defaultId: 0,
              cancelId: 1,
              title: 'Güncelleme mevcut',
              message: `Yeni sürüm çıktı: v${info?.version}`,
              detail: 'Resmi indirme sayfasını açmak için "İndirme sayfasını aç"a bas. ' +
                'Kurulumu sen onaylayacaksın — otomatik/sessiz kurulum yapılmaz.',
            })
            if (response === 0) {
              await shell.openExternal('https://github.com/BurakErdemci/Unity-Architect-AI/releases/latest')
            }
          } catch (e) { console.error('[updater] bildirim hatası:', (e as any)?.message || e) }
        })
        autoUpdater.checkForUpdates().catch((e) => console.error('[updater] kontrol başarısız:', e?.message || e))
      }
    })()

  const killBackend = () => {
    if (pyBackendProcess) {
      const pid = pyBackendProcess.pid
      if (process.platform === 'win32' && pid) {
        // Windows: negatif PID (process group) yok — taskkill /T tüm child ağacını öldürür
        // (PyInstaller bootloader + uvicorn worker'ları dahil). Aksi halde orphan kalır.
        try {
          spawn('taskkill', ['/pid', String(pid), '/T', '/F'], { stdio: 'ignore' })
        } catch {
          try { pyBackendProcess.kill() } catch { /* zaten ölmüş */ }
        }
      } else {
        // POSIX: tüm process grubunu öldür (uvicorn reload child'ları dahil)
        try {
          process.kill(-pid!, 'SIGKILL')
        } catch {
          pyBackendProcess.kill('SIGKILL')
        }
      }
      pyBackendProcess = null
    }
  }

  app.on('window-all-closed', () => {
    killBackend()
    app.quit()
  })

  app.on('before-quit', () => {
    killBackend()
  })

  // Beklenmedik çıkışlarda da temizle
  process.on('exit', killBackend)
  process.on('SIGTERM', () => { killBackend(); process.exit(0) })
}
