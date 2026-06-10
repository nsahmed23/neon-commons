/**
 * Heightfield terrain mesh built from the same pure terrainHeight()
 * the player-grounding code uses, so what you see is what you stand on.
 * Vertex colors by height/slope; no textures.
 */

import * as THREE from 'three';
import { WORLD, terrainHeight } from './WorldGeneration';

export function buildTerrain(seed: number): THREE.Mesh {
  const size = WORLD.half * 2;
  const segs = 160;
  const geo = new THREE.PlaneGeometry(size, size, segs, segs);
  geo.rotateX(-Math.PI / 2);

  const pos = geo.attributes['position'] as THREE.BufferAttribute;
  const colors = new Float32Array(pos.count * 3);
  const grass = new THREE.Color(0x2e4a2c);
  const rock = new THREE.Color(0x4a4a52);
  const sand = new THREE.Color(0x6b6248);
  const urban = new THREE.Color(0x23252e);
  const c = new THREE.Color();

  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i);
    const z = pos.getZ(i);
    const h = terrainHeight(x, z, seed);
    pos.setY(i, h);

    const inCity = Math.max(Math.abs(x), Math.abs(z)) < WORLD.cityHalf + 6;
    if (inCity) {
      c.copy(urban);
    } else if (h < WORLD.waterY + 0.6) {
      c.copy(sand);
    } else {
      c.lerpColors(grass, rock, Math.min(1, Math.max(0, (h - 1) / 6)));
    }
    colors[i * 3] = c.r;
    colors[i * 3 + 1] = c.g;
    colors[i * 3 + 2] = c.b;
  }
  geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  geo.computeVertexNormals();

  const mat = new THREE.MeshLambertMaterial({ vertexColors: true });
  const mesh = new THREE.Mesh(geo, mat);
  mesh.receiveShadow = true;
  mesh.name = 'terrain';
  return mesh;
}
