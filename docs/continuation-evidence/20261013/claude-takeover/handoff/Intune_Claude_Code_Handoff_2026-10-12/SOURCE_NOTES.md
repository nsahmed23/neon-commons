# Source notes and retrieval guide

This package separates original attached bytes from user reports, public metadata and external guidance. References such as `[P1]` in the handoff resolve here. JSON paths and repository paths are the authoritative locators; chat citation widgets are not required by Claude Code.

## Primary attachments and latest report

### P1 — Original attached C32 execution-outcome receipt; copied byte-for-byte.

Local file: `evidence/FINAL-RESULT.json`  
Bytes: 10671  
SHA-256: `2a314039e244e67052a68e14c5be5860ae0c724256179cc001eb165411b702cc`

### P2 — Original attached receiving-chat small synthetic roundtrip receipt; copied byte-for-byte.

Local file: `evidence/LIBRARY-ROUNDTRIP-RESULT.json`  
Bytes: 11228  
SHA-256: `2dc785ec59a4e2823e3f7327d33fbd659db06440d7f234be12006a77094c2af3`

### P3 — Original attached receiving-chat synthetic archive; matches P2 pin.

Local file: `evidence/synthetic_library_probe.zip`  
Bytes: 67732  
SHA-256: `ea982e34e5e535e9be2cb523ab93ba169ec4166d4c33d71fc113c19b6c6b84fc`

### P4 — New transcription of latest user report; not original Work ZIP/JSON/error receipt.

Local file: `evidence/WORK_EXPORT_FAILURE_USER_REPORT.md`  
Bytes: 1545  
SHA-256: `13152eebe1bf541c27d5c9208fa64a63dde09c2a3acba0d4ce91c150bf96cc89`

P1 records remote execution outcomes; copying P1 does not independently verify those actions. P2 is scoped to one small same-chat test and does not demonstrate a source-Work bridge. P3 is the receiving-chat probe, not the source-Work probe. P4 preserves a pasted report; no exact source execution timestamp or raw Drive error response was supplied.

## Immutable public repository references

Full original repository snapshots are not included. Selected content was inspected through the GitHub connector; direct raw snapshot downloads into this container were unavailable. The `reference/*EXTRACT.json` and `reference/*PINS.json` files are explicitly derived summaries, not byte-identical substitutes for the original public manifests. Read the original pinned documents in the receiving environment before executing project procedures.

### R1 — `docs/EXECUTION-SEQUENCE-R4.md`

Commit: `d057cc15c9928dd1a34a965b8d8ebf8e6755d94a`. Content inspected here: **YES (selected relevant content)**.

C32 export-first order; historical sections retained.

Source: https://github.com/nsahmed23/neon-commons/blob/d057cc15c9928dd1a34a965b8d8ebf8e6755d94a/docs/EXECUTION-SEQUENCE-R4.md

### R2 — `docs/EXTERNAL-GATES-R4.md`

Commit: `d057cc15c9928dd1a34a965b8d8ebf8e6755d94a`. Content inspected here: **YES (selected relevant content)**.

Current blockers, owners and qualification limits.

Source: https://github.com/nsahmed23/neon-commons/blob/d057cc15c9928dd1a34a965b8d8ebf8e6755d94a/docs/EXTERNAL-GATES-R4.md

### R3 — `docs/OPERATING-PROFILE-R4.md`

Commit: `d057cc15c9928dd1a34a965b8d8ebf8e6755d94a`. Content inspected here: **YES (selected relevant content)**.

Support declaration/native pins; C31 availability prose is stale where superseded by C32.

Source: https://github.com/nsahmed23/neon-commons/blob/d057cc15c9928dd1a34a965b8d8ebf8e6755d94a/docs/OPERATING-PROFILE-R4.md

### R4 — `docs/STRICT-CONTINUATION-CONTRACT-R4.md`

Commit: `d057cc15c9928dd1a34a965b8d8ebf8e6755d94a`. Content inspected here: **NO — reference only**.

Referenced by current source documents; complete contents not inspected in this handoff.

Source: https://github.com/nsahmed23/neon-commons/blob/d057cc15c9928dd1a34a965b8d8ebf8e6755d94a/docs/STRICT-CONTINUATION-CONTRACT-R4.md

### R5 — `docs/CONTINUATION-R4-LEDGER.json`

Commit: `d057cc15c9928dd1a34a965b8d8ebf8e6755d94a`. Content inspected here: **NO — reference only**.

Full contents not inspected; C32 original receipt records its size/hash.

Source: https://github.com/nsahmed23/neon-commons/blob/d057cc15c9928dd1a34a965b8d8ebf8e6755d94a/docs/CONTINUATION-R4-LEDGER.json

### R6 — `docs/continuation-evidence/20261012/checkpoint32/archive-disposition.json`

Commit: `d057cc15c9928dd1a34a965b8d8ebf8e6755d94a`. Content inspected here: **YES (selected relevant content)**.

Per-layer pins, manifests, typed scope, capacity and interrupted restore.

Source: https://github.com/nsahmed23/neon-commons/blob/d057cc15c9928dd1a34a965b8d8ebf8e6755d94a/docs/continuation-evidence/20261012/checkpoint32/archive-disposition.json

### R7 — `docs/continuation-evidence/20261012/checkpoint32/missing-originals.json`

Commit: `d057cc15c9928dd1a34a965b8d8ebf8e6755d94a`. Content inspected here: **YES (selected relevant content)**.

