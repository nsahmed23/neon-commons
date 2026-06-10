/**
 * Settings panel DOM. Every control writes through the controller,
 * which applies the REAL side effect immediately (sensitivity scales
 * mouse deltas, FOV changes the projection matrix, volumes drive gain
 * nodes, quality reconfigures the renderer/world, motion effects gate
 * head bob + water waves, debug toggles the overlay) and persists via
 * SaveSystem.
 */

import type { SettingsData } from '../systems/Serialization';

export interface SettingsController {
  get(): SettingsData;
  set<K extends keyof SettingsData>(key: K, value: SettingsData[K]): void;
  resetSave(): void;
}

export function buildSettingsPanel(ctrl: SettingsController): HTMLDivElement {
  const panel = document.createElement('div');
  panel.className = 'settings-panel';

  panel.appendChild(
    slider('Mouse sensitivity', 0.1, 3, 0.05, () => ctrl.get().mouseSensitivity, (v) =>
      ctrl.set('mouseSensitivity', v),
    ),
  );
  panel.appendChild(
    slider('Field of view', 50, 110, 1, () => ctrl.get().fov, (v) => ctrl.set('fov', v)),
  );
  panel.appendChild(
    slider('Master volume', 0, 1, 0.01, () => ctrl.get().masterVolume, (v) =>
      ctrl.set('masterVolume', v),
    ),
  );
  panel.appendChild(
    slider('SFX volume', 0, 1, 0.01, () => ctrl.get().sfxVolume, (v) =>
      ctrl.set('sfxVolume', v),
    ),
  );
  panel.appendChild(
    slider('Music volume', 0, 1, 0.01, () => ctrl.get().musicVolume, (v) =>
      ctrl.set('musicVolume', v),
    ),
  );

  // Quality select.
  const qRow = document.createElement('label');
  qRow.className = 'settings-row';
  const qText = document.createElement('span');
  qText.textContent = 'Quality';
  const qSel = document.createElement('select');
  for (const q of ['high', 'medium', 'low'] as const) {
    const opt = document.createElement('option');
    opt.value = q;
    opt.textContent = q;
    qSel.appendChild(opt);
  }
  qSel.value = ctrl.get().quality;
  qSel.addEventListener('change', () => {
    ctrl.set('quality', qSel.value as SettingsData['quality']);
  });
  qRow.append(qText, qSel);
  panel.appendChild(qRow);

  panel.appendChild(
    checkbox('Motion effects (head bob, waves)', () => ctrl.get().motionEffects, (v) =>
      ctrl.set('motionEffects', v),
    ),
  );
  panel.appendChild(
    checkbox('Debug overlay (F1)', () => ctrl.get().debugOverlay, (v) =>
      ctrl.set('debugOverlay', v),
    ),
  );

  const reset = document.createElement('button');
  reset.className = 'menu-button danger';
  reset.textContent = 'Reset save (settings to defaults)';
  reset.addEventListener('click', () => ctrl.resetSave());
  panel.appendChild(reset);

  return panel;
}

function slider(
  label: string,
  min: number,
  max: number,
  step: number,
  get: () => number,
  set: (v: number) => void,
): HTMLLabelElement {
  const row = document.createElement('label');
  row.className = 'settings-row';
  const text = document.createElement('span');
  const input = document.createElement('input');
  input.type = 'range';
  input.min = String(min);
  input.max = String(max);
  input.step = String(step);
  input.value = String(get());
  const refresh = (): void => {
    text.textContent = `${label}: ${Number(input.value).toFixed(2)}`;
  };
  input.addEventListener('input', () => {
    set(Number(input.value));
    refresh();
  });
  refresh();
  row.append(text, input);
  return row;
}

function checkbox(
  label: string,
  get: () => boolean,
  set: (v: boolean) => void,
): HTMLLabelElement {
  const row = document.createElement('label');
  row.className = 'settings-row checkbox';
  const input = document.createElement('input');
  input.type = 'checkbox';
  input.checked = get();
  input.addEventListener('change', () => set(input.checked));
  const text = document.createElement('span');
  text.textContent = label;
  row.append(input, text);
  return row;
}
