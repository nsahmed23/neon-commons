# Intune-to-IaC plugin: corrected completion and audit prompt

Prepared 2026-10-02. Read START-HERE.md first. This is an engineering handoff, not production acceptance.

## Scope and mission

Finish the interactive brownfield Microsoft Intune-to-IaC plugin and wizard using OpenTofu, Atmos, Azure, Entra and Graph. The deliverable must work in existing repositories and preserve policy identity, settings, inclusions, exclusions, assignment filters and relationships. Implement evidence-backed intake, repository/stack selection, cohort workflow, generation, import/adoption, exact plan review, protected execution and independent reconciliation.

The previous conversation drifted into Wally, a general-purpose native chat terminal. That is a separate project. Do not build or port model transport, chat sessions, a terminal emulator, or a complete agent runtime as prerequisites for this plugin. This package excludes that implementation. Reuse ideas only when they solve a specific Intune workflow requirement. A host agent may invoke the plugin; the plugin does not need to become the host agent.

Preserve the original performance intent: fast, responsive, bounded CLI/workflow behavior. The existing implementation is Python; no claim is made that it meets the later native-only/zero-allocation directives. Record this contract conflict explicitly. Measure the actual plugin commands and wizard, propose the smallest necessary implementation changes, and distinguish host overhead from plugin work. A language rewrite or whole chat-client product is not automatically authorized by a performance target.

Continue independent engineering when a particular tenant/hardware dependency is unavailable. Do not repeatedly ask whether to proceed. Use parallel implementers/reviewers where available and permitted, with explicit ownership and evidence. No live tenant mutation, paid inference, publication, trust installation or deployment is authorized by this prompt alone. Prepare concrete work and identify the exact missing authority for any such operation.

## Read and reproduce the actual product

Start with README.md, docs/PRODUCT-STATUS.md, docs/ENTERPRISE-GOAL.md, docs/ENTERPRISE-EXECUTION-LEDGER.md, docs/WORKFLOW.md, docs/PRODUCTION-MAPPING.md, docs/TARGET.md, docs/REPOSITORY.md, docs/GRAPH.md, docs/HOSTS.md, docs/CLM.md and docs/CI.md. Read research/provider-qualification/IMPLEMENTATION-REPORT.md and DEPENDENCY-FINDINGS.md, and the enterprise-target/execution/dependencies reports. Use the actual intune_iac/, reference/, plugin_tests/, evaluations/, labs/ and scripts/ code.

This is a focused derivative of the last saved combined source archive, whose SHA-256 was 5066e483fd96555968e2076aa2f0e6894aa8313554cde55416336026ff9ef705. Runtime implementation was copied unchanged using release-source-files.txt. Scope correction edits front-door documentation, adds this prompt, and retains materials-verifier format regressions under an Intune-specific path. Historical research and receipts retain their original bounded scope. SOURCE-CORRECTION.json lists the exact changed and added files.

The prior reference suites passed 417 plugin methods and 207 evaluation methods. These do not prove provider-backed adoption, authentic approvals, live service semantics, native host behavior or production safety. Rerun current tests and keep counts separate from assertions and source characterization cases. Historical Appendix B G03/G04/G06 closure claims are not current acceptance. Passing schemas or a specification are not implementation closure.

Keep production generation inactive when preservation, provider or target gates are missing. Do not rewrite goldens before fixing algorithms and independent oracles. An unavailable assignment collection must never become an empty desired assignment set.

## Known open issues

Use statuses CONFIRMED_DEFECT, UNIMPLEMENTED, UNSUPPORTED_PROFILE, UNQUALIFIED, ENVIRONMENT_BLOCKED, FIXED_LOCAL and ACCEPTED_WITHIN_SCOPE. Every issue needs exact paths/hashes, reproduction, impact, repair, independent closure oracle, test evidence and dependencies. Add newly discovered issues; this inventory is not a proof that there are no others.

### Protected execution and authentic context

**X01 — Production execution adapter.** The shipped runner supports fixed local actions and local policy/assignment simulations. It is not the qualified Intune provider/import/plan/change adapter. Implement the real guarded adapter without allowing model-generated commands, arbitrary shell text, caller assertions or test bypasses to grant authority. Existing native-tool labs establish workflow mechanics only.

