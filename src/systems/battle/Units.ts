/**
 * Robot roster + passive abilities — pure data, no three.js/DOM.
 * Original IP: six chassis with callsigns, no franchise echoes.
 *
 * Passives (6):
 *   surgeCore       — outgoing damage +30% while below 30% HP
 *   thermalShroud   — immune to Corrosion
 *   gyroGimbal      — speed cannot be lowered (Servo Lag + spd debuffs blocked)
 *   capacitorBank   — regenerates +6 extra energy each turn
 *   reactivePlating — incoming attack damage reduced 15%
 *   siphonCircuit   — heals 20% of the attack damage it deals
 */

import type { UnitType } from './TypeChart';

export const PASSIVE_IDS = [
  'surgeCore',
  'thermalShroud',
  'gyroGimbal',
  'capacitorBank',
  'reactivePlating',
  'siphonCircuit',
] as const;
export type PassiveId = (typeof PASSIVE_IDS)[number];

export interface PassiveDef {
  id: PassiveId;
  name: string;
  blurb: string;
}

export const PASSIVE_DEFS: Record<PassiveId, PassiveDef> = {
  surgeCore: {
    id: 'surgeCore', name: 'Surge Core',
    blurb: '+30% damage dealt while below 30% HP',
  },
  thermalShroud: {
    id: 'thermalShroud', name: 'Thermal Shroud',
    blurb: 'immune to Corrosion',
  },
  gyroGimbal: {
    id: 'gyroGimbal', name: 'Gyro Gimbal',
    blurb: 'speed cannot be lowered',
  },
  capacitorBank: {
    id: 'capacitorBank', name: 'Capacitor Bank',
    blurb: '+6 extra energy regeneration each turn',
  },
  reactivePlating: {
    id: 'reactivePlating', name: 'Reactive Plating',
    blurb: 'takes 15% less attack damage',
  },
  siphonCircuit: {
    id: 'siphonCircuit', name: 'Siphon Circuit',
    blurb: 'heals 20% of attack damage it deals',
  },
};

export const SURGE_CORE_THRESHOLD = 0.3;
export const SURGE_CORE_MUL = 1.3;
export const CAPACITOR_BANK_BONUS = 6;
export const REACTIVE_PLATING_MUL = 0.85;
export const SIPHON_CIRCUIT_FRACTION = 0.2;

export interface UnitSpec {
  id: string;
  name: string;
  type: UnitType;
  passive: PassiveId;
  maxHp: number;
  atk: number;
  def: number;
  spd: number;
  maxEnergy: number;
  /** exactly 4 move ids from Moves.ts */
  moves: readonly [string, string, string, string];
}

export const UNIT_SPECS: Record<string, UnitSpec> = {
  arclight: {
    id: 'arclight', name: 'VLT-9 Arclight', type: 'volt', passive: 'surgeCore',
    maxHp: 118, atk: 86, def: 70, spd: 96, maxEnergy: 100,
    moves: ['ionLance', 'stormcellBurst', 'staticShackles', 'fluxSiphon'],
  },
  kilnguard: {
    id: 'kilnguard', name: 'PYR-4 Kilnguard', type: 'pyre', passive: 'thermalShroud',
    maxHp: 142, atk: 92, def: 84, spd: 58, maxEnergy: 100,
    moves: ['cinderVolley', 'furnaceSlam', 'shieldbreakerMaul', 'overclockProtocol'],
  },
  solace: {
    id: 'solace', name: 'CRY-7 Solace', type: 'cryo', passive: 'capacitorBank',
    maxHp: 126, atk: 72, def: 78, spd: 74, maxEnergy: 110,
    moves: ['cryoSpike', 'hailwall', 'nanorepairSwarm', 'glacierDriver'],
  },
  whipcord: {
    id: 'whipcord', name: 'AER-2 Whipcord', type: 'aero', passive: 'gyroGimbal',
    maxHp: 110, atk: 84, def: 64, spd: 108, maxEnergy: 100,
    moves: ['razorGale', 'concussionRam', 'tailwindRotor', 'staticShackles'],
  },
  bulwark: {
    id: 'bulwark', name: 'HVY-6 Bulwark', type: 'pyre', passive: 'reactivePlating',
    maxHp: 156, atk: 88, def: 96, spd: 46, maxEnergy: 100,
    moves: ['furnaceSlam', 'cinderVolley', 'hailwall', 'shieldbreakerMaul'],
  },
  rimefang: {
    id: 'rimefang', name: 'CRY-1 Rimefang', type: 'cryo', passive: 'siphonCircuit',
    maxHp: 122, atk: 80, def: 72, spd: 82, maxEnergy: 110,
    moves: ['cryoSpike', 'glacierDriver', 'fluxSiphon', 'nanorepairSwarm'],
  },
};

export const PLAYER_TEAM: readonly string[] = ['arclight', 'kilnguard', 'solace'];
export const ENEMY_TEAM: readonly string[] = ['whipcord', 'bulwark', 'rimefang'];

export function getSpec(id: string): UnitSpec {
  const s = UNIT_SPECS[id];
  if (!s) throw new Error(`Unknown unit spec: ${id}`);
  return s;
}
