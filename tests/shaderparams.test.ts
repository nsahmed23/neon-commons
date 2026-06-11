import { describe, expect, test } from 'vitest';
import { Rng } from '../src/core/Rng';
import { LENSING } from '../src/systems/shader/LensingMath';
import {
  PARAM_RANGES,
  PRESETS,
  SHADER_QUALITY,
  clampParams,
  defaultParams,
  qualityToLensing,
  randomParams,
  type LensingParams,
} from '../src/systems/shader/ShaderParams';
import {
  MAX_RAY_STEPS,
  buildLensingFragmentShader,
  glslFloat,
} from '../src/systems/shader/ShaderSource';

const KEYS = Object.keys(PARAM_RANGES) as Array<keyof LensingParams>;

function expectInRange(p: LensingParams): void {
  for (const k of KEYS) {
    const r = PARAM_RANGES[k];
    expect(p[k], `${k} above min`).toBeGreaterThanOrEqual(r.min);
    expect(p[k], `${k} below max`).toBeLessThanOrEqual(r.max);
  }
}

describe('parameter schema', () => {
  test('default params are inside every range', () => {
    expectInRange(defaultParams());
  });

  test('clampParams clamps every field and rounds raySteps to an integer', () => {
    const wild: LensingParams = {
      mass: 99,
      diskBrightness: -5,
      diskThickness: 100,
      camDistance: 0,
      raySteps: 1000.7,
      timeScale: -1,
    };
    const c = clampParams(wild);
    expectInRange(c);
    expect(Number.isInteger(c.raySteps)).toBe(true);
    expect(c.mass).toBe(PARAM_RANGES.mass.max);
    expect(c.diskBrightness).toBe(PARAM_RANGES.diskBrightness.min);
    expect(c.camDistance).toBe(PARAM_RANGES.camDistance.min);
  });

  test('clampParams returns a new object (immutability)', () => {
    const p = defaultParams();
    const c = clampParams(p);
    expect(c).not.toBe(p);
    expect(c).toEqual(p); // defaults are already in range
  });
});

describe('presets', () => {
  test('there are 3-4 named presets with distinct ids and names', () => {
    expect(PRESETS.length).toBeGreaterThanOrEqual(3);
    expect(PRESETS.length).toBeLessThanOrEqual(4);
    expect(new Set(PRESETS.map((p) => p.id)).size).toBe(PRESETS.length);
    expect(new Set(PRESETS.map((p) => p.name)).size).toBe(PRESETS.length);
  });

  test('every preset is inside every parameter range', () => {
    for (const preset of PRESETS) expectInRange(preset.params);
  });

  test('presets are visually distinct (no two share all parameter values)', () => {
    for (let i = 0; i < PRESETS.length; i++) {
      for (let j = i + 1; j < PRESETS.length; j++) {
        expect(PRESETS[i]?.params).not.toEqual(PRESETS[j]?.params);
      }
    }
  });
});

describe('seeded randomization (core Rng)', () => {
  test('random params stay in range across many seeds', () => {
    for (let seed = 1; seed <= 200; seed++) {
      const p = randomParams(new Rng(seed));
      expectInRange(p);
      expect(Number.isInteger(p.raySteps)).toBe(true);
    }
  });

  test('same seed reproduces the identical parameter set', () => {
    expect(randomParams(new Rng(424242))).toEqual(randomParams(new Rng(424242)));
  });

  test('different seeds diverge', () => {
    expect(randomParams(new Rng(1))).not.toEqual(randomParams(new Rng(2)));
  });
});

describe('quality -> steps/resolution mapping', () => {
  test('every level is bounded: steps inside the slider range, scale in (0, 1]', () => {
    for (const q of ['high', 'medium', 'low'] as const) {
      const m = qualityToLensing(q);
      expect(m.raySteps).toBeGreaterThanOrEqual(PARAM_RANGES.raySteps.min);
      expect(m.raySteps).toBeLessThanOrEqual(PARAM_RANGES.raySteps.max);
      expect(m.resolutionScale).toBeGreaterThan(0);
      expect(m.resolutionScale).toBeLessThanOrEqual(1);
    }
  });

  test('mapping is monotone: high >= medium >= low on both axes', () => {
    expect(SHADER_QUALITY.high.raySteps).toBeGreaterThanOrEqual(SHADER_QUALITY.medium.raySteps);
    expect(SHADER_QUALITY.medium.raySteps).toBeGreaterThanOrEqual(SHADER_QUALITY.low.raySteps);
    expect(SHADER_QUALITY.high.resolutionScale).toBeGreaterThanOrEqual(
      SHADER_QUALITY.medium.resolutionScale,
    );
    expect(SHADER_QUALITY.medium.resolutionScale).toBeGreaterThanOrEqual(
      SHADER_QUALITY.low.resolutionScale,
    );
  });
});

describe('shader source shares the tested constants', () => {
  const src = buildLensingFragmentShader();

  test('every LENSING constant value is embedded verbatim in the GLSL', () => {
    const names: Record<keyof typeof LENSING, string> = {
      RS_PER_MASS: 'RS_PER_MASS',
      DEFLECT_K: 'DEFLECT_K',
      PHOTON_SPHERE: 'PHOTON_SPHERE',
      DISK_INNER: 'DISK_INNER',
      DISK_OUTER: 'DISK_OUTER',
      TEMP_EXPONENT: 'TEMP_EXPONENT',
      ESCAPE_RADIUS: 'ESCAPE_RADIUS',
      DOPPLER_STRENGTH: 'DOPPLER_STRENGTH',
      PHOTON_GLOW_WIDTH: 'PHOTON_GLOW_WIDTH',
    };
    for (const key of Object.keys(names) as Array<keyof typeof LENSING>) {
      expect(src).toContain(`const float ${names[key]} = ${glslFloat(LENSING[key])};`);
    }
  });

  test('the compile-time loop bound matches the raySteps slider maximum', () => {
    expect(MAX_RAY_STEPS).toBe(PARAM_RANGES.raySteps.max);
    expect(src).toContain(`const int MAX_RAY_STEPS = ${MAX_RAY_STEPS};`);
  });

  test('every exposed parameter has a real uniform declaration', () => {
    for (const u of [
      'uniform float uMass;',
      'uniform float uDiskBrightness;',
      'uniform float uDiskThickness;',
      'uniform float uCamDist;',
      'uniform float uCamYaw;',
      'uniform float uCamPitch;',
      'uniform int uSteps;',
      'uniform float uTime;',
      'uniform vec2 uResolution;',
    ]) {
      expect(src).toContain(u);
    }
  });

  test('the GLSL deflection line mirrors deflectStep', () => {
    expect(src).toContain('dir = normalize(dir - DEFLECT_K * uMass * pos / (r * r * r) * ds);');
  });

  test('glslFloat always emits a decimal point', () => {
    expect(glslFloat(1)).toBe('1.0');
    expect(glslFloat(0.75)).toBe('0.75');
    expect(glslFloat(42)).toBe('42.0');
  });
});
