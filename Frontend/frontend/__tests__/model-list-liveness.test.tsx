/**
 * Model listesinin KAYNAĞI kullanıcıya görünüyor mu.
 *
 * Elle yazılı bulut kataloğu 30 Ağu 2026'da SİLİNDİ (Burak'ın kararı): liste
 * listelediğinden ayrışıyordu ve Groq'un tek modeli 16 Ağu'da kapatılmışken
 * hâlâ tek seçenek olarak duruyordu. Artık iki kaynak var ve ikisi ayrı
 * soruyu cevaplıyor:
 *
 *   * sağlayıcının kendi listesi (kullanıcının anahtarıyla) → doğrulanmış
 *   * OpenRouter'ın açık kataloğu (anahtarsız)              → doğrulanmamış
 *
 * "Böyle bir model var" ile "senin hesabında var" ayrı iddialar, ve
 * ikincisini birincisinden çıkarmak kullanıcıyı çalışmayacak bir modele
 * yollar. Rozet bu ayrımı ekranda tutuyor.
 *
 * Sağlayıcının listesi HİÇ alınamadığında da ayrı bir hâl var: liste
 * doğrulanamadı. Onu "hesabında yok"a çevirmek, ağı olmayan bir makinede
 * çalışan her modeli kullanılamaz göstermek olurdu.
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

describe('doğrulanmışlık rozeti', () => {
  // Elle yazılı bulut kataloğu 30 Ağu 2026'da silindi. Liste artık ya
  // kullanıcının anahtarıyla sağlayıcıdan geliyor (doğrulanmış) ya da
  // OpenRouter'ın açık kataloğundan (doğrulanmamış). İkisi ayrı iddia:
  // "böyle bir model var" ile "senin hesabında var" aynı şey değil.
  it('açık katalogdan gelen model "doğrulanmadı" diye işaretleniyor', () => {
    ciz([MODEL({ verified: false, source: 'openrouter' })])
    expect(screen.getByTestId('model-unverified')).toBeTruthy()
  })

  it('kendi anahtarıyla doğrulanan modelde rozet yok', () => {
    ciz([MODEL({ verified: true, source: 'live', available: true })])
    satirVar()
    expect(screen.queryByTestId('model-unverified')).toBeNull()
  })

  it('alan hiç yoksa rozet yok — tanımsız "doğrulanmadı" DEĞİL', () => {
    ciz([MODEL()])
    satirVar()
    expect(screen.queryByTestId('model-unverified')).toBeNull()
  })
})

describe('liste doğrulanamadığında', () => {
  it('sağlayıcının listesine ulaşılamadıysa bu YAZIYOR', () => {
    ciz([MODEL()], { anthropic: 'unknown' })
    expect(screen.getByTestId('cloud-source-unknown')).toBeTruthy()
  })

  it('liste canlı doğrulandıysa uyarı çıkmıyor', () => {
    ciz([MODEL({ available: true, verified: true, source: 'live' })], { anthropic: 'live' })
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
