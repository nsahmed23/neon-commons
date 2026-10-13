# BRIEF: publication gate (lane pub-gate, Sonnet 5.5)

Workspace `C:/Dev/Projects/intune-rescue`. Python `py -3.11 -I`. Tests = unittest, same pattern as `tools/test_publish_branch.py` (temp dirs, run scripts via subprocess). Write tests FIRST, see them fail, then implement.

Why: public branch got owner-relayed source reply text via controller log (row = first 1,500 chars of a 69,304-char paste). Owner wants review BEFORE any push, bound to exact file-hash set.

## Task 1: `tools/controller_log.py`
1. Owner message longer than 2,000 chars (after whitespace collapse) -> row text exactly `[owner relay withheld from the published log: <N> chars, sha256 <first 16 hex of sha256(original text utf-8)>; full text kept in the local transcript]`. Both owner paths: user entries and `queued_command` attachments. Dedupe key logic unchanged.
2. Every row, every kind: replace case-insensitive `[posture redacted]`, `[posture redacted]`, `[posture redacted]` (plus optional ` = "never"` / `="never"`), `[posture redacted]`, `[posture redacted]`, `[posture redacted]` with `[posture redacted]`.
3. New `tools/test_controller_log.py`: synthetic transcript only. Cases: long owner msg withheld (planted fake id `ccarenv_TESTONLY0001` absent, prefix hash correct); short owner msg verbatim; posture terms redacted in controller-says and tool rows; owner replay deduped; repeated agent messages kept.

## Task 2: `tools/scan_published.py` + `tools/publish-scan-rules.txt`
1. Rules file: header comment says append-only, never delete or weaken a rule. Lines `id<TAB>severity<TAB>regex`, `#` comments. Seed with the 20 rules in `~/AppData/Local/Temp/claude/C--Users-~/a133a22b-c5ca-4dce-ac02-3ee2deac0cb9/scratchpad/manifest_and_scan.py` (RULES list), same ids, severities, regexes.
2. CLI: `scan_published.py <dir> --rules <file> [--allow <file>] [--json-out <file>]`. Walk dir. Skip content scan for `.zip .png .jpg .jpeg .gif .webp .pdf` (still hashed). Per hit print `SEVERITY rule path:line masked` with mask = first 6 chars of match + `***`. Never print a full match.
3. JSON out: `{"files": {posix relpath: {"bytes": n, "sha256": hex}}, "rules": count, "hits": [...masked...], "high": n}`.
4. Exit 1 if any unsuppressed HIGH; 0 otherwise. Exit 2 if rules file parses to fewer than 15 rules (truncated contract).
5. Allow file `tools/publish-scan-allow.txt`: lines `rule<TAB>relpath<TAB>sha256 of the exact line text`. Suppresses only that line; edited line re-triggers. Seed with ONE entry: rule `memory-file-name`, path `tools/test_publish_branch.py`, the sha256 of its line containing `memory\\project_y.md` (synthetic fixture, uses `{user}` placeholder).
6. New `tools/test_scan_published.py`: planted fake `ghp_` token -> HIGH, exit 1, full token absent from stdout; clean dir exit 0; truncated rules exit 2; allow entry suppresses exact line only; binary file hashed not scanned.

## Task 3: `tools/publish_branch.py`
1. `--export-dir DIR`: write the exact sanitized candidate bytes (output of `collect()`) under DIR by relative path. Refuse non-empty existing DIR (exit 2). No commit, no push; cannot combine with `--push`.
2. `--review-receipt FILE`: JSON with `"verdict"` and `"files"` (same shape as scanner JSON `files`). With `--push`: receipt REQUIRED; missing -> exit 5. Candidate set must equal receipt `files` exactly (same paths, same sha256) and verdict must be `"PASS"`; else print up to 20 differing paths tagged added/removed/changed, exit 5, no commit-tree, no push, ref unchanged.
3. Extend `tools/test_publish_branch.py`: push without receipt refused; mismatch refused; verdict not PASS refused; matching PASS receipt pushes fast-forward; export-dir writes sanitized bytes and refuses non-empty dir. All existing tests still pass.

## Task 4: `tools/sync_worker.py`
Remove `--push`: worker becomes local-only (regenerate logs, snapshot, ledger.js, tables, then publisher `--dry-run`). Update docstring. Starting with `--push` must fail with argparse error.

## Rules
You may edit only files under `tools/` and write `lanes/pub-gate/FINAL.md`.
Do not run any publisher command against `source.git` or any real remote; tests use temporary repositories only.
Do not read `inbox/`, `logs/transcripts/`, or the session transcript.
Do not commit, push, or change git config.
No network access is needed; make no outbound requests.
Time box: 35 minutes. At the box, stop and report what is done and what is not.

## Report (stdout and `lanes/pub-gate/FINAL.md`, caveman full)
Line 1: your model id. Then: files changed, test command, real tail of test output (counts, OK/FAILED), anything not done.
