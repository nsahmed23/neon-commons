/**
 * Battle mode: 3v3 turn-based tactical robots. All rules live in the
 * pure modules under src/systems/battle (Resolution/TurnOrder/BattleAI
 * etc.); this class owns the interactive loop — player move/target
 * selection, AI turns, paced presentation of resolution events into
 * the battle log, transform-only animations, camera framing, and the
 * win/lose -> hub lifecycle. Every log sentence comes from
 * describeEvent over real events; debug mode (F1) additionally prints
 * the AI's per-option score breakdown.
 */

import * as THREE from 'three';
import type { GameBus } from '../core/EventBus';
import type { Input } from '../core/Input';
import { Rng } from '../core/Rng';
import type { AudioSystem } from '../systems/Audio';
import {
  chooseAction,
  formatScoreBreakdown,
  type AIDecision,
} from '../systems/battle/BattleAI';
import { getMove, type MoveDef } from '../systems/battle/Moves';
import {
  canUse,
  checkLockup,
  createBattle,
  describeEvent,
  endOfUnitTurn,
  executeMove,
  validTargets,
  winner,
  type BattleEvent,
  type BattleState,
  type UnitState,
} from '../systems/battle/Resolution';
import { computeTurnOrder } from '../systems/battle/TurnOrder';
import { ENEMY_TEAM, PLAYER_TEAM } from '../systems/battle/Units';
import { BattleHUD } from '../ui/BattleHUD';
import { buildBattleScene, slotPosition, type BattleSceneParts } from './battle/BattleScene';
import type { Mode } from './Mode';

type Phase = 'select' | 'pick-move' | 'pick-target' | 'present' | 'results';

const PRESENT_SECONDS: Partial<Record<BattleEvent['kind'], number>> = {
  'move-used': 0.55,
  damage: 0.6,
  heal: 0.45,
  ko: 0.9,
};
const PRESENT_DEFAULT = 0.32;
const MAX_DEBUG_OPTIONS = 6;

interface AnimState {
  kind: 'none' | 'lunge' | 'flinch' | 'pulse' | 'ko';
  t: number;
  /** lunge direction in world space */
  dx: number;
  dz: number;
}

export interface BattleModeDeps {
  parent: HTMLElement;
  bus: GameBus;
  input: Input;
  audio: AudioSystem;
  seed: number;
  isDebugVisible: () => boolean;
  exitToHub: () => void;
  setLockWanted: (wanted: boolean) => void;
}

export class BattleMode implements Mode {
  readonly id = 'battle';
  readonly camera: THREE.PerspectiveCamera;

  get scene(): THREE.Scene {
    return this.parts.scene;
  }

  get entityCount(): number {
    return this.parts.entityCount;
  }

  private parts: BattleSceneParts;
  private hud: BattleHUD;
  private active = false;
  private phase: Phase = 'select';
  private state: BattleState;
  private rng = new Rng(0);
  private battleCount = 0;

  private turnQueue: number[] = [];
  private queueIdx = 0;
  private activeUnitId: number | null = null;
  private pendingMove: MoveDef | null = null;
  private targetables: number[] = [];

  // Presentation queue (events revealed one by one into the log).
  private presentQueue: BattleEvent[] = [];
  private presentTimer = 0;

  // Animation state per robot + camera scratch (no frame allocations).
  private anims: AnimState[] = [];
  private camPos = new THREE.Vector3(0, 16, 27);
  private camTarget = new THREE.Vector3(0, 1.5, 0);
  private camFocus = new THREE.Vector3(0, 1.5, 0);
  private deadSink: number[] = [];

  constructor(private deps: BattleModeDeps) {
    this.state = createBattle(PLAYER_TEAM, ENEMY_TEAM);
    this.parts = buildBattleScene(this.state.units);
    for (let i = 0; i < this.state.units.length; i++) {
      this.anims.push({ kind: 'none', t: 1, dx: 0, dz: 0 });
      this.deadSink.push(0);
    }

    this.camera = new THREE.PerspectiveCamera(55, innerWidth / innerHeight, 0.1, 400);
    this.camera.position.copy(this.camPos);
    this.camera.lookAt(this.camTarget);
    window.addEventListener('resize', () => {
      this.camera.aspect = innerWidth / innerHeight;
      this.camera.updateProjectionMatrix();
    });

    this.hud = new BattleHUD(deps.parent, {
      onStart: () => this.startBattle(),
      onRematch: () => this.startBattle(),
      onExitToHub: () => this.deps.exitToHub(),
      onMovePicked: (slot) => this.onMovePicked(slot),
      onTargetPicked: (unitId) => this.onTargetPicked(unitId),
      onCancelTarget: () => this.cancelTarget(),
    });
    this.hud.buildCards(this.state.units);

    this.deps.input.onEdge('escape', () => {
      if (this.active) this.deps.exitToHub();
    });
    window.addEventListener('keydown', (e) => this.onKeyDown(e));
  }

