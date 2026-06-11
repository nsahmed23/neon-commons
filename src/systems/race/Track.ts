/**
 * Pure, seeded race-track generation + geometric queries. No Three.js:
 * a seed becomes a closed centerline ribbon (radial harmonics around
 * the origin, so the loop can never self-intersect), with per-sample
 * tangents, arc-length progress, boost-pad spans, ordered checkpoint
 * gates, and a real surface query (track / boost / off-road) used by
 * vehicle physics. Query results write into caller-owned scratch
 * objects: zero allocations on the hot path. Unit-tested.
 */

import { Rng } from '../../core/Rng';

export const TRACK = {
  /** centerline sample count (closed loop) */
  samples: 256,
  /** asphalt half-width, meters */
  halfWidth: 9,
  /** off-road shoulder width beyond the asphalt, meters */
  offroadWidth: 13,
  /** ordered checkpoint gate count (gate 0 = start/finish) */
  checkpoints: 8,
  /** boost pad count */
  boostPads: 5,
  /** boost pads span the middle of the road only */
  boostHalfWidth: 6,
  /** pad length in centerline samples */
  boostSpan: 3,
} as const;

/** Hard barrier distance from the centerline (off-road ends in a wall). */
export const WALL_DIST = TRACK.halfWidth + TRACK.offroadWidth;

export const SURFACE_TRACK = 0;
export const SURFACE_BOOST = 1;
export const SURFACE_OFFROAD = 2;
export type Surface =
  | typeof SURFACE_TRACK
  | typeof SURFACE_BOOST
  | typeof SURFACE_OFFROAD;

export interface CheckpointGate {
  /** ordinal in lap order; gate 0 is the start/finish line */
  order: number;
  /** centerline sample index this gate sits on */
  sample: number;
  x: number;
  z: number;
  /** trigger radius (covers asphalt + shoulder, never past the wall) */
  r: number;
}

export interface BoostPad {
  /** inclusive centerline sample span */
  startSample: number;
  endSample: number;
  x: number;
  z: number;
}

export interface TrackData {
  seed: number;
  n: number;
  /** centerline positions */
  xs: Float32Array;
  zs: Float32Array;
  /** unit tangents (direction of travel) */
  tx: Float32Array;
  tz: Float32Array;
  /** cumulative arc length at sample i (cum[0] = 0) */
  cum: Float32Array;
  /** total lap length, meters */
  total: number;
  halfWidth: number;
  wallDist: number;
  /** 1 where the sample carries a boost pad */
  boostMask: Uint8Array;
  pads: BoostPad[];
  gates: CheckpointGate[];
}

/** Result buffer for queryTrack; create once per vehicle, reuse forever. */
export interface TrackQueryResult {
  /** nearest centerline sample index (pass back as the next hint) */
  seg: number;
  /** signed lateral offset from the centerline, meters (left positive) */
  lateral: number;
  /** lap progress 0..1 along the centerline */
  progress: number;
  /** track direction at the query point */
  tangentX: number;
  tangentZ: number;
  surface: Surface;
}

export function createQueryResult(): TrackQueryResult {
  return { seg: 0, lateral: 0, progress: 0, tangentX: 0, tangentZ: 1, surface: SURFACE_TRACK };
}

/**
 * Generate the track for a seed. Radial form r(theta) = R0 + sum of
 * sine harmonics keeps the loop simple (star-shaped about the origin),
 * so boundaries never cross themselves and the lateral query is
 * well defined everywhere near the ribbon.
 */
export function generateTrack(seed: number): TrackData {
  const rng = new Rng(seed).fork('race-track');
  const n = TRACK.samples;

  const R0 = 105;
  const a2 = rng.range(10, 20);
  const p2 = rng.range(0, Math.PI * 2);
  const a3 = rng.range(5, 12);
  const p3 = rng.range(0, Math.PI * 2);
  const a5 = rng.range(2, 6);
  const p5 = rng.range(0, Math.PI * 2);

  const xs = new Float32Array(n);
  const zs = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const th = (i / n) * Math.PI * 2;
    const r =
      R0 +
      a2 * Math.sin(2 * th + p2) +
      a3 * Math.sin(3 * th + p3) +
      a5 * Math.sin(5 * th + p5);
    xs[i] = Math.cos(th) * r;
    zs[i] = Math.sin(th) * r;
  }

  // Unit tangents from central differences (closed loop).
  const tx = new Float32Array(n);
  const tz = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const prev = (i - 1 + n) % n;
    const next = (i + 1) % n;
    let dx = (xs[next] as number) - (xs[prev] as number);
    let dz = (zs[next] as number) - (zs[prev] as number);
    const len = Math.hypot(dx, dz) || 1;
    dx /= len;
    dz /= len;
    tx[i] = dx;
    tz[i] = dz;
  }

  // Cumulative arc length.
  const cum = new Float32Array(n);
  let total = 0;
  for (let i = 1; i < n; i++) {
    total += Math.hypot(
      (xs[i] as number) - (xs[i - 1] as number),
      (zs[i] as number) - (zs[i - 1] as number),
    );
    cum[i] = total;
  }
  total += Math.hypot(
    (xs[0] as number) - (xs[n - 1] as number),
    (zs[0] as number) - (zs[n - 1] as number),
  );

  // Ordered checkpoint gates, evenly spaced; gate 0 = start/finish.
  const gates: CheckpointGate[] = [];
  const gateRadius = WALL_DIST; // cannot be skipped without hitting the wall
  for (let g = 0; g < TRACK.checkpoints; g++) {
    const sample = Math.floor((g * n) / TRACK.checkpoints);
    gates.push({
      order: g,
      sample,
      x: xs[sample] as number,
      z: zs[sample] as number,
      r: gateRadius,
    });
  }

  // Boost pads: seeded sample spans, kept clear of gates and each other.
  const boostMask = new Uint8Array(n);
  const pads: BoostPad[] = [];
  const minGapToGate = 8;
  const minGapToPad = 20;
  let attempts = 0;
  while (pads.length < TRACK.boostPads && attempts < 200) {
    attempts++;
    const start = rng.int(0, n - 1);
    let ok = true;
    for (const g of gates) {
      const d = ringDist(start, g.sample, n);
      if (d < minGapToGate) ok = false;
    }
    for (const p of pads) {
      if (ringDist(start, p.startSample, n) < minGapToPad) ok = false;
    }
    if (!ok) continue;
    const end = (start + TRACK.boostSpan - 1) % n;
    for (let k = 0; k < TRACK.boostSpan; k++) boostMask[(start + k) % n] = 1;
    const mid = (start + 1) % n;
    pads.push({ startSample: start, endSample: end, x: xs[mid] as number, z: zs[mid] as number });
  }

  return {
    seed,
    n,
    xs,
    zs,
    tx,
    tz,
    cum,
    total,
    halfWidth: TRACK.halfWidth,
    wallDist: WALL_DIST,
    boostMask,
    pads,
    gates,
  };
}

