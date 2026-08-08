import type { ProviderReady } from '../components/home/types';

/** Sohbet kilitli mi? — TEK karar noktası.
 *
 * Ürün kararı (8 Ağu 2026): kullanıcıya habersiz hiçbir şey kurulmuyor,
 * dolayısıyla sağlayıcısı olmayan kullanıcı bozuk bir sohbete de düşmemeli.
 * Model seçmiş olmak yetmiyor; arkasındaki şeyin var olması gerekiyor.
 *
 * Neden fonksiyon: karar iki yerde tüketiliyor (composer'ın `disabled`'ı ve
 * gönderme kapısı). İlk yazımda koşul iki kez kopyalanmıştı — ikisi ayrıştığında
 * ortaya çıkan hata "buton açık ama gönderim reddediliyor" gibi görünür ve
 * sebebi görünmez.
 */
export function sohbetKilitliMi(
  providerType: string,
  hazir: ProviderReady | null | undefined,
): boolean {
  // Bilgi tabanı modu bir AI sağlayıcısı istemiyor.
  if (providerType === 'kb') return false;
  // Ölçüm YOK → kapı AÇIK (fail-open). Backend'e ulaşamamak "sağlayıcı yok"
  // demek değil; burada kapatmak çalışan bir kurulumu geçici bir hata yüzünden
  // kilitlerdi, yani kapı çözmek için var olduğu problemi kendisi üretirdi.
  if (!hazir) return false;
  return !hazir.ready;
}
