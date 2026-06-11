/**
 * Exposed lensing parameters: schema, ranges, clamping, named presets,
 * seeded randomization, and the quality -> (ray steps, resolution
 * scale) mapping. Pure (no DOM/Three.js); every UI slider in the mode
 * drives one of these fields, and every field lands in a real uniform.
 */

import type { Rng } from '../../core/Rng';
import type { Quality } from '../Serialization';

export interface LensingParams {
  /** black-hole mass: rs (shadow radius) = RS_PER_MASS * mass, world units */
  mass: number;
  /** disk emission multiplier */
  diskBrightness: number;
  /** disk vertical half-thickness, in units of rs */
  diskThickness: number;
  /** camera orbit radius, world units */
  camDistance: number;
  /** raymarch steps per ray (integer) */
  raySteps: number;
  /** simulation-time multiplier for disk swirl / star twinkle */
  timeScale: number;
}

export interface ParamRange {
  min: number;
  max: number;
}

export const PARAM_RANGES: Record<keyof LensingParams, ParamRange> = {
  mass: { min: 0.4, max: 2.5 },
  diskBrightness: { min: 0, max: 3 },
  diskThickness: { min: 0.02, max: 0.6 },
  camDistance: { min: 7, max: 60 },
  raySteps: { min: 48, max: 256 },
  timeScale: { min: 0, max: 3 },
} as const;

const clamp = (v: number, r: ParamRange): number => Math.min(r.max, Math.max(r.min, v));

export function defaultParams(): LensingParams {
  return {
    mass: 1.2,
    diskBrightness: 1.2,
    diskThickness: 0.16,
    camDistance: 26,
    raySteps: 160,
    timeScale: 1,
  };
}

/** Clamp every field into range (raySteps to an integer); returns a NEW object. */
export function clampParams(p: LensingParams): LensingParams {
  return {
    mass: clamp(p.mass, PARAM_RANGES.mass),
    diskBrightness: clamp(p.diskBrightness, PARAM_RANGES.diskBrightness),
    diskThickness: clamp(p.diskThickness, PARAM_RANGES.diskThickness),
    camDistance: clamp(p.camDistance, PARAM_RANGES.camDistance),
    raySteps: Math.round(clamp(p.raySteps, PARAM_RANGES.raySteps)),
    timeScale: clamp(p.timeScale, PARAM_RANGES.timeScale),
  };
}

export interface LensingPreset {
  id: string;
  name: string;
  params: LensingParams;
}

export const PRESETS: readonly LensingPreset[] = [
  {
    id: 'quiet-giant',
    name: 'Quiet Giant',
    params: {
      mass: 2.1,
      diskBrightness: 0.6,
      diskThickness: 0.09,
      camDistance: 44,
      raySteps: 150,
      timeScale: 0.45,
    },
  },
  {
    id: 'feeding-frenzy',
    name: 'Feeding Frenzy',
    params: {
      mass: 1.0,
      diskBrightness: 2.6,
      diskThickness: 0.5,
      camDistance: 21,
      raySteps: 160,
      timeScale: 2.4,
    },
  },
  {
    id: 'photon-ring-study',
    name: 'Photon Ring Study',
    params: {
      mass: 1.3,
      diskBrightness: 0.35,
      diskThickness: 0.04,
      camDistance: 13,
      raySteps: 230,
      timeScale: 0.3,
    },
  },
] as const;

/**
 * Seeded randomization: every field drawn uniformly inside its range
 * from the provided core Rng (deterministic per seed; the mode shows
 * the seed next to the button).
 */
export function randomParams(rng: Rng): LensingParams {
  return clampParams({
    mass: rng.range(PARAM_RANGES.mass.min, PARAM_RANGES.mass.max),
    diskBrightness: rng.range(0.3, PARAM_RANGES.diskBrightness.max),
    diskThickness: rng.range(PARAM_RANGES.diskThickness.min, PARAM_RANGES.diskThickness.max),
    camDistance: rng.range(10, 50),
    raySteps: rng.int(90, 220),
    timeScale: rng.range(0.2, 2.6),
  });
}

export interface ShaderQualityProfile {
  /** baseline raymarch steps applied when quality changes */
  raySteps: number;
  /** multiplier on the renderer's effective pixel ratio, (0, 1] */
  resolutionScale: number;
}

/**
 * Quality mapping (PerformanceScaler convention: every level changes
 * real renderer state). Applied on enter and on 'quality:changed'.
 */
export const SHADER_QUALITY: Record<Quality, ShaderQualityProfile> = {
  high: { raySteps: 176, resolutionScale: 1 },
  medium: { raySteps: 120, resolutionScale: 0.75 },
  low: { raySteps: 72, resolutionScale: 0.55 },
} as const;

export function qualityToLensing(q: Quality): ShaderQualityProfile {
  return SHADER_QUALITY[q];
}
