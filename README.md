# Neon Commons: Systems Playground

An original-IP, browser-playable 3D systems demo. Stage A delivers the
foundation (core loop, input, settings, audio, debug tooling) and the
hub world: a seeded procedural neon city ringed by wilderness and a
lake, with real collision, a live minimap, and interact pedestals for
the five future game modes.

Everything is procedural: geometry, materials, textures, and audio are
generated in code. There are no asset files and no franchise content.

## Setup

```bash
npm install
npm run dev        # http://localhost:5173
npm run build      # production bundle in dist/
npm run typecheck  # tsc --noEmit
npm test           # vitest (52 tests)
```

Append `?seed=12345` to the URL to pin the world seed. The current seed
is shown in the debug overlay (F1) and the welcome toast.

Stack: TypeScript, Vite, Three.js, Vitest. No other runtime
dependencies; nothing native.

## Controls

| Input | Action |
|---|---|
| Click canvas | capture mouse (pointer lock) |
| WASD | move |
| Mouse | look |
| Space / Shift | jump / sprint |
| E | interact (pedestals) |
| N | day/night toggle |
| M | menu (settings, stress test) |
| P | pause simulation |
| F1 | debug overlay (real measured values) |
| F2 | cycle quality high/medium/low |
| R | reset position to spawn |
| Esc | release mouse |

## Architecture

```
src/
  core/       App (composition root + fixed-timestep loop), GameState
              (seed + RNG + entity counters), EventBus (typed), Input,
              Time, SaveSystem, DebugOverlay, SelfAudit
  rendering/  SceneManager, CameraRig, Lighting, Materials,
              PerformanceScaler (quality profiles)
  world/      WorldGeneration (PURE seed -> data), ProceduralCity,
              InteriorWindows (facade window shader), Terrain, Water,
              Vegetation, Collision (AABB spatial hash, PURE)
  modes/      Mode interface + ModeManager, HubMode
  ui/         HUD, Menu, Settings, Minimap, ToastLog
  systems/    Audio (procedural WebAudio), Serialization (PURE)
tests/        vitest suites for every pure module
```

Design rules in force:

- Simulation runs at a fixed 60 Hz; rendering is per-RAF. Pause stops
  the simulation clock, which also drives shader animation.
- The render loop allocates nothing; scratch vectors, query buffers,
  and the stats object are preallocated.
- World layout generation is pure and deterministic (`generateWorld(seed)`),
  shared by the renderer, the collision world, and the minimap, and unit
  tested for determinism.
- Entity counts are bounded: buildings/trees/grass/stress props all
  have fixed maximum instance counts allocated once.

### Window illusion

All buildings plus the landmark tower are ONE `InstancedMesh` whose
fragment shader paints a window grid on each facade in world meters
(2 m columns, 3 m floors, the same constants the generator uses to
count windows). A hash of (cell, facade, building seed, day/night
phase) decides per-window lit state and tint, so toggling night
genuinely re-rolls the lit distribution. Typical seeds produce
10,000+ window cells in 1 draw call for the entire skyline.

### Mode seams (for Stages B+)

Future modes implement `Mode` (`enter`/`exit`/`update`) and register
with `ModeManager`. The hub's five pedestals already emit real
`interact` events carrying the mode id (`race`, `battle`, `board`,
`flight`, `shader`); `App` routes them to `modes.switchTo(id)` when the
mode is registered, and shows a "docking soon" toast when it is not.
Installing a mode in a later stage means: implement `Mode`, call
`modes.register(...)`, done — no hub changes required.

## Verification

See `VERIFICATION.md` for the Stage A checklist: what is tested, what
is real vs. approximated, and known rough edges.
