/**
 * Race mode: a seeded procedural circuit with real kart physics, three
 * AI rivals on the SAME physics, ordered checkpoints, a time-trial
 * variant with a persisted ghost replay, and a full lifecycle:
 * select -> countdown -> active -> finishing -> results -> hub.
 *
 * The simulation lives in the pure modules under src/systems/race
 * (Track / Vehicle / Checkpoints / RaceAI / Ghost); this class wires
 * them to input, audio, HUD, and the Three.js scene. The fixed-step
 * update allocates nothing: all query results, inputs, and standings
 * rows are preallocated.
 */

import * as THREE from 'three';
import type { GameBus } from '../core/EventBus';
import type { Input } from '../core/Input';
import type { SaveSystem } from '../core/SaveSystem';
import type { AudioSystem } from '../systems/Audio';
import {
  LapTracker,
  compareRacers,
  formatMs,
  type RacerProgress,
} from '../systems/race/Checkpoints';
import {
  GhostRecorder,
  deserializeGhost,
  sampleGhost,
  serializeGhost,
  type GhostData,
} from '../systems/race/Ghost';
import { advanceTarget, aiDecide, makeSkills, type AISkill } from '../systems/race/RaceAI';
import {
  createQueryResult,
  generateTrack,
  queryTrack,
  type TrackData,
  type TrackQueryResult,
} from '../systems/race/Track';
import {
  VEHICLE,
  collideWithWall,
  createInput,
  createVehicle,
  forwardSpeed,
  resetVehicle,
  stepVehicle,
  type VehicleInput,
  type VehicleState,
} from '../systems/race/Vehicle';
import { RaceHUD } from '../ui/RaceHUD';
import { RACER_NAMES, buildRaceScene, type RaceSceneParts } from './race/RaceScene';
import type { Mode } from './Mode';

const TOTAL_LAPS = 3;
const AI_COUNT = 3;
const COUNTDOWN_SECONDS = 3;
const GO_FLASH_SECONDS = 0.9;
const FINISHING_SECONDS = 2.4;
const STANDINGS_EVERY_STEPS = 15;

type Phase = 'select' | 'countdown' | 'active' | 'finishing' | 'results';
type Variant = 'gp' | 'tt';

interface Racer {
  state: VehicleState;
  input: VehicleInput;
  query: TrackQueryResult;
  tracker: LapTracker;
  /** AI only */
  skill: AISkill | null;
  targetIdx: number;
  lastPassedTotal: number;
}

export interface RaceModeDeps {
  parent: HTMLElement;
  bus: GameBus;
  input: Input;
  audio: AudioSystem;
  save: SaveSystem;
  seed: number;
  isDebugVisible: () => boolean;
  exitToHub: () => void;
  setLockWanted: (wanted: boolean) => void;
}

export class RaceMode implements Mode {
  readonly id = 'race';
  readonly camera: THREE.PerspectiveCamera;
  readonly track: TrackData;

  get scene(): THREE.Scene {
    return this.parts.scene;
  }

  get entityCount(): number {
    return this.parts.entityCount;
  }

  private parts: RaceSceneParts;
  private hud: RaceHUD;
  private active = false;
  private phase: Phase = 'select';
  private variant: Variant = 'gp';
  private racers: Racer[] = [];
  private skills: AISkill[];
  private countdown = 0;
  private goFlash = 0;
  private finishTimer = 0;
  private stepCounter = 0;
  private playerPos = 1;
  private wantDebug = false;

  // Ghost (time trial).
  private recorder = new GhostRecorder();
  private bestGhost: GhostData | null = null;
  private ghostScratch = { x: 0, z: 0, h: 0 };
  private ghostKey: string;

  // Standings scratch (preallocated; sorted in place).
  private standings: RacerProgress[] = [];

  // Camera scratch.
  private camTarget = new THREE.Vector3();

