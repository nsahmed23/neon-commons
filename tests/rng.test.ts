import { describe, expect, test } from 'vitest';
import { Rng, hashString, mulberry32 } from '../src/core/Rng';

describe('seeded RNG', () => {
  test('same seed yields identical sequence', () => {
    const a = new Rng(12345);
    const b = new Rng(12345);
    for (let i = 0; i < 200; i++) {
      expect(a.next()).toBe(b.next());
    }
  });

  test('different seeds diverge', () => {
    const a = new Rng(1);
    const b = new Rng(2);
    const seqA = Array.from({ length: 10 }, () => a.next());
    const seqB = Array.from({ length: 10 }, () => b.next());
    expect(seqA).not.toEqual(seqB);
  });

  test('next() stays in [0, 1)', () => {
    const r = new Rng(999);
    for (let i = 0; i < 1000; i++) {
      const v = r.next();
      expect(v).toBeGreaterThanOrEqual(0);
      expect(v).toBeLessThan(1);
    }
  });

  test('range() respects bounds', () => {
    const r = new Rng(42);
    for (let i = 0; i < 500; i++) {
      const v = r.range(-5, 7);
      expect(v).toBeGreaterThanOrEqual(-5);
      expect(v).toBeLessThan(7);
    }
  });

  test('int() is inclusive on both ends and hits them', () => {
    const r = new Rng(7);
    const seen = new Set<number>();
    for (let i = 0; i < 2000; i++) {
      const v = r.int(0, 3);
      expect(v).toBeGreaterThanOrEqual(0);
      expect(v).toBeLessThanOrEqual(3);
      seen.add(v);
    }
    expect(seen.size).toBe(4);
  });

  test('pick throws on empty array', () => {
    expect(() => new Rng(1).pick([])).toThrow();
  });

  test('fork() is deterministic and independent of parent draw order', () => {
    const a = new Rng(555);
    const b = new Rng(555);
    b.next(); // advance parent b before forking
    const fa = a.fork('trees');
    const fb = b.fork('trees');
    for (let i = 0; i < 50; i++) {
      expect(fa.next()).toBe(fb.next());
    }
  });

  test('forks with different labels differ', () => {
    const r = new Rng(555);
    expect(r.fork('trees').next()).not.toBe(r.fork('lamps').next());
  });

  test('hashString is stable', () => {
    expect(hashString('neon')).toBe(hashString('neon'));
    expect(hashString('neon')).not.toBe(hashString('noen'));
  });

  test('mulberry32 raw generator is reproducible', () => {
    const g1 = mulberry32(0xdeadbeef);
    const g2 = mulberry32(0xdeadbeef);
    expect([g1(), g1(), g1()]).toEqual([g2(), g2(), g2()]);
  });
});
