/**
 * Battle HUD (DOM, editorial register): six unit cards with real
 * HP/energy bars and text status badges, the move-selection panel
 * (click or keys 1-4), target prompts, a scrolling battle log whose
 * every line comes from describeEvent over real resolution events,
 * and the intro/results panels. Nothing here invents state; BattleMode
 * feeds it from the engine.
 */

import type { UnitState } from '../systems/battle/Resolution';
import { getMove, type MoveDef } from '../systems/battle/Moves';
import { STATUS_DEFS, type StatusId } from '../systems/battle/Statuses';
import { TYPE_LABEL } from '../systems/battle/TypeChart';
import { PASSIVE_DEFS } from '../systems/battle/Units';

const STATUS_BADGE: Record<StatusId, string> = {
  corrosion: 'CRD',
  servoLag: 'LAG',
  aegisField: 'AEG',
  nanorepair: 'RGN',
  lockup: 'LCK',
  fluxLeak: 'FLX',
};

export interface BattleHudCallbacks {
  onStart: () => void;
  onRematch: () => void;
  onExitToHub: () => void;
  onMovePicked: (slot: number) => void;
  onTargetPicked: (unitId: number) => void;
  onCancelTarget: () => void;
}

interface CardRefs {
  root: HTMLDivElement;
  hpFill: HTMLDivElement;
  hpText: HTMLDivElement;
  enFill: HTMLDivElement;
  enText: HTMLDivElement;
  statusRow: HTMLDivElement;
}

export class BattleHUD {
  private root: HTMLDivElement;
  private cards: CardRefs[] = [];
  private cardsLeft: HTMLDivElement;
  private cardsRight: HTMLDivElement;
  private logEl: HTMLDivElement;
  private movePanel: HTMLDivElement;
  private moveButtons: HTMLButtonElement[] = [];
  private promptEl: HTMLDivElement;
  private selectPanel: HTMLDivElement;
  private resultsPanel: HTMLDivElement;
  private resultsTitle: HTMLHeadingElement;
  private resultsBody: HTMLDivElement;

  constructor(parent: HTMLElement, private cb: BattleHudCallbacks) {
    this.root = el('div', 'battle-hud');
    this.root.style.display = 'none';
    parent.appendChild(this.root);

    this.cardsLeft = el('div', 'battle-cards battle-cards-left');
    this.cardsRight = el('div', 'battle-cards battle-cards-right');
    this.root.appendChild(this.cardsLeft);
    this.root.appendChild(this.cardsRight);

    this.promptEl = el('div', 'battle-prompt');
    this.root.appendChild(this.promptEl);

    this.movePanel = el('div', 'battle-moves');
    this.movePanel.style.display = 'none';
    for (let i = 0; i < 4; i++) {
      const b = document.createElement('button');
      b.className = 'battle-move-btn';
      const slot = i;
      b.addEventListener('click', () => this.cb.onMovePicked(slot));
      this.movePanel.appendChild(b);
      this.moveButtons.push(b);
    }
    this.root.appendChild(this.movePanel);

    this.logEl = el('div', 'battle-log');
    this.root.appendChild(this.logEl);

    const hint = el('div', 'battle-hint');
    hint.textContent = '1-4 pick a move · 1-3 or click a card to target · X cancel · F1 shows AI reasoning · Esc hub';
    this.root.appendChild(hint);

    // Intro panel ------------------------------------------------------
    this.selectPanel = el('div', 'battle-panel');
    this.selectPanel.style.display = 'none';
    const card = el('div', 'battle-card-panel');
    const h = document.createElement('h1');
    h.textContent = 'CIRCUIT COLOSSEUM';
    card.appendChild(h);
    const sub = el('div', 'battle-sub');
    sub.textContent = '3v3 tactical robots · type chart · scored enemy AI with visible reasoning';
    card.appendChild(sub);
    card.appendChild(button('ENGAGE — 3v3 exhibition bout', () => this.cb.onStart()));
    card.appendChild(button('Return to Hub', () => this.cb.onExitToHub(), 'danger'));
    this.selectPanel.appendChild(card);
    parent.appendChild(this.selectPanel);

    // Results panel ------------------------------------------------------
    this.resultsPanel = el('div', 'battle-panel');
    this.resultsPanel.style.display = 'none';
    const rcard = el('div', 'battle-card-panel');
    this.resultsTitle = document.createElement('h1');
    rcard.appendChild(this.resultsTitle);
    this.resultsBody = el('div', 'battle-results-body');
    rcard.appendChild(this.resultsBody);
    rcard.appendChild(button('Rematch', () => this.cb.onRematch()));
    rcard.appendChild(button('Return to Hub', () => this.cb.onExitToHub(), 'danger'));
    this.resultsPanel.appendChild(rcard);
    parent.appendChild(this.resultsPanel);
  }

  setVisible(v: boolean): void {
    this.root.style.display = v ? 'block' : 'none';
    if (!v) {
      this.selectPanel.style.display = 'none';
      this.resultsPanel.style.display = 'none';
    }
  }

  showSelect(): void {
    this.resultsPanel.style.display = 'none';
    this.selectPanel.style.display = 'flex';
  }

  hidePanels(): void {
    this.selectPanel.style.display = 'none';
    this.resultsPanel.style.display = 'none';
  }

