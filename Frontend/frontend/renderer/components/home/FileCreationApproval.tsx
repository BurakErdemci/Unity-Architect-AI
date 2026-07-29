import { motion } from 'framer-motion';
import { useLang } from '../../lib/i18n';
import { 
  Check, 
  CheckCircle2, 
  ChevronRight, 
  FileCode, 
  SkipForward, 
  Zap, 
  XCircle,
  Eye
} from 'lucide-react';
import { useState, useEffect } from 'react';

export interface PendingFile {
  name: string;
  code: string;
  suggestedPath: string;
  originalCode?: string;
}

interface FileCreationApprovalProps {
  files: PendingFile[];
  /**
   * `true` = dosya GERÇEKTEN yazıldı/onay iletildi. Yalnız `true` dönerse kart
   * dosyayı "oluşturuldu" sayar.
   *
   * Neden `Promise<void>` değil (ölçüldü 2026-07-29): tek sinyal istisnaydı ve
   * asıl yazma yolu HİÇ throw etmiyor — `ipc.invoke('write-file')`
   * `{success:false, error}` dönüyor (main/background.ts:397-418). Yani
   * `.catch()` hiç ateşlenmiyordu ve reddedilen dosya "İşlem Tamamlandı"
   * kartında oluşturulmuş gibi listeleniyordu.
   */
  onAcceptOne: (file: PendingFile) => Promise<boolean>;
  onSkipOne: (file: PendingFile) => void;
  /** `true` = dosyaların HEPSİ yazıldı. Kısmi başarı `false`'tur; hangi dosyanın
   *  neden yazılamadığını çağıran kendi bildirir (dosya başına toast). */
  onAcceptAll: (files: PendingFile[]) => Promise<boolean>;
  /** Kararlar bittikten SONRA kartı kapatır ("Kapat"). Bir karar DEĞİLDİR. */
  onDone: () => void;
  /**
   * Kullanıcı karar vermeden kartı kapattı ("İptal") — bu bir KARARDIR.
   *
   * Neden `onDone`'dan ayrı (ölçüldü 2026-07-29, iki-varyant turu): tek prop iki
   * zıt anlamı taşıyordu. Çağıran taraf `onDone`'u "akış kendiliğinden kapandı"
   * diye okuyup bastırılan kararı SESSİZ geçiyordu; aynı sessizlik "İptal"e
   * basan kullanıcıya da uygulanınca, onay uçuştayken basılan İptal hiçbir iz
   * bırakmadan yutuluyordu — `stale-decision-latch` sınıfının sessiz biçimi.
   *
   * Opsiyonel ve varsayılanı `onDone`: mevcut çağıranlar (ChatPanel'in sohbet
   * akışı) davranışlarını aynen koruyor, ayrımı yalnız ihtiyacı olan taraf yapar.
   */
  onCancel?: () => void;
  onOpenFile?: (path: string) => void;
  autoAccept?: boolean;
  setDiffFile: (file: PendingFile | null) => void;
}

