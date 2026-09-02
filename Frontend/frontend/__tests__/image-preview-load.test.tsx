/**
 * The image panel's load path under jsdom: which channel call goes out, what the
 * user is left looking at, and whether the object URL is given back.
 *
 * Wording is pulled from the i18n table rather than typed in, so a copy edit
 * does not turn into a red test — and nothing here asserts on source text.
 *
 * jsdom implements neither `URL.createObjectURL` nor `revokeObjectURL`, so both
 * are stubbed. The stub is not just scaffolding: the revoke spy IS the
 * measurement for the leak this panel has to avoid.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'

const { cevir, translations } = await import('../renderer/lib/i18n')
const { ImagePreviewPanel } = await import('../renderer/components/image-viewer/ImagePreviewPanel')

const invoke = vi.fn()
;(globalThis as any).window.ipc = { invoke }

let created: string[] = []
const revoke = vi.fn()

beforeEach(() => {
  invoke.mockReset()
  revoke.mockReset()
  created = []
  ;(URL as any).createObjectURL = vi.fn(() => {
    const u = `blob:test/${created.length}`
    created.push(u)
    return u
  })
  ;(URL as any).revokeObjectURL = revoke
})

afterEach(() => {
  delete (URL as any).createObjectURL
  delete (URL as any).revokeObjectURL
})

const pngBytes = () => new ArrayBuffer(64)

const draw = (name = 'skin.png', workspacePath: string | null = 'C:\\proj') =>
  render(
    <ImagePreviewPanel
      file={{ path: `C:\\proj\\Assets\\Textures\\${name}`, name }}
      workspacePath={workspacePath}
    />,
  )

const img = (): HTMLImageElement | null => document.querySelector('img')

describe('image preview — a successful read', () => {
  it('shows the bytes as an object URL in an <img>', async () => {
    invoke.mockResolvedValue({ path: 'p', name: 'skin.png', data: pngBytes() })
    draw()

    await waitFor(() => expect(img()).not.toBeNull())
    expect(img()!.getAttribute('src')!.startsWith('blob:')).toBe(true)
    expect(invoke).toHaveBeenCalledWith('read-image-file', 'C:\\proj\\Assets\\Textures\\skin.png', 'C:\\proj')
  })

  it('gives the object URL back on unmount', async () => {
    invoke.mockResolvedValue({ path: 'p', name: 'skin.png', data: pngBytes() })
    const view = draw()

    await waitFor(() => expect(created.length).toBe(1))
    expect(revoke).not.toHaveBeenCalled()

    view.unmount()
    // The exact URL, not just "revoke was called": revoking some other string
    // would satisfy a call-count assertion while the real one still leaks.
    expect(revoke).toHaveBeenCalledWith(created[0])
  })

  it('gives the previous URL back when the file changes', async () => {
    invoke.mockResolvedValue({ path: 'p', name: 'skin.png', data: pngBytes() })
    const view = draw()
    await waitFor(() => expect(created.length).toBe(1))

    view.rerender(
      <ImagePreviewPanel
        file={{ path: 'C:\\proj\\Assets\\Textures\\other.png', name: 'other.png' }}
        workspacePath={'C:\\proj'}
      />,
    )
    await waitFor(() => expect(revoke).toHaveBeenCalledWith(created[0]))
  })
})

describe('image preview — refusals', () => {
  it('names the image cap rather than the model one when the file is too large', async () => {
    invoke.mockResolvedValue({ error: 'too-large' })
    draw()

    await waitFor(() => expect(screen.getByText(cevir('preview.imageTooLarge'))).toBeTruthy())
    // The model panel's sentence names 64 MiB; showing it here would tell the
    // user the wrong number.
    expect(screen.queryByText(cevir('preview.tooLarge'))).toBeNull()
  })

  it('reuses the model panel wording when the read gate is shedding load', async () => {
    invoke.mockResolvedValue({ error: 'busy' })
    draw()

    await waitFor(() => expect(screen.getByText(cevir('preview.busy'))).toBeTruthy())
    expect(screen.queryByText(cevir('preview.loadError'))).toBeNull()
  })

  it('falls back to the generic message on a null result', async () => {
    invoke.mockResolvedValue(null)
    draw()

    await waitFor(() => expect(screen.getByText(cevir('preview.loadError'))).toBeTruthy())
  })

  it('explains a blocked format without touching the channel', async () => {
    draw('skin.tga')

    await waitFor(() => expect(screen.getByText(cevir('preview.imageBlockedFormat'))).toBeTruthy())
    expect(invoke).not.toHaveBeenCalled()
    expect(img()).toBeNull()
  })

  it('offers every image message in both languages', () => {
    for (const key of ['preview.imageLoading', 'preview.imageBlockedFormat', 'preview.imageTooLarge',
      'preview.fitToView', 'preview.actualSize', 'preview.imageDimensions']) {
      for (const lang of ['tr', 'en'] as const) {
        expect(translations[lang][key].length).toBeGreaterThan(0)
      }
    }
  })
})
