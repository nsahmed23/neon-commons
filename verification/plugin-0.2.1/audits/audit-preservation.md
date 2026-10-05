# Preservation and intake audit — v0.2.0

Audited baseline commit: `77682f84022232569418e6ff4e678f2cf06246de`.
Scope: `intune_iac/production.py`, `production_oracle.py`, `engine.py`, the synthetic reference mapping selected by the engine, and observed source-to-output preservation. This audit did not execute a provider, Graph service, state import, or cloud operation.

## Findings and executed repairs

| ID | Severity | Reproduced baseline defect | Repair and verification |
| --- | --- | --- | --- |
| P01 | High for offline contract | The synthetic engine path accepted assignment `@odata.count:99` with only three captured rows, reported `offline_mapping_complete:true` / `preservation_verified:true`, and emitted two active reference `.tf` files. Negative, Boolean, string and null counts also escaped a consistency gate. The production path already checked counts. | Added independent count type/total checks in reference normalizer and oracle. Every collection is covered by regression assertions; contradictory synthetic inputs now retain review output and emit no active IaC. |
| P02 | Medium | Synthetic selected policy `isAssigned:false` with three observed assignment rows was reported complete, with no blocker. The production path already checked this contradiction. | Added selected-policy assignment-flag consistency to the synthetic normalizer and independent oracle. The diagnostic only compares complete assignment collections; denied/unavailable inventory remains unknown. |
| P03 | Medium | Production assignment rows with no `source` were silently treated as `direct`; a complete candidate was produced even though source provenance was unobserved. No execution authorization was issued, so this was an overstated candidate mapping claim, not an observed cloud mutation. | Require explicitly observed `source:"direct"`; absence emits `assignment_source_unobserved`. Microsoft describes distinct direct/policy-set sources but does not document omission as proof of direct provenance. This stricter requirement is a local support restriction, not a new claim about service behavior. Updated clearly synthetic API-shaped wizard/qualification fixtures to include their intended source; kept a regression for omission. |
| P04 | Medium | Every production field-accounting row said only `restricted_source` with opaque pointer/value hashes. Even the emitted desired setting value had no disposition, rule/version or destination, despite earlier correction requirements for mapping lineage. The oracle repeated this limited digest inventory. | Added explicit dispositions, rule IDs/versions, observation/configuration destination pointers, loss-blocking flags and retention locators for every source node. Unselected objects, unsupported records/pages and unverified envelope claims have distinct rules. The independent oracle derives lineage separately; mutations to disposition, destination, rule and loss flags are rejected. Added a closed schema and tests that every declared destination exists for supported and blocked candidates. |
| P05 | High for offline contract | An assignment ID repeated with different UUID letter casing, or a duplicate unselected policy ID with different casing, was accepted as distinct by the synthetic producer and oracle. | Canonical UUID comparison keys now guard policy/assignment observations, target group/filter tuples and reference matching. Duplicate/missing observed IDs also invalidate the corresponding collection completeness, so graph consumers cannot treat an ambiguous collection as complete. Raw spelling remains unchanged; setting IDs retain opaque string comparison. Regressions cover IDs, targets and an oracle mutation that falsely promotes the duplicate capture. |
| P06 | Medium, introduced during repair and caught before release | First implementation of P04 searched every record location for every source node, creating quadratic work for large unselected-policy inventories. | Both lineage implementations now index exact known record/page ancestor paths. A 4,000-unselected-record normalization/oracle regression runs in a subprocess with a generous 30-second bound. Before the new whole-export node budget, a separate 20,000-record measurement completed in under one second; that larger capture is now outside the public mapper budget. |
| P07 | Medium | A 64,182-byte source with 20,000 unsupported scalar-array items expanded to a 9,728,532-byte normalized file. A 124,182-byte source with 40,000 such items expanded to 19,388,532 bytes; the existing output parser rejected it before writing, but only after allocating the full ledger. | Producer and independent oracle now limit the whole production export to 10,000 JSON nodes before constructing lineage; iterator traversal bounds auxiliary memory by depth. `capture_node_limit` remains visible through the engine. A regression proves accounting/derivation is not reached and no output is created. The documentation explicitly forbids truncating complete captures to fit this bound. |

Production normalized contract is now `production-1.1.0`; its field-accounting rules are separately versioned `1.0.0`. Previous normalized production reviews must be regenerated and independently checked. The capture envelope/exporter version remains unchanged because the raw capture format did not change.

