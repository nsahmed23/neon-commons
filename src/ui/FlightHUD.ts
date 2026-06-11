/**
 * Flight HUD + panels (DOM, editorial register): briefing panel, live
 * readouts (ring counter, next-ring indicator arrow, hull bar, score,
 * speed/altitude, boss phase banner), and the results panel whose
 * breakdown rows come straight from the folded event stream. Every
 * readout is fed real values by FlightMode; DOM writes are
 * change-gated so steady frames touch nothing.
 */

import type { ScoreRow } from '../systems/flight/Scoring';

export interface FlightHudCallbacks {
  onLaunch: () => void;
  onRetry: () => void;
  onExitToHub: () => void;
}

export class FlightHUD {
  private root: HTMLDivElement;
  private briefingPanel: HTMLDivElement;
  private resultsPanel: HTMLDivElement;
  private resultsCard: HTMLDivElement;
  private ringEl: HTMLDivElement;
  private arrowWrap: HTMLDivElement;
  private arrowEl: HTMLDivElement;
  private arrowDist: HTMLDivElement;
  private hullFill: HTMLDivElement;
  private hullText: HTMLDivElement;
  private scoreEl: HTMLDivElement;
  private speedEl: HTMLDivElement;
  private bossEl: HTMLDivElement;
  private warnEl: HTMLDivElement;

  // change-gating caches
  private lastRing = '';
  private lastArrow = 9999;
  private lastArrowUp = 9999;
  private lastDist = '';
  private lastHull = -1;
  private lastScore = '';
  private lastSpeed = '';
  private lastBoss = '';
  private lastWarn = '';

  constructor(parent: HTMLElement, private cb: FlightHudCallbacks) {
    this.root = el('div', 'flight-hud');
    this.root.style.display = 'none';
    parent.appendChild(this.root);

    this.ringEl = el('div', 'flight-rings');
    this.scoreEl = el('div', 'flight-score');
    this.speedEl = el('div', 'flight-speed');
    this.bossEl = el('div', 'flight-boss');
    this.warnEl = el('div', 'flight-warn');

    this.arrowWrap = el('div', 'flight-arrow-wrap');
    this.arrowEl = el('div', 'flight-arrow');
    this.arrowEl.textContent = '▲';
    this.arrowDist = el('div', 'flight-arrow-dist');
    this.arrowWrap.appendChild(this.arrowEl);
    this.arrowWrap.appendChild(this.arrowDist);

    const hull = el('div', 'flight-hull');
    const hullBar = el('div', 'flight-hull-bar');
    this.hullFill = el('div', 'flight-hull-fill');
    hullBar.appendChild(this.hullFill);
    this.hullText = el('div', 'flight-hull-text');
    hull.appendChild(hullBar);
    hull.appendChild(this.hullText);

    const hint = el('div', 'flight-hint');
    hint.textContent =
      'Mouse aim · W/S thrust · A/D strafe · Space climb · Shift sink · Click/F fire · R respawn · Esc hub';

    for (const e of [
      this.ringEl, this.scoreEl, this.speedEl, this.bossEl, this.warnEl,
      this.arrowWrap, hull, hint,
    ]) {
      this.root.appendChild(e);
    }

    // Briefing ---------------------------------------------------------
    this.briefingPanel = el('div', 'flight-panel');
    this.briefingPanel.style.display = 'none';
    const card = el('div', 'flight-card');
    const h = document.createElement('h1');
    h.textContent = 'SKYLINE RUN';
    card.appendChild(h);
    const sub = el('div', 'flight-sub');
    sub.textContent = 'hover-drone over the live city · 10 ordered rings · sentries · the WARDEN';
    card.appendChild(sub);
    const brief = el('div', 'flight-brief');
    for (const line of [
      'Thread all 10 rings IN ORDER — the course rides the real skyline.',
      'Sentry drones patrol the route: outrun them or shoot them down.',
      'Past the final ring, the WARDEN waits over the lake. Its shield holds while its two escorts live: kill the escorts, then burn it down before it enrages.',
      'Score: 100 per ring, 250 per sentry, 1000 for the WARDEN, up to 500 accuracy bonus.',
    ]) {
      const p = document.createElement('p');
      p.textContent = line;
      brief.appendChild(p);
    }
    card.appendChild(brief);
    card.appendChild(button('LAUNCH', () => this.cb.onLaunch()));
    card.appendChild(button('Return to Hub', () => this.cb.onExitToHub(), 'danger'));
    this.briefingPanel.appendChild(card);
    parent.appendChild(this.briefingPanel);

    // Results ------------------------------------------------------------
    this.resultsPanel = el('div', 'flight-panel');
    this.resultsPanel.style.display = 'none';
    this.resultsCard = el('div', 'flight-card');
    this.resultsPanel.appendChild(this.resultsCard);
    parent.appendChild(this.resultsPanel);
  }

