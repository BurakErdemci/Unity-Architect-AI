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
  okumaKarariVer,
  taniticiKapsamdaMi,
  isAllowedWorkspaceWriteFile,
} from './helpers/file-security'
import {
  confirmLegacyRoot,
  isOwnFrame,
  isTrustedRoot,
  registerTrustedRoot,
} from './helpers/ipc-trust'
import { applyContentSecurityPolicy } from './helpers/csp'
import * as pty from 'node-pty'

const localAppToken = randomUUID()

const isProd = process.env.NODE_ENV === 'production'
let pyBackendProcess: ChildProcess | null = null
let backendPort: number | null = null
const BACKEND_HOST = '127.0.0.1'

// --- DOSYA LOGLAMA (paketlenmiş app'te konsol görünmez) ---
// Logları hem temp hem userData altına yazar; başka PC'de teşhis için kalıcı.
const logFilePath = path.join(os.tmpdir(), 'gamachine.log')
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

// --- IPC KAPILARI (2026-07-27 denetimi, D grubu) ---

/**
 * `ipcMain.handle` yerine bunu kullan. Tek işi: çağrının bizim sayfamızdan
 * geldiğini doğrulamak.
 *
 * Sebebi somut — preload `window.ipc`'yi KOŞULSUZ expose ediyor, yani renderer'da
 * çalışan her belge (uzak bir sayfa, enjekte bir script) 24 kanalın hepsine
 * erişebiliyordu: `app-token-get` ile backend bearer'ı, `terminal-spawn` +
 * `terminal-write` ile kullanıcının kabuğu. Gezinme politikası bu belgenin
 * renderer'a GİRMESİNİ engelliyor; burası o politika delinirse diye ikinci kilit.
 *
 * Reddedilen çağrı sessiz kalmıyor: log'a düşüyor, çünkü sessiz bir ret meşru bir
 * regresyonla saldırıyı ayırt edilemez kılar.
 */
const handleSecure = (
  channel: string,
  listener: (event: Electron.IpcMainInvokeEvent, ...args: any[]) => any,
) => {
  ipcMain.handle(channel, (event, ...args) => {
    if (!isOwnFrame(event)) {
      console.error(`[ipc-trust] '${channel}' reddedildi — gönderen:`, event.senderFrame?.url ?? '(bilinmiyor)')
      throw new Error('IPC reddedildi: gönderen çerçeve uygulamaya ait değil.')
    }
    return listener(event, ...args)
  })
}

/**
 * Workspace kökünün kendisi çağırandan geliyordu; yani hapsi hapsedilen
 * seçiyordu. `read-file($HOME/.codex/auth.json, $HOME)` bu yüzden kimlik
 * bilgisi okuyabiliyordu — yol "iddia edilen kök"ün içinde kalıyor.
 *
 * Artık kök, kullanıcının native diyalogla seçtiği kütüğe karşı doğrulanıyor.
 * Hata döndürürse çağıran handler kendi boş/başarısız değerini vermeli.
 */
const untrustedWorkspace = (workspacePath?: string): string | null => {
  if (!workspacePath) return 'Workspace path eksik.'
  if (isTrustedRoot(workspacePath) || confirmLegacyRoot(workspacePath)) return null
  return 'Bu klasör yetkili değil — klasörü uygulama içinden yeniden seçin.'
}

// --- TERMINAL YÖNETİMİ ---
const ptyProcesses: Map<string, pty.IPty> = new Map();

