/**
 * Board HUD (DOM, editorial register): per-seat player cards with live
 * money/position/holdings, the action bar (roll, buy, upgrade, end
 * turn, save, share), a scrolling game log whose every line comes from
 * describeBoardEvent over real engine events, intro panel with seat
 * setup + save/share-code restore, results panel, and the F1 debug
 * panel (ownership map, deck state, RNG cursor). Nothing here invents
 * state; BoardMode feeds it from the engine.
 */

import { BOARD } from '../systems/board/BoardData';
import {
  playerName,
  type BoardGameState,
} from '../systems/board/Engine';

export type SeatKind = 'human' | 'bot' | 'off';

export interface BoardHudCallbacks {
  onStart: (bots: boolean[]) => void;
  onExitToHub: () => void;
  onRoll: () => void;
  onBuy: () => void;
  onUpgradePick: (space: number) => void;
  onEndTurn: () => void;
  onSave: () => void;
  onShare: () => void;
  onLoadSave: () => void;
  onRestoreCode: (code: string) => void;
  onNewGame: () => void;
}

interface CardRefs {
  root: HTMLDivElement;
  money: HTMLDivElement;
  pos: HTMLDivElement;
  holdings: HTMLDivElement;
}

const SEAT_LABEL: Record<SeatKind, string> = {
  human: 'HUMAN',
  bot: 'BOT',
  off: 'OFF',
};

export class BoardHUD {
  private root: HTMLDivElement;
  private cardsCol: HTMLDivElement;
  private cards: CardRefs[] = [];
  private logEl: HTMLDivElement;
  private promptEl: HTMLDivElement;
  private actionsEl: HTMLDivElement;
  private btnRoll: HTMLButtonElement;
  private btnBuy: HTMLButtonElement;
  private btnUpgrade: HTMLButtonElement;
  private btnEnd: HTMLButtonElement;
  private upgradePicker: HTMLDivElement;
  private debugEl: HTMLPreElement;
  private introPanel: HTMLDivElement;
  private loadSaveBtn: HTMLButtonElement;
  private codeInput: HTMLInputElement;
  private introError: HTMLDivElement;
  private resultsPanel: HTMLDivElement;
  private resultsTitle: HTMLHeadingElement;
  private resultsBody: HTMLDivElement;
  private sharePanel: HTMLDivElement;
  private shareOutput: HTMLTextAreaElement;
  private seats: SeatKind[] = ['human', 'bot', 'off', 'off'];
  private seatButtons: HTMLButtonElement[] = [];

