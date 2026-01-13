import path from 'path'
import { app, ipcMain } from 'electron'
import serve from 'electron-serve'
import { createWindow } from './helpers'
import { spawn, ChildProcess } from 'child_process' // Python başlatmak için eklendi

const isProd = process.env.NODE_ENV === 'production'
let pyBackendProcess: ChildProcess | null = null // Python sürecini takip etmek için

if (isProd) {
  serve({ directory: 'app' })
} else {
  app.setPath('userData', `${app.getPath('userData')} (development)`)
}

// --- PYTHON BAŞLATMA FONKSİYONU ---
function startPythonBackend() {
  
  const appPath = app.getAppPath(); 


  const projectRoot = path.resolve(appPath, '..', '..');

  // 3. Ana klasörden Backend'e giriş yapıyoruz
  const pythonExec = path.join(projectRoot, 'Backend', 'venv', 'bin', 'python3');
  const pythonScript = path.join(projectRoot, 'Backend', 'app', 'main.py');

  console.log('--- YENİ YOL KONTROLÜ ---');
  console.log('Uygulama Yolu:', appPath);
  console.log('Proje Kökü:', projectRoot);
  console.log('Hedef Python:', pythonExec);
  console.log('Hedef Script:', pythonScript);

  // Süreci başlat
  pyBackendProcess = spawn(pythonExec, [pythonScript], {
    shell: true,
    stdio: 'inherit'
  });

  pyBackendProcess.on('error', (err) => {
    console.error('Başlatma hatası:', err);
  });
}

;(async () => {
  await app.whenReady()

  // --- UYGULAMA HAZIR OLDUĞUNDA PYTHON'U BAŞLAT ---
  if (!isProd) {
    startPythonBackend()
  }

  const mainWindow = createWindow('main', {
    width: 1200, // Biraz genişlettik
    height: 800,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
    },
  })

  if (isProd) {
    await mainWindow.loadURL('app://./home')
  } else {
    const port = process.argv[2]
    await mainWindow.loadURL(`http://localhost:${port}/home`)
    // Geliştirme modunda konsolu otomatik açmak istemiyorsan burayı kapatabilirsin
    // mainWindow.webContents.openDevTools() 
  }
})()

app.on('window-all-closed', () => {
  // --- UYGULAMA KAPANIRKEN PYTHON'U DA KAPAT ---
  if (pyBackendProcess) {
    console.log('Python Backend kapatılıyor...')
    pyBackendProcess.kill() 
  }
  app.quit()
})

ipcMain.on('message', async (event, arg) => {
  event.reply('message', `${arg} World!`)
})