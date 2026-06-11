/**
 * Flight course: an ordered ring sequence threading the hub city, plus
 * the RingTracker that enforces the order. Pure (no Three.js, no DOM).
 *
 * This extends the race Checkpoints pattern (src/systems/race/
 * Checkpoints.ts — ordered gates, "missed" flag when a later gate is
 * crossed early, lastPassed respawn anchor) from 2D lap circuits to a
 * 3D single-pass course: rings are spheres in space, passes count only
 * in order, and the course is generated deterministically from the
 * SAME WorldData buildings the hub renders, so rings genuinely clear
 * the real skyline instead of clipping through it.
 */

import { Rng } from '../../core/Rng';

export interface Ring {
  x: number;
  y: number;
  z: number;
  /** pass radius, meters (sphere proximity test) */
  r: number;
}

/** Structural subset of WorldData that course generation needs. */
export interface CourseWorld {
  buildings: ReadonlyArray<{ x: number; z: number; w: number; d: number; h: number }>;
  tower: { x: number; z: number; w: number; d: number; h: number };
  spawn: { x: number; z: number };
}

export interface CourseData {
  rings: Ring[];
  /** boss arena over the lake (open water; no buildings to clip) */
  bossArena: { x: number; y: number; z: number; radius: number };
  /** player start, above the plaza spawn */
  start: { x: number; y: number; z: number; yaw: number };
}

export const RING_COUNT = 10;
export const RING_RADIUS = 7;
/** vertical clearance required above any roof near a ring center */
export const RING_CLEARANCE = 5;
/** XZ radius within which buildings constrain a ring's altitude */
export const CLEARANCE_RADIUS = 24;
const LOOP_RINGS = 8;
const MIN_RING_Y = 16;
const MAX_RING_Y = 95;

/**
 * Tallest roof within CLEARANCE_RADIUS of (x, z), accounting for each
 * building's real footprint half-extents. 0 if nothing is near.
 */
export function maxRoofNear(world: CourseWorld, x: number, z: number): number {
  let best = 0;
  for (const b of world.buildings) {
    const dx = Math.max(0, Math.abs(b.x - x) - b.w / 2);
    const dz = Math.max(0, Math.abs(b.z - z) - b.d / 2);
    if (dx * dx + dz * dz <= CLEARANCE_RADIUS * CLEARANCE_RADIUS && b.h > best) {
      best = b.h;
    }
  }
  const t = world.tower;
  const dx = Math.max(0, Math.abs(t.x - x) - t.w / 2);
  const dz = Math.max(0, Math.abs(t.z - z) - t.d / 2);
  if (dx * dx + dz * dz <= CLEARANCE_RADIUS * CLEARANCE_RADIUS && t.h > best) best = t.h;
  return best;
}

/**
 * Deterministic course from the world seed: eight rings looping the
 * city (altitude rides the real skyline: each ring sits RING_CLEARANCE
 * above the tallest roof near it, diving low over plazas and streets),
 * then two approach rings heading east to the boss arena over the lake.
 */
export function generateCourse(seed: number, world: CourseWorld): CourseData {
  const rng = new Rng(seed).fork('flight-course');
  const rings: Ring[] = [];

  for (let i = 0; i < LOOP_RINGS; i++) {
    // Sweep a full loop starting over the spawn side (+z) going west.
    const ang = (i / LOOP_RINGS) * Math.PI * 2;
    const radius = 78 + 34 * Math.sin(i * 1.9 + rng.range(0, 0.6));
    const x = Math.sin(ang) * radius + rng.range(-6, 6);
    const z = Math.cos(ang) * radius + rng.range(-6, 6);
    const roof = maxRoofNear(world, x, z);
    const y = clampY(Math.max(MIN_RING_Y, roof + RING_CLEARANCE) + rng.range(0, 6));
    rings.push({ x, y, z, r: RING_RADIUS });
  }

  // Approach: break east off the loop toward the lake.
  const a1 = { x: 138, z: rng.range(-26, 26) };
  const a2 = { x: 178, z: rng.range(-14, 14) };
  for (const a of [a1, a2]) {
    const roof = maxRoofNear(world, a.x, a.z);
    rings.push({
      x: a.x,
      y: clampY(Math.max(MIN_RING_Y + 6, roof + RING_CLEARANCE)),
      z: a.z,
      r: RING_RADIUS,
    });
  }

  const first = rings[0] as Ring;
  const start = {
    x: world.spawn.x,
    y: 26,
    z: world.spawn.z + 28,
    yaw: Math.atan2(first.x - world.spawn.x, first.z - (world.spawn.z + 28)),
  };

  return {
    rings,
    bossArena: { x: 228, y: 42, z: 0, radius: 55 },
    start,
  };
}

function clampY(y: number): number {
  return Math.min(MAX_RING_Y, Math.max(MIN_RING_Y, y));
}

// ---- Ordered ring tracking ---------------------------------------------

export class RingTracker {
  /** index of the next ring that counts */
  next = 0;
  /** rings passed so far (== next while in order) */
  passed = 0;
  /** all rings collected */
  completed = false;
  /** raised when a later ring is entered while an earlier one is due */
  missed = false;
  /** index of the last ring actually passed (respawn anchor); -1 = start */
  lastPassed = -1;

  constructor(private rings: readonly Ring[]) {
    if (rings.length < 1) throw new Error('RingTracker needs at least 1 ring');
  }

  get total(): number {
    return this.rings.length;
  }

  /**
   * Advance one fixed step from the drone position. Returns true when
   * THIS step passed the required ring (the mode emits a ring-pass
   * event from real detection, never from a timer).
   */
  update(x: number, y: number, z: number): boolean {
    if (this.completed) return false;
    const ring = this.rings[this.next] as Ring;
    if (within(ring, x, y, z)) {
      this.lastPassed = this.next;
      this.passed++;
      this.next++;
      this.missed = false;
      if (this.next >= this.rings.length) this.completed = true;
      return true;
    }
    // Entering a LATER ring while an earlier one is due raises the
    // missed flag (HUD warning), exactly like the race gate logic.
    for (let i = this.next + 1; i < this.rings.length; i++) {
      if (within(this.rings[i] as Ring, x, y, z)) {
        this.missed = true;
        return false;
      }
    }
    return false;
  }

  /** Distance to the next required ring (HUD + AI placement). */
  distToNext(x: number, y: number, z: number): number {
    if (this.completed) return 0;
    const ring = this.rings[this.next] as Ring;
    return Math.hypot(ring.x - x, ring.y - y, ring.z - z);
  }

  /**
   * Fill `out` with the normalized direction and distance to the next
   * ring (caller-owned buffer; zero allocation). Returns false when the
   * course is complete.
   */
  dirToNext(
    x: number,
    y: number,
    z: number,
    out: { x: number; y: number; z: number; dist: number },
  ): boolean {
    if (this.completed) return false;
    const ring = this.rings[this.next] as Ring;
    const dx = ring.x - x;
    const dy = ring.y - y;
    const dz = ring.z - z;
    const d = Math.hypot(dx, dy, dz);
    out.dist = d;
    if (d > 1e-6) {
      out.x = dx / d;
      out.y = dy / d;
      out.z = dz / d;
    } else {
      out.x = 0;
      out.y = 0;
      out.z = 1;
    }
    return true;
  }
}

function within(ring: Ring, x: number, y: number, z: number): boolean {
  const dx = ring.x - x;
  const dy = ring.y - y;
  const dz = ring.z - z;
  return dx * dx + dy * dy + dz * dz <= ring.r * ring.r;
}