**X02 — Effective authenticated identity.** Bind actual Graph/ARM endpoints and cloud, tenant, provider and backend principal/client identities, federation issuer/subject/audience and fresh credential use. The target comparator has 54 binding leaves and three optional fixed GET observations, but supplies consistency/partial facts rather than complete authentication. Supplied JSON, opaque access-token decoding, labels and az account show cannot authenticate the actual provider/backend invocation. Separate backend and Intune identities.

**X03 — Backend state and writer ownership.** Inspect actual resolved subscription/storage resource/endpoint/container/key/workspace/blob/lineage/serial and writer lease. Do not invoke an accessor that creates empty state while calling the operation read-only. Add distributed single-writer exclusion/fencing, lease-loss handling, stale-plan binding and last-moment target comparison. Test competing hosts, state mutation and changed credentials.

**X04 — Protected approval and plan provenance.** Bind exact saved binary plan, configuration snapshot, tool/provider identities, target and state revision. Establish protected approver identity/delivery, reviewed preparation provenance, expiry, one-time consumption and trust/key lifecycle. Offline fingerprint comparison is not authentication. No self-signed bundle or model/judge decision can authorize effects.

**X05 — Restricted credential/tool execution.** Design least-privilege credentials, bounded secret-safe output, exact executable/provider identity, environment/descriptor hygiene and an explicit repository/hook policy. HCL, providers, provisioners, external data sources and dynamic Atmos functions are executable input. A fixed local lab is not arbitrary-repository containment. Include child processes and required tooling in resource/dependency accounting.

**X06 — Real recovery.** Policy updates, assignment requests, state writes and receipts are separate effects. Qualify fail-before/fail-after/lost-response/readback failure for each. Maintain partial/diverged/unknown outcomes and independent authenticated readback; never blindly retry or release another owner's lock. Visible bytes after failed fsync are not durable completion. Implement reviewed operator recovery and storage durability/concurrency qualification.

**X07 — Independent security review.** Audit the actual plugin boundaries for identity/approval spoofing, stale target, replay, input substitution, path/permission/TOCTOU errors, secret leakage, evidence tampering and privilege separation. Earlier bounded Python findings have repaired regressions; they do not certify expanded external execution. The blocked broad review of the separate native project is neither a completed plugin review nor a reason to mark this gate passed. Respect review restrictions and record unavailable capabilities.

### Provider, capture and preservation

**P01 — Selected provider has executed source defects; published provider is unchanged.** Baseline: `deploymenttheory/terraform-provider-microsoft365` v1.0.0, commit `1718c946b3ae111bb44c7c1d925b3e35b708cb0a`. Read the pinned ledger. The settings constructor receives ID but does not call the SDK setter; unknown instance types can be skipped; empty children and null references differ from observations. State mapping retains response wrappers/order, can preserve old settings on malformed JSON, and can accept an error envelope as settings. Secret restoration uses array positions. Normalization and placeholder `ModifyPlan` do not establish semantic equality. Fix the actual provider path; do not renumber IDs, discard observed fields, normalize away differences, or weaken the independent oracle to manufacture no-change.

**P02 — Pagination patch is a candidate, not provider closure.** Original selected GET source accepted first-page 403 and later-page truncated success, dropped initial `$expand=children`, and lacked helper-local continuation safety bounds. The candidate patch has passing source regressions but shares `makeRequest` with an unqualified DELETE caller, still uses a default client instead of configured adapter middleware, and does not establish item identity/count completeness or service semantics. Audit affected callers, configured transport/auth/retry behavior, bounds, duplicate identities and endpoint-specific success codes. Integrate only a reviewed, pinned complete provider build.

**P03 — Assignment refresh and semantics remain open.** Inspected assignment read consumes one SDK page without a continuation loop. Constructor null/unknown-to-empty and invalid-target skipping are source findings, not complete executed qualification. Prove complete paging, correct target/filter mapping, inclusion/exclusion preservation, and treatment of omitted versus empty assignments. Establish replacement-versus-merge and lost-response behavior with separately authorized service experiments; an outgoing array or “atomic” comment proves neither.

