/**
 * Deterministic bot policy for Neon Districts. Pure: given a state in
 * the action phase, returns the ordered actions the bot will take, so
 * tests can assert the exact plan. Policy (documented, simple):
 *   1. Buy the space under the pawn if unowned and cash minus price
 *      stays above the buy reserve (150 cr).
 *   2. Develop up to two districts per turn, cheapest upgrade first,
 *      while cash stays above the build reserve (300 cr).
 *   3. End the turn.
 */

import { BOARD, isPurchasable, type DistrictDef } from './BoardData';
import {
  canBuyCurrent,
  upgradableDistricts,
  type BoardGameState,
} from './Engine';

export const BOT_BUY_RESERVE = 150;
export const BOT_BUILD_RESERVE = 300;
export const BOT_MAX_UPGRADES_PER_TURN = 2;

export type BotAction =
  | { type: 'buy' }
  | { type: 'upgrade'; space: number }
  | { type: 'end' };

export function botActions(state: BoardGameState): BotAction[] {
  const out: BotAction[] = [];
  const p = state.players[state.current];
  if (!p || !p.alive || state.phase !== 'act') return [{ type: 'end' }];

  let cash = p.money;
  const here = BOARD[p.pos];
  if (here && isPurchasable(here) && canBuyCurrent(state).ok) {
    if (cash - here.price >= BOT_BUY_RESERVE) {
      out.push({ type: 'buy' });
      cash -= here.price;
    }
  }

  // Cheapest-first development plan against the *current* level map.
  const candidates = upgradableDistricts(state, p.id)
    .map((space) => ({ space, cost: (BOARD[space] as DistrictDef).upgradeCost }))
    .sort((a, b) => a.cost - b.cost || a.space - b.space);
  let built = 0;
  for (const c of candidates) {
    if (built >= BOT_MAX_UPGRADES_PER_TURN) break;
    if (cash - c.cost < BOT_BUILD_RESERVE) continue;
    out.push({ type: 'upgrade', space: c.space });
    cash -= c.cost;
    built++;
  }

  out.push({ type: 'end' });
  return out;
}
