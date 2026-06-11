import { describe, expect, test } from 'vitest';
import { PASS_START_STIPEND } from '../src/systems/board/BoardData';
import { rngInt } from '../src/systems/board/BoardRng';
import { EVENT_CARDS } from '../src/systems/board/EventDeck';
import {
  createBoardGame,
  rollDice,
  type BoardEvent,
  type BoardGameState,
} from '../src/systems/board/Engine';

function findDiceTotal(total: number): number {
  for (let s = 1; s < 100000; s++) {
    const r1 = rngInt(s, 1, 6);
    const r2 = rngInt(r1.state, 1, 6);
    if (r1.value !== r2.value && r1.value + r2.value === total) return s;
  }
  throw new Error('no cursor');
}

function cardIndex(name: string): number {
  const i = EVENT_CARDS.findIndex((c) => c.name === name);
  if (i < 0) throw new Error(`no card ${name}`);
  return i;
}

/** Game with player 0 one roll away from the first event space. */
function atEventSpace(nextCard: string): { g: BoardGameState; events: BoardEvent[] } {
  const g = createBoardGame(11, [false, false, false]);
  g.players[0]!.pos = 26; // 26 + 4 = 30 -> wraps to 2
  g.deckOrder = [cardIndex(nextCard), ...g.deckOrder.filter((c) => c !== cardIndex(nextCard))];
  g.deckIndex = 0;
  g.rngState = findDiceTotal(4);
  return { g, events: [] };
}

describe('flux event deck', () => {
  test('deck order is a deterministic seeded permutation; seeds diverge', () => {
    const a = createBoardGame(500, [false, false]);
    const b = createBoardGame(500, [false, false]);
    const c = createBoardGame(501, [false, false]);
    expect(a.deckOrder).toEqual(b.deckOrder);
    expect(a.deckOrder).not.toEqual(c.deckOrder);
    expect([...a.deckOrder].sort((x, y) => x - y)).toEqual(
      Array.from({ length: EVENT_CARDS.length }, (_, i) => i),
    );
  });

  test('an exhausted deck reshuffles deterministically and keeps drawing', () => {
    const { g, events } = atEventSpace('Grid Dividend');
    g.deckIndex = EVENT_CARDS.length; // force exhaustion
    const twin = structuredClone(g);
    rollDice(g, events);
    expect(events.some((e) => e.kind === 'reshuffle')).toBe(true);
    expect(g.deckIndex).toBe(1);
    const twinEvents: BoardEvent[] = [];
    rollDice(twin, twinEvents);
    expect(twin.deckOrder).toEqual(g.deckOrder); // same cursor, same reshuffle
    expect(twinEvents).toEqual(events);
  });

  test('money cards credit and debit real balances', () => {
    const { g, events } = atEventSpace('Festival Crowd'); // +100
    rollDice(g, events);
    // 1500 + 200 stipend (wrapped) + 100 card
    expect(g.players[0]!.money).toBe(1500 + PASS_START_STIPEND + 100);
    expect(events).toContainEqual(
      expect.objectContaining({ kind: 'cash', amount: 100, reason: 'Festival Crowd' }),
    );
  });

  test('Spire Patches charges per development level actually owned', () => {
    const { g, events } = atEventSpace('Spire Patches'); // 40/level
    g.ownership[1] = 0;
    g.ownership[4] = 0;
    g.levels[1] = 2;
    g.levels[4] = 1;
    rollDice(g, events);
    expect(g.players[0]!.money).toBe(1500 + PASS_START_STIPEND - 3 * 40);
  });

  test('Crowdfund collects from each rival; Street Repairs pays each rival', () => {
    const a = atEventSpace('Crowdfund'); // +25 from each
    rollDice(a.g, a.events);
    expect(a.g.players[0]!.money).toBe(1500 + PASS_START_STIPEND + 50);
    expect(a.g.players[1]!.money).toBe(1475);
    expect(a.g.players[2]!.money).toBe(1475);

    const b = atEventSpace('Street Repairs'); // -25 to each
    rollDice(b.g, b.events);
    expect(b.g.players[0]!.money).toBe(1500 + PASS_START_STIPEND - 50);
    expect(b.g.players[1]!.money).toBe(1525);
    expect(b.g.players[2]!.money).toBe(1525);
  });

  test('movement cards move the pawn and resolve the destination for real', () => {
    const { g, events } = atEventSpace('Spire Invitation'); // advance to 26
    g.ownership[26] = 1; // rival owns Spire Heights, level 0, split set
    rollDice(g, events);
    expect(g.players[0]!.pos).toBe(26);
    // Stipend (wrap to 2) + rent 26 paid on arrival.
    expect(events).toContainEqual(
      expect.objectContaining({ kind: 'rent', space: 26, amount: 26 }),
    );
    expect(g.players[0]!.money).toBe(1500 + PASS_START_STIPEND - 26);
    expect(g.players[1]!.money).toBe(1500 + 26);
  });

  test('Maintenance Recall is a direct move with no stipend', () => {
    const { g, events } = atEventSpace('Maintenance Recall');
    rollDice(g, events);
    expect(g.players[0]!.pos).toBe(7);
    // Exactly one stipend: the wrap onto the event space, none for the recall.
    expect(events.filter((e) => e.kind === 'stipend').length).toBe(1);
  });

  test('Skyrail Pass rides forward to the next transit node', () => {
    const { g, events } = atEventSpace('Skyrail Pass'); // from 2 -> 3
    rollDice(g, events);
    expect(g.players[0]!.pos).toBe(3);
    expect(events.at(-1)).toMatchObject({ kind: 'land', space: 3 });
  });

  test('Wrong Exit moves back 3 and resolves the landing', () => {
    const { g, events } = atEventSpace('Wrong Exit'); // 2 - 3 -> 27
    g.ownership[27] = 2;
    rollDice(g, events);
    expect(g.players[0]!.pos).toBe(27);
    expect(events).toContainEqual(
      expect.objectContaining({ kind: 'rent', space: 27, owner: 2, amount: 30 }),
    );
  });
});
