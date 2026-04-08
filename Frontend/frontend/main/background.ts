import path from 'path'
import fs from 'fs'
import { app, ipcMain, dialog } from 'electron'
import serve from 'electron-serve'
import { createWindow } from './helpers'
import { spawn, ChildProcess } from 'child_process'
import axios from 'axios'

const isProd = process.env.NODE_ENV === 'production'
let pyBackendProcess: ChildProcess | null = null

function isAllowedUnityScriptPath(filePath: string, workspacePath: string): boolean {
  try {
    const resolvedFile = path.resolve(filePath)
    const resolvedWorkspace = path.resolve(workspacePath)
    const relativePath = path.relative(resolvedWorkspace, resolvedFile)

    if (!relativePath || relativePath.startsWith('..') || path.isAbsolute(relativePath)) {
      return false
    }

    const parts = relativePath.split(path.sep)
    if (parts.length < 3) return false
    if (parts[0] !== 'Assets' || parts[1] !== 'Scripts') return false
    if (path.extname(resolvedFile).toLowerCase() !== '.cs') return false

    return true
  } catch {
    return false
  }
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
      { name: 'C# Dosyaları', extensions: ['cs'] }
    ]
  })
  if (result.canceled || result.filePaths.length === 0) return null
  const filePath = result.filePaths[0]
  const content = fs.readFileSync(filePath, 'utf-8')
  return { path: filePath, name: path.basename(filePath), content }
})

ipcMain.handle('open-folder-dialog', async () => {
  const result = await dialog.showOpenDialog({
    properties: ['openDirectory']
  })
  if (result.canceled || result.filePaths.length === 0) return null
  return result.filePaths[0]
})

ipcMain.handle('read-directory', async (_event, dirPath: string) => {
  try {
    const entries = fs.readdirSync(dirPath, { withFileTypes: true })
    const items = entries
      .filter(e => !e.name.startsWith('.'))
      .filter(e => e.isDirectory() || path.extname(e.name).toLowerCase() === '.cs')
      .map(e => ({
        name: e.name,
        path: path.join(dirPath, e.name),
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

ipcMain.handle('read-file', async (_event, filePath: string) => {
  try {
    const content = fs.readFileSync(filePath, 'utf-8')
    return { path: filePath, name: path.basename(filePath), content }
  } catch { return null }
})

ipcMain.handle('write-file', async (_event, filePath: string, content: string, workspacePath?: string) => {
  try {
    if (!workspacePath || !isAllowedUnityScriptPath(filePath, workspacePath)) {
      return { success: false, error: 'Dosya yalnızca workspace içindeki Assets/Scripts altına yazılabilir.' }
    }
    const dir = path.dirname(filePath)
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true })
    }
    fs.writeFileSync(filePath, content, 'utf-8')
    return { success: true, path: filePath }
  } catch (err: any) {
    return { success: false, error: err.message }
  }
})

ipcMain.handle('file-exists', async (_event, filePath: string, workspacePath?: string) => {
  if (!workspacePath || !isAllowedUnityScriptPath(filePath, workspacePath)) {
    return false
  }
  return fs.existsSync(filePath)
})

ipcMain.handle('write-multiple-files', async (_event, files: { path: string; content: string }[], workspacePath?: string) => {
  const results: { path: string; success: boolean; error?: string }[] = []
  for (const file of files) {
    try {
      if (!workspacePath || !isAllowedUnityScriptPath(file.path, workspacePath)) {
        results.push({ path: file.path, success: false, error: 'Dosya yalnızca workspace içindeki Assets/Scripts altına yazılabilir.' })
        continue
      }
      const dir = path.dirname(file.path)
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true })
      }
      fs.writeFileSync(file.path, file.content, 'utf-8')
      results.push({ path: file.path, success: true })
    } catch (err: any) {
      results.push({ path: file.path, success: false, error: err.message })
    }
  }
  return results
})

