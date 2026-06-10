/**
 * Fixed-timestep clock. Simulation advances in fixed 1/60s steps;
 * rendering happens every RAF. Pausing freezes simulation time
 * (`elapsed`), which also drives shader animation, so pause is real.
 */

export class Time {
  readonly fixedDelta = 1 / 60;
  /** max simulation steps per frame (spiral-of-death guard) */
  readonly maxSteps = 5;

  paused = false;
  /** simulation seconds (stops while paused) */
  elapsed = 0;
  /** wall-clock seconds of the last frame (for FPS measurement) */
  frameDelta = 0;

  private accumulator = 0;
  private lastMs = -1;

  /**
   * Advance from a RAF timestamp. Returns how many fixed steps the
   * caller should simulate this frame (0 while paused).
   */
  tick(nowMs: number): number {
    if (this.lastMs < 0) {
      this.lastMs = nowMs;
      return 0;
    }
    this.frameDelta = Math.min(0.25, (nowMs - this.lastMs) / 1000);
    this.lastMs = nowMs;
    if (this.paused) {
      this.accumulator = 0;
      return 0;
    }
    this.accumulator += this.frameDelta;
    let steps = 0;
    while (this.accumulator >= this.fixedDelta && steps < this.maxSteps) {
      this.accumulator -= this.fixedDelta;
      this.elapsed += this.fixedDelta;
      steps++;
    }
    if (steps === this.maxSteps) this.accumulator = 0; // drop backlog
    return steps;
  }

  setPaused(paused: boolean): void {
    this.paused = paused;
  }
}
