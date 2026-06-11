/**
 * Neon Districts rules engine. Pure and event-sourced like the battle
 * engine: every mutation emits a typed BoardEvent, and the HUD log is
 * generated exclusively by describeBoardEvent over that stream
 * (anti-faking clause). No DOM, no three.js, no Date/Math.random —
 * all randomness flows through the serializable rngState cursor so a
 * share code resumes the identical dice and deck stream.
 *
 * Turn shape: phase 'roll' -> rollDice() moves the pawn and resolves
 * the landing (rent/tax/card, with forced liquidation and bankruptcy)
 * -> phase 'act' (buy/upgrade) -> endTurn(). Rolling doubles ("echo
 * roll") grants another roll after acting; a third consecutive echo
 * triggers a Surge Recall: pay a fine, pawn recalled to the
 * Maintenance Bay, turn over. Game ends when one player remains
 * solvent, or at the round cap with a net-worth tiebreak.
 */

import {
  BOARD,
  BOARD_SIZE,
  DEFAULT_TURN_CAP,
  LIQUIDATION_FRACTION,
  MAX_LEVEL,
  PASS_START_STIPEND,
  REST_POS,
  SET_RENT_MULT,
  STARTING_MONEY,
  SURGE_RECALL_FINE,
  TRANSIT_RENT,
  UTILITY_RENT_MULT,
  isPurchasable,
  setMembers,
  spacePrice,
  transitIndices,
  utilityIndices,
  type DistrictDef,
} from './BoardData';
import { rngInt, rngShuffle } from './BoardRng';
import { EVENT_CARDS, type CardDef } from './EventDeck';

export type BoardPhase = 'roll' | 'act' | 'over';

export interface PlayerState {
  id: number;
  bot: boolean;
  money: number;
  pos: number;
  alive: boolean;
}

export interface BoardGameState {
  seed: number;
  /** Serializable mulberry32 cursor (see BoardRng). */
  rngState: number;
  players: PlayerState[];
  /** Per space: owning player id, or -1 for the bank. */
  ownership: number[];
  /** Per space: development level 0-3 (districts only). */
  levels: number[];
  /** Shuffled card indices into EVENT_CARDS. */
  deckOrder: number[];
  deckIndex: number;
  current: number;
  round: number;
  phase: BoardPhase;
  doublesCount: number;
  lastRoll: [number, number];
  turnCap: number;
  winner: number | null;
}

export type BoardEvent =
  | { kind: 'turn-start'; player: number; round: number }
  | { kind: 'roll'; player: number; d1: number; d2: number; doubles: boolean }
  | { kind: 'surge-recall'; player: number; fine: number }
  | { kind: 'move'; player: number; from: number; to: number; passedStart: boolean }
  | { kind: 'stipend'; player: number; amount: number }
  | { kind: 'land'; player: number; space: number }
  | {
      kind: 'rent';
      player: number;
      owner: number;
      space: number;
      amount: number;
      level: number;
      setBonus: boolean;
      diceTotal: number;
    }
  | { kind: 'tax'; player: number; space: number; amount: number }
  | { kind: 'buy'; player: number; space: number; price: number }
  | { kind: 'upgrade'; player: number; space: number; level: number; cost: number }
  | { kind: 'rejected'; player: number; action: 'buy' | 'upgrade'; reason: string }
  | { kind: 'card'; player: number; card: number }
  | { kind: 'cash'; player: number; amount: number; reason: string }
  | { kind: 'reshuffle' }
  | { kind: 'liquidate-upgrade'; player: number; space: number; level: number; refund: number }
  | { kind: 'liquidate-property'; player: number; space: number; refund: number }
  | { kind: 'bankrupt'; player: number; creditor: number | null }
  | { kind: 'turn-end'; player: number; extraTurn: boolean }
  | {
      kind: 'game-over';
      winner: number;
      reason: 'last-solvent' | 'turn-cap';
      netWorths: number[];
    };

// ---- construction ---------------------------------------------------------

