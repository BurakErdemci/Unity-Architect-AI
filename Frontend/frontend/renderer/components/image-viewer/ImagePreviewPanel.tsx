import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Loader2, Maximize2, Minimize2 } from 'lucide-react';
import { useLang, type TKey } from '../../lib/i18n';
import { extensionOf, routeForFile } from '../model-viewer/extensions';

/**
 * Same contract as ModelPreviewPanel: no `onClose`. Closing a preview is the
 * content tab's job (`home.tsx`, the X beside the file name).
 */
export interface ImagePreviewPanelProps {
  file: { path: string; name: string };
  workspacePath: string | null;
}

/**
 * Channel refusals the user can act on. `denied` is deliberately absent, for
 * the reason written at ModelPreviewPanel's copy: naming the boundary a probe
 * just hit tells the probe where the boundary is.
 */
const CHANNEL_ERROR_KEYS: Record<string, TKey> = {
  // Its own key, not `preview.tooLarge`: that sentence names 64 MiB and this
  // channel's cap is 32.
  'too-large': 'preview.imageTooLarge',
  unsupported: 'preview.unsupportedFormat',
  busy: 'preview.busy',
};

const MIME_BY_EXTENSION: Record<string, string> = {
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.webp': 'image/webp',
  '.bmp': 'image/bmp',
  '.svg': 'image/svg+xml',
};

/** Bytes as the strip shows them; a texture is talked about in KiB and MiB. */
const humanSize = (bytes: number): string =>
  bytes >= 1024 * 1024
    ? `${(bytes / (1024 * 1024)).toFixed(1)} MiB`
    : `${Math.max(1, Math.round(bytes / 1024))} KiB`;

// Transparency has to be visible: a sprite with an alpha channel is
// indistinguishable from an opaque one against a flat dark panel, and "is this
// cut out properly" is the question the preview exists to answer. A gradient,
// so no asset ships with it.
const CHECKER = {
  backgroundColor: '#141821',
  backgroundImage:
    'linear-gradient(45deg, #1e2430 25%, transparent 25%), '
    + 'linear-gradient(-45deg, #1e2430 25%, transparent 25%), '
    + 'linear-gradient(45deg, transparent 75%, #1e2430 75%), '
    + 'linear-gradient(-45deg, transparent 75%, #1e2430 75%)',
  backgroundSize: '16px 16px',
  backgroundPosition: '0 0, 0 8px, 8px -8px, -8px 0',
} as const;

export const ImagePreviewPanel: React.FC<ImagePreviewPanelProps> = ({ file, workspacePath }) => {
  const { t } = useLang();
  const [loading, setLoading] = useState(true);
  const [errorKey, setErrorKey] = useState<TKey | null>(null);
  const [url, setUrl] = useState<string | null>(null);
  const [byteLength, setByteLength] = useState(0);
  const [natural, setNatural] = useState<{ w: number; h: number } | null>(null);
  const [actualSize, setActualSize] = useState(false);

  // The object URL the panel currently owns, held outside React state so the
  // effect cleanup can revoke it without depending on a re-render having run.
  // A leaked URL pins the whole decoded image in memory for the life of the
  // window, and clicking through a texture folder leaks one per click.
  const urlRef = useRef<string | null>(null);
  const release = useCallback(() => {
    if (urlRef.current) {
      URL.revokeObjectURL(urlRef.current);
      urlRef.current = null;
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    release();
    setUrl(null);
    setNatural(null);
    setByteLength(0);
    setActualSize(false);
    setErrorKey(null);
    setLoading(true);

    const fail = (key: TKey) => {
      if (cancelled) return;
      setErrorKey(key);
      setLoading(false);
    };

    // .tga/.psd/.exr/.tiff reach this panel so the click has an answer, but no
    // browser can decode them. Saying so here keeps the main process from
    // reading a file whose bytes nothing can use.
    if (routeForFile(file.name) === 'blocked-image') {
      fail('preview.imageBlockedFormat');
      return () => { cancelled = true; };
    }

    void (async () => {
      const ipc = (window as any).ipc;
      const result = ipc ? await ipc.invoke('read-image-file', file.path, workspacePath) : null;
      if (cancelled) return;
      if (!result || result.error || !result.data) {
        // A null result is the handler having thrown, which says nothing the
        // user can act on: generic, same as a containment refusal.
        fail((result?.error && CHANNEL_ERROR_KEYS[result.error]) || 'preview.loadError');
        return;
      }

      const type = MIME_BY_EXTENSION[extensionOf(file.name)] ?? 'application/octet-stream';
      const objectUrl = URL.createObjectURL(new Blob([result.data], { type }));
      if (cancelled) { URL.revokeObjectURL(objectUrl); return; }
      urlRef.current = objectUrl;
      setByteLength(result.data.byteLength ?? 0);
      setUrl(objectUrl);
      // `loading` stays true until <img> reports back: the bytes being here is
      // not the same as the image being decodable.
    })();

    return () => { cancelled = true; release(); };
  }, [file.path, file.name, workspacePath, release]);

  const onLoad = useCallback((e: React.SyntheticEvent<HTMLImageElement>) => {
    const img = e.currentTarget;
    setNatural({ w: img.naturalWidth, h: img.naturalHeight });
    setLoading(false);
  }, []);

  const onError = useCallback(() => {
    setErrorKey('preview.loadError');
    setLoading(false);
  }, []);

  // Unity sprites are pixel art, and the browser's default smoothing turns a
  // 32x32 icon into a blur the moment it is shown at or above 1:1. Only
  // magnification is at issue — downscaling still wants the smooth filter.
  const magnified = actualSize;

  return (
    <div className="flex-1 min-h-0 w-full relative flex flex-col bg-[#0B0D12]">
      <div
        className={`flex-1 min-h-0 relative flex items-center justify-center ${
          actualSize ? 'overflow-auto custom-scrollbar' : 'overflow-hidden'
        }`}
        style={CHECKER}
      >
        {url && !errorKey && (
          <img
            src={url}
            alt={file.name}
            onLoad={onLoad}
            onError={onError}
            style={
              actualSize
                ? { imageRendering: 'pixelated', flexShrink: 0 }
                : { maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }
            }
          />
        )}
        {loading && !errorKey && (
          <div className="absolute inset-0 flex items-center justify-center gap-2 text-[11px] font-semibold text-slate-400 pointer-events-none">
            <Loader2 size={14} className="animate-spin" />
            {t('preview.imageLoading')}
          </div>
        )}
        {errorKey && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 px-8 text-center bg-[#0B0D12]">
            <span className="text-[12px] font-semibold text-slate-300">{t(errorKey)}</span>
          </div>
        )}
      </div>
      {natural && !errorKey && (
        <div className="shrink-0 flex items-center justify-between gap-3 px-3 py-1.5 border-t border-white/[0.06] bg-[#0B0D12]">
          <span className="text-[10px] font-mono text-slate-500 truncate">
            {t('preview.imageDimensions', { width: natural.w, height: natural.h })}
            {byteLength > 0 && ` · ${humanSize(byteLength)}`}
          </span>
          <button
            onClick={() => setActualSize(v => !v)}
            className="shrink-0 flex items-center gap-1.5 px-2 py-1 rounded text-[10px] font-semibold text-slate-400 hover:text-slate-200 hover:bg-white/[0.06] transition-colors"
          >
            {magnified ? <Minimize2 size={11} /> : <Maximize2 size={11} />}
            {t(magnified ? 'preview.fitToView' : 'preview.actualSize')}
          </button>
        </div>
      )}
    </div>
  );
};

export default ImagePreviewPanel;