  constructor(private deps: RaceModeDeps) {
    this.track = generateTrack(deps.seed);
    this.parts = buildRaceScene(this.track);
    this.camera = new THREE.PerspectiveCamera(72, innerWidth / innerHeight, 0.1, 1200);
    window.addEventListener('resize', () => {
      this.camera.aspect = innerWidth / innerHeight;
      this.camera.updateProjectionMatrix();
    });

    this.skills = makeSkills(deps.seed, AI_COUNT);
    for (let i = 0; i < 1 + AI_COUNT; i++) {
      this.racers.push({
        state: createVehicle(0, 0, 0),
        input: createInput(),
        query: createQueryResult(),
        tracker: new LapTracker(this.track.gates, TOTAL_LAPS),
        skill: i === 0 ? null : (this.skills[i - 1] as AISkill),
        targetIdx: 0,
        lastPassedTotal: 0,
      });
      this.standings.push({ id: String(i), finished: false, finishMs: 0, passedTotal: 0, distToNext: 0 });
    }

    this.ghostKey = `neon-commons:ghost:v1:${deps.seed}`;
    this.bestGhost = deserializeGhost(deps.save.loadRaw(this.ghostKey), deps.seed);

    this.hud = new RaceHUD(deps.parent, {
      onStartGrandPrix: () => this.startRace('gp'),
      onStartTimeTrial: () => this.startRace('tt'),
      onRestart: () => this.startRace(this.variant),
      onExitToHub: () => this.deps.exitToHub(),
    });

    this.deps.input.onEdge('reset', () => {
      if (this.active && this.phase === 'active') this.respawnPlayer();
    });
    this.deps.input.onEdge('escape', () => {
      if (this.active) this.deps.exitToHub();
    });
    this.deps.input.onEdge('modeDebug', () => {
      if (!this.active) return;
      this.wantDebug = !this.wantDebug;
      this.deps.bus.emit('toast', {
        text: this.wantDebug
          ? 'Race debug: racing line, gates, AI targets (needs F1 overlay on)'
          : 'Race debug off',
        kind: 'info',
      });
    });
  }

  // ---- Mode lifecycle --------------------------------------------------

  enter(): void {
    this.active = true;
    this.phase = 'select';
    this.deps.setLockWanted(false);
    this.hud.setVisible(true);
    this.hud.showSelect();
    this.placeGrid();
    this.snapCameraBehindPlayer();
    this.hud.setGhostNote(
      this.bestGhost
        ? `Saved ghost on this track: ${formatMs(this.bestGhost.timeMs)}`
        : 'No ghost saved on this track yet — set one in Time Trial',
    );
    this.deps.bus.emit('toast', {
      text: `Neon Circuit · lap ${(this.track.total / 1000).toFixed(2)} km · seed ${this.deps.seed}`,
      kind: 'info',
    });
  }

  exit(): void {
    this.active = false;
    this.phase = 'select';
    this.hud.setVisible(false);
    this.deps.audio.engineStop();
    this.deps.setLockWanted(true);
  }

  // ---- Race lifecycle ----------------------------------------------------

  private startRace(variant: Variant): void {
    this.variant = variant;
    this.phase = 'countdown';
    this.countdown = COUNTDOWN_SECONDS;
    this.goFlash = 0;
    this.stepCounter = 0;
    this.playerPos = 1;
    this.hud.hidePanels();
    this.hud.setGhostNote('');
    for (let i = 0; i < this.racers.length; i++) {
      const r = this.racers[i] as Racer;
      r.tracker = new LapTracker(this.track.gates, TOTAL_LAPS);
      r.lastPassedTotal = 0;
      r.targetIdx = 8;
      zeroInput(r.input);
    }
    this.placeGrid();
    this.snapCameraBehindPlayer();
    this.recorder.reset();
    this.deps.audio.engineStart();
    const aiVisible = variant === 'gp';
    for (let i = 1; i < this.parts.karts.length; i++) {
      (this.parts.karts[i] as THREE.Group).visible = aiVisible;
    }
    this.deps.bus.emit('toast', {
      text: variant === 'gp' ? 'Grand Prix: 3 laps, 3 rivals' : 'Time Trial: 3 laps vs the ghost',
      kind: 'success',
    });
  }

