/**
 * Finding class `mount-failure-unreported`.
 *
 * The mount call sits inside a try/catch, but the catch itself drew through
 * the stage before reporting. When the renderer's own `render()` was what
 * threw, the recovery threw again: the throw escaped the load effect's async
 * body as an unhandled rejection, `fail` was never reached, `setLoading(false)`
 * never ran, and the panel spun on a load it already knew had failed.
 *
 * The class is "a recovery or teardown path calls back into the renderer that
 * may itself be what broke". The other paths with that shape are covered
 * below: the load effect's `teardown`, the panel's unmount, and the repaint
 * that follows a context restore.
 *
 * jsdom cannot start a real renderer, so `WebGLRenderer` is a canvas-owning
 * stand-in whose `render()` can be told to start throwing at a chosen call.
 * Everything else — the glTF parse, the mount, the panel's state — is the
 * production path.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

/**
 * `throwFrom` is the 1-based `render()` call at which the fake renderer starts
 * failing, so a test can let setup succeed and break the draw that a specific
 * later path performs. `Infinity` never throws.
 */
const renderer = vi.hoisted(() => ({
  calls: 0,
  throwFrom: Infinity,
  contextLossCalls: 0,
  disposeCalls: 0,
}))

vi.mock('three', async importOriginal => {
  const actual = await importOriginal<typeof import('three')>()
  class FakeWebGLRenderer {
    domElement = document.createElement('canvas')
    setPixelRatio() {}
    setSize() {}
    render() {
      renderer.calls += 1
      if (renderer.calls >= renderer.throwFrom) throw new Error('renderer failed')
    }
    forceContextLoss() { renderer.contextLossCalls += 1 }
    dispose() { renderer.disposeCalls += 1 }
  }
  return { ...actual, WebGLRenderer: FakeWebGLRenderer }
})

const { cevir } = await import('../renderer/lib/i18n')
const { ModelPreviewPanel } = await import('../renderer/components/model-viewer/ModelPreviewPanel')

const invoke = vi.fn()
;(globalThis as any).window.ipc = { invoke }

// Copied into a jsdom-realm buffer so `instanceof ArrayBuffer` holds inside
// three; see model-format-dispatch.test.ts for that measurement.
const glb = (): ArrayBuffer => {
  const buf = readFileSync(resolve(__dirname, 'fixtures', 'triangle.glb'))
  const out = new ArrayBuffer(buf.byteLength)
  new Uint8Array(out).set(buf)
  return out
}

const LOADING = cevir('preview.loading')
const LOAD_ERROR = cevir('preview.loadError')
const GONE = cevir('preview.contextGone')

const draw = () =>
  render(
    <ModelPreviewPanel
      file={{ path: 'C:\\proj\\Assets\\triangle.glb', name: 'triangle.glb' }}
      workspacePath={'C:\\proj'}
    />,
  )

describe('a renderer that throws while a model is being mounted', () => {
  beforeEach(() => {
    invoke.mockReset()
    renderer.calls = 0
    renderer.throwFrom = Infinity
    renderer.contextLossCalls = 0
    renderer.disposeCalls = 0
    invoke.mockResolvedValue({ path: 'x', name: 'triangle.glb', data: glb() })
  })

  it('reports the load error even though the recovery draw fails too', async () => {
    // Call 1 is the setup resize; the mount's own draw is the next one, which
    // puts both the failure and the recovery's redraw on the failing side.
    renderer.throwFrom = 2
    draw()

    await waitFor(() => expect(screen.getByText(LOAD_ERROR)).toBeTruthy())
    expect(screen.queryByText(LOADING)).toBeNull()
  })

  it('keeps reporting when every later draw fails too', async () => {
    // Not just the recovery's own redraw: from the mount onwards nothing this
    // renderer is asked to draw succeeds, and the report is still owed.
    renderer.throwFrom = 2
    const view = draw()

    await waitFor(() => expect(screen.getByText(LOAD_ERROR)).toBeTruthy())
    expect(screen.queryByText(LOADING)).toBeNull()
    // The load effect's own cleanup draws through the same broken renderer.
    expect(() => view.unmount()).not.toThrow()
  })

  it('still releases the GL context when unmounting a broken renderer', async () => {
    // Same class on the teardown side: the frees run in dependency order, and
    // `forceContextLoss` is near the end. A throw earlier in that list used to
    // skip it, and a skipped release is cumulative — closed panels pile up
    // against the browser's context cap.
    renderer.throwFrom = 2
    const view = draw()
    await waitFor(() => expect(screen.getByText(LOAD_ERROR)).toBeTruthy())

    view.unmount()
    expect(renderer.contextLossCalls).toBe(1)
    expect(renderer.disposeCalls).toBe(1)
  })

  it('calls a restore that cannot draw a failure rather than a recovery', async () => {
    // The repaint after `webglcontextrestored` is the first draw through the
    // new context. If it throws, the context is not actually back, so clearing
    // the notice would promise the user a working viewport they cannot see.
    const view = draw()
    await waitFor(() => expect(screen.queryByText(LOADING)).toBeNull())
    const canvas = view.container.querySelector('canvas')!

    canvas.dispatchEvent(new Event('webglcontextlost', { cancelable: true }))
    renderer.throwFrom = renderer.calls + 1
    canvas.dispatchEvent(new Event('webglcontextrestored'))

    expect(screen.getByText(GONE)).toBeTruthy()
  })

  it('goes quiet on a restore whose repaint succeeds', async () => {
    // The counterpart of the case above: nothing here should make a working
    // restore look like a failed one.
    const view = draw()
    await waitFor(() => expect(screen.queryByText(LOADING)).toBeNull())
    const canvas = view.container.querySelector('canvas')!

    canvas.dispatchEvent(new Event('webglcontextlost', { cancelable: true }))
    canvas.dispatchEvent(new Event('webglcontextrestored'))

    expect(view.container.textContent?.trim()).toBe('')
  })
})
