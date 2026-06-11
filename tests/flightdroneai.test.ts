import { describe, expect, test } from 'vitest';
import {
  BOSS,
  ENEMY,
  createBoss,
  createEnemy,
  damageBoss,
  damageEnemy,
  stepBoss,
  stepEnemy,
  type BossState,
  type EnemyDrone,
} from '../src/systems/flight/DroneAI';

const DT = 1 / 60;

function stepN(d: EnemyDrone, px: number, py: number, pz: number, n: number, t0 = 0): void {
  for (let i = 0; i < n; i++) stepEnemy(d, px, py, pz, t0 + i * DT, DT);
}

describe('escort drone state machine', () => {
  test('patrol -> engage when the player enters engage range', () => {
    const d = createEnemy(0, 0, 40, 0);
    stepEnemy(d, 500, 40, 500, 0, DT); // player far away
    expect(d.state).toBe('patrol');
    expect(d.transitioned).toBeNull();
    stepEnemy(d, d.x + ENEMY.engageRange - 1, d.y, d.z, DT, DT);
    expect(d.state).toBe('engage');
    expect(d.transitioned).toBe('engage');
  });

  test('engage -> patrol only past the LOSE range (hysteresis band)', () => {
    const d = createEnemy(0, 0, 40, 0);
    stepEnemy(d, d.x + 10, d.y, d.z, 0, DT); // engage
    expect(d.state).toBe('engage');
    // Player inside the hysteresis band: still engaged.
    stepEnemy(d, d.x + ENEMY.loseRange - 5, d.y, d.z, DT, DT);
    expect(d.state).toBe('engage');
    // Player beyond loseRange: disengages.
    stepEnemy(d, d.x + ENEMY.loseRange + 5, d.y, d.z, 2 * DT, DT);
    expect(d.state).toBe('patrol');
    expect(d.transitioned).toBe('patrol');
  });

  test('drops to evade at low hp and STAYS there', () => {
    const d = createEnemy(1, 0, 40, 0);
    stepEnemy(d, d.x + 10, d.y, d.z, 0, DT);
    expect(d.state).toBe('engage');
    damageEnemy(d, ENEMY.maxHp * (1 - ENEMY.evadeHpFrac) + 1);
    stepEnemy(d, d.x + 10, d.y, d.z, DT, DT);
    expect(d.state).toBe('evade');
    expect(d.transitioned).toBe('evade');
    // Even with the player far away, evade persists (no re-patrol).
    stepN(d, 500, 40, 500, 60, 2 * DT);
    expect(d.state).toBe('evade');
  });

  test('evade actually flees: distance to the player grows', () => {
    const d = createEnemy(2, 0, 40, 0);
    damageEnemy(d, ENEMY.maxHp - 1); // 1 hp -> evade on next step
    const px = d.x + 12;
    const before = Math.hypot(px - d.x, 0, 0);
    stepN(d, px, d.y, d.z, 120);
    const after = Math.hypot(px - d.x, d.y - 40, d.z);
    expect(d.state).toBe('evade');
    expect(after).toBeGreaterThan(before + 10);
  });

  test('fires only in engage, within fire range, on its real cooldown', () => {
    const d = createEnemy(3, 0, 40, 0);
    // In patrol: never fires even point-blank... (it would engage first,
    // so prove the inverse: out of fire range while engaged).
    stepEnemy(d, d.x + ENEMY.fireRange + 8, d.y, d.z, 0, DT);
    expect(d.state).toBe('engage');
    let fired = 0;
    // Out of fire range: no shots even after the cooldown elapses.
    for (let i = 0; i < 120; i++) {
      stepEnemy(d, d.x + ENEMY.fireRange + 30, d.y, d.z, i * DT, DT);
      if (d.fired) fired++;
    }
    expect(fired).toBe(0);
    // Within range: fires, then respects the interval between shots.
    const times: number[] = [];
    for (let i = 0; i < 360; i++) {
      const t = 2 + i * DT;
      stepEnemy(d, d.x + 10, d.y, d.z, t, DT);
      if (d.fired) times.push(t);
    }
    expect(times.length).toBeGreaterThanOrEqual(2);
    for (let i = 1; i < times.length; i++) {
      expect((times[i] as number) - (times[i - 1] as number)).toBeGreaterThanOrEqual(
        ENEMY.fireInterval - DT,
      );
    }
  });

  test('patrol orbits its anchor: stays near the patrol radius', () => {
    const d = createEnemy(4, 100, 40, -50);
    stepN(d, 500, 40, 500, 600); // 10 s of undisturbed patrol
    const dist = Math.hypot(d.x - 100, d.z - -50);
    expect(d.state).toBe('patrol');
    expect(dist).toBeGreaterThan(ENEMY.patrolRadius * 0.5);
    expect(dist).toBeLessThan(ENEMY.patrolRadius * 1.5);
  });

  test('damageEnemy reports the killing hit exactly once', () => {
    const d = createEnemy(5, 0, 40, 0);
    expect(damageEnemy(d, ENEMY.maxHp - 1)).toBe(false);
    expect(damageEnemy(d, 1)).toBe(true);
    expect(d.alive).toBe(false);
    expect(damageEnemy(d, 99)).toBe(false); // already dead: no double kill
  });
});

