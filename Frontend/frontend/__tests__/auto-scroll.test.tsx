/**
 * Auto-scroll must not override where the user is reading.
 *
 * The fault (measured in `home.tsx:318` before the fix): a `useEffect` called
 * `scrollIntoView` UNCONDITIONALLY whenever `chat.messages`/`chat.loading`
 * changed. Scrolling up to re-read something mid-stream was impossible — every
 * streamed chunk threw the view back to the bottom. A second copy of the same
 * pattern sat in `TerminalPanel.tsx:101` (a 3 s poll, so a jump every 3 s).
 *
 * ⚠️ Making the scroll unconditional is what BROUGHT BACK an older fault:
 * approval/question cards stayed below the fold, the user could not answer a
 * request they never saw, and it was rejected after 180 s
 * (`approval-card-hidden-by-view-state`). So these tests nail down BOTH
 * directions: a new message waits, a decision card does not.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import React, { useEffect, useState } from 'react'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { resolve, join } from 'node:path'
import { render, screen, cleanup, fireEvent } from '@testing-library/react'

import { useAutoScroll, BOTTOM_TOLERANCE_PX } from '../renderer/hooks/home/useAutoScroll'
import { MessageNotices } from '../renderer/components/home/MessageNotices'

// jsdom has no layout: `scrollIntoView` is not even defined (calling it throws)
// and `scrollHeight`/`clientHeight` are always 0. Both are installed here — what
// is being measured is not the browser's scrolling but the DECISION to scroll.
const scrollIntoView = vi.fn()

beforeEach(() => {
  scrollIntoView.mockClear()
  Object.defineProperty(Element.prototype, 'scrollIntoView', {
    value: scrollIntoView,
    configurable: true,
    writable: true,
  })
})
afterEach(() => cleanup())

/** Writes fake geometry onto the container and dispatches a `scroll` event. */
const scrollTo = (el: HTMLElement, distanceFromBottom: number) => {
  const clientHeight = 200
  const scrollHeight = 1000
  for (const [name, value] of [
    ['scrollHeight', scrollHeight],
    ['clientHeight', clientHeight],
    ['scrollTop', scrollHeight - clientHeight - distanceFromBottom],
  ] as const) {
    Object.defineProperty(el, name, { value, configurable: true })
  }
  fireEvent.scroll(el)
}

const JUMP_LABEL = 'Yeni mesaj — aşağı in'

/**
 * The same wiring as `home.tsx`: `onScroll` on the container, a sentinel at the
 * end, new content via `followIfPinned`, decision cards via `scrollToBottom`.
 */
const Harness: React.FC<{ itemCount: number; gate: boolean }> = ({ itemCount, gate }) => {
  const s = useAutoScroll()
  const [unread, setUnread] = useState(false)

  useEffect(() => {
    if (!s.followIfPinned()) setUnread(true)
  }, [itemCount, s.followIfPinned])

  useEffect(() => {
    if (!gate) return
    s.scrollToBottom()
    setUnread(false)
  }, [gate, s.scrollToBottom])

  useEffect(() => {
    if (s.isPinned) setUnread(false)
  }, [s.isPinned])

  return (
    <div data-testid="scroller" onScroll={s.onScroll}>
      {Array.from({ length: itemCount }, (_, i) => <p key={i}>mesaj {i}</p>)}
      <div ref={s.endRef} />
      {unread && <button onClick={() => { s.scrollToBottom(); setUnread(false) }}>{JUMP_LABEL}</button>}
    </div>
  )
}

