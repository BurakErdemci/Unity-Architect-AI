/**
 * "Olmamış bir şeye 'oldu' denmesin" — onay kartlarının DOĞRULUK testleri.
 *
 * Ürünün vaadi "model onaysız bir byte değiştiremez". Aynası da tutmalı: reddedilen
 * ya da hiç gönderilmemiş bir işlem kullanıcıya başarı gibi gösterilmemeli.
 *
 * İki kök, ikisi de 2026-07-29'da gerçek bileşenler mount edilerek ölçüldü:
 *
 * KÖK B — IPC yazma sonucu okunmuyordu. `ipc.invoke('write-file')` ASLA throw
 *   etmiyor; `{success:false, error}` dönüyor (main/background.ts:397-418) ve
 *   `isAllowedWorkspaceWriteFile` gerçekten reddediyor (ör. `Assets/Scripts`
 *   dışındaki bir `.cs`). ChatPanel sonucu atıp koşulsuz yeşil toast basıyordu;
 *   FileCreationApproval de `.catch()` sonrası koşulsuz `setDone` yapıp
 *   "İşlem Tamamlandı" kartında dosyayı "oluşturuldu" diye listeliyordu.
 *   (`.catch` hiç ateşlenmiyordu — throw yok.)
 *
 * KÖK A — karar teslimatı okunmuyordu. Boş `gateId` yolunda hiçbir istek
 *   gitmeden `failure = null` sayılıyor, ardından başarı toast'ı basılıyordu.
 *
 * Testler DOM'a bakıyor, çağrı sayısına değil: kullanıcının GÖRDÜĞÜ iddia ölçülür.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import React from 'react'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'

// Monaco jsdom'da gerçek editör açamaz; DiffViewer'ın ölçtüğümüz yanı onay
// butonunun ne yaptığı, gösterdiği metin değil.
vi.mock('@monaco-editor/react', () => ({
  __esModule: true,
  default: () => null,
  DiffEditor: () => null,
  Editor: () => null,
  // monaco-loader.ts modül yüklenirken `loader.config(...)` çağırıyor — stub
  // etmezsek import zinciri patlıyor (ölçüldü: "No loader export is defined").
  loader: { config: () => {}, init: () => Promise.resolve({}) },
}))

import { ChatPanel } from '../renderer/components/home/ChatPanel'
import { FileCreationApproval, PendingFile } from '../renderer/components/home/FileCreationApproval'
import { postMcpDecision, decisionToast } from '../renderer/hooks/home/gateResponse'
import { useMCPApproval, takeMcpGate } from '../renderer/hooks/home/useMCPApproval'
import { useChat } from '../renderer/hooks/home/useChat'
import { renderHook, act } from '@testing-library/react'
import axios from 'axios'

vi.mock('axios', () => {
  const post = vi.fn()
  const get = vi.fn()
  return { default: { post, get }, post, get }
})
const mockedAxios = axios as unknown as { post: ReturnType<typeof vi.fn>; get: ReturnType<typeof vi.fn> }

const API = 'http://127.0.0.1:8000'

/** IPC reddi — gerçek background.ts:406 metninin kendisi. */
const WRITE_DENIED = {
  success: false,
  error: 'Dosya yalnızca seçili workspace içindeki kod/metin dosyalarına yazılabilir (.cs için Assets/Scripts altı).',
}

const MSG = {
  id: 1,
  role: 'assistant' as const,
  content: 'merhaba',
  smells: [],
  timestamp: '2026-07-29T00:00:00Z',
}

const FILE: PendingFile = { name: 'Player.cs', code: 'class Player {}', suggestedPath: 'Player.cs' }

type PanelOverrides = Partial<Record<string, any>>

/**
 * ⚠️ ChatPanel.tsx:167'de `messages.length === 0 && !loading` erken return'ü var:
 * mesajsız fixture'da HİÇBİR kart render edilmiyor ve test sessizce "geçiyor".
 * O yüzden fixture her zaman bir mesaj taşır.
 */
