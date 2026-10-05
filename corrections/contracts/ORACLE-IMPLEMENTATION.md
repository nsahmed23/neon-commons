# Independent oracle implementation contract

The executable original regressions demonstrate current omissions. The original correction pack specified this oracle without implementing it. This repaired distribution implements the bounded oracle in `../../reference/invariants.py`, exercised by `../../evaluations/test_repaired_oracle.py`; the requirements below remain its review criteria. It must use a separate reviewed parser/projection, not `normalize`, `generate` or their helper results.

Inputs: original restricted bytes, validated selection/context, pinned mapping rule set, normalized record, generated artifact directory, protected capture contract. Output: safe structured invariant failures, never raw values.

Algorithm:
1. Reject duplicate JSON keys, unsupported numeric encodings, malformed wrapper shapes and excessive nesting before parsing; compute raw-byte digest independently.
2. Verify all selected collections begin at the contract boundary and close the full nextLink chain. Derive policy/settings/assignments from those collections; reject ambiguous duplicate identities/references.
3. Locate selected policy from trusted tenant/family/object IDs. Derive stable key independently; compare normalized IDs/key and import/address references.
4. Recompute the specified canonical source digest. Reject an output digest not equal to the recomputed digest, even when the rest of the JSON is correct.
5. Map each policy/settings/assignment field using separately reviewed rules. Compare all desired fields, including technologies and scope tags. Compare settings ordered structure and IDs; compare assignments using validated semantic target tuples while detecting duplicates.
6. Derive all required reference identities from assignments/scope fields and verify exactly one qualifying source observation per identity, and unchanged external ownership. Compare normalized references; empty is not equivalent to missing.
7. Walk source JSON with escaped JSON Pointers. For every container/leaf, independently derive expected disposition, rule ID, destination pointer(s), and loss-blocking state. Compare the full entries, not pointer counts only. Unknown fields must produce blockers and safe retention refs.
8. Independently parse generated HCL/import structures (qualified parser and version) and compare generated address/import ID and selected object to step3. Ensure a partial record yields no active files or executable infrastructure command cards.
9. Check emitted artifacts/session/error paths for synthetic unsupported canaries and controlled secret canaries. Never treat passing canaries as general redaction proof.
10. Fail on any discrepancy; distinguish unknown/unqualified from semantic equality. File digests only prove byte identity, not correct interpretation.

Mutation operators required in addition to original suite: resource key, tenant/policy ID, source digest, technologies, scope, settings ID/value/type/child-order, lost/added/retyped assignment, exclusion/filter mode/ID, removed/duplicated/contradictory reference, every disposition/loss-blocking flag, destination pointer, generated import address/ID, first-page omission, fake final page, forbidden raw canary. A clean source-supported output must still pass so blanket refusal is not success.
