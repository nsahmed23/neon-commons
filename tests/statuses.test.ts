import { describe, expect, test } from 'vitest';
import { Rng } from '../src/core/Rng';
import {
  applyStageDelta,
  createStages,
  stageMultiplier,
} from '../src/systems/battle/Statuses';
import {
  createBattle,
  effectiveStat,
  endOfUnitTurn,
  tryApplyStatus,
  type BattleEvent,
  type BattleState,
  type UnitState,
} from '../src/systems/battle/Resolution';

function setup(): { state: BattleState; a: UnitState; rng: Rng; events: BattleEvent[] } {
  const state = createBattle(['arclight', 'kilnguard', 'solace'], ['whipcord', 'bulwark', 'rimefang']);
  return { state, a: state.units[0] as UnitState, rng: new Rng(42), events: [] };
}

describe('status application and stacking', () => {
  test('applying a new status emits status-applied with its duration', () => {
    const { a, rng, events } = setup();
    tryApplyStatus(a, 'corrosion', rng, 1, events);
    expect(events).toEqual([
      { kind: 'status-applied', targetId: 0, status: 'corrosion', turns: 3 },
    ]);
    expect(a.statuses).toEqual([{ id: 'corrosion', turnsLeft: 3 }]);
  });

  test('re-applying refreshes duration instead of stacking', () => {
    const { a, rng, events } = setup();
    tryApplyStatus(a, 'corrosion', rng, 1, events);
    (a.statuses[0] as { turnsLeft: number }).turnsLeft = 1;
    tryApplyStatus(a, 'corrosion', rng, 1, events);
    expect(a.statuses.length).toBe(1);
    expect(a.statuses[0]).toEqual({ id: 'corrosion', turnsLeft: 3 });
    expect(events[1]?.kind).toBe('status-refreshed');
  });

  test('thermalShroud passive blocks corrosion; gyroGimbal blocks servoLag', () => {
    const { state, rng, events } = setup();
    const kilnguard = state.units[1] as UnitState; // thermalShroud
    const whipcord = state.units[3] as UnitState; // gyroGimbal
    tryApplyStatus(kilnguard, 'corrosion', rng, 1, events);
    tryApplyStatus(whipcord, 'servoLag', rng, 1, events);
    expect(kilnguard.statuses.length).toBe(0);
    expect(whipcord.statuses.length).toBe(0);
    expect(events.map((e) => e.kind)).toEqual(['status-immune', 'status-immune']);
  });

  test('a sub-100% chance can be resisted, deterministically from the seed', () => {
    const { a, events } = setup();
    // Find a seed whose first draw fails a 40% roll.
    const rng = new Rng(7);
    const probe = new Rng(7);
    const willApply = probe.next() < 0.4;
    tryApplyStatus(a, 'corrosion', rng, 0.4, events);
    if (willApply) {
      expect(events[0]?.kind).toBe('status-applied');
    } else {
      expect(events[0]?.kind).toBe('status-resisted');
      expect(a.statuses.length).toBe(0);
    }
  });
});

describe('status ticks and expiry timing (end of own turn)', () => {
  test('corrosion damages 6% max HP per turn and expires after 3 ticks', () => {
    const { state, a, rng, events } = setup();
    tryApplyStatus(a, 'corrosion', rng, 1, events);
    const perTick = Math.round(a.spec.maxHp * 0.06);
    const hp0 = a.hp;
    endOfUnitTurn(state, 0, events);
    expect(a.hp).toBe(hp0 - perTick);
    endOfUnitTurn(state, 0, events);
    endOfUnitTurn(state, 0, events);
    expect(a.hp).toBe(hp0 - 3 * perTick);
    expect(a.statuses.length).toBe(0);
    expect(events.filter((e) => e.kind === 'status-expired')).toEqual([
      { kind: 'status-expired', targetId: 0, status: 'corrosion' },
    ]);
    // A 4th turn ticks nothing.
    const hpAfter = a.hp;
    endOfUnitTurn(state, 0, events);
    expect(a.hp).toBe(hpAfter);
  });

  test('nanorepair heals 8% max HP per turn; lockup expires after one turn', () => {
    const { state, a, rng, events } = setup();
    a.hp = 50;
    tryApplyStatus(a, 'nanorepair', rng, 1, events);
    tryApplyStatus(a, 'lockup', rng, 1, events);
    endOfUnitTurn(state, 0, events);
    expect(a.hp).toBe(50 + Math.round(a.spec.maxHp * 0.08));
    expect(a.statuses.map((s) => s.id)).toEqual(['nanorepair']); // lockup expired
  });

  test('fluxLeak drains 8 energy per turn (floored at 0)', () => {
    const { state, a, rng, events } = setup();
    tryApplyStatus(a, 'fluxLeak', rng, 1, events);
    a.energy = 5;
    endOfUnitTurn(state, 0, events);
    // -5 leak (floored), then +10 regen
    const tick = events.find((e) => e.kind === 'status-tick' && e.status === 'fluxLeak');
    expect(tick).toEqual({ kind: 'status-tick', targetId: 0, status: 'fluxLeak', amount: -5 });
    expect(a.energy).toBe(10);
  });

  test('corrosion tick can KO and clears remaining statuses', () => {
    const { state, a, rng, events } = setup();
    tryApplyStatus(a, 'corrosion', rng, 1, events);
    tryApplyStatus(a, 'servoLag', rng, 1, events);
    a.hp = 2;
    endOfUnitTurn(state, 0, events);
    expect(a.alive).toBe(false);
    expect(a.statuses.length).toBe(0);
    expect(events.some((e) => e.kind === 'ko' && e.targetId === 0)).toBe(true);
  });
});

describe('stat stages', () => {
  test('multiplier table: +3 = 2x, +1 = 4/3, 0 = 1, -3 = 0.5x', () => {
    expect(stageMultiplier(3)).toBeCloseTo(2);
    expect(stageMultiplier(1)).toBeCloseTo(4 / 3);
    expect(stageMultiplier(0)).toBe(1);
    expect(stageMultiplier(-3)).toBeCloseTo(0.5);
  });

  test('stages stack additively and clamp at +/-3', () => {
    const s = createStages();
    expect(applyStageDelta(s, 'atk', 2)).toBe(2);
    expect(applyStageDelta(s, 'atk', 2)).toBe(1); // clamped to +3
    expect(s.atk).toBe(3);
    expect(applyStageDelta(s, 'atk', 1)).toBe(0); // at the limit
    expect(applyStageDelta(s, 'def', -5)).toBe(-3);
    expect(s.def).toBe(-3);
  });

  test('servoLag halves effective speed on top of stages', () => {
    const { state, a } = setup();
    const base = a.spec.spd;
    expect(effectiveStat(a, 'spd')).toBe(base);
    a.stages.spd = 3;
    a.statuses.push({ id: 'servoLag', turnsLeft: 2 });
    expect(effectiveStat(a, 'spd')).toBeCloseTo(base * 2 * 0.5);
    expect(state.units[0]?.statuses.length).toBe(1);
  });
});
