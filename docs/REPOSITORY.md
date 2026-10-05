# Repository discovery and literal configuration resolution

`intune_iac.repository` reads a local Atmos repository without invoking Atmos, an
engine, a provider, authentication, templates, functions, or network services.
Its adapter is `atmos-literal/1.0`, based on selected source units from Atmos
**v1.199.0**, commit `10886fe5b17f034c01e2396c0c47de19575a8065`.
It implements the subset below; it is not a qualified Atmos binary or a complete
replacement for `atmos describe component`.

## Selecting a repository target

```python
from intune_iac.repository import discover_repository, resolve_component, public_resolution

inventory = discover_repository('/path/to/repository')
internal = resolve_component('/path/to/repository', 'deploy/dev', 'policy')
summary = public_resolution(internal)
```

The root must contain `atmos.yaml`. The `stack` argument is the physical manifest
path relative to the configured stack base, **without** `.yaml` or `.yml`:
`stacks/deploy/dev.yaml` becomes `deploy/dev`. It is not the Atmos logical stack
name derived from context variables. A literal `stacks.name_pattern` can be
present but is not evaluated. `logical_stack_identity` remains `unknown`.
Atmos `vars.tenant`, `vars.environment`, and cloud labels do not establish Entra
tenant, principal, backend, or deployment identity.

The module intentionally reads only repository-local configuration. System,
home, environment, CLI flags, and other Atmos configuration layers are not
consulted: `runtime_config_layers` is `not_evaluated`. Neither successful
resolution nor an existing implementation directory authorizes execution.
Every response has `execution_authorized: false`.

## Response contracts

Both APIs return `schema_version: "1.0"`, `adapter`, absolute `root`,
`source_fingerprint`, `sources`, `blockers`, `execution_authorized`,
`stack_identity: "physical_manifest_selector"`, `logical_stack_identity`,
`tenant_verification: "not_established"`, `runtime_config_layers`, and
`evaluation_scope: "repository_local_literal_configuration"`.

`discover_repository(root)` returns:

- `status`: `discovered` when the bounded inventory was read, otherwise `blocked`.
- `stacks`: entries with `stack`, repository-relative `manifest`, `status`,
  `blockers`, and `components`.
- Component entries: `name`, `kind` (`terraform` or `helmfile`), `status`,
  `implementation` (alias/path from selected metadata), `selectable`, `blockers`.

Discovery includes components contributed by imported manifests. Abstract
components remain visible but are not selectable. A duplicate component name
across Terraform and Helmfile is ambiguous because the selection API has no kind
argument; both candidates are blocked. A discovered repository can contain
blocked stacks/components alongside selectable ones: inspect their nested
statuses and blockers. Discovery never returns vars, env, settings, provider
configuration, or other arbitrary configuration values.

`resolve_component(root, stack, component)` returns:

- `status`: `resolved` or `blocked`; requested `stack`, `component`; `kind` and
  `implementation` when established.
- `effective` **only for a fully supported literal selection**: `vars`, `env`,
  `settings`, `command`, selected `metadata`, plus `providers` for Terraform.
  These are configuration sections within this adapter's scope, not the full
  native Atmos describe output.
- `provenance`: effective JSON Pointer → `{winner, history}`. Each origin has
  repository-relative `path`, source JSON `pointer`, 1-based `line` and `column`.
  History lists earlier and winning declarations in merge order, without values.
  Entire list replacements have history on the list field; only winning list
  elements remain. The built-in command default uses synthetic origin
  `atmos-literal/1.0`, `/defaults/command`, line/column 0.
- `implementation_path`: repository-relative directory; `implementation_exists`:
  whether it is a directory. Its absence does not prevent configuration analysis.
  Directory existence does not prove valid HCL, provider compatibility, or a
  runnable component.
- `abstract`: selected metadata type is `abstract`; `selection_fingerprint` binds
  the source fingerprint, physical stack, kind, and component.

**Internal effective configuration can contain credentials.** CLI, MCP, wizard,
and other display/export callers must use `public_resolution(report)`. This
projection removes `effective`, adds its `configuration_sha256`, and returns
`effective_fields` as sorted provenance pointers. Values never appear in
provenance or blockers. Source paths, component/implementation names, and field
names are visible; do not put secrets in these identifiers.

