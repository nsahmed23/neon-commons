/**
 * Global game state: the world seed (visible in the debug overlay and
 * settable via ?seed= in the URL), seeded RNG root, day/night phase,
 * and live entity counters fed by the systems that own the instances.
 */

import { Rng } from './Rng';

export class GameState {
  readonly seed: number;
  readonly rng: Rng;
  night = true; // Neon Commons wakes up at night
  modeId: string | null = null;
  paused = false;

  private entityCounts = new Map<string, number>();

  constructor(seed?: number) {
    this.seed = (seed ?? GameState.seedFromLocation()) >>> 0;
    this.rng = new Rng(this.seed);
  }

  static seedFromLocation(): number {
    if (typeof location !== 'undefined') {
      const m = location.search.match(/[?&]seed=(\d+)/);
      if (m) return parseInt(m[1] as string, 10) >>> 0;
    }
    return (Date.now() % 1_000_000_007) >>> 0;
  }

  /** Systems report how many live entities/instances they own. */
  reportEntities(label: string, count: number): void {
    this.entityCounts.set(label, count);
  }

  get totalEntities(): number {
    let total = 0;
    for (const v of this.entityCounts.values()) total += v;
    return total;
  }

  entityBreakdown(): ReadonlyMap<string, number> {
    return this.entityCounts;
  }
}
