/**
 * useVoiceInput — microphone → 16 kHz mono WAV → POST /transcribe → text.
 *
 * DICTATION, not an assistant: the recognised text is handed back through
 * `onText` and the caller drops it at the caret. Nothing is sent on the user's
 * behalf; they press Enter themselves.
 *
 * Why the renderer encodes the WAV instead of shipping the browser's own
 * MediaRecorder output: the backend validates with the stdlib `wave` module and
 * accepts only PCM 16-bit mono 16000 Hz. MediaRecorder produces WebM/Opus on
 * Chromium with no way to ask for RIFF, so the backend would have to carry a
 * decoder. An AudioWorklet tap plus `renderer/lib/wav.ts` keeps the format
 * contract on one side of the wire.
 *
 * ⚠️ TEARDOWN HAPPENS BEFORE THE REQUEST, not after. The OS microphone
 * indicator is driven by the live MediaStreamTrack; leaving the track open
 * across a network round trip would keep the "recording" light on for as long
 * as transcription takes, which reads to the user as "it is still listening".
 * The tests assert this ordering explicitly.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { apiHataMesaji } from '../../lib/apiError';
import { cevir } from '../../lib/i18n';
import {
  MAX_RECORD_MS,
  WAV_MAX_BYTES,
  WAV_SAMPLE_RATE,
  bytesToBase64,
  downsampleTo16k,
  encodeWav16kMono,
  floatTo16BitPcm,
  wavByteLength,
} from '../../lib/wav';

export type VoiceState = 'idle' | 'recording' | 'transcribing';

export type VoiceErrorKind = 'permission' | 'noDevice' | 'model' | 'empty' | 'server';

export interface VoiceError {
  kind: VoiceErrorKind;
  /** Raw backend detail / exception text — shown in a `title`, never as the label. */
  detail?: string;
}

interface VoiceInputParams {
  /** Backend base URL. Empty until IPC resolves it; the caller disables the button. */
  api: string;
  lang: 'tr' | 'en';
  onText: (text: string) => void;
}

/**
 * Stop every track of a stream we hold no ref to yet.
 *
 * Separate from `teardown()` because the leaks the audit found all happen
 * BEFORE the refs are installed: at that point `teardown()` has nothing to
 * release, so the only handle on the microphone is the local variable.
 */
const releaseStream = (stream: MediaStream | null | undefined) => {
  try { stream?.getTracks?.().forEach(t => t.stop()); } catch { /* no tracks */ }
};

/**
 * Close a context without letting the failure escape.
 *
 * `void ctx.close()` catches only a SYNCHRONOUS throw. `AudioContext.close()`
 * returns a promise, and a browser-level refusal became an unhandled rejection
 * surfacing outside the hook's error handling, after the context ref had
 * already been nulled (audit: `unhandled-cleanup-rejection`). Wrapping the call
 * in `Promise.resolve().then(...)` also covers a stub that throws synchronously
 * or returns a non-promise.
 */
const releaseContext = (ctx: AudioContext | null | undefined) => {
  if (!ctx) return;
  // Handled is not the same as explained: an empty catch left a context that
  // refused to close with no trace at all, and `teardown()` has already dropped
  // the ref, so there is nothing left to retry with either. Warn, never throw.
  Promise.resolve().then(() => ctx.close()).catch((reason) => {
    console.warn('[voice] AudioContext.close rejected:', reason);
  });
};

const WORKLET_URL = '/audio/pcm-capture-worklet.js';
const PROCESSOR_NAME = 'pcm-capture';
/** Elapsed-time refresh. 200 ms is under one mm:ss tick, so the timer never skips a second. */
const TICK_MS = 200;