  showResults(won: boolean, rounds: number, survivors: string[]): void {
    this.resultsTitle.textContent = won ? 'VICTORY' : 'DEFEAT';
    this.resultsTitle.className = won ? 'battle-win' : 'battle-loss';
    this.resultsBody.textContent =
      `${won ? 'Enemy team disabled' : 'Your team was disabled'} after ${rounds} round${rounds === 1 ? '' : 's'}.` +
      (survivors.length > 0 ? ` Still standing: ${survivors.join(', ')}.` : '');
    this.selectPanel.style.display = 'none';
    this.resultsPanel.style.display = 'flex';
  }

  // ---- unit cards -----------------------------------------------------

  buildCards(units: readonly UnitState[]): void {
    this.cardsLeft.textContent = '';
    this.cardsRight.textContent = '';
    this.cards = [];
    for (const u of units) {
      const root = el('div', 'battle-unit-card');
      root.dataset['unitId'] = String(u.id);
      const name = el('div', 'battle-unit-name');
      name.textContent = u.spec.name;
      const meta = el('div', 'battle-unit-meta');
      meta.textContent = `${TYPE_LABEL[u.spec.type]} · ${PASSIVE_DEFS[u.spec.passive].name}`;
      meta.title = PASSIVE_DEFS[u.spec.passive].blurb;
      const hpBar = el('div', 'battle-bar battle-bar-hp');
      const hpFill = el('div', 'battle-bar-fill');
      hpBar.appendChild(hpFill);
      const hpText = el('div', 'battle-bar-text');
      const enBar = el('div', 'battle-bar battle-bar-en');
      const enFill = el('div', 'battle-bar-fill');
      enBar.appendChild(enFill);
      const enText = el('div', 'battle-bar-text');
      const statusRow = el('div', 'battle-status-row');
      for (const piece of [name, meta, hpBar, hpText, enBar, enText, statusRow]) {
        root.appendChild(piece);
      }
      root.addEventListener('click', () => this.cb.onTargetPicked(u.id));
      (u.side === 0 ? this.cardsLeft : this.cardsRight).appendChild(root);
      this.cards.push({ root, hpFill, hpText, enFill, enText, statusRow });
    }
  }

  updateUnits(units: readonly UnitState[], activeId: number | null, targetables: readonly number[]): void {
    for (const u of units) {
      const c = this.cards[u.id];
      if (!c) continue;
      c.hpFill.style.width = `${(100 * u.hp) / u.spec.maxHp}%`;
      c.hpText.textContent = `HP ${u.hp}/${u.spec.maxHp}`;
      c.enFill.style.width = `${(100 * u.energy) / u.spec.maxEnergy}%`;
      c.enText.textContent = `EN ${u.energy}/${u.spec.maxEnergy}`;
      c.statusRow.textContent = '';
      for (const s of u.statuses) {
        const badge = el('div', `battle-badge${STATUS_DEFS[s.id].harmful ? ' harmful' : ''}`);
        badge.textContent = `${STATUS_BADGE[s.id]} ${s.turnsLeft}`;
        badge.title = `${STATUS_DEFS[s.id].name}: ${STATUS_DEFS[s.id].blurb}`;
        c.statusRow.appendChild(badge);
      }
      const stageBits: string[] = [];
      for (const key of ['atk', 'def', 'spd'] as const) {
        const v = u.stages[key];
        if (v !== 0) stageBits.push(`${key.toUpperCase()} ${v > 0 ? '+' : ''}${v}`);
      }
      if (stageBits.length > 0) {
        const badge = el('div', 'battle-badge stage');
        badge.textContent = stageBits.join(' ');
        c.statusRow.appendChild(badge);
      }
      c.root.classList.toggle('active', u.id === activeId);
      c.root.classList.toggle('dead', !u.alive);
      c.root.classList.toggle('targetable', targetables.includes(u.id));
    }
  }

  // ---- move selection ----------------------------------------------------

  showMoves(unit: UnitState, legal: readonly boolean[]): void {
    this.movePanel.style.display = 'grid';
    for (let i = 0; i < 4; i++) {
      const b = this.moveButtons[i] as HTMLButtonElement;
      const moveId = unit.spec.moves[i] as string;
      const move: MoveDef = getMove(moveId);
      const cd = unit.cooldowns[moveId] ?? 0;
      b.textContent = `${i + 1}. ${move.name} · ${TYPE_LABEL[move.type]} · ${move.energy} EN` +
        (move.cooldown > 0 ? ` · CD ${cd > 0 ? `${cd} left` : move.cooldown}` : '');
      b.title = move.blurb;
      b.disabled = !legal[i];
    }
  }

  hideMoves(): void {
    this.movePanel.style.display = 'none';
  }

  setPrompt(text: string): void {
    this.promptEl.textContent = text;
    this.promptEl.style.display = text ? 'block' : 'none';
  }

  // ---- battle log ----------------------------------------------------------

  clearLog(): void {
    this.logEl.textContent = '';
  }

  logLine(text: string, kind: 'event' | 'debug' | 'round' = 'event'): void {
    const line = el('div', `battle-log-line ${kind}`);
    line.textContent = text;
    this.logEl.appendChild(line);
    while (this.logEl.children.length > 120) {
      this.logEl.firstChild?.remove();
    }
    this.logEl.scrollTop = this.logEl.scrollHeight;
  }
}

function el(tag: 'div', className: string): HTMLDivElement {
  const e = document.createElement(tag);
  e.className = className;
  return e;
}

function button(label: string, onClick: () => void, extra = ''): HTMLButtonElement {
  const b = document.createElement('button');
  b.className = `menu-button${extra ? ` ${extra}` : ''}`;
  b.textContent = label;
  b.addEventListener('click', onClick);
  return b;
}