  /** Start grid: two staggered columns behind the start line; player last. */
  private placeGrid(): void {
    const t = this.track;
    const tx = t.tx[0] as number;
    const tz = t.tz[0] as number;
    const nx = -tz;
    const nz = tx;
    const heading = Math.atan2(tx, tz);
    for (let i = 0; i < this.racers.length; i++) {
      const slot = i === 0 ? this.racers.length - 1 : i - 1;
      const back = 7 + slot * 4.5;
      const side = (slot % 2 === 0 ? 1 : -1) * 2.8;
      const r = this.racers[i] as Racer;
      resetVehicle(
        r.state,
        (t.xs[0] as number) - tx * back + nx * side,
        (t.zs[0] as number) - tz * back + nz * side,
        heading,
      );
    }
  }

  private respawnPlayer(): void {
    const player = this.racers[0] as Racer;
    const gate = this.track.gates[player.tracker.lastPassed];
    if (!gate) return;
    const s = gate.sample;
    resetVehicle(
      player.state,
      this.track.xs[s] as number,
      this.track.zs[s] as number,
      Math.atan2(this.track.tx[s] as number, this.track.tz[s] as number),
    );
    this.deps.bus.emit('toast', { text: 'Respawned at the last checkpoint', kind: 'warn' });
  }

  // ---- Fixed-step simulation ----------------------------------------------

  update(dt: number): void {
    if (!this.active) return;

    if (this.phase === 'countdown') {
      const before = Math.ceil(this.countdown);
      this.countdown -= dt;
      const after = Math.ceil(this.countdown);
      if (after !== before && after > 0) this.deps.audio.blip(440, 0.09, 'square');
      if (this.countdown <= 0) {
        this.phase = 'active';
        this.goFlash = GO_FLASH_SECONDS;
        this.deps.audio.blip(880, 0.18, 'square');
      }
      return;
    }
    if (this.phase !== 'active' && this.phase !== 'finishing') return;

    this.goFlash = Math.max(0, this.goFlash - dt);
    this.stepCounter++;

    const player = this.racers[0] as Racer;

    // Player input (zeroed once finished: the kart coasts out).
    if (!player.tracker.finished) {
      const input = this.deps.input;
      player.input.throttle = input.isDown('forward') ? 1 : 0;
      player.input.brake = input.isDown('back') ? 1 : 0;
      player.input.steer = (input.isDown('right') ? 1 : 0) - (input.isDown('left') ? 1 : 0);
      player.input.drift = input.isDown('jump');
    } else {
      zeroInput(player.input);
      player.input.brake = 0.3;
    }

    const simCount = this.variant === 'gp' ? this.racers.length : 1;
    for (let i = 0; i < simCount; i++) {
      const r = this.racers[i] as Racer;

      // AI decision from the same waypoint stream every step.
      if (i > 0 && r.skill) {
        if (r.tracker.finished) {
          zeroInput(r.input);
          r.input.brake = 0.3;
        } else {
          r.targetIdx = advanceTarget(
            r.state.x, r.state.z, this.track.xs, this.track.zs, r.targetIdx, r.skill.lookahead,
          );
          aiDecide(
            r.state.x, r.state.z, r.state.heading, forwardSpeed(r.state),
            this.track.xs[r.targetIdx] as number, this.track.zs[r.targetIdx] as number,
            r.skill, r.input,
          );
        }
      }

      // Same physics pipeline for everyone: query -> step -> query -> wall.
      queryTrack(this.track, r.state.x, r.state.z, r.state.segHint, r.query);
      r.state.segHint = r.query.seg;
      stepVehicle(r.state, r.input, r.query.surface, dt);
      queryTrack(this.track, r.state.x, r.state.z, r.state.segHint, r.query);
      r.state.segHint = r.query.seg;
      collideWithWall(r.state, r.query, this.track.wallDist);

      // Ordered checkpoints (skip once finished; tracker self-guards too).
      const velDot = r.state.vx * r.query.tangentX + r.state.vz * r.query.tangentZ;
      r.tracker.update(dt, r.state.x, r.state.z, velDot);

      if (i === 0 && r.tracker.passedTotal !== r.lastPassedTotal) {
        r.lastPassedTotal = r.tracker.passedTotal;
        this.onPlayerGate(r);
      }
    }

    // Ghost recording (time trial only; bounded + decimated inside).
    if (this.variant === 'tt' && !player.tracker.finished) {
      this.recorder.tick(player.state.x, player.state.z, player.state.heading);
    }

    if (this.stepCounter % STANDINGS_EVERY_STEPS === 0) this.refreshStandings();

    if (this.phase === 'active' && player.tracker.finished) {
      this.phase = 'finishing';
      this.finishTimer = FINISHING_SECONDS;
      this.onPlayerFinished();
    }
    if (this.phase === 'finishing') {
      this.finishTimer -= dt;
      if (this.finishTimer <= 0) this.showResults();
    }
  }

