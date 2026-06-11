/**
 * Flight mode: a third-person hover-drone run over the EXISTING hub
 * city (this mode renders the hub scene with its own chase camera; the
 * payoff shot is flying over the Stage A skyline). All decisions live
 * in the pure modules under src/systems/flight (FlightModel / Rings /
 * Projectiles / DroneAI / Scoring); this class wires them to input,
 * audio, HUD, and the Three.js group it adds to the hub scene.
 *
 * Lifecycle: briefing -> active -> ending -> results -> hub. Score,
 * results breakdown and every callout toast derive from the typed
 * FlightEvent stream (anti-faking clause); camera shake respects the
 * motion-effects setting (reduced-motion rule). The fixed-step update
 * allocates nothing: targets, inputs and scratch vectors are
 * preallocated.
 */

import * as THREE from 'three';
import type { GameBus } from '../core/EventBus';
import type { Input } from '../core/Input';
import type { AudioSystem } from '../systems/Audio';
import {
  BOSS,
  ENEMY,
  createBoss,
  createEnemy,
  damageBoss,
  damageEnemy,
  stepBoss,
  stepEnemy,
  type BossState,
  type EnemyDrone,
} from '../systems/flight/DroneAI';
import {
  FLIGHT,
  createDrone,
  createFlightInput,
  droneForwardSpeed,
  resetDrone,
  stepDrone,
} from '../systems/flight/FlightModel';
import {
  PROJECTILE,
  collideProjectiles,
  createPool,
  spawnProjectile,
  stepProjectiles,
  type HitTarget,
  type ProjectileOwner,
} from '../systems/flight/Projectiles';
import { RingTracker, generateCourse, type CourseData, type Ring } from '../systems/flight/Rings';
import {
  applyFlightEvent,
  createScore,
  describeFlightEvent,
  scoreBreakdown,
  totalScore,
  type FlightEvent,
} from '../systems/flight/Scoring';
import { CollisionWorld, makeAABB } from '../world/Collision';
import { terrainHeight, type WorldData } from '../world/WorldGeneration';
import { FlightHUD } from '../ui/FlightHUD';
import {
  RING_FUTURE_COLOR,
  RING_NEXT_COLOR,
  RING_PASSED_COLOR,
  buildFlightScene,
  type FlightSceneParts,
} from './flight/FlightScene';
import type { Mode } from './Mode';

const PLAYER_MAX_HP = 100;
const PLAYER_FIRE_INTERVAL = 0.16;
const PLAYER_HIT_RADIUS = 1.5;
const ENDING_SECONDS = 2.2;
const SHAKE_SECONDS = 0.45;
const PLAYER_ID = 999;
const BOSS_ID = 500;
const MOUSE_LOOK_RATE = 0.0022;
const PITCH_LIMIT = 0.9;
/** terrain safety floor above the shared height function, meters */
const GROUND_CLEARANCE = 2.5;

type Phase = 'briefing' | 'active' | 'ending' | 'results';

export interface FlightModeDeps {
  parent: HTMLElement;
  bus: GameBus;
  input: Input;
  audio: AudioSystem;
  /** the hub scene: flight plays inside the city you walk in */
  scene: THREE.Scene;
  world: WorldData;
  seed: number;
  exitToHub: () => void;
  setLockWanted: (wanted: boolean) => void;
  /** motion-effects setting (reduced motion disables camera shake) */
  getMotionEffects: () => boolean;
}

export class FlightMode implements Mode {
  readonly id = 'flight';
  readonly camera: THREE.PerspectiveCamera;
  readonly course: CourseData;

  get entityCount(): number {
    return this.parts.entityCount;
  }

  private parts: FlightSceneParts;
  private hud: FlightHUD;
  private collision: CollisionWorld;
  private active = false;
  private phase: Phase = 'briefing';
  private won = false;
  private endingTimer = 0;

  // Player.
  private player = createDrone(0, 30, 0, 0);
  private flightInput = createFlightInput();
  private camPitch = 0;
  private hp = PLAYER_MAX_HP;
  private fireTimer = 0;
  private fireHeld = false;
  private shakeTimer = 0;

  // Course + combat.
  private tracker: RingTracker;
  private score = createScore();
  private enemies: EnemyDrone[] = [];
  private boss: BossState;
  private pool = createPool();
  private simTime = 0;

