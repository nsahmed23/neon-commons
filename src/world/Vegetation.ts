/**
 * Instanced wilderness vegetation. Trees = two InstancedMeshes (trunk
 * cylinders + canopy cones); grass = one InstancedMesh of crossed
 * quads. Max counts are allocated once; the quality profile changes
 * the visible .count (cheap, no reallocation).
 */

import * as THREE from 'three';
import { terrainHeight, type WorldData } from './WorldGeneration';
import { Rng } from '../core/Rng';

export const GRASS_MAX = 4000;

export class Vegetation {
  readonly group = new THREE.Group();
  private trunks: THREE.InstancedMesh;
  private canopies: THREE.InstancedMesh;
  private grass: THREE.InstancedMesh;
  private readonly treeTotal: number;

  constructor(world: WorldData) {
    const seed = world.seed;
    this.treeTotal = world.trees.length;

    // Trees ---------------------------------------------------------
    const trunkGeo = new THREE.CylinderGeometry(0.18, 0.3, 1, 5);
    trunkGeo.translate(0, 0.5, 0);
    const canopyGeo = new THREE.ConeGeometry(1.4, 3.2, 6);
    canopyGeo.translate(0, 1.6, 0);
    const trunkMat = new THREE.MeshLambertMaterial({ color: 0x3d2c1e });
    const canopyMat = new THREE.MeshLambertMaterial({ color: 0x1f3d26 });

    this.trunks = new THREE.InstancedMesh(trunkGeo, trunkMat, this.treeTotal);
    this.canopies = new THREE.InstancedMesh(canopyGeo, canopyMat, this.treeTotal);
    const m = new THREE.Matrix4();
    const q = new THREE.Quaternion();
    const up = new THREE.Vector3(0, 1, 0);
    const pos = new THREE.Vector3();
    const scl = new THREE.Vector3();
    world.trees.forEach((t, i) => {
      const y = terrainHeight(t.x, t.z, seed);
      q.setFromAxisAngle(up, (t.x * 13.37 + t.z * 7.77) % Math.PI);
      pos.set(t.x, y - 0.1, t.z);
      scl.set(t.scale, t.scale * (2.2 + (i % 5) * 0.35), t.scale);
      m.compose(pos, q, scl);
      this.trunks.setMatrixAt(i, m);
      this.canopies.setMatrixAt(i, m);
    });
    this.trunks.castShadow = true;
    this.canopies.castShadow = true;
    this.group.add(this.trunks, this.canopies);

    // Grass ---------------------------------------------------------
    const blade = new THREE.PlaneGeometry(0.5, 0.5);
    blade.translate(0, 0.25, 0);
    const grassMat = new THREE.MeshLambertMaterial({
      color: 0x35582f,
      side: THREE.DoubleSide,
    });
    this.grass = new THREE.InstancedMesh(blade, grassMat, GRASS_MAX);
    const rng = new Rng(seed).fork('grass');
    let placed = 0;
    let guard = 0;
    while (placed < GRASS_MAX && guard < GRASS_MAX * 4) {
      guard++;
      // Cluster grass around tree positions for believable meadows.
      const t = world.trees[rng.int(0, world.trees.length - 1)];
      if (!t) break;
      const x = t.x + rng.range(-9, 9);
      const z = t.z + rng.range(-9, 9);
      const y = terrainHeight(x, z, seed);
      if (y < -0.4) continue;
      pos.set(x, y, z);
      q.setFromAxisAngle(up, rng.range(0, Math.PI));
      const s = rng.range(0.6, 1.3);
      scl.set(s, s, s);
      m.compose(pos, q, scl);
      this.grass.setMatrixAt(placed, m);
      placed++;
    }
    this.grass.count = placed;
    this.group.add(this.grass);
    this.group.name = 'vegetation';
  }

  /** Quality profile hook: show a fraction of trees / N grass blades. */
  applyProfile(treeFraction: number, grassCount: number): void {
    const visible = Math.floor(this.treeTotal * treeFraction);
    this.trunks.count = visible;
    this.canopies.count = visible;
    this.grass.count = Math.min(GRASS_MAX, grassCount);
  }

  get activeInstances(): number {
    return this.trunks.count + this.canopies.count + this.grass.count;
  }
}
