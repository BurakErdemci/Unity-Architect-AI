/**
 * The two `gamachine-ws-fp-1` implementations must agree, and this is the only
 * thing that runs BOTH of them.
 *
 * The algorithm exists twice — `main/helpers/workspace-fingerprint.ts` and
 * `_fingerprint_lines` in `Backend/app/routes/auth_routes.py` — and Docker
 * startup compares their answers to refuse a container still serving an older
 * bind mount. Both failure directions are real: disagreeing about the same tree
 * refuses a correct setup, agreeing about different trees makes the guard
 * worthless.
 *
 * They already diverged once, during development, while every suite was green
 * and `tsc` was clean (31 Aug 2026): a descent clause was lost on the
 * TypeScript side while Python kept it, and nothing could see it because no test
 * executed both. The Python suite pins a GOLDEN digest measured from this side,
 * which catches a Python-side change and cannot catch a TypeScript-side one —
 * exactly the direction that actually broke.
 *
 * So this test builds real trees, runs the shipped TypeScript in-process, shells
 * out to the project's own Python to run the shipped backend function, and
 * compares digests. It is deliberately NOT a golden-value test: a golden number
 * is one more copy of the answer, and copies are what this whole class of defect
 * is made of.
 */
import { describe, it, expect, beforeAll, afterAll } from 'vitest'
import fs from 'fs'
import os from 'os'
import path from 'path'
import { execFileSync } from 'child_process'
import { hostWorkspaceFingerprint } from '../main/helpers/workspace-fingerprint'

const REPO = path.resolve(__dirname, '..', '..', '..')
const BACKEND = path.join(REPO, 'Backend')

/** The interpreter that owns the backend's dependencies, or '' if absent. */
function pythonBul(): string {
  const adaylar = [
    path.join(BACKEND, 'venv', 'Scripts', 'python.exe'),
    path.join(BACKEND, 'venv', 'bin', 'python3'),
  ]
  for (const c of adaylar) if (fs.existsSync(c)) return c
  return ''
}

const PY = pythonBul()

/** Runs the SHIPPED backend implementation over `root`. */
function pythonParmakIzi(root: string): { entries: number; fingerprint: string } {
  const kod = [
    'import sys, json, hashlib, os',
    'sys.path.insert(0, os.path.join(os.getcwd(), "app"))',
    'from routes.auth_routes import _fingerprint_lines, _fingerprint_digest',
    'root = sys.argv[1]',
    'lines = _fingerprint_lines(root)',
    'print(json.dumps({"entries": len(lines), "fingerprint": _fingerprint_digest(lines)}))',
  ].join('\n')
  const out = execFileSync(PY, ['-c', kod, root], {
    cwd: BACKEND,
    encoding: 'utf8',
    env: { ...process.env, PYTHONUTF8: '1' },
  })
  return JSON.parse(out.trim().split('\n').pop() as string)
}

let kok = ''
const agac = (ad: string) => path.join(kok, ad)

beforeAll(() => {
  kok = fs.mkdtempSync(path.join(os.tmpdir(), 'gm-fp-'))
})

afterAll(() => {
  if (kok) fs.rmSync(kok, { recursive: true, force: true })
})

// The suite needs the backend venv. Skipping is loud rather than silent: a
// parity test that quietly disappears is worse than no parity test, because the
// green tick then means something it does not mean.
const varsaCalis = PY ? describe : describe.skip

// Her vaka Python'u ALT SUREC olarak baslatiyor; tam takim paralel kosarken bu
// varsayilan 5 sn'yi asiyor (olculdu: tek basina 3,5 sn, yuk altinda 8,4 sn).
// Zaman asimi burada bir arizanin degil, olcum aracinin maliyeti.
const SURE = 60000

