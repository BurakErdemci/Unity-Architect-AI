/**
 * `/available-models` DÜŞTÜĞÜNDE kullanıcı bunu görüyor mu.
 *
 * Denetim bulgusu (30 Ağu 2026): `fetchAvailableModels` hatayı yalnız
 * `console.error` ile bildiriyordu ve başlangıçtaki boş listeleri olduğu gibi
 * bırakıyordu. Model seçici de bulut bölümünü `cloudGroups.length > 0` ile
 * gizlediği için sonuç şuydu: geçici bir katalog/ağ arızası, kullanıcıya
 * "bütün bulut modelleri kayboldu" gibi görünüyordu — hata yok, uyarı yok,
 * yeniden deneme yolu yok.
 *
 * Konsol bir KULLANICI ARAYÜZÜ DEĞİL. Ve boş liste ile alınamamış liste ayrı
 * iki şey: birincisi "seçecek bir şey yok", ikincisi "bilmiyoruz". İkisini aynı
 * boşluğa çevirmek, bu depoda tekrar eden arıza sınıfının ta kendisi.
 *
 * İki ayrı kanal sürülüyor, çünkü ikisi ayrı ana denk geliyor:
 *   • toast   → açılıştaki arıza (dropdown kapalı, uyarı satırı görünmez)
 *   • satır   → dropdown açıkken, yanında YENİDEN DENE ile
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import React from 'react'
import { render, renderHook, screen, cleanup, fireEvent, act } from '@testing-library/react'
import axios from 'axios'

import { useAIConfig } from '../renderer/hooks/home/useAIConfig'
import { ModelSelector } from '../renderer/components/home/ModelSelector'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

/** `/available-models` düşsün, geri kalan uçlar sessizce cevap versin. */
const katalogDussun = (istekler: string[]) =>
  vi.spyOn(axios, 'get').mockImplementation(async (url: any) => {
    istekler.push(String(url))
    if (String(url).includes('/available-models')) throw new Error('catalogue unavailable')
    return { data: { status: 'off' } } as any
  })

const KULLANICI = { id: 1, name: 'x', sessionToken: 't' }

describe('hook: katalog isteği başarısız', () => {
  it('kullanıcıya TOAST atıyor — sessiz kalmıyor', async () => {
    const istekler: string[] = []
    katalogDussun(istekler)
    const toast = vi.fn()
    const { result } = renderHook(() => useAIConfig('http://x', KULLANICI as any, toast))

    await act(async () => { await result.current.fetchAvailableModels() })

    // Kapı: istek gerçekten yapıldı mı. Yapılmadıysa aşağıdaki iddialar
    // hiçbir şey ölçmez ve test boşuna yeşil yanar.
    expect(istekler.some(u => u.includes('/available-models'))).toBe(true)
    expect(toast).toHaveBeenCalled()
    expect(String(toast.mock.calls[0][0])).toContain('Model listesi alınamadı')
    expect(toast.mock.calls[0][1]).toBe('error')
  })

  it('arıza state\'e YAZILIYOR — arayüz onu okuyabilsin', async () => {
    const istekler: string[] = []
    katalogDussun(istekler)
    const { result } = renderHook(() => useAIConfig('http://x', KULLANICI as any, vi.fn()))

    await act(async () => { await result.current.fetchAvailableModels() })

    expect(result.current.availableModels.catalog_error).toBe(true)
  })

  it('istek DÜZELİNCE bayrak kalkıyor — uyarı ekranda çakılı kalmıyor', async () => {
    const istekler: string[] = []
    const casus = katalogDussun(istekler)
    const { result } = renderHook(() => useAIConfig('http://x', KULLANICI as any, vi.fn()))
    await act(async () => { await result.current.fetchAvailableModels() })
    expect(result.current.availableModels.catalog_error).toBe(true)

    casus.mockImplementation(async () => ({
      data: { local: [], subscription: [], cloud: [{ id: 'm', name: 'M', provider: 'anthropic' }] },
    }) as any)
    await act(async () => { await result.current.fetchAvailableModels() })

    expect(result.current.availableModels.catalog_error).toBe(false)
    expect(result.current.availableModels.cloud.length).toBe(1)
  })
})

const secici = {
  aiConfig: { provider_type: 'anthropic', model_name: 'remote-x', api_key: '' } as any,
  setAiConfig: () => {},
  providersWithKeys: [],
  effectiveProvider: 'anthropic',
  displayModelName: 'secili-model',
  isModelDropdownOpen: true,
  setIsModelDropdownOpen: () => {},
  modelOrToggles: {},
  setModelOrToggles: () => {},
  user: null,
  setShowSettings: () => {},
  API: '',
  axios: { get: async () => ({ data: {} }), post: async () => ({ data: {} }) },
  showToast: () => {},
}

const cizSecici = (availableModels: any, tazele = vi.fn()) =>
  render(<ModelSelector {...(secici as any)} availableModels={availableModels} fetchAvailableModels={tazele} />)

describe('dropdown: katalog alınamadı', () => {
  const BOS_HATALI = { local: [], subscription: [], cloud: [], catalog_error: true }

  it('bulut bölümü boş kalıyorsa SEBEBİ yazıyor', () => {
    cizSecici(BOS_HATALI)
    const satir = screen.getByTestId('cloud-catalog-error')
    expect(satir.textContent).toContain('Model listesi alınamadı')
  })

  it('yeniden deneme yolu VAR ve gerçekten yeniden çekiyor', () => {
    // Bir arızayı gösterip çıkış yolu vermemek, yalnız arızayı daha görünür
    // yapardı — kullanıcının yapabileceği bir şey olmalı.
    const tazele = vi.fn()
    cizSecici(BOS_HATALI, tazele)
    fireEvent.click(screen.getByTestId('cloud-catalog-retry'))
    expect(tazele).toHaveBeenCalledTimes(1)
  })

  it('liste GERÇEKTEN boşken (arıza yok) uyarı çıkmıyor', () => {
    // Yanlış kırmızı da bir arıza: hesabında bulut modeli olmayan kullanıcıya
    // her açılışta "liste alınamadı" demek, gerçek arızayı gürültüye gömer.
    cizSecici({ local: [], subscription: [], cloud: [], catalog_error: false })
    expect(screen.queryByTestId('cloud-catalog-error')).toBeNull()
  })

  it('alan hiç yokken de uyarı çıkmıyor — tanımsız "arıza" DEĞİL', () => {
    cizSecici({ local: [], subscription: [], cloud: [] })
    expect(screen.queryByTestId('cloud-catalog-error')).toBeNull()
  })

  it('elde bayat bir liste varken hem liste hem uyarı duruyor', () => {
    // Bayat liste silinmiyor: hiç liste olmamasından iyi, yeter ki bayat
    // olduğu yazsın.
    //
    // `model_name` bilerek hiçbir CLI grubuna uymuyor. Uysaydı açılışta o CLI
    // grubu açılır, bulut grubu KAPALI kalır ve satır hiç çizilmezdi — bu
    // kurulum ilk yazıldığında `claude-x` yüzünden tam olarak öyle oldu.
    cizSecici({
      local: [], subscription: [],
      cloud: [{ id: 'remote-x', name: 'Claude X', provider: 'anthropic' }],
      catalog_error: true,
    })
    expect(screen.getByTestId('cloud-catalog-error')).toBeTruthy()
    expect(screen.getByText('Claude X')).toBeTruthy()
  })
})
