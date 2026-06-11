# Neon Commons: Systems Playground

An original-IP, browser-playable 3D systems demo: a seeded procedural
neon city (the hub) with five complete game modes docked around its
plaza — an arcade racer, a 3v3 tactical robot battle, a seeded economy
board game, a combat flight course over the live skyline, and a
raymarched black-hole shader toy. Every mode is a real loop with start,
active, and end states, backed by tested simulation rather than mockup
UI.

Everything is procedural: geometry, materials, textures, and audio are
generated in code. There are no asset files and no franchise content.

## Setup

```bash
npm install
npm run dev        # http://localhost:5173
npm run build      # production bundle in dist/
npm run typecheck  # tsc --noEmit
npm test           # vitest (318 tests, 34 files)
```

Stack: TypeScript, Vite, Three.js, Vitest. No other runtime
dependencies; nothing native.

Append `?seed=12345` to the URL to pin the world seed. The current seed
is shown in the debug overlay (F1) and the welcome toast. The same seed
also drives the race track, battle tiebreaks, board dice/deck, flight
course, and shader randomizer.

## Controls

Global (any mode):

| Input | Action |
|---|---|
| M | menu (settings, stress test) |
| P | pause simulation (freezes shader/water animation too) |
| F1 | debug overlay (real measured values) |
| F2 | cycle quality high/medium/low |
| N | day/night toggle |
| Esc | exit mode to hub / release mouse |

Hub: click canvas to capture the mouse; WASD move, mouse look, Space
jump, Shift sprint, E interact at a pedestal, R reset to spawn.

Race: W throttle, S brake/reverse, A/D steer, Space drift, R respawn at
the last checkpoint, B racing-line/AI-target debug layer (with F1 on).

Battle: 1-4 pick a move, 1-3 or click a card to pick a target, X cancel.
With F1 on, the log prints the enemy AI's full score breakdown.

Board: R or the Roll button rolls; Buy / Develop / End Turn / Save /
Share Code buttons; paste a share code on the intro screen to restore.
F1 shows the engine-state panel.

Flight: mouse aim, W/S thrust, A/D strafe, Space climb, Shift sink,
click or F fire, R respawn.

Shader: drag to orbit, wheel to zoom; sliders drive real uniforms;
quality buttons change ray steps + resolution scale.

## Feature checklist

- [x] Hub: seeded procedural city + wilderness, AABB spatial-hash
      collision, minimap from real world data, day/night, 10k+ shader
      window cells in one instanced draw, five interact pedestals
- [x] Race: kart physics with drift/boost/off-road, ordered checkpoints
      with wrong-way detection, 3 AI rivals on the same physics, time
      trial with persisted ghost replay, results, racing-line debug
- [x] Battle: 3v3, 4-type chart, 15 moves + Vent, 6 statuses, 6
      passives, event-sourced resolution engine, scored AI with visible
      reasoning, full battle log derived only from typed events
- [x] Board: 28-space ring, 2-4 hot-seat human/bot seats, seeded dice
      and 16-card flux deck, rent from real ownership/sets/levels,
      bankruptcy + liquidation, save/load, versioned share codes that
      restore identical state
- [x] Flight: hover-drone over the LIVE hub scene, 10 ordered rings
      riding the real skyline, pooled swept-collision projectiles,
      sentry state machines, 3-phase boss, event-stream scoring, win
      and fail end states
- [x] Shader: raymarched gravitational lensing with sliders bound to
      real uniforms, presets, seeded randomize, quality scaling,
      museum placard with the actual formula
- [x] Studio: typed EventBus, fixed-timestep core, settings with real
      side effects, procedural Web Audio, debug overlay with measured
      values, in-app self-audit (8 checks), stress test, CI gate
- [ ] Hub NPC dialogue (spec item; never built — see limitations)

## Architecture

```
src/
  core/       App (composition root + fixed-timestep loop), GameState,
              EventBus (typed), Input, Time, SaveSystem, DebugOverlay,
              SelfAudit, Rng (mulberry32 + forks)
  rendering/  SceneManager, CameraRig, Lighting, Materials,
              PerformanceScaler (quality profiles)
  world/      WorldGeneration (PURE seed -> data), ProceduralCity,
              InteriorWindows (facade window shader), Terrain, Water,
              Vegetation, Collision (AABB spatial hash, PURE)
  modes/      Mode interface + ModeManager; HubMode, RaceMode,
              BattleMode, BoardMode, FlightMode, ShaderMode (+ their
              scene builders under modes/<mode>/)
  systems/    Audio, Serialization, and the PURE simulation modules:
              race/ (Track, Vehicle, Checkpoints, RaceAI, Ghost)
              battle/ (TypeChart, Statuses, Moves, Units, Resolution,
                       TurnOrder, BattleAI)
              board/ (BoardData, BoardRng, EventDeck, Engine, Bot,
                      ShareCode)
              flight/ (FlightModel, Rings, Projectiles, DroneAI,
                       Scoring)
              shader/ (LensingMath, ShaderParams, ShaderSource)
  ui/         HUD, Menu, Settings, Minimap, ToastLog + per-mode HUDs
tests/        34 vitest suites over the pure modules (node env)
```

Design rules in force:

- Simulation runs at a fixed 60 Hz; rendering is per-RAF. Pause stops
  the simulation clock, which also drives every shader `uTime`.
