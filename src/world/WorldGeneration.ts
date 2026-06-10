/**
 * Pure, deterministic world layout generation. No Three.js imports:
 * this module turns a seed into plain data (buildings, lamps, signs,
 * trees, pedestals, water, collision extents) that the rendering side
 * (ProceduralCity / Terrain / Vegetation) turns into meshes and the
 * Minimap draws directly. Unit-tested for determinism.
 */

import { Rng } from '../core/Rng';

// ---- World constants -------------------------------------------------

export const WORLD = {
  /** half-extent of the playable square, meters */
  half: 320,
  /** city occupies a square of this half-extent, terrain flattened inside */
  cityHalf: 120,
  blockSize: 36,
  streetWidth: 12,
  blocksPerSide: 5,
  floorHeight: 3,
  windowCellW: 2,
  /** rectangular lake east of the city */
  lake: { minX: 150, maxX: 300, minZ: -100, maxZ: 100 },
  waterY: -0.6,
  lakeDepth: 4,
} as const;

// ---- Data shapes ------------------------------------------------------

export interface BuildingData {
  id: string;
  x: number;
  z: number;
  w: number;
  d: number;
  h: number;
  /** per-building hash seed driving the lit-window pattern */
  facadeSeed: number;
  /** real count of window cells on the four facades */
  windowCount: number;
  /** palette index for facade tint */
  tint: number;
}

export interface LampData { x: number; z: number }
export interface SignData {
  x: number; z: number; y: number;
  w: number; h: number;
  /** facing angle, radians around Y */
  rot: number;
  hue: number;
}
export interface TreeData { x: number; z: number; scale: number }
export interface PropData { id: string; x: number; z: number; w: number; d: number; h: number }

export interface PedestalData {
  id: string;
  label: string;
  x: number;
  z: number;
  hue: number;
}

export interface WorldData {
  seed: number;
  buildings: BuildingData[];
  lamps: LampData[];
  signs: SignData[];
  trees: TreeData[];
  props: PropData[];
  pedestals: PedestalData[];
  tower: { x: number; z: number; w: number; d: number; h: number };
  totalWindows: number;
  spawn: { x: number; z: number };
}

/** The five future game modes get real pedestals + interact targets now. */
export const FUTURE_MODES: ReadonlyArray<{ id: string; label: string; hue: number }> = [
  { id: 'race', label: 'Race', hue: 0.55 },
  { id: 'battle', label: 'Battle', hue: 0.0 },
  { id: 'board', label: 'Board', hue: 0.33 },
  { id: 'flight', label: 'Flight', hue: 0.12 },
  { id: 'shader', label: 'Shader', hue: 0.78 },
];

// ---- Terrain height (pure, shared by mesh + player grounding) ---------

function hash2(ix: number, iz: number, seed: number): number {
  let h = (ix * 374761393 + iz * 668265263) ^ seed;
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  h ^= h >>> 16;
  return (h >>> 0) / 4294967296;
}

function smooth(t: number): number {
  return t * t * (3 - 2 * t);
}

function valueNoise(x: number, z: number, seed: number): number {
  const ix = Math.floor(x);
  const iz = Math.floor(z);
  const fx = smooth(x - ix);
  const fz = smooth(z - iz);
  const a = hash2(ix, iz, seed);
  const b = hash2(ix + 1, iz, seed);
  const c = hash2(ix, iz + 1, seed);
  const d = hash2(ix + 1, iz + 1, seed);
  return a + (b - a) * fx + (c - a) * fz + (a - b - c + d) * fx * fz;
}

const clamp01 = (v: number): number => Math.min(1, Math.max(0, v));

/**
 * Terrain height at world (x, z) for a seed. Flat (0) inside the city,
 * rolling hills outside, a depression under the lake.
 */
export function terrainHeight(x: number, z: number, seed: number): number {
  const n =
    valueNoise(x / 60, z / 60, seed) * 6 +
    valueNoise(x / 17, z / 17, seed ^ 0x9e3779b9) * 1.6 -
    3.8;
  // Flatten inside the city with a smooth shoulder.
  const dCity = Math.max(Math.abs(x), Math.abs(z)) - WORLD.cityHalf;
  const cityBlend = smooth(clamp01(dCity / 40)); // 0 in city -> 1 outside
  let h = n * cityBlend;
  // Lake depression.
  const L = WORLD.lake;
  const inX = clamp01(Math.min(x - L.minX, L.maxX - x) / 25);
  const inZ = clamp01(Math.min(z - L.minZ, L.maxZ - z) / 25);
  const lakeBlend = smooth(inX) * smooth(inZ);
  h = h * (1 - lakeBlend) + (WORLD.waterY - WORLD.lakeDepth) * lakeBlend;
  return h === 0 ? 0 : h; // normalize -0 from the city-flatten multiply
}

// ---- Generation -------------------------------------------------------

function windowCountFor(w: number, d: number, h: number): number {
  const floors = Math.max(1, Math.floor(h / WORLD.floorHeight));
  const colsW = Math.max(1, Math.floor(w / WORLD.windowCellW));
  const colsD = Math.max(1, Math.floor(d / WORLD.windowCellW));
  return floors * 2 * (colsW + colsD);
}

