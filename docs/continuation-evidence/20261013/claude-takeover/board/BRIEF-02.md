# KIMI POLISH BRIEF 02 - fix index.html layout defects

Binding rules:
- Same rules as BRIEF.md: edit only index.html in this directory; no network requests; no invented data; do not modify ledger.js, ledger.json, BRIEF.md or this file.
- Time box: 15 minutes. At the box, save index.html as it is and report.

Controller rendered index.html in headless Edge at 1280px and 380px window widths. Defects:

1. At 380px the page overflows sideways. Header values, the owner-ask cards and their text clip at the right edge. Likely causes: a flex or grid child keeping min-width:auto, or a table's intrinsic width leaking past its overflow container. Fix so that page width never exceeds the viewport between 320px and 400px: min-width:0 on flex and grid children; max-width:100% on each table's overflow container; overflow-wrap:anywhere on long tokens (paths, hashes, IDs, model names) in cards and key/value rows. Header key/value rows may stack label above value below 480px.
2. At 1280px the content column is about 730px wide and the Source transfer table needs a horizontal scroll. Raise the main column max-width to 1120px.
3. Status dots appear on non-status values (for example source_path UNKNOWN, destination NONE). Show the dot only for these fields: lanes.status, milestones.status, gates.status, source_transfer.availability, source_transfer.readback, source_transfer.restore, outcome_flags.private_export. Everything else renders as plain text.
4. If missing, add `<meta name="viewport" content="width=device-width, initial-scale=1">`.

Before stopping, re-check the layout at 360px: header rows wrap, cards wrap, and only tables scroll, each inside its own container.

Report on stdout, caveman full: each defect 1 to 4 fixed or not and how; final byte size of index.html. No recap.
