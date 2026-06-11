import { describe, expect, test } from 'vitest';
import { PASS_START_STIPEND, REST_POS, STARTING_MONEY } from '../src/systems/board/BoardData';
import { rngInt } from '../src/systems/board/BoardRng';
import {
  createBoardGame,
  endTurn,
  rollDice,
  type BoardEvent,
} from '../src/systems/board/Engine';

/** Find an rng cursor whose next two d6 satisfy a predicate. */
function findDiceState(pred: (d1: number, d2: number) => boolean, start = 1): number {
  for (let s = start; s < start + 100000; s++) {
    const r1 = rngInt(s, 1, 6);
    const r2 = rngInt(r1.state, 1, 6);
    if (pred(r1.value, r2.value)) return s;
  }
  throw new Error('no cursor found');
}

const NON_DOUBLES = findDiceState((a, b) => a !== b);
const DOUBLES = findDiceState((a, b) => a === b);

describe('turn order and the echo-roll (doubles) rule', () => {
  test('turns advance in seat order and wrap with a round increment', () => {
    const g = createBoardGame(5, [false, false, false]);
    const events: BoardEvent[] = [];
    expect(g.current).toBe(0);
    expect(g.round).toBe(1);
    for (const expected of [1, 2, 0]) {
      g.rngState = NON_DOUBLES;
      expect(rollDice(g, events)).toBe(true);
      expect(g.phase).toBe('act');
      expect(endTurn(g, events)).toBe(true);
      expect(g.current).toBe(expected);
    }
    expect(g.round).toBe(2); // wrapped back to seat 0
    const starts = events.filter((e) => e.kind === 'turn-start');
    expect(starts.map((e) => (e as { player: number }).player)).toEqual([1, 2, 0]);
  });

  test('rolling out of phase or acting twice is rejected', () => {
    const g = createBoardGame(5, [false, false]);
    const events: BoardEvent[] = [];
    g.rngState = NON_DOUBLES;
    expect(rollDice(g, events)).toBe(true);
    expect(rollDice(g, events)).toBe(false); // already in 'act'
    expect(endTurn(g, events)).toBe(true);
    expect(endTurn(g, events)).toBe(false); // back in 'roll'
  });

  test('an echo roll (doubles) grants the same player another roll', () => {
    const g = createBoardGame(5, [false, false]);
    const events: BoardEvent[] = [];
    g.rngState = DOUBLES;
    expect(rollDice(g, events)).toBe(true);
    expect(g.doublesCount).toBe(1);
    endTurn(g, events);
    expect(g.current).toBe(0); // still player 1
    expect(g.phase).toBe('roll');
    const end = events.find((e) => e.kind === 'turn-end');
    expect(end).toMatchObject({ extraTurn: true });
  });

  test('a third consecutive echo triggers Surge Recall: fine + Maintenance Bay + turn over', () => {
    const g = createBoardGame(5, [false, false]);
    const events: BoardEvent[] = [];
    g.doublesCount = 2; // two echoes already this turn
    g.rngState = DOUBLES;
    const moneyBefore = (g.players[0]!).money;
    expect(rollDice(g, events)).toBe(true);
    expect(events.some((e) => e.kind === 'surge-recall')).toBe(true);
    expect(g.players[0]!.pos).toBe(REST_POS);
    expect(g.players[0]!.money).toBe(moneyBefore - 50);
    expect(g.current).toBe(1); // turn passed
    expect(g.phase).toBe('roll');
  });

  test('passing Plaza Gate pays the stipend exactly once per lap', () => {
    const g = createBoardGame(5, [false, false]);
    const events: BoardEvent[] = [];
    g.players[0]!.pos = 26; // two short of start
    // Avoid total 4 (= event space 2, whose card could move the pawn again).
    g.rngState = findDiceState((a, b) => a !== b && a + b !== 4);
    rollDice(g, events);
    const stipends = events.filter((e) => e.kind === 'stipend');
    expect(stipends.length).toBe(1);
    expect(stipends[0]).toMatchObject({ player: 0, amount: PASS_START_STIPEND });
  });

  test('no stipend without wrapping', () => {
    const g = createBoardGame(5, [false, false]);
    const events: BoardEvent[] = [];
    g.players[0]!.pos = 0;
    // Avoid the event space (total 2) and the levy (total 5) so the
    // landing is provably free and money must be exactly untouched.
    g.rngState = findDiceState((a, b) => a !== b && a + b !== 2 && a + b !== 5);
    rollDice(g, events);
    expect(events.some((e) => e.kind === 'stipend')).toBe(false);
    expect(g.players[0]!.money).toBe(STARTING_MONEY);
  });

  test('dead players are skipped in the rotation', () => {
    const g = createBoardGame(5, [false, false, false, false]);
    const events: BoardEvent[] = [];
    g.players[1]!.alive = false;
    g.players[1]!.money = 0;
    g.rngState = NON_DOUBLES;
    rollDice(g, events);
    endTurn(g, events);
    expect(g.current).toBe(2); // seat 1 skipped
  });
});
