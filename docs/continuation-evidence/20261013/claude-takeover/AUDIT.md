# Audit trail: Intune Workbench takeover (Claude Code controller)

This file is the entry point to the record of every communication, brief, report, run and decision across all lanes, as the owner directed on 2026-10-13 at 15:09:53Z. Status lives in `ledger/ledger.json` (and the board); this file says where the evidence is and what happened.

## Where everything is

| Record | Path | Written by | Published |
|---|---|---|---|
| Owner messages, agent messages, controller replies, every controller tool call, lane notices, tool errors | `logs/controller-log.md` | `tools/controller_log.py` from the session transcript | yes |
| Append-only event log (directives, briefs, dispatches, reports, relays, verifications, decisions, deviations, failures) | `logs/events.jsonl` | `tools/audit.py event` (system clock) | yes |
| One record per lane run: model requested and confirmed, effort, sandbox, start and end, exit, brief, outputs, transcript, deviations | `logs/runs.jsonl` | `tools/audit.py run` | yes |
| Human-readable tables of both | `logs/AUDIT-TABLES.md` | `tools/audit.py tables` | yes |
| Raw transcripts: Codex rollouts, Kimi sessions, Claude agent and controller transcripts | `logs/transcripts/` with `SHA256SUMS` and `SNAPSHOTS.jsonl` | `tools/audit.py snapshot` | **no, local only** |
| Owner attachments | `logs/owner-attachments/` | controller | yes |
| Lane briefs and lane outputs | `lanes/<lane>/BRIEF*.md`, `FINAL.md`, `REPORT.md`, run logs | controller and lanes | briefs and outputs yes; `*.log` and `*.err` no |
| Messages to and from the ChatGPT Work task | `outbox/` (sent), `inbox/` (received) | controller, owner relay | outbox yes; inbox no |
| Checked results of source replies | `observations/SOURCE-REPLY-*-CHECK.json` | `tools/check_source_reply.py` | yes (sanitized) |
| Publication reviews, bound to exact file hashes | `observations/PUBLICATION-REVIEW-*.json`, `lanes/pub-review/FINAL.md` | controller and review lane | yes |
| Which model really ran each lane (runtime metadata) | `observations/MODEL-EVIDENCE-01.md` | controller | yes |
| Route decision and source queries | `outbox/ROUTE-DECISION-01.md`, `outbox/SOURCE-QUERY-*.md` | controller, advisor-reviewed | yes |
| Stage checkpoints | `.checkpoints/*.json` | controller | yes |

Raw transcripts stay local because they embed the owner's private Claude and Codex configuration and memory, not only this project. Inbox replies stay local. In the published controller log, any owner message longer than 2,000 characters (a relay or paste) appears only as its length and a SHA-256 prefix. Private evidence never enters this folder's published set or any public repository.

## Publication

Since 2026-10-13T17:28Z nothing is pushed automatically. The sync worker (`tools/sync_worker.py`) is local-only: it regenerates the logs, tables and board data and runs a dry-run publish, with no fetch and no push. A publish takes these steps:
1. Export the exact sanitized candidate bytes: `publish_branch.py --export-dir`.
2. Scan them: `tools/scan_published.py` with the append-only `tools/publish-scan-rules.txt` and the line-bound `tools/publish-scan-allow.txt`.
3. Have the delta read by a reviewer.
4. Write a PASS receipt listing every file's SHA-256.
5. Push with `--review-receipt`. The publisher refuses (exit 5) if one byte differs from the receipt.

Commits are fast-forward only on `continuation/r4-20261007` in `github.com/nsahmed23/neon-commons`, under `docs/continuation-evidence/20261013/claude-takeover/`. The publisher never touches `main`. Home paths become `~`, memory-file names and the Remote Control setting value are redacted, and `handoff/` is not published (its `START_HERE.md` line 9 asks not to). The owner accepted public visibility for the work on 2026-10-13 at 15:16:15Z.

## Regenerate by hand

```
py -3.11 -I tools/controller_log.py --transcript ~/.claude/projects/C--Users-~/a133a22b-c5ca-4dce-ac02-3ee2deac0cb9.jsonl
py -3.11 -I tools/audit.py snapshot ~/.claude/projects/C--Users-~/a133a22b-c5ca-4dce-ac02-3ee2deac0cb9.jsonl claude/L0-controller-a133a22b.jsonl --rolling
py -3.11 -I tools/make_ledger_js.py C:/Dev/Projects/intune-rescue
py -3.11 -I tools/audit.py tables
```

## Narrative, 2026-10-13 (UTC)