export function createBoardGame(
  seed: number,
  bots: readonly boolean[],
  turnCap = DEFAULT_TURN_CAP,
): BoardGameState {
  if (bots.length < 2 || bots.length > 4) {
    throw new Error('Neon Districts is for 2-4 players');
  }
  const shuffled = rngShuffle(seed >>> 0, EVENT_CARDS.length);
  return {
    seed: seed >>> 0,
    rngState: shuffled.state,
    players: bots.map((bot, id) => ({
      id,
      bot,
      money: STARTING_MONEY,
      pos: 0,
      alive: true,
    })),
    ownership: BOARD.map(() => -1),
    levels: BOARD.map(() => 0),
    deckOrder: shuffled.order,
    deckIndex: 0,
    current: 0,
    round: 1,
    phase: 'roll',
    doublesCount: 0,
    lastRoll: [0, 0],
    turnCap,
    winner: null,
  };
}

export function playerName(state: BoardGameState, id: number): string {
  const p = state.players[id];
  if (!p) return `Seat ${id + 1}`;
  return p.bot ? `Bot ${id + 1}` : `Player ${id + 1}`;
}

// ---- queries ----------------------------------------------------------------

/** True if `owner` holds every district of the set `space` belongs to. */
export function ownsFullSet(state: BoardGameState, space: number, owner: number): boolean {
  const def = BOARD[space];
  if (!def || def.kind !== 'district') return false;
  return setMembers(def.set).every((i) => state.ownership[i] === owner);
}

/** Rent owed for landing on `space` (0 if unowned). Pure; table-tested. */
export function computeRent(state: BoardGameState, space: number, diceTotal: number): number {
  const def = BOARD[space];
  const owner = state.ownership[space] ?? -1;
  if (!def || owner < 0) return 0;
  if (def.kind === 'district') {
    const level = state.levels[space] ?? 0;
    if (level > 0) return def.rent[level as 1 | 2 | 3];
    return ownsFullSet(state, space, owner) ? def.rent[0] * SET_RENT_MULT : def.rent[0];
  }
  if (def.kind === 'transit') {
    const count = transitIndices().filter((i) => state.ownership[i] === owner).length;
    return TRANSIT_RENT[Math.min(3, Math.max(0, count - 1))] ?? 0;
  }
  if (def.kind === 'utility') {
    const count = utilityIndices().filter((i) => state.ownership[i] === owner).length;
    return diceTotal * (UTILITY_RENT_MULT[Math.min(1, Math.max(0, count - 1))] ?? 0);
  }
  return 0;
}

/** Full asset value: cash + property prices + upgrade spend. */
export function netWorth(state: BoardGameState, player: number): number {
  const p = state.players[player];
  if (!p || !p.alive) return 0;
  let total = p.money;
  for (let i = 0; i < BOARD.length; i++) {
    if (state.ownership[i] !== player) continue;
    const def = BOARD[i];
    if (!def) continue;
    total += spacePrice(def);
    if (def.kind === 'district') total += (state.levels[i] ?? 0) * def.upgradeCost;
  }
  return total;
}

/** Districts `player` may upgrade right now (full set, level < 3). */
export function upgradableDistricts(state: BoardGameState, player: number): number[] {
  const out: number[] = [];
  for (let i = 0; i < BOARD.length; i++) {
    const def = BOARD[i];
    if (!def || def.kind !== 'district') continue;
    if (state.ownership[i] !== player) continue;
    if ((state.levels[i] ?? 0) >= MAX_LEVEL) continue;
    if (!ownsFullSet(state, i, player)) continue;
    out.push(i);
  }
  return out;
}

/** Can the current player buy the space under their pawn? */
export function canBuyCurrent(state: BoardGameState): { ok: boolean; reason: string } {
  if (state.phase !== 'act') return { ok: false, reason: 'not in the action phase' };
  const p = state.players[state.current];
  if (!p || !p.alive) return { ok: false, reason: 'player is out' };
  const def = BOARD[p.pos];
  if (!def || !isPurchasable(def)) return { ok: false, reason: 'space is not for sale' };
  if ((state.ownership[p.pos] ?? -1) !== -1) return { ok: false, reason: 'already owned' };
  if (p.money < def.price) return { ok: false, reason: 'insufficient funds' };
  return { ok: true, reason: '' };
}

// ---- forced payments / liquidation / bankruptcy ------------------------------

