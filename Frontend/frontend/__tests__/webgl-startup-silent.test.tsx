/**
 * Finding class `webgl-startup-silent`.
 *
 * When `new THREE.WebGLRenderer` throws, the setup effect returns without a
 * stage. A valid model then reads, parses, and finds nothing to mount onto, so
 * the loading state clears onto an empty dark rectangle — which looks exactly
 * like a load that never finished, and offers the user nothing to act on.
 *
 * jsdom is the fixture: `getContext('webgl')` is not implemented there, so the
 * constructor fails for the same reason it fails on a machine with a blocked
 * or missing GPU. Nothing here has to fake the failure.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { cevir, translations } from '../renderer/lib/i18n'
import { ModelPreviewPanel } from '../renderer/components/model-viewer/ModelPreviewPanel'

const invoke = vi.fn()
;(globalThis as any).window.ipc = { invoke }

// Copied into a jsdom-realm buffer so `instanceof ArrayBuffer` holds inside
// three; see model-format-dispatch.test.ts for that measurement.
const bytes = (name: string): ArrayBuffer => {
  const buf = readFileSync(resolve(__dirname, 'fixtures', name))
  const out = new ArrayBuffer(buf.byteLength)
  new Uint8Array(out).set(buf)
  return out
}

const draw = (name: string) =>
  render(
    <ModelPreviewPanel
      file={{ path: `C:\\proj\\Assets\\${name}`, name }}
      workspacePath={'C:\\proj'}
      onClose={() => {}}
    />,
  )

const NO_WEBGL = cevir('preview.noWebgl')

describe('a machine that cannot give the panel a WebGL context', () => {
  beforeEach(() => { invoke.mockReset() })

  it('explains itself instead of leaving an empty panel behind a parsed model', async () => {
    invoke.mockResolvedValue({ path: 'x', name: 'hero.fbx', data: bytes('animated-triangle.fbx') })
    const view = draw('hero.fbx')

    await waitFor(() => expect(screen.queryByText(cevir('preview.loading'))).toBeNull())
    expect(view.container.textContent?.trim()).not.toBe('')
    expect(screen.getByText(NO_WEBGL)).toBeTruthy()
  })

  it('says nothing while the file is still being read', async () => {
    // The read may yet fail for a reason of its own, and two messages stacked
    // on one another is worse than the later, more specific one.
    let settle: (v: unknown) => void = () => {}
    invoke.mockReturnValue(new Promise(r => { settle = r }))
    draw('hero.fbx')

    expect(screen.getByText(cevir('preview.loading'))).toBeTruthy()
    expect(screen.queryByText(NO_WEBGL)).toBeNull()

    settle({ path: 'x', name: 'hero.fbx', data: bytes('animated-triangle.fbx') })
    await waitFor(() => expect(screen.getByText(NO_WEBGL)).toBeTruthy())
  })

  it('does not talk over a message about the file itself', async () => {
    // A .blend is unreadable whatever the GPU can do, and that is the more
    // specific and more actionable of the two facts.
    draw('scene.blend')

    await waitFor(() => expect(screen.getByText(cevir('preview.blockedFormat'))).toBeTruthy())
    expect(screen.queryByText(NO_WEBGL)).toBeNull()
  })

  it('says what to try, in both languages', () => {
    // A message naming only the failure leaves the user with nowhere to go;
    // the driver is the one thing they can actually act on.
    expect(translations.tr['preview.noWebgl']).toMatch(/sürücü/i)
    expect(translations.en['preview.noWebgl']).toMatch(/driver/i)
  })
})
