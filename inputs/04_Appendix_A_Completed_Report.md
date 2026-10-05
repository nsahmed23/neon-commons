# Deep Research Appendix A — Implementation Dossier for the Brownfield Intune-to-IaC Wizard

## Handoff summary

The strongest implementation direction is **not** a giant “senior DevSecOps” prompt and not a standalone AI application. It is a **thin agent/plugin layer coordinating a deterministic local builder** around the delivery path you already want:

> **Existing Intune estate → normalized inventory → explicit ownership/adoption decision → OpenTofu IaC → Atmos component/stack integration → Azure/Entra support → protected plan/import workflow → Intune and endpoint evidence.**

The developer-facing experience should remain conversational inside Claude Code or Codex, but correctness-sensitive work—normalization, ID mapping, generated-file manifests, command construction, session persistence, provider capability checks, and deterministic validation—should be delegated to local code rather than left entirely to free-form model generation.

The best initial vertical slice is **brownfield adoption of an existing Intune Settings Catalog policy, including assignments and targeting relationships**, because Microsoft now publishes a Microsoft Graph Terraform provider and official Terraform/Graph material, while Settings Catalog is the central Intune configuration surface. Microsoft still labels the `msgraph` provider preview, so the plugin must treat provider/API capabilities as version-qualified and must not imply that Microsoft publication automatically constitutes enterprise approval. [^source-01]

The current Microsoft Graph provider is substantially more useful than its early versions. Its v0.5.0 changelog records sovereign-cloud support, configurable create methods, fixes for nested-object updates, and earlier releases added collection import, moved-block support, transient-error retries, update-method selection, and fixes for external-change handling and `$ref` relationship state. Those details make it a serious implementation candidate for brownfield Graph/Intune work, while also showing why the wizard must pin provider versions and test imports rather than assuming generic Graph operations behave identically across releases. [^source-02]

There is also direct evidence that import/adoption deserves its own safety layer: a provider issue documents an existing `$ref` relationship import that planned replacement rather than a clean adoption. The correct lesson is not “the provider cannot import”; it is that **import success and post-import no-op are separate acceptance conditions**, especially for Graph relationships. [^source-03]

Atmos should remain the orchestration authority in repositories already using it. Its current releases include an interactive picker and increasingly demand-driven `list`/`describe` evaluation, which is useful for a wizard that must inspect effective configuration without eagerly authenticating unrelated subsystems. Atmos also explicitly separates UI output from data output in its own contribution guidance, a good pattern for machine-readable wizard operations. [^source-04]

The resulting product should feel approximately like this:

```text
$ intune-iac adopt

Repository
  Atmos project: detected
  IaC engine: OpenTofu
  Target component: not selected
  Existing IaC ownership: partial

Intune source
  Export: ./intune-export-2026-09-30/
  Objects discovered: 37
  Settings Catalog policies: 12
  Assignment relationships: 29
  Unsupported/unclassified records: 3

Which existing object should we adopt first?

> [Search] Windows - Security Baseline - Pilot

I found:
  Object ID:          8a...42
  Assignments:        3
  Exclusions:         1
  Assignment filter:  1
  Duplicate name:     no
  Existing IaC owner: none detected

One source field is not represented by the selected provider mapping.
I will preserve it in the adoption sidecar and block a "no-loss"
claim until it is resolved.

Choose:

> Generate supported IaC and preserve the gap
  Show source-to-IaC mapping
  Change provider/adapter
  Cancel

No Azure, Graph, state, or Intune changes have been made.
```

The research completed here is sufficient to give a computer-access builder a strong architecture, data contracts, first slice, and acquisition map. It is **not** sufficient to claim that all 88 advertised Terraform labs have been independently enumerated, that Claude/Codex A/B evaluations have run, that a production Intune provider has been organizationally approved, or that a finished plugin ZIP has been behaviorally validated. Those items remain explicit build/qualification tasks rather than invented results.

## Product architecture and engineering boundaries

### The recommended shape

Use a **hybrid architecture**:

```text
┌───────────────────────────────────────────────────────────────┐
│ Claude Code / Codex                                          │
│                                                               │
│  Senior engineering router                                   │
│  Guided questions                                            │
│  Explanation / review                                        │
│  Repository-aware decisions                                  │
└──────────────────────┬────────────────────────────────────────┘
                       │ typed local contracts
                       ▼
┌───────────────────────────────────────────────────────────────┐
│ Deterministic "intune-iac" helper                             │
│                                                               │
│ inspect     normalize     map          generate               │
│ diff        adopt-map     commands     verify-local           │
│ session     evidence      doctor       explain-capability     │
└──────┬────────────────────────────┬────────────────────────────┘
       │                            │
       ▼                            ▼
┌───────────────┐            ┌──────────────────────────┐
│ Local export  │            │ Existing repository      │
│ Raw evidence  │            │ Atmos/OpenTofu           │
└───────────────┘            └────────────┬─────────────┘
                                         │
                              separately authorized
                                         │
                                         ▼
                              ┌──────────────────────────┐
                              │ Protected CI            │
                              │ Atmos → OpenTofu        │
                              │ Graph/Azure providers   │
                              └────────────┬─────────────┘
                                           │
                 ┌─────────────────────────┴─────────────────────┐
                 ▼                                               ▼
             Azure/Entra                                     Intune
                 │                                               │
                 └────────────── evidence/read-back ──────────────┘
                                           │
                                           ▼
                                  Endpoint verification
```

The conversational host should own **human interaction and engineering explanation**. The helper should own **deterministic transformations and persistence**. Atmos should continue to own **repository orchestration**, and protected CI should own **privileged execution**.

