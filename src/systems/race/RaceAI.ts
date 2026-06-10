/**
 * AI racer steering: pure decision functions over centerline waypoints.
 * Each AI gets a seeded skill profile (lookahead, steer gain, top-speed
 * fraction, throttle ceiling, braking caution) so the three rivals feel
 * different, but every one of them drives the SAME stepVehicle physics
 * as the player; the AI only produces a VehicleInput. No teleporting.
 */

import { Rng } from '../../core/Rng';
import type { VehicleInput } from './Vehicle';

export interface AISkill {
  /** waypoint advance radius, meters */
  lookahead: number;
  /** steering response (rad error -> wheel) */
  steerGain: number;
  /** ceiling on the throttle input */
  maxThrottle: number;
  /** fraction of player top speed the AI dares to hold (via throttle) */
  speedMul: number;
  /** heading error (rad) above which the AI brakes at speed */
  brakeAngle: number;
}

/** Deterministic per-racer skill variance from a seed. */
export function makeSkills(seed: number, count: number): AISkill[] {
  const rng = new Rng(seed).fork('race-ai');
  const skills: AISkill[] = [];
  for (let i = 0; i < count; i++) {
    skills.push({
      lookahead: rng.range(11, 18),
      steerGain: rng.range(1.7, 2.6),
      maxThrottle: rng.range(0.84, 0.98),
      speedMul: rng.range(0.88, 0.99),
      brakeAngle: rng.range(0.85, 1.25),
    });
  }
  return skills;
}

/** Wrap an angle to (-PI, PI]. */
export function wrapAngle(a: number): number {
  while (a > Math.PI) a -= Math.PI * 2;
  while (a <= -Math.PI) a += Math.PI * 2;
  return a;
}

/**
 * Advance the AI's waypoint target while it is inside the lookahead
 * radius. Pure; returns the new index (wraps around the loop).
 */
export function advanceTarget(
  px: number,
  pz: number,
  xs: Float32Array,
  zs: Float32Array,
  idx: number,
  lookahead: number,
): number {
  const n = xs.length;
  let i = idx;
  for (let guard = 0; guard < n; guard++) {
    const dx = (xs[i] as number) - px;
    const dz = (zs[i] as number) - pz;
    if (dx * dx + dz * dz > lookahead * lookahead) return i;
    i = (i + 1) % n;
  }
  return i;
}

/**
 * The steering decision: given the kart pose, forward speed, and the
 * current target waypoint, fill a VehicleInput. Pure function of its
 * arguments (unit-testable without a track or renderer); writes into
 * the caller-owned input object, allocating nothing.
 */
export function aiDecide(
  px: number,
  pz: number,
  heading: number,
  forwardSpeed: number,
  targetX: number,
  targetZ: number,
  skill: AISkill,
  out: VehicleInput,
): void {
  const dx = targetX - px;
  const dz = targetZ - pz;
  // heading convention: forward = (sin h, cos h)
  const desired = Math.atan2(dx, dz);
  const diff = wrapAngle(desired - heading);
  const absDiff = Math.abs(diff);

  out.steer = clamp(diff * skill.steerGain, -1, 1);

  // Throttle eases off as the corner error grows; speedMul keeps the
  // slower racers honest on the straights.
  const corner = Math.max(0, 1 - absDiff * 0.8);
  out.throttle = clamp(skill.maxThrottle * skill.speedMul * corner, 0, 1);

  // Brake into sharp corners at speed; never brake while crawling.
  out.brake = absDiff > skill.brakeAngle && forwardSpeed > 15 ? 1 : 0;

  // Commit to a drift through long sharp corners.
  out.drift = absDiff > 0.85 && forwardSpeed > 16;
}

function clamp(v: number, lo: number, hi: number): number {
  return v < lo ? lo : v > hi ? hi : v;
}
