/**
 * Finding class `viewport-fault-hidden`.
 *
 * The loss handler recorded the fault correctly, but the branch that draws it
 * carried a blanket `!loading` guard. A driver reset that landed while the
 * model was still being read or parsed was therefore invisible: the event was
 * cancelled, `viewportFault` became `lost`, and the user kept looking at a
 * spinner over a canvas the driver had already blanked — a load that could
 * only finish into a dead viewport, with nothing on screen saying so.
 *
 * The guard itself is not the defect. It is what keeps the startup-time
 * `unavailable` fault from talking over a read that may yet produce a more
 * specific verdict about the file; that half is pinned by
 * `webgl-startup-silent.test.tsx` ("says nothing while the file is still being
 * read"), which needs a real absent context and so cannot live in this file.
 *
 * jsdom cannot start a real renderer, so `WebGLRenderer` is a canvas-owning
 * stand-in — the same pattern as the other `webgl-*` suites. Everything else,
 * including the panel's own loading state, is the production path.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
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

const { cevir } = await import('../renderer/lib/i18n')
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

const LOADING = cevir('preview.loading')
const LOST = cevir('preview.contextLost')
const GONE = cevir('preview.contextGone')

const draw = () =>
  render(
    <ModelPreviewPanel
      file={{ path: 'C:\\proj\\Assets\\triangle.glb', name: 'triangle.glb' }}
      workspacePath={'C:\\proj'}
    />,
  )

/** A panel whose read never settles, so `loading` stays true throughout. */
const stillReading = () => {
  invoke.mockReturnValue(new Promise(() => {}))
  const view = draw()
  const canvas = view.container.querySelector('canvas')
  expect(canvas).not.toBeNull()
  expect(screen.getByText(LOADING)).toBeTruthy()
  return { view, canvas: canvas! }
}

const lose = (canvas: HTMLCanvasElement) => {
  const event = new Event('webglcontextlost', { cancelable: true })
  canvas.dispatchEvent(event)
  return event
}

describe('a context lost while the model is still loading', () => {
  beforeEach(() => { invoke.mockReset() })

  it('says the context is gone instead of going on spinning', () => {
    const { canvas } = stillReading()

    expect(lose(canvas).defaultPrevented).toBe(true)
    expect(screen.getByText(LOST)).toBeTruthy()
  })

  it('drops the spinner rather than stacking it under the notice', () => {
    // Both branches are absolute inset-0, so leaving the spinner up would put
    // two messages on the same rectangle. The load is heading for a dead
    // canvas, which makes the fault the honest one of the two.
    const { canvas } = stillReading()
    lose(canvas)

    expect(screen.queryByText(LOADING)).toBeNull()
  })

  it('still escalates while the read has not settled', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      const { canvas } = stillReading()
      lose(canvas)
      await vi.advanceTimersByTimeAsync(CONTEXT_RESTORE_GRACE_MS)
      expect(screen.getByText(GONE)).toBeTruthy()
    } finally {
      vi.useRealTimers()
    }
  })

  it('goes back to the spinner when the context returns before the read does', async () => {
    // The read is still the thing being waited on, so once the viewport works
    // again the panel owes the user the wait it was showing before.
    const { canvas } = stillReading()
    lose(canvas)
    canvas.dispatchEvent(new Event('webglcontextrestored'))

    await waitFor(() => expect(screen.queryByText(LOST)).toBeNull())
    expect(screen.getByText(LOADING)).toBeTruthy()
  })

  it('leaves a settled load reading exactly as before', async () => {
    // The composition must only add a message to the loading state; a model
    // that mounts with no fault still ends on a bare canvas.
    invoke.mockResolvedValue({ path: 'x', name: 'triangle.glb', data: glb() })
    const view = draw()

    await waitFor(() => expect(screen.queryByText(LOADING)).toBeNull())
    expect(view.container.textContent?.trim()).toBe('')
  })
})
