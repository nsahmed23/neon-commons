// Generated from ledger/ledger.json by tools/make_ledger_js.py. Do not edit.
window.LEDGER = {
  "schema": "intune-rescue-ledger/1",
  "updated_utc": "2026-10-13T20:52:00Z",
  "writer": "Claude Code controller only; every other lane reads this file",
  "outcome_flags": {
    "private_export": "BLOCKED",
    "laboratory_complete": false,
    "platform_qualified": false,
    "organizational_production_approved": false
  },
  "owner_asks": [
    {
      "id": "OA-1",
      "urgency": "done",
      "ask": "Done: SOURCE-ACTION-02 ran; route B1-L probe PASS on both sides (observations/PROBE-B1L-01.json).",
      "blocks": "nothing"
    },
    {
      "id": "OA-2",
      "urgency": "done",
      "ask": "Done: repository, draft release, app access (all repositories) and approval line; SOURCE-ACTION-01 ran and failed at the upload with HTTP 401.",
      "blocks": "nothing"
    },
    {
      "id": "OA-3",
      "urgency": "now",
      "ask": "A tested route now exists: B1-L, Git LFS into the private custody repository (synthetic probe PASS). Limits for evidence: 2 GB per LFS file, 10 GiB LFS storage and 10 GiB monthly bandwidth on Free and Pro, readable by every app with access to all repositories, LFS objects removable only by deleting the repository. No copy of the four C32 archives survives in the searched source folders, so they are missing originals. The surviving r4-evidence and provider-candidates roots equal their receipts in files, bytes and links. Choose a loss disposition, or a new capture of those two roots. A new capture needs a classification plus destination, transit and retention approval, and a one-time lift of the handoff's large-source-tmpfs boundary. The two scratch layers cannot be recaptured.",
      "blocks": "M3"
    },
    {
      "id": "OA-4",
      "urgency": "before M3",
      "ask": "Decide the Remote Control posture for sessions that touch raw evidence.",
      "blocks": "M3 and M4 raw-evidence sessions"
    },
    {
      "id": "OA-5",
      "urgency": "before M5",
      "ask": "Name an off-machine backup destination; this PC has one physical disk.",
      "blocks": "M5 durability"
    },
    {
      "id": "OA-6",
      "urgency": "optional",
      "ask": "Public history keeps two things the current tree no longer will: the handoff bundle (commits 658ff7f4 to 7840c407) and one controller-log row with the Work environment id (7840c407). Keep it (default), or rewrite continuation/r4-20261007 with a force push on your named line.",
      "blocks": "nothing"
    }
  ],
  "lanes": [
    {
      "id": "L0",
      "lane": "controller",
      "model": "Claude Opus 5.5 (claude-opus-5-5[1m]), this Claude Code session",
      "role": "intake, ledger, gates, the only receiver writer",
      "status": "IN_PROGRESS",
      "output": "ledger/ledger.json"
    },
    {
      "id": "L1",
      "lane": "advisor-fable",
      "model": "Fable 5.1 (Claude Agent, read-only tools)",
      "role": "independent review: route decision and SOURCE-QUERY-01 (R01); ROUTE-DECISION-01 and SOURCE-QUERY-02 (R20)",
      "status": "DONE",
      "output": "lanes/advisor-fable/REPORT.md (R01); REPORT-R20.md (R20); REPORT-R22.md (R22)"
    },
    {
      "id": "L2",
      "lane": "advisor-astra",
      "model": "GPT-6 Astra via Codex CLI 0.156.0, read-only sandbox, effort max",
      "role": "independent review of the route decision and SOURCE-QUERY-01",
      "status": "DONE",
      "output": "lanes/advisor-astra/FINAL.md"
    },
    {
      "id": "L3",
      "lane": "chatgpt-source",
      "model": "original ChatGPT Work task, relayed by the owner",
      "role": "source operator; replied SOURCE-REPLY-01 (archives absent) and SOURCE-REPLY-02 (no copies; roots match receipts; app user token)",
      "status": "WAITING_ON_OWNER",
      "output": "inbox/SOURCE-REPLY-01.json, inbox/SOURCE-REPLY-02.json (local only)"
    },
    {
      "id": "L4",
      "lane": "kimi-board",
      "model": "Kimi K3 256k via Kimi Code CLI 0.37.2",
      "role": "frontend: this control board",
      "status": "DONE",
      "output": "board/index.html"
    },
    {
      "id": "L5",
      "lane": "m4-prep",
      "model": "GPT-6 Sol via Codex CLI 0.156.0, read-only sandbox, effort high",
      "role": "read the public snapshot builder and restorers; report the restore contract",
      "status": "DONE",
      "output": "lanes/m4-prep/FINAL.md"
    },
    {
      "id": "L6",
      "lane": "sol-query-check",
      "model": "gpt-6.1-sol refused (HTTP 400); ran on gpt-6-sol via Codex, read-only, effort high",
      "role": "non-author check of the merged SOURCE-QUERY-01",
      "status": "DONE",
      "output": "lanes/sol-query-check/FINAL.md"
    },
    {
      "id": "L7",
      "lane": "publisher",
      "model": "gpt-6-sol via Codex, workspace-write in lanes/publisher, effort high",
      "role": "implement publish_branch.py test-first (no network)",
      "status": "DONE",
      "output": "tools/publish_branch.py (6 of 6 tests green)"
    },
    {
      "id": "L8",
      "lane": "sync-worker",
      "model": "deterministic script, no model",
      "role": "every 10 min: logs, tables, board data, dry-run publish; local only since 2026-10-13T17:28Z (never pushes)",
      "status": "LOCAL_ONLY",
      "output": "logs/sync-worker.log (local)"
    },
    {
      "id": "L9",
      "lane": "leak-sweep",
      "model": "Haiku 5.5 (claude-haiku-5-5, Explore agent, read-only)",
      "role": "secret and personal-data sweep of the published files",
      "status": "DONE",
      "output": "no secrets; medium tooling-posture items redacted going forward"
    },
    {
      "id": "L10",
      "lane": "render-check",
      "model": "Sonnet 5.5 (fast-worker agent)",
      "role": "board render and overflow check at 360, 380 and 1280 px",
      "status": "DONE",
      "output": "agent report"
    },
    {
      "id": "L11",
      "lane": "redaction-fix",
      "model": "Sonnet 5.5 (code-editor agent)",
      "role": "publisher: redact C--Users-<user> and memory-file names; exclude host-intake JSON",
      "status": "DONE",
      "output": "tools/publish_branch.py (7 of 7 tests green)"
    },
    {
      "id": "L12",
      "lane": "pub-gate",
      "model": "Sonnet 5.5 (claude-sonnet-5-5 per API metadata), code-editor agent",
      "role": "relay withholding and posture redaction in the controller log; scanner with an append-only rules file; review-receipt gate on push; local-only worker",
      "status": "DONE",
      "output": "lanes/pub-gate/FINAL.md; tools/ (29 tests pass)"
    },
    {
      "id": "L13",
      "lane": "pub-review",
      "model": "Sonnet 5.5 (claude-sonnet-5-5 per API metadata), code-reader agent, read-only",
      "role": "careful read of published and candidate files: 7840c407 (R19), candidate-02 (R21), candidate-04 (R23)",
      "status": "DONE",
      "output": "lanes/pub-review/FINAL.md; observations/PUBLICATION-REVIEW-01.json to -03.json"
    }
  ],
  "milestones": [
    {
      "id": "M0",
      "title": "Intake and authority map",
      "status": "IN_PROGRESS",
      "evidence": "Host, WSL and repository measured; SOURCE-REPLY-01 received and checked against the sent pins (observations/SOURCE-REPLY-01-CHECK.json); SOURCE-QUERY-02 FINAL after Fable 5.1 review R20; waiting on owner relay (OA-1)."
    },
    {
      "id": "M1",
      "title": "Exact public source and package availability",
      "status": "PASS",
      "evidence": "Public scope only. d057cc15 is the immutable C32 baseline (it was the remote tip at 14:49Z); engine 39cc7761 tree f8bff355; ledger 2,025,195 B sha d6b787c6 matches; both 0.9.0 packages match bytes and SHA-256 at f9104700."
    },
    {
      "id": "M2",
      "title": "Original-source synthetic bridge",
      "status": "PASS",
      "evidence": "Route B1-L PASS 2026-10-13T20:47:05Z: the Work task pushed the 18,445-byte probe through Git LFS (commit 6dfaddbd, branch probe-lfs-20261013-01); this PC downloaded it with the required User-Agent and matched size and SHA-256 to the source pin; source reply, refs, commit author and release all checked (observations/PROBE-B1L-01.json). Earlier: probe through B1-R failed at the upload: uploads.github.com returned 401 Bad credentials; api.github.com reads succeeded; nothing uploaded. Diagnosis SOURCE-REPLY-04 PASS: only uploads.github.com rejects the Work task's login, so B1-R is closed for that task; git and Git LFS reach the private repository. Next: route B1-L (Git LFS), outbox/ROUTE-DECISION-02.md. R24 SEND WITH FIXES, all applied; the owner accepted the Git LFS User-Agent exception for the Work task (20:39Z, 20:40Z); SOURCE-ACTION-02 FINAL; the receiver watcher runs until about 22:43Z."
    },
    {
      "id": "M3",
      "title": "Four layers plus explicit amendment",
      "status": "BLOCKED",
      "evidence": "C32 archives are missing originals: ENOENT at recorded paths and no copy in /workspace, /tmp, /var/tmp or /home (/root not searchable). Surviving r4-evidence and provider-candidates roots equal their receipts in files, bytes and links. Next step only under OA-3 (new capture) or a loss disposition."
    },
    {
      "id": "M4",
      "title": "Full safe typed restoration",
      "status": "NOT_STARTED",
      "evidence": "Needs M3. Prep done: public restorer is POSIX-only stdlib Python (WSL required, no installs); no free-space check, so the controller preflights capacity; FIFO entries are pinned omissions, symlinks are recreated as links; fresh output root per attempt."
    },
    {
      "id": "M5",
      "title": "Durability and binding relocation",
      "status": "NOT_STARTED",
      "evidence": "Needs M4 and a second failure domain (OA-4)."
    },
    {
      "id": "M6",
      "title": "Current exact-artifact performance",
      "status": "NOT_STARTED",
      "evidence": "Needs M5 plus preparation inputs, quiet window and GO."
    },
    {
      "id": "M7",
      "title": "Remaining native procedures",
      "status": "NOT_STARTED",
      "evidence": "Needs current bindings, genuine witnesses, fresh approval, READY and GO."
    },
    {
      "id": "M8",
      "title": "External platform and organizational approval",
      "status": "NOT_STARTED",
      "evidence": "Separate owner-scoped projects."
    }
  ],
  "source_transfer": [
    {
      "label": "r4-evidence",
      "archive_bytes": 1469518188,
      "sha256": "7bbc9f88eee9b4c417f622fb76cb5e2c0b0d4790d5b7cceaa2ae661ce2012ad7",
      "manifest_bytes": 35983862,
      "manifest_sha256": "9f53658f8b795e136d32baab6d7043741a81cd6450e9d640489fb01a97610fb1",
      "source_path": "recorded /tmp path (C32)",
      "availability": "MISSING ORIGINAL (no copy in searched roots); input root present and equal to its receipt in files, bytes and links",
      "destination": "NONE (missing original); a new capture could use route B1-L after OA-3",
      "readback": "NOT_POSSIBLE unless a copy is found",
      "restore": "NOT_POSSIBLE unless a copy is found"
    },
    {
      "label": "provider-candidates",
      "archive_bytes": 9849950,
      "sha256": "755b9f4f8d29e562f476fc7e1f3bb8f376fd0fbfbeabe7a8e7e7ec78099280c7",
      "manifest_bytes": 2875760,
      "manifest_sha256": "bccf1c15dcda000ebeae37f1c23de016233d062d8a0edcf535b39f67ffd99fa6",
      "source_path": "recorded /tmp path (C32)",
      "availability": "MISSING ORIGINAL (no copy in searched roots); input root present and equal to its receipt in files, bytes and links",
      "destination": "NONE (missing original); a new capture could use route B1-L after OA-3",
      "readback": "NOT_POSSIBLE unless a copy is found",
      "restore": "NOT_POSSIBLE unless a copy is found"
    },
    {
      "label": "current-diagnostic-scratch",
      "archive_bytes": 14485539,
      "sha256": "60960f3760f24893e7114185d5d14ee7ab3e35e1fc17008097d2b6eecc83e939",
      "manifest_bytes": 5496,
      "manifest_sha256": "43ef5e7852f9e2be9878cfc17ef096182d166fc693b970333828e54e11f7b992",
      "source_path": "recorded /tmp path (C32)",
      "availability": "MISSING ORIGINAL (no copy in searched roots); input root gone with /tmp",
      "destination": "NONE (missing original); a new capture could use route B1-L after OA-3",
      "readback": "NOT_POSSIBLE unless a copy is found",
      "restore": "NOT_POSSIBLE unless a copy is found"
    },
    {
      "label": "current-exact-artifact-scratch",
      "archive_bytes": 41538870,
      "sha256": "c221c1410d905806275dc3ea72c2793db83839816d112d4d3095e3bbe4819add",
      "manifest_bytes": 1677589,
      "manifest_sha256": "5d8b84ecc1c8bf9690fa0cbfa0012650430e36f302f4982969a04366b7984c2e",
      "source_path": "recorded /tmp path (C32)",
      "availability": "MISSING ORIGINAL (no copy in searched roots); input root gone with /tmp",
      "destination": "NONE (missing original); a new capture could use route B1-L after OA-3",
      "readback": "NOT_POSSIBLE unless a copy is found",
      "restore": "NOT_POSSIBLE unless a copy is found"
    },
    {
      "label": "post-cutoff amendment",
      "archive_bytes": null,
      "sha256": null,
      "manifest_bytes": null,
      "manifest_sha256": null,
      "source_path": "UNKNOWN",
      "availability": "68 records fully listed (SOURCE-REPLY-01 and -02); 64 in the epoch, 241,052 B; not built",
      "destination": "NONE",
      "readback": "NOT_STARTED",
      "restore": "NOT_STARTED"
    },
    {
      "label": "synthetic probe",
      "archive_bytes": 18445,
      "sha256": "d01a9b0e9cd1506b1ee5d0defcfebf4f377af858ab610d3ec5362623ee0c67c3",
      "manifest_bytes": null,
      "manifest_sha256": null,
      "source_path": "/workspace (C33 probe folder)",
      "availability": "PRESENT, PIN-MATCH 2026-10-13T16:02:54Z; PIN-MATCH again in SOURCE-ACTION-REPLY-02 preflight",
      "destination": "B1-L: nsahmed23/intune-evidence-custody, branch probe-lfs-20261013-01 (commit 6dfaddbd), Git LFS object",
      "readback": "PASS 2026-10-13T20:47:05Z: 18,445 B, SHA-256 d01a9b0e...0c67c3 (observations/PROBE-B1L-01.json)",
      "restore": "n/a"
    }
  ],
  "gates": [
    {
      "gate": "G11 binary export",
      "status": "BLOCKED",
      "boundary": "Route B1-L (Git LFS into the private custody repository) PASS for the synthetic probe (observations/PROBE-B1L-01.json). B1-R closed for the Work task (uploads.github.com 401). Drive 403 not retried. C32 archives are missing originals. Evidence export waits on OA-3 classification and approval.",
      "owner": "source integration owner, then evidence owner",
      "next_input": "OA-3"
    },
    {
      "gate": "G11 receiving capacity",
      "status": "BLOCKED",
      "boundary": "Receiver measured (C: backs 326,692,147,200 B free against a 7,827,771,392 B scenario). The custody repository is approved for the synthetic probe only; evidence needs its own destination approval.",
      "owner": "receiving storage owner (the owner)",
      "next_input": "OA-3"
    },
    {
      "gate": "F03 full restoration",
      "status": "FAIL",
      "boundary": "First restore interrupted (KeyboardInterrupt); no full receipt exists",
      "owner": "receiving custodian",
      "next_input": "M3 transfer, then a fresh typed restore"
    },
    {
      "gate": "F03/F09 missing originals",
      "status": "FAIL",
      "boundary": "C30 runtime evidence ZIP (46,862,494 B), observer ZIP (50,239 B), raw tree and aggregate-reader output absent at origin; the four C32 snapshot archives absent with no copy in the searched source folders",
      "owner": "original evidence custodian",
      "next_input": "a loss disposition, or a new capture under OA-3"
    },
    {
      "gate": "D12/E01 performance",
      "status": "NOT_STARTED",
      "boundary": "Zero current samples",
      "owner": "performance custodian",
      "next_input": "restored preparation inputs, quiet window, per-lane GO"
    },
    {
      "gate": "B08/B13 native",
      "status": "NOT_STARTED",
      "boundary": "Historical 38 planned, 6 attempted; not current state",
      "owner": "native qualification controller",
      "next_input": "current bindings, genuine witnesses, fresh approval, READY and GO"
    },
    {
      "gate": "G13 denied repair",
      "status": "BLOCKED",
      "boundary": "Automatic approval review rejected the isolated malformed-error provider repair; no alternate route",
      "owner": "provider, execution-policy and AppSec owner",
      "next_input": "owner disposition only"
    }
  ],
  "observations": {
    "host": {
      "os": "Windows 11 Pro 10.0.26200",
      "cpu": "Ryzen 7 8745H, 8 cores, 16 threads",
      "ram_total_bytes": 31982632960,
      "ram_available_mb": 2211,
      "disk": "one 1 TB NVMe SSD",
      "c_free_bytes": 326692147200,
      "claude_code": "2.1.296"
    },
    "wsl": {
      "distro": "Ubuntu 24.04.2 LTS (WSL2, default)",
      "fs": "ext4, 4096-byte blocks",
      "inodes_free": 67057462,
      "guest_ram_available_bytes": 14778331136,
      "missing_tools": "claude, atmos, tofu, pwsh, gh, rclone, zstd"
    },
    "public_source": {
      "continuation_tip": "d057cc15 (C32), unchanged",
      "main_tip": "4ba077d9, unchanged",
      "ledger_sha256_match": true,
      "packages_match": true
    },
    "detail_file": "observations/2026-10-13-host-intake.json"
  },
  "events": [
    {
      "utc": "2026-10-13T14:35:02Z",
      "text": "Owner handed over the 2026-10-12 handoff package."
    },
    {
      "utc": "2026-10-13T14:37:46Z",
      "text": "Handoff ZIP verified: 16 of 16 checksums."
    },
    {
      "utc": "2026-10-13T14:46:02Z",
      "text": "Windows host and WSL Ubuntu measured read-only."
    },
    {
      "utc": "2026-10-13T14:48:59Z",
      "text": "M1 PASS (public scope): C32 tip, engine tree, ledger hash and 0.9.0 packages verified."
    },
    {
      "utc": "2026-10-13T14:56:01Z",
      "text": "Dispatched Fable 5.1, GPT-6 Astra and Kimi lanes."
    },
    {
      "utc": "2026-10-13T15:01:15Z",
      "text": "GPT-6 Sol read the public restorer; controller spot-check passed."
    },
    {
      "utc": "2026-10-13T15:07:21Z",
      "text": "Both advisors reported; Fable leads where they conflict."
    },
    {
      "utc": "2026-10-13T15:19:24Z",
      "text": "gpt-6.1-sol refused for this Codex login (HTTP 400); fell back to gpt-6-sol."
    },
    {
      "utc": "2026-10-13T15:24:52Z",
      "text": "SOURCE-QUERY-01 final after three reviews."
    },
    {
      "utc": "2026-10-13T15:27:41Z",
      "text": "Audit trail live: controller log, events, runs, transcript snapshots; see AUDIT.md."
    },
    {
      "utc": "2026-10-13T15:29:19Z",
      "text": "Publisher (GPT-6 Sol) done; controller re-ran 6 of 6 tests and reviewed the code."
    },
    {
      "utc": "2026-10-13T15:31:38Z",
      "text": "First publish: 658ff7f4 on continuation/r4-20261007 (56 files, fast-forward, main untouched)."
    },
    {
      "utc": "2026-10-13T15:31:52Z",
      "text": "Sync worker cycle 1 pushed de69761f; runs every 10 minutes for 12 hours."
    },
    {
      "utc": "2026-10-13T15:32:17Z",
      "text": "Codex CLI 0.162.1: gpt-6.1-sol now runs; the earlier HTTP 400 was a client-version gate."
    },
    {
      "utc": "2026-10-13T17:19:43Z",
      "text": "Owner relayed SOURCE-REPLY-01 and a ChatGPT correction (saved locally in inbox/)."
    },
    {
      "utc": "2026-10-13T17:28:06Z",
      "text": "Sync worker stopped via STOP_SYNC after cycle 12 (7840c407); publishing now needs a review receipt."
    },
    {
      "utc": "2026-10-13T17:43:22Z",
      "text": "Reply checked: four archives ABSENT, probe PIN-MATCH; publication review of 7840c407 done; ROUTE-DECISION-01 and SOURCE-QUERY-02 drafted."
    },
    {
      "utc": "2026-10-13T17:51:47Z",
      "text": "Fable 5.1 review R20: SEND-WITH-FIXES; fixes applied; SOURCE-QUERY-02 FINAL; ROUTE-DECISION-01 reviewed."
    },
    {
      "utc": "2026-10-13T17:55:13Z",
      "text": "Reviewed publish 02: 7a9716b9 (receipt PUBLICATION-REVIEW-02, 56 files; R21 PASS); handoff/ no longer in the tree."
    },
    {
      "utc": "2026-10-13T18:19:24Z",
      "text": "SOURCE-REPLY-02: no surviving archive copies; receipts intact; surviving roots equal receipts by count and bytes; source credential is a GitHub App user token."
    },
    {
      "utc": "2026-10-13T18:26:28Z",
      "text": "Fable 5.1 review R22: SOURCE-ACTION-01 SEND; hardenings applied plus a destination privacy check; FINAL."
    },
    {
      "utc": "2026-10-13T18:29:34Z",
      "text": "Reviewed publish 03: c7170215 (receipt PUBLICATION-REVIEW-03, 62 files; R23 PASS)."
    },
    {
      "utc": "2026-10-13T18:43:05Z",
      "text": "OA-2 steps 1-2 done by the owner; controller verified the repository is private and the draft release exists with no assets."
    },
    {
      "utc": "2026-10-13T18:45:04Z",
      "text": "Owner approved route B1-R for the synthetic probe only (exact line recorded in logs/events.jsonl)."
    },
    {
      "utc": "2026-10-13T18:50:34Z",
      "text": "SOURCE-ACTION-01: preflight, privacy check and release lookup passed; the upload returned 401 Bad credentials; nothing uploaded."
    }
  ],
  "routing": "Opus 5.5 controller: judgment, gates, synthesis, last-mile git. Sonnet 5.5: mechanical Claude lanes (verification runs, records, reply parsing). Haiku 5.5: sweeps and inventories. Fable 5.1 leads the advisor tier, GPT-6 Astra is its peer. GPT-6.1 Sol (working since Codex CLI 0.162.1) is the Opus-tier ChatGPT executor. Kimi K3: frontend only."
};
