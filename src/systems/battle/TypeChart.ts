/**
 * Battle type chart. Four original robot chassis types arranged in a
 * strict cycle: VOLT > AERO > PYRE > CRYO > VOLT (2x). Attacking your
 * own type, or attacking the type that counters you, deals 0.5x.
 * Everything else is neutral. Pure data + one lookup function; no
 * three.js, no DOM.
 */

export const UNIT_TYPES = ['volt', 'pyre', 'cryo', 'aero'] as const;
export type UnitType = (typeof UNIT_TYPES)[number];

/** The type each entry deals double damage TO (the cycle). */
const BEATS: Record<UnitType, UnitType> = {
  volt: 'aero',
  aero: 'pyre',
  pyre: 'cryo',
  cryo: 'volt',
};

/**
 * Damage multiplier for attackType hitting defendType:
 *   2.0  — attacker beats defender (cycle edge)
 *   0.5  — same type, or attacking the type that beats you
 *   1.0  — otherwise
 */
export function typeMultiplier(attack: UnitType, defend: UnitType): number {
  if (BEATS[attack] === defend) return 2.0;
  if (attack === defend) return 0.5;
  if (BEATS[defend] === attack) return 0.5;
  return 1.0;
}

/** Human label used by HUD/log. */
export const TYPE_LABEL: Record<UnitType, string> = {
  volt: 'VOLT',
  pyre: 'PYRE',
  cryo: 'CRYO',
  aero: 'AERO',
};

/** Hue per type for procedural meshes/badges (matches the neon palette). */
export const TYPE_HUE: Record<UnitType, number> = {
  volt: 0.52, // cyan
  pyre: 0.04, // ember
  cryo: 0.58, // ice blue
  aero: 0.36, // jade
};
