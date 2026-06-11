import { describe, expect, test } from 'vitest';
import {
  SCORE,
  accuracy,
  accuracyBonus,
  applyFlightEvent,
  createScore,
  describeFlightEvent,
  scoreBreakdown,
  totalScore,
  type FlightEvent,
} from '../src/systems/flight/Scoring';

function fold(events: FlightEvent[]): ReturnType<typeof createScore> {
  const s = createScore();
  for (const ev of events) applyFlightEvent(s, ev);
  return s;
}

describe('scoring from scripted event streams', () => {
  test('a full scripted run produces the exact expected total', () => {
    const events: FlightEvent[] = [];
    for (let i = 0; i < 10; i++) events.push({ kind: 'ring-pass', index: i, total: 10 });
    // 20 player shots, 12 hits, 2 drone kills, then the boss.
    for (let i = 0; i < 20; i++) events.push({ kind: 'shot-fired', by: 'player' });
    for (let i = 0; i < 12; i++) events.push({ kind: 'shot-hit', targetId: i % 3 });
    events.push({ kind: 'drone-kill', droneId: 0 });
    events.push({ kind: 'drone-kill', droneId: 1 });
    events.push({ kind: 'course-complete' });
    events.push({ kind: 'boss-phase', phase: 'vulnerable' });
    events.push({ kind: 'boss-kill' });
    const s = fold(events);
    const expectedBase = 10 * SCORE.ringPass + 2 * SCORE.droneKill + SCORE.bossKill;
    expect(s.base).toBe(expectedBase);
    expect(accuracy(s)).toBeCloseTo(0.6, 9);
    expect(accuracyBonus(s)).toBe(Math.round(0.6 * SCORE.accuracyMax));
    expect(totalScore(s)).toBe(expectedBase + 300);
  });

  test('non-scoring events never change the score', () => {
    const s = fold([
      { kind: 'player-hit', amount: 8, hp: 92 },
      { kind: 'boss-shield-blocked' },
      { kind: 'drone-state', droneId: 0, to: 'engage' },
      { kind: 'boss-phase', phase: 'enraged' },
      { kind: 'shot-fired', by: 'enemy' },
      { kind: 'shot-fired', by: 'boss' },
      { kind: 'player-down' },
    ]);
    expect(totalScore(s)).toBe(0);
    expect(s.shotsFired).toBe(0); // enemy/boss shots don't touch accuracy
  });

  test('accuracy bonus is 0 when no shots were fired (no NaN)', () => {
    const s = fold([{ kind: 'ring-pass', index: 0, total: 10 }]);
    expect(accuracy(s)).toBe(0);
    expect(accuracyBonus(s)).toBe(0);
    expect(totalScore(s)).toBe(SCORE.ringPass);
  });

  test('breakdown rows are derived from the folded stream and sum to the total', () => {
    const s = fold([
      { kind: 'ring-pass', index: 0, total: 10 },
      { kind: 'ring-pass', index: 1, total: 10 },
      { kind: 'shot-fired', by: 'player' },
      { kind: 'shot-fired', by: 'player' },
      { kind: 'shot-hit', targetId: 0 },
      { kind: 'drone-kill', droneId: 0 },
      { kind: 'boss-kill' },
    ]);
    const rows = scoreBreakdown(s);
    expect(rows.map((r) => r.label)).toStrictEqual([
      'Rings', 'Drone kills', 'Boss destroyed', 'Accuracy bonus',
    ]);
    const sum = rows.reduce((acc, r) => acc + r.points, 0);
    expect(sum).toBe(totalScore(s));
    expect(rows[0]?.detail).toBe('2 × 100');
    expect(rows[3]?.detail).toContain('1/2 hits (50%)');
  });

  test('no boss row when the boss survived', () => {
    const rows = scoreBreakdown(fold([{ kind: 'ring-pass', index: 0, total: 10 }]));
    expect(rows.some((r) => r.label === 'Boss destroyed')).toBe(false);
  });

  test('describeFlightEvent produces the exact callout sentences', () => {
    expect(describeFlightEvent({ kind: 'ring-pass', index: 2, total: 10 })).toBe('Ring 3/10 clear.');
    expect(describeFlightEvent({ kind: 'ring-pass', index: 9, total: 10 })).toBe(
      'Final ring 10/10 — course complete. The WARDEN is waking up over the lake.',
    );
    expect(describeFlightEvent({ kind: 'player-hit', amount: 8, hp: 92 })).toBe(
      'Hull hit — integrity 92%.',
    );
    expect(describeFlightEvent({ kind: 'drone-kill', droneId: 1 })).toBe('Sentry 2 destroyed. +250');
    expect(describeFlightEvent({ kind: 'boss-phase', phase: 'vulnerable' })).toBe(
      'Escorts down — the WARDEN shield is OPEN. Hit it now!',
    );
    expect(describeFlightEvent({ kind: 'boss-shield-blocked' })).toBe(
      'No effect — the WARDEN is shielded while its escorts live.',
    );
  });

  test('per-shot spam and silent events return null (no toast flooding)', () => {
    expect(describeFlightEvent({ kind: 'shot-fired', by: 'player' })).toBeNull();
    expect(describeFlightEvent({ kind: 'shot-hit', targetId: 0 })).toBeNull();
    expect(describeFlightEvent({ kind: 'course-complete' })).toBeNull();
    expect(describeFlightEvent({ kind: 'drone-state', droneId: 0, to: 'patrol' })).toBeNull();
  });
});