## Supported semantics

| Area | Supported behavior |
|---|---|
| CLI config | `base_path`; `stacks.base_path`, `included_paths`, `excluded_paths`, literal `name_pattern`; `components.terraform`/`helmfile` base paths and command; literal boolean `apply_auto_approve` and `auto_generate_backend_file` are accepted declarations only; `settings.list_merge_strategy: replace` |
| Discovery | `.yaml`/`.yml` stack manifests; include/exclude patterns with `*`, `**`, `?`, with `**/` matching zero or more directories; patterns match filenames or extensionless physical selectors; default includes `**/*` |
| Imports | Ordered literal string paths or `{path: literal}`; normal imports relative to stack base; `./` imports relative to importing manifest; optional extension resolved `.yaml`, then `.yml`; later imports override earlier imports, local manifest last |
| Global configuration | Root then component-type `vars`, `env`, `settings`; Terraform providers start at `terraform.providers`; type-global command |
| Inheritance | Recursive ordered `metadata.inherits` within the fully imported manifest; later parents override earlier ones, then the selected component's direct sections |
| Component overrides | Selected component's `overrides.vars/env/settings/command`, plus `overrides.providers` for Terraform, applied last; parent overrides are not inherited |
| Implementation | Selected `metadata.component`, otherwise selected component name; parent metadata does not propagate through `inherits` |
| Merge | Recursive mapping merge; same-type scalar replacement including empty string/zero/false; lists replace entire lists including `[]`; `{}` preserves existing map children; null replaces a leaf/container and a non-null value replaces null |
| Command | Configured component-type command, type-global command, inherited command, own command, own overrides command; default engine-kind string; no binary/version qualification |
| Dependency declarations | Literal `settings.depends_on` data is preserved as configuration; resolution does not schedule components or verify dependency identities |

A component's metadata is not inherited from base components. Import overlays
can still extend the same named component's metadata, just like its other
literal declarations. Unknown fields are never silently discarded to produce a
successful result.

## Explicit unknowns and boundaries

A blocked report omits effective values and carries diagnostics shaped
`{code, status: "unknown", path?, pointer?}`. It does not include source text or
exception messages. Among the blockers:

- Go/environment template expressions (`{{`, `{%`, `${`), template manifests,
  custom YAML tags/functions, YAML aliases/merge keys, duplicate/non-string keys,
  multiple YAML documents, non-finite/exotic scalars. Booleans must be
  `true`/`false`; numbers use the narrow JSON-compatible forms accepted by the
  parser. Quoted strings remain strings.
- Glob imports, import contexts/flags, absolute/parent-traversing import paths,
  missing imports/parents, and import/inheritance cycles. If an explicit YAML
  import has a `.tmpl` sibling, the template is recognized and blocked.
- Unsupported CLI config, name templates, append/merge list strategies, unknown
  manifest/component/type fields, legacy top-level `component`, root/type
  overrides, backend/remote-state processing, auth, hooks, and settings
  `integrations`/`spacelift` transformations.
- Non-null type-changing merges. Literal null is supported within configuration
  values, but a required mapping section such as `vars: null` remains invalid.
  Empty-value behavior is qualified by native fixtures, rather than inferred
  solely from Mergo options.

YAML validation covers each selected/imported document in full, so a dynamic
value elsewhere in that document blocks its selection. An unrelated unselected
manifest is fingerprinted without evaluating its contents and does not block an
otherwise supported target. This does not claim runtime configuration parity,
verified tenant/cloud/principal identity, state identity, engine/provider version
selection, or an execution dependency graph.

## Containment, bounds, and invalidation

All configured roots, imports, and implementation paths remain within the
selected repository. Symlinks in traversed source paths and nonregular source
files are rejected. Parent traversal and absolute configured paths are blocked.
Scans skip `.git`, `.terraform`, `.cache`, `node_modules`, and `__pycache__`.

