/**
 * Settings schema + safe serialization. Pure (no DOM/localStorage here),
 * so it is unit-testable; SaveSystem handles the storage side.
 * Every field is validated and clamped on load: never trust stored data.
 */

export type Quality = 'high' | 'medium' | 'low';

export interface SettingsData {
  mouseSensitivity: number; // 0.1 .. 3.0
  fov: number; // 50 .. 110 degrees
  masterVolume: number; // 0 .. 1
  sfxVolume: number; // 0 .. 1
  musicVolume: number; // 0 .. 1
  quality: Quality;
  motionEffects: boolean; // head bob + water motion amplitude
  debugOverlay: boolean;
}

export const SETTINGS_VERSION = 1;

export function defaultSettings(): SettingsData {
  return {
    mouseSensitivity: 1.0,
    fov: 75,
    masterVolume: 0.8,
    sfxVolume: 0.8,
    musicVolume: 0.5,
    quality: 'high',
    motionEffects: true,
    debugOverlay: false,
  };
}

const clamp = (v: number, min: number, max: number): number =>
  Math.min(max, Math.max(min, v));

function asNumber(v: unknown, fallback: number): number {
  return typeof v === 'number' && Number.isFinite(v) ? v : fallback;
}

function asBoolean(v: unknown, fallback: boolean): boolean {
  return typeof v === 'boolean' ? v : fallback;
}

function asQuality(v: unknown, fallback: Quality): Quality {
  return v === 'high' || v === 'medium' || v === 'low' ? v : fallback;
}

export function serializeSettings(s: SettingsData): string {
  return JSON.stringify({ version: SETTINGS_VERSION, settings: s });
}

/**
 * Parse a stored settings string. Malformed JSON, wrong shapes, or
 * out-of-range values all fall back to defaults (per-field, clamped).
 */
export function deserializeSettings(raw: string | null): SettingsData {
  const d = defaultSettings();
  if (!raw) return d;
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return d;
  }
  if (typeof parsed !== 'object' || parsed === null) return d;
  const obj = parsed as Record<string, unknown>;
  const s =
    typeof obj['settings'] === 'object' && obj['settings'] !== null
      ? (obj['settings'] as Record<string, unknown>)
      : obj; // tolerate flat legacy shape
  return {
    mouseSensitivity: clamp(asNumber(s['mouseSensitivity'], d.mouseSensitivity), 0.1, 3.0),
    fov: clamp(asNumber(s['fov'], d.fov), 50, 110),
    masterVolume: clamp(asNumber(s['masterVolume'], d.masterVolume), 0, 1),
    sfxVolume: clamp(asNumber(s['sfxVolume'], d.sfxVolume), 0, 1),
    musicVolume: clamp(asNumber(s['musicVolume'], d.musicVolume), 0, 1),
    quality: asQuality(s['quality'], d.quality),
    motionEffects: asBoolean(s['motionEffects'], d.motionEffects),
    debugOverlay: asBoolean(s['debugOverlay'], d.debugOverlay),
  };
}
