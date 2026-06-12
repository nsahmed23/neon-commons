# MIGRATION-NOTES — neon-commons → meadow-hearth apps/commons

Audit date: 2026-06-12. Read-and-prepare pass only; nothing structural was
changed. Master plan: meadow-hearth PR #156. Rollback point: tag
`pre-migration-2026-06-12` on `bee55c0` (current main).

## 1. CI — verified with evidence

- Workflow: `ci` (`.github/workflows/ci.yml`, workflow id 293843969), one job
  (`gate`): `npm ci` → `tsc --noEmit` → `vitest run` → `vite build` → boot
  smoke (dev server must serve `id="app"` within 30 s).
- Runs on main: 2, both `success`.
  - Run #2 (latest): id 27345809109, push of `bee55c0` ("chore: Firebase
    Hosting config"), 2026-06-11T12:11Z, ~29 s.
  - Run #1: id 27345732886, push of `340ab89` (Stage G merge),
    2026-06-11T12:09Z, ~31 s.
- 318-test claim verified by running the suite in this session, not taken on
  faith: **34 files, 318 tests, 318 passed** (vitest 1.6, node env, ~4 s).
  Matches README and the repo description exactly.
- Note: CI gates only; there is **no deploy step** in CI. Firebase deploys are
  manual.

## 2. Migration characterization

### Build system
- Vite 5 (`vite build`, target es2022, sourcemaps on), TypeScript 5.5 strict
  (`tsc --noEmit` as a separate gate), Vitest 1.6 (node environment — tests
  never touch the DOM or Three.js). ESM throughout (`"type": "module"`).
- Single runtime dependency: `three ^0.165.0`. Dev deps: `@types/three`,
  `typescript`, `vite`, `vitest`. Nothing native, no asset files (everything
  procedural) — a very clean candidate for a pnpm/turbo workspace package.
- Output: `dist/` (gitignored), one JS chunk ~672 kB (186 kB gzip) + one CSS
  file, hashed filenames.

### Deployment today
- Standalone: Firebase Hosting site `neon-commons` in project
  `personal-website-44b59` → https://neon-commons.web.app. `firebase.json`
  serves `dist/` with immutable 1-year cache headers on js/css; `.firebaserc`
  maps hosting target `neon-commons` → site `neon-commons`. Deploys are
  manual (`firebase deploy`); commit `bee55c0` added this config.