This division addresses a central weakness in a pure skill-only implementation: instructions can tell a model to preserve IDs or quote shell arguments safely, but instructions do not prove it did so. The helper can make those properties machine-testable.

### Do not create another deployment controller

The wizard should not maintain an independent database of desired infrastructure. Its durable results should be ordinary repository artifacts:

```text
components/
stacks/
modules/
imports/
tests/
docs/
.github/workflows/         # where already appropriate
```

The wizard's session file contains only interaction state and provenance. The Git repository remains the source of truth.

Likewise, the plugin should not switch an Atmos/OpenTofu repository to `azd`, Bicep, direct `terraform apply`, a custom Graph release service, or another orchestration framework merely because an upstream skill uses one. The Microsoft Graph Terraform documentation itself demonstrates conventional Terraform configuration and plan/apply behavior; the reusable knowledge is the Graph resource model, not a mandate to change your enterprise execution system. [^source-05]

### Keep adoption and change separate

This should be a hard product rule:

```text
ADOPT_EXISTING
    objective: represent and attach to what already exists
    acceptance: identity preserved and every planned difference explained

CHANGE_EXISTING
    objective: intentionally alter desired configuration
    acceptance: reviewed functional delta and rollout/verification contract
```

Do not combine those into one “migrate policy” action.

A successful import only proves that the provider attached state to an object. It does **not** prove:

```text
plan == no-op
```

nor does it establish that assignments, `$ref` relationships, service defaults, nested Graph objects, or read-normalized fields are represented safely. The known provider relationship-import report reinforces the need for a post-import plan assertion. [^source-03]

### Proposed skill/plugin topology

The previous eight-domain structure remains useful, but the runtime should expose **one coherent entry experience**:

```text
microsoft-cloud-iac/
├── router
├── brownfield-intune
├── iac-engineering
├── atmos-engineering
├── azure-engineering
├── entra-graph-authorization
├── endpoint-diagnostics
└── delivery-security
```

`brownfield-intune` should be the flagship workflow rather than just another skill.

The router's responsibilities should be narrow:

```yaml
routes:
  adopt_existing_intune:
    load:
      - brownfield-intune
      - iac-engineering
      - atmos-engineering
      - entra-graph-authorization

  review_opentofu:
    load:
      - iac-engineering

  debug_atmos:
    load:
      - atmos-engineering
      - iac-engineering

  azure_dependency:
    load:
      - azure-engineering
      - entra-graph-authorization

  investigate_endpoint:
    load:
      - endpoint-diagnostics

  pipeline_or_secret_issue:
    load:
      - delivery-security
```

Loading everything on every question would defeat the intended progressive-disclosure model.

## Brownfield Intune vertical slice

### Why Settings Catalog should come first

Microsoft describes Settings Catalog as the consolidated Intune surface for configuring a large range of platform settings. [^source-06] Microsoft Graph also exposes Settings Catalog policy creation through `deviceManagement/configurationPolicies`; a current Microsoft example uses the beta Graph endpoint and requires `DeviceManagementConfiguration.ReadWrite.All` for the illustrated operation. [^source-07]

That makes it a practical first family for proving the wizard architecture while forcing the implementation to deal with the hard parts:

- nested setting instances;
- setting-definition IDs rather than friendly display text;
- object identity;
- assignments and exclusions;
- scope metadata;
- beta-versus-v1.0 API selection;
- provider normalization;
- unsupported fields;
- permission qualification;
- brownfield import.

Microsoft's general Graph Terraform guidance recommends v1.0 where available and beta only when the needed resource/property requires it. The wizard should encode that as a **decision procedure**, not blindly force either version. [^source-05]

### Canonical brownfield model

Do **not** transform arbitrary Graph JSON directly into HCL. Introduce a loss-aware intermediate representation.

A builder should implement approximately this schema:

```json
{
  "schema_version": "1.0",
  "source": {
    "kind": "intune-export",
    "captured_at": "2026-09-30T15:00:00Z",
    "tenant": {
      "id": null,
      "cloud": "public"
    },
    "coverage": {
      "status": "partial",
      "resource_families": [],
      "permission_gaps": [],
      "pagination_complete": true
    },
    "raw_digest": "sha256:..."
  },
  "objects": [
    {
      "source_identity": {
        "service": "intune",
        "resource_family": "settings_catalog_policy",
        "object_id": "00000000-0000-0000-0000-000000000001",
        "display_name": "Windows - Security Baseline - Pilot"
      },
      "observed": {},
      "relationships": [],
      "assignments": [],
      "field_accounting": [],
      "ownership": {
        "status": "unmanaged",
        "writer": null
      },
      "mapping": {
        "provider": null,
        "resource_type": null,
        "support": "unknown"
      }
    }
  ]
}
```

Every raw field must receive an accounting disposition:

```yaml
dispositions:
  desired:
    meaning: emitted into desired IaC

  relationship:
    meaning: modeled as a separate edge/assignment resource

  service_owned:
    meaning: observed but not sent back as desired configuration

  separately_managed:
    meaning: owned by another object/component

  sensitive_local_only:
    meaning: retained locally but not exposed to the model or repository

  unsupported:
    meaning: preserved and blocks lossless-adoption claim

  unknown:
    meaning: mapping not yet established; also blocks lossless-adoption claim
```

This is more important than sophisticated UI. It prevents the most dangerous failure mode in brownfield conversion: **the generated HCL looks complete because the exporter silently discarded something it did not understand**.

### Identity map

Do not derive Terraform/OpenTofu resource identity from display names.

Maintain a dedicated adoption map:

