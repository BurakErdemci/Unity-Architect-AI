/**
 * Slider position <-> clip time arithmetic for the preview's playback bar.
 *
 * Deliberately free of three and of React: the panel that owns the mixer needs
 * a WebGL context to exist at all, so anything tested headless has to live
 * outside it. Every function here is total — no input produces NaN, because a
 * NaN reaching `action.time` silently blanks the model (same failure class the
 * zero-duration guard in loaders.ts exists for).
 */

/** Playback rates offered by the speed selector, in mixer `timeScale` units. */
export const SPEEDS = [0.25, 0.5, 1, 2] as const;

export type Speed = (typeof SPEEDS)[number];

export const DEFAULT_SPEED: Speed = 1;

/** A clip is scrubbable only if it spans real time. */
export const hasDuration = (duration: number): boolean =>
  Number.isFinite(duration) && duration > 0;

/**
 * Fold `time` into `[0, duration)` — the wrap a looping clip performs. Negative
 * input folds forward rather than clamping to 0, so stepping back past the
 * start lands at the end the way the loop would.
 */
export const wrapTime = (time: number, duration: number): number => {
  if (!hasDuration(duration) || !Number.isFinite(time)) return 0;
  const wrapped = time % duration;
  return wrapped < 0 ? wrapped + duration : wrapped;
};

/** Where the slider thumb belongs for a clip time, as `0..1`. */
export const fractionAtTime = (time: number, duration: number): number =>
  hasDuration(duration) ? wrapTime(time, duration) / duration : 0;

/**
 * The clip time a slider fraction points at, already wrapped. Dragging fully
 * right therefore lands on 0: for a looping clip the end and the start are the
 * same instant, and returning `duration` would only let the next mixer update
 * do the wrap one frame later.
 */
export const timeAtFraction = (fraction: number, duration: number): number => {
  if (!hasDuration(duration) || !Number.isFinite(fraction)) return 0;
  return wrapTime(Math.min(Math.max(fraction, 0), 1) * duration, duration);
};

/**
 * `m:ss.d`, always. Not routed through i18n on purpose: it carries no words,
 * and a translated timecode would be a translated number format we do not have
 * the locale data to get right.
 */
export const formatTimecode = (seconds: number): string => {
  const safe = Number.isFinite(seconds) && seconds > 0 ? seconds : 0;
  const minutes = Math.floor(safe / 60);
  const rest = safe - minutes * 60;
  // toFixed rounds, so 59.97 becomes "60.0" and the clock reads 0:60.0.
  const shown = Math.min(rest, 59.9);
  return `${minutes}:${shown < 10 ? '0' : ''}${shown.toFixed(1)}`;
};
