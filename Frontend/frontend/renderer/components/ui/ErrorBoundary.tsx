import React from 'react';
import { AlertTriangle } from 'lucide-react';

import { translations, type Lang } from '../../lib/i18n';

/**
 * Render sırasındaki bir hatayı yakalayıp BEYAZ EKRAN yerine okunabilir bir
 * kart gösterir.
 *
 * ⚠️ Neden var (ölçülmüş arıza, kullanıcı bildirimi 2 Ağu 2026): dosya
 * ağacındaki bir dosyaya tıklandığında pencere bomboş kalıyor ve uygulamayı
 * KAPATIP AÇMAK gerekiyordu. Sebep React'in varsayılan davranışı: yakalanmayan
 * bir render hatasında tüm ağaç unmount ediliyor ve geriye boş bir kök kalıyor.
 * Ölçüm: bu dosyadan önce depoda `componentDidCatch` /
 * `getDerivedStateFromError` SIFIR eşleşme veriyordu.
 *
 * Bu bileşen iki iş yapıyor ve ikisi de ayrı ayrı gerekli:
 *   1. Kurtarma — kullanıcı uygulamayı kapatmadan devam edebiliyor.
 *   2. TEŞHİS — hatanın mesajı ve yığını EKRANDA. Beyaz ekranın en pahalı
 *      yanı bilgiyi yok etmesiydi: kullanıcı "bozuldu" diyebiliyordu ama
 *      NEYİN bozulduğunu kimse göremiyordu. Kart bu yüzden hatayı gizlemiyor.
 *
 * ⚠️ i18n hook'la DEĞİL sözlükten okunuyor. İki ölçülmüş kısıt:
 *   • Hata sınırı olabilmek için class component olmak zorunda (React yalnız
 *     class API'sinde `getDerivedStateFromError` sunuyor) ve class'ta hook
 *     çağrılamaz.
 *   • `LangContext.Provider` `_app.tsx`'te değil `home.tsx` İÇİNDE kuruluyor.
 *     Bu bileşen `home.tsx`'i saran katmanda duruyor, yani `contextType` ile
 *     bağlansa provider'ı göremez ve dil her zaman `tr` kalırdı — sessizce
 *     yanlış, ki bu hiç çevirmemekten kötü. `app-lang` anahtarı dilin zaten
 *     tek kalıcı kaynağı (`home.tsx` de oradan okuyor).
 */

function dilOku(): Lang {
  // localStorage Electron dışı bir bağlamda (SSR, test) yoksa patlamamalı:
  // hata gösteren bir bileşenin kendi kendine hata üretmesi, kullanıcıyı
  // yakalanamayan ikinci bir beyaz ekrana götürürdü.
  try {
    return localStorage.getItem('app-lang') === 'en' ? 'en' : 'tr';
  } catch {
    return 'tr';
  }
}

interface ErrorBoundaryProps {
  children: React.ReactNode;
  /** Testte enjekte edilebilsin diye ayrı: varsayılan `location.reload()`. */
  onReload?: () => void;
}

interface ErrorBoundaryState {
  error: Error | null;
  stack: string | null;
  kopyalandi: boolean;
}

export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null, stack: null, kopyalandi: false };

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    return { error, kopyalandi: false };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    // Bileşen yığını, hatanın kendi yığınından daha kullanışlı: hangi
    // bileşende patladığını söylüyor. İkisini de saklıyoruz.
    this.setState({ stack: info.componentStack ?? null });
    console.error('[ErrorBoundary] render hatası yakalandı:', error, info.componentStack);
  }

  private tamMetin(): string {
    const { error, stack } = this.state;
    return [
      error?.message ?? '',
      error?.stack ?? '',
      stack ? `\nBileşen yığını:${stack}` : '',
    ].filter(Boolean).join('\n');
  }

  private kopyala = () => {
    // Pano yoksa ya da izin verilmezse sessizce geç: kopyalayamamak kartı
    // kullanılamaz yapmamalı, metin zaten ekranda seçilebilir durumda.
    try {
      navigator.clipboard?.writeText(this.tamMetin());
      this.setState({ kopyalandi: true });
    } catch {
      /* pano yok — metin ekranda okunabilir, kayıp yok */
    }
  };

  private yenidenYukle = () => {
    if (this.props.onReload) {
      this.props.onReload();
      return;
    }
    location.reload();
  };

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    const t = (k: string) => translations[dilOku()][k] ?? k;

    return (
      <div
        role="alert"
        className="h-screen bg-[#0B0D12] flex items-center justify-center p-6"
      >
        <div className="bg-[#0a0a0a] border border-slate-700 rounded-2xl shadow-2xl w-[520px] max-w-[92vw] p-5">
          <div className="flex items-start gap-3">
            <div className="shrink-0 w-9 h-9 rounded-full bg-red-500/15 border border-red-500/30 flex items-center justify-center">
              <AlertTriangle size={16} className="text-red-400" />
            </div>
            <div className="min-w-0">
              <h2 className="text-white text-[15px] font-bold mb-1">{t('error.title')}</h2>
              <p className="text-[13px] text-slate-300 leading-relaxed">{t('error.body')}</p>
            </div>
          </div>

          <div className="mt-4">
            <div className="text-[10px] font-mono text-slate-400 mb-1 uppercase tracking-wider">
              {t('error.detailsLabel')}
            </div>
            {/* Hata metni React'in text child'ı olarak giriyor — kaçış React'in
                kendisinde, ayrıca sanitize etmeye gerek yok. `whitespace-pre-wrap`
                yığının okunabilir kalması için; kart büyümesin diye kaydırılıyor. */}
            <pre className="max-h-[220px] overflow-auto custom-scrollbar text-[11px] text-red-300 bg-red-500/10 border border-red-500/40 rounded-lg px-3 py-2 whitespace-pre-wrap break-words font-mono m-0">
              {this.tamMetin()}
            </pre>
          </div>

          <div className="mt-4 flex items-center justify-end gap-2">
            <button
              onClick={this.kopyala}
              className="px-3.5 py-1.5 rounded-lg text-[12px] font-medium text-slate-300 bg-slate-800/60 hover:bg-slate-700/60 transition-colors"
            >
              {this.state.kopyalandi ? t('error.copied') : t('error.copy')}
            </button>
            <button
              onClick={this.yenidenYukle}
              className="px-3.5 py-1.5 rounded-lg text-[12px] font-semibold text-white bg-red-600 hover:bg-red-500 transition-colors"
            >
              {t('error.reload')}
            </button>
          </div>
        </div>
      </div>
    );
  }
}
