# BRIEF 04: delta review for reviewed publish 04 (lane pub-review, run R25)

Same lane, same categories 1-6 as BRIEF.md. Candidate = exact sanitized bytes from `publish_branch.py --export-dir`:

`~/AppData/Local/Temp/claude/C--Users-~/a133a22b-c5ca-4dce-ac02-3ee2deac0cb9/scratchpad/candidate-06/`

Baseline = public commit c7170215, whose 62 files are listed with SHA-256 in `C:/Dev/Projects/intune-rescue/observations/PUBLICATION-REVIEW-03.json` (`files`). You read those bytes in R19, R21 and R23. Delta list: `.../scratchpad/candidate-06.delta.json`. Deterministic scan of the candidate: `.../scratchpad/candidate-06.scan.json` (0 HIGH; 2 MEDIUM email hits in the delta, both the synthetic commit identity `probe@example.invalid`).

## Do
1. Read every ADDED and CHANGED file in full. Skip unchanged files.
2. New content that needs extra care:
   - `outbox/SOURCE-QUERY-03.md`, `outbox/SOURCE-QUERY-04.md`, `outbox/SOURCE-ACTION-02.md`, `outbox/ROUTE-DECISION-02.md`: instructions for the source task. Confirm none can print a credential, and that they name only the private repository `nsahmed23/intune-evidence-custody` and its one probe branch.
   - `tools/fetch_lfs_probe.py`, `tools/check_probe_b1l.py`, `tools/check_source_reply_04.py`, `tools/lfs_ua_loopback_test.py`, `tools/fetch_probe.py`: confirm no token, signed URL or batch header is printed or saved.
   - `observations/PROBE-B1L-01.json`, `observations/SOURCE-REPLY-04-CHECK.json`, `observations/UPLOAD-HOST-CALIBRATION-01.json`: flag anything beyond pins, counts, statuses, commit and blob ids, ref names, GitHub request ids, the synthetic commit identity, the local incoming path, and the probe zip member names.
   - `logs/controller-log.md`: owner rows since 18:30Z. Relays over 2,000 characters must show only length and hash. Shorter relays (SOURCE-REPLY-04, SOURCE-ACTION-REPLY-02) appear verbatim; confirm they hold no credential. Screenshot rows must not describe personal notifications or app lists beyond what is in prior PASSed rows.
   - `lanes/advisor-fable/REPORT-R24.md` (verbatim advisor text) and the CHANGED `lanes/advisor-fable/REPORT-R22.md` and `outbox/ROUTE-DECISION-01.md`: say what changed versus the baseline and whether it is benign.
3. Confirm no `handoff/` or `inbox/` path exists, and no posture or Remote Control setting value appears outside `.py` files.

## Rules
This lane is read-only: do not edit, move or delete any file anywhere.
Do not open `C:/Dev/Projects/intune-rescue/inbox/`, `logs/transcripts/`, `incoming/`, or any session transcript.
Make no network requests and run no git commands.
Time box: 15 minutes.

## Report (final message, caveman full)
Line 1 exactly: `R25 VERDICT: PASS` or `R25 VERDICT: FAIL`. Line 2: your model id. Findings table (file, line, category, severity, what, fix) for NEW issues only. Confirmations for Do 2 and Do 3. Coverage list (READ or NOT-READ per added or changed file). PASS means no new HIGH or MEDIUM.
