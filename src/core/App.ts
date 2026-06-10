/**
 * Composition root. Owns the fixed-timestep loop, wires every system
 * together, applies settings/quality side effects, runs the stress
 * test state machine, and feeds the debug overlay with measured
 * numbers. The render loop allocates nothing: scratch objects are
 * created once here.
 */

import { EventBus, type GameEvents } from './EventBus';
import { GameState } from './GameState';
import { Input } from './Input';
import { SaveSystem } from './SaveSystem';
import { SelfAudit } from './SelfAudit';
import { Time } from './Time';
import { DebugOverlay, type DebugStats } from './DebugOverlay';
import { CameraRig } from '../rendering/CameraRig';
import { Lighting } from '../rendering/Lighting';
import {
  PerformanceScaler,
  type QualityProfile,
} from '../rendering/PerformanceScaler';
import {
  DAY_FOG,
  NIGHT_FOG,
  SceneManager,
} from '../rendering/SceneManager';
import { HubMode } from '../modes/HubMode';
import { ModeManager } from '../modes/Mode';
import { AudioSystem } from '../systems/Audio';
import {
  deserializeSettings,
  serializeSettings,
  type SettingsData,
} from '../systems/Serialization';
import { ProceduralCity, STRESS_MAX } from '../world/ProceduralCity';
import { buildTerrain } from '../world/Terrain';
import { Vegetation } from '../world/Vegetation';
import { Water } from '../world/Water';
import { generateWorld, type WorldData } from '../world/WorldGeneration';
import { HUD } from '../ui/HUD';
import { Menu } from '../ui/Menu';
import { Minimap } from '../ui/Minimap';
import { ToastLog } from '../ui/ToastLog';

const FPS_WINDOW = 60;
const STRESS_SAMPLE_FRAMES = 90;

export class App {
  private bus = new EventBus<GameEvents>();
  private state: GameState;
  private time = new Time();
  private input = new Input();
  private save = new SaveSystem();
  private settings: SettingsData;
  private audio = new AudioSystem();
  private scaler: PerformanceScaler;

  private sceneMgr: SceneManager;
  private rig: CameraRig;
  private lighting: Lighting;
  private world: WorldData;
  private city: ProceduralCity;
  private water: Water;
  private vegetation: Vegetation;
  private hub: HubMode;
  private modes: ModeManager;

  private overlay: DebugOverlay;
  private hud: HUD;
  private minimap: Minimap;
  private menu: Menu;
  private audit: SelfAudit;

  // Measurement state (preallocated; render loop allocates nothing).
  private fpsRing = new Float32Array(FPS_WINDOW);
  private fpsIdx = 0;
  private fpsFilled = 0;
  private lastDrawCalls = 0;
  private lastTriangles = 0;
  private overlayTimer = 0;
  private mouseDelta = { x: 0, y: 0 };
  private stats: DebugStats = {
    fps: 0, frameMs: 0, drawCalls: 0, triangles: 0, entities: 0,
    mode: 'none', quality: 'high', camX: 0, camY: 0, camZ: 0,
    seed: 0, windows: 0, stress: 'not run',
  };
  private stress = {
    phase: 'idle' as 'idle' | 'before' | 'after',
    frames: 0,
    accum: 0,
    beforeFps: 0,
  };
  private pausedByMenu = false;

