import { describe, expect, test } from 'vitest';
import {
  LENSING,
  deflectStep,
  diskTemperature,
  diskWeight,
  dopplerBoost,
  photonRingGlow,
  schwarzschildRadius,
  tempToColor,
  type Vec3,
} from '../src/systems/shader/LensingMath';

const v = (x: number, y: number, z: number): Vec3 => ({ x, y, z });

/** |delta dir| produced by one small step at impact parameter r. */
function deflectionMag(r: number, mass: number, ds: number): number {
  const pos = v(r, 0, 0);
  const dir = v(0, 0, 1);
  const out = v(0, 0, 0);
  deflectStep(pos, dir, mass, ds, out);
  return Math.hypot(out.x - dir.x, out.y - dir.y, out.z - dir.z);
}

describe('deflection step (the lensing core)', () => {
  test('ray passing beside the mass bends TOWARD it', () => {
    // Ray at +x offset traveling along +z: the pull is in -x.
    const out = v(0, 0, 0);
    deflectStep(v(5, 0, 0), v(0, 0, 1), 1.2, 0.1, out);
    expect(out.x).toBeLessThan(0);
    expect(out.z).toBeGreaterThan(0.99);
  });

  test('deflection magnitude falls off as ~1/r^2', () => {
    const ds = 0.001; // small step: renormalization is near-identity
    const near = deflectionMag(4, 1, ds);
    const far = deflectionMag(8, 1, ds);
    expect(near).toBeGreaterThan(far);
    expect(near / far).toBeCloseTo(4, 2);
  });

  test('deflection scales linearly with mass', () => {
    const ds = 0.001;
    const m1 = deflectionMag(6, 0.5, ds);
    const m2 = deflectionMag(6, 1.0, ds);
    expect(m2 / m1).toBeCloseTo(2, 2);
  });

  test('output direction stays normalized', () => {
    const out = v(0, 0, 0);
    deflectStep(v(2.2, 1.1, -0.6), v(0.6, 0, 0.8), 2.5, 0.8, out);
    expect(Math.hypot(out.x, out.y, out.z)).toBeCloseTo(1, 9);
  });

  test('zero mass leaves the direction unchanged (straight-line limit)', () => {
    const dir = v(0.6, 0, 0.8);
    const out = v(0, 0, 0);
    deflectStep(v(3, 0, 0), dir, 0, 0.5, out);
    expect(out.x).toBeCloseTo(dir.x, 12);
    expect(out.y).toBeCloseTo(dir.y, 12);
    expect(out.z).toBeCloseTo(dir.z, 12);
  });

  test('deterministic: identical inputs produce identical outputs', () => {
    const a = v(0, 0, 0);
    const b = v(0, 0, 0);
    deflectStep(v(3.7, -1.2, 0.4), v(0.1, 0.2, 0.97), 1.7, 0.33, a);
    deflectStep(v(3.7, -1.2, 0.4), v(0.1, 0.2, 0.97), 1.7, 0.33, b);
    expect(a).toEqual(b);
  });

  test('a marched ray with offset curls around the mass (net bend accumulates)', () => {
    // March a ray past the hole and confirm the total bend exceeds any
    // single step: the lensing is an accumulated path effect.
    const pos = v(6, 0, -40);
    const dir = v(0, 0, 1);
    const out = v(0, 0, 0);
    const ds = 0.25;
    for (let i = 0; i < 400; i++) {
      deflectStep(pos, dir, 1.5, ds, out);
      dir.x = out.x;
      dir.y = out.y;
      dir.z = out.z;
      pos.x += dir.x * ds;
      pos.y += dir.y * ds;
      pos.z += dir.z * ds;
    }
    // Started parallel to z; should have gained a clearly negative x drift.
    expect(dir.x).toBeLessThan(-0.05);
    expect(pos.x).toBeLessThan(6);
  });
});

