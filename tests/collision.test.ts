import { describe, expect, test } from 'vitest';
import { CollisionWorld, makeAABB } from '../src/world/Collision';

function world(): CollisionWorld {
  const w = new CollisionWorld(16);
  // 10x10x10 box centered at origin (footprint -5..5).
  w.addBox(makeAABB('center', 0, 0, 10, 10, 0, 10));
  // Far box centered at (100, 100).
  w.addBox(makeAABB('far', 100, 100, 4, 4, 0, 6));
  return w;
}

describe('CollisionWorld AABB grid', () => {
  test('queryPoint hits inside, misses outside', () => {
    const w = world();
    expect(w.queryPoint(0, 1, 0)?.id).toBe('center');
    expect(w.queryPoint(4.9, 9.9, -4.9)?.id).toBe('center');
    expect(w.queryPoint(6, 1, 0)).toBeNull();
    expect(w.queryPoint(0, 11, 0)).toBeNull(); // above the box
    expect(w.queryPoint(100, 1, 100)?.id).toBe('far');
  });

  test('queryAABB returns overlapping boxes only', () => {
    const w = world();
    const hits = w.queryAABB(-2, -2, 2, 2);
    expect(hits.map((b) => b.id)).toEqual(['center']);
    const none = w.queryAABB(20, 20, 30, 30);
    expect(none.length).toBe(0);
    const both = w.queryAABB(-10, -10, 110, 110);
    expect(both.map((b) => b.id).sort()).toEqual(['center', 'far']);
  });

  test('queryAABB respects Y band', () => {
    const w = world();
    const above = w.queryAABB(-2, -2, 2, 2, 20, 30);
    expect(above.length).toBe(0);
    const within = w.queryAABB(-2, -2, 2, 2, 5, 8);
    expect(within.length).toBe(1);
  });

  test('box spanning multiple grid cells is found from every cell, once', () => {
    const w = new CollisionWorld(4); // small cells force multi-cell boxes
    w.addBox(makeAABB('wide', 0, 0, 20, 20, 0, 5));
    expect(w.queryPoint(9, 1, 9)?.id).toBe('wide');
    expect(w.queryPoint(-9, 1, -9)?.id).toBe('wide');
    const hits = w.queryAABB(-9, -9, 9, 9);
    expect(hits.length).toBe(1); // deduplicated
  });

  test('resolveCapsule pushes player out of a wall', () => {
    const w = world();
    // Player radius 0.5 standing just inside the +X face (x=5).
    const res = w.resolveCapsule(5.2, 0, 0, 0.5, 1.8);
    expect(res.collided).toBe(true);
    expect(res.hitIds).toContain('center');
    expect(res.x).toBeCloseTo(5.5, 5);
    expect(res.z).toBeCloseTo(0, 5);
  });

  test('resolveCapsule leaves free player untouched', () => {
    const w = world();
    const res = w.resolveCapsule(8, 0, 8, 0.5, 1.8);
    expect(res.collided).toBe(false);
    expect(res.x).toBe(8);
    expect(res.z).toBe(8);
  });

  test('resolveCapsule ignores boxes entirely above the capsule', () => {
    const w = new CollisionWorld(16);
    w.addBox(makeAABB('bridge', 0, 0, 10, 10, 5, 8)); // overhead slab
    const res = w.resolveCapsule(0, 0, 0, 0.5, 1.8);
    expect(res.collided).toBe(false);
  });

  test('resolveCapsule with center inside box pushes out shallowest face', () => {
    const w = world();
    const res = w.resolveCapsule(4.6, 0, 0, 0.5, 1.8);
    expect(res.collided).toBe(true);
    expect(res.x).toBeCloseTo(5.5, 5); // pushed out through +X face
  });

  test('corner contact resolves diagonally', () => {
    const w = world();
    const res = w.resolveCapsule(5.2, 0, 5.2, 0.5, 1.8);
    expect(res.collided).toBe(true);
    const dx = res.x - 5;
    const dz = res.z - 5;
    expect(Math.hypot(dx, dz)).toBeGreaterThanOrEqual(0.5 - 1e-6);
  });

  test('boxCount tracks additions', () => {
    const w = world();
    expect(w.boxCount).toBe(2);
  });
});
