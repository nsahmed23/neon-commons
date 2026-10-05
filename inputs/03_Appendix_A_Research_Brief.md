# Deep Research Appendix A
# Build materials for an interactive brownfield Intune-to-IaC engineering wizard

**First-class domains:** existing Microsoft Intune configuration; Terraform/OpenTofu; Atmos; Azure; Microsoft Entra and Graph; PowerShell/Bash; developer-facing terminal interaction.

**Deliverable:** a source-grounded implementation dossier that a separate LLM with computer access can use to build, test, and package the complete plugin(s), terminal workflow, and supporting code into a ZIP.

**Relationship to prior work:** supplement the “Deep Research v3: Build a Senior Microsoft Cloud and Endpoint DevSecOps Engineering Plugin” brief and its completed report. Do not repeat the broad landscape report. Retain its useful decisions, close its implementation-evidence gaps, and incorporate the user's subsequent clarification: the primary product is an interactive technical builder for adopting an existing Intune estate into IaC, not merely a plan reviewer, policy adviser, or safety checklist.

## 1. Mission and fixed product intent

Find and assemble the concrete data, documentation, source files, reusable implementations, schemas, examples, fixtures, test designs, and packaging contracts needed to build this experience:

> A developer opens a terminal in an existing repository, invokes the plugin/wizard, supplies an existing Intune export or selects a separately authorized discovery path, answers a few relevant guiding questions, and receives actual maintainable IaC, import/adoption mappings, Atmos configuration, Azure workflow integration, tests, and clear next commands. The developer can review and edit generated files, run permitted local steps, resume later, or copy correctly rendered PowerShell/Bash commands into an approved environment.

The principal journey is:

**Existing Intune configuration → scoped inventory and ownership → loss-aware normalization → provider/API mapping → generated IaC and Atmos configuration → import/adoption proposal → evidence of no unintended remote configuration change → separately reviewed functional change → approved CI delivery → cloud and endpoint verification.**

OpenTofu is the approved enterprise execution engine. Terraform knowledge is required for source reuse, interoperability, and separately permitted environments, not silent substitution. Preserve Git/PR → protected CI → Atmos → approved OpenTofu/provider or explicitly governed adapter execution. “Azure workflows” includes the supporting Azure infrastructure, identity, permissions, networking, artifacts, and CI integration; it does not automatically mean Azure DevOps, azd, Bicep, Logic Apps, or a new release platform.

Preserve existing Intune object IDs, policy settings, assignments, exclusions, filters, group relationships, and declared ownership. Distinguish policy/application deployment waves from Windows Update rings. Start with the existing repository's provider and conventions when available. A registry listing or public example is not organizational approval.

Deliver technical-builder capability: code, modules, PowerShell/Bash, APIs, tests, CI, and inspectable evidence. Safety controls must enable bounded useful work; a bot that only warns or refuses is not the requested product. Conversely, “wizard” must not become a euphemism for uncontrolled production execution.

## 2. Inputs, authority, and the gap register

Read the v3 brief and completed report in full when available. The report is titled **“Deep Research: Senior Microsoft Cloud and Endpoint DevSecOps Engineering Plugin.”** It recommends composition with a thin original layer and proposes eight focused skills: engineering-context, iac-engineering, atmos-engineering, azure-engineering, entra-graph-authorization, intune-engineering, endpoint-diagnostics, and delivery-security. Treat those as a starting topology, not a mandatory package count.

The report explicitly did not deliver a complete per-lab catalogue manifest, an installable ZIP, or an executed Claude/Codex behavioral comparison. It also contains illustrative manifests, helper interfaces, and source references that need implementation-grade verification. Do not promote a proposed file tree or a confidence label into proof of working software.

Create `gap-register.json` and `requirements-traceability.csv` first. Reconcile the report with the clarified brownfield wizard goal. For each requirement record the missing material, exact research question, planned source, proposed output path, dependent implementation task, acceptance test, and blocker class.

Separate four kinds of blockers: public-source research gaps; implementation gaps; environment-specific facts that only the developer/organization can supply; and live qualification that requires separate authorization. Do not make missing production credentials a blocker to authoring and testing offline code. Do not invent an existing private repository, provider version, export format, tenant, role assignment, or approval.

The later user clarification governs product priorities. Preserve approved architecture and safety boundaries. Reopen other report decisions only when new evidence requires a narrowly documented change. A report's citation token, blob identifier, or proposed URL is a discovery clue until resolved to retrievable evidence.

## 3. The research/build boundary

This assignment is research and local dossier preparation, not authorization to install plugins, authenticate to Azure/Graph, export tenant data, import live objects into state, run provider-backed plans, collect endpoint data, deploy infrastructure, or execute the dsoxlab catalogue.