  // ---- Mode lifecycle -----------------------------------------------------

  enter(): void {
    this.active = true;
    this.phase = 'select';
    this.deps.setLockWanted(false);
    this.hud.setVisible(true);
    this.hud.showSelect();
    this.hud.hideMoves();
    this.hud.setPrompt('');
    this.refreshCards();
    this.deps.bus.emit('toast', {
      text: 'Circuit Colosseum · 3v3 tactical robots · F1 shows AI reasoning',
      kind: 'info',
    });
  }

  exit(): void {
    this.active = false;
    this.phase = 'select';
    this.hud.setVisible(false);
    this.deps.setLockWanted(true);
  }

  // ---- battle lifecycle -------------------------------------------------

  private startBattle(): void {
    this.battleCount++;
    this.state = createBattle(PLAYER_TEAM, ENEMY_TEAM);
    // A fresh deterministic stream per bout, derived from the world seed.
    this.rng = new Rng((this.deps.seed ^ Math.imul(this.battleCount, 0x9e3779b9)) >>> 0);
    this.hud.buildCards(this.state.units);
    this.hud.hidePanels();
    this.hud.clearLog();
    this.hud.logLine(`Bout ${this.battleCount} — seed ${this.deps.seed}`, 'round');
    this.presentQueue.length = 0;
    this.pendingMove = null;
    this.resetRigs();
    this.beginRound();
    this.advanceTurn();
  }

  private resetRigs(): void {
    for (let i = 0; i < this.parts.robots.length; i++) {
      const rig = this.parts.robots[i];
      if (!rig) continue;
      rig.group.position.copy(rig.home);
      rig.group.rotation.set(0, rig.facing, 0);
      rig.group.visible = true;
      rig.bodyMat.emissiveIntensity = 0.18;
      const anim = this.anims[i];
      if (anim) {
        anim.kind = 'none';
        anim.t = 1;
      }
      this.deadSink[i] = 0;
    }
  }

  private beginRound(): void {
    this.turnQueue = computeTurnOrder(this.state);
    this.queueIdx = 0;
    this.hud.logLine(`— Round ${this.state.round} —`, 'round');
  }

  /** Walk the turn queue; hand control to the player or run the AI. */
  private advanceTurn(): void {
    const win = winner(this.state);
    if (win !== null) {
      this.endBattle(win);
      return;
    }
    if (this.queueIdx >= this.turnQueue.length) {
      this.state.round++;
      this.beginRound();
    }
    const unitId = this.turnQueue[this.queueIdx++];
    if (unitId === undefined) {
      this.advanceTurn();
      return;
    }
    const unit = this.state.units[unitId];
    if (!unit || !unit.alive) {
      this.advanceTurn();
      return;
    }
    this.activeUnitId = unitId;
    this.refreshCards();

    const events: BattleEvent[] = [];
    if (checkLockup(unit, events)) {
      endOfUnitTurn(this.state, unitId, events);
      this.present(events);
      return;
    }

    if (unit.side === 1) {
      const decision = chooseAction(this.state, unitId, this.rng);
      if (!decision) {
        endOfUnitTurn(this.state, unitId, events);
        this.present(events);
        return;
      }
      this.logAIDebug(unit, decision);
      executeMove(this.state, decision.action, this.rng, events);
      endOfUnitTurn(this.state, unitId, events);
      this.present(events);
      return;
    }

    // Player unit: open the move panel.
    this.phase = 'pick-move';
    const legal = unit.spec.moves.map((moveId) => {
      const move = getMove(moveId);
      return canUse(unit, move) && validTargets(this.state, unit, move).length > 0;
    });
    this.hud.showMoves(unit, legal);
    const anyLegal = legal.some((v) => v);
    this.hud.setPrompt(
      anyLegal
        ? `${unit.spec.name} — choose a move (1-4)`
        : `${unit.spec.name} is out of energy — press 1-4 to Vent`,
    );
    if (!anyLegal) {
      // All four moves unaffordable: the turn becomes a Vent.
      this.performAction('vent', unit.id);
    }
  }

  /** Debug-mode AI transparency: per-option named score breakdown. */
  private logAIDebug(unit: UnitState, decision: AIDecision): void {
    if (!this.deps.isDebugVisible()) return;
    this.hud.logLine(`[AI] ${unit.spec.name} scored ${decision.options.length} options:`, 'debug');
    for (const o of decision.options.slice(0, MAX_DEBUG_OPTIONS)) {
      const move = getMove(o.moveId);
      const target = this.state.units[o.targetId];
      const mark = o === decision.chosen ? '> ' : '  ';
      this.hud.logLine(
        `${mark}${move.name} -> ${target?.spec.name ?? '?'}: ${formatScoreBreakdown(o)}`,
        'debug',
      );
    }
  }

