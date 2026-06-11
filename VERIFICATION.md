# Verification — Stage A (Foundation & Hub)

Date: 2026-06-10. All commands run on Node 24 / Windows 11.

## Gates

| Gate | Result |
|---|---|
| `npx tsc --noEmit` | clean (strict, noUncheckedIndexedAccess, exactOptionalPropertyTypes) |
| `npx vitest run` | 52/52 tests, 6 files |
| `npm run build` | clean (one bundle-size note from Three.js itself) |
| `npm run dev` + `curl localhost:5199/` | HTTP 200, app shell served |
| Headless Chromium load (playwright-cli) | zero runtime/shader errors; in-app self-audit 8/8 PASS |

## What is tested (vitest, node env, pure modules only)

- `rng.test.ts` (10): mulberry32 determinism, bounds, fork independence
  (same label + same seed = same stream regardless of parent draws).
- `eventbus.test.ts` (8): typed on/emit/off/once, unsubscribe closures,
  once-handler not skipping siblings.
- `collision.test.ts` (10): point and region queries against the
  spatial hash (known hits AND misses), Y-band filtering, multi-cell
  dedup, capsule push-out (face, corner, center-inside cases),
  overhead boxes ignored.
- `worldgen.test.ts` (11): deep equality of two `generateWorld(seed)`
  calls, divergence across seeds, building bounds, window count > 1000
  for multiple seeds, exactly 5 pedestals with the future-mode roster,
  trees excluded from city/lake, spawn outside all footprints, terrain
  flat in city / depressed under lake.
- `perfscaler.test.ts` (6): profile monotonicity (high > medium > low on
  every axis), change notification, no-op set, F2 cycle order.
- `serialization.test.ts` (7): settings round-trip, malformed JSON,
  clamping, per-field fallback, legacy flat shape.

Runtime behaviors (pointer lock, WebGL, audio graph) are exercised by
the in-app SelfAudit (8 checks, run 2 s after boot, surfaced as a
toast) plus a scripted headless-browser session: walk into a pedestal,
prompt appears, E fires the interact event, toast confirms; N toggles
day (lit-window fraction visibly drops); F2 cycles quality with fog
changes; menu pause/resume verified after a bug fix (see below).

## Real vs. approximation

Real (backed by state/simulation/logic):
- FPS, frame time, draw calls, triangles in the overlay come from a
  wall-clock ring buffer and `renderer.info` after each render.
- Window count is the summed per-facade cell count from the same
  constants the shader uses to draw cells.
- Collision is a queried AABB spatial hash (buildings, tower, props,
  pedestals, 4 lake-shore walls, 4 world-rim walls); the player capsule
  is resolved against it every fixed step. Walking into the lake is
  physically blocked, not scripted.
- Minimap draws actual building footprints/lake/pedestals from
  WorldData and the live player position/yaw.
- Settings each have a verified side effect: sensitivity scales mouse
  deltas, FOV updates the projection matrix, volumes drive WebAudio
  gain nodes, quality swaps fog/draw-distance/instance-counts/shadows/
  pixel-ratio, motion effects gate head bob + water wave amplitude,
  debug toggles the overlay, reset clears localStorage.
- Stress test measures 90 frames, raises the prewarmed InstancedMesh
  count to 3000, measures 90 more, reports both in overlay + toast.
- Pause stops the simulation clock, which also feeds every shader
  `uTime`, so water/neon/pedestal animation genuinely freezes.

Approximations (documented, not faked):
- Windows are shader cells, not rooms; there is no interior parallax.
  The day/night lit-set re-roll and per-cell tints are real, the rooms
  are not. (Interior parallax is a candidate Stage H shader-mode toy.)
- Building lighting in the facade shader is a single-direction lambert
  + ambient with manual fog; it does not consume the Three.js light
  list (visually consistent since buildings are axis-aligned).
- Capsule collision resolves in XZ only; you cannot stand ON buildings
  or props (step height/roof landing is future work). Terrain grounding
  is exact via the shared height function.
- Water is a displaced plane with procedural highlights, not a
  reflective/refractive surface.
- Footstep cadence is distance-based but the sound itself is a filtered
  blip, not surface-aware.

