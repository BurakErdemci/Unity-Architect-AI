import React from 'react';
import { Pause, Play } from 'lucide-react';
import { useLang } from '../../lib/i18n';
import { fractionAtTime, formatTimecode, SPEEDS, type Speed } from './timeline';

export interface PlaybackControlsProps {
  /** Clip length in seconds. The caller renders nothing when there is no clip. */
  duration: number;
  time: number;
  playing: boolean;
  speed: Speed;
  onTogglePlay: () => void;
  /** Slider fraction in `0..1`; the owner converts it to clip time. */
  onSeek: (fraction: number) => void;
  onSpeedChange: (speed: Speed) => void;
}

// The range input is integer-stepped and scaled down on read: a float `step`
// makes browsers snap to their own rounding of the interval, which drifts the
// thumb away from the pointer on long clips.
const STEPS = 1000;

/**
 * The transport bar. Presentational and three-free on purpose — it is the only
 * part of the playback UI that can be exercised under jsdom, where no WebGL
 * context exists and the panel that owns the mixer never gets built.
 */
export const PlaybackControls: React.FC<PlaybackControlsProps> = ({
  duration, time, playing, speed, onTogglePlay, onSeek, onSpeedChange,
}) => {
  const { t } = useLang();
  const label = playing ? t('preview.pause') : t('preview.play');

  return (
    <div className="absolute bottom-0 inset-x-0 flex items-center gap-3 px-3 py-2 bg-[#0B0D12]/85 backdrop-blur-sm border-t border-white/5">
      <button
        type="button"
        onClick={onTogglePlay}
        aria-label={label}
        title={label}
        className="shrink-0 grid place-items-center w-7 h-7 rounded-md text-slate-300 hover:text-white hover:bg-white/10 transition-colors"
      >
        {playing ? <Pause size={14} /> : <Play size={14} />}
      </button>

      <span className="shrink-0 text-[10px] font-mono tabular-nums text-slate-400">
        {formatTimecode(time)}
      </span>

      <input
        type="range"
        min={0}
        max={STEPS}
        step={1}
        value={Math.round(fractionAtTime(time, duration) * STEPS)}
        onChange={e => onSeek(Number(e.target.value) / STEPS)}
        aria-label={t('preview.timeline')}
        title={t('preview.timeline')}
        className="flex-1 min-w-0 h-1 accent-sky-400 cursor-pointer"
      />

      <span className="shrink-0 text-[10px] font-mono tabular-nums text-slate-500">
        {formatTimecode(duration)}
      </span>

      <select
        value={speed}
        onChange={e => onSpeedChange(Number(e.target.value) as Speed)}
        aria-label={t('preview.speed')}
        title={t('preview.speed')}
        className="shrink-0 bg-white/5 border border-white/10 rounded-md text-[10px] font-semibold text-slate-300 px-1.5 py-1 outline-none hover:bg-white/10 cursor-pointer"
      >
        {SPEEDS.map(value => (
          <option key={value} value={value} className="bg-[#0B0D12]">{`${value}×`}</option>
        ))}
      </select>
    </div>
  );
};

export default PlaybackControls;
