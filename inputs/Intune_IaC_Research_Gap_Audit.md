# Intune IaC handoff: research gap audit

Audited September 30, 2026. Scope: the attached `Intune_IaC_Builder_Handoff(1).zip`, its two briefs, and its two completed reports. This is a static research and implementation-readiness audit, with selected primary-source checks. It is not an evaluation of a working Intune plugin.

## Decision

The handoff provides a useful product direction: a conversational agent coordinates a deterministic local builder, preserves existing Intune identity and targeting, generates ordinary OpenTofu/Atmos repository artifacts, and keeps adoption separate from intentional configuration changes.

**It does not yet satisfy Appendix A's implementation-dossier completion standard.** The remaining problem is concrete material and evidence, rather than another architecture discussion. A builder could start designing from this bundle, but would have to repeat important source inspection and invent several interfaces before implementing a trustworthy first slice.

Proceed with a focused dossier-completion pass. Prioritize a complete Settings Catalog adoption reference path, then the host/evaluation contracts and the remaining Azure/diagnostic materials. Keep the broader required capabilities in a staged coverage matrix. Inventorying every training lab should not delay the local adoption prototype, but remains an outstanding promised deliverable.

## What was checked

All four numbered documents were read and compared. The ZIP has six files: the four documents, README, and SHA256SUMS. All five listed checksums passed. The archive contains no separate schemas, helper source, HCL projects, plugin manifests, executable tests, or machine-readable implementation ledgers. Embedded examples were assessed separately; their presence is partial design evidence, not zero progress.

For references below:

- **D1** = `01_V3_Research_Brief.md`.
- **D2** = `02_V3_Completed_Report.md`.
- **D3** = `03_Appendix_A_Research_Brief.md`.
- **D4** = `04_Appendix_A_Completed_Report.md`.

Plugin Eval's local router and static analyzer were run against the extracted folder. Both classified it as `directory`, rather than `plugin` or `skill`. The analysis performed generic budget/coverage checks only. Its token count was an **estimated-static** 56,852 tokens for the whole research folder; observed usage was null. Its automatic 86/B score is **not a research-quality, plugin-quality, behavioral, or readiness score**. No calibrated local skill/plugin baseline samples were available. There is no reason to shorten research just to improve that generic score.

The applicable use of Plugin Eval here is to identify what future structural and behavioral evaluation needs. No benchmark initialization or model benchmark was run on the research documents.

## Prioritized gap register

P0 means the gap prevents a reproducible, defensible first adoption reference path. P1 means it prevents the specified developer experience, packaging, or broader required coverage. P2 means it can follow the first prototype while remaining outstanding. These priorities describe missing materials; they are not incident severities or accusations that an unbuilt product has failed.

