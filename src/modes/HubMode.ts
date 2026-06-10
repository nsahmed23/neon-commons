/**
 * The hub: first-person walking around Neon Commons. Owns the player
 * body (capsule vs the AABB collision grid, gravity vs the shared
 * terrain height function), the interact system (proximity to the five
 * mode pedestals + E), and footstep audio. No allocations in update():
 * all scratch state is preallocated.
 */

import type { GameBus } from '../core/EventBus';
import type { Input } from '../core/Input';
import type { CameraRig } from '../rendering/CameraRig';
import type { AudioSystem } from '../systems/Audio';
import { CollisionWorld, makeAABB } from '../world/Collision';
import {
  WORLD,
  terrainHeight,
  type WorldData,
} from '../world/WorldGeneration';
import type { Mode } from './Mode';

const PLAYER_RADIUS = 0.45;
const PLAYER_HEIGHT = 1.8;
const WALK_SPEED = 6;
const SPRINT_SPEED = 11;
const ACCEL = 40;
const GRAVITY = 22;
const JUMP_VELOCITY = 7.5;

export class HubMode implements Mode {
  readonly id = 'hub';
  readonly collision: CollisionWorld;

  // Player body (public for camera/minimap reads).
  x = 0;
  y = 0;
  z = 0;
  grounded = true;

  private vx = 0;
  private vy = 0;
  private vz = 0;
  private stepTimer = 0;
  private nearPedestal: { id: string; label: string } | null = null;
  private nearId = '';
  private active = false;

  constructor(
    private world: WorldData,
    private bus: GameBus,
    private input: Input,
    private rig: CameraRig,
    private audio: AudioSystem,
    private onPrompt: (text: string | null) => void,
  ) {
    this.collision = HubMode.buildCollision(world);
    this.respawn();
    this.input.onEdge('interact', () => this.tryInteract());
    this.input.onEdge('reset', () => {
      if (this.active) {
        this.respawn();
        this.bus.emit('toast', { text: 'Position reset to plaza spawn', kind: 'info' });
      }
    });
  }

  /** Static so tests could rebuild the same collision set if needed. */
  static buildCollision(world: WorldData): CollisionWorld {
    const c = new CollisionWorld(16);
    for (const b of world.buildings) {
      c.addBox(makeAABB(b.id, b.x, b.z, b.w, b.d, -2, b.h));
    }
    const t = world.tower;
    c.addBox(makeAABB('tower', t.x, t.z, t.w, t.d, -2, t.h));
    for (const p of world.props) {
      c.addBox(makeAABB(p.id, p.x, p.z, p.w, p.d, -2, p.h));
    }
    for (const p of world.pedestals) {
      c.addBox(makeAABB(`ped-${p.id}`, p.x, p.z, 2.4, 2.4, -2, 0.9));
    }
    // REAL water boundary: four walls hugging the lake rectangle.
    const L = WORLD.lake;
    const wallT = 2;
    const lw = L.maxX - L.minX;
    const ld = L.maxZ - L.minZ;
    c.addBox(makeAABB('lake-w', L.minX - wallT / 2, (L.minZ + L.maxZ) / 2, wallT, ld + wallT * 2, -8, 4));
    c.addBox(makeAABB('lake-e', L.maxX + wallT / 2, (L.minZ + L.maxZ) / 2, wallT, ld + wallT * 2, -8, 4));
    c.addBox(makeAABB('lake-n', (L.minX + L.maxX) / 2, L.minZ - wallT / 2, lw + wallT * 2, wallT, -8, 4));
    c.addBox(makeAABB('lake-s', (L.minX + L.maxX) / 2, L.maxZ + wallT / 2, lw + wallT * 2, wallT, -8, 4));
    // World rim.
    const H = WORLD.half;
    c.addBox(makeAABB('rim-w', -H, 0, 4, H * 2 + 8, -20, 60));
    c.addBox(makeAABB('rim-e', H, 0, 4, H * 2 + 8, -20, 60));
    c.addBox(makeAABB('rim-n', 0, -H, H * 2 + 8, 4, -20, 60));
    c.addBox(makeAABB('rim-s', 0, H, H * 2 + 8, 4, -20, 60));
    return c;
  }

