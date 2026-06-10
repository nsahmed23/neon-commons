/**
 * Lake water: animated ShaderMaterial (vertex waves + moving surface
 * highlights). Time comes from the simulation clock so pause freezes
 * it; wave amplitude obeys the motion-effects setting. The shoreline
 * has REAL collision walls (added in HubMode from WORLD.lake).
 */

import * as THREE from 'three';
import { WORLD } from './WorldGeneration';

const VERT = /* glsl */ `
uniform float uTime;
uniform float uAmp;
varying vec2 vUvM;     // meters across the lake
varying float vViewDist;
varying float vWave;

void main() {
  vec3 p = position;
  float w1 = sin(p.x * 0.18 + uTime * 1.1);
  float w2 = sin(p.y * 0.23 - uTime * 0.8);
  float w3 = sin((p.x + p.y) * 0.09 + uTime * 0.5);
  vWave = (w1 + w2 + w3) / 3.0;
  p.z += vWave * uAmp;
  vUvM = p.xy;
  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  vViewDist = -mv.z;
  gl_Position = projectionMatrix * mv;
}
`;

const FRAG = /* glsl */ `
precision highp float;
uniform float uTime;
uniform vec3 uDeep;
uniform vec3 uShallow;
uniform vec3 uFogColor;
uniform float uFogNear;
uniform float uFogFar;
varying vec2 vUvM;
varying float vViewDist;
varying float vWave;

void main() {
  // Moving interference bands read as ripples/specular streaks.
  float band = sin(vUvM.x * 0.7 + uTime * 1.6) * sin(vUvM.y * 0.5 - uTime * 1.1);
  float sparkle = smoothstep(0.86, 1.0, band);
  vec3 color = mix(uDeep, uShallow, 0.5 + 0.5 * vWave);
  color += sparkle * vec3(0.35, 0.45, 0.55);
  float fogF = smoothstep(uFogNear, uFogFar, vViewDist);
  gl_FragColor = vec4(mix(color, uFogColor, fogF), 0.93);
}
`;

export class Water {
  readonly mesh: THREE.Mesh;
  private uniforms: {
    uTime: THREE.IUniform<number>;
    uAmp: THREE.IUniform<number>;
    uDeep: THREE.IUniform<THREE.Color>;
    uShallow: THREE.IUniform<THREE.Color>;
    uFogColor: THREE.IUniform<THREE.Color>;
    uFogNear: THREE.IUniform<number>;
    uFogFar: THREE.IUniform<number>;
  };

  constructor() {
    const L = WORLD.lake;
    const w = L.maxX - L.minX;
    const d = L.maxZ - L.minZ;
    const geo = new THREE.PlaneGeometry(w, d, 48, 48);

    this.uniforms = {
      uTime: { value: 0 },
      uAmp: { value: 0.12 },
      uDeep: { value: new THREE.Color(0x0a2435) },
      uShallow: { value: new THREE.Color(0x14506b) },
      uFogColor: { value: new THREE.Color(0x10142e) },
      uFogNear: { value: 120 },
      uFogFar: { value: 700 },
    };

    const mat = new THREE.ShaderMaterial({
      vertexShader: VERT,
      fragmentShader: FRAG,
      uniforms: this.uniforms as unknown as Record<string, THREE.IUniform>,
      transparent: true,
    });

    this.mesh = new THREE.Mesh(geo, mat);
    this.mesh.rotation.x = -Math.PI / 2;
    this.mesh.position.set((L.minX + L.maxX) / 2, WORLD.waterY, (L.minZ + L.maxZ) / 2);
    this.mesh.name = 'water';
  }

  /** dt source = simulation time, so pause freezes the lake. */
  update(simTime: number): void {
    this.uniforms.uTime.value = simTime;
  }

  setMotionEffects(enabled: boolean): void {
    this.uniforms.uAmp.value = enabled ? 0.12 : 0.0;
  }

  setFog(color: number, near: number, far: number): void {
    this.uniforms.uFogColor.value.setHex(color);
    this.uniforms.uFogNear.value = near;
    this.uniforms.uFogFar.value = far;
  }

  setNight(night: boolean): void {
    this.uniforms.uDeep.value.setHex(night ? 0x0a2435 : 0x1a5a7a);
    this.uniforms.uShallow.value.setHex(night ? 0x14506b : 0x3a98ab);
  }
}