Read public repositories and documentation. Assemble licensed material and original synthetic fixtures. Use inspected non-mutating validation within available permissions. Record proposed commands separately from commands actually executed. Never run a README installation command, test fixture, plugin hook, or collector just to discover what it does.

Keep organizational data in approved environments. Do not send tenant exports or proprietary configuration to third-party comparison services, documentation tools, or external models without explicit approval. Prefer synthetic data for research and distributable fixtures. An offline parser may process a sensitive export locally without exposing the raw payload to the LLM.

For the future product, distinguish preview/emit-only, authorized local generation, provider/network reads, state mutation/import, and real cloud/device mutation. Future lab execution must have an explicit disposable-resource contract. High-impact production actions remain owned by approved human/protected-CI controls. A resumed session or answered menu question is not a new grant of permission.

## 4. Research the terminal experience as a first-class implementation

Evaluate three approaches: a conversational wizard inside Claude Code/Codex using their existing terminal and approval tools; a small deterministic CLI/TUI helper coordinated by the plugin; and selective use of existing Atmos interactive facilities. Recommend the smallest approach that meets the actual user experience and testability requirements. Do not automatically build a new LLM client, require a second API subscription, introduce a web dashboard, or fork Atmos.

The experience must have a real terminal path. A terminal menu for launching plan/apply commands alone does not satisfy guided brownfield adoption. Conversely, an elaborate full-screen TUI is not required when a clear conversational terminal workflow plus small helpers works better.

Collect exact host capabilities, terminal libraries or existing code, versions, licensing, tests, and integration limits before choosing. Examine native Windows PowerShell, PowerShell 7, Linux Bash, and WSL separately. State the minimum supported environments and where behavior has only been documented. Do not claim Bash code runs natively in PowerShell or make WSL an unexplained prerequisite.

### Required interaction contract

The wizard discovers facts before asking questions. It should show what it found, cite the local source of each consequential fact, ask one meaningful decision or a short coherent group, explain why the answer matters, and recommend a safe default with a brief reason. Developers can request more detail without being forced through a tutorial.

Provide branching questions about input source, target tenant/environment, selected resource family, existing writer/provider, scope, naming/module conventions, Atmos component/stack, supported mapping, and adoption versus functional change. Do not ask again when a fact has already been supplied and remains valid. Do not require the developer to know every Graph route, resource type, or import identifier.

Support inspect, search/select, back, edit, explain, skip-with-consequence, cancel, resume, and export-commands. Show a useful progress summary and a final list of generated files, diffs, checks, unresolved gaps, and next steps. There must be a plain-text/non-TTY fallback, accessible keyboard behavior, machine-readable output, and an unattended mode that fails clearly on missing required inputs rather than waiting indefinitely.

Resume records contain validated decisions and provenance, not secrets or authentication tokens. Define invalidation when the export, repository revision, provider/API/engine version, tenant, target cohort, or plan changes. Resuming must not replay an import, retry an ambiguous mutation, or reuse stale authorization automatically.

Create `wizard-state-machine.yaml`, `wizard-questions.yaml`, a session-state schema, and at least three complete target-experience transcripts: Windows PowerShell brownfield adoption; Bash/CI or emit-only use; and a failure/recovery flow. Label transcripts as designed/synthetic unless recorded from an actual run. Include precise stage transitions, side effects, preconditions, resume behavior, and artifacts, not just screen mockups.

## 5. Find the best applicable working code, not just more skills

**The central output is a curated implementation reference pack.** Inspect actual implementations and their tests, not only README claims, skill descriptions, repository counts, or stars. For every required build capability, locate the strongest applicable implementation, explain why it fits, and show exactly what to reuse, adapt, or avoid. “All the best code” means complete coverage of required capabilities with high-value selections, not copying every repository into the deliverable.

### Mandatory source families

