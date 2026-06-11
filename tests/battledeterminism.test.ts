import { describe, expect, test } from 'vitest';
import { Rng } from '../src/core/Rng';
import { chooseAction } from '../src/systems/battle/BattleAI';
import {
  checkLockup,
  createBattle,
  describeEvent,
  endOfUnitTurn,
  executeMove,
  winner,
  type BattleEvent,
  type BattleState,
} from '../src/systems/battle/Resolution';
import { computeTurnOrder } from '../src/systems/battle/TurnOrder';
import { ENEMY_TEAM, PLAYER_TEAM } from '../src/systems/battle/Units';

const MAX_ROUNDS = 80;

interface BattleRun {
  events: BattleEvent[];
  log: string[];
  winner: 0 | 1 | null;
  rounds: number;
}

/**
 * Full scripted battle: the same AI drives BOTH sides; every random
 * draw (variance, status chances, tie breaks) comes from one seeded
 * stream. This is the determinism proof for HANDOVER 4.3.
 */
function runScriptedBattle(seed: number): BattleRun {
  const state: BattleState = createBattle(PLAYER_TEAM, ENEMY_TEAM);
  const rng = new Rng(seed);
  const events: BattleEvent[] = [];
  const log: string[] = [];
  const record = (from: number): void => {
    for (let i = from; i < events.length; i++) {
      log.push(describeEvent(state, events[i] as BattleEvent));
    }
  };

  while (state.round <= MAX_ROUNDS && winner(state) === null) {
    const order = computeTurnOrder(state);
    for (const unitId of order) {
      const unit = state.units[unitId];
      if (!unit || !unit.alive || winner(state) !== null) continue;
      const before = events.length;
      if (!checkLockup(unit, events)) {
        const decision = chooseAction(state, unitId, rng);
        if (decision) executeMove(state, decision.action, rng, events);
      }
      endOfUnitTurn(state, unitId, events);
      record(before);
    }
    state.round++;
  }
  return { events, log, winner: winner(state), rounds: state.round - 1 };
}

describe('full scripted battle determinism', () => {
  test('the same seed reproduces the identical event log, sentence for sentence', () => {
    const a = runScriptedBattle(20260610);
    const b = runScriptedBattle(20260610);
    expect(a.events).toEqual(b.events);
    expect(a.log).toEqual(b.log);
    expect(a.winner).toBe(b.winner);
    expect(a.rounds).toBe(b.rounds);
  });

  test('the battle actually completes with a winner and substantial play', () => {
    const run = runScriptedBattle(20260610);
    expect(run.winner === 0 || run.winner === 1).toBe(true);
    // At least the losing side's three units went down.
    expect(run.events.filter((e) => e.kind === 'ko').length).toBeGreaterThanOrEqual(3);
    expect(run.events.filter((e) => e.kind === 'damage').length).toBeGreaterThan(5);
    // Every sentence is real prose derived from a real event.
    for (const line of run.log) {
      expect(line.length).toBeGreaterThan(10);
    }
  });

  test('different seeds diverge (variance and choices are really seeded)', () => {
    const a = runScriptedBattle(1);
    const c = runScriptedBattle(2);
    expect(a.log.join('\n')).not.toBe(c.log.join('\n'));
  });
});
