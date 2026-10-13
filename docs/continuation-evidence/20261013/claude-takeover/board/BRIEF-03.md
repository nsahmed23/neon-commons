# KIMI POLISH BRIEF 03 - tables must scroll, not squeeze, on phones

Binding rules:
- Same rules as BRIEF.md: edit only index.html in this directory; no network requests; no invented data; do not modify ledger.js, ledger.json or any BRIEF file.
- Do not launch a browser. The controller verifies rendering itself.
- Time box: 10 minutes. At the box, save index.html as it is and report.

Defect, measured by the controller's Sonnet render check at 360px: the Lanes table does not scroll inside its container; it squeezes columns until model, role and output cells break one character per line. Page-level overflow is already fixed (scrollWidth equals clientWidth at 360 and 1280); keep it that way.

Fix: give every table inside its overflow container a sensible minimum width so it scrolls horizontally inside the container instead of compressing, for example `.table-wrap > table { min-width: 720px; }` and `white-space: nowrap` only on short cells (id, status, bytes, UTC). Long text cells (model, role, evidence, boundary, ask) wrap normally at a readable width (about 16 to 28 characters minimum). Milestones and observations tables may keep their current behavior if they already read well.

Report on stdout, caveman full: the CSS rules changed, final byte size of index.html. No recap.
