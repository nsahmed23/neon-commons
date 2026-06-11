/**
 * Three.js side of Flight mode. Unlike Race/Battle/Board (which own
 * separate scenes), flight plays INSIDE the existing hub scene — the
 * payoff shot is flying over the skyline Stage A built — so this module
 * builds one THREE.Group (player drone, course ring toruses, sentry and
 * escort drones, the boss + its shield bubble, a pooled projectile
 * InstancedMesh) that FlightMode adds to the hub scene on enter and
 * removes on exit. Everything is procedural geometry built once; the
 * frame path only writes transforms, instance matrices and colors.
 */

import * as THREE from 'three';
import { PROJECTILE } from '../../systems/flight/Projectiles';
import type { CourseData } from '../../systems/flight/Rings';

export interface FlightSceneParts {
  group: THREE.Group;
  player: THREE.Group;
  rings: THREE.Mesh[];
  ringMaterials: THREE.MeshLambertMaterial[];
  enemies: THREE.Group[];
  boss: THREE.Group;
  shield: THREE.Mesh;
  shieldMaterial: THREE.MeshBasicMaterial;
  bolts: THREE.InstancedMesh;
  entityCount: number;
}

export const RING_NEXT_COLOR = 0x47e6ff;
export const RING_PASSED_COLOR = 0x35ffa8;
export const RING_FUTURE_COLOR = 0x6a5acd;

function droneBody(hull: number, accent: number, scale: number): THREE.Group {
  const g = new THREE.Group();
  const hullMat = new THREE.MeshLambertMaterial({ color: hull });
  const accentMat = new THREE.MeshLambertMaterial({
    color: accent,
    emissive: accent,
    emissiveIntensity: 0.7,
  });
  const body = new THREE.Mesh(new THREE.BoxGeometry(1.6, 0.5, 2.2), hullMat);
  g.add(body);
  const canopy = new THREE.Mesh(new THREE.BoxGeometry(0.7, 0.35, 0.9), accentMat);
  canopy.position.set(0, 0.4, 0.3);
  g.add(canopy);
  for (const sx of [-1, 1]) {
    const arm = new THREE.Mesh(new THREE.BoxGeometry(1.3, 0.16, 0.5), hullMat);
    arm.position.set(sx * 1.3, 0, -0.2);
    g.add(arm);
    const rotor = new THREE.Mesh(new THREE.CylinderGeometry(0.55, 0.55, 0.1, 10), accentMat);
    rotor.position.set(sx * 1.85, 0.14, -0.2);
    g.add(rotor);
  }
  const tail = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.3, 1.0), accentMat);
  tail.position.set(0, 0.1, -1.4);
  g.add(tail);
  g.scale.setScalar(scale);
  return g;
}

export function buildFlightScene(course: CourseData): FlightSceneParts {
  const group = new THREE.Group();
  group.name = 'flight-group';
  let entityCount = 0;

  // Player drone.
  const player = droneBody(0x2a2f45, 0x47e6ff, 1);
  group.add(player);
  entityCount++;

  // Course rings: torus per ring (10 of them; cheap and individually
  // recolorable for the passed/next/future states).
  const ringGeo = new THREE.TorusGeometry(7, 0.45, 10, 36);
  const rings: THREE.Mesh[] = [];
  const ringMaterials: THREE.MeshLambertMaterial[] = [];
  for (const r of course.rings) {
    const mat = new THREE.MeshLambertMaterial({
      color: RING_FUTURE_COLOR,
      emissive: RING_FUTURE_COLOR,
      emissiveIntensity: 0.55,
    });
    const mesh = new THREE.Mesh(ringGeo, mat);
    mesh.position.set(r.x, r.y, r.z);
    group.add(mesh);
    rings.push(mesh);
    ringMaterials.push(mat);
    entityCount++;
  }

  // Enemy drones: 4 sentries + 2 boss escorts share a silhouette.
  const enemies: THREE.Group[] = [];
  for (let i = 0; i < 6; i++) {
    const e = droneBody(0x3d1f2a, i < 4 ? 0xff5470 : 0xffd166, 0.9);
    group.add(e);
    enemies.push(e);
    entityCount++;
  }

  // Boss: a heavy tri-rotor with a glowing core.
  const boss = droneBody(0x1c2233, 0xff5470, 2.6);
  const core = new THREE.Mesh(
    new THREE.SphereGeometry(0.55, 12, 10),
    new THREE.MeshLambertMaterial({
      color: 0xff5470,
      emissive: 0xff5470,
      emissiveIntensity: 1,
    }),
  );
  core.position.set(0, 0.1, 0.6);
  boss.add(core);
  group.add(boss);
  entityCount++;

  // Shield bubble (visible only while the boss phase is 'shielded').
  const shieldMaterial = new THREE.MeshBasicMaterial({
    color: 0x47e6ff,
    transparent: true,
    opacity: 0.22,
    side: THREE.DoubleSide,
    depthWrite: false,
  });
  const shield = new THREE.Mesh(new THREE.SphereGeometry(6.2, 18, 14), shieldMaterial);
  boss.add(shield);

  // Projectiles: one InstancedMesh sized to the pool bound.
  const bolts = new THREE.InstancedMesh(
    new THREE.SphereGeometry(0.28, 6, 5),
    new THREE.MeshBasicMaterial({ color: 0xffffff }),
    PROJECTILE.max,
  );
  bolts.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  bolts.count = 0;
  group.add(bolts);

  return {
    group,
    player,
    rings,
    ringMaterials,
    enemies,
    boss,
    shield,
    shieldMaterial,
    bolts,
    entityCount,
  };
}
