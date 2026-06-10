# Neon Commons — Stage Ledger

Per HANDOVER.md section 8.6: this file plus `.checkpoints/` lets any
session resume with zero conversation history.

## Done

- [x] Stage A / Phase 1 (Foundation): fixed-timestep core, typed
      EventBus, Input (pointer lock + M/P/F1/F2/R/E/N), seeded
      GameState, SaveSystem (localStorage), DebugOverlay (measured
      values), SelfAudit (8 runtime checks), procedural Web Audio,
      settings menu with real side effects, PerformanceScaler, CI gate.
- [x] Stage A / Phase 2 (Hub): seeded procedural city (one instanced
      facade draw with shader window grid, 10k+ counted window cells),
      terrain heightfield + lake water shader + instanced vegetation,
      AABB spatial-hash collision (buildings/props/pedestals/lake
      walls/world rim) vs player capsule, minimap from real WorldData,
      HUD/ToastLog, 5 future-mode pedestals with a real interact
      system, stress test with measured before/after FPS.

Branch: `stage-a-foundation-hub` (no remote yet). 52 vitest tests,
tsc clean, vite build clean, headless browser session: 0 errors,
self-audit 8/8.

## In flight

- Nothing.

## Next (other agents' stages — do NOT stub their content)

- [ ] Phase 3 Race: implement `Mode`, register as id `race`; the Race
      pedestal interact event already routes to `modes.switchTo('race')`
      once registered.
- [ ] Phase 4 Battle (`battle`), Phase 5 Board (`board`),
      Phase 6 Flight (`flight`), Phase 7 Shader (`shader`): same seam.
- [ ] Phase 8 Optimization + release: continuous VERIFICATION.md
      already started; final pass adds before/after numbers on a real
      GPU and a deployed smoke run.

## Seams and contracts future stages rely on

- `src/modes/Mode.ts`: `Mode` interface + `ModeManager.register/switchTo`.
- `src/core/EventBus.ts` `GameEvents`: extend the map, don't fork it.
- `src/world/WorldGeneration.ts` `FUTURE_MODES`: pedestal ids/labels.
- `src/rendering/PerformanceScaler.ts`: add profile axes here, apply in
  `App.applyProfile`.
- Settings: add fields to `SettingsData` + `deserializeSettings`
  (validated), wire side effects in `App.applySetting`.
- Keep: zero allocations in the render loop, bounded instance counts,
  simulation-time-driven shader animation (pause must freeze).
