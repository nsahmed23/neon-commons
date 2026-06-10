/**
 * Stacked toast log (top right). Driven by the 'toast' bus event; the
 * interact system, self-audit, stress test, and settings all speak
 * through it. DOM churn happens only on toast events, never per frame.
 */

import type { GameBus } from '../core/EventBus';

const MAX_TOASTS = 6;
const TTL_MS = 4500;

export class ToastLog {
  private container: HTMLDivElement;

  constructor(parent: HTMLElement, bus: GameBus) {
    this.container = document.createElement('div');
    this.container.id = 'toast-log';
    parent.appendChild(this.container);
    bus.on('toast', ({ text, kind }) => this.push(text, kind ?? 'info'));
  }

  push(text: string, kind: 'info' | 'warn' | 'success' = 'info'): void {
    while (this.container.children.length >= MAX_TOASTS) {
      this.container.firstChild?.remove();
    }
    const el = document.createElement('div');
    el.className = `toast toast-${kind}`;
    el.textContent = text;
    this.container.appendChild(el);
    setTimeout(() => {
      el.classList.add('toast-out');
      setTimeout(() => el.remove(), 400);
    }, TTL_MS);
  }
}
