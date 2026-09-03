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
}))

vi.mock('../renderer/hooks/home/useVoiceInput', () => ({
  useVoiceInput: (params: any) => {
    voice.captured = params
    return {
      state: voice.state,
      elapsedMs: voice.elapsedMs,
      error: voice.error,
      start: vi.fn(),
      stop: vi.fn(),
      cancel: vi.fn(),
      clearError: vi.fn(),
    }
  },
  formatElapsed: (ms: number) => `00:${String(Math.floor(ms / 1000)).padStart(2, '0')}`,
}))

import { AnimatedChatInput } from '../renderer/components/ui/animated-ai-chat'
import { tr } from '../renderer/lib/i18n'

const API = 'http://127.0.0.1:1'

const mount = () => {
  const setValue = vi.fn()
  render(
    <AnimatedChatInput
      value=""
      setValue={setValue}
      onSendMessage={vi.fn()}
      isLoading={false}
      api={API}
    />,
  )
  return { setValue, textarea: screen.getByRole('textbox') as HTMLTextAreaElement }
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