const renderPanel = (overrides: PanelOverrides = {}) => {
  const showToast = vi.fn()
  const ipc = { invoke: vi.fn().mockResolvedValue({ success: true, path: '/ws/Player.cs' }) }
  const props: any = {
    messages: [MSG],
    activeConvId: 1,
    user: { id: 1, name: 'b', sessionToken: 'tok' },
    loading: false,
    clearHistory: vi.fn(),
    lang: 'tr',
    effectiveProvider: 'claude',
    thinkingLevel: 'auto',
    workspacePath: '/ws',
    handleExportToUnity: vi.fn(),
    pendingGenFiles: null,
    setPendingGenFiles: vi.fn(),
    pendingFix: null,
    setPendingFix: vi.fn(),
    openedFilePath: null,
    setCode: vi.fn(),
    refreshFileTree: vi.fn(),
    analyzeProject: vi.fn(),
    openFile: vi.fn(),
    sendMessage: vi.fn(),
    currentPlan: [],
    messagesEndRef: React.createRef<HTMLDivElement>(),
    ipc,
    showToast,
    diffFile: null,
    setDiffFile: vi.fn(),
    pendingDelete: null,
    setPendingDelete: vi.fn(),
    pendingCommand: null,
    setPendingCommand: vi.fn(),
    onApproveCommand: vi.fn().mockResolvedValue(null),
    pendingQuestion: null,
    setPendingQuestion: vi.fn(),
    onAnswerQuestion: vi.fn(),
    deleteFile: vi.fn(),
    setIsTerminalOpen: vi.fn(),
    ...overrides,
  }
  render(React.createElement(ChatPanel, props))
  // props.showToast döner (yerel değil): çağıran kendi toast'ını geçirebilsin.
  return { showToast: props.showToast, ipc, props }
}

/** Kullanıcıya basılmış YEŞİL/başarı iddiası var mı. */
const successToasts = (showToast: ReturnType<typeof vi.fn>) =>
  showToast.mock.calls.filter(([, type]) => type === 'success')

/** Basılmış tüm toast metinleri, tek dizgede. */
const toastText = (showToast: ReturnType<typeof vi.fn>) =>
  showToast.mock.calls.map(c => String(c[0])).join('|')

/**
 * ⚠️ Ölçülmüş tuzak (bu testleri yazarken): `await waitFor(() =>
 * expect(queryByText(X)).toBeNull())` DÜZELTME OLMADAN DA geçiyor — waitFor ilk
 * denemede başarılı olursa hemen döner ve o an X henüz render edilmemiştir.
 * "Olumsuz" bir iddiayı ölçmek için önce durumun YERLEŞTİĞİNİ kanıtlayan pozitif
 * bir sinyal beklenmeli. Bu yardımcı, çözümü test kontrolünde tutuyor:
 * söz verilen değer act() içinde çözülür, dolayısıyla React commit'i garanti.
 */
const deferred = <T,>() => {
  let resolve!: (v: T) => void
  const promise = new Promise<T>(r => { resolve = r })
  return { promise, resolve }
}

