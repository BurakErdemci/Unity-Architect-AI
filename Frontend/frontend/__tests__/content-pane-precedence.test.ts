/**
 * One content area, three candidates. The measured fault: the pane chose the
 * 3D preview first, so a `diffFile` — set while the assistant is ASKING the
 * user to approve a file change — rendered nowhere. The approval card stayed
 * on screen asking about content that was not on screen, and the only ways out
 * were approving blind or closing the preview by guess.
 */
import { describe, it, expect } from 'vitest'
import { contentPane } from '../renderer/lib/contentPane'

const preview = { path: 'C:\\proj\\Assets\\hero.fbx', name: 'hero.fbx' }
const diff = { name: 'Player.cs', code: 'new', originalCode: 'old', suggestedPath: 'Assets/Player.cs' }

describe('contentPane', () => {
  it('shows the pending diff even with a preview open — the blocking ask wins', () => {
    expect(contentPane(preview, diff, null)).toBe('editor')
  })

  it('shows the pending diff over an open text file too', () => {
    expect(contentPane(null, diff, 'Assets/Other.cs')).toBe('editor')
  })

  it('goes back to the preview once the approval is decided', () => {
    expect(contentPane(preview, null, null)).toBe('preview')
  })

  it('shows the preview over a stale editor path', () => {
    expect(contentPane(preview, null, 'Assets/Player.cs')).toBe('preview')
  })

  it('shows the editor for an opened text file', () => {
    expect(contentPane(null, null, 'Assets/Player.cs')).toBe('editor')
  })

  it('shows the hero when nothing is open', () => {
    expect(contentPane(null, null, null)).toBe('hero')
  })
})