  // Preallocated scratch (zero allocations in update/frame).
  private targetSlots: HitTarget[] = [];
  private targets: HitTarget[] = [];
  private onHit = (targetId: number, damage: number, owner: ProjectileOwner): void =>
    this.resolveHit(targetId, damage, owner);
  private camTarget = new THREE.Vector3();
  private lookDir = new THREE.Vector3();
  private boltMatrix = new THREE.Matrix4();
  private boltColorPlayer = new THREE.Color(0x9ef7ff);
  private boltColorEnemy = new THREE.Color(0xff5470);

  constructor(private deps: FlightModeDeps) {
    this.course = generateCourse(deps.seed, deps.world);
    this.parts = buildFlightScene(this.course);
    this.tracker = new RingTracker(this.course.rings);
    this.boss = createBoss(this.course.bossArena.x, this.course.bossArena.y, this.course.bossArena.z);
    this.camera = new THREE.PerspectiveCamera(74, innerWidth / innerHeight, 0.1, 1200);
    window.addEventListener('resize', () => {
      this.camera.aspect = innerWidth / innerHeight;
      this.camera.updateProjectionMatrix();
    });

    // Real building collision for the drone, from the same WorldData
    // the hub renders (buildings + tower; the sky needs no lake walls).
    this.collision = new CollisionWorld(16);
    for (const b of deps.world.buildings) {
      this.collision.addBox(makeAABB(b.id, b.x, b.z, b.w, b.d, -2, b.h));
    }
    const t = deps.world.tower;
    this.collision.addBox(makeAABB('tower', t.x, t.z, t.w, t.d, -2, t.h));

    // 4 sentries patrol rings 2/4/6/8; 2 escort adds guard the arena.
    for (let i = 0; i < 4; i++) {
      const ring = this.course.rings[2 + i * 2] as Ring;
      this.enemies.push(createEnemy(i, ring.x, ring.y + 6, ring.z));
    }
    const arena = this.course.bossArena;
    this.enemies.push(createEnemy(100, arena.x - 14, arena.y, arena.z - 14));
    this.enemies.push(createEnemy(101, arena.x + 14, arena.y, arena.z + 14));

    for (let i = 0; i < 1 + this.enemies.length + 1; i++) {
      this.targetSlots.push({ id: 0, x: 0, y: 0, z: 0, radius: 1, team: 0 });
    }

    this.hud = new FlightHUD(deps.parent, {
      onLaunch: () => this.launch(),
      onRetry: () => this.launch(),
      onExitToHub: () => this.deps.exitToHub(),
    });

    this.deps.input.onEdge('reset', () => {
      if (this.active && this.phase === 'active') this.respawn();
    });
    this.deps.input.onEdge('escape', () => {
      if (this.active) this.deps.exitToHub();
    });
    window.addEventListener('mousedown', (e) => {
      if (this.active && e.button === 0) this.fireHeld = true;
    });
    window.addEventListener('mouseup', (e) => {
      if (e.button === 0) this.fireHeld = false;
    });
  }

  // ---- Mode lifecycle --------------------------------------------------

  enter(): void {
    this.active = true;
    this.phase = 'briefing';
    this.deps.scene.add(this.parts.group);
    this.deps.setLockWanted(false);
    this.hud.setVisible(true);
    this.hud.showBriefing();
    this.resetRun();
    this.snapCamera();
    this.deps.bus.emit('toast', {
      text: `Skyline Run · ${this.course.rings.length} rings · seed ${this.deps.seed}`,
      kind: 'info',
    });
  }

  exit(): void {
    this.active = false;
    this.phase = 'briefing';
    this.fireHeld = false;
    this.deps.scene.remove(this.parts.group);
    this.hud.setVisible(false);
    this.deps.audio.engineStop();
    this.deps.setLockWanted(true);
  }

  /** Mouse look while flying (routed from the App frame loop). */
  applyLook(dx: number, dy: number): void {
    if (this.phase !== 'active') return;
    this.player.yaw -= dx * MOUSE_LOOK_RATE;
    this.camPitch = Math.max(-PITCH_LIMIT, Math.min(PITCH_LIMIT, this.camPitch - dy * MOUSE_LOOK_RATE));
  }

  // ---- Run lifecycle -----------------------------------------------------

