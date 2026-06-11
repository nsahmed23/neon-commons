/**
 * Compact share codes for Neon Districts: the full game state (seed,
 * RNG cursor, players, ownership, levels, deck, turn machine) packed
 * into a versioned minimal array encoding, JSON-stringified and
 * base64'd with a human-readable NCB1. prefix. decode() validates
 * every field and returns null on anything malformed; a decoded state
 * is deep-equal to the encoded one, so play continues identically.
 */

import { BOARD, BOARD_SIZE, MAX_LEVEL } from './BoardData';
import { EVENT_CARDS } from './EventDeck';
import type { BoardGameState, BoardPhase } from './Engine';

export const SHARE_CODE_PREFIX = 'NCB1.';
const VERSION = 1;
const PHASES: readonly BoardPhase[] = ['roll', 'act', 'over'];

type Packed = [
  version: number,
  seed: number,
  rngState: number,
  current: number,
  round: number,
  phase: number,
  doublesCount: number,
  d1: number,
  d2: number,
  turnCap: number,
  winner: number, // -1 = none
  deckIndex: number,
  deckOrder: number[],
  players: number[], // flat [bot, money, pos, alive] per player
  ownership: number[],
  levels: number[],
];

function toBase64(s: string): string {
  // btoa exists in browsers and in Node 16+ (vitest node env).
  return btoa(s);
}

function fromBase64(s: string): string | null {
  try {
    return atob(s);
  } catch {
    return null;
  }
}

export function encodeShareCode(state: BoardGameState): string {
  const packed: Packed = [
    VERSION,
    state.seed,
    state.rngState,
    state.current,
    state.round,
    PHASES.indexOf(state.phase),
    state.doublesCount,
    state.lastRoll[0],
    state.lastRoll[1],
    state.turnCap,
    state.winner ?? -1,
    state.deckIndex,
    [...state.deckOrder],
    state.players.flatMap((p) => [p.bot ? 1 : 0, p.money, p.pos, p.alive ? 1 : 0]),
    [...state.ownership],
    [...state.levels],
  ];
  return SHARE_CODE_PREFIX + toBase64(JSON.stringify(packed));
}

const isInt = (v: unknown): v is number =>
  typeof v === 'number' && Number.isInteger(v);

const isIntArray = (v: unknown): v is number[] =>
  Array.isArray(v) && v.every(isInt);

/** Decode and validate. Returns null for anything not provably sound. */
export function decodeShareCode(code: string): BoardGameState | null {
  if (typeof code !== 'string' || !code.startsWith(SHARE_CODE_PREFIX)) return null;
  const raw = fromBase64(code.slice(SHARE_CODE_PREFIX.length).trim());
  if (raw === null) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!Array.isArray(parsed) || parsed.length !== 16) return null;
  const [
    version, seed, rngState, current, round, phase, doublesCount,
    d1, d2, turnCap, winner, deckIndex, deckOrder, playersFlat,
    ownership, levels,
  ] = parsed as unknown[];

  if (version !== VERSION) return null;
  if (![seed, rngState, current, round, phase, doublesCount, d1, d2, turnCap, winner, deckIndex]
    .every(isInt)) return null;
  if (!isIntArray(deckOrder) || !isIntArray(playersFlat) || !isIntArray(ownership) ||
    !isIntArray(levels)) return null;

  // Deck must be a permutation of 0..EVENT_CARDS.length-1.
  if (deckOrder.length !== EVENT_CARDS.length) return null;
  if ([...deckOrder].sort((a, b) => a - b).some((v, i) => v !== i)) return null;
  const di = deckIndex as number;
  if (di < 0 || di > deckOrder.length) return null;

  // Players: 2-4, flat groups of 4.
  if (playersFlat.length % 4 !== 0) return null;
  const playerCount = playersFlat.length / 4;
  if (playerCount < 2 || playerCount > 4) return null;
  const players = [];
  for (let i = 0; i < playerCount; i++) {
    const bot = playersFlat[i * 4] as number;
    const money = playersFlat[i * 4 + 1] as number;
    const pos = playersFlat[i * 4 + 2] as number;
    const alive = playersFlat[i * 4 + 3] as number;
    if ((bot !== 0 && bot !== 1) || (alive !== 0 && alive !== 1)) return null;
    if (money < 0 || pos < 0 || pos >= BOARD_SIZE) return null;
    players.push({ id: i, bot: bot === 1, money, pos, alive: alive === 1 });
  }

  if (ownership.length !== BOARD_SIZE || levels.length !== BOARD_SIZE) return null;
  for (let i = 0; i < BOARD_SIZE; i++) {
    const o = ownership[i] as number;
    const l = levels[i] as number;
    if (o < -1 || o >= playerCount) return null;
    if (l < 0 || l > MAX_LEVEL) return null;
    if (l > 0 && BOARD[i]?.kind !== 'district') return null;
  }

  const ph = PHASES[phase as number];
  if (!ph) return null;
  const cur = current as number;
  if (cur < 0 || cur >= playerCount) return null;
  const w = winner as number;
  if (w < -1 || w >= playerCount) return null;
  const dd1 = d1 as number;
  const dd2 = d2 as number;
  if (dd1 < 0 || dd1 > 6 || dd2 < 0 || dd2 > 6) return null;
  if ((round as number) < 1 || (turnCap as number) < 1) return null;
  if ((doublesCount as number) < 0 || (doublesCount as number) > 3) return null;

  return {
    seed: (seed as number) >>> 0,
    rngState: (rngState as number) >>> 0,
    players,
    ownership: [...ownership],
    levels: [...levels],
    deckOrder: [...deckOrder],
    deckIndex: di,
    current: cur,
    round: round as number,
    phase: ph,
    doublesCount: doublesCount as number,
    lastRoll: [dd1, dd2],
    turnCap: turnCap as number,
    winner: w === -1 ? null : w,
  };
}
