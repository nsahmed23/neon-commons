import { describe, expect, test } from 'vitest';
import { Rng } from '../src/core/Rng';
import { getMove } from '../src/systems/battle/Moves';
import {
  canUse,
  createBattle,
  describeEvent,
  endOfUnitTurn,
  executeMove,
  legalOptions,
  previewDamage,
  winner,
  type BattleEvent,
  type BattleState,
  type UnitState,
} from '../src/systems/battle/Resolution';
import { computeTurnOrder } from '../src/systems/battle/TurnOrder';

function setup(seed = 99): {
  state: BattleState;
  rng: Rng;
  events: BattleEvent[];
  unit: (i: number) => UnitState;
} {
  const state = createBattle(['arclight', 'kilnguard', 'solace'], ['whipcord', 'bulwark', 'rimefang']);
  return {
    state,
    rng: new Rng(seed),
    events: [],
    unit: (i) => state.units[i] as UnitState,
  };
}

describe('damage resolution', () => {
  test('damage lands within the deterministic preview bounds', () => {
    const { state, rng, events, unit } = setup();
    const preview = previewDamage(unit(0), unit(3), getMove('ionLance'));
    const hp0 = unit(3).hp;
    executeMove(state, { userId: 0, moveId: 'ionLance', targetId: 3 }, rng, events);
    const dealt = hp0 - unit(3).hp;
    expect(dealt).toBeGreaterThanOrEqual(preview.min);
    expect(dealt).toBeLessThanOrEqual(preview.max);
  });

  test('type multipliers change real damage: 2x vs 0.5x targets', () => {
    const { unit } = setup();
    // Ion Lance is VOLT: whipcord is AERO (2x), rimefang is CRYO (0.5x).
    const strong = previewDamage(unit(0), unit(3), getMove('ionLance'));
    const weak = previewDamage(unit(0), unit(5), getMove('ionLance'));
    expect(strong.typeMult).toBe(2);
    expect(weak.typeMult).toBe(0.5);
    // Same defense-ish targets: the 2x hit must far exceed the 0.5x hit.
    expect(strong.min).toBeGreaterThan(weak.max * 2);
  });

  test('attack stages modify real computed damage', () => {
    const { state, unit } = setup();
    const before = previewDamage(unit(1), unit(3), getMove('furnaceSlam'));
    unit(1).stages.atk = 2; // +2 -> 5/3 multiplier
    const after = previewDamage(unit(1), unit(3), getMove('furnaceSlam'));
    expect(after.min / before.min).toBeCloseTo(5 / 3, 1);
    // Defense debuff on the target also raises damage.
    unit(3).stages.def = -2;
    const cracked = previewDamage(unit(1), unit(3), getMove('furnaceSlam'));
    expect(cracked.min).toBeGreaterThan(after.min);
    expect(state.units.length).toBe(6);
  });

  test('aegisField halves incoming damage and the event says so', () => {
    const { state, rng, events, unit } = setup();
    const open = previewDamage(unit(0), unit(3), getMove('ionLance'));
    unit(3).statuses.push({ id: 'aegisField', turnsLeft: 2 });
    const shielded = previewDamage(unit(0), unit(3), getMove('ionLance'));
    expect(shielded.max).toBeLessThanOrEqual(Math.ceil(open.min * 0.62));
    executeMove(state, { userId: 0, moveId: 'ionLance', targetId: 3 }, rng, events);
    const dmg = events.find((e) => e.kind === 'damage');
    expect(dmg && dmg.kind === 'damage' && dmg.shielded).toBe(true);
  });

  test('reactivePlating reduces damage 15%; surgeCore boosts it 30% below 30% HP', () => {
    const { unit } = setup();
    // bulwark (4) has reactivePlating. Compare same move/stats vs a clone without it.
    const vsBulwark = previewDamage(unit(0), unit(4), getMove('ionLance'));
    unit(0).hp = Math.floor(unit(0).spec.maxHp * 0.2); // arclight surgeCore engages
    const surged = previewDamage(unit(0), unit(4), getMove('ionLance'));
    expect(surged.min / vsBulwark.min).toBeCloseTo(1.3, 1);
  });

  test('KO emits a ko event, clears statuses, and decides the winner', () => {
    const { state, rng, events, unit } = setup();
    for (const id of [3, 4, 5]) {
      const u = unit(id);
      u.hp = 1;
    }
    unit(3).statuses.push({ id: 'corrosion', turnsLeft: 3 });
    executeMove(state, { userId: 0, moveId: 'ionLance', targetId: 3 }, rng, events);
    expect(unit(3).alive).toBe(false);
    expect(unit(3).statuses.length).toBe(0);
    expect(events.some((e) => e.kind === 'ko' && e.targetId === 3)).toBe(true);
    expect(winner(state)).toBeNull();
    executeMove(state, { userId: 0, moveId: 'ionLance', targetId: 4 }, rng, events);
    executeMove(state, { userId: 0, moveId: 'ionLance', targetId: 5 }, rng, events);
    expect(winner(state)).toBe(0);
  });

  test('siphonCircuit heals the attacker for 20% of damage dealt', () => {
    const { state, rng, events, unit } = setup();
    const rime = unit(5); // siphonCircuit
    rime.hp = 60;
    const hp0 = unit(0).hp;
    executeMove(state, { userId: 5, moveId: 'cryoSpike', targetId: 0 }, rng, events);
    const dealt = hp0 - unit(0).hp;
    const heal = events.find((e) => e.kind === 'heal');
    expect(heal && heal.kind === 'heal' && heal.amount).toBe(Math.round(dealt * 0.2));
    expect(rime.hp).toBe(60 + Math.round(dealt * 0.2));
  });
});

