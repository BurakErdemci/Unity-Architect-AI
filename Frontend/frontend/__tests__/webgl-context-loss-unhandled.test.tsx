/**
 * Finding class `webgl-context-loss-unhandled`.
 *
 * The panel subscribed to `webglcontextrestored` but to nothing on the way
 * down. A still model parks its render loop, so a driver-level loss produced
 * no state change at all: the canvas stayed mounted and black with no message,
 * and if the context never came back there was no route out of it either.
 *
 * jsdom cannot start a real renderer, so `WebGLRenderer` is replaced by a
 * canvas-owning stand-in — everything else, including the glTF parse and the
 * mount, is the production path. What this therefore measures is the panel's
 * reaction to the context events, not a hardware loss/restore cycle; a real
 * driver reset stays unproven here.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

vi.mock('three', async importOriginal => {
  const actual = await importOriginal<typeof import('three')>()
  class FakeWebGLRenderer {
    domElement = document.createElement('canvas')
    setPixelRatio() {}
    setSize() {}
    render() {}
    forceContextLoss() {}
    dispose() {}
  }
  return { ...actual, WebGLRenderer: FakeWebGLRenderer }
})

const { cevir, translations } = await import('../renderer/lib/i18n')
const { ModelPreviewPanel, CONTEXT_RESTORE_GRACE_MS } =
  await import('../renderer/components/model-viewer/ModelPreviewPanel')

const invoke = vi.fn()
;(globalThis as any).window.ipc = { invoke }

const glb = (): ArrayBuffer => {
  const buf = readFileSync(resolve(__dirname, 'fixtures', 'triangle.glb'))
  const out = new ArrayBuffer(buf.byteLength)
  new Uint8Array(out).set(buf)
  return out
}

const LOST = cevir('preview.contextLost')
const GONE = cevir('preview.contextGone')

/** A mounted still model: parsed, framed, render loop parked, nothing to say. */
const mounted = async () => {
  invoke.mockResolvedValue({ path: 'x', name: 'triangle.glb', data: glb() })
  const view = render(
    <ModelPreviewPanel
      file={{ path: 'C:\\proj\\Assets\\triangle.glb', name: 'triangle.glb' }}
      workspacePath={'C:\\proj'}
      onClose={() => {}}
    />,
  )
  await waitFor(() => expect(screen.queryByText(cevir('preview.loading'))).toBeNull())
  const canvas = view.container.querySelector('canvas')
  expect(canvas).not.toBeNull()
  expect(view.container.textContent?.trim()).toBe('')
  return { view, canvas: canvas! }
}

const lose = (canvas: HTMLCanvasElement) => {
  const event = new Event('webglcontextlost', { cancelable: true })
  act(() => { canvas.dispatchEvent(event) })
  return event
}

describe('a preview whose canvas loses its WebGL context', () => {
  beforeEach(() => {
    invoke.mockReset()
    // `shouldAdvanceTime` keeps the real clock feeding waitFor and the parse's
    // promise chain while the grace timer stays under this test's control.
    vi.useFakeTimers({ shouldAdvanceTime: true })
  })
  afterEach(() => { vi.useRealTimers() })

  it('replaces the silent black canvas with a message', async () => {
    const { canvas } = await mounted()
    lose(canvas)
    expect(screen.getByText(LOST)).toBeTruthy()
  })

  it('asks the browser to bring the context back', async () => {
    // Cancelling the event is the whole difference between a loss that may be
    // restored and one the browser will never retry, so the "may come back"
    // wording is only honest if this happens.
    const { canvas } = await mounted()
    expect(lose(canvas).defaultPrevented).toBe(true)
  })

  it('still calls the loss recoverable while the restore window is open', async () => {
    const { canvas } = await mounted()
    lose(canvas)
    await act(async () => { vi.advanceTimersByTime(CONTEXT_RESTORE_GRACE_MS - 1) })
    expect(screen.getByText(LOST)).toBeTruthy()
    expect(screen.queryByText(GONE)).toBeNull()
  })

  it('gives up once the context has not come back', async () => {
    const { canvas } = await mounted()
    lose(canvas)
    await act(async () => { vi.advanceTimersByTime(CONTEXT_RESTORE_GRACE_MS) })
    expect(screen.getByText(GONE)).toBeTruthy()
    expect(screen.queryByText(LOST)).toBeNull()
  })

  it('goes quiet again when the context is restored', async () => {
    const { view, canvas } = await mounted()
    lose(canvas)
    act(() => { canvas.dispatchEvent(new Event('webglcontextrestored')) })
    expect(view.container.textContent?.trim()).toBe('')
    expect(view.container.querySelector('canvas')).not.toBeNull()
  })

  it('goes quiet even when the context comes back after it was given up on', async () => {
    // A late restore is still a working viewport; leaving `gone` on screen
    // would tell the user to reopen a preview that already draws.
    const { view, canvas } = await mounted()
    lose(canvas)
    await act(async () => { vi.advanceTimersByTime(CONTEXT_RESTORE_GRACE_MS) })
    expect(screen.getByText(GONE)).toBeTruthy()

    act(() => { canvas.dispatchEvent(new Event('webglcontextrestored')) })
    expect(view.container.textContent?.trim()).toBe('')
  })

  it('does not escalate a restored context on the old timer', async () => {
    const { view, canvas } = await mounted()
    lose(canvas)
    act(() => { canvas.dispatchEvent(new Event('webglcontextrestored')) })
    await act(async () => { vi.advanceTimersByTime(CONTEXT_RESTORE_GRACE_MS * 2) })
    expect(view.container.textContent?.trim()).toBe('')
  })

  it('tells the two states apart in both languages', () => {
    // One message asks the user to wait, the other asks them to act. Wording
    // that collapses them costs the distinction the handler exists to make.
    for (const lang of ['tr', 'en'] as const) {
      expect(translations[lang]['preview.contextLost']).toBeTruthy()
      expect(translations[lang]['preview.contextGone']).toBeTruthy()
      expect(translations[lang]['preview.contextLost'])
        .not.toBe(translations[lang]['preview.contextGone'])
    }
  })
})