| ID | Priority | Gap and evidence | Exact question to resolve | Required evidence/output |
|---|---|---|---|---|
| G01 | P0 | The promised implementation dossier was replaced by instructions for the builder to create it. D3 §§2, 16–17 require populated materials; D4 “Required dossier files” lists future paths. | Which requirements are satisfied by supplied files, which have only illustrative prose, and which have no usable material? | Populated gap register and traceability table; each row links requirement, contract, source, artifact, assertion, and assurance status. |
| G02 | P0 | Settings Catalog is recommended, but the policy/settings/assignment lifecycle is not mapped to a qualified resource implementation. D4's adoption map uses placeholder provider/import identifiers, and its capability example says import and assignment still need verification. | For a pinned candidate, exactly how are policy, nested settings, and assignments read, represented, imported, refreshed, and changed without replacing the policy or losing existing targeting? | Provider/API matrix; importer and lifecycle source references; complete HCL/import recipe; assignment-set semantics; request/read-back fixtures; separate live qualification plan. |
| G03 | P0 | The intake model has a global pagination flag and empty observed objects. No concrete exporter format, acquisition closure, or per-relationship completeness rules are delivered. D3 §7 asks for these explicitly. | What files and requests constitute a complete snapshot for the supported policy, its settings, and its targeting relationships, and how do partial exports remain partial? | Versioned export contract, supported exporter adapter specification, per-object/per-collection coverage, complete and partial synthetic inputs, explicit unavailable/access-denied cases. |
| G04 | P0 | The canonical model is a sample object, not a JSON Schema or normalization algorithm. D4 lists eight schema filenames but supplies none as validating schemas. | How does every nested source field retain lineage and a disposition, including absent/null/empty values, polymorphic settings, ordering, defaults, and unknown fields? | Real schemas, meaningful conforming/rejected examples, JSON Pointer or equivalent lineage rules, mapping table, deterministic normalization and comparison rules. |
| G05 | P0 | A generated project tree and test names are supplied, but no complete input-to-output golden project or executable assertion set. D3 §§11, 14 require complete contents. | Can another engineer reproduce the supported fixture's expected IaC, ownership/import map, relationships, and diff without guessing file contents? | Complete supported and partial fixtures; expected normalized records and HCL/YAML; success/failure plan examples; deterministic assertions and their expected results. |
| G06 | P1 | The illustrative wizard graph is open, and resume/local-write rules are incomplete. Seven referenced states have no definition. | What are every branch, precondition, error, cancellation, invalidation, and local-file ownership rule, including changed user files and interrupted generation? | Closed state machine, question definitions, session schema, transition tests, staged-write/conflict/idempotence specification, three complete synthetic transcripts. |
| G07 | P1 | The helper language, distribution, platform floor, subprocess contract, and shell semantics remain undecided. Two harmless command examples do not prove renderers. | What implementation and minimum Windows/Linux environments support equivalent argument values, cancellation, exit semantics, and emit-only behavior? | Bounded runtime choice, CLI/exit/output contract, PowerShell/Bash command-card schemas, adversarial argv fixtures, non-TTY/EOF/PTY specifications. |
| G08 | P1 | Atmos introspection, Azure identity/backend, and CI integration are described as boundaries or recipe names. There is no complete supporting Azure workflow, effective-target record, or permission matrix. | How does the tool integrate into an existing Atmos repository and Azure delivery path without misidentifying engine, state, identity, effective configuration, or executable hooks? | Minimal complete Atmos project and existing-repo adaptation; inspection effect table; Azure/CI reference recipe; target/approval binding; operation-specific permission and negative-test specifications. |
| G09 | P1 | Provenance is incomplete at code-unit level. D2 has several useful commit pins but 12 unresolved exported citations; D4's illustrative source lock has null/placeholder pins and a largely repository-level reuse table. | Which exact files/functions/tests are being reused, under which terms, with what dependencies, transformations, and reproducible acquisition steps? | Populated source lock, code catalogue, file-level reuse/licensing ledger, dependency closure, citation repair ledger, notices, acquired-byte hashes where actually computed. |
| G10 | P1 | Host packaging and evaluation contracts are deferred. There are no manifests, harness configs, protected graders, or result adapters. D4 also characterizes Plugin Eval broadly as host-specific behavioral evaluation. | Which installed harness validates which package format and measures which outcomes, and how are static checks, host interaction, token measurement, behavioral comparison, and live evidence kept distinct? | Host/version/schema matrix; minimal valid manifests; harness/version pins; native configuration examples; original cases with outcome graders; four-arm comparison plan; result/status/usage contracts. |
| G11 | P1 | The mandatory Azure and diagnostic slices and app/script coverage are underdeveloped. D3 §11 requires three complete journeys; D4 provides one partial policy journey and evidence-stage lists. | What complete materials implement the Azure-support and offline-diagnostics journeys, and what is the explicit disposition of other required Intune families? | One Azure integration fixture, one diagnostic evidence bundle and expected analysis, concrete evidence/freshness/denominator schema, app/script generation-review contracts, family coverage/release matrix. |
| G12 | P2 for prototype; P1 for full promised dossier | Both reports acknowledge the missing per-lab catalogue. D4's replay discussion cites the Linux curriculum README rather than a pinned Terraform runner implementation. | What is the actual Terraform catalogue and verified learner/grader lifecycle at the selected revision, with replay, prerequisites, side effects, and OpenTofu adaptations accounted for? | Per-lab catalogue manifest, matching runner contract, original holdouts, grader-sensitivity specifications, protected assessment layout; actual executions remain separately labeled. |

## Concrete defects and weak evidence that deserve special attention

### The wizard example cannot be treated as an executable specification

Parsing D4's “State machine” YAML found 14 defined states and these seven referenced but undefined targets:

`blocked_with_offline_alternative`, `handoff_only`, `mapping_gap_decision`, `ownership_conflict`, `ownership_question`, `repair_generated`, and `review_existing`.

The question/state identifiers also need alignment: for example the state branch `existing_iac_only` differs from the question choice `existing_iac`. The two adoption and interaction state machines have no specified joining contract. These are defects in an illustrative specification, not observed runtime bugs.

A completed contract must also say what happens when two sessions generate the same files, a user edits generated files, writes are interrupted, a source digest changes, or an operation times out ambiguously. “Resume requires matching digests” is a useful start but does not define selective invalidation or recovery.

