/**
 * Pause/main menu overlay (M). Hosts resume, the settings panel,
 * the stress-test trigger, and a short manifest. Opening the menu
 * releases pointer lock; closing re-arms it.
 */

import { buildSettingsPanel, type SettingsController } from './Settings';

export class Menu {
  private root: HTMLDivElement;
  private open = false;
  private settingsHost!: HTMLDivElement;
  private ctrl!: SettingsController;

  constructor(
    parent: HTMLElement,
    ctrl: SettingsController,
    private callbacks: {
      onOpenChange: (open: boolean) => void;
      onStressTest: () => void;
    },
  ) {
    this.root = document.createElement('div');
    this.root.id = 'menu';
    this.root.style.display = 'none';

    const card = document.createElement('div');
    card.id = 'menu-card';

    const title = document.createElement('h1');
    title.textContent = 'NEON COMMONS';
    const sub = document.createElement('p');
    sub.className = 'menu-sub';
    sub.textContent = 'Systems Playground · Stage A: Foundation & Hub';
    card.append(title, sub);

    const resume = document.createElement('button');
    resume.className = 'menu-button';
    resume.textContent = 'Resume (M)';
    resume.addEventListener('click', () => this.setOpen(false));
    card.appendChild(resume);

    const stress = document.createElement('button');
    stress.className = 'menu-button';
    stress.textContent = 'Run stress test (+3000 instanced props)';
    stress.addEventListener('click', () => {
      this.setOpen(false);
      this.callbacks.onStressTest();
    });
    card.appendChild(stress);

    const h2 = document.createElement('h2');
    h2.textContent = 'Settings';
    card.appendChild(h2);
    this.settingsHost = document.createElement('div');
    card.appendChild(this.settingsHost);
    this.ctrl = ctrl;

    this.root.appendChild(card);
    parent.appendChild(this.root);
  }

  get isOpen(): boolean {
    return this.open;
  }

  setOpen(open: boolean): void {
    if (open === this.open) return;
    this.open = open;
    if (open) {
      // Rebuild so controls always reflect live state (F1/F2 can have
      // changed settings since the last open) — no stale UI claims.
      this.settingsHost.replaceChildren(buildSettingsPanel(this.ctrl));
    }
    this.root.style.display = open ? 'flex' : 'none';
    this.callbacks.onOpenChange(open);
  }

  toggle(): void {
    this.setOpen(!this.open);
  }
}
