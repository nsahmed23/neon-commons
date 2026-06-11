/**
 * Three.js side of Battle mode: a hex-lit arena and six procedural
 * robot meshes built from boxes/cylinders (no asset packs), name
 * plates via the shared Materials label helper, and transform-only
 * animation hooks (lunge, flinch, heal pulse, KO sink) driven by
 * BattleMode from real resolution events. Everything is constructed
 * once; the frame path only writes transforms and material colors.
 */

import * as THREE from 'three';
import { makeLabelTexture } from '../../rendering/Materials';
import type { UnitState } from '../../systems/battle/Resolution';
import { TYPE_HUE } from '../../systems/battle/TypeChart';

export const ARENA_HALF = 16;
const RANK_X = 7.5; // distance of each team line from center
const FILE_Z = 6.5; // spacing between units in a line

export interface RobotRig {
  group: THREE.Group;
  /** body material whose emissive we pulse on hit/heal */
  bodyMat: THREE.MeshLambertMaterial;
  ring: THREE.Mesh;
  ringMat: THREE.MeshBasicMaterial;
  home: THREE.Vector3;
  facing: number;
}

export interface BattleSceneParts {
  scene: THREE.Scene;
  robots: RobotRig[];
  entityCount: number;
}

/** Slot position for unit i (0-2 player side -X, 3-5 enemy side +X). */
export function slotPosition(id: number): THREE.Vector3 {
  const side = id < 3 ? -1 : 1;
  const file = id % 3;
  return new THREE.Vector3(side * RANK_X, 0, (file - 1) * FILE_Z);
}

/** One robot: torso, head, visor, shoulder pods, legs — type-tinted. */
function buildRobot(unit: UnitState): RobotRig {
  const hue = TYPE_HUE[unit.spec.type];
  const color = new THREE.Color().setHSL(hue, 0.75, 0.55);
  const dark = new THREE.Color().setHSL(hue, 0.3, 0.16);

  const group = new THREE.Group();
  const bodyMat = new THREE.MeshLambertMaterial({
    color,
    emissive: color,
    emissiveIntensity: 0.18,
  });
  const darkMat = new THREE.MeshLambertMaterial({ color: dark });

  // Heavier chassis read as tanks; speed reads as slimmer.
  const bulk = 0.8 + (unit.spec.maxHp - 110) / 160;
  const torso = new THREE.Mesh(new THREE.BoxGeometry(1.5 * bulk, 1.5, 1.1 * bulk), bodyMat);
  torso.position.y = 1.7;
  group.add(torso);

  const pelvis = new THREE.Mesh(new THREE.BoxGeometry(1.0 * bulk, 0.45, 0.8), darkMat);
  pelvis.position.y = 0.85;
  group.add(pelvis);

  const legGeo = new THREE.BoxGeometry(0.38, 0.85, 0.5);
  for (const side of [-1, 1]) {
    const leg = new THREE.Mesh(legGeo, darkMat);
    leg.position.set(side * 0.42 * bulk, 0.42, 0);
    group.add(leg);
  }

  const head = new THREE.Mesh(new THREE.BoxGeometry(0.7, 0.55, 0.7), darkMat);
  head.position.y = 2.75;
  group.add(head);
  const visor = new THREE.Mesh(
    new THREE.BoxGeometry(0.55, 0.16, 0.1),
    new THREE.MeshBasicMaterial({ color }),
  );
  visor.position.set(0, 2.78, 0.38);
  group.add(visor);

  const podGeo = new THREE.CylinderGeometry(0.28, 0.34, 0.8, 8);
  for (const side of [-1, 1]) {
    const pod = new THREE.Mesh(podGeo, bodyMat);
    pod.position.set(side * (0.95 * bulk + 0.15), 2.15, 0);
    group.add(pod);
  }

  const antenna = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 0.7, 5), darkMat);
  antenna.position.set(0.25, 3.3, -0.1);
  group.add(antenna);

  // Active-turn ground ring.
  const ringMat = new THREE.MeshBasicMaterial({
    color: 0xffffff,
    transparent: true,
    opacity: 0,
    side: THREE.DoubleSide,
  });
  const ring = new THREE.Mesh(new THREE.RingGeometry(1.35, 1.65, 28), ringMat);
  ring.rotation.x = -Math.PI / 2;
  ring.position.y = 0.03;
  group.add(ring);

  // Name plate (reuses the hub's procedural label texture).
  const plateTex = makeLabelTexture(unit.spec.name.split(' ')[0] ?? unit.spec.name, hue);
  const plate = new THREE.Mesh(
    new THREE.PlaneGeometry(2.4, 0.9),
    new THREE.MeshBasicMaterial({ map: plateTex, transparent: true, side: THREE.DoubleSide }),
  );
  plate.position.y = 4.0;
  group.add(plate);

  const home = slotPosition(unit.id);
  group.position.copy(home);
  const facing = unit.side === 0 ? Math.PI / 2 : -Math.PI / 2; // face the other team
  group.rotation.y = facing;

  return { group, bodyMat, ring, ringMat, home, facing };
}

export function buildBattleScene(units: readonly UnitState[]): BattleSceneParts {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x07060f);
  scene.fog = new THREE.Fog(0x0c0a1e, 60, 180);

  scene.add(new THREE.AmbientLight(0x46507a, 1.0));
  const key = new THREE.DirectionalLight(0xbfd0ff, 1.0);
  key.position.set(30, 60, -20);
  scene.add(key);
  const rim = new THREE.DirectionalLight(0xff66aa, 0.25);
  rim.position.set(-40, 25, 35);
  scene.add(rim);

  // Arena floor + glow border strips for each side.
  const floor = new THREE.Mesh(
    new THREE.CylinderGeometry(ARENA_HALF + 6, ARENA_HALF + 7, 0.6, 10),
    new THREE.MeshLambertMaterial({ color: 0x191c2c }),
  );
  floor.position.y = -0.3;
  scene.add(floor);

  const gridLines = new THREE.GridHelper(ARENA_HALF * 2, 8, 0x2c3354, 0x222842);
  gridLines.position.y = 0.01;
  scene.add(gridLines);

  for (const side of [-1, 1]) {
    const strip = new THREE.Mesh(
      new THREE.BoxGeometry(0.5, 0.12, ARENA_HALF * 2),
      new THREE.MeshBasicMaterial({ color: side < 0 ? 0x47e6ff : 0xff5470 }),
    );
    strip.position.set(side * (RANK_X + 3.2), 0.06, 0);
    scene.add(strip);
  }

  // Distant ring of pylons for depth (cheap, static).
  const pylonMat = new THREE.MeshLambertMaterial({ color: 0x232842 });
  const pylonGeo = new THREE.BoxGeometry(1.6, 9, 1.6);
  for (let i = 0; i < 12; i++) {
    const a = (i / 12) * Math.PI * 2;
    const p = new THREE.Mesh(pylonGeo, pylonMat);
    p.position.set(Math.cos(a) * (ARENA_HALF + 14), 4.5, Math.sin(a) * (ARENA_HALF + 14));
    scene.add(p);
  }

  const robots: RobotRig[] = [];
  for (const u of units) {
    const rig = buildRobot(u);
    scene.add(rig.group);
    robots.push(rig);
  }

  let entityCount = 0;
  scene.traverse(() => entityCount++);
  return { scene, robots, entityCount };
}
