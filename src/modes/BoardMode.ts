/**
 * Board mode: Neon Districts, a 2-4 seat hot-seat economy board game.
 * All rules live in the pure modules under src/systems/board; this
 * class owns the interactive loop — seat setup, paced presentation of
 * engine events into the log, dice/pawn animation from REAL rolls,
 * bot turns, save/load via SaveSystem, share codes, and the results ->
 * hub lifecycle. Every log sentence comes from describeBoardEvent over
 * real events; F1 shows the live engine state (ownership map, deck,
 * RNG cursor).
 */

import * as THREE from 'three';
import type { GameBus } from '../core/EventBus';
import { isEditableTarget, type Input } from '../core/Input';
import type { SaveSystem } from '../core/SaveSystem';
import type { AudioSystem } from '../systems/Audio';
import { BOARD, BOARD_SIZE, type DistrictDef } from '../systems/board/BoardData';
import { botActions } from '../systems/board/Bot';
import {
  buyCurrent,
  canBuyCurrent,
  createBoardGame,
  describeBoardEvent,
  endTurn,
  playerName,
  rollDice,
  upgradableDistricts,
  upgradeDistrict,
  type BoardEvent,
  type BoardGameState,
} from '../systems/board/Engine';
import { EVENT_CARDS } from '../systems/board/EventDeck';
import { decodeShareCode, encodeShareCode } from '../systems/board/ShareCode';
import { BoardHUD } from '../ui/BoardHUD';
import {
  buildBoardScene,
  diceSettleRotation,
  PLAYER_HEX,
  spaceCenter,
  type BoardSceneParts,
} from './board/BoardScene';
import type { Mode } from './Mode';

const SAVE_KEY = 'neon-commons:board:v1';
const PRESENT_SECONDS: Partial<Record<BoardEvent['kind'], number>> = {
  'turn-start': 0.35,
  roll: 0.9,
  move: 0.75,
  card: 1.2,
  rent: 0.7,
  bankrupt: 1.2,
  'surge-recall': 1.0,
  'game-over': 1.0,
};
const PRESENT_DEFAULT = 0.42;
const BOT_THINK_SECONDS = 0.55;
/** Per-seat pawn offset so shared tiles stay readable. */
const PAWN_OFFSETS: ReadonlyArray<[number, number]> = [
  [-0.65, -0.5], [0.65, -0.5], [-0.65, 0.7], [0.65, 0.7],
];

interface PawnAnim {
  from: number;
  to: number;
  t: number; // 0..1, 1 = settled
}

interface DiceAnim {
  t: number; // counts up; settles after TUMBLE
  d1: number;
  d2: number;
}

export interface BoardModeDeps {
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

export class BoardMode implements Mode {
  readonly id = 'board';
  readonly camera: THREE.PerspectiveCamera;

  get scene(): THREE.Scene {
    return this.parts.scene;
  }

  get entityCount(): number {
    return this.parts.entityCount;
  }

  private parts: BoardSceneParts;
  private hud: BoardHUD;
  private active = false;
  private playing = false;
  private state: BoardGameState | null = null;
  private gameCount = 0;

  private presentQueue: BoardEvent[] = [];
  private presentTimer = 0;
  private botTimer = -1;
  private debugTimer = 0;

  private pawnAnims: PawnAnim[] = [];
  private diceAnim: DiceAnim = { t: 2, d1: 1, d2: 1 };
  private camPos = new THREE.Vector3(0, 27, 26);
  private camTarget = new THREE.Vector3(0, 0, 0);
  private camFocus = new THREE.Vector3(0, 0, 0);
  private scratchA = new THREE.Vector3();
  private scratchB = new THREE.Vector3();