  constructor(parent: HTMLElement) {
    this.state = new GameState();
    this.settings = this.save.load();
    this.scaler = new PerformanceScaler(this.settings.quality);
    this.world = generateWorld(this.state.seed);

    // Rendering ------------------------------------------------------
    this.sceneMgr = new SceneManager(parent);
    const profile = this.scaler.profile;
    this.rig = new CameraRig(this.settings.fov, profile.drawDistance + 80);
    this.lighting = new Lighting(this.sceneMgr.scene);

    // World ----------------------------------------------------------
    this.sceneMgr.scene.add(buildTerrain(this.state.seed));
    this.water = new Water();
    this.sceneMgr.scene.add(this.water.mesh);
    this.vegetation = new Vegetation(this.world);
    this.sceneMgr.scene.add(this.vegetation.group);
    this.city = new ProceduralCity(this.world);
    this.sceneMgr.scene.add(this.city.group);

    // UI --------------------------------------------------------------
    this.hud = new HUD(parent, this.bus);
    new ToastLog(parent, this.bus);
    this.minimap = new Minimap(parent, this.world);
    this.overlay = new DebugOverlay(parent);
    this.menu = new Menu(parent, this.settingsController(), {
      onOpenChange: (open) => this.onMenuOpenChange(open),
      onStressTest: () => this.startStressTest(),
    });

    // Modes ------------------------------------------------------------
    this.modes = new ModeManager(this.bus);
    this.hub = new HubMode(
      this.world,
      this.bus,
      this.input,
      this.rig,
      this.audio,
      (text) => this.hud.setPrompt(text),
    );
    this.modes.register(this.hub);
    this.modes.switchTo('hub');
    this.state.modeId = 'hub';

    // Input ------------------------------------------------------------
    this.input.attach(this.sceneMgr.canvas);
    this.input.setLockWanted(true);
    this.wireEdgeActions();

    // Audio: browsers require a user gesture before AudioContext runs.
    const armAudio = (): void => {
      this.audio.ensure();
      this.audio.setVolumes(
        this.settings.masterVolume,
        this.settings.sfxVolume,
        this.settings.musicVolume,
      );
    };
    window.addEventListener('pointerdown', armAudio, { once: true });
    window.addEventListener('keydown', armAudio, { once: true });

    // Apply persisted settings + initial quality/night.
    this.applyAllSettings();
    this.scaler.onChange((q, p) => {
      this.applyProfile(p);
      this.bus.emit('quality:changed', { quality: q });
      this.bus.emit('toast', { text: `Quality: ${q}`, kind: 'info' });
    });
    this.applyProfile(profile);
    this.applyNight(this.state.night);

    // Interact plumbing: pedestals exist, modes are not installed yet.
    this.bus.on('interact', ({ targetId, label }) => {
      if (this.modes.has(targetId)) {
        this.modes.switchTo(targetId); // future stages take this branch
      } else {
        this.bus.emit('toast', {
          text: `${label} systems detected — docking soon (mode ships in a later stage)`,
          kind: 'info',
        });
      }
    });

    // Self-audit -------------------------------------------------------
    this.audit = new SelfAudit(this.bus);
    this.registerAuditChecks();
    this.bus.on('audit:done', ({ passed, failed }) => {
      this.bus.emit('toast', {
        text: `Self-audit: ${passed}/${passed + failed} checks passed`,
        kind: failed === 0 ? 'success' : 'warn',
      });
    });
    window.setTimeout(() => this.audit.run(), 2000);

    this.bus.emit('toast', {
      text: `Welcome to Neon Commons · seed ${this.state.seed}`,
      kind: 'success',
    });
  }

  start(): void {
    requestAnimationFrame(this.loop);
  }

  // ---- main loop ----------------------------------------------------

  private loop = (now: number): void => {
    const steps = this.time.tick(now);

    // Mouse look applies per frame for responsiveness.
    this.input.consumeMouseDelta(this.mouseDelta);
    if (this.input.pointerLocked && !this.menu.isOpen) {
      this.rig.applyLook(this.mouseDelta.x, this.mouseDelta.y);
    }

    for (let i = 0; i < steps; i++) {
      this.modes.update(this.time.fixedDelta);
    }

    // Visual updates driven by simulation time (freeze on pause).
    this.water.update(this.time.elapsed);
    this.city.update(this.time.elapsed, this.hub.x, this.hub.z);
    this.rig.follow(this.hub.x, this.hub.y, this.hub.z);
    this.minimap.update(this.hub.x, this.hub.z, this.rig.yaw);

    this.sceneMgr.render(this.rig.camera);
    this.lastDrawCalls = this.sceneMgr.info.render.calls;
    this.lastTriangles = this.sceneMgr.info.render.triangles;

    this.measure();
    requestAnimationFrame(this.loop);
  };

