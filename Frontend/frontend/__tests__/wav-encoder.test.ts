/**
 * The WAV byte layout is the half of the dictation contract the backend
 * refuses silently-ish: a wrong rate or channel count comes back as
 * `stt_wrong_format`, which tells the user nothing about which field was
 * wrong. Asserting the header byte by byte means the format is checked here,
 * where the failure names the field, rather than across the wire.
 */
import { describe, it, expect } from 'vitest'
import {
  MAX_RECORD_MS,
  WAV_MAX_BYTES,
  bytesToBase64,
  downsampleTo16k,
  encodeWav16kMono,
  floatTo16BitPcm,
} from '../renderer/lib/wav'

const ascii = (bytes: Uint8Array, at: number, len: number) =>
  String.fromCharCode(...bytes.subarray(at, at + len))

const u32 = (bytes: Uint8Array, at: number) =>
  new DataView(bytes.buffer, bytes.byteOffset).getUint32(at, true)

const u16 = (bytes: Uint8Array, at: number) =>
  new DataView(bytes.buffer, bytes.byteOffset).getUint16(at, true)

describe('WAV header', () => {
  it('an empty recording still produces a valid 44-byte RIFF file', () => {
    const wav = encodeWav16kMono(new Int16Array(0))
    expect(wav.length).toBe(44)
    expect(ascii(wav, 0, 4)).toBe('RIFF')
    expect(u32(wav, 4)).toBe(36)          // file size - 8
    expect(ascii(wav, 8, 4)).toBe('WAVE')
    expect(ascii(wav, 12, 4)).toBe('fmt ')  // the trailing space is part of the id
    expect(u32(wav, 40)).toBe(0)          // data chunk size
  })

  it('N samples give the sizes, rate, channel count and bit depth the backend demands', () => {
    const N = 800
    const wav = encodeWav16kMono(new Int16Array(N))
    expect(wav.length).toBe(44 + N * 2)
    expect(u32(wav, 4)).toBe(36 + N * 2)
    expect(u32(wav, 16)).toBe(16)         // PCM fmt body
    expect(u16(wav, 20)).toBe(1)          // format 1 = PCM
    expect(u16(wav, 22)).toBe(1)          // mono
    expect(u32(wav, 24)).toBe(16000)      // sample rate
    expect(u32(wav, 28)).toBe(32000)      // byte rate = 16000 * 2
    expect(u16(wav, 32)).toBe(2)          // block align
    expect(u16(wav, 34)).toBe(16)         // bits per sample
    expect(ascii(wav, 36, 4)).toBe('data')
    expect(u32(wav, 40)).toBe(N * 2)
  })

  it('samples are written little-endian', () => {
    const wav = encodeWav16kMono(Int16Array.from([0x0102]))
    expect(wav[44]).toBe(0x02)
    expect(wav[45]).toBe(0x01)
  })
})

describe('float → int16', () => {
  it('clamps out-of-range floats instead of wrapping around', () => {
    // Unclamped, 2.0 * 32767 overflows the Int16Array store and comes back
    // NEGATIVE — a loud syllable would invert rather than saturate.
    const out = floatTo16BitPcm(Float32Array.from([2, -2, 0]))
    expect(out[0]).toBe(32767)
    expect(out[1]).toBe(-32768)
    expect(out[2]).toBe(0)
  })

  it('maps the endpoints of the legal range to the endpoints of int16', () => {
    const out = floatTo16BitPcm(Float32Array.from([1, -1, 0.5]))
    expect(out[0]).toBe(32767)
    expect(out[1]).toBe(-32768)
    expect(out[2]).toBe(Math.trunc(0.5 * 32767))
  })
})

describe('downsampling', () => {
  it('48000 → 16000 keeps one sample in three', () => {
    const input = new Float32Array(4800)
    const out = downsampleTo16k(input, 48000)
    expect(out.length).toBe(1600)
  })

  it('averages rather than dropping samples', () => {
    // Three source samples 0, 1, 2 collapse to their mean, not to the first.
    const out = downsampleTo16k(Float32Array.from([0, 1, 2]), 48000)
    expect(out.length).toBe(1)
    expect(out[0]).toBeCloseTo(1, 5)
  })

  it('16000 in is returned untouched — identity, not a copy of a resample', () => {
    const input = Float32Array.from([0.1, -0.2, 0.3])
    expect(downsampleTo16k(input, 16000)).toBe(input)
  })
})

describe('base64', () => {
  it('encodes 2 MiB without throwing', () => {
    // The apply/spread argument limit is the failure this guards: it would fire
    // only on the longest recordings, i.e. exactly at the size the backend
    // still accepts.
    const big = new Uint8Array(WAV_MAX_BYTES)
    for (let i = 0; i < big.length; i += 997) big[i] = i & 0xff
    let text = ''
    expect(() => { text = bytesToBase64(big) }).not.toThrow()
    expect(text.length).toBe(Math.ceil(WAV_MAX_BYTES / 3) * 4)
  })

  it('round-trips through atob', () => {
    const sample = Uint8Array.from([0, 1, 2, 253, 254, 255, 42])
    const decoded = atob(bytesToBase64(sample))
    expect(Array.from(decoded, c => c.charCodeAt(0))).toEqual(Array.from(sample))
  })

  it('a chunk boundary does not inject padding into the middle', () => {
    // Chunking with a size not divisible by 3 would emit '=' mid-string and
    // atob would then decode a different byte run than went in.
    const sample = new Uint8Array(100_000)
    for (let i = 0; i < sample.length; i++) sample[i] = i & 0xff
    const text = bytesToBase64(sample)
    expect(text.slice(0, -4)).not.toContain('=')
    expect(atob(text).length).toBe(sample.length)
  })
})

describe('limits', () => {
  it('a full-length recording fits inside the byte budget', () => {
    // 60 s of 16 kHz mono 16-bit. If this ever exceeded the budget the clock
    // limit would be unreachable and every long recording would end on the
    // byte check instead, at a length that varies with the device sample rate.
    const bytes = 44 + (MAX_RECORD_MS / 1000) * 16000 * 2
    expect(bytes).toBeLessThan(WAV_MAX_BYTES)
  })
})