### A Graph relationship example does not prove Intune assignment lifecycle support

Microsoft's policy resource reference separates `settings` and `assignments` from policy properties and lists an `assign` action [S1]. The nested settings resource is itself polymorphic [S2]. The research's general `$ref` discussion concerns group relationships. It supplies no evidence that the selected mechanism has the same lifecycle, import, ownership, or collection-update semantics for Intune policy assignments.

The next researcher must resolve the actual assignment mechanism and whether it replaces the set, merges, or follows another behavior. It must also distinguish managing assignment references from owning Entra groups, filters, scope tags, or their memberships. Existing externally managed groups should not become resources owned by this project merely because a policy references them.

Microsoft's provider quickstart still labels `msgraph` preview [S3]. A generic provider is a plausible candidate, but first-slice feasibility remains unproved by the materials supplied. Compare the candidate with the actual approved provider when known, or a tightly bounded alternative when lifecycle evidence warrants it.

### Historical import defects must be followed through their fix and release

Issue #91 describes unwanted replacement when importing a group member. It is now closed through PR #148. The v0.5.0 changelog includes the related fix, and the PR describes an acceptance check expecting an update rather than replacement [S4–S6]. That supports the report's concern about qualification; it does not establish a currently broken importer or a successful Settings Catalog no-op adoption.

The dossier should distinguish an update that only reconciles provider state from an API write that changes remote configuration. A simple count of `update` actions is insufficient to establish that distinction. Inspect the pinned implementation, classify the effect, and retain the post-import evidence requirement.

### Partial generation needs an execution-blocking contract

The recommendation to preserve an unsupported field in a sidecar is useful. It does not establish that applying the generated supported portion is safe. The missing field could affect an API update or replacement of a collection. The partial fixture must demonstrate preserved evidence, useful supported output, and a blocked executable adoption/change path until its behavioral gap is resolved. Do not use broad `ignore_changes` to convert uncertainty into a passing result.

### Host support and analyzer support differ

OpenAI's current packaging documentation accepts a root portable `plugin.json`, with an optional `.codex-plugin/plugin.json` fallback. It also specifies precedence for inline OpenAI settings [S7]. The installed Plugin Eval resolver inspected here recognizes the `.codex-plugin/plugin.json` layout or a `SKILL.md`; a root portable manifest alone is not recognized as a plugin by that resolver.

The research must qualify this mismatch explicitly. A host-valid package classified as a generic directory has not received plugin structural validation. Choose a justified compatibility layout or adapt validation; do not change the product's packaging silently just to get a score.

### Evaluation tooling needs version and code verification

The installed Plugin Eval bundle is under plugin distribution 0.1.2, while its package metadata reports 0.1.0. Its current benchmark code requires schemaVersion 2 and `runner.type: codex-cli`; it rejects legacy Responses-style configs and launches actual `codex exec` sessions. Its broader technical-design reference contains older Responses-oriented descriptions. The matching benchmark reference and implementation are therefore necessary evidence, not just the product name.

Anthropic's `claude plugin eval` is a separate harness with its own case and grader formats. Its documentation distinguishes structural validation from behavioral evaluation and documents native Windows limitations for shell-granting suites [S8]. Three repetitions are a starting measurement plan, not proof of rare-failure reliability. Specify protected graders, independent observed artifacts and effects, positive useful-action checks, denominators, and critical-failure gates.

## Specific research questions to send next

1. Which pinned resource implementation supports importing an existing Settings Catalog policy together with its nested settings and preserving all its assignments, exclusions, and filter modes? Supply the exact import IDs, lifecycle code paths, HCL, and request/read-back cases.
2. What is the smallest complete export contract for that path? Show every required policy/settings/assignment retrieval and how a missing page, missing relationship, or denied request is represented without implying deletion.
3. What are the exact source-field accounting and normalization rules? Supply real schemas and supported/unsupported fixtures with expected output, including absent/null/empty and nested `@odata.type` cases.
4. Can the supported fixture generate a complete OpenTofu/Atmos repository and a reproducible import proposal? Show every file and assertion; separate synthetic expected plans from observed provider runs.
5. What closes the seven undefined wizard branches, and which artifacts/decisions invalidate on back/edit/resume, changed source, changed lockfile, or changed user files?
6. What language/runtime and shell contracts make native Windows generation and Bash/CI emission predictable? Supply quoting/argv, exit-code, cancellation, EOF, and emit-only tests.
7. Which exact upstream functions, tests, schemas, and references should be reused, with immutable revisions, file-level terms, dependencies, and adaptation instructions?
8. What minimal complete Azure/CI integration and offline diagnostic journey meet the other mandatory slices without requiring tenant access during dossier preparation?
9. Which exact host manifests and harness configurations apply to Codex/Claude and the installed Plugin Eval? How will outcome graders, four comparison arms, tokens, and forbidden effects be observed independently?
10. What remains of the Terraform lab inventory and learner/replay separation after inspecting the pinned Terraform catalogue and runner rather than borrowing Linux documentation?