  // ---- player input ---------------------------------------------------------

  private onMovePicked(slot: number): void {
    if (this.phase !== 'pick-move' || this.activeUnitId === null) return;
    const unit = this.state.units[this.activeUnitId];
    if (!unit) return;
    const moveId = unit.spec.moves[slot];
    if (moveId === undefined) return;
    const move = getMove(moveId);
    if (!canUse(unit, move)) {
      // Out-of-energy turns fall back to Vent regardless of the slot.
      if (unit.spec.moves.every((id) => !canUse(unit, getMove(id)))) {
        this.performAction('vent', unit.id);
      } else {
        this.deps.audio.blip(160, 0.06, 'sine');
      }
      return;
    }
    const targets = validTargets(this.state, unit, move);
    if (targets.length === 0) return;
    if (move.target === 'self' || targets.length === 1) {
      this.performAction(move.id, (targets[0] as UnitState).id);
      return;
    }
    this.pendingMove = move;
    this.phase = 'pick-target';
    this.targetables = targets.map((t) => t.id);
    this.refreshCards();
    this.hud.setPrompt(
      `${move.name} — choose a target (1-${targets.length}, click a card, X cancels)`,
    );
  }

  private onTargetPicked(unitId: number): void {
    if (this.phase !== 'pick-target' || !this.pendingMove) return;
    if (!this.targetables.includes(unitId)) return;
    this.performAction(this.pendingMove.id, unitId);
  }

  private cancelTarget(): void {
    if (this.phase !== 'pick-target') return;
    this.pendingMove = null;
    this.targetables = [];
    this.phase = 'pick-move';
    this.refreshCards();
    const unit = this.activeUnitId !== null ? this.state.units[this.activeUnitId] : null;
    if (unit) this.hud.setPrompt(`${unit.spec.name} — choose a move (1-4)`);
  }

  private performAction(moveId: string, targetId: number): void {
    if (this.activeUnitId === null) return;
    const events: BattleEvent[] = [];
    executeMove(this.state, { userId: this.activeUnitId, moveId, targetId }, this.rng, events);
    endOfUnitTurn(this.state, this.activeUnitId, events);
    this.pendingMove = null;
    this.targetables = [];
    this.present(events);
  }

  private onKeyDown(e: KeyboardEvent): void {
    if (!this.active) return;
    if (this.phase === 'pick-move') {
      if (e.code.startsWith('Digit')) {
        const n = Number(e.code.slice(5));
        if (n >= 1 && n <= 4) this.onMovePicked(n - 1);
      }
    } else if (this.phase === 'pick-target') {
      if (e.code === 'KeyX') {
        this.cancelTarget();
        return;
      }
      if (e.code.startsWith('Digit')) {
        const n = Number(e.code.slice(5));
        const id = this.targetables[n - 1];
        if (id !== undefined) this.onTargetPicked(id);
      }
    }
  }

  // ---- presentation ---------------------------------------------------------

  private present(events: BattleEvent[]): void {
    this.phase = 'present';
    this.hud.hideMoves();
    this.hud.setPrompt('');
    for (const e of events) this.presentQueue.push(e);
    this.presentTimer = 0.1;
  }

  /** Fixed-step: paces the event reveal (sim time, so pause freezes it). */
  update(dt: number): void {
    if (!this.active || this.phase !== 'present') return;
    this.presentTimer -= dt;
    if (this.presentTimer > 0) return;
    const e = this.presentQueue.shift();
    if (e) {
      this.hud.logLine(describeEvent(this.state, e));
      this.animateEvent(e);
      this.refreshCards();
      this.presentTimer = PRESENT_SECONDS[e.kind] ?? PRESENT_DEFAULT;
      return;
    }
    // Queue drained: next turn (or results).
    this.advanceTurn();
  }

  private endBattle(win: 0 | 1): void {
    this.phase = 'results';
    this.activeUnitId = null;
    this.refreshCards();
    const survivors = this.state.units
      .filter((u) => u.alive && u.side === win)
      .map((u) => u.spec.name);
    this.hud.showResults(win === 0, this.state.round, survivors);
    this.deps.audio.blip(win === 0 ? 990 : 120, 0.3, 'square');
    this.deps.bus.emit('toast', {
      text: win === 0 ? 'Victory — enemy team disabled' : 'Defeat — your team is down',
      kind: win === 0 ? 'success' : 'warn',
    });
  }

  private refreshCards(): void {
    this.hud.updateUnits(
      this.state.units,
      this.phase === 'pick-move' || this.phase === 'pick-target' ? this.activeUnitId : null,
      this.phase === 'pick-target' ? this.targetables : [],
    );
  }

  // ---- animation + audio from events ---------------------------------------

