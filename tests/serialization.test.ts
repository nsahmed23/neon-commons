import { describe, expect, test } from 'vitest';
import {
  defaultSettings,
  deserializeSettings,
  serializeSettings,
} from '../src/systems/Serialization';

describe('settings serialization', () => {
  test('round-trip preserves every field', () => {
    const s = {
      mouseSensitivity: 1.7,
      fov: 92,
      masterVolume: 0.25,
      sfxVolume: 0.9,
      musicVolume: 0.1,
      quality: 'medium' as const,
      motionEffects: false,
      debugOverlay: true,
    };
    expect(deserializeSettings(serializeSettings(s))).toEqual(s);
  });

  test('null / empty input returns defaults', () => {
    expect(deserializeSettings(null)).toEqual(defaultSettings());
    expect(deserializeSettings('')).toEqual(defaultSettings());
  });

  test('malformed JSON returns defaults', () => {
    expect(deserializeSettings('{not json')).toEqual(defaultSettings());
    expect(deserializeSettings('42')).toEqual(defaultSettings());
  });

  test('out-of-range numbers are clamped', () => {
    const raw = serializeSettings({
      ...defaultSettings(),
      mouseSensitivity: 99,
      fov: 10,
      masterVolume: -3,
    });
    const s = deserializeSettings(raw);
    expect(s.mouseSensitivity).toBe(3.0);
    expect(s.fov).toBe(50);
    expect(s.masterVolume).toBe(0);
  });

  test('unknown quality value falls back to default', () => {
    const raw = JSON.stringify({
      version: 1,
      settings: { ...defaultSettings(), quality: 'ultra' },
    });
    expect(deserializeSettings(raw).quality).toBe(defaultSettings().quality);
  });

  test('wrong types fall back per-field, valid fields survive', () => {
    const raw = JSON.stringify({
      version: 1,
      settings: { fov: 'huge', motionEffects: 'yes', musicVolume: 0.33 },
    });
    const s = deserializeSettings(raw);
    expect(s.fov).toBe(defaultSettings().fov);
    expect(s.motionEffects).toBe(defaultSettings().motionEffects);
    expect(s.musicVolume).toBe(0.33);
  });

  test('tolerates legacy flat shape (no settings wrapper)', () => {
    const raw = JSON.stringify({ fov: 100, quality: 'low' });
    const s = deserializeSettings(raw);
    expect(s.fov).toBe(100);
    expect(s.quality).toBe('low');
  });
});
