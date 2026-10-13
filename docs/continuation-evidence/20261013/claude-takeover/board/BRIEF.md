# KIMI BRIEF - board/index.html - Intune rescue control board

Role: senior frontend engineer. Build one static status page. Controller = Claude (orchestrator). Owner reads page on desktop and phone.

Binding rules:
- Work only in the current directory C:\Dev\Projects\intune-rescue\board. Create or overwrite only index.html. Do not modify ledger.js, ledger.json or BRIEF.md, and do not read files outside this directory.
- index.html must make no network request: no CDN, no web fonts, no remote images, no analytics. Inline all CSS and JS. The only external file it loads is ledger.js from this directory.
- Do not invent data. Render only fields present in window.LEDGER. A missing value shows the text UNKNOWN. An empty list shows the text None.
- Time box: 25 minutes. At the box, save index.html as it is and report.

Input: ledger.js sets window.LEDGER. Same data in ledger.json: read it first to learn the shape. Top-level keys: schema, updated_utc, writer, outcome_flags, owner_asks, lanes, milestones, source_transfer, gates, observations, events.

Steps:
1. Read ledger.json. Map each key to a section below.
2. Write index.html: `<script src="ledger.js"></script>`, then one inline script that renders everything with plain DOM APIs (createElement, textContent). Never put ledger strings into innerHTML. No framework, no build step.
3. Sections, in this order:
   a. Header: title "Intune rescue control board"; updated_utc; the four outcome_flags as "name: VALUE" lines.
   b. "Blocked on owner": owner_asks with id, urgency, ask, blocks. Most prominent section after the header.
   c. "Lanes": table with id, lane, model, role, status, output.
   d. "Milestones": M0 to M8 with id, title, status, evidence.
   e. "Source transfer": table with label, archive_bytes, sha256, manifest_bytes, source_path, availability, destination, readback, restore.
   f. "Gates": table with gate, status, boundary, owner, next_input.
   g. "Fresh observations": observations flattened to key/value rows (for example host.c_free_bytes).
   h. "Events": newest first, utc and text.
4. Status display: status word as text, preceded by an 8px round dot. Dot colors: PASS green; FAIL red; BLOCKED amber; IN_PROGRESS and RUNNING blue; WAITING_ON_OWNER violet; NOT_STARTED, NOT_TESTED, NOT_RECHECKED, NOT_DEFINED, UNKNOWN, NONE, QUEUED gray. Boolean flags as plain text true or false.
5. Look: restrained, Linear or Vercel dashboard style. System font stack. Hairline 1px borders. Radius 8px. No pills, no badges, no letter-spacing, no gradients, no drop shadows, no emoji, no icons. Body 14px; labels 12px muted. Numbers use tabular-nums; byte counts get thousands separators. Hashes show the first 12 characters, with the full hash in a title attribute and still selectable.
6. Theme: color tokens as CSS variables on :root; dark values under @media (prefers-color-scheme: dark); body background set explicitly in both themes.
7. Responsive: works at 360px wide with a 16px side gutter. The page never scrolls sideways; each wide table scrolls inside its own overflow-x container.
8. Self-check before stopping: (a) search index.html for the string "http" and remove any hit; (b) confirm every section renders when its array is empty; (c) compare the page against steps 3 to 7.

Style example (rhythm only, not data):

```
Lanes
L2   advisor-astra   GPT-6 Astra via Codex ...   independent review ...   (dot) RUNNING   lanes/advisor-astra/FINAL.md
```

Report on stdout, caveman full (drop articles and filler, keep paths and numbers): files written with byte sizes; sections done; anything skipped and why. No recap.
