/**
 * Pooled projectiles with REAL swept collision. Pure (no Three.js, no
 * DOM): a fixed-size structure-of-arrays pool, integrated per fixed
 * step, tested as swept segments against target spheres so a fast bolt
 * cannot tunnel through a drone between steps. Zero allocations after
 * construction: spawn/step/collide touch only preallocated arrays.
 */

export const PROJECTILE = {
  /** hard pool bound (player + all enemies share it) */
  max: 96,
  /** bolt life, seconds */
  ttl: 2.2,
  playerSpeed: 95,
  enemySpeed: 55,
  playerDamage: 10,
  enemyDamage: 8,
} as const;

export type ProjectileOwner = 0 | 1; // 0 = player, 1 = enemy

export interface ProjectilePool {
  /** slots in use (alive[i] === 1) */
  alive: Uint8Array;
  x: Float32Array;
  y: Float32Array;
  z: Float32Array;
  vx: Float32Array;
  vy: Float32Array;
  vz: Float32Array;
  age: Float32Array;
  owner: Uint8Array;
  damage: Float32Array;
  /** live count (maintained by spawn/kill) */
  count: number;
  /** ring cursor for slot search */
  cursor: number;
}

export function createPool(): ProjectilePool {
  const n = PROJECTILE.max;
  return {
    alive: new Uint8Array(n),
    x: new Float32Array(n),
    y: new Float32Array(n),
    z: new Float32Array(n),
    vx: new Float32Array(n),
    vy: new Float32Array(n),
    vz: new Float32Array(n),
    age: new Float32Array(n),
    owner: new Uint8Array(n),
    damage: new Float32Array(n),
    count: 0,
    cursor: 0,
  };
}

/**
 * Spawn a bolt. Returns the slot index, or -1 when the pool is FULL
 * (bounded by construction: a full pool refuses, it never grows).
 */
export function spawnProjectile(
  p: ProjectilePool,
  owner: ProjectileOwner,
  x: number,
  y: number,
  z: number,
  vx: number,
  vy: number,
  vz: number,
  damage: number,
): number {
  if (p.count >= PROJECTILE.max) return -1;
  // Ring search from the cursor for a free slot.
  for (let k = 0; k < PROJECTILE.max; k++) {
    const i = (p.cursor + k) % PROJECTILE.max;
    if (p.alive[i] === 0) {
      p.alive[i] = 1;
      p.x[i] = x;
      p.y[i] = y;
      p.z[i] = z;
      p.vx[i] = vx;
      p.vy[i] = vy;
      p.vz[i] = vz;
      p.age[i] = 0;
      p.owner[i] = owner;
      p.damage[i] = damage;
      p.count++;
      p.cursor = (i + 1) % PROJECTILE.max;
      return i;
    }
  }
  return -1;
}

export function killProjectile(p: ProjectilePool, i: number): void {
  if (p.alive[i] === 1) {
    p.alive[i] = 0;
    p.count--;
  }
}

/** Integrate all live bolts and expire the old ones. */
export function stepProjectiles(p: ProjectilePool, dt: number): void {
  for (let i = 0; i < PROJECTILE.max; i++) {
    if (p.alive[i] === 0) continue;
    p.x[i] = (p.x[i] as number) + (p.vx[i] as number) * dt;
    p.y[i] = (p.y[i] as number) + (p.vy[i] as number) * dt;
    p.z[i] = (p.z[i] as number) + (p.vz[i] as number) * dt;
    p.age[i] = (p.age[i] as number) + dt;
    if ((p.age[i] as number) >= PROJECTILE.ttl) killProjectile(p, i);
  }
}

/**
 * Swept segment-vs-sphere test: does the segment from (x0,y0,z0) to
 * (x1,y1,z1) come within `r` of the sphere center? Closed-form closest
 * point on the segment; exact, not sampled.
 */
export function segmentHitsSphere(
  x0: number, y0: number, z0: number,
  x1: number, y1: number, z1: number,
  cx: number, cy: number, cz: number,
  r: number,
): boolean {
  const dx = x1 - x0;
  const dy = y1 - y0;
  const dz = z1 - z0;
  const fx = x0 - cx;
  const fy = y0 - cy;
  const fz = z0 - cz;
  const len2 = dx * dx + dy * dy + dz * dz;
  let t = 0;
  if (len2 > 1e-12) {
    t = -(fx * dx + fy * dy + fz * dz) / len2;
    if (t < 0) t = 0;
    else if (t > 1) t = 1;
  }
  const px = fx + dx * t;
  const py = fy + dy * t;
  const pz = fz + dz * t;
  return px * px + py * py + pz * pz <= r * r;
}

/** What a projectile can hit: a sphere with an id the caller maps back. */
export interface HitTarget {
  id: number;
  x: number;
  y: number;
  z: number;
  radius: number;
  /** 0 = player team, 1 = enemy team; bolts skip their own team */
  team: ProjectileOwner;
}

/**
 * Collide every live bolt's LAST step segment (pos - vel*dt -> pos)
 * against the target spheres. On hit: the bolt dies and `onHit` fires
 * with (targetId, damage, bolt owner). Friendly fire is off: a bolt
 * never hits its own team. The callback is caller-owned and reused, so
 * this allocates nothing per tick.
 */
export function collideProjectiles(
  p: ProjectilePool,
  targets: readonly HitTarget[],
  dt: number,
  onHit: (targetId: number, damage: number, owner: ProjectileOwner) => void,
): void {
  for (let i = 0; i < PROJECTILE.max; i++) {
    if (p.alive[i] === 0) continue;
    const x1 = p.x[i] as number;
    const y1 = p.y[i] as number;
    const z1 = p.z[i] as number;
    const x0 = x1 - (p.vx[i] as number) * dt;
    const y0 = y1 - (p.vy[i] as number) * dt;
    const z0 = z1 - (p.vz[i] as number) * dt;
    const owner = p.owner[i] as ProjectileOwner;
    for (let j = 0; j < targets.length; j++) {
      const t = targets[j] as HitTarget;
      if (t.team === owner) continue;
      if (segmentHitsSphere(x0, y0, z0, x1, y1, z1, t.x, t.y, t.z, t.radius)) {
        killProjectile(p, i);
        onHit(t.id, p.damage[i] as number, owner);
        break;
      }
    }
  }
}