  constructor(private deps: BoardModeDeps) {
    this.parts = buildBoardScene();
    for (let i = 0; i < 4; i++) this.pawnAnims.push({ from: 0, to: 0, t: 1 });

    this.camera = new THREE.PerspectiveCamera(52, innerWidth / innerHeight, 0.1, 400);
    this.camera.position.copy(this.camPos);
    this.camera.lookAt(this.camTarget);
    window.addEventListener('resize', () => {
      this.camera.aspect = innerWidth / innerHeight;
      this.camera.updateProjectionMatrix();
    });

    this.hud = new BoardHUD(deps.parent, {
      onStart: (bots) => this.startGame(bots),
      onExitToHub: () => this.deps.exitToHub(),
      onRoll: () => this.humanAction('roll'),
      onBuy: () => this.humanAction('buy'),
      onUpgradePick: (space) => this.humanUpgrade(space),
      onEndTurn: () => this.humanAction('end'),
      onSave: () => this.saveGame(),
      onShare: () => this.shareGame(),
      onLoadSave: () => this.loadSave(),
      onRestoreCode: (code) => this.restoreFromCode(code),
      onNewGame: () => this.showIntro(),
    });

    this.deps.input.onEdge('escape', () => {
      if (this.active) this.deps.exitToHub();
    });
    window.addEventListener('keydown', (e) => {
      if (!this.active || !this.playing) return;
      if (isEditableTarget(e.target as { tagName?: string } | null)) return;
      if (e.code === 'KeyR') this.humanAction('roll');
    });
  }

  // ---- Mode lifecycle -----------------------------------------------------

  enter(): void {
    this.active = true;
    this.deps.setLockWanted(false);
    this.hud.setVisible(true);
    this.showIntro();
    this.deps.bus.emit('toast', {
      text: 'Neon Districts · seeded economy board game · F1 shows the engine state',
      kind: 'info',
    });
  }

  exit(): void {
    this.active = false;
    this.playing = false;
    this.hud.setVisible(false);
    this.hud.setDebugVisible(false);
    this.deps.setLockWanted(true);
  }

  private showIntro(): void {
    this.playing = false;
    this.presentQueue.length = 0;
    this.botTimer = -1;
    this.hud.showIntro(this.deps.save.loadRaw(SAVE_KEY) !== null);
    this.hud.setActions({ canRoll: false, canBuy: false, canEnd: false, upgradable: [], visible: false });
    this.hud.setPrompt('');
  }

  // ---- game lifecycle -------------------------------------------------------

  private startGame(bots: boolean[]): void {
    this.gameCount++;
    const gameSeed = (this.deps.seed ^ Math.imul(this.gameCount, 0x9e3779b9)) >>> 0;
    this.adoptState(createBoardGame(gameSeed, bots), `New game — seed ${gameSeed}`);
  }

  /** Install a state (new, loaded, or restored) and sync every visual. */
  private adoptState(state: BoardGameState, headline: string): void {
    this.state = state;
    this.playing = true;
    this.hud.hidePanels();
    this.hud.clearLog();
    this.hud.logLine(headline, 'round');
    this.hud.logLine(
      `— Round ${state.round}: ${playerName(state, state.current)} to ${state.phase === 'act' ? 'act' : 'roll'} —`,
      'round',
    );
    this.hud.buildCards(state);
    this.presentQueue.length = 0;
    this.botTimer = -1;
    for (let i = 0; i < 4; i++) {
      const pawn = this.parts.pawns[i];
      const p = state.players[i];
      const anim = this.pawnAnims[i];
      if (!pawn || !anim) continue;
      pawn.visible = p !== undefined && p.alive;
      if (p) {
        anim.from = p.pos;
        anim.to = p.pos;
        anim.t = 1;
      }
    }
    this.parts.dice[0].visible = true;
    this.parts.dice[1].visible = true;
    const [d1, d2] = state.lastRoll;
    this.diceAnim = { t: 2, d1: d1 || 1, d2: d2 || 1 };
    this.settleDice();
    this.refreshOwnership();
    this.afterEvents();
  }

  // ---- actions ---------------------------------------------------------------

  private get busy(): boolean {
    return this.presentQueue.length > 0 || this.presentTimer > 0;
  }

  private currentIsHuman(): boolean {
    const s = this.state;
    return s !== null && s.phase !== 'over' && !(s.players[s.current]?.bot ?? true);
  }

  private humanAction(kind: 'roll' | 'buy' | 'end'): void {
    const s = this.state;
    if (!s || this.busy || !this.currentIsHuman()) return;
    const events: BoardEvent[] = [];
    if (kind === 'roll') rollDice(s, events);
    else if (kind === 'buy') buyCurrent(s, events);
    else endTurn(s, events);
    this.present(events);
  }

  private humanUpgrade(space: number): void {
    const s = this.state;
    if (!s || this.busy || !this.currentIsHuman()) return;
    const events: BoardEvent[] = [];
    upgradeDistrict(s, space, events);
    this.present(events);
  }

