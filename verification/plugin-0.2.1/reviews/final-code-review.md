# Independent combined-change review

Date: 2026-09-30  
Baseline: `77682f84022232569418e6ff4e678f2cf06246de`  
Reviewed worktree: `intune-iac-plugin`, proposed 0.2.1 audit repair  
Status: final; all four reproduced findings, including follow-up variants, repaired and independently checked.

## Verdict

Spec verdict: pass for the bounded local-evidence audit repair. Quality verdict: no unresolved correctness/security finding remains from this independent review after the four findings below were repaired. Proceed with the root reviewer's final integrated and exact-byte source/runtime release gates. This is an engineering alpha for local evidence inspection and candidate authoring. Neither the inspected code nor the local suite establishes production adoption readiness.

The review covered the whole tracked diff, new audit regressions, production lineage schema, product-status matrix and audit plan. Focus was on contradictory source coverage, assignment provenance, fabricated saved review, unresolved dependencies, malformed MCP recovery and release-file boundaries. No cloud, provider, native host or paid-model execution was performed. The source inventory and release-verification report were still being prepared and their absence was not treated as a defect.

## Reproduced findings

### R1 — P2: unknown dependency selector fields create a qualified local dependency edge

Location: `intune_iac/atmos.py`, static dependency target selection (approximately line 199 before follow-up repair).

With same-manifest components `app` and `target`, set `app.settings.depends_on.dependency` to `{component: target, workspace: production}`. `inspect_atmos` produces `declaresDependencyOn` with `qualification: same_manifest_literal_selector` and no dependency issue. The selection ignores arbitrary fields outside the four named context keys. The effective projection correctly retains this selector as unknown, so static and effective paths disagree about qualification.

Observed result: one qualified declaration edge and an empty dependency-issue list. This is a pre-existing defect missed by the first repair, within the requested unresolved-dependency audit boundary.

Repair verified: an exact `{component}` selector is now required. The reviewer subsequently reproduced non-string YAML key bypasses in dependency and import selectors; those were also repaired by checking original key-node types/tags before the supported-key comparison. The exact original numeric-key counterexample now produces zero dependency/import edges plus `atmos_dependency_unresolved` and `atmos_import_evaluation_unqualified`. Numeric, boolean and sequence-key regressions pass. R1 is closed.

### R2 — P2: release member validation can be bypassed by a concurrent symlink replacement

Location: `scripts/build-release.py`, `write_archive` validation followed by `Path.read_bytes` (approximately lines 74–78 before follow-up repair).

The builder checks every member's symlink/regular-file path and later opens each path independently. Replacing a reviewed regular `README.md` with a symlink to an unlisted external private file between those operations causes the external bytes to enter the archive under the reviewed name. An ancestor directory swap has the same class of risk.

Deterministic reproduction patched `Path.read_bytes` to replace only the selected fixture member immediately before invoking the original read. Observed result: `unlisted_external_bytes_archived: true`. This requires concurrent filesystem write access; it is not an unauthenticated remote exploit. It defeats the selected-file confidentiality boundary nevertheless.

Repair verified: the builder opens an anchored source-directory descriptor, uses no-follow directory/member opens, checks bounded regular-file bytes and metadata, and feeds both archives plus inventory receipt from one source-byte snapshot. The platform boundary and quiescent-checkout requirement are documented. Leaf/parent-swap and runtime/source equality regressions pass. R2 is closed for the reproduced boundary.

### R3 — P2: typed graph validation accepts a filtered group exclusion

Location: `intune_iac/graph.py`, `_validate_graph` Assignment branch (approximately lines 540–559 before follow-up repair).

Start with the supported graph's include-filter assignment. Change its `target_type` to `exclusionGroupAssignmentTarget`, change its `includesGroup` edge to `excludesGroup`, and recompute the graph digest. `query_graph(..., 'assignments')` accepts the resulting filtered exclusion. Both bounded source contracts reject filters on exclusion-group targets. The new endpoint/mode consistency checks validate the pieces independently and omit this combination rule.

Observed result: `accepted_filtered_exclusion: true`, using the prepared clean Python environment and supplied supported fixture.

Repair verified: exclusion-group targets now require filter mode `none`; the paired node/edge mutation regression passes. R3 is closed.

### R4 — P2: duplicate synthetic assignment identities still appear as a complete fixed-query inventory

The synthetic UUID-duplicate follow-up now blocks offline generation, but its collection coverage remains complete. With `assignments[1].id = assignments[0].id.upper()`, `query_graph(build_graph(source), "assignments", selected_policy)` returns `coverage.status: complete` and both case variants as separate Assignment nodes. The full graph contains `duplicate_assignment_identity`, but that issue is absent from the fixed assignment query. Production normalization already marks duplicated collection identities incomplete. This is a remaining consequence of the existing audit finding, not a production-scope expansion.

Repair verified: producer and independent oracle now mark duplicate/missing collection identities incomplete. Graph projection omits ambiguous UUID-case assignment identities, and policy/assignment/setting fixed queries retain relevant policy-scoped blockers. The exact original duplicate-assignment counterexample now returns assignment coverage `unknown`, only the unrelated third assignment, and explicit duplicate/incomplete issues. Original source bytes are unchanged. R4 is closed.

## Focused review verification

A fresh prepared-environment run of `plugin_tests.test_release_audit` and `plugin_tests.test_atmos_audit` passed 24 tests after the final fixes. The log is `audit-03/final-review-regressions.log`. This includes source symlink swaps, shared archive snapshot, concurrent final output creation, known-production continuation handling, unknown/non-string selector fields, duplicate-assignment query behavior and filtered exclusion mutation. Exact original residual-counterexample outcomes are saved in `audit-03/final-review-counterexamples.json`. The full suite was not repeated solely for this review. `git diff --check` passed. Reviewed implementation/test byte hashes are in `audit-03/final-review-source-hashes.json`; release reports and inventory were still under root review.

## Other reviewed boundaries

- The production mapper now requires observed direct-assignment provenance. Its versioned field accounting names observation/configuration locations; the separate oracle derives expected dispositions and destinations from source records. Blocked candidate configurations do not acquire fictitious configuration destinations.
- Saved review completion requires generation and source evidence. Resume checks output bytes and independently reconstructs the source-derived project. Hashes and saved booleans are not used as approval.
- MCP initialization checks required metadata before changing phase; malformed JSON/encoding and malformed initialization metadata have bounded errors. Tool operations await the initialized notification.
- Count validation compares page declarations with complete-chain totals and preserves raw bytes. Synthetic assignment/reference UUID comparisons now use canonical comparison identities while preserving source spellings; duplicated observations also invalidate collection coverage.
- Exclusive archive and receipt opens preserve existing or concurrently created final files. Anchored source-file reads separately protect the member-read boundary, as checked for R2.
- `docs/PRODUCT-STATUS.md` accurately separates implemented behavior, observed local evidence, unfinished engineering and qualification gates. It does not infer production readiness from test totals.

## Remaining risks and limits

The next production milestones still require qualified provider request/state behavior, authenticated target/reference/writer ownership, a protected external action path with reconciliation, and native host/platform workflow evidence. The release inventory needs deliberate content review; an allowlist does not classify secrets in deliberately listed files. Local cooperative locks are not distributed ownership or hostile-writer protection. Live capture is not an atomic or authenticated tenant snapshot merely because its page chain is complete. Dynamic Atmos features and effective runtime configuration outside the documented literal subset remain unqualified.

The repaired implementation is defensible for a bounded local development release once the final exact-byte release gates pass. It cannot be described as completed brownfield production adoption.
