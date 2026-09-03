/**
 * Dictated text has to land where the user is looking — at the caret — and the
 * caret has to stay after it so they can keep typing.
 *
 * Why this lives inside `AnimatedChatInput` and is tested there: the composer
 * keeps what is being typed in its own `internalValue` and only syncs FROM the
 * parent, so text pushed in from outside through `setChatInput` would overwrite
 * whatever the user had typed. The insertion therefore has to be done by the
 * component that owns the textarea, and this file measures that it is.
 *
 * The recording hook itself is mocked: what is under test is the insertion
 * arithmetic and the inline error, not Web Audio.
 */
import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, act, waitFor, cleanup } from '@testing-library/react'

const voice = vi.hoisted(() => ({
  captured: null as null | { onText: (text: string) => void },
  state: 'idle' as 'idle' | 'recording' | 'transcribing',
  elapsedMs: 0,
  error: null as null | { kind: string; detail?: string },
  partialText: '',
  // Stable across renders so a test can assert the composer asked for a
  // recording to start or to be thrown away.
  start: vi.fn(),
  stop: vi.fn(),
  cancel: vi.fn(),
  clearError: vi.fn(),
}))

vi.mock('../renderer/hooks/home/useVoiceInput', () => ({
  useVoiceInput: (params: any) => {
    voice.captured = params
    return {
      state: voice.state,
      elapsedMs: voice.elapsedMs,
      error: voice.error,
      partialText: voice.partialText,
      start: voice.start,
      stop: voice.stop,
      cancel: voice.cancel,
      clearError: voice.clearError,
    }
  },
  formatElapsed: (ms: number) => `00:${String(Math.floor(ms / 1000)).padStart(2, '0')}`,
}))

import { AnimatedChatInput } from '../renderer/components/ui/animated-ai-chat'
import { tr } from '../renderer/lib/i18n'

const API = 'http://127.0.0.1:1'

const mount = () => {
  const setValue = vi.fn()
  const onSendMessage = vi.fn()
  // A FRESH element every time: React bails out of a re-render handed the same
  // element reference, so reusing one would silently never pick the stub up.
  const ui = () => (
    <AnimatedChatInput
      value=""
      setValue={setValue}
      onSendMessage={onSendMessage}
      isLoading={false}
      api={API}
    />
  )
  const utils = render(ui())
  // The hook is a module-level stub, so a state change in it only reaches the
  // component through a re-render — that is what `bump` is for.
  const bump = () => act(() => { utils.rerender(ui()) })
  return {
    setValue,
    onSendMessage,
    bump,
    textarea: screen.getByRole('textbox') as HTMLTextAreaElement,
  }
}

const micButton = () => document.querySelector('[data-mic-button]') as HTMLButtonElement
const sendButton = () =>
  Array.from(document.querySelectorAll('button')).find(b => b.textContent === 'Send') as HTMLButtonElement

/** Press the mic, then let the stub report that recording really started. */
const startRecording = (ctx: { bump: () => void }) => {
  fireEvent.click(micButton())
  voice.state = 'recording'
  ctx.bump()
}

/** Push one partial result through the composer, as the hook would. */
const say = (partial: string, ctx: { bump: () => void }) => {
  voice.partialText = partial
  ctx.bump()
}

/** The `api` prop OMITTED, not passed as undefined — that is what home.tsx
 *  effectively does before `useAppInitialization` resolves the address. */
const mountWithoutApi = () => {
  render(
    <AnimatedChatInput value="" setValue={vi.fn()} onSendMessage={vi.fn()} isLoading={false} />,
  )
}

beforeEach(() => {
  cleanup()
  voice.captured = null
  voice.state = 'idle'
  voice.elapsedMs = 0
  voice.error = null
  voice.partialText = ''
  voice.start.mockClear()
  voice.stop.mockClear()
  voice.cancel.mockClear()
  voice.clearError.mockClear()
})

