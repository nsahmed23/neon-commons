import { describe, expect, test } from 'vitest';
import { botActions } from '../src/systems/board/Bot';
import {
  buyCurrent,
  createBoardGame,
  endTurn,
  rollDice,
  upgradeDistrict,
  type BoardEvent,
  type BoardGameState,
} from '../src/systems/board/Engine';
import {
  SHARE_CODE_PREFIX,
  decodeShareCode,
  encodeShareCode,
} from '../src/systems/board/ShareCode';

/** Play n scripted bot turns to dirty every part of the state. */
function playTurns(g: BoardGameState, turns: number): void {
  const events: BoardEvent[] = [];
  for (let i = 0; i < turns && g.phase !== 'over'; i++) {
    rollDice(g, events);
    if (g.phase !== 'act') continue; // surge recall / bankruptcy ended the turn
    for (const a of botActions(g)) {
      if (a.type === 'buy') buyCurrent(g, events);
      else if (a.type === 'upgrade') upgradeDistrict(g, a.space, events);
      else endTurn(g, events);
    }
  }
}

describe('share codes', () => {
  test('round-trip of a fresh game is deep-equal', () => {
    const g = createBoardGame(2024, [false, true, true, false]);
    const restored = decodeShareCode(encodeShareCode(g));
    expect(restored).toEqual(g);
  });

  test('round-trip after many scripted turns restores the IDENTICAL state', () => {
    const g = createBoardGame(777, [true, true, true]);
    playTurns(g, 40);
    const code = encodeShareCode(g);
    expect(code.startsWith(SHARE_CODE_PREFIX)).toBe(true);
    const restored = decodeShareCode(code);
    expect(restored).toEqual(g); // deep equality, every field
  });

  test('a restored game continues exactly like the original', () => {
    const g = createBoardGame(31337, [true, true]);
    playTurns(g, 12);
    const twin = decodeShareCode(encodeShareCode(g));
    expect(twin).not.toBeNull();
    playTurns(g, 10);
    playTurns(twin as BoardGameState, 10);
    expect(twin).toEqual(g);
  });

  test('codes are compact text', () => {
    const g = createBoardGame(99999, [false, true, true, true]);
    playTurns(g, 30);
    const code = encodeShareCode(g);
    expect(code.length).toBeLessThan(600);
    expect(code).toMatch(/^NCB1\.[A-Za-z0-9+/=]+$/);
  });

  test('malformed input returns null, never throws', () => {
    expect(decodeShareCode('')).toBeNull();
    expect(decodeShareCode('garbage')).toBeNull();
    expect(decodeShareCode('NCB1.!!!not-base64!!!')).toBeNull();
    expect(decodeShareCode(`${SHARE_CODE_PREFIX}${btoa('{"not":"an array"}')}`)).toBeNull();
    expect(decodeShareCode(`${SHARE_CODE_PREFIX}${btoa('[2]')}`)).toBeNull();
  });

  test('tampered fields are rejected by validation', () => {
    const g = createBoardGame(42, [false, true]);
    const tamper = (mutate: (s: BoardGameState) => void): string => {
      const s = structuredClone(g);
      mutate(s);
      return encodeShareCode(s);
    };
    // Out-of-range pawn position.
    expect(decodeShareCode(tamper((s) => (s.players[0]!.pos = 99)))).toBeNull();
    // Ownership pointing at a non-existent player.
    expect(decodeShareCode(tamper((s) => (s.ownership[1] = 7)))).toBeNull();
    // Development level on a non-district space.
    expect(decodeShareCode(tamper((s) => (s.levels[3] = 2)))).toBeNull();
    // Deck no longer a permutation.
    expect(decodeShareCode(tamper((s) => (s.deckOrder[0] = s.deckOrder[1] as number)))).toBeNull();
    // Level beyond the cap.
    expect(decodeShareCode(tamper((s) => (s.levels[1] = 9)))).toBeNull();
  });
});
