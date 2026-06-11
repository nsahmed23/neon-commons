import { describe, expect, test } from 'vitest';
import { generateWorld } from '../src/world/WorldGeneration';
import {
  CLEARANCE_RADIUS,
  RING_CLEARANCE,
  RING_COUNT,
  RingTracker,
  generateCourse,
  maxRoofNear,
  type Ring,
} from '../src/systems/flight/Rings';

const SEEDS = [1, 42, 124935158, 987654];

function ringsOnALine(n: number): Ring[] {
  const out: Ring[] = [];
  for (let i = 0; i < n; i++) out.push({ x: i * 50, y: 30, z: 0, r: 7 });
  return out;
}

describe('course generation', () => {
  test('deterministic: two generations from one seed are deeply equal', () => {
    for (const seed of SEEDS) {
      const world = generateWorld(seed);
      expect(generateCourse(seed, world)).toStrictEqual(generateCourse(seed, world));
    }
  });

  test('different seeds diverge', () => {
    const a = generateCourse(1, generateWorld(1));
    const b = generateCourse(2, generateWorld(2));
    expect(JSON.stringify(a)).not.toBe(JSON.stringify(b));
  });

  test(`exactly ${RING_COUNT} rings, all inside the world bounds`, () => {
    for (const seed of SEEDS) {
      const course = generateCourse(seed, generateWorld(seed));
      expect(course.rings.length).toBe(RING_COUNT);
      for (const r of course.rings) {
        expect(Math.abs(r.x)).toBeLessThan(320);
        expect(Math.abs(r.z)).toBeLessThan(320);
        expect(r.y).toBeGreaterThan(0);
        expect(r.y).toBeLessThan(150);
      }
    }
  });

  test('every ring clears the real skyline near its center', () => {
    for (const seed of SEEDS) {
      const world = generateWorld(seed);
      const course = generateCourse(seed, world);
      for (const r of course.rings) {
        const roof = maxRoofNear(world, r.x, r.z);
        // Ring center must sit at least the clearance above any roof
        // within CLEARANCE_RADIUS (the generator's own promise).
        expect(r.y).toBeGreaterThanOrEqual(Math.min(95, roof + RING_CLEARANCE) - 1e-9);
      }
    }
  });

  test('boss arena is over the lake (open water, beyond the city)', () => {
    const course = generateCourse(7, generateWorld(7));
    expect(course.bossArena.x).toBeGreaterThan(150); // lake spans x 150..300
    expect(Math.abs(course.bossArena.z)).toBeLessThan(100);
  });

  test('maxRoofNear sees a building only within the clearance radius', () => {
    const world = {
      buildings: [{ x: 0, z: 0, w: 10, d: 10, h: 40 }],
      tower: { x: 500, z: 500, w: 10, d: 10, h: 96 },
      spawn: { x: 0, z: 22 },
    };
    expect(maxRoofNear(world, 0, 0)).toBe(40);
    // footprint half-extent is 5, so the roof is "near" out to x = 29
    expect(maxRoofNear(world, CLEARANCE_RADIUS + 5, 0)).toBe(40);
    expect(maxRoofNear(world, CLEARANCE_RADIUS + 5 + 2, 0)).toBe(0);
  });
});

describe('ordered ring tracking', () => {
  test('rings advance only in order; entering ring 2 first does nothing', () => {
    const t = new RingTracker(ringsOnALine(4));
    expect(t.update(100, 30, 0)).toBe(false); // ring 2 while ring 0 is due
    expect(t.passed).toBe(0);
    expect(t.next).toBe(0);
    expect(t.missed).toBe(true);
    expect(t.update(0, 30, 0)).toBe(true); // ring 0 counts
    expect(t.passed).toBe(1);
    expect(t.missed).toBe(false);
  });

  test('sequential passes complete the course exactly once', () => {
    const rings = ringsOnALine(3);
    const t = new RingTracker(rings);
    for (let i = 0; i < 3; i++) {
      expect(t.update((rings[i] as Ring).x, 30, 0)).toBe(true);
    }
    expect(t.completed).toBe(true);
    expect(t.passed).toBe(3);
    expect(t.lastPassed).toBe(2);
    // Further updates are inert.
    expect(t.update(0, 30, 0)).toBe(false);
    expect(t.passed).toBe(3);
  });

  test('pass detection is sphere proximity: inside counts, outside does not', () => {
    const t = new RingTracker([{ x: 0, y: 30, z: 0, r: 7 }]);
    expect(t.update(0, 30 + 7.2, 0)).toBe(false); // 7.2 m above center: out
    expect(t.update(4, 30 + 4, 4)).toBe(true); // sqrt(48) ≈ 6.93 < 7: in
  });

  test('dirToNext fills the caller buffer with a unit vector + distance', () => {
    const t = new RingTracker(ringsOnALine(2));
    const out = { x: 0, y: 0, z: 0, dist: 0 };
    expect(t.dirToNext(-30, 30, 0, out)).toBe(true);
    expect(out.dist).toBeCloseTo(30, 6);
    expect(out.x).toBeCloseTo(1, 6);
    expect(out.y).toBeCloseTo(0, 6);
    t.update(0, 30, 0);
    t.update(50, 30, 0);
    expect(t.dirToNext(0, 0, 0, out)).toBe(false); // completed
  });

  test('distToNext is the 3D distance to the required ring', () => {
    const t = new RingTracker([{ x: 3, y: 4, z: 0, r: 7 }]);
    expect(t.distToNext(0, 0, 0)).toBeCloseTo(5, 6);
  });
});
