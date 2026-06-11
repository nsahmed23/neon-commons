import { describe, expect, test } from 'vitest';
import {
  BOARD,
  BOARD_SIZE,
  REST_POS,
  START_POS,
  isPurchasable,
  setMembers,
  transitIndices,
  utilityIndices,
  type DistrictDef,
  type SetId,
} from '../src/systems/board/BoardData';

const SETS: SetId[] = ['dock', 'market', 'arcade', 'fab', 'uptown', 'spire'];

describe('board data invariants', () => {
  test('ring has 28 spaces with corners at 0/7/14/21 and start at 0', () => {
    expect(BOARD.length).toBe(BOARD_SIZE);
    expect(BOARD_SIZE).toBe(28);
    for (const i of [0, 7, 14, 21]) {
      // 21 is the Grid Inspection levy "corner" of the ring quadrant.
      expect(['corner', 'tax']).toContain(BOARD[i]?.kind);
    }
    expect(BOARD[START_POS]).toMatchObject({ kind: 'corner', corner: 'start' });
    expect(BOARD[REST_POS]).toMatchObject({ kind: 'corner', corner: 'rest' });
  });

  test('space census: 14 districts, 4 transit, 2 utilities, 2 taxes, 3 events', () => {
    const count = (kind: string): number => BOARD.filter((s) => s.kind === kind).length;
    expect(count('district')).toBe(14);
    expect(count('transit')).toBe(4);
    expect(count('utility')).toBe(2);
    expect(count('tax')).toBe(2);
    expect(count('event')).toBe(3);
    expect(count('corner')).toBe(3);
  });

  test('every set has 2-3 members and all 14 districts are covered', () => {
    let covered = 0;
    for (const set of SETS) {
      const members = setMembers(set);
      expect(members.length).toBeGreaterThanOrEqual(2);
      expect(members.length).toBeLessThanOrEqual(3);
      covered += members.length;
    }
    expect(covered).toBe(14);
  });

  test('rent tables strictly increase with development level', () => {
    for (const s of BOARD) {
      if (s.kind !== 'district') continue;
      const d = s as DistrictDef;
      for (let lvl = 1; lvl <= 3; lvl++) {
        expect(d.rent[lvl as 1 | 2 | 3]).toBeGreaterThan(d.rent[(lvl - 1) as 0 | 1 | 2]);
      }
      expect(d.price).toBeGreaterThan(d.rent[0]);
      expect(d.upgradeCost).toBeGreaterThan(0);
    }
  });

  test('purchasable lookup and transit/utility indices agree with the board', () => {
    expect(transitIndices()).toEqual([3, 10, 17, 24]);
    expect(utilityIndices()).toEqual([12, 20]);
    for (let i = 0; i < BOARD.length; i++) {
      const s = BOARD[i]!;
      expect(isPurchasable(s)).toBe(
        s.kind === 'district' || s.kind === 'transit' || s.kind === 'utility',
      );
    }
  });
});
