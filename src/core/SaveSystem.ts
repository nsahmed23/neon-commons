/**
 * Settings persistence to localStorage. Parsing/validation lives in
 * systems/Serialization (pure + tested); this wraps the storage calls
 * and survives environments where localStorage throws.
 */

import {
  SettingsData,
  defaultSettings,
  deserializeSettings,
  serializeSettings,
} from '../systems/Serialization';

const STORAGE_KEY = 'neon-commons:settings:v1';

export class SaveSystem {
  load(): SettingsData {
    try {
      return deserializeSettings(localStorage.getItem(STORAGE_KEY));
    } catch {
      return defaultSettings();
    }
  }

  save(settings: SettingsData): boolean {
    try {
      localStorage.setItem(STORAGE_KEY, serializeSettings(settings));
      return true;
    } catch {
      return false;
    }
  }

  /** Wipe the save and return fresh defaults. */
  reset(): SettingsData {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      /* storage unavailable: defaults are the reset */
    }
    return defaultSettings();
  }
}