  setVisible(v: boolean): void {
    this.root.style.display = v ? 'block' : 'none';
    if (!v) this.hidePanels();
  }

  showBriefing(): void {
    this.resultsPanel.style.display = 'none';
    this.briefingPanel.style.display = 'flex';
  }

  hidePanels(): void {
    this.briefingPanel.style.display = 'none';
    this.resultsPanel.style.display = 'none';
  }

  setRings(passed: number, total: number, bossUp: boolean): void {
    const s = bossUp ? `RINGS ${passed}/${total} · WARDEN` : `RING ${Math.min(passed + 1, total)}/${total}`;
    if (s !== this.lastRing) {
      this.lastRing = s;
      this.ringEl.textContent = s;
    }
  }

  /**
   * Next-target indicator: `bearing` is the signed angle (radians)
   * between the drone nose and the target in the horizontal plane,
   * `pitch` the vertical angle, `dist` meters. Hidden when done.
   */
  setArrow(visible: boolean, bearing: number, pitch: number, dist: number): void {
    this.arrowWrap.style.display = visible ? 'flex' : 'none';
    if (!visible) return;
    const deg = Math.round((bearing * 180) / Math.PI);
    if (Math.abs(deg - this.lastArrow) >= 2) {
      this.lastArrow = deg;
      this.arrowEl.style.transform = `rotate(${deg}deg)`;
    }
    const up = Math.round((pitch * 180) / Math.PI);
    if (Math.abs(up - this.lastArrowUp) >= 3) {
      this.lastArrowUp = up;
      this.arrowEl.style.color = up > 8 ? '#9ef7ff' : up < -8 ? '#6a5acd' : '#47e6ff';
    }
    const d = `${Math.round(dist)} m${up > 8 ? ' ↑' : up < -8 ? ' ↓' : ''}`;
    if (d !== this.lastDist) {
      this.lastDist = d;
      this.arrowDist.textContent = d;
    }
  }

  setHull(hp: number, max: number): void {
    if (hp === this.lastHull) return;
    this.lastHull = hp;
    const frac = Math.max(0, hp / max);
    this.hullFill.style.width = `${(frac * 100).toFixed(1)}%`;
    this.hullFill.classList.toggle('low', frac <= 0.3);
    this.hullText.textContent = `HULL ${Math.max(0, hp)}/${max}`;
  }

  setScore(score: number): void {
    const s = `SCORE ${score}`;
    if (s !== this.lastScore) {
      this.lastScore = s;
      this.scoreEl.textContent = s;
    }
  }

  setSpeed(metersPerSecond: number, altitude: number): void {
    const s = `${Math.round(Math.abs(metersPerSecond) * 3.6)} km/h · ALT ${Math.round(altitude)} m`;
    if (s !== this.lastSpeed) {
      this.lastSpeed = s;
      this.speedEl.textContent = s;
    }
  }

  /** Boss phase banner; empty string hides it. */
  setBossBanner(text: string, hpFrac: number): void {
    const filled = Math.max(0, Math.min(10, Math.ceil(hpFrac * 10)));
    const s = text ? `${text} ${'▰'.repeat(filled)}${'▱'.repeat(10 - filled)}` : '';
    if (s === this.lastBoss) return;
    this.lastBoss = s;
    this.bossEl.textContent = s;
    this.bossEl.style.display = s ? 'block' : 'none';
  }

  setWarning(text: string): void {
    if (text === this.lastWarn) return;
    this.lastWarn = text;
    this.warnEl.textContent = text;
    this.warnEl.style.display = text ? 'block' : 'none';
  }

  showResults(won: boolean, rows: ScoreRow[], total: number): void {
    this.resultsCard.textContent = '';
    const h = document.createElement('h1');
    h.textContent = won ? 'COURSE CLEAR' : 'DRONE DOWN';
    h.className = won ? 'flight-win' : 'flight-loss';
    this.resultsCard.appendChild(h);
    const table = document.createElement('table');
    table.className = 'flight-table';
    for (const r of rows) {
      const tr = document.createElement('tr');
      for (const c of [r.label, r.detail, `+${r.points}`]) {
        const td = document.createElement('td');
        td.textContent = c;
        tr.appendChild(td);
      }
      table.appendChild(tr);
    }
    const totalRow = document.createElement('tr');
    totalRow.className = 'flight-total';
    for (const c of ['TOTAL', '', String(total)]) {
      const td = document.createElement('td');
      td.textContent = c;
      totalRow.appendChild(td);
    }
    table.appendChild(totalRow);
    this.resultsCard.appendChild(table);
    this.resultsCard.appendChild(button('Fly Again', () => this.cb.onRetry()));
    this.resultsCard.appendChild(button('Return to Hub', () => this.cb.onExitToHub(), 'danger'));
    this.briefingPanel.style.display = 'none';
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