| Source | Material to extract or qualify |
|---|---|
| `cloudposse/atmos` | Relevant skill files, actual TUI/selection code, target/configuration resolution, generation helpers, YAML parsing, workflows, command construction, streaming output/exit handling, and corresponding tests. |
| `hashicorp/agent-skills` | HCL/module, refactor, test, import/search, policy, Azure module and provider guidance; current manifests and validation; selectively chosen concrete examples. |
| `antonbabenko/terraform-skill` and `LukasNiessen/terrashark` | Useful cross-engine, failure-mode, migration, state, test, and CI implementations/references; verify overlap and promotional claims. |
| `microsoft/azure-skills` | Applicable Azure knowledge, real recipes, diagnostic/validation code, schemas, tests, and host packaging; separate service expertise from azd orchestration and live MCP adoption. |
| `powerstacks-corp/intune-advanced-troubleshooting` | Actual PowerShell collectors/helpers and evidence conventions; inspect local writes, installation, elevation, logging coverage, and tests before adaptation. |
| `TheLobbi/Claude-m` | Relevant Intune, Entra, Azure, security, monitoring and CI files; distinguish working code from knowledge-only commands and unimplemented routes. |
| `stephrobert/terraform-dsoxlab-training` and `stephrobert/dsoxlab` | Complete catalogue metadata, fixtures, grader and learner-mode code, runner contract, mutation tests, and attestation evidence; do not copy hidden solutions into runtime skills. |
| `obra/superpowers` and applicable Plugin Eval implementation | Planning/debugging/verification/skill-evaluation methods, actual harness/schema/interfaces, reusable tests, and permissions; avoid duplicating the whole framework. |
| Official provider and SDK sources | The approved existing provider when supplied; otherwise qualify AzureRM, AzAPI, Entra-oriented and Graph/Intune-oriented candidates without claiming approval. Inspect resource implementations, importers, schemas, acceptance tests, examples and release notes. |
| `microsoft/mggraph-intune-samples` and `microsoftgraph/msgraph-sdk-powershell` | Existing Intune discovery/export/assignment examples, SDK request/pagination/error behavior, and tests; independently derive minimum permissions and remove installation/authentication assumptions. |

Use these exact entrypoints, then discover canonical current paths and revisions:

```text
https://github.com/cloudposse/atmos/tree/main/agent-skills/skills
https://github.com/hashicorp/agent-skills
https://github.com/antonbabenko/terraform-skill
https://github.com/LukasNiessen/terrashark
https://github.com/microsoft/azure-skills
https://github.com/powerstacks-corp/intune-advanced-troubleshooting
https://github.com/TheLobbi/Claude-m
https://github.com/stephrobert/terraform-dsoxlab-training
https://github.com/stephrobert/dsoxlab
https://github.com/obra/superpowers
https://github.com/obra/superpowers-marketplace
https://github.com/microsoft/mggraph-intune-samples
https://github.com/microsoftgraph/msgraph-sdk-powershell
```

Carry forward a disposition for all 15 entries from the original article: terraform-style-guide, terraform-refactor-module, terraform-test, terrashark, Anton Babenko terraform-skill, terraform-stacks, owasp-security, varlock-claude-skill, security-auditor, devops-engineer, developer-kit-devops, create-pr/git workflow, monorepo-management, cc-devops-skills, and systematic-debugging. Resolve actual authors and files. Use the original aggregator repositories only as discovery aids. Do not import irrelevant packs merely to fill a list.

Search beyond these sources only to close a named implementation gap—for example terminal question handling, Intune export normalization, or a provider importer. Give the builder a justified choice rather than an unranked list of alternative frameworks. For terminal libraries, examine original repositories and runnable examples; choose based on the selected implementation language, Windows support, cancellation, accessibility, non-TTY use, testing, and dependency burden.

Starting observation to verify: Atmos documentation describes an interactive CLI, and prior inspection located `internal/tui/atmos/tui.go`, `pkg/terraform/ui/model.go`, and `pkg/ui/spinner/spinner.go`. A PRD mentioning a feature is not proof the feature ships; follow it into implementation, tests, and a release.

Starting observation to verify: Microsoft's legacy `microsoftgraph/powershell-intune-samples` material is marked deprecated, with newer SDK-based examples elsewhere. Avoid reintroducing retired authentication patterns. Newer samples are still examples, not automatic least-privilege or production guarantees.

## 6. Code provenance, dependency closure, and reuse decisions

Produce `source-lock.json`, `code-catalog.jsonl`, and `reuse-ledger.csv`. Each selected code unit needs:

**Source ID; canonical repository; immutable commit SHA; file path; blob SHA when available; symbol/function or line range; applicable release; local material path; retrieval date; byte hash when actually downloaded; license/notice files; provenance; intended destination; purpose; dependencies; platform/runtime requirements; input/output contract; side effects; upstream tests; test evidence; security gaps; exact adaptation; and exclusion rationale for rejected alternatives.**

Distinguish a commit SHA, a file blob SHA, and a locally computed SHA-256. Never fill one field with another or invent a digest for content that was not acquired. Use explicit unavailable/null states with reasons. Git branches and tags alone are not immutable acquisition locks.

