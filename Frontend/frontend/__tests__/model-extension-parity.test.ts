import { describe, it, expect } from 'vitest'
import { IMAGE_FILE_EXTENSIONS, MODEL_FILE_EXTENSIONS } from '../main/helpers/file-security'
import { IMAGE_EXTENSIONS, MODEL_EXTENSIONS } from '../renderer/components/model-viewer/extensions'

// The renderer keeps its own copy of the model extension list, because the main
// process module cannot be imported from the renderer bundle. Two copies of one
// decision is this repo's named defect class, so the copy is allowed only with a
// test that fails the moment they drift apart.
//
// Both sides are imported STATICALLY on purpose. An earlier version skipped the
// whole file when the renderer module was missing, which made sense only while
// that module lived on a sibling branch; it is permanently on this branch now,
// and a guard that can silently switch off the only check on a duplicated
// decision fails in exactly the direction that matters.
describe('model uzantı listeleri ayrışmıyor', () => {
  it('MODEL_FILE_EXTENSIONS ile MODEL_EXTENSIONS küme olarak eşit', () => {
    const ana = new Set(MODEL_FILE_EXTENSIONS.map((e) => e.toLowerCase()))
    const renderer = new Set(MODEL_EXTENSIONS.map((e) => e.toLowerCase()))

    expect(renderer.size).toBeGreaterThan(0)
    expect([...renderer].sort()).toEqual([...ana].sort())
  })
})

// Same duplicated-decision problem, same gate. BLOCKED_IMAGE_EXTENSIONS has no
// counterpart on purpose: it is a statement about what Chromium can decode, not
// about what the channel will hand over, and the main process refuses those
// files simply by not whitelisting them.
describe('görsel uzantı listeleri ayrışmıyor', () => {
  it('IMAGE_FILE_EXTENSIONS ile IMAGE_EXTENSIONS küme olarak eşit', () => {
    const ana = new Set(IMAGE_FILE_EXTENSIONS.map((e) => e.toLowerCase()))
    const renderer = new Set(IMAGE_EXTENSIONS.map((e) => e.toLowerCase()))

    expect(renderer.size).toBeGreaterThan(0)
    expect([...renderer].sort()).toEqual([...ana].sort())
  })
})
