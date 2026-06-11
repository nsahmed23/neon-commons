import { describe, expect, test } from 'vitest';
import { BOT_BUY_RESERVE, botActions } from '../src/systems/board/Bot';
import {
  buyCurrent,
  createBoardGame,
  describeBoardEvent,
  endTurn,
  rollDice,
  upgradeDistrict,
  type BoardEvent,
  type BoardGameState,
} from '../src/systems/board/Engine';

/** Run a full bot game from a seed; returns the sentence log + state. */
function playGame(
  seed: number,
  seats: boolean[],
  maxTurns = 600,
): { log: string[]; state: BoardGameState } {
  const state = createBoardGame(seed, seats, 40);
  const log: string[] = [];
  for (let i = 0; i < maxTurns && state.phase !== 'over'; i++) {
    const events: BoardEvent[] = [];
    rollDice(state, events);
    if (state.phase === 'act') {
      for (const a of botActions(state)) {
        if (a.type === 'buy') buyCurrent(state, events);
        else if (a.type === 'upgrade') upgradeDistrict(state, a.space, events);
        else endTurn(state, events);
      }
    }
    for (const e of events) log.push(describeBoardEvent(state, e));
  }
  return { log, state };
}

describe('full-game determinism from one seed', () => {
  test('two runs of the same seed produce the identical event log, sentence for sentence', () => {
    const a = playGame(123456, [true, true, true, true]);
    const b = playGame(123456, [true, true, true, true]);
    expect(a.log.length).toBeGreaterThan(100);
    expect(a.log).toEqual(b.log);
    expect(a.state).toEqual(b.state);
  });

  test('the game reaches a definite end with a winner', () => {
    const { log, state } = playGame(98765, [true, true, true]);
    expect(state.phase).toBe('over');
    expect(state.winner).not.toBeNull();
    expect(log.some((l) => l.startsWith('GAME OVER'))).toBe(true);
    // Real economy happened: somebody bought something.
    expect(log.some((l) => l.includes(' buys '))).toBe(true);
  });

  test('different seeds diverge', () => {
    const a = playGame(1111, [true, true]);
    const b = playGame(2222, [true, true]);
    expect(a.log).not.toEqual(b.log);
  });
});

describe('bot policy (provable plan)', () => {
  test('bot buys an affordable unowned space and always ends its turn', () => {
    const g = createBoardGame(8, [true, true]);
    g.phase = 'act';
    g.players[0]!.pos = 1; // Dockside Sprawl, 60 cr
    const plan = botActions(g);
    expect(plan[0]).toEqual({ type: 'buy' });
    expect(plan.at(-1)).toEqual({ type: 'end' });
  });

  test('bot refuses to buy below its cash reserve', () => {
    const g = createBoardGame(8, [true, true]);
    g.phase = 'act';
    g.players[0]!.pos = 1;
    g.players[0]!.money = 60 + BOT_BUY_RESERVE - 1;
    expect(botActions(g)).toEqual([{ type: 'end' }]);
  });

  test('bot develops cheapest-first when it owns a full set with spare cash', () => {
    const g = createBoardGame(8, [true, true]);
    g.phase = 'act';
    g.players[0]!.pos = 0;
    g.players[0]!.money = 2000;
    g.ownership[1] = 0; // dock set, upgradeCost 50
    g.ownership[4] = 0;
    g.ownership[26] = 0; // spire set, upgradeCost 150
    g.ownership[27] = 0;
    const plan = botActions(g);
    expect(plan).toEqual([
      { type: 'upgrade', space: 1 },
      { type: 'upgrade', space: 4 },
      { type: 'end' },
    ]);
  });

  test('bot plan is deterministic for identical states', () => {
    const g1 = createBoardGame(8, [true, true]);
    const g2 = createBoardGame(8, [true, true]);
    g1.phase = 'act';
    g2.phase = 'act';
    expect(botActions(g1)).toEqual(botActions(g2));
  });
});
