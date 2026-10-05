# Deep Research Appendix B: complete the Intune IaC implementation materials

Use this prompt with the original `Intune_IaC_Builder_Handoff(1).zip` and the accompanying `Intune_IaC_Research_Gap_Audit.md`.

## Mission

Complete the specific research and reference-material gaps that prevent a computer-access builder from implementing the brownfield Intune-to-IaC wizard without another discovery pass. Deliver populated contracts, pinned source selections, complete synthetic examples, and executable or implementation-precise test specifications. Preserve the approved product direction. Research technical feasibility and supply evidence; do not turn a recommendation, illustrative tree, or test title into proof of implementation.

The product is an interactive engineering builder inside Claude Code/Codex. A deterministic local helper inspects an existing repository and Intune export, asks only meaningful missing questions, preserves object IDs and targeting, generates maintainable OpenTofu/Atmos artifacts and PowerShell/Bash command cards, and supports back/edit/cancel/resume. Adoption attaches code/state to existing configuration without intentional functional change; proposed functional changes follow separately. Existing protected CI remains the execution path.

Read the four documents in the attached ZIP and the audit. The later Appendix A brief governs the clarified developer experience. The completed reports supply useful decisions and partial examples; their future file trees are not delivered artifacts. Use the audit's G01–G12 IDs in the new traceability records.

This assignment authorizes public-source inspection, local dossier creation, synthetic fixtures, and inspected non-mutating/offline validation. It does not authorize tenant login/export, provider-backed plans, live state imports, cloud or endpoint mutation, endpoint collection, plugin installation, paid agent benchmarks, or training-lab execution. Record proposed commands separately from executions. Missing live access must not prevent complete offline materials.

## Deliverable and completion rule

Produce `build-materials-gap-closure/` with a usable `BUILD-START-HERE.md`. Supply an actual checked ZIP when file creation is available. Otherwise provide complete labeled text artifacts plus a precise acquisition map; do not claim a ZIP exists.

Close the trace for each required first-slice capability:

**requirement → decision/stage → pinned source or original contract → generated artifact → concrete fixture/assertion → actual assurance status.**

Track separate fields for acquisition, review, authored content, static validation, fixture tests, host tests, behavioral evaluation, and live qualification. A test plan is not a test result. A synthetic plan is not a provider-generated plan. A locally calculated digest is not a Git commit or blob ID. Unknown organizational values stay explicit; public-source questions must get bounded answers or exact retrieval blockers.

Finish the first Settings Catalog reference path before broadening it. Retain a coverage/disposition row for all required Azure, Entra, Intune, diagnostics, and evaluation capabilities. Do not mark the broader scope complete merely because one policy fixture is complete. Keep the full lab inventory as a separate workstream so it does not hold up the deterministic adoption path.

## Work package 1 — resolve the actual provider and assignment path

Addresses G02, G05, G08.

Answer: **Which pinned resource implementation can represent and import an existing Windows Settings Catalog policy, preserve its nested settings and existing assignment set, and expose unintended change?**

Start with the existing approved provider when non-secret repository context is supplied. Otherwise evaluate `microsoft/terraform-provider-msgraph` as the report's reference candidate. Compare a narrowly selected typed Intune provider or governed adapter only if it closes a documented lifecycle gap. Public availability is not enterprise approval. Make one justified first-slice recommendation, with version-specific limits.

For policy, settings, assignments, exclusions, assignment filters, and scope metadata, obtain:

- Provider publisher/source, release, immutable commit, resource type, schema, importer, create/read/update/delete implementation, relevant tests, known issues, and minimum supported engine/API versions.
- Actual Graph method/path/version and request/response shapes. Distinguish the policy's properties, settings navigation collection, assignment collection, and assign action. An Entra group `$ref` example does not prove Intune assignment support.
- Exact import identifier syntax for the selected resource shape; ownership boundaries for policy and assignments; treatment of referenced groups, filters, and scope tags that remain externally managed.
- Whether assignment updates replace the whole set, merge, or behave otherwise. Specify include/exclude/filter-mode preservation, ordering, duplicate targets, empty sets, drift, external deletion, retries, and ambiguous timeouts.
- Exact read/write permission requirements by principal type and API operation. Distinguish documented permission from observed authorization enforcement.
- TCM/metadata requirements or other provider constraints for the chosen Intune route, including how unavailable schema coverage is represented.

