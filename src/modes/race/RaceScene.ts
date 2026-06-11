/**
 * Three.js side of Race mode: builds the track ribbon, shoulders,
 * barrier walls, boost pads, start gantry, kart meshes, the translucent
 * ghost, and the debug layer (checkpoint gates, racing line, AI target
 * markers) from the PURE TrackData. Everything is procedural geometry
 * built once at construction; per-frame work only writes transforms and
 * uniform-free material colors. No allocations in the frame path.
 */

import * as THREE from 'three';
import type { TrackData } from '../../systems/race/Track';

export const KART_COLORS = [0x47e6ff, 0xff5470, 0xffd166, 0xb388ff] as const;
export const RACER_NAMES = ['YOU', 'VECTOR', 'HALOGEN', 'QUARTZ'] as const;

const TRACK_Y = 0.02;
const SHOULDER_Y = 0.005;

/** Build a flat ribbon mesh that follows the centerline at +/- widths. */
function buildRibbon(
  t: TrackData,
  inner: number,
  outer: number,
  y: number,
  color: number,
  emissive = 0,
): THREE.Mesh {
  const n = t.n;
  const positions = new Float32Array(n * 2 * 3 + 6);
  const idx: number[] = [];
  for (let i = 0; i <= n; i++) {
    const k = i % n;
    const nx = -(t.tz[k] as number);
    const nz = t.tx[k] as number;
    const cx = t.xs[k] as number;
    const cz = t.zs[k] as number;
    const o = i * 6;
    if (o + 5 < positions.length) {
      positions[o] = cx + nx * inner;
      positions[o + 1] = y;
      positions[o + 2] = cz + nz * inner;
      positions[o + 3] = cx + nx * outer;
      positions[o + 4] = y;
      positions[o + 5] = cz + nz * outer;
    }
    if (i < n) {
      const a = i * 2;
      idx.push(a, a + 1, a + 2, a + 1, a + 3, a + 2);
    }
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geo.setIndex(idx);
  geo.computeVertexNormals();
  const mat = new THREE.MeshLambertMaterial({
    color,
    emissive,
    side: THREE.DoubleSide,
  });
  return new THREE.Mesh(geo, mat);
}

/** Vertical barrier strip at a fixed lateral offset (the wall you hit). */
function buildWall(t: TrackData, offset: number, height: number, color: number): THREE.Mesh {
  const n = t.n;
  const positions = new Float32Array((n + 1) * 2 * 3);
  const idx: number[] = [];
  for (let i = 0; i <= n; i++) {
    const k = i % n;
    const nx = -(t.tz[k] as number);
    const nz = t.tx[k] as number;
    const x = (t.xs[k] as number) + nx * offset;
    const z = (t.zs[k] as number) + nz * offset;
    const o = i * 6;
    positions[o] = x;
    positions[o + 1] = 0;
    positions[o + 2] = z;
    positions[o + 3] = x;
    positions[o + 4] = height;
    positions[o + 5] = z;
    if (i < n) {
      const a = i * 2;
      idx.push(a, a + 1, a + 2, a + 1, a + 3, a + 2);
    }
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geo.setIndex(idx);
  const mat = new THREE.MeshBasicMaterial({
    color,
    transparent: true,
    opacity: 0.38,
    side: THREE.DoubleSide,
  });
  return new THREE.Mesh(geo, mat);
}

/** One kart: body + cabin + 4 wheels under a single group. */
export function buildKart(color: number, ghost = false): THREE.Group {
  const g = new THREE.Group();
  const opts = ghost
    ? { transparent: true as const, opacity: 0.32, depthWrite: false }
    : {};
  const bodyMat = new THREE.MeshLambertMaterial({ color, emissive: color, emissiveIntensity: 0.25, ...opts });
  const darkMat = new THREE.MeshLambertMaterial({ color: 0x14161f, ...opts });

  const body = new THREE.Mesh(new THREE.BoxGeometry(1.7, 0.5, 3.0), bodyMat);
  body.position.y = 0.45;
  g.add(body);
  const cabin = new THREE.Mesh(new THREE.BoxGeometry(1.1, 0.42, 1.2), darkMat);
  cabin.position.set(0, 0.85, -0.3);
  g.add(cabin);
  const wheelGeo = new THREE.BoxGeometry(0.34, 0.62, 0.62);
  for (const [wx, wz] of [[-0.95, 1.0], [0.95, 1.0], [-0.95, -1.05], [0.95, -1.05]] as const) {
    const w = new THREE.Mesh(wheelGeo, darkMat);
    w.position.set(wx, 0.31, wz);
    g.add(w);
  }
  return g;
}

export interface RaceSceneParts {
  scene: THREE.Scene;
  karts: THREE.Group[];
  ghost: THREE.Group;
  padMaterial: THREE.MeshBasicMaterial;
  debugGroup: THREE.Group;
  aiTargets: THREE.Mesh[];
  /** total meshes created (entity reporting) */
  entityCount: number;
}

export function buildRaceScene(t: TrackData): RaceSceneParts {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x070512);
  scene.fog = new THREE.Fog(0x0d0a24, 160, 900);

  // Lighting: cheap and shadowless (the race scene is its own world).
  scene.add(new THREE.AmbientLight(0x404a6a, 1.1));
  const dir = new THREE.DirectionalLight(0x9fb4ff, 0.9);
  dir.position.set(120, 180, -80);
  scene.add(dir);

  // Ground disc beneath everything.
  const ground = new THREE.Mesh(
    new THREE.CircleGeometry(420, 48),
    new THREE.MeshLambertMaterial({ color: 0x0c1410 }),
  );
  ground.rotation.x = -Math.PI / 2;
  ground.position.y = -0.05;
  scene.add(ground);

  // Off-road shoulder, asphalt, neon edge lines, barrier walls.
  scene.add(buildRibbon(t, -t.wallDist, t.wallDist, SHOULDER_Y, 0x21281c));
  scene.add(buildRibbon(t, -t.halfWidth, t.halfWidth, TRACK_Y, 0x1c1e2a));
  scene.add(buildRibbon(t, t.halfWidth - 0.5, t.halfWidth + 0.1, TRACK_Y + 0.012, 0x000000, 0x47e6ff));
  scene.add(buildRibbon(t, -t.halfWidth - 0.1, -t.halfWidth + 0.5, TRACK_Y + 0.012, 0x000000, 0xff4d9a));
  scene.add(buildWall(t, t.wallDist, 1.4, 0x47e6ff));
  scene.add(buildWall(t, -t.wallDist, 1.4, 0xff4d9a));

  // Boost pads: bright quads on the asphalt (color pulsed per frame).
  const padMaterial = new THREE.MeshBasicMaterial({ color: 0x35ffa8 });
  for (const pad of t.pads) {
    const i = pad.startSample;
    const j = pad.endSample;
    const geo = new THREE.PlaneGeometry(10, 7);
    const mesh = new THREE.Mesh(geo, padMaterial);
    const mx = ((t.xs[i] as number) + (t.xs[j] as number)) / 2;
    const mz = ((t.zs[i] as number) + (t.zs[j] as number)) / 2;
    mesh.position.set(mx, TRACK_Y + 0.02, mz);
    mesh.rotation.x = -Math.PI / 2;
    mesh.rotation.z = -Math.atan2(t.tx[i] as number, t.tz[i] as number);
    scene.add(mesh);
  }

  // Start/finish gantry at gate 0.
  const g0 = t.gates[0];
  if (g0) {
    const nx = -(t.tz[g0.sample] as number);
    const nz = t.tx[g0.sample] as number;
    const postMat = new THREE.MeshLambertMaterial({ color: 0x2a2f45 });
    const beamMat = new THREE.MeshBasicMaterial({ color: 0x47e6ff });
    const postGeo = new THREE.BoxGeometry(0.6, 8, 0.6);
    for (const side of [-1, 1]) {
      const post = new THREE.Mesh(postGeo, postMat);
      post.position.set(g0.x + nx * side * (t.halfWidth + 1), 4, g0.z + nz * side * (t.halfWidth + 1));
      scene.add(post);
    }
    const beam = new THREE.Mesh(new THREE.BoxGeometry((t.halfWidth + 1) * 2, 0.7, 0.7), beamMat);
    beam.position.set(g0.x, 7.6, g0.z);
    beam.rotation.y = Math.atan2(nx, nz) + Math.PI / 2;
    scene.add(beam);
  }

  // Karts: player + 3 rivals + the ghost.
  const karts: THREE.Group[] = [];
  for (let i = 0; i < 4; i++) {
    const kart = buildKart(KART_COLORS[i] as number);
    scene.add(kart);
    karts.push(kart);
  }
  const ghost = buildKart(0xf2f6ff, true);
  ghost.visible = false;
  scene.add(ghost);

  // Debug layer: gates, racing line, AI target markers (hidden by default).
  const debugGroup = new THREE.Group();
  debugGroup.visible = false;
  const lineGeo = new THREE.BufferGeometry();
  const linePos = new Float32Array((t.n + 1) * 3);
  for (let i = 0; i <= t.n; i++) {
    const k = i % t.n;
    linePos[i * 3] = t.xs[k] as number;
    linePos[i * 3 + 1] = 0.5;
    linePos[i * 3 + 2] = t.zs[k] as number;
  }
  lineGeo.setAttribute('position', new THREE.BufferAttribute(linePos, 3));
  debugGroup.add(new THREE.Line(lineGeo, new THREE.LineBasicMaterial({ color: 0x35ffa8 })));

  const gateMat = new THREE.MeshBasicMaterial({ color: 0xffd166, wireframe: true });
  for (const gate of t.gates) {
    const ring = new THREE.Mesh(new THREE.TorusGeometry(gate.r, 0.18, 6, 40), gateMat);
    ring.position.set(gate.x, 0.4, gate.z);
    ring.rotation.x = Math.PI / 2;
    debugGroup.add(ring);
  }

  const aiTargets: THREE.Mesh[] = [];
  const targetGeo = new THREE.SphereGeometry(0.9, 8, 8);
  for (let i = 0; i < 3; i++) {
    const m = new THREE.Mesh(
      targetGeo,
      new THREE.MeshBasicMaterial({ color: KART_COLORS[i + 1] as number }),
    );
    m.position.y = 1.2;
    debugGroup.add(m);
    aiTargets.push(m);
  }
  scene.add(debugGroup);

  let entityCount = 0;
  scene.traverse(() => entityCount++);

  return { scene, karts, ghost, padMaterial, debugGroup, aiTargets, entityCount };
}
