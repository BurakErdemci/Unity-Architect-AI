/**
 * Which content surface a file-tree click opens.
 *
 * The router is the only thing standing between a binary mesh and the text
 * editor: a wrong 'text' answer feeds a .fbx to Monaco, and a wrong 'model'
 * answer hides a source file behind an empty 3D canvas.
 */
import { describe, it, expect } from 'vitest'
import { routeForFile, MODEL_EXTENSIONS, BLOCKED_MODEL_EXTENSIONS } from '../renderer/components/model-viewer/extensions'

describe('routeForFile', () => {
  it('routes every renderable model extension to the viewer', () => {
    for (const ext of MODEL_EXTENSIONS) {
      expect(routeForFile(`Assets/Models/hero${ext}`)).toBe('model')
    }
  })

  it('routes every blocked authoring format to blocked-model', () => {
    for (const ext of BLOCKED_MODEL_EXTENSIONS) {
      expect(routeForFile(`Assets/Models/hero${ext}`)).toBe('blocked-model')
    }
  })

  it('routes anything else to the text editor', () => {
    expect(routeForFile('Assets/Scripts/Player.cs')).toBe('text')
    expect(routeForFile('README.md')).toBe('text')
    expect(routeForFile('Assets/Textures/skin.png')).toBe('text')
  })

  it('is case-insensitive — Unity assets ship .FBX as often as .fbx', () => {
    expect(routeForFile('Assets/HERO.FBX')).toBe('model')
    expect(routeForFile('Assets/Hero.GlTf')).toBe('model')
    expect(routeForFile('Assets/Hero.BLEND')).toBe('blocked-model')
  })

  it('treats a file with no extension as text', () => {
    expect(routeForFile('Assets/LICENSE')).toBe('text')
    expect(routeForFile('Makefile')).toBe('text')
    expect(routeForFile('')).toBe('text')
  })

  it('treats a dotfile as text, not as an extension-only name', () => {
    expect(routeForFile('.gitignore')).toBe('text')
    expect(routeForFile('project/.obj')).toBe('text')
  })

  it('reads the extension from the basename, not from a dotted directory', () => {
    expect(routeForFile('Assets/v1.2/notes')).toBe('text')
    expect(routeForFile('Assets/hero.fbx/meta')).toBe('text')
    expect(routeForFile('C:\\Users\\b\\Assets\\hero.fbx')).toBe('model')
  })
})
