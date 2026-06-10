/**
 * Anti-faking enforcement: a set of runtime checks that verify the
 * claims the UI makes are backed by actual state. Runs shortly after
 * startup, logs each check to the console, and reports the tally via
 * the event bus (which the ToastLog surfaces).
 */

import type { GameBus } from './EventBus';

export interface AuditCheck {
  name: string;
  /** return true when the claim holds; may throw (counts as failure) */
  fn: () => boolean;
}

export class SelfAudit {
  private checks: AuditCheck[] = [];

  constructor(private bus: GameBus) {}

  add(name: string, fn: () => boolean): void {
    this.checks.push({ name, fn });
  }

  run(): { passed: number; failed: number } {
    let passed = 0;
    let failed = 0;
    for (const c of this.checks) {
      let ok = false;
      let err = '';
      try {
        ok = c.fn();
      } catch (e) {
        err = e instanceof Error ? e.message : String(e);
      }
      if (ok) {
        passed++;
        console.info(`[self-audit] PASS ${c.name}`);
      } else {
        failed++;
        console.warn(`[self-audit] FAIL ${c.name}${err ? ` (${err})` : ''}`);
      }
    }
    this.bus.emit('audit:done', { passed, failed });
    return { passed, failed };
  }
}
