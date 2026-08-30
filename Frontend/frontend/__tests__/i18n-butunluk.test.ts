/**
 * İki dilin AYNI anahtar kümesini taşıması ve şablon alanlarının uyuşması.
 *
 * Burak sordu (30 Ağu 2026): "bu eklediklerin sadece Türkçe değil mi, İngilizce
 * modda değişmiyor mu?" — soru haklıydı ve cevabı ölçmek gerekiyordu. O ölçüm
 * elle yapıldı; bu dosya onu kalıcı bir kapıya çeviriyor, çünkü elle yapılan
 * kontrol bir dahaki eklemede yapılmaz.
 *
 * Eksik bir anahtar SESSİZ arıza: `cevir()` bulamadığı anahtar için ham
 * anahtarı ya da boş metin döndürür, hiçbir test kırılmaz ve kullanıcı
 * `report.busy` diye bir şey görür.
 *
 * Şablon alanları da kontrol ediliyor: `{model}` bir dilde varken diğerinde
 * yoksa, o dilde bilgi sessizce DÜŞER — cümle kurallı görünür ama modelin adı
 * yoktur.
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const kaynak = readFileSync(resolve(__dirname, '../renderer/lib/i18n.tsx'), 'utf8')

const blok = (bas: string, son?: string) => {
  const i = kaynak.indexOf(bas)
  const j = son ? kaynak.indexOf(son, i) : kaynak.length
  return kaynak.slice(i, j === -1 ? kaynak.length : j)
}

/** `'anahtar': 'metin',` satırlarını topla. Çok satırlı değerler yok. */
const girdiler = (b: string): Map<string, string> => {
  const m = new Map<string, string>()
  for (const satir of b.split('\n')) {
    const e = satir.match(/^\s*'([a-zA-Z][a-zA-Z0-9_.]*)'\s*:\s*(.+),\s*$/)
    if (e) m.set(e[1], e[2])
  }
  return m
}

const TR = girdiler(blok('const tr = {', 'const en'))
const EN = girdiler(blok('const en'))

const alanlar = (deger: string) =>
  new Set((deger.match(/\{([a-zA-Z][a-zA-Z0-9_]*)\}/g) || []).sort())

describe('i18n bütünlüğü', () => {
  it('her iki sözlük de doldu — ayrıştırıcı boşa çalışmıyor', () => {
    // Bu kapı olmadan aşağıdaki testler boş kümeleri karşılaştırıp yeşil yanar.
    expect(TR.size).toBeGreaterThan(300)
    expect(EN.size).toBeGreaterThan(300)
  })

  it('Türkçede olup İngilizcede olmayan anahtar yok', () => {
    const eksik = [...TR.keys()].filter(k => !EN.has(k))
    expect(eksik).toEqual([])
  })

  it('İngilizcede olup Türkçede olmayan anahtar yok', () => {
    const eksik = [...EN.keys()].filter(k => !TR.has(k))
    expect(eksik).toEqual([])
  })

  it('şablon alanları iki dilde aynı', () => {
    const uyusmayan: string[] = []
    for (const [k, tr] of TR) {
      const en = EN.get(k)
      if (en === undefined) continue
      const a = [...alanlar(tr)].join(',')
      const b = [...alanlar(en)].join(',')
      if (a !== b) uyusmayan.push(`${k}: tr[${a}] en[${b}]`)
    }
    expect(uyusmayan).toEqual([])
  })
})
