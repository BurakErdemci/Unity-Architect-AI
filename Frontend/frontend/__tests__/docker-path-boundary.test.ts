/**
 * The renderer↔backend path boundary, exercised rather than read.
 *
 * Two defects live here and both were reproduced by probes on 31 Aug 2026:
 *
 *   D4-01  IntelliSense crossed the boundary untranslated in BOTH directions.
 *          `/lsp/completion|hover|definition` sent the absolute HOST path while
 *          their fourth sibling `/lsp/change` sent the workspace-relative
 *          spelling; the backend's `_abs()` keeps an absolute path untouched,
 *          so a container received `C:\...` and resolved nothing. The return
 *          leg was open too: a definition result and a clicked diagnostic carry
 *          the BACKEND's spelling and were handed straight to the host opener.
 *
 *   D4-04  The workspace save raced itself: two independent writers, each
 *          awaiting the host→backend mapping before posting, so selections
 *          A then B could land as B then A — database on A, UI on B.
 *
 * Nothing here asserts on source text. A "the file contains X" assertion has
 * produced a false green four times in this repo in one day, most recently in
 * the test written to close the previous instance, so every case below drives
 * the real provider / the real hook and reads what actually went out.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import {
  createLspBridge,
  hostOpenTarget,
  workspaceRelativePath,
  type LspContext,
} from '../renderer/components/home/EditorPanel';

const WS_HOST = 'C:\\host\\game';
const DOSYA_HOST = 'C:\\host\\game\\Assets\\Scripts\\Player.cs';
const DOSYA_GORELI = 'Assets/Scripts/Player.cs';
const WS_BACKEND = '/workspace';

const orijinalIpc = (window as any).ipc;
const orijinalFetch = global.fetch;

afterEach(() => {
  (window as any).ipc = orijinalIpc;
  global.fetch = orijinalFetch;
  delete (window as any).__csProvidersRegistered;
  vi.restoreAllMocks();
});

// --- sahte Monaco -----------------------------------------------------------

type Saglayicilar = { completion?: any; hover?: any; definition?: any };

const sahteMonaco = () => {
  const s: Saglayicilar = {};
  return {
    saglayicilar: s,
    monaco: {
      languages: {
        registerCompletionItemProvider: (_l: string, p: any) => { s.completion = p; },
        registerHoverProvider: (_l: string, p: any) => { s.hover = p; },
        registerDefinitionProvider: (_l: string, p: any) => { s.definition = p; },
      },
    },
  };
};

const sahteModel = { getValue: () => 'public class Player {}', getWordUntilPosition: () => ({ startColumn: 1, endColumn: 4 }) };
const konum = { lineNumber: 7, column: 12 };

/** Records every `/lsp/*` body and answers each endpoint from `cevaplar`. */
const fetchKaydedici = (cevaplar: Record<string, any> = {}) => {
  const gonderilen: Array<{ uc: string; body: any }> = [];
  global.fetch = vi.fn(async (url: any, init: any) => {
    const uc = String(url).split('/lsp/')[1];
    gonderilen.push({ uc, body: JSON.parse(init.body) });
    return { ok: true, json: async () => cevaplar[uc] ?? {} } as any;
  }) as any;
  return gonderilen;
};

const kopruKur = (ctx: Partial<LspContext>) => {
  const tam: LspContext = {
    apiUrl: 'http://localhost:8000',
    sessionToken: 'tok',
    openedFilePath: DOSYA_HOST,
    workspacePath: WS_HOST,
    ...ctx,
  };
  const { monaco, saglayicilar } = sahteMonaco();
  createLspBridge(() => tam).registerCsProviders(monaco);
  return { saglayicilar, ctx: tam };
};

