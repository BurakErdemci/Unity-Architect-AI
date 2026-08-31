/**
 * The two `gamachine-ws-fp-1` implementations must agree, and this is the only
 * thing that runs BOTH of them.
 *
 * The algorithm exists twice — `main/helpers/workspace-fingerprint.ts` and
 * `fingerprint_lines` in `Backend/app/workspace_fingerprint.py` — and Docker
 * startup compares their answers to refuse a container still serving an older
 * bind mount. Both failure directions are real: disagreeing about the same tree
 * refuses a correct setup, agreeing about different trees makes the guard
 * worthless.
 *
 * KNOWN LIMIT, and it is structural: this file runs both implementations on ONE
 * machine, while production runs the TypeScript one on the user's OS and the
 * Python one on Linux inside the container. A disagreement that only appears
 * across that boundary is invisible here. Two such defects have already shipped
 * past this suite — a junction, and then a FIFO and a Unix socket — and both
 * were found by bind-mounting a tree into a real container and comparing, not
 * by this test. Closing the gap in CI would mean running Docker in the frontend
 * job; that has not been done, so the boundary cases are measured by hand and
 * recorded in `kind`'s docstring on both sides.
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
import { hostWorkspaceFingerprint, fingerprintLines, direntKind } from '../main/helpers/workspace-fingerprint'

const REPO = path.resolve(__dirname, '..', '..', '..')
const BACKEND = path.join(REPO, 'Backend')

/**
 * ANY working Python 3, or '' if there is none.
 *
 * It used to accept only `Backend/venv/...`, and that made the whole suite
 * disappear from the gate: the frontend CI job installs Node and nothing else,
 * so `describe.skip` was selected, six cases reported "skipped", and `vitest`
 * stayed green (AUDIT R6-02, 31 Aug 2026). A parity test that does not run in
 * CI is not a gate.
 *
 * The venv is no longer needed. `Backend/app/workspace_fingerprint.py` imports
 * the standard library and nothing else — it was split out of
 * `routes/auth_routes.py`, which drags in FastAPI, precisely so a bare
 * interpreter can run it. So a PATH `python3` is enough, and CI has one.
 *
 * Candidates are probed by RUNNING them rather than by `existsSync`: on Windows
 * a bare `python` is often an App Execution Alias that exists as a file and
 * exits without an interpreter.
 */
function pythonBul(): string {
  const adaylar = [
    path.join(BACKEND, 'venv', 'Scripts', 'python.exe'),
    path.join(BACKEND, 'venv', 'bin', 'python3'),
    'python3',
    'python',
  ]
  for (const c of adaylar) {
    try {
      const v = execFileSync(c, ['-c', 'import sys; print(sys.version_info[0])'],
        { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] })
      if (v.trim() === '3') return c
    } catch {
      // Absent, or not an interpreter. Try the next one.
    }
  }
  return ''
}

const PY = pythonBul()

// In CI an absent interpreter is a BROKEN GATE, not an unmeasurable
// environment: the workflow installs Python on purpose, so if it is missing
// something regressed in the workflow and skipping would hide exactly that.
// Locally, skipping stays the right answer — a contributor without Python
// should not see a red suite for a tool they were never asked to install.
if (!PY && process.env.CI) {
  throw new Error(
    'No Python 3 found, but CI is set. This suite is the only thing that runs ' +
    'both fingerprint implementations, so a missing interpreter disables the ' +
    'check rather than passing it. Restore the Python setup step in the ' +
    'frontend job of .github/workflows/test.yml.')
}

/** Runs the SHIPPED backend implementation over `root`. */
function pythonParmakIzi(root: string): { entries: number; fingerprint: string } {
  const kod = [
    'import sys, json, os',
    'sys.path.insert(0, os.path.join(os.getcwd(), "app"))',
    'from workspace_fingerprint import fingerprint_lines, fingerprint_digest',
    'root = sys.argv[1]',
    'lines = fingerprint_lines(root)',
    'print(json.dumps({"entries": len(lines), "fingerprint": fingerprint_digest(lines)}))',
  ].join('\n')
  const out = execFileSync(PY, ['-c', kod, root], {
    cwd: BACKEND,
    encoding: 'utf8',
    env: { ...process.env, PYTHONUTF8: '1' },
  })
  return JSON.parse(out.trim().split('\n').pop() as string)
}

/**
 * The backend's `<relpath>\t<kind>` lines, not just their digest.
 *
 * Comparing digests alone cannot see WHAT was walked, and that is how the
 * previous link case passed while the property it named was false: both sides
 * followed the junction, so both digests moved together and the assertion was
 * happy (AUDIT R6-01). The line list is what makes "did anything outside the
 * root get in" answerable.
 */
