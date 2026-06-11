import { describe, expect, test } from 'vitest';
import { BOARD, type DistrictDef } from '../src/systems/board/BoardData';
import {
  buyCurrent,
  canBuyCurrent,
  createBoardGame,
  upgradableDistricts,
  upgradeDistrict,
  type BoardEvent,
  type BoardGameState,
} from '../src/systems/board/Engine';

const DOCK_A = 1;
const DOCK_B = 4;
const MARKET_A = 6;

/** A game frozen mid-turn in the action phase with the pawn placed. */
function inAct(pos: number, money = 1500): BoardGameState {
  const g = createBoardGame(99, [false, true]);
  g.phase = 'act';
  g.players[0]!.pos = pos;
  g.players[0]!.money = money;
  return g;
}

describe('buying rules', () => {
  test('buying an unowned district transfers money and sets real ownership', () => {
    const g = inAct(DOCK_A);
    const events: BoardEvent[] = [];
    const price = (BOARD[DOCK_A] as DistrictDef).price;
    expect(buyCurrent(g, events)).toBe(true);
    expect(g.players[0]!.money).toBe(1500 - price);
    expect(g.ownership[DOCK_A]).toBe(0);
    expect(events).toContainEqual({ kind: 'buy', player: 0, space: DOCK_A, price });
  });

  test('insufficient funds are rejected with a typed event and no state change', () => {
    const g = inAct(DOCK_A, 10);
    const events: BoardEvent[] = [];
    expect(buyCurrent(g, events)).toBe(false);
    expect(g.players[0]!.money).toBe(10);
    expect(g.ownership[DOCK_A]).toBe(-1);
    expect(events).toContainEqual({
      kind: 'rejected', player: 0, action: 'buy', reason: 'insufficient funds',
    });
  });

  test('an owned space cannot be bought again', () => {
    const g = inAct(DOCK_A);
    g.ownership[DOCK_A] = 1;
    const events: BoardEvent[] = [];
    expect(buyCurrent(g, events)).toBe(false);
    expect(canBuyCurrent(g).reason).toBe('already owned');
  });

  test('non-purchasable spaces and the roll phase are rejected', () => {
    const g = inAct(5); // Civic Levy
    expect(canBuyCurrent(g).reason).toBe('space is not for sale');
    const g2 = inAct(DOCK_A);
    g2.phase = 'roll';
    expect(canBuyCurrent(g2).reason).toBe('not in the action phase');
  });
});

describe('development (upgrade) rules', () => {
  test('upgrading requires the full color set', () => {
    const g = inAct(DOCK_A);
    g.ownership[DOCK_A] = 0; // only half the dock set
    const events: BoardEvent[] = [];
    expect(upgradeDistrict(g, DOCK_A, events)).toBe(false);
    expect(events).toContainEqual({
      kind: 'rejected', player: 0, action: 'upgrade', reason: 'full color set required',
    });
    expect(g.levels[DOCK_A]).toBe(0);
  });

  test('with the full set, upgrades spend money and raise the real level', () => {
    const g = inAct(DOCK_A);
    g.ownership[DOCK_A] = 0;
    g.ownership[DOCK_B] = 0;
    const events: BoardEvent[] = [];
    const cost = (BOARD[DOCK_A] as DistrictDef).upgradeCost;
    expect(upgradableDistricts(g, 0)).toEqual([DOCK_A, DOCK_B]);
    expect(upgradeDistrict(g, DOCK_A, events)).toBe(true);
    expect(g.levels[DOCK_A]).toBe(1);
    expect(g.players[0]!.money).toBe(1500 - cost);
    expect(events).toContainEqual({
      kind: 'upgrade', player: 0, space: DOCK_A, level: 1, cost,
    });
  });

  test('upgrades cap at level 3 and reject insufficient funds', () => {
    const g = inAct(DOCK_A);
    g.ownership[DOCK_A] = 0;
    g.ownership[DOCK_B] = 0;
    g.levels[DOCK_A] = 3;
    const events: BoardEvent[] = [];
    expect(upgradeDistrict(g, DOCK_A, events)).toBe(false);
    expect(events.at(-1)).toMatchObject({ reason: 'already at maximum development' });
    g.players[0]!.money = 5;
    expect(upgradeDistrict(g, DOCK_B, events)).toBe(false);
    expect(events.at(-1)).toMatchObject({ reason: 'insufficient funds' });
    expect(g.levels[DOCK_B]).toBe(0);
  });

  test("you cannot develop a rival's district or a non-district", () => {
    const g = inAct(DOCK_A);
    g.ownership[MARKET_A] = 1;
    const events: BoardEvent[] = [];
    expect(upgradeDistrict(g, MARKET_A, events)).toBe(false);
    expect(events.at(-1)).toMatchObject({ reason: 'not yours' });
    expect(upgradeDistrict(g, 3, events)).toBe(false); // Skyrail North
    expect(events.at(-1)).toMatchObject({ reason: 'not a district' });
  });
});