```yaml
schema_version: 1

objects:
  - source:
      tenant_id: "<validated-target-id>"
      resource_family: settings_catalog_policy
      object_id: "00000000-0000-0000-0000-000000000001"

    iac:
      component: intune-configuration
      address: >-
        msgraph_resource.settings_catalog_policy["windows_security_baseline_pilot"]

    provider:
      source: microsoft/msgraph
      version: "PINNED-BY-REPOSITORY"
      import_id: "VERSION-QUALIFIED-IMPORT-ID"

    ownership:
      desired_writer: opentofu
      relationships_writer: opentofu

    adoption:
      imported: false
      post_import_plan: not_run
```

The builder must populate the actual import-ID syntax from the **selected provider version's documentation or importer implementation**, not from this illustrative value.

### Relationship preservation

Assignments should be modeled as relationships, not flattened into policy body text merely for convenience.

The adoption invariant should look like:

```text
source policy ID
    == imported object ID

source assignment target IDs
    == generated desired assignment target IDs

source exclusions
    == generated exclusions

source filter IDs + filter modes
    == generated filter relationships

unsupported source fields
    == accounted for explicitly

unexpected planned remote changes
    == 0
```

A relationship import or collection resource deserves separate validation because Graph `$ref` resources have historically had provider-specific state and update behavior. The msgraph changelog shows that later releases added collection import and fixed `$ref` state/drift behavior, which is exactly why the dossier should pin and test the chosen version instead of inheriting examples written for older provider versions. [^source-02]

### First generated project

A good golden fixture should end approximately here:

```text
examples/settings-catalog-adoption/expected/
├── components/
│   └── terraform/
│       └── intune-configuration/
│           ├── component.yaml
│           ├── versions.tf
│           ├── providers.tf
│           ├── variables.tf
│           ├── locals.tf
│           ├── policies.tf
│           ├── assignments.tf
│           ├── outputs.tf
│           └── tests/
├── stacks/
│   ├── catalog/
│   │   └── intune/
│   └── orgs/
│       └── example/
│           └── dev.yaml
├── adoption/
│   ├── object-map.yaml
│   ├── field-accounting.json
│   ├── unsupported.json
│   └── import-proposal.json
├── commands/
│   ├── inspect.ps1
│   ├── inspect.sh
│   ├── review-plan.ps1
│   └── review-plan.sh
└── README.md
```

Do not hard-code this layout where an existing repository already has a different valid Atmos structure. The fixture demonstrates a contract; the wizard's first job is to infer the repository's established structure.

### No-op adoption gate

The builder should implement an explicit adoption status machine:

```text
DISCOVERED
    ↓
NORMALIZED
    ↓
MAPPED
    ↓
GENERATED
    ↓
STATICALLY_VALID
    ↓
IMPORT_PROPOSED
    ↓
IMPORT_REVIEWED
    ↓
IMPORTED_IN_AUTHORIZED_ENVIRONMENT
    ↓
POST_IMPORT_PLAN_REVIEWED
    ├── no differences → ADOPTED
    └── differences → RECONCILIATION_REQUIRED
```

`RECONCILIATION_REQUIRED` is a successful diagnostic state, not necessarily failure.

The wizard should say:

```text
The existing object was attached to state successfully, but that alone
does not establish a no-change adoption.

The post-import plan contains 2 differences:

1. roleScopeTagIds
   Source: ["0"]
   Desired: omitted

2. assignments
   Source: 3 relationships
   Desired: 2 relationships

I will not classify this object as safely adopted until these differences
are resolved or explicitly approved as functional changes.
```

## Wizard, terminal, and command contracts

### Let Claude/Codex converse; let deterministic code transform

The plugin should not build a separate chat client.

Use Claude Code/Codex for:

- intent recognition;
- repository-oriented conversation;
- asking context-dependent questions;
- explaining mappings and risks;
- editing generated files;
- invoking deterministic local helpers.

Use the helper for:

- scanning known file formats;
- normalizing exports;
- generating stable IDs/addresses;
- validating JSON Schemas;
- creating manifests;
- recording session decisions;
- producing command cards;
- checking field-accounting completeness;
- comparing expected/observed mapping sets;
- producing machine-readable output.

Atmos itself now has an interactive picker when invoked in appropriate interactive conditions, and current release notes describe demand-driven `list`/`describe` evaluation rather than eagerly authenticating unrelated fields. That makes existing Atmos UI useful for selecting known stack/component context; it should not be mistaken for the complete brownfield adoption wizard. [^source-08]

Atmos's project guidance also recommends a clean separation between UI and data streams—prompts/status on stderr, data on stdout—which should be copied as an interface principle for the helper. [^source-09]

### State machine

A builder-ready `wizard-state-machine.yaml` should resemble:

```yaml
schema_version: 1

initial: repository_inspection

states:
  repository_inspection:
    side_effect_class: local_read
    outputs:
      - repository-facts.json
    next:
      detected_atmos: source_selection
      no_atmos: orchestration_decision

  orchestration_decision:
    asks:
      - repository_orchestration
    next:
      existing_valid_structure: source_selection
      adopt_atmos: source_selection
      remain_non_atmos: source_selection

  source_selection:
    asks:
      - intune_input_source
    next:
      local_export: inventory
      authorized_graph_read: authorization_check
      existing_iac_only: inventory

  authorization_check:
    side_effect_class: network_read
    requires_explicit_scope: true
    next:
      authorized: inventory
      denied: blocked_with_offline_alternative

  inventory:
    outputs:
      - normalized-inventory.json
      - coverage.json
      - field-accounting.json
    next: object_selection

  object_selection:
    asks:
      - resource_family
      - selected_objects
    next: ownership_detection

  ownership_detection:
    next:
      already_managed: review_existing
      external_approved_for_adoption: provider_mapping
      conflicting_writer: ownership_conflict
      unknown: ownership_question

  provider_mapping:
    outputs:
      - capability-report.json
      - unsupported.json
    next:
      complete: generate
      partial: mapping_gap_decision
      unsupported: handoff_only

  generate:
    side_effect_class: local_write
    outputs:
      - generated-files.json
      - adoption-map.yaml
    next: local_validation

  local_validation:
    next:
      pass: adoption_preview
      fail: repair_generated

  adoption_preview:
    side_effect_class: emit_only
    outputs:
      - command-cards.json
    next: user_review

  user_review:
    next:
      approve_for_ci: handoff_to_authorized_execution
      edit: generate
      back: object_selection
      cancel: suspended
      save: suspended

  handoff_to_authorized_execution:
    side_effect_class: external_authorization_required
    terminal: true

  suspended:
    resume_requires:
      - source_digest_match
      - repository_revision_match
      - provider_context_match
      - target_context_match
```

