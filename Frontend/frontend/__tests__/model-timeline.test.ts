/**
 * Slider-position <-> clip-time arithmetic.
 *
 * Worth its own file because every one of these values ends up in
 * `action.time`, and the failure mode there is silent: a NaN or a negative time
 * blanks the model without raising anything (the same class of trap the
 * zero-duration guard in loaders.ts was written for).
 */
import { describe, it, expect } from 'vitest'
import {
  DEFAULT_SPEED,
  SPEEDS,
  formatTimecode,
  fractionAtTime,
  hasDuration,
  timeAtFraction,
  wrapTime,
} from '../renderer/components/model-viewer/timeline'

describe('wrapTime', () => {
  it('leaves a time inside the clip alone', () => {
    expect(wrapTime(1.5, 4)).toBe(1.5)
  })

  it('folds a time past the end back to the start, however many loops over', () => {
    expect(wrapTime(4, 4)).toBe(0)
    expect(wrapTime(5, 4)).toBe(1)
    expect(wrapTime(13, 4)).toBe(1)
  })

  it('folds a negative time forward instead of clamping at zero', () => {
    expect(wrapTime(-1, 4)).toBe(3)
    expect(wrapTime(-9, 4)).toBe(3)
  })

  it('answers zero rather than NaN for a clip with no length', () => {
    for (const duration of [0, -1, Number.NaN, Number.POSITIVE_INFINITY]) {
      expect(wrapTime(2, duration)).toBe(0)
    }
    expect(wrapTime(Number.NaN, 4)).toBe(0)
  })
})

describe('fractionAtTime', () => {
  it('places the thumb proportionally along the clip', () => {
    expect(fractionAtTime(0, 4)).toBe(0)
    expect(fractionAtTime(1, 4)).toBe(0.25)
    expect(fractionAtTime(3, 4)).toBe(0.75)
  })

  it('sends the wrapped end of the clip back to the start of the track', () => {
    expect(fractionAtTime(4, 4)).toBe(0)
  })

  it('parks the thumb at zero for an unplayable clip', () => {
    expect(fractionAtTime(2, 0)).toBe(0)
  })
})

describe('timeAtFraction', () => {
  it('reads a drag position as a clip time', () => {
    expect(timeAtFraction(0, 4)).toBe(0)
    expect(timeAtFraction(0.5, 4)).toBe(2)
  })

  it('treats a drag to the far right as the loop point, not one frame past it', () => {
    expect(timeAtFraction(1, 4)).toBe(0)
  })

  it('clamps a fraction outside 0..1', () => {
    expect(timeAtFraction(-3, 4)).toBe(0)
    expect(timeAtFraction(9, 4)).toBe(0)
  })

  it('round-trips against fractionAtTime everywhere but the loop point', () => {
    for (const f of [0, 0.1, 0.25, 0.5, 0.75, 0.9]) {
      expect(fractionAtTime(timeAtFraction(f, 6), 6)).toBeCloseTo(f, 10)
    }
  })

  it('answers zero rather than NaN for a clip with no length', () => {
    expect(timeAtFraction(0.5, 0)).toBe(0)
    expect(timeAtFraction(Number.NaN, 4)).toBe(0)
  })
})

describe('formatTimecode', () => {
  it('reads as m:ss.d', () => {
    expect(formatTimecode(0)).toBe('0:00.0')
    expect(formatTimecode(3.24)).toBe('0:03.2')
    expect(formatTimecode(75.5)).toBe('1:15.5')
  })

  it('never rolls the seconds field to 60', () => {
    expect(formatTimecode(59.99)).toBe('0:59.9')
  })

  it('shows zero for a nonsense length instead of NaN', () => {
    expect(formatTimecode(Number.NaN)).toBe('0:00.0')
    expect(formatTimecode(-4)).toBe('0:00.0')
  })
})

describe('speed options', () => {
  it('offers the four rates the brief names, in order', () => {
    expect([...SPEEDS]).toEqual([0.25, 0.5, 1, 2])
  })

  it('starts at authored speed', () => {
    expect(DEFAULT_SPEED).toBe(1)
  })
})

describe('hasDuration', () => {
  it('accepts only a finite positive length', () => {
    expect(hasDuration(0.001)).toBe(true)
    expect(hasDuration(0)).toBe(false)
    expect(hasDuration(-1)).toBe(false)
    expect(hasDuration(Number.NaN)).toBe(false)
    expect(hasDuration(Number.POSITIVE_INFINITY)).toBe(false)
  })
})