## Measured numbers (headless Chromium, software GL, 1280x720)

- Draw calls: 32 for the full night scene (8 self-audit asserts < 64).
  One call covers all ~85 buildings + tower; trees are 2 calls; grass 1.
- Triangles: ~98k at high quality.
- FPS: pinned at the ~56-60 compositor cap in headless SwiftShader,
  before AND after +3000 stress props; on real GPUs the headroom is
  larger. The stress harness itself is what Stage A ships; absolute
  numbers are machine-dependent.
- Window cells for seed 124935158: 11,974 (audit floor is 1,000).

## Known rough edges

- Esc both releases pointer lock (browser-level) and is not bound to
  the menu; M is the menu key. A future stage may unify them.
- Quality "high" enables shadow maps, but only terrain/props/trees
  participate; the facade ShaderMaterial neither casts nor receives.
- The R reset key also resets while the menu is open (input is not
  scoped to gameplay focus yet).
- Sprint + jump can briefly exceed walk speed mid-air (no air-control
  clamp); harmless in the hub.
- `noUnusedLocals` etc. are enforced, but the Water/facade uniform
  objects are typed via a local interface rather than generated types.

## Bugs found and fixed during this verification pass

1. Spawn faced away from the plaza (yaw=PI aimed +Z); now yaw=0.
2. Pedestal labels could render mirrored when facing away from spawn;
   labels now face the spawn point.
3. `pausedByMenu` was clobbered on menu close, leaving the game paused
   after using a menu button; state is now only captured on open.
4. Settings panel controls could go stale if F1/F2 changed settings
   while the menu was closed; the panel now rebuilds on every open.
5. `terrainHeight` returned `-0` inside the city (multiply by 0 blend),
   caught by a determinism test; normalized to `0`.

## Stage B — Race Mode (2026-06-10)

Note on provenance: the Stage B build agent hit its session limit after its
final fix iteration but before writing this section. This entry was written
post-mortem by the orchestrator from observable evidence (commits d692a5b,
e6834db, recovered WIP commit; test suite; file inspection). Claims here are
limited to what was independently verified.

Verified by orchestrator:
- tsc --noEmit clean; vite build clean (1.08s); 108/108 tests green
  (52 Stage A + 56 race: track 12, raceai 13, vehicle 12, checkpoints 11,
  ghost 8).
- Systems present as pure modules under src/systems/race/ (Track,
  Vehicle, Checkpoints, RaceAI, Ghost) with RaceMode + RaceHUD wiring,
  per the spec's testable-without-three.js requirement.
- Ordered-checkpoint and wrong-way logic, AI steering decisions, ghost
  record/replay round-trip, and surface-slowdown all covered by named
  unit tests.

Not verified (agent died before doing/recording it):
- Headless browser pass of the full race loop (enter from pedestal →
  countdown → lap increment). Carried forward to Stage G's full audit.
- The agent's own real-vs-approximation and bugs-found notes for this
  stage are lost; Stage G's self-audit should re-derive them.

## Stage C — Battle Mode (2026-06-10)

## Gates

| Gate | Result |
|---|---|
| `npx tsc --noEmit` | clean |
| `npx vitest run` | 155/155 tests, 16 files (108 prior + 47 new battle tests) |
| `npm run build` | clean (same pre-existing Three.js chunk-size note) |
| dev server + `curl` | HTTP 200, app shell served |
| Headless Chromium session (playwright-cli) | 0 console errors/warnings; full bout played to VICTORY and back to hub |

## What is tested (vitest, node env, pure modules only)

- `typechart.test.ts` (7): 4-type cycle (volt>aero>pyre>cryo>volt at
  2x), self/reverse resistance at 0.5x, full matrix only {0.5,1,2},
  content minimums (>=12 named moves + Vent, >=6 statuses, >=6
  passives, every unit has exactly 4 known moves).
- `statuses.test.ts` (11): apply/refresh-not-stack, passive immunities
  (Thermal Shroud vs Corrosion, Gyro Gimbal vs Servo Lag), seeded
  resist rolls, tick magnitudes (6% corrosion, 8% nanorepair, 8 energy
  flux leak) and expiry timing at end of the unit's OWN turn,
  corrosion-tick KO clearing statuses, stage multiplier table,
  additive stage stacking clamped at +/-3, Servo Lag halving speed on
  top of stages.
