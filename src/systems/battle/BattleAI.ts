/**
 * Enemy AI — pure, deterministic given a seeded Rng, no three.js/DOM.
 *
 * Scores EVERY legal (move, target) pair from the acting unit's own
 * perspective using nine named modifiers, picks the maximum, and breaks
 * exact ties with the seeded RNG. The full per-option breakdown is
 * returned so debug mode can print the reasoning into the battle log.
 */

import type { Rng } from '../../core/Rng';
import { isAttack, isDefensive, type MoveDef } from './Moves';
import {
  legalOptions,
  previewDamage,
  type Action,
  type BattleState,
  type UnitState,
} from './Resolution';
import { STAGE_MAX, STAGE_MIN, hasStatus, type StatKey, type StatusId } from './Statuses';

export interface ScoreParts {
  typeAdvantage: number;
  expectedDamage: number;
  koPotential: number;
  healingValue: number;
  statusValue: number;
  buffValue: number;
  cooldownTiming: number;
  survivalRisk: number;
  targetPriority: number;
}

export interface ScoredOption {
  moveId: string;
  targetId: number;
  total: number;
  parts: ScoreParts;
}

// Larger than any achievable chip-damage total (dmg cap ~78 + type 15 +
// status 16 + focus 8), so a guaranteed KO always wins the argmax.
const KO_BONUS = 100;
const DAMAGE_SCALE = 0.5;
const TYPE_SCALE = 15;
const HEAL_SCALE = 0.5;
const LOW_HP_FRACTION = 0.35;
const LOW_HP_HEAL_MUL = 1.6;
const SURVIVAL_BONUS = 14;
const COOLDOWN_PENALTY = 2;
const TARGET_PRIORITY_SCALE = 8;
const VENT_BASE = 1;
const VENT_LOW_ENERGY_SCALE = 6;

const STATUS_WEIGHT: Record<StatusId, number> = {
  lockup: 16,
  servoLag: 14,
  corrosion: 12,
  aegisField: 12,
  nanorepair: 10,
  fluxLeak: 8,
};

function statusImmune(target: UnitState, status: StatusId): boolean {
  if (status === 'corrosion' && target.spec.passive === 'thermalShroud') return true;
  if (status === 'servoLag' && target.spec.passive === 'gyroGimbal') return true;
  return false;
}