handleSecure('terminal-spawn', (event, { id, cwd }) => {
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

  // cwd çağırandan geliyor ve kabuk o dizinde açılıyor. Yetkili bir workspace
  // değilse ev dizinine düşürülüyor: kabuk zaten kullanıcının yetkisiyle
  // çalışıyor, ama saldırganın SEÇTİĞİ bir dizinde başlaması (ör. bir git
  // reposunun içi, bir kimlik bilgisi klasörü) fazladan bilgi ve kolaylık verir.
  if (!isTrustedRoot(finalCwd)) {
    console.warn('[Terminal] yetkisiz cwd, ev dizinine düşülüyor:', finalCwd);
    finalCwd = homeDir || '.';
  }

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

handleSecure('terminal-write', (_event, { id, data }) => {
  const ptyProcess = ptyProcesses.get(id);
  if (ptyProcess) {
    ptyProcess.write(data);
    return { success: true };
  }
  return { success: false, error: 'Terminal bulunamadı' };
});

handleSecure('terminal-resize', (_event, { id, cols, rows }) => {
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
handleSecure('open-file-dialog', async () => {
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
handleSecure('open-video-dialog', async () => {
  const result = await dialog.showOpenDialog({
    properties: ['openFile', 'multiSelections'],
    filters: [
      { name: 'Video', extensions: ['mp4', 'mov', 'mkv', 'webm', 'avi', 'm4v'] }
    ]
  })
  if (result.canceled || result.filePaths.length === 0) return null
  return result.filePaths.map(p => ({ path: p, name: path.basename(p) }))
})

handleSecure('open-folder-dialog', async () => {
  const result = await dialog.showOpenDialog({
    properties: ['openDirectory']
  })
  if (result.canceled || result.filePaths.length === 0) return null
  // Yetkili kök kütüğüne YALNIZCA buradan giriliyor: kullanıcının native
  // diyalogda kendi eliyle seçtiği klasör. Renderer'ın önerdiği hiçbir yol
  // kendiliğinden yetkili olmuyor (bkz. helpers/ipc-trust.ts).
  registerTrustedRoot(result.filePaths[0])
  return result.filePaths[0]
})

handleSecure('save-file-dialog', async (_event, options) => {
  const result = await dialog.showSaveDialog(options)
  if (result.canceled) return null
  return result.filePath
})

// Hafıza export/import gibi kullanıcı-tetikli akışlar için atomik dialog+yazma/okuma.
// write-file kasıtlı olarak workspace .cs dosyalarına kısıtlı; bu handler kullanıcı
// dialog'dan onayladığı path'i doğrudan kullandığı için ayrı kanaldan gidiyor.
handleSecure('export-text-file', async (_event, defaultName: string, content: string) => {
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

handleSecure('import-text-file', async (_event, options?: { filters?: { name: string; extensions: string[] }[] }) => {
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

handleSecure('read-directory', async (_event, dirPath: string, workspacePath?: string) => {
  try {
    if (!workspacePath) return [];
    const _ws = untrustedWorkspace(workspacePath); if (_ws) return [];
    const fullPath = path.isAbsolute(dirPath) ? dirPath : path.join(workspacePath, dirPath);
    if (!isAllowedWorkspacePath(fullPath, workspacePath)) {
      return []
    }
    const entries = fs.readdirSync(fullPath, { withFileTypes: true })
    const items = entries
      .filter(e => !e.name.startsWith('.'))
      // Ağaç HER dosyayı gösterir (prefab/anim/fbx/png…) — yalnız .meta gürültüsü
      // gizli (her asset'in yanında bir tane var, ağacı ikiye katlar).
      .filter(e => e.isDirectory() || path.extname(e.name).toLowerCase() !== '.meta')
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
handleSecure('git-status', async (_event, workspacePath?: string) => {
  const empty = { isRepo: false, files: {}, dirs: {} }
  try {
    if (!workspacePath || !fs.existsSync(workspacePath)) return empty
    // Kök doğrulanmasaydı `git -C <herhangi bir dizin>` çalıştırılabilirdi:
    // kullanıcının makinesindeki başka bir reponun dosya listesi ve durumu.
    if (untrustedWorkspace(workspacePath)) return empty
    const { execFile } = require('child_process') as typeof import('child_process')
    const run = (args: string[]) => new Promise<string>((resolve, reject) => {
      execFile('git', ['-C', workspacePath, ...args], {
        timeout: 8000, maxBuffer: 8 * 1024 * 1024, windowsHide: true,
      }, (err, stdout) => err ? reject(err) : resolve(stdout))
    })

    const toplevel = (await run(['rev-parse', '--show-toplevel'])).trim()
    if (!toplevel) return empty
    // `--show-toplevel` seçili klasörün DEĞİL, onu içeren reponun kökünü döndürür.
    // Workspace bir monorepo'nun alt dizini ise burada dışarıdaki bir yol ve onun
    // altındaki tüm değişiklikler görünür hâle geliyordu — yani kullanıcının
    // yetkilendirdiğinden fazlası. Kök kütüğün dışına çıkıyorsa repo durumu yok.
    if (!isTrustedRoot(toplevel)) {
      console.warn('[git-status] repo kökü yetkili alan dışında, atlanıyor:', toplevel)
      return empty
    }
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

handleSecure('read-file', async (_event, filePath: string, workspacePath?: string) => {
  try {
    if (!workspacePath) return null;
    const _ws = untrustedWorkspace(workspacePath); if (_ws) return null;
    const fullPath = path.isAbsolute(filePath) ? filePath : path.join(workspacePath, filePath);
    // ⚠️ Kapı ve açış AYNI çözümü paylaşmak ZORUNDA (doğrulama turu bulgusu
    // `check-open-resolve-divergence`). Eskiden kapı kendi içinde bir kez,
    // çağıran ikinci kez çözüyordu; aradaki pencerede bir ara bileşen
    // junction'a çevrilince kontrol edilen dosya ile açılan dosya ayrışıyordu.
    const karar = okumaKarariVer(fullPath, workspacePath)
    if (!karar.izinli) {
      return { error: 'unsupported' }
    }
    // ⚠️ KONTROL EDİLEN ile OKUNAN aynı dosya olmalı (dış denetim bulgusu
    // `path-check-use-race`, probe ile üretildi). Eskiden kapı çözülmüş yol
    // üzerinde karar veriyor, `statSync`/`readFileSync` ise HAM yolu okuyordu;
    // aradaki pencerede bir junction hedefini değiştirirse ürün workspace
    // dışındaki dosyayı döndürüyordu.
    //
    // Çözüm bir kez AÇIP tanıtıcıdan ilerlemek: `fstat` ve okuma artık kapının
    // gördüğü inode'a bağlı, yola değil. Aynı desen backend'de zaten var
    // (`local_token_file` fd üzerinden doğruluyor) — burada tekrar edilmesinin
    // sebebi iki ayrı süreç olması, kopyalama değil.
    // Kapının kararını verdiği yol açılıyor — ham yol DEĞİL.
    const okunacak = karar.cozulmusYol
    let fd: number | null = null
    try {
      fd = fs.openSync(okunacak, 'r')
      const st = fs.fstatSync(fd)
      if (!st.isFile()) return { error: 'unsupported' }
      // Dev Unity sahne/prefab YAML'ları 100MB'ı bulabilir — Monaco'yu dondurur.
      if (st.size > 8 * 1024 * 1024) {
        return { error: 'too-large' }
      }
      // Sabit bağ kapıda da reddediliyor; burada tekrar bakmak, açış ile kapı
      // arasında yaratılmış bir ikinci adı da yakalıyor.
      if (st.nlink > 1) return { error: 'unsupported' }

      // Sınıfı kapatan kontrol; gerekçesi fonksiyonun başında.
      if (!taniticiKapsamdaMi(st, okunacak, workspacePath)) {
        return { error: 'unsupported' }
      }

      const content = fs.readFileSync(fd, 'utf-8')
      // `fullPath` döndürülüyor: kapsama kanıtlandıktan sonra o ad da aynı
      // inode'u gösteriyor, ve dosya ağacı da bu adı kullanıyor — çözülmüş yolu
      // döndürmek workspace'in kendisi bir junction olduğunda ağaçla editörün
      // yolunu ayrıştırırdı.
      return { path: fullPath, name: path.basename(fullPath), content }
    } finally {
      if (fd !== null) { try { fs.closeSync(fd) } catch { /* kapatma hatası okumayı geçersizleştirmez */ } }
    }
  } catch { return null }
})

handleSecure('write-file', async (_event, filePath: string, content: string, workspacePath?: string) => {
  try {
    const isAbsolute = path.isAbsolute(filePath);

    if (!workspacePath && !isAbsolute) return { success: false, error: 'Workspace path eksik.' };
    const _ws = untrustedWorkspace(workspacePath); if (_ws) return { success: false, error: _ws };

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

handleSecure('file-exists', async (_event, filePath: string, workspacePath?: string) => {
  if (!workspacePath) return false;
  const _ws = untrustedWorkspace(workspacePath); if (_ws) return false;
  const fullPath = path.isAbsolute(filePath) ? filePath : path.join(workspacePath, filePath);
  if (!isAllowedWorkspaceWriteFile(fullPath, workspacePath)) {
    return false
  }
  return fs.existsSync(fullPath)
})

handleSecure('write-multiple-files', async (_event, files: { path: string; content: string }[], workspacePath?: string) => {
  const results: { path: string; success: boolean; error?: string }[] = []
  if (!workspacePath) return results;
  const _ws = untrustedWorkspace(workspacePath); if (_ws) return results;

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
handleSecure('create-file', async (_event, filePath: string, workspacePath?: string) => {
  if (!workspacePath) return { success: false, error: 'Workspace path eksik.' }
  const _ws = untrustedWorkspace(workspacePath); if (_ws) return { success: false, error: _ws };
  const fullPath = path.isAbsolute(filePath) ? filePath : path.join(workspacePath, filePath)
  if (!isAllowedWorkspacePath(fullPath, workspacePath)) return { success: false, error: 'Dosya workspace dışında.' }
  if (fs.existsSync(fullPath)) return { success: false, error: 'Dosya zaten var.' }
  fs.mkdirSync(path.dirname(fullPath), { recursive: true })
  fs.writeFileSync(fullPath, '', 'utf-8')
  return { success: true, path: fullPath }
})

handleSecure('delete-file', async (_event, relativePath: string, workspacePath?: string) => {
  try {
    if (!workspacePath) return { success: false, error: 'Workspace path eksik.' };
    const _ws = untrustedWorkspace(workspacePath); if (_ws) return { success: false, error: _ws };
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

handleSecure('create-folder', async (_event, folderPath: string, workspacePath?: string) => {
  if (!workspacePath) return { success: false, error: 'Workspace path eksik.' }
  const _ws = untrustedWorkspace(workspacePath); if (_ws) return { success: false, error: _ws };
  const fullPath = path.isAbsolute(folderPath) ? folderPath : path.join(workspacePath, folderPath)
  if (!isAllowedWorkspacePath(fullPath, workspacePath)) return { success: false, error: 'Klasör workspace dışında.' }
  if (fs.existsSync(fullPath)) return { success: false, error: 'Klasör zaten var.' }
  fs.mkdirSync(fullPath, { recursive: true })
  return { success: true, path: fullPath }
})

handleSecure('rename-entry', async (_event, oldPath: string, newName: string, workspacePath?: string) => {
  if (!workspacePath) return { success: false, error: 'Workspace path eksik.' }
  const _ws = untrustedWorkspace(workspacePath); if (_ws) return { success: false, error: _ws };
  const fullOldPath = path.isAbsolute(oldPath) ? oldPath : path.join(workspacePath, oldPath)
  if (!isAllowedWorkspacePath(fullOldPath, workspacePath)) return { success: false, error: 'Dosya workspace dışında.' }
  if (!fs.existsSync(fullOldPath)) return { success: false, error: 'Dosya bulunamadı.' }
  // `newName` bir AD olmalı, yol değil. Doğrulanmadığında Node traversal
  // segmentlerini normalize ediyordu ve dosya workspace dışına taşınıyordu:
  //   path.join('/trusted/workspace', '../../escaped.txt') → '/escaped.txt'
  // Bu, meşru arayüzden de tetiklenir — kullanıcı adlandırma kutusuna '../'
  // yazması yeterdi. Önce ayraç/traversal reddediliyor, sonra hedef de tıpkı
  // kaynak gibi workspace hapsine sokuluyor (biri yeterli değil: ayraçsız bir
  // sembolik bağ da dışarı çıkabilir).
  if (!newName || newName.includes('/') || newName.includes('\\') || newName === '..' || newName === '.') {
    return { success: false, error: 'Geçersiz ad: yol ayracı içeremez.' }
  }
  const newPath = path.join(path.dirname(fullOldPath), newName)
  if (!isAllowedWorkspacePath(newPath, workspacePath)) return { success: false, error: 'Hedef workspace dışında.' }
  if (fs.existsSync(newPath)) return { success: false, error: 'Bu isimde bir dosya zaten var.' }
  fs.renameSync(fullOldPath, newPath)
  return { success: true, newPath }
})

handleSecure('delete-entry', async (_event, entryPath: string, workspacePath?: string) => {
  if (!workspacePath) return { success: false, error: 'Workspace path eksik.' }
  const _ws = untrustedWorkspace(workspacePath); if (_ws) return { success: false, error: _ws };
  const fullPath = path.isAbsolute(entryPath) ? entryPath : path.join(workspacePath, entryPath)
  if (!isAllowedWorkspacePath(fullPath, workspacePath)) return { success: false, error: 'Dosya workspace dışında.' }
  if (!fs.existsSync(fullPath)) return { success: false, error: 'Dosya bulunamadı.' }
  fs.rmSync(fullPath, { recursive: true, force: true })
  return { success: true }
})

handleSecure('move-entry', async (_event, sourcePath: string, targetDir: string, workspacePath?: string) => {
  if (!workspacePath) return { success: false, error: 'Workspace path eksik.' }
  const _ws = untrustedWorkspace(workspacePath); if (_ws) return { success: false, error: _ws };
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
handleSecure('path-exists', async (_event, targetPath: string) => {
  try {
    if (!targetPath) return false
    // Bu handler yetkili kök kapısından MUAFTI: `workspacePath` parametresi
    // olmadığı için untrustedWorkspace() ona hiç uygulanmamıştı. Sonuç, çağıranın
    // dosya sisteminin herhangi bir yerinde dizin varlığını sorgulayabilmesiydi
    // — tek başına küçük, ama keşif adımı olarak diğer bulguları besliyor.
    //
    // Meşru kullanım DAR: renderer bunu yalnız "önceki workspace hâlâ duruyor mu"
    // diye çağırıyor (useFileSystem.selectWorkspace). Yetkili köklerle sınırlamak
    // o kullanımı bozmuyor, çünkü sorulan yol zaten bir zamanlar seçilmiş kök.
    if (!isTrustedRoot(targetPath)) return false
    return fs.existsSync(targetPath) && fs.statSync(targetPath).isDirectory()
  } catch {
    return false
  }
})

handleSecure('app-token-get', () => localAppToken)
handleSecure('get-backend-base-url', () => getBackendBaseUrl())

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
      if (response.data?.status === 'ok' && response.data?.service === 'gamachine') {
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

      // CSP, pencere açılmadan ÖNCE kuruluyor: politika ilk belge yanıtına
      // yetişmezse ana sayfa korumasız yüklenir ve bu sessizce olur.
      applyContentSecurityPolicy(isProd)

      // Windows görev çubuğu ikonu: AppUserModelId set edilmezse taskbar default
      // Electron ikonunu gösterir (window/exe ikonundan bağımsız). appId ile eşle.
      if (process.platform === 'win32') {
        app.setAppUserModelId('com.gamachine.app')
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
              await shell.openExternal('https://github.com/BurakErdemci/gamachine/releases/latest')
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
