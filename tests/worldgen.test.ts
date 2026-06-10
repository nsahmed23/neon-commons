import { describe, expect, test } from 'vitest';
import { FUTURE_MODES, WORLD, generateWorld, terrainHeight } from '../src/world/WorldGeneration';

describe('world generation determinism', () => {
  test('same seed produces identical world data (deep equality)', () => {
    const a = generateWorld(20260610);
    const b = generateWorld(20260610);
    expect(a.buildings.length).toBe(b.buildings.length);
    expect(a).toEqual(b);
  });

  test('different seeds produce different layouts', () => {
    const a = generateWorld(1);
    const b = generateWorld(2);
    expect(a.buildings.map((x) => x.h)).not.toEqual(b.buildings.map((x) => x.h));
  });

  test('building count is bounded and non-trivial', () => {
    const w = generateWorld(7);
    // 24 buildable blocks * up to 4 lots, minus ~12% empty lots.
    expect(w.buildings.length).toBeGreaterThan(50);
    expect(w.buildings.length).toBeLessThanOrEqual(96);
  });

  test('all buildings sit inside the city square', () => {
    const w = generateWorld(99);
    for (const b of w.buildings) {
      expect(Math.abs(b.x) + b.w / 2).toBeLessThan(WORLD.cityHalf + 5);
      expect(Math.abs(b.z) + b.d / 2).toBeLessThan(WORLD.cityHalf + 5);
      expect(b.h).toBeGreaterThan(0);
    }
  });

  test('total window count exceeds 1000 (real count, summed per facade)', () => {
    for (const seed of [1, 42, 20260610]) {
      const w = generateWorld(seed);
      expect(w.totalWindows).toBeGreaterThan(1000);
      // Cross-check the sum against per-building counts.
      const sum = w.buildings.reduce((acc, b) => acc + b.windowCount, 0);
      expect(w.totalWindows).toBeGreaterThanOrEqual(sum); // + tower windows
    }
  });

  test('exactly five pedestals matching the future mode roster', () => {
    const w = generateWorld(5);
    expect(w.pedestals.map((p) => p.id)).toEqual(FUTURE_MODES.map((m) => m.id));
    expect(w.pedestals.map((p) => p.label)).toEqual([
      'Race', 'Battle', 'Board', 'Flight', 'Shader',
    ]);
  });

  test('trees avoid the city and the lake', () => {
    const w = generateWorld(123);
    expect(w.trees.length).toBeGreaterThan(100);
    const L = WORLD.lake;
    for (const t of w.trees) {
      expect(Math.max(Math.abs(t.x), Math.abs(t.z))).toBeGreaterThanOrEqual(WORLD.cityHalf + 10);
      const inLake = t.x > L.minX && t.x < L.maxX && t.z > L.minZ && t.z < L.maxZ;
      expect(inLake).toBe(false);
    }
  });

  test('spawn point is outside every building footprint', () => {
    const w = generateWorld(31337);
    for (const b of w.buildings) {
      const inside =
        Math.abs(w.spawn.x - b.x) < b.w / 2 && Math.abs(w.spawn.z - b.z) < b.d / 2;
      expect(inside).toBe(false);
    }
  });
});

describe('terrain height field', () => {
  test('deterministic for seed + position', () => {
    expect(terrainHeight(200, -150, 9)).toBe(terrainHeight(200, -150, 9));
    expect(terrainHeight(200, -150, 9)).not.toBe(terrainHeight(200, -150, 10));
  });

  test('flat inside the city', () => {
    expect(terrainHeight(0, 0, 77)).toBe(0);
    expect(terrainHeight(50, -50, 77)).toBe(0);
  });

  test('lake bed is below water level', () => {
    const L = WORLD.lake;
    const cx = (L.minX + L.maxX) / 2;
    const cz = (L.minZ + L.maxZ) / 2;
    expect(terrainHeight(cx, cz, 77)).toBeLessThan(WORLD.waterY);
  });
});