**P04 — Full provider RPC/config/import/no-change qualification is absent.** Twenty-seven characterization tests, fourteen patched-helper tests, and six AST-extracted Schema tests are narrower than a full resource. Full native schema/RPC/config validation was not established; earlier provider startup encountered host restrictions. Full dependency acquisition/verification is incomplete. Complete actual provider build/schema/HCL/default/validator lifecycle, ID-preserving import, ordinary and refresh-only no-change, and actual request/state roundtrip. The default zero filter GUID differs from explicitly configured zero; adjacent ID validation does not enforce the comment's first-zero rule. Keep these distinctions until real lifecycle evidence resolves them.

**P05 — Authenticated capture and production exporter coverage are incomplete.** Preserve exact initial collection boundary, full returned nextLink, origin/path/bounds, missing/denied/failed status, duplicate observation policy and source lineage. A complete supplied chain is not proof of authenticity, freshness or a transactionally consistent snapshot. Extend only with explicit exporter/cloud/version contracts; implement actual credential integration, independent external-reference accessibility and collection denominators. Never translate unavailable assignments into an empty desired assignment set.

**P06 — Mapper/oracle support is narrow.** The known-production candidate covers one Windows/MDM privacy choice setting and direct group assignments. Implement additional metadata, setting/value polymorphs and required targeting forms against independent evidence. Preserve stable keys, source digests, import addresses, every desired field/value, settings structure, assignment tuple and reference, plus exact field dispositions/destinations. Pointer presence or schema acceptance is not preservation. Retain unsupported raw values only in restricted originals; model-visible artifacts use safe references/reasons/blockers without secret-bearing hashes or canary values. Regenerate goldens only after algorithms and independent mutation checks are repaired.

**P07 — Estate denominator, diagnosis and rollout are unfinished.** Establish requested versus supported/unsupported/unavailable families, object and assignment counts, rings/cohorts and exclusions. App/script/other policy adapters and Windows diagnostics remain staged. The reviewed Powerstacks collector lacked an applicable repository license at the pin and needs native exit checks, immutable bounded capture, ACLs, explicit denied/truncated channels, UTC correlation, redaction and provenance before reuse. Do not copy unlicensed code or execute privileged collectors merely because they are research inspirations. Qualify diagnostics against independent device/service signals and actual rollout denominators.

### Atmos, semantics, workflow, hosts and operations

**A01 — Literal Atmos resolution is not complete effective context.** Existing code/labs handle bounded imports, inheritance, overrides and implementation/component distinctions. Complete logical versus physical stack identity, runtime configuration precedence, environment/CLI/auth/backend transformations, workspace templates and selected dynamic features. Distinguish the pinned Atmos 1.199.0 from current-main examples. Use native differential tests or a protected native inspector; arbitrary `describe` can evaluate functions/templates/auth and is executable input. Do not assume source YAML alone identifies the actual state target.

**A02 — Semantic relationships need observed backing.** The graph has 23 centralized predicate contracts and substantial differential coverage, but reference existence/access, state-writer ownership, cross-stack identity, real cohort membership and filter semantics need authentic evidence. Maintain declared versus effective versus observed facts, provenance, freshness, unknown/denied/conflicting states, cardinality and referential integrity. Labels/names are not identity. Prove semantic answers and action prerequisites from evidence; adding an ontology library does not supply missing facts.

**A03 — Complete guided adoption workflow.** The reference has a receipt-backed cohort wizard, nine reconstructed milestones, partial generation and edit/resume invalidation. Complete provider-qualified adoption, protected approval handoff, conflicts/reconciliation UX and capability selection in this plugin. Preserve progress-frontier limits and selective dependency invalidation: changing cohort at object selection must not jump forward; changing stack during partial generation must not route to full generation. Reconstruct receipts from real artifacts/dependency hashes; a verified_completed parameter is not evidence by itself.