  private resetRun(): void {
    resetDrone(this.player, this.course.start.x, this.course.start.y, this.course.start.z, this.course.start.yaw);
    this.camPitch = 0;
    this.hp = PLAYER_MAX_HP;
    this.fireTimer = 0;
    this.shakeTimer = 0;
    this.simTime = 0;
    this.won = false;
    this.tracker = new RingTracker(this.course.rings);
    this.score = createScore();
    this.pool = createPool();
    this.enemies.length = 0;
    for (let i = 0; i < 4; i++) {
      const ring = this.course.rings[2 + i * 2] as Ring;
      this.enemies.push(createEnemy(i, ring.x, ring.y + 6, ring.z));
    }
    const arena = this.course.bossArena;
    this.enemies.push(createEnemy(100, arena.x - 14, arena.y, arena.z - 14));
    this.enemies.push(createEnemy(101, arena.x + 14, arena.y, arena.z + 14));
    this.boss = createBoss(arena.x, arena.y, arena.z);
  }

  private launch(): void {
    this.resetRun();
    this.phase = 'active';
    this.hud.hidePanels();
    this.deps.setLockWanted(true);
    this.deps.audio.engineStart();
    this.deps.bus.emit('toast', {
      text: 'Launch! Thread the rings in order — sentries are live.',
      kind: 'success',
    });
  }

  private respawn(): void {
    const anchor =
      this.tracker.lastPassed >= 0
        ? (this.course.rings[this.tracker.lastPassed] as Ring)
        : { x: this.course.start.x, y: this.course.start.y, z: this.course.start.z };
    resetDrone(this.player, anchor.x, anchor.y, anchor.z, this.player.yaw);
    this.deps.bus.emit('toast', { text: 'Respawned at the last ring', kind: 'warn' });
  }

  private endRun(won: boolean): void {
    this.won = won;
    this.phase = 'ending';
    this.endingTimer = ENDING_SECONDS;
  }

  private showResults(): void {
    this.phase = 'results';
    this.deps.audio.engineStop();
    this.deps.setLockWanted(false);
    this.hud.showResults(this.won, scoreBreakdown(this.score), totalScore(this.score));
  }

  // ---- Events (the anti-faking seam) --------------------------------------

  private emit(ev: FlightEvent): void {
    applyFlightEvent(this.score, ev);
    const text = describeFlightEvent(ev);
    if (text) {
      this.deps.bus.emit('toast', {
        text,
        kind: ev.kind === 'player-hit' || ev.kind === 'player-down' ? 'warn' : 'info',
      });
    }
  }

  // ---- Fixed-step simulation ----------------------------------------------

  update(dt: number): void {
    if (!this.active) return;
    if (this.phase === 'ending') {
      this.endingTimer -= dt;
      this.stepWorld(dt, false);
      if (this.endingTimer <= 0) this.showResults();
      return;
    }
    if (this.phase !== 'active') return;
    this.stepWorld(dt, true);
  }