Follow msgraph issue #91 through PR #148, its tests, and the applicable release. Determine whether a post-import update is local state reconciliation or a remote configuration mutation by inspecting the pinned code. Do not assert a persistent defect just from the original issue, or no-change adoption just from its closure.

Deliver `provider-api-coverage.csv`, `recipes/settings-catalog-adoption.md`, `recipes/assignment-preservation.md`, and complete minimal HCL/import examples. Include success, state-only reconciliation, real update, replacement, incomplete mapping, and ownership-conflict cases. If full assignment adoption cannot be supported, say exactly why; preserve existing targeting and supply the governed handoff rather than silently falling back to an opaque provisioner.

## Work package 2 — define intake, field accounting, and complete golden fixtures

Addresses G01, G03, G04, G05.

Answer: **What exactly goes into the tool, what transformations are valid, and what exact files come out?**

Define one versioned synthetic export format based on verified source/API shapes. Identify a concrete exporter/sample adapter and precisely what it includes or omits. Do not invent a universal Intune export format. Trace policy list/get, settings, assignments, and referenced relationship acquisition, including pagination, errors, permissions, capture times, API versions, and provenance. Coverage must be scoped per collection/object/relationship, not just one global boolean. Missing data cannot become an empty desired collection or a deletion.

Supply actual JSON Schemas, not illustrative objects, for export intake, observed inventory, field accounting, adoption map, capability report, operations, command cards, sessions, and evidence. Choose and record the schema dialect. Provide useful conforming and rejecting examples, stable schema IDs/versioning, and rules for schema migration.

Specify normalization and semantic comparison precisely: nested `@odata.type`, setting-definition IDs, lineage/source pointers, containers versus leaves, absent/null/empty values, set versus ordered arrays, service-owned metadata, writable defaults, secrets/local-only data, unknown fields, and read-normalized values. Every source field must be accounted for. Preserve raw/local evidence without exposing sensitive payloads to the model or committing it to a repository.

Provide stable tenant/family/object-ID-based addressing and collision rules; display-name changes must not change managed identity. Keep observed and proposed desired records distinct.

Deliver two complete projects with all file contents:

1. **Supported:** one existing Windows policy with real API-shaped nested settings, multiple assignments, one exclusion, one assignment filter with mode, scope metadata, and an unrelated duplicate-name object. All fields are accounted for, and the expected mapping preserves identity and relationships.
2. **Partial:** the same path with an unsupported polymorphic field or missing relationship page. Preserve the unresolved content, generate useful supported output, and prevent executable adoption/change until the behavior gap is resolved. Sidecar preservation alone is not proof partial HCL is safe to apply.

Each project needs input bundle, expected normalized records, field accounting, adoption/import map, complete HCL and Atmos YAML, expected manifest/diffs, PowerShell/Bash command cards, and expected check results. Label expected plan/API evidence as synthetic unless actually observed. Include at least one deliberately wrong result per important invariant so the grader must reject it. Do not use broad `ignore_changes`, fake state edits, or blanket refusal to satisfy the oracle.

## Work package 3 — close the wizard, file-write, and platform contracts

Addresses G06, G07.

Answer: **How does the developer complete, correct, interrupt, and resume the journey deterministically?**

Choose a practical helper language/runtime and a minimum Windows/Linux support matrix using a bounded comparison of relevant implementations. State dependencies and distribution implications. Native Windows generation must not acquire an unexplained WSL or administrator prerequisite. Choose PowerShell versions explicitly; an example `.exe` is not evidence a binary exists.

Deliver a closed `wizard-state-machine.yaml`, `wizard-questions.yaml`, session schema, CLI/exit-code/stream contract, and transition specifications. Resolve these undefined targets in the existing example: `blocked_with_offline_alternative`, `handoff_only`, `mapping_gap_decision`, `ownership_conflict`, `ownership_question`, `repair_generated`, `review_existing`. Align question-choice IDs with branches and join adoption qualification to the local interaction flow.

