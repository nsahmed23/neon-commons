# BRIEF 03: delta review for reviewed publish 03 (lane pub-review, run R23)

Same lane, same categories 1-6 as BRIEF.md. Candidate = exact sanitized bytes from `publish_branch.py --export-dir`:

`~/AppData/Local/Temp/claude/C--Users-~/a133a22b-c5ca-4dce-ac02-3ee2deac0cb9/scratchpad/candidate-04/`

Baseline = the public commit 7a9716b9, whose 56 files are listed with SHA-256 in `C:/Dev/Projects/intune-rescue/observations/PUBLICATION-REVIEW-02.json` (`files`). You already read those bytes in R19 and R21. Delta list: `.../scratchpad/candidate-04.delta.json`. Deterministic scan of the candidate: `.../scratchpad/candidate-04.scan.json`.

## Do
1. Read every ADDED and CHANGED file in full. Skip unchanged files.
2. Content new since R21 deserves extra care:
   - `observations/SOURCE-REPLY-02-CHECK.json` and `tools/check_source_reply_02.py`: source-reply facts in sanitized form. Flag anything beyond pins, counts, statuses, the two input-root paths, the GitHub client type, the public login and the boot time. Flag any evidence-tree path other than those two roots, any attachment id, and any credential material.
   - `outbox/SOURCE-ACTION-01.md` and `outbox/ROUTE-DECISION-01.md`: these instruct a write in the source task. Confirm they cannot print a credential and name only the new private repository.
   - `logs/controller-log.md`: owner relay rows must show only length and hash. The short owner rows (a Gemini note, "Test it") are fine verbatim.
3. Confirm no `handoff/` path exists and no posture or Remote Control setting value appears outside `.py` files.

## Rules
This lane is read-only: do not edit, move or delete any file anywhere.
Do not open `C:/Dev/Projects/intune-rescue/inbox/`, `logs/transcripts/`, or any session transcript.
Make no network requests and run no git commands.
Time box: 15 minutes.

## Report (final message, caveman full)
Line 1: your model id. Findings table (file, line, category, severity, what, fix) for NEW issues only. Confirmations for Do 2 and Do 3. Coverage list (READ or NOT-READ per added or changed file). Verdict: PASS (no new HIGH or MEDIUM) or FAIL.
