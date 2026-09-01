import React, { useCallback, useEffect, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import * as THREE from 'three';
// The `.js` suffix is required by three's exports map under this tsconfig.
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { Loader2 } from 'lucide-react';
import { useLang, type TKey } from '../../lib/i18n';
import { extensionOf, routeForFile } from './extensions';
import {
  boneBounds,
  disposeObject,
  hasDrawableSkeleton,
  ModelParseError,
  parseModel,
  playableClip,
  type ParsedModel,
} from './loaders';
import { buildMannequin, type MannequinHandle } from './mannequin';
import { createPlayback, type Playback } from './playback';
import { PlaybackControls } from './PlaybackControls';
import { DEFAULT_SPEED, timeAtFraction, type Speed } from './timeline';

/**
 * No `onClose`: the panel has no close affordance of its own. Closing a preview
 * is the content tab's job (`home.tsx`, the X beside the file name), and it
 * always was — the prop was required, handed a real callback, and never read,
 * so the contract promised a control the panel does not have.
 */
export interface ModelPreviewPanelProps {
  file: { path: string; name: string };
  workspacePath: string | null;
}

// Matches the content area background in home.tsx, so the canvas edges are
// invisible while the scene is empty.
const BACKGROUND = 0x0b0d12;

// Fraction of the viewport the framed model should occupy. Below 1 the bounding
// sphere touches the frustum edge; the margin keeps the silhouette off the rim.
const FRAME_FILL = 0.72;

// Slider refresh interval, ms. The mixer advances every frame either way; this
// only caps how often the thumb's React state is rewritten, and a few hundred
// pixels of track cannot show more than this.
const TIMELINE_TICK_MS = 50;

/**
 * The orbit rig as this file uses it. Structural rather than `OrbitControls`
 * on purpose: the concrete class needs a canvas, and a canvas is what jsdom
 * cannot give, so naming only the members that are touched is what lets the
 * mount path be exercised at all.
 */
export interface OrbitRig {
  enableDamping: boolean;
  target: THREE.Vector3;
  minDistance: number;
  maxDistance: number;
  update: () => boolean;
}

/** The slice of the stage that mounting one parsed file writes to. */
export interface MountTarget {
  camera: THREE.PerspectiveCamera;
  controls: OrbitRig;
  /** Everything a single file contributes hangs here and nowhere else. */
  content: THREE.Group;
  grid: THREE.GridHelper;
  render: () => void;
  playback: Playback | null;
  /** Mirrors the play/pause state where the rAF loop can read it un-staled. */
  playing: boolean;
  /** Start the rAF loop if it is not already running. */
  wake: () => void;
  /**
   * The volumes drawn for a file that has bones and no geometry, or null when
   * the file needed none. Held here because they hang off the MODEL's bones
   * rather than off `content`, so removing `content`'s children does not reach
   * them — the handle is the only route to freeing them.
   */
  mannequin: MannequinHandle | null;
}

/** The slice of the stage that returning to "no file loaded" reads. */
export interface ClearTarget extends MountTarget {
  /** rAF handle of the running loop; null when it is parked. */
  frame: number | null;
}

interface Stage extends ClearTarget {
  renderer: THREE.WebGLRenderer;
  scene: THREE.Scene;
  controls: OrbitControls;
}

/**
 * Channel refusals the user can act on. `denied` is deliberately absent: it is
 * the containment gate refusing a path outside the workspace, and naming the
 * boundary a probe just hit tells the probe where the boundary is. Anything
 * unlisted — including a code added to the gate later — falls to the generic
 * wording rather than to a blank panel.
 */
const CHANNEL_ERROR_KEYS: Record<string, TKey> = {
  'too-large': 'preview.tooLarge',
  unsupported: 'preview.unsupportedFormat',
};

/**
 * Why the viewport cannot draw, as a fact about the MACHINE rather than about
 * the file. Kept separate from `errorKey` because the load effect resets that
 * on every file change, and a GPU that cannot draw outlives any one file.
 *
 * `lost` and `gone` are the same event seen at two ages: a driver reset that
 * comes back within the grace window, versus one that does not. They are worth
 * distinguishing because only the second one has an action the user can take.
 */
type ViewportFault = 'unavailable' | 'lost' | 'gone';

const VIEWPORT_FAULT_KEYS: Record<ViewportFault, TKey> = {
  unavailable: 'preview.noWebgl',
  lost: 'preview.contextLost',
  gone: 'preview.contextGone',
};

/**
 * How long a lost context is described as coming back before the panel gives
 * up on it. A driver reset restores in well under a second when it restores at
 * all, so this is generous rather than tuned.
 */
export const CONTEXT_RESTORE_GRACE_MS = 8000;

interface Framing {
  center: THREE.Vector3;
  /** Camera-to-centre distance the framing chose; the zoom limits derive from it. */
  distance: number;
}

/**
 * Point the camera at `box` from its standing angle, far enough to see all
 * of it, and put the grid under its feet at a matching scale. Both are needed
 * together: FBX is routinely authored in centimetres, so a character arrives
 * ~170 units tall and a fixed 10-unit grid would be a speck beneath it.
 */
const frameObject = (
  camera: THREE.PerspectiveCamera,
  grid: THREE.GridHelper,
  // Handed in rather than measured here: the load path already needs the box to
  // decide whether the file has anything in it, and walking a rigged mesh's
  // vertices twice per file is the kind of cost a folder of 200 models notices.
  box: THREE.Box3,
): Framing => {
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  const radius = Math.max(size.length() / 2, 1e-4);

  const vFov = THREE.MathUtils.degToRad(camera.fov);
  const hFov = 2 * Math.atan(Math.tan(vFov / 2) * camera.aspect);
  // The narrower of the two fields is the one that clips, so it sets the distance.
  const distance = radius / Math.sin(Math.min(vFov, hFov) / 2) / FRAME_FILL;

  // FBX authored in centimetres yields radii in the hundreds; the default
  // 0.1/1000 clip planes would swallow the model whole. Both are derived.
  camera.near = Math.max(distance / 1000, 1e-4);
  camera.far = distance * 100;
  camera.position.copy(center).add(
    new THREE.Vector3(0.7, 0.45, 1).normalize().multiplyScalar(distance),
  );
  camera.lookAt(center);
  camera.updateProjectionMatrix();

  // The helper is built 10 units wide, so this puts roughly two model-widths of
  // floor around it whatever the file's unit is.
  grid.scale.setScalar(Math.max(size.x, size.z, radius) / 5);
  grid.position.set(center.x, box.min.y, center.z);

  return { center, distance };
};

/**
 * Re-aim the orbit rig at a freshly framed model. Damping is switched off for
 * the one settling update on purpose: with it on, `update()` only *decays* the
 * pending rotation instead of dropping it, so the previous file's half-finished
 * drag would bleed into the new one's opening shot.
 */
const reseatControls = (controls: OrbitRig, framing: Framing): void => {
  controls.enableDamping = false;
  controls.target.copy(framing.center);
  controls.minDistance = framing.distance / 50;
  controls.maxDistance = framing.distance * 10;
  controls.update();
  controls.enableDamping = true;
};

/** Return the stage to "no file loaded": stop the clock, free the GPU side. */
export const clearContent = (stage: ClearTarget): void => {
  if (stage.frame !== null) { cancelAnimationFrame(stage.frame); stage.frame = null; }
  stage.playback?.dispose();
  stage.playback = null;
  stage.playing = false;
  // Before the traversal below, not after: the mannequin's meshes are children
  // of the model's own bones, so `disposeObject` would otherwise walk into them
  // and dispose geometries this handle also owns — a second dispose() on the
  // same buffers. The handle is the single owner; detaching them here is what
  // keeps the traversal from ever seeing them.
  stage.mannequin?.dispose();
  stage.mannequin = null;
  for (const child of [...stage.content.children]) {
    stage.content.remove(child);
    disposeObject(child);
  }
  stage.grid.scale.setScalar(1);
  stage.grid.position.set(0, 0, 0);
};

export interface ViewableBounds {
  /** What the camera and grid are sized against. */
  box: THREE.Box3;
  /** The file's shape is its rig alone, so the bones need drawing themselves. */
  skeleton: boolean;
}

/**
 * What there is to look at in a parsed file, or null when the answer is
 * nothing. Split from mounting because the panel must be able to reach the
 * "nothing visible" message with no stage to mount onto — under jsdom there
 * never is one, and that is where the message is pinned.
 *
 * @param box the object's drawable bounds, which the caller already measured.
 */
export const viewableBounds = (
  parsed: ParsedModel,
  box: THREE.Box3,
): ViewableBounds | null => {
  if (!box.isEmpty()) return { box, skeleton: false };
  const bones = boneBounds(parsed.object);
  // Bones alone are not enough: a volume is built per bone-to-bone segment
  // (see hasDrawableSkeleton), so a single bone or a flat rig with no such
  // pair would take this branch and render nothing — the exact blank panel the
  // empty-model message exists to avoid.
  return bones && hasDrawableSkeleton(parsed.object) ? { box: bones, skeleton: true } : null;
};

/**
 * Everything that happens once a file has parsed: hang it on the stage, frame
 * it, re-aim the orbit rig, and start the clip if the file has a playable one.
 * Split out of the load effect because that effect cannot get past
 * `new WebGLRenderer` under jsdom — which left the panel's entire success path
 * with no automated coverage. Returns the clip length (0 = nothing to play)
 * rather than writing React state: the caller owns the component, this owns
 * the scene.
 */
export const mountParsedModel = (
  stage: MountTarget,
  parsed: ParsedModel,
  bounds: ViewableBounds,
): number => {
  // Volumes only for the bones-without-geometry case: a file that brought its
  // own meshes is already its own silhouette, and capsules over it would be an
  // overlay nobody asked for.
  //
  // Freed and reassigned on BOTH branches. Overwriting is not freeing, and a
  // caller that mounts twice without clearing in between would otherwise drop
  // the previous handle's geometries on the floor — an unwritten precondition
  // on an exported seam. The panel does clear first, so this never fires in
  // production; it is what keeps the seam honest for everyone else.
  //
  // Built BEFORE the rig joins the scene so that the gate `bounds.skeleton`
  // was decided on and the graph this reads are the same shape: a root that is
  // itself a bone parented to a bone would lose that segment to the reparenting
  // below, leaving a true gate with no figure to show for it.
  //
  // Known limitation: each volume is baked once at build time from its bone's
  // offset and hangs off the PARENT bone, so ancestor rotation and root motion
  // carry it, but a clip that keys a bone's own TRANSLATION drags that joint
  // away from a capsule which stays put at its old length. Humanoid clips are
  // rotation plus hips translation, so this is rare in practice — and it is the
  // architecture the feature was specified with.
  stage.mannequin?.dispose();
  stage.mannequin = bounds.skeleton ? buildMannequin(parsed.object) : null;
  stage.content.add(parsed.object);
  reseatControls(stage.controls, frameObject(stage.camera, stage.grid, bounds.box));

  const clip = playableClip(parsed.clips);
  if (!clip) {
    // Nothing will animate, so the parked loop has to be told once.
    stage.render();
    return 0;
  }

  stage.playback = createPlayback(parsed.object, clip);
  stage.playback.setSpeed(DEFAULT_SPEED);
  stage.playing = true;
  stage.wake();
  return stage.playback.duration;
};

export const ModelPreviewPanel: React.FC<ModelPreviewPanelProps> = ({ file, workspacePath }) => {
  const { t } = useLang();
  const hostRef = useRef<HTMLDivElement | null>(null);
  const stageRef = useRef<Stage | null>(null);
  const [loading, setLoading] = useState(true);
  // null = nothing to say. Otherwise the i18n key of the message that replaces
  // the viewport; `errorDetail` is the parser's own one-liner underneath it,
  // which only a genuine parse failure has.
  const [errorKey, setErrorKey] = useState<TKey | null>(null);
  const [errorDetail, setErrorDetail] = useState<string | null>(null);
  const [viewportFault, setViewportFault] = useState<ViewportFault | null>(null);
  // 0 = the file has no playable clip, which is what hides the transport bar.
  const [duration, setDuration] = useState(0);
  const [time, setTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<Speed>(DEFAULT_SPEED);

  // Renderer lifetime is the PANEL's, not the file's: browsers cap live WebGL
  // contexts at ~16, and clicking through a model folder would burn one per
  // file if this effect keyed on the path.
  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true });
    } catch {
      // No WebGL context (jsdom, blocked GPU). The load path can still read and
      // parse the file and then find no stage to mount it on, so without this
      // the panel would clear its loading state onto an empty dark rectangle
      // that is indistinguishable from a load which never finished.
      setViewportFault('unavailable');
      return;
    }

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(BACKGROUND);

    const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 1000);
    camera.position.set(3, 2.5, 4);
    camera.lookAt(0, 0.5, 0);

    const grid = new THREE.GridHelper(10, 20, 0x2a2f3a, 0x1a1e26);
    scene.add(grid);
    scene.add(new THREE.HemisphereLight(0xbfd4ff, 0x20242c, 1.2));
    const key = new THREE.DirectionalLight(0xffffff, 1.4);
    key.position.set(4, 6, 3);
    scene.add(key);

    const content = new THREE.Group();
    scene.add(content);

    // A canvas is an inline element by default, so the line box reserves room
    // for descenders under it and the bottom 4-5px of the render gets clipped
    // by the parent's overflow-hidden.
    renderer.domElement.style.display = 'block';
    host.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;

    const stage: Stage = {
      renderer, scene, camera, controls, content, grid,
      render: () => renderer.render(scene, camera),
      playback: null,
      playing: false,
      frame: null,
      mannequin: null,
      wake: () => {},
    };
    stageRef.current = stage;

    // The loop is demand-driven rather than always-on: it runs while the clip
    // is playing or the damped camera is still settling, and parks itself the
    // frame after both stop. Idle cost is then zero — a still model with a
    // still camera schedules no callback at all, which is what Task 3's
    // render-on-resize path bought and this must not spend.
    const clock = new THREE.Clock();
    let lastEmit = 0;
    const tick = () => {
      const moved = controls.update();
      let running = false;
      const delta = clock.getDelta();
      if (stage.playback && stage.playing) {
        const at = stage.playback.advance(delta);
        running = true;
        const now = Date.now();
        if (now - lastEmit >= TIMELINE_TICK_MS) { lastEmit = now; setTime(at); }
      }
      if (moved || running) {
        stage.render();
        stage.frame = requestAnimationFrame(tick);
      } else {
        stage.frame = null;
      }
    };
    stage.wake = () => {
      if (stage.frame !== null) return;
      // Drop the gap the loop spent parked, or the clip would jump forward by
      // however long the user sat still.
      clock.getDelta();
      stage.frame = requestAnimationFrame(tick);
    };
    // Every OrbitControls gesture ends in a `change`, so this is what restarts
    // the loop for damping without polling for it.
    controls.addEventListener('change', stage.wake);

    const resize = () => {
      const w = host.clientWidth || 1;
      const h = host.clientHeight || 1;
      // Re-read on every resize rather than once at mount: dragging the window
      // to a display with different scaling changes the ratio while the CSS
      // size stays put, and a stale ratio renders at the wrong resolution.
      renderer.setPixelRatio(window.devicePixelRatio || 1);
      // setSize must be left to update the canvas style (updateStyle defaults
      // true). With updateStyle:false the canvas keeps its device-pixel
      // dimensions as its LAYOUT size, so at any ratio above 1 — Retina,
      // Windows at 125% — it is drawn 25-100% too large and the parent's
      // overflow-hidden clips it.
      renderer.setSize(w, h);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      // A parked loop means nothing else would repaint the new viewport.
      stage.render();
    };
    resize();

    // three reinstalls its GL state on `webglcontextrestored`, but nothing
    // repaints: the rAF loop parks itself whenever the clip is paused and the
    // camera is still, so after a loss/restore the panel stays black until the
    // user happens to drag it. Resizing redraws at the current size.
    let restoreTimer: ReturnType<typeof setTimeout> | null = null;
    const stopRestoreTimer = () => {
      if (restoreTimer === null) return;
      clearTimeout(restoreTimer);
      restoreTimer = null;
    };

    const onContextLost = (event: Event) => {
      // Without preventDefault the browser does not even attempt a restore, so
      // this call is what makes the `lost` state a recoverable one rather than
      // a description of something already permanent.
      event.preventDefault();
      // flushSync, not a plain setState: this listener is outside React, so the
      // commit would otherwise be scheduled and land after the current task.
      // The canvas is ALREADY blank the instant the context goes — the driver
      // took it, not us — so a deferred commit leaves the user looking at an
      // unexplained black rectangle for however long the flush is postponed,
      // which is the whole failure this state exists to end. Committing here
      // makes the quiet "reconnecting" line part of the same task as the loss.
      flushSync(() => setViewportFault('lost'));
      stopRestoreTimer();
      restoreTimer = setTimeout(() => {
        restoreTimer = null;
        // Only escalate the loss this timer was started for: a restore, or a
        // second loss, has already written whatever is true now.
        setViewportFault(current => (current === 'lost' ? 'gone' : current));
      }, CONTEXT_RESTORE_GRACE_MS);
    };

    const onContextRestored = () => {
      stopRestoreTimer();
      // Clears `gone` as well as `lost`: a context that comes back late is
      // still back, and the panel would otherwise keep telling the user to
      // reopen a preview that already works. Flushed for the same reason the
      // loss is: the viewport draws again from this moment, and a message that
      // outlives the condition it describes is its own defect.
      flushSync(() => setViewportFault(null));
      resize();
    };
    renderer.domElement.addEventListener('webglcontextlost', onContextLost);
    renderer.domElement.addEventListener('webglcontextrestored', onContextRestored);

    // ResizeObserver, not a window listener: the panel also changes width when
    // the sidebar or chat pane toggles, which fires no window resize.
    const observer = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(resize) : null;
    observer?.observe(host);

    // A pixel-ratio change on its own moves no element, so the observer never
    // fires; this query is what notices a move between differently scaled
    // monitors. It matches only the ratio in force at setup, so it has to be
    // rebuilt after each change.
    let dprQuery: MediaQueryList | null = null;
    const onRatioChange = () => { resize(); watchRatio(); };
    const watchRatio = () => {
      if (typeof window.matchMedia !== 'function') return;
      dprQuery?.removeEventListener('change', onRatioChange);
      dprQuery = window.matchMedia(`(resolution: ${window.devicePixelRatio || 1}dppx)`);
      dprQuery.addEventListener('change', onRatioChange);
    };
    watchRatio();

    return () => {
      observer?.disconnect();
      dprQuery?.removeEventListener('change', onRatioChange);
      stopRestoreTimer();
      renderer.domElement.removeEventListener('webglcontextlost', onContextLost);
      renderer.domElement.removeEventListener('webglcontextrestored', onContextRestored);
      controls.removeEventListener('change', stage.wake);
      clearContent(stage);
      controls.dispose();
      grid.geometry.dispose();
      (Array.isArray(grid.material) ? grid.material : [grid.material]).forEach(m => m.dispose());
      scene.clear();
      // `dispose()` frees three's own caches and NOT the GL context (three
      // 0.185.1, WebGLRenderer.js:1074-1097): only the WEBGL_lose_context
      // extension releases it. This panel unmounts on every preview close and
      // on every switch back to a text file, so without the explicit loss the
      // contexts pile up against the browser's ~16 cap and older viewers get
      // killed off. It has to precede dispose(), which tears down the state
      // the extension lookup needs.
      renderer.forceContextLoss();
      renderer.dispose();
      renderer.domElement.remove();
      stageRef.current = null;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setErrorKey(null);
    setErrorDetail(null);
    setDuration(0);
    setTime(0);
    setPlaying(false);
    setSpeed(DEFAULT_SPEED);

    const fail = (key: TKey, detail: string | null = null) => {
      if (cancelled) return;
      setErrorKey(key);
      setErrorDetail(detail);
      setLoading(false);
    };

    const teardown = () => {
      cancelled = true;
      const stage = stageRef.current;
      if (!stage) return;
      clearContent(stage);
      stage.render();
    };

    // .blend and .3ds reach this panel so the click has an answer, but there is
    // no loader for either. Explaining that here — before the channel — keeps
    // the main process from reading a file whose bytes nothing can use.
    if (routeForFile(file.name) === 'blocked-model') {
      fail('preview.blockedFormat');
      return teardown;
    }

    void (async () => {
      const ipc = (window as any).ipc;
      const result = ipc ? await ipc.invoke('read-model-file', file.path, workspacePath) : null;
      if (cancelled) return;
      if (!result || result.error || !result.data) {
        // A null result is the handler having thrown, which says nothing the
        // user can act on: generic, same as a containment refusal.
        fail((result?.error && CHANNEL_ERROR_KEYS[result.error]) || 'preview.loadError');
        return;
      }

      // three's loaders parse synchronously, so nothing here can interrupt a
      // parse already under way; this only avoids STARTING one for a file the
      // user navigated away from while the channel read was in flight.
      if (cancelled) return;

      let parsed: ParsedModel;
      try {
        parsed = await parseModel(extensionOf(file.name), result.data);
      } catch (err) {
        if (err instanceof ModelParseError && err.code === 'external-resources') {
          fail('preview.gltfExternal');
          return;
        }
        // First line only: three's messages are single-line, but a stack-laden
        // Error from anywhere else would blow the panel's layout open.
        fail('preview.loadError', String(err instanceof Error ? err.message : err).split(/\r?\n/)[0]);
        return;
      }
      if (cancelled) { disposeObject(parsed.object); return; }

      // Nothing to draw and no rig either — a materials-only .dae, an .obj of
      // nothing but comments. Framing it is impossible, so without this the
      // panel is an empty dark rectangle that looks exactly like a load that
      // never finished.
      const bounds = viewableBounds(parsed, new THREE.Box3().setFromObject(parsed.object));
      if (!bounds) {
        disposeObject(parsed.object);
        fail('preview.emptyModel');
        return;
      }

      const stage = stageRef.current;
      if (!stage) { disposeObject(parsed.object); setLoading(false); return; }

      const clipDuration = mountParsedModel(stage, parsed, bounds);
      if (clipDuration > 0) {
        setDuration(clipDuration);
        setPlaying(true);
      }
      setLoading(false);
    })();

    return teardown;
  }, [file.path, file.name, workspacePath]);

  const togglePlay = useCallback(() => {
    const stage = stageRef.current;
    if (!stage?.playback) return;
    const next = !stage.playing;
    stage.playing = next;
    setPlaying(next);
    if (next) stage.wake();
    else setTime(stage.playback.time());
  }, []);

  const seek = useCallback((fraction: number) => {
    const stage = stageRef.current;
    if (!stage?.playback) return;
    const at = stage.playback.seek(timeAtFraction(fraction, stage.playback.duration));
    setTime(at);
    // While paused the loop is parked, so nothing else would draw the new pose.
    if (!stage.playing) stage.render();
  }, []);

  const changeSpeed = useCallback((next: Speed) => {
    setSpeed(next);
    stageRef.current?.playback?.setSpeed(next);
  }, []);

  return (
    <div className="flex-1 min-h-0 w-full relative bg-[#0B0D12]">
      <div ref={hostRef} className="absolute inset-0" />
      {loading && (
        <div className="absolute inset-0 flex items-center justify-center gap-2 text-[11px] font-semibold text-slate-400 pointer-events-none">
          <Loader2 size={14} className="animate-spin" />
          {t('preview.loading')}
        </div>
      )}
      {errorKey && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 px-8 text-center">
          <span className="text-[12px] font-semibold text-slate-300">{t(errorKey)}</span>
          {errorDetail && (
            <span className="text-[10px] font-mono text-slate-500 break-all max-w-full">{errorDetail}</span>
          )}
        </div>
      )}
      {/*
        Behind both of the above: what is wrong with the file is more specific
        than what is wrong with the GPU, and a still-running read has not yet
        earned either verdict.
      */}
      {viewportFault && !errorKey && !loading && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 px-8 text-center">
          <span className="text-[12px] font-semibold text-slate-300">{t(VIEWPORT_FAULT_KEYS[viewportFault])}</span>
        </div>
      )}
      {duration > 0 && !errorKey && (
        <PlaybackControls
          duration={duration}
          time={time}
          playing={playing}
          speed={speed}
          onTogglePlay={togglePlay}
          onSeek={seek}
          onSpeedChange={changeSpeed}
        />
      )}
    </div>
  );
};

export default ModelPreviewPanel;
