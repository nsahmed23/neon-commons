/**
 * Shader-showcase overlay (DOM, editorial register): parameter sliders
 * that each drive a REAL uniform, quality + preset + seeded-randomize
 * controls, a live FPS readout, and the museum placard (HANDOVER 8.4:
 * plain-language paragraph + the actual formula + an honest
 * approximation note). Slider positions are synced back whenever
 * presets/randomize/wheel-zoom change the parameters.
 */

import type { Quality } from '../systems/Serialization';
import {
  PARAM_RANGES,
  PRESETS,
  type LensingParams,
} from '../systems/shader/ShaderParams';

export interface ShaderHudCallbacks {
  onParam: (key: keyof LensingParams, value: number) => void;
  onQuality: (q: Quality) => void;
  onPreset: (id: string) => void;
  onRandomize: () => void;
  onExitToHub: () => void;
}

interface SliderRow {
  input: HTMLInputElement;
  value: HTMLSpanElement;
  fmt: (v: number) => string;
}

const SLIDER_DEFS: ReadonlyArray<{
  key: keyof LensingParams;
  label: string;
  step: number;
  fmt: (v: number) => string;
}> = [
  { key: 'mass', label: 'Mass / lensing strength', step: 0.01, fmt: (v) => v.toFixed(2) },
  { key: 'diskBrightness', label: 'Disk brightness', step: 0.01, fmt: (v) => v.toFixed(2) },
  { key: 'diskThickness', label: 'Disk thickness', step: 0.01, fmt: (v) => `${v.toFixed(2)} rs` },
  { key: 'camDistance', label: 'Camera distance', step: 0.1, fmt: (v) => `${v.toFixed(1)} u` },
  { key: 'raySteps', label: 'Ray steps', step: 1, fmt: (v) => String(Math.round(v)) },
  { key: 'timeScale', label: 'Time speed', step: 0.01, fmt: (v) => `${v.toFixed(2)}x` },
];

export const PLACARD_TITLE = 'GRAVITY WELL — light, bent';

export const PLACARD_BODY =
  'A black hole bends passing light. Mass curves spacetime and light follows ' +
  'that curve, so rays that would have missed the hole are folded around it: ' +
  'the starfield behind it smears into arcs, a bright ring piles up where ' +
  'light can nearly orbit, and the far side of the glowing accretion disk ' +
  'reappears above and below the shadow, because its light loops over and ' +
  'under the hole on the way to you.';

export const PLACARD_FORMULA =
  "Each ray marches in steps of length Δs; every step bends its direction toward the mass with an inverse-square pull:\n" +
  'd′ = normalize(d − k·M·(p/|p|³)·Δs)\n' +
  'with capture inside r_s (= M in scene units) and extra glow where a ray’s closest approach grazes the photon sphere at 1.5·r_s.';

export const PLACARD_HONESTY =
  'What is approximated: this is a visual physics sketch, not a geodesic ' +
  'integrator. Real light follows null geodesics of the Schwarzschild metric; ' +
  'here each step applies a Newtonian-style inverse-square deflection (k tuned ' +
  'by eye), which reproduces the look — lensed arcs, shadow, photon ring — but ' +
  'not the exact deflection angles. The disk’s doppler asymmetry is a linear ' +
  'brightness bias, not relativistic beaming; the colors are an artistic ' +
  'temperature ramp T ∝ (r_in/r)^0.75, not blackbody spectra; and there is no ' +
  'gravitational redshift.';

export class ShaderHUD {
  private root: HTMLDivElement;
  private sliders = new Map<keyof LensingParams, SliderRow>();
  private qualityButtons = new Map<Quality, HTMLButtonElement>();
  private seedEl: HTMLDivElement;
  private fpsEl: HTMLDivElement;
  private lastFps = '';
  private syncing = false;

