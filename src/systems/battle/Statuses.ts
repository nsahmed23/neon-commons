/**
 * Status effects and stat stages — pure data + helpers, no three.js/DOM.
 *
 * Statuses (6, original names):
 *   corrosion  — burn analog: loses 6% max HP at end of its own turn
 *   servoLag   — slow: effective speed halved while active
 *   aegisField — shield: incoming attack damage halved
 *   nanorepair — regen: restores 8% max HP at end of its own turn
 *   lockup     — stun: skips its next action
 *   fluxLeak   — energy drain: loses 8 energy at end of its own turn
 *
 * Stacking rule: a status NEVER stacks with itself; re-applying refreshes
 * the duration to the new value (if longer) and emits a refresh event.
 *
 * Stat stages (buffs/debuffs): atk/def/spd stages clamped to [-3, +3],
 * additive stacking within the clamp. Multiplier (3+s)/3 for s >= 0,
 * 3/(3-s) for s < 0, so +3 = 2.0x and -3 = 0.5x.
 */

export const STATUS_IDS = [
  'corrosion',
  'servoLag',
  'aegisField',
  'nanorepair',
  'lockup',
  'fluxLeak',
] as const;
export type StatusId = (typeof STATUS_IDS)[number];

export interface StatusDef {
  id: StatusId;
  name: string;
  /** plain-language effect, used by HUD tooltips and the log */
  blurb: string;
  /** default duration in the afflicted unit's own turns */
  duration: number;
  harmful: boolean;
}

export const STATUS_DEFS: Record<StatusId, StatusDef> = {
  corrosion: {
    id: 'corrosion',
    name: 'Corroded',
    blurb: 'loses 6% max HP each turn',
    duration: 3,
    harmful: true,
  },
  servoLag: {
    id: 'servoLag',
    name: 'Servo-Lagged',
    blurb: 'speed halved',
    duration: 2,
    harmful: true,
  },
  aegisField: {
    id: 'aegisField',
    name: 'Aegis-Shielded',
    blurb: 'incoming damage halved',
    duration: 2,
    harmful: false,
  },
  nanorepair: {
    id: 'nanorepair',
    name: 'Nanorepairing',
    blurb: 'restores 8% max HP each turn',
    duration: 3,
    harmful: false,
  },
  lockup: {
    id: 'lockup',
    name: 'Locked Up',
    blurb: 'skips its next action',
    duration: 1,
    harmful: true,
  },
  fluxLeak: {
    id: 'fluxLeak',
    name: 'Flux-Leaking',
    blurb: 'loses 8 energy each turn',
    duration: 3,
    harmful: true,
  },
};

/** Per-turn magnitudes (fractions of max HP, flat energy). */
export const CORROSION_FRACTION = 0.06;
export const NANOREPAIR_FRACTION = 0.08;
export const FLUX_LEAK_ENERGY = 8;
export const SERVO_LAG_SPEED_MUL = 0.5;
export const AEGIS_DAMAGE_MUL = 0.5;

export interface ActiveStatus {
  id: StatusId;
  turnsLeft: number;
}

// ---- stat stages -----------------------------------------------------

export type StatKey = 'atk' | 'def' | 'spd';
export const STAGE_MIN = -3;
export const STAGE_MAX = 3;

export interface StatStages {
  atk: number;
  def: number;
  spd: number;
}

export function createStages(): StatStages {
  return { atk: 0, def: 0, spd: 0 };
}

/** Multiplier for a stage: +3 -> 2.0, +1 -> 1.333, 0 -> 1, -3 -> 0.5. */
export function stageMultiplier(stage: number): number {
  return stage >= 0 ? (3 + stage) / 3 : 3 / (3 - stage);
}

/**
 * Apply a stage delta with clamping. Returns how many stages actually
 * changed (0 when already at the clamp — callers report "won't go
 * higher/lower" from that).
 */
export function applyStageDelta(stages: StatStages, key: StatKey, delta: number): number {
  const before = stages[key];
  const after = Math.max(STAGE_MIN, Math.min(STAGE_MAX, before + delta));
  stages[key] = after;
  return after - before;
}

export const STAT_LABEL: Record<StatKey, string> = {
  atk: 'attack',
  def: 'defense',
  spd: 'speed',
};

// ---- active status helpers --------------------------------------------

export function hasStatus(list: readonly ActiveStatus[], id: StatusId): boolean {
  return list.some((s) => s.id === id);
}

/**
 * Add or refresh a status. Returns 'applied' when new, 'refreshed' when
 * already present (duration extended to at least the new duration —
 * the no-stack rule).
 */
export function addStatus(
  list: ActiveStatus[],
  id: StatusId,
  duration: number,
): 'applied' | 'refreshed' {
  const existing = list.find((s) => s.id === id);
  if (existing) {
    existing.turnsLeft = Math.max(existing.turnsLeft, duration);
    return 'refreshed';
  }
  list.push({ id, turnsLeft: duration });
  return 'applied';
}

export function removeStatus(list: ActiveStatus[], id: StatusId): void {
  const i = list.findIndex((s) => s.id === id);
  if (i >= 0) list.splice(i, 1);
}
