/**
 * The mixer glue behind the transport bar, driven headless.
 *
 * `AnimationMixer` needs no WebGL, so the whole seek/advance/speed contract is
 * measurable in jsdom — which is the point of it living outside the panel.
 * What is checked is the POSE, not the bookkeeping: a seek that moves
 * `action.time` but never writes the bound property looks correct in every
 * numeric assertion and shows the user a frozen model.
 */
import { describe, it, expect } from 'vitest'
import * as THREE from 'three'
import { createPlayback } from '../renderer/components/model-viewer/playback'
import { timeAtFraction } from '../renderer/components/model-viewer/timeline'

const DURATION = 2

/** A root that rises to y=10 at the midpoint and returns, so the pose is readable. */
const rig = () => {
  const root = new THREE.Object3D()
  root.name = 'Root'
  const track = new THREE.VectorKeyframeTrack(
    'Root.position',
    [0, 1, 2],
    [0, 0, 0, 0, 10, 0, 0, 0, 0],
  )
  return { root, clip: new THREE.AnimationClip('rise', DURATION, [track]) }
}

/**
 * A one-shot: rises and stays up, so the last pose is nothing like the first.
 * That difference is the point — the looping rig above cannot tell "seeked to
 * the end" apart from "wrapped back to the start".
 */
const oneShot = () => {
  const root = new THREE.Object3D()
  root.name = 'Root'
  const track = new THREE.VectorKeyframeTrack(
    'Root.position',
    [0, 1, 2],
    [0, 0, 0, 0, 5, 0, 0, 10, 0],
  )
  return { root, clip: new THREE.AnimationClip('jump', DURATION, [track]) }
}

describe('createPlayback', () => {
  it('reports the clip length it was handed', () => {
    const { root, clip } = rig()
    expect(createPlayback(root, clip).duration).toBe(DURATION)
  })

  it('poses the model at the sought time without any clock advancing', () => {
    const { root, clip } = rig()
    const playback = createPlayback(root, clip)

    expect(playback.seek(1)).toBeCloseTo(1, 6)
    expect(root.position.y).toBeCloseTo(10, 6)

    expect(playback.seek(0.5)).toBeCloseTo(0.5, 6)
    expect(root.position.y).toBeCloseTo(5, 6)
  })

  it('poses the LAST frame when the slider is dragged fully right', () => {
    const { root, clip } = oneShot()
    const playback = createPlayback(root, clip)
    playback.seek(timeAtFraction(1, DURATION))
    // 0 here would mean the user asking to see the finish got the opening pose.
    expect(root.position.y).toBeCloseTo(10, 6)
  })

  it('wraps a seek past the end onto the loop', () => {
    const { root, clip } = rig()
    const playback = createPlayback(root, clip)
    expect(playback.seek(DURATION)).toBe(0)
    expect(playback.seek(DURATION + 1)).toBeCloseTo(1, 6)
    expect(root.position.y).toBeCloseTo(10, 6)
  })

  it('advances by wall-clock seconds and reports where it landed', () => {
    const { root, clip } = rig()
    const playback = createPlayback(root, clip)
    expect(playback.advance(0.5)).toBeCloseTo(0.5, 6)
    expect(root.position.y).toBeCloseTo(5, 6)
    expect(playback.advance(0.5)).toBeCloseTo(1, 6)
    expect(root.position.y).toBeCloseTo(10, 6)
  })

  it('keeps looping past the end instead of running off the clip', () => {
    const { root, clip } = rig()
    const playback = createPlayback(root, clip)
    playback.advance(2.5)
    expect(playback.time()).toBeCloseTo(0.5, 6)
    expect(root.position.y).toBeCloseTo(5, 6)
  })

  it('covers half the clip in the same wall-clock second at half speed', () => {
    const { root, clip } = rig()
    const playback = createPlayback(root, clip)
    playback.setSpeed(0.5)
    expect(playback.advance(1)).toBeCloseTo(0.5, 6)
  })

  it('covers twice the clip in the same wall-clock second at double speed', () => {
    const { root, clip } = rig()
    const playback = createPlayback(root, clip)
    playback.setSpeed(2)
    expect(playback.advance(0.5)).toBeCloseTo(1, 6)
  })

  it('seeks to the same clip time whatever the speed is', () => {
    const { root, clip } = rig()
    const playback = createPlayback(root, clip)
    playback.setSpeed(2)
    // mixer.setTime() would multiply this by timeScale; the bar must not lie.
    expect(playback.seek(1)).toBeCloseTo(1, 6)
    expect(root.position.y).toBeCloseTo(10, 6)
  })

  it('lets go of the object graph on dispose', () => {
    const { root, clip } = rig()
    const playback = createPlayback(root, clip)
    playback.advance(0.5)
    playback.dispose()
    // A live binding cache would keep answering; an uncached root has none.
    expect(playback.mixer.existingAction(clip)).toBeNull()
  })
})
