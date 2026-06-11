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

  /**
   * Generic raw-string persistence for other systems (race ghosts,
   * later board saves). Callers own validation of what comes back;
   * storage failures degrade to null/false, never throw.
   */
  loadRaw(key: string): string | null {
    try {
      return localStorage.getItem(key);
    } catch {
      return null;
    }
  }

  saveRaw(key: string, raw: string): boolean {
    try {
      localStorage.setItem(key, raw);
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