  respawn(): void {
    this.x = this.world.spawn.x;
    this.z = this.world.spawn.z;
    this.y = this.groundAt(this.x, this.z);
    this.vx = this.vy = this.vz = 0;
    this.rig.yaw = 0; // face -Z, toward plaza center and tower
    this.rig.pitch = 0;
  }

  private groundAt(x: number, z: number): number {
    // terrainHeight is flat 0 across the city by construction.
    return terrainHeight(x, z, this.world.seed);
  }

  enter(): void {
    this.active = true;
  }

  exit(): void {
    this.active = false;
    this.onPrompt(null);
  }

  update(dt: number): void {
    if (!this.active) return;

    // Desired horizontal velocity from input, in camera-yaw space.
    const fwd = (this.input.isDown('forward') ? 1 : 0) - (this.input.isDown('back') ? 1 : 0);
    const strafe = (this.input.isDown('right') ? 1 : 0) - (this.input.isDown('left') ? 1 : 0);
    const speed = this.input.isDown('sprint') ? SPRINT_SPEED : WALK_SPEED;
    const sinY = Math.sin(this.rig.yaw);
    const cosY = Math.cos(this.rig.yaw);
    let tx = (-sinY * fwd + cosY * strafe);
    let tz = (-cosY * fwd - sinY * strafe);
    const len = Math.hypot(tx, tz);
    if (len > 1) {
      tx /= len;
      tz /= len;
    }
    tx *= speed;
    tz *= speed;

    // Accelerate toward target velocity.
    const blend = Math.min(1, ACCEL * dt / Math.max(speed, 1));
    this.vx += (tx - this.vx) * blend;
    this.vz += (tz - this.vz) * blend;

    // Vertical: gravity + jump.
    if (this.grounded && this.input.isDown('jump')) {
      this.vy = JUMP_VELOCITY;
      this.grounded = false;
      this.audio.blip(220, 0.06, 'sine');
    }
    this.vy -= GRAVITY * dt;

    // Integrate.
    this.x += this.vx * dt;
    this.z += this.vz * dt;
    this.y += this.vy * dt;

    // Ground from the shared terrain function (flat 0 in the city).
    const floor = this.groundAt(this.x, this.z);
    if (this.y <= floor) {
      this.y = floor;
      this.vy = 0;
      this.grounded = true;
    } else {
      this.grounded = false;
    }

    // Push out of buildings/props/lake walls (real AABB resolution).
    const res = this.collision.resolveCapsule(this.x, this.y, this.z, PLAYER_RADIUS, PLAYER_HEIGHT);
    if (res.collided) {
      this.x = res.x;
      this.z = res.z;
    }

    // Camera follows; bob scales with actual horizontal speed.
    const hSpeed = Math.hypot(this.vx, this.vz);
    this.rig.updateBob(hSpeed, this.grounded, dt);

    // Footsteps tied to real movement.
    if (this.grounded && hSpeed > 1.5) {
      this.stepTimer -= dt * hSpeed;
      if (this.stepTimer <= 0) {
        this.stepTimer = 3.4;
        this.audio.step();
      }
    }

    // Interact proximity: nearest pedestal within 4 m.
    let nearest: { id: string; label: string } | null = null;
    let bestD2 = 16;
    for (const p of this.world.pedestals) {
      const d2 = (p.x - this.x) ** 2 + (p.z - this.z) ** 2;
      if (d2 < bestD2) {
        bestD2 = d2;
        nearest = p;
      }
    }
    if ((nearest?.id ?? '') !== this.nearId) {
      this.nearId = nearest?.id ?? '';
      this.nearPedestal = nearest;
      this.onPrompt(nearest ? `[E] Dock at ${nearest.label} pedestal` : null);
      if (nearest) this.audio.hum(64, 0.5);
    }
  }

  private tryInteract(): void {
    if (!this.active || !this.nearPedestal) return;
    this.audio.blip(660, 0.1);
    this.bus.emit('interact', {
      targetId: this.nearPedestal.id,
      label: this.nearPedestal.label,
    });
  }
}