**Successes**
- 14:37Z: handoff ZIP verified (17 regular files, 16 of 16 checksums). Evidence: `handoff/`.
- 14:46Z: Windows host and WSL Ubuntu measured read-only. Evidence: `observations/2026-10-13-host-intake.json`.
- 14:49Z: M1 PASS, public scope: C32 tip, engine tree, ledger hash and both 0.9.0 packages verified against GitHub. Evidence: `.checkpoints/M1-public-source.json`.
- 15:01Z to 15:02Z: GPT-6 Sol read the public restorer; the controller spot-checked four claims against the code. Evidence: `lanes/m4-prep/FINAL.md`.
- 15:05Z and 15:07Z: both advisors reported (Fable 5.1 confirmed as `claude-fable-5-1`; GPT-6 Astra confirmed in the Codex header). Evidence: `lanes/advisor-fable/REPORT.md`, `lanes/advisor-astra/FINAL.md`.
- 15:23Z: GPT-6 Sol's final query check; SOURCE-QUERY-01 finalized with edits from three reviewers. Evidence: `outbox/SOURCE-QUERY-01.md`, `outbox/SOURCE-QUERY-01.draft-v1.md`.
- 15:29Z: GPT-6 Sol delivered `publish_branch.py` test-first; the controller re-ran 6 of 6 tests on Python 3.11 and reviewed the code. Evidence: `lanes/publisher/FINAL.md`, `tools/publish_branch.py`.
- 15:31Z: first publish, commit 658ff7f4 on `continuation/r4-20261007` (parent d057cc15, 56 files, all under the takeover folder); the sync worker's first cycle pushed de69761f.
- 15:32Z: Codex CLI 0.156.0 updated to 0.162.1; `gpt-6.1-sol` now runs. The earlier HTTP 400 was a client-version gate, not the login.
- 15:35Z: Sonnet 5.5 render check: no page overflow at 360 or 1280 px; Lanes table squeezes at 360 (Kimi pass 03 dispatched).
- 15:40Z to 15:42Z: Haiku 5.5 leak sweep of the first publish (no secrets), then a Sonnet 5.5 redaction fix (encoded home folder, memory-file names, host-intake JSON excluded).
- 17:19Z: the owner relayed SOURCE-REPLY-01 and a ChatGPT correction (inbox, local only). Checked by script: the four C32 archives are ABSENT (ENOENT) in a source runtime that booted 15:52:05Z; the probe is intact (PIN-MATCH). Evidence: `observations/SOURCE-REPLY-01-CHECK.json`.
- 17:28Z: sync worker stopped through `tools/STOP_SYNC` after cycle 12 (7840c407), per the correction.
- 17:32Z to 17:38Z: Sonnet 5.5 lanes built the review-before-push gate (29 tests after controller additions) and reviewed the exact 58 published files at 7840c407. Evidence: `lanes/pub-gate/FINAL.md`, `lanes/pub-review/FINAL.md`, `observations/PUBLICATION-REVIEW-01.json`.
- 17:44Z: model identities re-derived from runtime metadata instead of self-reports; all match. Evidence: `observations/MODEL-EVIDENCE-01.md`.
- 17:45Z: route B1-R proposed (GitHub release asset on an owner-created private repository) and SOURCE-QUERY-02 drafted, sent to Fable 5.1 for review. Evidence: `outbox/ROUTE-DECISION-01.md`, `outbox/SOURCE-QUERY-02.md`.

**Failures and deviations**
- 14:56Z: Astra attempt 1 refused before start: "Not inside a trusted directory and --skip-git-repo-check was not specified." Fix: relaunch with `--skip-git-repo-check`. Evidence: `lanes/advisor-astra/stderr.log`.
- 14:59Z to 15:05Z: Fable's report did not reach the controller until a SendMessage nudge at 15:03Z (a named teammate's plain-text final output is not routed). Evidence: controller log rows at 15:03Z and 15:05Z.
- 15:00Z: Kimi run 01 failed the controller's 380px render gate (sideways overflow); fixed in run 02. Evidence: `lanes/kimi-board/index.run-01.html`, `board/index.html`.
- 15:00Z: the controller's headless Edge render logged a failed component-catalog update despite the disable flags; that background request could not carry the mandated User-Agent.
- 15:07Z: Kimi run 02 ran a headless browser on temp copies outside `board/` (not authorized or forbidden by its brief; no residue).
- 15:19Z: both `gpt-6.1-sol` lanes rejected with HTTP 400, "not supported when using Codex with a ChatGPT account." Fallback: `gpt-6-sol`, same tier. Cause found at 15:32Z: the installed CLI (0.156.0) was too old; 0.162.1 runs the model. Evidence: `lanes/*/stderr-attempt1-gpt-6.1-sol-rejected.log`, `lanes/codex-probe/stderr.log`.
- 15:31Z: the Codex update's pre-check listed two running `codex.exe` processes but did not gate the install. Both belonged to the ChatGPT desktop app's bundled Codex (`AppData/Local/OpenAI/Codex/bin`), separate from the npm install, so they were unaffected.
- Early event labels in the ledger ran ahead of the clock; they were corrected from the session transcript, which is now the only source of event times.
- 15:31Z to 17:22Z: every publish carried `handoff/`, the whole handoff bundle including its ZIP, although `START_HERE.md` line 9 says not to move it into a public repository automatically. It is removed from the allowlist from the next publish onward; commits 658ff7f4 to 7840c407 keep it (OA-6).
- 15:42Z: a controller row said the ledger no longer published the Remote Control setting value. That was wrong: the OA-4 ask still carried it until 17:43Z.
- 17:22:55Z: worker cycle 12 (7840c407) published the first 1,500 characters of the owner's 69,304-character relay of the source reply. That included the Work environment id and runtime boot data; no credential. Cause: the controller log kept owner messages verbatim up to 1,500 characters. Fixed forward by withholding long relays; history keeps it (OA-6).
- Run records R01 to R17 cited "report line 1" or a CLI header as model confirmation. A model's self-report is not evidence; `observations/MODEL-EVIDENCE-01.md` replaces those citations with runtime metadata.
