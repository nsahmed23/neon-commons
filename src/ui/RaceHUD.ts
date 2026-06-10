/**
 * Race HUD + panels (DOM, editorial register): mode-select panel,
 * countdown, live lap/time/position/speed readouts, wrong-way and
 * missed-checkpoint warnings, and the results screen. Every readout is
 * fed real values by RaceMode; nothing here invents state. DOM writes
 * are change-gated so steady frames touch nothing.
 */

import { formatMs } from '../systems/race/Checkpoints';

export interface RaceResultRow {
  position: number;
  name: string;
  isPlayer: boolean;
  finished: boolean;
  finishMs: number;
  bestLapMs: number;
  lapsDone: number;
}

export interface RaceHudCallbacks {
  onStartGrandPrix: () => void;
  onStartTimeTrial: () => void;
  onRestart: () => void;
  onExitToHub: () => void;
}

export class RaceHUD {
  private root: HTMLDivElement;
  private selectPanel: HTMLDivElement;
  private resultsPanel: HTMLDivElement;
  private resultsBody: HTMLDivElement;
  private countdownEl: HTMLDivElement;
  private lapEl: HTMLDivElement;
  private timeEl: HTMLDivElement;
  private bestEl: HTMLDivElement;
  private posEl: HTMLDivElement;
  private speedEl: HTMLDivElement;
  private warnEl: HTMLDivElement;
  private ghostEl: HTMLDivElement;

  // change-gating caches
  private lastCountdown = '';
  private lastLap = '';
  private lastTime = '';
  private lastBest = '';
  private lastPos = '';
  private lastSpeed = '';
  private lastWarn = '';

  constructor(parent: HTMLElement, private cb: RaceHudCallbacks) {
    this.root = el('div', 'race-hud');
    this.root.style.display = 'none';
    parent.appendChild(this.root);

    this.countdownEl = el('div', 'race-countdown');
    this.lapEl = el('div', 'race-lap');
    this.timeEl = el('div', 'race-time');
    this.bestEl = el('div', 'race-best');
    this.posEl = el('div', 'race-pos');
    this.speedEl = el('div', 'race-speed');
    this.warnEl = el('div', 'race-warn');
    this.ghostEl = el('div', 'race-ghost-note');
    const hint = el('div', 'race-hint');
    hint.textContent =
      'W throttle · S brake/reverse · A/D steer · Space drift · R respawn · B race debug (with F1) · Esc hub';
    for (const e of [
      this.countdownEl, this.lapEl, this.timeEl, this.bestEl,
      this.posEl, this.speedEl, this.warnEl, this.ghostEl, hint,
    ]) {
      this.root.appendChild(e);
    }

    // Mode select -----------------------------------------------------
    this.selectPanel = el('div', 'race-panel');
    this.selectPanel.style.display = 'none';
    const card = el('div', 'race-card');
    const h = document.createElement('h1');
    h.textContent = 'NEON CIRCUIT';
    card.appendChild(h);
    const sub = el('div', 'race-sub');
    sub.textContent = 'seeded procedural track · ordered checkpoints · real kart physics';
    card.appendChild(sub);
    card.appendChild(
      button('GRAND PRIX — 3 laps vs 3 AI rivals', () => this.cb.onStartGrandPrix()),
    );
    card.appendChild(
      button('TIME TRIAL — 3 laps vs your ghost', () => this.cb.onStartTimeTrial()),
    );
    card.appendChild(button('Return to Hub', () => this.cb.onExitToHub(), 'danger'));
    this.selectPanel.appendChild(card);
    parent.appendChild(this.selectPanel);

    // Results ----------------------------------------------------------
    this.resultsPanel = el('div', 'race-panel');
    this.resultsPanel.style.display = 'none';
    const rcard = el('div', 'race-card');
    const rh = document.createElement('h1');
    rh.textContent = 'RACE RESULTS';
    rcard.appendChild(rh);
    this.resultsBody = el('div', 'race-results-body');
    rcard.appendChild(this.resultsBody);
    rcard.appendChild(button('Race Again', () => this.cb.onRestart()));
    rcard.appendChild(button('Change Event', () => this.showSelect()));
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

  setGhostNote(text: string): void {
    this.ghostEl.textContent = text;
    this.ghostEl.style.display = text ? 'block' : 'none';
  }

  setCountdown(text: string): void {
    if (text === this.lastCountdown) return;
    this.lastCountdown = text;
    this.countdownEl.textContent = text;
    this.countdownEl.style.display = text ? 'block' : 'none';
  }

  setLap(lap: number, total: number): void {
    const s = `LAP ${Math.min(lap + 1, total)}/${total}`;
    if (s !== this.lastLap) {
      this.lastLap = s;
      this.lapEl.textContent = s;
    }
  }

  setTimes(currentLapMs: number, bestLapMs: number): void {
    const t = formatMs(currentLapMs);
    if (t !== this.lastTime) {
      this.lastTime = t;
      this.timeEl.textContent = t;
    }
    const b = `BEST ${formatMs(bestLapMs)}`;
    if (b !== this.lastBest) {
      this.lastBest = b;
      this.bestEl.textContent = b;
    }
  }

  setPosition(pos: number, total: number): void {
    const s = total > 1 ? `POS ${pos}/${total}` : '';
    if (s !== this.lastPos) {
      this.lastPos = s;
      this.posEl.textContent = s;
    }
  }

  setSpeed(metersPerSecond: number, boosting: boolean): void {
    const s = `${Math.round(Math.abs(metersPerSecond) * 3.6)} km/h${boosting ? ' · BOOST' : ''}`;
    if (s !== this.lastSpeed) {
      this.lastSpeed = s;
      this.speedEl.textContent = s;
      this.speedEl.classList.toggle('boosting', boosting);
    }
  }

  setWarning(wrongWay: boolean, missed: boolean): void {
    const s = wrongWay ? 'WRONG WAY' : missed ? 'CHECKPOINT MISSED — GO BACK' : '';
    if (s === this.lastWarn) return;
    this.lastWarn = s;
    this.warnEl.textContent = s;
    this.warnEl.style.display = s ? 'block' : 'none';
  }

  showResults(rows: RaceResultRow[], playerLapTimes: readonly number[]): void {
    this.resultsBody.textContent = '';
    const table = document.createElement('table');
    table.className = 'race-table';
    const head = document.createElement('tr');
    for (const cell of ['#', 'RACER', 'TIME', 'BEST LAP']) {
      const th = document.createElement('th');
      th.textContent = cell;
      head.appendChild(th);
    }
    table.appendChild(head);
    for (const r of rows) {
      const tr = document.createElement('tr');
      if (r.isPlayer) tr.className = 'race-row-player';
      const cells = [
        String(r.position),
        r.name,
        r.finished ? formatMs(r.finishMs) : `DNF (lap ${r.lapsDone + 1})`,
        formatMs(r.bestLapMs),
      ];
      for (const c of cells) {
        const td = document.createElement('td');
        td.textContent = c;
        tr.appendChild(td);
      }
      table.appendChild(tr);
    }
    this.resultsBody.appendChild(table);

    if (playerLapTimes.length > 0) {
      const laps = el('div', 'race-laptimes');
      laps.textContent =
        'Your laps: ' + playerLapTimes.map((m, i) => `L${i + 1} ${formatMs(m)}`).join(' · ');
      this.resultsBody.appendChild(laps);
    }
    this.selectPanel.style.display = 'none';
    this.resultsPanel.style.display = 'flex';
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