Missing exact originals, historical counts and scope limits.

Source: https://github.com/nsahmed23/neon-commons/blob/d057cc15c9928dd1a34a965b8d8ebf8e6755d94a/docs/continuation-evidence/20261012/checkpoint32/missing-originals.json

### R8 — `docs/continuation-evidence/20261012/checkpoint32/library-contract.json`

Commit: `d057cc15c9928dd1a34a965b8d8ebf8e6755d94a`. Content inspected here: **NO — reference only**.

Referenced in C32; original attached P1 also records contract limits.

Source: https://github.com/nsahmed23/neon-commons/blob/d057cc15c9928dd1a34a965b8d8ebf8e6755d94a/docs/continuation-evidence/20261012/checkpoint32/library-contract.json

### R9 — `docs/continuation-evidence/20261012/checkpoint32/storage-export-result.json`

Commit: `d057cc15c9928dd1a34a965b8d8ebf8e6755d94a`. Content inspected here: **NO — reference only**.

Referenced by canonical resume command; full contents not inspected here.

Source: https://github.com/nsahmed23/neon-commons/blob/d057cc15c9928dd1a34a965b8d8ebf8e6755d94a/docs/continuation-evidence/20261012/checkpoint32/storage-export-result.json

### R10 — `intune-workbench/r4-20261011/c30-20261011/ARTIFACTS.json`

Commit: `f9104700b1871642f89f982fc625ab0da9eae310`. Content inspected here: **YES (selected relevant content)**.

Exact release archive pins and false qualification/completeness flags.

Source: https://github.com/nsahmed23/neon-commons/blob/f9104700b1871642f89f982fc625ab0da9eae310/intune-workbench/r4-20261011/c30-20261011/ARTIFACTS.json

The four archive identities in R6 are metadata, not the archives or their full private manifest bytes. The public disposition intentionally excludes source archive filenames/paths and sensitive member details. The C32 P1 ledger hash is a recorded expectation; the full ledger was not downloaded or rehashed during this handoff.

Historical public recovery references from the conversation:

- https://github.com/nsahmed23/neon-commons/releases/tag/intune-r2-handoff-20261007
- https://github.com/nsahmed23/neon-commons/releases/tag/intune-r3-handoff-20261007

These releases were not fetched or verified during this handoff. They cannot be assumed to contain current C32 private evidence.

## Conversation context

**C1:** Historical mini-PC details: Minisforum UM870 Slim, Ryzen 7 8745H, 8 cores/16 threads, 32 GB RAM, 1 TB NVMe, Windows 11 Pro; WSL2/Docker/virtualization mentioned earlier. No current readiness is asserted. The earlier 360 GB free-space claim was withdrawn and must not be revived. Prior preferences favor an existing local Claude controller, bounded workers, and local coordination rather than a new orchestration platform. Model/effort names and plan usage are not pinned by this handoff.

**C2:** This conversation's product architecture, failed preservation progression, scope distinctions, mini-PC/VM ideas, and proposed next actions. The user's request is to prepare a Claude Code handoff. Suggestions about Hyper-V, Proxmox, cloud providers, Drive reconnection and remote computer access were not executed approvals or successful tests. Unrelated DEX scoring and presentation files are not the basis of this Intune handoff.

## External official guidance — not project evidence

Consulted while preparing the handoff on 2026-10-12. Guidance may change; check the installed tool and relevant organizational policy at execution. Summaries in the handoff do not establish account eligibility, source credentials, supported connector methods, or authorization.

### V1 — Claude Code overview

Local/other execution surfaces; source Work access is not provided by this documentation.

Source: https://code.claude.com/docs/en/overview

### V2 — Claude Code advanced setup

Windows/WSL setup; version and installation diagnostics. Recheck installed version.

Source: https://code.claude.com/docs/en/setup

### V3 — Claude Code security

Permissions, shell/working-directory limitations, sensitive content handling.

Source: https://code.claude.com/docs/en/security

### V4 — Claude Code permissions

Permission modes and managed boundaries; not external service authority.

Source: https://code.claude.com/docs/en/permissions

### V5 — Claude Code Remote Control

Local execution controlled remotely; machine/process lifetime and transcript handling.

Source: https://code.claude.com/docs/en/remote-control

### V6 — Claude Code data usage

Account-specific handling; no blanket local-only data claim.

Source: https://code.claude.com/docs/en/data-usage

### V7 — Google Drive API scopes

Scope distinctions; connector required scopes are not established.

Source: https://developers.google.com/workspace/drive/api/guides/api-specific-auth

### V8 — Google Drive error handling

Inspect actual error reasons; no proof of which grant or admin policy caused this particular denial.

Source: https://developers.google.com/workspace/drive/api/guides/handle-errors

### V9 — Microsoft WSL filesystem guidance

Linux-tool filesystem placement; does not qualify archive metadata automatically.

Source: https://learn.microsoft.com/en-us/windows/wsl/filesystems

### V10 — Google Drive upload methods

Resumable API option; not proof that source connector exposes it.

Source: https://developers.google.com/workspace/drive/api/guides/manage-uploads

## Authoring verification boundary

The author read the two attached receipts, confirmed the receiving-chat synthetic ZIP's actual bytes against its recorded hash, inspected selected immutable public metadata, and assembled this handoff. The author did not repair Drive authorization, export private evidence, inspect the source Work host, run the product tests, install a VM, approve a tenant operation, or resolve G13. Handoff package integrity is separate from every project qualification.