  constructor(parent: HTMLElement, private cb: ShaderHudCallbacks) {
    this.root = document.createElement('div');
    this.root.className = 'shader-hud';
    this.root.style.display = 'none';
    parent.appendChild(this.root);

    // Title + hint -----------------------------------------------------
    const title = div('shader-title');
    title.textContent = 'GRAVITY WELL';
    const hint = div('shader-hint');
    hint.textContent = 'Drag to orbit · Wheel to zoom · Esc hub';
    this.root.appendChild(title);
    this.root.appendChild(hint);

    // FPS readout (fed real frame-delta measurements) -------------------
    this.fpsEl = div('shader-fps');
    this.root.appendChild(this.fpsEl);

    // Control panel ------------------------------------------------------
    const panel = div('shader-controls shader-ui');
    const ph = document.createElement('h2');
    ph.textContent = 'PARAMETERS';
    panel.appendChild(ph);

    for (const def of SLIDER_DEFS) {
      const row = div('shader-row');
      const label = document.createElement('label');
      label.textContent = def.label;
      const value = document.createElement('span');
      value.className = 'shader-value';
      const input = document.createElement('input');
      input.type = 'range';
      const r = PARAM_RANGES[def.key];
      input.min = String(r.min);
      input.max = String(r.max);
      input.step = String(def.step);
      input.dataset['param'] = def.key;
      input.addEventListener('input', () => {
        if (this.syncing) return;
        const v = Number(input.value);
        value.textContent = def.fmt(v);
        this.cb.onParam(def.key, v);
      });
      label.appendChild(value);
      row.appendChild(label);
      row.appendChild(input);
      panel.appendChild(row);
      this.sliders.set(def.key, { input, value, fmt: def.fmt });
    }

    // Quality ------------------------------------------------------------
    const qh = document.createElement('h2');
    qh.textContent = 'QUALITY';
    panel.appendChild(qh);
    const qrow = div('shader-buttons');
    for (const q of ['high', 'medium', 'low'] as const) {
      const b = button(q, () => this.cb.onQuality(q));
      this.qualityButtons.set(q, b);
      qrow.appendChild(b);
    }
    panel.appendChild(qrow);

    // Presets + randomize --------------------------------------------------
    const sh = document.createElement('h2');
    sh.textContent = 'PRESETS';
    panel.appendChild(sh);
    const prow = div('shader-buttons shader-presets');
    for (const p of PRESETS) {
      prow.appendChild(button(p.name, () => this.cb.onPreset(p.id)));
    }
    prow.appendChild(button('Randomize', () => this.cb.onRandomize(), 'accent'));
    panel.appendChild(prow);
    this.seedEl = div('shader-seed');
    panel.appendChild(this.seedEl);

    panel.appendChild(button('Return to Hub', () => this.cb.onExitToHub(), 'danger'));
    this.root.appendChild(panel);

    // Placard (HANDOVER 8.4) ----------------------------------------------
    const placard = div('shader-placard shader-ui');
    const h = document.createElement('h2');
    h.textContent = PLACARD_TITLE;
    placard.appendChild(h);
    const body = document.createElement('p');
    body.textContent = PLACARD_BODY;
    placard.appendChild(body);
    const formula = document.createElement('pre');
    formula.className = 'shader-formula';
    formula.textContent = PLACARD_FORMULA;
    placard.appendChild(formula);
    const honesty = document.createElement('p');
    honesty.className = 'shader-honesty';
    honesty.textContent = PLACARD_HONESTY;
    placard.appendChild(honesty);
    this.root.appendChild(placard);
  }

  setVisible(v: boolean): void {
    this.root.style.display = v ? 'block' : 'none';
  }

  /** Sync sliders + value labels to params WITHOUT firing callbacks. */
  setParams(p: LensingParams): void {
    this.syncing = true;
    for (const def of SLIDER_DEFS) {
      const row = this.sliders.get(def.key);
      if (!row) continue;
      row.input.value = String(p[def.key]);
      row.value.textContent = row.fmt(p[def.key]);
    }
    this.syncing = false;
  }

  setQuality(q: Quality): void {
    for (const [key, b] of this.qualityButtons) {
      b.classList.toggle('active', key === q);
    }
  }

  setSeed(text: string): void {
    this.seedEl.textContent = text;
  }

  /** ~3 Hz from the mode's frame loop; change-gated. */
  setFps(text: string): void {
    if (text === this.lastFps) return;
    this.lastFps = text;
    this.fpsEl.textContent = text;
  }
}

function div(className: string): HTMLDivElement {
  const e = document.createElement('div');
  e.className = className;
  return e;
}

function button(label: string, onClick: () => void, extra = ''): HTMLButtonElement {
  const b = document.createElement('button');
  b.className = `menu-button shader-button${extra ? ` ${extra}` : ''}`;
  b.textContent = label;
  b.addEventListener('click', onClick);
  return b;
}