describe('dictated text at the caret', () => {
  it('lands where the caret is, separated by a single space', async () => {
    const { setValue, textarea } = mount()
    fireEvent.change(textarea, { target: { value: 'hello world' } })
    textarea.setSelectionRange(5, 5)  // right after "hello"

    act(() => { voice.captured!.onText('there') })

    await waitFor(() => expect(textarea.value).toBe('hello there world'))
    // The parent is told too, otherwise the message sent on Enter would be the
    // pre-dictation text.
    expect(setValue).toHaveBeenCalledWith('hello there world')
  })

  it('leaves the caret after the inserted words, not at the end of the box', async () => {
    const { textarea } = mount()
    fireEvent.change(textarea, { target: { value: 'hello world' } })
    textarea.setSelectionRange(5, 5)

    act(() => { voice.captured!.onText('there') })

    await waitFor(() => expect(textarea.value).toBe('hello there world'))
    await waitFor(() => expect(textarea.selectionStart).toBe(11))
    expect(textarea.selectionEnd).toBe(11)
  })

  it('an empty box gets no leading space', async () => {
    const { textarea } = mount()
    act(() => { voice.captured!.onText('merhaba') })
    await waitFor(() => expect(textarea.value).toBe('merhaba'))
  })

  it('a caret already after a space does not get a second one', async () => {
    const { textarea } = mount()
    fireEvent.change(textarea, { target: { value: 'hello ' } })
    textarea.setSelectionRange(6, 6)
    act(() => { voice.captured!.onText('there') })
    await waitFor(() => expect(textarea.value).toBe('hello there'))
  })

  it('a selection is replaced, not appended around', async () => {
    const { textarea } = mount()
    fireEvent.change(textarea, { target: { value: 'hello world' } })
    textarea.setSelectionRange(6, 11)  // "world" selected
    act(() => { voice.captured!.onText('everyone') })
    await waitFor(() => expect(textarea.value).toBe('hello everyone'))
  })
})

describe('the mic button', () => {
  it('is a plain button and reports its recording state to assistive tech', () => {
    mount()
    const btn = document.querySelector('[data-mic-button]') as HTMLButtonElement
    expect(btn.getAttribute('type')).toBe('button')
    expect(btn.getAttribute('aria-pressed')).toBe('false')
    expect(btn.getAttribute('aria-label')).toBe(tr['mic.start'])
  })

  it('while recording it flips aria-pressed, shows the timer and offers to stop', () => {
    voice.state = 'recording'
    voice.elapsedMs = 7_000
    mount()
    const btn = document.querySelector('[data-mic-button]') as HTMLButtonElement
    expect(btn.getAttribute('aria-pressed')).toBe('true')
    expect(btn.getAttribute('aria-label')).toBe(tr['mic.stop'])
    expect(btn.textContent).toContain('00:07')
  })

  it('is disabled with the unreachable-backend title while the address is unknown', () => {
    // No `api` prop: `home.tsx` only has the address after IPC resolves it, and
    // a mic that posts to `"/transcribe"` would fail in a way the user cannot read.
    mountWithoutApi()
    const btn = document.querySelector('[data-mic-button]') as HTMLButtonElement
    expect(btn.disabled).toBe(true)
    expect(btn.getAttribute('title')).toBe(tr['mic.err.server'])
  })

  it('carries a speaking-language toggle that starts at the app language', () => {
    mount()
    const toggle = document.querySelector('[data-mic-lang]') as HTMLButtonElement
    expect(toggle.textContent).toBe('tr')
    fireEvent.click(toggle)
    expect(toggle.textContent).toBe('en')
  })
})

describe('the inline error', () => {
  it('is text beside the button — not a toast — and says which failure it was', () => {
    voice.error = { kind: 'permission' }
    mount()
    expect(screen.getByText(tr['mic.err.permission'])).toBeTruthy()
  })

  it('keeps the raw backend detail in the title instead of showing jargon', () => {
    voice.error = { kind: 'server', detail: 'stt_too_large' }
    mount()
    const label = document.querySelector('[data-mic-error]') as HTMLElement
    expect(label.textContent).toBe(tr['mic.err.server'])
    expect(label.getAttribute('title')).toBe('stt_too_large')
  })
})

