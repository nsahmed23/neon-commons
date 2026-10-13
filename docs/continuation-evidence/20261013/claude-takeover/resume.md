# Intune Workbench rescue: resume point

Read this first in any new session. `ledger/ledger.json` is the source of truth for lane, milestone and gate status; `AUDIT.md` indexes the full record; this file says where the work stands and what comes next.

## What this folder is

The local controller workspace for taking over the Intune Workbench from the ChatGPT Work environment, per the 2026-10-12 handoff in `handoff/`. Private evidence is NOT here: the four archive layers still live only in the original ChatGPT Work task's tmpfs.

## Done (2026-10-13)

- M0 intake measurements: Windows host, WSL Ubuntu, local repo, tools (`.checkpoints/M0-intake.json`).
- M1 PASS, public scope: C32 tip, engine tree, canonical ledger hash, both 0.9.0 package hashes (`.checkpoints/M1-public-source.json`).
- Route analysis reviewed by Fable 5.1, GPT-6 Astra and GPT-6 Sol; `outbox/SOURCE-QUERY-01.md` is final.
- M4 preparation: the public restorer is POSIX-only stdlib Python, so it runs in WSL with no installs; it has no free-space check (`lanes/m4-prep/FINAL.md`).
- Audit trail live (`AUDIT.md`); a sync worker publishes the sanitized set to `continuation/r4-20261007` every 10 minutes (first commit 658ff7f4).
- Codex CLI updated to 0.162.1; `gpt-6.1-sol` works.

## In flight

- OA-1: the owner relays SOURCE-QUERY-01 to the ChatGPT Work task; the reply goes to `inbox/SOURCE-REPLY-01.json`.
- Sync worker (`logs/sync-worker.log`), started 2026-10-13T15:31:44Z for 12 hours. Stop it by creating `tools/STOP_SYNC`.

## Next

1. Parse `inbox/SOURCE-REPLY-01.json` against the pins (Sonnet 5.5 lane, script-checked); update the ledger's `source_transfer` rows.
2. Pick the M2 route with the owner (OA-2), then run the synthetic bridge with the existing 18,445-byte probe.
3. After OA-3 and OA-4: create the WSL receiver tree (`~/intune-rescue/{incoming,archives,restored,amendments,observations}`) and transfer the small layers first.

## Routing

Opus 5.5 controls and gates. Sonnet 5.5 takes mechanical Claude work; Haiku 5.5 takes sweeps. Fable 5.1 leads the advisors with GPT-6 Astra as its peer. GPT-6.1 Sol is the Opus-tier ChatGPT executor. Kimi K3 does frontend only.

## Boundaries that stay in force

No Drive retry without an evidenced scope change. No private evidence in any public repository, and no raw transcripts published. No credential changes, VM installs, laboratory mutations or G13 attempts. New runs are new evidence, never recovery of a missing original.