  private onPlayerGate(player: Racer): void {
    this.deps.audio.blip(660, 0.07, 'triangle');
    const laps = player.tracker.lapTimes;
    if (player.tracker.next === 1 && laps.length > 0 && !player.tracker.finished) {
      const lapMs = laps[laps.length - 1] as number;
      this.deps.bus.emit('toast', {
        text: `Lap ${laps.length} — ${formatMs(lapMs)}${lapMs === player.tracker.bestLapMs ? ' (best)' : ''}`,
        kind: 'success',
      });
    }
  }

  private onPlayerFinished(): void {
    const player = this.racers[0] as Racer;
    this.deps.audio.blip(990, 0.25, 'square');
    if (this.variant === 'tt') {
      const timeMs = player.tracker.finishMs;
      if (!this.bestGhost || timeMs < this.bestGhost.timeMs) {
        const ghost = this.recorder.finalize(this.deps.seed, timeMs);
        if (this.deps.save.saveRaw(this.ghostKey, serializeGhost(ghost))) {
          this.bestGhost = ghost;
          this.deps.bus.emit('toast', {
            text: `New best run ${formatMs(timeMs)} — ghost saved`,
            kind: 'success',
          });
        }
      } else {
        this.deps.bus.emit('toast', {
          text: `${formatMs(timeMs)} — ghost stands at ${formatMs(this.bestGhost.timeMs)}`,
          kind: 'info',
        });
      }
    }
  }

  private refreshStandings(): void {
    const count = this.variant === 'gp' ? this.racers.length : 1;
    for (let i = 0; i < count; i++) {
      const r = this.racers[i] as Racer;
      const row = this.standings[i] as RacerProgress;
      row.id = String(i);
      row.finished = r.tracker.finished;
      row.finishMs = r.tracker.finishMs;
      row.passedTotal = r.tracker.passedTotal;
      row.distToNext = r.tracker.distToNext(r.state.x, r.state.z);
    }
    if (count > 1) {
      this.standings.length = count;
      this.standings.sort(compareRacers);
      this.playerPos = this.standings.findIndex((s) => s.id === '0') + 1;
      // restore stable storage order for the next refresh
      this.standings.sort((a, b) => Number(a.id) - Number(b.id));
    } else {
      this.playerPos = 1;
    }
  }

  private showResults(): void {
    this.phase = 'results';
    this.deps.audio.engineStop();
    const count = this.variant === 'gp' ? this.racers.length : 1;
    this.refreshStandings();
    const snapshot: RacerProgress[] = [];
    for (let i = 0; i < count; i++) snapshot.push({ ...(this.standings[i] as RacerProgress) });
    snapshot.sort(compareRacers);
    const rows = snapshot.map((s, pos) => {
      const idx = Number(s.id);
      const r = this.racers[idx] as Racer;
      return {
        position: pos + 1,
        name: RACER_NAMES[idx] as string,
        isPlayer: idx === 0,
        finished: r.tracker.finished,
        finishMs: r.tracker.finishMs,
        bestLapMs: r.tracker.bestLapMs,
        lapsDone: r.tracker.lap,
      };
    });
    const player = this.racers[0] as Racer;
    this.hud.showResults(rows, player.tracker.lapTimes);
    this.hud.setGhostNote(
      this.variant === 'tt' && this.bestGhost
        ? `Ghost on file: ${formatMs(this.bestGhost.timeMs)}`
        : '',
    );
  }

