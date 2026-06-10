import { describe, expect, test } from 'vitest';
import {
  advanceTarget,
  aiDecide,
  makeSkills,
  wrapAngle,
  type AISkill,
} from '../src/systems/race/RaceAI';
import { createInput } from '../src/systems/race/Vehicle';

const SKILL: AISkill = {
  lookahead: 12,
  steerGain: 2.0,
  maxThrottle: 0.95,
  speedMul: 0.95,
  brakeAngle: 1.0,
};

describe('aiDecide (pure steering decision)', () => {
  test('steers right toward a target on the right, left toward the left', () => {
    const out = createInput();
    // Facing +Z (heading 0); target to the +X side = right turn.
    aiDecide(0, 0, 0, 20, 10, 10, SKILL, out);
    expect(out.steer).toBeGreaterThan(0.5);
    aiDecide(0, 0, 0, 20, -10, 10, SKILL, out);
    expect(out.steer).toBeLessThan(-0.5);
  });

  test('drives straight at a dead-ahead target with full committed throttle', () => {
    const out = createInput();
    aiDecide(0, 0, 0, 20, 0, 50, SKILL, out);
    expect(Math.abs(out.steer)).toBeLessThan(0.01);
    expect(out.throttle).toBeCloseTo(SKILL.maxThrottle * SKILL.speedMul, 5);
    expect(out.brake).toBe(0);
    expect(out.drift).toBe(false);
  });

  test('eases the throttle as the corner error grows', () => {
    const ahead = createInput();
    const corner = createInput();
    aiDecide(0, 0, 0, 20, 0, 50, SKILL, ahead);
    aiDecide(0, 0, 0, 20, 40, 10, SKILL, corner);
    expect(corner.throttle).toBeLessThan(ahead.throttle);
  });

  test('brakes into a sharp corner at speed, not while slow', () => {
    const out = createInput();
    // Target almost behind: large heading error.
    aiDecide(0, 0, 0, 25, -5, -50, SKILL, out);
    expect(out.brake).toBe(1);
    aiDecide(0, 0, 0, 5, -5, -50, SKILL, out);
    expect(out.brake).toBe(0);
  });

  test('commits to a drift through long sharp corners at speed', () => {
    const out = createInput();
    aiDecide(0, 0, 0, 25, 50, 0, SKILL, out); // 90 degrees right, fast
    expect(out.drift).toBe(true);
    aiDecide(0, 0, 0, 10, 50, 0, SKILL, out); // same corner, slow
    expect(out.drift).toBe(false);
  });

  test('is a pure function: same inputs, same decision', () => {
    const a = createInput();
    const b = createInput();
    aiDecide(3, -4, 0.7, 18, 25, 30, SKILL, a);
    aiDecide(3, -4, 0.7, 18, 25, 30, SKILL, b);
    expect(a).toEqual(b);
  });

  test('handles the heading wrap: target across the -PI/PI seam', () => {
    const out = createInput();
    // Heading just below +PI, target requires a small right turn across the seam.
    aiDecide(0, 0, Math.PI - 0.1, 20, Math.sin(-Math.PI + 0.1) * 10, Math.cos(-Math.PI + 0.1) * 10, SKILL, out);
    expect(Math.abs(out.steer)).toBeLessThan(0.6); // small correction, not a U-turn
  });
});

describe('waypoint advancement', () => {
  const xs = new Float32Array([0, 10, 20, 30]);
  const zs = new Float32Array([0, 0, 0, 0]);

  test('advances past waypoints inside the lookahead radius', () => {
    expect(advanceTarget(0, 0, xs, zs, 0, 12)).toBe(2); // 0 and 1 are within 12 m
  });

  test('keeps the target when it is still far away', () => {
    expect(advanceTarget(0, 0, xs, zs, 2, 12)).toBe(2);
  });

  test('wraps around the loop', () => {
    expect(advanceTarget(29, 0, xs, zs, 3, 5)).toBe(0);
  });
});

describe('skill variance', () => {
  test('skills are deterministic from the seed', () => {
    expect(makeSkills(42, 3)).toEqual(makeSkills(42, 3));
    expect(makeSkills(42, 3)).not.toEqual(makeSkills(43, 3));
  });

  test('racers differ from each other and stay inside sane bounds', () => {
    const skills = makeSkills(7, 3);
    expect(skills.length).toBe(3);
    const gains = new Set(skills.map((s) => s.steerGain));
    expect(gains.size).toBe(3);
    for (const s of skills) {
      expect(s.maxThrottle).toBeGreaterThan(0.5);
      expect(s.maxThrottle).toBeLessThanOrEqual(1);
      expect(s.speedMul).toBeGreaterThan(0.8);
      expect(s.speedMul).toBeLessThan(1);
      expect(s.lookahead).toBeGreaterThan(5);
    }
  });

  test('wrapAngle maps any angle into (-PI, PI]', () => {
    expect(wrapAngle(0)).toBe(0);
    expect(Math.abs(wrapAngle(Math.PI * 3))).toBeCloseTo(Math.PI, 10);
    expect(wrapAngle(-Math.PI * 2.5)).toBeCloseTo(-Math.PI / 2, 10);
    expect(wrapAngle(7)).toBeCloseTo(7 - Math.PI * 2, 10);
  });
});