Trace every selected unit's transitive code, schema, template, reference and configuration dependencies. Detect references that escape the proposed package, hidden executable assumptions, hooks, submodules, LFS content, generated files, credentials, and unpinned runtime downloads. A copied `SKILL.md` with broken relative references is not a usable dependency.

For each unit classify `reuse-as-is`, `adapt`, `reimplement-from-contract`, `reference-only`, or `exclude`. Include a concrete adaptation recipe or small patch where permitted and useful. Preserve attribution and file-level licensing. Do not relicense upstream material under the new project's license by default. Material with unclear redistribution rights remains reference-only or unresolved; do not claim legal compatibility from a repository badge alone.

Provide complete small functions/examples with necessary context when legally permitted. For large source units, prefer a pinned acquisition recipe plus targeted, attributable excerpts and an explicit transformation specification. Do not mirror entire manuals or repositories indiscriminately. Keep the research/reference corpus separate from the shipped runtime plugin.

Working-evidence labels must distinguish source-present, source-reviewed, upstream-tests-present, upstream-CI-observed, locally-statically-checked, locally-fixture-tested, and live-qualified. Record which version and test proves which behavior. An upstream green badge does not prove the selected function, new platform, API, or adaptation works. Report stronger and weaker evidence without manufacturing a universal quality score.

## 7. Collect the brownfield input and normalization contracts

Specify an intake model for an existing export directory/JSON bundle, an existing IaC repository, and a future separately authorized read-only Graph discovery session. Prioritize local export and repository modes so the product is useful without tenant authentication. Do not assume an undocumented universal Intune export format.

Find code for pagination, nested settings and assignment retrieval, record provenance, duplicate-name handling, partial failures, error classification, and coverage reporting. Determine exactly which relationships each exporter includes or omits. A successful list request is not a complete inventory.

Create a versioned canonical model and synthetic input fixtures. Preserve the distinction between raw source, normalized observed configuration, proposed desired configuration, generated IaC, ownership/import mappings, and observed endpoint evidence. Record source tenant/cloud, object type/ID, capture time, API version, permissions/coverage, raw-content digest, source lineage and relationships without putting sensitive raw data into the distributable package.

Every source field must be mapped to one of: desired configuration; service-owned/read-only metadata; relationship; separately managed object; sensitive/local-only data; or unsupported/unknown content. Preserve unsupported material in a restricted sidecar/reference and surface a review blocker where losing it could change behavior. Never silently drop settings, nested values, exclusions, assignment filters, scope metadata, or custom payloads to make generation succeed.

Define handling for absent versus null versus empty values, ordering and set semantics, defaults, dynamic values, secrets, read-only fields, API normalization, versioned definitions, and unsupported polymorphic types. An arbitrary JSON export is not a valid create/update payload.

Make coverage explicit: complete, partial, access-denied, unsupported, stale, or unknown. Missing pages or permissions must not be interpreted as deletions. Distinguish a difference between two exported snapshots from provider-reported drift against a declared desired state, and distinguish both from changed effective endpoint behavior.

Deliver actual JSON Schemas, field-mapping tables, normalization rules, synthetic records, and invariants. Include meaningful examples, not schemas whose only example is an empty object.

## 8. Collect implementable policy-to-IaC and import recipes

Start from a bounded existing configuration family and map it end to end. Research Settings Catalog/configuration profiles, compliance/endpoint security, assignments/groups/filters, and application/script/remediation concerns sufficiently to publish an honest supported-family matrix. The first implementation must include at least one real policy/configuration family and its assignment/adoption path—not only inventory or advice. Additional families may be staged, but every required area needs a concrete material-gathering disposition.

For each candidate provider resource or adapter operation obtain the canonical publisher, exact version, schema, real API method/path/version, documented permissions, import syntax and identifier shape, lifecycle implementation, examples, tests, known issues and limitations. Determine stable/preview/beta status at research time; do not copy the report's status as timeless fact.

Research source-to-HCL generation, variable/locals/module contracts, stable address construction, naming collisions, provider aliases, import blocks or commands, field normalization, lifecycle flags, and output/read-back conventions. Match installed Terraform/OpenTofu semantics; no unsupported feature should be generated simply because a newer example uses it.

For adoption, identity should not depend solely on display names. Keep an explicit mapping among source object ID, logical IaC address, provider import ID, relationships, tenant and ownership. Preserve existing assignments; verify whether the relevant assignment operation replaces an entire collection, merges, or has another documented behavior. Do not reset an existing assignment set while adding one pilot group.

Separate three cases: already managed by this repository; externally owned but approved for adoption; and unsupported or uncertain ownership. Define one writer at object or explicitly supported subresource level. A provider and an adapter must not both reconcile the same assignments implicitly.

