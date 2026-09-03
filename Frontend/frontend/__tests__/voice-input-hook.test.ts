/**
 * Voice dictation recording hook.
 *
 * jsdom has neither `navigator.mediaDevices` nor `AudioContext` (measured: both
 * are `undefined` under vitest's jsdom environment), so the whole capture graph
 * is stubbed here. What is being measured is not Web Audio — it is the four
 * things that can go wrong in a way the user cannot diagnose: which failure
 * gets which named error, that the request carries the session token, that the
 * microphone is released BEFORE the request rather than after, and that a late
 * response cannot write into a composer that is gone.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { act, renderHook } from '@testing-library/react'

vi.mock('axios', () => {
  const post = vi.fn()
  return { __esModule: true, default: { post, defaults: { headers: { common: {} } } }, post }
})

import axios from 'axios'
import { useVoiceInput } from '../renderer/hooks/home/useVoiceInput'

const mockedAxios = axios as unknown as {
  post: ReturnType<typeof vi.fn>
  defaults: { headers: { common: Record<string, string> } }
}

const API = 'http://127.0.0.1:8000'

let track: { stop: ReturnType<typeof vi.fn> }
let lastNode: any
let lastCtx: any
// `any`: these are reassigned per test and called through a spread, which
// `Mock<Procedure | Constructable>` does not model as callable.
let getUserMedia: any
let addModule: any
let contextRate = 16000
// Per-test overrides for the three graph steps that can fail AFTER the
// microphone has already been acquired - the window where a leak is possible.
let closeImpl: () => any
let createSourceImpl: () => any
let onNodeConstruct: (() => void) | null

class FakeAudioContext {
  sampleRate: number
  audioWorklet = { addModule: (...a: any[]) => addModule(...a) }
  close = vi.fn(() => closeImpl())
  createMediaStreamSource = vi.fn(() => createSourceImpl())
  constructor(options?: { sampleRate?: number }) {
    // The browser may refuse the requested rate; the stub honours it so the
    // default path is the no-resample one, and the 48 kHz case is set up per test.
    this.sampleRate = contextRate !== 16000 ? contextRate : (options?.sampleRate ?? contextRate)
    lastCtx = this
  }
}

class FakeAudioWorkletNode {
  port: any = { onmessage: null, close: vi.fn() }
  connect = vi.fn()
  disconnect = vi.fn()
  constructor(_ctx: any, _name: string) { onNodeConstruct?.(); lastNode = this }
}

const failWith = (name: string) => {
  const err: any = new Error(name)
  err.name = name
  return err
}

beforeEach(() => {
  contextRate = 16000
  lastNode = null
  lastCtx = null
  closeImpl = () => Promise.resolve()
  createSourceImpl = () => ({ connect: vi.fn(), disconnect: vi.fn() })
  onNodeConstruct = null
  track = { stop: vi.fn() }
  getUserMedia = vi.fn().mockResolvedValue({ getTracks: () => [track] })
  addModule = vi.fn().mockResolvedValue(undefined)
  mockedAxios.post.mockReset()
  mockedAxios.defaults.headers.common = {}
  Object.defineProperty(globalThis.navigator, 'mediaDevices', {
    value: { getUserMedia: (...a: any[]) => getUserMedia(...a) },
    configurable: true,
  })
  ;(globalThis as any).AudioContext = FakeAudioContext
  ;(globalThis as any).AudioWorkletNode = FakeAudioWorkletNode
})

afterEach(() => {
  vi.useRealTimers()
})

const speak = (samples = 1600) => {
  act(() => { lastNode.port.onmessage({ data: new Float32Array(samples) }) })
}

const setup = (onText = vi.fn(), lang: 'tr' | 'en' = 'tr') =>
  ({ onText, ...renderHook(() => useVoiceInput({ api: API, lang, onText })) })

describe('useVoiceInput failures at the microphone', () => {
  it('a denied permission is reported as `permission`, not as a generic failure', async () => {
    getUserMedia.mockRejectedValue(failWith('NotAllowedError'))
    const { result } = setup()
    await act(async () => { await result.current.start() })
    expect(result.current.error?.kind).toBe('permission')
    expect(result.current.state).toBe('idle')
  })

  it('SecurityError is the same refusal and gets the same name', async () => {
    getUserMedia.mockRejectedValue(failWith('SecurityError'))
    const { result } = setup()
    await act(async () => { await result.current.start() })
    expect(result.current.error?.kind).toBe('permission')
  })

  it('NotFoundError is `noDevice` — a different sentence because the fix is different', async () => {
    getUserMedia.mockRejectedValue(failWith('NotFoundError'))
    const { result } = setup()
    await act(async () => { await result.current.start() })
    expect(result.current.error?.kind).toBe('noDevice')
  })

  it('OverconstrainedError also means no usable device', async () => {
    getUserMedia.mockRejectedValue(failWith('OverconstrainedError'))
    const { result } = setup()
    await act(async () => { await result.current.start() })
    expect(result.current.error?.kind).toBe('noDevice')
  })
})

describe('useVoiceInput happy path', () => {
  it('start → stop posts the WAV to /transcribe with the session token and hands the text back', async () => {
    mockedAxios.defaults.headers.common['X-Session-Token'] = 'tok-123'
    mockedAxios.post.mockResolvedValue({ data: { text: '  merhaba dünya  ' } })
    const { result, onText } = setup()

    await act(async () => { await result.current.start() })
    expect(result.current.state).toBe('recording')
    speak()
    await act(async () => { await result.current.stop() })

    expect(mockedAxios.post).toHaveBeenCalledTimes(1)
    const [url, body, config] = mockedAxios.post.mock.calls[0]
    expect(url).toBe(`${API}/transcribe`)
    expect(body.lang).toBe('tr')
    expect(typeof body.wav_base64).toBe('string')
    expect(body.wav_base64.length).toBeGreaterThan(0)
    // The base64 really is a RIFF file, not just some string: 'RIFF' encodes
    // to 'UklGR' at offset 0.
    expect(body.wav_base64.startsWith('UklGR')).toBe(true)
    expect(config.headers['X-Session-Token']).toBe('tok-123')
    expect(config.timeout).toBe(30000)
    expect(onText).toHaveBeenCalledWith('merhaba dünya')
    expect(result.current.state).toBe('idle')
  })

  it('the chosen speaking language is what goes on the wire, not the app language', async () => {
    mockedAxios.post.mockResolvedValue({ data: { text: 'hello' } })
    const { result } = setup(vi.fn(), 'en')
    await act(async () => { await result.current.start() })
    speak()
    await act(async () => { await result.current.stop() })
    expect(mockedAxios.post.mock.calls[0][1].lang).toBe('en')
  })
})

describe('useVoiceInput answers from the backend', () => {
  const run = async (respond: () => Promise<any>) => {
    mockedAxios.post.mockImplementation(respond)
    const { result, onText } = setup()
    await act(async () => { await result.current.start() })
    speak()
    await act(async () => { await result.current.stop() })
    return { result, onText }
  }

  it('200 with empty text is `empty` — the request worked, the audio did not', async () => {
    const { result, onText } = await run(async () => ({ data: { text: '   ' } }))
    expect(result.current.error?.kind).toBe('empty')
    expect(onText).not.toHaveBeenCalled()
  })

  it('503 is `model` — the recognition files are missing, not the server', async () => {
    const { result } = await run(async () => {
      throw { response: { status: 503, data: { detail: 'stt_model_missing' } } }
    })
    expect(result.current.error?.kind).toBe('model')
  })

  it('no response at all is `server`', async () => {
    const { result } = await run(async () => { throw new Error('Network Error') })
    expect(result.current.error?.kind).toBe('server')
    expect(result.current.error?.detail).toBe('Network Error')
  })

  it('any other status is `server` and keeps the raw detail for the title', async () => {
    const { result } = await run(async () => {
      throw { response: { status: 413, data: { detail: 'stt_too_large' } } }
    })
    expect(result.current.error?.kind).toBe('server')
    expect(result.current.error?.detail).toBe('stt_too_large')
  })
})

describe('useVoiceInput resource release', () => {
  it('the microphone is released BEFORE the request resolves, not after', async () => {
    // The OS recording indicator follows the live track. Releasing it after the
    // round trip would leave the light on for the whole transcription, which
    // reads as "still listening".
    let resolvePost: (v: any) => void = () => {}
    mockedAxios.post.mockImplementation(() => new Promise(res => { resolvePost = res }))
    const { result, onText } = setup()
    await act(async () => { await result.current.start() })
    speak()

    let stopped: Promise<void> = Promise.resolve()
    act(() => { stopped = result.current.stop() as unknown as Promise<void> })

    expect(track.stop).toHaveBeenCalled()
    expect(onText).not.toHaveBeenCalled()
    expect(result.current.state).toBe('transcribing')

    await act(async () => { resolvePost({ data: { text: 'ok' } }); await stopped })
    expect(onText).toHaveBeenCalledWith('ok')
  })

  it('cancel discards the audio and never posts', async () => {
    const { result, onText } = setup()
    await act(async () => { await result.current.start() })
    speak()
    act(() => { result.current.cancel() })
    expect(track.stop).toHaveBeenCalled()
    expect(result.current.state).toBe('idle')
    expect(mockedAxios.post).not.toHaveBeenCalled()
    expect(onText).not.toHaveBeenCalled()
  })

  it('unmounting mid-recording stops the tracks and no late answer reaches onText', async () => {
    let resolvePost: (v: any) => void = () => {}
    mockedAxios.post.mockImplementation(() => new Promise(res => { resolvePost = res }))
    const { result, onText, unmount } = setup()
    await act(async () => { await result.current.start() })
    speak()
    act(() => { void result.current.stop() })
    unmount()
    expect(track.stop).toHaveBeenCalled()
    await act(async () => { resolvePost({ data: { text: 'too late' } }) })
    expect(onText).not.toHaveBeenCalled()
  })

  it('unmounting while still recording stops the tracks', async () => {
    const { result, unmount } = setup()
    await act(async () => { await result.current.start() })
    speak()
    unmount()
    expect(track.stop).toHaveBeenCalled()
  })
})

describe('useVoiceInput limits', () => {
  it('a recording left running stops itself at 60 s and transcribes what it has', async () => {
    vi.useFakeTimers()
    mockedAxios.post.mockResolvedValue({ data: { text: 'uzun kayıt' } })
    const { result, onText } = setup()
    await act(async () => { await result.current.start() })
    speak()
    expect(result.current.state).toBe('recording')

    await act(async () => { await vi.advanceTimersByTimeAsync(60_000) })

    expect(mockedAxios.post).toHaveBeenCalledTimes(1)
    // No `waitFor` here: fake timers are installed, so its polling would never
    // advance and the test would hang rather than fail (measured).
    await act(async () => { await Promise.resolve(); await Promise.resolve() })
    expect(onText).toHaveBeenCalledWith('uzun kayıt')
  })

  it('a 48 kHz device is decimated, so the wire format stays 16 kHz mono', async () => {
    contextRate = 48000
    mockedAxios.post.mockResolvedValue({ data: { text: 'x' } })
    const { result } = setup()
    await act(async () => { await result.current.start() })
    speak(48000)  // one second at the device rate
    await act(async () => { await result.current.stop() })

    const wav = atob(mockedAxios.post.mock.calls[0][1].wav_base64)
    const bytes = Uint8Array.from(wav, c => c.charCodeAt(0))
    const view = new DataView(bytes.buffer)
    expect(view.getUint32(24, true)).toBe(16000)   // header rate
    expect(view.getUint32(40, true)).toBe(32000)   // one second of 16 kHz 16-bit
  })
})

/**
 * Everything below promotes an audit finding into a permanent gate.
 *
 * The shared shape of all six: the microphone is an OS-VISIBLE resource, and
 * each of these paths left the track live with no reference left to stop it.
 * The user's only signal would be a recording indicator that never goes out,
 * which reads as the app listening in the background — the worst thing a
 * dictation feature can do quietly.
 */
