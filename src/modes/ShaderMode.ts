/**
 * Shader mode: a full-screen raymarched black-hole gravitational
 * lensing showcase on a single quad. All the math the fragment shader
 * runs is mirrored (and unit-tested) in src/systems/shader/; the GLSL
 * is generated from the same constants, so the tests constrain the
 * shader (anti-faking clause). Every UI slider writes a real uniform.
 *
 * Time honesty: the uTime uniform advances on the fixed-step
 * simulation clock scaled by the time-speed slider, so P-pause freezes
 * the piece, and the motion-effects setting OFF freezes it permanently
 * (reduced-motion rule: one beautiful static frame). Quality changes
 * the baseline ray-step count AND the renderer's effective pixel
 * ratio (resolution scale), per the PerformanceScaler conventions.
 */

import * as THREE from 'three';
import type { GameBus } from '../core/EventBus';
import type { Input } from '../core/Input';
import { Rng } from '../core/Rng';
import type { AudioSystem } from '../systems/Audio';
import type { Quality } from '../systems/Serialization';
import {
  PARAM_RANGES,
  PRESETS,
  clampParams,
  defaultParams,
  qualityToLensing,
  randomParams,
  type LensingParams,
} from '../systems/shader/ShaderParams';
import {
  LENSING_VERTEX_SHADER,
  buildLensingFragmentShader,
} from '../systems/shader/ShaderSource';
import { ShaderHUD } from '../ui/ShaderHUD';
import type { Mode } from './Mode';

const DRAG_RATE = 0.005;
const PITCH_LIMIT = 1.45;
const WHEEL_ZOOM_RATE = 0.0012;
const FPS_REPORT_INTERVAL = 0.3;

export interface ShaderModeDeps {
  parent: HTMLElement;
  bus: GameBus;
  input: Input;
  audio: AudioSystem;
  seed: number;
  exitToHub: () => void;
  setLockWanted: (wanted: boolean) => void;
  /** motion-effects setting OFF freezes the time uniform */
  getMotionEffects: () => boolean;
  getQuality: () => Quality;
  /** routes to the same PerformanceScaler path as the settings menu / F2 */
  setQuality: (q: Quality) => void;
  /** scales the renderer's effective pixel ratio while this mode renders */
  setPixelRatioCap: (cap: number) => void;
  /** the active quality profile's own pixel-ratio cap (restored on exit) */
  getProfilePixelRatioCap: () => number;
}

