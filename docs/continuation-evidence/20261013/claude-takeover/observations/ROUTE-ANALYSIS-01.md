# ROUTE-ANALYSIS-01: source-to-receiver route decision (controller draft)

Recorded 2026-10-13T14:55Z by the Claude Code controller. Inputs: the 2026-10-12 handoff package (sections 5 to 14, 19 to 23), `evidence/FINAL-RESULT.json`, `evidence/WORK_EXPORT_FAILURE_USER_REPORT.md`, and the fresh observations in `observations/2026-10-13-host-intake.json`. Status words follow handoff section 1.3.

## Decision in one line

No source-to-receiver route is proven today (Route D). Two Route B candidates exist that the handoff did not evaluate, and one read-only inventory of the source task (`outbox/SOURCE-QUERY-01.md`) decides between them. The receiver side is ready to be approved: WSL2 Ubuntu ext4 on this PC.

## Routes

**Route A: original Work task's Google Drive action. BLOCKED.** File creation returned HTTP 403 `ACCESS_TOKEN_SCOPE_INSUFFICIENT` while metadata reads worked. The likely reading (a hypothesis, not a verified cause) is that the connection holds read-only Drive scopes and no file-creation scope. Only the owner of that ChatGPT connection, or a workspace administrator, can change it, and nothing on this PC can: a Google connection in Claude is a different token. Drive's support for a 1.47 GB upload through that connector is also untested. Retry only after a scope change is evidenced, and then only with the 18,445-byte probe.

**Route B1: the source's own authenticated GitHub write path. CANDIDATE.** Evidence that the path exists: the C32 receipt records `public_branch_delivery: PASS` with 9 anonymous HTTP 200 readbacks matching size and SHA-256, and the remote carries earlier data branches pushed by the same project (`intune-r2-snapshot-data-20261007`, `intune-r3-evidence-data-20261007`). Constraints:
- The destination must be a private repository. `nsahmed23/neon-commons` is public, and handoff section 9 and the start prompt forbid public private-evidence uploads.
- GitHub rejects git blobs over 100 MiB, so `r4-evidence` (1,469,518,188 bytes) cannot travel as a plain git file. Release assets (under 2 GiB each) or Git LFS would carry it unchanged, but only if the source's credential and tooling support them.
- Unknown until SOURCE-QUERY-01 returns: whether the source credential can reach a private repository at all. If it cannot, a new credential would be an owner decision and a new custodian (GitHub), not a workaround.
- This PC can retrieve with the existing `gh` login, then verify bytes against the pins.

**Route B2: a chat attachment or download link from the Work task. UNKNOWN.** The receiving chat delivered this handoff ZIP as a download link, but that was a different environment, and the Work task's own report says it found no callable binary-export operation. If SOURCE-QUERY-01 shows an attachment tool, B2 is the most conservative bridge: the bytes stay with the provider that already holds them, the owner clicks the download, and this PC verifies the hash. Its size limit decides whether it can carry `r4-evidence`.

**Route C: an existing approved copy. NONE KNOWN.** No owner-provided location holds the C32 layers or the missing originals, and the handoff forbids indiscriminate searching. The public R2/R3 tags and data branches are historical recovery sources only.

**Route D: no route yet. CURRENT STATE.** Independent preparation continues meanwhile: M1 public-source verification passed, and the receiver was measured.

## Proposed order once SOURCE-REPLY-01 arrives

1. If all four layers are present and match their pins: run the synthetic bridge (M2) with the existing 18,445-byte probe on the first available route, in this preference order: B2, then B1 (private repository plus release assets), then A after a scope repair.
2. Transfer the three small layers (65.9 MB together) first on the proven route, then `r4-evidence`, then the explicit post-cutoff amendment. Verify every received file against its pin before the next one.
3. If any layer is missing or mismatched: record FAIL for that layer, transfer the survivors, and ask for a scoped loss disposition. Never regenerate a lost layer under its old identity.

## Receiver proposal (needs owner approval: OA-2)

- Location: WSL2 Ubuntu 24.04 ext4, under the owner's Linux home: `~/intune-rescue/{incoming,archives,restored,amendments,observations}`. Created only after approval.
- Why not NTFS: the R4 layer records 640 literal symlinks and 8 FIFO metadata entries. ext4 represents both natively, while NTFS needs elevated rights for symlinks and has no FIFOs. The archive's own restore contract still decides the representation.
- Capacity: C: has 326,692,147,200 bytes free, about 41.7 times the recorded 7,827,771,392-byte scenario. The guest's 1.02 TB figure is a virtual ceiling, not real space.
- Gaps: one physical disk, so no independent failure domain (M5 needs an off-machine copy; OA-4). Host RAM was 2.2 GB available at measurement while the guest reports 14.8 GB, so cap WSL memory or free host memory before a 4.6 GB restore. `zstd` is absent in WSL; whether it is needed depends on the archive format (SOURCE-QUERY-01 step 2).

## Risks for the next 48 hours

1. The tmpfs layers vanish on a source resumption or reset (precedent recorded in C32). Mitigation: send SOURCE-QUERY-01 now, keep it light, and start M2 on the first proven route.
2. A route proven with 18 KB fails at 1.47 GB (size caps, timeouts, partial objects). Mitigation: read documented limits first (query step 5); verify finalized size and hash, never an ID alone.
3. Private evidence reaches a new custodian without classification (GitHub, a Drive folder, this PC, Remote Control transcripts). Mitigation: OA-2 and OA-3 before M3; process raw archives locally and show the model only bounded, redacted results.

## Explicitly not done

No Drive retry, no browser automation of the ChatGPT task, no credentials touched, no VM or WSL configuration change, no product code run, no G13 action, no Wally work.
