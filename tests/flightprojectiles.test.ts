import { describe, expect, test } from 'vitest';
import {
  PROJECTILE,
  collideProjectiles,
  createPool,
  killProjectile,
  segmentHitsSphere,
  spawnProjectile,
  stepProjectiles,
  type HitTarget,
} from '../src/systems/flight/Projectiles';

const DT = 1 / 60;

describe('projectile pool bounds', () => {
  test('pool refuses to grow past its hard maximum', () => {
    const p = createPool();
    for (let i = 0; i < PROJECTILE.max; i++) {
      expect(spawnProjectile(p, 0, 0, 0, 0, 1, 0, 0, 10)).toBeGreaterThanOrEqual(0);
    }
    expect(p.count).toBe(PROJECTILE.max);
    expect(spawnProjectile(p, 0, 0, 0, 0, 1, 0, 0, 10)).toBe(-1); // FULL: refused
    expect(p.count).toBe(PROJECTILE.max);
    expect(p.alive.length).toBe(PROJECTILE.max); // storage never grew
  });

  test('killing a slot frees it for reuse', () => {
    const p = createPool();
    const slot = spawnProjectile(p, 0, 1, 2, 3, 0, 0, 0, 10);
    expect(p.count).toBe(1);
    killProjectile(p, slot);
    expect(p.count).toBe(0);
    expect(p.alive[slot]).toBe(0);
    expect(spawnProjectile(p, 1, 9, 9, 9, 0, 0, 0, 8)).toBeGreaterThanOrEqual(0);
    expect(p.count).toBe(1);
  });

  test('bolts expire after their ttl and free their slots', () => {
    const p = createPool();
    spawnProjectile(p, 0, 0, 0, 0, 10, 0, 0, 10);
    const steps = Math.ceil(PROJECTILE.ttl / DT) + 1;
    for (let i = 0; i < steps; i++) stepProjectiles(p, DT);
    expect(p.count).toBe(0);
  });

  test('step integrates position from velocity', () => {
    const p = createPool();
    const slot = spawnProjectile(p, 0, 0, 0, 0, 60, 0, 0, 10);
    for (let i = 0; i < 30; i++) stepProjectiles(p, DT); // 0.5 s
    expect(p.x[slot]).toBeCloseTo(30, 4);
    expect(p.y[slot]).toBeCloseTo(0, 6);
  });
});

describe('swept segment-vs-sphere collision math', () => {
  test('direct pass through the sphere hits', () => {
    expect(segmentHitsSphere(-10, 0, 0, 10, 0, 0, 0, 0, 0, 2)).toBe(true);
  });

  test('segment passing wide of the sphere misses', () => {
    expect(segmentHitsSphere(-10, 5, 0, 10, 5, 0, 0, 0, 0, 2)).toBe(false);
  });

  test('grazing exactly at the radius counts (closed surface)', () => {
    expect(segmentHitsSphere(-10, 2, 0, 10, 2, 0, 0, 0, 0, 2)).toBe(true);
    expect(segmentHitsSphere(-10, 2.001, 0, 10, 2.001, 0, 0, 0, 0, 2)).toBe(false);
  });

  test('segment that STOPS before the sphere misses (no infinite ray)', () => {
    expect(segmentHitsSphere(-10, 0, 0, -5, 0, 0, 0, 0, 0, 2)).toBe(false);
  });

  test('fast bolt cannot tunnel: the step segment catches a sphere it crossed', () => {
    const p = createPool();
    // 95 m/s at 60 Hz ≈ 1.58 m per step; use a tiny 0.5 m target the
    // point positions would skip without the swept test.
    spawnProjectile(p, 0, 0, 0, 0, 95, 0, 0, 10);
    const target: HitTarget = { id: 7, x: 0.79, y: 0, z: 0, radius: 0.3, team: 1 };
    let hits = 0;
    for (let i = 0; i < 5; i++) {
      stepProjectiles(p, DT);
      collideProjectiles(p, [target], DT, (id) => {
        expect(id).toBe(7);
        hits++;
      });
    }
    expect(hits).toBe(1);
    expect(p.count).toBe(0); // the bolt died on impact
  });
});

describe('projectile vs target resolution', () => {
  test('a hit reports target id, damage and owner, and kills the bolt', () => {
    const p = createPool();
    spawnProjectile(p, 1, -2, 10, 0, 60, 0, 0, 8);
    const targets: HitTarget[] = [{ id: 3, x: 1, y: 10, z: 0, radius: 1.5, team: 0 }];
    const seen: Array<[number, number, number]> = [];
    for (let i = 0; i < 10; i++) {
      stepProjectiles(p, DT);
      collideProjectiles(p, targets, DT, (id, dmg, owner) => seen.push([id, dmg, owner]));
    }
    expect(seen).toStrictEqual([[3, 8, 1]]);
  });

  test('friendly fire is off: a bolt never hits its own team', () => {
    const p = createPool();
    spawnProjectile(p, 0, -2, 0, 0, 60, 0, 0, 10); // player bolt
    const playerTeamTarget: HitTarget = { id: 0, x: 1, y: 0, z: 0, radius: 2, team: 0 };
    let hits = 0;
    for (let i = 0; i < 10; i++) {
      stepProjectiles(p, DT);
      collideProjectiles(p, [playerTeamTarget], DT, () => hits++);
    }
    expect(hits).toBe(0);
    expect(p.count).toBe(1); // the bolt flew straight through, still live
  });
});
