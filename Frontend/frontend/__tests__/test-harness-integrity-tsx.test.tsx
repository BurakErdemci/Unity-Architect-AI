/**
 * Bütünlük kapısının İKİNCİ yönü — bilerek `.tsx`.
 *
 * Ölçülmüş arıza (30 Tem 2026 denetimi): tek kapı vardı ve `.ts` idi. O kapı
 * "`include` deseni `.tsx` topluyor mu" diye soruyor, yani `.tsx` kaybını
 * yakalıyor. Ama deseni `.tsx`-only yapınca koşu YEŞİL kaldı ve 243 vaka buhar
 * oldu: kaybolan taraf `.ts` olduğunda kapının KENDİSİ de kaybolanlar arasında.
 * Bir kapı yalnız kendisi ayaktayken bağırabilir.
 *
 * Bu yüzden iki kapı karşılıklı duruyor ve her biri ÖTEKİNİN uzantısını
 * doğruluyor:
 *
 *   test-harness-integrity.test.ts   → desende `.tsx` var mı  (bu dosyayı korur)
 *   test-harness-integrity-tsx.test.tsx → desende `.ts` var mı  (öbürünü korur)
 *
 * Desen hangi yöne daralırsa daralsın, hayatta kalan kapı kırmızı olur.
 * Kendi uzantısını doğrulayan bir kapı hiçbir şey kanıtlamaz — bu dosya
 * bilerek `.ts` toplanmasını sınıyor, `.tsx` toplanmasını değil.
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'

const cfg = readFileSync(resolve(__dirname, '../vitest.config.ts'), 'utf8')
const include = cfg.match(/include:\s*\[[^\]]*\]/)?.[0] ?? ''

describe('vitest yapılandırması .ts kaybına da kapalı', () => {
  it('include deseni .ts dosyalarını topluyor', () => {
    expect(include).toBeTruthy()
    // `{ts,tsx}` ya da düz `.ts` — `tsx`'i çıkarınca geriye `.ts` kalmalı.
    // Düz `/ts/` araması `tsx` ile de eşleşirdi ve iddiayı boşa çıkarırdı.
    expect(include.replace(/tsx/g, '')).toMatch(/\bts\b|\{ts[,}]|\.ts/)
  })

  it('diskte .test.ts dosyası VAR — desen boşa yazılmış bir kural değil', () => {
    const dosyalar = readdirSync(resolve(__dirname))
    expect(dosyalar.filter(f => f.endsWith('.test.ts')).length).toBeGreaterThan(0)
  })

  it('karşı kapı diskte duruyor', () => {
    // Öbür kapı silinirse `.tsx` yönü korumasız kalır ve bunu kimse görmez.
    const dosyalar = readdirSync(resolve(__dirname))
    expect(dosyalar).toContain('test-harness-integrity.test.ts')
  })

  it('bu koşuda .tsx GERÇEKTEN toplandı — dosyanın kendi varlığı kanıt', () => {
    // Bu iddia metin okumuyor: dosya toplanmadıysa hiç koşmaz, yani bu satırın
    // çalışıyor olması `.tsx` toplamanın canlı ölçümü.
    expect(true).toBe(true)
  })
})
