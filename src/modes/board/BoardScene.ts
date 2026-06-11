/**
 * Three.js side of Board mode: a procedural flat ring of 28 colored
 * space tiles in the arena style, four pawn meshes, two real dice
 * whose settle rotations show the actual seeded roll, per-space owner
 * strips and development markers. Built once; the frame path only
 * writes transforms, colors and visibility (no allocations).
 */

import * as THREE from 'three';
import { makeLabelTexture } from '../../rendering/Materials';
import {
  BOARD,
  BOARD_SIZE,
  SET_HUE,
  type SpaceDef,
} from '../../systems/board/BoardData';

export const RING_RADIUS = 17;
const TILE_W = 3.3;
const TILE_D = 2.4;

/** Pawn/owner colors per seat (cyan, magenta, amber, green). */
export const PLAYER_HEX: readonly number[] = [0x47e6ff, 0xff5470, 0xffd166, 0x35ffa8];

export interface BoardSceneParts {
  scene: THREE.Scene;
  tileMats: THREE.MeshLambertMaterial[];
  ownerStrips: (THREE.Mesh | null)[];
  ownerStripMats: (THREE.MeshBasicMaterial | null)[];
  levelMarkers: (THREE.Mesh[] | null)[];
  pawns: THREE.Group[];
  dice: [THREE.Mesh, THREE.Mesh];
  entityCount: number;
}

const scratch = new THREE.Vector3();

/** World-space center of space i (ring runs clockwise from the gate). */
export function spaceCenter(i: number, out?: THREE.Vector3): THREE.Vector3 {
  const v = out ?? scratch.clone();
  const a = -((i / BOARD_SIZE) * Math.PI * 2) + Math.PI / 2;
  v.set(Math.cos(a) * RING_RADIUS, 0, Math.sin(a) * RING_RADIUS);
  return v;
}

function spaceAngle(i: number): number {
  return -((i / BOARD_SIZE) * Math.PI * 2) + Math.PI / 2;
}

function tileColor(def: SpaceDef): THREE.Color {
  const c = new THREE.Color();
  switch (def.kind) {
    case 'district':
      return c.setHSL(SET_HUE[def.set], 0.7, 0.45);
    case 'transit':
      return c.set(0x3d6fd6);
    case 'utility':
      return c.set(0x9a7b2f);
    case 'tax':
      return c.set(0x8a2f3c);
    case 'event':
      return c.set(0x6a3fae);
    case 'corner':
      return c.set(def.corner === 'start' ? 0x2fa05a : 0x2c3354);
  }
}

/** Pip texture for one die face. */
function pipTexture(value: number): THREE.CanvasTexture {
  const canvas = document.createElement('canvas');
  canvas.width = 64;
  canvas.height = 64;
  const g = canvas.getContext('2d');
  if (g) {
    g.fillStyle = '#f4f6ff';
    g.fillRect(0, 0, 64, 64);
    g.fillStyle = '#101428';
    const spots: Record<number, Array<[number, number]>> = {
      1: [[32, 32]],
      2: [[18, 18], [46, 46]],
      3: [[16, 16], [32, 32], [48, 48]],
      4: [[18, 18], [46, 18], [18, 46], [46, 46]],
      5: [[16, 16], [48, 16], [32, 32], [16, 48], [48, 48]],
      6: [[18, 14], [46, 14], [18, 32], [46, 32], [18, 50], [46, 50]],
    };
    for (const [x, y] of spots[value] ?? []) {
      g.beginPath();
      g.arc(x, y, 6, 0, Math.PI * 2);
      g.fill();
    }
  }
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

/**
 * Rotation that puts face `value` on top. Face layout on the box
 * materials: +x=3, -x=4, +y=1, -y=6, +z=2, -z=5.
 */
export function diceSettleRotation(value: number): [number, number, number] {
  switch (value) {
    case 1: return [0, 0, 0];
    case 2: return [-Math.PI / 2, 0, 0];
    case 3: return [0, 0, Math.PI / 2];
    case 4: return [0, 0, -Math.PI / 2];
    case 5: return [Math.PI / 2, 0, 0];
    default: return [Math.PI, 0, 0]; // 6
  }
}

function buildPawn(hex: number): THREE.Group {
  const group = new THREE.Group();
  const mat = new THREE.MeshLambertMaterial({
    color: hex,
    emissive: hex,
    emissiveIntensity: 0.35,
  });
  const cone = new THREE.Mesh(new THREE.ConeGeometry(0.42, 1.2, 10), mat);
  cone.position.y = 0.8;
  group.add(cone);
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.26, 10, 8), mat);
  head.position.y = 1.55;
  group.add(head);
  return group;
}

