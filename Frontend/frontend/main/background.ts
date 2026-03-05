import path from 'path'
import fs from 'fs'
import { app, ipcMain, dialog } from 'electron'
import serve from 'electron-serve'
import { createWindow } from './helpers'
import { spawn, ChildProcess } from 'child_process'
import axios from 'axios'

const isProd = process.env.NODE_ENV === 'production'
let pyBackendProcess: ChildProcess | null = null

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

ipcMain.handle('write-file', async (_event, filePath: string, content: string) => {
  try {
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

  const appPath = app.getAppPath();
  const projectRoot = path.resolve(appPath, '..', '..');
  const pythonExec = path.join(projectRoot, 'Backend', 'venv', 'bin', 'python3');
  const pythonScript = path.join(projectRoot, 'Backend', 'app', 'main.py');

  pyBackendProcess = spawn(pythonExec, [pythonScript], {
    shell: true,
    stdio: 'inherit'
  });

  pyBackendProcess.on('error', (err) => {
    console.error('Python başlatılamadı:', err);
  });
}

// --- TEK INSTANCE KİLİDİ (Nextron çift restart'ı önler) ---
const gotTheLock = app.requestSingleInstanceLock()

if (!gotTheLock) {
  // İkinci instance — sessizce çık, ilk instance zaten çalışıyor
  console.log('--- BAŞKA BİR INSTANCE ZATEN ÇALIŞIYOR, ÇIKILIYOR ---')
  app.quit()
} else {
  // İlk instance — normal başlat
  app.on('second-instance', () => {
    // İkinci instance başlatılmaya çalışıldığında, mevcut pencereye focus ver
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
        // Retry logic — sayfa hazır olmayabilir
        const maxRetries = 5
        for (let i = 0; i < maxRetries; i++) {
          try {
            await mainWindow.loadURL(`http://localhost:${port}/home`)
            break // Başarılı, döngüden çık
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
    if (isProd && pyBackendProcess) {
      pyBackendProcess.kill();
    }
    app.quit();
  })
}