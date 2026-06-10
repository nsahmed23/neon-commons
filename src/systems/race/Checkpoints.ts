/**
 * Ordered checkpoint / lap logic + race standings. Pure (no Three.js,
 * no DOM): a LapTracker consumes positions and a velocity-vs-track
 * tangent dot product each fixed step and maintains lap count, lap
 * times, best lap, wrong-way and missed-checkpoint flags. Laps only
 * count after every gate has been crossed in order; crossing a later
 * gate early does nothing except raise the "missed checkpoint" flag.
 * Unit-tested without any rendering.
 */

export interface GateLike {
  x: number;
  z: number;
  r: number;
}

const WRONG_WAY_SPEED = 2; // m/s against the tangent before we care
const WRONG_WAY_DELAY = 0.6; // sustained seconds before the flag raises

export class LapTracker {
  /** completed laps */
  lap = 0;
  /** index of the next gate that counts (starts at 1; gate 0 = finish) */
  next = 1;
  /** total gates passed since the start (lap ordering key) */
  passedTotal = 0;
  finished = false;
  finishMs = 0;
  /** raised when a later gate is crossed while an earlier one is due */
  missed = false;
  wrongWay = false;
  lapTimes: number[] = [];
  bestLapMs = Infinity;
  /** ordinal of the last gate actually passed (respawn anchor) */
  lastPassed = 0;

  private raceMs = 0;
  private lapStartMs = 0;
  private wrongWayTimer = 0;

  constructor(
    private gates: readonly GateLike[],
    readonly totalLaps: number,
  ) {
    if (gates.length < 2) throw new Error('LapTracker needs at least 2 gates');
  }

  get elapsedMs(): number {
    return this.raceMs;
  }

  get currentLapMs(): number {
    return this.raceMs - this.lapStartMs;
  }

  /** Distance to the next required gate (standings tiebreaker). */
  distToNext(x: number, z: number): number {
    const g = this.gates[this.next] as GateLike;
    return Math.hypot(g.x - x, g.z - z);
  }

  /**
   * Advance one fixed step. `velDotTangent` is the dot product of the
   * vehicle velocity with the track tangent at its position (from the
   * surface query): negative means driving against the lap direction.
   */
  update(dt: number, x: number, z: number, velDotTangent: number): void {
    if (this.finished) return;
    this.raceMs += dt * 1000;

    // Wrong-way: sustained motion against the tangent.
    if (velDotTangent < -WRONG_WAY_SPEED) {
      this.wrongWayTimer += dt;
    } else if (velDotTangent > 0.5) {
      this.wrongWayTimer = 0;
    }
    this.wrongWay = this.wrongWayTimer >= WRONG_WAY_DELAY;

    // Ordered gate logic: only `next` counts.
    const m = this.gates.length;
    const nextGate = this.gates[this.next] as GateLike;
    if (within(nextGate, x, z)) {
      this.lastPassed = this.next;
      this.passedTotal++;
      this.missed = false;
      if (this.next === 0) {
        // Crossed the finish with all gates collected: lap completes.
        this.lap++;
        const lapMs = this.raceMs - this.lapStartMs;
        this.lapTimes.push(lapMs);
        if (lapMs < this.bestLapMs) this.bestLapMs = lapMs;
        this.lapStartMs = this.raceMs;
        if (this.lap >= this.totalLaps) {
          this.finished = true;
          this.finishMs = this.raceMs;
        }
      }
      this.next = (this.next + 1) % m;
      return;
    }

    // Crossing the gate AFTER the required one means a gate was skipped
    // (e.g. an off-road shortcut around a checkpoint): no progress, and
    // the HUD shows it until the missing gate is collected.
    const aheadGate = this.gates[(this.next + 1) % m] as GateLike;
    if (within(aheadGate, x, z)) {
      this.missed = true;
    }
  }
}

function within(g: GateLike, x: number, z: number): boolean {
  const dx = g.x - x;
  const dz = g.z - z;
  return dx * dx + dz * dz <= g.r * g.r;
}

// ---- Standings ---------------------------------------------------------

export interface RacerProgress {
  id: string;
  finished: boolean;
  finishMs: number;
  passedTotal: number;
  distToNext: number;
}

/**
 * Race ordering: finishers first (by finish time), then by gates
 * passed, then by who is closer to their next gate. Pure comparator
 * for Array.prototype.sort.
 */
export function compareRacers(a: RacerProgress, b: RacerProgress): number {
  if (a.finished || b.finished) {
    if (a.finished && b.finished) return a.finishMs - b.finishMs;
    return a.finished ? -1 : 1;
  }
  if (a.passedTotal !== b.passedTotal) return b.passedTotal - a.passedTotal;
  return a.distToNext - b.distToNext;
}

/** mm:ss.cc formatting for lap/race times. */
export function formatMs(ms: number): string {
  if (!Number.isFinite(ms)) return '--:--.--';
  const total = Math.max(0, Math.round(ms / 10)); // centiseconds
  const cs = total % 100;
  const s = Math.floor(total / 100) % 60;
  const min = Math.floor(total / 6000);
  return `${min}:${String(s).padStart(2, '0')}.${String(cs).padStart(2, '0')}`;
}