Define inspect/search/select/back/edit/explain/cancel/save/resume/export-commands; facts discovered versus questions asked; failure on missing noninteractive inputs; EOF and keyboard interruption; accessible plain output; stdout data versus stderr status; and sanitized control sequences from untrusted names/logs.

Specify stage-selective invalidation for changed source, repository revision/dirty files, engine/Atmos/provider/API versions, tenant/cloud, component/stack, selected IDs/cohort, and reviewed plan. Never replay an import or ambiguous mutation automatically. Resume records contain decisions and provenance, not credentials or persisted approval grants.

Define staging/diff/merge, atomic writes where available, file ownership, user-edited generated files, overwrite conflicts, interrupted writes, backup retention, rerun idempotence, and concurrent sessions. Supply Windows adoption, Bash/CI emit-only, and failure/recovery transcripts marked authored/synthetic unless recorded.

Build command cards from one structured operation. Supply equivalent PowerShell/Bash renderings and argv test vectors for drive paths, spaces, quotes, apostrophes, brackets, dollar signs, Unicode, newlines, leading dashes, and shell metacharacters. Define safe rejection where values cannot be represented. Include working directory, executable resolution, shell version, native exit semantics, output artifacts, and every local/network/state/cloud effect. Emit-only must never execute. No `eval`, `Invoke-Expression`, or interpolated shell execution.

## Work package 4 — supply Atmos and Azure/CI integration materials

Addresses G08, G11.

Answer: **How does the generated component fit the repository and its supporting Azure delivery workflow?**

Inspect pinned Atmos configuration, describe/list resolution, YAML functions, hooks, workflows, and engine selection. Preserve the repository's structure and use Atmos's own effective-resolution semantics. Do not implement a partial YAML merger and call it equivalent. Qualify introspection by requested fields and configuration: network/authentication/hook/secret effects cannot be assumed absent.

Provide a complete minimal project and an existing-repository adaptation example with engine pin, stack/component, input origins, provider aliases, backend/workspace/state key, imports, generated-file origins, and discovered ownership. Add wrong-stack, inherited override, state-key collision, executable/version mismatch, and dangerous-hook cases.

Complete one supporting Azure integration reference journey: reuse an existing backend or introduce a justified dependency, explain bootstrap versus normal operation, wire the relevant CI federation identity, and produce protected plan/import/change and verification artifacts. Supply actual minimal IaC/YAML and synthetic target/identity evidence, not recipe names alone. Keep Git/PR → protected CI → Atmos → OpenTofu. No implicit azd, new release controller, paid service, or broad landing-zone dependency.

Deliver an operation-level authorization matrix covering Azure RBAC, Entra roles, Graph application/delegated permissions, and Intune boundaries. Define issuer/subject/audience and target validation for federation. Supply positive and negative test specifications without claiming unobserved tenant scope enforcement. Protect credentials from untrusted PR code; bind reviewed artifact/revision/configuration/tool versions and target; define concurrency/staleness handling and artifact access/retention.

## Work package 5 — finish provenance, reuse, and acquisition closure

Addresses G09; supports every other work package.

Answer: **What exact existing code or contract should the builder acquire and adapt?**

Keep earlier useful commit pins and determine whether they still match selected releases. Repair the 12 unresolved D2 export citations by inspecting retrievable canonical evidence; if repair is impossible, mark the dependent claim unsupported instead of fabricating a URL. Inspect the mandatory source families from Appendix A only for the capabilities being reused; do not repeat a landscape ranking.

Populate `source-lock.json`, `code-catalog.jsonl`, `reuse-ledger.csv`, a citation-repair ledger, and `THIRD-PARTY-NOTICES.md`. Selected units need immutable commit/path/symbol, exact purpose and destination, input/output contract, side effects, transitive dependencies, platform/runtime, upstream test references, adaptation recipe, acquisition evidence, file-level license/notice, and truthful assurance labels. Separate commit IDs, blob IDs, and computed byte hashes.

Classify reuse-as-is, adapt, reimplement-from-contract, reference-only, or exclude. For small selected units provide permitted complete examples; for large ones supply pinned retrieval and precise transformation instructions. Check referenced schemas, templates, scripts, hooks, executable assumptions, and offline dependencies. No broken relative references, hidden runtime downloads, or unlicensed vendoring. Where no suitable implementation exists, provide an original precise interface/algorithm with fixtures and label its execution status.

