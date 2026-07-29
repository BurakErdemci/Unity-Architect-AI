/**
 * Onay kartının TESLİM yolu — kart kullanıcının EKRANINA geliyor mu?
 *
 * Bu dosya, kapının kendisini değil kapıdan öncesini ölçüyor. Ayrım önemli:
 * kart hiç gelmezse köprü 180 sn bekleyip reddediyor (`approval_bridge.py:115`),
 * yani ürün "güvenli" görünür ama KULLANILAMAZ olur. unityMCP mutasyon kapısı
 * sunucuya konmadan önce bu yolun düzelmesi gerekiyor, çünkü kapı konulduğu an
 * bugün hiç kapıya uğramayan 8 sağlayıcı da uğramaya başlıyor.
 *
 * İki kusur 2026-07-29'da kaynaktan ölçüldü:
 *
 *  D1 — polling sağlayıcıya VE `chat.loading`'e bağlıydı
 *       (`home.tsx:94-95` → `useMCPApproval.ts:157`). `effectiveProvider ===
 *       'subscription'` olmayan her yolda kart hiç gelmiyordu; CLI sağlayıcıları
 *       sohbet "idle" görünürken de araç çağırdığı için `loading` koşulu abonelik
 *       yolunda bile kart düşürüyordu.
 *
 *  D2 — `pendingFix` (VAR OLAN dosyanın değiştirilmesi) hiçbir yerde render
 *       edilmiyordu. Hook kartı `messageId: -999` ile kuruyor
 *       (`useMCPApproval.ts:124`), ChatPanel ise `pendingFix`i yalnız
 *       `messageId === msg.id` iken çiziyordu; `pendingGenFiles`/`pendingDelete`/
 *       `pendingCommand`'ın aksine `-999` dalı YOKTU. Ölü kod değil: köprü
 *       dosya varsa `original`ı DOLU gönderiyor (`file_tools.py:50-54`,
 *       `unityai_cli.py:80-93` ve `cmd_bash`'in dosya-yazma dalı) ve hook
 *       `original` doluysa `setPendingFix`e sapıyor. Yani "mevcut bir .cs
 *       dosyasını düzenle" isteği kart üretmeden zaman aşımına düşüyordu.
 *
 * Testler iki YÖNÜ de ölçüyor. Bu depoda kapıların yalnız "çok dar değil" yönü
 * sınandığı için üç ayrı arıza üretildi; burada "çok geniş değil" yönü de var
 * (kapalıyken polling YAPILMAMALI).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import React from 'react'
import { render, screen, cleanup, renderHook, act } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

// Monaco jsdom'da gerçek editör açamaz; ölçtüğümüz şey diff'in görüntüsü değil
// kartın VARLIĞI ve butonunun ne yaptığı.
vi.mock('@monaco-editor/react', () => ({
  __esModule: true,
  default: () => null,
  DiffEditor: () => null,
  Editor: () => null,
  loader: { config: () => {}, init: () => Promise.resolve({}) },
}))

vi.mock('axios', () => {
  const post = vi.fn()
  const get = vi.fn()
  return { default: { post, get }, post, get }
})

import axios from 'axios'
import { ChatPanel } from '../renderer/components/home/ChatPanel'
import { useMCPApproval } from '../renderer/hooks/home/useMCPApproval'

const mockedAxios = axios as unknown as { post: ReturnType<typeof vi.fn>; get: ReturnType<typeof vi.fn> }

const API = 'http://127.0.0.1:8000'

/** MCP kartlarının bağlandığı sanal mesaj kimliği (useMCPApproval.ts:29). */
const MCP_MSG_ID = -999

const MSG = {
  id: 1,
  role: 'assistant' as const,
  content: 'merhaba',
  smells: [],
  timestamp: '2026-07-29T00:00:00Z',
}

