/**
 * The window illusion: ONE InstancedMesh draws every building (and the
 * landmark tower) with a custom shader that procedurally paints a
 * window grid on each facade. No per-window geometry exists, yet each
 * window cell is individually addressed: a hash of (cell, facade,
 * building seed, day/night phase) decides whether it is lit and what
 * warm/cool tint it gets. Toggling night re-rolls the lit set and the
 * lit fraction, so the distribution genuinely changes.
 *
 * Cell metrics (2 m columns x 3 m floors) are the same constants
 * WorldGeneration uses to COUNT windows, so the overlay's "windows"
 * number describes exactly what the shader draws.
 */

import * as THREE from 'three';
import { WORLD, type BuildingData, type WorldData } from './WorldGeneration';

const TINTS: ReadonlyArray<[number, number, number]> = [
  [0.16, 0.17, 0.22],
  [0.20, 0.18, 0.17],
  [0.13, 0.15, 0.20],
  [0.18, 0.20, 0.23],
];

const VERT = /* glsl */ `
attribute vec3 aSize;
attribute float aSeed;
attribute float aTint;
varying vec3 vLocal;     // x,z in [-0.5,0.5], y in [0,1]
varying vec3 vNormalL;   // local-space normal (box faces)
varying vec3 vSize;
varying float vSeed;
varying float vTint;
varying float vViewDist;

void main() {
  vLocal = position;
  vNormalL = normal;
  vSize = aSize;
  vSeed = aSeed;
  vTint = aTint;
  vec4 world = instanceMatrix * vec4(position, 1.0);
  vec4 mv = viewMatrix * world;
  vViewDist = -mv.z;
  gl_Position = projectionMatrix * mv;
}
`;

const FRAG = /* glsl */ `
precision highp float;
varying vec3 vLocal;
varying vec3 vNormalL;
varying vec3 vSize;
varying float vSeed;
varying float vTint;
varying float vViewDist;

uniform float uLitFraction;
uniform float uPhase;      // 0 day, 1 night (re-rolls the lit set)
uniform vec3 uSunDir;
uniform vec3 uSunColor;
uniform vec3 uAmbient;
uniform vec3 uFogColor;
uniform float uFogNear;
uniform float uFogFar;
uniform float uWindowEmit; // emissive strength (night >> day)
uniform vec3 uTints[4];

float hash3(vec3 p) {
  return fract(sin(dot(p, vec3(127.1, 311.7, 74.7))) * 43758.5453123);
}

void main() {
  vec3 n = vNormalL;
  vec3 base = uTints[int(clamp(vTint, 0.0, 3.0) + 0.5)];

  // Simple lambert from the (local==world, buildings are axis-aligned) normal.
  float diff = max(dot(normalize(n), uSunDir), 0.0);
  vec3 lit = base * (uAmbient + uSunColor * diff);

  vec3 color = lit;

  if (abs(n.y) < 0.5) {
    // Facade: build the window grid in meters.
    float u = (abs(n.x) > 0.5) ? vLocal.z * vSize.z : vLocal.x * vSize.x;
    float v = vLocal.y * vSize.y;
    float faceId = n.x + n.z * 2.0 + 3.0;

    float cu = floor(u / ${WORLD.windowCellW.toFixed(1)});
    float cv = floor(v / ${WORLD.floorHeight.toFixed(1)});
    float fu = fract(u / ${WORLD.windowCellW.toFixed(1)});
    float fv = fract(v / ${WORLD.floorHeight.toFixed(1)});

    // Window rect inside the cell.
    float inWin = step(0.18, fu) * step(fu, 0.82) * step(0.30, fv) * step(fv, 0.78);
    // Distance fade: beyond ~180m windows blur into the facade.
    float fade = 1.0 - smoothstep(120.0, 220.0, vViewDist);

    if (inWin > 0.5 && cv >= 0.0) {
      float h = hash3(vec3(cu * 7.13 + faceId * 91.7, cv * 3.71, vSeed * 251.0 + uPhase * 17.0));
      if (h < uLitFraction) {
        // Lit interior: warm/cool mix per cell.
        float warm = hash3(vec3(cu, cv, vSeed * 97.0));
        vec3 winColor = mix(vec3(1.0, 0.78, 0.45), vec3(0.55, 0.85, 1.0), step(0.75, warm));
        float flick = 0.92 + 0.08 * hash3(vec3(cv, cu, vSeed));
        color = mix(lit, winColor * uWindowEmit * flick, fade);
      } else {
        // Dark glass: slightly bluer + darker than the wall.
        color = mix(lit, base * 0.35 + vec3(0.02, 0.03, 0.06), fade * 0.9);
      }
    }
  } else {
    color = lit * 0.8; // roof
  }

  float fogF = smoothstep(uFogNear, uFogFar, vViewDist);
  gl_FragColor = vec4(mix(color, uFogColor, fogF), 1.0);
}
`;

