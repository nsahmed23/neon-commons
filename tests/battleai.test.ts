import { describe, expect, test } from 'vitest';
import { Rng } from '../src/core/Rng';
import {
  chooseAction,
  formatScoreBreakdown,
  scoreAllOptions,
  type AIDecision,
} from '../src/systems/battle/BattleAI';
import { getMove } from '../src/systems/battle/Moves';
import {
  createBattle,
  previewDamage,
  type BattleState,
  type UnitState,
} from '../src/systems/battle/Resolution';

function setup(): { state: BattleState; unit: (i: number) => UnitState } {
  const state = createBattle(['arclight', 'kilnguard', 'solace'], ['whipcord', 'bulwark', 'rimefang']);
  return { state, unit: (i) => state.units[i] as UnitState };
}

function decide(state: BattleState, userId: number, seed = 1): AIDecision {
  const d = chooseAction(state, userId, new Rng(seed));
  if (!d) throw new Error('no decision');
  return d;
}

describe('AI move choice (provably correct scenarios)', () => {
  test('a guaranteed KO beats chip damage on a healthier target', () => {
    const { state, unit } = setup();
    // Whipcord (AI, id 3) acts. Arclight at 10 HP: even weak razorGale min-rolls a KO.
    unit(0).hp = 10;
    const d = decide(state, 3);
    expect(d.action.targetId).toBe(0);
    expect(d.chosen.parts.koPotential).toBe(100);
    // Sanity: the KO is genuinely guaranteed at minimum roll.
    const min = previewDamage(unit(3), unit(0), getMove(d.action.moveId)).min;
    expect(min).toBeGreaterThanOrEqual(10);
  });

  test('healing is chosen at low HP over attacking', () => {
    const { state, unit } = setup();
    // Rimefang (id 5) has nanorepairSwarm and is nearly dead; its attack
    // is crippled (-3) so no attack can KO or out-score the heal.
    unit(5).hp = Math.floor(unit(5).spec.maxHp * 0.15);
    unit(5).stages.atk = -3;
    const d = decide(state, 5);
    expect(d.action.moveId).toBe('nanorepairSwarm');
    expect(d.action.targetId).toBe(5);
    expect(d.chosen.parts.healingValue).toBeGreaterThan(0);
    expect(d.chosen.parts.survivalRisk).toBeGreaterThan(0);
  });

  test('the AI respects cooldowns: a cooling move never appears in the options', () => {
    const { state, unit } = setup();
    unit(3).cooldowns['concussionRam'] = 2;
    const options = scoreAllOptions(state, 3);
    expect(options.some((o) => o.moveId === 'concussionRam')).toBe(false);
    const d = decide(state, 3);
    expect(d.action.moveId).not.toBe('concussionRam');
  });

  test('the AI respects energy: with an empty tank it Vents', () => {
    const { state, unit } = setup();
    unit(3).energy = 4;
    const d = decide(state, 3);
    expect(d.action.moveId).toBe('vent');
  });

  test('type advantage is a named modifier steering target choice', () => {
    const { state, unit } = setup();
    // Arclight (VOLT) scoring ionLance: vs whipcord (AERO, 2x) must out-score
    // vs rimefang (CRYO, 0.5x), all else similar.
    const options = scoreAllOptions(state, 0).filter((o) => o.moveId === 'ionLance');
    const vsAero = options.find((o) => o.targetId === 3);
    const vsCryo = options.find((o) => o.targetId === 5);
    expect(vsAero && vsCryo).toBeTruthy();
    if (vsAero && vsCryo) {
      expect(vsAero.parts.typeAdvantage).toBeCloseTo(15);
      expect(vsCryo.parts.typeAdvantage).toBeCloseTo(-7.5);
      expect(vsAero.total).toBeGreaterThan(vsCryo.total);
    }
    expect(unit(0).spec.type).toBe('volt');
  });

  test('status moves lose their value once the status is already present', () => {
    const { state, unit } = setup();
    const before = scoreAllOptions(state, 3).find(
      (o) => o.moveId === 'staticShackles' && o.targetId === 0,
    );
    unit(0).statuses.push({ id: 'servoLag', turnsLeft: 2 });
    const after = scoreAllOptions(state, 3).find(
      (o) => o.moveId === 'staticShackles' && o.targetId === 0,
    );
    expect(before?.parts.statusValue).toBe(14);
    expect(after?.parts.statusValue).toBe(0);
  });

  test('ties break via the seeded RNG, deterministically per seed', () => {
    const { state } = setup();
    const a = decide(state, 3, 123);
    const b = decide(state, 3, 123);
    expect(a.action).toEqual(b.action);
  });

  test('every option exposes a full named breakdown that sums to its total', () => {
    const { state } = setup();
    for (const o of scoreAllOptions(state, 4)) {
      const p = o.parts;
      const sum =
        p.typeAdvantage + p.expectedDamage + p.koPotential + p.healingValue +
        p.statusValue + p.buffValue + p.cooldownTiming + p.survivalRisk + p.targetPriority;
      expect(sum).toBeCloseTo(o.total, 6);
      const line = formatScoreBreakdown(o);
      expect(line).toContain('=');
      expect(line.startsWith(o.total.toFixed(1))).toBe(true);
    }
  });
});