- `resolution.test.ts` (18): damage inside deterministic preview
  bounds, 2x vs 0.5x changing real numbers, atk/def stages modifying
  real computed damage (5/3 ratio verified), Aegis halving + flagged
  in the event, Reactive Plating and Surge Core multipliers, KO events
  and winner detection, Siphon Circuit healing 20% of damage dealt,
  energy gating (only Vent legal when broke), cooldown enforcement
  turn-by-turn, illegal-move throw, turn order from effective speed
  with stable index tiebreak and dead-unit exclusion, and
  describeEvent producing the exact expected sentences from events.
- `battleai.test.ts` (8): guaranteed KO beats chip damage (KO bonus
  100 chosen to dominate the max achievable chip total ~80), healing
  chosen at low HP when no KO is on the board, cooldowns/energy
  respected (cooling moves absent from the option list; empty tank
  Vents), type advantage as a named modifier steering target choice,
  status options worth 0 once the status is present, seeded tie
  breaks, and every option's named parts summing to its total.
- `battledeterminism.test.ts` (3): a full AI-vs-AI battle from one
  seed reproduces the identical event log sentence-for-sentence,
  completes with a winner and >=3 KOs, and diverges across seeds.

## Real vs. approximation

Real (backed by state/simulation/logic):
- The battle log is generated exclusively by `describeEvent` over the
  typed BattleEvent stream that the resolution engine emits while
  mutating state; there are no parallel strings (anti-faking clause).
- The AI debug lines (F1) print the actual ScoredOption breakdown the
  enemy used for the turn, e.g.
  `> Concussion Ram -> PYR-4 Kilnguard: 54.3 = type +15.0, dmg +38.5, status +4.8, cd -4.0`
  captured live from the headless session.
- HP/energy bars, status badges, stage badges, cooldown labels and
  move legality on the HUD all read UnitState directly after each
  presented event.
- Turn order, statuses, stages, cooldowns, energy, passives and the
  type chart all flow through the same pure modules the tests cover.
- Pause freezes presentation pacing (it runs on fixed-step sim time).

Approximations (documented, not faked):
- Attack/hit/heal/KO animations are transform-and-emissive tweens on
  the procedural robots (lunge toward target, flinch, pulse, fall);
  there is no skeletal animation or particles.
- AI is 1-ply: it scores the current board only (no lookahead, no
  multi-turn planning); modifiers like cooldownTiming approximate
  timing judgement.
- Robots are shared static meshes; the arena is its own scene (cheap
  lights, no shadows), like Race.

## Measured numbers (headless Chromium, software GL)

- Battle scene: 88 draw calls, ~1.8k triangles, 92 scene nodes.
- Full bout (enemy HP pinned to 1 for the lifecycle check): 2 rounds
  to VICTORY, results panel correct, return-to-hub clean, console
  0 errors / 0 warnings, hub self-audit still 8/8.

## Bugs found and fixed during this verification pass

1. TS narrowing bug in the robot anim chain (`anim.kind !== 'ko'` in
   an unreachable else branch) caught by tsc; restructured.
2. First playtest showed 2x type-advantage heavies one-shotting
   full-HP units (Glacier Driver hit 117 of Arclight's 118 HP);
   trimmed the three nuke powers (80/85/90 -> 72/76/78) and re-ran
   the full suite (155/155 still green).
3. KO_BONUS at 60 could lose the argmax to a big 2x chip hit
   (computed during test design, before it shipped); raised to 100
   with a comment deriving the bound.

## Known rough edges

- 88 draw calls for 6 robots (~10 meshes each, 2 materials each);
  merging per-robot geometry would cut this to ~14 if a later
  optimization pass wants it.
- Target selection by keyboard uses 1-N over the targetable list, but
  the cards do not show those ordinal numbers; clicking is clearer.
- Defeat path and Lockup-skip were exercised by unit tests and partial
  browser play (a Lockup application + expiry appeared in the live
  log), but a full browser defeat was not staged.
- Rematch reuses the same six robots; no team selection screen.