beforeEach(() => {
  mockedAxios.post.mockReset()
  mockedAxios.get.mockReset()
  vi.spyOn(console, 'error').mockImplementation(() => {})
  vi.spyOn(console, 'warn').mockImplementation(() => {})
  ;(window as any).__API__ = API
  delete (window as any).__mcpWriteGate
  delete (window as any).__mcpDeleteGate
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

// ── KÖK B · yerel (API) dosya yazımı ────────────────────────────────────────
describe('KÖK B · ChatPanel yerel dosya yazımı — reddedilen yazım "oluşturuldu" denmez', () => {
  it('write-file {success:false} → "İşlem Tamamlandı" kartı ÇIKMAZ', async () => {
    const { showToast, ipc } = renderPanel({
      pendingGenFiles: { files: [FILE], messageId: 1 },
    })
    ipc.invoke.mockResolvedValue(WRITE_DENIED)

    fireEvent.click(screen.getByText('Uygula'))

    // Önce durumun yerleştiğini kanıtla (bkz. `deferred` yorumu), sonra olumsuz iddia.
    await screen.findByText(/yazılamadı/)
    expect(screen.queryByText('İşlem Tamamlandı')).toBeNull()
    expect(successToasts(showToast)).toHaveLength(0)
  })

  it('write-file {success:false} → kullanıcı NEDENİ görür (backend mesajı)', async () => {
    const { showToast, ipc } = renderPanel({
      pendingGenFiles: { files: [FILE], messageId: 1 },
    })
    ipc.invoke.mockResolvedValue(WRITE_DENIED)

    fireEvent.click(screen.getByText('Uygula'))

    await waitFor(() => expect(showToast).toHaveBeenCalled())
    const [msg, type] = showToast.mock.calls[0]
    expect(type).toBe('error')
    // Ham `error` alanı taşınmalı: "bir hata oldu" kullanıcıya ne yapacağını söylemiyor.
    expect(String(msg)).toContain('workspace')
  })

  it('KARŞI YÖN: write-file {success:true} → kart hâlâ "İşlem Tamamlandı" der', async () => {
    // Testi gevşetmediğimizin kanıtı: başarı yolu bozulmadı.
    const { ipc } = renderPanel({ pendingGenFiles: { files: [FILE], messageId: 1 } })
    ipc.invoke.mockResolvedValue({ success: true, path: '/ws/Player.cs' })

    fireEvent.click(screen.getByText('Uygula'))

    expect(await screen.findByText('İşlem Tamamlandı')).toBeTruthy()
  })

  it('"Tümünü Onayla" yolunda da reddedilen yazım başarı sayılmaz', async () => {
    const { showToast, ipc } = renderPanel({
      pendingGenFiles: { files: [FILE], messageId: 1 },
    })
    ipc.invoke.mockResolvedValue(WRITE_DENIED)

    fireEvent.click(screen.getByText('Tümünü Onayla'))

    await screen.findByText(/yazılamadı/)
    expect(screen.queryByText('İşlem Tamamlandı')).toBeNull()
    expect(successToasts(showToast)).toHaveLength(0)
  })

  it('DiffViewer yerel yolu: yazım reddedilince "Dosya güncellendi" BASILMAZ', async () => {
    const { showToast, ipc } = renderPanel({
      openedFilePath: 'Player.cs',
      pendingFix: {
        messageId: 1,
        applied: false,
        data: { original_code: 'a', fixed_code: 'b', explanation: 'x', editor_hint: 'Player.cs' },
      },
    })
    ipc.invoke.mockResolvedValue(WRITE_DENIED)

    fireEvent.click(screen.getByText('Kabul Et'))

    await waitFor(() => expect(showToast).toHaveBeenCalled())
    expect(successToasts(showToast)).toHaveLength(0)
    expect(showToast.mock.calls.map(c => String(c[0])).join('|')).not.toContain('Dosya güncellendi')
  })

  it('KARŞI YÖN: DiffViewer yerel yolu başarıda hâlâ başarı toast\'ı basar', async () => {
    const { showToast, ipc } = renderPanel({
      openedFilePath: 'Player.cs',
      pendingFix: {
        messageId: 1,
        applied: false,
        data: { original_code: 'a', fixed_code: 'b', explanation: 'x', editor_hint: 'Player.cs' },
      },
    })
    ipc.invoke.mockResolvedValue({ success: true, path: '/ws/Player.cs' })

    fireEvent.click(screen.getByText('Kabul Et'))

    await waitFor(() => expect(successToasts(showToast)).toHaveLength(1))
  })
})

// ── KÖK B · FileCreationApproval sözleşmesi ─────────────────────────────────
describe('KÖK B · FileCreationApproval — setDone yalnız GERÇEK başarıda', () => {
  const mount = (handlers: Partial<Record<string, any>> = {}) =>
    render(
      React.createElement(FileCreationApproval, {
        files: [FILE],
        autoAccept: false,
        setDiffFile: vi.fn(),
        onOpenFile: vi.fn(),
        onSkipOne: vi.fn(),
        onDone: vi.fn(),
        onAcceptOne: vi.fn().mockResolvedValue(true),
        onAcceptAll: vi.fn().mockResolvedValue(true),
        ...handlers,
      } as any),
    )

  it('onAcceptOne false dönerse "İşlem Tamamlandı" gösterilmez', async () => {
    const d = deferred<boolean>()
    mount({ onAcceptOne: vi.fn(() => d.promise) })
    fireEvent.click(screen.getByText('Uygula'))
    await act(async () => { d.resolve(false) })
    expect(screen.queryByText('İşlem Tamamlandı')).toBeNull()
  })

  it('onAcceptOne reject ederse de gösterilmez (eski `.catch` yolu)', async () => {
    let reject!: (e: unknown) => void
    const promise = new Promise<boolean>((_, r) => { reject = r })
    mount({ onAcceptOne: vi.fn(() => promise) })
    fireEvent.click(screen.getByText('Uygula'))
    await act(async () => { reject(new Error('EACCES')) })
    expect(screen.queryByText('İşlem Tamamlandı')).toBeNull()
  })

  it('başarısızlıkta kullanıcı KARTTA da bir iz görür (sessiz kalmaz)', async () => {
    // Sadece "başarı deme" yetmez: kart bir şey söylemeli, yoksa kullanıcı
    // butona bastığını ve hiçbir şey olmadığını düşünür.
    mount({ onAcceptOne: vi.fn().mockResolvedValue(false) })
    fireEvent.click(screen.getByText('Uygula'))
    expect(await screen.findByText(/yazılamadı/)).toBeTruthy()
  })

  it('onAcceptAll false dönerse "İşlem Tamamlandı" gösterilmez', async () => {
    const d = deferred<boolean>()
    mount({ onAcceptAll: vi.fn(() => d.promise) })
    fireEvent.click(screen.getByText('Tümünü Onayla'))
    await act(async () => { d.resolve(false) })
    expect(screen.queryByText('İşlem Tamamlandı')).toBeNull()
    expect(screen.getByText(/yazılamadı/)).toBeTruthy()
  })

  it('KARŞI YÖN: true dönünce dosya "oluşturuldu" listesinde görünür', async () => {
    mount({ onAcceptOne: vi.fn().mockResolvedValue(true) })
    fireEvent.click(screen.getByText('Uygula'))
    expect(await screen.findByText('İşlem Tamamlandı')).toBeTruthy()
    expect(screen.getAllByText('Player.cs').length).toBeGreaterThan(0)
  })
})

// ── KÖK A · boş gateId ──────────────────────────────────────────────────────
describe('KÖK A · boş gateId — istek gitmeden başarı iddia edilmez', () => {
  it('postMcpDecision boş gateId ile istek GÖNDERMEZ ama başarı da DÖNMEZ', async () => {
    const fetchSpy = vi.fn()
    vi.stubGlobal('fetch', fetchSpy)

    const failure = await postMcpDecision(API, '', true, 'tok')

    expect(fetchSpy).not.toHaveBeenCalled()
    expect(failure).not.toBeNull()
    expect(decisionToast(failure, '✅ Dosya oluşturuldu').type).not.toBe('success')
  })

  it('boş gateId KESİN başarısızlıktır — "belirsiz" değil', async () => {
    // Hiçbir istek gitmedi: işlemin yapılmadığı kesin. Belirsize katlamak
    // kullanıcıyı boşuna durum kontrolüne yollardı.
    const failure = await postMcpDecision(API, '', true, 'tok')
    expect(failure?.uncertain).toBeFalsy()
  })

  it('MCP oluşturma kartı: gate yokken yeşil toast basılmaz', async () => {
    const fetchSpy = vi.fn()
    vi.stubGlobal('fetch', fetchSpy)
    delete (window as any).__mcpWriteGate

    const { showToast } = renderPanel({ pendingGenFiles: { files: [FILE], messageId: -999 } })
    fireEvent.click(screen.getByText('Uygula'))

    await waitFor(() => expect(showToast).toHaveBeenCalled())
    expect(successToasts(showToast)).toHaveLength(0)
  })

  it('MCP silme kartı: gate yokken "Dosya silindi" denmez', async () => {
    const fetchSpy = vi.fn()
    vi.stubGlobal('fetch', fetchSpy)
    delete (window as any).__mcpDeleteGate

    const { showToast } = renderPanel({ pendingDelete: { path: 'Player.cs', messageId: -999 } })
    fireEvent.click(screen.getByText('Evet, Dosyayı Sil'))

    await waitFor(() => expect(showToast).toHaveBeenCalled())
    expect(showToast.mock.calls.map(c => String(c[0])).join('|')).not.toContain('Dosya silindi')
  })
})

// ── KÖK A · komut onayı ─────────────────────────────────────────────────────
describe('KÖK A · komut onay kartı — iletilmemiş onay "çalışıyor" demez', () => {
  const failure = { message: 'Onayınız iletilemedi.', type: 'warning' as const }

  it('onApproveCommand başarısız dönerse "çalışıyor..." BASILMAZ', async () => {
    const d = deferred<any>()
    const onApproveCommand = vi.fn(() => d.promise)
    const { showToast } = renderPanel({
      pendingCommand: { command: 'ls', gateId: 'g1', messageId: 1 },
      onApproveCommand,
    })

    fireEvent.click(screen.getByText('Komutu Çalıştır'))
    expect(onApproveCommand).toHaveBeenCalledWith('g1', true)
    await act(async () => { d.resolve(failure) })

    // useChat.approveCommand hata mesajını KENDİ basıyor; buradaki tek iddia
    // "başarı" olmamalı — aksi halde sarı "iletilemedi" ile yeşil "çalışıyor"
    // aynı anda ekranda durur (Toast.tsx:32 toast'ları diziye EKLİYOR).
    expect(successToasts(showToast)).toHaveLength(0)
  })

  it('iptal yolunda da iletilmemiş karar "iptal edildi" demez', async () => {
    const d = deferred<any>()
    const onApproveCommand = vi.fn(() => d.promise)
    const { showToast } = renderPanel({
      pendingCommand: { command: 'ls', gateId: 'g1', messageId: 1 },
      onApproveCommand,
    })

    fireEvent.click(screen.getByText('İptal'))
    expect(onApproveCommand).toHaveBeenCalledWith('g1', false)
    await act(async () => { d.resolve(failure) })

    expect(toastText(showToast)).not.toContain('iptal edildi')
  })

  it('KARŞI YÖN: onay iletildiyse "çalışıyor..." hâlâ basılır', async () => {
    const d = deferred<any>()
    const { showToast } = renderPanel({
      pendingCommand: { command: 'ls', gateId: 'g1', messageId: 1 },
      onApproveCommand: vi.fn(() => d.promise),
    })

    fireEvent.click(screen.getByText('Komutu Çalıştır'))
    await act(async () => { d.resolve(null) })

    expect(successToasts(showToast)).toHaveLength(1)
    expect(toastText(showToast)).toContain('çalışıyor')
  })

  /**
   * Yukarıdaki testler `onApproveCommand`'ı MOCK'luyor; gerçek bağlantıyı
   * (home.tsx:572 → `chat.approveCommand`) ölçmüyorlar. Mutasyonla kanıtlandı:
   * `useChat.approveCommand` başarısızlığı DÖNDÜRMEZ hâline getirildiğinde
   * 22 testin HİÇBİRİ kırılmıyordu. Bu test o dikişi kapatıyor — iki parça
   * ayrı ayrı doğru olup birleşimi yanlış olabiliyor.
   */
  it('GERÇEK BAĞLANTI: useChat.approveCommand + kart — gate düşmüşse yeşil toast yok', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true, status: 200, json: async () => ({ status: 'gate_not_found' }),
    }))
    const showToast = vi.fn()
    const { result } = renderHook(() =>
      useChat(
        API,
        { id: 1, name: 'b', sessionToken: 'tok' } as any,
        { provider_type: 'api' } as any,
        null,
        showToast,
        vi.fn(),
        (n: string) => n,
      ),
    )

    renderPanel({
      showToast,
      pendingCommand: { command: 'ls', gateId: 'g1', messageId: 1 },
      onApproveCommand: result.current.approveCommand,
    })

    await act(async () => { fireEvent.click(screen.getByText('Komutu Çalıştır')) })

    // Tam olarak BİR mesaj: useChat'in uyarısı. Kart ikinci (yeşil) bir iddia
    // eklerse kullanıcı sarı "iletilemedi" ile yeşil "çalışıyor"u aynı anda
    // görür — Toast.tsx:32 toast'ları diziye EKLİYOR, üzerine yazmıyor.
    expect(successToasts(showToast)).toHaveLength(0)
    expect(showToast).toHaveBeenCalledTimes(1)
  })
})

