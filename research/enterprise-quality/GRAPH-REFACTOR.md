# Graph validation and query refactor

The graph's existing semantics now have separate, named validation and query
responsibilities. This is a maintainability change to the shipped implementation,
not a broader ontology, new source-of-truth claim or execution feature.

## Scope and architecture

- `intune_iac/graph_contract.py` centralizes the 23 existing predicates' source and
  target types, allowed relation statuses, and previously enforced conditional
  cardinalities. The closed node fields are declared alongside them. Rules such
  as exactly one assignment policy, one setting definition, one resolved component
  configuration, and no resolved target for an unknown dependency remain explicit.
- `intune_iac/graph_validation.py` separates envelope/work limits, source/origin
  checks, closed row shapes, typed relationships, policy/setting/assignment
  preservation, effective Atmos identities/fingerprints, and dependency resolution.
  Value-dependent assignment inclusion/exclusion/filter checks remain dedicated
  validation functions; a generic cardinality label cannot replace them.
- `query_graph` dispatches the same six fixed queries. Declaration selection,
  effective dependency selection, component placement, subject lookup and evidence
  projection have named helpers. Effective dependency lookups use a referring-edge
  set instead of repeated per-node scans. Output order and error messages remain
  unchanged in the checked corpus.

The practical Ontology Playground lesson is now implemented: relationship
contracts are executable and distinct from graph instances. No Microsoft runtime
code or RDF parser was copied. Missing/invalid cardinality is not defaulted and
unknown dependency placeholders are not dropped. No graph relationship grants
execution authority, authenticates evidence or infers an execution schedule.

The `_validate_graph` compatibility wrapper stays in `graph.py` and passes its
relationship-work limit explicitly. Work-budget validation remains before digest
calculation, shape scans and relational validation. Existing source-projection
budgets remain unchanged. The two new runtime modules must be included in release
inventories.

## Measurements

Tool: **Radon 6.0.1**, actual Python AST cyclomatic complexity (`radon cc -j`).
The exact before/after reports are `graph-complexity-before.json` and
`graph-complexity-after.json`.

| Responsibility | Before | After |
|---|---:|---:|
| `_validate_graph` | CC 212, 206 lines | Compatibility wrapper CC 1; validation entrypoint CC 1; most complex dedicated validator CC 15 |
| `query_graph` | CC 145, 98 lines | CC 12, 23 lines; most complex query helper CC 16 |
| Largest other graph function | `build_graph`, CC 92 | Unchanged, CC 92 |

This does not remove the domain's branching or claim the whole graph module is
simple. It moves related checks into reviewable units with one purpose and a
shared contract. `build_graph` (CC 92), effective Atmos projection (CC 42), and
capture-chain checking (CC 32) remain further maintainability work. More named
functions and expanded control blocks increase source line count; a reduced
headline function score is not a correctness gate.

## Verification

1. Before edits, all **34 existing graph/budget tests passed**.
2. After structural validation extraction, all 34 still passed.
3. After final query decomposition, all **34 passed**, zero failures/errors/skips.
   Their evidence includes denied/unknown captures, secret-safe output,
   identity scoping, exclusion/filter preservation, dynamic or unsupported Atmos
   resolution, malformed effective claims, and work-budget rejection before
   expensive validation.
4. A preserved six-graph corpus exercised every fixed query with no subject,
   every graph node, policy UUID subjects, an unknown subject and an invalid
   subject. **918 exact result/error cases matched** before and after. Canonical
   case digest: `3aebc98f7682122cd9626d922db303aece70717038d0b817b8a8fe4a62d16df2`.
5. A separate differential check rehashed edge-status changes, endpoint type
   substitutions, removed/duplicated edges, and node-status changes.
   **5,013 mutated cases matched** the pre-refactor implementation's accepted
   output or rejection code/message; zero mismatches. This verifies preservation
   of established constraints, not correctness of every possible input.
6. Point-in-time full shared-checkout verifier: **589 passed**, zero failures,
   errors or skips, including core regressions (`graph-full-verifier.json`).
   Root's final integrated verification supersedes this concurrent-work checkpoint.
7. `git diff --check` passed for the modified existing graph file.

The before implementation and six fixed graph fixtures are preserved under
`graph-refactor/`. Reproduce the 918 query cases and 5,013 adversarial cases from
an approved environment with the project's validation dependencies:

```bash
python research/enterprise-quality/graph-refactor/verify.py
```

This reads local fixture data and imports the current runtime. It does not call
cloud services or execute native tools. It prints a receipt and exits nonzero on
any mismatch. `graph-refactor-verification.json` records the shipped reproduction
harness result; `graph-equivalence.json` records runtime file hashes. The baseline
is historical comparison material and is never loaded by the product.

No new behavioral constraint was intentionally introduced, so existing behavior
tests and differential checks were used rather than adding tests that simply
mirror the extracted helper implementation. Independent review was requested for
the new contract, validation decomposition and final query projection; its result
is recorded by the integrating root reviewer.

## Limits

This refactor does not qualify service semantics, authenticate stored graph
provenance, expand supported setting families, close native host qualification,
or make the plugin production-ready. The graph still preserves unknowns and
returns `execution_authorized: false`.
