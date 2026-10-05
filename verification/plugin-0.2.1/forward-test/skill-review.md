# Offline Intune capture review

The local review is blocked for adoption. Both wizard workflows generated review artifacts and returned `status: complete`, `generated: true`, `execution_authorized: false`. Mandatory standalone verification fails for the first proposal and passes for the second proposal. Neither proposal contains active `.tf` files, inactive `.tf.txt` candidate files, or executable command cards.

## Scope and selections

The supplied capture is an offline constructed test fixture, despite its `synthetic: false` envelope and `plugin_graph_capture` classification. It is not evidence of a live tenant capture. No cloud, model, provider, Atmos, Terraform, or OpenTofu calls were made. No supplied input or plugin source was modified by this review.

The repository route was used because no context was supplied: `repository inspect` followed by `wizard --repo`. Repository discovery found physical stack selector `deploy/dev`, selectable Terraform component `policy`, and implementation `policy`. The wizard created each context from the repository. These were assistant selections for local review; no deployment or adoption approval is asserted.

Both policy UUIDs have the same display name, so each was selected by exact UUID and reviewed separately.

| Policy UUID | Output directory | Mapping status | Standalone verification |
| --- | --- | --- | --- |
| `22222222-2222-4222-8222-222222222222` | `proposal/` | Blocked; no configuration candidate | Exit 3: `postcondition_failed`, repeated with the same paths |
| `33333333-3333-4333-8333-333333333333` | `secondary-proposal/` | Blocked; no configuration candidate | Exit 0: `preservation_verified: true`, repeated with the same paths |

## Adoption blockers

The first policy has complete policy, setting and assignment collection chains in the supplied evidence. Its three assignments each lack observed `source` provenance, producing three `assignment_source_unobserved` and three `unsupported_assignment_shape` blockers. Each unrecognized assignment remains an empty observation object in normalized output; its original data remains in the supplied source. The one setting retains source ID `0`.

The second policy has no captured settings or assignments. Its blockers include two `collection_incomplete` records, `settings_missing`, `unsupported_setting_cardinality`, `setting_count_mismatch` and `assignment_flag_mismatch`. These gaps do not establish an empty live configuration.

Both policies additionally report `reference_evidence_unverified`, `ownership_unknown` and `provider_qualification_required`. Tenant identity is source-asserted. Repository discovery is bounded literal resolution; runtime layers, authenticated tenant identity, ownership and provider/state roundtrip behavior remain unqualified. All execution authorization flags remain false.

## Verification discrepancy

The first wizard printed a verified local proposal and completed the handoff, but the subsequent standalone verifier returned `postcondition_failed`: "Output does not match independently derived source expectations." The same-path repeat failed too. The second proposal independently verifies as a blocked review artifact.

The parent audit reported concurrent plugin repairs. A concrete version difference is visible: the first normalized review uses `production-1.0.0`, while the second uses `production-1.1.0`. Therefore this run does not establish a stable same-build verifier defect. Exact command arguments, return codes, stdout/stderr, and before/after hashes of source, context, output files, repository files and plugin Python files are preserved in the two `*-verification-repeat.json` records. Hashes were unchanged during each repeat, and each input/context matched the original wizard session fingerprint. The original proposals were preserved.

## Useful evidence

- `proposal/BLOCKED.json`, `proposal/review/normalized.json`, and `proposal/generated-files.json`: first policy review and manifest.
- `secondary-proposal/BLOCKED.json`, `secondary-proposal/review/normalized.json`, and `secondary-proposal/generated-files.json`: second policy review and manifest.
- `session.json` and `secondary-session.json`: workflow sessions; each `paths.context` identifies the wizard-owned repository context.
- `session-verification.json`, `secondary-session-verification.json`: first saved standalone verification results.
- `session-verification-repeat.json`, `secondary-session-verification-repeat.json`: exact repeat commands/results and hashes.
- `secondary-wizard-transcript.txt`: complete second wizard transcript.
- `doctor.json`, `repository-inspection.json`: local prerequisites and repository discovery evidence.
- Each proposal also has source/target receipts and an empty `commands/command-cards.json`.

## Next concrete step

After the concurrent plugin repairs settle, regenerate the first policy into a fresh output directory using the same source and a newly resolved repository context, then independently verify it without modifying the preserved proposal. Adoption still requires adequate assignment provenance, complete policy-specific capture evidence for the second UUID, reference and ownership evidence, and provider/state qualification. Do not infer missing evidence or deploy these review artifacts.

The doctor found the Python dependencies ready, while native tools (`atmos`, `tofu`, `pwsh`, `claude`, `codex`) were unavailable. This did not prevent the documented local review route.
