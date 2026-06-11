/**
 * Full scripted flight run, headless: the SAME pure modules the mode
 * wires (FlightModel autopiloted by a deterministic controller, Rings,
 * DroneAI, Projectiles, Scoring) simulated end to end from one seed.
 * Proves the whole pipeline is deterministic and actually completes:
 * 10 ordered ring passes, sentry fights, escort adds, boss phases in
 * order, boss kill, and a final score derived only from the event log.
 *
 * The scripted pilot has deep hull plating (it does not dodge); this
 * harness tests determinism and systems integration, not balance.
 */

import { describe, expect, test } from 'vitest';
import { generateWorld } from '../src/world/WorldGeneration';
import {
  createDrone,
  createFlightInput,
  stepDrone,
} from '../src/systems/flight/FlightModel';
import { RingTracker, generateCourse } from '../src/systems/flight/Rings';
import {
  BOSS,
  createBoss,
  createEnemy,
  damageBoss,
  damageEnemy,
  stepBoss,
  stepEnemy,
  type EnemyDrone,
} from '../src/systems/flight/DroneAI';
import {
  PROJECTILE,
  collideProjectiles,
  createPool,
  spawnProjectile,
  stepProjectiles,
  type HitTarget,
} from '../src/systems/flight/Projectiles';
import {
  applyFlightEvent,
  createScore,
  totalScore,
  type FlightEvent,
} from '../src/systems/flight/Scoring';

const DT = 1 / 60;
const MAX_STEPS = 60 * 240; // 4 minutes of sim time, hard cap
const PLAYER_ID = 999;
const BOSS_ID = 500;

interface RunResult {
  log: string[];
  score: number;
  steps: number;
  bossDown: boolean;
  ringsPassed: number;
}

function angleDiff(target: number, current: number): number {
  let d = target - current;
  while (d > Math.PI) d -= Math.PI * 2;
  while (d < -Math.PI) d += Math.PI * 2;
  return d;
}