function pythonSatirlar(root: string): string[] {
  const kod = [
    'import sys, json, os',
    'sys.path.insert(0, os.path.join(os.getcwd(), "app"))',
    'from workspace_fingerprint import fingerprint_lines',
    'print(json.dumps(fingerprint_lines(sys.argv[1])))',
  ].join('\n')
  const out = execFileSync(PY, ['-c', kod, root], {
    cwd: BACKEND,
    encoding: 'utf8',
    env: { ...process.env, PYTHONUTF8: '1' },
  })
  return JSON.parse(out.trim().split('\n').pop() as string)
}

/** The same lines from the Electron side, decoded for comparison. */
function tsSatirlar(root: string): string[] {
  return fingerprintLines(root).map((b) => b.toString('utf8'))
}

let kok = ''
const agac = (ad: string) => path.join(kok, ad)

beforeAll(() => {
  kok = fs.mkdtempSync(path.join(os.tmpdir(), 'gm-fp-'))
})

afterAll(() => {
  if (kok) fs.rmSync(kok, { recursive: true, force: true })
})

// The suite needs SOME Python 3 — no venv, no backend dependencies; the module
// it runs is stdlib-only for exactly this reason. Skipping is loud rather than
// silent, and under `CI` it does not skip at all: `pythonBul()` above throws,
// because a parity test that quietly disappears from the gate is worse than no
// parity test — the green tick then means something it does not mean.
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

  // ── baglantilar ────────────────────────────────────────────────────────────
  //
  // Bu iki vakanin oncesi, "bagin KENDISI siniflandiriliyor" baslikli ve iki
  // tarafin da bagi TAKIP ettigi hâlde yesil kalan tek bir vakaydi: yalniz iki
  // ozet karsilastiriliyordu, ikisi birlikte kaydigi icin fark gorunmuyordu
  // (AUDIT R6-01). Artik uretilen SATIRLAR karsilastiriliyor.
  //
  // Kural: duz klasor `d`, duz dosya `f`, BASKA HER SEY `o` — ve `o`nun icine
  // hic inilmiyor. Yani bir bag, neye bakarsa baksin `o`.
  //
  // Ayri bir `l` turu denendi ve gercek konteynere karsi olculdunce dustu
  // (31 Agu 2026): symlink ve junction'da anlasiyordu ama FIFO ve Unix
  // soketinde ana makine `l`, konteyner `o` diyordu. Sebep, Windows'un bu
  // nesneleri BIRBIRINDEN AYIRAMAMASI: Docker Desktop ucunu de reparse point
  // olarak sakliyor ve Node her etiketi isSymbolicLink() altinda topluyor.
  // Ayrimi bir taraf yapamiyorsa o ayrim parmak izine girmez.
  //
  // Bu vakalar junction kuruyor; FIFO/soket ayrimi bu dosyada OLCULEMEZ
  // (yukaridaki bilinen sinir), elle konteynerle olculdu.

  // Kurulamazsa ATLA, gecme. Onceki hâli `false` donuyordu ve cagiran `return`
  // ediyordu; bir `it` geri donunce vitest onu GECTI sayiyor, yani iki vaka da
  // TEK BIR iddia calistirmadan yesil rapor ediliyordu (AUDIT R7-01). Testin
  // basligi o durumda yanlis bir cumleye donusuyordu — bu serinin en sik
  // kusuru, ve bu kez onu duzelten testin kendisinde.
  //
  // POSIX'te 'junction' turu yok sayilir ve siradan bir symlink kurulur, yani
  // Ubuntu CI bu vakalari gercekten kosuyor. Atlama yalnizca ayricaligi olmayan
  // bir Windows makinesinde devreye giriyor.
  const junctionKur = (ctx: { skip: (not?: string) => void },
                       hedef: string, ad: string): void => {
    try {
      fs.symlinkSync(hedef, ad, 'junction')
    } catch (e) {
      ctx.skip(`baglanti kurulamadi (${(e as NodeJS.ErrnoException).code}); ` +
        'bu makinede junction/symlink ayricaligi yok')
    }
  }

  it("kok ICINE bakan bag: iki taraf da 'o' diyor ve icine INMIYOR", (ctx) => {
    const d = agac('bag-ic')
    fs.mkdirSync(path.join(d, 'gercek'), { recursive: true })
    fs.writeFileSync(path.join(d, 'gercek', 'a.txt'), 'x')
    junctionKur(ctx, path.join(d, 'gercek'), path.join(d, 'bag'))

    const ts = tsSatirlar(d)
    expect(ts).toEqual(pythonSatirlar(d))
    expect(ts).toContain('bag\to')
    // Hedef ICERIDE olmasina ragmen inilmiyor: kural hedefe degil bagin
    // kendisine bakiyor. Icerideki hedef zaten kendi adiyla listeleniyor
    // (`gercek/a.txt`), yani bilgi kaybi yok — yalniz ikinci kez sayilmiyor.
    expect(ts.filter((l) => l.startsWith('bag/'))).toEqual([])
    expect(ts).toContain('gercek/a.txt\tf')
  }, SURE)

  it("kok DISINA bakan bag: 'o' olarak listeleniyor, hedefi parmak izine GIRMIYOR", (ctx) => {
    // R6-01'in ta kendisi. `direntKind` baglari takip etmeye baslayinca bu
    // junction 'd' olarak siniflandi ve icine INILDI, yani mount DISINDAKI
    // dosyalar, tek iddiasi calisma alanini tarif etmek olan bir parmak izine
    // girdi — ustelik genisligi sinirsizdi.
    const d = agac('bag-dis')
    const disari = agac('bag-dis-hedef')
    fs.mkdirSync(d, { recursive: true })
    fs.mkdirSync(disari, { recursive: true })
    fs.writeFileSync(path.join(disari, 'sentinel.txt'), 'x')
    junctionKur(ctx, disari, path.join(d, 'kacis'))

    const ts = tsSatirlar(d)
    expect(ts).toEqual(pythonSatirlar(d))
    expect(ts).toContain('kacis\to')
    expect(ts.filter((l) => l.startsWith('kacis/'))).toEqual([])
    // Hedefin ADI da girmiyor: iki tarafta farkli yaziliyor (`C:\...` burada,
    // ulasilamaz `/mnt/host/c/...` konteynerde), yani hedefi ozete katmak
    // korumanin onlemek icin var oldugu uyusmazligi garanti ederdi.
    expect(ts.join('\n')).not.toContain('sentinel')
    expect(ts.join('\n')).not.toContain('bag-dis-hedef')
  }, SURE)
})

