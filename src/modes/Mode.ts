/**
 * Mode seam for later stages. Each mode (Hub today; Race/Battle/Board/
 * Flight/Shader in future stages) implements this interface and gets
 * registered with the ModeManager. Switching modes is a real state
 * transition (exit -> enter -> 'mode:changed' event); future modes
 * plug in by calling manager.register() and manager.switchTo(id) from
 * the pedestal interact event.
 */

import type { GameBus } from '../core/EventBus';

export interface Mode {
  readonly id: string;
  /** called when the mode becomes active */
  enter(): void;
  /** called when another mode takes over */
  exit(): void;
  /** fixed-timestep simulation update */
  update(dt: number): void;
}

export class ModeManager {
  private modes = new Map<string, Mode>();
  private active: Mode | null = null;

  constructor(private bus: GameBus) {}

  register(mode: Mode): void {
    if (this.modes.has(mode.id)) {
      throw new Error(`Mode already registered: ${mode.id}`);
    }
    this.modes.set(mode.id, mode);
  }

  has(id: string): boolean {
    return this.modes.has(id);
  }

  get currentId(): string {
    return this.active?.id ?? 'none';
  }

  switchTo(id: string): void {
    const next = this.modes.get(id);
    if (!next) throw new Error(`Unknown mode: ${id}`);
    if (next === this.active) return;
    const from = this.active?.id ?? null;
    this.active?.exit();
    this.active = next;
    next.enter();
    this.bus.emit('mode:changed', { from, to: id });
  }

  update(dt: number): void {
    this.active?.update(dt);
  }
}