  private stepWorld(dt: number, playerControl: boolean): void {
    this.simTime += dt;
    this.shakeTimer = Math.max(0, this.shakeTimer - dt);
    const input = this.deps.input;
    const fi = this.flightInput;
    if (playerControl) {
      fi.thrust = (input.isDown('forward') ? 1 : 0) - (input.isDown('back') ? 1 : 0);
      fi.strafe = (input.isDown('right') ? 1 : 0) - (input.isDown('left') ? 1 : 0);
      fi.lift = (input.isDown('jump') ? 1 : 0) - (input.isDown('sprint') ? 1 : 0);
      fi.yaw = 0;
    } else {
      fi.thrust = 0;
      fi.strafe = 0;
      fi.lift = 0;
      fi.yaw = 0;
    }
    stepDrone(this.player, fi, dt);

    // Terrain floor (shared height function) + real building push-out.
    const p = this.player;
    const floor = terrainHeight(p.x, p.z, this.deps.world.seed) + GROUND_CLEARANCE;
    if (p.y < floor) {
      p.y = floor;
      if (p.vy < 0) p.vy = 0;
    }
    const res = this.collision.resolveCapsule(p.x, p.y - 0.6, p.z, 1.2, 1.2);
    if (res.collided) {
      p.x = res.x;
      p.z = res.z;
    }

    // Ordered rings (real sphere detection -> real events).
    if (playerControl && this.tracker.update(p.x, p.y, p.z)) {
      this.deps.audio.blip(660, 0.09, 'triangle');
      this.emit({ kind: 'ring-pass', index: this.tracker.lastPassed, total: this.tracker.total });
      if (this.tracker.completed) this.emit({ kind: 'course-complete' });
    }

    // Player fire along the real aim direction.
    this.fireTimer -= dt;
    const wantFire = this.fireHeld || input.isDown('fire');
    if (playerControl && wantFire && this.fireTimer <= 0) {
      this.fireTimer = PLAYER_FIRE_INTERVAL;
      const cp = Math.cos(this.camPitch);
      const dx = Math.sin(p.yaw) * cp;
      const dy = Math.sin(this.camPitch);
      const dz = Math.cos(p.yaw) * cp;
      const slot = spawnProjectile(
        this.pool, 0,
        p.x + dx * 2.2, p.y + dy * 2.2, p.z + dz * 2.2,
        dx * PROJECTILE.playerSpeed, dy * PROJECTILE.playerSpeed, dz * PROJECTILE.playerSpeed,
        PROJECTILE.playerDamage,
      );
      if (slot >= 0) {
        this.emit({ kind: 'shot-fired', by: 'player' });
        this.deps.audio.blip(990, 0.04, 'sawtooth');
      }
    }

    // Enemies (sentries + escorts share the same state machine).
    for (const e of this.enemies) {
      stepEnemy(e, p.x, p.y, p.z, this.simTime, dt);
      if (e.transitioned) this.emit({ kind: 'drone-state', droneId: e.id, to: e.transitioned });
      if (e.fired && playerControl) {
        this.fireEnemyBolt(e.x, e.y, e.z, p.x, p.y, p.z);
        this.emit({ kind: 'shot-fired', by: 'enemy' });
      }
    }

    // Boss engages once the course is complete.
    let addsAlive = 0;
    for (const e of this.enemies) {
      if (e.id >= 100 && e.alive) addsAlive++;
    }
    if (this.tracker.completed && this.boss.phase !== 'down') {
      stepBoss(this.boss, addsAlive, p.x, p.y, p.z, this.simTime, dt);
      if (this.boss.transitioned) this.emit({ kind: 'boss-phase', phase: this.boss.transitioned });
      if (this.boss.fired && playerControl) {
        const yawTo = Math.atan2(p.x - this.boss.x, p.z - this.boss.z);
        const n = this.boss.fireCount;
        for (let k = 0; k < n; k++) {
          const off = n === 1 ? 0 : (k - (n - 1) / 2) * BOSS.spreadAngle;
          const a = yawTo + off;
          const dh = Math.max(1e-6, Math.hypot(p.x - this.boss.x, p.z - this.boss.z));
          const vy = ((p.y - this.boss.y) / dh) * PROJECTILE.enemySpeed * 0.5;
          spawnProjectile(
            this.pool, 1, this.boss.x, this.boss.y, this.boss.z,
            Math.sin(a) * PROJECTILE.enemySpeed, vy, Math.cos(a) * PROJECTILE.enemySpeed,
            PROJECTILE.enemyDamage,
          );
          this.emit({ kind: 'shot-fired', by: 'boss' });
        }
      }
    }

    // Projectiles: integrate, then swept-collide against live targets.
    stepProjectiles(this.pool, dt);
    this.targets.length = 0;
    let slotIdx = 0;
    const ps = this.targetSlots[slotIdx++] as HitTarget;
    ps.id = PLAYER_ID;
    ps.x = p.x;
    ps.y = p.y;
    ps.z = p.z;
    ps.radius = PLAYER_HIT_RADIUS;
    ps.team = 0;
    this.targets.push(ps);
    for (const e of this.enemies) {
      if (!e.alive) continue;
      const s = this.targetSlots[slotIdx++] as HitTarget;
      s.id = e.id;
      s.x = e.x;
      s.y = e.y;
      s.z = e.z;
      s.radius = ENEMY.radius;
      s.team = 1;
      this.targets.push(s);
    }
    if (this.tracker.completed && this.boss.phase !== 'down') {
      const s = this.targetSlots[slotIdx++] as HitTarget;
      s.id = BOSS_ID;
      s.x = this.boss.x;
      s.y = this.boss.y;
      s.z = this.boss.z;
      s.radius = BOSS.radius;
      s.team = 1;
      this.targets.push(s);
    }
    collideProjectiles(this.pool, this.targets, dt, this.onHit);
  }

  private fireEnemyBolt(x: number, y: number, z: number, tx: number, ty: number, tz: number): void {
    const dx = tx - x;
    const dy = ty - y;
    const dz = tz - z;
    const d = Math.max(1e-6, Math.hypot(dx, dy, dz));
    spawnProjectile(
      this.pool, 1, x, y, z,
      (dx / d) * PROJECTILE.enemySpeed, (dy / d) * PROJECTILE.enemySpeed,
      (dz / d) * PROJECTILE.enemySpeed, PROJECTILE.enemyDamage,
    );
  }

