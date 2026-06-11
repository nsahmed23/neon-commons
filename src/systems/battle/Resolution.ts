/**
 * Battle resolution engine — pure, deterministic given a seeded Rng,
 * no three.js/DOM. Every observable consequence of an action is pushed
 * as a typed BattleEvent; the battle log and all presentation derive
 * from these events (describeEvent), never from parallel strings.
 *
 * Damage formula:
 *   dmg = max(1, round(power * (atkEff / defEff) * typeMult
 *         * surgeCore? * reactivePlating? * aegis? * variance))
 *   atkEff/defEff include stat-stage multipliers; variance is a seeded
 *   roll in [0.9, 1.0).
 */

import type { Rng } from '../../core/Rng';
import { getMove, isAttack, type MoveDef } from './Moves';
import {
  AEGIS_DAMAGE_MUL,
  CORROSION_FRACTION,
  FLUX_LEAK_ENERGY,
  NANOREPAIR_FRACTION,
  SERVO_LAG_SPEED_MUL,
  STATUS_DEFS,
  STAT_LABEL,
  addStatus,
  applyStageDelta,
  createStages,
  hasStatus,
  stageMultiplier,
  type ActiveStatus,
  type StatKey,
  type StatStages,
  type StatusId,
} from './Statuses';
import { typeMultiplier } from './TypeChart';
import {
  CAPACITOR_BANK_BONUS,
  PASSIVE_DEFS,
  REACTIVE_PLATING_MUL,
  SIPHON_CIRCUIT_FRACTION,
  SURGE_CORE_MUL,
  SURGE_CORE_THRESHOLD,
  getSpec,
  type UnitSpec,
} from './Units';

export const ENERGY_REGEN = 10;
export const VARIANCE_MIN = 0.9;
export const VARIANCE_SPAN = 0.1;

export type Side = 0 | 1;

export interface UnitState {
  /** index into BattleState.units */
  id: number;
  spec: UnitSpec;
  side: Side;
  hp: number;
  energy: number;
  stages: StatStages;
  statuses: ActiveStatus[];
  /** moveId -> turns until usable again */
  cooldowns: Record<string, number>;
  alive: boolean;
}

export interface BattleState {
  units: UnitState[];
  round: number;
}

export interface Action {
  userId: number;
  moveId: string;
  targetId: number;
}

// ---- events (the anti-faking layer) ------------------------------------

export type BattleEvent =
  | { kind: 'move-used'; userId: number; moveId: string; targetId: number }
  | {
      kind: 'damage';
      userId: number;
      targetId: number;
      moveId: string;
      amount: number;
      typeMult: number;
      shielded: boolean;
    }
  | { kind: 'heal'; targetId: number; amount: number; source: string }
  | { kind: 'status-applied'; targetId: number; status: StatusId; turns: number }
  | { kind: 'status-refreshed'; targetId: number; status: StatusId; turns: number }
  | { kind: 'status-immune'; targetId: number; status: StatusId; passive: string }
  | { kind: 'status-resisted'; targetId: number; status: StatusId }
  | { kind: 'status-tick'; targetId: number; status: StatusId; amount: number }
  | { kind: 'status-expired'; targetId: number; status: StatusId }
  | { kind: 'stat-change'; targetId: number; stat: StatKey; delta: number; stage: number }
  | { kind: 'stat-blocked'; targetId: number; stat: StatKey; passive: string }
  | { kind: 'stat-at-limit'; targetId: number; stat: StatKey; rising: boolean }
  | { kind: 'energy'; targetId: number; amount: number; source: string }
  | { kind: 'ko'; targetId: number }
  | { kind: 'skip-lockup'; userId: number }
  | { kind: 'passive'; userId: number; passive: string; note: string };

// ---- construction ---------------------------------------------------------

export function createUnit(specId: string, id: number, side: Side): UnitState {
  const spec = getSpec(specId);
  return {
    id,
    spec,
    side,
    hp: spec.maxHp,
    energy: spec.maxEnergy,
    stages: createStages(),
    statuses: [],
    cooldowns: {},
    alive: true,
  };
}

