import fs from 'fs'
import os from 'os'
import path from 'path'
import { afterEach, beforeEach, describe, it, expect } from 'vitest'
import {
  MODEL_FILE_EXTENSIONS,
  MODEL_MAX_BYTES,
  TEXT_MAX_BYTES,
  isAllowedWorkspaceReadFile,
  okumaKarariVer,
  readModelFileFromWorkspace,
} from '../main/helpers/file-security'

let ws = ''
let disari = ''

/**
 * Can this filesystem make a hardlink at all?
 *
 * Hardlinks are the subject of one of the gate's own rules, so their absence
 * has to be VISIBLE. The earlier shape returned early from inside `it()` when
 * `linkSync` threw, which reported a green test that asserted nothing — on a
 * container volume or FAT/exFAT that is a silently disabled security check.
 */
const sabitBagDestekli = ((): boolean => {
  const probe = fs.mkdtempSync(path.join(os.tmpdir(), 'model-gate-link-probe-'))
  try {
    const kaynak = path.join(probe, 'a')
    fs.writeFileSync(kaynak, 'x')
    fs.linkSync(kaynak, path.join(probe, 'b'))
    return true
  } catch {
    return false
  } finally {
    try { fs.rmSync(probe, { recursive: true, force: true }) } catch { /* best effort */ }
  }
})()

beforeEach(() => {
  ws = fs.mkdtempSync(path.join(os.tmpdir(), 'model-gate-ws-'))
  disari = fs.mkdtempSync(path.join(os.tmpdir(), 'model-gate-out-'))
})

afterEach(() => {
  for (const dir of [ws, disari]) {
    if (dir) { try { fs.rmSync(dir, { recursive: true, force: true }) } catch { /* best effort */ } }
  }
  ws = ''
  disari = ''
})

function yaz(dir: string, ad: string, icerik: Buffer | string): string {
  const p = path.join(dir, ad)
  fs.writeFileSync(p, icerik)
  return p
}

describe('model okuma kapısı — kabul', () => {
  for (const ext of MODEL_FILE_EXTENSIONS) {
    it(`workspace içindeki ${ext} dosyasını okur`, () => {
      const bytes = Buffer.from([0x67, 0x6c, 0x54, 0x46, 0x02, 0x00, 0x00, 0x00])
      const p = yaz(ws, `mesh${ext}`, bytes)

      const sonuc = readModelFileFromWorkspace(p, ws)

      expect('error' in sonuc).toBe(false)
      if ('error' in sonuc) return
      expect(sonuc.name).toBe(`mesh${ext}`)
      expect(sonuc.path).toBe(p)
      // `toBeInstanceOf(ArrayBuffer)` kullanılmıyor: jsdom ortamında global
      // ArrayBuffer Node realm'ininkinden farklı bir sınıf, o yüzden gerçek bir
      // ArrayBuffer bile o kontrolden kalıyor. Tür etiketi realm'den bağımsız.
      expect(Object.prototype.toString.call(sonuc.data)).toBe('[object ArrayBuffer]')
      expect(sonuc.data.byteLength).toBe(bytes.length)
      expect(Buffer.from(new Uint8Array(sonuc.data)).equals(bytes)).toBe(true)
    })
  }

  it('büyük harfli uzantıyı kabul eder', () => {
    const p = yaz(ws, 'Mesh.GLB', Buffer.from([1, 2, 3]))
    expect(readModelFileFromWorkspace(p, ws)).not.toHaveProperty('error')
  })

  it('alt klasördeki modeli okur', () => {
    fs.mkdirSync(path.join(ws, 'Assets', 'Models'), { recursive: true })
    const p = yaz(path.join(ws, 'Assets', 'Models'), 'char.fbx', Buffer.from([9, 9]))
    expect(readModelFileFromWorkspace(p, ws)).not.toHaveProperty('error')
  })

  // Sıfır bayt kapının üç sorusunun (kapsama, uzantı, boyut) hepsini geçiyor,
  // yani kanal onu OKUYOR. Davranış burada çivileniyor çünkü "boş dosya" bir
  // ayrıştırıcı sorunu: panel zaten ayrıştırma hatasını gösterecek sözü taşıyor,
  // ve kapıya bir boşluk reddi eklenecekse bu bilinçli bir değişiklik olmalı,
  // sessiz bir kayma değil.
  it('sıfır baytlık dosyayı reddetmez — boşluk kapının değil ayrıştırıcının işi', () => {
    const p = yaz(ws, 'empty.glb', Buffer.alloc(0))

    const sonuc = readModelFileFromWorkspace(p, ws)

    expect('error' in sonuc).toBe(false)
    if ('error' in sonuc) return
    expect(sonuc.data.byteLength).toBe(0)
  })

  it('tavan sınırındaki dosyayı reddetmez', () => {
    const p = yaz(ws, 'edge.stl', Buffer.alloc(0))
    const fd = fs.openSync(p, 'r+')
    try { fs.ftruncateSync(fd, MODEL_MAX_BYTES) } finally { fs.closeSync(fd) }

    expect(readModelFileFromWorkspace(p, ws)).not.toHaveProperty('error')
  })
})

