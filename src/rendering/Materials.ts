/**
 * Shared simple materials + procedural canvas label textures.
 * All procedural; no asset files.
 */

import * as THREE from 'three';

export function asphaltMaterial(): THREE.MeshLambertMaterial {
  return new THREE.MeshLambertMaterial({ color: 0x1b1d26 });
}

export function plazaMaterial(): THREE.MeshLambertMaterial {
  return new THREE.MeshLambertMaterial({ color: 0x2a2d3c });
}

export function lampPoleMaterial(): THREE.MeshLambertMaterial {
  return new THREE.MeshLambertMaterial({ color: 0x33384a });
}

export function lampHeadMaterial(): THREE.MeshBasicMaterial {
  // Basic (unlit) so the head glows regardless of scene lights.
  return new THREE.MeshBasicMaterial({ color: 0xffd9a0 });
}

export function propMaterial(): THREE.MeshLambertMaterial {
  return new THREE.MeshLambertMaterial({ color: 0x4a4338 });
}

export function pedestalMaterial(): THREE.MeshLambertMaterial {
  return new THREE.MeshLambertMaterial({ color: 0x262b3d });
}

export function pedestalRingMaterial(hue: number): THREE.MeshBasicMaterial {
  const c = new THREE.Color().setHSL(hue, 0.9, 0.6);
  return new THREE.MeshBasicMaterial({ color: c });
}

/**
 * Static decorative pylon ring shared by the battle and board arenas.
 * Stage G optimization: one InstancedMesh instead of N meshes (12 + 10
 * draw calls became 2 across the two scenes). Matrices are written once
 * at build time; the ring never animates.
 */
export function makePylonRing(
  geo: THREE.BoxGeometry,
  count: number,
  radius: number,
  y: number,
): THREE.InstancedMesh {
  const mat = new THREE.MeshLambertMaterial({ color: 0x232842 });
  const mesh = new THREE.InstancedMesh(geo, mat, count);
  const m = new THREE.Matrix4();
  for (let i = 0; i < count; i++) {
    const a = (i / count) * Math.PI * 2;
    m.makeTranslation(Math.cos(a) * radius, y, Math.sin(a) * radius);
    mesh.setMatrixAt(i, m);
  }
  mesh.instanceMatrix.needsUpdate = true;
  return mesh;
}

/**
 * Render a text label to a canvas texture (procedural, generated once
 * per pedestal at world build, never in the render loop).
 */
export function makeLabelTexture(text: string, hue: number): THREE.CanvasTexture {
  const canvas = document.createElement('canvas');
  canvas.width = 256;
  canvas.height = 96;
  const g = canvas.getContext('2d');
  if (g) {
    g.fillStyle = 'rgba(8, 10, 24, 0.82)';
    g.fillRect(0, 0, 256, 96);
    const c = new THREE.Color().setHSL(hue, 0.9, 0.65);
    g.strokeStyle = `#${c.getHexString()}`;
    g.lineWidth = 5;
    g.strokeRect(5, 5, 246, 86);
    g.fillStyle = `#${c.getHexString()}`;
    g.font = 'bold 44px monospace';
    g.textAlign = 'center';
    g.textBaseline = 'middle';
    g.fillText(text.toUpperCase(), 128, 50);
  }
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}