**A04 — Host/platform integration is unqualified.** Portable/Codex/Claude manifests, CLI/MCP tests and Linux PTYs do not prove actual installation/discovery/use/uninstall. Resolve Plugin Eval manifest/schema/runner-version differences against the installed host, separating structural checks from actual model execution. Qualify native Windows/PowerShell and other declared platforms, terminal restoration, paths/quoting, environment handling, registration and interrupted journeys. Do not claim a host supports the plugin because a local JSON validator accepts its manifest.

**A05 — Labs and research are bounded evidence.** Real Atmos/OpenTofu local adoption, identity-only import, no-change, stack isolation, stale plan and local lock exercises exist. They use built-in `terraform_data`, not Intune service state. All 88 Terraform catalog entries were scanned, 24 targeted semantic inspections and eight complete checker reads were recorded; 299 encrypted solutions remained unread and most labs unexecuted. Eight adapted local locking tests do not qualify the whole catalog, remote backend or Terraform 1.15. Select labs that close a named gap; do not repeat broad ecosystem research or claim every acquired file was audited.

**A06 — Maintainability and scaling require further work.** Some graph construction/resolution functions remain large. Measure complexity and bounded work, then refactor with independent differential semantics and exact performance comparisons. Test large estates, graph fan-out, provenance size, path/import cycles, deep configuration, total byte/object limits and adversarial multiplier combinations. A lower complexity number or more files does not prove clearer, faster or correct code.

**E01 — CLM/judge usefulness is unproven.** There is an optional bounded advisory CLM HTTP adapter, with local protocol tests, not calibrated learned-model quality or production latency evidence. Do not assume CLM is better than Jev for these tasks. Pin model/server/tokenizer/rubric, measure accuracy, abstention, uncertainty, cost, latency and distribution shift on representative held-out tasks. Deterministic checks own preservation, authorization, plan effects and performance acceptance; judges cannot overrule them.

**E02 — Production-shaped behavioral evaluation is missing.** Implement the evaluation program in section 8. Test actual host discovery and task execution, not only forced skill loading or static package scores. Establish whether the tool improves useful, safe decisions and repairs compared with a capable agent and a minimal checklist. Preserve null/inconclusive results.

**R01 — Enterprise release and operations are unaccepted.** Existing CI is local-validation configuration, not an observed organization-hosted pipeline. Establish actual branch/review protections, scoped CI identities, artifact signing/provenance, publisher trust, vulnerability/update policy, dependency locks for supported platforms, install/upgrade/rollback/uninstall, support owner, incident procedures, sensitive-data retention and audit access. Refresh advisory evidence; no monitoring was created by the old lookup. Inventory the shipped plugin and required native toolchains separately, then describe the full deployment dependency boundary.

**R02 — Authorized pilot and accountable release decision are absent.** Require a named nonproduction tenant, existing policy/family/exporter/backend/host combination, least-privilege identities, expected preservation, recovery exercises, ring rollout criteria and accountable approver. A narrow pilot qualifies only its named slice. Do not provide a completion percentage based on test counts or quietly shrink the requested estate to declare success.

**R03 — Evidence tooling must remain trustworthy.** Inspect collectors and pass/fail aggregation, not just application code. Test stale/extra/missing source inventories, dependency changes, false ready markers, zero/skipped tests, malformed receipts, process errors, drifted workloads and unbound timings. The materials verifier honors declared JSON Schema dialects and distinguishes acquired `.jsonstream` from JSONL; acquired bytes are unchanged. Preserve its 15 regressions in research/verification-repair/tests/ and do not revert that rename. Run the text-only materials scan on the source distribution before introducing compiled binaries.

## Behavioral evaluation and hill-climbing


Build one complete small experiment before a large framework: a real task, actual candidate/host execution, independent grading, retained trace, fair control, and a useful failure. Then expand by independent causal task families:

- Safe brownfield import/no-change and correct rejection of incomplete capture.
- Preservation of settings, exclusions, filters and IDs under benign transformations.
- Correct Atmos/target/backend selection and honest handling of unknowns.
- Planning and recovery under stale approval, partial effects and unavailable evidence.
- Plugin workflow/input/session defects and true CLI performance repairs.
- Diagnostics that distinguish plausible hypotheses from observed service/device facts.

