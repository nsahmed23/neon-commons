import { describe, expect, test } from 'vitest';
import {
  BOARD,
  SET_RENT_MULT,
  TRANSIT_RENT,
  UTILITY_RENT_MULT,
  setMembers,
  type DistrictDef,
} from '../src/systems/board/BoardData';
import {
  computeRent,
  createBoardGame,
  ownsFullSet,
  type BoardGameState,
} from '../src/systems/board/Engine';

const game = (): BoardGameState => createBoardGame(1234, [false, true, true]);

// Dockside set = spaces 1 and 4; Market set = 6, 8, 9.
const DOCK_A = 1;
const DOCK_B = 4;

describe('rent vs ownership, sets and upgrade levels', () => {
  test('unowned space charges no rent', () => {
    const g = game();
    expect(computeRent(g, DOCK_A, 7)).toBe(0);
  });

  test('base rent for a lone district comes from the level-0 table entry', () => {
    const g = game();
    g.ownership[DOCK_A] = 1;
    const def = BOARD[DOCK_A] as DistrictDef;
    expect(computeRent(g, DOCK_A, 7)).toBe(def.rent[0]);
    expect(ownsFullSet(g, DOCK_A, 1)).toBe(false);
  });

  test('completing the color set doubles level-0 rent', () => {
    const g = game();
    g.ownership[DOCK_A] = 1;
    g.ownership[DOCK_B] = 1;
    const def = BOARD[DOCK_A] as DistrictDef;
    expect(ownsFullSet(g, DOCK_A, 1)).toBe(true);
    expect(computeRent(g, DOCK_A, 7)).toBe(def.rent[0] * SET_RENT_MULT);
  });

  test('a split set does NOT double rent (real ownership state)', () => {
    const g = game();
    g.ownership[DOCK_A] = 1;
    g.ownership[DOCK_B] = 2; // different owner
    const def = BOARD[DOCK_A] as DistrictDef;
    expect(computeRent(g, DOCK_A, 7)).toBe(def.rent[0]);
  });

  test.each([[1], [2], [3]])(
    'development level %i reads its own rent-table entry for every district',
    (level) => {
      const g = game();
      for (const space of BOARD.keys()) {
        const def = BOARD[space];
        if (!def || def.kind !== 'district') continue;
        for (const m of setMembers(def.set)) g.ownership[m] = 1;
        g.levels[space] = level;
        expect(computeRent(g, space, 7)).toBe(def.rent[level as 1 | 2 | 3]);
        g.levels[space] = 0;
      }
    },
  );

  test.each([
    [1, TRANSIT_RENT[0]],
    [2, TRANSIT_RENT[1]],
    [3, TRANSIT_RENT[2]],
    [4, TRANSIT_RENT[3]],
  ])('transit rent with %i Skyrail nodes owned is %i', (count, expected) => {
    const g = game();
    const transits = [3, 10, 17, 24];
    for (let i = 0; i < count; i++) g.ownership[transits[i] as number] = 1;
    expect(computeRent(g, 3, 7)).toBe(expected);
  });

  test.each([
    [1, 7, 7 * UTILITY_RENT_MULT[0]],
    [1, 12, 12 * UTILITY_RENT_MULT[0]],
    [2, 7, 7 * UTILITY_RENT_MULT[1]],
    [2, 12, 12 * UTILITY_RENT_MULT[1]],
  ])('utility rent with %i owned and dice %i is %i', (count, dice, expected) => {
    const g = game();
    g.ownership[12] = 1;
    if (count === 2) g.ownership[20] = 1;
    expect(computeRent(g, 12, dice)).toBe(expected);
  });
});
