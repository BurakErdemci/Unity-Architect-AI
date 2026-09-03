/**
 * Raw PCM tap for voice dictation.
 *
 * Served from `renderer/public/`, so the runtime path is `/audio/pcm-capture-worklet.js`
 * in both modes — the same root-relative shape and the same reason as
 * `MONACO_VS_PATH` in `renderer/components/home/monaco-loader.ts`: under the
 * `app://` scheme a leading `/` keeps the host ('.'), while a relative path
 * would resolve differently in dev (`/home/…`) than in production.
 *
 * Plain JS with no imports: AudioWorklet code runs in a separate global scope
 * loaded by URL, not by the bundler, so nothing here can be imported or
 * transpiled.
 *
 * It only copies and forwards. Encoding, downsampling and the size budget all
 * live on the main thread (`renderer/lib/wav.ts`), because this callback runs
 * on the real-time audio thread where a stall is an audible dropout.
 */
class PcmCaptureProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const input = inputs[0];
    // No input yet (the graph is still connecting) or a silent disconnected
    // source: emit nothing rather than a run of zeros, so the recording does
    // not accumulate padding.
    if (!input || input.length === 0) return true;
    const channel = input[0];
    if (!channel || channel.length === 0) return true;

    // A COPY, not the buffer itself: the render quantum buffer is reused by
    // the audio thread on the next call, so posting it without copying would
    // hand the main thread memory that is overwritten before it is read.
    this.port.postMessage(new Float32Array(channel));
    return true;
  }
}

registerProcessor('pcm-capture', PcmCaptureProcessor);
