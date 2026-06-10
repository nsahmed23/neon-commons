/**
 * Arcade-but-real kart physics. Pure math, no Three.js, fixed timestep,
 * zero allocations per tick (every function mutates caller-owned state
 * and touches only scalars). The model: velocity is decomposed into a
 * forward and a lateral component in the kart's frame; throttle/brake
 * act on the forward component, lateral grip exponentially bleeds the
 * lateral component (much less while drifting), steering turns the
 * heading with speed-sensitive authority, and the surface query result
 * scales acceleration and top speed (off-road genuinely slows you).
 * Player and AI run the exact same step function: no teleporting karts.
 */

import {
  SURFACE_BOOST,
  SURFACE_OFFROAD,
  type Surface,
  type TrackQueryResult,
} from './Track';

export const VEHICLE = {
  /** forward acceleration, m/s^2 */
  accel: 30,
  /** brake deceleration, m/s^2 */
  brake: 46,
  /** reverse acceleration / top reverse speed */
  reverseAccel: 14,
  reverseMax: 9,
  /** top speed on asphalt, m/s */
  maxSpeed: 40,
  /** passive drag, 1/s */
  drag: 0.32,
  /** how fast over-cap speed decays back to the cap, 1/s */
  capDecay: 2.2,
  /** lateral grip, 1/s (exponential damping of lateral velocity) */
  gripRoad: 9,
  gripDrift: 2.0,
  gripOffroadMul: 0.6,
  /** steering */
  steerRate: 7, // how fast the wheel moves toward the input, 1/s
  steerGain: 2.3, // rad/s at full lock and reference speed
  driftYawMul: 1.65,
  /** drift entry threshold, m/s */
  driftMinSpeed: 11,
  /** mini-boost from a held drift */
  driftChargeRate: 1.0,
  driftBoostMax: 0.85,
  /** surfaces */
  offroadAccelMul: 0.4,
  offroadSpeedMul: 0.55,
  /** boost pads */
  boostTime: 1.5,
  boostAccel: 34,
  boostSpeedMul: 1.4,
  /** wall response */
  wallRestitution: 0.25,
  wallFriction: 0.86,
} as const;

export interface VehicleState {
  x: number;
  z: number;
  /** heading in radians; forward = (sin h, cos h) */
  heading: number;
  vx: number;
  vz: number;
  /** smoothed wheel position -1..1 */
  steer: number;
  /** seconds of boost remaining */
  boostTimer: number;
  drifting: boolean;
  driftCharge: number;
  /** last nearest centerline sample (queryTrack hint) */
  segHint: number;
}

export interface VehicleInput {
  throttle: number; // 0..1
  brake: number; // 0..1
  steer: number; // -1..1 target
  drift: boolean;
}

export function createVehicle(x: number, z: number, heading: number): VehicleState {
  return {
    x,
    z,
    heading,
    vx: 0,
    vz: 0,
    steer: 0,
    boostTimer: 0,
    drifting: false,
    driftCharge: 0,
    segHint: -1,
  };
}

export function createInput(): VehicleInput {
  return { throttle: 0, brake: 0, steer: 0, drift: false };
}

export function resetVehicle(s: VehicleState, x: number, z: number, heading: number): void {
  s.x = x;
  s.z = z;
  s.heading = heading;
  s.vx = 0;
  s.vz = 0;
  s.steer = 0;
  s.boostTimer = 0;
  s.drifting = false;
  s.driftCharge = 0;
  s.segHint = -1;
}

/** Signed forward speed of a vehicle (positive = moving forward). */
export function forwardSpeed(s: VehicleState): number {
  return s.vx * Math.sin(s.heading) + s.vz * Math.cos(s.heading);
}

/**
 * Advance one fixed step. `surface` must come from a real queryTrack
 * call at the vehicle's position (that is what makes off-road slowdown
 * and boost pads real instead of cosmetic).
 */
