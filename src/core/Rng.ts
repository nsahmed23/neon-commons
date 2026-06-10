/**
 * Seeded deterministic RNG (mulberry32). Pure, no globals.
 * Every world-generation decision flows through an Rng instance so a
 * given seed always produces the same world.
 */

/** Raw mulberry32 generator: returns a function yielding floats in [0, 1). */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Deterministic 32-bit string hash (FNV-1a) used to derive child seeds. */
export function hashString(str: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

export class Rng {
  readonly seed: number;
  private readonly gen: () => number;

  constructor(seed: number) {
    this.seed = seed >>> 0;
    this.gen = mulberry32(this.seed);
  }

  /** Float in [0, 1). */
  next(): number {
    return this.gen();
  }

  /** Float in [min, max). */
  range(min: number, max: number): number {
    return min + (max - min) * this.gen();
  }

  /** Integer in [min, max] inclusive. */
  int(min: number, max: number): number {
    return min + Math.floor(this.gen() * (max - min + 1));
  }

  /** True with probability p. */
  chance(p: number): boolean {
    return this.gen() < p;
  }

  /** Pick a random element (throws on empty array). */
  pick<T>(arr: readonly T[]): T {
    if (arr.length === 0) throw new Error('Rng.pick: empty array');
    return arr[this.int(0, arr.length - 1)] as T;
  }

  /**
   * Derive an independent child generator from a label. Forking keeps
   * subsystems (city, trees, lamps...) decoupled: adding draws to one
   * does not shift the sequence of another.
   */
  fork(label: string): Rng {
    return new Rng((this.seed ^ hashString(label)) >>> 0);
  }
}