export function createBattle(
  playerSpecIds: readonly string[],
  enemySpecIds: readonly string[],
): BattleState {
  const units: UnitState[] = [];
  for (const specId of playerSpecIds) units.push(createUnit(specId, units.length, 0));
  for (const specId of enemySpecIds) units.push(createUnit(specId, units.length, 1));
  return { units, round: 1 };
}

// ---- derived values ----------------------------------------------------

export function effectiveStat(unit: UnitState, key: StatKey): number {
  let v = unit.spec[key] * stageMultiplier(unit.stages[key]);
  if (key === 'spd' && hasStatus(unit.statuses, 'servoLag')) v *= SERVO_LAG_SPEED_MUL;
  return v;
}

export function livingUnits(state: BattleState, side?: Side): UnitState[] {
  return state.units.filter((u) => u.alive && (side === undefined || u.side === side));
}

/** 0 or 1 when that side has won, null while both sides have living units. */
export function winner(state: BattleState): Side | null {
  const p = livingUnits(state, 0).length;
  const e = livingUnits(state, 1).length;
  if (p > 0 && e === 0) return 0;
  if (e > 0 && p === 0) return 1;
  return null;
}

// ---- legality ---------------------------------------------------------------

export function validTargets(state: BattleState, user: UnitState, move: MoveDef): UnitState[] {
  if (move.target === 'self') return user.alive ? [user] : [];
  if (move.target === 'ally') return livingUnits(state, user.side);
  return livingUnits(state, user.side === 0 ? 1 : 0);
}

export function canUse(user: UnitState, move: MoveDef): boolean {
  if (!user.alive) return false;
  if (user.energy < move.energy) return false;
  if ((user.cooldowns[move.id] ?? 0) > 0) return false;
  return true;
}

export interface LegalOption {
  move: MoveDef;
  targets: UnitState[];
}

/**
 * Every legal (move, target-set) for the unit. The Vent fallback is
 * always appended so a unit out of energy still has a turn.
 */
export function legalOptions(state: BattleState, userId: number): LegalOption[] {
  const user = state.units[userId];
  if (!user || !user.alive) return [];
  const out: LegalOption[] = [];
  for (const moveId of user.spec.moves) {
    const move = getMove(moveId);
    if (!canUse(user, move)) continue;
    const targets = validTargets(state, user, move);
    if (targets.length > 0) out.push({ move, targets });
  }
  out.push({ move: getMove('vent'), targets: [user] });
  return out;
}

// ---- damage ----------------------------------------------------------------

export interface DamagePreview {
  min: number;
  max: number;
  typeMult: number;
}

/** Deterministic damage bounds (used by the AI; no RNG consumed). */
export function previewDamage(user: UnitState, target: UnitState, move: MoveDef): DamagePreview {
  if (!isAttack(move)) return { min: 0, max: 0, typeMult: 1 };
  const base = rawDamage(user, target, move);
  return {
    min: Math.max(1, Math.round(base * VARIANCE_MIN)),
    max: Math.max(1, Math.round(base * (VARIANCE_MIN + VARIANCE_SPAN))),
    typeMult: typeMultiplier(move.type, target.spec.type),
  };
}

function rawDamage(user: UnitState, target: UnitState, move: MoveDef): number {
  const atk = effectiveStat(user, 'atk');
  const def = effectiveStat(target, 'def');
  let dmg = move.power * (atk / def) * typeMultiplier(move.type, target.spec.type);
  if (user.spec.passive === 'surgeCore' && user.hp < user.spec.maxHp * SURGE_CORE_THRESHOLD) {
    dmg *= SURGE_CORE_MUL;
  }
  if (target.spec.passive === 'reactivePlating') dmg *= REACTIVE_PLATING_MUL;
  if (hasStatus(target.statuses, 'aegisField')) dmg *= AEGIS_DAMAGE_MUL;
  return dmg;
}