  private stepBot(): void {
    const s = this.state;
    if (!s || s.phase === 'over') return;
    const events: BoardEvent[] = [];
    if (s.phase === 'roll') {
      rollDice(s, events);
    } else {
      for (const a of botActions(s)) {
        if (a.type === 'buy') buyCurrent(s, events);
        else if (a.type === 'upgrade') upgradeDistrict(s, a.space, events);
        else endTurn(s, events);
      }
    }
    this.present(events);
  }

  // ---- save / share ------------------------------------------------------------

  private saveGame(): void {
    if (!this.state) return;
    const ok = this.deps.save.saveRaw(SAVE_KEY, encodeShareCode(this.state));
    this.deps.bus.emit('toast', {
      text: ok ? 'Board game saved' : 'Save failed (storage unavailable)',
      kind: ok ? 'success' : 'warn',
    });
  }

  private loadSave(): void {
    const raw = this.deps.save.loadRaw(SAVE_KEY);
    const state = raw !== null ? decodeShareCode(raw) : null;
    if (!state) {
      this.deps.bus.emit('toast', { text: 'No valid board save found', kind: 'warn' });
      return;
    }
    this.adoptState(state, 'Game restored from save');
  }

  private shareGame(): void {
    if (!this.state) return;
    const code = encodeShareCode(this.state);
    this.hud.showShareCode(code);
    const nav = navigator as { clipboard?: { writeText(t: string): Promise<void> } };
    nav.clipboard?.writeText(code).catch(() => undefined);
  }

  private restoreFromCode(code: string): void {
    const state = decodeShareCode(code);
    if (!state) {
      this.deps.bus.emit('toast', { text: 'Invalid share code', kind: 'warn' });
      return;
    }
    this.adoptState(state, 'Game restored from share code');
  }

  // ---- presentation ---------------------------------------------------------

  private present(events: BoardEvent[]): void {
    if (events.length === 0) return;
    for (const e of events) this.presentQueue.push(e);
    this.presentTimer = 0.05;
    this.hud.setActions({ canRoll: false, canBuy: false, canEnd: false, upgradable: [], visible: true });
    this.hud.setPrompt('');
  }

  /** Fixed-step: paces event reveal + bot turns (sim time; pause freezes). */
  update(dt: number): void {
    if (!this.active) return;
    this.pollDebug(dt);
    if (!this.playing || !this.state) return;

    if (this.presentTimer > 0 || this.presentQueue.length > 0) {
      this.presentTimer -= dt;
      if (this.presentTimer > 0) return;
      const e = this.presentQueue.shift();
      if (e) {
        this.hud.logLine(
          describeBoardEvent(this.state, e),
          e.kind === 'turn-start' || e.kind === 'game-over' ? 'round' : 'event',
        );
        this.animateEvent(e);
        this.hud.updateCards(this.state);
        this.presentTimer = PRESENT_SECONDS[e.kind] ?? PRESENT_DEFAULT;
        return;
      }
      this.afterEvents();
      return;
    }

    if (this.botTimer >= 0) {
      this.botTimer -= dt;
      if (this.botTimer < 0) this.stepBot();
    }
  }

  /** Queue drained: refresh UI and decide who acts next. */
  private afterEvents(): void {
    const s = this.state;
    if (!s) return;
    this.refreshOwnership();
    this.hud.updateCards(s);

    if (s.phase === 'over') {
      const won = s.winner !== null && !(s.players[s.winner]?.bot ?? true);
      const name = s.winner !== null ? playerName(s, s.winner) : 'Nobody';
      const worths = s.players
        .map((p) => `${playerName(s, p.id)}: ${p.alive ? `${p.money} cr cash` : 'bankrupt'}`)
        .join(' · ');
      this.hud.showResults(`${name.toUpperCase()} WINS`, `${worths}.`, won);
      this.hud.setActions({ canRoll: false, canBuy: false, canEnd: false, upgradable: [], visible: false });
      this.botTimer = -1;
      return;
    }

    if (!this.currentIsHuman()) {
      this.hud.setActions({ canRoll: false, canBuy: false, canEnd: false, upgradable: [], visible: true });
      this.hud.setPrompt(`${playerName(s, s.current)} is thinking…`);
      this.botTimer = BOT_THINK_SECONDS;
      return;
    }

    const upgradable = upgradableDistricts(s, s.current).map((space) => {
      const def = BOARD[space] as DistrictDef;
      return { space, name: def.name, cost: def.upgradeCost, level: s.levels[space] ?? 0 };
    });
    this.hud.setActions({
      canRoll: s.phase === 'roll',
      canBuy: canBuyCurrent(s).ok,
      canEnd: s.phase === 'act',
      upgradable: s.phase === 'act' ? upgradable : [],
      visible: true,
    });
    this.hud.setPrompt(
      s.phase === 'roll'
        ? `${playerName(s, s.current)} — roll the dice`
        : `${playerName(s, s.current)} — buy, develop, or end the turn`,
    );
  }

