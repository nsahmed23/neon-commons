# Start here — Claude Code handoff

**Purpose:** take over the existing Intune Workbench without losing its exact identities, evidence boundaries, or unresolved failures. First resolve authorized source-to-receiver access; then preserve and restore the surviving evidence; then run only eligible original laboratory procedures.

**This is not the private evidence export.** The four original temporary archive layers, post-cutoff amendment, missing originals, and original-Work synthetic probe are not in this package.

## How to use

Extract this handoff into an existing approved local folder. Open a terminal in that folder and start your existing Claude Code installation with `claude`. Paste the contents of `CLAUDE_START_PROMPT.md`. Do not replace an existing repository's `CLAUDE.md` or move this bundle into a public repository automatically.

The first session is for read-only intake and a concrete source-access/receiver decision. The document does not authorize OS installation, credential changes, cloud provisioning, private export, live tenant changes, or G13 repair attempts.

## Important files

| File | Use |
|---|---|
| `CLAUDE_CODE_HANDOFF.md` | Extensive no-context handoff: exact pins, chronology, boundaries, decision tree, milestones, recovery and qualification requirements. |
| `CLAUDE_START_PROMPT.md` | Paste-ready initial instruction for Claude Code. |
| `HANDOFF_STATE.json` | Machine-readable current recorded state, proposals, and unknowns. |
| `evidence/FINAL-RESULT.json` | Original attached C32 outcome receipt, copied unchanged. |
| `evidence/LIBRARY-ROUNDTRIP-RESULT.json` | Original attached receiving-chat synthetic Library receipt, copied unchanged. |
| `evidence/synthetic_library_probe.zip` | That receiving-chat synthetic ZIP only, not the Work probe or project evidence. |
| `evidence/WORK_EXPORT_FAILURE_USER_REPORT.md` | Latest Work failure as a user-report transcription, not an original execution receipt. |
| `reference/ARCHIVE_LAYER_PINS.json` | Derived transfer expectations from pinned public metadata; actual layer bytes not included. |
| `reference/PACKAGE_PINS.json` | Exact release and native-tool references; binaries not included. |
| `SOURCE_NOTES.md` / `SOURCE_REGISTER.json` | What was inspected, what is linked only, and how each claim is sourced. |
| `worksheets/RECEIVER_AND_AUTHORIZATION.md` | Unknown receiving facts and approvals to resolve, not an approval grant. |
| `PACKAGE_QA.json` | Handoff-only validation outcomes and limitations. |
| `HANDOFF_PACKAGE_MANIFEST.json` / `SHA256SUMS` | Package integrity checks; not Intune test results or a signature. |

## The distinction to keep in view

A 67,732-byte Library test passed in the receiving chat. A different 18,445-byte file could not be exported from the original Work task: Drive returned 403 `ACCESS_TOKEN_SCOPE_INSUFFICIENT`. Claude Code can manage local work, but it does not inherit access to the source task's files or token. Do not repeat the failed source attempt without a relevant authorized change.

## Minimal launch message

```text
Read START_HERE.md and CLAUDE_START_PROMPT.md, then follow their intake phase.
Inspect the selected local environment and supplied evidence read-only.
Identify the actual authorized source-to-receiver route and the next bounded
step. Do not claim that a new local machine resolves source export, change
credentials, execute project code, or attempt G13 without its separate approval.
```