## Questions only the developer or organization can answer

These are optional inputs for tailoring the dossier; their absence should lead to explicit synthetic assumptions, not stop public-source research.

| Input | Specific question | Safe fallback until answered |
|---|---|---|
| Provider and tools | Which provider source/version and OpenTofu/Atmos pins does the existing repository use? A sanitized lock/config excerpt is sufficient. | Evaluate a pinned reference candidate without claiming organizational approval. |
| Export | Which export tool/format is available, and does it include settings, assignments, exclusions, and filters? | Use a clearly versioned synthetic Graph-shaped bundle and specify adapters. |
| First real family | Should the first production adaptation cover Windows Settings Catalog, or another configuration family already represented in the repository? | Start with Windows Settings Catalog as the research's proposed reference slice. |
| Host/platform floor | Is the intended first host Claude Code, Codex CLI/app, or both, and is PowerShell 7 allowed? | Document both hosts; keep native Windows helper tests separate from WSL-specific evaluation. |
| Existing delivery/evidence | Which CI, backend, writer conventions, and sanctioned evidence sources already exist? | Provide parameterized examples and leave environment-specific values unresolved. |

No tokens, client secrets, raw production exports, private state, or credentials are needed to answer these questions.

## What should be retained

Retain the hybrid architecture, OpenTofu/Atmos delivery path, explicit ownership and ID map, adoption/change separation, local emit-only mode, unsupported-field visibility, task-based skill loading, and evidence stages that distinguish API acceptance from endpoint results. Their value does not depend on claiming the reports have supplied the missing implementation pack.

No further broad ecosystem ranking is needed to act on this audit. Narrow public-source questions should be resolved; original contracts and fixtures should be authored; organizational values should remain input parameters; provider/host/behavioral runs should be separate, clearly recorded qualification tasks.

## Sources and limits

Primary pages checked September 30, 2026:

- **S1** [Microsoft Graph beta: deviceManagementConfigurationPolicy](https://learn.microsoft.com/en-us/graph/api/resources/intune-deviceconfigv2-devicemanagementconfigurationpolicy?view=graph-rest-beta) — properties, relationships, and listed actions.
- **S2** [Microsoft Graph beta: deviceManagementConfigurationSetting](https://learn.microsoft.com/en-us/graph/api/resources/intune-deviceconfigv2-devicemanagementconfigurationsetting?view=graph-rest-beta) — setting instance and definition relationship.
- **S3** [Microsoft Graph Terraform quickstart](https://learn.microsoft.com/en-us/graph/templates/terraform/quickstart-create-terraform) — provider preview label.
- **S4** [Microsoft msgraph changelog](https://github.com/microsoft/terraform-provider-msgraph/blob/main/CHANGELOG.md) — release notes, including v0.5.0. This is a moving branch, not an acquisition lock.
- **S5** [Microsoft msgraph issue #91](https://github.com/microsoft/terraform-provider-msgraph/issues/91) — original group-member import report and closed status.
- **S6** [Microsoft msgraph PR #148](https://github.com/microsoft/terraform-provider-msgraph/pull/148) — merged fix and described import test.
- **S7** [OpenAI plugin packaging](https://developers.openai.com/plugins/build/plugins) — portable and compatibility manifest layouts and precedence.
- **S8** [Claude Code plugin eval documentation](https://code.claude.com/docs/en/plugin-evals) — evaluation and platform contracts.

Local Plugin Eval evidence: package.json; `src/core/target.js`; `src/core/analyze.js`; `src/core/benchmark.js`; `references/technical-design.md`; and `references/benchmark-harness.md` in the installed plugin bundle. The router and analyzer were executed, but no behavioral harness was run.

Some attempts to retrieve the Graph `assign` page, provider implementation pages, and a pinned Terraform `conftest.py` were unsuccessful. Failure to fetch is not evidence those APIs/files are absent or broken. Assignment lifecycle and replay verification remain named research tasks. This audit did not acquire provider source archives, verify every upstream commit/license, run live APIs, import state, run provider-backed plans, collect endpoint evidence, or install a plugin. The accompanying prompt asks for those missing research materials while preserving the distinction between preparation and separately authorized execution.