  private resolveHit(targetId: number, damage: number, owner: ProjectileOwner): void {
    if (targetId === PLAYER_ID) {
      if (this.phase !== 'active') return;
      this.hp = Math.max(0, this.hp - damage);
      this.shakeTimer = SHAKE_SECONDS;
      this.deps.audio.blip(160, 0.12, 'sawtooth');
      this.emit({ kind: 'player-hit', amount: damage, hp: this.hp });
      if (this.hp <= 0) {
        this.emit({ kind: 'player-down' });
        this.endRun(false);
      }
      return;
    }
    if (owner !== 0) return;
    this.emit({ kind: 'shot-hit', targetId });
    if (targetId === BOSS_ID) {
      const result = damageBoss(this.boss, damage);
      if (result === 'blocked') {
        this.emit({ kind: 'boss-shield-blocked' });
        this.deps.audio.blip(330, 0.05, 'sine');
      } else if (result === 'killed') {
        this.emit({ kind: 'boss-kill' });
        this.deps.audio.blip(1100, 0.3, 'square');
        this.endRun(true);
      } else {
        this.emit({ kind: 'boss-hit', amount: damage, hp: this.boss.hp });
        this.deps.audio.blip(440, 0.04, 'square');
      }
      return;
    }
    const hit = this.enemies.find((e) => e.id === targetId);
    if (hit && damageEnemy(hit, damage)) {
      this.emit({ kind: 'drone-kill', droneId: hit.id });
      this.deps.audio.blip(880, 0.16, 'square');
    } else {
      this.deps.audio.blip(520, 0.04, 'square');
    }
  }

  // ---- Per-frame visuals ---------------------------------------------------

  /** Called from the App render loop while flight mode is active. */
  frame(elapsed: number, frameDt: number): void {
    const p = this.player;
    const parts = this.parts;

    // Player drone transform straight from simulation state.
    parts.player.position.set(p.x, p.y, p.z);
    parts.player.rotation.set(-p.lean, p.yaw, p.bank, 'YXZ');

    // Rings: passed green, next pulsing cyan, future violet.
    for (let i = 0; i < parts.rings.length; i++) {
      const mesh = parts.rings[i] as THREE.Mesh;
      const mat = parts.ringMaterials[i] as THREE.MeshLambertMaterial;
      if (i < this.tracker.next || this.tracker.completed) {
        mat.emissive.setHex(RING_PASSED_COLOR);
        mat.color.setHex(RING_PASSED_COLOR);
        mat.emissiveIntensity = 0.35;
      } else if (i === this.tracker.next) {
        mat.emissive.setHex(RING_NEXT_COLOR);
        mat.color.setHex(RING_NEXT_COLOR);
        mat.emissiveIntensity = 0.6 + 0.35 * Math.sin(elapsed * 5);
      } else {
        mat.emissive.setHex(RING_FUTURE_COLOR);
        mat.color.setHex(RING_FUTURE_COLOR);
        mat.emissiveIntensity = 0.45;
      }
      // Face the player's approach (billboarding around Y only).
      mesh.rotation.y = Math.atan2(p.x - mesh.position.x, p.z - mesh.position.z);
    }

    // Enemies + boss.
    for (let i = 0; i < this.enemies.length; i++) {
      const e = this.enemies[i] as EnemyDrone;
      const mesh = parts.enemies[i] as THREE.Group;
      mesh.visible = e.alive;
      if (e.alive) {
        mesh.position.set(e.x, e.y, e.z);
        mesh.rotation.y = Math.atan2(p.x - e.x, p.z - e.z);
      }
    }
    const bossUp = this.boss.phase !== 'down';
    parts.boss.visible = bossUp;
    if (bossUp) {
      parts.boss.position.set(this.boss.x, this.boss.y, this.boss.z);
      parts.boss.rotation.y = Math.atan2(p.x - this.boss.x, p.z - this.boss.z);
      parts.shield.visible = this.boss.phase === 'shielded';
      parts.shieldMaterial.opacity = 0.16 + 0.08 * Math.sin(elapsed * 3);
    }

    // Projectile instances (front-compacted each frame; pool is SoA).
    let count = 0;
    const pool = this.pool;
    for (let i = 0; i < PROJECTILE.max; i++) {
      if (pool.alive[i] === 0) continue;
      this.boltMatrix.makeTranslation(
        pool.x[i] as number, pool.y[i] as number, pool.z[i] as number,
      );
      parts.bolts.setMatrixAt(count, this.boltMatrix);
      parts.bolts.setColorAt(count, pool.owner[i] === 0 ? this.boltColorPlayer : this.boltColorEnemy);
      count++;
    }
    parts.bolts.count = count;
    parts.bolts.instanceMatrix.needsUpdate = true;
    if (parts.bolts.instanceColor) parts.bolts.instanceColor.needsUpdate = true;

    // Chase camera with exponential smoothing + reduced-motion-aware shake.
    const cp = Math.cos(this.camPitch);
    this.lookDir.set(Math.sin(p.yaw) * cp, Math.sin(this.camPitch), Math.cos(p.yaw) * cp);
    const lerp = 1 - Math.exp(-8 * frameDt);
    this.camTarget.set(
      p.x - this.lookDir.x * 11,
      p.y - this.lookDir.y * 11 + 3.4,
      p.z - this.lookDir.z * 11,
    );
    this.camera.position.lerp(this.camTarget, lerp);
    if (this.shakeTimer > 0 && this.deps.getMotionEffects()) {
      const a = this.shakeTimer / SHAKE_SECONDS;
      this.camera.position.x += Math.sin(elapsed * 71) * 0.3 * a;
      this.camera.position.y += Math.cos(elapsed * 67) * 0.25 * a;
    }
    this.camera.lookAt(p.x + this.lookDir.x * 9, p.y + this.lookDir.y * 9, p.z + this.lookDir.z * 9);

    // Engine pitch follows real speed.
    const speed = Math.hypot(p.vx, p.vy, p.vz);
    this.deps.audio.engineSet(Math.min(1, speed / FLIGHT.maxForward), false);

    // HUD readouts (change-gated inside).
    this.hud.setRings(this.tracker.passed, this.tracker.total, this.tracker.completed);
    this.hud.setHull(Math.round(this.hp), PLAYER_MAX_HP);
    this.hud.setScore(totalScore(this.score));
    this.hud.setSpeed(droneForwardSpeed(p), p.y);
    this.updateArrow();
    this.hud.setWarning(this.tracker.missed ? 'WRONG RING — an earlier ring is still due' : '');
    if (this.tracker.completed && bossUp) {
      const frac = this.boss.hp / BOSS.maxHp;
      const label =
        this.boss.phase === 'shielded'
          ? 'WARDEN — SHIELDED (destroy its escorts)'
          : this.boss.phase === 'vulnerable'
            ? 'WARDEN — VULNERABLE'
            : 'WARDEN — ENRAGED';
      this.hud.setBossBanner(label, frac);
    } else {
      this.hud.setBossBanner('', 0);
    }
  }