Use at least CONTROL (same capable agent without the plugin), MINIMAL_CHECKLIST, REPAIRED_BASELINE and one CANDIDATE. Hold tasks, tools, information, budgets and environment constant; include the plugin's overhead in cost. Separate forced-loading tests from natural host discovery. Measure review quality separately from downstream repair ability, and frozen versus optimizable software behavior separately from prompt changes.

Validate tasks and graders with independent known-good alternatives and known-bad mutations. Include shortcuts such as always abstaining, refusing all changes, generic checklists, claiming measurement without running it, and dropping work to look fast. Reward successful safe adoption as well as correct blocking; an agent that refuses every task is not useful. Unexpected valid solutions require blinded adjudication rather than exact-answer matching.

Split by causal family, repository ancestry and mechanism, not cosmetic variants. Existing published fixtures are exposed regression/training material, not hidden holdouts. Keep answers, seeds, generators that reveal answers, and evaluator credentials inaccessible to the optimizing agent. Context inheritance also contaminates a holdout. Report actual isolation limits; publishing a private evaluator retires its secrecy.

Deterministic oracles own correctness, preservation, authorization and performance gates. Calibrated CLM/LLM judgments may assess explanation quality or prioritize review, with abstention and escalation. Freeze grader version before optimization; never co-tune the judge to make the plugin win. Compare available stronger models/more effort as a diagnostic hypothesis, not a guaranteed monotonic law. Keep hard-but-solvable challenge headroom while permitting regression suites to saturate.

Predeclare practical effect thresholds, critical-failure rules, noninferiority margins, task exclusions, infrastructure retries, model/effort and spend limits, analysis, and a bounded mutation budget. Pair runs and randomize order; use family-level uncertainty, not thousands of correlated variants as independent evidence. Keep all scheduled attempts, including failures and infrastructure errors. Unknown cost/usage fields remain null. Do not infer private reasoning traces.

For each mutation retain parent/candidate hashes, causal hypothesis, changed surface, targeted failure family, metrics, guardrails, all run IDs, validation access and keep/reject/inconclusive decision. Use train screening, limited validation selection, and a frozen final holdout comparison; repeated validation winner selection is not confirmatory evidence. Promote only meaningful quality improvement with guardrails or demonstrated cost reduction with quality noninferiority. No significant difference is not proof of parity. Verify attribution with a revert/ablation. Never weaken tests, alter denominators, hide losing cases or regenerate baseline measurements to manufacture improvement.

## Execution order and required evidence

1. Reproduce the current repository, capture, oracle, graph, wizard and plan-review tests. Audit every open issue and preserve known failing provider cases.
2. Repair and integrate the selected provider corrections; complete full provider schema/HCL/RPC/config/request/state testing. Do not confuse AST-extracted Schema or helper characterization with full lifecycle validation.
3. Complete authentic effective Atmos/identity/backend observations and protected plan/approval/credential/writer contracts.
4. Implement guarded import/plan/change and reconciliation, with failure injection and durable unknown outcomes.
5. Qualify real supported hosts/platforms and a representative plugin evaluation. Continue broader mapper/collector coverage and complexity/scaling improvements independently.
6. Run separately authorized service experiments and a named nonproduction pilot; finish organization CI, operational ownership and accountable release acceptance.

For each issue reproduce a meaningful failure, repair the underlying path, preserve independent oracles, review the diff and rerun the gates affected by the change. Do not add mirrored tests just to increase counts or weaken preservation to make the provider pass.

## Adversarial closure matrix

