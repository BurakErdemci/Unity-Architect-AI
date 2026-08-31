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
 * The last instant still INSIDE the clip. `duration` itself is the loop point,
 * which is frame 0 — see `timeAtFraction`.
 */
const lastInstant = (duration: number): number => {
  const under = duration * (1 - Number.EPSILON);
  // Subnormal durations round straight back to `duration`; there is no interior
  // instant to offer then, and 0 is the only safe answer.
  return under < duration ? under : 0;
};

/**
 * The clip time a slider fraction points at.
 *
 * Dragging fully right lands just short of `duration`, not on it. Landing on
 * `duration` wraps to 0, and that breaks two things. The end of a one-shot clip
 * — an attack, a death, a jump — becomes unreachable by scrubbing, so the user
 * dragging right to see the finish is shown the opening pose. And because the
 * slider is a controlled input that reads back through `fractionAtTime`, the
 * thumb snaps to the far LEFT while the pointer still holds the far right;
 * every further pointermove re-fires the round trip and pins it there. The End
 * key does it in one keystroke.
 *
 * Only this input direction clamps. `fractionAtTime` still wraps, so a clip
 * that reaches its end while PLAYING parks the thumb at 0 — which is where the
 * next loop genuinely starts.
 */
export const timeAtFraction = (fraction: number, duration: number): number => {
  if (!hasDuration(duration) || !Number.isFinite(fraction)) return 0;
  const requested = Math.min(Math.max(fraction, 0), 1) * duration;
  return wrapTime(Math.min(requested, lastInstant(duration)), duration);
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
