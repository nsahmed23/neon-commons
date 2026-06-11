/**
 * Keyboard + pointer-lock mouse input. Continuous actions (move) are
 * polled with isDown(); edge actions (menu, pause, debug...) fire
 * registered callbacks on keydown. Mouse deltas accumulate and are
 * consumed once per simulation step into a caller-owned object
 * (no per-frame allocation).
 */

export type ContinuousAction =
  | 'forward' | 'back' | 'left' | 'right' | 'sprint' | 'jump' | 'fire';

export type EdgeAction =
  | 'menu' | 'pause' | 'debug' | 'quality' | 'reset' | 'interact' | 'daynight'
  | 'modeDebug' | 'escape';

const CONTINUOUS_BINDINGS: Record<string, ContinuousAction> = {
  KeyW: 'forward',
  KeyS: 'back',
  KeyA: 'left',
  KeyD: 'right',
  ShiftLeft: 'sprint',
  ShiftRight: 'sprint',
  Space: 'jump',
  KeyF: 'fire',
};

const EDGE_BINDINGS: Record<string, EdgeAction> = {
  KeyM: 'menu',
  KeyP: 'pause',
  F1: 'debug',
  F2: 'quality',
  KeyR: 'reset',
  KeyE: 'interact',
  KeyN: 'daynight',
  KeyB: 'modeDebug',
  Escape: 'escape',
};

export class Input {
  mouseSensitivity = 1.0;

  private down = new Set<ContinuousAction>();
  private edgeHandlers = new Map<EdgeAction, Array<() => void>>();
  private dx = 0;
  private dy = 0;
  private element: HTMLElement | null = null;
  private lockWanted = false;

  attach(element: HTMLElement): void {
    this.element = element;
    window.addEventListener('keydown', this.onKeyDown);
    window.addEventListener('keyup', this.onKeyUp);
    window.addEventListener('mousemove', this.onMouseMove);
    window.addEventListener('blur', this.onBlur);
    element.addEventListener('click', () => {
      if (this.lockWanted) this.requestLock();
    });
  }

  /** Whether gameplay wants the pointer captured (false while in menus). */
  setLockWanted(wanted: boolean): void {
    this.lockWanted = wanted;
    if (!wanted) this.releaseLock();
  }

  requestLock(): void {
    if (this.element && document.pointerLockElement !== this.element) {
      this.element.requestPointerLock();
    }
  }

  releaseLock(): void {
    if (document.pointerLockElement) document.exitPointerLock();
  }

  get pointerLocked(): boolean {
    return this.element !== null && document.pointerLockElement === this.element;
  }

  isDown(action: ContinuousAction): boolean {
    return this.down.has(action);
  }

  onEdge(action: EdgeAction, fn: () => void): void {
    let arr = this.edgeHandlers.get(action);
    if (!arr) {
      arr = [];
      this.edgeHandlers.set(action, arr);
    }
    arr.push(fn);
  }

  /** Move accumulated mouse delta into `out` and zero the accumulator. */
  consumeMouseDelta(out: { x: number; y: number }): void {
    out.x = this.dx * this.mouseSensitivity;
    out.y = this.dy * this.mouseSensitivity;
    this.dx = 0;
    this.dy = 0;
  }

  private onKeyDown = (e: KeyboardEvent): void => {
    const cont = CONTINUOUS_BINDINGS[e.code];
    if (cont) {
      this.down.add(cont);
      e.preventDefault();
      return;
    }
    const edge = EDGE_BINDINGS[e.code];
    if (edge) {
      e.preventDefault();
      if (e.repeat) return;
      const arr = this.edgeHandlers.get(edge);
      if (arr) for (const fn of arr) fn();
    }
  };

  private onKeyUp = (e: KeyboardEvent): void => {
    const cont = CONTINUOUS_BINDINGS[e.code];
    if (cont) this.down.delete(cont);
  };

  private onMouseMove = (e: MouseEvent): void => {
    if (!this.pointerLocked) return;
    this.dx += e.movementX;
    this.dy += e.movementY;
  };

  private onBlur = (): void => {
    this.down.clear();
  };
}