/**
 * Charge `amount` to `payer`, liquidating assets if cash is short:
 * developments sell back first (highest level, then lowest index) at
 * half the upgrade cost, then properties (cheapest, then lowest index)
 * at half price. If everything is gone and the debt still stands, the
 * payer is bankrupt: the creditor receives what was recovered and the
 * player leaves the game. Returns the amount actually paid.
 */
function charge(
  state: BoardGameState,
  payerId: number,
  amount: number,
  creditorId: number | null,
  events: BoardEvent[],
): number {
  const payer = state.players[payerId];
  if (!payer || !payer.alive || amount <= 0) return 0;

  while (payer.money < amount) {
    // 1) Sell back a development: highest level first, then lowest index.
    let bestUpgrade = -1;
    let bestLevel = 0;
    for (let i = 0; i < BOARD.length; i++) {
      const lvl = state.levels[i] ?? 0;
      if (state.ownership[i] === payerId && lvl > bestLevel) {
        bestLevel = lvl;
        bestUpgrade = i;
      }
    }
    if (bestUpgrade >= 0) {
      const def = BOARD[bestUpgrade] as DistrictDef;
      const refund = Math.floor(def.upgradeCost * LIQUIDATION_FRACTION);
      state.levels[bestUpgrade] = bestLevel - 1;
      payer.money += refund;
      events.push({
        kind: 'liquidate-upgrade',
        player: payerId,
        space: bestUpgrade,
        level: bestLevel - 1,
        refund,
      });
      continue;
    }
    // 2) Sell a property to the bank: cheapest first, then lowest index.
    let bestProp = -1;
    let bestPrice = Infinity;
    for (let i = 0; i < BOARD.length; i++) {
      if (state.ownership[i] !== payerId) continue;
      const def = BOARD[i];
      if (!def) continue;
      const price = spacePrice(def);
      if (price < bestPrice) {
        bestPrice = price;
        bestProp = i;
      }
    }
    if (bestProp >= 0) {
      const refund = Math.floor(bestPrice * LIQUIDATION_FRACTION);
      state.ownership[bestProp] = -1;
      payer.money += refund;
      events.push({ kind: 'liquidate-property', player: payerId, space: bestProp, refund });
      continue;
    }
    break; // nothing left to liquidate
  }

  if (payer.money >= amount) {
    payer.money -= amount;
    const creditor = creditorId !== null ? state.players[creditorId] : undefined;
    if (creditor && creditor.alive) creditor.money += amount;
    return amount;
  }

  // Bankruptcy: hand over the remainder and leave the game.
  const paid = payer.money;
  payer.money = 0;
  payer.alive = false;
  for (let i = 0; i < BOARD.length; i++) {
    if (state.ownership[i] === payerId) {
      state.ownership[i] = -1;
      state.levels[i] = 0;
    }
  }
  const creditor = creditorId !== null ? state.players[creditorId] : undefined;
  if (creditor && creditor.alive) creditor.money += paid;
  events.push({ kind: 'bankrupt', player: payerId, creditor: creditorId });
  return paid;
}

// ---- movement + landing resolution -------------------------------------------

function movePawn(
  state: BoardGameState,
  playerId: number,
  to: number,
  collectStart: boolean,
  events: BoardEvent[],
): void {
  const p = state.players[playerId];
  if (!p) return;
  const from = p.pos;
  const passedStart = collectStart && (to <= from || to === 0) && to !== from;
  p.pos = to;
  events.push({ kind: 'move', player: playerId, from, to, passedStart });
  if (passedStart) {
    p.money += PASS_START_STIPEND;
    events.push({ kind: 'stipend', player: playerId, amount: PASS_START_STIPEND });
  }
}

function drawCard(state: BoardGameState, events: BoardEvent[]): CardDef {
  if (state.deckIndex >= state.deckOrder.length) {
    const shuffled = rngShuffle(state.rngState, EVENT_CARDS.length);
    state.rngState = shuffled.state;
    state.deckOrder = shuffled.order;
    state.deckIndex = 0;
    events.push({ kind: 'reshuffle' });
  }
  const idx = state.deckOrder[state.deckIndex] as number;
  state.deckIndex++;
  return EVENT_CARDS[idx] as CardDef;
}

