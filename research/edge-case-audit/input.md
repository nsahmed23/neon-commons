# Input, graph, and preservation edge audit

## Scope and method

Inspected bounded JSON decoding, capture chain handling, graph construction/validation, and the separate synthetic/production preservation oracles. Constructed counterexamples against the existing supported fixture, rehashed graph mutations so a checksum mismatch could not mask semantic defects, and retained valid complete/denied/declaration controls. No network, cloud, provider, or paid model calls occurred.

This is a selected adversarial audit, not exhaustive testing of every JSON value or Graph shape.

## Reproduced findings

| Finding | Minimal mutation after building the supported graph/output | Before repair | Repair |
|---|---|---|---|
| IN01: graph edge identities not unique | Set `edges[1].id = edges[0].id`, recompute graph digest | `query_graph(..., 'policies')` accepts two distinct relations with one identity | Require nonempty string edge identities and reject duplicate IDs |
| IN02: coverage assertions not unique or type checked | Append duplicate first coverage row; optionally change its status from complete to unknown | Both contradictory claims returned as valid policy query coverage | Require exactly one claim per allowed `(subject_id, aspect)` |
| IN03: coverage attached to wrong subject type | Change first policies claim subject to an Assignment node | Invalid policy coverage accepted | Derive claim denominator from actual node types |
| IN04: coverage denominator can disappear | Replace graph coverage with `[]`, recompute digest | Query accepts missing coverage | Require all emitted coverage identities; preserve explicit unknowns |
| IN05: synthetic oracle uses Python bool/int equivalence | Replace normalized observed policy `settingCount: 1` with `true`; or mapping flag `true` with `1`; or coverage `complete: true` with `1` | Each oracle invocation returns empty discrepancy list | Root owns independent JSON-typed comparison repair in `reference/invariants.py` |

The graph validator repair does not authenticate a graph's underlying observations. A recomputable digest is integrity bookkeeping, not a signature or proof that a cloud read occurred.

## Graph contract preserved

The required coverage denominator follows builder output rather than adding new cloud claims:

- Tenant: policies.
- Policy: policies, settings, assignments.
- StackDeclaration: Atmos effective resolution, always unknown.
- Resolved ComponentInstance: Atmos effective resolution; its existing semantic validator requires complete.
- Other nodes: no coverage claims.

Malformed declarations and denied collections stay unknown. Declared stack coverage cannot become complete merely because an adjacent resolved representation exists.

## Regression/control evidence

`plugin_tests/test_edge_input_audit.py` contains graph mutations, the three synthetic oracle mutations, a valid complete/denied graph pair, and a declared Atmos unknown-to-complete mutation/control. It also checks escaped duplicate JSON keys, nonfinite exponent overflow, unsafe integers, unpaired Unicode surrogates, depth 65 rejection, depth 64 acceptance, and maximum supported integer acceptance. Failure diagnostics must not echo the canary payload.

Initial run before repairs: 7 test methods, 8 assertion failures, zero harness errors. Five graph mutation subcases and three oracle mutation subcases failed as intended; valid graph and bounded JSON controls passed. Log: `edge-input-red.txt` in the workspace root.

After graph repairs: graph, resolution, budget, Atmos audit, and the then-seven new tests ran 55 methods with only the three expected unpatched oracle assertion failures and zero errors. Additional declared Atmos coverage test passed separately. Root owns the final combined run after oracle repair.

An initial repair omitted the existing StackDeclaration unknown coverage representation, producing 16 compatibility errors. The builder in `intune_iac/atmos.py` was then incorporated explicitly; rerun produced zero compatibility errors. This intermediate failure is not reported as a pre-existing defect.

## Remaining boundaries

JSON parsing uses binary floating-point; this audit does not establish arbitrary precision decimal preservation. The supported production setting subset uses string choice values and validates integer-only policy fields separately. Larger source node budgets, service freshness/authenticity, cross-page transactional consistency, and Windows filesystem guarantees remain separate qualifications.

Final scoped run after the root's typed oracle repair: **56 tests passed, zero failures/errors/skips**. Command: `python -m unittest plugin_tests.test_edge_input_audit plugin_tests.test_graph plugin_tests.test_graph_resolution plugin_tests.test_graph_budget plugin_tests.test_atmos_audit`. Receipt log: `edge-input-final.txt` in workspace root. This replaces the intermediate expected-red status above; the original red evidence is retained.