  private measure(): void {
    const dt = this.time.frameDelta;
    if (dt > 0) {
      this.fpsRing[this.fpsIdx] = dt;
      this.fpsIdx = (this.fpsIdx + 1) % FPS_WINDOW;
      if (this.fpsFilled < FPS_WINDOW) this.fpsFilled++;
    }

    this.runStressMachine(dt);

    this.overlayTimer += dt;
    if (this.overlayTimer >= 0.2 && this.overlay.isVisible) {
      this.overlayTimer = 0;
      this.state.reportEntities('city', this.city.activeInstances);
      this.state.reportEntities('vegetation', this.vegetation.activeInstances);
      this.state.reportEntities('player', 1);
      const s = this.stats;
      s.fps = this.currentFps();
      s.frameMs = dt * 1000;
      s.drawCalls = this.lastDrawCalls;
      s.triangles = this.lastTriangles;
      s.entities = this.state.totalEntities;
      s.mode = this.modes.currentId;
      s.quality = this.scaler.current;
      s.camX = this.rig.camera.position.x;
      s.camY = this.rig.camera.position.y;
      s.camZ = this.rig.camera.position.z;
      s.seed = this.state.seed;
      s.windows = this.world.totalWindows;
      this.overlay.update(s);
    }
  }

  private currentFps(): number {
    if (this.fpsFilled === 0) return 0;
    let sum = 0;
    for (let i = 0; i < this.fpsFilled; i++) sum += this.fpsRing[i] as number;
    return sum > 0 ? this.fpsFilled / sum : 0;
  }

  // ---- stress test ----------------------------------------------------

  private startStressTest(): void {
    if (this.stress.phase !== 'idle') return;
    this.city.setStressCount(0);
    this.stress.phase = 'before';
    this.stress.frames = 0;
    this.stress.accum = 0;
    this.stats.stress = 'measuring baseline...';
    this.bus.emit('toast', { text: 'Stress test: measuring baseline FPS', kind: 'info' });
  }

  private runStressMachine(dt: number): void {
    const st = this.stress;
    if (st.phase === 'idle' || dt <= 0) return;
    st.frames++;
    st.accum += dt;
    if (st.frames < STRESS_SAMPLE_FRAMES) return;
    const fps = st.frames / st.accum;
    if (st.phase === 'before') {
      st.beforeFps = fps;
      this.city.setStressCount(STRESS_MAX);
      st.phase = 'after';
      st.frames = 0;
      st.accum = 0;
      this.stats.stress = `baseline ${fps.toFixed(0)} fps, loading +${STRESS_MAX} props...`;
    } else {
      st.phase = 'idle';
      this.city.setStressCount(0);
      this.stats.stress = `before ${st.beforeFps.toFixed(0)} fps / after ${fps.toFixed(0)} fps (+${STRESS_MAX} props)`;
      this.bus.emit('stress:result', {
        before: st.beforeFps,
        after: fps,
        props: STRESS_MAX,
      });
      this.bus.emit('toast', {
        text: `Stress: ${st.beforeFps.toFixed(0)} fps -> ${fps.toFixed(0)} fps with +${STRESS_MAX} instanced props`,
        kind: 'success',
      });
    }
  }

  // ---- settings / quality / night -------------------------------------

  private settingsController() {
    return {
      get: () => this.settings,
      set: <K extends keyof SettingsData>(key: K, value: SettingsData[K]): void => {
        this.settings = { ...this.settings, [key]: value };
        this.applySetting(key);
        this.save.save(this.settings);
        this.bus.emit('settings:changed', { key });
      },
      resetSave: (): void => {
        this.settings = this.save.reset();
        this.applyAllSettings();
        this.bus.emit('toast', { text: 'Save cleared; settings back to defaults', kind: 'warn' });
      },
    };
  }

  private applySetting(key: keyof SettingsData): void {
    switch (key) {
      case 'mouseSensitivity':
        this.input.mouseSensitivity = this.settings.mouseSensitivity;
        break;
      case 'fov':
        this.rig.setFov(this.settings.fov);
        break;
      case 'masterVolume':
      case 'sfxVolume':
      case 'musicVolume':
        this.audio.setVolumes(
          this.settings.masterVolume,
          this.settings.sfxVolume,
          this.settings.musicVolume,
        );
        break;
      case 'quality':
        this.scaler.set(this.settings.quality);
        break;
      case 'motionEffects':
        this.rig.bobEnabled = this.settings.motionEffects;
        this.water.setMotionEffects(this.settings.motionEffects);
        break;
      case 'debugOverlay':
        this.overlay.setVisible(this.settings.debugOverlay);
        break;
    }
  }

  private applyAllSettings(): void {
    for (const key of Object.keys(this.settings) as Array<keyof SettingsData>) {
      this.applySetting(key);
    }
  }