  private startAnim(unitId: number, kind: AnimState['kind'], towardId?: number): void {
    const anim = this.anims[unitId];
    if (!anim) return;
    anim.kind = kind;
    anim.t = 0;
    if (towardId !== undefined && towardId !== unitId) {
      const from = slotPosition(unitId);
      const to = slotPosition(towardId);
      const dx = to.x - from.x;
      const dz = to.z - from.z;
      const len = Math.hypot(dx, dz) || 1;
      anim.dx = dx / len;
      anim.dz = dz / len;
    } else {
      anim.dx = 0;
      anim.dz = 0;
    }
  }

  private animateEvent(e: BattleEvent): void {
    switch (e.kind) {
      case 'move-used':
        this.startAnim(e.userId, 'lunge', e.targetId);
        this.deps.audio.blip(480, 0.07, 'triangle');
        break;
      case 'damage':
        this.startAnim(e.targetId, 'flinch');
        this.deps.audio.blip(e.typeMult >= 2 ? 320 : 220, 0.1, 'square');
        break;
      case 'heal':
        this.startAnim(e.targetId, 'pulse');
        this.deps.audio.hum(180, 0.3);
        break;
      case 'status-applied':
      case 'status-refreshed':
        this.startAnim(e.targetId, 'pulse');
        this.deps.audio.blip(560, 0.08, 'sine');
        break;
      case 'stat-change':
        this.startAnim(e.targetId, 'pulse');
        this.deps.audio.blip(e.delta > 0 ? 700 : 240, 0.08, 'sine');
        break;
      case 'ko':
        this.startAnim(e.targetId, 'ko');
        this.deps.audio.blip(90, 0.35, 'sawtooth');
        break;
      case 'status-tick':
        this.startAnim(e.targetId, 'pulse');
        break;
      default:
        break;
    }
  }

  // ---- per-frame visuals -------------------------------------------------------

  /** Called from the App render loop while battle mode is active. */
  frame(elapsed: number, frameDt: number): void {
    for (let i = 0; i < this.parts.robots.length; i++) {
      const rig = this.parts.robots[i];
      const anim = this.anims[i];
      const unit = this.state.units[i];
      if (!rig || !anim || !unit) continue;

      // Base pose.
      let x = rig.home.x;
      let z = rig.home.z;
      let y = unit.alive ? Math.sin(elapsed * 2 + i * 1.3) * 0.06 : 0;
      let tilt = 0;

      anim.t = Math.min(1.5, anim.t + frameDt * 2.2);
      const t = anim.t;
      if (anim.kind === 'lunge' && t < 1) {
        const arc = Math.sin(Math.min(1, t) * Math.PI); // out and back
        x += anim.dx * arc * 3.2;
        z += anim.dz * arc * 3.2;
      } else if (anim.kind === 'flinch' && t < 1) {
        const fade = 1 - t;
        x += Math.sin(t * 40) * 0.22 * fade;
        rig.bodyMat.emissiveIntensity = 0.18 + fade * 0.9;
      } else if (anim.kind === 'pulse' && t < 1) {
        rig.bodyMat.emissiveIntensity = 0.18 + Math.sin(t * Math.PI) * 0.55;
      } else if (anim.kind === 'ko') {
        const sink = Math.min(1, this.deadSink[i] ?? 0);
        this.deadSink[i] = sink + frameDt * 1.2;
        tilt = Math.min(1, sink) * (Math.PI / 2.2);
        y = -Math.min(1, sink) * 0.6;
        rig.bodyMat.emissiveIntensity = Math.max(0.04, 0.18 - sink * 0.2);
      } else {
        rig.bodyMat.emissiveIntensity = 0.18;
      }

      rig.group.position.set(x, y, z);
      rig.group.rotation.z = unit.side === 0 ? -tilt : tilt;

      // Active-unit ground ring pulse.
      const isActive = i === this.activeUnitId && this.phase !== 'results';
      rig.ringMat.opacity = isActive ? 0.45 + 0.3 * Math.sin(elapsed * 5) : 0;
    }

    // Camera: frame the arena, drifting gently toward the acting unit.
    const focusUnit =
      this.activeUnitId !== null ? this.parts.robots[this.activeUnitId] : undefined;
    const fx = focusUnit ? focusUnit.home.x * 0.35 : 0;
    const fz = focusUnit ? focusUnit.home.z * 0.35 : 0;
    this.camFocus.set(fx, 1.6, fz);
    const sway = Math.sin(elapsed * 0.12) * 3.5;
    this.camPos.set(sway + fx * 0.4, 15.5, 26 + fz * 0.2);
    const lerp = 1 - Math.exp(-3 * frameDt);
    this.camera.position.lerp(this.camPos, lerp);
    this.camTarget.lerp(this.camFocus, lerp);
    this.camera.lookAt(this.camTarget);
  }
}
