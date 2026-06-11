/**
 * Neon Districts board definition. Original IP: a 28-space ring of
 * neon-city districts in six color sets, four Skyrail transit nodes,
 * two grid utilities, two levy spaces, three Flux Event spaces and
 * four corners. Pure data + lookup helpers; the Engine consumes this,
 * the scene renders it, and the tests validate its invariants.
 */

export type SetId = 'dock' | 'market' | 'arcade' | 'fab' | 'uptown' | 'spire';

export interface DistrictDef {
  kind: 'district';
  name: string;
  set: SetId;
  price: number;
  upgradeCost: number;
  /** Rent by development level 0-3 (Lot, Node, Hub, Spire). */
  rent: readonly [number, number, number, number];
}

export interface TransitDef {
  kind: 'transit';
  name: string;
  price: number;
}

export interface UtilityDef {
  kind: 'utility';
  name: string;
  price: number;
}

export interface TaxDef {
  kind: 'tax';
  name: string;
  amount: number;
}

export interface EventSpaceDef {
  kind: 'event';
  name: string;
}

export interface CornerDef {
  kind: 'corner';
  name: string;
  corner: 'start' | 'rest' | 'free';
}

export type SpaceDef =
  | DistrictDef
  | TransitDef
  | UtilityDef
  | TaxDef
  | EventSpaceDef
  | CornerDef;

export const BOARD_SIZE = 28;
export const START_POS = 0;
export const REST_POS = 7; // Maintenance Bay (surge recall destination)
export const PASS_START_STIPEND = 200;
export const STARTING_MONEY = 1500;
export const SURGE_RECALL_FINE = 50;
export const MAX_LEVEL = 3;
/** Set-completion multiplier on level-0 rent. */
export const SET_RENT_MULT = 2;
/** Transit rent by number of Skyrail nodes the owner holds (1-4). */
export const TRANSIT_RENT: readonly [number, number, number, number] = [25, 50, 100, 200];
/** Utility rent = dice total x this, by utilities owned (1-2). */
export const UTILITY_RENT_MULT: readonly [number, number] = [4, 10];
/** Liquidation refunds: half of what was paid in. */
export const LIQUIDATION_FRACTION = 0.5;
/** Hard game cap (completed rounds); net-worth tiebreak after. */
export const DEFAULT_TURN_CAP = 60;

const d = (
  name: string,
  set: SetId,
  price: number,
  upgradeCost: number,
  rent: [number, number, number, number],
): DistrictDef => ({ kind: 'district', name, set, price, upgradeCost, rent });

/**
 * The ring, clockwise from Plaza Gate. Corners at 0/7/14/21.
 * 14 districts, 4 transit, 2 utilities, 2 levies, 3 events, 3 corners
 * beyond start.
 */
export const BOARD: readonly SpaceDef[] = [
  { kind: 'corner', name: 'Plaza Gate', corner: 'start' }, // 0
  d('Dockside Sprawl', 'dock', 60, 50, [4, 20, 60, 180]), // 1
  { kind: 'event', name: 'Flux Event' }, // 2
  { kind: 'transit', name: 'Skyrail North', price: 200 }, // 3
  d('Cargo Canals', 'dock', 60, 50, [6, 24, 72, 220]), // 4
  { kind: 'tax', name: 'Civic Levy', amount: 100 }, // 5
  d('Lantern Alley', 'market', 100, 60, [8, 32, 90, 270]), // 6
  { kind: 'corner', name: 'Maintenance Bay', corner: 'rest' }, // 7
  d('Vendor Row', 'market', 100, 60, [8, 32, 90, 270]), // 8
  d('Hologram Bazaar', 'market', 120, 60, [10, 40, 110, 330]), // 9
  { kind: 'transit', name: 'Skyrail East', price: 200 }, // 10
  d('Arcade Strip', 'arcade', 140, 80, [12, 48, 130, 390]), // 11
  { kind: 'utility', name: 'Power Grid', price: 150 }, // 12
  d('Synthwave Hall', 'arcade', 160, 80, [14, 56, 150, 450]), // 13
  { kind: 'corner', name: 'Night Market', corner: 'free' }, // 14
  d('Fabrication Belt', 'fab', 180, 100, [16, 64, 170, 510]), // 15
  { kind: 'event', name: 'Flux Event' }, // 16
  { kind: 'transit', name: 'Skyrail South', price: 200 }, // 17
  d('Foundry Blocks', 'fab', 180, 100, [16, 64, 170, 510]), // 18
  d('Assembler Yards', 'fab', 200, 100, [18, 72, 190, 570]), // 19
  { kind: 'utility', name: 'Data Exchange', price: 150 }, // 20
  { kind: 'tax', name: 'Grid Inspection', amount: 75 }, // 21
  d('Uptown Glass', 'uptown', 220, 120, [20, 80, 220, 660]), // 22
  d('Mirror Promenade', 'uptown', 240, 120, [22, 88, 240, 720]), // 23
  { kind: 'transit', name: 'Skyrail West', price: 200 }, // 24
  { kind: 'event', name: 'Flux Event' }, // 25
  d('Spire Heights', 'spire', 280, 150, [26, 104, 290, 870]), // 26
  d('Crown Antenna', 'spire', 300, 150, [30, 120, 330, 990]), // 27
];

export const SET_LABEL: Record<SetId, string> = {
  dock: 'Dockside',
  market: 'Night Market Row',
  arcade: 'Arcade Strip',
  fab: 'Fabrication Belt',
  uptown: 'Uptown Glass',
  spire: 'Spire Heights',
};

/** Hue (0-1) per set, shared by the scene and HUD. */
export const SET_HUE: Record<SetId, number> = {
  dock: 0.52,
  market: 0.85,
  arcade: 0.62,
  fab: 0.08,
  uptown: 0.35,
  spire: 0.95,
};

/** Indices of all districts in a set (derived once from BOARD). */
export function setMembers(set: SetId): number[] {
  const out: number[] = [];
  for (let i = 0; i < BOARD.length; i++) {
    const s = BOARD[i];
    if (s && s.kind === 'district' && s.set === set) out.push(i);
  }
  return out;
}

export function isPurchasable(
  s: SpaceDef,
): s is DistrictDef | TransitDef | UtilityDef {
  return s.kind === 'district' || s.kind === 'transit' || s.kind === 'utility';
}

export function spacePrice(s: SpaceDef): number {
  return isPurchasable(s) ? s.price : 0;
}

export function transitIndices(): number[] {
  const out: number[] = [];
  for (let i = 0; i < BOARD.length; i++) if (BOARD[i]?.kind === 'transit') out.push(i);
  return out;
}

export function utilityIndices(): number[] {
  const out: number[] = [];
  for (let i = 0; i < BOARD.length; i++) if (BOARD[i]?.kind === 'utility') out.push(i);
  return out;
}