describe('D4-01 giden yön: üç IntelliSense kardeşi de workspace-göreli yazım gönderir', () => {
  it('completion, hover ve definition aynı yolu gönderir — /lsp/change ile aynı yazım', async () => {
    // The sibling `/lsp/change` sends `getRelativePath(...)`; these three sent
    // the raw host path. A rule one call site follows and its siblings do not
    // is this repo's most expensive defect shape — hence one assertion over
    // all three, not three separate ones that can drift.
    const gonderilen = fetchKaydedici({ definition: {} });
    const { saglayicilar } = kopruKur({});

    await saglayicilar.completion.provideCompletionItems(sahteModel, konum, {}, undefined);
    await saglayicilar.hover.provideHover(sahteModel, konum, undefined);
    await saglayicilar.definition.provideDefinition(sahteModel, konum, undefined);

    expect(gonderilen.map(g => g.uc)).toEqual(['completion', 'hover', 'definition']);
    for (const g of gonderilen) {
      expect(g.body.path).toBe(DOSYA_GORELI);
    }
  });

  it('göreli yazım POSIX ayırıcı kullanır — konteyner Linux', () => {
    // `os.path.join('/workspace', 'Assets\\Player.cs')` inside the container is
    // a single file NAME containing backslashes, so a Windows host that kept
    // its own separators would still address nothing.
    expect(workspaceRelativePath(DOSYA_HOST, WS_HOST)).toBe(DOSYA_GORELI);
    expect(workspaceRelativePath('/host/game/Assets/Player.cs', '/host/game')).toBe('Assets/Player.cs');
  });

  it('workspace yokken mutlak yol korunur — bugünkü davranış', () => {
    // With no workspace the backend has no root to join to, and `_abs()` keeps
    // an absolute path as-is. Sending a basename here would make the backend
    // resolve some unrelated persisted root; this is the Docker-OFF path an
    // ordinary user hits when opening a loose file through the file picker.
    expect(workspaceRelativePath(DOSYA_HOST, null)).toBe(DOSYA_HOST);
  });
});

