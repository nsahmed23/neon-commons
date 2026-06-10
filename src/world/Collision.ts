/**
 * Real collision: static AABBs in a uniform spatial-hash grid, plus a
 * capsule (vertical cylinder for XZ purposes) resolver for the player.
 * Pure math, no Three.js, fully unit-tested.
 *
 * No allocations on the hot path: query results and scratch vectors are
 * reused buffers owned by the CollisionWorld instance.
 */

export interface AABB {
  id: string;
  minX: number;
  minY: number;
  minZ: number;
  maxX: number;
  maxY: number;
  maxZ: number;
}

export function makeAABB(
  id: string,
  cx: number,
  cz: number,
  w: number,
  d: number,
  y0: number,
  y1: number,
): AABB {
  return {
    id,
    minX: cx - w / 2,
    maxX: cx + w / 2,
    minZ: cz - d / 2,
    maxZ: cz + d / 2,
    minY: y0,
    maxY: y1,
  };
}

export interface ResolveResult {
  x: number;
  z: number;
  collided: boolean;
  /** ids of boxes the capsule was pushed out of this resolve */
  hitIds: string[];
}

export class CollisionWorld {
  readonly cellSize: number;
  private grid = new Map<number, AABB[]>();
  private boxes: AABB[] = [];
  // Reused buffers (bounded; no per-frame allocation).
  private queryBuf: AABB[] = [];
  private seen = new Set<string>();
  private resolveResult: ResolveResult = { x: 0, z: 0, collided: false, hitIds: [] };

  constructor(cellSize = 16) {
    this.cellSize = cellSize;
  }

  get boxCount(): number {
    return this.boxes.length;
  }

  private key(ix: number, iz: number): number {
    // Interleave-free packing; world stays within +/- 32k cells.
    return (ix + 32768) * 65536 + (iz + 32768);
  }

  addBox(box: AABB): void {
    this.boxes.push(box);
    const ix0 = Math.floor(box.minX / this.cellSize);
    const ix1 = Math.floor(box.maxX / this.cellSize);
    const iz0 = Math.floor(box.minZ / this.cellSize);
    const iz1 = Math.floor(box.maxZ / this.cellSize);
    for (let ix = ix0; ix <= ix1; ix++) {
      for (let iz = iz0; iz <= iz1; iz++) {
        const k = this.key(ix, iz);
        let cell = this.grid.get(k);
        if (!cell) {
          cell = [];
          this.grid.set(k, cell);
        }
        cell.push(box);
      }
    }
  }

  /** Is a point inside any box? */
  queryPoint(x: number, y: number, z: number): AABB | null {
    const k = this.key(Math.floor(x / this.cellSize), Math.floor(z / this.cellSize));
    const cell = this.grid.get(k);
    if (!cell) return null;
    for (const b of cell) {
      if (
        x >= b.minX && x <= b.maxX &&
        z >= b.minZ && z <= b.maxZ &&
        y >= b.minY && y <= b.maxY
      ) {
        return b;
      }
    }
    return null;
  }

  /**
   * All boxes overlapping the given AABB region. Returns an internal
   * reused buffer: consume before the next query, do not retain.
   */
  queryAABB(minX: number, minZ: number, maxX: number, maxZ: number, minY = -Infinity, maxY = Infinity): readonly AABB[] {
    this.queryBuf.length = 0;
    this.seen.clear();
    const ix0 = Math.floor(minX / this.cellSize);
    const ix1 = Math.floor(maxX / this.cellSize);
    const iz0 = Math.floor(minZ / this.cellSize);
    const iz1 = Math.floor(maxZ / this.cellSize);
    for (let ix = ix0; ix <= ix1; ix++) {
      for (let iz = iz0; iz <= iz1; iz++) {
        const cell = this.grid.get(this.key(ix, iz));
        if (!cell) continue;
        for (const b of cell) {
          if (this.seen.has(b.id)) continue;
          if (
            b.maxX >= minX && b.minX <= maxX &&
            b.maxZ >= minZ && b.minZ <= maxZ &&
            b.maxY >= minY && b.minY <= maxY
          ) {
            this.seen.add(b.id);
            this.queryBuf.push(b);
          }
        }
      }
    }
    return this.queryBuf;
  }

  /**
   * Resolve a capsule (radius r, feet at y, head at y+height) against all
   * nearby boxes by pushing it out along XZ. Iterates a few times so
   * corner cases (two boxes meeting) settle. Returns a reused object.
   */
  resolveCapsule(x: number, y: number, z: number, radius: number, height: number): ResolveResult {
    const res = this.resolveResult;
    res.x = x;
    res.z = z;
    res.collided = false;
    res.hitIds.length = 0;

    const yLo = y + 0.1; // ignore boxes entirely below the feet (steps)
    const yHi = y + height;

    for (let iter = 0; iter < 3; iter++) {
      const hits = this.queryAABB(
        res.x - radius, res.z - radius, res.x + radius, res.z + radius, yLo, yHi,
      );
      let pushed = false;
      for (const b of hits) {
        // Closest point on box to circle center (XZ plane).
        const cx = Math.max(b.minX, Math.min(res.x, b.maxX));
        const cz = Math.max(b.minZ, Math.min(res.z, b.maxZ));
        let dx = res.x - cx;
        let dz = res.z - cz;
        const distSq = dx * dx + dz * dz;
        if (distSq >= radius * radius) continue;
        if (distSq > 1e-12) {
          const dist = Math.sqrt(distSq);
          const push = radius - dist;
          res.x += (dx / dist) * push;
          res.z += (dz / dist) * push;
        } else {
          // Center inside box: push out along the shallowest face.
          const left = res.x - b.minX;
          const right = b.maxX - res.x;
          const near = res.z - b.minZ;
          const far = b.maxZ - res.z;
          const m = Math.min(left, right, near, far);
          if (m === left) res.x = b.minX - radius;
          else if (m === right) res.x = b.maxX + radius;
          else if (m === near) res.z = b.minZ - radius;
          else res.z = b.maxZ + radius;
        }
        if (!res.hitIds.includes(b.id)) res.hitIds.push(b.id);
        res.collided = true;
        pushed = true;
      }
      if (!pushed) break;
    }
    return res;
  }
}