- Capture: independently known initial root; exact full nextLink; wrong origin/path/query; missing, denied, failed, looping, duplicated and dangling pages; bounds and freshness; unavailable required references; inconsistent snapshots.
- Preservation: mutated ID, setting, exclusion, filter mode/value, assignment tuple, import address, stable key, source digest, field disposition, destination mapping and required reference; unsupported-value canaries; null/omitted/empty/order distinctions; valid alternative encodings.
- Repository/semantics: import/inheritance cycles, override precedence, logical versus physical selectors, implementation versus instance, dynamic features, changed runtime backend/workspace, conflicting provenance and unobserved ownership; limits against multiplicative graph work.
- Wizard: changed cohort/stack, stale receipt hashes, saved-frontier and prerequisite failures, partial generation, ownership metadata corruption, conflicts, back/edit/save/resume, interruption and atomic output writes. Receipt presence alone must not advance progress.
- Runner/approval: replay, expiry, wrong principal/cloud/backend, modified plan/tool/config/state, lock owner replacement, distributed lease loss, policy success/assignment failure, lost responses, readback failure, partial state/history and undurable receipts; fixed argv and secret/environment isolation.
- Provider: numeric ID preservation, discriminators, unknown subtype, zero-filter default versus explicit configuration, full settings and assignment paging, constructor/writer/state differences, native RPC/import/ordinary/refresh-only no-change, failed service steps.
- Host/shell: real registration/discovery/install/use/uninstall, Windows paths/PowerShell quoting, POSIX arguments, permissions, native exit codes, cancellation, slow/broken pipes, bounded logs and input, session corruption and unsupported features.
- Evaluator/release: zero/skipped tests, malformed receipts, wrong binaries/dependencies, stale source hashes, changed workloads, missing observations, privilege-free local versus genuine tenant claims, unsafe archives, wheel tampering, hidden grader leakage and misleading completion counts.

No finite corpus proves every edge case. Use bounded fuzzing, state-machine exploration, property and independent mutation tests where they address a named invariant. Keep minimizable reproductions and seeds.

## Reproduction and performance

Use a separately approved Python environment with requirements-validation.txt. Output receipts outside the repository. Do not install tools, execute repository hooks or call cloud services implicitly.

```sh
<validation-python> tools/verify-materials.py --output <external-output>/materials
<validation-python> scripts/verify-plugin.py --include-core --output <external-output>/reference
<validation-python> -m unittest discover -s research/verification-repair/tests -p 'test_*.py' -v
<validation-python> scripts/intune-iac.py doctor
```

Read labs/atmos-adoption/, labs/provider-contract/ and labs/state-locking/ help and prerequisites before their real native-tool experiments. They are bounded local evidence, not an Intune remote service. Keep OpenTofu/Atmos versions pinned and preserve tool, fixture, state and plan receipts.

Preserve the requested limits: invocation-to-main <=10 ms; usable prompt <=15 ms; first useful result P99 <=25 ms; interactive completion P99 <=50 ms; idle <=35 MB and peak <=50 MB; no hot-path heap allocations; bounded workers/buffers/dependencies; and >=350 MB/s where the declared workflow includes the exact PTY ingestion workload. Physical input/paint targets (4 ms/8.33 ms) require real terminal/host instrumentation. Specify applicability and unresolved conflicts explicitly; do not silently waive them or certify the current Python product as compliant.

Benchmark actual cold CLI startup, first useful inspection result, interactive response, representative estate size, memory, cancellation and output throughput under declared supported workloads. Keep raw samples, exact bytes and consumer completion; warmed hyperfine runs are not cold-cache proof, sample max is not population P99, and OS pipe receipts are not physical display timestamps. Do not import the separate chat terminal's performance numbers as plugin measurements. Keep user-requested limits visible and explicitly resolve any language/runtime or physical-endpoint feasibility conflict before acceptance.

## Deliverables and definition of done

Provide actual source fixes; issue/evidence ledger; prioritized plan; support denominator; independent review; provider/context/approval/recovery results; current dependency and reproducibility receipts; real host compatibility; calibrated behavioral evaluation; operational deployment/incident/rollback runbooks; and one verified handoff package.

Enterprise acceptance requires a named supported estate/exporter/provider/engine/Atmos/backend/host combination, authentic target and writer, preserved existing policy/settings/targeting, reviewed exact plan, protected authorized effects, independent readback, recoverable partial/unknown outcomes, platform qualification, operations ownership and an authorized pilot. Passing local labs or high test counts does not close those gates.

Do not stop actionable work because tenant access blocks a specific experiment. Separate locally implementable work from dependencies requiring credentials, native hosts, evaluation budget, permitted security review or organizational acceptance. Report PASS, FAIL, INCONCLUSIVE, BLOCKED and NOT_RUN honestly. Do not silently narrow the requested estate or provide a percentage complete unsupported by an explicit denominator.
