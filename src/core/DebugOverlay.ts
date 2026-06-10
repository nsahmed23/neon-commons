/**
 * F1 overlay reporting REAL runtime numbers. Nothing here is invented:
 * FPS / frame time come from a wall-clock ring buffer, draw calls and
 * triangles come from renderer.info after the previous render, entity
 * count comes from the systems' own instance counters, camera position
 * from the live camera, seed from GameState.
 */

export interface DebugStats {
  fps: number;
  frameMs: number;
  drawCalls: number;
  triangles: number;
  entities: number;
  mode: string;
  quality: string;
  camX: number;
  camY: number;
  camZ: number;
  seed: number;
  windows: number;
  stress: string;
}

export class DebugOverlay {
  private el: HTMLDivElement;
  private visible = false;
  private lastText = '';

  constructor(parent: HTMLElement) {
    this.el = document.createElement('div');
    this.el.id = 'debug-overlay';
    this.el.style.display = 'none';
    parent.appendChild(this.el);
  }

  setVisible(v: boolean): void {
    this.visible = v;
    this.el.style.display = v ? 'block' : 'none';
  }

  get isVisible(): boolean {
    return this.visible;
  }

  toggle(): boolean {
    this.setVisible(!this.visible);
    return this.visible;
  }

  /** Called at ~5 Hz from the app, not every frame. */
  update(s: DebugStats): void {
    if (!this.visible) return;
    const text =
      `FPS ${s.fps.toFixed(0)}  frame ${s.frameMs.toFixed(2)} ms\n` +
      `draw calls ${s.drawCalls}  tris ${formatK(s.triangles)}\n` +
      `entities ${s.entities}  windows ${s.windows}\n` +
      `mode ${s.mode}  quality ${s.quality}\n` +
      `cam ${s.camX.toFixed(1)}, ${s.camY.toFixed(1)}, ${s.camZ.toFixed(1)}\n` +
      `seed ${s.seed}\n` +
      `stress ${s.stress}`;
    if (text !== this.lastText) {
      this.el.textContent = text;
      this.lastText = text;
    }
  }
}

function formatK(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : `${n}`;
}
