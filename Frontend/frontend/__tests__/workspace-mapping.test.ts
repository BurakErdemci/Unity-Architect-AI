/**
 * Host↔container workspace mapping — the behaviour, not the source text.
 *
 * These exist because a source-scanning assertion proved worthless in the
 * mutation round of the very fix it guarded: the IPC handler contained two
 * `return ''` statements, so breaking one left "the source contains `return ''`"
 * satisfied and the suite green (measured 31 Aug 2026). The logic moved into a
 * pure module so it could be exercised instead of read.
 *
 * The class being guarded, stated once: Docker exposes exactly ONE host tree.
 * A translation that answers for folders outside it aliases every project onto
 * the mounted one — the editor works in the folder you picked while every agent
 * works in a different one, and both halves report success.
 */
import { describe, it, expect } from 'vitest'
import path from 'path'
import {
  DOCKER_WORKSPACE_MOUNT,
  hostRootFrom,
  toBackendPath,
  toHostPath,
} from '../main/helpers/workspace-mapping'

const KOK = path.resolve(path.sep === '\\' ? 'C:\\host\\game' : '/host/game')
const DISARISI = path.resolve(path.sep === '\\' ? 'C:\\host\\other' : '/host/other')

describe('hostRootFrom — bilinemeyen kök reddedilir', () => {
  it('mutlak yol çözülür', () => {
    expect(hostRootFrom(KOK)).toBe(KOK)
  })

  it('göreli yol REDDEDİLİR — iki taraf onu farklı çözüyor', () => {
    // Compose'un çalışma dizini depo kökü, Electron'unki Frontend/frontend.
    // Aynı dize iki farklı klasörü adlandırıyor; tahmin etmek her açılışta son
    // çalışma alanını sessizce düşürüyordu.
    expect(hostRootFrom('./Backend')).toBe('')
    expect(hostRootFrom('Backend')).toBe('')
  })

  it('tanımsız da reddedilir', () => {
    expect(hostRootFrom(undefined)).toBe('')
    expect(hostRootFrom('')).toBe('')
  })
})

describe('toBackendPath — yalnız bağlanan ağaç adlandırılabilir', () => {
  it('kökün kendisi mount noktasına eşlenir', () => {
    expect(toBackendPath(KOK, KOK)).toBe(DOCKER_WORKSPACE_MOUNT)
  })

  it('alt klasör POSIX ayırıcılarla eşlenir', () => {
    const alt = path.join(KOK, 'Assets', 'Scripts')
    // Konteyner Linux; ana makine Windows olsa bile cevap ters bölü içermez.
    expect(toBackendPath(alt, KOK)).toBe(`${DOCKER_WORKSPACE_MOUNT}/Assets/Scripts`)
  })

  it('mount DIŞINDAKİ klasör için cevap YOKTUR', () => {
    // Asıl bulgu buydu: burada mount noktasını döndürmek, kullanıcının seçtiği
    // projeyi bağlanan projeyle karıştırıyordu.
    expect(toBackendPath(DISARISI, KOK)).toBe('')
  })

  it('üst klasör de dışarıdadır', () => {
    expect(toBackendPath(path.dirname(KOK), KOK)).toBe('')
  })

  it('kök bilinmiyorsa cevap yoktur', () => {
    expect(toBackendPath(KOK, '')).toBe('')
  })

  it('yol adı kökün ÖNEKİNİ paylaşan başka bir klasör kabul edilmez', () => {
    // `/host/game-yedek`, `/host/game` ile aynı dize önekini taşıyor ama onun
    // içinde değil. Düz `startsWith` ile yazılsaydı burası kırılırdı.
    expect(toBackendPath(`${KOK}-yedek`, KOK)).toBe('')
  })
})

describe('toHostPath — geri çeviri', () => {
  it('mount noktası köke döner', () => {
    expect(toHostPath(DOCKER_WORKSPACE_MOUNT, KOK)).toBe(KOK)
  })

  it('mount altındaki yol ana makine biçimine döner', () => {
    expect(toHostPath(`${DOCKER_WORKSPACE_MOUNT}/Assets/Scripts`, KOK))
      .toBe(path.join(KOK, 'Assets', 'Scripts'))
  })

  it('mount altında OLMAYAN bir yol reddedilir', () => {
    // Bu, bu çeviri var olmadan önce kaydedilmiş bir değer ya da başka bir
    // projeye ayarlı bir koşumdan kalma. Açmak, düzenleyiciyi bir ağaca,
    // backend'i başka bir ağaca koyardı.
    expect(toHostPath('/home/biri/eski-proje', KOK)).toBe('')
  })

  it('kök bilinmiyorsa cevap yoktur', () => {
    expect(toHostPath(DOCKER_WORKSPACE_MOUNT, '')).toBe('')
  })
})

describe('gidiş-dönüş', () => {
  it('mount altındaki her yol kendine döner', () => {
    for (const parca of [[], ['Assets'], ['Assets', 'Scripts', 'Player.cs']]) {
      const host = path.join(KOK, ...parca)
      expect(toHostPath(toBackendPath(host, KOK), KOK)).toBe(host)
    }
  })
})