- Integrated: meadow-hearth ships something at `/commons` (its commit #154).
  Mechanism could not be verified from this session — see §3.

### Base-path / root assumptions (the things that break under /commons)
Verified by building in this session:

1. **Vite `base` is unset** (`vite.config.ts`) → the emitted
   `dist/index.html` references assets root-absolute:
   `/assets/index-CjqigrHm.js`, `/assets/index-gxj721tv.css`. This exact
   build **404s if served under `/commons/`**. The fix at migration time is
   one line: `base: '/commons/'` (or `'./'`) in the integrated build config.
2. That is the *only* root assumption. Full grep of `src/` found:
   - No router, no `history` API, no `fetch()` calls, no `new URL`, no
     `import.meta.env` usage, no asset URLs in code (favicon is an inline
     data URI).
   - The single `location` usage is `location.search.match(/[?&]seed=(\d+)/)`
     in `src/core/GameState.ts:25` — path-agnostic, works at any mount point.
3. localStorage is per-origin: moving users from `neon-commons.web.app` to
   the meadow-hearth domain silently resets their settings/ghosts/board
   saves. Not a blocker (it's a demo), but worth a line in release notes.

## 3. Relationship to meadow-hearth's existing /commons integration

**Could not be conclusively determined from this session.** This environment's
GitHub access is scoped to `nsahmed23/neon-commons` only, the repo-management
tools to widen scope are not available here, and the network policy blocks all
outbound fetches (probing neon-commons.web.app and the meadow-hearth site both
returned proxy 403s). What *can* be established from this side:

- This repo contains **zero references to meadow-hearth** — no subtree or
  submodule metadata, no remote, no mention in any doc except HANDOVER.md's
  provenance note (meadow-hearth as a sibling project).
- This repo **publishes nothing**: `"private": true`, no npm package, no CI
  artifact upload, no release. So meadow-hearth cannot be consuming a
  published package or pipeline output; whatever is at `/commons` had to be
  copied, vendored, subtree'd, linked, or framed from its side.
- The absolute-base build output (§2) is a useful discriminator: this repo's
  unmodified `dist/` cannot work when path-mounted at `/commons`. So the
  integration is one of:
  - (a) the arcade cabinet is an **external link/redirect** to
    `neon-commons.web.app` (cheapest, most likely given the wording of
    meadow-hearth #154 and that this repo needed no changes);
  - (b) an **iframe** of neon-commons.web.app;
  - (c) a **vendored copy of the source** rebuilt inside meadow-hearth with
    its own `base` (drift risk: it forks silently from this repo);
  - (d) a **git subtree/pinned snapshot** on the meadow-hearth side.

**Verification steps (run from the meadow-hearth session):**
1. `git log --oneline --all -- '*commons*'` and grep the repo for
   `neon-commons`, `neon-commons.web.app`, `Visit Neon Commons`.
2. Check meadow-hearth's `firebase.json` for `/commons` rewrites/redirects.
3. If vendored: diff the vendored copy against this repo's `bee55c0`
   (the asset hash of a faithful copy of the current build would be
   `index-CjqigrHm.js`) and note which commit it forked from.
4. Check meadow-hearth #154's diff — it is the authoritative answer.

## 4. Identity / user-state inventory

**This repo has no user identity.** No avatar, no user callsign, no profile,
no accounts. (Battle "callsigns" in `src/systems/battle/Units.ts` are the six
NPC robots' names — original-IP flavor, not user state.)

All persisted state, via `SaveSystem` (`src/core/SaveSystem.ts`), namespaced
under `neon-commons:*` so it cannot collide with meadow-hearth keys on a
shared origin:

| Key | What | Written by |
|---|---|---|
| `neon-commons:settings:v1` | settings (fov, volume, quality…) | `src/core/SaveSystem.ts:14` |
| `neon-commons:ghost:v1:<seed>` | race ghost replay | `src/modes/RaceMode.ts:150` |
| `neon-commons:board:v1` | board-game save (share-code format) | `src/modes/BoardMode.ts:44` |

On a clean migration consuming meadow-hearth's `packages/identity`, the change
is **additive** (there is nothing to replace). The touch points would be:
- `src/core/App.ts` (composition root) — where an identity provider would be
  injected alongside `SaveSystem`.
- `src/core/SaveSystem.ts` — decide whether keys stay `neon-commons:*` or
  become identity-scoped.
- UI surfaces that could display a callsign: welcome toast (`ui/ToastLog`),
  debug overlay, race/board results screens.

**None of these were changed in this pass.**

## 5. The in-world link (arcade cabinet "Visit Neon Commons")

The cabinet lives **entirely in meadow-hearth** — this repo has no reference
to it and no inbound-link awareness. For it to survive any migration:
- If the cabinet currently points at `https://neon-commons.web.app`, it keeps
  working regardless of what happens in the monorepo (that hosting target is
  independent), and must only be updated if/when the standalone site is
  retired in favor of the `/commons` route.
- If it points at the meadow-hearth `/commons` route, it survives a migration
  into `apps/commons` only if that route keeps serving the app — i.e. the
  migrated package must build with `base: '/commons/'` and deploy to the same
  path.
- Action for the meadow-hearth session: locate the cabinet's link target
  (search `Visit Neon Commons`) and record it in PR #156 before any cutover.

## 6. Recommendation: migrate properly vs. leave as-is

**Recommendation: leave as-is for now; decide after meadow-hearth #154's
mechanism is confirmed.** Concretely:

- This repo is the strongest public artifact (recruiter-grade description,
  green CI, verified 318 tests, clean single-dependency build). **It should
  remain the canonical public home either way** — folding it into the
  monorepo and archiving it would degrade the portfolio for zero user-facing
  gain, since an integration at `/commons` already ships.
- If #154 turns out to be a **link/iframe/redirect** to neon-commons.web.app
  (hypothesis (a)/(b) in §3): there is nothing to migrate. The wiring is
  fine, has no drift risk, and a monorepo move would add work and risk to a
  green, finished project. Leave as-is; just record the link target.
- If #154 is a **vendored copy** ((c)/(d)): there is real drift risk, and a
  proper history-preserving move to `apps/commons` (with this repo kept as a
  public mirror, `base` made configurable, CI folded into the monorepo gate)
  becomes worth doing. Even then it is low urgency: this repo is feature-
  complete (Stage G closed) and not under active change, so drift is
  currently theoretical.
- Either way, the migration-time checklist is short: set Vite `base`,
  keep the `neon-commons:*` storage namespace, keep neon-commons.web.app
  deploying (or 301 it), update the cabinet link, and preserve history via
  `git subtree add` / filter-repo — not a flatten-and-paste.

## 7. Rollback point

- Tag `pre-migration-2026-06-12` → `bee55c0` (tip of main at audit time),
  pushed to origin. `main` itself was not touched; this audit lives on branch
  `claude/neon-commons-migration-audit-vtoaks`.