describe('D4-01 dönüş yönü: backend yazımı host yazımına çevrilir', () => {
  it('definition mutlak backend yolu döndürdüğünde dosya HOST yoluyla açılır', async () => {
    (window as any).ipc = {
      invoke: async (kanal: string, yol: string) => {
        expect(kanal).toBe('host-workspace-path');
        return yol.replace(WS_BACKEND, WS_HOST).replace(/\//g, '\\');
      },
    };
    fetchKaydedici({ definition: { location: { file: '/workspace/Assets/Enemy.cs' } } });
    const acilanlar: string[] = [];
    const { saglayicilar } = kopruKur({ openFile: (p) => { acilanlar.push(p); } });

    await saglayicilar.definition.provideDefinition(sahteModel, konum, undefined);

    expect(acilanlar).toEqual(['C:\\host\\game\\Assets\\Enemy.cs']);
  });

  it('çeviri null dönerse HİÇBİR dosya açılmaz — reddi zayıflatma', async () => {
    (window as any).ipc = { invoke: async () => '' };   // bridge says: no host answer
    fetchKaydedici({ definition: { location: { file: '/elsewhere/Enemy.cs' } } });
    const acilanlar: string[] = [];
    const { saglayicilar } = kopruKur({ openFile: (p) => { acilanlar.push(p); } });

    await saglayicilar.definition.provideDefinition(sahteModel, konum, undefined);

    expect(acilanlar).toEqual([]);
  });

  it('göreli yol köprüye HİÇ uğramaz — read-file onu host workspace ile birleştiriyor', async () => {
    let cagrildi = false;
    (window as any).ipc = { invoke: async () => { cagrildi = true; return ''; } };
    await expect(hostOpenTarget('Assets/Scripts/Player.cs')).resolves.toBe('Assets/Scripts/Player.cs');
    expect(cagrildi).toBe(false);
  });

  it('Docker KAPALI: mutlak yol kimlik çevirisinden aynen geçer', async () => {
    // The non-Docker main process answers both translation channels with the
    // argument. The same code runs for every ordinary user, so this is the case
    // a regression would actually cost something.
    (window as any).ipc = { invoke: async (_k: string, yol: string) => yol };
    await expect(hostOpenTarget(DOSYA_HOST)).resolves.toBe(DOSYA_HOST);
  });
});

// --- D4-04 ------------------------------------------------------------------

const gonderilenler: Array<{ url: string; body: any }> = [];
vi.mock('axios', () => ({
  default: {
    post: vi.fn(async (url: string, body: any) => { gonderilenler.push({ url, body }); return { data: {} }; }),
    get: vi.fn(async () => ({ data: {} })),
  },
}));

const KULLANICI = { id: 1, sessionToken: 'tok' } as any;
const API = 'http://localhost:8000';

/**
 * `useFileSystem` captures `window.ipc` at MODULE load, so the bridge has to be
 * in place before the import — hence the reset + dynamic import per test.
 */
const useFileSystemYukle = async (invoke: (kanal: string, ...a: any[]) => any) => {
  vi.resetModules();
  (window as any).ipc = { invoke };
  const mod = await import('../renderer/hooks/home/useFileSystem');
  return mod.useFileSystem;
};

const ertelenmis = <T,>() => {
  let coz!: (v: T) => void;
  const sozu = new Promise<T>((r) => { coz = r; });
  return { sozu, coz };
};

describe('D4-04 çalışma alanı kaydı kendisiyle yarışmaz', () => {
  beforeEach(() => { gonderilenler.length = 0; });

  it('eşleme yavaş kalan A için dönerse yazma B ile kalır', async () => {
    // The reported shape, and the ONE stage that produced it: both writers
    // awaited the host→backend mapping before posting, so the abandoned
    // selection could be the last write — database on A while the UI showed B,
    // neither side reporting an error. A is deliberately let through every
    // earlier step so this test fails when the guard in front of the POST is
    // the only thing missing.
    const gecikmeliA = ertelenmis<string>();
    const eslemeIstendi = ertelenmis<void>();
    const useFileSystem = await useFileSystemYukle(async (kanal: string, arg: string) => {
      if (kanal === 'path-exists') return true;
      if (kanal === 'read-directory') return [];
      if (kanal === 'backend-workspace-path') {
        if (arg !== 'C:\\host\\A') return '/workspace/B';
        eslemeIstendi.coz();
        return gecikmeliA.sozu;
      }
      return null;
    });

    const { result } = renderHook(() => useFileSystem(API, KULLANICI, () => {}));

    await act(async () => {
      const bittiA = result.current.selectWorkspace('C:\\host\\A');
      await eslemeIstendi.sozu;                       // A eşlemeyi bekliyor
      const bittiB = result.current.selectWorkspace('C:\\host\\B');
      await bittiB;
      gecikmeliA.coz('/workspace/A');                 // A geç cevabını alıyor
      await bittiA;
    });

    expect(gonderilenler.map(g => g.body.path)).toEqual(['/workspace/B']);
    await waitFor(() => expect(result.current.workspacePath).toBe('C:\\host\\B'));
  });

  it('geç dönen dosya ağacı B çalışma alanının üzerine yazmaz', async () => {
    // The same overlap one stage earlier: the directory listing is awaited too,
    // so A's tree could land in a UI that has already moved to B — a file list
    // belonging to a project nobody is in, with no error anywhere.
    const gecikmeliA = ertelenmis<any[]>();
    const okumaIstendi = ertelenmis<void>();
    const useFileSystem = await useFileSystemYukle(async (kanal: string, arg: string) => {
      if (kanal === 'path-exists') return true;
      if (kanal === 'read-directory') {
        if (arg !== 'C:\\host\\A') return [{ name: 'B.cs', path: 'B.cs', isDirectory: false }];
        okumaIstendi.coz();
        return gecikmeliA.sozu;
      }
      if (kanal === 'backend-workspace-path') return arg;
      return null;
    });

    const { result } = renderHook(() => useFileSystem(API, KULLANICI, () => {}));

    await act(async () => {
      const bittiA = result.current.selectWorkspace('C:\\host\\A');
      await okumaIstendi.sozu;
      const bittiB = result.current.selectWorkspace('C:\\host\\B');
      await bittiB;
      gecikmeliA.coz([{ name: 'A.cs', path: 'A.cs', isDirectory: false }]);
      await bittiA;
    });

    expect(result.current.fileTree.map((e: any) => e.name)).toEqual(['B.cs']);
  });

  it('geç dönen "klasör yok" cevabı yeni seçimi temizlemez', async () => {
    // Auto-restore of a workspace that has since been deleted overlaps a user
    // selection: without the guard the stale answer clears `workspacePath` and
    // warns about a folder the user never picked.
    const gecikmeliA = ertelenmis<boolean>();
    const varlikSoruldu = ertelenmis<void>();
    const useFileSystem = await useFileSystemYukle(async (kanal: string, arg: string) => {
      if (kanal === 'path-exists') {
        if (arg !== 'C:\\host\\silinmis') return true;
        varlikSoruldu.coz();
        return gecikmeliA.sozu;
      }
      if (kanal === 'read-directory') return [];
      if (kanal === 'backend-workspace-path') return arg;
      return null;
    });
    const uyarilar: string[] = [];
    const { result } = renderHook(() => useFileSystem(API, KULLANICI, (m: string) => { uyarilar.push(m); }));

    await act(async () => {
      const bittiA = result.current.selectWorkspace('C:\\host\\silinmis');
      await varlikSoruldu.sozu;
      const bittiB = result.current.selectWorkspace('C:\\host\\B');
      await bittiB;
      gecikmeliA.coz(false);
      await bittiA;
    });

    expect(result.current.workspacePath).toBe('C:\\host\\B');
    expect(uyarilar).toEqual([]);
  });

  it('her olağan seçim TEK bir yazma üretir', async () => {
    // There used to be a second writer in home.tsx on a `workspacePath` effect;
    // one selection produced two mappings and two posts of the same value.
    const useFileSystem = await useFileSystemYukle(async (kanal: string) => {
      if (kanal === 'path-exists') return true;
      if (kanal === 'read-directory') return [];
      if (kanal === 'backend-workspace-path') return '/workspace';
      return null;
    });
    const { result } = renderHook(() => useFileSystem(API, KULLANICI, () => {}));

    await act(async () => { await result.current.selectWorkspace(WS_HOST); });

    expect(gonderilenler).toHaveLength(1);
    expect(gonderilenler[0].body.path).toBe('/workspace');
  });

  it('adlandırılamayan klasör: kullanıcı uyarılır ve HİÇBİR şey gönderilmez', async () => {
    const useFileSystem = await useFileSystemYukle(async (kanal: string) => {
      if (kanal === 'path-exists') return true;
      if (kanal === 'read-directory') return [];
      if (kanal === 'backend-workspace-path') return '';   // outside the mount
      return null;
    });
    const uyarilar: Array<[string, string]> = [];
    const { result } = renderHook(() => useFileSystem(API, KULLANICI, (m: string, t: string) => { uyarilar.push([m, t]); }));

    await act(async () => { await result.current.selectWorkspace('C:\\baska\\yer'); });

    expect(gonderilenler).toEqual([]);
    expect(uyarilar.map(u => u[1])).toEqual(['warning']);
  });

  it('Docker KAPALI: host yolu olduğu gibi kaydedilir', async () => {
    const useFileSystem = await useFileSystemYukle(async (kanal: string, arg: string) => {
      if (kanal === 'path-exists') return true;
      if (kanal === 'read-directory') return [];
      if (kanal === 'backend-workspace-path') return arg;   // identity, non-Docker
      return null;
    });
    const { result } = renderHook(() => useFileSystem(API, KULLANICI, () => {}));

    await act(async () => { await result.current.selectWorkspace(WS_HOST); });

    expect(gonderilenler.map(g => g.body.path)).toEqual([WS_HOST]);
  });
});