/**
 * Live dictation: the words appear in the box while the user speaks.
 *
 * The composer owns a RANGE of the text between pressing the mic and the final
 * result, and rewrites it on every partial. What is measured here is that the
 * range is rewritten rather than appended to (vosk revises its own guesses), and
 * that the box is handed back to the keyboard in every exit — final, error and
 * cancel — because a textarea left read-only is a chat the user cannot type in.
 */
describe('live dictation in the box', () => {
  it('shows each partial where the caret was, with the separator rule', async () => {
    const ctx = mount()
    fireEvent.change(ctx.textarea, { target: { value: 'hello world' } })
    ctx.textarea.setSelectionRange(5, 5)  // right after "hello"
    startRecording(ctx)

    say('there', ctx)
    await waitFor(() => expect(ctx.textarea.value).toBe('hello there world'))
    expect(ctx.setValue).toHaveBeenCalledWith('hello there world')
  })

  it('replaces the previous partial instead of piling the guesses up', async () => {
    const ctx = mount()
    startRecording(ctx)

    say('mer', ctx)
    await waitFor(() => expect(ctx.textarea.value).toBe('mer'))
    say('merhaba', ctx)
    await waitFor(() => expect(ctx.textarea.value).toBe('merhaba'))
    // The recogniser is allowed to change its mind about words it already sent.
    say('merhaba dunya', ctx)
    await waitFor(() => expect(ctx.textarea.value).toBe('merhaba dunya'))
  })

  it('an empty box gets no leading space from the interim text either', async () => {
    const ctx = mount()
    startRecording(ctx)
    say('merhaba', ctx)
    await waitFor(() => expect(ctx.textarea.value).toBe('merhaba'))
  })

  it('a selection is replaced by what is dictated, not spoken around', async () => {
    const ctx = mount()
    fireEvent.change(ctx.textarea, { target: { value: 'hello world' } })
    ctx.textarea.setSelectionRange(6, 11)  // "world" selected
    startRecording(ctx)

    say('everyone', ctx)
    await waitFor(() => expect(ctx.textarea.value).toBe('hello everyone'))
  })

  it('the final text replaces the interim and leaves the caret after it', async () => {
    const ctx = mount()
    fireEvent.change(ctx.textarea, { target: { value: 'hello world' } })
    ctx.textarea.setSelectionRange(5, 5)
    startRecording(ctx)
    say('ther', ctx)
    await waitFor(() => expect(ctx.textarea.value).toBe('hello ther world'))

    voice.state = 'transcribing'
    ctx.bump()
    act(() => { voice.captured!.onText('there') })

    await waitFor(() => expect(ctx.textarea.value).toBe('hello there world'))
    await waitFor(() => expect(ctx.textarea.selectionStart).toBe(11))
    expect(ctx.textarea.selectionEnd).toBe(11)
  })

  it('the textarea is read-only while recording, so typing cannot fight the transcript', () => {
    const ctx = mount()
    expect(ctx.textarea.readOnly).toBe(false)
    startRecording(ctx)
    expect(ctx.textarea.readOnly).toBe(true)
    // Still read-only while the final text is being fetched: it is still coming.
    voice.state = 'transcribing'
    ctx.bump()
    expect(ctx.textarea.readOnly).toBe(true)
  })

  it('Enter is ignored while recording — a half-transcribed sentence is not sent', () => {
    const ctx = mount()
    fireEvent.change(ctx.textarea, { target: { value: 'yarim' } })
    startRecording(ctx)
    fireEvent.keyDown(ctx.textarea, { key: 'Enter' })
    expect(ctx.onSendMessage).not.toHaveBeenCalled()
  })

  it('the Send button is disabled while recording', () => {
    const ctx = mount()
    fireEvent.change(ctx.textarea, { target: { value: 'hazir' } })
    expect(sendButton().disabled).toBe(false)
    startRecording(ctx)
    expect(sendButton().disabled).toBe(true)
  })

  it('the Send button stays disabled while transcribing, not just while recording', async () => {
    // Audit finding, 3 Sep 2026: the button's own disabled check only tested
    // `voice.state === 'recording'`, so an interim value could still be sent
    // during the `transcribing` window the textarea was already read-only for.
    const ctx = mount()
    startRecording(ctx)
    say('half sentence', ctx)
    await waitFor(() => expect(ctx.textarea.value).toBe('half sentence'))

    voice.state = 'transcribing'
    ctx.bump()
    expect(sendButton().disabled).toBe(true)
    fireEvent.click(sendButton())
    expect(ctx.onSendMessage).not.toHaveBeenCalled()
  })

  it('an error puts the pre-recording text back and hands the box over', async () => {
    const ctx = mount()
    fireEvent.change(ctx.textarea, { target: { value: 'hello world' } })
    ctx.textarea.setSelectionRange(5, 5)
    startRecording(ctx)
    say('there', ctx)
    await waitFor(() => expect(ctx.textarea.value).toBe('hello there world'))

    voice.state = 'idle'
    voice.error = { kind: 'server' }
    ctx.bump()

    await waitFor(() => expect(ctx.textarea.value).toBe('hello world'))
    expect(ctx.textarea.readOnly).toBe(false)
    await waitFor(() => expect(document.activeElement).toBe(ctx.textarea))
  })

  it('a final that arrives after an error has restored the box is dropped, not inserted', async () => {
    // Audit finding, 3 Sep 2026: `handleFinalText` treated a cleared
    // `dictationRef` as "no dictation was ever armed" and inserted the late
    // text as if it were a fresh one-shot recording, undoing the error's own
    // restore of the pre-recording text.
    const ctx = mount()
    fireEvent.change(ctx.textarea, { target: { value: 'hello world' } })
    ctx.textarea.setSelectionRange(5, 5)
    startRecording(ctx)
    say('there', ctx)
    await waitFor(() => expect(ctx.textarea.value).toBe('hello there world'))

    voice.state = 'idle'
    voice.error = { kind: 'server' }
    ctx.bump()
    await waitFor(() => expect(ctx.textarea.value).toBe('hello world'))

    act(() => { voice.captured!.onText('late') })
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(ctx.textarea.value).toBe('hello world')
  })

  it('a genuine one-shot final (no button-armed dictation) still inserts normally', async () => {
    // The drop above must be scoped to a final that follows THIS composer's
    // own abort, not to every final with no armed range.
    const ctx = mount()
    fireEvent.change(ctx.textarea, { target: { value: 'hello' } })
    ctx.textarea.setSelectionRange(5, 5)
    act(() => { voice.captured!.onText('world') })
    await waitFor(() => expect(ctx.setValue).toHaveBeenCalled())
  })

  it('Escape while recording cancels it and restores the box', async () => {
    const ctx = mount()
    fireEvent.change(ctx.textarea, { target: { value: 'merhaba' } })
    ctx.textarea.setSelectionRange(7, 7)
    startRecording(ctx)
    say('dunya', ctx)
    await waitFor(() => expect(ctx.textarea.value).toBe('merhaba dunya'))

    fireEvent.keyDown(ctx.textarea, { key: 'Escape' })
    expect(voice.cancel).toHaveBeenCalled()
    await waitFor(() => expect(ctx.textarea.value).toBe('merhaba'))
  })

  it('unmounting cancels the deferred caret/scroll work each partial scheduled', async () => {
    // Audit finding, 3 Sep 2026: every partial armed a `setTimeout(0)` for
    // caret and scroll work with nothing to cancel it, so unmounting mid-
    // dictation left them scheduled. Fake timers only for this one test —
    // real timers elsewhere in this file, restored in `finally` regardless of
    // outcome so a failure here cannot leak into the next test.
    vi.useFakeTimers()
    try {
      const ctx = mount()
      startRecording(ctx)
      const afterStart = vi.getTimerCount()
      for (let i = 1; i <= 5; i++) say(`p${i}`, ctx)
      const afterPartials = vi.getTimerCount()
      expect(afterPartials).toBe(afterStart + 5)

      cleanup()  // unmounts every currently-rendered tree, this composer included
      // Exactly the 5 partial-driven callbacks must be gone; whatever existed
      // before the first partial (unrelated to dictation) is not this fix's claim.
      expect(vi.getTimerCount()).toBeLessThanOrEqual(afterStart)
    } finally {
      vi.useRealTimers()
    }
  })
})
