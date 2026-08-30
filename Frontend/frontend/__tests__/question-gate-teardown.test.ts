/**
 * BİTMİŞ BİR TURUN SORU KARTI EKRANDA KALMAMALI.
 *
 * Arıza (denetim `session-question-stale`, 30 Ağu 2026): `question_needed`
 * kartı `pendingQuestion`'a yazıyor, ama turu bitiren `done` yalnız aktivite
 * satırını temizliyordu. Kapı zaman aşımına düşüp koşum bittiğinde kart
 * duruyordu; kullanıcı onu cevaplarsa `answerQuestion` ÖLÜ bir kapıya POST
 * ediyor ve cevap hiçbir şeyi etkilemiyordu — kullanıcının göremeyeceği bir
 * kayıp, çünkü kart normal şekilde kapanıyor.
 *
 * Testler `useChat`'i gerçek SSE akışıyla sürüyor: ölçülen şey akışın
 * ayrıştırılması değil, tur bitince NE KALDIĞI. Kuyruk da ölçülüyor —
 * gösterilmemiş bir kart da aynı bitmiş tura ait.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'

vi.mock('axios', () => {
  const get = vi.fn().mockResolvedValue({ data: [] })
  const post = vi.fn().mockResolvedValue({ data: {} })
  return { __esModule: true, default: { get, post }, get, post }
})

import { useChat } from '../renderer/hooks/home/useChat'

const API = 'http://x'
const USER = { id: 1, name: 'b', sessionToken: 'tok' } as any
// `subscription` bilerek: diğer dalda `done` olayı `export-utils`'i dinamik
// import edip üretilen dosyaları ayrıştırıyor, ki bu testin ölçtüğü şey değil.
const CONFIG = { provider_type: 'subscription', model_name: 'claude-opus' } as any

const SORU = (gateId: string) => ({
  type: 'question_needed',
  gate_id: gateId,
  questions: [{ question: 'Devam edilsin mi?', options: [{ label: 'evet' }] }],
})

/** Verilen olayları TEK parça SSE gövdesi olarak döndüren bir `fetch`. */
const akis = (...events: any[]) => {
  const body = events.map(e => `data: ${JSON.stringify(e)}\n\n`).join('')
  let verildi = false
  return vi.fn(async (url: any) => {
    if (String(url).includes('/chat-stream')) {
      return {
        body: {
          getReader: () => ({
            read: async () => {
              if (verildi) return { done: true }
              verildi = true
              return { done: false, value: new TextEncoder().encode(body) }
            },
          }),
        },
      }
    }
    return { ok: true, status: 200, json: async () => ({ status: 'ok' }) }
  })
}

const tur = async (...events: any[]) => {
  vi.stubGlobal('fetch', akis(...events))
  const { result } = renderHook(() =>
    useChat(API, USER, CONFIG, null, vi.fn(), vi.fn(), (n: string) => n),
  )
  act(() => { result.current.setActiveConvId(7) })
  await act(async () => {
    await result.current.sendMessage('devam', '', 'tr', 'auto', 'medium', vi.fn(), vi.fn())
  })
  return result
}

describe('soru kapısı — tur bitince kart kalmıyor', () => {
  beforeEach(() => { vi.clearAllMocks() })
  afterEach(() => { vi.unstubAllGlobals() })

  it('cevaplanmamış soru akış sürerken EKRANDA — kart gerçekten tutuluyor', async () => {
    // Karşı kutup: `done` gelmeyen bir akışta kart durmalı. Bu olmadan aşağıdaki
    // testler, soru hiç saklanmasa bile yeşil kalırdı.
    const result = await tur(SORU('q-1'))
    expect(result.current.pendingQuestion?.gateId).toBe('q-1')
  })

  it('done gelince kart kapanıyor — bitmiş tura ait karar sorulmuyor', async () => {
    const result = await tur(SORU('q-expired'), { type: 'done', stop_reason: 'max_iterations', iterations: 300 })
    expect(result.current.pendingQuestion).toBeNull()
    expect(result.current.loading).toBe(false)
  })

  it('error de sonlandırıcı — hata sonrası kart kalmıyor', async () => {
    const result = await tur(SORU('q-1'), { type: 'error', message: 'sağlayıcı düştü' })
    expect(result.current.pendingQuestion).toBeNull()
  })

  it('kuyrukta bekleyen kart da siliniyor', async () => {
    // İki paralel soru: ikincisi kuyruğa giriyor. `done` sonrası birinciyi
    // cevaplamak, kuyruk temizlenmemişse ikinciyi ekrana getirirdi.
    const result = await tur(SORU('q-1'), SORU('q-2'), { type: 'done', stop_reason: 'complete' })
    expect(result.current.pendingQuestion).toBeNull()
    await act(async () => { await (result.current as any).answerQuestion('q-1', {}) })
    expect(result.current.pendingQuestion).toBeNull()
  })
})