The first adoption milestone is **no unintended remote configuration change**, not a broad cleanup/refactor. Import may write state and providers may normalize reads; that does not authorize setting changes. Deliver a procedure and fixture that demonstrates identity preservation and exposes any planned updates or replacement. Every difference needs an explained cause and separate review. Do not hide differences using broad `ignore_changes` or mutate raw state to manufacture a no-op.

Unsupported settings or incomplete import support must yield preserved evidence plus a precise capability gap. Research a governed adapter contract only when justified; do not substitute an opaque `local-exec` or an autonomous live Graph client. The wizard must still generate supported code and a usable handoff for the unresolved portion.

## 9. Collect Atmos and Azure integration materials

Find actual Atmos configuration/generation and introspection code that can preserve the repository's component/stack structure. Record source and precedence of effective variables, backend/workspace/state key, provider configuration, engine selection and version pinning, imports, executable YAML functions, hooks, workflow steps, and generated paths.

Use real version-qualified commands and tests; do not construct a partial YAML merger and call it equivalent to Atmos. Inspect introspection side effects and secret exposure before declaring it safe. Generated files are not necessarily the durable source of truth. Keep the configured engine OpenTofu even where Atmos uses a `terraform` command namespace.

Collect examples for existing Azure remote state, CI federation/identity, approved artifact storage, Key Vault integration, and required network/DNS access. Discover what already exists before generating dependencies. Separate bootstrap from normal execution. Do not create a landing zone, Kubernetes cluster, new analytics platform, or second CI controller without a concrete need.

For each Azure workflow provide exact provider/API references, minimal module or configuration recipe, identity/role requirements, scoped target checks, relevant read-back/data-plane verification, and failure examples. Distinguish ARM success from usable service access. Maintain the same ownership and source-of-truth rules across providers, CLI and portal activity.

Create a per-operation permission matrix covering Azure RBAC, Entra roles, Graph application/delegated permissions, and Intune service-specific boundaries. Include issuer/subject/audience and target validation for CI federation. Do not assume portal scope tags constrain app-only identities. Supply positive and negative test specifications; label actual tenant enforcement unverified without authorized evidence.

Research CI templates for local/static checks, schema and script tests, protected plan artifacts, approval/revision binding, concurrency, short-lived credentials, and outcome evidence. Never grant cloud credentials to untrusted PR code. Do not adopt AWS-backed Atmos CI artifacts or paid services as hidden requirements for an Azure workflow.

## 10. Specify PowerShell/Bash command generation precisely

Find and compare working command-rendering, subprocess, output-streaming, and error-handling implementations. Prefer a structured operation model plus shell-specific rendering over concatenating untrusted strings. Interactive execution and emitted commands must use the same validated target and operation specification.

Create an `operation.schema.json` and a command-card schema. Each command card must contain its purpose, shell/version, working directory, prerequisites, validated target, executable/arguments, local/network/state/cloud effects, privilege requirement, input artifacts, expected exit/status semantics, expected output artifacts, verification, and approval boundary.

Emit separate, correctly tagged `powershell` and `bash` code blocks in the agent UI. A raw terminal should display executable command text without requiring users to paste Markdown fences. Offer a saved script or command file when a sequence is long. Show examples with resolved safe values or validated parameter prompts; do not leave unexplained placeholders that a developer could paste as real values.

Test quoting and escaping for Windows drive paths, spaces, apostrophes, brackets, dollar signs, Unicode, newlines, and metacharacters. Sanitize terminal control sequences in untrusted names/logs. Treat JSON depth/serialization/encoding, native command exit codes, PowerShell version differences, and Bash failure/pipeline semantics explicitly. Do not use `eval`, `Invoke-Expression`, or string-built shell execution as a convenience.

Preserve command exit meanings rather than treating every nonzero status identically. Generated scripts must stop safely on unmet prerequisites and must not install tools, change authentication, or escalate privilege silently. Secrets belong in approved secret mechanisms, never emitted command strings or persisted wizard answers.

Distinguish **emit-only preview** from an actual `plan`: a printed command is not execution, and provider-backed planning may require network/authentication and invoke code. Before executing a reviewed card, verify that its files, target, revision and operation are unchanged. The wizard's confirmation is not a substitute for protected CI approval.

## 11. Provide concrete developer journeys and golden artifacts

Research enough material to give the builder three complete vertical slices and their failure variants:

| Slice | Required end product |
|---|---|
| Existing Intune policy adoption | Sanitized export → normalized records → supported IaC and variables → ID/import map → Atmos target → no-unintended-change review → assignment/evidence contract. |
| Azure workflow integration | Existing-repository discovery → required Azure dependency or integration → generated/reused IaC → CI/identity plan → review artifact → management/data-plane evidence contract. |
| Intune failure investigation | Sanitized service/device evidence → timeline and competing hypotheses → missing-evidence decision → bounded remediation or collection command cards. |

