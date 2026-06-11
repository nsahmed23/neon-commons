import { describe, expect, test } from 'vitest';
import { BOARD, type DistrictDef } from '../src/systems/board/BoardData';
import { rngInt } from '../src/systems/board/BoardRng';
import {
  createBoardGame,
  endTurn,
  netWorth,
  rollDice,
  type BoardEvent,
  type BoardGameState,
} from '../src/systems/board/Engine';

const SPIRE_A = 26; // Spire Heights (rent[3] = 870)
const SPIRE_B = 27;
const DOCK_A = 1;

function findDiceTotal(total: number): number {
  for (let s = 1; s < 100000; s++) {
    const r1 = rngInt(s, 1, 6);
    const r2 = rngInt(r1.state, 1, 6);
    if (r1.value !== r2.value && r1.value + r2.value === total) return s;
  }
  throw new Error('no cursor');
}

/** Player 0 about to land on Spire Heights, owned by player 1 at level 3. */
function debtTrap(money: number): { g: BoardGameState; events: BoardEvent[] } {
  const g = createBoardGame(7, [false, false]);
  g.players[0]!.pos = SPIRE_A - 7;
  g.players[0]!.money = money;
  g.ownership[SPIRE_A] = 1;
  g.ownership[SPIRE_B] = 1;
  g.levels[SPIRE_A] = 3;
  g.rngState = findDiceTotal(7);
  return { g, events: [] };
}

describe('forced payments, liquidation and bankruptcy', () => {
  test('rent is paid in full from cash when available, into the owner pocket', () => {
    const { g, events } = debtTrap(1000);
    rollDice(g, events);
    expect(g.players[0]!.money).toBe(1000 - 870);
    expect(g.players[1]!.money).toBe(1500 + 870);
    expect(events).toContainEqual(
      expect.objectContaining({ kind: 'rent', amount: 870, level: 3 }),
    );
  });

  test('a short payer liquidates developments first (half refund), then properties', () => {
    const { g, events } = debtTrap(800);
    // Payer owns a developed dock district + a spare transit.
    g.ownership[DOCK_A] = 0;
    g.ownership[4] = 0;
    g.levels[DOCK_A] = 2;
    g.ownership[3] = 0; // Skyrail North, price 200
    rollDice(g, events);
    const liqUp = events.filter((e) => e.kind === 'liquidate-upgrade');
    const liqProp = events.filter((e) => e.kind === 'liquidate-property');
    // 800 + 25 + 25 (two upgrade levels at half of 50) = 850 < 870,
    // so the cheapest property (Dockside Sprawl, 60) sells for 30 next.
    expect(liqUp.length).toBe(2);
    expect(liqUp[0]).toMatchObject({ space: DOCK_A, level: 1, refund: 25 });
    expect(liqUp[1]).toMatchObject({ space: DOCK_A, level: 0, refund: 25 });
    expect(liqProp[0]).toMatchObject({ space: DOCK_A, refund: 30 });
    expect(g.levels[DOCK_A]).toBe(0);
    expect(g.ownership[DOCK_A]).toBe(-1);
    expect(g.ownership[3]).toBe(0); // transit survived, debt was covered
    expect(g.players[0]!.alive).toBe(true);
    expect(g.players[0]!.money).toBe(800 + 25 + 25 + 30 - 870);
    expect(g.players[1]!.money).toBe(1500 + 870);
  });

  test('total asset exhaustion bankrupts the player and the creditor gets what was recovered', () => {
    const { g, events } = debtTrap(100);
    g.ownership[DOCK_A] = 0; // 60 cr district, sells for 30
    rollDice(g, events);
    const p0 = g.players[0]!;
    expect(p0.alive).toBe(false);
    expect(p0.money).toBe(0);
    expect(g.ownership[DOCK_A]).toBe(-1); // returned to the bank
    expect(events).toContainEqual({ kind: 'bankrupt', player: 0, creditor: 1 });
    // Creditor receives 100 cash + 30 liquidation, not the full 870.
    expect(g.players[1]!.money).toBe(1500 + 130);
  });

  test('bankruptcy of the second-to-last player ends the game: last solvent wins', () => {
    const { g, events } = debtTrap(0);
    rollDice(g, events);
    expect(g.phase).toBe('over');
    expect(g.winner).toBe(1);
    const over = events.find((e) => e.kind === 'game-over');
    expect(over).toMatchObject({ winner: 1, reason: 'last-solvent' });
  });

  test('with 3 players one bankruptcy does not end the game', () => {
    const g = createBoardGame(7, [false, false, false]);
    g.players[0]!.pos = SPIRE_A - 7;
    g.players[0]!.money = 0;
    g.ownership[SPIRE_A] = 1;
    g.ownership[SPIRE_B] = 1;
    g.levels[SPIRE_A] = 3;
    g.rngState = findDiceTotal(7);
    const events: BoardEvent[] = [];
    rollDice(g, events);
    expect(g.players[0]!.alive).toBe(false);
    expect(g.winner).toBeNull();
    expect(g.phase).toBe('roll');
    expect(g.current).toBe(1); // play continues with the next seat
  });

  test('net worth counts cash + property prices + upgrade spend', () => {
    const g = createBoardGame(7, [false, false]);
    g.players[0]!.money = 500;
    g.ownership[DOCK_A] = 0;
    g.levels[DOCK_A] = 0;
    g.ownership[3] = 0;
    const dock = BOARD[DOCK_A] as DistrictDef;
    expect(netWorth(g, 0)).toBe(500 + dock.price + 200);
    g.levels[DOCK_A] = 2;
    expect(netWorth(g, 0)).toBe(500 + dock.price + 200 + 2 * dock.upgradeCost);
    g.players[1]!.alive = false;
    expect(netWorth(g, 1)).toBe(0);
  });

  test('the round cap ends the game with a net-worth tiebreak', () => {
    const g = createBoardGame(7, [false, false]);
    g.turnCap = 1;
    g.players[1]!.money = 2000; // richer
    g.players[0]!.pos = 10;
    g.players[1]!.pos = 10;
    const events: BoardEvent[] = [];
    // Seat 0 then seat 1; the wrap back to seat 0 exceeds the cap.
    for (let i = 0; i < 2; i++) {
      g.rngState = findDiceTotal(4); // 10 -> 14 (free corner), 14 -> 18 (unowned)
      rollDice(g, events);
      expect(g.phase).toBe('act');
      endTurn(g, events);
    }
    expect(g.phase).toBe('over');
    expect(g.winner).toBe(1);
    const over = events.find((e) => e.kind === 'game-over');
    expect(over).toMatchObject({ reason: 'turn-cap', winner: 1 });
  });
});
