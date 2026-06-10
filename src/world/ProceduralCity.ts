/**
 * Assembles the city from WorldData: building facades (one instanced
 * draw via BuildingFacades), street lamps, animated neon signs,
 * plaza props, the five mode pedestals with procedural canvas labels,
 * ground planes, and a bounded stress-test prop pool.
 */

import * as THREE from 'three';
import {
  WORLD,
  type PedestalData,
  type WorldData,
} from './WorldGeneration';
import { BuildingFacades } from './InteriorWindows';
import {
  asphaltMaterial,
  lampHeadMaterial,
  lampPoleMaterial,
  makeLabelTexture,
  pedestalMaterial,
  pedestalRingMaterial,
  plazaMaterial,
  propMaterial,
} from '../rendering/Materials';
import { Rng } from '../core/Rng';

export const STRESS_MAX = 3000;

const NEON_VERT = /* glsl */ `
attribute float aHue;
varying float vHue;
varying vec2 vUv;
void main() {
  vHue = aHue;
  vUv = uv;
  gl_Position = projectionMatrix * viewMatrix * instanceMatrix * vec4(position, 1.0);
}
`;

const NEON_FRAG = /* glsl */ `
precision highp float;
uniform float uTime;
uniform float uNight;
varying float vHue;
varying vec2 vUv;

vec3 hsl2rgb(float h, float s, float l) {
  vec3 rgb = clamp(abs(mod(h * 6.0 + vec3(0.0, 4.0, 2.0), 6.0) - 3.0) - 1.0, 0.0, 1.0);
  return l + s * (rgb - 0.5) * (1.0 - abs(2.0 * l - 1.0));
}

void main() {
  // Animated glyph bars: a few vertical strips that pulse per-sign.
  float strip = step(0.12, fract(vUv.x * 5.0 + vHue * 9.0));
  float border = step(0.06, vUv.x) * step(vUv.x, 0.94) * step(0.12, vUv.y) * step(vUv.y, 0.88);
  float flicker = 0.75 + 0.25 * sin(uTime * (2.0 + vHue * 6.0) + vHue * 40.0);
  float bright = mix(0.35, 1.0, uNight) * flicker;
  vec3 c = hsl2rgb(vHue, 0.95, 0.6) * bright;
  gl_FragColor = vec4(c * border * (0.35 + 0.65 * strip), 1.0);
}
`;

export class ProceduralCity {
  readonly group = new THREE.Group();
  readonly facades: BuildingFacades;
  readonly pedestalAnchors: Array<{ data: PedestalData; ring: THREE.Mesh }> = [];
  private neonUniforms = { uTime: { value: 0 }, uNight: { value: 1 } };
  private lampHeads: THREE.InstancedMesh;
  private stressMesh: THREE.InstancedMesh;
  private stressActive = 0;
  private readonly worldSeed: number;
  private staticInstanceCount = 0;

  constructor(world: WorldData) {
    this.worldSeed = world.seed;
    this.group.name = 'city';

    // Buildings + tower: single instanced draw with the window shader.
    this.facades = new BuildingFacades(world);
    this.group.add(this.facades.mesh);

    // City ground + plaza disc.
    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry((WORLD.cityHalf + 8) * 2, (WORLD.cityHalf + 8) * 2),
      asphaltMaterial(),
    );
    ground.rotation.x = -Math.PI / 2;
    ground.position.y = 0.02;
    ground.receiveShadow = true;
    this.group.add(ground);

    const plaza = new THREE.Mesh(new THREE.CircleGeometry(22, 40), plazaMaterial());
    plaza.rotation.x = -Math.PI / 2;
    plaza.position.set(0, 0.04, 0);
    plaza.receiveShadow = true;
    this.group.add(plaza);

    // Street lamps: instanced poles + glowing heads.
    const poleGeo = new THREE.CylinderGeometry(0.08, 0.12, 5, 6);
    poleGeo.translate(0, 2.5, 0);
    const headGeo = new THREE.SphereGeometry(0.28, 8, 6);
    const poles = new THREE.InstancedMesh(poleGeo, lampPoleMaterial(), world.lamps.length);
    this.lampHeads = new THREE.InstancedMesh(headGeo, lampHeadMaterial(), world.lamps.length);
    const m = new THREE.Matrix4();
    world.lamps.forEach((l, i) => {
      m.identity().setPosition(l.x, 0, l.z);
      poles.setMatrixAt(i, m);
      m.identity().setPosition(l.x, 5.1, l.z);
      this.lampHeads.setMatrixAt(i, m);
    });
    this.group.add(poles, this.lampHeads);

    // Neon signs: instanced planes with the animated shader.
    if (world.signs.length > 0) {
      const signGeo = new THREE.PlaneGeometry(1, 1);
      const hues = new Float32Array(world.signs.length);
      const signMat = new THREE.ShaderMaterial({
        vertexShader: NEON_VERT,
        fragmentShader: NEON_FRAG,
        uniforms: this.neonUniforms,
        side: THREE.DoubleSide,
      });
      const signs = new THREE.InstancedMesh(signGeo, signMat, world.signs.length);
      const q = new THREE.Quaternion();
      const up = new THREE.Vector3(0, 1, 0);
      const pos = new THREE.Vector3();
      const scl = new THREE.Vector3();
      world.signs.forEach((s, i) => {
        q.setFromAxisAngle(up, s.rot);
        pos.set(s.x, s.y, s.z);
        scl.set(s.w, s.h, 1);
        m.compose(pos, q, scl);
        signs.setMatrixAt(i, m);
        hues[i] = s.hue;
      });
      signGeo.setAttribute('aHue', new THREE.InstancedBufferAttribute(hues, 1));
      signs.frustumCulled = false;
      this.group.add(signs);
    }