For each supply the starting repository/export, question-and-answer transcript, chosen decisions, expected generated file tree, complete minimal file contents, command cards, deterministic checks, expected outcomes, invalid/failure examples, resume behavior and source references. Distinguish authored reference artifacts from actual recorded execution.

The policy example must include multiple existing assignments, an exclusion/filter or another meaningful targeting relationship, an unknown/unsupported field, duplicate display names or another identity ambiguity, and a correction path that does not discard them. Provide both a fully supported success fixture and a deliberately unsupported/partial fixture.

Application/script material must include practical install/detection/execution-context, package provenance/hash, requirements, reboot/exit, dependency/supersedence, and verification contracts. Do not equate an app record, upload, or installer exit with endpoint success. Supply review/generation material even where live delivery remains separately qualified.

A generated project should be maintainable without the wizard. Do not hide the source of truth in a bot database. Respect existing filenames/conventions and avoid overwriting unrelated files. Define staging/diff/merge behavior, atomic local writes where practical, backup retention, rerun idempotence, and conflict detection.

## 12. Diagnostics and rollout evidence materials

Adapt useful PowerStacks methodology and code into an offline-first evidence analyzer. Select narrow collectors only where an identified missing signal justifies them. Distinguish reading configuration from bundle writes, downloads, installation, driver loading, tracing, sync/restarts and active reproduction. Audit actual scripts and subprocesses.

Create a bundle manifest, coverage/freshness schema, timeline convention, pseudonymization rules and test fixtures. Raw originals remain restricted; model-visible derivatives preserve enough correlation without exposing tokens, private keys, recovery material, unrestricted registry hives, script secrets or user data. Do not claim regex redaction guarantees safety.

Record log window, timezone/clock assumptions, access failures, logging state, truncation and rollover. Missing events are not proof of nonexecution without established completeness. Registry values and decompiled constants are evidence about a version/context, not proof a particular code path ran. Specialized binary analysis remains separately authorized, not a default dependency.

Define Azure and Intune evidence stages separately. For Intune preserve object read-back, assignment, intended cohort, endpoint receipt, execution, effective state and device/user outcome. Collect sample records for success, failure, pending, unknown, offline/stale, and conflicting signals.

Specify eligible/targeted/reporting denominators, freshness windows, cohort versioning and promotion/hold logic without inventing production thresholds. An eight-of-eight reporter success result cannot silently become success for one hundred targets. Distinguish schema-valid evidence, synthetic evidence, observed execution and live-qualified outcome.

## 13. Finish the dsoxlab and evaluation-material inventory

Enumerate the actual Terraform catalogue at an immutable revision; do not assume the advertised 88 count. Produce the complete per-lab `catalog-manifest.json` the first report left pending. Every row needs ID/path, prerequisites, engines/providers, services, mutable paths, networking/credentials, setup/grader/cleanup, source files, expected invariant, competency, learner-mode behavior, solution/hint exposure, attestation and replay status.

Inspect hardcoded engine names and reference-solution replay. Identify legitimate OpenTofu adaptations with patches/contracts, separate workdirs/state and preserved acceptance criteria. Do not run live/destructive labs or decrypt solutions during this research. Missing prerequisites and skipped tests remain visible.

Use the catalogue as development/evaluation material, not always-loaded context. Build original held-out variants with changed topology, data shape, provider/version and failure conditions, not merely renamed resources. Protect assessment graders and solutions from the evaluated agent; the builder may author them, but the runtime package and candidate workspace must not expose them.

Distinguish the installed **Plugin Eval** project's CLI/schema, Anthropic's **`claude plugin eval`**, and other skill-creator/pytest harnesses. Obtain exact official contracts and installed-version verification procedures; names do not imply format compatibility. Separate structural scoring, deterministic helper tests, agent A/B behavior, token measurement and live qualification. Do not invent baseline results or harness output.

The comparison plan must hold model, task, available tools, permissions and budget constant where possible: no added skill; strongest upstream configuration; proposed skills; proposed skills plus extra controls. Include repeated safety-critical cases and actual denominators. Improvements from tools or permissions must not be attributed solely to prose.

## 14. Acceptance fixtures for the wizard and generated code

Create test-ready fixture specifications with expected files, data, action traces, exit/status behavior, and forbidden side effects. Provide actual synthetic inputs and expected assertions, not a list of test titles. Prefer deterministic tests for objective behavior and reserve model judgment for genuinely qualitative decisions.

