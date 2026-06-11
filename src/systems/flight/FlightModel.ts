/**
 * Hover-drone flight model. Pure math, no Three.js, fixed timestep,
 * zero allocations per tick (every function mutates caller-owned
 * state and touches only scalars) — same contract as race/Vehicle.
 *
 * The model: thrust acts along the yaw heading, strafe along the right
 * vector, lift along world Y. Velocity bleeds with exponential drag on
 * each axis, speed is soft-capped per axis class, and altitude is
 * clamped to a [floor, ceiling] band (gentle arcade feel: hitting a
 * limit zeroes the offending velocity component instead of bouncing).
 * Banking lean (visual roll) and nose pitch are derived from the real
 * lateral/forward velocity so the drone leans into what it is actually
 * doing, not what was pressed.
 */

export const FLIGHT = {
  /** forward/backward thrust acceleration, m/s^2 */
  thrustAccel: 34,
  /** strafe acceleration, m/s^2 */
  strafeAccel: 26,
  /** vertical (lift) acceleration, m/s^2 */
  liftAccel: 24,
  /** top forward speed, m/s */
  maxForward: 38,
  /** top reverse speed, m/s */
  maxReverse: 14,
  /** top strafe speed, m/s */
  maxStrafe: 20,
  /** top climb/sink speed, m/s */
  maxLift: 16,
  /** exponential drag per axis, 1/s (hover drones stop on their own) */
  dragForward: 0.9,
  dragStrafe: 2.2,
  dragLift: 2.6,
  /** yaw input authority, rad/s */
  yawRate: 2.4,
  /** altitude band, meters */
  minAltitude: 4,
  maxAltitude: 150,
  /** visual bank: radians of roll per (m/s) of lateral velocity */
  bankPerLateral: 0.028,
  bankMax: 0.55,
  /** visual pitch: radians of nose-down per (m/s) of forward velocity */
  pitchPerForward: 0.011,
  pitchMax: 0.42,
  /** how fast the visual lean follows the velocity, 1/s */
  leanFollow: 7,
} as const;

export interface DroneState {
  x: number;
  y: number;
  z: number;
  /** heading in radians; forward = (sin yaw, 0, cos yaw) */
  yaw: number;
  vx: number;
  vy: number;
  vz: number;
  /** visual roll (banking lean), derived from real lateral velocity */
  bank: number;
  /** visual nose pitch, derived from real forward velocity */
  lean: number;
}

export interface FlightInput {
  /** -1..1: forward / reverse thrust */
  thrust: number;
  /** -1..1: right / left strafe */
  strafe: number;
  /** -1..1: climb / sink */
  lift: number;
  /** -1..1: yaw right / left (keyboard assist; mouse adds directly) */
  yaw: number;
}

export function createDrone(x: number, y: number, z: number, yaw: number): DroneState {
  return { x, y, z, yaw, vx: 0, vy: 0, vz: 0, bank: 0, lean: 0 };
}

export function createFlightInput(): FlightInput {
  return { thrust: 0, strafe: 0, lift: 0, yaw: 0 };
}

export function resetDrone(s: DroneState, x: number, y: number, z: number, yaw: number): void {
  s.x = x;
  s.y = y;
  s.z = z;
  s.yaw = yaw;
  s.vx = 0;
  s.vy = 0;
  s.vz = 0;
  s.bank = 0;
  s.lean = 0;
}

/** Signed forward speed (positive = moving along the nose). */
export function droneForwardSpeed(s: DroneState): number {
  return s.vx * Math.sin(s.yaw) + s.vz * Math.cos(s.yaw);
}

/** Signed rightward (strafe) speed. */
export function droneLateralSpeed(s: DroneState): number {
  return s.vx * Math.cos(s.yaw) - s.vz * Math.sin(s.yaw);
}

const clamp = (v: number, lo: number, hi: number): number =>
  v < lo ? lo : v > hi ? hi : v;

/**
 * Advance one fixed step. Deterministic: same state + same inputs =>
 * the same next state, bit for bit (no Math.random, no wall clock).
 */
export function stepDrone(s: DroneState, input: FlightInput, dt: number): void {
  // Yaw from the keyboard channel (mouse look adds to s.yaw directly).
  s.yaw += clamp(input.yaw, -1, 1) * FLIGHT.yawRate * dt;

  const fx = Math.sin(s.yaw);
  const fz = Math.cos(s.yaw);
  const rx = fz; // right vector
  const rz = -fx;

  // Decompose into the drone frame.
  let vF = s.vx * fx + s.vz * fz;
  let vR = s.vx * rx + s.vz * rz;
  let vY = s.vy;

  // Thrust / strafe / lift.
  vF += clamp(input.thrust, -1, 1) * FLIGHT.thrustAccel * dt;
  vR += clamp(input.strafe, -1, 1) * FLIGHT.strafeAccel * dt;
  vY += clamp(input.lift, -1, 1) * FLIGHT.liftAccel * dt;

  // Per-axis drag (hover feel: release the stick and the drone settles).
  vF -= vF * FLIGHT.dragForward * dt;
  vR -= vR * FLIGHT.dragStrafe * dt;
  vY -= vY * FLIGHT.dragLift * dt;

  // Hard per-axis caps (no boost mechanic in flight mode, so there is
  // never a legitimate over-cap state to decay from).
  vF = clamp(vF, -FLIGHT.maxReverse, FLIGHT.maxForward);
  vR = clamp(vR, -FLIGHT.maxStrafe, FLIGHT.maxStrafe);
  vY = clamp(vY, -FLIGHT.maxLift, FLIGHT.maxLift);

  // Recompose and integrate.
  s.vx = fx * vF + rx * vR;
  s.vz = fz * vF + rz * vR;
  s.vy = vY;
  s.x += s.vx * dt;
  s.y += s.vy * dt;
  s.z += s.vz * dt;

  // Altitude band: gentle clamp, kill only the offending component.
  if (s.y < FLIGHT.minAltitude) {
    s.y = FLIGHT.minAltitude;
    if (s.vy < 0) s.vy = 0;
  } else if (s.y > FLIGHT.maxAltitude) {
    s.y = FLIGHT.maxAltitude;
    if (s.vy > 0) s.vy = 0;
  }

  // Visual lean follows the REAL velocity (banking into strafes/turns).
  const bankTarget = clamp(-vR * FLIGHT.bankPerLateral, -FLIGHT.bankMax, FLIGHT.bankMax);
  const leanTarget = clamp(vF * FLIGHT.pitchPerForward, -FLIGHT.pitchMax, FLIGHT.pitchMax);
  const follow = Math.min(1, FLIGHT.leanFollow * dt);
  s.bank += (bankTarget - s.bank) * follow;
  s.lean += (leanTarget - s.lean) * follow;
}
