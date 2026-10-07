# Intune / Atmos / Wally — complete work repository

This repository snapshot collects the implementation and saved work records from
all six engineering threads, the parent/provider work, original input, intermediate
checkpoints and exact final release artifacts in one directory.

**Enterprise acceptance remains blocked. No Wally candidate was promoted.**
Packaging does not change any earlier qualification result or grant deployment,
tenant mutation, privilege expansion or organizational risk acceptance.

## Start here

1. Read `WORK_THREADS.md` for the work-thread index.
2. Read `work/docs/RESULTS.md` and
   `work/releases/delivery-final/DELIVERY-RECEIPT.json` for final observations.
3. For continuation, read `AGENTS.md`, `work/docs/LLM_INSTRUCTIONS.md`,
   `work/docs/LLM_EXECUTION_DIRECTIVE.md` and
   `work/docs/ENTERPRISE_TERMINAL_SECURITY.md` in full, then `work/CHECKPOINT.md`.
4. Follow `work/docs/REPLAY-EPOCH.md` and the requirement/security ledgers. Historical
   absolute workspace paths are retained as evidence; adapt replay locations to
   this extracted repository. Never silently alter historical receipts.

## Layout

| Path | Contents |
| --- | --- |
| `work/projects/intune/` | Exact extracted final Intune source package |
| `work/projects/wally/` | Exact extracted final Wally source package |
| `work/provider-source/` | Exact extracted final Microsoft365 provider source |
| `work/evidence/epoch-20261004/` | Canonical raw evidence from every thread, including Wally reviews |
| `work/docs/`, `work/scripts/` | Full directives, acceptance, replay, packaging and operational records |
| `work/releases/` | Original final source/runtime/evidence ZIPs, current and historical provider binaries, final verification records and draft packaging history |
| `work/checkpoints/` | All four saved intermediate checkpoint ZIPs |
| `work/wheelhouse/` | Ten pinned offline Python dependency wheels |
| `inputs/` | Unmodified original uploaded continuation ZIP, containing original source archives and historical evidence |
| `workspace-supplement/` | Any regular working-project files absent from or different from the exact release source; separately identified, not silently added to qualified source |
| `provenance/` | Scope, source-archive identities, unpacking mappings and supplemental-file inventory |
| `tools/` | This consolidation script and the extracted-repository verifier |

The folder is Git-ready source, not a fabricated Git history. No new repository
commit, remote, dependency installation or application execution is performed by
this packaging step. Existing project-local instructions remain present.

## Verify after extraction

Run from this directory using Python 3.12:

```sh
python3 tools/verify_repository.py .
```

The verifier checks SHA-256, size and exact file-set closure. It does not run the
application, labs, model experiments or historical attack fixtures. Verify before
adding files or initializing Git, because exact closure intentionally reports extras.
The ZIP has a detached SHA-256 checksum delivered alongside it.

## Scope and preserved limitations

This is a consolidation of saved work artifacts, not an export of private agent
conversation transcripts. Thread checkpoints, reports, review outputs, trial
records, reproducers, failures, skips and replay commands are included wherever
they were saved. `WORK_THREADS.md` links those records directly.

The raw evidence archive's existing per-path omission/reconstruction inventories
remain authoritative. Redundant extracted release copies, downloaded tool trees,
virtual environments, process state and regenerable caches are not newly duplicated.
Exact released archives, including the historical provider binary, are included.
Their presence does not mean the original multi-gigabyte execution workspace was
fully reconstructed or that external tool/host prerequisites are satisfied.

The latest Intune strict gate records 967 passes and one required-host skip, with
strict success false. The matched Wally matrix records 87 completions and nine
timeouts from 96 scheduled reviews; benefit is unestablished. Supported-host,
provider-RPC/lifecycle, security, AppSec and authorized tenant gates remain visible
in the delivered reports. No live tenant mutation was performed.
