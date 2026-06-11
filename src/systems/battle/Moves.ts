/**
 * Move catalog — pure data, no three.js/DOM. 15 named moves plus the
 * always-available Vent fallback (energy recovery when a unit cannot
 * afford anything else). Each move has an energy cost, an optional
 * cooldown (turns the user must wait after use), and a bundle of
 * effects resolved by Resolution.ts.
 */

import type { StatKey } from './Statuses';
import type { StatusId } from './Statuses';
import type { UnitType } from './TypeChart';

export type MoveTarget = 'enemy' | 'ally' | 'self';

export interface MoveDef {
  id: string;
  name: string;
  type: UnitType;
  target: MoveTarget;
  energy: number;
  /** turns the user waits before reuse (0 = none) */
  cooldown: number;
  /** attack power; 0 for pure utility moves */
  power: number;
  /** chance [0,1] to apply `status` to the move's target */
  statusChance?: number;
  status?: StatusId;
  /** stat stage deltas applied to the move's target */
  stages?: Partial<Record<StatKey, number>>;
  /** heal the target for this fraction of its max HP */
  healFraction?: number;
  /** drain this much energy from an enemy target immediately */
  energyDrain?: number;
  /** restore this much energy to the user (Vent) */
  energyRestore?: number;
  /** one-line flavor for the HUD */
  blurb: string;
}

export const MOVES: Record<string, MoveDef> = {
  ionLance: {
    id: 'ionLance', name: 'Ion Lance', type: 'volt', target: 'enemy',
    energy: 12, cooldown: 0, power: 55,
    blurb: 'reliable charged spear thrust',
  },
  stormcellBurst: {
    id: 'stormcellBurst', name: 'Stormcell Burst', type: 'volt', target: 'enemy',
    energy: 22, cooldown: 2, power: 72,
    blurb: 'heavy capacitor dump',
  },
  staticShackles: {
    id: 'staticShackles', name: 'Static Shackles', type: 'volt', target: 'enemy',
    energy: 10, cooldown: 1, power: 0, status: 'servoLag', statusChance: 1,
    blurb: 'clamps servos: Servo Lag',
  },
  fluxSiphon: {
    id: 'fluxSiphon', name: 'Flux Siphon', type: 'volt', target: 'enemy',
    energy: 8, cooldown: 1, power: 25, status: 'fluxLeak', statusChance: 1,
    energyDrain: 10,
    blurb: 'taps the target\'s power bus: Flux Leak + energy drain',
  },
  cinderVolley: {
    id: 'cinderVolley', name: 'Cinder Volley', type: 'pyre', target: 'enemy',
    energy: 10, cooldown: 0, power: 50, status: 'corrosion', statusChance: 0.4,
    blurb: 'ember spray, may Corrode',
  },
  furnaceSlam: {
    id: 'furnaceSlam', name: 'Furnace Slam', type: 'pyre', target: 'enemy',
    energy: 24, cooldown: 2, power: 76,
    blurb: 'white-hot body check',
  },
  shieldbreakerMaul: {
    id: 'shieldbreakerMaul', name: 'Shieldbreaker Maul', type: 'pyre', target: 'enemy',
    energy: 16, cooldown: 1, power: 40, stages: { def: -1 },
    blurb: 'cracks plating: -1 defense',
  },
  overclockProtocol: {
    id: 'overclockProtocol', name: 'Overclock Protocol', type: 'volt', target: 'self',
    energy: 10, cooldown: 3, power: 0, stages: { atk: 2 },
    blurb: 'redlines the core: +2 attack',
  },
  cryoSpike: {
    id: 'cryoSpike', name: 'Cryo Spike', type: 'cryo', target: 'enemy',
    energy: 12, cooldown: 0, power: 55,
    blurb: 'supercooled javelin',
  },
  glacierDriver: {
    id: 'glacierDriver', name: 'Glacier Driver', type: 'cryo', target: 'enemy',
    energy: 26, cooldown: 3, power: 78,
    blurb: 'slow, enormous pile-driver',
  },
  hailwall: {
    id: 'hailwall', name: 'Hailwall', type: 'cryo', target: 'ally',
    energy: 14, cooldown: 2, power: 0, status: 'aegisField', statusChance: 1,
    blurb: 'raises an Aegis Field on an ally',
  },
  nanorepairSwarm: {
    id: 'nanorepairSwarm', name: 'Nanorepair Swarm', type: 'cryo', target: 'ally',
    energy: 18, cooldown: 2, power: 0, healFraction: 0.35,
    status: 'nanorepair', statusChance: 1,
    blurb: 'heals 35% max HP and keeps repairing',
  },
  razorGale: {
    id: 'razorGale', name: 'Razor Gale', type: 'aero', target: 'enemy',
    energy: 10, cooldown: 0, power: 50,
    blurb: 'blade-edged crosswind',
  },
  concussionRam: {
    id: 'concussionRam', name: 'Concussion Ram', type: 'aero', target: 'enemy',
    energy: 18, cooldown: 2, power: 65, status: 'lockup', statusChance: 0.3,
    blurb: 'staggering charge, may cause Lockup',
  },
  tailwindRotor: {
    id: 'tailwindRotor', name: 'Tailwind Rotor', type: 'aero', target: 'self',
    energy: 12, cooldown: 2, power: 0, stages: { spd: 2 },
    blurb: 'spools the rotors: +2 speed',
  },
  vent: {
    id: 'vent', name: 'Vent', type: 'aero', target: 'self',
    energy: 0, cooldown: 0, power: 0, energyRestore: 30,
    blurb: 'vents heat and recovers 30 energy',
  },
};

/** Moves that count toward the content minimum (excludes the Vent fallback). */
export const NAMED_MOVE_COUNT = Object.keys(MOVES).length - 1;

export function getMove(id: string): MoveDef {
  const m = MOVES[id];
  if (!m) throw new Error(`Unknown move: ${id}`);
  return m;
}

export function isAttack(move: MoveDef): boolean {
  return move.power > 0;
}

/** Defensive utility = heals or shields (used by AI survival scoring). */
export function isDefensive(move: MoveDef): boolean {
  return (move.healFraction ?? 0) > 0 || move.status === 'aegisField';
}