describe('model okuma kapısı — uzantı beyaz listesi', () => {
  // Bir model kanalının workspace İÇİNDEN bile sır dosyası döndürebilmesi
  // sızıntı yüzeyidir; kanal ne reddettiğini değil ne kabul ettiğini sayıyor.
  for (const ad of ['.env', 'key.pem', 'secrets.json', 'Player.cs', 'notes.md', 'app.exe']) {
    it(`workspace içinde olsa da reddeder: ${ad}`, () => {
      const p = yaz(ws, ad, 'SECRET=1')
      expect(readModelFileFromWorkspace(p, ws)).toEqual({ error: 'unsupported' })
    })
  }

  it('uzantısız dosyayı reddeder', () => {
    const p = yaz(ws, 'model', Buffer.from([1]))
    expect(readModelFileFromWorkspace(p, ws)).toEqual({ error: 'unsupported' })
  })
})

describe('model okuma kapısı — kapsama', () => {
  it('workspace dışındaki modeli reddeder', () => {
    const p = yaz(disari, 'outside.glb', Buffer.from([1, 2]))
    expect(readModelFileFromWorkspace(p, ws)).toEqual({ error: 'denied' })
  })

  it('.. ile dışarı çıkışı reddeder', () => {
    const p = yaz(disari, 'outside.obj', Buffer.from([1, 2]))
    const traversal = path.join(ws, '..', path.basename(disari), 'outside.obj')
    expect(readModelFileFromWorkspace(traversal, ws)).toEqual({ error: 'denied' })
  })

  it('dizini reddeder', () => {
    const d = path.join(ws, 'fake.glb')
    fs.mkdirSync(d)
    const sonuc = readModelFileFromWorkspace(d, ws)
    expect(sonuc).toHaveProperty('error')
  })

  it.skipIf(!sabitBagDestekli)('workspace dışına giden sabit bağı reddeder', () => {
    const hedef = yaz(disari, 'secret.glb', Buffer.from([7, 7, 7]))
    const bag = path.join(ws, 'linked.glb')
    fs.linkSync(hedef, bag)
    expect(readModelFileFromWorkspace(bag, ws)).toEqual({ error: 'denied' })
  })

  it('boş workspace ile reddeder', () => {
    const p = yaz(ws, 'a.glb', Buffer.from([1]))
    expect(readModelFileFromWorkspace(p, '')).toHaveProperty('error')
  })
})

describe('model okuma kapısı — boyut tavanı', () => {
  it(`${MODEL_MAX_BYTES} baytı aşan dosyayı too-large ile reddeder`, () => {
    const p = yaz(ws, 'huge.fbx', Buffer.alloc(0))
    const fd = fs.openSync(p, 'r+')
    try {
      fs.ftruncateSync(fd, MODEL_MAX_BYTES + 1)
    } finally {
      fs.closeSync(fd)
    }
    expect(fs.statSync(p).size).toBe(MODEL_MAX_BYTES + 1)

    expect(readModelFileFromWorkspace(p, ws)).toEqual({ error: 'too-large' })
  })
})

describe('metin yolu regresyonu', () => {
  it('metin kapısı model uzantısını kabul etmiyor', () => {
    const p = yaz(ws, 'mesh.glb', Buffer.from([1]))
    expect(isAllowedWorkspaceReadFile(p, ws)).toBe(false)
  })

  it('model kapısı metin uzantısını kabul etmiyor', () => {
    const p = yaz(ws, 'Player.cs', 'class A {}')
    expect(okumaKarariVer(p, ws, 'model').izinli).toBe(false)
  })

  it('varsayılan tür metin — .cs hâlâ geçiyor', () => {
    const p = yaz(ws, 'Player.cs', 'class A {}')
    expect(okumaKarariVer(p, ws).izinli).toBe(true)
    expect(isAllowedWorkspaceReadFile(p, ws)).toBe(true)
  })

  // Both caps are named constants now, so both can be pinned from here; the
  // text cap used to be an inline literal in `background.ts` and could not be.
  it('model tavanı 64 MiB, metin tavanı 8 MiB sabitinde kaldı', () => {
    expect(MODEL_MAX_BYTES).toBe(64 * 1024 * 1024)
    expect(TEXT_MAX_BYTES).toBe(8 * 1024 * 1024)
  })
})