// ---- execution -------------------------------------------------------------

/**
 * Execute one action. Mutates state, pushes every consequence into
 * `events`. Throws on illegal actions (callers gate via legalOptions).
 */
export function executeMove(
  state: BattleState,
  action: Action,
  rng: Rng,
  events: BattleEvent[],
): void {
  const user = state.units[action.userId];
  const target = state.units[action.targetId];
  if (!user || !target) throw new Error('executeMove: bad unit id');
  const move = getMove(action.moveId);
  if (!canUse(user, move)) throw new Error(`executeMove: illegal move ${move.id}`);
  if (!target.alive) throw new Error('executeMove: dead target');

  user.energy -= move.energy;
  if (move.cooldown > 0) user.cooldowns[move.id] = move.cooldown + 1; // decremented at end of this turn
  events.push({ kind: 'move-used', userId: user.id, moveId: move.id, targetId: target.id });

  // Damage.
  if (isAttack(move)) {
    const variance = VARIANCE_MIN + VARIANCE_SPAN * rng.next();
    const amount = Math.max(1, Math.round(rawDamage(user, target, move) * variance));
    const shielded = hasStatus(target.statuses, 'aegisField');
    applyDamage(target, amount, events, {
      kind: 'damage',
      userId: user.id,
      targetId: target.id,
      moveId: move.id,
      amount,
      typeMult: typeMultiplier(move.type, target.spec.type),
      shielded,
    });
    if (user.spec.passive === 'siphonCircuit' && user.alive) {
      const heal = Math.round(amount * SIPHON_CIRCUIT_FRACTION);
      if (heal > 0 && user.hp < user.spec.maxHp) {
        const healed = applyHeal(user, heal);
        events.push({ kind: 'passive', userId: user.id, passive: PASSIVE_DEFS.siphonCircuit.name, note: 'siphons the impact' });
        events.push({ kind: 'heal', targetId: user.id, amount: healed, source: PASSIVE_DEFS.siphonCircuit.name });
      }
    }
  }

  // Healing.
  if ((move.healFraction ?? 0) > 0 && target.alive) {
    const healed = applyHeal(target, Math.round(target.spec.maxHp * (move.healFraction as number)));
    events.push({ kind: 'heal', targetId: target.id, amount: healed, source: move.name });
  }

  // Status application.
  if (move.status && target.alive) {
    tryApplyStatus(target, move.status, rng, move.statusChance ?? 1, events);
  }

  // Stat stages.
  if (move.stages && target.alive) {
    for (const key of Object.keys(move.stages) as StatKey[]) {
      applyStatStage(target, key, move.stages[key] as number, events);
    }
  }

  // Energy drain / restore.
  if ((move.energyDrain ?? 0) > 0 && target.alive) {
    const drained = Math.min(target.energy, move.energyDrain as number);
    target.energy -= drained;
    events.push({ kind: 'energy', targetId: target.id, amount: -drained, source: move.name });
  }
  if ((move.energyRestore ?? 0) > 0) {
    const gained = Math.min(user.spec.maxEnergy - user.energy, move.energyRestore as number);
    user.energy += gained;
    events.push({ kind: 'energy', targetId: user.id, amount: gained, source: move.name });
  }
}

function applyDamage(
  target: UnitState,
  amount: number,
  events: BattleEvent[],
  damageEvent: BattleEvent,
): void {
  target.hp = Math.max(0, target.hp - amount);
  events.push(damageEvent);
  if (target.hp === 0 && target.alive) {
    target.alive = false;
    target.statuses.length = 0;
    events.push({ kind: 'ko', targetId: target.id });
  }
}

function applyHeal(target: UnitState, amount: number): number {
  const healed = Math.min(target.spec.maxHp - target.hp, amount);
  target.hp += healed;
  return healed;
}

