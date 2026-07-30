/**
 * Test koşucusunun kendisini sınayan kapı.
 *
 * Ölçülmüş arıza (2026-07-30): `vitest.config.ts`'in `include` deseni yalnız
 * `__tests__/**\/*.test.ts` idi. Üç yeni `.test.tsx` dosyası diske yazıldı,
 * koşu "11 dosya / hepsi geçti" dedi ve **hiçbiri koşmadı**. Sahte yeşilin en
 * pahalı biçimi bu: kırmızı bir test görmemek değil, testin var olduğunu
 * sanmak.
 *
 * Bu dosya BİLEREK `.ts`: desen bozulduğunda `.tsx` testleri sessizce
 * kaybolurken bu kapı ayakta kalır ve bağırır. Kendi kendini doğrulayan bir
 * kapı hiçbir şeyi doğrulamaz.
 *
 * Aynı sebeple `setupFiles` de burada sınanıyor: onun yokluğunda Node 25'in
 * kullanılamaz `localStorage` global'i 42 testi düşürüyor (gerekçe
 * `vitest.setup.ts`'in başında).
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'

const cfg = readFileSync(resolve(__dirname, '../vitest.config.ts'), 'utf8')

describe('vitest yapılandırması test kaybına kapalı', () => {
  it('include deseni .tsx dosyalarını da topluyor', () => {
    const include = cfg.match(/include:\s*\[[^\]]*\]/)?.[0] ?? ''
    expect(include).toBeTruthy()
    expect(include).toMatch(/tsx/)
  })

  it('diskte .test.tsx dosyası VAR — yani desen boşa yazılmış bir kural değil', () => {
    // İki iddia birlikte anlam taşıyor: desen `.tsx` içeriyor VE toplanacak
    // `.tsx` dosyası var. Biri olmadan diğeri bir şey kanıtlamıyor.
    const dosyalar = readdirSync(resolve(__dirname))
    expect(dosyalar.filter(f => f.endsWith('.test.tsx')).length).toBeGreaterThan(0)
  })

  it('setupFiles bağlı — localStorage kurulumu koşuyor', () => {
    expect(cfg).toMatch(/setupFiles:\s*\[[^\]]*vitest\.setup/)
  })

  it('kurulum dosyası localStorage ı gerçekten tanımlıyor', () => {
    const setup = readFileSync(resolve(__dirname, '../vitest.setup.ts'), 'utf8')
    expect(setup).toMatch(/defineProperty/)
    expect(setup).toMatch(/localStorage/)
    // Kurulumun kendi işi: bir testin yazdığı anahtar diğerine sızmasın.
    expect(setup).toMatch(/beforeEach/)
  })

  it('localStorage bu koşuda KULLANILABİLİR — kurulumun etkisi ölçülüyor', () => {
    // Yukarıdaki üç iddia metin okuyor; bu davranışı ölçüyor. Node'un
    // ham global'inde `getItem` bir fonksiyon DEĞİL, dolayısıyla bu iddia
    // kurulum çalışmadığı an kırılır.
    expect(typeof window.localStorage.getItem).toBe('function')
    window.localStorage.setItem('kapi', 'acik')
    expect(window.localStorage.getItem('kapi')).toBe('acik')
  })
})