  // ---- Per-frame visuals ---------------------------------------------------

  /** Called from the App render loop while race mode is active. */
  frame(elapsed: number, frameDt: number): void {
    const player = this.racers[0] as Racer;

    // Kart transforms straight from simulation state.
    const count = this.variant === 'gp' ? this.racers.length : 1;
    for (let i = 0; i < count; i++) {
      const r = this.racers[i] as Racer;
      const kart = this.parts.karts[i] as THREE.Group;
      kart.position.set(r.state.x, 0, r.state.z);
      kart.rotation.y = r.state.heading;
      kart.rotation.z = -r.state.steer * (r.state.drifting ? 0.14 : 0.05);
    }

    // Ghost replay (time trial, while racing).
    const showGhost =
      this.variant === 'tt' &&
      this.bestGhost !== null &&
      (this.phase === 'active' || this.phase === 'finishing') &&
      sampleGhost(this.bestGhost, player.tracker.elapsedMs / 1000, this.ghostScratch);
    this.parts.ghost.visible = showGhost;
    if (showGhost) {
      this.parts.ghost.position.set(this.ghostScratch.x, 0, this.ghostScratch.z);
      this.parts.ghost.rotation.y = this.ghostScratch.h;
    }

    // Boost pads pulse on simulation time (freezes on pause).
    this.parts.padMaterial.color.setHSL(0.42, 1, 0.4 + 0.22 * Math.sin(elapsed * 6));

    // Debug layer: only while the F1 overlay is up.
    this.parts.debugGroup.visible = this.wantDebug && this.deps.isDebugVisible();
    if (this.parts.debugGroup.visible) {
      for (let i = 0; i < this.parts.aiTargets.length; i++) {
        const r = this.racers[i + 1] as Racer;
        const m = this.parts.aiTargets[i] as THREE.Mesh;
        m.visible = this.variant === 'gp';
        m.position.set(
          this.track.xs[r.targetIdx] as number,
          1.2,
          this.track.zs[r.targetIdx] as number,
        );
      }
    }

    // Chase camera with exponential smoothing.
    const s = player.state;
    const fx = Math.sin(s.heading);
    const fz = Math.cos(s.heading);
    const lerp = 1 - Math.exp(-7 * frameDt);
    this.camTarget.set(s.x - fx * 10.5, 4.6, s.z - fz * 10.5);
    this.camera.position.lerp(this.camTarget, lerp);
    this.camera.lookAt(s.x + fx * 5, 1.1, s.z + fz * 5);

    // Engine pitch follows real speed.
    const speed = forwardSpeed(s);
    this.deps.audio.engineSet(
      Math.min(1, Math.abs(speed) / VEHICLE.maxSpeed),
      s.boostTimer > 0,
    );

    // HUD readouts (change-gated inside).
    if (this.phase === 'countdown') {
      this.hud.setCountdown(String(Math.max(1, Math.ceil(this.countdown))));
    } else if (this.goFlash > 0) {
      this.hud.setCountdown('GO!');
    } else {
      this.hud.setCountdown('');
    }
    const tr = player.tracker;
    this.hud.setLap(tr.lap, TOTAL_LAPS);
    this.hud.setTimes(tr.finished ? 0 : tr.currentLapMs, tr.bestLapMs);
    this.hud.setPosition(this.playerPos, this.variant === 'gp' ? this.racers.length : 1);
    this.hud.setSpeed(speed, s.boostTimer > 0);
    this.hud.setWarning(tr.wrongWay, tr.missed);
  }

  private snapCameraBehindPlayer(): void {
    const s = (this.racers[0] as Racer).state;
    const fx = Math.sin(s.heading);
    const fz = Math.cos(s.heading);
    this.camera.position.set(s.x - fx * 10.5, 4.6, s.z - fz * 10.5);
    this.camera.lookAt(s.x + fx * 5, 1.1, s.z + fz * 5);
  }
}

function zeroInput(i: VehicleInput): void {
  i.throttle = 0;
  i.brake = 0;
  i.steer = 0;
  i.drift = false;
}
