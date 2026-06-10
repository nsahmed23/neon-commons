import { describe, expect, test } from 'vitest';
import {
  SURFACE_BOOST,
  SURFACE_OFFROAD,
  SURFACE_TRACK,
  createQueryResult,
  generateTrack,
  queryTrack,
} from '../src/systems/race/Track';
import {
  VEHICLE,
  collideWithWall,
  createInput,
  createVehicle,
  forwardSpeed,
  stepVehicle,
} from '../src/systems/race/Vehicle';

const DT = 1 / 60;

function drive(
  surface: typeof SURFACE_TRACK | typeof SURFACE_BOOST | typeof SURFACE_OFFROAD,
  seconds: number,
  inputMod?: (i: ReturnType<typeof createInput>) => void,
) {
  const s = createVehicle(0, 0, 0);
  const input = createInput();
  input.throttle = 1;
  if (inputMod) inputMod(input);
  for (let i = 0; i < seconds * 60; i++) stepVehicle(s, input, surface, DT);
  return s;
}

describe('vehicle physics', () => {
  test('accelerates forward from rest under throttle', () => {
    const s = drive(SURFACE_TRACK, 1);
    expect(forwardSpeed(s)).toBeGreaterThan(10);
    // heading 0 means forward = (+sin 0, +cos 0) = +Z
    expect(s.z).toBeGreaterThan(5);
    expect(Math.abs(s.x)).toBeLessThan(0.001);
  });

  test('top speed settles at the asphalt cap, never above', () => {
    const s = drive(SURFACE_TRACK, 12);
    const v = forwardSpeed(s);
    expect(v).toBeGreaterThan(VEHICLE.maxSpeed * 0.85);
    expect(v).toBeLessThanOrEqual(VEHICLE.maxSpeed + 0.01);
  });

  test('off-road surface genuinely slows the kart (lower top speed)', () => {
    const road = forwardSpeed(drive(SURFACE_TRACK, 12));
    const dirt = forwardSpeed(drive(SURFACE_OFFROAD, 12));
    expect(dirt).toBeLessThan(road * 0.7);
    expect(dirt).toBeLessThanOrEqual(VEHICLE.maxSpeed * VEHICLE.offroadSpeedMul + 0.01);
  });

  test('boost surface raises speed beyond the normal cap', () => {
    const s = drive(SURFACE_BOOST, 12);
    expect(forwardSpeed(s)).toBeGreaterThan(VEHICLE.maxSpeed * 1.05);
    expect(s.boostTimer).toBeGreaterThan(0);
  });

  test('braking stops the kart, holding brake reverses it', () => {
    const s = drive(SURFACE_TRACK, 5);
    const input = createInput();
    input.brake = 1;
    for (let i = 0; i < 6 * 60; i++) stepVehicle(s, input, SURFACE_TRACK, DT);
    const v = forwardSpeed(s);
    expect(v).toBeLessThan(0); // reversing
    expect(v).toBeGreaterThanOrEqual(-VEHICLE.reverseMax - 0.01);
  });

  test('steering turns the heading in the steer direction', () => {
    const right = drive(SURFACE_TRACK, 2, (i) => (i.steer = 1));
    const left = drive(SURFACE_TRACK, 2, (i) => (i.steer = -1));
    expect(right.heading).toBeGreaterThan(0.3);
    expect(left.heading).toBeLessThan(-0.3);
  });

  test('drift keeps lateral velocity alive that grip would kill', () => {
    // Build the same entry state twice, then corner with/without drift.
    const make = () => {
      const s = drive(SURFACE_TRACK, 4);
      return s;
    };
    const lateralOf = (s: ReturnType<typeof createVehicle>) => {
      const rx = Math.cos(s.heading);
      const rz = -Math.sin(s.heading);
      return Math.abs(s.vx * rx + s.vz * rz);
    };
    const gripS = make();
    const driftS = make();
    const input = createInput();
    input.throttle = 1;
    input.steer = 1;
    for (let i = 0; i < 45; i++) stepVehicle(gripS, input, SURFACE_TRACK, DT);
    input.drift = true;
    for (let i = 0; i < 45; i++) stepVehicle(driftS, input, SURFACE_TRACK, DT);
    expect(driftS.drifting).toBe(true);
    expect(gripS.drifting).toBe(false);
    expect(lateralOf(driftS)).toBeGreaterThan(lateralOf(gripS) * 2);
  });

  test('identical inputs produce an identical trajectory (determinism)', () => {
    const run = () => {
      const s = createVehicle(3, -2, 0.4);
      const input = createInput();
      for (let i = 0; i < 600; i++) {
        input.throttle = 1;
        input.steer = Math.sin(i / 30);
        input.drift = i % 200 > 150;
        stepVehicle(s, input, i % 90 < 5 ? SURFACE_BOOST : SURFACE_TRACK, DT);
      }
      return s;
    };
    expect(run()).toEqual(run());
  });
});