  constructor(parent: HTMLElement, private cb: BoardHudCallbacks) {
    this.root = el('div', 'board-hud');
    this.root.style.display = 'none';
    parent.appendChild(this.root);

    this.cardsCol = el('div', 'board-cards');
    this.root.appendChild(this.cardsCol);

    this.promptEl = el('div', 'battle-prompt board-prompt');
    this.root.appendChild(this.promptEl);

    this.actionsEl = el('div', 'board-actions');
    this.btnRoll = action('Roll (R)', () => this.cb.onRoll());
    this.btnBuy = action('Buy', () => this.cb.onBuy());
    this.btnUpgrade = action('Develop', () => this.toggleUpgradePicker());
    this.btnEnd = action('End Turn', () => this.cb.onEndTurn());
    const btnSave = action('Save', () => this.cb.onSave());
    const btnShare = action('Share Code', () => this.cb.onShare());
    for (const b of [this.btnRoll, this.btnBuy, this.btnUpgrade, this.btnEnd, btnSave, btnShare]) {
      this.actionsEl.appendChild(b);
    }
    this.root.appendChild(this.actionsEl);

    this.upgradePicker = el('div', 'board-upgrade-picker');
    this.upgradePicker.style.display = 'none';
    this.root.appendChild(this.upgradePicker);

    this.logEl = el('div', 'battle-log board-log');
    this.root.appendChild(this.logEl);

    const hint = el('div', 'battle-hint');
    hint.textContent =
      'Hot-seat: the action bar always drives the CURRENT player · F1 board state · Esc hub';
    this.root.appendChild(hint);

    this.debugEl = document.createElement('pre');
    this.debugEl.className = 'board-debug';
    this.debugEl.style.display = 'none';
    this.root.appendChild(this.debugEl);

    // Share code output panel ------------------------------------------
    this.sharePanel = el('div', 'board-share');
    this.sharePanel.style.display = 'none';
    const shareLabel = el('div', 'board-share-label');
    shareLabel.textContent = 'Share code (select + copy; paste on the intro screen to restore):';
    this.sharePanel.appendChild(shareLabel);
    this.shareOutput = document.createElement('textarea');
    this.shareOutput.className = 'board-share-output';
    this.shareOutput.readOnly = true;
    this.shareOutput.rows = 3;
    this.sharePanel.appendChild(this.shareOutput);
    this.sharePanel.appendChild(
      button('Close', () => (this.sharePanel.style.display = 'none')),
    );
    this.root.appendChild(this.sharePanel);

    // Intro panel --------------------------------------------------------
    this.introPanel = el('div', 'battle-panel');
    this.introPanel.style.display = 'none';
    const card = el('div', 'battle-card-panel');
    const h = document.createElement('h1');
    h.textContent = 'NEON DISTRICTS';
    card.appendChild(h);
    const sub = el('div', 'battle-sub');
    sub.textContent =
      'district development board game · 2-4 local seats · seeded dice + flux deck · share codes';
    card.appendChild(sub);

    const seatsRow = el('div', 'board-seats');
    for (let i = 0; i < 4; i++) {
      const b = document.createElement('button');
      b.className = 'menu-button board-seat-btn';
      const seat = i;
      b.addEventListener('click', () => {
        const cycle: SeatKind[] =
          seat < 2 ? ['human', 'bot'] : ['off', 'human', 'bot'];
        const cur = cycle.indexOf(this.seats[seat] as SeatKind);
        this.seats[seat] = cycle[(cur + 1) % cycle.length] as SeatKind;
        this.renderSeatButtons();
      });
      this.seatButtons.push(b);
      seatsRow.appendChild(b);
    }
    this.renderSeatButtons();
    card.appendChild(seatsRow);

    this.introError = el('div', 'board-intro-error');
    card.appendChild(this.introError);

    card.appendChild(button('START GAME', () => this.startClicked()));
    this.loadSaveBtn = button('Load saved game', () => this.cb.onLoadSave());
    card.appendChild(this.loadSaveBtn);

    const codeRow = el('div', 'board-code-row');
    this.codeInput = document.createElement('input');
    this.codeInput.className = 'board-code-input';
    this.codeInput.placeholder = 'paste a share code (NCB1.…)';
    codeRow.appendChild(this.codeInput);
    codeRow.appendChild(
      button('Restore', () => this.cb.onRestoreCode(this.codeInput.value.trim())),
    );
    card.appendChild(codeRow);

    card.appendChild(button('Return to Hub', () => this.cb.onExitToHub(), 'danger'));
    this.introPanel.appendChild(card);
    parent.appendChild(this.introPanel);

    // Results panel ------------------------------------------------------
    this.resultsPanel = el('div', 'battle-panel');
    this.resultsPanel.style.display = 'none';
    const rcard = el('div', 'battle-card-panel');
    this.resultsTitle = document.createElement('h1');
    rcard.appendChild(this.resultsTitle);
    this.resultsBody = el('div', 'battle-results-body');
    rcard.appendChild(this.resultsBody);
    rcard.appendChild(button('New Game', () => this.cb.onNewGame()));
    rcard.appendChild(button('Return to Hub', () => this.cb.onExitToHub(), 'danger'));
    this.resultsPanel.appendChild(rcard);
    parent.appendChild(this.resultsPanel);
  }

  private renderSeatButtons(): void {
    for (let i = 0; i < 4; i++) {
      const b = this.seatButtons[i];
      if (b) b.textContent = `Seat ${i + 1}: ${SEAT_LABEL[this.seats[i] as SeatKind]}`;
    }
  }

  private startClicked(): void {
    const active = this.seats.filter((s) => s !== 'off');
    if (active.length < 2) {
      this.introError.textContent = 'At least two seats must be active.';
      return;
    }
    this.introError.textContent = '';
    this.cb.onStart(active.map((s) => s === 'bot'));
  }

  // ---- panels -----------------------------------------------------------

  setVisible(v: boolean): void {
    this.root.style.display = v ? 'block' : 'none';
    if (!v) {
      this.introPanel.style.display = 'none';
      this.resultsPanel.style.display = 'none';
      this.sharePanel.style.display = 'none';
    }
  }

  showIntro(hasSave: boolean): void {
    this.resultsPanel.style.display = 'none';
    this.introPanel.style.display = 'flex';
    this.loadSaveBtn.style.display = hasSave ? 'block' : 'none';
    this.introError.textContent = '';
  }

  hidePanels(): void {
    this.introPanel.style.display = 'none';
    this.resultsPanel.style.display = 'none';
    this.sharePanel.style.display = 'none';
  }

