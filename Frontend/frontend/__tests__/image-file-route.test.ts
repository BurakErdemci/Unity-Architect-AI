/**
 * Which panel a click lands in, for image files.
 *
 * The routing table is the only thing standing between a click on a .png and
 * Monaco being handed binary bytes, and it is also where a new extension gets
 * forgotten. Model routing is re-asserted here as well: images were added
 * BELOW the model checks, so a mistake in the ordering shows up as a model
 * suddenly routing somewhere else.
 */
import { describe, it, expect } from 'vitest'
import {
  routeForFile,
  IMAGE_EXTENSIONS,
  BLOCKED_IMAGE_EXTENSIONS,
  MODEL_EXTENSIONS,
  BLOCKED_MODEL_EXTENSIONS,
} from '../renderer/components/model-viewer/extensions'

describe('routeForFile — images', () => {
  for (const ext of IMAGE_EXTENSIONS) {
    it(`routes ${ext} to the image panel`, () => {
      expect(routeForFile(`Assets/Textures/skin${ext}`)).toBe('image')
    })
  }

  for (const ext of BLOCKED_IMAGE_EXTENSIONS) {
    it(`routes ${ext} to the image panel as blocked`, () => {
      expect(routeForFile(`Assets/Textures/skin${ext}`)).toBe('blocked-image')
    })
  }

  it('is case-insensitive', () => {
    expect(routeForFile('Assets/SKIN.PNG')).toBe('image')
    expect(routeForFile('Assets/Skin.JpEg')).toBe('image')
    expect(routeForFile('Assets/Skin.TGA')).toBe('blocked-image')
  })

  it('treats a dotfile as text, not as an image', () => {
    expect(routeForFile('.png')).toBe('text')
    expect(routeForFile('project/.svg')).toBe('text')
  })

  it('only the basename decides — a directory with a dot is not an image', () => {
    expect(routeForFile('Assets/skin.png/meta')).toBe('text')
    expect(routeForFile('Assets/v1.2/notes')).toBe('text')
    expect(routeForFile('C:\\Users\\b\\Assets\\skin.png')).toBe('image')
  })

  it('leaves text routing alone', () => {
    expect(routeForFile('Assets/Scripts/Player.cs')).toBe('text')
    expect(routeForFile('README.md')).toBe('text')
  })
})

describe('routeForFile — model routing is unchanged by the image branch', () => {
  for (const ext of MODEL_EXTENSIONS) {
    it(`still routes ${ext} to the model panel`, () => {
      expect(routeForFile(`Assets/Models/hero${ext}`)).toBe('model')
    })
  }

  for (const ext of BLOCKED_MODEL_EXTENSIONS) {
    it(`still routes ${ext} as a blocked model`, () => {
      expect(routeForFile(`Assets/Models/hero${ext}`)).toBe('blocked-model')
    })
  }

  it('the two extension sets do not overlap — a file has one route, not two', () => {
    const images = new Set([...IMAGE_EXTENSIONS, ...BLOCKED_IMAGE_EXTENSIONS])
    for (const ext of [...MODEL_EXTENSIONS, ...BLOCKED_MODEL_EXTENSIONS]) {
      expect(images.has(ext)).toBe(false)
    }
  })
})
