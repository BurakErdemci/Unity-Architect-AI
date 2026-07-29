/**
 * Oturum token'ı kurulumu — "hazır" demek NE ZAMAN doğru?
 *
 * Dış denetim bulgusu `invalid-auth-readiness` (2026-07-29): `useAuth`
 * `ipc.invoke('app-token-get')` hatasını sessizce yutup token'ı `'local'`
 * bırakıyor ve `ready`'yi yine de true yapıyordu. `'local'` iki farklı durumu
 * temsil ediyor ve ikisi karıştırılıyordu:
 *
 *   (a) IPC HİÇ YOK (tarayıcı/dev modu) → `'local'` MEŞRU; backend
 *       `UNITYAI_ALLOW_NO_TOKEN=1` ile bunu kabul ediyor.
 *   (b) Electron içindeyiz, IPC var ama çağrı düştü → `'local'` YANLIŞ bir
 *       token; her istek 401/503 alacak.
 *
 * (b) durumunda `ready` true olduğu için MCP yoklaması açılıyor, her saniye
 * sessizce yutulan bir 401 üretiyor ve onay kartı yolu HİÇBİR iz bırakmadan
 * ölüyordu. Bu dosya iki durumun ayrıldığını ölçüyor — ve ters yönü de:
 * dev modunda gereksiz hata üretilmediğini.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'

vi.mock('axios', () => {
  const defaults = { headers: { common: {} as Record<string, unknown> } }
  return { default: { defaults }, defaults }
})

import axios from 'axios'
import { useAuth } from '../renderer/hooks/home/useAuth'

const mockedAxios = axios as unknown as { defaults: { headers: { common: Record<string, unknown> } } }

const API = 'http://127.0.0.1:8000'

beforeEach(() => {
  mockedAxios.defaults.headers.common = {}
  vi.spyOn(console, 'error').mockImplementation(() => {})
  delete (window as any).ipc
})

afterEach(() => {
  vi.restoreAllMocks()
  delete (window as any).ipc
})

describe('useAuth · token alınamadığında sessiz kalmaz', () => {
  it('IPC hata fırlatırsa tokenError DOLU olur', async () => {
    ;(window as any).ipc = { invoke: vi.fn().mockRejectedValue(new Error('EPIPE')) }
    const { result } = renderHook(() => useAuth(API, true))

    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.tokenError).toContain('EPIPE')
  })

  it('IPC boş string dönerse de BAŞARISIZLIK sayılır', async () => {
    // Eskiden doğrudan atanıyordu; `X-Session-Token: ''` başlığıyla backend
    // 503 dönüyor ve ürün "çalışıyor ama hiçbir şey olmuyor" haline geliyordu.
    ;(window as any).ipc = { invoke: vi.fn().mockResolvedValue('') }
    const { result } = renderHook(() => useAuth(API, true))

    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.tokenError).not.toBeNull()
  })

  it('IPC undefined dönerse başlık undefined YAZILMAZ', async () => {
    ;(window as any).ipc = { invoke: vi.fn().mockResolvedValue(undefined) }
    const { result } = renderHook(() => useAuth(API, true))

    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.tokenError).not.toBeNull()
    // Değer ne olursa olsun STRING olmalı: `undefined` bir başlık, gönderilmeyen
    // bir başlıktır ve teşhisi imkânsızlaştırır.
    expect(typeof mockedAxios.defaults.headers.common['X-Session-Token']).toBe('string')
  })

  it('TERS YÖN: IPC hiç yoksa (dev modu) hata ÜRETİLMEZ', async () => {
    // Burada `'local'` gerçek değer, arıza değil. Bunu hata saymak her dev
    // oturumunda yanlış bir uyarı basardı ve gerçek arızayı gömerdi.
    const { result } = renderHook(() => useAuth(API, true))

    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.tokenError).toBeNull()
    expect(mockedAxios.defaults.headers.common['X-Session-Token']).toBe('local')
  })

  it('TERS YÖN: IPC geçerli token dönerse hata YOK ve başlık o token', async () => {
    ;(window as any).ipc = { invoke: vi.fn().mockResolvedValue('tok-abc') }
    const { result } = renderHook(() => useAuth(API, true))

    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.tokenError).toBeNull()
    expect(mockedAxios.defaults.headers.common['X-Session-Token']).toBe('tok-abc')
    expect(result.current.user.sessionToken).toBe('tok-abc')
  })

  it('backend hazır değilken hiç denenmez', async () => {
    const invoke = vi.fn().mockResolvedValue('tok')
    ;(window as any).ipc = { invoke }
    const { result } = renderHook(() => useAuth(API, false))

    expect(invoke).not.toHaveBeenCalled()
    // `isLoading` true kalmalı: token yokken `enabled` kapısı açılmamalı.
    expect(result.current.isLoading).toBe(true)
  })
})
