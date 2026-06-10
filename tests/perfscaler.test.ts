import { describe, expect, test } from 'vitest';
import {
  PerformanceScaler,
  QUALITY_ORDER,
  QUALITY_PROFILES,
} from '../src/rendering/PerformanceScaler';

describe('quality profiles', () => {
  test('profiles are monotonically cheaper from high to low', () => {
    const { high, medium, low } = QUALITY_PROFILES;
    expect(high.drawDistance).toBeGreaterThan(medium.drawDistance);
    expect(medium.drawDistance).toBeGreaterThan(low.drawDistance);
    expect(high.treeFraction).toBeGreaterThan(medium.treeFraction);
    expect(medium.treeFraction).toBeGreaterThan(low.treeFraction);
    expect(high.grassCount).toBeGreaterThan(medium.grassCount);
    expect(medium.grassCount).toBeGreaterThan(low.grassCount);
    expect(high.pixelRatioCap).toBeGreaterThan(low.pixelRatioCap);
    expect(high.shadows).toBe(true);
    expect(low.shadows).toBe(false);
  });
});

describe('PerformanceScaler', () => {
  test('starts at requested level and exposes its profile', () => {
    const s = new PerformanceScaler('medium');
    expect(s.current).toBe('medium');
    expect(s.profile).toBe(QUALITY_PROFILES.medium);
  });

  test('set() notifies listeners with quality and profile', () => {
    const s = new PerformanceScaler('high');
    const events: string[] = [];
    s.onChange((q, p) => events.push(`${q}:${p.drawDistance}`));
    s.set('low');
    expect(s.current).toBe('low');
    expect(events).toEqual([`low:${QUALITY_PROFILES.low.drawDistance}`]);
  });

  test('set() to the same level is a no-op (no duplicate notification)', () => {
    const s = new PerformanceScaler('high');
    let calls = 0;
    s.onChange(() => calls++);
    s.set('high');
    expect(calls).toBe(0);
  });

  test('cycle() walks high -> medium -> low -> high', () => {
    const s = new PerformanceScaler('high');
    expect(s.cycle()).toBe('medium');
    expect(s.cycle()).toBe('low');
    expect(s.cycle()).toBe('high');
    expect(QUALITY_ORDER).toEqual(['high', 'medium', 'low']);
  });

  test('onChange unsubscribe stops notifications', () => {
    const s = new PerformanceScaler('high');
    let calls = 0;
    const unsub = s.onChange(() => calls++);
    s.set('medium');
    unsub();
    s.set('low');
    expect(calls).toBe(1);
  });
});
