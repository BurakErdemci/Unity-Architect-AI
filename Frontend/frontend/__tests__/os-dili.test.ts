import { describe, it, expect } from 'vitest';
import { osDilindenDil } from '../renderer/lib/i18n';

describe('os dilinden uygulama dili', () => {
  it('Türkçe yerel ayarları tr veriyor', () => {
    for (const v of ['tr', 'tr-TR', 'TR-tr', 'tr-CY']) {
      expect(osDilindenDil(v)).toBe('tr');
    }
  });

  it('Türkçe olmayan her şey en veriyor', () => {
    // Bilinmeyen bir yerel ayarda İngilizce'ye düşmek, Türkçe'ye düşmekten
    // kıyaslanamaz derecede daha az yanlış — desteklenen iki dil var.
    for (const v of ['en-US', 'de-DE', 'ja', 'pt-BR', 'zh-CN', 'ar']) {
      expect(osDilindenDil(v)).toBe('en');
    }
  });

  it('yerel ayar hiç yoksa çökmüyor, en veriyor', () => {
    expect(osDilindenDil(null)).toBe('en');
    expect(osDilindenDil(undefined)).toBe('en');
    expect(osDilindenDil('')).toBe('en');
  });

  it('⚠️ tr ÖNEKİ olan başka bir dil kodunu tr saymıyor mu — bilinen sınır', () => {
    // `startsWith('tr')` kaba bir ölçüt. ISO 639-1'de 'tr' ile başlayan başka bir
    // DİL kodu yok, o yüzden bugün güvenli; ama ölçüt bu, ve bir gün eklenirse
    // burası yanlış cevap verir. Sınırı gizlemek yerine yazıyoruz.
    expect(osDilindenDil('tra-XX')).toBe('tr'); // bilinen ve kabul edilmiş yanlış
  });
});
