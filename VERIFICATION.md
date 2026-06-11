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