function scoreOption(
  user: UnitState,
  target: UnitState,
  move: MoveDef,
): ScoredOption {
  const parts: ScoreParts = {
    typeAdvantage: 0,
    expectedDamage: 0,
    koPotential: 0,
    healingValue: 0,
    statusValue: 0,
    buffValue: 0,
    cooldownTiming: 0,
    survivalRisk: 0,
    targetPriority: 0,
  };
  const isEnemyTarget = target.side !== user.side;
  let koGuaranteed = false;

  if (isAttack(move) && isEnemyTarget) {
    const dmg = previewDamage(user, target, move);
    const avg = (dmg.min + dmg.max) / 2;
    parts.expectedDamage = Math.min(avg, target.hp) * DAMAGE_SCALE;
    parts.typeAdvantage = (dmg.typeMult - 1) * TYPE_SCALE;
    if (dmg.min >= target.hp) {
      koGuaranteed = true;
      parts.koPotential = KO_BONUS;
    }
    parts.targetPriority = (1 - target.hp / target.spec.maxHp) * TARGET_PRIORITY_SCALE;
  }

  if ((move.healFraction ?? 0) > 0 && !isEnemyTarget) {
    const heal = Math.min(
      Math.round(target.spec.maxHp * (move.healFraction as number)),
      target.spec.maxHp - target.hp,
    );
    let v = heal * HEAL_SCALE;
    if (target.hp < target.spec.maxHp * LOW_HP_FRACTION) v *= LOW_HP_HEAL_MUL;
    parts.healingValue = v;
  }

  if (move.status) {
    const already = hasStatus(target.statuses, move.status);
    const immune = statusImmune(target, move.status);
    if (!already && !immune) {
      parts.statusValue = STATUS_WEIGHT[move.status] * (move.statusChance ?? 1);
    }
  }

  if (move.stages) {
    for (const key of Object.keys(move.stages) as StatKey[]) {
      const delta = move.stages[key] as number;
      const blocked = delta < 0 && key === 'spd' && target.spec.passive === 'gyroGimbal';
      if (blocked) continue;
      const before = target.stages[key];
      const after = Math.max(STAGE_MIN, Math.min(STAGE_MAX, before + delta));
      const realized = Math.abs(after - before);
      // Buffing an ally (or self) and debuffing an enemy are both worth points.
      const helpful = (delta > 0) !== isEnemyTarget;
      if (helpful) parts.buffValue += realized * 10;
    }
  }

  // Saving long-cooldown moves unless they secure a KO.
  if (move.cooldown > 0 && !koGuaranteed) {
    parts.cooldownTiming = -COOLDOWN_PENALTY * move.cooldown;
  }

  // Self-preservation: at low HP, defensive moves aimed at ourselves gain value.
  if (
    user.hp < user.spec.maxHp * LOW_HP_FRACTION &&
    isDefensive(move) &&
    target.id === user.id
  ) {
    parts.survivalRisk = SURVIVAL_BONUS;
  }

  // Vent: only attractive when the tank is actually empty.
  if ((move.energyRestore ?? 0) > 0) {
    parts.expectedDamage = 0;
    parts.statusValue = 0;
    parts.buffValue =
      VENT_BASE + (1 - user.energy / user.spec.maxEnergy) * VENT_LOW_ENERGY_SCALE;
  }

  const total =
    parts.typeAdvantage +
    parts.expectedDamage +
    parts.koPotential +
    parts.healingValue +
    parts.statusValue +
    parts.buffValue +
    parts.cooldownTiming +
    parts.survivalRisk +
    parts.targetPriority;

  return { moveId: move.id, targetId: target.id, total, parts };
}

/** Score every legal (move, target) pair for the unit. */
export function scoreAllOptions(state: BattleState, userId: number): ScoredOption[] {
  const user = state.units[userId];
  if (!user || !user.alive) return [];
  const out: ScoredOption[] = [];
  for (const opt of legalOptions(state, userId)) {
    for (const target of opt.targets) {
      out.push(scoreOption(user, target, opt.move));
    }
  }
  return out;
}

export interface AIDecision {
  action: Action;
  chosen: ScoredOption;
  /** all options, sorted best-first, for the debug log */
  options: ScoredOption[];
}

const TIE_EPSILON = 1e-9;

/**
 * Pick the best-scoring option; exact ties break via the seeded RNG so
 * a battle replayed from the same seed makes the same choices.
 */
export function chooseAction(state: BattleState, userId: number, rng: Rng): AIDecision | null {
  const options = scoreAllOptions(state, userId);
  if (options.length === 0) return null;
  options.sort((a, b) => b.total - a.total);
  const best = (options[0] as ScoredOption).total;
  const tied = options.filter((o) => best - o.total < TIE_EPSILON);
  const chosen = tied.length === 1 ? (tied[0] as ScoredOption) : rng.pick(tied);
  return {
    action: { userId, moveId: chosen.moveId, targetId: chosen.targetId },
    chosen,
    options,
  };
}

/** One debug line per option: named modifier breakdown for the log. */
export function formatScoreBreakdown(o: ScoredOption): string {
  const p = o.parts;
  const terms: string[] = [];
  const add = (label: string, v: number): void => {
    if (v !== 0) terms.push(`${label} ${v >= 0 ? '+' : ''}${v.toFixed(1)}`);
  };
  add('type', p.typeAdvantage);
  add('dmg', p.expectedDamage);
  add('ko', p.koPotential);
  add('heal', p.healingValue);
  add('status', p.statusValue);
  add('buff', p.buffValue);
  add('cd', p.cooldownTiming);
  add('survive', p.survivalRisk);
  add('focus', p.targetPriority);
  return `${o.total.toFixed(1)} = ${terms.length > 0 ? terms.join(', ') : 'baseline 0'}`;
}