describe('disk temperature and color ramp', () => {
  const rs = schwarzschildRadius(1.2);

  test('temperature is monotonically non-increasing in radius', () => {
    let prev = Infinity;
    for (let r = LENSING.DISK_INNER * rs; r <= LENSING.DISK_OUTER * rs; r += 0.1) {
      const t = diskTemperature(r, rs);
      expect(t).toBeLessThanOrEqual(prev + 1e-12);
      prev = t;
    }
  });

  test('temperature is 1 at the inner edge and bounded in (0, 1]', () => {
    expect(diskTemperature(LENSING.DISK_INNER * rs, rs)).toBeCloseTo(1, 12);
    const far = diskTemperature(LENSING.DISK_OUTER * rs, rs);
    expect(far).toBeGreaterThan(0);
    expect(far).toBeLessThan(1);
  });

  test('every color channel is monotonically non-decreasing in temperature', () => {
    const c = { x: 0, y: 0, z: 0 };
    let pr = -1;
    let pg = -1;
    let pb = -1;
    for (let t = 0; t <= 1.0001; t += 0.05) {
      tempToColor(t, c);
      expect(c.x).toBeGreaterThanOrEqual(pr);
      expect(c.y).toBeGreaterThanOrEqual(pg);
      expect(c.z).toBeGreaterThanOrEqual(pb);
      pr = c.x;
      pg = c.y;
      pb = c.z;
    }
  });

  test('hotter is bluer: blue/red ratio rises with temperature', () => {
    const cool = { x: 0, y: 0, z: 0 };
    const hot = { x: 0, y: 0, z: 0 };
    tempToColor(0.15, cool);
    tempToColor(0.95, hot);
    expect(hot.z / hot.x).toBeGreaterThan(cool.z / cool.x);
  });
});

describe('disk weight (annulus + thickness)', () => {
  const rs = 1.0;

  test('zero well inside the inner edge and beyond the outer edge', () => {
    expect(diskWeight(LENSING.DISK_INNER * rs * 0.6, 0, rs, 0.2)).toBe(0);
    expect(diskWeight(LENSING.DISK_OUTER * rs * 1.05, 0, rs, 0.2)).toBe(0);
  });

  test('positive mid-annulus at the midplane, maximal at y = 0', () => {
    const mid = (LENSING.DISK_INNER + LENSING.DISK_OUTER) * 0.5 * rs;
    const w0 = diskWeight(mid, 0, rs, 0.2);
    expect(w0).toBeGreaterThan(0.5);
    expect(diskWeight(mid, 0.15, rs, 0.2)).toBeLessThan(w0);
    expect(diskWeight(mid, -0.15, rs, 0.2)).toBeLessThan(w0);
  });

  test('weight decreases monotonically with |y|', () => {
    const mid = (LENSING.DISK_INNER + LENSING.DISK_OUTER) * 0.5 * rs;
    let prev = Infinity;
    for (let y = 0; y <= 1; y += 0.1) {
      const w = diskWeight(mid, y, rs, 0.25);
      expect(w).toBeLessThanOrEqual(prev + 1e-12);
      prev = w;
    }
  });

  test('a thicker disk is brighter off the midplane (slider has a real effect)', () => {
    const mid = (LENSING.DISK_INNER + LENSING.DISK_OUTER) * 0.5 * rs;
    expect(diskWeight(mid, 0.3, rs, 0.5)).toBeGreaterThan(diskWeight(mid, 0.3, rs, 0.1));
  });
});

describe('doppler boost and photon ring', () => {
  test('doppler boost is 1 for transverse motion, monotonic, and bounded', () => {
    expect(dopplerBoost(0)).toBe(1);
    let prev = -Infinity;
    for (let c = -1; c <= 1.0001; c += 0.1) {
      const b = dopplerBoost(c);
      expect(b).toBeGreaterThanOrEqual(prev);
      expect(b).toBeGreaterThanOrEqual(0.05);
      expect(b).toBeLessThanOrEqual(2.5);
      prev = b;
    }
    expect(dopplerBoost(1)).toBeGreaterThan(dopplerBoost(-1));
  });

  test('photon-ring glow peaks at 1.5 rs and decays on both sides', () => {
    const rs = 1.4;
    const peak = photonRingGlow(LENSING.PHOTON_SPHERE * rs, rs);
    expect(peak).toBeCloseTo(1, 12);
    expect(photonRingGlow(LENSING.PHOTON_SPHERE * rs - 0.5 * rs, rs)).toBeLessThan(peak);
    expect(photonRingGlow(LENSING.PHOTON_SPHERE * rs + 0.5 * rs, rs)).toBeLessThan(peak);
    // Monotone decay moving outward from the peak.
    let prev = peak;
    for (let d = 0.1; d <= 2; d += 0.1) {
      const g = photonRingGlow((LENSING.PHOTON_SPHERE + d) * rs, rs);
      expect(g).toBeLessThan(prev);
      prev = g;
    }
  });

  test('schwarzschildRadius scales linearly with mass', () => {
    expect(schwarzschildRadius(2)).toBeCloseTo(2 * schwarzschildRadius(1), 12);
  });
});
