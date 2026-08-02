/**
 * Birlik dışı durum değeri arayüzü DÜŞÜREMİYOR — bulgu I-1.
 *
 * Eski satır `res.data.status as UnityMCPStatus` idi. `as` çalışma anında
 * hiçbir şey yapmıyor: birliğin dışındaki bir değer (backend'in eklediği yeni
 * bir durum, bozuk bir yanıt) doğrudan state'e giriyordu. İki tüketici de
 * durumu bir `Record<UnityMCPStatus, …>` sözlüğünde arıyor (`TONE[status]`,
 * `UNITY_STATUS_CONFIG[status]`) → `undefined` → `.btn` okuması → TypeError →
 * tüm ağaç unmount → BEYAZ EKRAN.
 *
 * ⚠️ `Record<...>` tipinin koruduğu sanılmıştı ve bu ölçülerek yanlışlandı:
 * `Record` yalnız tip DOĞRUYSA koruyor, cast'in altından geçen değeri
 * görmüyor. Sınıfın kapanması için doğrulamanın DİKİŞTE, çalışma anında
 * olması gerekiyordu.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

import {
  UNITY_MCP_DURUMLARI,
  unityMcpStatusOku,
} from '../renderer/hooks/home/useAIConfig'

beforeEach(() => {
  vi.spyOn(console, 'warn').mockImplementation(() => {})
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('unityMcpStatusOku', () => {
  it('geçerli durumların HEPSİ aynen geçiyor', () => {
    // Listeden türetiliyor: yeni bir durum eklendiğinde bu test onu
    // kendiliğinden kapsıyor, elle güncellenmesi gereken ikinci bir liste yok.
    for (const durum of UNITY_MCP_DURUMLARI) {
      expect(unityMcpStatusOku(durum)).toBe(durum)
    }
  })

  it('birlik DIŞI bir metin unknown a düşüyor', () => {
    expect(unityMcpStatusOku('future')).toBe('unknown')
  })

  it('unknown a düşüyor, off a DEĞİL', () => {
    // Ayırt edici iddia. `off` bir "aç" davetidir; tanımadığımız bir yanıtı
    // davete çevirmek, ölçmediğimiz bir şeyi iddia etmek olurdu (I-2'nin
    // dersi). Yalnız "çökmüyor" diyen bir test bu farkı göremezdi.
    expect(unityMcpStatusOku('future')).not.toBe('off')
    expect(unityMcpStatusOku(undefined)).not.toBe('off')
  })

  it('metin OLMAYAN değerler de unknown a düşüyor', () => {
    // Bozuk bir yanıtın `status` alanı nesne ya da dizi olabilir; `in`/`includes`
    // ile yapılan naif bir kontrol bunlarda patlardı.
    expect(unityMcpStatusOku(undefined)).toBe('unknown')
    expect(unityMcpStatusOku(null)).toBe('unknown')
    expect(unityMcpStatusOku(42)).toBe('unknown')
    expect(unityMcpStatusOku({ status: 'connected' })).toBe('unknown')
    expect(unityMcpStatusOku(['connected'])).toBe('unknown')
  })

  it('tanınmayan değer SESSİZ geçmiyor — konsola düşüyor', () => {
    // Sessiz bir düşüş, backend'in sözleşmeyi bozduğunu gizlerdi: arayüz
    // çalışmaya devam eder ve kimse yeni durumun geldiğini fark etmez.
    unityMcpStatusOku('future')
    expect((console.warn as any).mock.calls.length).toBeGreaterThan(0)
  })

  it('geçerli değerde konsolu KİRLETMİYOR', () => {
    // Yoklama 8 saniyede bir koşuyor; her turda uyarı basmak konsolu
    // kullanılamaz hale getirir ve gerçek uyarıyı görünmez yapardı.
    unityMcpStatusOku('connected')
    expect((console.warn as any).mock.calls.length).toBe(0)
  })
})