describe('boss phases', () => {
  function stepBossN(b: BossState, adds: number, n: number, t0 = 0, px = 200, py = 42, pz = 0): void {
    for (let i = 0; i < n; i++) stepBoss(b, adds, px, py, pz, t0 + i * DT, DT);
  }

  test('starts shielded and damage is BLOCKED while adds live', () => {
    const b = createBoss(228, 42, 0);
    expect(b.phase).toBe('shielded');
    expect(damageBoss(b, 50)).toBe('blocked');
    expect(b.hp).toBe(BOSS.maxHp);
    stepBossN(b, 2, 60);
    expect(b.phase).toBe('shielded'); // adds alive: no transition
  });

  test('shielded -> vulnerable the step the last add dies (real state)', () => {
    const b = createBoss(228, 42, 0);
    stepBoss(b, 1, 200, 42, 0, 0, DT);
    expect(b.phase).toBe('shielded');
    stepBoss(b, 0, 200, 42, 0, DT, DT);
    expect(b.phase).toBe('vulnerable');
    expect(b.transitioned).toBe('vulnerable');
    expect(damageBoss(b, 30)).toBe('hit');
    expect(b.hp).toBe(BOSS.maxHp - 30);
  });

  test('vulnerable -> enraged at the real hp threshold', () => {
    const b = createBoss(228, 42, 0);
    stepBoss(b, 0, 200, 42, 0, 0, DT); // open the shield
    const toThreshold = BOSS.maxHp - Math.floor(BOSS.maxHp * BOSS.enrageHpFrac);
    damageBoss(b, toThreshold - 1);
    stepBoss(b, 0, 200, 42, 0, DT, DT);
    expect(b.phase).toBe('vulnerable'); // 1 hp above the line: not yet
    damageBoss(b, 1);
    stepBoss(b, 0, 200, 42, 0, 2 * DT, DT);
    expect(b.phase).toBe('enraged');
    expect(b.transitioned).toBe('enraged');
  });

  test('killing blow flips the phase to down and further damage is inert', () => {
    const b = createBoss(228, 42, 0);
    stepBoss(b, 0, 200, 42, 0, 0, DT);
    expect(damageBoss(b, BOSS.maxHp)).toBe('killed');
    expect(b.phase).toBe('down');
    expect(damageBoss(b, 10)).toBe('blocked');
    stepBoss(b, 0, 200, 42, 0, DT, DT);
    expect(b.fired).toBe(false);
  });

  test('phases have distinct fire behavior: spread vs aimed vs fast spread', () => {
    // Shielded: fires fans of spreadCount on the slow interval.
    const a = createBoss(228, 42, 0);
    let spreadShots = 0;
    for (let i = 0; i < 600; i++) {
      stepBoss(a, 2, 220, 42, 0, i * DT, DT);
      if (a.fired) {
        expect(a.fireCount).toBe(BOSS.spreadCount);
        spreadShots++;
      }
    }
    // Vulnerable: single aimed bolts, faster interval.
    const v = createBoss(228, 42, 0);
    let aimedShots = 0;
    for (let i = 0; i < 600; i++) {
      stepBoss(v, 0, 220, 42, 0, i * DT, DT);
      if (v.fired) {
        expect(v.fireCount).toBe(1);
        aimedShots++;
      }
    }
    // Enraged: spread fans at the fastest interval.
    const e = createBoss(228, 42, 0);
    stepBoss(e, 0, 220, 42, 0, 0, DT);
    damageBoss(e, BOSS.maxHp - 1); // deep into enrage territory
    let enragedShots = 0;
    for (let i = 1; i < 601; i++) {
      stepBoss(e, 0, 220, 42, 0, i * DT, DT);
      if (e.fired) enragedShots++;
    }
    expect(e.phase).toBe('enraged');
    expect(aimedShots).toBeGreaterThan(spreadShots);
    expect(enragedShots).toBeGreaterThan(aimedShots);
  });

  test('boss holds the arena center while vulnerable', () => {
    const b = createBoss(228, 42, 0);
    stepBossN(b, 0, 600); // 10 s vulnerable
    const dist = Math.hypot(b.x - 228, b.y - 42, b.z);
    expect(b.phase).toBe('vulnerable');
    expect(dist).toBeLessThan(2);
  });
});
