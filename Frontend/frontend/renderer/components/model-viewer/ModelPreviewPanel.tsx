import React, { useEffect, useRef } from 'react';
import * as THREE from 'three';

export interface ModelPreviewPanelProps {
  file: { path: string; name: string };
  onClose: () => void;
}

// Matches the content area background in home.tsx, so the canvas edges are
// invisible while the scene is empty.
const BACKGROUND = 0x0b0d12;

export const ModelPreviewPanel: React.FC<ModelPreviewPanelProps> = ({ file }) => {
  const hostRef = useRef<HTMLDivElement | null>(null);

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

    host.appendChild(renderer.domElement);

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
      renderer.render(scene, camera);
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
      grid.geometry.dispose();
      (Array.isArray(grid.material) ? grid.material : [grid.material]).forEach(m => m.dispose());
      scene.clear();
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [file.path]);

  return <div ref={hostRef} className="flex-1 min-h-0 w-full bg-[#0B0D12]" />;
};

export default ModelPreviewPanel;
