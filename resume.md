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

- [x] Stage B / Phase 3 (Race): pure race systems under
      src/systems/race (Track/Vehicle/Checkpoints/RaceAI/Ghost),
      RaceMode + RaceHUD + RaceScene, 56 race tests. Merged to main;
      browser pass deferred to Stage G (see VERIFICATION.md).
- [x] Stage C / Phase 4 (Battle): pure battle systems under
      src/systems/battle (TypeChart 4-type cycle, Statuses x6 + stat
      stages, Moves x15 + Vent, Units x6 with passives x6, Resolution
      event-sourced engine, TurnOrder, BattleAI with 9 named score
      modifiers + seeded tie breaks), BattleMode + BattleHUD +
      BattleScene (procedural robots, transform animations, unit
      cards, event-derived battle log, F1 AI score breakdown),
      47 new tests (155 total). Headless bout played to victory,
      0 console errors. Branch `stage-c-battle`.

- [x] Stage D / Phase 5 (Board): pure board systems under
      src/systems/board (BoardData 28-space ring w/ 6 color sets,
      BoardRng serializable cursor, EventDeck 16 flux cards, Engine
      event-sourced rules — rent from real ownership/sets/levels,
      echo-roll doubles + surge recall, liquidation + bankruptcy,
      last-solvent / round-cap + net-worth wins, Bot deterministic
      policy, ShareCode versioned base64 full-state round-trip),
      BoardMode + BoardHUD + BoardScene (tile ring, pawns, real-result
      dice, owner strips/level markers, seat setup, save/load + share
      codes, F1 engine-state panel), 68 new tests (223 total).
      Headless: pedestal entry, human+bot rounds, live share-code
      restore to identical state, 0 console errors.
      Branch `stage-d-board`.

- [x] Stage E / Phase 6 (Flight): pure flight systems under
      src/systems/flight (FlightModel hover-drone with per-axis
      drag/caps + altitude band + velocity-derived banking, Rings
      course generated from real WorldData skyline clearance +
      RingTracker extending the race checkpoint order pattern to 3D,
      Projectiles bounded SoA pool with swept segment-sphere collision,
      DroneAI patrol/engage/evade sentries + 3-phase boss
      shielded/vulnerable/enraged from real state, Scoring typed
      FlightEvent stream + accuracy bonus), FlightMode + FlightHUD +
      FlightScene — flies over the LIVE hub scene with its own chase
      camera, real building push-out, briefing -> active -> ending ->
      results lifecycle, reduced-motion-aware camera shake, 56 new
      tests (279 total). Headless: pedestal entry, full win run
      (10 rings ordered, boss through all phases, 2500-point breakdown
      from the event stream), organic fail path, 0 console errors.
      Branch `stage-e-flight`.

Stage A branch: `stage-a-foundation-hub` (no remote). 52 tests, tsc
clean, vite build clean, headless: 0 errors, self-audit 8/8.

## In flight

- Nothing.

## Next (other agents' stages — do NOT stub their content)

- [ ] Phase 7 Shader (`shader`): implement `Mode`, register with the
      ModeManager; the pedestal interact event already routes to
      `modes.switchTo(id)` once registered.
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
- `window.__neonApp` (main.ts): dev/audit handle used by scripted
  browser sessions to drive mode switches; keep it.
