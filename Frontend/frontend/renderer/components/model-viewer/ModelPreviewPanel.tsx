import React, { useCallback, useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
// The `.js` suffix is required by three's exports map under this tsconfig.
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { Loader2 } from 'lucide-react';
import { useLang, type TKey } from '../../lib/i18n';
import { extensionOf, routeForFile } from './extensions';
import {
  disposeObject,
  ModelParseError,
  parseModel,
  playableClip,
  type ParsedModel,
} from './loaders';
import { createPlayback, type Playback } from './playback';
import { PlaybackControls } from './PlaybackControls';
import { DEFAULT_SPEED, timeAtFraction, type Speed } from './timeline';

export interface ModelPreviewPanelProps {
  file: { path: string; name: string };
  workspacePath: string | null;
  onClose: () => void;
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

interface Stage {
  renderer: THREE.WebGLRenderer;
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  controls: OrbitControls;
  /** Everything a single file contributes hangs here and nowhere else. */
  content: THREE.Group;
  grid: THREE.GridHelper;
  render: () => void;
  playback: Playback | null;
  /** Mirrors the play/pause state where the rAF loop can read it un-staled. */
  playing: boolean;
  frame: number | null;
  /** Start the rAF loop if it is not already running. */
  wake: () => void;
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
const reseatControls = (controls: OrbitControls, framing: Framing): void => {
  controls.enableDamping = false;
  controls.target.copy(framing.center);
  controls.minDistance = framing.distance / 50;
  controls.maxDistance = framing.distance * 10;
  controls.update();
  controls.enableDamping = true;
};

/** Return the stage to "no file loaded": stop the clock, free the GPU side. */
const clearContent = (stage: Stage): void => {
  if (stage.frame !== null) { cancelAnimationFrame(stage.frame); stage.frame = null; }
  stage.playback?.dispose();
  stage.playback = null;
  stage.playing = false;
  for (const child of [...stage.content.children]) {
    stage.content.remove(child);
    disposeObject(child);
  }
  stage.grid.scale.setScalar(1);
  stage.grid.position.set(0, 0, 0);
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
      // No WebGL context (jsdom, blocked GPU): the panel stays an empty dark
      // area rather than taking the whole renderer down.
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
      controls.removeEventListener('change', stage.wake);
      clearContent(stage);
      controls.dispose();
      grid.geometry.dispose();
      (Array.isArray(grid.material) ? grid.material : [grid.material]).forEach(m => m.dispose());
      scene.clear();
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

      // An empty bounding box means the file parsed and carries no drawable
      // vertex — a materials-only .dae, an .obj of nothing but comments. Framing
      // it is impossible, so without this the panel is an empty dark rectangle
      // that looks exactly like a load that never finished.
      const box = new THREE.Box3().setFromObject(parsed.object);
      if (box.isEmpty()) {
        disposeObject(parsed.object);
        fail('preview.emptyModel');
        return;
      }

      const stage = stageRef.current;
      if (!stage) { disposeObject(parsed.object); setLoading(false); return; }

      stage.content.add(parsed.object);
      reseatControls(stage.controls, frameObject(stage.camera, stage.grid, box));

      const clip = playableClip(parsed.clips);
      if (clip) {
        stage.playback = createPlayback(parsed.object, clip);
        stage.playback.setSpeed(DEFAULT_SPEED);
        stage.playing = true;
        setDuration(stage.playback.duration);
        setPlaying(true);
        stage.wake();
      } else {
        stage.render();
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