/** Köprünün var olan bir dosya için ürettiği kart: `original` DOLU. */
const EXISTING_FILE_EDIT = {
  messageId: MCP_MSG_ID,
  applied: false,
  gateId: 'gate123abc',
  data: {
    original_code: 'class Player {}',
    fixed_code: 'class Player { void Jump() {} }',
    explanation: 'MCP: Assets/Scripts/Player.cs güncelleniyor',
    editor_hint: 'Assets/Scripts/Player.cs',
  },
}

/**
 * ⚠️ ChatPanel.tsx'te `messages.length === 0 && !loading` erken return'ü var:
 * mesajsız fixture'da hiçbir kart render edilmiyor ve test sessizce "geçiyor".
 * Fixture bu yüzden her zaman bir mesaj taşır.
 */
const renderPanel = (overrides: Record<string, any> = {}) => {
  const showToast = vi.fn()
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
    ipc: { invoke: vi.fn().mockResolvedValue({ success: true }) },
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
  return { props, showToast: props.showToast }
}

const hookParams = (over: Record<string, any> = {}) => ({
  API,
  enabled: true,
  setPendingGenFiles: vi.fn(),
  setPendingDelete: vi.fn(),
  setPendingCommand: vi.fn(),
  setPendingFix: vi.fn(),
  ...over,
})

beforeEach(() => {
  mockedAxios.get.mockReset()
  mockedAxios.post.mockReset()
  mockedAxios.get.mockResolvedValue({ data: { pending: {} } })
  vi.spyOn(console, 'error').mockImplementation(() => {})
  vi.spyOn(console, 'warn').mockImplementation(() => {})
  ;(window as any).__API__ = API
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

// ── D2 · var olan dosyanın düzenlenmesi ekrana geliyor mu ───────────────────
describe('D2 · MCP "mevcut dosyayı düzenle" kartı ekrana gelir', () => {
  it('pendingFix messageId=-999 iken kart RENDER EDİLİR', () => {
    renderPanel({ pendingFix: EXISTING_FILE_EDIT })

    // Kartın varlığının kanıtı onay butonu: DiffViewer'ın kendisi (Monaco)
    // stub'lı, ama aksiyon çubuğu gerçek bileşenin kendisi.
    expect(screen.queryByText('Kabul Et')).not.toBeNull()
    expect(screen.queryByText('Reddet')).not.toBeNull()
  })

  it('karttaki onay GERÇEKTEN gate\'e gider — sadece görünmek yetmez', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ status: 'ok' }) })
    vi.stubGlobal('fetch', fetchMock)

    renderPanel({ pendingFix: EXISTING_FILE_EDIT })
    await act(async () => { screen.getByText('Kabul Et').click() })

    // Kart görünüp butonu ölü olsaydı yukarıdaki test yeşil, ürün bozuk olurdu.
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(String(fetchMock.mock.calls[0][0])).toContain(`/mcp-approval-respond/${EXISTING_FILE_EDIT.gateId}`)
  })

  it('pendingFix yokken kart ÇIKMAZ — kapının çok geniş olmadığının kanıtı', () => {
    renderPanel({ pendingFix: null })
    expect(screen.queryByText('Kabul Et')).toBeNull()
  })
})

// ── D3 · erken return'ler kartı yutmuyor ────────────────────────────────────
describe('D3 · ChatPanel\'in erken return\'leri MCP kartını yutmaz', () => {
  /**
   * Köprü ürünün sohbet durumundan bağımsız çalışıyor: kart, konuşma açılmadan
   * ya da mesaj listesi boşken de gelebiliyor. ChatPanel'in iki erken return'ü
   * (`!activeConvId`, `messages.length === 0 && !loading`) o anda kartı hiç
   * çizmiyordu — kullanıcı hiçbir şey görmeden istek 180 sn'de reddediliyordu.
   */
  it('konuşma açık değilken bile kart gelir', () => {
    renderPanel({ activeConvId: null, pendingFix: EXISTING_FILE_EDIT })
    expect(screen.queryByText('Kabul Et')).not.toBeNull()
  })

  it('mesaj listesi boşken bile kart gelir', () => {
    renderPanel({ messages: [], loading: false, pendingFix: EXISTING_FILE_EDIT })
    expect(screen.queryByText('Kabul Et')).not.toBeNull()
  })

  it('kart YOKKEN konuşmasız hâl hâlâ boş ekran — ters yön', () => {
    renderPanel({ activeConvId: null, pendingFix: null })
    expect(screen.queryByText('Kabul Et')).toBeNull()
  })
})