### Question definitions

Questions should be facts-first rather than interrogating the developer about things the tool can discover.

```yaml
questions:
  intune_input_source:
    prompt: "Where should I read the existing Intune configuration from?"
    choices:
      - id: local_export
        label: "Local export or sanitized bundle"
        recommended: true

      - id: existing_iac
        label: "Existing repository configuration only"

      - id: graph_read
        label: "Separately authorized read-only Microsoft Graph discovery"
        requires_authorization: true

  adoption_intent:
    prompt: "What should happen to the selected existing objects?"
    choices:
      - id: adopt_unchanged
        label: "Bring them under IaC without intentional configuration change"
        recommended: true

      - id: adopt_then_change
        label: "Adopt them first, then prepare a separate reviewed change"

      - id: analyze_only
        label: "Analyze and generate a proposal only"

  unsupported_fields:
    shown_when: "mapping.unsupported_count > 0"
    prompt: >-
      "The selected object contains fields the current mapping cannot
      reproduce. How should I proceed?"
    choices:
      - id: preserve_and_block_lossless_claim
        label: "Generate the supported portion and preserve the gap"
        recommended: true

      - id: inspect_alternative_provider
        label: "Evaluate another approved provider/adapter"

      - id: stop
        label: "Stop this object"
```

### Resume record

```json
{
  "schema_version": 1,
  "session_id": "generated-id",
  "created_at": "2026-09-30T00:00:00Z",
  "source": {
    "digest": "sha256:...",
    "kind": "local_export"
  },
  "repository": {
    "revision": "git-sha",
    "dirty_digest": "sha256:..."
  },
  "context": {
    "engine": "tofu",
    "engine_version": "observed-version",
    "atmos_version": "observed-version",
    "provider_lock_digest": "sha256:..."
  },
  "decisions": [],
  "generated_files": [],
  "authorization": {
    "persisted": false
  }
}
```

Never serialize:

```text
access tokens
client secrets
refresh tokens
state credentials
private keys
raw secret values
interactive login caches
```

Resume should invalidate at least the affected stages when one of these changes:

```text
source export digest
repository revision / relevant dirty files
provider lockfile
OpenTofu version
Atmos version where behavior matters
tenant/cloud
selected component or stack
selected object IDs
assignment cohort
reviewed plan identity
```

### Operation contract

Commands should be generated from a typed operation, not from shell interpolation.

Conceptually:

```json
{
  "schema_version": "1",
  "operation_id": "inspect-atmos-component",
  "purpose": "Resolve the effective Atmos component configuration",
  "effect_class": "local_or_config_read",
  "working_directory": ".",
  "executable": "atmos",
  "arguments": [
    "describe",
    "component",
    "intune-configuration",
    "-s",
    "example-dev"
  ],
  "target": {
    "stack": "example-dev",
    "component": "intune-configuration"
  },
  "requires": {
    "network": "version-dependent",
    "authentication": "version-and-config-dependent",
    "privilege": "standard-user"
  },
  "outputs": {
    "stdout": "machine-readable-data",
    "stderr": "ui-or-diagnostics"
  },
  "execution": {
    "allowed_in_default_research_mode": false
  }
}
```

Atmos's recent work explicitly notes that some `list`/`describe` values may cause deferred authentication only if the requested values require it. Therefore the wizard cannot globally label every Atmos describe operation “offline” or “read-only with no auth”; its command card should state exactly what is requested. [^source-08]

### PowerShell and Bash rendering

Both shell renderers must derive from the same operation structure.

For example, a harmless local helper operation might render:

**PowerShell**

```powershell
& ".\bin\intune-iac.exe" normalize `
    --input ".\fixtures\export" `
    --output ".\.intune-iac\normalized.json"

if ($LASTEXITCODE -ne 0) {
    throw "Normalization failed with exit code $LASTEXITCODE"
}
```

**Bash**

```bash
./bin/intune-iac normalize \
  --input './fixtures/export' \
  --output './.intune-iac/normalized.json'
status=$?

if [ "$status" -ne 0 ]; then
  printf 'Normalization failed with exit code %s\n' "$status" >&2
  exit "$status"
fi
```

The runtime implementation should execute an argument vector equivalent to:

```text
[
  "./bin/intune-iac",
  "normalize",
  "--input",
  "./fixtures/export",
  "--output",
  "./.intune-iac/normalized.json"
]
```

not:

```text
shell("intune-iac normalize " + user_supplied_path)
```

Do not use `Invoke-Expression`, `eval`, or equivalent string execution.

## Source and implementation reuse ledger

The builder should acquire source at immutable revisions and maintain a `source-lock.json`. Do not copy entire repositories into the runtime ZIP.

A high-value initial ledger is:

| Source | Disposition | Implementation value |
|---|---|---|
| `cloudposse/atmos` | **depend/reference + selectively adapt** | Existing orchestration, effective component/stack resolution, current interactive picker, terminal conventions. |
| `microsoft/terraform-provider-msgraph` | **provider candidate; pin and qualify** | Generic Graph resources, relationships, imports, retries, Graph authentication, TCM-driven authoring. |
| Microsoft Graph Terraform Learn material | **reference and fixture source** | Official expected resource model and provider usage; especially valuable for first Settings Catalog slice. |
| `hashicorp/agent-skills` | **selective guidance reuse** | Terraform authoring, refactor/test conventions; do not assume OpenTofu parity automatically. |
| `antonbabenko/terraform-skill` | **reference/adapt** | Opinionated lifecycle and validation discipline; useful as review guidance rather than core runtime dependency. |
| TerraShark | **reference/adapt** | Failure-mode and diagnostic framing; avoid stacking overlapping prompt text blindly. |
| `microsoft/azure-skills` | **selective expertise reuse** | Azure service planning/validation/diagnostic knowledge; do not inherit unrelated azd orchestration automatically. |
| PowerStacks Intune troubleshooting | **selective code/reference** | Evidence-driven endpoint troubleshooting; audit collectors for installation/elevation/write side effects before reuse. |
| Claude-m | **reference-only until each unit is proven executable** | Useful domain prompts/cataloguing, but knowledge commands must not be treated as real Graph adapters without implementation evidence. |
| Microsoft Graph PowerShell SDK | **dependency/reference candidate** | Graph discovery and request handling for an authorized collector; keep authentication out of offline mode. |
| Microsoft Intune Graph samples | **reference-only unless current path verified** | Learn request shapes and relationships; avoid retired authentication patterns. |
| dsoxlab curriculum/runner | **development/evaluation only** | Terraform competency fixtures and deterministic grading ideas; never runtime prompt baggage. |
| Superpowers | **development methodology** | Red/green/refactor, debugging, verification, skill-authoring patterns. |
| Plugin Eval | **evaluation-only** | Host-specific behavioral evaluation after exact current schema/CLI is verified. |

### Atmos material

The current Atmos release line is active; the search result captured v1.230.0 and documents an interactive picker restoration as well as demand-driven list/describe evaluation. [^source-08]

The builder should inspect and pin these already identified implementation entrypoints from the supplied research brief:

```text
internal/tui/atmos/tui.go
pkg/terraform/ui/model.go
pkg/ui/spinner/
internal/exec/
```

Do not simply copy the TUI. First ask whether the wizard can use Atmos itself for stack/component selection.

A sensible separation is:

```text
Atmos picker:
    select an existing Atmos stack/component

wizard:
    select Intune object(s)
    establish adoption intent
    show unsupported mappings
    collect missing ownership decisions
```

That avoids implementing a second Atmos browser.

### Microsoft Graph provider material

The provider should be acquired from a fixed release and SHA, then the builder should inspect:

```text
provider configuration/authentication
msgraph_resource
msgraph_resource_collection
import implementation
TCM metadata handling
create/update/delete request construction
read normalization
retry logic
examples
acceptance/unit tests
```

The current repository describes itself as a thin Terraform layer over Microsoft Graph REST APIs. [^source-10]

The current changelog provides particularly useful implementation evidence:

- v0.5.0 added `create_method` and sovereign-cloud behavior;
- nested-object updates were corrected to avoid resetting omitted sibling fields;
- v0.4.0 added collection import and default retry behavior for transient errors;
- v0.3.0 added update-method selection, moved support from `azuread`, consistency waits, and fixes around arrays and `$ref` state. [^source-02]

These are precisely the features a brownfield wizard must feature-detect or version-gate.

The provider should **not** be presented as universally production-ready. Microsoft Learn still labels the provider preview in its current Terraform Graph quickstart. [^source-05]

### dsoxlab evaluation corpus

The full Terraform catalogue manifest remains a build-materials gap in this research pass; it should not be fabricated from the advertised count.

However, the runner's documented architecture gives the builder a useful model: the lab ecosystem separates repository-level `meta.yml` from per-lab `lab.yaml`, uses a defined learner lifecycle, and distinguishes learner checking from instructor/reference-solution replay. The broader dsoxlab documentation explicitly describes `LAB_NO_REPLAY=1` as disabling solution replay in the learner path. [^source-11]

This should lead to two rules for the later benchmark:

```text
reference solution replay enabled
    => not valid agent-performance evidence

skipped due missing solution/runtime/prerequisite
    => not a pass
```

The builder should enumerate the **Terraform** catalogue at the already identified revision, rather than mixing statistics from the Linux catalogue.

### Suggested source-lock structure

```json
{
  "schema_version": 1,
  "generated_at": "2026-09-30T00:00:00Z",
  "sources": [
    {
      "id": "atmos",
      "repository": "cloudposse/atmos",
      "commit": null,
      "release": "builder-must-pin-current-supported-release",
      "license": "builder-must-record",
      "selected_paths": [
        "internal/tui/atmos/tui.go",
        "pkg/terraform/ui/model.go",
        "internal/exec/"
      ],
      "status": "entrypoints_identified_not_vendor-locked"
    },
    {
      "id": "microsoft-msgraph-provider",
      "repository": "microsoft/terraform-provider-msgraph",
      "release": "0.5.0",
      "commit": "builder-must-verify-release-sha",
      "selected_paths": [
        "CHANGELOG.md",
        "internal/provider/",
        "internal/services/",
        "examples/"
      ],
      "status": "version-qualified-research-source"
    }
  ]
}
```

Where a SHA has not actually been established, `null` plus a blocker is correct. Filling it with a branch name or guessed hash is not.

## Build contracts and implementation plan

### Required dossier files

The computer-access builder should create this dossier before the runtime ZIP:

```text
build-materials/
├── BUILD-START-HERE.md
├── INPUTS-AND-DECISIONS.md
├── REQUIREMENTS-TRACEABILITY.csv
├── gap-register.json
├── source-lock.json
├── code-catalog.jsonl
├── reuse-ledger.csv
│
├── contracts/
│   ├── observed-intune.schema.json
│   ├── field-accounting.schema.json
│   ├── adoption-map.schema.json
│   ├── capability-report.schema.json
│   ├── operation.schema.json
│   ├── command-card.schema.json
│   ├── session-state.schema.json
│   └── evidence.schema.json
│
├── wizard/
│   ├── wizard-state-machine.yaml
│   ├── wizard-questions.yaml
│   ├── interaction-contract.md
│   └── transcripts/
│       ├── powershell-adoption.md
│       ├── bash-emit-only.md
│       └── recovery.md
│
├── recipes/
│   ├── settings-catalog-adoption.md
│   ├── atmos-integration.md
│   ├── azure-ci-identity.md
│   ├── assignment-preservation.md
│   └── endpoint-evidence-analysis.md
│
├── examples/
│   ├── settings-catalog-supported/
│   ├── settings-catalog-partial/
│   ├── duplicate-name/
│   └── endpoint-investigation/
│
├── evaluations/
│   ├── cases.yaml
│   ├── fixture-manifest.json
│   ├── forbidden-effects.yaml
│   └── agent-eval-plan.md
│
├── catalog-manifest.json
├── compatibility.csv
├── provider-api-coverage.csv
├── microsoft-workflows.yaml
├── PERMISSIONS.md
├── DIAGNOSTICS.md
├── INTUNE-ROLLOUT.md
├── BUILD-PLAN.md
├── ZIP-ACCEPTANCE.md
├── THIRD-PARTY-NOTICES.md
└── MATERIALS-STATUS.md
```

### Capability report

Before generating HCL, the helper should produce something like:

```json
{
  "resource_family": "settings_catalog_policy",
  "source_object_id": "00000000-0000-0000-0000-000000000001",
  "provider": {
    "source": "microsoft/msgraph",
    "version": "0.5.0"
  },
  "api": {
    "resource": "deviceManagement/configurationPolicies",
    "version": "beta",
    "reason": "version-qualified-mapping-requires-beta"
  },
  "operations": {
    "read": "supported",
    "create": "supported",
    "update": "supported_with_qualified_mapping",
    "import": "must_verify_for_exact_resource_shape",
    "assignment": "must_map_relationship_operation",
    "delete": "supported_but_not_authorized_by_adoption"
  },
  "field_coverage": {
    "desired": 18,
    "service_owned": 5,
    "relationship": 4,
    "unsupported": 1,
    "unknown": 0
  },
  "lossless_adoption": false,
  "blockers": [
    "One source field has no proven write mapping"
  ]
}
```

### Command card contract

A command card should make side effects impossible to miss:

```yaml
schema_version: 1

id: adoption-plan

purpose: >
  Produce the provider-backed OpenTofu plan used to compare the imported
  object with generated desired configuration.

shell_renderers:
  - powershell
  - bash

effect:
  local_files: writes_plan_artifact
  network: provider_may_read_remote_apis
  state: reads_configured_state
  cloud_mutation: false_by_intent
  authentication: required

authorization:
  default_research_mode: forbidden
  approved_ci: allowed_when_policy_permits

target:
  component: intune-configuration
  stack: example-dev

preconditions:
  - repository revision matches reviewed revision
  - source export digest matches adoption record
  - OpenTofu/provider locks match review record
  - target tenant is independently validated

postconditions:
  - structured plan artifact produced
  - action parser succeeds
  - unexpected creates/updates/deletes/replacements are reported
```

A provider-backed plan is **not** the same category as a local syntax check, even when it is expected not to mutate resources.

### Evidence contract

For Intune:

```yaml
stages:
  - desired_configuration_reviewed
  - provider_or_api_accepted
  - service_object_read_back
  - assignment_read_back
  - intended_cohort_resolved
  - endpoint_received
  - workload_executed
  - effective_state_observed
  - user_or_device_outcome_observed
```

For Azure:

```yaml
stages:
  - desired_configuration_reviewed
  - target_identity_validated
  - protected_change_executed
  - arm_or_service_read_back
  - data_plane_access_validated
  - network_or_dns_path_validated
  - workload_outcome_observed
```

No earlier stage should imply later-stage success.

### Permission model

The wizard should expose permissions per operation rather than saying “needs Azure admin.”

For example:

```yaml
operation: intune.settings_catalog.read

planes:
  azure_rbac: none
  entra_directory_role: depends_on_authentication_model
  graph:
    type: delegated_or_application
    scopes: version-qualified
  intune_rbac:
    applicability: principal-type-and-operation-dependent

negative_test:
  required: true
  question: >
    Can the automation principal read/write outside the cohort or scope
    it is expected to control?
```

The current Microsoft example for directly creating a Settings Catalog policy through Graph identifies `DeviceManagementConfiguration.ReadWrite.All`; that is useful evidence for that specific demonstrated call, **not** a universal permission prescription for the wizard's entire workflow. [^source-07]

### Initial deterministic tests

Before expanding provider coverage, the builder should make these pass:

```text
normalization_accounts_for_every_input_field
unsupported_field_is_preserved
partial_inventory_cannot_imply_deletion
duplicate_display_names_do_not_collide
source_id_is_preserved_in_adoption_map
assignments_and_exclusions_are_not_dropped
filter_relationship_is_not_dropped
existing_writer_conflict_blocks_generation
rerun_is_idempotent
cancel_performs_no_external_operation
back_invalidates_dependent_answer
changed_export_invalidates_resume_stage
changed_provider_lock_invalidates_mapping
wrong_stack_is_rejected
wrong_tenant_is_rejected_before_write
emit_only_never_executes
powershell_renderer_preserves_argument_values
bash_renderer_preserves_argument_values
terminal_control_characters_are_sanitized
secrets_are_not_serialized_into_session
unsupported_provider_version_fails_closed
```