    // Plaza props (crates) — these have matching collision AABBs.
    const propGeo = new THREE.BoxGeometry(1, 1, 1);
    propGeo.translate(0, 0.5, 0);
    const props = new THREE.InstancedMesh(propGeo, propMaterial(), world.props.length);
    world.props.forEach((p, i) => {
      m.makeScale(p.w, p.h, p.d);
      m.setPosition(p.x, 0, p.z);
      props.setMatrixAt(i, m);
    });
    props.castShadow = true;
    this.group.add(props);

    // Mode pedestals: base + glow ring + floating label.
    const baseGeo = new THREE.CylinderGeometry(1.1, 1.4, 0.9, 14);
    const ringGeo = new THREE.TorusGeometry(0.85, 0.09, 8, 24);
    for (const p of world.pedestals) {
      const base = new THREE.Mesh(baseGeo, pedestalMaterial());
      base.position.set(p.x, 0.45, p.z);
      const ring = new THREE.Mesh(ringGeo, pedestalRingMaterial(p.hue));
      ring.rotation.x = Math.PI / 2;
      ring.position.set(p.x, 1.0, p.z);
      const label = new THREE.Mesh(
        new THREE.PlaneGeometry(2.6, 0.975),
        new THREE.MeshBasicMaterial({
          map: makeLabelTexture(p.label, p.hue),
          transparent: true,
          side: THREE.DoubleSide,
        }),
      );
      label.position.set(p.x, 2.3, p.z);
      label.lookAt(world.spawn.x, 2.3, world.spawn.z); // readable from spawn
      this.group.add(base, ring, label);
      this.pedestalAnchors.push({ data: p, ring });
    }

    // Tower beacon: small glowing tip.
    const beacon = new THREE.Mesh(
      new THREE.SphereGeometry(1.2, 10, 8),
      new THREE.MeshBasicMaterial({ color: 0xff4d6d }),
    );
    beacon.position.set(world.tower.x, world.tower.h + 1.5, world.tower.z);
    this.group.add(beacon);

    // Stress-test pool: allocated once, count starts at 0 (bounded).
    const stressGeo = new THREE.TetrahedronGeometry(0.5);
    this.stressMesh = new THREE.InstancedMesh(
      stressGeo,
      new THREE.MeshLambertMaterial({ color: 0x9a4dff }),
      STRESS_MAX,
    );
    this.stressMesh.count = 0;
    this.stressMesh.frustumCulled = false;
    this.group.add(this.stressMesh);

    this.staticInstanceCount =
      this.facades.instanceCount +
      world.lamps.length * 2 +
      world.signs.length +
      world.props.length +
      world.pedestals.length * 3 +
      2; // beacon + ground bits

    // Pre-fill stress matrices ONCE (not in the render loop).
    const rng = new Rng(world.seed).fork('stress');
    const q = new THREE.Quaternion();
    const axis = new THREE.Vector3();
    const pos = new THREE.Vector3();
    const scl = new THREE.Vector3(1, 1, 1);
    for (let i = 0; i < STRESS_MAX; i++) {
      axis.set(rng.next() - 0.5, rng.next(), rng.next() - 0.5).normalize();
      q.setFromAxisAngle(axis, rng.range(0, Math.PI * 2));
      pos.set(rng.range(-100, 100), rng.range(2, 50), rng.range(-100, 100));
      m.compose(pos, q, scl);
      this.stressMesh.setMatrixAt(i, m);
    }
    this.stressMesh.instanceMatrix.needsUpdate = true;
  }

  /** simulation-time driven animation (freezes on pause) */
  update(simTime: number, playerX: number, playerZ: number): void {
    this.neonUniforms.uTime.value = simTime;
    // Pulse the ring of the nearest pedestal: cheap scalar work only.
    for (const { data, ring } of this.pedestalAnchors) {
      const d2 = (data.x - playerX) ** 2 + (data.z - playerZ) ** 2;
      const near = d2 < 16;
      const s = near ? 1 + 0.18 * Math.sin(simTime * 5) : 1;
      ring.scale.set(s, s, s);
      ring.position.y = 1.0 + (near ? 0.12 * Math.sin(simTime * 2.4) : 0);
    }
  }

  setNight(night: boolean): void {
    this.facades.setNight(night);
    this.neonUniforms.uNight.value = night ? 1 : 0.25;
    (this.lampHeads.material as THREE.MeshBasicMaterial).color.setHex(
      night ? 0xffd9a0 : 0x6a6a72,
    );
  }

  /** Stress test: raise the instanced count (bounded by STRESS_MAX). */
  setStressCount(count: number): number {
    this.stressActive = Math.max(0, Math.min(STRESS_MAX, count));
    this.stressMesh.count = this.stressActive;
    return this.stressActive;
  }

  get stressCount(): number {
    return this.stressActive;
  }

  get activeInstances(): number {
    return this.staticInstanceCount + this.stressActive;
  }

  get seed(): number {
    return this.worldSeed;
  }
}
