/**
 * Ghost replay: a bounded, decimated recording of the player transform
 * stream (x, z, heading at 20 Hz; the sim runs 60 Hz) plus a compact,
 * validated serialization for localStorage. Pure: no Three.js, no DOM.
 * Values are quantized at serialization (cm for position, mrad for
 * heading) so encode -> decode -> encode is byte-identical, which the
 * round-trip test asserts.
 */

/** Record every Nth fixed step: 60 Hz / 3 = 20 Hz. */
export const GHOST_DECIMATE = 3;
/** Sample period, seconds. */
export const GHOST_DT = GHOST_DECIMATE / 60;
/** Hard cap: 10 minutes of recording (bounded memory). */
export const GHOST_MAX_SAMPLES = 12000;

export interface GhostData {
  seed: number;
  /** total run time, ms */
  timeMs: number;
  dt: number;
  n: number;
  x: Float32Array;
  z: Float32Array;
  h: Float32Array;
}

export class GhostRecorder {
  private xs = new Float32Array(GHOST_MAX_SAMPLES);
  private zs = new Float32Array(GHOST_MAX_SAMPLES);
  private hs = new Float32Array(GHOST_MAX_SAMPLES);
  private count = 0;
  private step = 0;

  get samples(): number {
    return this.count;
  }

  get full(): boolean {
    return this.count >= GHOST_MAX_SAMPLES;
  }

  reset(): void {
    this.count = 0;
    this.step = 0;
  }

  /** Call once per fixed sim step; records every GHOST_DECIMATE-th. */
  tick(x: number, z: number, heading: number): void {
    if (this.step % GHOST_DECIMATE === 0 && this.count < GHOST_MAX_SAMPLES) {
      this.xs[this.count] = quant(x, 100);
      this.zs[this.count] = quant(z, 100);
      this.hs[this.count] = quant(heading, 1000);
      this.count++;
    }
    this.step++;
  }

  finalize(seed: number, timeMs: number): GhostData {
    return {
      seed,
      timeMs: Math.round(timeMs),
      dt: GHOST_DT,
      n: this.count,
      x: this.xs.slice(0, this.count),
      z: this.zs.slice(0, this.count),
      h: this.hs.slice(0, this.count),
    };
  }
}

/** Quantize then round-trip through Float32 so storage is stable. */
function quant(v: number, scale: number): number {
  return Math.fround(Math.round(v * scale) / scale);
}

/**
 * Sample the ghost at race time t (seconds), interpolating between the
 * recorded frames (shortest-path lerp for heading). Writes into `out`;
 * returns false once t is past the end of the recording.
 */
export function sampleGhost(
  g: GhostData,
  t: number,
  out: { x: number; z: number; h: number },
): boolean {
  if (g.n === 0) return false;
  const f = t / g.dt;
  const i0 = Math.floor(f);
  if (i0 >= g.n - 1) {
    const last = g.n - 1;
    out.x = g.x[last] as number;
    out.z = g.z[last] as number;
    out.h = g.h[last] as number;
    return false;
  }
  const i1 = i0 + 1;
  const u = f - i0;
  const x0 = g.x[i0] as number;
  const z0 = g.z[i0] as number;
  const h0 = g.h[i0] as number;
  out.x = x0 + ((g.x[i1] as number) - x0) * u;
  out.z = z0 + ((g.z[i1] as number) - z0) * u;
  let dh = (g.h[i1] as number) - h0;
  while (dh > Math.PI) dh -= Math.PI * 2;
  while (dh < -Math.PI) dh += Math.PI * 2;
  out.h = h0 + dh * u;
  return true;
}

const GHOST_VERSION = 1;

/** Compact JSON: integer cm / mrad arrays (deterministic output). */
export function serializeGhost(g: GhostData): string {
  const xi = new Array<number>(g.n);
  const zi = new Array<number>(g.n);
  const hi = new Array<number>(g.n);
  for (let i = 0; i < g.n; i++) {
    xi[i] = Math.round((g.x[i] as number) * 100);
    zi[i] = Math.round((g.z[i] as number) * 100);
    hi[i] = Math.round((g.h[i] as number) * 1000);
  }
  return JSON.stringify({
    v: GHOST_VERSION,
    seed: g.seed,
    timeMs: g.timeMs,
    dt: g.dt,
    n: g.n,
    x: xi,
    z: zi,
    h: hi,
  });
}

/**
 * Parse a stored ghost. Returns null on malformed JSON, wrong version,
 * wrong seed (the track would not match), or inconsistent arrays.
 * Never trusts stored data.
 */
export function deserializeGhost(raw: string | null, expectedSeed: number): GhostData | null {
  if (!raw) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (typeof parsed !== 'object' || parsed === null) return null;
  const o = parsed as Record<string, unknown>;
  if (o['v'] !== GHOST_VERSION) return null;
  if (o['seed'] !== expectedSeed) return null;
  const n = o['n'];
  const timeMs = o['timeMs'];
  const dt = o['dt'];
  if (typeof n !== 'number' || !Number.isInteger(n) || n < 0 || n > GHOST_MAX_SAMPLES) return null;
  if (typeof timeMs !== 'number' || !Number.isFinite(timeMs)) return null;
  if (typeof dt !== 'number' || !(dt > 0)) return null;
  const xi = o['x'];
  const zi = o['z'];
  const hi = o['h'];
  if (!isIntArray(xi, n) || !isIntArray(zi, n) || !isIntArray(hi, n)) return null;
  const x = new Float32Array(n);
  const z = new Float32Array(n);
  const h = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    x[i] = Math.fround((xi[i] as number) / 100);
    z[i] = Math.fround((zi[i] as number) / 100);
    h[i] = Math.fround((hi[i] as number) / 1000);
  }
  return { seed: expectedSeed, timeMs, dt, n, x, z, h };
}

function isIntArray(v: unknown, n: number): v is number[] {
  return (
    Array.isArray(v) &&
    v.length === n &&
    v.every((e) => typeof e === 'number' && Number.isInteger(e))
  );
}