Then add provider-backed disposable-fixture checks separately.

### One especially important provider regression test

Because msgraph v0.5.0 specifically fixed nested-object update behavior that could otherwise reset omitted siblings, create a fixture explicitly covering a complex nested value. [^source-02]

For example:

```text
observed nested object:
    A = 1
    B = 2
    C = 3

desired change:
    B = 4

acceptance:
    outgoing desired/update representation does not unintentionally erase A or C
```

That test is much more useful than a generic “provider works” assertion.

## Builder-ready work plan and assurance ladder

### Thin slice first

The builder should proceed in this sequence:

**Fixture and contracts first.** Create a synthetic Settings Catalog export containing multiple assignments, one exclusion or filter, service-owned fields, a deliberately unsupported field, and a duplicate-name decoy. Write failing deterministic tests around field accounting and identity.

**Normalizer second.** Produce the observed canonical representation and coverage report. No HCL yet.

**Provider capability map third.** Pin the selected provider; inspect its schema/import implementation and official Graph API. Map every normalized field and relationship.

**Generation fourth.** Generate a minimal repository-aware Atmos/OpenTofu component without overwriting unrelated files.

**Command cards fifth.** Implement emit-only PowerShell/Bash rendering from structured operations.

**Wizard integration sixth.** Add the guided conversational stages, resume state, back/edit/cancel, and provenance display.

**Offline acceptance seventh.** Run parser/schema/unit/golden-file/PTY tests.

**Provider-backed disposable testing eighth.** Only under a separate authorized test contract.

**Agent evaluations ninth.** Compare no skill, strongest upstream composition, proposed skill, and proposed skill plus helper/enforcement using the same model/tools/budget.

This ordering prevents the model prompt from being optimized before the deterministic product has a stable contract.

### Assurance labels

The builder should never reduce all evidence to “works”:

| Status | Meaning |
|---|---|
| **Acquired** | Exact source/material has been obtained. |
| **Reviewed** | Relevant implementation and dependencies were inspected. |
| **Syntax-checked** | Parser/compiler/schema accepts it. |
| **Fixture-tested** | Deterministic synthetic tests passed. |
| **Provider-tested** | Qualified provider behavior was tested in a disposable environment. |
| **Host-tested** | Claude Code/Codex packaging and interaction were actually exercised. |
| **Behaviorally evaluated** | Agent comparison was run against protected cases. |
| **Live-qualified** | Separately authorized real Azure/Intune behavior was observed. |
| **Blocked** | Prerequisite exists but is unavailable/not authorized. |
| **Unsupported** | Current selected implementation cannot satisfy it. |

A provider document is evidence for documented capability, not `Provider-tested`. A generated transcript is `Authored`, not `Host-tested`.

### Runtime ZIP versus research/evaluation material

Build three outputs:

```text
dist/
├── microsoft-cloud-iac-plugin.zip
├── microsoft-cloud-iac-evaluation.zip
└── microsoft-cloud-iac-provenance.zip
```

The **runtime ZIP** may include:

```text
skills
router
schemas needed at runtime
deterministic helper
safe templates
small synthetic examples
README
license/notices
```

It should not include:

```text
golden hidden answers
reference-solution replay material
production exports
live state
saved production plans
tokens
credential caches
private logs
restricted device evidence
decompiled proprietary binaries
personal absolute paths
```

### Acceptance criteria for the eventual plugin ZIP

The builder should not release the ZIP until these are true:

```text
[ ] Clean extraction succeeds on Windows and Linux.
[ ] No archive path escapes the extraction root.
[ ] Plugin/skill manifests validate against the current host specs.
[ ] Every runtime relative reference resolves.
[ ] No hidden installation/download happens during ordinary inspection.
[ ] Offline brownfield fixture works without Azure/Graph credentials.
[ ] Existing object IDs survive normalization and generation.
[ ] Every input field is classified.
[ ] Unsupported fields remain visible.
[ ] Assignments/exclusions/filters survive the supported fixture.
[ ] Re-running generation is idempotent.
[ ] Back/edit/cancel/resume behavior has deterministic tests.
[ ] PowerShell command cards pass quoting fixtures.
[ ] Bash command cards pass quoting fixtures.
[ ] Emit-only never executes generated commands.
[ ] Wrong stack/tenant/version fixtures fail before consequential operations.
[ ] OpenTofu is retained as the enterprise execution engine.
[ ] Atmos is retained where the repository uses Atmos.
[ ] No adoption workflow silently performs functional cleanup.
[ ] Source/provenance and third-party notices are complete.
[ ] Actual tests run are recorded rather than inferred.
```

## Open questions and incomplete material

The most important unresolved item is **your actual existing repository/provider combination**. The wizard is specifically intended to inspect that at runtime, so the research should not invent it. The organizational input template should ask only for non-secret facts such as:

```yaml
repository:
  path: null

approved_engine:
  name: opentofu
  pinned_version: null

atmos:
  version: null

providers:
  lockfile_is_authoritative: true

targets:
  tenant_id: null
  cloud: null
  azure_subscription_ids: []

ownership:
  existing_writers: []

intune_input:
  export_format_or_path: null

delivery:
  protected_ci_system: null
  approval_policy_reference: null

evidence:
  approved_service_side_sources: []
  approved_endpoint_sources: []
```

It should **not** ask for secrets in this file.

