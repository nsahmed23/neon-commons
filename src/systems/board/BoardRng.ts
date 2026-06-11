/**
 * Serializable seeded RNG for the board engine. Same mulberry32 math
 * as core/Rng, but the 32-bit cursor lives IN the game state instead
 * of a closure, so a share code can capture it and a restored game
 * continues the identical dice/deck stream. Pure functions only.
 */

/** One mulberry32 step: returns the next cursor and a float in [0, 1). */
export function rngStep(state: number): { state: number; value: number } {
  let a = (state + 0x6d2b79f5) | 0;
  let t = Math.imul(a ^ (a >>> 15), 1 | a);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
  return { state: a >>> 0, value: ((t ^ (t >>> 14)) >>> 0) / 4294967296 };
}

/** Integer in [min, max] inclusive, advancing the cursor. */
export function rngInt(
  state: number,
  min: number,
  max: number,
): { state: number; value: number } {
  const r = rngStep(state);
  return { state: r.state, value: min + Math.floor(r.value * (max - min + 1)) };
}

/**
 * Deterministic Fisher-Yates shuffle of [0..n). Returns the order and
 * the advanced cursor; used for the Flux Event deck (and reshuffles).
 */
export function rngShuffle(
  state: number,
  n: number,
): { state: number; order: number[] } {
  const order: number[] = [];
  for (let i = 0; i < n; i++) order.push(i);
  let s = state;
  for (let i = n - 1; i > 0; i--) {
    const r = rngInt(s, 0, i);
    s = r.state;
    const tmp = order[i] as number;
    order[i] = order[r.value] as number;
    order[r.value] = tmp;
  }
  return { state: s, order };
}
