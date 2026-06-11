import { describe, expect, test } from 'vitest';
import { UNIT_TYPES, typeMultiplier } from '../src/systems/battle/TypeChart';
import { MOVES, NAMED_MOVE_COUNT } from '../src/systems/battle/Moves';
import { STATUS_IDS } from '../src/systems/battle/Statuses';
import { PASSIVE_IDS, UNIT_SPECS, getSpec } from '../src/systems/battle/Units';

describe('type chart', () => {
  test('has at least 4 types', () => {
    expect(UNIT_TYPES.length).toBeGreaterThanOrEqual(4);
  });

  test('the cycle deals 2x: volt>aero>pyre>cryo>volt', () => {
    expect(typeMultiplier('volt', 'aero')).toBe(2);
    expect(typeMultiplier('aero', 'pyre')).toBe(2);
    expect(typeMultiplier('pyre', 'cryo')).toBe(2);
    expect(typeMultiplier('cryo', 'volt')).toBe(2);
  });

  test('same-type and reverse-cycle attacks are resisted at 0.5x', () => {
    for (const t of UNIT_TYPES) expect(typeMultiplier(t, t)).toBe(0.5);
    expect(typeMultiplier('aero', 'volt')).toBe(0.5);
    expect(typeMultiplier('volt', 'cryo')).toBe(0.5);
  });

  test('every matchup is defined and meaningful (only 0.5/1/2)', () => {
    let twos = 0;
    let halves = 0;
    for (const a of UNIT_TYPES) {
      for (const d of UNIT_TYPES) {
        const m = typeMultiplier(a, d);
        expect([0.5, 1, 2]).toContain(m);
        if (m === 2) twos++;
        if (m === 0.5) halves++;
      }
    }
    expect(twos).toBe(4);
    expect(halves).toBe(8);
  });
});

describe('content minimums (HANDOVER 4.3)', () => {
  test('at least 12 named moves plus the Vent fallback', () => {
    expect(NAMED_MOVE_COUNT).toBeGreaterThanOrEqual(12);
    expect(MOVES['vent']).toBeDefined();
  });

  test('at least 6 statuses and 6 passives', () => {
    expect(STATUS_IDS.length).toBeGreaterThanOrEqual(6);
    expect(PASSIVE_IDS.length).toBeGreaterThanOrEqual(6);
  });

  test('every unit has exactly 4 known moves and a known passive', () => {
    for (const id of Object.keys(UNIT_SPECS)) {
      const spec = getSpec(id);
      expect(spec.moves.length).toBe(4);
      for (const m of spec.moves) expect(MOVES[m], `${id} move ${m}`).toBeDefined();
      expect(PASSIVE_IDS).toContain(spec.passive);
    }
  });
});