// ── KÖK A · gate kimliğinin yazılma SIRASI ve temizliği ─────────────────────
describe('KÖK A · MCP gate kimliği — kart görünmeden ÖNCE yazılır, karardan SONRA silinir', () => {
  const setupPoll = (pending: Record<string, any>, setters: Record<string, any>) => {
    mockedAxios.get.mockResolvedValue({ data: { pending } })
    return renderHook(() =>
      useMCPApproval({
        API,
        enabled: false,
        loading: false,
        setPendingGenFiles: vi.fn(),
        setPendingDelete: vi.fn(),
        setPendingCommand: vi.fn(),
        setPendingFix: vi.fn(),
        showToast: vi.fn(),
        ...setters,
      } as any),
    )
  }

  it('delete_file: setPendingDelete çağrıldığı ANDA gate kimliği yazılmış olmalı', async () => {
    // Şu an sıra ters (useMCPApproval.ts:101-103) ve yalnız React batching
    // kurtarıyor — batching'e bağlı doğruluk, doğruluk değildir.
    let gateAtRender: unknown = 'HİÇ-ÇAĞRILMADI'
    const setPendingDelete = vi.fn(() => { gateAtRender = (window as any).__mcpDeleteGate })

    const { result } = setupPoll(
      { 'del-1': { tool: 'delete_file', params: { path: 'Player.cs' } } },
      { setPendingDelete },
    )
    await act(async () => { await (result.current as any).poll?.() })

    expect(setPendingDelete).toHaveBeenCalled()
    expect(gateAtRender).toBe('del-1')
  })

  it('takeMcpGate okur VE siler — bayat kimlik ikinci karara taşınmaz', () => {
    ;(window as any).__mcpDeleteGate = 'del-1'
    expect(takeMcpGate('delete')).toBe('del-1')
    expect(takeMcpGate('delete')).toBe('')
  })

  it('gate hiç yoksa takeMcpGate boş string döner (undefined sızdırmaz)', () => {
    delete (window as any).__mcpWriteGate
    expect(takeMcpGate('write')).toBe('')
  })

  it('MCP kararından sonra global temizlenir', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ status: 'ok' }) }))
    ;(window as any).__mcpWriteGate = 'w-1'

    const { showToast } = renderPanel({ pendingGenFiles: { files: [FILE], messageId: -999 } })
    fireEvent.click(screen.getByText('Uygula'))

    await waitFor(() => expect(showToast).toHaveBeenCalled())
    expect((window as any).__mcpWriteGate).toBeFalsy()
  })
})