describe('useVoiceInput partial teardown when the graph fails after acquisition', () => {
  it('AudioWorkletNode constructor throws → track stopped, context closed, error noDevice', async () => {
    onNodeConstruct = () => { throw new Error('node boom') }
    const { result } = setup()
    await act(async () => { await result.current.start() })
    expect(track.stop).toHaveBeenCalled()
    expect(lastCtx.close).toHaveBeenCalled()
    expect(result.current.error?.kind).toBe('noDevice')
    expect(result.current.state).toBe('idle')
  })

  it('createMediaStreamSource throws → track stopped, context closed, error noDevice', async () => {
    createSourceImpl = () => { throw new Error('source boom') }
    const { result } = setup()
    await act(async () => { await result.current.start() })
    expect(track.stop).toHaveBeenCalled()
    expect(lastCtx.close).toHaveBeenCalled()
    expect(result.current.error?.kind).toBe('noDevice')
  })

  it('source.connect throws → track stopped, context closed, error noDevice', async () => {
    createSourceImpl = () => ({
      connect: vi.fn(() => { throw new Error('connect boom') }),
      disconnect: vi.fn(),
    })
    const { result } = setup()
    await act(async () => { await result.current.start() })
    expect(track.stop).toHaveBeenCalled()
    expect(lastCtx.close).toHaveBeenCalled()
    expect(result.current.error?.kind).toBe('noDevice')
  })
})

