/**
 * Minimal diegetic HUD: crosshair, current mode + day/night readout
 * (bound to real state via the bus), interact prompt, controls hint.
 */

import type { GameBus } from '../core/EventBus';

export class HUD {
  private modeEl: HTMLDivElement;
  private promptEl: HTMLDivElement;

  constructor(parent: HTMLElement, bus: GameBus) {
    const crosshair = document.createElement('div');
    crosshair.id = 'crosshair';
    crosshair.textContent = '+';
    parent.appendChild(crosshair);

    this.modeEl = document.createElement('div');
    this.modeEl.id = 'hud-mode';
    parent.appendChild(this.modeEl);

    this.promptEl = document.createElement('div');
    this.promptEl.id = 'hud-prompt';
    this.promptEl.style.display = 'none';
    parent.appendChild(this.promptEl);

    const hint = document.createElement('div');
    hint.id = 'hud-hint';
    hint.textContent =
      'WASD move · mouse look (click to capture) · Space jump · Shift sprint · E interact · N day/night · M menu · P pause · F1 debug · F2 quality · R reset';
    parent.appendChild(hint);

    let mode = 'hub';
    let night = true;
    let paused = false;
    const refresh = (): void => {
      this.modeEl.textContent = `NEON COMMONS · ${mode.toUpperCase()} · ${night ? 'NIGHT' : 'DAY'}${paused ? ' · PAUSED' : ''}`;
    };
    bus.on('mode:changed', (e) => {
      mode = e.to;
      refresh();
    });
    bus.on('daynight:changed', (e) => {
      night = e.night;
      refresh();
    });
    bus.on('pause:changed', (e) => {
      paused = e.paused;
      refresh();
    });
    refresh();
  }

  setPrompt(text: string | null): void {
    if (text) {
      this.promptEl.textContent = text;
      this.promptEl.style.display = 'block';
    } else {
      this.promptEl.style.display = 'none';
    }
  }
}
