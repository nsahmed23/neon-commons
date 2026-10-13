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
- OA-2 done; SOURCE-ACTION-01 ran at 18:50Z. Preflight, privacy check and release lookup passed; the upload to uploads.github.com failed with HTTP 401 Bad credentials. Nothing was uploaded and nothing was retried.
- SOURCE-QUERY-03 (diagnosis) was replaced by `outbox/SOURCE-QUERY-04.md` at 20:11Z. The owner said "This isn’t a cybersecurity issue", and the 03 upload-host read returns 400 for any login (`observations/UPLOAD-HOST-CALIBRATION-01.json`).
- SOURCE-REPLY-04 checked PASS (`observations/SOURCE-REPLY-04-CHECK.json`). Route B1-R is closed for the Work task, because only uploads.github.com rejects its login. Git and Git LFS 3.6.1 reach the private repository from there.
- Route B1-L (Git LFS) is in `outbox/ROUTE-DECISION-02.md` and `outbox/SOURCE-ACTION-02.md`.
  - SOURCE-ACTION-02 is FINAL after Fable R24, with all fixes applied.
  - The owner accepted the Git LFS User-Agent exception for the Work task at 20:39Z and 20:40Z.
- **M2 PASS at 20:47:05Z** (`observations/PROBE-B1L-01.json`):
  - the Work task pushed the probe through Git LFS to branch `probe-lfs-20261013-01` (commit 6dfaddbd);
  - `tools/fetch_lfs_probe.py` downloaded it here with the required User-Agent, and the size and SHA-256 match the source pin;
  - the source reply, refs, commit author and release were all checked.
- Finding: the Work task's clock runs 149 to 334 s behind this PC's.

## In flight

- The local-only sync worker (`logs/sync-worker.log`); stop it with `tools/STOP_SYNC`.

## Next

1. OA-3 (owner): a loss disposition for the four C32 archives, or a new capture of the two surviving roots through B1-L.
   - A capture needs data classification, destination approval and a one-time lift of the large-source-tmpfs boundary.
   - It also needs files under 2 GB each.
   - The audience is every app with access to all repositories, and LFS objects are removable only by deleting the repository.
2. After an OA-3 decision, draft the capture plan and have Fable and Astra review it independently.
3. Publish only through `--export-dir`, then scan, review the delta, write a PASS receipt, and push with `--review-receipt`. Pause the local worker during the publish window. The next publish carries SOURCE-QUERY-03/04, ROUTE-DECISION-02, SOURCE-ACTION-02, the new tools and observations, R24, the ledger and the logs.

## Routing

Opus 5.5 controls and gates. Sonnet 5.5 takes mechanical Claude work; Haiku 5.5 takes sweeps. Fable 5.1 leads the advisors with GPT-6 Astra as its peer. GPT-6.1 Sol is the Opus-tier ChatGPT executor. Kimi K3 does frontend only. Model identity is taken from runtime metadata, never from a self-report.

## Boundaries that stay in force

- No Drive retry without an evidenced scope change.
- No private evidence in any public repository.
- Raw transcripts, inbox replies and the handoff bundle are never published.
- No credential changes, VM installs, laboratory mutations or G13 attempts.
- No large source tmpfs build without the owner's explicit lift.
- New runs and new captures are new evidence, never recovery of a missing original.