function resolveLanding(state: BoardGameState, playerId: number, events: BoardEvent[]): void {
  const p = state.players[playerId];
  if (!p || !p.alive) return;
  const space = p.pos;
  const def = BOARD[space];
  if (!def) return;
  events.push({ kind: 'land', player: playerId, space });

  if (isPurchasable(def)) {
    const owner = state.ownership[space] ?? -1;
    if (owner >= 0 && owner !== playerId && state.players[owner]?.alive) {
      const diceTotal = state.lastRoll[0] + state.lastRoll[1];
      const amount = computeRent(state, space, diceTotal);
      events.push({
        kind: 'rent',
        player: playerId,
        owner,
        space,
        amount,
        level: state.levels[space] ?? 0,
        setBonus:
          def.kind === 'district' &&
          (state.levels[space] ?? 0) === 0 &&
          ownsFullSet(state, space, owner),
        diceTotal,
      });
      charge(state, playerId, amount, owner, events);
    }
    return;
  }

  if (def.kind === 'tax') {
    events.push({ kind: 'tax', player: playerId, space, amount: def.amount });
    charge(state, playerId, def.amount, null, events);
    return;
  }

  if (def.kind === 'event') {
    const card = drawCard(state, events);
    events.push({ kind: 'card', player: playerId, card: EVENT_CARDS.indexOf(card) });
    applyCard(state, playerId, card, events);
    return;
  }
  // corners: nothing to resolve (the stipend handled landing on start)
}

function applyCard(
  state: BoardGameState,
  playerId: number,
  card: CardDef,
  events: BoardEvent[],
): void {
  const p = state.players[playerId];
  if (!p || !p.alive) return;
  const e = card.effect;
  switch (e.type) {
    case 'money':
      events.push({ kind: 'cash', player: playerId, amount: e.amount, reason: card.name });
      if (e.amount >= 0) p.money += e.amount;
      else charge(state, playerId, -e.amount, null, events);
      break;
    case 'perLevel': {
      let levels = 0;
      for (let i = 0; i < BOARD.length; i++) {
        if (state.ownership[i] === playerId) levels += state.levels[i] ?? 0;
      }
      const owed = levels * e.amount;
      events.push({ kind: 'cash', player: playerId, amount: -owed, reason: card.name });
      if (owed > 0) charge(state, playerId, owed, null, events);
      break;
    }
    case 'fromEach': {
      let received = 0;
      for (const rival of state.players) {
        if (rival.id === playerId || !rival.alive) continue;
        received += charge(state, rival.id, e.amount, playerId, events);
      }
      events.push({ kind: 'cash', player: playerId, amount: received, reason: card.name });
      break;
    }
    case 'toEach':
      for (const rival of state.players) {
        if (rival.id === playerId || !rival.alive || !p.alive) continue;
        events.push({ kind: 'cash', player: playerId, amount: -e.amount, reason: card.name });
        charge(state, playerId, e.amount, rival.id, events);
      }
      break;
    case 'moveTo':
      movePawn(state, playerId, e.pos, e.collectStart, events);
      resolveLanding(state, playerId, events);
      break;
    case 'moveBy': {
      const to = (p.pos + e.delta + BOARD_SIZE) % BOARD_SIZE;
      movePawn(state, playerId, to, false, events);
      resolveLanding(state, playerId, events);
      break;
    }
    case 'toNearestTransit': {
      const transits = transitIndices();
      let to = -1;
      for (let step = 1; step <= BOARD_SIZE; step++) {
        const cand = (p.pos + step) % BOARD_SIZE;
        if (transits.includes(cand)) {
          to = cand;
          break;
        }
      }
      if (to >= 0) {
        movePawn(state, playerId, to, true, events);
        resolveLanding(state, playerId, events);
      }
      break;
    }
  }
}

// ---- player-facing actions ----------------------------------------------------