describe('useAutoScroll — dipteyken takip et, yukarıdayken bırak', () => {
  it('dipteyken yeni içerik görüntüyü aşağı çekiyor', () => {
    const { rerender } = render(<Harness itemCount={1} gate={false} />)
    scrollIntoView.mockClear()
    rerender(<Harness itemCount={2} gate={false} />)
    expect(scrollIntoView).toHaveBeenCalled()
    expect(screen.queryByText(JUMP_LABEL)).toBeNull()
  })

  it('kullanıcı yukarı kaydırmışken yeni içerik görüntüyü OYNATMIYOR', () => {
    const { rerender } = render(<Harness itemCount={1} gate={false} />)
    scrollTo(screen.getByTestId('scroller'), 400)
    scrollIntoView.mockClear()
    rerender(<Harness itemCount={2} gate={false} />)
    expect(scrollIntoView).not.toHaveBeenCalled()
  })

  it('yukarıdayken gelen içerik için görünür bir "aşağı in" düğmesi çiziliyor', () => {
    const { rerender } = render(<Harness itemCount={1} gate={false} />)
    scrollTo(screen.getByTestId('scroller'), 400)
    // Scrolling up on its own is not a reason to nag: nothing new arrived yet.
    expect(screen.queryByText(JUMP_LABEL)).toBeNull()
    rerender(<Harness itemCount={2} gate={false} />)
    expect(screen.getByText(JUMP_LABEL)).toBeTruthy()
  })

  it('düğmeye basınca dibe iniyor ve düğme kayboluyor', () => {
    const { rerender } = render(<Harness itemCount={1} gate={false} />)
    scrollTo(screen.getByTestId('scroller'), 400)
    rerender(<Harness itemCount={2} gate={false} />)
    scrollIntoView.mockClear()
    fireEvent.click(screen.getByText(JUMP_LABEL))
    expect(scrollIntoView).toHaveBeenCalled()
    expect(screen.queryByText(JUMP_LABEL)).toBeNull()
  })

  it('kullanıcı ELLE dibe inince takip kendiliğinden geri açılıyor', () => {
    const { rerender } = render(<Harness itemCount={1} gate={false} />)
    const container = screen.getByTestId('scroller')
    scrollTo(container, 400)
    rerender(<Harness itemCount={2} gate={false} />)
    expect(screen.getByText(JUMP_LABEL)).toBeTruthy()

    scrollTo(container, 0)
    expect(screen.queryByText(JUMP_LABEL)).toBeNull()

    scrollIntoView.mockClear()
    rerender(<Harness itemCount={3} gate={false} />)
    expect(scrollIntoView).toHaveBeenCalled()
  })

  it('yumuşak kaydırmanın birkaç piksel eksik inmesi takibi kapatmıyor', () => {
    const { rerender } = render(<Harness itemCount={1} gate={false} />)
    // Inside the tolerance: the user did not leave, the browser just landed short.
    scrollTo(screen.getByTestId('scroller'), BOTTOM_TOLERANCE_PX - 1)
    scrollIntoView.mockClear()
    rerender(<Harness itemCount={2} gate={false} />)
    expect(scrollIntoView).toHaveBeenCalled()
  })

  // The constant is exported and documented as "still at the bottom", but the
  // comparison was `<`, so the single position the constant NAMES was the one
  // position it excluded (audit `auto-scroll-boundary`). Measured at the
  // boundary itself, not near it: an off-by-one is invisible at 39 and 41.
  it('tam sınırdaki konum takibi KAPATMIYOR — sabit neyi diyorsa o', () => {
    const { rerender } = render(<Harness itemCount={1} gate={false} />)
    scrollTo(screen.getByTestId('scroller'), BOTTOM_TOLERANCE_PX)
    scrollIntoView.mockClear()
    rerender(<Harness itemCount={2} gate={false} />)
    expect(scrollIntoView).toHaveBeenCalled()
    expect(screen.queryByText(JUMP_LABEL)).toBeNull()
  })

  // The other side of the same boundary: widening it to `<=` must not turn into
  // "a bit more is fine too". One pixel past the tolerance is a user who left.
  it('sınırın bir piksel ötesi takibi kapatıyor', () => {
    const { rerender } = render(<Harness itemCount={1} gate={false} />)
    scrollTo(screen.getByTestId('scroller'), BOTTOM_TOLERANCE_PX + 1)
    scrollIntoView.mockClear()
    rerender(<Harness itemCount={2} gate={false} />)
    expect(scrollIntoView).not.toHaveBeenCalled()
    expect(screen.getByText(JUMP_LABEL)).toBeTruthy()
  })
})

describe('useAutoScroll — karar kartı kullanıcıyı BEKLEMEZ', () => {
  it('onay/soru kartı yukarıdayken bile görüntüye zorlanıyor', () => {
    const { rerender } = render(<Harness itemCount={1} gate={false} />)
    scrollTo(screen.getByTestId('scroller'), 400)
    rerender(<Harness itemCount={2} gate={false} />)
    expect(screen.getByText(JUMP_LABEL)).toBeTruthy()

    scrollIntoView.mockClear()
    rerender(<Harness itemCount={2} gate={true} />)
    expect(scrollIntoView).toHaveBeenCalled()
    expect(screen.queryByText(JUMP_LABEL)).toBeNull()
  })

  it('kart görüntüye alındıktan sonra takip yeniden açık', () => {
    const { rerender } = render(<Harness itemCount={1} gate={false} />)
    scrollTo(screen.getByTestId('scroller'), 400)
    rerender(<Harness itemCount={2} gate={true} />)
    scrollIntoView.mockClear()
    rerender(<Harness itemCount={3} gate={true} />)
    expect(scrollIntoView).toHaveBeenCalled()
  })
})

/**
 * "Close the class, not the path": this repo's most common failure shape is a
 * fix that closes one of several call sites. The unconditional scroll lived in
 * three places; all three now go through one hook, and a direct call may only
 * exist there.
 */
