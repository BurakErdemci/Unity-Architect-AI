import React, { useCallback, useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { RefreshCw, X } from 'lucide-react';
import { useLang } from '../../lib/i18n';
import { SlashCommandCard } from './SlashCommandCard';

type Durum = 'yukleniyor' | 'ok' | 'no_session' | 'busy' | 'unsupported' | 'outdated' | 'error';
interface Rapor { durum: Durum; text?: string }

interface Props {
  open: boolean;
  onClose: () => void;
  API: string;
  sessionToken: string;
  convId: number | null;
  /** Gerçek bağlam metni geldiğinde haber ver — gösterge tahmin yerine bunu kullanır. */
  onContextText?: (text: string) => void;
}

/**
 * `/usage` ve `/context` raporlarını SOHBETE YAZMADAN gösteren panel.
 *
 * Bugüne kadar bu iki rapora ancak sohbete `/usage` yazarak bakılabiliyordu,
 * yani her bakış geçmişe bir mesaj çifti bırakıyordu ve akış sürerken
 * bakılamıyordu. Panel aynı kartları (`SlashCommandCard`) kullanıyor —
 * ayrı bir görünüm yazmak, aynı çıktının iki ayrı yorumunu doğururdu.
 *
 * Dört "veri yok" hâli AYRI AYRI yazılıyor: oturum yok · tur akıyor ·
 * bu sağlayıcıda yok · hata. Hepsini tek bir boş kutuya çevirmek, kullanıcıya
 * "bozuk" ile "henüz değil"i aynı şey gibi gösterirdi.
 */
export const SessionReportPanel: React.FC<Props> = ({
  open, onClose, API, sessionToken, convId, onContextText,
}) => {
  const { t } = useLang();
  const [usage, setUsage] = useState<Rapor>({ durum: 'yukleniyor' });
  const [context, setContext] = useState<Rapor>({ durum: 'yukleniyor' });

  const getir = useCallback(async (kind: 'usage' | 'context'): Promise<Rapor> => {
    if (!API || !convId) return { durum: 'no_session' };
    try {
      const res = await fetch(`${API}/session-report/${convId}/${kind}`, {
        headers: { 'X-Session-Token': sessionToken },
      });
      // 404 = bu uç sunucuda YOK, yani çalışan arka uç bu sürümden eski.
      // "Hata" diye göstermek kullanıcıyı log okumaya yollardı; oysa yapılacak
      // şey belli ve tek: uygulamayı yeniden başlat. Ölçüldü 30 Ağu 2026 —
      // panel ilk denemede tam bu yüzden "Rapor alınamadı" dedi.
      if (res.status === 404) return { durum: 'outdated' };
      if (!res.ok) return { durum: 'error' };
      const d = await res.json();
      if (d.status === 'ok') return { durum: 'ok', text: d.text || '' };
      if (d.status === 'no_session' || d.status === 'busy' || d.status === 'unsupported') {
        return { durum: d.status };
      }
      return { durum: 'error' };
    } catch {
      return { durum: 'error' };
    }
  }, [API, convId, sessionToken]);

  /**
   * Uçuştaki çekimin KİMLİĞİ. Yalnız en son başlatılan çekim state'e yazabilir.
   *
   * Eskiden her `Promise.all` sonucu koşulsuz yazılıyordu. Ölçüldü 30 Ağu 2026:
   * A sohbeti için açılan panel kapatılıp B için yeniden açıldığında, A'nın geç
   * dönen yanıtı B'nin AÇIK panelini eziyordu — kullanıcı yanlış sohbetin
   * raporunu, doğru sanarak okuyordu. Bir raporun hangi sohbete ait olduğu
   * ekranda hiçbir yerde yazmadığı için de fark edilemezdi.
   *
   * Sayaç `convId` karşılaştırmasına tercih edildi: aynı sohbette arka arkaya
   * basılan "yenile" de aynı yarışı üretiyor ve kimlik testi orada `convId`
   * eşit olduğu için geçerdi.
   */
  const nesilRef = useRef(0);

  const tazele = useCallback(async () => {
    const nesil = ++nesilRef.current;
    setUsage({ durum: 'yukleniyor' });
    setContext({ durum: 'yukleniyor' });
    const [u, c] = await Promise.all([getir('usage'), getir('context')]);
    if (nesil !== nesilRef.current) return;
    setUsage(u);
    setContext(c);
    if (c.durum === 'ok' && c.text) onContextText?.(c.text);
  }, [getir, onContextText]);

  useEffect(() => { if (open) void tazele(); }, [open, tazele]);

  if (!open) return null;

  const bos = (r: Rapor) => {
    // `ok` BURADA açıkça sayılıyor. Bu dala yalnız metni boş olan BAŞARILI bir
    // yanıt düşüyor (HTTP 200 + `status: "ok"` + `text: ""`), ve o eskiden
    // sondaki `: 'report.error'` varsayılanına kayıyordu: sunucu doğru
    // çalışmışken kullanıcıya "Rapor alınamadı, ayrıntı loglarda" deniyordu —
    // yani okunacak bir log bile yoktu. Varsayılana düşmeye bırakılan her yeni
    // durum aynı yalanı üretir; onun için dal listelenerek yazılıyor.
    const anahtar = r.durum === 'yukleniyor' ? 'report.loading'
      : r.durum === 'ok' ? 'report.emptyOk'
      : r.durum === 'no_session' ? 'report.noSession'
      : r.durum === 'busy' ? 'report.busy'
      : r.durum === 'unsupported' ? 'report.unsupported'
      : r.durum === 'outdated' ? 'report.outdated'
      : 'report.error';
    return <p data-testid={`report-empty-${r.durum}`} className="text-[11.5px] text-slate-500 px-1 py-2">{t(anahtar as any)}</p>;
  };

  const bolum = (baslik: string, kind: 'usage' | 'context', r: Rapor) => (
    <div className="space-y-1.5">
      <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold px-1">{baslik}</div>
      {r.durum === 'ok' && r.text
        ? <SlashCommandCard command={kind} text={r.text} />
        : bos(r)}
    </div>
  );

  return (
    <motion.div
      data-testid="session-report-panel"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="absolute bottom-full left-0 right-0 mb-2 mx-2 z-30 rounded-xl border border-white/10 bg-[#0b0b0d] shadow-2xl shadow-black/60 overflow-hidden"
    >
      <div className="flex items-center gap-2 px-3 py-2 border-b border-white/[0.07]">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-300">
          {t('report.title')}
        </span>
        <button
          data-testid="report-refresh"
          onClick={() => void tazele()}
          title={t('report.refresh')}
          className="ml-auto p-1 rounded-md text-slate-500 hover:text-slate-200 hover:bg-white/5 transition-colors"
        >
          <RefreshCw size={12} />
        </button>
        <button
          data-testid="report-close"
          onClick={onClose}
          className="p-1 rounded-md text-slate-500 hover:text-slate-200 hover:bg-white/5 transition-colors"
        >
          <X size={13} />
        </button>
      </div>
      <div className="p-3 space-y-3 max-h-[52vh] overflow-y-auto">
        {bolum(t('report.usage'), 'usage', usage)}
        {bolum(t('report.context'), 'context', context)}
      </div>
    </motion.div>
  );
};
