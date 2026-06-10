/**
 * Owns the WebGLRenderer, Scene, and fog. Quality profile changes fog
 * range and pixel ratio here; day/night changes sky + fog colors.
 */

import * as THREE from 'three';

export const NIGHT_SKY = 0x0a0d1f;
export const NIGHT_FOG = 0x10142e;
export const DAY_SKY = 0x9fc4e8;
export const DAY_FOG = 0xb8cfe0;

export class SceneManager {
  readonly renderer: THREE.WebGLRenderer;
  readonly scene: THREE.Scene;
  readonly canvas: HTMLCanvasElement;
  private pixelRatioCap = 2;

  constructor(parent: HTMLElement) {
    this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
    this.renderer.shadowMap.type = THREE.PCFShadowMap;
    this.canvas = this.renderer.domElement;
    this.canvas.id = 'game-canvas';
    parent.appendChild(this.canvas);

    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(NIGHT_SKY);
    this.scene.fog = new THREE.Fog(NIGHT_FOG, 120, 700);

    window.addEventListener('resize', this.onResize);
    this.onResize();
  }

  get fog(): THREE.Fog {
    return this.scene.fog as THREE.Fog;
  }

  setFogRange(near: number, far: number): void {
    this.fog.near = near;
    this.fog.far = far;
  }

  setPixelRatioCap(cap: number): void {
    this.pixelRatioCap = cap;
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, cap));
  }

  setShadows(enabled: boolean): void {
    this.renderer.shadowMap.enabled = enabled;
    // Force material recompile so the toggle takes effect immediately.
    this.scene.traverse((o) => {
      const mesh = o as THREE.Mesh;
      if (mesh.isMesh) {
        const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
        for (const m of mats) m.needsUpdate = true;
      }
    });
  }

  setNight(night: boolean): void {
    (this.scene.background as THREE.Color).setHex(night ? NIGHT_SKY : DAY_SKY);
    this.fog.color.setHex(night ? NIGHT_FOG : DAY_FOG);
  }

  /** Render the hub scene by default; modes may supply their own scene. */
  render(camera: THREE.Camera, scene: THREE.Scene = this.scene): void {
    this.renderer.render(scene, camera);
  }

  get info(): THREE.WebGLInfo {
    return this.renderer.info;
  }

  private onResize = (): void => {
    this.renderer.setSize(window.innerWidth, window.innerHeight);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, this.pixelRatioCap));
  };
}
