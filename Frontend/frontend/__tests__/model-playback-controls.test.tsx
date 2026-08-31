/**
 * The transport bar on its own. It is tested apart from the panel because the
 * panel needs a WebGL context to build a stage at all, and jsdom has none — so
 * inside the panel this bar can never appear.
 *
 * Wording is pulled from the i18n table rather than typed in, so a copy edit
 * does not turn into a red test.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { cevir } from '../renderer/lib/i18n'
import { PlaybackControls } from '../renderer/components/model-viewer/PlaybackControls'

const PLAY = cevir('preview.play')
const PAUSE = cevir('preview.pause')
const TIMELINE = cevir('preview.timeline')
const SPEED = cevir('preview.speed')

const draw = (over: Partial<React.ComponentProps<typeof PlaybackControls>> = {}) => {
  const props = {
    duration: 4,
    time: 0,
    playing: true,
    speed: 1 as const,
    onTogglePlay: vi.fn(),
    onSeek: vi.fn(),
    onSpeedChange: vi.fn(),
    ...over,
  }
  render(<PlaybackControls {...props} />)
  return props
}

const slider = () => screen.getByLabelText(TIMELINE) as HTMLInputElement

describe('PlaybackControls', () => {
  it('offers pause while running and play while stopped', () => {
    const { unmount } = render(
      <PlaybackControls
        duration={4} time={0} playing speed={1}
        onTogglePlay={() => {}} onSeek={() => {}} onSpeedChange={() => {}}
      />,
    )
    expect(screen.getByLabelText(PAUSE)).toBeTruthy()
    expect(screen.queryByLabelText(PLAY)).toBeNull()
    unmount()

    draw({ playing: false })
    expect(screen.getByLabelText(PLAY)).toBeTruthy()
    expect(screen.queryByLabelText(PAUSE)).toBeNull()
  })

  it('asks the owner to toggle when the transport button is pressed', () => {
    const props = draw({ playing: false })
    fireEvent.click(screen.getByLabelText(PLAY))
    expect(props.onTogglePlay).toHaveBeenCalledTimes(1)
  })

  it('puts the thumb where the current time sits in the clip', () => {
    draw({ time: 1, duration: 4 })
    const el = slider()
    expect(Number(el.value) / Number(el.max)).toBeCloseTo(0.25, 6)
  })

  it('parks the thumb at the start of the track when the clip restarts', () => {
    draw({ time: 4, duration: 4 })
    expect(Number(slider().value)).toBe(0)
  })

  it('reports a drag as a 0..1 fraction of the clip', () => {
    const props = draw()
    const el = slider()
    fireEvent.change(el, { target: { value: String(Number(el.max) / 2) } })
    expect(props.onSeek).toHaveBeenCalledWith(0.5)
  })

  it('reports a drag to either end as 0 and 1', () => {
    // Starts mid-clip: React fires no change event when a controlled input is
    // set to the value it already holds, so ends have to be moved TO.
    const props = draw({ time: 2, duration: 4 })
    const el = slider()
    fireEvent.change(el, { target: { value: el.min } })
    fireEvent.change(el, { target: { value: el.max } })
    expect(props.onSeek).toHaveBeenNthCalledWith(1, 0)
    expect(props.onSeek).toHaveBeenNthCalledWith(2, 1)
  })

  it('shows both the current position and the clip length', () => {
    draw({ time: 1.5, duration: 4 })
    expect(screen.getByText('0:01.5')).toBeTruthy()
    expect(screen.getByText('0:04.0')).toBeTruthy()
  })

  it('offers exactly the four playback rates', () => {
    draw()
    const options = Array.from((screen.getByLabelText(SPEED) as HTMLSelectElement).options)
    expect(options.map(o => o.value)).toEqual(['0.25', '0.5', '1', '2'])
    expect(options.map(o => o.textContent)).toEqual(['0.25×', '0.5×', '1×', '2×'])
  })

  it('shows the rate in force and reports a change as a number', () => {
    const props = draw({ speed: 0.5 })
    const select = screen.getByLabelText(SPEED) as HTMLSelectElement
    expect(select.value).toBe('0.5')
    fireEvent.change(select, { target: { value: '2' } })
    expect(props.onSpeedChange).toHaveBeenCalledWith(2)
  })

  it('labels every control, so none of them is an unnamed icon', () => {
    draw()
    for (const label of [PAUSE, TIMELINE, SPEED]) {
      expect(screen.getByLabelText(label)).toBeTruthy()
    }
  })
})
