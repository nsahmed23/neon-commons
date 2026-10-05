# Independent review 02

Reviewed changes relative to baseline `f86b072` in `production.py`, `production_oracle.py`, `engine.py`, `repository.py`, and the repository additions to CLI/MCP/runner. This review did **not** independently review `wizard.py` or its tests, which this reviewer authored. No runtime or repository files were changed during review; probes and logs are under `review-02/` beside this report.

## Findings at the reviewed snapshot

After these findings were delivered, the root agent reported repairs for count contradictions, canonical UUID duplicate targets/record IDs, and inconsistent `isAssigned` metadata, with 36 focused tests passing. Those repairs were authored and tested by root and were not independently re-reviewed here. Probe result files retain the original reviewed-snapshot evidence.

### P2 — Contradictory OData counts still authorize an empty-assignment candidate

Locations: `intune_iac/production.py`, `normalize` collection loop (`@odata.count` check and terminal completeness); `intune_iac/production_oracle.py`, `_collections`.

Both implementations validate only that `@odata.count` is a nonnegative integer. They never compare a supplied total against the number of captured records. A terminal assignments page with `{"value": [], "@odata.count": 2}` therefore reports complete assignment coverage and `candidate_mapping_complete: true`, producing `configuration.assignments: []`. The probe sets policy `isAssigned` to false to isolate the count contradiction. A count of zero alongside existing assignment records also passes.

Impact: an explicitly contradictory capture can be presented as a fully mapped inactive candidate which removes all assignments. Execution remains blocked, but the candidate-mapping/completeness claim is incorrect; the source already contains evidence that rows are missing. The independent oracle repeats this gap and accepts it.

Suggested fix: reconcile supplied collection counts with the complete observed page chain, and block candidate mapping on mismatched or contradictory counts. Preserve source metadata in accounting; do not replace a mismatching capture with an empty successful projection. Cover positive count with no rows, zero count with rows, and consistent/inconsistent counts across pages in producer and independent oracle tests.

Reproducer: `review-02/probe.py`, cases `empty_with_count` and `zero_count_with_rows`. Evidence: `review-02/probe-results.json`; both currently return `candidate_mapping_complete: true` with only reference/ownership/provider qualification blockers.

### P2 — UUID casing bypasses duplicate assignment-target detection

Locations: `intune_iac/production.py`, `normalize` target-key digest; `intune_iac/production_oracle.py`, `_derive` target-digest check.

UUID validation explicitly accepts upper- and lowercase hexadecimal. Duplicate-target detection hashes the unchanged projected strings. Two otherwise identical direct assignments targeting `aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa` and `AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA` are therefore treated as different targets, and candidate mapping remains complete. These are the same UUID and should trip the existing `duplicate_assignment_target` gate. The oracle reproduces the same string-level comparison.

Impact: a case-equivalent duplicate bypasses an intended malformed-target safeguard and enters the inactive candidate. Execution authority is still false.

Suggested fix: canonicalize UUIDs for comparison keys only, while retaining exact source spellings in observed data/accounting. Apply semantic identity normalization to group/filter target keys and add mixed-case duplicate regressions. Do not silently rewrite retained source observations.

Reproducer: `review-02/probe.py`, case `case_duplicate_target`. Evidence: `review-02/probe-results.json`, where the two case variants remain in `configuration.assignments` with `candidate_mapping_complete: true`.

## Verification and scope limits

- 71 existing tests passed across repository, production, engine, repository interfaces, CLI, and runner. Command and output are recorded in `review-02/tests.stderr` and this review's tool history.
- Seven independent public-engine/repository/MCP probes passed (`review-02/verify-probes.py`, `verify-results.json`): changed target context rejected; changed assignments, forged execution authority, and missing source accounting rejected even after manifest hashes were updated; import/inheritance precedence and winning provenance correct; effective environment values omitted from public and MCP results; HCL addition changes source fingerprint; source symlink blocks discovery.
- Missing assignment collections correctly block candidate mapping. Unknown assignment fields produce opaque accounting without copying the canary key/value into normalized candidate configuration.
- Read-only inspection found no new native, shell, provider, or cloud dispatch path. Repository integration continues to return `execution_authorized: false` and omits `effective` from CLI/MCP/runner results. Source closure and containment were sampled, not exhaustively proven under concurrent filesystem mutation.
- `repository.py` empty/null merge semantics were actively being independently qualified by its owner during this review. This report does not flag transient intermediate implementation/documentation differences in that area.
- No real tenant, live provider, or native Atmos execution was used by this review. These findings concern offline completeness and semantic identity, not a claim that candidate Terraform is deployable.