export const useVoiceInput = ({ api, lang, onText }: VoiceInputParams) => {
  const [state, setState] = useState<VoiceState>('idle');
  const [elapsedMs, setElapsedMs] = useState(0);
  const [error, setError] = useState<VoiceError | null>(null);

  const streamRef = useRef<MediaStream | null>(null);
  const ctxRef = useRef<AudioContext | null>(null);
  const nodeRef = useRef<AudioWorkletNode | null>(null);
  const sourceRef = useRef<AudioNode | null>(null);
  const chunksRef = useRef<Float32Array[]>([]);
  const rawSampleCountRef = useRef(0);
  const inputRateRef = useRef(WAV_SAMPLE_RATE);
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const autoStopRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const startedAtRef = useRef(0);

  /**
   * Per-recording cancellation flag, an object rather than a boolean so the
   * in-flight request closes over THIS recording's flag. A shared boolean would
   * be reset by the next `start()` and a late response from the abandoned
   * recording would then be treated as live.
   */
  const runRef = useRef<{ cancelled: boolean }>({ cancelled: true });

  /**
   * SYNCHRONOUS duplicate-start guard.
   *
   * The old guard read React state, which stays `idle` for the whole async
   * acquisition — so two clicks in the same render both passed it, both called
   * `getUserMedia`, and the single set of refs kept only the second. The first
   * microphone track was then unreachable and could never be stopped (audit:
   * `duplicate-start-race`). A ref is written before the first await, so the
   * second call sees it in the same tick.
   */
  const startingRef = useRef(false);

  /**
   * The stream and context DURING acquisition, before the graph is committed.
   *
   * Between `getUserMedia` resolving and `addModule` settling these existed only
   * as `start()` locals, so a `cancel()`/`stop()`/unmount arriving in that window
   * had nothing to release: a worklet fetch that never returns left the
   * microphone on with no way for the user to turn it off (audit round 2,
   * `partial-teardown-on-async-cancel`). `teardown()` drains this too, which
   * makes release possible at any instant rather than only at the await
   * boundaries. The post-await abort checks stay as the second line of defence.
   */
  const pendingRef = useRef<{ stream: MediaStream | null; ctx: AudioContext | null } | null>(null);

  /**
   * "The thing we are acquiring for is gone." Set by unmount and by `cancel()`,
   * and re-checked after EVERY await inside `start()`: a `getUserMedia` or
   * `addModule` promise that settles after cleanup would otherwise install a
   * live capture graph that no effect will ever tear down again (audit:
   * `async-start-after-unmount`).
   */
  const abortAcquisitionRef = useRef(false);

  // `onText` and `lang` read through refs: `start`/`stop` are handed to a
  // button and to timers, and rebuilding them on every parent render would
  // restart the auto-stop timeout mid-recording.
  const onTextRef = useRef(onText);
  onTextRef.current = onText;
  const langRef = useRef(lang);
  langRef.current = lang;
  const apiRef = useRef(api);
  apiRef.current = api;

  /** Release every OS-visible resource. Safe to call twice. */
  const teardown = useCallback(() => {
    if (tickRef.current) { clearInterval(tickRef.current); tickRef.current = null; }
    if (autoStopRef.current) { clearTimeout(autoStopRef.current); autoStopRef.current = null; }
    try { nodeRef.current?.port?.close?.(); } catch { /* already closed */ }
    try { nodeRef.current?.disconnect(); } catch { /* not connected */ }
    nodeRef.current = null;
    try { sourceRef.current?.disconnect(); } catch { /* not connected */ }
    sourceRef.current = null;
    // Tracks first among the things the OS can see — this is what turns the
    // microphone indicator off.
    releaseStream(streamRef.current);
    streamRef.current = null;
    releaseContext(ctxRef.current);
    ctxRef.current = null;
    // Anything an in-flight `start()` has acquired but not yet committed.
    releaseStream(pendingRef.current?.stream);
    releaseContext(pendingRef.current?.ctx);
    pendingRef.current = null;
  }, []);

  const clearError = useCallback(() => setError(null), []);

  const start = useCallback(async () => {
    // Ref first, state second: only the ref is reliable inside the same tick.
    if (startingRef.current || streamRef.current) return;
    if (state !== 'idle') return;
    startingRef.current = true;
    abortAcquisitionRef.current = false;

    // Held locally until the graph is fully built. Every early return below
    // releases these directly, because until the refs are assigned `teardown()`
    // cannot see them.
    let stream: MediaStream | null = null;
    let ctx: AudioContext | null = null;

    try {
      setError(null);

      const media = (globalThis as any).navigator?.mediaDevices;
      if (!media?.getUserMedia) {
        setError({ kind: 'noDevice' });
        return;
      }

      try {
        stream = await media.getUserMedia({
          audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
        });
      } catch (err: any) {
        const name = err?.name;
        // NotAllowedError/SecurityError are a REFUSAL (user or policy);
        // NotFound/Overconstrained mean there is no device that fits. Different
        // sentences, because the fix is different: grant permission vs plug
        // something in.
        if (name === 'NotAllowedError' || name === 'SecurityError') {
          setError({ kind: 'permission', detail: err?.message });
        } else {
          setError({ kind: 'noDevice', detail: err?.message ?? String(err) });
        }
        return;
      }

      // Publish immediately: from here on the microphone is live, so anyone
      // calling cancel/stop/unmount must be able to reach it.
      pendingRef.current = { stream, ctx: null };

      // The permission dialog can outlive the component. Bail without touching
      // state — a `setError` here would be a write into an unmounted tree, and
      // the point is to release the microphone, not to report anything.
      if (abortAcquisitionRef.current) { releaseStream(stream); pendingRef.current = null; return; }

      try {
        // Asking for 16000 directly avoids resampling entirely where the browser
        // honours it. Where it refuses (Firefox historically throws), we take the
        // default rate and decimate — hence reading `ctx.sampleRate` below rather
        // than assuming the requested value was applied.
        ctx = new (globalThis as any).AudioContext({ sampleRate: WAV_SAMPLE_RATE });
      } catch {
        try {
          ctx = new (globalThis as any).AudioContext();
        } catch (err: any) {
          releaseStream(stream);
          pendingRef.current = null;
          setError({ kind: 'noDevice', detail: err?.message ?? String(err) });
          return;
        }
      }
      pendingRef.current = { stream, ctx };

      // ONE protected block for every remaining graph step. Each of these could
      // throw after the microphone was already live — the audit reproduced a
      // leak from the `AudioWorkletNode` constructor, from
      // `createMediaStreamSource()` and from `connect()`, all of which used to
      // run outside any cleanup (`partial-teardown-on-exception`).
      let node: AudioWorkletNode;
      let source: AudioNode;
      try {
        await ctx!.audioWorklet.addModule(WORKLET_URL);
        if (abortAcquisitionRef.current) {
          releaseStream(stream); releaseContext(ctx); pendingRef.current = null; return;
        }

        node = new (globalThis as any).AudioWorkletNode(ctx, PROCESSOR_NAME);
        source = ctx!.createMediaStreamSource(stream!);
        source.connect(node);
      } catch (err: any) {
        releaseStream(stream);
        releaseContext(ctx);
        pendingRef.current = null;
        setError({ kind: 'noDevice', detail: err?.message ?? String(err) });
        return;
      }

      // Past this line nothing can throw, so installing the refs here means the
      // refs and the live resources are always in the same state.
      const run = { cancelled: false };
      runRef.current = run;
      chunksRef.current = [];
      rawSampleCountRef.current = 0;
      inputRateRef.current = ctx!.sampleRate || WAV_SAMPLE_RATE;
      streamRef.current = stream;
      ctxRef.current = ctx;
      nodeRef.current = node;
      sourceRef.current = source;
      // The refs own these now.
      pendingRef.current = null;


      startedAtRef.current = Date.now();
      setElapsedMs(0);
      setState('recording');
      tickRef.current = setInterval(() => {
        setElapsedMs(Date.now() - startedAtRef.current);
      }, TICK_MS);
      // Hard ceiling. Without it a forgotten recording runs until the byte budget
      // trips, and the byte budget depends on the sample rate — i.e. the user
      // would get a different maximum length on different machines.
      autoStopRef.current = setTimeout(() => { stopRef.current(); }, MAX_RECORD_MS);

      // Handler installed LAST, after the recording state and the timers are
      // committed. A real MessagePort delivers asynchronously so a message
      // cannot interleave here, but the budget callback calls `stop()`, and with
      // the handler installed first that stop could be immediately overwritten
      // by this function's own `setState('recording')` - leaving the indicator
      // lit over a graph already torn down. The ordering costs nothing and
      // removes the possibility (audit round 2, `premature-stop-state-race`).
      node.port.onmessage = (event: MessageEvent) => {
        const block = event.data as Float32Array;
        if (!block || !block.length) return;
        chunksRef.current.push(block);
        rawSampleCountRef.current += block.length;
        // Budget check in the 16 kHz domain, because that is what actually goes
        // on the wire. Stopping early is better than posting a body the backend
        // answers with 413 — a rejection the user cannot act on.
        const ratio = inputRateRef.current / WAV_SAMPLE_RATE;
        const projected = wavByteLength(Math.floor(rawSampleCountRef.current / ratio));
        if (projected >= WAV_MAX_BYTES) stopRef.current();
      };
    } finally {
      startingRef.current = false;
    }
  }, [state]);

  const stop = useCallback(async () => {
    // A stop asked for while `start()` is still awaiting used to fall through
    // this guard (state idle, refs empty) and the acquisition then committed
    // `recording` anyway - the user's stop was silently ignored and the
    // microphone stayed live (audit round 2, `stop-during-async-acquisition`).
    // `!streamRef.current` narrows this to the ACQUIRING window specifically:
    // `startingRef` is still true at the moment the message handler is
    // installed, by which point the graph is committed and a stop there is a
    // real stop that must transcribe, not an abort.
    if (startingRef.current && !streamRef.current) {
      abortAcquisitionRef.current = true;
      teardown();  // drains `pendingRef`, i.e. whatever has been acquired so far
      setState('idle');
      setElapsedMs(0);
      return;
    }
    if (state !== 'recording' && !streamRef.current) return;
    const run = runRef.current;
    const chunks = chunksRef.current;
    const inputRate = inputRateRef.current;

    // Order matters — see the header note. Everything the OS can see is gone
    // before a single byte is sent.
    teardown();
    chunksRef.current = [];
    if (run.cancelled) { setState('idle'); return; }

    setState('transcribing');

    let total = 0;
    for (const c of chunks) total += c.length;
    const merged = new Float32Array(total);
    let offset = 0;
    for (const c of chunks) { merged.set(c, offset); offset += c.length; }

    const at16k = downsampleTo16k(merged, inputRate);
    const wav = encodeWav16kMono(floatTo16BitPcm(at16k));
    const wavBase64 = bytesToBase64(wav);

    // Belt and braces on the token: `useAuth` puts it on
    // `axios.defaults.headers.common`, but a per-call `headers` object REPLACES
    // the default for that header, so anything that later adds headers here
    // would silently drop auth. Reading the default back and passing it
    // explicitly makes the two impossible to diverge.
    const token = (axios as any).defaults?.headers?.common?.['X-Session-Token'];
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (token) headers['X-Session-Token'] = String(token);

    try {
      const res = await axios.post(
        `${apiRef.current}/transcribe`,
        { lang: langRef.current, wav_base64: wavBase64 },
        { headers, timeout: 30000 },
      );
      if (run.cancelled) return;
      const text = typeof res?.data?.text === 'string' ? res.data.text : '';
      if (text.trim() === '') {
        setError({ kind: 'empty' });
      } else {
        onTextRef.current(text.trim());
      }
    } catch (err: any) {
      if (run.cancelled) return;
      const status = err?.response?.status;
      if (status === 503) {
        setError({ kind: 'model', detail: apiHataMesaji(err, '') || undefined });
      } else if (!err?.response) {
        // No response at all: the backend is down, or the request never left.
        setError({ kind: 'server', detail: err?.message ?? String(err) });
      } else {
        // 400 / 413 / 401 / other 5xx all land here. The user-facing sentence
        // is the same "could not reach the backend" one by contract; the raw
        // detail goes into the title so a report can name it.
        setError({ kind: 'server', detail: apiHataMesaji(err, `HTTP ${status}`) });
      }
    } finally {
      if (!run.cancelled) {
        setState('idle');
        setElapsedMs(0);
      }
    }
  }, [state, teardown]);

  // Timers hold the CURRENT `stop`, not the one that existed when the timer was
  // armed: `stop` closes over `state` and would otherwise fire a stale copy
  // that sees `state === 'idle'` and returns without encoding anything.
  const stopRef = useRef(stop);
  stopRef.current = stop;

  const cancel = useCallback(() => {
    runRef.current.cancelled = true;
    abortAcquisitionRef.current = true;
    teardown();
    chunksRef.current = [];
    setState('idle');
    setElapsedMs(0);
  }, [teardown]);

  useEffect(() => () => {
    // Unmount: the flags first, so neither a request already in flight nor an
    // acquisition still resolving can write into a composer that is gone.
    runRef.current.cancelled = true;
    abortAcquisitionRef.current = true;
    teardown();
  }, [teardown]);

  return { state, elapsedMs, error, start, stop, cancel, clearError };
};

/** `mm:ss` for the recording badge. Kept here so the button and its tests agree. */
export const formatElapsed = (ms: number): string => {
  const total = Math.max(0, Math.floor(ms / 1000));
  const mm = String(Math.floor(total / 60)).padStart(2, '0');
  const ss = String(total % 60).padStart(2, '0');
  return `${mm}:${ss}`;
};

/** i18n key for an error kind — one mapping, read by the composer. */
export const voiceErrorText = (err: VoiceError): string => cevir(`mic.err.${err.kind}` as any);