describe('track boundary collision', () => {
  test('kart beyond the wall is clamped back and outward velocity removed', () => {
    const t = generateTrack(42);
    const q = createQueryResult();
    const i = 32;
    const nx = -(t.tz[i] as number);
    const nz = t.tx[i] as number;
    // Place the kart 4 m past the wall, moving outward.
    const s = createVehicle(
      (t.xs[i] as number) + nx * (t.wallDist + 4),
      (t.zs[i] as number) + nz * (t.wallDist + 4),
      0,
    );
    s.vx = nx * 20;
    s.vz = nz * 20;
    queryTrack(t, s.x, s.z, -1, q);
    expect(Math.abs(q.lateral)).toBeGreaterThan(t.wallDist);
    const hit = collideWithWall(s, q, t.wallDist);
    expect(hit).toBe(true);
    queryTrack(t, s.x, s.z, q.seg, q);
    expect(Math.abs(q.lateral)).toBeLessThanOrEqual(t.wallDist + 0.05);
    // Outward component is now inward (restitution bounce).
    const vOut = s.vx * nx + s.vz * nz;
    expect(vOut).toBeLessThanOrEqual(0);
  });

  test('kart inside the boundary is untouched', () => {
    const t = generateTrack(42);
    const q = createQueryResult();
    const s = createVehicle(t.xs[10] as number, t.zs[10] as number, 0);
    s.vx = 5;
    queryTrack(t, s.x, s.z, -1, q);
    const before = { x: s.x, z: s.z, vx: s.vx, vz: s.vz };
    expect(collideWithWall(s, q, t.wallDist)).toBe(false);
    expect(s.x).toBe(before.x);
    expect(s.vx).toBe(before.vx);
  });

  test('full-physics integration: a kart driven by the surface query slows off-road', () => {
    // Drive straight along the track tangent on asphalt vs the shoulder,
    // querying the REAL track each step, and compare distance covered.
    const t = generateTrack(7);
    const q = createQueryResult();
    const input = createInput();
    input.throttle = 1;
    const distance = (latOffset: number): number => {
      const i = 0;
      const nx = -(t.tz[i] as number);
      const nz = t.tx[i] as number;
      const heading = Math.atan2(t.tx[i] as number, t.tz[i] as number);
      const s = createVehicle(
        (t.xs[i] as number) + nx * latOffset,
        (t.zs[i] as number) + nz * latOffset,
        heading,
      );
      const x0 = s.x;
      const z0 = s.z;
      for (let k = 0; k < 120; k++) {
        queryTrack(t, s.x, s.z, s.segHint, q);
        s.segHint = q.seg;
        stepVehicle(s, input, q.surface, DT);
      }
      return Math.hypot(s.x - x0, s.z - z0);
    };
    const onRoad = distance(0);
    const offRoad = distance(t.halfWidth + 5);
    expect(offRoad).toBeLessThan(onRoad * 0.75);
  });
});