All seven findings are fixed within the bounded offline implementation. None expands supported setting families, qualifies provider semantics, authenticates captures, or grants execution authority.

## Reproduction and failure-to-pass evidence

Runtime: `/workspace/scratch/26b6d364cfda/plugin-clean-venv/bin/python`.

Baseline behavior repro:

```sh
/workspace/scratch/26b6d364cfda/plugin-clean-venv/bin/python /workspace/scratch/26b6d364cfda/repro-preservation-audit.py
```

That script imports the current checkout; the recorded baseline defects above were observed before repairs. The stronger failure-to-pass check runs the new regressions against an immutable `git archive` extraction of baseline commit `77682f8`, then against repaired code:

```sh
/workspace/scratch/26b6d364cfda/plugin-clean-venv/bin/python /workspace/scratch/26b6d364cfda/run-preservation-regressions.py /workspace/scratch/26b6d364cfda/preservation-baseline-020 /workspace/scratch/26b6d364cfda/preservation-red
/workspace/scratch/26b6d364cfda/plugin-clean-venv/bin/python /workspace/scratch/26b6d364cfda/run-preservation-regressions.py /workspace/scratch/26b6d364cfda/intune-iac-plugin /workspace/scratch/26b6d364cfda/preservation-green
```

Results: eleven regression test methods produced 21 assertion failures on baseline (subtests counted individually), zero harness errors, zero skips. The same eleven methods passed after repairs, with zero failures/errors/skips. Receipts and full logs: `preservation-red.json/.log`, `preservation-green.json/.log` next to this report.

Additional verification: 44 selected engine/production/wizard tests passed. All 207 original core evaluation tests passed after repair; existing goldens were not changed. An interim diagnostic incorrectly compared denied assignments to `isAssigned`; the original denied golden caught it, and the implementation was fixed to compare only complete assignment inventory.

## Reviewed primary source

Microsoft Graph `deviceManagementConfigurationPolicyAssignment` resource, properties `source` and `sourceId`:
https://learn.microsoft.com/en-us/graph/api/resources/intune-deviceconfigv2-devicemanagementconfigurationpolicyassignment?view=graph-rest-beta

Reviewed during this audit. The page distinguishes `direct` and `policySets`; no omission-as-direct default was identified. It identifies assignment `id` as a string key, so this audit did not impose an unsupported universal UUID requirement on that field.

## Remaining product boundaries

The corrected mapper still supports one worked privacy choice only. It emits inactive production candidates and keeps provider, service, ownership, reference existence, request serialization and refreshed-state equivalence unqualified. The explicit lineage contract improves explainability and mutation detection; it is not a replacement for independent provider/service qualification or broader settings-family implementation.

## Lineage lookup performance check

The pre-optimization lineage function was reconstructed from the immediately preceding local implementation and retained as `preservation-lineage-before-optimization.py.txt`. `benchmark-preservation-lineage.py` runs that function and the indexed replacement over identical inputs, requiring exact row equality. Single local samples below are performance evidence for this implementation change, not a production SLA.

| Extra unselected policy records | Before seconds | After seconds | Same lineage |
| --- | ---: | ---: | --- |
| 500 | 0.054 | 0.006 | Yes |
| 1,000 | 0.126 | 0.011 | Yes |
| 2,000 | 0.453 | 0.021 | Yes |
| 5,000 | 2.697 | 0.058 | Yes |

Exact timings and function hashes: `preservation-lineage-latency.json`. The synthetic UUID repairs were independently cross-reviewed by the host/judge reviewer. After the final changes, all eleven audit regression methods and all 207 original core tests passed; existing goldens remained unchanged.

## Node expansion budget evidence

`preservation-budget-before.json` records the two measured expansion cases; `preservation-budget-after.json` confirms both now fail with `capture_node_limit` and no destination written. This limit counts the entire production source, including unselected policies, containers and scalar values. Larger complete captures need a separately qualified batching or streaming adapter; the limit does not permit filtering or truncating the fixed expected capture boundary. Existing output parser and 16 MiB file limits remain defense in depth.

The final baseline run is eleven test methods with 21 expected assertion failures, zero harness errors/skips; the repaired run has eleven passes and zero failures/errors/skips. All 207 original core tests also passed after the final duplicate-coverage and node-budget changes.