varsaCalis('iki uygulama ayni agac icin ayni parmak izini uretir', () => {
  it('bos agac', () => {
    const d = agac('bos')
    fs.mkdirSync(d)
    expect(hostWorkspaceFingerprint(d)).toEqual(pythonParmakIzi(d))
  }, SURE)

  it('siradan Unity duzeni', () => {
    const d = agac('unity')
    fs.mkdirSync(path.join(d, 'Assets', 'Scripts'), { recursive: true })
    fs.mkdirSync(path.join(d, 'ProjectSettings'), { recursive: true })
    fs.writeFileSync(path.join(d, 'Assets', 'Scripts', 'Player.cs'), 'x')
    fs.writeFileSync(path.join(d, 'ProjectSettings', 'p.asset'), 'x')
    expect(hostWorkspaceFingerprint(d)).toEqual(pythonParmakIzi(d))
  }, SURE)

  it('derleme klasorleri listeleniyor ama icine INILMIYOR', () => {
    // `Library` iki tarafta da atlanmali. Bir taraf inerse ozetler ayrisir ve
    // dogru bir kurulum reddedilir; ayrica Editor o klasoru surekli yazdigi
    // icin iki ornek milisaniyelerle ayri alindiginda gurultu uretir.
    const d = agac('derleme')
    fs.mkdirSync(path.join(d, 'Library', 'derin'), { recursive: true })
    fs.writeFileSync(path.join(d, 'Library', 'derin', 'a.bin'), 'x')
    fs.mkdirSync(path.join(d, 'Assets'), { recursive: true })
    const ts = hostWorkspaceFingerprint(d)
    expect(ts).toEqual(pythonParmakIzi(d))
    // Icine inilseydi `Library/derin` bir satir olurdu; iki taraf da uretmiyor.
    expect(ts.entries).toBe(2)
  }, SURE)

  it('BMP disi ve ozel kullanim karakterleri — siralama farkinin ortaya ciktigi yer', () => {
    // JavaScript UTF-16 kod birimi, Python kod noktasi karsilastirir. U+1F600
    // vekil ciftle (D83D) baslar, U+E000 tek birimdir: D83D < E000 oldugu icin
    // naif bir JS siralamasi emojiyi one alir, Python ise sona. Bayt sirasi
    // ikisini de ayni yere koyar — bu test o korumanin bir sey korudugunun
    // kanitidir.
    const d = agac('unicode')
    fs.mkdirSync(path.join(d, '\u{1F600}-emoji'), { recursive: true })
    fs.mkdirSync(path.join(d, '-ozel'), { recursive: true })
    fs.writeFileSync(path.join(d, 'a.txt'), 'x')
    expect(hostWorkspaceFingerprint(d)).toEqual(pythonParmakIzi(d))
  }, SURE)

  it('4096 girdinin otesinde ayrisan agaclar AYNI ozeti uretmez', () => {
    // Eski `slice(0, 4096)` bunu tam tersine cevirmisti: iki farkli proje ayni
    // kabul ediliyordu (denetim bulgusu R5-01). Sinir kaldirildi.
    const yap = (ad: string, gecKalan: string) => {
      const d = agac(ad)
      fs.mkdirSync(d)
      for (let i = 0; i < 4100; i++) {
        fs.writeFileSync(path.join(d, `f${String(i).padStart(5, '0')}.txt`), 'x')
      }
      fs.writeFileSync(path.join(d, gecKalan), 'x')
      return d
    }
    const a = yap('capA', 'zz-yalniz-a.txt')
    const b = yap('capB', 'zz-yalniz-b.txt')

    const tsA = hostWorkspaceFingerprint(a)
    const tsB = hostWorkspaceFingerprint(b)
    expect(tsA).toEqual(pythonParmakIzi(a))
    expect(tsB).toEqual(pythonParmakIzi(b))
    // Asil iddia: gec siralanan tek bir dosya farki GORULUYOR.
    expect(tsA.fingerprint).not.toBe(tsB.fingerprint)
  }, SURE)

  it('sembolik bag icerigi degil KENDISI siniflandiriliyor', () => {
    // Iki taraf da bagi takip etmeden 'l' demeli. Biri takip ederse bir tarafta
    // 'd', digerinde 'l' cikar ve dogru agac reddedilir.
    const d = agac('bag')
    fs.mkdirSync(path.join(d, 'gercek'), { recursive: true })
    try {
      fs.symlinkSync(path.join(d, 'gercek'), path.join(d, 'bag'), 'junction')
    } catch {
      return   // ayricalik yoksa bu vaka olculemez; sessiz gecmek yerine cikiyoruz
    }
    expect(hostWorkspaceFingerprint(d)).toEqual(pythonParmakIzi(d))
  }, SURE)
})
