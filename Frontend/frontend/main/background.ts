import path from 'path'
import { app, ipcMain } from 'electron'
import serve from 'electron-serve'
import { createWindow } from './helpers'
import { spawn, ChildProcess } from 'child_process'
import axios from 'axios' // axios'u buraya da ekleyelim (npm install axios)

const isProd = process.env.NODE_ENV === 'production'
let pyBackendProcess: ChildProcess | null = null

if (isProd) {
  serve({ directory: 'app' })
} else {
  app.setPath('userData', `${app.getPath('userData')} (development)`)
}

// --- AKILLI BACKEND KONTROLÜ ---
async function startPythonBackend() {
  try {
    // Port 8000'e bir istek atıyoruz
    await axios.get('http://127.0.0.1:8000/');
    
    // Eğer buraya ulaştıysa cevap gelmiş demektir (200 OK)
    console.log('--- BACKEND ZATEN AYAKTA, BAŞLATILMADI ---');
    return;
  } catch (err: any) {
    // Eğer portta biri varsa ama 404 dönüyorsa err.response oluşur
    if (err.response) {
      console.log('--- PORT 8000 MEŞGUL (404/500), YENİDEN BAŞLATILMADI ---');
      return;
    }
    // Sadece bağlantı tamamen reddedildiyse (ECONNREFUSED) backend kapalıdır
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
;(async () => {
  await app.whenReady()

  // Python'u başlatmayı deniyoruz
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
    await mainWindow.loadURL(`http://localhost:${port}/home`)
  }
})()

app.on('window-all-closed', () => {
  // Sadece prod modunda kapatmak isteyebilirsin, 
  // dev modunda sürekli restart attığı için Python'u kapatmıyoruz.
  if (isProd && pyBackendProcess) {
    pyBackendProcess.kill();
  }
  app.quit();
})