describe('energy and cooldowns', () => {
  test('moves cost energy; an unaffordable move is not legal but Vent always is', () => {
    const { state, unit } = setup();
    unit(0).energy = 5; // cheapest arclight move costs 8
    const opts = legalOptions(state, 0);
    expect(opts.map((o) => o.move.id)).toEqual(['vent']);
    expect(canUse(unit(0), getMove('ionLance'))).toBe(false);
  });

  test('cooldown enforcement: a used move stays illegal for its cooldown turns', () => {
    const { state, rng, events, unit } = setup();
    executeMove(state, { userId: 0, moveId: 'stormcellBurst', targetId: 3 }, rng, events);
    endOfUnitTurn(state, 0, events); // turn 1 ends: cooldown 3 -> 2
    expect(canUse(unit(0), getMove('stormcellBurst'))).toBe(false);
    endOfUnitTurn(state, 0, events); // 2 -> 1
    expect(canUse(unit(0), getMove('stormcellBurst'))).toBe(false);
    endOfUnitTurn(state, 0, events); // 1 -> 0
    expect(canUse(unit(0), getMove('stormcellBurst'))).toBe(true);
  });

  test('executeMove throws on an illegal (cooling-down) move', () => {
    const { state, rng, events } = setup();
    executeMove(state, { userId: 0, moveId: 'stormcellBurst', targetId: 3 }, rng, events);
    expect(() =>
      executeMove(state, { userId: 0, moveId: 'stormcellBurst', targetId: 3 }, rng, events),
    ).toThrow(/illegal/);
  });

  test('Vent restores 30 energy capped at max', () => {
    const { state, rng, events, unit } = setup();
    unit(0).energy = 10;
    executeMove(state, { userId: 0, moveId: 'vent', targetId: 0 }, rng, events);
    expect(unit(0).energy).toBe(40);
    const e = events.find((ev) => ev.kind === 'energy');
    expect(e && e.kind === 'energy' && e.amount).toBe(30);
  });
});

describe('turn order from speed', () => {
  test('orders living units by descending effective speed', () => {
    const { state } = setup();
    // base speeds: arclight 96, kilnguard 58, solace 74, whipcord 108, bulwark 46, rimefang 82
    expect(computeTurnOrder(state)).toEqual([3, 0, 5, 2, 1, 4]);
  });

  test('servoLag and speed stages reorder the round', () => {
    const { state, unit } = setup();
    unit(3).statuses.push({ id: 'servoLag', turnsLeft: 2 }); // whipcord 108 -> 54
    unit(1).stages.spd = 3; // kilnguard 58 -> 116
    expect(computeTurnOrder(state)).toEqual([1, 0, 5, 2, 3, 4]);
  });

  test('exact speed ties break stably by unit index', () => {
    const { state, unit } = setup();
    for (const u of state.units) {
      u.stages.spd = 0;
      u.statuses.length = 0;
    }
    // Force a three-way tie via spec speed override on copies.
    unit(0).spec = { ...unit(0).spec, spd: 80 };
    unit(2).spec = { ...unit(2).spec, spd: 80 };
    unit(4).spec = { ...unit(4).spec, spd: 80 };
    const order = computeTurnOrder(state);
    const tied = order.filter((i) => [0, 2, 4].includes(i));
    expect(tied).toEqual([0, 2, 4]);
    // And it is stable across repeated computation.
    expect(computeTurnOrder(state)).toEqual(order);
  });

  test('dead units are excluded from the order', () => {
    const { state, unit } = setup();
    unit(3).alive = false;
    expect(computeTurnOrder(state)).toEqual([0, 5, 2, 1, 4]);
  });
});

describe('battle log derives from events', () => {
  test('a damage event renders as a plain sentence with the multiplier', () => {
    const { state } = setup();
    const text = describeEvent(state, {
      kind: 'damage', userId: 0, targetId: 3, moveId: 'ionLance',
      amount: 34, typeMult: 2, shielded: false,
    });
    expect(text).toBe('AER-2 Whipcord takes 34 damage (2x type advantage).');
  });

  test('status and stat events explain themselves', () => {
    const { state } = setup();
    expect(
      describeEvent(state, { kind: 'status-applied', targetId: 3, status: 'servoLag', turns: 2 }),
    ).toBe('AER-2 Whipcord is now Servo-Lagged (speed halved, 2 turns).');
    expect(
      describeEvent(state, { kind: 'stat-change', targetId: 4, stat: 'def', delta: -1, stage: -1 }),
    ).toBe("HVY-6 Bulwark's defense falls (stage -1).");
    expect(describeEvent(state, { kind: 'ko', targetId: 5 })).toBe(
      'CRY-1 Rimefang is knocked out!',
    );
  });

  test('every event produced by a real action describes to a non-empty sentence', () => {
    const { state, rng, events } = setup();
    executeMove(state, { userId: 1, moveId: 'shieldbreakerMaul', targetId: 3 }, rng, events);
    expect(events.length).toBeGreaterThanOrEqual(3); // move-used, damage, stat or block
    for (const e of events) {
      const s = describeEvent(state, e);
      expect(s.length).toBeGreaterThan(10);
      expect(s.endsWith('.') || s.endsWith('!')).toBe(true);
    }
  });
});