  // ---- animation + audio from events ----------------------------------------

  private animateEvent(e: BoardEvent): void {
    switch (e.kind) {
      case 'roll':
        this.diceAnim = { t: 0, d1: e.d1, d2: e.d2 };
        this.deps.audio.blip(420, 0.08, 'triangle');
        break;
      case 'move': {
        const anim = this.pawnAnims[e.player];
        if (anim) {
          anim.from = e.from;
          anim.to = e.to;
          anim.t = 0;
        }
        this.deps.audio.blip(520, 0.06, 'sine');
        break;
      }
      case 'stipend':
      case 'cash':
        this.deps.audio.blip(e.kind === 'stipend' || e.amount >= 0 ? 760 : 220, 0.08, 'sine');
        break;
      case 'buy':
      case 'upgrade':
        this.refreshOwnership();
        this.deps.audio.blip(660, 0.1, 'square');
        break;
      case 'rent':
      case 'tax':
        this.deps.audio.blip(240, 0.1, 'square');
        break;
      case 'card': {
        const card = EVENT_CARDS[e.card];
        if (card && this.state) {
          this.deps.bus.emit('toast', {
            text: `${playerName(this.state, e.player)} draws ${card.name}: ${card.text}`,
            kind: 'info',
          });
        }
        this.deps.audio.blip(560, 0.09, 'sine');
        break;
      }
      case 'liquidate-upgrade':
      case 'liquidate-property':
        this.refreshOwnership();
        this.deps.audio.blip(180, 0.12, 'sawtooth');
        break;
      case 'bankrupt': {
        this.refreshOwnership();
        const pawn = this.parts.pawns[e.player];
        if (pawn) pawn.visible = false;
        if (this.state) {
          this.deps.bus.emit('toast', {
            text: `${playerName(this.state, e.player)} is bankrupt and out of the game`,
            kind: 'warn',
          });
        }
        this.deps.audio.blip(90, 0.3, 'sawtooth');
        break;
      }
      case 'surge-recall':
        this.deps.audio.blip(120, 0.25, 'sawtooth');
        break;
      case 'game-over':
        this.deps.audio.blip(this.state && !(this.state.players[e.winner]?.bot ?? true) ? 990 : 330, 0.3, 'square');
        break;
      default:
        break;
    }
  }

  /** Owner strips + development markers from real ownership state. */
  private refreshOwnership(): void {
    const s = this.state;
    if (!s) return;
    for (let i = 0; i < BOARD_SIZE; i++) {
      const strip = this.parts.ownerStrips[i];
      const stripMat = this.parts.ownerStripMats[i];
      const owner = s.ownership[i] ?? -1;
      if (strip && stripMat) {
        strip.visible = owner >= 0;
        if (owner >= 0) stripMat.color.set(PLAYER_HEX[owner] as number);
      }
      const markers = this.parts.levelMarkers[i];
      if (markers) {
        const level = s.levels[i] ?? 0;
        for (let m = 0; m < markers.length; m++) {
          (markers[m] as THREE.Mesh).visible = m < level;
        }
      }
    }
  }

  private settleDice(): void {
    for (let d = 0; d < 2; d++) {
      const die = this.parts.dice[d] as THREE.Mesh;
      const v = d === 0 ? this.diceAnim.d1 : this.diceAnim.d2;
      const [rx, ry, rz] = diceSettleRotation(v);
      die.rotation.set(rx, ry, rz);
      die.position.y = 0.85;
    }
  }

  // ---- debug (F1) ---------------------------------------------------------------