- The render loop allocates nothing app-side; scratch vectors, SoA
  pools, and query buffers are preallocated (measured ~1 KB/frame
  total churn including Three.js internals).
- Every rule set lives in a pure module testable without Three.js or
  the DOM; modes wire those modules to input, audio, HUD, and scenes.
- Scenes are built once in mode constructors and reused; mode
  enter/exit was leak-checked (5x cycles, forced GC, < 40 KB drift).
- Entity counts are bounded: instances, projectile pools (96), ghost
  samples, battle log length all have fixed caps.

### Mode seam

Modes implement `Mode` (`enter`/`exit`/`update`) and register with
`ModeManager`. Hub pedestals emit real `interact` events carrying the
mode id; `App` routes them to `modes.switchTo(id)`. `window.__neonApp`
(set in main.ts) is the dev/audit handle scripted browser sessions use.

## What is real simulation/state versus visual approximation

Real, backed by state/simulation/logic (the anti-faking clause):

- Overlay numbers: FPS/frame time from a wall-clock ring buffer, draw
  calls/triangles from `renderer.info`, entity counts from per-system
  reports, window count from the same constants the facade shader uses.
- Hub collision is a queried spatial hash; walking into the lake or a
  wall is physically blocked, not scripted. The minimap draws actual
  world data and live player position.
- Race: laps count only via in-order checkpoint gates with wrong-way
  detection; AI rivals run the same vehicle physics as the player;
  ghosts are recorded state replayed from localStorage.
- Battle: every log sentence is generated from the typed event stream
  the resolution engine emits while mutating state; the F1 panel prints
  the actual per-option AI score breakdown used for the turn.
- Board: rent computed from real ownership/set/level arrays at landing
  time; dice are seeded draws (the 3D tumble is cosmetic but settles on
  the REAL faces); share codes encode the entire state and restore it
  identically; bots follow a deterministic, unit-tested policy.
- Flight: ring passes are 3D sphere tests against an ordered course
  derived from the real skyline; projectiles use swept segment-sphere
  collision (no tunneling); boss phases derive from real add-alive
  counts and hp thresholds; score folds only the typed event stream.
- Shader: sliders drive real uniforms (verified by uniform readback AND
  pixel diffs); the GLSL is generated from the same constants the
  tested TypeScript mirrors use; quality changes real renderer state.
- Settings each have a verified side effect; persistence is real
  localStorage round-trips (settings, board saves, ghosts).

Visual approximation, documented and labeled, never load-bearing:

- Windows are shader cells, not rooms (no interior parallax); facade
  lighting is a manual lambert + fog, outside the Three.js light list.
- Hub capsule collision resolves in XZ only; you cannot stand on roofs.
- Water is a displaced plane with procedural highlights, no reflection.
- Battle animations are transform/emissive tweens (lunge, flinch,
  pulse, KO sink); robots are merged static meshes; the AI is 1-ply.
- Board dice tumble and pawn glide are cosmetic between real states;
  only corners/transit carry 3D name plates.
- Flight enemies move by kinematic seek, not the player's flight
  model; enemy bolts aim without lead (the intended dodge window);
  drones ignore building collision; ring pass is sphere proximity, not
  a torus plane-crossing.
- The black hole is a per-step inverse-square deflection sketch, not a
  geodesic integrator; doppler is a linear bias; colors are an artistic
  ramp. The in-app placard says exactly this.

## Performance notes

Headless Chromium (SwiftShader, 1280x720, high quality) after the
Stage G optimization pass; real GPUs have far more headroom:

| Mode | Draw calls | Triangles |
|---|---|---|
| Hub (night) | 32 | ~98k |
| Race | 38 | ~4.5k |
| Battle | 47 (was 89) | ~1.8k |
| Board (in game) | 61 (was ~70) | ~0.9k |
| Flight (launch view) | 12 (was 17) | ~92k |
| Shader | 1 | 2 |

- The whole skyline (85+ buildings, 10k+ window cells) is ONE
  instanced draw; trees/grass/stress props are instanced with bounded
  counts; all 96 flight bolts are one instanced draw.
- Quality profiles really change draw distance, fog, shadows,
  vegetation counts, and pixel-ratio cap; the shader mode maps quality
  to ray steps + resolution scale.
- Stress test: +3000 instanced props with measured before/after FPS
  (M menu). Headless FPS pins at the ~56 fps compositor cap; treat
  absolute numbers as machine-dependent.
- Mode switch leak check: 5x enter/exit per mode under forced GC
  showed < 40 KB drift (noise); no listener or geometry leaks.

## Known limitations

- No hub NPC dialogue (the one unbuilt spec item; the hub is a place,
  not a conversation).
- Board R-roll still fires while the pause menu is open (hot-seat
  trust model; input scoping is future work).
- Race shows a stale HUD strip behind the event-select panel; respawn
  (R) in flight keeps current hull (respawn-spamming is viable).
- Battle target hotkey ordinals are not printed on the cards; clicking
  is clearer. Rematch reuses the same six robots.
- Shader placard can overlap the controls panel on small windows; F2
  resets a hand-tuned ray-steps slider to the quality baseline.
- Esc releases pointer lock at the browser level AND exits modes; M
  remains the menu key.

Per-stage detail, measured numbers, bug archaeology, and the closing
14-question self-verification live in `VERIFICATION.md`. The stage
ledger is `resume.md` + `.checkpoints/`.