export function generateWorld(seed: number): WorldData {
  const root = new Rng(seed);
  const cityRng = root.fork('city');
  const lampRng = root.fork('lamps');
  const signRng = root.fork('signs');
  const treeRng = root.fork('trees');
  const propRng = root.fork('props');

  const { blockSize, streetWidth, blocksPerSide } = WORLD;
  const pitch = blockSize + streetWidth;
  const origin = -((blocksPerSide * pitch - streetWidth) / 2) + blockSize / 2;
  const center = Math.floor(blocksPerSide / 2);

  const buildings: BuildingData[] = [];
  const lamps: LampData[] = [];
  const signs: SignData[] = [];
  let totalWindows = 0;

  for (let bx = 0; bx < blocksPerSide; bx++) {
    for (let bz = 0; bz < blocksPerSide; bz++) {
      const cx = origin + bx * pitch;
      const cz = origin + bz * pitch;
      if (bx === center && bz === center) continue; // central plaza block

      // 2x2 lots per block.
      for (let lx = 0; lx < 2; lx++) {
        for (let lz = 0; lz < 2; lz++) {
          if (cityRng.chance(0.12)) continue; // some empty lots (pocket parks)
          const lotX = cx + (lx - 0.5) * (blockSize / 2);
          const lotZ = cz + (lz - 0.5) * (blockSize / 2);
          const w = cityRng.range(9, 15);
          const d = cityRng.range(9, 15);
          // Taller toward the center of the city.
          const distNorm =
            Math.hypot(bx - center, bz - center) / Math.hypot(center, center);
          const hMax = 18 + (1 - distNorm) * 42;
          const h = cityRng.range(9, hMax);
          const b: BuildingData = {
            id: `b${buildings.length}`,
            x: lotX + cityRng.range(-1.5, 1.5),
            z: lotZ + cityRng.range(-1.5, 1.5),
            w,
            d,
            h,
            facadeSeed: cityRng.next(),
            windowCount: windowCountFor(w, d, h),
            tint: cityRng.int(0, 3),
          };
          buildings.push(b);
          totalWindows += b.windowCount;

          // Some buildings sport a neon sign near the top of one face.
          if (h > 16 && signRng.chance(0.5)) {
            const face = signRng.int(0, 3);
            const sw = signRng.range(4, Math.max(4.5, w - 3));
            const sh = signRng.range(1.2, 2.4);
            const off = 0.12;
            let sx = b.x, sz = b.z, rot = 0;
            if (face === 0) { sz = b.z + d / 2 + off; rot = 0; }
            else if (face === 1) { sz = b.z - d / 2 - off; rot = Math.PI; }
            else if (face === 2) { sx = b.x + w / 2 + off; rot = Math.PI / 2; }
            else { sx = b.x - w / 2 - off; rot = -Math.PI / 2; }
            signs.push({
              x: sx, z: sz, y: h * signRng.range(0.6, 0.85),
              w: sw, h: sh, rot, hue: signRng.next(),
            });
          }
        }
      }

      // Street lamps on block corners.
      const lo = blockSize / 2 + 2.5;
      if (lampRng.chance(0.9)) lamps.push({ x: cx - lo, z: cz - lo });
      if (lampRng.chance(0.9)) lamps.push({ x: cx + lo, z: cz + lo });
    }
  }

  // Plaza: landmark tower offset to the plaza's north edge, pedestal arc south.
  const plazaX = origin + center * pitch;
  const plazaZ = origin + center * pitch;
  const tower = { x: plazaX, z: plazaZ - 12, w: 10, d: 10, h: 96 };
  totalWindows += windowCountFor(tower.w, tower.d, tower.h);

  const pedestals: PedestalData[] = FUTURE_MODES.map((m, i) => {
    const ang = Math.PI * (0.15 + (0.7 * i) / (FUTURE_MODES.length - 1));
    return {
      id: m.id,
      label: m.label,
      x: plazaX + Math.cos(ang) * 10,
      z: plazaZ + 4 + Math.sin(ang) * 8,
      hue: m.hue,
    };
  });

  // Plaza props: crates/benches with real collision.
  const props: PropData[] = [];
  for (let i = 0; i < 8; i++) {
    const ang = propRng.range(0, Math.PI * 2);
    const r = propRng.range(14, 17);
    props.push({
      id: `p${i}`,
      x: plazaX + Math.cos(ang) * r,
      z: plazaZ + Math.sin(ang) * r,
      w: propRng.range(0.8, 1.6),
      d: propRng.range(0.8, 1.6),
      h: propRng.range(0.6, 1.4),
    });
  }

  // Wilderness trees: seeded scatter outside the city, off the lake.
  const trees: TreeData[] = [];
  const L = WORLD.lake;
  const margin = 6;
  let attempts = 0;
  while (trees.length < 700 && attempts < 5000) {
    attempts++;
    const x = treeRng.range(-WORLD.half + 8, WORLD.half - 8);
    const z = treeRng.range(-WORLD.half + 8, WORLD.half - 8);
    if (Math.max(Math.abs(x), Math.abs(z)) < WORLD.cityHalf + 10) continue;
    if (x > L.minX - margin && x < L.maxX + margin && z > L.minZ - margin && z < L.maxZ + margin) continue;
    if (terrainHeight(x, z, seed) < WORLD.waterY + 0.3) continue;
    trees.push({ x, z, scale: treeRng.range(0.7, 1.6) });
  }

  return {
    seed,
    buildings,
    lamps,
    signs,
    trees,
    props,
    pedestals,
    tower,
    totalWindows,
    spawn: { x: plazaX, z: plazaZ + 22 },
  };
}
