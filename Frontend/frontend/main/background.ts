import path from 'path'
import fs from 'fs'
import net from 'net'
import { app, ipcMain, dialog, safeStorage } from 'electron'
import serve from 'electron-serve'
import { createWindow } from './helpers'
import { spawn, ChildProcess } from 'child_process'
import axios from 'axios'
import {
  isAllowedUnityScriptPath,
  isAllowedWorkspacePath,
  isAllowedWorkspaceReadFile,
} from './helpers/file-security'
import { sessionGet, sessionSet, sessionClear } from './helpers/session-storage-handlers'

const isProd = process.env.NODE_ENV === 'production'
let pyBackendProcess: ChildProcess | null = null
let backendPort: number | null = null
const BACKEND_HOST = '127.0.0.1'

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

ipcMain.handle('read-directory', async (_event, dirPath: string, workspacePath?: string) => {
  try {
    if (!workspacePath || !isAllowedWorkspacePath(dirPath, workspacePath)) {
      return []
    }
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

ipcMain.handle('read-file', async (_event, filePath: string, workspacePath?: string) => {
  try {
    if (!workspacePath || !isAllowedWorkspaceReadFile(filePath, workspacePath)) {
      return null
    }
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

// --- IPC: SESSION STORAGE (safeStorage) ---
const makeSessionDeps = () => ({
  userDataPath: app.getPath('userData'),
  safeStorage,
})

ipcMain.handle('session-get', () => sessionGet(makeSessionDeps()))
ipcMain.handle('session-set', (_event, token: string) => sessionSet(makeSessionDeps(), token))
ipcMain.handle('session-clear', () => sessionClear(makeSessionDeps()))
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
    env: { ...process.env, PYTHONUNBUFFERED: '1', PORT: String(selectedPort) },
  });

  pyBackendProcess.stdout?.on('data', (data) => {
    console.log(`[Backend] ${data.toString().trim()}`)
  })
  pyBackendProcess.stderr?.on('data', (data) => {
    console.error(`[Backend] ${data.toString().trim()}`)
  })
  pyBackendProcess.on('error', (err) => {
    console.error('Backend başlatılamadı:', err)
  })
  pyBackendProcess.on('exit', (code) => {
    console.log(`--- BACKEND KAPANDI (exit code: ${code}) ---`)
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
      try {
        await startPythonBackend()
      } catch (err) {
        console.error('--- BACKEND BAŞLATILAMADI, PENCERE YINE DE AÇILIYOR ---', err)
        backendPort = null
      }

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
