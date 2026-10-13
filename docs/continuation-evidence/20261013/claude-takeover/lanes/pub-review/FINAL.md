<!-- Final report of lane pub-review (R19), copied from its transcript; API-reported model claude-sonnet-5-5; message at 2026-10-13T17:35:38.513Z. -->

Model: claude-sonnet-5-5

Verdict: **NEW-FINDINGS**. No credentials, emails or phone numbers found. The new items are posture and identity leaks, MEDIUM at worst. Everything is in 58 exported files at 7840c407.

**Findings table.** Paths are relative to `.../claude-takeover/`.

| file | line | cat | sev | what | fix |
|---|---|---|---|---|---|
| ledger/ledger.json | 33 | 4 | MEDIUM | OA-4 ask states the owner's Claude Remote Control setting ([setting redacted]) and says it syncs transcripts. Controller-log line 255 says the ledger "no longer publishes the Remote Control setting". At this commit it still does. | Strip the setting text from the OA-4 ask and regenerate. |
| board/ledger.js | 34 | 4 | MEDIUM | Same OA-4 text; generated copy of ledger.json. | Regenerate after the ledger fix. |
| lanes/advisor-fable/REPORT.md | 28 | 4 | LOW | Mentions the Remote Control setting as true and cites host-intake line 43. | Redact the clause, or accept the leak. |
| handoff/Intune_Claude_Code_Handoff_2026-10-12/evidence/LIBRARY-ROUNDTRIP-RESULT.json | 14-19 | 5 | MEDIUM | ChatGPT personal Library ids for a synthetic ZIP: `directory_id`, `file_id`, `library_file_id`, plus a run id. They tie to the owner's ChatGPT account. | Owner decision. Files under handoff/ are published byte-identical by design. |
| handoff/.../HANDOFF_STATE.json | 63 | 5 | LOW | Same `library_file_id`. | Same as above. |
| handoff/.../CLAUDE_CODE_HANDOFF.md | 277-278 | 5 | LOW | Same Library file ids. | Same as above. |
| handoff/.../evidence/FINAL-RESULT.json | 26-134 | 5 | LOW | Source-environment detail: `/workspace` paths, `instance129`, `as118`, uid 1000, receipt paths and hashes. | Likely already public via C32; owner to confirm. |
| handoff/ (START_HERE.md:9, CLAUDE_START_PROMPT.md) | 9 | 6 | MEDIUM | The handoff says not to move the bundle into a public repository automatically. The whole bundle, including the zip, is now public. The owner accepted public visibility for the work, but not necessarily for this bundle. | Owner confirms, or drops handoff/ from the allowlist going forward. |
| handoff/.../HANDOFF_STATE.json | 106-115 | 3 | LOW | Hardware: Minisforum UM870 Slim, Ryzen 7 8745H, 32 GB RAM, 1 TB NVMe, Windows 11 Pro. | Accept. |
| handoff/.../CLAUDE_CODE_HANDOFF.md | 166, 190, 689 | 2 | LOW | ChatGPT storage "4.11 GB of 100 GB"; mini-PC model; "employer approval" and organizational-evidence wording. No employer is named. | Accept. |
| handoff/.../SOURCE_NOTES.md | 128-130 | 6 | LOW | Mini-PC model, owner tool preferences, and a mention of unrelated "DEX scoring" files. | Accept. |
| ledger/ledger.json, board/ledger.js | 311-326 | 3 | LOW | Host CPU, RAM total, disk, Claude Code 2.1.296, WSL distro and missing tools. | Accept, or drop `observations.host` and `observations.wsl`. |
| logs/events.jsonl | 5 | 3 | LOW | Free bytes on C:, RAM, and the Ubuntu version. The same text is in `logs/AUDIT-TABLES.md` line 35. | Accept. |
| logs/controller-log.md | 4, 18 and similar | 3 | LOW | Session id `a133a22b-...` in the header and in the scratchpad paths. | Accept. |
| AUDIT.md | 28-29 | 3 | LOW | Sanitized `~/.claude/projects/C--Users-~/` paths. This shows the Claude project-dir layout only. | Accept. |
| logs/controller-log.md | 14, 32-40, 143 | 4 | LOW | 12+ "Read ~\.claude\projects\...\memory\[redacted].md" rows. They show that a memory-file set exists, but the names are redacted. | Accept. |
| logs/controller-log.md | 49, 50, 217 | 4 | LOW | Tool-call descriptions: grep for remote-control, model and EFFORT settings; check Codex defaults and the gh login file; check model alias overrides. They show the owner's config is being probed, with no values. | Accept. |
| logs/runs.jsonl | 4, 6, 14 | 4 | LOW | Kimi lane run in "prompt mode, auto permission". Same text in `logs/AUDIT-TABLES.md` lines 12, 14, 22 and in `tools/backfill_20261013.py` lines 184, 196. | Accept. |
| logs/runs.jsonl, logs/AUDIT-TABLES.md, lanes/publisher/FINAL.md | runs.jsonl 10; FINAL.md 23 | 4 | LOW | Lane sandboxes (`read-only`, `workspace-write`), Codex "auto-review" blocking a delete, and Codex ChatGPT-account login mode. | Accept. |
| logs/runs.jsonl | 1-17 | 3 | LOW | Local transcript paths with Codex rollout and Kimi session UUIDs. The files are local-only, but their names are public. | Accept. |
| logs/events.jsonl, AUDIT.md | events 50; AUDIT 55 | 3 | LOW | `AppData/Local/OpenAI/Codex/bin` path and the "ChatGPT desktop app's bundled Codex" detail. | Accept. |
| lanes/publisher/FINAL.md | 5 | 3 | LOW | Sanitized `~\AppData\Local\Python\bin\python.exe` path. | Accept. |
| outbox/SOURCE-QUERY-01.md and draft-v1 | 3, 10-11 | 5 | LOW | Source-environment ids (`instance129`, `as118`, uid 1000) and `/workspace`, `/tmp` layout. This is the same content as the C32 receipt. | Accept. |