  private pollDebug(dt: number): void {
    const visible = this.deps.isDebugVisible() && this.playing;
    this.hud.setDebugVisible(visible);
    if (!visible || !this.state) return;
    this.debugTimer -= dt;
    if (this.debugTimer > 0) return;
    this.debugTimer = 0.25;
    const s = this.state;
    const lines: string[] = [
      'NEON DISTRICTS — engine state',
      `seed ${s.seed}  rng cursor ${s.rngState}`,
      `round ${s.round}/${s.turnCap}  phase ${s.phase}  current ${playerName(s, s.current)}`,
      `last roll ${s.lastRoll[0]}+${s.lastRoll[1]}  doubles streak ${s.doublesCount}`,
      `deck ${s.deckIndex}/${s.deckOrder.length}  next [${s.deckOrder
        .slice(s.deckIndex, s.deckIndex + 4)
        .map((c) => EVENT_CARDS[c]?.name ?? '?')
        .join(', ')}]`,
      'players:',
    ];
    for (const p of s.players) {
      const props: string[] = [];
      for (let i = 0; i < BOARD_SIZE; i++) {
        if (s.ownership[i] === p.id) {
          const lvl = s.levels[i] ?? 0;
          props.push(`${i}${lvl > 0 ? `L${lvl}` : ''}`);
        }
      }
      lines.push(
        ` ${playerName(s, p.id)}${p.alive ? '' : ' (OUT)'}  ${p.money} cr  @${p.pos} ${
          BOARD[p.pos]?.name ?? ''
        }  owns [${props.join(' ')}]`,
      );
    }
    lines.push(
      `ownership map ${s.ownership.map((o) => (o < 0 ? '.' : String(o + 1))).join('')}`,
    );
    lines.push(`level map     ${s.levels.map((l) => String(l)).join('')}`);
    this.hud.setDebugText(lines.join('\n'));
  }

  // ---- per-frame visuals -----------------------------------------------------

  /** Called from the App render loop while board mode is active. */
  frame(elapsed: number, frameDt: number): void {
    // Pawn glides (forward around the ring, with a little hop).
    for (let i = 0; i < this.pawnAnims.length; i++) {
      const anim = this.pawnAnims[i];
      const pawn = this.parts.pawns[i];
      if (!anim || !pawn || !pawn.visible) continue;
      anim.t = Math.min(1, anim.t + frameDt * 1.6);
      const steps = (anim.to - anim.from + BOARD_SIZE) % BOARD_SIZE;
      const ease = anim.t * anim.t * (3 - 2 * anim.t); // smoothstep
      const idx = anim.from + steps * ease;
      spaceCenter(idx % BOARD_SIZE, this.scratchA);
      const off = PAWN_OFFSETS[i] as [number, number];
      const hop = anim.t < 1 ? Math.abs(Math.sin(anim.t * Math.PI * Math.max(1, steps) * 0.5)) * 0.5 : 0;
      pawn.position.set(
        this.scratchA.x + off[0],
        hop + (anim.t >= 1 ? Math.sin(elapsed * 2 + i) * 0.04 : 0),
        this.scratchA.z + off[1],
      );
    }

    // Dice: tumble then settle on the REAL rolled faces.
    const da = this.diceAnim;
    if (da.t < 1) {
      da.t = Math.min(1, da.t + frameDt * 1.4);
      if (da.t < 0.7) {
        for (let d = 0; d < 2; d++) {
          const die = this.parts.dice[d] as THREE.Mesh;
          die.rotation.set(
            elapsed * (9 + d * 3),
            elapsed * (7 - d * 2),
            elapsed * (5 + d),
          );
          die.position.y = 0.85 + Math.abs(Math.sin(elapsed * 10 + d)) * 1.1 * (1 - da.t);
        }
      } else {
        this.settleDice();
      }
    }

    // Camera: high orbit with a slow sway, drifting toward the active pawn.
    const s = this.state;
    const focusPawn =
      s && s.phase !== 'over' ? this.parts.pawns[s.current] : undefined;
    if (focusPawn && focusPawn.visible) {
      this.scratchB.copy(focusPawn.position).multiplyScalar(0.35);
    } else {
      this.scratchB.set(0, 0, 0);
    }
    this.camFocus.set(this.scratchB.x, 0.5, this.scratchB.z);
    const sway = Math.sin(elapsed * 0.1) * 4;
    this.camPos.set(sway + this.scratchB.x * 0.3, 26.5, 25 + this.scratchB.z * 0.2);
    const lerp = 1 - Math.exp(-3 * frameDt);
    this.camera.position.lerp(this.camPos, lerp);
    this.camTarget.lerp(this.camFocus, lerp);
    this.camera.lookAt(this.camTarget);
  }
}