export interface FacadeUniforms {
  uLitFraction: THREE.IUniform<number>;
  uPhase: THREE.IUniform<number>;
  uSunDir: THREE.IUniform<THREE.Vector3>;
  uSunColor: THREE.IUniform<THREE.Color>;
  uAmbient: THREE.IUniform<THREE.Color>;
  uFogColor: THREE.IUniform<THREE.Color>;
  uFogNear: THREE.IUniform<number>;
  uFogFar: THREE.IUniform<number>;
  uWindowEmit: THREE.IUniform<number>;
  uTints: THREE.IUniform<THREE.Vector3[]>;
}

export class BuildingFacades {
  readonly mesh: THREE.InstancedMesh;
  readonly uniforms: FacadeUniforms;
  readonly instanceCount: number;

  constructor(world: WorldData) {
    const items: BuildingData[] = [
      ...world.buildings,
      {
        id: 'tower',
        x: world.tower.x,
        z: world.tower.z,
        w: world.tower.w,
        d: world.tower.d,
        h: world.tower.h,
        facadeSeed: 0.777,
        windowCount: 0,
        tint: 2,
      },
    ];
    this.instanceCount = items.length;

    const geo = new THREE.BoxGeometry(1, 1, 1);
    geo.translate(0, 0.5, 0); // base sits on the ground

    this.uniforms = {
      uLitFraction: { value: 0.55 },
      uPhase: { value: 1 },
      uSunDir: { value: new THREE.Vector3(0.45, 0.8, 0.3).normalize() },
      uSunColor: { value: new THREE.Color(0x8899ff) },
      uAmbient: { value: new THREE.Color(0x2a3050) },
      uFogColor: { value: new THREE.Color(0x10142e) },
      uFogNear: { value: 120 },
      uFogFar: { value: 700 },
      uWindowEmit: { value: 1.6 },
      uTints: { value: TINTS.map(([r, g, b]) => new THREE.Vector3(r, g, b)) },
    };

    const mat = new THREE.ShaderMaterial({
      vertexShader: VERT,
      fragmentShader: FRAG,
      uniforms: this.uniforms as unknown as Record<string, THREE.IUniform>,
    });

    this.mesh = new THREE.InstancedMesh(geo, mat, items.length);
    const m = new THREE.Matrix4();
    const sizes = new Float32Array(items.length * 3);
    const seeds = new Float32Array(items.length);
    const tints = new Float32Array(items.length);
    items.forEach((b, i) => {
      m.makeScale(b.w, b.h, b.d);
      m.setPosition(b.x, 0, b.z);
      this.mesh.setMatrixAt(i, m);
      sizes[i * 3] = b.w;
      sizes[i * 3 + 1] = b.h;
      sizes[i * 3 + 2] = b.d;
      seeds[i] = b.facadeSeed;
      tints[i] = b.tint;
    });
    geo.setAttribute('aSize', new THREE.InstancedBufferAttribute(sizes, 3));
    geo.setAttribute('aSeed', new THREE.InstancedBufferAttribute(seeds, 1));
    geo.setAttribute('aTint', new THREE.InstancedBufferAttribute(tints, 1));
    this.mesh.instanceMatrix.needsUpdate = true;
    this.mesh.frustumCulled = false; // one mesh spanning the city
  }

  /** Night: more windows lit, brighter; the lit SET also re-rolls. */
  setNight(night: boolean): void {
    this.uniforms.uLitFraction.value = night ? 0.55 : 0.07;
    this.uniforms.uPhase.value = night ? 1 : 0;
    this.uniforms.uWindowEmit.value = night ? 1.7 : 0.9;
    this.uniforms.uSunColor.value.setHex(night ? 0x55609a : 0xffeedd);
    this.uniforms.uAmbient.value.setHex(night ? 0x2a3050 : 0x8c97ad);
  }

  setFog(color: number, near: number, far: number): void {
    this.uniforms.uFogColor.value.setHex(color);
    this.uniforms.uFogNear.value = near;
    this.uniforms.uFogFar.value = far;
  }
}