**Known items, locations confirmed:**
- `logs/controller-log.md` line 262: owner relay row with source-environment JSON.
  - It holds an environment id (`ccarenv_b64_...`), uid, kernel boot time, pid1 timing, spec revisions, the repo path and HEAD, and the start of the archive list. HIGH.
- `logs/controller-log.md` lines 252 and 259: posture text.
  - Line 252 has `[posture redacted]` and `[posture redacted]`, plus the memory-file and home-path summary. Line 259 has `[posture redacted]`.
- `tools/test_publish_branch.py` lines 27, 29, 222: synthetic fixtures (`fixture@example.test`, memory file `project_y.md`).
  - These fixtures include the `{user}` placeholder in the Windows-path forms.
  - Line 222 also builds a `C--Users-{user}` form from the runtime username, not a literal.

**Cleared:**
- No literal local username in any published file.
- The host-intake JSON is correctly absent.
- No auth headers, tokens or keys.

**Coverage.** READ means fully read; every text file was read.

READ:
- Dynamic files (all read): `logs/controller-log.md`, `logs/events.jsonl`, `logs/runs.jsonl`, `logs/AUDIT-TABLES.md`, `ledger/ledger.json`, `board/ledger.js`, `AUDIT.md`, `resume.md`
- `.checkpoints/M0-intake.json`, `.checkpoints/M1-public-source.json`
- `lanes/` text files: `advisor-astra/BRIEF.md`, `advisor-astra/FINAL.md`, `advisor-fable/BRIEF.md`, `advisor-fable/REPORT.md`, `codex-probe/FINAL.md`, `kimi-board/kimi-run-01.out`, `kimi-run-02.out`, `kimi-run-03.out`, `m4-prep/BRIEF.md`, `m4-prep/FINAL.md`, `publisher/BRIEF.md`, `publisher/FINAL.md`, `sol-query-check/BRIEF.md`, `sol-query-check/FINAL.md`
- `observations/ROUTE-ANALYSIS-01.md`
- `outbox/SOURCE-QUERY-01.md`, `outbox/SOURCE-QUERY-01.draft-v1.md`
- `board/BRIEF.md`, `board/BRIEF-02.md`, `board/BRIEF-03.md`, `board/index.html`
- `tools/` files: `audit.py`, `backfill_20261013.py`, `controller_log.py`, `make_ledger_js.py`, `publish-allowlist.txt`, `publish_branch.py`, `sync_worker.py`, `test_publish_branch.py`
- `handoff/Intune_Claude_Code_Handoff_2026-10-12/` text files, all read: `CLAUDE_CODE_HANDOFF.md` (lines 1-768), `CLAUDE_START_PROMPT.md`, `START_HERE.md`, `SOURCE_NOTES.md`, `SOURCE_REGISTER.json`, `HANDOFF_STATE.json`, `HANDOFF_PACKAGE_MANIFEST.json`, `PACKAGE_QA.json`, `SHA256SUMS`, `evidence/FINAL-RESULT.json`, `evidence/LIBRARY-ROUNDTRIP-RESULT.json`, `evidence/WORK_EXPORT_FAILURE_USER_REPORT.md`, `reference/ARCHIVE_LAYER_PINS.json`, `reference/MISSING_ORIGINALS_EXTRACT.json`, `reference/PACKAGE_PINS.json`, `worksheets/RECEIVER_AND_AUTHORIZATION.md`

NOT-READ (binary, skipped per the brief):
- `handoff/Intune_Claude_Code_Handoff_2026-10-12.zip`. Not checked that its contents equal the extracted tree. Its hash is pinned in the logs.
- `handoff/.../evidence/synthetic_library_probe.zip`, synthetic.
- `logs/owner-attachments/2026-10-13T151432Z-github-branches.png`. Screenshot of the owner's GitHub branches page. It could show account name, avatar, private repo names or browser chrome. Someone should view it by eye before it counts as clean.

Not looked at, per rules: `inbox/`, `logs/transcripts/`, session transcripts. No git, no network, no edits.

**Verdict: NEW-FINDINGS.** Two items need action:
1. The Remote Control setting is still published, in `ledger/ledger.json` line 33 and `board/ledger.js` line 34, although the log claims it was removed.
2. The owner should rule on publishing the whole handoff bundle: it has Library ids, hardware details, and its own "do not publish" instruction.

Everything else is LOW and acceptable.

Files: `~/AppData/Local/Temp/claude/C--Users-~/a133a22b-c5ca-4dce-ac02-3ee2deac0cb9/scratchpad/review-7840c407/docs/continuation-evidence/20261013/claude-takeover/`
