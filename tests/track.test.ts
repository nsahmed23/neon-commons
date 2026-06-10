import { describe, expect, test } from 'vitest';
import {
  SURFACE_BOOST,
  SURFACE_OFFROAD,
  SURFACE_TRACK,
  TRACK,
  WALL_DIST,
  createQueryResult,
  generateTrack,
  queryTrack,
  ringDist,
} from '../src/systems/race/Track';

const SEEDS = [1, 42, 124935158, 987654321];

describe('track generation', () => {
  test('same seed generates the identical track', () => {
    const a = generateTrack(42);
    const b = generateTrack(42);
    expect(Array.from(a.xs)).toEqual(Array.from(b.xs));
    expect(Array.from(a.zs)).toEqual(Array.from(b.zs));
    expect(a.total).toBe(b.total);
    expect(a.gates).toEqual(b.gates);
    expect(a.pads).toEqual(b.pads);
  });

  test('different seeds diverge', () => {
    const a = generateTrack(1);
    const b = generateTrack(2);
    expect(Array.from(a.xs)).not.toEqual(Array.from(b.xs));
  });

  test('loop is closed and continuous (no segment longer than 2x average)', () => {
    for (const seed of SEEDS) {
      const t = generateTrack(seed);
      const avg = t.total / t.n;
      for (let i = 0; i < t.n; i++) {
        const j = (i + 1) % t.n;
        const seg = Math.hypot(
          (t.xs[j] as number) - (t.xs[i] as number),
          (t.zs[j] as number) - (t.zs[i] as number),
        );
        expect(seg).toBeLessThan(avg * 2);
        expect(seg).toBeGreaterThan(0);
      }
    }
  });

  test('ribbon never self-intersects: non-neighbor samples stay > 2x wall apart', () => {
    for (const seed of SEEDS) {
      const t = generateTrack(seed);
      for (let i = 0; i < t.n; i++) {
        for (let j = i + 1; j < t.n; j++) {
          if (ringDist(i, j, t.n) <= 24) continue; // skip the local stretch
          const d = Math.hypot(
            (t.xs[i] as number) - (t.xs[j] as number),
            (t.zs[i] as number) - (t.zs[j] as number),
          );
          expect(d).toBeGreaterThan(WALL_DIST * 2);
        }
      }
    }
  });

  test('gates are ordered, on the centerline, with gate 0 at sample 0', () => {
    const t = generateTrack(7);
    expect(t.gates.length).toBe(TRACK.checkpoints);
    expect(t.gates[0]?.sample).toBe(0);
    for (let g = 0; g < t.gates.length; g++) {
      const gate = t.gates[g];
      expect(gate?.order).toBe(g);
      expect(gate?.x).toBe(t.xs[gate?.sample ?? 0]);
    }
    // strictly increasing sample order around the loop
    for (let g = 1; g < t.gates.length; g++) {
      expect(t.gates[g]!.sample).toBeGreaterThan(t.gates[g - 1]!.sample);
    }
  });

  test('boost pads exist, sit clear of gates, and mark the mask', () => {
    const t = generateTrack(99);
    expect(t.pads.length).toBe(TRACK.boostPads);
    let marked = 0;
    for (let i = 0; i < t.n; i++) marked += t.boostMask[i] as number;
    expect(marked).toBe(TRACK.boostPads * TRACK.boostSpan);
    for (const p of t.pads) {
      for (const g of t.gates) {
        expect(ringDist(p.startSample, g.sample, t.n)).toBeGreaterThanOrEqual(8);
      }
    }
  });
});

describe('surface query', () => {
  test('centerline point is on-track with ~zero lateral offset', () => {
    const t = generateTrack(42);
    const q = createQueryResult();
    queryTrack(t, t.xs[40] as number, t.zs[40] as number, -1, q);
    expect(q.surface === SURFACE_TRACK || q.surface === SURFACE_BOOST).toBe(true);
    expect(Math.abs(q.lateral)).toBeLessThan(0.5);
    expect(q.seg).toBe(40);
  });

  test('point past the asphalt edge is off-road, lateral sign follows the side', () => {
    const t = generateTrack(42);
    const q = createQueryResult();
    const i = 64;
    // left normal of tangent = (-tz, tx)
    const nx = -(t.tz[i] as number);
    const nz = t.tx[i] as number;
    const off = t.halfWidth + 3;
    queryTrack(t, (t.xs[i] as number) + nx * off, (t.zs[i] as number) + nz * off, -1, q);
    expect(q.surface).toBe(SURFACE_OFFROAD);
    expect(q.lateral).toBeGreaterThan(t.halfWidth);
    queryTrack(t, (t.xs[i] as number) - nx * off, (t.zs[i] as number) - nz * off, -1, q);
    expect(q.surface).toBe(SURFACE_OFFROAD);
    expect(q.lateral).toBeLessThan(-t.halfWidth);
  });

  test('a boost pad sample queries as boost in the middle, track at the edge', () => {
    const t = generateTrack(42);
    const q = createQueryResult();
    const pad = t.pads[0]!;
    const i = pad.startSample;
    queryTrack(t, t.xs[i] as number, t.zs[i] as number, -1, q);
    expect(q.surface).toBe(SURFACE_BOOST);
    // same sample, but out near the asphalt edge: plain track
    const nx = -(t.tz[i] as number);
    const nz = t.tx[i] as number;
    const edge = (TRACK.boostHalfWidth + t.halfWidth) / 2 + 0.6;
    queryTrack(t, (t.xs[i] as number) + nx * edge, (t.zs[i] as number) + nz * edge, -1, q);
    expect(q.surface).toBe(SURFACE_TRACK);
  });

  test('progress increases monotonically along the lap', () => {
    const t = generateTrack(5);
    const q = createQueryResult();
    let prev = -1;
    for (let i = 0; i < t.n; i += 8) {
      queryTrack(t, t.xs[i] as number, t.zs[i] as number, i, q);
      if (i > 0) expect(q.progress).toBeGreaterThan(prev);
      prev = q.progress;
    }
    expect(prev).toBeLessThanOrEqual(1);
  });

  test('hinted query matches full-scan query', () => {
    const t = generateTrack(1234);
    const qa = createQueryResult();
    const qb = createQueryResult();
    const i = 100;
    const x = (t.xs[i] as number) + 2;
    const z = (t.zs[i] as number) - 1;
    queryTrack(t, x, z, -1, qa);
    queryTrack(t, x, z, i - 5, qb);
    expect(qb.seg).toBe(qa.seg);
    expect(qb.lateral).toBeCloseTo(qa.lateral, 5);
    expect(qb.progress).toBeCloseTo(qa.progress, 6);
  });

  test('tangent from the query is unit length and matches travel direction', () => {
    const t = generateTrack(77);
    const q = createQueryResult();
    queryTrack(t, t.xs[10] as number, t.zs[10] as number, -1, q);
    expect(Math.hypot(q.tangentX, q.tangentZ)).toBeCloseTo(1, 5);
    // should roughly agree with the precomputed sample tangent
    const dot = q.tangentX * (t.tx[10] as number) + q.tangentZ * (t.tz[10] as number);
    expect(dot).toBeGreaterThan(0.9);
  });
});
