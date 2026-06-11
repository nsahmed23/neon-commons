import { describe, expect, test } from 'vitest';
import { rngInt, rngShuffle, rngStep } from '../src/systems/board/BoardRng';
import { mulberry32 } from '../src/core/Rng';

describe('board rng (serializable cursor)', () => {
  test('rngStep matches core mulberry32 stream exactly', () => {
    const seed = 987654321;
    const core = mulberry32(seed);
    let state = seed >>> 0;
    for (let i = 0; i < 50; i++) {
      const r = rngStep(state);
      state = r.state;
      expect(r.value).toBe(core());
    }
  });

  test('dice are deterministic per seed and within 1..6', () => {
    const rollSeq = (seed: number, n: number): number[] => {
      let s = seed;
      const out: number[] = [];
      for (let i = 0; i < n; i++) {
        const r = rngInt(s, 1, 6);
        s = r.state;
        out.push(r.value);
      }
      return out;
    };
    const a = rollSeq(42, 200);
    const b = rollSeq(42, 200);
    expect(a).toEqual(b);
    expect(a.every((v) => v >= 1 && v <= 6)).toBe(true);
    expect(rollSeq(43, 200)).not.toEqual(a);
    // All six faces appear over 200 rolls (sanity, not statistics).
    expect(new Set(a).size).toBe(6);
  });

  test('resuming from a mid-stream cursor continues the identical stream', () => {
    let s = 7;
    const first: number[] = [];
    for (let i = 0; i < 10; i++) {
      const r = rngInt(s, 1, 6);
      s = r.state;
      first.push(r.value);
    }
    const savedCursor = s; // what a share code would store
    const tail: number[] = [];
    let s2 = savedCursor;
    for (let i = 0; i < 10; i++) {
      const r = rngInt(s2, 1, 6);
      s2 = r.value >= 0 ? r.state : s2;
      tail.push(r.value);
    }
    // Replaying 20 from the seed = first 10 + tail 10.
    let s3 = 7;
    const all: number[] = [];
    for (let i = 0; i < 20; i++) {
      const r = rngInt(s3, 1, 6);
      s3 = r.state;
      all.push(r.value);
    }
    expect(all).toEqual([...first, ...tail]);
  });

  test('shuffle is a permutation, deterministic per cursor, divergent across cursors', () => {
    const a = rngShuffle(123, 16);
    const b = rngShuffle(123, 16);
    const c = rngShuffle(124, 16);
    expect(a.order).toEqual(b.order);
    expect(a.state).toBe(b.state);
    expect([...a.order].sort((x, y) => x - y)).toEqual(
      Array.from({ length: 16 }, (_, i) => i),
    );
    expect(c.order).not.toEqual(a.order);
  });
});
