/**
 * Flight scoring + the typed event stream (the anti-faking layer, same
 * pattern as battle's BattleEvent/describeEvent and board's
 * BoardEvent). The mode pushes a FlightEvent for everything observable
 * (ring passes from real detection, kills from real projectile hits,
 * boss phases from real state); the score, the results breakdown, and
 * every HUD callout derive from this stream. There are no parallel
 * strings and no score writes outside applyFlightEvent.
 */

import type { BossPhase, EnemyAIState } from './DroneAI';

export type FlightEvent =
  | { kind: 'ring-pass'; index: number; total: number }
  | { kind: 'shot-fired'; by: 'player' | 'enemy' | 'boss' }
  | { kind: 'shot-hit'; targetId: number }
  | { kind: 'player-hit'; amount: number; hp: number }
  | { kind: 'drone-state'; droneId: number; to: EnemyAIState }
  | { kind: 'drone-kill'; droneId: number }
  | { kind: 'boss-shield-blocked' }
  | { kind: 'boss-hit'; amount: number; hp: number }
  | { kind: 'boss-phase'; phase: BossPhase }
  | { kind: 'boss-kill' }
  | { kind: 'course-complete' }
  | { kind: 'player-down' };

export const SCORE = {
  ringPass: 100,
  droneKill: 250,
  bossKill: 1000,
  /** accuracy bonus = round(hits / shots * accuracyMax); 0 if no shots */
  accuracyMax: 500,
} as const;

export interface FlightScore {
  rings: number;
  droneKills: number;
  bossKilled: boolean;
  shotsFired: number;
  shotsHit: number;
  /** running score from ring passes + kills (no accuracy yet) */
  base: number;
}

export function createScore(): FlightScore {
  return { rings: 0, droneKills: 0, bossKilled: false, shotsFired: 0, shotsHit: 0, base: 0 };
}

/**
 * Fold one event into the score. ONLY scoring events change `base`;
 * being hit, AI chatter, and shield blocks never do.
 */
export function applyFlightEvent(s: FlightScore, ev: FlightEvent): void {
  switch (ev.kind) {
    case 'ring-pass':
      s.rings++;
      s.base += SCORE.ringPass;
      break;
    case 'drone-kill':
      s.droneKills++;
      s.base += SCORE.droneKill;
      break;
    case 'boss-kill':
      s.bossKilled = true;
      s.base += SCORE.bossKill;
      break;
    case 'shot-fired':
      if (ev.by === 'player') s.shotsFired++;
      break;
    case 'shot-hit':
      s.shotsHit++;
      break;
    default:
      break;
  }
}

export function accuracy(s: FlightScore): number {
  return s.shotsFired === 0 ? 0 : s.shotsHit / s.shotsFired;
}

export function accuracyBonus(s: FlightScore): number {
  return Math.round(accuracy(s) * SCORE.accuracyMax);
}

export function totalScore(s: FlightScore): number {
  return s.base + accuracyBonus(s);
}

/** Results breakdown rows, derived only from the folded event stream. */
export interface ScoreRow {
  label: string;
  detail: string;
  points: number;
}

export function scoreBreakdown(s: FlightScore): ScoreRow[] {
  const rows: ScoreRow[] = [
    {
      label: 'Rings',
      detail: `${s.rings} × ${SCORE.ringPass}`,
      points: s.rings * SCORE.ringPass,
    },
    {
      label: 'Drone kills',
      detail: `${s.droneKills} × ${SCORE.droneKill}`,
      points: s.droneKills * SCORE.droneKill,
    },
  ];
  if (s.bossKilled) {
    rows.push({ label: 'Boss destroyed', detail: 'WARDEN down', points: SCORE.bossKill });
  }
  rows.push({
    label: 'Accuracy bonus',
    detail: `${s.shotsHit}/${s.shotsFired} hits (${Math.round(accuracy(s) * 100)}%)`,
    points: accuracyBonus(s),
  });
  return rows;
}

/**
 * Dialogue callouts for the toast log. Returns null for events that
 * are presentation-silent (per-shot spam). Every string a player reads
 * traces back to a real event.
 */
export function describeFlightEvent(ev: FlightEvent): string | null {
  switch (ev.kind) {
    case 'ring-pass':
      return ev.index + 1 === ev.total
        ? `Final ring ${ev.index + 1}/${ev.total} — course complete. The WARDEN is waking up over the lake.`
        : `Ring ${ev.index + 1}/${ev.total} clear.`;
    case 'player-hit':
      return `Hull hit — integrity ${ev.hp}%.`;
    case 'drone-state':
      if (ev.to === 'engage') return `Sentry ${ev.droneId + 1} has a lock on you.`;
      if (ev.to === 'evade') return `Sentry ${ev.droneId + 1} is smoking and breaking off!`;
      return null; // back to patrol: silent
    case 'drone-kill':
      return `Sentry ${ev.droneId + 1} destroyed. +${SCORE.droneKill}`;
    case 'boss-shield-blocked':
      return 'No effect — the WARDEN is shielded while its escorts live.';
    case 'boss-phase':
      if (ev.phase === 'vulnerable') return 'Escorts down — the WARDEN shield is OPEN. Hit it now!';
      if (ev.phase === 'enraged') return 'The WARDEN is enraged — watch its volleys!';
      return null;
    case 'boss-kill':
      return `WARDEN destroyed! +${SCORE.bossKill}`;
    case 'course-complete':
      return null; // the final ring-pass line carries the callout
    case 'player-down':
      return 'Hull integrity zero — drone down.';
    default:
      return null;
  }
}