/** Shortest distance between two indices on a ring of n samples. */
export function ringDist(a: number, b: number, n: number): number {
  const d = Math.abs(a - b) % n;
  return Math.min(d, n - d);
}

const HINT_WINDOW = 20;

/**
 * Real surface query. Finds the nearest centerline sample (local search
 * around `hint`, full scan when hint < 0), projects onto the adjacent
 * segments for an exact lateral offset, and classifies the surface.
 * Writes into `out`; allocates nothing.
 */
export function queryTrack(
  t: TrackData,
  x: number,
  z: number,
  hint: number,
  out: TrackQueryResult,
): void {
  const n = t.n;
  let best = 0;
  let bestD2 = Infinity;
  if (hint >= 0) {
    for (let off = -HINT_WINDOW; off <= HINT_WINDOW; off++) {
      const i = (hint + off + n) % n;
      const dx = x - (t.xs[i] as number);
      const dz = z - (t.zs[i] as number);
      const d2 = dx * dx + dz * dz;
      if (d2 < bestD2) {
        bestD2 = d2;
        best = i;
      }
    }
  } else {
    for (let i = 0; i < n; i++) {
      const dx = x - (t.xs[i] as number);
      const dz = z - (t.zs[i] as number);
      const d2 = dx * dx + dz * dz;
      if (d2 < bestD2) {
        bestD2 = d2;
        best = i;
      }
    }
  }

  // Project onto the segment before and after the nearest sample; keep
  // the closer projection for exact lateral distance + progress.
  let segStart = best;
  let segT = 0;
  let segD2 = Infinity;
  for (let pick = 0; pick < 2; pick++) {
    const i0 = pick === 0 ? (best - 1 + n) % n : best;
    const i1 = (i0 + 1) % n;
    const ax = t.xs[i0] as number;
    const az = t.zs[i0] as number;
    const bx = t.xs[i1] as number;
    const bz = t.zs[i1] as number;
    const ex = bx - ax;
    const ez = bz - az;
    const len2 = ex * ex + ez * ez || 1;
    let u = ((x - ax) * ex + (z - az) * ez) / len2;
    u = u < 0 ? 0 : u > 1 ? 1 : u;
    const px = ax + ex * u;
    const pz = az + ez * u;
    const dx = x - px;
    const dz = z - pz;
    const d2 = dx * dx + dz * dz;
    if (d2 < segD2) {
      segD2 = d2;
      segStart = i0;
      segT = u;
    }
  }

  const i0 = segStart;
  const i1 = (i0 + 1) % n;
  const ax = t.xs[i0] as number;
  const az = t.zs[i0] as number;
  const bx = t.xs[i1] as number;
  const bz = t.zs[i1] as number;
  let ex = bx - ax;
  let ez = bz - az;
  const segLen = Math.hypot(ex, ez) || 1;
  ex /= segLen;
  ez /= segLen;
  // Left normal of the direction of travel.
  const nx = -ez;
  const nz = ex;
  const px = ax + ex * segLen * segT;
  const pz = az + ez * segLen * segT;
  const lateral = (x - px) * nx + (z - pz) * nz;

  const along = (t.cum[i0] as number) + segLen * segT;
  out.seg = best;
  out.lateral = lateral;
  out.progress = (along % t.total) / t.total;
  out.tangentX = ex;
  out.tangentZ = ez;

  const absLat = Math.abs(lateral);
  if (absLat <= t.halfWidth) {
    out.surface =
      t.boostMask[best] === 1 && absLat <= TRACK.boostHalfWidth
        ? SURFACE_BOOST
        : SURFACE_TRACK;
  } else {
    out.surface = SURFACE_OFFROAD;
  }
}