describe('useVoiceInput acquisition that finishes after unmount', () => {
  it('unmount while getUserMedia is pending → late stream stopped, no graph installed', async () => {
    let resolveMedia: (v: any) => void = () => {}
    getUserMedia = vi.fn(() => new Promise(res => { resolveMedia = res }))
    const { result, unmount, onText } = setup()
    let pending!: Promise<void>
    act(() => { pending = result.current.start() as unknown as Promise<void> })
    unmount()
    await act(async () => { resolveMedia({ getTracks: () => [track] }); await pending })
    expect(track.stop).toHaveBeenCalled()
    // No context at all: the resumed path has to bail before building anything.
    expect(lastCtx).toBeNull()
    expect(onText).not.toHaveBeenCalled()
    expect(result.current.state).toBe('idle')
  })

  it('unmount while addModule is pending → track stopped and context closed', async () => {
    let resolveModule: () => void = () => {}
    addModule = vi.fn(() => new Promise<void>(res => { resolveModule = res }))
    const { result, unmount } = setup()
    let pending!: Promise<void>
    act(() => { pending = result.current.start() as unknown as Promise<void> })
    // Let `start()` get past getUserMedia and actually park inside the module
    // load — otherwise the earlier post-getUserMedia check would be what stops
    // it and this test would not measure the window it is named for.
    await act(async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve() })
    expect(addModule).toHaveBeenCalled()
    expect(lastCtx).not.toBeNull()
    unmount()
    await act(async () => { resolveModule(); await pending })
    expect(track.stop).toHaveBeenCalled()
    expect(lastCtx.close).toHaveBeenCalled()
    expect(lastNode).toBeNull()
  })
})

