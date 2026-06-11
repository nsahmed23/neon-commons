import { describe, expect, test } from 'vitest';
import {
  FLIGHT,
  createDrone,
  createFlightInput,
  droneForwardSpeed,
  droneLateralSpeed,
  resetDrone,
  stepDrone,
  type DroneState,
} from '../src/systems/flight/FlightModel';

const DT = 1 / 60;

function run(s: ReturnType<typeof createDrone>, input: Partial<ReturnType<typeof createFlightInput>>, steps: number): void {
  const inp = { ...createFlightInput(), ...input };
  for (let i = 0; i < steps; i++) stepDrone(s, inp, DT);
}

describe('flight model integration step', () => {
  test('deterministic: identical input tape produces an identical state', () => {
    const tape: Array<{ thrust: number; strafe: number; lift: number; yaw: number }> = [];
    for (let i = 0; i < 600; i++) {
      tape.push({
        thrust: Math.sin(i * 0.03),
        strafe: Math.cos(i * 0.07) * 0.6,
        lift: Math.sin(i * 0.011) * 0.5,
        yaw: Math.sin(i * 0.02) * 0.8,
      });
    }
    const a = createDrone(0, 30, 0, 0.4);
    const b = createDrone(0, 30, 0, 0.4);
    for (const inp of tape) stepDrone(a, inp, DT);
    for (const inp of tape) stepDrone(b, inp, DT);
    expect(a).toStrictEqual(b);
  });

  test('full thrust accelerates along the yaw heading', () => {
    const s = createDrone(0, 30, 0, 0); // facing +z
    run(s, { thrust: 1 }, 120);
    expect(s.z).toBeGreaterThan(20);
    expect(Math.abs(s.x)).toBeLessThan(0.01);
    expect(droneForwardSpeed(s)).toBeGreaterThan(15);
  });

  test('forward speed never exceeds the cap (plus soft-cap tolerance)', () => {
    const s = createDrone(0, 30, 0, 1.1);
    run(s, { thrust: 1 }, 1200); // 20 simulated seconds, pinned throttle
    expect(droneForwardSpeed(s)).toBeLessThanOrEqual(FLIGHT.maxForward + 0.5);
  });

  test('reverse thrust caps at the (smaller) reverse limit', () => {
    const s = createDrone(0, 30, 0, 0);
    run(s, { thrust: -1 }, 1200);
    expect(droneForwardSpeed(s)).toBeGreaterThanOrEqual(-(FLIGHT.maxReverse + 0.5));
    expect(droneForwardSpeed(s)).toBeLessThan(-5);
  });

  test('altitude floor clamps and kills downward velocity', () => {
    const s = createDrone(0, FLIGHT.minAltitude + 3, 0, 0);
    run(s, { lift: -1 }, 600);
    expect(s.y).toBe(FLIGHT.minAltitude);
    expect(s.vy).toBeGreaterThanOrEqual(0);
  });

  test('altitude ceiling clamps and kills upward velocity', () => {
    const s = createDrone(0, FLIGHT.maxAltitude - 3, 0, 0);
    run(s, { lift: 1 }, 600);
    expect(s.y).toBe(FLIGHT.maxAltitude);
    expect(s.vy).toBeLessThanOrEqual(0);
  });

  test('strafe moves laterally and banks the drone INTO the motion', () => {
    const s = createDrone(0, 30, 0, 0); // facing +z, right = +x
    run(s, { strafe: 1 }, 90);
    expect(s.x).toBeGreaterThan(3);
    expect(droneLateralSpeed(s)).toBeGreaterThan(4);
    // rightward velocity -> negative roll (leans right), per bankPerLateral sign
    expect(s.bank).toBeLessThan(-0.05);
    expect(Math.abs(s.bank)).toBeLessThanOrEqual(FLIGHT.bankMax);
  });

  test('forward velocity pitches the nose down, clamped at pitchMax', () => {
    const s = createDrone(0, 30, 0, 0);
    run(s, { thrust: 1 }, 600);
    expect(s.lean).toBeGreaterThan(0.1);
    expect(s.lean).toBeLessThanOrEqual(FLIGHT.pitchMax);
  });

  test('zero input bleeds velocity toward hover (drag is real)', () => {
    const s = createDrone(0, 30, 0, 0);
    run(s, { thrust: 1, strafe: 1, lift: 1 }, 120);
    const speedBefore = Math.hypot(s.vx, s.vy, s.vz);
    run(s, {}, 600);
    const speedAfter = Math.hypot(s.vx, s.vy, s.vz);
    expect(speedBefore).toBeGreaterThan(10);
    expect(speedAfter).toBeLessThan(1);
  });

  test('yaw input turns the heading at the configured rate', () => {
    const s = createDrone(0, 30, 0, 0);
    run(s, { yaw: 1 }, 60); // exactly 1 second
    expect(s.yaw).toBeCloseTo(FLIGHT.yawRate, 5);
  });

  test('resetDrone zeroes velocity and lean', () => {
    const s: DroneState = createDrone(0, 30, 0, 0);
    run(s, { thrust: 1, strafe: 1 }, 120);
    resetDrone(s, 5, 40, 6, 1.2);
    expect(s).toStrictEqual({ x: 5, y: 40, z: 6, yaw: 1.2, vx: 0, vy: 0, vz: 0, bank: 0, lean: 0 });
  });
});
