/**
 * Quality scaling. The profile table is pure data (unit-tested); the
 * scaler tracks the current level and notifies listeners, and the App /
 * world layers apply the profile to fog, camera far plane, instanced
 * mesh counts, shadows, and pixel ratio. Every quality switch changes
 * real renderer state, not just a label.
 */

import type { Quality } from '../systems/Serialization';

export interface QualityProfile {
  /** camera far plane + fog far, meters */
  drawDistance: number;
  fogNear: number;
  /** fraction of generated trees actually instanced */
  treeFraction: number;
  /** grass instance count */
  grassCount: number;
  shadows: boolean;
  /** cap on devicePixelRatio */
  pixelRatioCap: number;
}

export const QUALITY_PROFILES: Record<Quality, QualityProfile> = {
  high: {
    drawDistance: 700,
    fogNear: 120,
    treeFraction: 1.0,
    grassCount: 4000,
    shadows: true,
    pixelRatioCap: 2,
  },
  medium: {
    drawDistance: 450,
    fogNear: 80,
    treeFraction: 0.6,
    grassCount: 1800,
    shadows: false,
    pixelRatioCap: 1.5,
  },
  low: {
    drawDistance: 260,
    fogNear: 40,
    treeFraction: 0.3,
    grassCount: 500,
    shadows: false,
    pixelRatioCap: 1,
  },
};

export const QUALITY_ORDER: readonly Quality[] = ['high', 'medium', 'low'];

export class PerformanceScaler {
  private quality: Quality;
  private listeners: Array<(q: Quality, p: QualityProfile) => void> = [];

  constructor(initial: Quality = 'high') {
    this.quality = initial;
  }

  get current(): Quality {
    return this.quality;
  }

  get profile(): QualityProfile {
    return QUALITY_PROFILES[this.quality];
  }

  onChange(fn: (q: Quality, p: QualityProfile) => void): () => void {
    this.listeners.push(fn);
    return () => {
      const i = this.listeners.indexOf(fn);
      if (i >= 0) this.listeners.splice(i, 1);
    };
  }

  set(q: Quality): void {
    if (q === this.quality) return;
    this.quality = q;
    for (const fn of [...this.listeners]) fn(q, QUALITY_PROFILES[q]);
  }

  /** F2 cycles high -> medium -> low -> high. */
  cycle(): Quality {
    const i = QUALITY_ORDER.indexOf(this.quality);
    const next = QUALITY_ORDER[(i + 1) % QUALITY_ORDER.length] as Quality;
    this.set(next);
    return next;
  }
}
