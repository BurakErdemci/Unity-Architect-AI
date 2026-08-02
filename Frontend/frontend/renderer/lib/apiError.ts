/**
 * Backend hata gövdesinden KULLANICIYA GÖSTERİLEBİLİR bir metin çıkarır.
 *
 * Neden ayrı bir modül: bu koruma bir siteye yazılmıştı (`useAIConfig`) ve
 * kardeş çağrı yerleri (`ModelSelector`'daki kurulum/giriş dalları) açıkta
 * kalmıştı — bulgu I-3. Bu depoda "düzeltmeyi kopyalamak" adı konmuş bir arıza
 * sınıfı; kopyalanan koruma er ya da geç bir yerde eskiyor. Tek gövde olması,
 * dördüncü bir çağıran geldiğinde de doğru davranmasını sağlıyor.
 *
 * Korunan çökme: FastAPI'nin 422 doğrulama hatasında `detail` bir NESNE DİZİSİ
 * (`[{loc, msg, type}, …]`). `detail || 'yedek'` yazıldığında `||` diziyi
 * truthy görüyor, dizi doğrudan React'e giriyor ve React "Objects are not valid
 * as a React child" fırlatıyor. Yani bu tip kontrolü kozmetik değil, bir
 * çökme kapısı.
 *
 * Boş/boşluk metin de yedeğe düşüyor: gözle boş bir hata kartı, hata
 * göstermemekle aynı şey.
 */
export function apiHataMesaji(err: unknown, yedek: string): string {
  const detail = (err as any)?.response?.data?.detail;
  return typeof detail === 'string' && detail.trim() ? detail : yedek;
}