export function stepVehicle(
  s: VehicleState,
  input: VehicleInput,
  surface: Surface,
  dt: number,
): void {
  const fx = Math.sin(s.heading);
  const fz = Math.cos(s.heading);
  const rx = fz; // right vector
  const rz = -fx;

  let vF = s.vx * fx + s.vz * fz;
  let vL = s.vx * rx + s.vz * rz;

  // Wheel moves toward the requested steer.
  const dSteer = input.steer - s.steer;
  const maxMove = VEHICLE.steerRate * dt;
  s.steer += Math.abs(dSteer) <= maxMove ? dSteer : Math.sign(dSteer) * maxMove;

  // Boost pads arm the boost timer; drift release adds a mini-boost.
  if (surface === SURFACE_BOOST) s.boostTimer = VEHICLE.boostTime;
  const wasDrifting = s.drifting;
  s.drifting = input.drift && Math.abs(vF) > VEHICLE.driftMinSpeed;
  if (s.drifting && Math.abs(s.steer) > 0.35) {
    s.driftCharge = Math.min(VEHICLE.driftBoostMax, s.driftCharge + VEHICLE.driftChargeRate * dt);
  }
  if (wasDrifting && !s.drifting && s.driftCharge > 0.2) {
    s.boostTimer = Math.max(s.boostTimer, s.driftCharge);
  }
  if (!s.drifting) s.driftCharge = 0;

  const offroad = surface === SURFACE_OFFROAD;
  const boosting = s.boostTimer > 0;
  const accelMul = offroad ? VEHICLE.offroadAccelMul : 1;
  const cap =
    VEHICLE.maxSpeed *
    (offroad ? VEHICLE.offroadSpeedMul : 1) *
    (boosting ? VEHICLE.boostSpeedMul : 1);

  // Throttle / boost: accelerates up to (never past) the current cap.
  if (vF < cap) {
    const a = VEHICLE.accel * accelMul + (boosting ? VEHICLE.boostAccel : 0);
    vF = Math.min(cap, vF + input.throttle * a * dt);
  }

  // Brake toward zero, then reverse.
  if (input.brake > 0) {
    if (vF > 0.4) {
      vF = Math.max(0, vF - VEHICLE.brake * input.brake * dt);
    } else {
      vF = Math.max(-VEHICLE.reverseMax, vF - VEHICLE.reverseAccel * input.brake * dt);
    }
  }

  // Drag; if the cap dropped under us (boost expired, drove off-road),
  // decay down toward it instead of snapping.
  vF -= vF * VEHICLE.drag * dt;
  if (vF > cap) vF += (cap - vF) * Math.min(1, VEHICLE.capDecay * dt);
  if (vF < -VEHICLE.reverseMax) vF = -VEHICLE.reverseMax;

  // Lateral grip: exponential bleed, weak while drifting / off-road.
  let grip = s.drifting ? VEHICLE.gripDrift : VEHICLE.gripRoad;
  if (offroad) grip *= VEHICLE.gripOffroadMul;
  const keep = Math.exp(-grip * dt);
  // Drifting converts a sliver of forward speed into outward slide.
  if (s.drifting) vL += -s.steer * Math.abs(vF) * 0.55 * dt;
  vL *= keep;

  // Steering: speed-sensitive yaw authority, reversed in reverse.
  const speedFactor = Math.min(1, Math.abs(vF) / 8) / (1 + Math.abs(vF) * 0.015);
  let yawRate = s.steer * VEHICLE.steerGain * speedFactor;
  if (s.drifting) yawRate *= VEHICLE.driftYawMul;
  s.heading += yawRate * dt * (vF >= 0 ? 1 : -1);

  // Recompose and integrate (using the post-steer frame keeps the
  // velocity glued to the kart, which is the arcade feel).
  const nfx = Math.sin(s.heading);
  const nfz = Math.cos(s.heading);
  const nrx = nfz;
  const nrz = -nfx;
  s.vx = nfx * vF + nrx * vL;
  s.vz = nfz * vF + nrz * vL;
  s.x += s.vx * dt;
  s.z += s.vz * dt;

  s.boostTimer = Math.max(0, s.boostTimer - dt);
}

/**
 * Hard track boundary: if the latest query puts the kart beyond the
 * wall distance, clamp it back to the wall line and reflect the outward
 * velocity component (with restitution + a speed scrub). This is a
 * real collision response, not a scripted reset. Returns true on hit.
 */
export function collideWithWall(s: VehicleState, q: TrackQueryResult, wallDist: number): boolean {
  const absLat = Math.abs(q.lateral);
  if (absLat <= wallDist) return false;
  const sign = q.lateral >= 0 ? 1 : -1;
  // Left normal of the travel direction.
  const nx = -q.tangentZ * 1;
  const nz = q.tangentX * 1;
  const overshoot = q.lateral - sign * wallDist;
  s.x -= nx * overshoot;
  s.z -= nz * overshoot;
  // Outward velocity component (toward the wall side we hit).
  const vN = s.vx * nx + s.vz * nz;
  if (vN * sign > 0) {
    s.vx -= (1 + VEHICLE.wallRestitution) * vN * nx;
    s.vz -= (1 + VEHICLE.wallRestitution) * vN * nz;
    s.vx *= VEHICLE.wallFriction;
    s.vz *= VEHICLE.wallFriction;
  }
  return true;
}