  showResults(title: string, body: string, won: boolean): void {
    this.resultsTitle.textContent = title;
    this.resultsTitle.className = won ? 'battle-win' : 'battle-loss';
    this.resultsBody.textContent = body;
    this.introPanel.style.display = 'none';
    this.resultsPanel.style.display = 'flex';
  }

  showShareCode(code: string): void {
    this.shareOutput.value = code;
    this.sharePanel.style.display = 'block';
    this.shareOutput.focus();
    this.shareOutput.select();
  }

  // ---- player cards -------------------------------------------------------

  buildCards(state: BoardGameState): void {
    this.cardsCol.textContent = '';
    this.cards = [];
    for (const p of state.players) {
      const root = el('div', 'battle-unit-card board-player-card');
      root.dataset['playerId'] = String(p.id);
      const name = el('div', 'battle-unit-name');
      name.textContent = playerName(state, p.id);
      name.style.color = ['#47e6ff', '#ff5470', '#ffd166', '#35ffa8'][p.id] as string;
      const money = el('div', 'board-money');
      const pos = el('div', 'board-pos');
      const holdings = el('div', 'board-holdings');
      for (const piece of [name, money, pos, holdings]) root.appendChild(piece);
      this.cardsCol.appendChild(root);
      this.cards.push({ root, money, pos, holdings });
    }
    this.updateCards(state);
  }

  updateCards(state: BoardGameState): void {
    for (const p of state.players) {
      const c = this.cards[p.id];
      if (!c) continue;
      c.money.textContent = `${p.money} cr`;
      c.pos.textContent = BOARD[p.pos]?.name ?? `Space ${p.pos}`;
      const owned = state.ownership.filter((o) => o === p.id).length;
      const levels = state.ownership.reduce(
        (sum, o, i) => (o === p.id ? sum + (state.levels[i] ?? 0) : sum),
        0,
      );
      c.holdings.textContent = p.alive
        ? `${owned} properties · ${levels} developments`
        : 'BANKRUPT';
      c.root.classList.toggle('active', p.id === state.current && state.phase !== 'over');
      c.root.classList.toggle('dead', !p.alive);
    }
  }

  // ---- actions --------------------------------------------------------------

  setActions(opts: {
    canRoll: boolean;
    canBuy: boolean;
    canEnd: boolean;
    upgradable: ReadonlyArray<{ space: number; name: string; cost: number; level: number }>;
    visible: boolean;
  }): void {
    this.actionsEl.style.display = opts.visible ? 'flex' : 'none';
    this.btnRoll.disabled = !opts.canRoll;
    this.btnBuy.disabled = !opts.canBuy;
    this.btnEnd.disabled = !opts.canEnd;
    this.btnUpgrade.disabled = opts.upgradable.length === 0;
    this.upgradePicker.textContent = '';
    if (opts.upgradable.length === 0) this.upgradePicker.style.display = 'none';
    for (const u of opts.upgradable) {
      const b = document.createElement('button');
      b.className = 'battle-move-btn';
      b.textContent = `${u.name} → level ${u.level + 1} · ${u.cost} cr`;
      b.addEventListener('click', () => {
        this.upgradePicker.style.display = 'none';
        this.cb.onUpgradePick(u.space);
      });
      this.upgradePicker.appendChild(b);
    }
  }

  private toggleUpgradePicker(): void {
    if (this.upgradePicker.childElementCount === 0) return;
    this.upgradePicker.style.display =
      this.upgradePicker.style.display === 'none' ? 'grid' : 'none';
  }

  setPrompt(text: string): void {
    this.promptEl.textContent = text;
    this.promptEl.style.display = text ? 'block' : 'none';
  }

  // ---- log + debug -------------------------------------------------------------

  clearLog(): void {
    this.logEl.textContent = '';
  }

  logLine(text: string, kind: 'event' | 'round' = 'event'): void {
    const line = el('div', `battle-log-line ${kind}`);
    line.textContent = text;
    this.logEl.appendChild(line);
    while (this.logEl.children.length > 140) {
      this.logEl.firstChild?.remove();
    }
    this.logEl.scrollTop = this.logEl.scrollHeight;
  }

  setDebugVisible(v: boolean): void {
    this.debugEl.style.display = v ? 'block' : 'none';
  }

  setDebugText(text: string): void {
    if (this.debugEl.textContent !== text) this.debugEl.textContent = text;
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

function action(label: string, onClick: () => void): HTMLButtonElement {
  const b = document.createElement('button');
  b.className = 'battle-move-btn board-action-btn';
  b.textContent = label;
  b.addEventListener('click', onClick);
  return b;
}
