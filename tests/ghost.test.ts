import { describe, expect, test } from 'vitest';
import {
  GHOST_DECIMATE,
  GHOST_DT,
  GHOST_MAX_SAMPLES,
  GhostRecorder,
  deserializeGhost,
  sampleGhost,
  serializeGhost,
} from '../src/systems/race/Ghost';
import {
  createInput,
  createVehicle,
  stepVehicle,
} from '../src/systems/race/Vehicle';
import { SURFACE_TRACK } from '../src/systems/race/Track';

describe('ghost recording', () => {
  test('records every Nth fixed step (decimation)', () => {
    const r = new GhostRecorder();
    for (let i = 0; i < 60; i++) r.tick(i, -i, 0.1);
    expect(r.samples).toBe(Math.ceil(60 / GHOST_DECIMATE));
  });

  test('recording is bounded at GHOST_MAX_SAMPLES', () => {
    const r = new GhostRecorder();
    for (let i = 0; i < (GHOST_MAX_SAMPLES + 100) * GHOST_DECIMATE; i++) r.tick(1, 2, 3);
    expect(r.samples).toBe(GHOST_MAX_SAMPLES);
    expect(r.full).toBe(true);
  });

  test('reset starts a fresh recording', () => {
    const r = new GhostRecorder();
    for (let i = 0; i < 30; i++) r.tick(1, 1, 1);
    r.reset();
    expect(r.samples).toBe(0);
    r.tick(5, 6, 0.5);
    const g = r.finalize(1, 1000);
    expect(g.n).toBe(1);
    expect(g.x[0]).toBeCloseTo(5, 2);
  });

  test('sampleGhost interpolates between frames and ends cleanly', () => {
    const r = new GhostRecorder();
    // Two recorded frames: (0,0) then (3,6), heading 0 -> 0.2.
    r.tick(0, 0, 0);
    for (let i = 1; i < GHOST_DECIMATE; i++) r.tick(99, 99, 9); // skipped by decimation
    r.tick(3, 6, 0.2);
    const g = r.finalize(7, 500);
    expect(g.n).toBe(2);
    const out = { x: 0, z: 0, h: 0 };
    expect(sampleGhost(g, GHOST_DT / 2, out)).toBe(true);
    expect(out.x).toBeCloseTo(1.5, 2);
    expect(out.z).toBeCloseTo(3, 2);
    expect(out.h).toBeCloseTo(0.1, 3);
    // Past the end: clamps to the final frame and reports false.
    expect(sampleGhost(g, 99, out)).toBe(false);
    expect(out.x).toBeCloseTo(3, 2);
  });

  test('heading interpolation takes the short way around the wrap', () => {
    const r = new GhostRecorder();
    r.tick(0, 0, 3.1);
    for (let i = 1; i < GHOST_DECIMATE; i++) r.tick(0, 0, 0);
    r.tick(0, 0, -3.1);
    const g = r.finalize(7, 500);
    const out = { x: 0, z: 0, h: 0 };
    sampleGhost(g, GHOST_DT / 2, out);
    // midway between 3.1 and -3.1 the short way is near PI, not 0
    expect(Math.abs(out.h)).toBeGreaterThan(3.0);
  });
});

describe('ghost serialization round-trip', () => {
  /** Record a real deterministic drive so the data is representative. */
  function recordDrive(seed: number): ReturnType<GhostRecorder['finalize']> {
    const r = new GhostRecorder();
    const s = createVehicle(12.34, -56.78, 0.9);
    const input = createInput();
    for (let i = 0; i < 600; i++) {
      input.throttle = 1;
      input.steer = Math.sin(i / 40);
      stepVehicle(s, input, SURFACE_TRACK, 1 / 60);
      r.tick(s.x, s.z, s.heading);
    }
    return r.finalize(seed, 10_000);
  }

  test('encode -> decode -> encode is byte-identical (deterministic)', () => {
    const g = recordDrive(42);
    const raw1 = serializeGhost(g);
    const decoded = deserializeGhost(raw1, 42);
    expect(decoded).not.toBeNull();
    const raw2 = serializeGhost(decoded!);
    expect(raw2).toBe(raw1);
  });

  test('decode restores the exact recorded stream', () => {
    const g = recordDrive(7);
    const d = deserializeGhost(serializeGhost(g), 7)!;
    expect(d.n).toBe(g.n);
    expect(d.timeMs).toBe(g.timeMs);
    expect(Array.from(d.x)).toEqual(Array.from(g.x));
    expect(Array.from(d.z)).toEqual(Array.from(g.z));
    expect(Array.from(d.h)).toEqual(Array.from(g.h));
  });

  test('rejects malformed JSON, wrong version, wrong seed, bad arrays', () => {
    const g = recordDrive(1);
    const raw = serializeGhost(g);
    expect(deserializeGhost(null, 1)).toBeNull();
    expect(deserializeGhost('not json{', 1)).toBeNull();
    expect(deserializeGhost(raw, 2)).toBeNull(); // wrong seed: track mismatch
    const o = JSON.parse(raw) as Record<string, unknown>;
    expect(deserializeGhost(JSON.stringify({ ...o, v: 99 }), 1)).toBeNull();
    expect(deserializeGhost(JSON.stringify({ ...o, n: -1 }), 1)).toBeNull();
    expect(deserializeGhost(JSON.stringify({ ...o, x: [1, 2] }), 1)).toBeNull();
    expect(
      deserializeGhost(JSON.stringify({ ...o, n: GHOST_MAX_SAMPLES + 1 }), 1),
    ).toBeNull();
  });
});
