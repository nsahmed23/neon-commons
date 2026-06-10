import { describe, expect, test } from 'vitest';
import {
  LapTracker,
  compareRacers,
  formatMs,
  type GateLike,
  type RacerProgress,
} from '../src/systems/race/Checkpoints';

const DT = 1 / 60;

/** Four gates on a 100 m square, lap order 0 -> 1 -> 2 -> 3 -> 0. */
function squareGates(): GateLike[] {
  return [
    { x: 0, z: 0, r: 5 },
    { x: 100, z: 0, r: 5 },
    { x: 100, z: 100, r: 5 },
    { x: 0, z: 100, r: 5 },
  ];
}

/** Step the tracker `n` times at a fixed position, driving forward. */
function stand(t: LapTracker, x: number, z: number, n = 1, dot = 5): void {
  for (let i = 0; i < n; i++) t.update(DT, x, z, dot);
}

describe('ordered checkpoints', () => {
  test('gates passed in order advance next and passedTotal', () => {
    const t = new LapTracker(squareGates(), 3);
    expect(t.next).toBe(1);
    stand(t, 100, 0);
    expect(t.next).toBe(2);
    stand(t, 100, 100);
    expect(t.next).toBe(3);
    expect(t.passedTotal).toBe(2);
    expect(t.lap).toBe(0);
  });

  test('out-of-order gate is rejected: crossing gate 2 first does nothing', () => {
    const t = new LapTracker(squareGates(), 3);
    stand(t, 100, 100, 30); // sit inside gate 2 while gate 1 is due
    expect(t.next).toBe(1);
    expect(t.passedTotal).toBe(0);
    expect(t.lap).toBe(0);
  });

  test('skipping a gate raises the missed flag, collecting it clears it', () => {
    const t = new LapTracker(squareGates(), 3);
    stand(t, 100, 100, 5); // gate 2 while gate 1 is due -> missed
    expect(t.missed).toBe(true);
    stand(t, 100, 0); // collect gate 1
    expect(t.missed).toBe(false);
    expect(t.next).toBe(2);
  });

  test('lap increments ONLY after all gates then the finish line', () => {
    const t = new LapTracker(squareGates(), 3);
    // Crossing the finish line straight away does not count a lap.
    stand(t, 0, 0, 30);
    expect(t.lap).toBe(0);
    // Full ordered tour.
    stand(t, 100, 0);
    stand(t, 100, 100);
    stand(t, 0, 100);
    expect(t.lap).toBe(0); // still on lap 1 until the finish
    stand(t, 0, 0);
    expect(t.lap).toBe(1);
    expect(t.lapTimes.length).toBe(1);
    expect(t.next).toBe(1); // lap 2 begins at gate 1 again
  });

  test('race finishes after totalLaps and stops accumulating', () => {
    const t = new LapTracker(squareGates(), 2);
    for (let lap = 0; lap < 2; lap++) {
      stand(t, 100, 0);
      stand(t, 100, 100);
      stand(t, 0, 100);
      stand(t, 0, 0);
    }
    expect(t.finished).toBe(true);
    expect(t.lap).toBe(2);
    const ms = t.finishMs;
    stand(t, 100, 0, 60);
    expect(t.finishMs).toBe(ms);
    expect(t.passedTotal).toBe(8);
  });

  test('lap times are measured and best lap tracked', () => {
    const t = new LapTracker(squareGates(), 3);
    // Lap 1: 40 steps standing around + the 4 gate steps.
    stand(t, 50, 50, 40);
    stand(t, 100, 0);
    stand(t, 100, 100);
    stand(t, 0, 100);
    stand(t, 0, 0);
    // Lap 2: faster (only the gate steps).
    stand(t, 100, 0);
    stand(t, 100, 100);
    stand(t, 0, 100);
    stand(t, 0, 0);
    expect(t.lapTimes.length).toBe(2);
    expect(t.lapTimes[1]).toBeLessThan(t.lapTimes[0] as number);
    expect(t.bestLapMs).toBe(t.lapTimes[1]);
  });

  test('wrong-way raises only after sustained reversed motion and clears', () => {
    const t = new LapTracker(squareGates(), 3);
    // A brief blip against the tangent: no flag.
    for (let i = 0; i < 20; i++) t.update(DT, 50, 50, -6);
    expect(t.wrongWay).toBe(false);
    // Sustained: flag.
    for (let i = 0; i < 30; i++) t.update(DT, 50, 50, -6);
    expect(t.wrongWay).toBe(true);
    // Driving forward again clears it.
    for (let i = 0; i < 5; i++) t.update(DT, 50, 50, 6);
    expect(t.wrongWay).toBe(false);
  });

  test('lastPassed tracks the respawn anchor', () => {
    const t = new LapTracker(squareGates(), 3);
    expect(t.lastPassed).toBe(0);
    stand(t, 100, 0);
    stand(t, 100, 100);
    expect(t.lastPassed).toBe(2);
  });
});

describe('race standings', () => {
  const racer = (
    id: string,
    p: Partial<RacerProgress>,
  ): RacerProgress => ({
    id,
    finished: false,
    finishMs: 0,
    passedTotal: 0,
    distToNext: 0,
    ...p,
  });

  test('more gates passed ranks ahead; distance to next breaks ties', () => {
    const order = [
      racer('a', { passedTotal: 5, distToNext: 80 }),
      racer('b', { passedTotal: 7, distToNext: 10 }),
      racer('c', { passedTotal: 7, distToNext: 40 }),
    ].sort(compareRacers);
    expect(order.map((r) => r.id)).toEqual(['b', 'c', 'a']);
  });

  test('finishers rank ahead of everyone, ordered by finish time', () => {
    const order = [
      racer('slowFinisher', { finished: true, finishMs: 90_000 }),
      racer('leaderOnTrack', { passedTotal: 99, distToNext: 1 }),
      racer('fastFinisher', { finished: true, finishMs: 80_000 }),
    ].sort(compareRacers);
    expect(order.map((r) => r.id)).toEqual(['fastFinisher', 'slowFinisher', 'leaderOnTrack']);
  });

  test('formatMs renders mm:ss.cc and tolerates Infinity', () => {
    expect(formatMs(83_456)).toBe('1:23.46');
    expect(formatMs(0)).toBe('0:00.00');
    expect(formatMs(Infinity)).toBe('--:--.--');
  });
});