The exact first production provider also remains an environment decision. `microsoft/msgraph` is a strong reference implementation for the first fixture because Microsoft publishes it and provides Graph Terraform guidance, but it remains preview in the current Microsoft documentation, and provider behavior has changed materially across releases. [^source-12] The builder should also qualify whatever provider your existing repository already uses before attempting to change the provider architecture.

The complete `terraform-dsoxlab-training` per-lab `catalog-manifest.json` was **not completed in this research pass**. The repository revision identified in the research should be enumerated by the builder from `meta.yml` and every Terraform `lab.yaml`; the learner path/reference-replay separation should be verified from the pinned runner rather than inferred from an advertised “88 labs” count. The documented dsoxlab model supports this distinction and explicitly describes learner checking as separate from instructor solution replay. [^source-11]

The complete current Claude Code, Codex/OpenAI plugin, Agent Skills, and Plugin Eval manifest/schema matrix also still needs to be pinned by the computer-access builder before packaging. That is intentionally a packaging-stage requirement: host formats evolve, and an illustrative manifest copied from a previous report should not be treated as a current executable contract.

No live Azure/Graph authentication, Intune export, provider-backed plan, state import, endpoint collection, dsoxlab execution, or agent A/B benchmark was performed as part of this research. Therefore none of those activities should be marked `passed` in the builder's material-status file.

The strongest implementation handoff is:

> **Build the local loss-aware brownfield pipeline first.** Start from a synthetic existing Settings Catalog policy with real identity and assignment complexity. Prove that the tool can account for every source field, preserve IDs and relationships, map only supported capabilities, generate repository-aware OpenTofu/Atmos code, emit safe PowerShell/Bash command cards, and resume deterministically. Then connect that thin slice to the pinned Microsoft Graph provider in a disposable environment. Only after those deterministic pieces work should the agent prompts be optimized and evaluated.

That path produces the “wizard” you described: **the LLM asks the questions that require engineering judgment, deterministic code handles the things that must not be guessed, Atmos/OpenTofu remain the deployment path, and Azure/Intune evidence determines whether the work actually succeeded.**

---

## Exported source references

Packaging note: the report text above is preserved in full. ChatGPT citation markers have been converted to Markdown footnotes using the source links embedded in the original report export. References without a resolvable link are explicitly marked. This packaging step did not re-run the research or re-verify its technical claims.

[^source-01]: [Create and deploy your first Terraform configuration with Microsoft Graph resources - Microsoft Graph Terraform | Microsoft Learn](https://learn.microsoft.com/en-us/graph/templates/terraform/quickstart-create-terraform?utm_source=chatgpt.com); [Create a policy using settings catalog in Microsoft Intune - Microsoft Intune | Microsoft Learn](https://learn.microsoft.com/en-us/intune/device-configuration/settings-catalog/?utm_source=chatgpt.com).

[^source-02]: [terraform-provider-msgraph/CHANGELOG.md at main · microsoft/terraform-provider-msgraph · GitHub](https://github.com/microsoft/terraform-provider-msgraph/blob/main/CHANGELOG.md?utm_source=chatgpt.com).

[^source-03]: [Importing a group member to `msgraph_resource` replaces the resource · Issue #91 · microsoft/terraform-provider-msgraph · GitHub](https://github.com/microsoft/terraform-provider-msgraph/issues/91?utm_source=chatgpt.com).

[^source-04]: [Releases · cloudposse/atmos · GitHub](https://github.com/cloudposse/atmos/releases?utm_source=chatgpt.com); [atmos/CLAUDE.md at main · cloudposse/atmos · GitHub](https://github.com/cloudposse/atmos/blob/main/CLAUDE.md?utm_source=chatgpt.com).

[^source-05]: [Create and deploy your first Terraform configuration with Microsoft Graph resources - Microsoft Graph Terraform | Microsoft Learn](https://learn.microsoft.com/en-us/graph/templates/terraform/quickstart-create-terraform?utm_source=chatgpt.com).

[^source-06]: [Create a policy using settings catalog in Microsoft Intune - Microsoft Intune | Microsoft Learn](https://learn.microsoft.com/en-us/intune/device-configuration/settings-catalog/?utm_source=chatgpt.com).

[^source-07]: [Common Education privacy configuration - Microsoft Intune | Microsoft Learn](https://learn.microsoft.com/hr-hr/intune/solutions/education/tutorial-school-deployment/ref-privacy-settings-windows?utm_source=chatgpt.com).

[^source-08]: [Releases · cloudposse/atmos · GitHub](https://github.com/cloudposse/atmos/releases?utm_source=chatgpt.com).

[^source-09]: [atmos/CLAUDE.md at main · cloudposse/atmos · GitHub](https://github.com/cloudposse/atmos/blob/main/CLAUDE.md?utm_source=chatgpt.com).

[^source-10]: [GitHub - microsoft/terraform-provider-msgraph · GitHub](https://github.com/microsoft/terraform-provider-msgraph?utm_source=chatgpt.com).

[^source-11]: [linux-dsoxlab-training/README.md at main · stephrobert/linux-dsoxlab-training · GitHub](https://github.com/stephrobert/linux-dsoxlab-training/blob/main/README.md?utm_source=chatgpt.com).

[^source-12]: [Create and deploy your first Terraform configuration with Microsoft Graph resources - Microsoft Graph Terraform | Microsoft Learn](https://learn.microsoft.com/en-us/graph/templates/terraform/quickstart-create-terraform?utm_source=chatgpt.com); [terraform-provider-msgraph/CHANGELOG.md at main · microsoft/terraform-provider-msgraph · GitHub](https://github.com/microsoft/terraform-provider-msgraph/blob/main/CHANGELOG.md?utm_source=chatgpt.com).