function simulateRun(seed: number): RunResult {
  const world = generateWorld(seed);
  const course = generateCourse(seed, world);
  const tracker = new RingTracker(course.rings);
  const player = createDrone(course.start.x, course.start.y, course.start.z, course.start.yaw);
  const input = createFlightInput();
  const pool = createPool();
  const score = createScore();
  const log: string[] = [];
  const events: FlightEvent[] = [];
  const emit = (ev: FlightEvent): void => {
    applyFlightEvent(score, ev);
    events.push(ev);
    log.push(JSON.stringify(ev));
  };

  // Sentries patrol anchors at rings 2/4/6/8; two escort adds at the arena.
  const enemies: EnemyDrone[] = [];
  for (let i = 0; i < 4; i++) {
    const ring = course.rings[2 + i * 2];
    if (!ring) throw new Error('course too short');
    enemies.push(createEnemy(i, ring.x, ring.y + 6, ring.z));
  }
  const arena = course.bossArena;
  const adds = [
    createEnemy(100, arena.x - 14, arena.y, arena.z - 14),
    createEnemy(101, arena.x + 14, arena.y, arena.z + 14),
  ];
  const boss = createBoss(arena.x, arena.y, arena.z);
  let playerHp = 1000; // scripted pilot: deep plating, see header note
  let fireTimer = 0;
  let bossDown = false;

  const targets: HitTarget[] = [];

  for (let step = 0; step < MAX_STEPS; step++) {
    const simTime = step * DT;

    // ---- scripted pilot ------------------------------------------------
    let aimAt: { x: number; y: number; z: number } | null = null;
    if (!tracker.completed) {
      const ring = course.rings[tracker.next];
      if (!ring) throw new Error('tracker overran the course');
      const yawTo = Math.atan2(ring.x - player.x, ring.z - player.z);
      const diff = angleDiff(yawTo, player.yaw);
      input.yaw = Math.max(-1, Math.min(1, diff * 3));
      input.thrust = Math.abs(diff) < 0.5 ? 1 : 0.25;
      input.lift = Math.max(-1, Math.min(1, (ring.y - player.y) * 0.25));
      input.strafe = 0;
      // Opportunity fire at any live sentry within 50 m.
      let bestD = 50;
      for (const e of enemies) {
        if (!e.alive) continue;
        const d = Math.hypot(e.x - player.x, e.y - player.y, e.z - player.z);
        if (d < bestD) {
          bestD = d;
          aimAt = e;
        }
      }
    } else if (!bossDown) {
      // Boss fight: hold ~38 m from the boss, orbit-strafe, focus adds first.
      let target: { x: number; y: number; z: number } = boss;
      for (const a of adds) {
        if (a.alive) {
          target = a;
          break;
        }
      }
      aimAt = target;
      const yawTo = Math.atan2(target.x - player.x, target.z - player.z);
      const diff = angleDiff(yawTo, player.yaw);
      input.yaw = Math.max(-1, Math.min(1, diff * 3));
      const dist = Math.hypot(target.x - player.x, target.z - player.z);
      input.thrust = dist > 42 ? 0.8 : dist < 30 ? -0.5 : 0;
      input.strafe = 0.8;
      input.lift = Math.max(-1, Math.min(1, (target.y - player.y) * 0.25));
    } else {
      input.thrust = 0;
      input.strafe = 0;
      input.lift = 0;
      input.yaw = 0;
    }
    stepDrone(player, input, DT);

    // ---- rings ----------------------------------------------------------
    if (tracker.update(player.x, player.y, player.z)) {
      emit({ kind: 'ring-pass', index: tracker.lastPassed, total: tracker.total });
      if (tracker.completed) emit({ kind: 'course-complete' });
    }

    // ---- player fire ------------------------------------------------------
    fireTimer -= DT;
    if (aimAt && fireTimer <= 0 && !bossDown) {
      fireTimer = 0.2;
      const dx = aimAt.x - player.x;
      const dy = aimAt.y - player.y;
      const dz = aimAt.z - player.z;
      const d = Math.max(1e-6, Math.hypot(dx, dy, dz));
      spawnProjectile(
        pool, 0, player.x, player.y, player.z,
        (dx / d) * PROJECTILE.playerSpeed, (dy / d) * PROJECTILE.playerSpeed,
        (dz / d) * PROJECTILE.playerSpeed, PROJECTILE.playerDamage,
      );
      emit({ kind: 'shot-fired', by: 'player' });
    }

    // ---- enemies ---------------------------------------------------------
    for (const e of enemies) {
      stepEnemy(e, player.x, player.y, player.z, simTime, DT);
      if (e.transitioned) emit({ kind: 'drone-state', droneId: e.id, to: e.transitioned });
      if (e.fired) {
        fireAt(pool, e, player);
        emit({ kind: 'shot-fired', by: 'enemy' });
      }
    }
    const courseDone = tracker.completed;
    let addsAlive = 0;
    for (const a of adds) {
      if (courseDone) {
        stepEnemy(a, player.x, player.y, player.z, simTime, DT);
        if (a.transitioned) emit({ kind: 'drone-state', droneId: a.id, to: a.transitioned });
        if (a.fired) {
          fireAt(pool, a, player);
          emit({ kind: 'shot-fired', by: 'enemy' });
        }
      }
      if (a.alive) addsAlive++;
    }

    // ---- boss -------------------------------------------------------------
    if (courseDone && !bossDown) {
      stepBoss(boss, addsAlive, player.x, player.y, player.z, simTime, DT);
      if (boss.transitioned) emit({ kind: 'boss-phase', phase: boss.transitioned });
      if (boss.fired) {
        const yawToPlayer = Math.atan2(player.x - boss.x, player.z - boss.z);
        const n = boss.fireCount;
        for (let k = 0; k < n; k++) {
          const off = n === 1 ? 0 : (k - (n - 1) / 2) * BOSS.spreadAngle;
          const a = yawToPlayer + off;
          const dy = player.y - boss.y;
          const dh = Math.max(1e-6, Math.hypot(player.x - boss.x, player.z - boss.z));
          spawnProjectile(
            pool, 1, boss.x, boss.y, boss.z,
            Math.sin(a) * PROJECTILE.enemySpeed,
            (dy / dh) * PROJECTILE.enemySpeed * 0.5,
            Math.cos(a) * PROJECTILE.enemySpeed,
            PROJECTILE.enemyDamage,
          );
          emit({ kind: 'shot-fired', by: 'boss' });
        }
      }
    }

    // ---- projectiles -------------------------------------------------------
    stepProjectiles(pool, DT);
    targets.length = 0;
    targets.push({ id: PLAYER_ID, x: player.x, y: player.y, z: player.z, radius: 1.5, team: 0 });
    for (const e of enemies) {
      if (e.alive) targets.push({ id: e.id, x: e.x, y: e.y, z: e.z, radius: 1.9, team: 1 });
    }
    for (const a of adds) {
      if (a.alive) targets.push({ id: a.id, x: a.x, y: a.y, z: a.z, radius: 1.9, team: 1 });
    }
    if (courseDone && !bossDown) {
      targets.push({ id: BOSS_ID, x: boss.x, y: boss.y, z: boss.z, radius: 4.2, team: 1 });
    }
    collideProjectiles(pool, targets, DT, (targetId, damage, owner) => {
      if (targetId === PLAYER_ID) {
        playerHp -= damage;
        emit({ kind: 'player-hit', amount: damage, hp: Math.max(0, Math.round(playerHp)) });
        return;
      }
      if (owner !== 0) return;
      emit({ kind: 'shot-hit', targetId });
      if (targetId === BOSS_ID) {
        const result = damageBoss(boss, damage);
        if (result === 'blocked') emit({ kind: 'boss-shield-blocked' });
        else if (result === 'killed') {
          bossDown = true;
          emit({ kind: 'boss-kill' });
        } else emit({ kind: 'boss-hit', amount: damage, hp: boss.hp });
        return;
      }
      const all = targetId >= 100 ? adds : enemies;
      const hit = all.find((e) => e.id === targetId);
      if (hit && damageEnemy(hit, damage)) emit({ kind: 'drone-kill', droneId: hit.id });
    });

    if (bossDown) {
      return {
        log, score: totalScore(score), steps: step, bossDown, ringsPassed: tracker.passed,
      };
    }
  }
  return {
    log, score: totalScore(score), steps: MAX_STEPS, bossDown, ringsPassed: tracker.passed,
  };
}

