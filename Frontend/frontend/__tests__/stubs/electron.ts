/**
 * `electron` paketinin TEST karşılığı — adlandırılmış bir platform dikişi.
 *
 * ⚠️ Ölçülmüş arıza (2 Ağu 2026): CI bağımlılıkları `npm ci --ignore-scripts`
 * ile kuruyor. Bu bilinçli bir karar — electron'un postinstall'ı 100MB+ ikili
 * indiriyor ve testlerin o ikiliye ihtiyacı yok. Ama script koşmayınca
 * `node_modules/electron/index.js` "Electron failed to install correctly" diye
 * FIRLATIYOR, ve ana süreç yardımcılarını import eden her test paketi
 * toplanırken çöküyordu. Yerelde ikili kurulu olduğu için hepsi yeşildi:
 * bu deponun kayıtlı "CI kırmızı, yerelde yeşil" sınıfı.
 *
 * Neden `skipif` değil: o, testi iki ortamdan birinde sessizce yok ediyor.
 * Buradaki dikiş testleri KOŞTURUYOR — zaten sınanan şey saf mantık
 * (navigasyon kararı, origin karşılaştırması), Electron çalışma zamanı değil.
 *
 * ⚠️ Bu dosya bir SINIRIN ilanı: ana süreç davranışı burada sınanmıyor,
 * sınanamıyor da. Depoda canlı bir Electron koşum ortamı yok ve o AÇIK bir iş
 * kalemi — bu stub onu kapatmıyor, yalnız görünür kılıyor.
 *
 * Tipler buradan GELMİYOR: `tsc` hâlâ `node_modules/electron`'un gerçek
 * tiplerini okuyor (alias yalnız Vite'ın çalışma zamanı çözümünde geçerli),
 * yani tip güvenliği kaybolmuyor.
 */

export const shell = {
  openExternal: async (_url: string): Promise<void> => {},
}

export const app = {
  getPath: (_name: string): string => '/tmp',
  whenReady: async (): Promise<void> => {},
  on: (): void => {},
  quit: (): void => {},
}

export const dialog = {
  showMessageBox: async () => ({ response: 0 }),
  showOpenDialog: async () => ({ canceled: true, filePaths: [] as string[] }),
}

const ekran = {
  bounds: { x: 0, y: 0, width: 1920, height: 1080 },
  workArea: { x: 0, y: 0, width: 1920, height: 1040 },
  workAreaSize: { width: 1920, height: 1040 },
}

export const screen = {
  getAllDisplays: () => [ekran],
  getPrimaryDisplay: () => ekran,
  getDisplayMatching: () => ekran,
  getCursorScreenPoint: () => ({ x: 0, y: 0 }),
}

export class BrowserWindow {
  webContents = {
    on: (): void => {},
    setWindowOpenHandler: (): void => {},
    getURL: (): string => '',
    send: (): void => {},
  }
  on(): void {}
  loadURL(): void {}
}

export const ipcMain = {
  handle: (): void => {},
  on: (): void => {},
}

export default { shell, app, dialog, screen, BrowserWindow, ipcMain }