The inventory includes `atmos.yaml`, stack `.yaml`/`.yml` and template files, and
`.tf`, `.tf.json`, `.terraform.lock.hcl` files beneath configured/default component
roots. HCL is hashed, never evaluated. Other repository files and runtime/session
JSON are outside this inventory. Limits: 512 source files, 2 MiB per source,
16 MiB total, 20,000 traversed entries, depth 64, 100,000 parsed YAML value nodes,
400,000 merge visits, 2,048 provenance history entries per field, and 800,000
aggregate history entries allocated during merges.

`sources` is sorted by repository-relative path and contains `{path, sha256}`.
The source fingerprint is the canonical JSON SHA-256 digest of:

```json
{"adapter":"atmos-literal/1.0","sources":[{"path":"atmos.yaml","sha256":"..."}]}
```

`selection_fingerprint` is the digest of
`[source_fingerprint, stack, kind, component, implementation_path, implementation_exists]`.
The final two fields bind the selected directory claim even when the directory
contains no inventoried files. Action-runner repository evidence additionally
binds the public discovery structure, so creating or removing a component
directory invalidates a prior proposal. The file-only `source_fingerprint`
continues to describe bytes and does not change for an empty directory alone.
Changes to imported files,
implementation HCL/locks, and inventoried file additions/removals invalidate the
source fingerprint. The whole inventory is used conservatively, including
unselected manifests. Fingerprints establish byte consistency, not authorship,
approval, or live-state freshness.

## Source basis and validation

The implementation follows the pinned `stack_processor_utils.go` import/base
component order, `stack_processor_process_stacks.go` root/type merges,
`stack_processor_process_stacks_helpers_inheritance.go` metadata rules,
`stack_processor_process_stacks_helpers_overrides.go` selected overrides, and
`pkg/merge/merge.go` default list strategy. Unsupported backend/auth/integration
paths are blocked instead of approximated.

An isolated, socket-denied Atmos 1.199.0 qualification run additionally confirmed
empty/null behavior at import, parent-to-child, and child-to-override boundaries:
`[]`, `""`, `0`, `false`, and `null` replace earlier values; `{}` preserves map
children. Scalar/list/map ↔ null transitions were qualified separately. The
binary SHA-256 was
`8e4b057f0cf38686c5eb61db57c8291027a22dfc4ce54a806dc83b34aa96757b`.
Receipts are named `atmos-empty_values.json` and
`atmos-empty-supplement-summary.json`; these tests are narrow fixture evidence,
not general runtime compatibility or permission to invoke Atmos through this
module. The module itself never invokes native tools.

`atmos-python-comparison.json` records 11 exact-input native-versus-Python
comparisons: ten equal effective `vars` maps and one matching type-conflict
rejection. The prepared corpus removes runtime-only CLI configuration outside
this adapter's scope; one generated YAML alias is expanded into duplicate literal
mapping content. Original and prepared hashes are both retained. Native and
Python then consume the same prepared file bytes, with native source hashes and
unchanged-source checks included in each comparison. This qualifies the tested
literal cases only, not backend/auth/identity or complete Atmos output.

`plugin_tests/test_repository.py` covers import and inheritance order, scoped
and own overrides, nested winning provenance, list replacement, parent override
exclusion, missing/cyclic declarations, dynamic/tagged/aliased input, discovery
patterns, fingerprint changes, secret-free summaries, and filesystem/input
bounds. The first run failed because the module did not yet exist. No native
Atmos, Terraform/OpenTofu, cloud, or state operation is used by these tests.

## Pinned native context comparison

`repository native --root REPO --stack PHYSICAL --component COMPONENT --executable /absolute/atmos`
now invokes the exact Linux AMD64 Atmos 1.199.0 executable after independent
literal-subset admission. It creates a disposable source snapshot, disables
functions and templates, removes inherited configuration and credentials, denies
network sockets with seccomp, bounds process time/output, and independently
compares effective vars/env/settings/providers and physical/logical component
identity. An explicit supported `stacks.name_pattern` is required. Workspace
and backend outputs are recorded as digests; this does not authenticate either.

The adapter rejects dynamic repositories rather than executing their hooks or
expanding this support boundary. It is not an OS filesystem isolation service
against a compromised process owner. See `research/completion/native-atmos-measured.json`
for the measured comparison; full enterprise configuration-layer parity remains open.
