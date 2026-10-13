# Audit tables

Generated 2026-10-13T17:12:45Z by tools/audit.py from logs/runs.jsonl and logs/events.jsonl.

## Lane runs (17)

| run | lane | executor | model requested / confirmed | effort | sandbox | start / end UTC | exit | status | deviations |
|---|---|---|---|---|---|---|---|---|---|
| R01 | L1 advisor-fable | Claude Agent (architect, read-only tools) | fable / claude-fable-5-1 (report line 1) | agent default | read-only tools | 2026-10-13T14:56:01Z / 2026-10-13T14:59:19Z | n/a | DONE | report reached the controller only after a SendMessage nudge at 15:03Z |
| R02 | L2 advisor-astra | Codex CLI 0.156.0 | gpt-6-astra / none (refused before start) | max | read-only | 2026-10-13T14:56:03Z / 2026-10-13T14:56:05Z | 1 | FAILED | non-git workdir needs --skip-git-repo-check |
| R03 | L2 advisor-astra | Codex CLI 0.156.0 | gpt-6-astra / gpt-6-astra (stderr header and report line 1) | max | read-only | 2026-10-13T14:56:35Z / 2026-10-13T15:07:21Z | 0 | DONE | none |
| R04 | L4 kimi-board | Kimi Code CLI 0.37.2 | kimi-code/k3-256k / UNCONFIRMED (the CLI silently falls back on a mistyped ID; see wire.jsonl) | default | prompt mode, auto permission, cwd board/ | 2026-10-13T14:56:05Z / 2026-10-13T14:59:05Z | 0 | DONE | controller render gate: 380px overflow (fixed in R06) |
| R05 | L5 m4-prep | Codex CLI 0.156.0 | gpt-6-sol / gpt-6-sol (stderr header) | high | read-only | 2026-10-13T14:58:37Z / 2026-10-13T15:01:15Z | 0 | DONE | none |
| R06 | L4 kimi-board | Kimi Code CLI 0.37.2 | kimi-code/k3-256k / UNCONFIRMED (see wire.jsonl) | default | prompt mode, auto permission, cwd board/ | 2026-10-13T15:01:09Z / 2026-10-13T15:07:49Z | 0 | DONE | ran headless Edge on temp copies outside board/ (removed) |
| R07 | L6 sol-query-check | Codex CLI 0.156.0 | gpt-6.1-sol / none (HTTP 400 for ChatGPT-account login) | high | read-only | 2026-10-13T15:19:13Z / 2026-10-13T15:19:24Z | 1 | FAILED | model not entitled on this Codex login |
| R08 | L7 publisher | Codex CLI 0.156.0 | gpt-6.1-sol / none (HTTP 400 for ChatGPT-account login) | high | workspace-write | 2026-10-13T15:19:15Z / 2026-10-13T15:19:26Z | 1 | FAILED | model not entitled on this Codex login |
| R09 | L6 sol-query-check | Codex CLI 0.156.0 | gpt-6-sol / gpt-6-sol (stderr header and report line 1) | high | read-only | 2026-10-13T15:21:43Z / 2026-10-13T15:23:23Z | 0 | DONE | none |
| R10 | L7 publisher | Codex CLI 0.156.0 | gpt-6-sol / gpt-6-sol (stderr header; report line 1 said only GPT-6) | high | workspace-write | 2026-10-13T15:21:45Z / 2026-10-13T15:29:19Z | 0 | DONE | tests ran on Python 3.14 in the sandbox; controller re-ran 6 of 6 green on 3.11; Codex auto-review blocked deleting its own __pycache__ |
| R11 | codex-probe | Codex CLI 0.162.1 | gpt-6.1-sol / gpt-6.1-sol (stderr header) | low | read-only | 2026-10-13T15:32:17Z / 2026-10-13T15:32:17Z | 0 | DONE | none |
| R12 | L8 sync-worker | tools/sync_worker.py (deterministic, no model) | none / UNCONFIRMED | n/a | local process, pushes fast-forward to continuation/r4-20261007 | 2026-10-13T15:31:44Z / None |  | RUNNING | none |
| R13 | L10 render-check | Claude Agent fast-worker | sonnet (alias claude-sonnet-5-5) / claude-sonnet-5-5 (report line 1) | agent default | writes only scratchpad/render-check | 2026-10-13T15:34:13Z / 2026-10-13T15:34:44Z | n/a | DONE | 360px window screenshot clipped by headless Edge; harness iframe measurement used as the authority |
| R14 | L4 kimi-board | Kimi Code CLI 0.37.2 | kimi-code/k3-256k / UNCONFIRMED (see wire.jsonl) | default | prompt mode, auto permission, cwd board/ | 2026-10-13T15:35:32Z / 2026-10-13T15:37:25Z | 0 | DONE | none |
| R15 | L10 render-check | Claude Agent fast-worker (resumed) | sonnet (alias claude-sonnet-5-5) / claude-sonnet-5-5 (report line 1) | agent default | writes only scratchpad/render-check | 2026-10-13T15:37:53Z / 2026-10-13T15:38:23Z | n/a | DONE | none |
| R16 | L9 leak-sweep | Claude Agent Explore (read-only) | haiku / claude-haiku-5-5 (report line 1) | agent default | read-only tools | 2026-10-13T15:34:04Z / 2026-10-13T15:40:36Z | n/a | DONE | made one no-op call to an AWS sandbox tool (self-reported; no access to the target) |
| R17 | L11 redaction-fix | Claude Agent code-editor | sonnet (alias claude-sonnet-5-5) / claude-sonnet-5-5 (report line 1) | agent default | edits limited to three tools/ files | 2026-10-13T15:41:31Z / 2026-10-13T15:42:28Z | n/a | DONE | agent skipped its ASCII check (grep error); controller verified 0 non-ASCII bytes |

