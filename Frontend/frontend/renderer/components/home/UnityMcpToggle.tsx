import React from 'react';
import { ShieldAlert } from 'lucide-react';

import { useLang, type LangContextValue } from '../../lib/i18n';
import type { UnityMCPStatus } from '../../hooks/home/useAIConfig';

type Anahtar = Parameters<LangContextValue['t']>[0];

/**
 * Durum → görünüm tablosu.
 *
 * `Record<UnityMCPStatus, …>` olması bilinçli: tip yeni bir durum kazandığı an
 * eksik satır DERLEME hatası veriyor. Ama bu korumanın ölçülmüş bir sınırı var
 * ve tam olarak bu özelliğin doğuş sebebi o: `SettingsModal` aynı deseni
 * kullanıyordu, yine de `blocked` geldiğinde çalışma anında çöküyordu — çünkü
 * hook `res.data.status as UnityMCPStatus` diye YALANCI bir cast yapıyordu ve
 * tipin dışındaki bir değeri içeri sokuyordu. `Record` ancak tip doğruysa
 * koruyor; cast'in altından geçen değer için hiçbir şey yapmıyor.
 */
const TONE: Record<UnityMCPStatus, { btn: string; dot: string; title: Anahtar }> = {
  off: {
    btn: 'bg-white/[0.03] border-white/[0.08] text-slate-500 hover:bg-white/[0.06] hover:text-slate-300',
    dot: 'bg-slate-600',
    title: 'home.unityOpen',
  },
  blocked: {
    // Kırmızı, ve nabız YOK: nabız bu üründe "çalışıyor, bekle" demek
    // (starting/running). `blocked` beklenecek bir şey değil, kullanıcının
    // müdahalesi gereken bir duruş.
    btn: 'bg-red-500/10 border-red-500/30 text-red-400 hover:bg-red-500/20',
    dot: 'bg-red-500',
    title: 'home.unityBlocked',
  },
  starting: {
    btn: 'bg-yellow-500/10 border-yellow-500/30 text-yellow-400',
    dot: 'bg-yellow-400 animate-pulse',
    title: 'home.unityStarting',
  },
  running: {
    btn: 'bg-yellow-500/10 border-yellow-500/30 text-yellow-400 hover:bg-yellow-500/20',
    dot: 'bg-yellow-400 animate-pulse',
    title: 'home.unityConnecting',
  },
  connected: {
    btn: 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/20',
    dot: 'bg-emerald-400',
    title: 'home.unityConnected',
  },
  unknown: {
    // Gri ve nabızsız. Nabız bu üründe "çalışıyor, bekle" demek; burada
    // çalışan bir şey olduğunu bilmiyoruz. Yeşil bırakmak bulgu I-2'ydi:
    // yoklama başarısızken gösterge süresiz `connected` kalıyordu ve
    // kullanıcı yabancı bir sunucuya bağlı olduğunu göremiyordu.
    btn: 'bg-white/[0.03] border-white/[0.08] text-slate-500 hover:bg-white/[0.06] hover:text-slate-300',
    dot: 'bg-slate-500',
    title: 'home.unityUnknown',
  },
};

interface UnityMcpToggleProps {
  status: UnityMCPStatus;
  toggling: boolean;
  /** `blocked` sebebi — backend'den gelir, durumla yaşar. */
  reason: string | null;
  /** Bir toggle denemesinin geçici hatası; 6 sn sonra çağıran tarafça silinir. */
  error: string | null;
  onToggle: () => void;
}

/**
 * Unity MCP durum düğmesi ve durumun gerekçesini taşıyan şeritler.
 *
 * `home.tsx` içinde satır içi 35 satırlık bir JSX bloğuydu ve bu yüzden DOM'da
 * SINANAMIYORDU: `home.tsx` jsdom'da render edilemiyor (Monaco + electron IPC +
 * altı hook). Ayrı bileşen olması bu depoda ölçülmüş bir kuralın gereği —
 * ölçülemeyen bir kontrol başlı başına bir bulgudur, çünkü "düzelttim" iddiası
 * kanıtsız kalır.
 */
export const UnityMcpToggle: React.FC<UnityMcpToggleProps> = ({
  status,
  toggling,
  reason,
  error,
  onToggle,
}) => {
  const { t } = useLang();
  const tone = TONE[status];
  // Sebep yalnız `blocked`'a ait: başka bir durumda elde kalmış bir sebep
  // varsa o bayattır, gösterilmez.
  const sebep = status === 'blocked' ? reason : null;

  return (
    <div className="relative shrink-0">
      <button
        onClick={onToggle}
        // `blocked` BASILABİLİR kalıyor: kullanıcı çakışan sunucuyu kapattıktan
        // sonra tekrar denemesinin tek yolu bu düğme.
        disabled={toggling || status === 'starting'}
        title={t(tone.title)}
        className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-[10px] font-bold uppercase tracking-wider transition-all disabled:opacity-50 whitespace-nowrap shrink-0 ${tone.btn}`}
      >
        <span
          data-testid="unity-mcp-dot"
          aria-hidden="true"
          className={`w-1.5 h-1.5 rounded-full ${tone.dot}`}
        />
        Unity MCP
      </button>

      {(sebep || error) && (
        // İkisi birden olabilir (blocked bir portta toggle denemesi 500 alır),
        // o yüzden dikey yığın: eskiden ikisi de `absolute top-full` olduğu için
        // üst üste binerlerdi.
        <div className="absolute top-full right-0 mt-2 z-50 flex flex-col items-end gap-2">
          {sebep && (
            <div
              role="alert"
              className="flex items-start gap-2 max-w-[360px] px-3 py-2 rounded-lg border border-red-500/40 bg-red-500/10 text-red-300 text-[11px] font-medium shadow-lg"
            >
              <ShieldAlert size={13} className="mt-px shrink-0" />
              <div className="min-w-0">
                <div className="font-bold">{t('unity.blocked')}</div>
                {/* `whitespace-nowrap` BİLEREK yok: sebep süreç adı ve PID
                    taşıyor, yani uzun; eski banner nowrap olduğu için dar
                    pencerede üst bardaki yazılara giriyordu. */}
                <div className="leading-relaxed">{sebep}</div>
              </div>
            </div>
          )}
          {error && (
            <div
              role="alert"
              className="flex items-center gap-2 max-w-[360px] px-3 py-2 rounded-lg border border-red-500/40 bg-red-500/10 text-red-300 text-[11px] font-medium shadow-lg animate-in fade-in slide-in-from-top-1"
            >
              <span className="w-1.5 h-1.5 rounded-full bg-red-400 animate-pulse shrink-0" />
              <span className="min-w-0">{error}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
