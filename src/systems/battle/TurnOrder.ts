/**
 * Round turn order — pure, no three.js/DOM. Living units act in
 * descending effective-speed order (stat stages and Servo Lag both
 * count). Speed ties break stably by unit index, so two equal-speed
 * units keep a consistent order all battle (tested).
 */

import { effectiveStat, type BattleState } from './Resolution';

export function computeTurnOrder(state: BattleState): number[] {
  const rows: Array<{ id: number; spd: number }> = [];
  for (const u of state.units) {
    if (u.alive) rows.push({ id: u.id, spd: effectiveStat(u, 'spd') });
  }
  rows.sort((a, b) => (b.spd !== a.spd ? b.spd - a.spd : a.id - b.id));
  return rows.map((r) => r.id);
}