function fireAt(
  pool: ReturnType<typeof createPool>,
  from: { x: number; y: number; z: number },
  at: { x: number; y: number; z: number },
): void {
  const dx = at.x - from.x;
  const dy = at.y - from.y;
  const dz = at.z - from.z;
  const d = Math.max(1e-6, Math.hypot(dx, dy, dz));
  spawnProjectile(
    pool, 1, from.x, from.y, from.z,
    (dx / d) * PROJECTILE.enemySpeed, (dy / d) * PROJECTILE.enemySpeed,
    (dz / d) * PROJECTILE.enemySpeed, PROJECTILE.enemyDamage,
  );
}

describe('full scripted run', () => {
  test('one seed reproduces the identical event log, twice', () => {
    const a = simulateRun(124935158);
    const b = simulateRun(124935158);
    expect(a.log).toStrictEqual(b.log);
    expect(a.score).toBe(b.score);
    expect(a.steps).toBe(b.steps);
  }, 30000);

  test('the run completes: 10 rings in order, boss phases in order, boss down', () => {
    const r = simulateRun(124935158);
    expect(r.ringsPassed).toBe(10);
    expect(r.bossDown).toBe(true);
    const kinds = r.log.map((s) => JSON.parse(s) as FlightEvent);
    const ringIdx = kinds.filter((e) => e.kind === 'ring-pass').map((e) =>
      e.kind === 'ring-pass' ? e.index : -1,
    );
    expect(ringIdx).toStrictEqual([0, 1, 2, 3, 4, 5, 6, 7, 8, 9]);
    const vulnerableAt = r.log.findIndex((s) => s.includes('"phase":"vulnerable"'));
    const enragedAt = r.log.findIndex((s) => s.includes('"phase":"enraged"'));
    const killAt = r.log.findIndex((s) => s.includes('"boss-kill"'));
    expect(vulnerableAt).toBeGreaterThan(-1);
    expect(enragedAt).toBeGreaterThan(vulnerableAt);
    expect(killAt).toBeGreaterThan(enragedAt);
    expect(r.score).toBeGreaterThan(10 * 100 + 1000); // rings + boss at minimum
  }, 30000);

  test('a different seed produces a different run', () => {
    const a = simulateRun(124935158);
    const b = simulateRun(42);
    expect(a.log).not.toStrictEqual(b.log);
  }, 30000);
});
