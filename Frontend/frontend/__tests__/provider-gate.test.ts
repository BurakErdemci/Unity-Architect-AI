import { describe, it, expect } from 'vitest';
import { sohbetKilitliMi } from '../renderer/lib/providerGate';
import { translations } from '../renderer/lib/i18n';
import type { ProviderReady } from '../renderer/components/home/types';

const hazir = (o: Partial<ProviderReady>): ProviderReady => ({
  ready: true, kind: 'cli', provider: 'claude', needs: null, ...o,
});

describe('sohbet kapısı', () => {
  it('sağlayıcı hazır DEĞİLSE sohbeti kilitliyor', () => {
    expect(sohbetKilitliMi('subscription', hazir({ ready: false, needs: 'install' }))).toBe(true);
    expect(sohbetKilitliMi('anthropic', hazir({ ready: false, kind: 'api', needs: 'apikey' }))).toBe(true);
    expect(sohbetKilitliMi('ollama', hazir({ ready: false, kind: 'local', needs: 'service' }))).toBe(true);
  });

  it('sağlayıcı hazırsa sohbeti AÇIYOR', () => {
    // KARŞIT YÖN: bu testin kırılması, sağlayıcısı çalışan kullanıcının
    // sohbetinin kilitli kalması demektir — kapının en pahalı arıza şekli.
    expect(sohbetKilitliMi('subscription', hazir({ ready: true }))).toBe(false);
  });

  it('ölçüm YOKSA kapıyı açık bırakıyor (fail-open)', () => {
    // Backend'e ulaşamamak "sağlayıcı yok" demek değil. Burada kapatmak,
    // geçici bir hata yüzünden çalışan bir kurulumu kilitlerdi.
    expect(sohbetKilitliMi('subscription', null)).toBe(false);
    expect(sohbetKilitliMi('subscription', undefined)).toBe(false);
  });

  it('bilgi tabanı (kb) modu HER durumda muaf', () => {
    // O mod bir AI sağlayıcısı istemiyor; kapıya takılması işlevi öldürürdü.
    expect(sohbetKilitliMi('kb', hazir({ ready: false, needs: 'apikey' }))).toBe(false);
  });
});

describe('kapı metinleri', () => {
  // Backend yalnız KOD döndürüyor (`needs`); metin buradan geliyor. Bir kod
  // karşılığı olmayan anahtarla gelirse kullanıcı ham kod görür — bu test
  // backend'in ürettiği DÖRT kodun dördünün de iki dilde karşılığı olmasını
  // sabitliyor. Kodlar bilerek elle yazıldı: üretimden import edilse, kod
  // eklendiğinde test de kendiliğinden genişler ve hiçbir şeyi korumaz.
  const kodlar = ['apikey', 'install', 'login', 'service'];

  for (const dil of ['tr', 'en'] as const) {
    it(`${dil}: her 'needs' kodunun karşılığı var`, () => {
      for (const k of kodlar) {
        const anahtar = `gate.needs.${k}`;
        expect(translations[dil][anahtar], `${dil}/${anahtar} eksik`).toBeTruthy();
      }
      for (const anahtar of ['gate.title', 'gate.hint', 'gate.placeholder',
                             'gate.openSettings', 'chat.placeholder']) {
        expect(translations[dil][anahtar], `${dil}/${anahtar} eksik`).toBeTruthy();
      }
    });
  }

  it('yer tutucu artık başka bir ürünün adını taşımıyor', () => {
    // "Ask zap a question..." şablon artığıydı ve kullanıcının ilk yazacağı
    // yerde duruyordu.
    for (const dil of ['tr', 'en'] as const) {
      expect(translations[dil]['chat.placeholder'].toLowerCase()).not.toContain('zap');
    }
  });
});