export class ShaderMode implements Mode {
  readonly id = 'shader';
  readonly scene = new THREE.Scene();
  readonly camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);

  /** one full-screen quad */
  readonly entityCount = 1;

  private hud: ShaderHUD;
  private params: LensingParams = defaultParams();
  private active = false;
  private shaderTime = 0;
  private camYaw = 0.6;
  private camPitch = 0.22;
  private dragging = false;

  // Seeded randomize chain: deterministic from the world seed.
  private randomizer: Rng;

  // Local FPS readout (real frame-delta measurements).
  private fpsAccum = 0;
  private fpsFrames = 0;
  private fpsReportTimer = 0;
  private lastResolutionScale = 1;

  private uniforms = {
    uResolution: { value: new THREE.Vector2(innerWidth, innerHeight) },
    uTime: { value: 0 },
    uMass: { value: 1 },
    uDiskBrightness: { value: 1 },
    uDiskThickness: { value: 0.16 },
    uCamDist: { value: 26 },
    uCamYaw: { value: 0 },
    uCamPitch: { value: 0 },
    uSteps: { value: 160 },
  };

  constructor(private deps: ShaderModeDeps) {
    this.randomizer = new Rng(deps.seed).fork('shader-randomize');

    const material = new THREE.ShaderMaterial({
      vertexShader: LENSING_VERTEX_SHADER,
      fragmentShader: buildLensingFragmentShader(),
      uniforms: this.uniforms,
      depthWrite: false,
      depthTest: false,
    });
    const quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), material);
    quad.frustumCulled = false;
    this.scene.add(quad);

    this.hud = new ShaderHUD(deps.parent, {
      onParam: (key, value) => this.setParam(key, value),
      onQuality: (q) => this.deps.setQuality(q),
      onPreset: (id) => this.applyPreset(id),
      onRandomize: () => this.randomize(),
      onExitToHub: () => this.deps.exitToHub(),
    });

    window.addEventListener('resize', () => {
      this.uniforms.uResolution.value.set(innerWidth, innerHeight);
    });

    // Orbit drag + wheel zoom on the canvas (the HUD panels carry the
    // .shader-ui class and swallow their own pointer events).
    window.addEventListener('mousedown', (e) => {
      if (!this.active || e.button !== 0) return;
      if ((e.target as HTMLElement | null)?.closest?.('.shader-ui')) return;
      this.dragging = true;
    });
    window.addEventListener('mouseup', () => {
      this.dragging = false;
    });
    window.addEventListener('mousemove', (e) => {
      if (!this.active || !this.dragging) return;
      this.camYaw -= e.movementX * DRAG_RATE;
      this.camPitch = Math.max(
        -PITCH_LIMIT,
        Math.min(PITCH_LIMIT, this.camPitch + e.movementY * DRAG_RATE),
      );
    });
    window.addEventListener(
      'wheel',
      (e) => {
        if (!this.active) return;
        if ((e.target as HTMLElement | null)?.closest?.('.shader-ui')) return;
        const r = PARAM_RANGES.camDistance;
        const next = this.params.camDistance * (1 + e.deltaY * WHEEL_ZOOM_RATE);
        this.params = { ...this.params, camDistance: Math.min(r.max, Math.max(r.min, next)) };
        this.hud.setParams(this.params);
      },
      { passive: true },
    );

    this.deps.input.onEdge('escape', () => {
      if (this.active) this.deps.exitToHub();
    });

    // F2 / settings-menu quality changes re-map steps + resolution here.
    this.deps.bus.on('quality:changed', ({ quality }) => {
      if (this.active) this.applyQuality(quality, true);
    });
  }

  // ---- Mode lifecycle ----------------------------------------------------

  enter(): void {
    this.active = true;
    this.deps.setLockWanted(false);
    this.hud.setVisible(true);
    this.hud.setParams(this.params);
    this.hud.setSeed('');
    this.applyQuality(this.deps.getQuality(), false);
    this.deps.bus.emit('toast', {
      text: 'Gravity Well · drag to orbit, wheel to zoom · every slider drives a uniform',
      kind: 'info',
    });
  }

  exit(): void {
    this.active = false;
    this.dragging = false;
    this.hud.setVisible(false);
    // Hand the renderer's pixel ratio back to the quality profile.
    this.deps.setPixelRatioCap(this.deps.getProfilePixelRatioCap());
    this.deps.setLockWanted(true);
  }

  /**
   * Fixed-step: advance the time uniform on the SIMULATION clock so
   * pause freezes the piece; motion-effects OFF freezes it entirely.
   */
  update(dt: number): void {
    if (!this.active) return;
    if (this.deps.getMotionEffects()) {
      this.shaderTime += dt * this.params.timeScale;
    }
  }

  // ---- Parameters ----------------------------------------------------------

  private setParam(key: keyof LensingParams, value: number): void {
    this.params = clampParams({ ...this.params, [key]: value });
  }

  private applyPreset(id: string): void {
    const preset = PRESETS.find((p) => p.id === id);
    if (!preset) return;
    this.params = clampParams({ ...preset.params });
    this.hud.setParams(this.params);
    this.hud.setSeed(`preset · ${preset.name}`);
    this.deps.audio.blip(720, 0.05, 'triangle');
  }

  private randomize(): void {
    // Draw a fresh 32-bit seed from the deterministic chain, show it,
    // and derive every parameter from it via the core Rng.
    const seed = Math.floor(this.randomizer.next() * 0xffffffff) >>> 0;
    this.params = randomParams(new Rng(seed));
    this.hud.setParams(this.params);
    this.hud.setSeed(`seed ${seed}`);
    this.deps.audio.blip(880, 0.05, 'triangle');
  }

  private applyQuality(q: Quality, setSteps: boolean): void {
    const map = qualityToLensing(q);
    if (setSteps) {
      this.params = { ...this.params, raySteps: map.raySteps };
      this.hud.setParams(this.params);
    }
    this.lastResolutionScale = map.resolutionScale;
    const base = Math.min(window.devicePixelRatio, this.deps.getProfilePixelRatioCap());
    this.deps.setPixelRatioCap(base * map.resolutionScale);
    this.hud.setQuality(q);
  }

  // ---- Per-frame -------------------------------------------------------------

  frame(_elapsed: number, frameDt: number): void {
    const u = this.uniforms;
    u.uTime.value = this.shaderTime;
    u.uMass.value = this.params.mass;
    u.uDiskBrightness.value = this.params.diskBrightness;
    u.uDiskThickness.value = this.params.diskThickness;
    u.uCamDist.value = this.params.camDistance;
    u.uCamYaw.value = this.camYaw;
    u.uCamPitch.value = this.camPitch;
    u.uSteps.value = this.params.raySteps;

    // Real FPS readout from frame deltas.
    if (frameDt > 0) {
      this.fpsAccum += frameDt;
      this.fpsFrames++;
      this.fpsReportTimer += frameDt;
      if (this.fpsReportTimer >= FPS_REPORT_INTERVAL && this.fpsAccum > 0) {
        const fps = this.fpsFrames / this.fpsAccum;
        this.hud.setFps(
          `FPS ${fps.toFixed(0)} · ${this.params.raySteps} steps · res x${this.lastResolutionScale.toFixed(2)}`,
        );
        this.fpsReportTimer = 0;
        this.fpsAccum = 0;
        this.fpsFrames = 0;
      }
    }
  }

  // ---- Dev/audit handle (scripted browser sessions) ---------------------------

  /** Current uniform values, for scripted verification (read-only copies). */
  uniformSnapshot(): Record<string, number> {
    return {
      uTime: this.uniforms.uTime.value,
      uMass: this.uniforms.uMass.value,
      uDiskBrightness: this.uniforms.uDiskBrightness.value,
      uDiskThickness: this.uniforms.uDiskThickness.value,
      uCamDist: this.uniforms.uCamDist.value,
      uCamYaw: this.uniforms.uCamYaw.value,
      uCamPitch: this.uniforms.uCamPitch.value,
      uSteps: this.uniforms.uSteps.value,
    };
  }
}
