/**
 * Minimal typed event bus. The event map is supplied as a type parameter
 * so emit/on payloads are checked at compile time.
 */

export type Unsubscribe = () => void;

export class EventBus<E extends object> {
  private listeners = new Map<keyof E, Set<(payload: never) => void>>();

  on<K extends keyof E>(event: K, fn: (payload: E[K]) => void): Unsubscribe {
    let set = this.listeners.get(event);
    if (!set) {
      set = new Set();
      this.listeners.set(event, set);
    }
    set.add(fn as (payload: never) => void);
    return () => this.off(event, fn);
  }

  once<K extends keyof E>(event: K, fn: (payload: E[K]) => void): Unsubscribe {
    const wrapped = (payload: E[K]) => {
      this.off(event, wrapped);
      fn(payload);
    };
    return this.on(event, wrapped);
  }

  off<K extends keyof E>(event: K, fn: (payload: E[K]) => void): void {
    this.listeners.get(event)?.delete(fn as (payload: never) => void);
  }

  emit<K extends keyof E>(event: K, payload: E[K]): void {
    const set = this.listeners.get(event);
    if (!set) return;
    // Copy so handlers that unsubscribe (or once-handlers) don't skip peers.
    for (const fn of [...set]) {
      (fn as (payload: E[K]) => void)(payload);
    }
  }

  listenerCount(event: keyof E): number {
    return this.listeners.get(event)?.size ?? 0;
  }

  clear(): void {
    this.listeners.clear();
  }
}

/** Concrete event map for the game. Extend in later stages. */
export interface GameEvents {
  'settings:changed': { key: string };
  'quality:changed': { quality: 'high' | 'medium' | 'low' };
  'mode:changed': { from: string | null; to: string };
  'pause:changed': { paused: boolean };
  'daynight:changed': { night: boolean };
  'toast': { text: string; kind?: 'info' | 'warn' | 'success' };
  'interact': { targetId: string; label: string };
  'stress:result': { before: number; after: number; props: number };
  'audit:done': { passed: number; failed: number };
}

export type GameBus = EventBus<GameEvents>;
