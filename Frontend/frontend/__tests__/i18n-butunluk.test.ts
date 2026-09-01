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
 *
 * ÖLÇÜM NEYİN ÜZERİNDE (denetim bulgusu `checker-self-gap`): bu dosya eskiden
 * `i18n.tsx`'i METİN olarak okuyup satır satır düzenli ifadeyle ayrıştırıyordu.
 * Yani uygulamanın çalışırken kullandığı nesneyi hiç görmüyordu: tabloya
 * çalışma anında eklenen ya da değiştirilen bir değer — örneğin `translations`
 * kurulurken araya sıkıştırılan bir yama — kaynak metinde görünmediği için kapı
 * yemyeşil kalıyordu. Artık gerçek nesne içeri alınıyor. Düzenli ifadenin ayrıca
 * yakaladığı bir şey yoktu (yinelenen anahtarı JS de Map de aynı şekilde son
 * değere indiriyor); tek üstünlüğü "sunulan tablo, yazılan tablonun kendisidir"
 * varsayımıydı ve bunu aşağıdaki kimlik iddiası kaynak metne bakmadan yerine
 * koyuyor.
 */
import { describe, it, expect } from 'vitest'
import {
  translations, tr, en, ceviriUygula, cevir, aktifDilAyarla, type Lang, type TKey,
} from '../renderer/lib/i18n'

const alanlar = (deger: string) =>
  new Set((deger.match(/\{([a-zA-Z][a-zA-Z0-9_]*)\}/g) || []).sort())

const TR = translations.tr
const EN = translations.en

describe('i18n bütünlüğü', () => {
  it('sunulan sözlükler, yazılan tabloların ta kendisi', () => {
    // Denetim bulgusu `regression-test-sensitivity`: burası eskiden yalnızca
    // `translations.tr === tr` diyordu. O kimlik, testin KENDİ içeri aldığı iki
    // ada bakıyor; metni ekrana asıl veren `ceviriUygula`/`cevir` yoluna hiç
    // dokunmuyordu. Yani çeviri fonksiyonu tabloların bir KOPYASINDAN okumaya
    // başlasa — `{...tr}` gibi tek bir yayılım yeter — bu kapı yemyeşil kalır,
    // oysa cümlesi tam olarak bunun olmadığını vaat ediyor.
    //
    // Ölçüm artık davranışsal: yazılan tabloya çalışma anında bir anahtar
    // eklenip aynı anahtar servis yolundan geri isteniyor. Kopyadan okuyan bir
    // uygulama bu eklemeyi göremez, çünkü kopya eklemeden önce alınmıştır.
    const sonda = `__olcum.${Math.random().toString(36).slice(2)}`
    const yollar: Array<[Lang, Record<string, string>]> =
      [['tr', tr as Record<string, string>], ['en', en as Record<string, string>]]
    try {
      for (const [dil, tablo] of yollar) {
        tablo[sonda] = `sonda-${dil}`
        aktifDilAyarla(dil)
        expect(ceviriUygula(dil, sonda)).toBe(`sonda-${dil}`)
        expect(cevir(sonda as TKey)).toBe(`sonda-${dil}`)
      }
    } finally {
      for (const [, tablo] of yollar) delete tablo[sonda]
      aktifDilAyarla('tr')
    }

    // Kimlik iddiası da kalıyor: yukarıdaki sonda `translations` haritasının
    // doğru tabloya baktığını gösterir, bu satırlar da aşağıdaki anahtar/şablon
    // karşılaştırmalarının o tabloların üzerinde koştuğunu.
    expect(TR).toBe(tr)
    expect(EN).toBe(en)
  })

  it('her iki sözlük de doldu — ölçüm boşa çalışmıyor', () => {
    // Bu kapı olmadan aşağıdaki testler boş kümeleri karşılaştırıp yeşil yanar.
    expect(Object.keys(TR).length).toBeGreaterThan(300)
    expect(Object.keys(EN).length).toBeGreaterThan(300)
  })

  it('Türkçede olup İngilizcede olmayan anahtar yok', () => {
    const eksik = Object.keys(TR).filter(k => !(k in EN))
    expect(eksik).toEqual([])
  })

  it('İngilizcede olup Türkçede olmayan anahtar yok', () => {
    const eksik = Object.keys(EN).filter(k => !(k in TR))
    expect(eksik).toEqual([])
  })

  it('hiçbir çeviri boş değil', () => {
    // Boş bir değer eksik bir anahtarla aynı sonucu veriyor — kullanıcı boşluk
    // görüyor — ama anahtar kümesi karşılaştırması onu göremiyor.
    const bos = (['tr', 'en'] as const).flatMap(dil =>
      Object.entries(translations[dil])
        .filter(([, v]) => String(v).trim() === '')
        .map(([k]) => `${dil}:${k}`))
    expect(bos).toEqual([])
  })

  it('şablon alanları iki dilde aynı', () => {
    const uyusmayan: string[] = []
    for (const [k, deger] of Object.entries(TR)) {
      const ingilizce = EN[k]
      if (ingilizce === undefined) continue
      const a = [...alanlar(deger)].join(',')
      const b = [...alanlar(ingilizce)].join(',')
      if (a !== b) uyusmayan.push(`${k}: tr[${a}] en[${b}]`)
    }
    expect(uyusmayan).toEqual([])
  })
})
