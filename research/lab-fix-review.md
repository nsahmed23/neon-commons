# Independent review of local-lab audit fixes

Reviewed the uncommitted changes to `intune_iac/repository.py`, `graph.py`, `runner.py` and `docs/REPOSITORY.md` against `539f9421bf3ab890b0b0ced9d645e6896fbbc02a`. This reviewer did not author the implementation. The scope is the two local-lab audit repairs and related evidence consumers, not a full production certification.

## Findings at initial review

### R01 — `graph_build` still accepts changed implementation presence (P2)

The repository-specific evidence fix is not used for the graph builder's `atmos_root` parameter. `_proposal` still calls `_directory_evidence` for that parameter, and the directory digest contains file entries only. The graph builder reads implementation-directory presence, so this leaves the same evidence mismatch through another action.

Reproduced with an ordinary temporary repository:

1. Declare `app` in a literal stack with no implementation directory.
2. Obtain a `graph_build` proposal with `atmos_root` pointing to that repository.
3. Create the empty `components/terraform/app` directory.
4. The resolver changes `implementation_exists` from false to true and changes the newly repaired selection fingerprint, but `_recheck(proposal)` accepts the old graph-build evidence.

Repair either the directory evidence's structural coverage or the graph builder's evidence adapter, retaining its existing whole-directory byte coverage where needed. Add graph-build regressions for creation/removal of empty selected implementation directories. This is a remaining local evidence-consistency defect, not evidence of cloud execution or approval bypass.

### R02 — Repository result postcondition does not bind structural claims (P2, preexisting adjacent weakness)

The new proposal binds discovery structure, but `_verify` compares the dispatched repository report only to the file-only `source_fingerprint` plus a status allowlist. With the repository unchanged, passing a public resolution report whose `implementation_exists` was changed from true to false still returns `evidence_unchanged: true` rather than rejecting the internally inconsistent result.

This was reproduced by a focused `_verify` fault-injection call; no spontaneous production dispatch failure is claimed. The existing regression for a wrong source fingerprint protects one report field, but does not cover the new structure/selection claims. Bind the returned resolution/discovery result to the proposal's selected target and observed structure, and reject contradictory selection fingerprint/presence/path combinations. A result claiming verified evidence should not accept the opposite implementation observation.

## Repair disposition and verification

The root implementer accepted and repaired both findings after reproducing them with two additional failing regression tests.

- **R01 repaired:** `_directory_evidence` now binds both file digests and sorted directory paths, with a 4,096-entry traversal bound. This covers the graph builder's existing `atmos_root` evidence without reducing its file coverage.
- **R02 repaired:** repository result verification now reconstructs the selected parameters, compares their digest with the proposal, rereads the public repository result and requires the entire returned report to match. The contradictory implementation observation is rejected.

This reviewer inspected those repair changes and independently reran all **6** methods in `plugin_tests.test_lab_audit_regressions`: all passed with no failures or errors. No unresolved finding remains in this bounded review. The root implementer separately reported 37 passing scoped tests and is responsible for the final integrated suite.

## Other passing checks

- All **4** supplied `test_lab_audit_regressions` methods passed.
- All **60** repository, repository-interface, effective-graph and Atmos-audit tests passed.
- Five additional dependency collection shapes—string containing a private canary, list containing that canary, null, boolean and number—produced visible `atmos_dependency_collection_unresolved` issues for the selected component. The private canary did not appear in any query output. Each graph reported partial Atmos resolution and execution remained unavailable.
- The graph validator recomputes the selection fingerprint from the implementation directory and presence. The newly added unknown dependency node uses null selectors, opaque provenance pointers and safe structural fields; the tested malformed values are not copied into the review projection.

## Documentation and compatibility

The revised `docs/REPOSITORY.md` correctly separates file-byte source fingerprints from selection fingerprints that include implementation path/presence. Its formula matches the changed resolver and graph validator. Directory presence still does not establish valid HCL or provider readiness.

Selection fingerprint computation changed without changing the `atmos-literal/1.0` adapter or graph schema version. Old persisted graphs with effective Atmos configurations therefore need regeneration before the new validator can query them. This is a compatibility note rather than a release blocker for the stated alpha, but the release notes should make it explicit or the format should carry a new version.

No authenticated approver, real provider/service lifecycle, filesystem race isolation, Windows terminal or external host behavior was tested in this review. Closing these local findings does not close those production qualification requirements.
