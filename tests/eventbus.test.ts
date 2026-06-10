import { describe, expect, test } from 'vitest';
import { EventBus } from '../src/core/EventBus';

interface TestEvents {
  ping: { n: number };
  note: string;
  [key: string]: unknown;
}

describe('EventBus', () => {
  test('on/emit delivers typed payload', () => {
    const bus = new EventBus<TestEvents>();
    let got = -1;
    bus.on('ping', (p) => {
      got = p.n;
    });
    bus.emit('ping', { n: 42 });
    expect(got).toBe(42);
  });

  test('multiple listeners all fire', () => {
    const bus = new EventBus<TestEvents>();
    const calls: number[] = [];
    bus.on('ping', () => calls.push(1));
    bus.on('ping', () => calls.push(2));
    bus.emit('ping', { n: 0 });
    expect(calls).toEqual([1, 2]);
  });

  test('off removes a listener', () => {
    const bus = new EventBus<TestEvents>();
    let count = 0;
    const fn = () => count++;
    bus.on('ping', fn);
    bus.emit('ping', { n: 0 });
    bus.off('ping', fn);
    bus.emit('ping', { n: 0 });
    expect(count).toBe(1);
  });

  test('unsubscribe function returned by on works', () => {
    const bus = new EventBus<TestEvents>();
    let count = 0;
    const unsub = bus.on('note', () => count++);
    bus.emit('note', 'a');
    unsub();
    bus.emit('note', 'b');
    expect(count).toBe(1);
  });

  test('once fires exactly once', () => {
    const bus = new EventBus<TestEvents>();
    let count = 0;
    bus.once('ping', () => count++);
    bus.emit('ping', { n: 1 });
    bus.emit('ping', { n: 2 });
    expect(count).toBe(1);
  });

  test('once unsubscribing does not skip sibling listeners', () => {
    const bus = new EventBus<TestEvents>();
    const calls: string[] = [];
    bus.once('ping', () => calls.push('once'));
    bus.on('ping', () => calls.push('always'));
    bus.emit('ping', { n: 0 });
    expect(calls).toEqual(['once', 'always']);
  });

  test('emit with no listeners is a no-op', () => {
    const bus = new EventBus<TestEvents>();
    expect(() => bus.emit('ping', { n: 0 })).not.toThrow();
  });

  test('listenerCount and clear', () => {
    const bus = new EventBus<TestEvents>();
    bus.on('ping', () => {});
    bus.on('ping', () => {});
    expect(bus.listenerCount('ping')).toBe(2);
    bus.clear();
    expect(bus.listenerCount('ping')).toBe(0);
  });
});
