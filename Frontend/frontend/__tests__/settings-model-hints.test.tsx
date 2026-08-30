/**
 * Ayarlar ekranındaki model önerileri CANLI listeden gelmeli.
 *
 * 30 Ağu 2026: elle yazılı bulut kataloğu backend'den silindi, ama bu dosyada
 * İKİNCİ bir kopya kalmıştı ve Burak onu sahada gördü — Groq için
 * `llama-3.3-70b-versatile` öneriyordu, oysa o model 16 Ağu'da kapatılmıştı.
 *
 * Kalıbın adı bu depoda kayıtlı: kapı bir dala konup diğeri açık bırakılıyor.
 * Ve bu hâli daha sinsi, çünkü ortada "düzeltilmiş" bir yer var — bakan kişi
 * sorunun kapandığını sanıyor.
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import React from 'react'
import { render, screen, cleanup } from '@testing-library/react'

import { SettingsModal } from '../renderer/components/home/SettingsModal'

afterEach(() => cleanup())

const temel = {
  open: true,
  providersWithKeys: ['anthropic'],
  onChange: () => {},
  onClose: () => {},
  onSave: async () => {},
  onLogout: () => {},
  onDeleteKey: async () => {},
  unityMcpStatus: 'off' as any,
  unityMcpToggling: false,
  onToggleUnityMcp: () => {},
  lang: 'tr' as any,
  onLangChange: () => {},
}

const ciz = (provider: string, cloud: any[], ekler: any = {}) =>
  render(
    <SettingsModal
      {...(temel as any)}
      aiConfig={{ provider_type: provider, model_name: '', api_key: '' } as any}
      availableModels={{ local: [], subscription: [], cloud, ...ekler }}
    />,
  )

const M = (id: string, name: string, provider: string) => ({ id, name, provider })

describe('model önerileri', () => {
  it('seçili sağlayıcının CANLI modellerini gösteriyor', () => {
    ciz('anthropic', [M('claude-opus-9', 'Claude Opus 9', 'anthropic')])
    expect(screen.getByText('Claude Opus 9')).toBeTruthy()
  })

  it('başka sağlayıcının modellerini göstermiyor', () => {
    ciz('anthropic', [
      M('claude-opus-9', 'Claude Opus 9', 'anthropic'),
      M('gpt-9', 'GPT-9', 'openai'),
    ])
    expect(screen.getByText('Claude Opus 9')).toBeTruthy()
    expect(screen.queryByText('GPT-9')).toBeNull()
  })

  it('artık ELLE YAZILI bir model önerisi kalmadı', () => {
    // Liste boşsa hiç öneri çıkmamalı. Eski kod burada sabit bir katalog
    // gösteriyordu ve o katalog ölü bir modeli öneriyordu.
    const { container } = ciz('groq', [])
    expect(container.textContent).not.toContain('llama-3.3-70b-versatile')
    expect(container.textContent).not.toContain('Llama 3.3 70B')
  })

  it('liste boşken çip alanı hiç çizilmiyor', () => {
    const { container } = ciz('groq', [])
    // Tek bir öneri çipi bile yoksa boş bir satır bırakmıyoruz.
    expect(container.querySelectorAll('button').length).toBeGreaterThan(0)  // sağlayıcı kutuları
    expect(container.textContent).not.toContain('(Önerilen)')
  })

  it('çok uzun canlı liste sekiz öneriyle sınırlanıyor', () => {
    // Canlı liste yüzlerce model dönebiliyor; burası bir çip serisi, katalog değil.
    const cok = Array.from({ length: 40 }, (_, i) => M(`m-${i}`, `Model ${i}`, 'anthropic'))
    ciz('anthropic', cok)
    expect(screen.getByText('Model 0')).toBeTruthy()
    expect(screen.getByText('Model 7')).toBeTruthy()
    expect(screen.queryByText('Model 8')).toBeNull()
  })

  it('Ollama seçiliyken yerel modeller kullanılıyor', () => {
    ciz('ollama', [M('claude-opus-9', 'Claude Opus 9', 'anthropic')],
        { local: [M('qwen3:8b', 'Qwen3 8B', 'ollama')] })
    expect(screen.getByText('Qwen3 8B')).toBeTruthy()
    expect(screen.queryByText('Claude Opus 9')).toBeNull()
  })
})