export function tryApplyStatus(
  target: UnitState,
  status: StatusId,
  rng: Rng,
  chance: number,
  events: BattleEvent[],
): void {
  // Passive immunities.
  if (status === 'corrosion' && target.spec.passive === 'thermalShroud') {
    events.push({ kind: 'status-immune', targetId: target.id, status, passive: PASSIVE_DEFS.thermalShroud.name });
    return;
  }
  if (status === 'servoLag' && target.spec.passive === 'gyroGimbal') {
    events.push({ kind: 'status-immune', targetId: target.id, status, passive: PASSIVE_DEFS.gyroGimbal.name });
    return;
  }
  if (chance < 1 && !rng.chance(chance)) {
    events.push({ kind: 'status-resisted', targetId: target.id, status });
    return;
  }
  const turns = STATUS_DEFS[status].duration;
  const result = addStatus(target.statuses, status, turns);
  events.push({
    kind: result === 'applied' ? 'status-applied' : 'status-refreshed',
    targetId: target.id,
    status,
    turns,
  });
}

export function applyStatStage(
  target: UnitState,
  key: StatKey,
  delta: number,
  events: BattleEvent[],
): void {
  if (delta < 0 && key === 'spd' && target.spec.passive === 'gyroGimbal') {
    events.push({ kind: 'stat-blocked', targetId: target.id, stat: key, passive: PASSIVE_DEFS.gyroGimbal.name });
    return;
  }
  const changed = applyStageDelta(target.stages, key, delta);
  if (changed === 0) {
    events.push({ kind: 'stat-at-limit', targetId: target.id, stat: key, rising: delta > 0 });
  } else {
    events.push({ kind: 'stat-change', targetId: target.id, stat: key, delta: changed, stage: target.stages[key] });
  }
}

// ---- turn bookkeeping -----------------------------------------------------

/**
 * True when the unit's action this turn is consumed by Lockup.
 * Emits the skip event (the status still ticks down at end of turn).
 */
export function checkLockup(unit: UnitState, events: BattleEvent[]): boolean {
  if (hasStatus(unit.statuses, 'lockup')) {
    events.push({ kind: 'skip-lockup', userId: unit.id });
    return true;
  }
  return false;
}

/**
 * End-of-turn bookkeeping for ONE unit, in order: status ticks
 * (corrosion damage, nanorepair heal, flux leak drain), status expiry,
 * energy regeneration, cooldown decrement.
 */
export function endOfUnitTurn(state: BattleState, unitId: number, events: BattleEvent[]): void {
  const unit = state.units[unitId];
  if (!unit || !unit.alive) return;

  for (const st of [...unit.statuses]) {
    if (st.id === 'corrosion') {
      const dmg = Math.max(1, Math.round(unit.spec.maxHp * CORROSION_FRACTION));
      events.push({ kind: 'status-tick', targetId: unit.id, status: 'corrosion', amount: -dmg });
      unit.hp = Math.max(0, unit.hp - dmg);
      if (unit.hp === 0) {
        unit.alive = false;
        unit.statuses.length = 0;
        events.push({ kind: 'ko', targetId: unit.id });
        return;
      }
    } else if (st.id === 'nanorepair') {
      const heal = applyHeal(unit, Math.round(unit.spec.maxHp * NANOREPAIR_FRACTION));
      events.push({ kind: 'status-tick', targetId: unit.id, status: 'nanorepair', amount: heal });
    } else if (st.id === 'fluxLeak') {
      const drain = Math.min(unit.energy, FLUX_LEAK_ENERGY);
      unit.energy -= drain;
      events.push({ kind: 'status-tick', targetId: unit.id, status: 'fluxLeak', amount: -drain });
    }
    st.turnsLeft--;
    if (st.turnsLeft <= 0) {
      const i = unit.statuses.indexOf(st);
      if (i >= 0) unit.statuses.splice(i, 1);
      events.push({ kind: 'status-expired', targetId: unit.id, status: st.id });
    }
  }

  // Energy regeneration.
  let regen = ENERGY_REGEN;
  if (unit.spec.passive === 'capacitorBank') regen += CAPACITOR_BANK_BONUS;
  const gained = Math.min(unit.spec.maxEnergy - unit.energy, regen);
  if (gained > 0) {
    unit.energy += gained;
    events.push({ kind: 'energy', targetId: unit.id, amount: gained, source: 'regeneration' });
  }

  // Cooldowns tick down at the end of the unit's own turn.
  for (const moveId of Object.keys(unit.cooldowns)) {
    const left = (unit.cooldowns[moveId] as number) - 1;
    if (left <= 0) delete unit.cooldowns[moveId];
    else unit.cooldowns[moveId] = left;
  }
}