// ── D1 · polling sağlayıcıdan ve loading'den bağımsız ───────────────────────
describe('D1 · kart yoklaması sağlayıcıdan ve sohbet durumundan bağımsızdır', () => {
  it('sohbet BOŞTAYKEN de yoklama yapar', async () => {
    vi.useFakeTimers()
    renderHook(() => useMCPApproval(hookParams() as any))

    await act(async () => { await vi.advanceTimersByTimeAsync(1200) })

    // Eski davranış: `loading` false olduğu için setInterval hiç kurulmuyordu.
    // CLI sağlayıcıları sohbet idle görünürken araç çağırdığı için kart ölüyordu.
    expect(mockedAxios.get).toHaveBeenCalled()
    expect(String(mockedAxios.get.mock.calls[0][0])).toContain('/mcp-pending')
  })

  it('ilk yoklama bir saniye BEKLEMEZ', async () => {
    vi.useFakeTimers()
    renderHook(() => useMCPApproval(hookParams() as any))

    // Köprü ürün penceresinden bağımsız çalışıyor: mount anında zaten açık bir
    // gate olabilir. Yalnız setInterval'e güvenmek onu bir tam saniye
    // geciktirirdi.
    await act(async () => { await vi.advanceTimersByTimeAsync(0) })

    expect(mockedAxios.get).toHaveBeenCalledTimes(1)
  })

  it('enabled=false iken YOKLAMA YAPMAZ — ters yön', async () => {
    vi.useFakeTimers()
    renderHook(() => useMCPApproval(hookParams({ enabled: false }) as any))

    await act(async () => { await vi.advanceTimersByTimeAsync(5000) })

    // `enabled` artık sağlayıcı değil "backend hazır + token kurulu" demek.
    // Kurulmadan yoklamak her saniye sessiz 401 üretirdi.
    expect(mockedAxios.get).not.toHaveBeenCalled()
  })
})

// ── Kablolama tripwire'ı ────────────────────────────────────────────────────
describe('kablolama · çağrı yeri kartı sağlayıcıya geri bağlamaz', () => {
  /**
   * ⚠️ Bunun NE OLMADIĞI: doğruluk kanıtı değil. home.tsx'i mount etmek
   * (Electron IPC, auth, workspace, Monaco) bu suite'te makul değil, o yüzden
   * ölçülen şey çağrı yerinin METNİ. Yaptığı tek şey sessiz bir geri dönüşü
   * gürültülü yapmak — kütük pin'iyle aynı sınıf araç, aynı sınırla.
   */
  it('home.tsx içindeki useMCPApproval çağrısında provider/loading koşulu yok', () => {
    const src = readFileSync(join(__dirname, '..', 'renderer', 'pages', 'home.tsx'), 'utf-8')
    const start = src.indexOf('useMCPApproval({')
    expect(start, 'home.tsx artık useMCPApproval çağırmıyor — bu testin öncülü çöktü').toBeGreaterThan(-1)

    // Çağrının kapanışına kadar olan blok: süslü parantezleri sayarak.
    let depth = 0
    let end = start
    for (let i = src.indexOf('{', start); i < src.length; i++) {
      if (src[i] === '{') depth++
      else if (src[i] === '}') { depth--; if (depth === 0) { end = i; break } }
    }
    const call = src.slice(start, end + 1)

    expect(call).not.toContain('effectiveProvider')
    expect(call).not.toContain('subscription')
    expect(call).not.toContain('loading')
  })
})