/** Roll, move, resolve. Returns false if rolling is not legal right now. */
export function rollDice(state: BoardGameState, events: BoardEvent[]): boolean {
  if (state.phase !== 'roll' || state.winner !== null) return false;
  const p = state.players[state.current];
  if (!p || !p.alive) return false;

  const r1 = rngInt(state.rngState, 1, 6);
  const r2 = rngInt(r1.state, 1, 6);
  state.rngState = r2.state;
  const d1 = r1.value;
  const d2 = r2.value;
  const doubles = d1 === d2;
  state.lastRoll = [d1, d2];
  if (doubles) state.doublesCount++;
  events.push({ kind: 'roll', player: p.id, d1, d2, doubles });

  if (doubles && state.doublesCount >= 3) {
    // Surge Recall: third echo in a row overloads the grid.
    events.push({ kind: 'surge-recall', player: p.id, fine: SURGE_RECALL_FINE });
    charge(state, p.id, SURGE_RECALL_FINE, null, events);
    if (p.alive) movePawn(state, p.id, REST_POS, false, events);
    advanceTurn(state, events);
    return true;
  }

  const to = (p.pos + d1 + d2) % BOARD_SIZE;
  movePawn(state, p.id, to, true, events);
  resolveLanding(state, p.id, events);

  if (!p.alive) {
    advanceTurn(state, events);
    return true;
  }
  state.phase = 'act';
  return true;
}

/** Buy the space under the current pawn. Rejections emit a typed event. */
export function buyCurrent(state: BoardGameState, events: BoardEvent[]): boolean {
  const p = state.players[state.current];
  if (!p) return false;
  const check = canBuyCurrent(state);
  if (!check.ok) {
    events.push({ kind: 'rejected', player: p.id, action: 'buy', reason: check.reason });
    return false;
  }
  const def = BOARD[p.pos];
  if (!def || !isPurchasable(def)) return false;
  p.money -= def.price;
  state.ownership[p.pos] = p.id;
  events.push({ kind: 'buy', player: p.id, space: p.pos, price: def.price });
  return true;
}

/** Develop a district one level (requires the full color set). */
export function upgradeDistrict(
  state: BoardGameState,
  space: number,
  events: BoardEvent[],
): boolean {
  const p = state.players[state.current];
  const def = BOARD[space];
  const reject = (reason: string): false => {
    events.push({ kind: 'rejected', player: state.current, action: 'upgrade', reason });
    return false;
  };
  if (state.phase !== 'act' || !p || !p.alive) return reject('not in the action phase');
  if (!def || def.kind !== 'district') return reject('not a district');
  if (state.ownership[space] !== p.id) return reject('not yours');
  if (!ownsFullSet(state, space, p.id)) return reject('full color set required');
  const level = state.levels[space] ?? 0;
  if (level >= MAX_LEVEL) return reject('already at maximum development');
  if (p.money < def.upgradeCost) return reject('insufficient funds');
  p.money -= def.upgradeCost;
  state.levels[space] = level + 1;
  events.push({
    kind: 'upgrade',
    player: p.id,
    space,
    level: level + 1,
    cost: def.upgradeCost,
  });
  return true;
}

/** End the action phase; echo rolls (doubles) grant another roll. */
export function endTurn(state: BoardGameState, events: BoardEvent[]): boolean {
  if (state.phase !== 'act' || state.winner !== null) return false;
  const p = state.players[state.current];
  if (!p) return false;
  const [d1, d2] = state.lastRoll;
  const extra = p.alive && d1 === d2 && d1 > 0 && state.doublesCount < 3;
  events.push({ kind: 'turn-end', player: p.id, extraTurn: extra });
  if (extra) {
    state.phase = 'roll';
    return true;
  }
  advanceTurn(state, events);
  return true;
}

function endGame(
  state: BoardGameState,
  reason: 'last-solvent' | 'turn-cap',
  events: BoardEvent[],
): void {
  const worths = state.players.map((pl) => netWorth(state, pl.id));
  let winner = -1;
  let best = -1;
  for (const pl of state.players) {
    if (!pl.alive) continue;
    const w = worths[pl.id] ?? 0;
    if (w > best) {
      best = w;
      winner = pl.id; // ties go to the earliest seat
    }
  }
  state.winner = winner;
  state.phase = 'over';
  events.push({ kind: 'game-over', winner, reason, netWorths: worths });
}