// ---- plain-sentence log (derived from events, never parallel) -------------

function multText(mult: number): string {
  if (mult >= 2) return ' (2x type advantage)';
  if (mult <= 0.5) return ' (0.5x resisted)';
  return '';
}

export function describeEvent(state: BattleState, e: BattleEvent): string {
  const name = (id: number): string => state.units[id]?.spec.name ?? `Unit ${id}`;
  switch (e.kind) {
    case 'move-used': {
      const move = getMove(e.moveId);
      return e.userId === e.targetId
        ? `${name(e.userId)} uses ${move.name}.`
        : `${name(e.userId)} uses ${move.name} on ${name(e.targetId)}.`;
    }
    case 'damage':
      return `${name(e.targetId)} takes ${e.amount} damage${multText(e.typeMult)}${
        e.shielded ? ', halved by the Aegis Field' : ''
      }.`;
    case 'heal':
      return `${name(e.targetId)} recovers ${e.amount} HP from ${e.source}.`;
    case 'status-applied': {
      const def = STATUS_DEFS[e.status];
      return `${name(e.targetId)} is now ${def.name} (${def.blurb}, ${e.turns} turns).`;
    }
    case 'status-refreshed':
      return `${name(e.targetId)}'s ${STATUS_DEFS[e.status].name} state is refreshed (${e.turns} turns).`;
    case 'status-immune':
      return `${name(e.targetId)}'s ${e.passive} blocks ${STATUS_DEFS[e.status].name}.`;
    case 'status-resisted':
      return `${name(e.targetId)} shrugs off the ${STATUS_DEFS[e.status].name} attempt.`;
    case 'status-tick': {
      const def = STATUS_DEFS[e.status];
      if (e.status === 'nanorepair') return `${name(e.targetId)} repairs ${e.amount} HP (${def.name}).`;
      if (e.status === 'fluxLeak') return `${name(e.targetId)} leaks ${-e.amount} energy (${def.name}).`;
      return `${name(e.targetId)} takes ${-e.amount} damage from ${def.name}.`;
    }
    case 'status-expired':
      return `${name(e.targetId)} is no longer ${STATUS_DEFS[e.status].name}.`;
    case 'stat-change': {
      const dir = e.delta > 0 ? 'rises' : 'falls';
      const steps = Math.abs(e.delta);
      return `${name(e.targetId)}'s ${STAT_LABEL[e.stat]} ${dir}${steps > 1 ? ' sharply' : ''} (stage ${e.stage >= 0 ? '+' : ''}${e.stage}).`;
    }
    case 'stat-blocked':
      return `${name(e.targetId)}'s ${e.passive} keeps its ${STAT_LABEL[e.stat]} steady.`;
    case 'stat-at-limit':
      return `${name(e.targetId)}'s ${STAT_LABEL[e.stat]} can't go any ${e.rising ? 'higher' : 'lower'}.`;
    case 'energy':
      return e.amount >= 0
        ? `${name(e.targetId)} gains ${e.amount} energy (${e.source}).`
        : `${name(e.targetId)} loses ${-e.amount} energy (${e.source}).`;
    case 'ko':
      return `${name(e.targetId)} is knocked out!`;
    case 'skip-lockup':
      return `${name(e.userId)} is Locked Up and cannot act.`;
    case 'passive':
      return `${name(e.userId)}'s ${e.passive} ${e.note}.`;
  }
}
