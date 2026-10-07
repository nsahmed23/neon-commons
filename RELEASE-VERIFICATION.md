# Current 0.8.0 qualification authority

The final external artifact receipt and R3 acceptance ledger bind the tested commit, exact source/runtime ZIP bytes, strict result, independent CLI/PTY journeys and reproducibility. The preserved R2 result is 1,141/1,141 with zero failures/errors/skips at commit `74130d0db99febf2f41cf4f4ebe2920a5d4dffb7`; it is not a test result for changed 0.8.0 source. See [R3 checkpoint](docs/CONTINUATION-R3.md) and [external gates](docs/EXTERNAL-QUALIFICATION-R3.md). All historical counts and failures below remain scoped to their original artifacts.

# Verification status: Intune IaC 0.5.1 engineering epoch

Current scoped results and unresolved gates are in [EPOCH-ACCEPTANCE.md](docs/EPOCH-ACCEPTANCE.md). The continuation bundle's `docs/T00-T13-ACCEPTANCE.json` links individual assertions to exact source revisions, commands and raw results. **The accompanying exact-archive verification receipts and acceptance ledger are authoritative for the delivered artifact.** This source document asserts no current integrated or packaged-artifact test total.

The counts below are preserved historical checkpoint results. In particular, the 884-run / 883-pass / one-prerequisite-skip result belongs to inherited 0.5.0 source and its reproduced baseline. It does not qualify modified 0.5.1 files. New source, local native tools, provider source methods, modeled lifecycle, performance and security observations retain separate evidence scopes. Enterprise release remains blocked.

---

# Historical verification: Intune IaC 0.5.0 engineering candidate

The retained 0.5.0 integrated source run executed **884 tests: 883 complete passes, zero
failures/errors, and one explicit native-provider prerequisite skip**. The strict
release verifier returned `success: false` and exit 1 because incomplete coverage
cannot pass its gate. The skipped case requires AF_UNIX provider communication
that this host denies. Native Atmos/OpenTofu adoption, locking and sealed-plan
observations are recorded separately; none establishes a live Intune lifecycle.

Read the [historical 0.5.0 acceptance](docs/PRODUCTION-COMPLETION-ACCEPTANCE.md),
`research/production-completion/final-verification/` and the external packaged
release receipt for archive hashes and clean-extraction results. The old 729-test
statement below applies only to the preserved 0.4.0 checkpoint.

Enterprise production acceptance remains **BLOCKED**. No live tenant operation
or organizational security acceptance is implied.

---

# Historical verification: Intune IaC 0.4.0

**729 tests passed**, with zero failures/errors/skips in the frozen integrated suite. See [current acceptance](docs/COMPLETION-ACCEPTANCE.md) and `verification/completion-0.4/result.json` in the source distribution for the final freshly executed suite. Native, simulation, provider-source, host and independent security receipts are separate under `research/completion/` and `research/provider-qualification/completion-20261002/`. Archive hashes and clean-extraction evidence are in the delivered integrity receipt. This checkpoint does not qualify enterprise or live-service use.

The reports below are retained historical checkpoints. Their counts are not substituted for current evidence.

---

# Release verification: Intune IaC 0.3.1

This edge-case repair release extends the prior engineering alpha. **624 tests passed**, with zero failures, errors, skips, expected failures or unexpected successes. The original 597-test result was real but did not cover the counterexamples below. It is not evidence of exhaustive correctness or enterprise readiness.

New regressions reject duplicate graph edge identities, contradictory/mistyped/missing coverage, Boolean/number substitutions in preservation evidence, duplicate JSON artifact keys, another session owner's lock, malformed saved progress, and six interrupted journal boundaries. The release verifier now rejects empty or incomplete suites and counts successful test methods directly, avoiding negative pass counts from multiple failing subtests.

`research/edge-case-audit/` in the source distribution contains the coverage matrix, red/control results, findings, independent cross-review summary and full source test receipt. Four new test modules add 27 methods; subcases are not counted as separate methods. The final external archive receipt records clean-extraction results and exact byte identities after packaging.

The workflow lock remains a cooperative local filesystem protocol; no hostile race-proof or distributed locking guarantee is implied. Graph validation checks consistency, not authenticated observations. The judge remains advisory, and no actual learned-model, native-host or live-provider benchmark ran. The enterprise goal remains open.

---

# Release verification: Intune IaC 0.3.0

This engineering alpha implements a guided cohort workflow, target evidence inspection, conservative plan review, a durable local operation/reconciliation protocol, explicit graph relationship contracts, dependency integrity controls and validation CI. **It is not production ready.** The continuing goal and exact unpassed gates are in `docs/ENTERPRISE-GOAL.md` and `docs/ENTERPRISE-EXECUTION-LEDGER.md`.

## Observed execution

