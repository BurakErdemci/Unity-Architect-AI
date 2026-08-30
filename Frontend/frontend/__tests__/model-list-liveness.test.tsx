/**
 * Model listesinin KAYNAĞI kullanıcıya görünüyor mu.
 *
 * Bulut kataloğu elle yazılı ve elle tutulan liste listelediğinden ayrışıyor.
 * Canlı liste onu silmiyor (küratörlü alanlar — görünen ad, OpenRouter
 * karşılığı, ücretli işareti — hiçbir `/v1/models` cevabında yok), yanına üç
 * hâl ekliyor: erişilebilir · erişilemez · BİLİNMİYOR.
 *
 * Üçüncüsü ayrı durmazsa ağı olmayan bir makinede çalışan her model
 * "erişemiyorsun" diye görünür ve kullanıcı denemekten vazgeçer. Buradaki
 * testler tam olarak o çökmeyi engelliyor.
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import React from 'react'
import { render, screen, cleanup } from '@testing-library/react'

import { ModelSelector } from '../renderer/components/home/ModelSelector'

afterEach(() => cleanup())

// `model_name` bilerek hiçbir CLI grubuna uymuyor: uysaydı açılışta o grup
// açılır, bulut grubu kapalı kalır ve satırlar hiç çizilmezdi. Bu kurulum ilk
// yazıldığında tam olarak öyle oldu ve "rozet YOK" testleri boşuna yeşildi —
// hiçbir satır olmadığı için. Aşağıdaki `satirVar` kapısı o yanlış yeşili
// bir daha mümkün kılmıyor.
const temel = {
  aiConfig: { provider_type: 'anthropic', model_name: 'bulut-secili', api_key: '', use_openrouter: false } as any,
  setAiConfig: () => {},
  providersWithKeys: ['anthropic'],
  effectiveProvider: 'anthropic',
  // Satır metniyle ÇAKIŞMAYAN bir ad: aynı metin hem tetikleyici düğmede hem
  // satırda çizilirse `satirVar` iki sonuç bulup patlıyor ve kapı kendi
  // ölçtüğü şeyi ölçemez hale geliyor.
  displayModelName: 'secili-model',
  isModelDropdownOpen: true,
  setIsModelDropdownOpen: () => {},
  modelOrToggles: {},
  setModelOrToggles: () => {},
  user: { id: 1, sessionToken: 'x' } as any,
  fetchAvailableModels: vi.fn(),
  setShowSettings: () => {},
  API: 'http://x',
  axios: { get: vi.fn().mockResolvedValue({ data: {} }), post: vi.fn().mockResolvedValue({ data: {} }) },
  showToast: () => {},
}

const ciz = (cloud: any[], cloud_sources?: Record<string, string>) =>
  render(
    <ModelSelector
      {...(temel as any)}
      availableModels={{ local: [], subscription: [], cloud, cloud_sources }}
    />,
  )

const MODEL = (ek: Record<string, any> = {}) => ({
  id: 'claude-opus-5', name: 'Claude Opus 5', provider: 'anthropic', ...ek,
})

/** Satır gerçekten çizildi mi. Rozet yokluğu ancak satır VARSA bir şey söyler. */
const satirVar = () => expect(screen.getByText('Claude Opus 5')).toBeTruthy()

describe('erişilebilirlik rozeti', () => {
  it('hesapta olmayan model işaretleniyor', () => {
    ciz([MODEL({ available: false, source: 'catalog' })])
    expect(screen.getByTestId('model-unavailable')).toBeTruthy()
  })

  it('hesapta olan modelde rozet yok', () => {
    ciz([MODEL({ available: true, source: 'catalog' })])
    satirVar()
    expect(screen.queryByTestId('model-unavailable')).toBeNull()
  })

  it('BİLİNMİYORken rozet yok — tanımsız, "erişemiyorsun" değil', () => {
    // Bu testin tamamı bu ayrım için var.
    ciz([MODEL()])
    satirVar()
    expect(screen.queryByTestId('model-unavailable')).toBeNull()
  })
})

describe('kaynak rozeti', () => {
  it('yalnız canlı listeden gelen model "yeni" diye işaretleniyor', () => {
    ciz([MODEL({ id: 'claude-opus-6', name: 'Claude Opus 6', source: 'live', available: true })])
    expect(screen.getByTestId('model-live')).toBeTruthy()
  })

  it('katalogdan gelen modelde "yeni" rozeti yok', () => {
    ciz([MODEL({ source: 'catalog', available: true })])
    satirVar()
    expect(screen.queryByTestId('model-live')).toBeNull()
  })
})

describe('liste doğrulanamadığında', () => {
  it('sağlayıcının listesine ulaşılamadıysa bu YAZIYOR', () => {
    ciz([MODEL()], { anthropic: 'unknown' })
    expect(screen.getByTestId('cloud-source-unknown')).toBeTruthy()
  })

  it('liste canlı doğrulandıysa uyarı çıkmıyor', () => {
    ciz([MODEL({ available: true, source: 'catalog' })], { anthropic: 'live' })
    satirVar()
    expect(screen.queryByTestId('cloud-source-unknown')).toBeNull()
  })

  it('anahtar yokluğu "doğrulanamadı" ile karıştırılmıyor', () => {
    // Anahtar yoksa liste zaten sorulmadı; bu bir arıza değil.
    ciz([MODEL()], { anthropic: 'no_key' })
    satirVar()
    expect(screen.queryByTestId('cloud-source-unknown')).toBeNull()
  })
})