// --- BACKEND YOLLARINI BUL ---
function getBackendPaths(): { pythonExec: string; pythonScript: string; backendDir: string; sitePackages: string } {
  const isWin = process.platform === 'win32'

  if (isProd) {
    const resourcesPath = process.resourcesPath
    const backendDir = path.join(resourcesPath, 'Backend')
    const pythonScript = path.join(backendDir, 'app', 'main.py')

    // venv'deki site-packages'ı bul
    let sitePackages = ''
    if (isWin) {
      // Windows: venv/Lib/site-packages
      const winSitePackages = path.join(backendDir, 'venv', 'Lib', 'site-packages')
      if (fs.existsSync(winSitePackages)) {
        sitePackages = winSitePackages
      }
    } else {
      // macOS/Linux: venv/lib/python3.x/site-packages
      const venvLib = path.join(backendDir, 'venv', 'lib')
      try {
        const pyDirs = fs.readdirSync(venvLib).filter(d => d.startsWith('python'))
        if (pyDirs.length > 0) {
          sitePackages = path.join(venvLib, pyDirs[0], 'site-packages')
        }
      } catch {}
    }

    // Sistem python kullan (venv symlink'leri build'de kırılır)
    const pythonExec = isWin ? 'python' : 'python3'

    return { pythonExec, pythonScript, backendDir, sitePackages }
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

// --- AKILLI BACKEND KONTROLÜ ---
async function startPythonBackend() {
  try {
    await axios.get('http://127.0.0.1:8000/');
    console.log('--- BACKEND ZATEN AYAKTA, BAŞLATILMADI ---');
    return;
  } catch (err: any) {
    if (err.response) {
      console.log('--- PORT 8000 MEŞGUL (404/500), YENİDEN BAŞLATILMADI ---');
      return;
    }
    console.log('--- BACKEND ÇEVRİMDIŞI, BAŞLATILIYOR... ---');
  }

  const { pythonExec, pythonScript, backendDir, sitePackages } = getBackendPaths()

  // Script dosyasının varlığını kontrol et
  if (!fs.existsSync(pythonScript)) {
    console.error(`--- BACKEND SCRIPT BULUNAMADI: ${pythonScript} ---`)
    return
  }

  // Python'ın erişilebilir olup olmadığını kontrol et (venv veya sistem)
  if (pythonExec !== 'python3' && pythonExec !== 'python' && !fs.existsSync(pythonExec)) {
    console.error(`--- PYTHON BULUNAMADI: ${pythonExec} ---`)
    return
  }

  console.log(`--- BACKEND BAŞLATILIYOR: ${pythonExec} ${pythonScript} ---`)
  console.log(`--- BACKEND CWD: ${backendDir} ---`)
  if (sitePackages) {
    console.log(`--- PYTHONPATH: ${sitePackages} ---`)
  }

  // PYTHONPATH ile venv paketlerini sistem python3'e tanıt
  const spawnEnv = {
    ...process.env,
    PYTHONUNBUFFERED: '1',
    ...(sitePackages ? { PYTHONPATH: sitePackages + (process.env.PYTHONPATH ? `${process.platform === 'win32' ? ';' : ':'}${process.env.PYTHONPATH}` : '') } : {}),
  }

  pyBackendProcess = spawn(pythonExec, [pythonScript], {
    stdio: ['ignore', 'pipe', 'pipe'],
    cwd: backendDir,
    env: spawnEnv,
  });

  // Backend loglarını Electron console'a yönlendir
  pyBackendProcess.stdout?.on('data', (data) => {
    console.log(`[Backend] ${data.toString().trim()}`)
  })
  pyBackendProcess.stderr?.on('data', (data) => {
    console.error(`[Backend] ${data.toString().trim()}`)
  })

  pyBackendProcess.on('error', (err) => {
    console.error('Python başlatılamadı:', err);
  });

  pyBackendProcess.on('exit', (code) => {
    console.log(`--- BACKEND KAPANDI (exit code: ${code}) ---`);
  });

  // Backend ayağa kalkana kadar bekle (max 30 saniye)
  await waitForBackend(30000)
}

async function waitForBackend(timeoutMs: number): Promise<void> {
  const interval = 500
  const maxAttempts = timeoutMs / interval
  for (let i = 0; i < maxAttempts; i++) {
    try {
      await axios.get('http://127.0.0.1:8000/')
      console.log(`--- BACKEND HAZIR (${(i * interval / 1000).toFixed(1)}s) ---`)
      return
    } catch (err: any) {
      if (err.response) {
        // Sunucu cevap verdi (404/500 olsa da ayakta)
        console.log(`--- BACKEND HAZIR (${(i * interval / 1000).toFixed(1)}s) ---`)
        return
      }
    }
    await new Promise(resolve => setTimeout(resolve, interval))
  }
  console.warn('--- BACKEND 30s içinde hazır olmadı, devam ediliyor ---')
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
      await startPythonBackend();

      const mainWindow = createWindow('main', {
        width: 1280,
        height: 850,
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
    })()

  app.on('window-all-closed', () => {
    if (pyBackendProcess) {
      pyBackendProcess.kill();
    }
    app.quit();
  })
}