| Check | Observed result and boundary |
|---|---|
| Final integrated Python verifier | 597 passed; zero failures, errors or skips, including repaired core regressions; final result in `verification/enterprise-0.3/result.json` |
| Final CLI, repository and terminal | 11 CLI checks, seven repository/wizard/action/MCP checks, and an actual Linux PTY generate/finish/verify journey passed |
| Guided cohort journey | Ten checks over three actual CLI invocations; incomplete policy stays blocked, changed-stack resume stays on the partial path, all nine receipts reconstruct, missing mapping receipt invalidates progress |
| Provider source characterization | 27 top-level Go tests passed against actual selected provider/SDK/serializer code; passing characterization includes reproduction of unsafe behavior |
| Provider paging correction | Original desired behavior: two controls passed and 12 top-level failures; candidate source patch: 14 top-level cases passed, zero failures/skips |
| Extracted resource Schema | Six Go cases passed, including actual Framework implementation validation; exact AST-selected method with unchanged helpers, not full resource/RPC/HCL execution |
| Graph refactor | 34 scoped tests, 918 query/error comparisons and 5,013 adversarial differential comparisons passed; independent rehashed mutations rejected |
| Wizard refactor | 54 scoped tests and 264 saved-session differential comparisons passed; real CLI/PTY journeys retained |
| Dependency installation | All ten wheel digests/sizes matched independently acquired PyPI records; fresh hash-required offline install, pip check and CLI doctor passed; CycloneDX artifact inventory validated |
| Known dependency advisories | Dated 2026-10-01 lookup: ten exact versions, successful OSV and PyPI queries, no returned runtime advisory IDs; historical uninstalled PyYAML control returned advisories. Not an absence-of-vulnerabilities guarantee |
| Validation CI | Seven local contract tests passed, including actual shell failure propagation and malicious archive cases; no GitHub-hosted workflow run |
| Independent review | Runtime specification/code-quality review passed after the prior-state denominator repair; bounded Codex Security scan repairs verified; provider/CI addenda retained with evidence |

The scope rows overlap; do not add their counts into a fictitious total. `verification/enterprise-0.3/` contains the source verifier, selected actual journey receipts, security evidence and independent review. Provider source profiles are in `research/provider-qualification/evidence/`. The final archive receipt, delivered separately, records exact ZIP hashes, clean-extraction tests, archive rebuild and exact-distribution Plugin Eval results. It is intentionally outside the ZIP to avoid a self-referential archive hash.

## Repairs and compatibility

- New generated project directories use mode 0700 and files 0600 on POSIX. Existing owned output is preserved, not silently permission-modified. Windows ACL behavior is unqualified.
- Graph projection and validation have explicit input/work bounds before repeated normalization, digest work and relationship scans. Relationship contracts and named validators retain unsupported/unknown relationships.
- Production accounting is now `production-1.2.0`, rule `1.1.0`. Restricted values, loss-blocking rows and container rows have null per-value hashes. Mapped visible scalar hashes remain. Whole-source digests still permit equality guesses when other input is known; this is not a confidentiality guarantee. Regenerate earlier review artifacts under the new contract.
- The plan reviewer cross-checks both prior and planned resource/output denominators and typed before/after values. Removed evidence cannot falsely become an empty no-change plan.
- Local journals enforce closed fields and legal transitions, dispatch verifies the desired snapshot, and lock ownership is checked before effects and release. Lost-response and receipt-write failures remain uncertain and require readback/reconciliation.
- Guided schema 2.1 has a separate explicit entrypoint and receipt store; it does not silently upgrade legacy wizard sessions. Saved progress never grants execution approval. Traversal, preexisting receipt conflict and concurrent cancellation cases are covered.
- CLI failures for locked or reconciliation-required simulations return nonzero. Three new MCP tools are read-only plan/target inspection and comparison; no network collector or simulation action is exposed through MCP.

Measured Radon complexity fell from 212 to dedicated validators at most 15 for graph validation, 145 to 12 for graph query dispatch, 127 to 9 for the legacy wizard controller, and 47 to 4 for plan review. Some large construction functions remain. These measurements make review easier; they are not correctness or readiness scores.

## Provider boundary

Actual selected-source execution reproduced initial HTTP-error acceptance, later-page silent truncation, unbounded continuations and dropped initial query expansion. The candidate MPL-2.0 GET patch rejects these cases, preserves complete continuation queries and imposes explicit bounds. The published provider is unchanged. Its shared DELETE caller, configured adapter/middleware behavior, assignment paging, complete lifecycle and service semantics still need qualification.

The real constructor/SDK test also confirmed an input setting ID is omitted by the provider constructor; refreshed settings retain response structure that configuration normalization does not reconcile. Production HCL remains inactive. Neither a green extracted Schema test nor a local GET patch establishes provider-valid no-change adoption.

No full provider RPC/HCL/import/refresh run, tenant operation, native host registration, Windows/PowerShell qualification, paid model inference or organization release approval occurred in this checkpoint. Earlier 0.2.2 native local Atmos/OpenTofu lab evidence remains historical evidence under its own declared scope; it is not silently presented as a new Intune run.

## Acquisition and packaging

All nine additional supplied repositories were acquired at pinned commits, with 7,610 regular files hashed. Selected files were inspected; the inventory is not a claim of auditing or executing all files. Reuse/rejection decisions are in `research/enterprise-inspiration/`. Raw selected provider/SDK/backend code retains upstream licenses and exact source hashes; see `THIRD-PARTY-NOTICES.md`.

The source archive uses an explicit reviewed inventory. The runtime excludes research, tests, labs, upstream clones and model weights. Hashes establish byte consistency, not authenticated publication or approval. Linux x86_64 CPython3.12 has a tested hash-locked wheel set; other platforms need separately reviewed artifacts. CI pins actions and uses read-only permissions, but organization hosting, branch protections and operational ownership remain open.

Static Plugin Eval remains a packaging/maintainability diagnostic. Its publisher policy fields cannot be invented to improve a grade, and its heuristics do not replace behavioral or security evidence. Native host and calibrated judge evaluation remain separate acceptance work.