function advanceTurn(state: BoardGameState, events: BoardEvent[]): void {
  state.doublesCount = 0;
  state.lastRoll = [0, 0];
  if (state.winner !== null) return;

  const aliveCount = state.players.filter((pl) => pl.alive).length;
  if (aliveCount <= 1) {
    endGame(state, 'last-solvent', events);
    return;
  }

  for (let i = 1; i <= state.players.length; i++) {
    const cand = (state.current + i) % state.players.length;
    const pl = state.players[cand];
    if (!pl || !pl.alive) continue;
    const wrapped = cand <= state.current;
    if (wrapped) {
      state.round++;
      if (state.round > state.turnCap) {
        endGame(state, 'turn-cap', events);
        return;
      }
    }
    state.current = cand;
    state.phase = 'roll';
    events.push({ kind: 'turn-start', player: cand, round: state.round });
    return;
  }
}

// ---- event -> sentence (the only source of log lines) --------------------------

export function describeBoardEvent(state: BoardGameState, e: BoardEvent): string {
  const name = (id: number): string => playerName(state, id);
  const space = (i: number): string => BOARD[i]?.name ?? `Space ${i}`;
  switch (e.kind) {
    case 'turn-start':
      return `— Round ${e.round}: ${name(e.player)} to roll —`;
    case 'roll':
      return `${name(e.player)} rolls ${e.d1} + ${e.d2}${e.doubles ? ' — echo roll!' : ''}.`;
    case 'surge-recall':
      return `${name(e.player)} overloads the grid (three echoes) — fined ${e.fine} cr and recalled to the Maintenance Bay.`;
    case 'move':
      return `${name(e.player)} advances to ${space(e.to)}.`;
    case 'stipend':
      return `${name(e.player)} passes Plaza Gate and collects ${e.amount} cr.`;
    case 'land':
      return `${name(e.player)} lands on ${space(e.space)}.`;
    case 'rent': {
      const detail =
        BOARD[e.space]?.kind === 'utility'
          ? ` (dice ${e.diceTotal})`
          : e.setBonus
            ? ' (full set, doubled)'
            : e.level > 0
              ? ` (level ${e.level})`
              : '';
      return `${name(e.player)} pays ${e.amount} cr rent to ${name(e.owner)} for ${space(e.space)}${detail}.`;
    }
    case 'tax':
      return `${name(e.player)} pays the ${space(e.space)}: ${e.amount} cr.`;
    case 'buy':
      return `${name(e.player)} buys ${space(e.space)} for ${e.price} cr.`;
    case 'upgrade':
      return `${name(e.player)} develops ${space(e.space)} to level ${e.level} for ${e.cost} cr.`;
    case 'rejected':
      return `${name(e.player)} cannot ${e.action}: ${e.reason}.`;
    case 'card': {
      const card = EVENT_CARDS[e.card];
      return `${name(e.player)} draws "${card?.name ?? '?'}" — ${card?.text ?? ''}`;
    }
    case 'cash':
      return e.amount >= 0
        ? `${name(e.player)} collects ${e.amount} cr (${e.reason}).`
        : `${name(e.player)} owes ${-e.amount} cr (${e.reason}).`;
    case 'reshuffle':
      return 'The Flux Event deck is reshuffled.';
    case 'liquidate-upgrade':
      return `${name(e.player)} sells a development on ${space(e.space)} (now level ${e.level}) for ${e.refund} cr.`;
    case 'liquidate-property':
      return `${name(e.player)} sells ${space(e.space)} back to the bank for ${e.refund} cr.`;
    case 'bankrupt':
      return `${name(e.player)} is bankrupt${e.creditor !== null ? `; remaining assets go to ${name(e.creditor)}` : ''} — out of the game.`;
    case 'turn-end':
      return e.extraTurn
        ? `${name(e.player)} ends the action phase — echo roll grants another turn.`
        : `${name(e.player)} ends their turn.`;
    case 'game-over': {
      const worths = e.netWorths.map((w, i) => `${name(i)} ${w}`).join(', ');
      return `GAME OVER — ${name(e.winner)} wins (${
        e.reason === 'last-solvent' ? 'last solvent player' : 'round cap, highest net worth'
      }). Net worth: ${worths}.`;
    }
  }
}