export function buildBoardScene(): BoardSceneParts {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x07060f);
  scene.fog = new THREE.Fog(0x0c0a1e, 70, 190);

  scene.add(new THREE.AmbientLight(0x4a5480, 1.05));
  const key = new THREE.DirectionalLight(0xbfd0ff, 0.95);
  key.position.set(25, 55, -15);
  scene.add(key);
  const rim = new THREE.DirectionalLight(0xff66aa, 0.22);
  rim.position.set(-35, 20, 30);
  scene.add(rim);

  // Table.
  const table = new THREE.Mesh(
    new THREE.CylinderGeometry(RING_RADIUS + 5, RING_RADIUS + 6, 0.6, 12),
    new THREE.MeshLambertMaterial({ color: 0x171a2b }),
  );
  table.position.y = -0.32;
  scene.add(table);

  // Center plate with the game title.
  const plate = new THREE.Mesh(
    new THREE.PlaneGeometry(9, 3.4),
    new THREE.MeshBasicMaterial({
      map: makeLabelTexture('Neon Districts', 0.52),
      transparent: true,
    }),
  );
  plate.rotation.x = -Math.PI / 2;
  plate.position.y = 0.02;
  scene.add(plate);

  // The 28 tiles + per-space owner strips and level markers.
  const tileGeo = new THREE.BoxGeometry(TILE_W, 0.3, TILE_D);
  const stripGeo = new THREE.BoxGeometry(TILE_W * 0.84, 0.14, 0.34);
  const markerGeo = new THREE.BoxGeometry(0.42, 0.42, 0.42);
  const tileMats: THREE.MeshLambertMaterial[] = [];
  const ownerStrips: (THREE.Mesh | null)[] = [];
  const ownerStripMats: (THREE.MeshBasicMaterial | null)[] = [];
  const levelMarkers: (THREE.Mesh[] | null)[] = [];

  for (let i = 0; i < BOARD_SIZE; i++) {
    const def = BOARD[i] as SpaceDef;
    const mat = new THREE.MeshLambertMaterial({
      color: tileColor(def),
      emissive: tileColor(def),
      emissiveIntensity: 0.12,
    });
    tileMats.push(mat);
    const tile = new THREE.Mesh(tileGeo, mat);
    spaceCenter(i, tile.position);
    tile.rotation.y = spaceAngle(i) + Math.PI / 2;
    scene.add(tile);

    if (def.kind === 'district' || def.kind === 'transit' || def.kind === 'utility') {
      const stripMat = new THREE.MeshBasicMaterial({ color: 0xffffff });
      const strip = new THREE.Mesh(stripGeo, stripMat);
      // Inner edge of the tile (toward the table center).
      const a = spaceAngle(i);
      strip.position.set(
        Math.cos(a) * (RING_RADIUS - TILE_D / 2 - 0.35),
        0.18,
        Math.sin(a) * (RING_RADIUS - TILE_D / 2 - 0.35),
      );
      strip.rotation.y = a + Math.PI / 2;
      strip.visible = false;
      scene.add(strip);
      ownerStrips.push(strip);
      ownerStripMats.push(stripMat);
    } else {
      ownerStrips.push(null);
      ownerStripMats.push(null);
    }

    if (def.kind === 'district') {
      const markers: THREE.Mesh[] = [];
      const a = spaceAngle(i);
      for (let lvl = 0; lvl < 3; lvl++) {
        const m = new THREE.Mesh(
          markerGeo,
          new THREE.MeshLambertMaterial({
            color: 0xf4f6ff,
            emissive: 0x7df9ff,
            emissiveIntensity: 0.4,
          }),
        );
        // Stack outward along the tile on the rim side.
        const side = (lvl - 1) * 1.0;
        m.position.set(
          Math.cos(a) * (RING_RADIUS + TILE_D / 2 + 0.45) - Math.sin(a) * side,
          0.36,
          Math.sin(a) * (RING_RADIUS + TILE_D / 2 + 0.45) + Math.cos(a) * side,
        );
        m.visible = false;
        scene.add(m);
        markers.push(m);
      }
      levelMarkers.push(markers);
    } else {
      levelMarkers.push(null);
    }
  }

  // Corner + transit name plates for orientation.
  for (const i of [0, 7, 14, 3, 10, 17, 24]) {
    const def = BOARD[i] as SpaceDef;
    const hue = def.kind === 'corner' ? 0.42 : 0.6;
    const p = new THREE.Mesh(
      new THREE.PlaneGeometry(3.4, 1.3),
      new THREE.MeshBasicMaterial({
        map: makeLabelTexture(def.name, hue),
        transparent: true,
        side: THREE.DoubleSide,
      }),
    );
    spaceCenter(i, p.position);
    p.position.y = 2.0;
    p.rotation.y = spaceAngle(i) - Math.PI / 2;
    scene.add(p);
  }

  // Pawns (4 seats; unused ones hidden by the mode).
  const pawns: THREE.Group[] = [];
  for (let s = 0; s < 4; s++) {
    const pawn = buildPawn(PLAYER_HEX[s] as number);
    spaceCenter(0, pawn.position);
    pawn.visible = false;
    scene.add(pawn);
    pawns.push(pawn);
  }

  // Two dice near the center; face layout +x=3 -x=4 +y=1 -y=6 +z=2 -z=5.
  const faceFor = (v: number): THREE.MeshLambertMaterial =>
    new THREE.MeshLambertMaterial({ map: pipTexture(v) });
  const diceGeo = new THREE.BoxGeometry(1.1, 1.1, 1.1);
  const mkDie = (x: number): THREE.Mesh => {
    const die = new THREE.Mesh(diceGeo, [
      faceFor(3), faceFor(4), faceFor(1), faceFor(6), faceFor(2), faceFor(5),
    ]);
    die.position.set(x, 0.85, 6.5);
    die.visible = false;
    scene.add(die);
    return die;
  };
  const dice: [THREE.Mesh, THREE.Mesh] = [mkDie(-1.2), mkDie(1.2)];

  // Ring of distant pylons for depth, matching the arena look.
  const pylonMat = new THREE.MeshLambertMaterial({ color: 0x232842 });
  const pylonGeo = new THREE.BoxGeometry(1.5, 8, 1.5);
  for (let i = 0; i < 10; i++) {
    const a = (i / 10) * Math.PI * 2;
    const p = new THREE.Mesh(pylonGeo, pylonMat);
    p.position.set(Math.cos(a) * (RING_RADIUS + 13), 4, Math.sin(a) * (RING_RADIUS + 13));
    scene.add(p);
  }

  let entityCount = 0;
  scene.traverse(() => entityCount++);
  return { scene, tileMats, ownerStrips, ownerStripMats, levelMarkers, pawns, dice, entityCount };
}