  private arrowOut = { x: 0, y: 0, z: 0, dist: 0 };

  private updateArrow(): void {
    const p = this.player;
    let tx = 0;
    let ty = 0;
    let tz = 0;
    let dist = 0;
    if (!this.tracker.completed) {
      if (!this.tracker.dirToNext(p.x, p.y, p.z, this.arrowOut)) {
        this.hud.setArrow(false, 0, 0, 0);
        return;
      }
      tx = this.arrowOut.x;
      ty = this.arrowOut.y;
      tz = this.arrowOut.z;
      dist = this.arrowOut.dist;
    } else if (this.boss.phase !== 'down') {
      const dx = this.boss.x - p.x;
      const dy = this.boss.y - p.y;
      const dz = this.boss.z - p.z;
      dist = Math.max(1e-6, Math.hypot(dx, dy, dz));
      tx = dx / dist;
      ty = dy / dist;
      tz = dz / dist;
    } else {
      this.hud.setArrow(false, 0, 0, 0);
      return;
    }
    let bearing = Math.atan2(tx, tz) - p.yaw;
    while (bearing > Math.PI) bearing -= Math.PI * 2;
    while (bearing < -Math.PI) bearing += Math.PI * 2;
    const pitch = Math.asin(Math.max(-1, Math.min(1, ty)));
    this.hud.setArrow(this.phase === 'active' || this.phase === 'ending', bearing, pitch, dist);
  }

  private snapCamera(): void {
    const p = this.player;
    const cpch = Math.cos(this.camPitch);
    this.lookDir.set(Math.sin(p.yaw) * cpch, Math.sin(this.camPitch), Math.cos(p.yaw) * cpch);
    this.camera.position.set(
      p.x - this.lookDir.x * 11,
      p.y + 3.4,
      p.z - this.lookDir.z * 11,
    );
    this.camera.lookAt(p.x + this.lookDir.x * 9, p.y, p.z + this.lookDir.z * 9);
  }
}