## Work package 6 — qualify host packaging and evaluation harnesses

Addresses G10, G05, G07.

Answer: **What exactly can be installed, validated, exercised, and credibly measured on each intended host?**

Pin current Agent Skills, OpenAI/Codex, and Claude packaging specifications, then supply complete minimal valid manifests, relative-path rules, invocation/discovery behavior, installation/removal recipes, and validation commands. Keep runtime, evaluation, and provenance distributions separate. Hidden assessment answers and production data must not enter the runtime or candidate workspace.

Distinguish three tools explicitly: the installed OpenAI-curated `plugin-eval` CLI, Anthropic `claude plugin eval`, and other skill-creator/custom harnesses. Record package/distribution and code versions, actual schemas, required binaries, host/platform limits, sandbox assumptions, subprocess/scaffold effects, and publication defaults. No paid runs or report publication during dossier preparation.

Resolve two concrete mismatches:

- Current OpenAI documentation permits a root portable manifest, while the installed Plugin Eval resolver inspected in the audit detects `.codex-plugin/plugin.json` or `SKILL.md`. What layout or validator adapter gives correct structural coverage?
- The installed Plugin Eval benchmark implementation requires schemaVersion 2 and a Codex CLI runner, while an older design reference discusses a Responses-style harness. Which installed contract is authoritative and how will it be tested without model calls?

Supply current-native example configurations and a host-neutral result adapter. Define four comparison arms: no added skill; strongest selected upstream composition; proposed skills with equivalent tools; proposed skills plus added helper/enforcement. Hold model, task, tools, permissions, context, and budget comparable where possible, and attribute tooling gains separately. Verify that the appropriate skill/plugin was actually available/loaded in each arm. Run Claude and Codex comparisons separately.

Author a bounded first suite, roughly 12–20 original cases, with concrete fixture inputs, observable output/effect assertions, and protected graders. Cover supported adoption, partial export, duplicate names, lost exclusion/filter, ownership conflict, wrong tenant/stack, changed provider pin, stale review, back/cancel/resume, quoting, emit-only, false endpoint success, secret/control-sequence handling, and a simple question that should load little context. Check useful completion as well as unsafe behavior; refusing everything must fail useful-action criteria.

Record attempted/issued/executed forbidden effects independently of the final response. Use deterministic assertions for IDs, files, arguments, actions, and side effects. Reserve model judges for genuinely qualitative reasoning and state judge/version/rubric limitations. Keep graders, golden answers, replay material, and result logs outside candidate write access; specify how grader-sensitivity mutations are checked.

Provide statuses `pass`, `fail`, `not-run`, `blocked`, `unsupported`, `skipped`, and `harness-error`, with denominators. Critical unauthorized mutation, wrong-target execution, secret disclosure, evidence fabrication, and grader tampering cannot be averaged away. Three repetitions can be the initial plan; do not claim rare-failure reliability from that sample. Token estimates, observed usage, latency, list-price estimates, and billed cost must remain distinct.

## Work package 7 — complete diagnostic/evidence and staged family coverage

Addresses G11.

Answer: **How does the plugin investigate a failure and report the deepest outcome actually supported by evidence?**

Provide a complete offline synthetic service/device bundle and diagnostic journey with timeline, competing hypotheses, capture window/timezone/clock assumptions, freshness/completeness/access/truncation information, expected conclusions, and the smallest discriminating next evidence request. Include one app installed-but-detected-failed case or another comparably useful Windows endpoint case. No live collector installation or execution.

Supply an actual evidence schema with object, assignment, cohort, receipt, execution, effective state, and outcome stages. Show success/failure/pending/unknown/stale/conflicting records and explicit eligible/targeted/reporting denominators. Missing events cannot prove nonexecution when completeness is unknown. Promotion thresholds remain organization inputs.

Audit selected PowerStacks/SDK collectors and helpers for local writes, downloads, global installs, elevation, subprocesses, sync/restart/reproduction, and sensitive outputs before proposing adaptation. Keep raw evidence restricted; define model-visible minimization and correlation without claiming regex redaction is a guarantee.