export const FileCreationApproval = ({
  files,
  onAcceptOne,
  onSkipOne,
  onAcceptAll,
  onDone,
  onCancel,
  onOpenFile,
  autoAccept,
  setDiffFile
}: FileCreationApprovalProps) => {
  const { t } = useLang();
  const [currentIdx, setCurrentIdx] = useState(0);
  const [done, setDone] = useState<Set<number>>(new Set());
  const [skipped, setSkipped] = useState<Set<number>>(new Set());
  // Yazılamayanlar ayrı tutulur: `done`'a katmak yalanın ta kendisiydi,
  // `skipped`'a katmak da yanlış olurdu (kullanıcı atlamadı, sistem reddetti).
  const [failed, setFailed] = useState<Set<number>>(new Set());
  // "Tümünü Onayla" başarısızlığı ayrı bir bayrak: toplu yolda hangi dosyanın
  // yazıldığı bilinmiyor, o yüzden dosya bazında işaretleme YAPILMIYOR.
  const [bulkFailed, setBulkFailed] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [allDone, setAllDone] = useState(false);

  const remaining = files.length - done.size - skipped.size - failed.size;

  // Dosya değiştiğinde ana editörü güncelle
  useEffect(() => {
    if (!allDone && files[currentIdx]) {
      setDiffFile(files[currentIdx]);
    }
    return () => setDiffFile(null);
  }, [currentIdx, allDone, files]);

  useEffect(() => {
    if (autoAccept && !allDone && !processing && files.length > 0) {
      handleAcceptAll();
    }
  }, [autoAccept]);

  /**
   * Bir dosya çözüldükten (yazıldı / atlandı / başarısız) sonra sıradakine geç,
   * hepsi çözüldüyse özet kartına düş. `done`/`skipped`/`failed` bu noktada hâlâ
   * bayat (setState henüz uygulanmadı), o yüzden çözülen dosya `+1` ile sayılır —
   * mevcut davranış, korundu.
   */
  const advance = (idx: number) => {
    const next = files.findIndex(
      (_, i) => !done.has(i) && !skipped.has(i) && !failed.has(i) && i !== idx,
    );
    if (next !== -1) setCurrentIdx(next);
    else if (done.size + skipped.size + failed.size + 1 === files.length) {
      setAllDone(true);
      setDiffFile(null);
    }
  };

  const handleAccept = async (idx: number) => {
    const file = files[idx];
    if (!file || processing || done.has(idx)) return;
    setProcessing(true);
    // Eskiden burada `.catch()` + KOŞULSUZ `setDone` vardı. Yazma yolu hiç throw
    // etmediği için `.catch` ölü koddu ve reddedilen dosya "oluşturuldu"
    // listesine giriyordu. `.catch` yine duruyor (beklenmedik istisna hâlâ
    // olabilir) ama artık bir DEĞERE — `false`'a — çevriliyor.
    const ok = await onAcceptOne(file).catch(err => { console.error(err); return false; });
    setProcessing(false);
    if (ok) setDone(prev => new Set([...prev, idx]));
    else setFailed(prev => new Set([...prev, idx]));
    advance(idx);
  };

  const handleSkip = (idx: number) => {
    const file = files[idx];
    if (!file || done.has(idx)) return;
    onSkipOne(file);
    setSkipped(prev => new Set([...prev, idx]));
    advance(idx);
  };

  const handleAcceptAll = async () => {
    if (processing) return;
    setProcessing(true);
    const ok = await onAcceptAll(files).catch(err => { console.error(err); return false; });
    setProcessing(false);
    // Kısmi başarı `false` sayılıyor. Ama başarısızlıkta dosyalar TEK TEK
    // "yazılamadı" diye işaretlenmiyor: bu bileşen hangisinin yazıldığını
    // bilmiyor ve yazılmış bir dosyaya "yazılamadı" demek, kapattığımız yalanın
    // ayna görüntüsü olurdu. Bilinen tek şey "hepsi başarılı değil" — kart da
    // yalnız onu söyler.
    if (ok) setDone(new Set(files.map((_, i) => i)));
    else setBulkFailed(true);
    setAllDone(true);
    setDiffFile(null);
  };

  if (allDone) {
    const createdFiles = files.filter((_, i) => done.has(i));
    const failedFiles = files.filter((_, i) => failed.has(i));
    // Tek bir başarısızlık bile "İşlem Tamamlandı" başlığını hak etmiyor:
    // kullanıcının o başlıktan çıkardığı sonuç "dosyalar diskte" oluyor.
    const hasFailure = bulkFailed || failedFiles.length > 0;
    return (
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className={`rounded-xl border bg-[#0a0a0a] px-4 py-3 mt-3 ${hasFailure ? 'border-rose-500/30' : 'border-emerald-500/30'}`}
      >
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            {hasFailure
              ? <XCircle size={16} className="text-rose-400" />
              : <CheckCircle2 size={16} className="text-emerald-400" />}
            <span className="text-[12px] font-bold text-white">
              {hasFailure ? t('approval.failed') : t('approval.done')}
            </span>
          </div>
          <button onClick={onDone} className="text-[11px] text-slate-500 hover:text-white transition-colors">{t('approval.close')}</button>
        </div>
        <div className="space-y-1">
          {createdFiles.map((file) => (
            <div key={file.suggestedPath} className="flex items-center gap-2 text-[11px] text-slate-400">
              <FileCode size={12} className="text-blue-500" />
              <span className="truncate">{file.name}</span>
            </div>
          ))}
          {failedFiles.map((file) => (
            <div key={`failed-${file.suggestedPath}`} className="flex items-center gap-2 text-[11px] text-rose-300">
              <XCircle size={12} className="text-rose-500" />
              <span className="truncate">{file.name}</span>
            </div>
          ))}
          {bulkFailed && (
            <p className="text-[11px] text-rose-300">{t('approval.verifyTree')}</p>
          )}
        </div>
      </motion.div>
    );
  }

  return (
    <div className="rounded-xl border border-slate-700/50 bg-[#0d0d0d] mt-4 flex flex-col shadow-xl overflow-hidden">
      {/* HEADER */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-slate-800/60 bg-black/40">
        <div className="flex items-center gap-2">
          <Zap size={14} className="text-yellow-400 animate-pulse" />
          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">{t('approval.title')}</span>
        </div>
        <span className="text-[10px] text-slate-500 font-mono">{remaining} {t('approval.pending')}</span>
      </div>

      {/* COMPACT LIST */}
      <div className="p-2 space-y-1 max-h-[250px] overflow-y-auto custom-scrollbar">
        {files.map((file, i) => {
          const isDone = done.has(i);
          const isSkipped = skipped.has(i);
          const isFailed = failed.has(i);
          const isActive = i === currentIdx;
          // Yazılamayan dosya "bekliyor" sayılmaz: sayaçla (remaining) ve
          // ilerleme mantığıyla (advance) aynı tanımı kullanmazsa liste
          // "0 bekliyor" derken hâlâ Uygula butonu gösterirdi.
          const isPending = !isDone && !isSkipped && !isFailed;

          return (
            <div 
              key={i} 
              onClick={() => isPending && setCurrentIdx(i)}
              className={`group flex items-center gap-2 p-2 rounded-lg border transition-all cursor-pointer ${
                isActive ? 'bg-blue-600/20 border-blue-500/40' : 
                isPending ? 'bg-slate-900/20 border-slate-800/60 hover:bg-slate-900/40' : 
                'bg-black/20 border-transparent opacity-50'
              }`}
            >
              <div className="shrink-0">
                {isDone ? <CheckCircle2 size={13} className="text-emerald-500" /> :
                 isFailed ? <XCircle size={13} className="text-rose-500" /> :
                 isSkipped ? <SkipForward size={13} className="text-slate-600" /> :
                 <FileCode size={13} className={isActive ? 'text-blue-400' : 'text-slate-500'} />}
              </div>
              
              <div className="flex-1 min-w-0">
                <p className={`text-[11px] truncate ${isActive ? 'text-blue-200 font-bold' : 'text-slate-300'}`}>
                  {file.name}
                </p>
              </div>

              {isPending && isActive && (
                <div className="flex items-center gap-1 shrink-0">
                  {/* Yalnız ikon taşıyan bir butonun erişilebilir adı yoktu:
                      ekran okuyucuda adsız, testte de seçilemez durumdaydı —
                      bu yüzden "atla" yolu hiç ölçülememişti (2026-07-29). */}
                  <button
                    onClick={(e) => { e.stopPropagation(); handleSkip(i); }}
                    aria-label={t('approval.skip')}
                    title={t('approval.skip')}
                    className="p-1 hover:bg-rose-500/20 text-rose-400 rounded transition-all"
                  >
                    <SkipForward size={12} />
                  </button>
                  <button 
                    onClick={(e) => { e.stopPropagation(); handleAccept(i); }} 
                    className="px-2 py-0.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded text-[10px] font-bold"
                  >
                    {t('approval.apply')}
                  </button>
                </div>
              )}
              
              {isPending && !isActive && (
                <Eye size={12} className="text-slate-600 opacity-0 group-hover:opacity-100 transition-opacity" />
              )}
            </div>
          );
        })}
      </div>

      {/* FOOTER */}
      <div className="flex items-center justify-between px-3 py-2 border-t border-slate-800/60 bg-black/20">
        {/* "İptal" bir KARARDIR — `onDone` ("Kapat") ile aynı şey değil. */}
        <button onClick={onCancel ?? onDone} className="text-[10px] font-bold text-rose-500 hover:text-rose-400 flex items-center gap-1">
          <XCircle size={12} /> {t('approval.cancel')}
        </button>
        <button 
          onClick={handleAcceptAll} 
          disabled={processing}
          className="flex items-center gap-1 px-3 py-1 bg-blue-600/20 border border-blue-500/40 text-blue-400 hover:bg-blue-600/30 rounded-lg text-[10px] font-bold transition-all disabled:opacity-50"
        >
          <CheckCircle2 size={12} /> {t('approval.approveAll')}
        </button>
      </div>
    </div>
  );
};
