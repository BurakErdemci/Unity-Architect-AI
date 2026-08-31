import * as THREE from 'three';
import { wrapTime } from './timeline';

/**
 * Mixer plumbing for one clip, separated from the panel so it can be exercised
 * without a WebGL context: `AnimationMixer` needs no renderer, only the panel
 * around it does. Pausing is NOT `action.paused` — the owner simply stops
 * calling `advance`, which keeps "is it running" in one place (the rAF loop's
 * own condition) instead of two that can disagree.
 */
export interface Playback {
  mixer: THREE.AnimationMixer;
  duration: number;
  /** Advance by `delta` wall-clock seconds and return the new clip time. */
  advance: (delta: number) => number;
  /** Jump to `time` and apply the pose without advancing the clock. */
  seek: (time: number) => number;
  time: () => number;
  /** Mixer `timeScale`; 1 is authored speed. */
  setSpeed: (speed: number) => void;
  dispose: () => void;
}

export const createPlayback = (
  root: THREE.Object3D,
  clip: THREE.AnimationClip,
): Playback => {
  const mixer = new THREE.AnimationMixer(root);
  const action = mixer.clipAction(clip).setLoop(THREE.LoopRepeat, Infinity);
  action.play();

  const time = () => wrapTime(action.time, clip.duration);

  return {
    mixer,
    duration: clip.duration,
    advance: delta => { mixer.update(delta); return time(); },
    seek: target => {
      action.time = wrapTime(target, clip.duration);
      // A zero delta still runs the interpolants and writes the bindings, so
      // the pose lands even while nothing is advancing the clock.
      mixer.update(0);
      return time();
    },
    time,
    setSpeed: speed => { mixer.timeScale = speed; },
    dispose: () => {
      mixer.stopAllAction();
      // stopAllAction leaves the mixer's per-root binding cache populated, which
      // keeps the whole object graph reachable after the scene has let go of it.
      mixer.uncacheRoot(mixer.getRoot() as THREE.Object3D);
    },
  };
};