At minimum cover: lossless field/relationship accounting; stable IDs; no unintended adoption changes; unsupported provider/schema rejection; incomplete inventory not treated as deletion; duplicate display names; assignment-set preservation; wrong tenant/stack; provider-version mismatch; existing-writer conflict; rerun without duplicate files/resources; safe back/edit/cancel; resume after changed source; ambiguous operation timeout; stale approval; non-TTY/EOF; PowerShell/Bash quoting equivalence; secret/control-sequence output; read-only mode avoiding auth/download/installation; and a simple question that does not load the entire plugin.

Add combined developer journeys: unfamiliar export format, no admin rights, partially managed estate, a provider import that yields a real configuration difference, a Win32 app installed but detected incorrectly, and a pilot with low reporting coverage. Include useful-action checks so blanket refusal cannot pass.

Require fixture/parser/unit tests, HCL/JSON/YAML/script validation appropriate to the chosen versions, and pseudo-terminal or host-interaction tests for the implemented interface. Capture keyboard cancellation, narrow terminals, color-disabled/plain mode, Unicode, and interrupted subprocess behavior. Toolchain-only or static validation is not proof of semantic adoption or live API support.

## 15. Package contracts, acquisition, and final ZIP requirements

Collect current authoritative Agent Skills, Claude Code and Codex packaging specifications, minimal reference manifests, lifecycle/permissions behavior and validation examples. Verify portable versus host-specific manifests, discovery, slash/invocation behavior, dependency loading, relative paths, executable permissions, and local/repository installation. Do not freeze the report's illustrative file tree as a tested packaging standard.

Decide one plugin with focused skills versus several coordinated plugins using actual host packaging and permission needs. The developer should experience a coherent entrypoint. Avoid duplicate routers, repeated questions and conflicting writers. A missing optional integration must not prevent offline review/generation.

Maintain three distinct distributions: runtime plugin(s); development/evaluation material; and research provenance/source-reference material. Golden assessment answers, production exports, credentials, local state/plans, `.terraform` caches, unrestricted logs, downloaded proprietary tools and absolute personal paths do not belong in the runtime ZIP.

Select whether each dependency is bundled, separately installed, or reference-only, with license, size, integrity, offline and update implications. Provide Windows/PowerShell and Linux/Bash acquisition/install/uninstall recipes. Acquisition must be opt-in, version-locked and integrity-checked where evidence permits; archive extraction must reject path traversal and unsafe links. Do not add hidden runtime downloads or automatic live hooks.

Specify the builder's release verification: clean extraction, path/reference validation, manifest/schema validation, local helper tests, terminal smoke journeys on stated platforms, secret/data scans with documented limitations, deterministic archive contents, notices, dependency inventory, checksums and a clean-environment reproduction command. A ZIP must include real file contents, not empty placeholders or only a research report.

## 16. Required implementation dossier

Return actual populated materials, organized so the builder can open `BUILD-START-HERE.md` and proceed without repeating broad discovery. A reasonable logical structure is:

```text
build-materials/
  BUILD-START-HERE.md
  INPUTS-AND-DECISIONS.md
  REQUIREMENTS-TRACEABILITY.csv
  gap-register.json
  source-lock.json
  code-catalog.jsonl
  reuse-ledger.csv
  sources/                     # Selected lawful extracts or verified retrieval records
  recipes/                     # Concrete generation/adoption/CI/diagnostic recipes
  contracts/                   # Real schemas and interface definitions
  wizard/                      # Questions, state machine, transcripts, command cards
  examples/                    # Complete synthetic starting and expected projects
  evaluations/                 # Cases, fixtures, grader specs and runner contracts
  catalog-manifest.json
  compatibility.csv
  provider-api-coverage.csv
  microsoft-workflows.yaml
  PERMISSIONS.md
  DIAGNOSTICS.md
  INTUNE-ROLLOUT.md
  BUILD-PLAN.md
  ZIP-ACCEPTANCE.md
  THIRD-PARTY-NOTICES.md
  MATERIALS-STATUS.md
```

Paths may be consolidated, but every required record must remain explicit and machine-readable where specified. Provide schemas for important manifests and examples that satisfy them. Each implementation task in `BUILD-PLAN.md` must name input source IDs/files, target files, interfaces, decisions already resolved, tests, dependencies, expected verification output, and remaining environment-specific facts.

For each capability maintain a closed trace:

**User requirement → wizard decision/stage → vetted code/source → data or operation contract → generated artifact → fixture/assertion → execution/assurance status.**

