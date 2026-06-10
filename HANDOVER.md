# Neon Commons: Systems Playground — No-Context Handover Brief

This document is self-contained. A model (or person) with zero conversation history should be able to build, extend, or audit this project from this file alone.

Provenance: distilled from a review of viral Fable/Mythos-class demos (Godogen's plan→implement→run→inspect→repair→test→document harness being the strongest reference), a survey of the modern HTML/CSS storytelling platform, and one full day of field-tested agentic production on a sibling project (meadow-hearth, 2026-06-10: five PRs, four parallel build agents, CI-gated merges, production deploy). Sections 1-7 are the original brief; section 8 is the field-amendment layer added after that day. Where they conflict, section 8 wins, because it was paid for.

---

## 1. Purpose

The goal is not "make a cool 3D game." The goal is a browser-playable, visually impressive, technically robust, stateful interactive artifact. The strongest demos are not pretty scenes; they contain real systems: rules engines, physics loops, deterministic state, session logic, shader tricks, performance budgets, debug overlays, tests, self-verification, and optimization passes.

The prompt turns the model from a scene painter into a tiny game studio with a clipboard.

## 2. The Production Loop (Godogen pattern)

1. Plan the systems.
2. Implement the smallest complete playable version.
3. Run it.
4. Inspect browser state or output.
5. Compare against the spec.
6. Fix visible bugs.
7. Repeat until the core loop is playable.
8. Document tested features, limitations, and rough edges.

## 3. The Three Clauses (non-negotiable)

**Anti-Faking Clause.** When a feature could be faked visually, implement the smallest real version instead. Every visible UI claim must be backed by actual state, simulation, or logic. A tiny working rules engine beats a beautiful nonfunctional mockup.

**Optimization Clause.** After the first working version, perform an optimization pass. Preserve visual quality while reducing draw calls, geometry count, memory churn, shader cost, and frame-time spikes. Record before/after FPS.

**Self-Repair Clause.** Do not stop after writing code. Run the app, inspect it, compare against the acceptance checklist, fix visible issues, and repeat until playable.

## 4. Project Spec

**Title:** Neon Commons: Systems Playground. Original IP only; borrow mechanics (arcade racing, tactical battles, board economy, procedural city, cinematic flight, shader spectacle), never franchises.

**Stack:** TypeScript, Vite, Three.js, Web Audio API, vitest. Minimal dependencies; procedural geometry/materials/textures/audio; runs locally with `npm install` + `npm run dev`.

**Architecture:** modular by system — `/src/core` (App, GameState, EventBus, Input, Time, SaveSystem, DebugOverlay, SelfAudit), `/src/rendering` (SceneManager, CameraRig, Lighting, Materials, PostFX, PerformanceScaler, ShaderShowcase), `/src/world` (ProceduralCity, Terrain, Water, Vegetation, InteriorWindows, Collision, WorldGeneration), `/src/modes` (Hub, Race, Battle, Board, Flight, Shader behind one Mode interface), `/src/ui` (HUD, Menu, Settings, Dialogue, ToastLog, Minimap), `/src/systems` (PhysicsLite, Economy, RulesEngine, BattleAI, RaceAI, TrafficAI, Audio, Particles, Serialization).

**Modes (each must have start, active, and end states; each is a real loop):**

1. **Hub** — navigable procedural city + wilderness; WASD + mouse-look; collision; interact markers to all modes; minimap; NPC dialogue; day/night; not a menu, a place.
2. **Race** — one complete track first; vehicle physics, drift, boost pads, off-road slowdown; ordered checkpoints (laps only count in order, wrong-way visible); 3 AI racers; time trial; local ghost replay; results; debug racing-line view.
3. **Battle** — 3v3 tactical robots; HP/energy/speed/type/passive + 4 moves each; ≥12 moves, ≥6 abilities, ≥6 statuses; type chart; battle log explaining every effect. Enemy AI scores each legal move (type advantage, expected damage, KO potential, healing/status/buff value, cooldown timing, survival risk, target priority), picks best, breaks ties randomly, exposes reasoning in debug mode. Tests for resolution, status expiry, type advantage, buffs, cooldowns, AI choice.
4. **Board** — 2-4 local players; seeded deterministic dice; buying, rent tied to real ownership, sets, upgrades that change real rent math, taxes/events, bankruptcy rule, event log, save/load, compact share codes that restore identical state; debug state panel.
5. **Flight** — third-person craft; rings; enemy drones; projectiles with real collision; score from real events; health; boss with distinct phases; win/fail; finish screen.
6. **Shader/Simulation** — one visually impressive procedural piece with exposed parameters, quality controls, FPS display, explanatory labels. (See 8.4 for the field-proven menu.)

**Performance:** 60 FPS target on a normal laptop. Debug overlay shows REAL values (FPS, frame time, draw calls and triangles from `renderer.info`, entity count, active mode, quality, camera, seed). Quality scaling High/Medium/Low that actually changes draw distance, instance counts, shadows. Instancing, pooling, culling, bounded entities, zero allocations in the render loop. Stress Test button with measured FPS impact. 1,000+ windows via material/shader illusion, never per-window meshes.

**Settings:** sensitivity, FOV, volumes, quality, motion toggle, subtitles, debug toggle, resets. Keys: M menu, P pause, F1 debug, F2 quality, R reset, Esc hub.

**Audio:** procedural Web Audio (blips, engine, hits, coins, ambient pad, looping synth bed). No files.

**Persistence:** settings to localStorage; board save/load + share codes; race ghosts; seed visible in debug.

**Self-Verification:** a `VERIFICATION.md` answering: install/dev work? hub navigable? every mode enterable/exitable with full state lifecycle? race counts laps correctly? battle resolves correctly with explained AI? board economy correct and deterministic? flight has real combat and end states? shader interactive? overlay live? stress test survivable? what was optimized? what remains rough?

**Acceptance:** runs locally; browser-playable; multiple real interactive modes; original IP; real systems not fake UI; debug visibility; tests; save/load; self-audit; survives optimization; honest limitations. The goal is the smallest complete version of a large-feeling demo.

## 5. Phases

1 Foundation → 2 Hub → 3 Race → 4 Battle → 5 Board → 6 Flight → 7 Shader → 8 Optimization + Verification. Split into per-phase prompts; never ask for everything in one generation.

## 6. Bad vs Strong Prompts

Bad: "Make Minecraft." "Make Mario Kart." "Make a cool 3D game." These invite surface imitation and fragile mockups.

Strong: "Build a complete original browser-playable systems demo with an agentic production loop: plan, implement, run, inspect, repair, test, document" — plus a spec like section 4.

## 7. Demo Lessons Reference (condensed)

Terrain/forest demos → instancing, wind, water collision, fog, FPS overlay, optimization pass. Board-game demos → deterministic seeded economy with tests. Battle demos → scored AI with exposed reasoning. Flight demos → real projectile collision and boss phases. City demos → interior-mapping/parallax-window illusions, batching, never brute-force geometry. Multiplayer demos → a real state layer; if networking is unavailable, local bots behind the same API boundary, honestly labeled. Racing demos → ordered checkpoints, ghost replay, complete menu-to-results loop. Generative-design demos → seeds, lockable parameters, presets, history, export. Shader demos → single-module spectacle with controls and a quality fallback.

---

## 8. Field Amendments (2026-06-10) — paid-for lessons from a real agentic production day

These were learned shipping a five-stage product push on a sibling project (content pipeline, motion system, generative-math gallery, reading overlay, world integration) with four parallel build agents, a CI gate, and a production deploy. They upgrade sections 2-7.

### 8.1 The pipeline IS part of the artifact

- **Gate every merge.** A `pull_request` CI workflow (typecheck + unit tests + an end-to-end run against a fully local stack) caught a real regression on a "content-only" PR the same day it was built. Build the gate in Phase 1, not Phase 8. For this project: vitest + `tsc --noEmit` + a headless boot check minimum; a Playwright "ship-smoke" once the hub exists.
- **One agent per stage, isolated worktrees, disjoint file scopes.** Parallel agents must not share files. Integration wiring (the small edits that connect components into the world/app shell) is the orchestrator's job, done serially after each merge. This eliminated all merge conflicts across five same-day PRs.
- **Verify the worktree.** Agent harnesses can cut worktrees from the wrong repo (it happened twice in one day when the cwd was itself a different git clone). First step of every agent: `git remote -v`, self-create the worktree from the canonical clone if wrong.
- **Trust but verify agent reports.** Agents must report evidence (test counts, build output, measured frame times), and the orchestrator re-runs the key suite before merging. One agent caught three field-name errors in its own brief by reading the actual files first; require that behavior ("do not trust this prompt over the files").

### 8.2 Tests that refuse to be fooled (the false-green pattern)

A test that checks "the dialog mounted" passes on a beautiful empty shell — exactly what the Anti-Faking Clause forbids. Assert on content that only a working system can produce:

- For a reading surface: a sentence from a real document, fetched through the real pipeline.
- For a math exhibit: the placard phrase AND unit tests on the pure math (known values, determinism from seed, bounds, LUT error tolerance vs the exact formula).
- For an economy: rent computed from actual ownership state, share-code round-trip restoring identical state.
- For flake fixes: wait on real state transitions (`toBeEnabled`, an event landing), never on timeouts. File an issue for every flake the moment it appears; fix it at the spec level within a day.

### 8.3 Two registers, one world (design system doctrine)

A stylized world (pixel art, neon city, whatever the register is) should NOT bleed into its informational overlays, and vice versa. Run two visual registers: the **world register** (the game's own aesthetic, untouched) and the **editorial register** (readers, placards, menus, debug: modern editorial typography, 65ch measures, drop caps where fitting, generous leading). Concretely:

- Design tokens first: oklch color tokens with hex fallbacks behind `@supports`, derived hover/active tints via `color-mix`, an easing/duration token set (`--ease-gentle: cubic-bezier(0.22,1,0.36,1)`, `--dur-quick/calm/drift: 180/480/1200ms`).
- Motion is meditative, never gratuitous: `@starting-style` entrances, staggered settles capped at ~6 steps, and **every** motion rule neutralized under `prefers-reduced-motion: reduce`. This is accessibility law, not garnish.
- Progressive enhancement everywhere: `text-wrap: balance/pretty`, frontier CSS behind `@supports`; the artifact must read correctly with all enhancements stripped.
- Know when NOT to integrate: a smooth generative canvas behind crunchy pixel art muddies both registers. Skipping a planned flourish to protect coherence is a shipping decision, not a failure. Record such decisions in VERIFICATION.md.

### 8.4 Generative math, the proven recipes (for Shader/Simulation mode and ambient art)

Field-built and performance-measured; reuse these shapes:

- **Phyllotaxis bloom:** `θ = n · 137.50776°, r = c·√n`. Precompute unit positions into a Float32Array; per-frame cost is just fills. The placard story: the golden angle is the most irrational rotation, so florets never align and packing stays even — sunflowers found it first.
- **Flow field:** advect ~600 particles through the analytic curl of a layered-sine potential `ψ = Σ aᵢ sin(kᵢ·p + ωᵢt + φᵢ)`, `v = (∂ψ/∂y, −∂ψ/∂x)`. Divergence-free by construction, so particles never clump or thin. ~0.05ms/frame. No noise libraries.
- **Wave interference:** sum 3-5 moving sine sources per cell on a quarter-resolution grid into reused ImageData, upscale. A 4096-entry sine LUT cut frame logic from 4.0ms to 0.6ms at sub-8-bit error (7.7e-4) — unit-test the LUT against the exact formula with an explicit tolerance.
- Universal rules: deterministic from a seed; typed arrays; zero allocations in RAF; pause on `document.hidden`; DPR-aware (cap 2x); reduced-motion renders one beautiful static frame. **Every exhibit gets a museum placard:** plain-language paragraph + the actual formula. The placard is part of the artifact; write it like you mean it.

### 8.5 Content and voice (if the artifact carries words)

- Voice content (dialogue, placards, posts, flavor text) is authored by the orchestrator or a human, never delegated to cold-start agents; agents hallucinate voice.
- If content flows from an external corpus, gate it mechanically (an explicit per-item opt-in flag the pipeline enforces) and verify the gate by counting what was *excluded* (e.g., "8,520 pages skipped" is the security evidence).
- Curate by register: a public artifact carries craft/curiosity topics; keep anything sensitive out by category, not by case-by-case judgment under deadline.

### 8.6 The loop ledger (process memory)

- A plan file before implementing; a `resume.md` + `.checkpoints/` in the repo from the first commit; stage checkboxes updated at each merge. A session limit or context loss then costs nothing.
- VERIFICATION.md is append-per-stage, not written once at the end. Each stage records: what is real simulation vs visual approximation, what was tested, what is rough.
- After the final stage: an optimization pass with before/after numbers, then a deploy/release step that re-runs the full smoke against the shipped artifact — and only then is the stage ledger closed.

### 8.7 Sequencing amendment to section 5

Phase 1 now includes the CI gate and the debug overlay (they are the studio, not the product). The original Phase 8 verification becomes continuous (8.6); the final phase is optimization + release + an honest README that distinguishes real systems from approximations, because the difference between a demo and an artifact is that the artifact tells you where its seams are.

---

*End of brief. Build the systems.*