Publish a staged family matrix for Settings Catalog, relevant configuration/compliance/endpoint-security policies, groups/filters, Win32 apps, scripts/remediations, and enrollment/Autopilot where relevant. Each row needs selected source/API/provider, actual material present, limit, qualification need, release stage, and next bounded task. Provide concrete app/script review/generation contracts for artifact hashes, install/detection/context/requirements/exit/reboot/dependencies and outcome verification. Do not claim those families implemented from a row alone.

## Work package 8 — complete the separate Terraform corpus inventory

Addresses G12.

Answer: **What is actually in the pinned Terraform curriculum, and how could a later authorized assessment avoid instructor replay and false passes?**

Enumerate `stephrobert/terraform-dsoxlab-training` at an immutable revision together with its matching `stephrobert/dsoxlab` runner. Do not assume 88 or borrow Linux catalogue statistics/commands. Inspect the Terraform learner/grader and shared helpers directly, including executable names, `LAB_NO_REPLAY`, workspace handling, skips, reference replay, setup/cleanup, runtime services, credentials, and network effects.

Supply `catalog-manifest.json` with real per-lab metadata, requirements, mutable paths, effect class, grader entrypoint, expected invariant, competency, solution/hint exposure, upstream attestation, adaptation, and execution status. Provide protected holdout/grader specifications and legitimate OpenTofu adaptation patches where appropriate, with separate workdirs/state and preserved assertions. Do not decrypt solutions or run labs during this research. Inventory completion and agent performance are different outputs.

## Required pack contents

Consolidate paths where sensible, but populate every required record:

- `BUILD-START-HERE.md`, `INPUTS-AND-DECISIONS.md`, `BUILD-PLAN.md`, `MATERIALS-STATUS.md`.
- `gap-register.json`, `requirements-traceability.csv`, `source-lock.json`, `code-catalog.jsonl`, `reuse-ledger.csv`, citation-repair ledger, notices.
- `contracts/` with real schemas, positive/negative examples, normalization rules, field mappings, and interface definitions.
- `wizard/` with closed states/questions, session/operation contracts, platform table, complete transcripts, and command cards.
- `examples/` with complete supported/partial adoption projects, Azure integration, and offline diagnostics.
- `recipes/` with exact provider/import/assignment, Atmos, Azure/CI identity, and diagnostic paths.
- `evaluations/` with actual native harness examples, cases/fixtures, protected-grader specifications, forbidden-effects observation, result schema, and four-arm plan.
- `provider-api-coverage.csv`, `compatibility.csv`, `family-coverage.csv`, `catalog-manifest.json`, permission matrix, evidence/rollout contract, and `ZIP-ACCEPTANCE.md`.

Every task in `BUILD-PLAN.md` must name inputs/source IDs, target files, interfaces, decisions, dependencies, tests and expected artifacts, unresolved organizational parameters, and qualification boundary. Explain how the finished first-slice pack can be implemented offline without another broad search.

Before handing off, check JSON/YAML/schema consistency, every state reference, required-file/relative-reference closure, complete example contents, hash/provenance truthfulness, and archive paths where supported by inspected local tooling. Report exactly what ran. If a tool or source cannot be accessed, record the exact bounded retrieval/validation step and affected capability; do not silently downgrade the completion criteria.

## Organizational inputs and sensible assumptions

If supplied, use non-secret provider/engine/Atmos pins, exporter format, existing naming/ownership/CI/backend conventions, first real resource family, intended host/PowerShell floor, and sanctioned evidence sources. Otherwise use explicit synthetic values and the proposed Windows Settings Catalog reference slice. Do not request raw production exports, tenant credentials, private state, or client secrets.

## Final response

Lead with the actual deliverable link or complete text artifacts and the first slice's supported limits. Show G01–G12 as closed, partial, or blocked **with file evidence**, and distinguish public research blockers, remaining implementation, organizational facts, and live qualification. Preserve useful architecture decisions without repeating their full justification. No invented benchmark scores, observed no-op claims, provider approvals, host tests, or ZIPs.

The requested outcome is a concrete materials pack from which another LLM can build, test, and package the interactive wizard. The builder must receive exact sources, contracts, inputs, generated files, commands, and assertions rather than another list of things to research.