describe('sınıf kapanışı — doğrudan scrollIntoView çağrısı kalmadı', () => {
  const RENDERER = resolve(__dirname, '../renderer')
  const ALLOWED = resolve(RENDERER, 'hooks/home/useAutoScroll.ts')

  const sourceFiles = (dir: string): string[] => {
    const out: string[] = []
    for (const name of readdirSync(dir)) {
      // `public/` holds the third-party Monaco build — not our code.
      if (name === 'public' || name === 'node_modules') continue
      const path = join(dir, name)
      if (statSync(path).isDirectory()) out.push(...sourceFiles(path))
      else if (/\.(ts|tsx)$/.test(name)) out.push(path)
    }
    return out
  }

  it('renderer altında kancanın dışında scrollIntoView yok', () => {
    const offenders = sourceFiles(RENDERER)
      .filter(path => resolve(path) !== ALLOWED)
      .filter(path => readFileSync(path, 'utf8').includes('scrollIntoView'))
    expect(offenders).toEqual([])
  })

  it('home.tsx kaydırma dinleyicisini GERÇEKTEN kaydıran kapsayıcıya bağlıyor', () => {
    // ChatPanel's own root (`ChatPanel.tsx:273`) carries `flex-1 overflow-y-auto`,
    // but its parent is a block box, so its height stays `auto` and it never
    // overflows: a listener attached there would silently do nothing.
    const source = readFileSync(resolve(RENDERER, 'pages/home.tsx'), 'utf8')
    expect(source).toContain('onScroll={chatScroll.onScroll}')
    expect(source).toContain("t('chat.newBelow')")
  })

  it('dört karar kapısının hepsi zorlanan kaydırmayı tetikliyor', () => {
    // Four separate gates can put an unanswerable card on screen; the earlier
    // fix only covered `mcp.activeGate`. Asserted on the dependency list because
    // an effect that does not re-run for a gate cannot scroll to it, and the
    // harness above cannot see which gates `home.tsx` actually lists.
    const source = readFileSync(resolve(RENDERER, 'pages/home.tsx'), 'utf8')
    const forced = /chatScroll\.scrollToBottom\(\);[\s\S]*?\}, \[([^\]]*)\]\);/.exec(source)
    expect(forced).not.toBeNull()
    for (const gate of ['mcp.activeGate', 'chat.pendingCommand', 'chat.pendingQuestion', 'fs.pendingDelete']) {
      expect(forced![1]).toContain(gate)
    }
  })
})

/**
 * "The function was called" ≠ "the user saw it" (the ToastContainer case): the
 * notice may well be written onto the message, but if nothing renders it, it is
 * invisible.
 */
describe('MessageNotices — uyarı DOM da görünüyor', () => {
  it('tavana çarpan koşumun uyarısı çiziliyor, ayrıntı katlanmış duruyor', () => {
    render(<MessageNotices notices={[{
      kind: 'stopped',
      title: 'Koşum yarıda durdu',
      message: 'Model adım sınırına ulaştı.',
      detail: 'stop_reason=max_iterations · iterations=40',
    }]} />)
    expect(screen.getByText('Koşum yarıda durdu')).toBeTruthy()
    expect(screen.getByText('Model adım sınırına ulaştı.')).toBeTruthy()
    // The detail is in the DOM but inside `<details>` — secondary, it does not
    // crowd out the plain-language message.
    const detail = screen.getByText('stop_reason=max_iterations · iterations=40')
    expect(detail.closest('details')).not.toBeNull()
  })

  it('yarıda kesilme HATA gibi görünmüyor', () => {
    const { container } = render(<MessageNotices notices={[{
      kind: 'stopped', title: 'Koşum yarıda durdu', message: 'Model adım sınırına ulaştı.',
    }]} />)
    expect(container.textContent).not.toContain('❌')
    expect(container.innerHTML).not.toContain('text-red-')
  })

  it('bilinmeyen kodlu bir uyarı da gösteriliyor — kod listesine bağlı değil', () => {
    render(<MessageNotices notices={[{
      kind: 'warning',
      title: 'Uyarı',
      message: 'Video indirilemedi, mesaj videosuz gönderildi.',
      detail: 'code=henuz_olmayan_bir_kod',
    }]} />)
    expect(screen.getByText('Video indirilemedi, mesaj videosuz gönderildi.')).toBeTruthy()
  })

  it('bildirim yoksa hiçbir şey çizilmiyor', () => {
    const { container } = render(<MessageNotices notices={[]} />)
    expect(container.innerHTML).toBe('')
  })

  it('ChatPanel bu bileşeni gerçekten mount ediyor', () => {
    // The ToastContainer lesson: a notification component that is defined and
    // exported but called from nowhere is green in tests and invisible in the
    // product.
    const source = readFileSync(
      resolve(__dirname, '../renderer/components/home/ChatPanel.tsx'), 'utf8')
    expect(source).toContain('<MessageNotices')
  })
})