describe('useVoiceInput cleanup that itself fails', () => {
  it('AudioContext.close rejecting → a rejection handler is attached, so nothing escapes', async () => {
    // Detection follows the audit probe: a thenable that records whether the
    // caller passed an `onRejected`. `void ctx.close()` catches only a
    // SYNCHRONOUS throw, so a rejected close promise escaped as an unhandled
    // rejection while the hook had already nulled its context ref.
    let closeRejectionHandled = false
    closeImpl = () => ({
      then(onFulfilled?: any, onRejected?: any) {
        if (typeof onRejected === 'function') closeRejectionHandled = true
        queueMicrotask(() => {
          if (typeof onRejected === 'function') onRejected(new Error('close refused'))
        })
        return Promise.resolve()
      },
      catch(onRejected?: any) {
        if (typeof onRejected === 'function') closeRejectionHandled = true
        return this.then(undefined, onRejected)
      },
    })
    mockedAxios.post.mockResolvedValue({ data: { text: 'x' } })
    const { result } = setup()
    await act(async () => { await result.current.start() })
    speak()
    await act(async () => { await result.current.stop() })
    expect(lastCtx.close).toHaveBeenCalledTimes(1)
    expect(closeRejectionHandled).toBe(true)
  })
})

describe('useVoiceInput duplicate start', () => {
  it('two start() calls before acquisition settles → one stream acquired, cancel stops it', async () => {
    // The old guard read React state, which stays `idle` for the whole async
    // acquisition: both calls passed it, both acquired a stream, and the refs
    // held only the second — so the first track could never be stopped again.
    const tracks = [{ stop: vi.fn() }, { stop: vi.fn() }]
    let call = 0
    getUserMedia = vi.fn(() => {
      const t = tracks[Math.min(call++, tracks.length - 1)]
      return Promise.resolve({ getTracks: () => [t] })
    })
    const { result } = setup()
    let first!: Promise<void>
    let second!: Promise<void>
    act(() => {
      first = result.current.start() as unknown as Promise<void>
      second = result.current.start() as unknown as Promise<void>
    })
    await act(async () => { await Promise.all([first, second]) })
    act(() => { result.current.cancel() })
    expect(getUserMedia).toHaveBeenCalledTimes(1)
    expect(tracks[0].stop).toHaveBeenCalled()
    expect(tracks[1].stop).not.toHaveBeenCalled()
  })
})
