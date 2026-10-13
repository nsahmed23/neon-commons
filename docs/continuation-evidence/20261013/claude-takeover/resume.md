# Intune Workbench rescue: resume point

Read this first in any new session. `ledger/ledger.json` is the source of truth for lane, milestone and gate status; `AUDIT.md` indexes the full record; this file says where the work stands and what comes next.

## What this folder is

The local controller workspace for taking over the Intune Workbench from the ChatGPT Work environment, per the 2026-10-12 handoff in `handoff/` (local only, never published). Private evidence is NOT here.

## Done (2026-10-13)

- M0 intake measurements and M1 PASS (public scope; d057cc15 is the immutable C32 baseline).
- SOURCE-QUERY-01 answered (`inbox/SOURCE-REPLY-01.json`, local). Checked against the sent pins (`observations/SOURCE-REPLY-01-CHECK.json`):
  - the four C32 archives are ABSENT (ENOENT) in a source runtime that booted 2026-10-13T15:52:05Z;
  - the 18,445-byte probe is intact;
  - the input roots for r4-evidence and provider-candidates exist in `/workspace`, and the two `/tmp` scratch roots are gone.
- The public sync was stopped at 17:28Z, and publishing now needs a review receipt bound to exact file hashes:
  - the gate is in `tools/publish_branch.py`, the scanner in `tools/scan_published.py`, and the tool tests pass (30);
  - review of the already-public commit 7840c407: `observations/PUBLICATION-REVIEW-01.json`.
- Model identities confirmed from runtime metadata (`observations/MODEL-EVIDENCE-01.md`).
- Route B1-R proposed and reviewed (`outbox/ROUTE-DECISION-01.md`). SOURCE-QUERY-02 was answered (`observations/SOURCE-REPLY-02-CHECK.json`):
  - no copy of any C32 archive survives in the searched folders;
  - the surviving roots equal their receipts in files, bytes and links;
  - the source credential is a GitHub App user token.
- `outbox/SOURCE-ACTION-01.md` FINAL after Fable 5.1 review R22.

## In flight

- The local-only sync worker (`logs/sync-worker.log`); stop it with `tools/STOP_SYNC`.

## Next

1. OA-2: the owner creates the private repository and the draft release `probe-20261013-01`, adds the repository to the ChatGPT GitHub App's access if needed, and sends the approval line. Then the owner pastes `outbox/SOURCE-ACTION-01.md` into the Work task and downloads the asset in the browser.
2. Hash the download (18,445 B, `d01a9b0e...0c67c3`); record PASS or FAIL in `observations/`.
3. OA-3: a loss disposition for the four C32 archives, or a new capture of the two surviving roots.
4. Publish only through `--export-dir`, then scan, review the delta, write a PASS receipt, and push with `--review-receipt`. Pause the local worker during the publish window.

## Routing

Opus 5.5 controls and gates. Sonnet 5.5 takes mechanical Claude work; Haiku 5.5 takes sweeps. Fable 5.1 leads the advisors with GPT-6 Astra as its peer. GPT-6.1 Sol is the Opus-tier ChatGPT executor. Kimi K3 does frontend only. Model identity is taken from runtime metadata, never from a self-report.

## Boundaries that stay in force

- No Drive retry without an evidenced scope change.
- No private evidence in any public repository.
- Raw transcripts, inbox replies and the handoff bundle are never published.
- No credential changes, VM installs, laboratory mutations or G13 attempts.
- No large source tmpfs build without the owner's explicit lift.
- New runs and new captures are new evidence, never recovery of a missing original.
