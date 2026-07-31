/**
 * Model listesi, token GELDİKTEN SONRA doğru token'la sorulmalı.
 *
 * Yaşanmış arıza (2026-07-31, kullanıcı bildirdi): açılır listede BÜTÜN
 * bulut/API modelleri yok olmuştu ve CLI tarafında Claude Code ile Antigravity
 * boş açılıyordu; Codex/Copilot/Cursor/OpenCode ise düzgün çalışıyordu.
 *
 * Sebep `useAIConfig.fetchAvailableModels`'in bağımlılık listesiydi: gövde
 * `user?.sessionToken` okuyor ama liste yalnız `[API]` idi, yani fonksiyon ilk
 * render'ın `user`'ına kilitleniyordu. O anda token `useAuth`'un başlangıç
 * değeri `'local'`; gerçek token IPC `app-token-get` ile SONRADAN geliyor.
 * Ölçüldü: `X-Session-Token: local` → backend 401, `catch` sessizce yutuyor,
 * `availableModels` sonsuza kadar boş.
 *
 * Asimetrinin sebebi de buydu: `dynamic` alanı olan CLI grupları modellerini
 * `/cli-models/{cli}` ucundan DÜZ fonksiyonlarla çekiyor (her render'da
 * yeniden yaratıldıkları için token'ları güncel), `dynamic` olmayanlar
 * (claude, gemini, kimi) ve bütün bulut grupları ise `availableModels`'a bağlı.
 *
 * Bu dosya iki yönü de ölçüyor: doğru token gidiyor mu, ve gitmeyen bir
 * senaryoda gerçekten kırmızı oluyor mu.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'

vi.mock('axios', () => {
  const get = vi.fn(async () => ({ data: null }))
  const post = vi.fn(async () => ({ data: {} }))
  const defaults = { headers: { common: {} as Record<string, unknown> } }
  return { default: { get, post, defaults }, get, post, defaults }
})

import axios from 'axios'
import { useAIConfig } from '../renderer/hooks/home/useAIConfig'

const mocked = axios as unknown as { get: ReturnType<typeof vi.fn> }

const API = 'http://127.0.0.1:8000'
const noopToast = () => {}

/** `/available-models` çağrılarının taşıdığı X-Session-Token başlıkları. */
const modelTokenlari = (): unknown[] =>
  mocked.get.mock.calls
    .filter(c => typeof c[0] === 'string' && (c[0] as string).includes('/available-models'))
    .map(c => (c[1] as any)?.headers?.['X-Session-Token'])

beforeEach(() => {
  mocked.get.mockClear()
  mocked.get.mockResolvedValue({ data: null })
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

describe('useAIConfig · model listesi GÜNCEL token ile sorulur', () => {
  it('token sonradan gelirse çağrı YENİ token ile gider', async () => {
    const { result, rerender } = renderHook(
      ({ user }) => useAIConfig(API, user, noopToast),
      { initialProps: { user: { id: 1, sessionToken: 'local' } as any } },
    )

    // useAuth'un IPC'den gerçek token'ı çözmesi: `user` yeni bir nesne olur.
    rerender({ user: { id: 1, sessionToken: 'gercek-token' } as any })

    await act(async () => {
      await result.current.fetchAvailableModels()
    })

    // Bağımlılık listesi `[API]`ye geri dönerse burada 'local' görünür.
    expect(modelTokenlari()).toContain('gercek-token')
    expect(modelTokenlari()).not.toContain('local')
  })

  it('yanıt geldiyse liste DOLDURULUR (çağrı yapıldı ≠ liste geldi)', async () => {
    mocked.get.mockResolvedValue({
      data: { local: [], cloud: [{ id: 'claude-opus-5', name: 'Claude Opus 5', provider: 'anthropic' }], subscription: [] },
    })

    const { result } = renderHook(() =>
      useAIConfig(API, { id: 1, sessionToken: 'gercek-token' } as any, noopToast),
    )

    await act(async () => {
      await result.current.fetchAvailableModels()
    })

    expect(result.current.availableModels.cloud).toHaveLength(1)
  })

  it('TERS YÖN: 401 yutulursa liste BOŞ kalır — arızanın kullanıcıya görünen hali', async () => {
    // Bu testin işi düzeltmeyi korumak değil, arızanın ŞEKLİNİ sabitlemek:
    // istek patlarsa `catch` sessiz kalıyor ve tüketiciler (bulut bölümü,
    // claude/gemini/kimi grupları) boş bir listeyle karşılaşıyor.
    mocked.get.mockRejectedValue(Object.assign(new Error('401'), { response: { status: 401 } }))

    const { result } = renderHook(() =>
      useAIConfig(API, { id: 1, sessionToken: 'local' } as any, noopToast),
    )

    await act(async () => {
      await result.current.fetchAvailableModels()
    })

    expect(result.current.availableModels.cloud).toHaveLength(0)
    expect(result.current.availableModels.subscription).toHaveLength(0)
  })
})
