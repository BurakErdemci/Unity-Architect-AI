/**
 * The model read gate answers `busy` when too many reads are already in
 * flight. That is the machine shedding load for a moment, not a verdict on
 * the file, so it must not arrive as "this model could not be opened" — the
 * user would go looking for damage that is not there instead of clicking
 * again.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'

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
const { ModelPreviewPanel } = await import('../renderer/components/model-viewer/ModelPreviewPanel')

const invoke = vi.fn()
;(globalThis as any).window.ipc = { invoke }

const draw = () =>
  render(
    <ModelPreviewPanel
      file={{ path: 'C:\\proj\\Assets\\hero.fbx', name: 'hero.fbx' }}
      workspacePath={'C:\\proj'}
    />,
  )

describe('the read gate shedding load', () => {
  beforeEach(() => { invoke.mockReset() })

  it('says to try again shortly rather than calling the file broken', async () => {
    invoke.mockResolvedValue({ error: 'busy' })
    draw()
    await waitFor(() => expect(screen.getByText(cevir('preview.busy'))).toBeTruthy())
    expect(screen.queryByText(cevir('preview.loadError'))).toBeNull()
    expect(screen.queryByText(cevir('preview.loading'))).toBeNull()
  })

  it('offers the retry in both languages', () => {
    for (const lang of ['tr', 'en'] as const) {
      expect(translations[lang]['preview.busy'].length).toBeGreaterThan(0)
    }
  })
})
