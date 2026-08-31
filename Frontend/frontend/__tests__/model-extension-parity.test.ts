import fs from 'fs'
import path from 'path'
import { describe, it, expect } from 'vitest'
import { MODEL_FILE_EXTENSIONS } from '../main/helpers/file-security'

// The renderer keeps its own copy of the model extension list, because the main
// process module cannot be imported from the renderer bundle. Two copies of one
// decision is this repo's named defect class, so the copy is allowed only with a
// test that fails the moment they drift apart.
//
// The renderer module is built on a sibling branch; until it merges, this file
// skips with the reason below instead of failing red for an absent dependency.
const RENDERER_MODULE = path.resolve(__dirname, '../renderer/components/model-viewer/extensions.ts')
const rendererVar = fs.existsSync(RENDERER_MODULE)

describe.skipIf(!rendererVar)(
  'model uzantı listeleri ayrışmıyor (renderer kopyası yoksa atlanır)',
  () => {
    it('MODEL_FILE_EXTENSIONS ile MODEL_EXTENSIONS küme olarak eşit', async () => {
      // Belirteç parça parça kuruluyor: sabit yazılsaydı Vite modülü DERLEME
      // anında çözmeye çalışır ve dosya henüz yokken paket toplanamaz — test
      // atlanmadan önce kırmızıya düşerdi.
      const belirtec = ['..', 'renderer', 'components', 'model-viewer', 'extensions'].join('/')
      const mod: any = await import(/* @vite-ignore */ belirtec)
      const rendererListesi: string[] = mod.MODEL_EXTENSIONS

      expect(Array.isArray(rendererListesi)).toBe(true)
      const ana = new Set(MODEL_FILE_EXTENSIONS.map((e) => e.toLowerCase()))
      const renderer = new Set(rendererListesi.map((e) => e.toLowerCase()))

      expect([...renderer].sort()).toEqual([...ana].sort())
    })
  },
)