  private applyProfile(p: QualityProfile): void {
    this.sceneMgr.setFogRange(p.fogNear, p.drawDistance);
    this.sceneMgr.setPixelRatioCap(p.pixelRatioCap);
    this.sceneMgr.setShadows(p.shadows);
    this.lighting.setShadows(p.shadows);
    this.rig.setFar(p.drawDistance + 80);
    this.vegetation.applyProfile(p.treeFraction, p.grassCount);
    const fogColor = this.state.night ? NIGHT_FOG : DAY_FOG;
    this.city.facades.setFog(fogColor, p.fogNear, p.drawDistance);
    this.water.setFog(fogColor, p.fogNear, p.drawDistance);
  }

  private applyNight(night: boolean): void {
    this.state.night = night;
    this.sceneMgr.setNight(night);
    this.lighting.setNight(night);
    this.city.setNight(night);
    this.water.setNight(night);
    const p = this.scaler.profile;
    const fogColor = night ? NIGHT_FOG : DAY_FOG;
    this.city.facades.setFog(fogColor, p.fogNear, p.drawDistance);
    this.water.setFog(fogColor, p.fogNear, p.drawDistance);
    this.bus.emit('daynight:changed', { night });
  }

  // ---- input edges ----------------------------------------------------

  private wireEdgeActions(): void {
    this.input.onEdge('menu', () => this.menu.toggle());
    this.input.onEdge('pause', () => this.setPaused(!this.time.paused));
    this.input.onEdge('debug', () => {
      const visible = this.overlay.toggle();
      this.settings = { ...this.settings, debugOverlay: visible };
      this.save.save(this.settings);
    });
    this.input.onEdge('quality', () => {
      const q = this.scaler.cycle();
      this.settings = { ...this.settings, quality: q };
      this.save.save(this.settings);
    });
    this.input.onEdge('daynight', () => this.applyNight(!this.state.night));
  }

  private setPaused(paused: boolean): void {
    this.time.setPaused(paused);
    this.state.paused = paused;
    this.bus.emit('pause:changed', { paused });
  }

  private onMenuOpenChange(open: boolean): void {
    if (open) {
      this.pausedByMenu = !this.time.paused; // remember if WE paused
      this.input.setLockWanted(false);
      if (this.pausedByMenu) this.setPaused(true);
    } else {
      this.input.setLockWanted(true);
      this.input.requestLock();
      if (this.pausedByMenu) this.setPaused(false);
      this.pausedByMenu = false;
    }
  }

  // ---- self-audit -------------------------------------------------------

  private registerAuditChecks(): void {
    this.audit.add('1000+ procedural windows are real counted cells', () =>
      this.world.totalWindows >= 1000,
    );
    this.audit.add('collision grid covers buildings+tower+props+pedestals+lake+rim', () => {
      const expected =
        this.world.buildings.length + 1 + this.world.props.length +
        this.world.pedestals.length + 4 + 4;
      return this.hub.collision.boxCount === expected;
    });
    this.audit.add('spawn point is collision-free', () => {
      const r = this.hub.collision.resolveCapsule(
        this.world.spawn.x, 0, this.world.spawn.z, 0.45, 1.8,
      );
      return !r.collided;
    });
    this.audit.add('renderer batches the city (< 64 draw calls)', () =>
      this.lastDrawCalls > 0 && this.lastDrawCalls < 64,
    );
    this.audit.add('vegetation instancing respects quality profile', () => {
      const expectTrees = Math.floor(this.world.trees.length * this.scaler.profile.treeFraction);
      return this.vegetation.activeInstances >= expectTrees * 2;
    });
    this.audit.add('settings persist through a save/load round-trip', () => {
      const restored = deserializeSettings(serializeSettings(this.settings));
      return JSON.stringify(restored) === JSON.stringify(this.settings);
    });
    this.audit.add('exactly 5 future-mode pedestals with interact targets', () =>
      this.world.pedestals.length === 5,
    );
    this.audit.add('world rebuild from seed is deterministic', () => {
      const again = generateWorld(this.state.seed);
      return (
        again.buildings.length === this.world.buildings.length &&
        again.totalWindows === this.world.totalWindows &&
        again.buildings.every((b, i) => {
          const o = this.world.buildings[i];
          return o !== undefined && o.x === b.x && o.z === b.z && o.h === b.h;
        })
      );
    });
  }
}
