/**
 * Backend hata gövdesinin kullanıcıya ulaşırken ÇÖKMEMESİ — bulgu I-3.
 *
 * FastAPI 422'de `detail` bir NESNE DİZİSİ döndürüyor. `detail || 'yedek'`
 * yazıldığında `||` diziyi truthy görüyor, dizi React'e giriyor ve React
 * "Objects are not valid as a React child" fırlatıyor — yani bir toast denemesi
 * tüm arayüzü düşürebiliyordu.
 *
 * Koruma `useAIConfig`'de vardı, `ModelSelector`'da YOKTU: düzeltme
 * KOPYALANMIŞTI. Bu yüzden testler yalnız fonksiyonu değil, ÇAĞIRANLARIN
 * hepsinin ona bağlı olduğunu da ölçüyor.
 */
import { readFileSync } from 'fs'
import { resolve } from 'path'

import { describe, it, expect } from 'vitest'

import { apiHataMesaji } from '../renderer/lib/apiError'

const yanit = (detail: unknown) => ({ response: { data: { detail } } })

describe('apiHataMesaji', () => {
  it('metin detail i AYNEN geçiriyor', () => {
    // Ters yön: her zaman yedeğe düşen bir mutant "çökmüyor" testlerini
    // geçerdi ama sebebi kullanıcıdan gizlerdi. 500 gövdesi portu tutan
    // sürecin ADINI taşıyor ve eyleme dönüşen kısım orası.
    expect(apiHataMesaji(yanit('node · PID 4242 portu tutuyor'), 'yedek'))
      .toBe('node · PID 4242 portu tutuyor')
  })

  it('422 DİZİSİ yedeğe düşüyor — React e dizi basılmıyor', () => {
    const sonuc = apiHataMesaji(
      yanit([{ loc: ['body'], msg: 'field required', type: 'missing' }]),
      'Kurulum başlatılamadı.',
    )
    expect(sonuc).toBe('Kurulum başlatılamadı.')
    expect(typeof sonuc).toBe('string')
  })

  it('nesne detail i de yedeğe düşüyor', () => {
    expect(apiHataMesaji(yanit({ msg: 'hata' }), 'yedek')).toBe('yedek')
  })

  it('gözle boş metin yedeğe düşüyor', () => {
    // Boş bir hata kartı, hata göstermemekle aynı şey.
    expect(apiHataMesaji(yanit('   '), 'yedek')).toBe('yedek')
    expect(apiHataMesaji(yanit(''), 'yedek')).toBe('yedek')
  })

  it('gövde hiç yokken patlamıyor', () => {
    expect(apiHataMesaji(new Error('ağ koptu'), 'yedek')).toBe('yedek')
    expect(apiHataMesaji(undefined, 'yedek')).toBe('yedek')
    expect(apiHataMesaji(null, 'yedek')).toBe('yedek')
  })
})

describe('korumanın ÇAĞIRANLARI — kopyalanmış düzeltme geri gelmesin', () => {
  /**
   * Kaynak düzeyinde nöbetçi. Sebebi ölçülmüş: I-3 tam olarak "koruma bir
   * siteye yazıldı, kardeşi açık kaldı" hatasıydı. Yalnız fonksiyonu test
   * etmek o hatayı bir kez daha kaçırırdı — fonksiyon doğruydu zaten,
   * çağrılmıyordu.
   */
  const oku = (p: string) => readFileSync(resolve(__dirname, p), 'utf8')

  it('ModelSelector ham detail i doğrudan toast a vermiyor', () => {
    const src = oku('../renderer/components/home/ModelSelector.tsx')
    expect(src).not.toMatch(/showToast\(\s*[^)]*\.detail\s*\|\|/)
    expect(src).toContain('apiHataMesaji')
  })

  it('useAIConfig aynı gövdeye bağlı — ikinci bir kopya yok', () => {
    const src = oku('../renderer/hooks/home/useAIConfig.ts')
    expect(src).toContain('apiHataMesaji')
    expect(src).not.toMatch(/typeof\s+detail\s*===\s*'string'/)
  })
})
