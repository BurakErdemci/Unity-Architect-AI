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
    try { streamRef.current?.getTracks().forEach(t => t.stop()); } catch { /* no tracks */ }
    streamRef.current = null;
    try { void ctxRef.current?.close(); } catch { /* already closed */ }
    ctxRef.current = null;
  }, []);

  const clearError = useCallback(() => setError(null), []);

  const start = useCallback(async () => {
    if (state !== 'idle') return;
    setError(null);

    const media = (globalThis as any).navigator?.mediaDevices;
    if (!media?.getUserMedia) {
      setError({ kind: 'noDevice' });
      return;
    }

    let stream: MediaStream;
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
      } else if (name === 'NotFoundError' || name === 'OverconstrainedError') {
        setError({ kind: 'noDevice', detail: err?.message });
      } else {
        setError({ kind: 'noDevice', detail: err?.message ?? String(err) });
      }
      return;
    }

    let ctx: AudioContext;
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
        stream.getTracks().forEach(t => t.stop());
        setError({ kind: 'noDevice', detail: err?.message ?? String(err) });
        return;
      }
    }

    try {
      await ctx.audioWorklet.addModule(WORKLET_URL);
    } catch (err: any) {
      stream.getTracks().forEach(t => t.stop());
      try { void ctx.close(); } catch { /* ignore */ }
      setError({ kind: 'noDevice', detail: err?.message ?? String(err) });
      return;
    }

    const run = { cancelled: false };
    runRef.current = run;
    chunksRef.current = [];
    rawSampleCountRef.current = 0;
    inputRateRef.current = ctx.sampleRate || WAV_SAMPLE_RATE;
    streamRef.current = stream;
    ctxRef.current = ctx;

    const node = new (globalThis as any).AudioWorkletNode(ctx, PROCESSOR_NAME);
    nodeRef.current = node;
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
    const source = ctx.createMediaStreamSource(stream);
    sourceRef.current = source;
    source.connect(node);

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
  }, [state]);

  const stop = useCallback(async () => {
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
    teardown();
    chunksRef.current = [];
    setState('idle');
    setElapsedMs(0);
  }, [teardown]);

  useEffect(() => () => {
    // Unmount: the flag first, so a request already in flight cannot call
    // `onText` into a composer that no longer exists.
    runRef.current.cancelled = true;
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