## Events (73)

| UTC | actor | kind | lane | summary | refs |
|---|---|---|---|---|---|
| 2026-10-13T14:35:02Z (backfilled) | owner | owner-directive | - | Handoff: path to Intune_Claude_Code_Handoff_2026-10-12.zip plus pasted ChatGPT summary of two handoff packages; take over per the handoff intake. | handoff/Intune_Claude_Code_Handoff_2026-10-12.zip |
| 2026-10-13T14:37:46Z (backfilled) | controller | verification | - | Handoff ZIP: 17 regular-file entries, no unsafe paths; 16 of 16 SHA256SUMS entries match. | handoff/Intune_Claude_Code_Handoff_2026-10-12.zip |
| 2026-10-13T14:38:50Z (backfilled) | owner | owner-directive | - | you need to work with chatgpt and kimi as well |  |
| 2026-10-13T14:39:07Z (backfilled) | owner | owner-directive | - | you are in charge of orchestratring thme and using fable 5.1 as an advisor lane |  |
| 2026-10-13T14:46:02Z (backfilled) | controller | verification | - | Windows host and WSL Ubuntu measured read-only: C: 326,692,147,200 B free on one NVMe; host RAM 2,211 MB available; Ubuntu 24.04.2 ext4, 4096-byte blocks. | observations/2026-10-13-host-intake.json |
| 2026-10-13T14:47:44Z (backfilled) | controller | controller-action | - | Created C:/Dev/Projects/intune-rescue; copied the original handoff ZIP; extraction re-verified 16 of 16. |  |
| 2026-10-13T14:48:59Z (backfilled) | controller | verification | M1 | M1 PASS (public scope): continuation tip d057cc15 is C32; engine 39cc7761 tree f8bff355; ledger 2,025,195 B sha d6b787c6 matches; both 0.9.0 packages match bytes and SHA-256 at f9104700. | .checkpoints/M1-public-source.json |
| 2026-10-13T14:52:50Z (backfilled) | controller | brief | L3 | SOURCE-QUERY-01 v1 drafted: read-only inventory for the original ChatGPT Work task. | outbox/SOURCE-QUERY-01.draft-v1.md |
| 2026-10-13T14:53:16Z (backfilled) | controller | decision | - | ROUTE-ANALYSIS-01: no proven route (state D); candidates B2 chat download, B1 private GitHub, A Drive after scope repair. | observations/ROUTE-ANALYSIS-01.md |
| 2026-10-13T14:56:01Z (backfilled) | controller | dispatch | L1 | L1 Fable 5.1 advisor dispatched (Agent, architect type, read-only tools, 20 min box). | lanes/advisor-fable/BRIEF.md |
| 2026-10-13T14:56:03Z (backfilled) | controller | dispatch | L2 | L2 GPT-6 Astra advisor dispatched via Codex (read-only sandbox, effort max). | lanes/advisor-astra/BRIEF.md |
| 2026-10-13T14:56:05Z (backfilled) | controller | dispatch | L4 | L4 Kimi K3 256k dispatched to build board/index.html (25 min box). | board/BRIEF.md |
| 2026-10-13T14:56:28Z (backfilled) | controller | failure | L2 | L2 attempt 1 refused before start: 'Not inside a trusted directory and --skip-git-repo-check was not specified.' | lanes/advisor-astra/stderr.log |
| 2026-10-13T14:56:35Z (backfilled) | controller | dispatch | L2 | L2 attempt 2 relaunched with --skip-git-repo-check; header confirmed gpt-6-astra, read-only, effort max. |  |
| 2026-10-13T14:58:37Z (backfilled) | controller | dispatch | L5 | L5 GPT-6 Sol dispatched to read the public snapshot builder and restorers (read-only, effort high). | lanes/m4-prep/BRIEF.md |
| 2026-10-13T14:59:05Z (backfilled) | kimi | report | L4 | L4 run 01 finished: index.html 10,850 B; inputs untouched. | lanes/kimi-board/kimi-run-01.out, lanes/kimi-board/index.run-01.html |
| 2026-10-13T14:59:19Z (backfilled) | fable-advisor | agent-message | L1 | L1 finished (idle notification) but its plain-text report did not reach the controller. |  |
| 2026-10-13T14:59:45Z (backfilled) | controller | verification | L4 | L4 run 01 static gate PASS: no network references, no innerHTML, only ledger.js loaded. |  |
| 2026-10-13T15:00:06Z (backfilled) | controller | deviation | L4 | Controller's headless Edge render logged one failed component-catalog update despite the disable flags; that request could not carry the mandated User-Agent. |  |
| 2026-10-13T15:00:20Z (backfilled) | controller | verification | L4 | L4 run 01 render gate: desktop PASS; 380px FAIL (header and cards overflow sideways). |  |
| 2026-10-13T15:01:09Z (backfilled) | controller | dispatch | L4 | L4 run 02 polish dispatched with four defects (overflow, width, dot scoping, viewport). | board/BRIEF-02.md |
| 2026-10-13T15:01:15Z (backfilled) | gpt-6-sol | report | L5 | L5 report: ZIP plus JSON manifest; POSIX-only stdlib restorer; FIFO entries are pinned omissions; no free-space check; fresh output root per attempt. | lanes/m4-prep/FINAL.md |
| 2026-10-13T15:02:33Z (backfilled) | controller | verification | L5 | L5 spot-check PASS against code: POSIX guard, limits (200,000 members, 32 GiB, 64 MiB manifest), FIFO handling, no free-space check. |  |
| 2026-10-13T15:03:05Z (backfilled) | controller | relay-out | L1 | Asked fable-advisor to resend its Q1-Q5 report via SendMessage. |  |
| 2026-10-13T15:04:56Z (backfilled) | controller | decision | L3 | Fable's query edits applied; v1 preserved as SOURCE-QUERY-01.draft-v1.md. | outbox/SOURCE-QUERY-01.draft-v1.md |
| 2026-10-13T15:05:19Z (backfilled) | fable-advisor | report | L1 | L1 report delivered; model claude-fable-5-1. Key points: B1 is a new custodian needing explicit owner authorization; never push to origin; amendment is a separate source write; 7 query edits. | lanes/advisor-fable/REPORT.md |
| 2026-10-13T15:07:21Z (backfilled) | gpt-6-astra | report | L2 | L2 report; model gpt-6-astra. Key points: no automatic partial transfer; decouple M2 from layer availability; no auth/API calls in the query (overruled: Fable leads). | lanes/advisor-astra/FINAL.md |
| 2026-10-13T15:07:36Z (backfilled) | owner | owner-directive | - | Use 6.1 sol |  |
| 2026-10-13T15:07:49Z (backfilled) | kimi | report | L4 | L4 run 02 finished: index.html 11,556 B; 4 defects fixed; Kimi verified 360px in headless Edge on temp copies it removed. | lanes/kimi-board/kimi-run-02.out |
| 2026-10-13T15:09:07Z (backfilled) | owner | owner-directive | - | Sol and opus are equivalents in my head with opus 5.5 leading. Then Astra and fable are equivalents with fable 5.1 leading |  |
| 2026-10-13T15:09:07Z (backfilled) | controller | decision | - | Routing set: Opus 5.5 leads, GPT-6.1 Sol is its ChatGPT-side peer; Fable 5.1 leads the advisor tier, GPT-6 Astra is its peer. The Fable-vs-Astra conflict on step 5b resolves for Fable. |  |
| 2026-10-13T15:09:53Z (backfilled) | owner | owner-directive | - | Make sure we are documenting and creating logs for all communication and documentation and work being done across all agents |  |
| 2026-10-13T15:10:15Z (backfilled) | controller | deviation | L4 | L4 run 02 launched a headless browser and wrote temp copies outside board/; the brief neither authorized nor forbade it; no residue found. |  |
| 2026-10-13T15:13:05Z (backfilled) | owner | owner-directive | - | Make sure we have a background worker updating our branch with this work as well |  |
| 2026-10-13T15:14:32Z (backfilled) | owner | owner-directive | - | There seems to be a bunch of branches open (screenshot of 12 neon-commons branches) | logs/owner-attachments/2026-10-13T151432Z-github-branches.png |
| 2026-10-13T15:16:15Z (backfilled) | owner | owner-directive | - | No one looks at my GitHub so it's probs fine |  |
| 2026-10-13T15:16:15Z (backfilled) | controller | decision | - | Publish sanitized work products as fast-forward commits on continuation/r4-20261007 under docs/continuation-evidence/20261013/claude-takeover/; no new branch, never main, never force. Raw transcripts, inbox replies an... |  |
| 2026-10-13T15:19:13Z (backfilled) | controller | dispatch | L6 | Sol query check dispatched on gpt-6.1-sol (read-only, effort high). | lanes/sol-query-check/BRIEF.md |
| 2026-10-13T15:19:15Z (backfilled) | controller | dispatch | L7 | Publisher implementation dispatched on gpt-6.1-sol (workspace-write, effort high, TDD). | lanes/publisher/BRIEF.md |
| 2026-10-13T15:19:24Z (backfilled) | controller | verification | - | Branch map: 12 branches; 6 fully contained in another branch or tag (wally handoff, r2, r3; source 0.7.0, 0.8.0; pre-migration); 6 hold unique history. |  |
| 2026-10-13T15:20:55Z (backfilled) | controller | failure | - | Both gpt-6.1-sol lanes rejected before work: HTTP 400 'The gpt-6.1-sol model is not supported when using Codex with a ChatGPT account.' | lanes/sol-query-check/stderr-attempt1-gpt-6.1-sol-rejected.log, lanes/publisher/stderr-attempt1-gpt-6.1-sol-rejected.log |
| 2026-10-13T15:21:43Z (backfilled) | controller | dispatch | L6 | Sol query check relaunched on fallback gpt-6-sol (same tier). |  |
| 2026-10-13T15:21:45Z (backfilled) | controller | dispatch | L7 | Publisher relaunched on fallback gpt-6-sol (same tier). |  |
| 2026-10-13T15:23:11Z (backfilled) | controller | controller-action | - | Raw transcripts snapshotted to logs/transcripts/ (local only) with SHA256SUMS: Codex rollouts, Kimi sessions, Fable subagent, controller session. | logs/transcripts/SHA256SUMS |
| 2026-10-13T15:23:23Z (backfilled) | gpt-6-sol | report | L6 | L6 report; model gpt-6-sol: 7 line edits (two contradictions from the merge, mid-hash change guard, User-Agent on source HEAD checks). | lanes/sol-query-check/FINAL.md |
| 2026-10-13T15:24:52Z (backfilled) | controller | decision | L3 | SOURCE-QUERY-01 final: Sol edits adopted; gh auth status replaced by the gh api header check, which can carry the User-Agent. | outbox/SOURCE-QUERY-01.md |
| 2026-10-13T15:29:20Z | controller | checkpoint | - | Ledger refreshed: lanes L1-L5 done, L6 done on gpt-6-sol, L7 running, L8 queued; owner asks restructured OA-1 to OA-5. | ledger/ledger.json, AUDIT.md |
| 2026-10-13T15:31:38Z | controller | controller-action | - | First publish: commit 658ff7f4 on continuation/r4-20261007 (parent d057cc15, C32), 56 files under docs/continuation-evidence/20261013/claude-takeover/, fast-forward, main untouched. | tools/publish_branch.py, tools/publish-allowlist.txt |
| 2026-10-13T15:31:52Z | sync-worker | controller-action | - | Published audit trail to continuation/r4-20261007: de69761fb2287c1a3bebb4a9267a7962ada66c9e |  |
| 2026-10-13T15:32:18Z | controller | deviation | - | Codex CLI updated 0.156.0 -> 0.162.1 (owner asked to refresh Codex). The pre-check listed two running codex.exe processes but did not gate the install; both belong to the ChatGPT desktop app's bundled Codex (AppData/L... |  |
| 2026-10-13T15:33:30Z | controller | verification | - | gpt-6.1-sol probe PASS on Codex CLI 0.162.1 (header model gpt-6.1-sol, exit 0): the HTTP 400 was a client-version gate, not the login. Sol-tier lanes use gpt-6.1-sol from now on. | lanes/codex-probe/stderr.log |
| 2026-10-13T15:33:30Z | owner | owner-directive | - | We should be using sonnet 5.5 and haiku 5.5 wherever appropriate |  |
| 2026-10-13T15:34:36Z | controller | dispatch | L9 | Haiku leak sweep of the 56 published files (Explore agent, model haiku, read-only, 15 min box). |  |
| 2026-10-13T15:34:36Z | controller | dispatch | L10 | Sonnet 5.5 board render check at 360, 380 and 1280 px (fast-worker, model sonnet, 15 min box). |  |
| 2026-10-13T15:35:39Z | sonnet-5-5 | report | L10 | Render check: no page overflow at 360 or 1280 (scrollWidth equals clientWidth); Lanes table squeezes to one character per line at 360 instead of scrolling; dark theme readable; dots only on status columns. |  |
| 2026-10-13T15:35:39Z | controller | dispatch | L4 | Kimi polish pass 03: tables keep a minimum width and scroll inside their containers on phones. | board/BRIEF-03.md |
| 2026-10-13T15:37:59Z | kimi | report | L4 | Pass 03: table min-width 720px inside scroll containers; long cells floor at 18ch; index.html 11,635 B. Controller static gate PASS; render re-check sent back to the Sonnet 5.5 agent. | board/index.html |
| 2026-10-13T15:39:05Z | sonnet-5-5 | report | L10 | Re-check after Kimi pass 03: page 360/360 and 1280/1280; all five tables scroll inside their containers (753, 720, 1101, 720, 720 over 326 at 360); narrowest Lanes model cell 136 px. PASS. |  |
| 2026-10-13T15:39:05Z | controller | verification | L4 | Controller viewed the 360px harness screenshot: header and owner-ask cards wrap, tables scroll in place. Board lane closed. |  |
| 2026-10-13T15:39:41Z | controller | deviation | - | controller_log.py de-duplicated identical lane notices, dropping a second completion of the same agent; fixed to de-duplicate owner replays only. R15 end time corrected from the regenerated log. | tools/controller_log.py |
| 2026-10-13T15:41:50Z | haiku-5-5 | report | L9 | Leak sweep of published commit 658ff7f4: secrets NONE; personal contact data NONE (fixture email only); LOW local-identity hints (C--Users-<user> encoding, hardware, UUIDs); MEDIUM private tooling posture (Codex defau... |  |
| 2026-10-13T15:41:50Z | haiku-5-5 | deviation | L9 | Explore agent self-reported one stray no-op call to an AWS sandbox tool; it printed noop and touched nothing. |  |
| 2026-10-13T15:41:50Z | controller | decision | - | Redact going forward (no history rewrite; that would need a force push and the owner's call): exclude host-intake JSON from publishing, sanitize C--Users-<user> and memory-file names, drop the Remote Control field fro... |  |
| 2026-10-13T15:42:00Z | sync-worker | controller-action | - | Published audit trail to continuation/r4-20261007: 0f869f5b5dff6cda4217ba1ce004d57494c48427 |  |
| 2026-10-13T15:43:48Z | controller | verification | L11 | Redaction gate PASS: 7 of 7 tests on 3.11, ASCII clean; dry-run commit shows 0 files with the encoded home folder, host-intake JSON excluded, 18 memory names redacted. Accepted residual: one earlier controller reply i... | tools/publish_branch.py |
| 2026-10-13T15:52:05Z | sync-worker | controller-action | - | Published audit trail to continuation/r4-20261007: ed7bded1dd66b82fba7c18e250692657dd6f650a |  |
| 2026-10-13T16:02:11Z | sync-worker | controller-action | - | Published audit trail to continuation/r4-20261007: 84b308ee887a9e1eee6130f4b8a36d5f6d39c4fd |  |
| 2026-10-13T16:12:16Z | sync-worker | controller-action | - | Published audit trail to continuation/r4-20261007: 7d874f04a7ecbe0f04697a2192cdef02875952be |  |
| 2026-10-13T16:22:22Z | sync-worker | controller-action | - | Published audit trail to continuation/r4-20261007: cab90042b6e319303d321feb3336ede1941a76d1 |  |
| 2026-10-13T16:32:28Z | sync-worker | controller-action | - | Published audit trail to continuation/r4-20261007: 042ee72f667b0b3f734d2bd3c0aab7e01c9b1070 |  |
| 2026-10-13T16:42:34Z | sync-worker | controller-action | - | Published audit trail to continuation/r4-20261007: 6fce451282ae1d94cf18401b2fcede623f03d80e |  |
| 2026-10-13T16:52:39Z | sync-worker | controller-action | - | Published audit trail to continuation/r4-20261007: 4fa09634ba1e2aa3ba160be3ef9304be5480b8b1 |  |
| 2026-10-13T17:02:45Z | sync-worker | controller-action | - | Published audit trail to continuation/r4-20261007: ef9b797e62d1a6934e539ea3a302f7911960db9d |  |
