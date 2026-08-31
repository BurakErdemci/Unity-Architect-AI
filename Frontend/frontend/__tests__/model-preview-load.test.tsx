/**
 * The panel's load path under jsdom. There is no WebGL here, so what is
 * measured is everything around the draw: which channel call goes out, and
 * which of the three states the user is left looking at.
 *
 * Wording is pulled from the i18n table rather than typed in, so a copy edit
 * does not turn into a red test.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { cevir } from '../renderer/lib/i18n'
import { ModelPreviewPanel } from '../renderer/components/model-viewer/ModelPreviewPanel'

const invoke = vi.fn()
;(globalThis as any).window.ipc = { invoke }

const fbxBytes = (): ArrayBuffer => {
  const buf = readFileSync(resolve(__dirname, 'fixtures', 'animated-triangle.fbx'))
  return buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength) as ArrayBuffer
}

const draw = (name = 'hero.fbx', workspacePath: string | null = 'C:\\proj') =>
  render(
    <ModelPreviewPanel
      file={{ path: `C:\\proj\\Assets\\${name}`, name }}
      workspacePath={workspacePath}
      onClose={() => {}}
    />,
  )

const LOAD_ERROR = cevir('preview.loadError')

describe('ModelPreviewPanel load', () => {
  beforeEach(() => { invoke.mockReset() })

  it('asks the model channel for the clicked file, scoped to the workspace', async () => {
    invoke.mockResolvedValue({ path: 'x', name: 'hero.fbx', data: fbxBytes() })
    draw()
    await waitFor(() => expect(invoke).toHaveBeenCalledWith('read-model-file', 'C:\\proj\\Assets\\hero.fbx', 'C:\\proj'))
  })

  it('shows the loading state until the answer arrives', async () => {
    let settle: (v: unknown) => void = () => {}
    invoke.mockReturnValue(new Promise(r => { settle = r }))
    draw()
    expect(screen.getByText(cevir('preview.loading'))).toBeTruthy()

    settle({ path: 'x', name: 'hero.fbx', data: fbxBytes() })
    await waitFor(() => expect(screen.queryByText(cevir('preview.loading'))).toBeNull())
  })

  it('leaves no error visible once a real FBX parses', async () => {
    invoke.mockResolvedValue({ path: 'x', name: 'hero.fbx', data: fbxBytes() })
    draw()
    await waitFor(() => expect(screen.queryByText(cevir('preview.loading'))).toBeNull())
    expect(screen.queryByText(LOAD_ERROR)).toBeNull()
  })

  it('falls back to the generic message for a channel refusal', async () => {
    // 'denied' / 'too-large' / 'unsupported' all land here for now; Task 5 is
    // what tells them apart.
    invoke.mockResolvedValue({ error: 'denied' })
    draw()
    await waitFor(() => expect(screen.getByText(LOAD_ERROR)).toBeTruthy())
  })

  it('falls back to the generic message when the handler answers with nothing', async () => {
    invoke.mockResolvedValue(null)
    draw()
    await waitFor(() => expect(screen.getByText(LOAD_ERROR)).toBeTruthy())
  })

  it('prints the parser one-liner under the generic message', async () => {
    invoke.mockResolvedValue({ path: 'x', name: 'hero.fbx', data: new TextEncoder().encode('plain text').buffer })
    draw()
    await waitFor(() => expect(screen.getByText(LOAD_ERROR)).toBeTruthy())
    expect(screen.getByText(/FBXLoader/)).toBeTruthy()
  })

  it('reports an extension it has no loader for instead of rendering blank', async () => {
    invoke.mockResolvedValue({ path: 'x', name: 'hero.glb', data: new ArrayBuffer(8) })
    draw('hero.glb')
    await waitFor(() => expect(screen.getByText(LOAD_ERROR)).toBeTruthy())
    expect(screen.getByText(/\.glb/)).toBeTruthy()
  })

  it('re-reads when the previewed file changes', async () => {
    invoke.mockResolvedValue({ path: 'x', name: 'hero.fbx', data: fbxBytes() })
    const view = draw()
    await waitFor(() => expect(invoke).toHaveBeenCalledTimes(1))
    view.rerender(
      <ModelPreviewPanel
        file={{ path: 'C:\\proj\\Assets\\second.fbx', name: 'second.fbx' }}
        workspacePath={'C:\\proj'}
        onClose={() => {}}
      />,
    )
    await waitFor(() => expect(invoke).toHaveBeenLastCalledWith('read-model-file', 'C:\\proj\\Assets\\second.fbx', 'C:\\proj'))
  })
})