Assign statuses by dimension: acquired, reviewed, authored, syntax-checked, fixture-tested, behaviorally evaluated, live-qualified, blocked or unavailable. Publish complete/partial counts for code selections, lab inventory, workflow coverage, schemas, fixtures and unresolved questions. A nonempty CSV is not evidence every requirement is satisfied.

Supply buildable minimal originals where no suitable implementation exists, or a sufficiently precise algorithm/interface plus tests for the builder to implement. Mark original reference implementations untested when appropriate. Do not end a required capability with “research this later” unless its exact blocker and bounded next action are recorded.

Include a narrowly scoped environment-input template for facts only the organization can supply: repository/provider pins, approved execution identities, tenant/cloud/subscription, backend ownership, export shape, scope/cohorts, approval policy and evidence sources. It must not request raw secrets or private production exports for an unapproved environment.

## 17. Completion standard and researcher-to-builder handoff

The research is successful when a computer-access LLM can identify exactly what to build, obtain the selected source material, understand its permissions/licenses and limitations, implement the terminal flow and generation pipeline, run deterministic offline tests, and produce a coherent installable ZIP—without another broad ecosystem search.

That does not eliminate necessary environment verification, original coding, agent A/B evaluation or separately authorized live qualification. Separate **ready for offline implementation**, **ready for host testing**, and **ready for live qualification**. Do not turn unknown tenant permissions into a false guarantee or use unavailable live access as a reason to withhold complete offline materials.

The final response should start with a brief handoff summary and links/files for the dossier, then name the strongest selected code units, the supported first vertical slice, and remaining blockers. Deliver `build-materials.zip` only when it actually exists and has been checked; it is a research dossier, not the finished plugin ZIP. Otherwise provide complete text artifacts and a precise acquisition map without inventing files, hashes, commands or executions.

Include this builder instruction, adapted to the actual completed dossier:

> Read BUILD-START-HERE.md, the approved v3 scope, and the user's brownfield terminal-wizard requirements. Inspect the supplied source lock, code catalogue, reuse decisions, contracts, fixtures and build plan. Build the implementation rather than issuing another landscape report. Begin with failing deterministic tests and a thin end-to-end adoption slice; implement guided questions, actual file generation, and PowerShell/Bash command output before broadening resource families. Preserve existing IDs/assignments, OpenTofu/Atmos execution and approval boundaries. Validate host packaging and terminal behavior, produce the actual source repository and ZIP, and report exactly which checks ran. Keep production auth, state import, deployment, endpoint collection and live qualification outside the authorized build scope unless separately approved. Do not claim the skills' behavioral benefit before the corresponding agent evaluations.

The final product must feel like a competent interactive engineering assistant: it helps a developer move from an existing Intune estate to maintainable IaC and Azure workflows, asks the questions that affect correctness, builds useful artifacts, makes commands easy to inspect and run, and explains what the evidence does—and does not—establish.

---

## Reference entrypoints for this appendix's preparer

These are initial source leads, not a claim that every implementation was audited or executed when this prompt was prepared. Verify them again during the research and capture the actual revisions used.

```text
# Prior report supplied with the research request
Deep Research: Senior Microsoft Cloud and Endpoint DevSecOps Engineering Plugin

# Atmos interaction and current skill catalogue
https://atmos.tools/cli/
https://atmos.tools/cli/commands/describe/component/
https://github.com/cloudposse/atmos/tree/main/agent-skills/skills
https://github.com/cloudposse/atmos/blob/d5790b2b11cce4b1c1ed96da9a73716510d6d03a/internal/tui/atmos/tui.go
https://github.com/cloudposse/atmos/blob/d5790b2b11cce4b1c1ed96da9a73716510d6d03a/pkg/terraform/ui/model.go

# Microsoft SDK-based samples and legacy-status guidance
https://github.com/microsoft/mggraph-intune-samples
https://github.com/microsoftgraph/msgraph-sdk-powershell
https://learn.microsoft.com/en-us/samples/microsoftgraph/powershell-intune-samples/important/

# Host packaging and skill guidance: inspect current contracts, not remembered paths
https://developers.openai.com/plugins/build/plugins
https://developers.openai.com/plugins/build/skills
https://code.claude.com/docs/en/plugins
https://code.claude.com/docs/en/plugin-evals
https://agentskills.io/specification

# API and engine evidence: use the exact applicable versions
https://learn.microsoft.com/en-us/graph/api/resources/intune-graph-overview?view=graph-rest-1.0
https://opentofu.org/docs/
https://developer.hashicorp.com/terraform/docs
```

**Prepared as a research prompt on September 30, 2026. No plugin, lab, tenant, or endpoint execution is implied.**
