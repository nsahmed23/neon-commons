// Generated from ledger/ledger.json by tools/make_ledger_js.py. Do not edit.
window.LEDGER = {
  "schema": "intune-rescue-ledger/1",
  "updated_utc": "2026-10-13T15:41:50Z",
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
      "urgency": "now",
      "ask": "Paste the fenced block in outbox/SOURCE-QUERY-01.md into the original ChatGPT Work task, keep that task open (no reset, no new task), and save its JSON reply as inbox/SOURCE-REPLY-01.json or paste it to the controller.",
      "blocks": "M2 route selection and the M3 availability recheck"
    },
    {
      "id": "OA-2",
      "urgency": "after the reply",
      "ask": "Authorize one route in writing for the 18,445-byte synthetic probe only (for example a new private GitHub repository). A private repository is a new custodian, not an extension of the public C32 push.",
      "blocks": "M2 synthetic bridge"
    },
    {
      "id": "OA-3",
      "urgency": "before M3",
      "ask": "Classify the private corpus and approve destination, transit and retention for the four layers; separately approve building the post-cutoff amendment, which is a write in the source task.",
      "blocks": "M3 transfer and amendment"
    },
    {
      "id": "OA-4",
      "urgency": "before M3",
      "ask": "Remote Control starts on by default (remoteControlAtStartup is true) and syncs transcripts through Anthropic. Decide whether sessions that touch raw evidence run with it off.",
      "blocks": "M3 and M4 raw-evidence sessions"
    },
    {
      "id": "OA-5",
      "urgency": "before M5",
      "ask": "Name an off-machine backup destination; this PC has one physical disk.",
      "blocks": "M5 durability"
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
      "role": "independent review of the route decision and SOURCE-QUERY-01",
      "status": "DONE",
      "output": "lanes/advisor-fable/REPORT.md"
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
      "role": "source operator; the only holder of the four archive layers",
      "status": "WAITING_ON_OWNER",
      "output": "inbox/SOURCE-REPLY-01.json"
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
      "role": "every 10 min: logs, tables, board data, publish to continuation/r4-20261007",
      "status": "RUNNING",
      "output": "logs/sync-worker.log; commits on continuation/r4-20261007"
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
      "status": "RUNNING",
      "output": "tools/publish_branch.py"
    }
  ],
  "milestones": [
    {
      "id": "M0",
      "title": "Intake and authority map",
      "status": "IN_PROGRESS",
      "evidence": "Host, WSL and repository measured; route analysis reviewed by Fable 5.1, GPT-6 Astra and GPT-6 Sol; final query waits on owner relay (OA-1)."
    },
    {
      "id": "M1",
      "title": "Exact public source and package availability",
      "status": "PASS",
      "evidence": "Public scope only. Remote tip d057cc15 is C32; engine 39cc7761 tree f8bff355; ledger 2,025,195 B sha d6b787c6 matches; both 0.9.0 packages match bytes and SHA-256 at f9104700."
    },
    {
      "id": "M2",
      "title": "Original-source synthetic bridge",
      "status": "BLOCKED",
      "evidence": "No proven route. Drive returned 403 ACCESS_TOKEN_SCOPE_INSUFFICIENT; waiting on OA-1."
    },
    {
      "id": "M3",
      "title": "Four layers plus explicit amendment",
      "status": "BLOCKED",
      "evidence": "Availability NOT_RECHECKED; destination not approved (OA-2)."
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
      "source_path": "UNKNOWN",
      "availability": "NOT_RECHECKED",
      "destination": "NONE",
      "readback": "NOT_STARTED",
      "restore": "NOT_STARTED"
    },
    {
      "label": "provider-candidates",
      "archive_bytes": 9849950,
      "sha256": "755b9f4f8d29e562f476fc7e1f3bb8f376fd0fbfbeabe7a8e7e7ec78099280c7",
      "manifest_bytes": 2875760,
      "manifest_sha256": "bccf1c15dcda000ebeae37f1c23de016233d062d8a0edcf535b39f67ffd99fa6",
      "source_path": "UNKNOWN",
      "availability": "NOT_RECHECKED",
      "destination": "NONE",
      "readback": "NOT_STARTED",
      "restore": "NOT_STARTED"
    },
    {
      "label": "current-diagnostic-scratch",
      "archive_bytes": 14485539,
      "sha256": "60960f3760f24893e7114185d5d14ee7ab3e35e1fc17008097d2b6eecc83e939",
      "manifest_bytes": 5496,
      "manifest_sha256": "43ef5e7852f9e2be9878cfc17ef096182d166fc693b970333828e54e11f7b992",
      "source_path": "UNKNOWN",
      "availability": "NOT_RECHECKED",
      "destination": "NONE",
      "readback": "NOT_STARTED",
      "restore": "NOT_STARTED"
    },
    {
      "label": "current-exact-artifact-scratch",
      "archive_bytes": 41538870,
      "sha256": "c221c1410d905806275dc3ea72c2793db83839816d112d4d3095e3bbe4819add",
      "manifest_bytes": 1677589,
      "manifest_sha256": "5d8b84ecc1c8bf9690fa0cbfa0012650430e36f302f4982969a04366b7984c2e",
      "source_path": "UNKNOWN",
      "availability": "NOT_RECHECKED",
      "destination": "NONE",
      "readback": "NOT_STARTED",
      "restore": "NOT_STARTED"
    },
    {
      "label": "post-cutoff amendment",
      "archive_bytes": null,
      "sha256": null,
      "manifest_bytes": null,
      "manifest_sha256": null,
      "source_path": "UNKNOWN",
      "availability": "NOT_DEFINED",
      "destination": "NONE",
      "readback": "NOT_STARTED",
      "restore": "NOT_STARTED"
    }
  ],
  "gates": [
    {
      "gate": "G11 binary export",
      "status": "BLOCKED",
      "boundary": "Drive upload 403 ACCESS_TOKEN_SCOPE_INSUFFICIENT; no Library save or materialize in the source task",
      "owner": "source integration owner, then evidence owner",
      "next_input": "SOURCE-REPLY-01, then route approval (OA-2)"
    },
    {
      "gate": "G11 receiving capacity",
      "status": "BLOCKED",
      "boundary": "Receiver measured (C: backs 326,692,147,200 B free against a 7,827,771,392 B scenario) but the destination is not approved",
      "owner": "receiving storage owner (the owner)",
      "next_input": "OA-2"
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
      "boundary": "C30 runtime evidence ZIP (46,862,494 B), observer ZIP (50,239 B), raw tree and aggregate-reader output absent at origin",
      "owner": "original evidence custodian",
      "next_input": "exact copies, or a scoped loss disposition"
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
    }
  ],
  "routing": "Opus 5.5 controller: judgment, gates, synthesis, last-mile git. Sonnet 5.5: mechanical Claude lanes (verification runs, records, reply parsing). Haiku 5.5: sweeps and inventories. Fable 5.1 leads the advisor tier, GPT-6 Astra is its peer. GPT-6.1 Sol (working since Codex CLI 0.162.1) is the Opus-tier ChatGPT executor. Kimi K3: frontend only."
};