// Python GEREKTIRMEZ, bu yuzden `varsaCalis` disinda: her makinede ve CI'da kosar.
//
// Neden ayri: `direntKind`'in UNKNOWN dali hicbir testin ULASMADIGI bir daldi.
// Olculdu (31 Agu 2026) — o dala bir mutasyon uygulandi ('o' yerine 'd'
// dondurulup) ve yedi vakanin yedisi YESIL kaldi, cunku Windows'ta hizli yol
// zaten 'o' donduruyor ve fallback'e hic inilmiyor. Ulasilmayan bir dal,
// olculmemis bir daldir; d_type doldurmayan dosya sistemlerinde (bazi ag ve
// Linux dosya sistemleri) tam olarak orasi calisir.
describe('direntKind: dirent turu UNKNOWN geldiginde', () => {
  // Gercek bir junction'a bakan, ama uc sorunun ucune de false diyen bir dirent
  // — d_type doldurmayan bir dosya sisteminin urettigi seyin ta kendisi.
  const bilinmeyenDirent = (ad: string) => ({
    name: Buffer.from(ad),
    isSymbolicLink: () => false,
    isDirectory: () => false,
    isFile: () => false,
  }) as unknown as fs.Dirent<Buffer>

  it("bag oldugunu lstat ile bulup 'o' donuyor, 'd' degil", () => {
    const d = fs.mkdtempSync(path.join(os.tmpdir(), 'gm-unknown-'))
    try {
      fs.mkdirSync(path.join(d, 'gercek'))
      try {
        fs.symlinkSync(path.join(d, 'gercek'), path.join(d, 'bag'), 'junction')
      } catch {
        return   // ayricalik yoksa asagidaki duz klasor vakasi yine kosuyor
      }
      // 'd' donseydi bu girdinin ICINE INILIRDI; korunan sey bu.
      expect(direntKind(Buffer.from(d), bilinmeyenDirent('bag'))).toBe('o')
    } finally {
      fs.rmSync(d, { recursive: true, force: true })
    }
  })

  it("duz klasor ve duz dosya icin yine 'd' ve 'f' donuyor", () => {
    // Fallback'in yalniz 'o' uretmedigi de bir iddia: hepsini 'o' yapan bir
    // uygulama yukaridaki testi gecer ve dogru agaci reddederdi.
    const d = fs.mkdtempSync(path.join(os.tmpdir(), 'gm-unknown2-'))
    try {
      fs.mkdirSync(path.join(d, 'klasor'))
      fs.writeFileSync(path.join(d, 'dosya.txt'), 'x')
      expect(direntKind(Buffer.from(d), bilinmeyenDirent('klasor'))).toBe('d')
      expect(direntKind(Buffer.from(d), bilinmeyenDirent('dosya.txt'))).toBe('f')
      expect(direntKind(Buffer.from(d), bilinmeyenDirent('yok.txt'))).toBe('o')
    } finally {
      fs.rmSync(d, { recursive: true, force: true })
    }
  })
})
