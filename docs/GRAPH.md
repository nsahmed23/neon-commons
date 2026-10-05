# Offline relationship graph

`graph_contract.py` defines the 23 supported predicates' endpoint types, allowed statuses and conditional cardinalities. `graph_validation.py` validates graph instances against those contracts and dedicated preservation/provenance rules. The six fixed queries project validated evidence; they do not infer membership, authenticate provenance or grant execution authority. Missing relationships remain explicit unknowns.

`build_graph(input_path, context_path=None, atmos_root=None)` returns a JSON graph with typed `nodes`, directed `edges`, byte-backed `sources`, `coverage`, `issues`, and a canonical `graph_digest`. It reads local files only. It does not invoke Atmos, YAML functions, a shell, a provider, or Microsoft Graph.

The current whole-capture projection is bounded before per-policy normalization: at most 10,000 JSON nodes and 64 unique candidate policies, with at most 100,000 source-node/policy visits and 8 MiB of source-bytes/policy work. The first exceeded limit rejects the complete graph request; it never truncates inventory. Larger estates require an indexed or qualified batching adapter. Stored graph queries also reject when nodes multiplied by the sum of edges, coverage and source rows exceeds 2,000,000, before digest verification or relational scans. Relationship target lookups use an adjacency index. These are explicit current support limits, not estate-wide scalability qualification.

Policy identity uses cloud, tenant UUID, resource family, and object UUID. Assignment identity adds the policy and source assignment key. The historical `assignment_uuid` field preserves that key, which can be an opaque string in production captures; group and filter relationships still require UUIDs. Display names are labels, so policies with identical names remain distinct. Supported cloud labels are `public`, `usgovernment`, `dod`, and `china`; an unrecognized cloud receives an opaque distinct scope. Only the public-cloud bounded mapping is qualified by the reference core. Tenant identity has `identity_assurance: source_asserted`: a capture's tenant field is not authentication evidence.

The graph uses the repaired reference normalizer's closed safety projection. Supported settings expose their normalized instance, definition, digest, and pinned provider mapping. Unsupported settings and unknown fields stay in the input file; the graph carries safe blocker codes and opaque pointers. It never copies raw unsupported records, error bodies, auth configuration, environment values, or YAML tag payloads into a review artifact. Provenance identifies an artifact SHA-256 and a JSON pointer, or YAML line and column. A record from a failed HTTP page cannot receive a successful page's provenance.

The exact `intune-iac-settings-catalog-graph` 1.0.0 capture exporter uses the production projection and its independent preservation oracle. Its source artifact records the adapter scope; tenant identity still remains source asserted. Direct assignment `source` and `sourceId` annotations survive as `assignment_source` and `assignment_source_id` when present. Policy-set assignments remain unsupported and carry opaque blockers instead of being flattened into direct assignments. Production setting IDs outside the graph's bounded setting schema are omitted with `graph_setting_projection_unsupported`; their original observation remains in the restricted source capture. Production provider mappings are explicitly unqualified, and complete collection coverage establishes capture completeness only.

Assignments preserve `target_type`, inclusion versus exclusion, group UUID, filter UUID, and filter mode. `includesGroup`, `excludesGroup`, and `usesFilter` are different predicates. Reference coverage describes captured group/filter references, not live membership or device rollout. A missing, denied, malformed, or incomplete collection has `status: unknown`. Only a successful, complete capture contract yields `complete`; an empty unknown collection never means no assignments. Tenant inventory coverage independently rejects invalid/duplicate policy identities and declared collection counts that do not equal the captured total.

For the known production capture adapter, tenant inventory independently validates the exact trusted initial URL and follows the complete returned continuation URL, including its query. It rejects wrong origins/routes, dropped query bytes, failed responses, loops and missing tails. The legacy synthetic adapter retains its narrower continuation-query contract. Neither chain establishes source authenticity or transactional freshness.

The bounded assignment contract allows filters on inclusion targets only. Exclusion targets must use `filter_mode: none` with no filter reference; a recomputed graph digest cannot make a filtered exclusion valid.

## Fixed read API

`query_graph(graph, query, subject=None)` returns a detached JSON projection. It checks the graph's closed field shape, supported setting schema, predicate endpoint types, assignment/group/filter consistency, and digest before answering. These checks detect malformed or contradictory artifacts; the digest is recomputable and does not authenticate the producer. No arbitrary query language is accepted. Policy, assignment and setting-explanation queries retain selected-policy blocker evidence. Ambiguous assignment keys are omitted from known assignment projections, with UUID-case duplicates treated as the same identity and their source blockers retained. Dependency queries retain unresolved declaration nodes and their diagnostic evidence; an unresolved selector is not presented as an empty dependency set. Their completeness and execution order remain unknown.

| Query | Subject | Result |
|---|---|---|
| `policies` | Optional exact Policy node ID or unambiguous policy UUID | Policy inventory and policy capture coverage |
| `assignments` | Optional exact Policy node ID or unambiguous policy UUID | Assignment semantics, reference edges, and assignment coverage |
| `why-setting` | Required SettingValue node ID | Safe normalized setting, definition, provider mapping, and source origin |
| `impact` | Required exact node ID | Reverse relationship closure, its source evidence, and graph issues; completeness remains unknown |
| `dependencies` | Optional ComponentInstance node ID | Declared dependencies and effective literal dependency targets, including selector provenance; execution order is not established |
| `placement` | Optional Policy node ID/UUID, or ComponentInstance node ID | Policy placement intent, declaration placement, or resolved physical stack, configuration evidence, implementation presence, and source artifacts |

An absent subject is an error for `why-setting` and `impact`. Unknown or ambiguous subjects fail. Use returned node IDs for exact reads. `placement` with no subject lists policy placement intents. A context file's component/stack names are declared intent; they do not resolve an Atmos stack or verify a cloud target.

## Static Atmos projection

The inspector composes YAML syntax nodes with `yaml.SafeLoader`; it does not construct YAML objects or invoke tag handlers. It inspects at most 512 `.yaml`/`.yml` files, 2 MiB per file, and 16 MiB total under the selected local root. Symlink files and imports outside that root are not followed. YAML node depth is bounded, duplicate keys fail, and aliases, YAML merge keys, tags, and template expressions produce unresolved issues. Template file execution is unavailable.

A `ManifestDeclaration` and `StackDeclaration` identify a physical declaration file. A filename is never presented as a resolved logical stack name. Local repository scope is a digest of the selected absolute root; moving the project changes that local scope. Source artifacts additionally bind exact paths and bytes. No repository revision or native resolver identity is guessed.

A `ComponentDefinition` identifies a declared implementation path within that local repository scope and component kind. A `ComponentInstance` identifies a named declaration within one manifest's stack declaration. Several instances can share one definition. These nodes describe source declarations, not resolved deployment instances.

Ordered imports have `ImportOccurrence`, `hasImport`, `resolvesToManifest`, and `imports` facts. Literal imports use both static `base_path` (default `.`) and `stacks.base_path` (default `stacks`) in `atmos.yaml`, or the importing file's directory for `./` paths. A dynamic or invalid configured base produces an unresolved import instead of falling back to a different existing file. No import overlay is merged. Import options beyond a literal `path` remain unresolved. Mapping key types are checked on the original YAML nodes so non-string keys cannot disappear before this boundary check.

`metadata.inherits` produces ordered `inheritsConfigurationFrom` facts when the parent is explicitly declared in the same manifest and component kind. An inherited declaration available only after import merging remains unresolved. `metadata.component` produces a separate `usesImplementation` relation; inheritance does not change implementation identity. Legacy top-level `component` syntax remains unqualified.

For the v1.199.0 declaration adapter, `settings.depends_on` is a keyed map. Only a selector containing exactly one literal `component` field produces a same-manifest `declaresDependencyOn` edge. Selectors with any other field, including unknown fields or non-string YAML keys, are retained as dependency declarations with unknown resolution and an unresolved diagnostic. `metadata.depends_on` is unrecognized; newer `dependencies` syntax requires a separately qualified adapter. Import, inheritance, and declared dependency predicates are never collapsed into execution ordering. Import and inheritance cycles are reported without recursion or execution.

Component config assignments retain section, opaque key digest, and source origin. Values in env, auth, backend, providers, and vars are not exposed. Dynamic tags and templates remain unknown without displaying their payloads. Static declaration nodes keep `resolution_status: unknown`, including projects with entirely literal YAML. The declaration inspector itself does not establish overlay semantics, CLI configuration, discovery, list merge strategy, backend/workspace identity, binary/toolchain evidence, or actual tenant/principal observations.

## Bounded effective configuration

When the selected root has a supported `atmos.yaml`, graph construction also uses the offline repository discovery and configuration resolver. This resolves the supported literal subset, not native Atmos execution. Dynamic or unsupported repositories retain their static declaration evidence. The graph does not promote templates to effective configuration facts.

Resolved physical stacks have separate `EffectiveStack` nodes. Their identity uses the local repository scope and path without the YAML extension beneath the configured stack base. A tenant label never identifies a stack or authenticates an Intune tenant. An effective `ComponentInstance` has its own identity, `status: derived`, and `resolution_status: resolved`; the source declaration instances remain separate and unknown. An imported component therefore becomes an effective instance in each selected physical stack without changing the catalog declaration's identity.

The relationship `ComponentInstance → hasEffectiveConfiguration → EffectiveConfiguration → usesImplementation → ComponentDefinition` connects a selected instance to its effective configuration digest, source fingerprint, selection fingerprint, and implementation evidence. `belongsToEffectiveStack` identifies its physical placement. `derivedFrom` connects configuration evidence to `ResolutionSource` nodes and byte-backed artifacts. These artifacts cover the resolver's input inventory; they are not a claim that every input contributes a winning value. The derived implementation definition reports the configured directory and `implementation_presence: present` or `missing`. Configuration resolution remains valid when that directory is missing, and it never grants execution authority.

Effective `settings.depends_on` entries have separate `EffectiveDependency` nodes. `hasEffectiveDependency` links each to configuration evidence. An implicit same-stack literal component selector gets a `dependsOn` edge only when its target is another resolved instance in the same physical stack and both components have matching known `namespace`, `tenant`, `environment`, and `stage` values. Those context values must each be a string or absent; null or structured values remain unknown. The graph retains only a context digest and an equality result. Explicit stack selectors remain unknown because a physical manifest selector does not establish Atmos logical stack identity. Explicit context selectors and missing targets also remain unknown. Dependency origins refer to the winning source artifact and opaque source pointer; selector map keys and raw configuration values are not published. These relationships establish configuration references, not an execution schedule or verified rollout order.

The graph publishes structural evidence only: it excludes effective vars, env, backend, auth, provider, and custom payloads. Configuration digests are integrity references, not authentication or confidential storage. The closed validator checks effective node identities, typed edge endpoints, required evidence relationships, source and selection fingerprint bindings, and consistent resolution claims. Its recomputable graph digest cannot authenticate the producer or establish that the local files still match. `execution_authorized` remains false, and tenant verification and execution order remain `not_established`. Abstract configuration parents remain declaration evidence; they are not projected as selectable effective instances.

Top-level Atmos resolution is `resolved` when all projected Terraform selections resolve without discovered stack failures, `partial` when some resolve but another selection or discovered stack is blocked, and `unknown` when no supported effective selection is available. A blocked manifest stays in this accounting even if its components could not be enumerated. Coverage for static stack declarations stays unknown; bounded effective configuration coverage is recorded separately on resolved instances.

Example Python use:

```python
from intune_iac.graph import build_graph, query_graph

graph = build_graph('capture.json', 'context.json', './project')
assignments = query_graph(graph, 'assignments', '22222222-2222-4222-8222-222222222222')
settings = [n for n in graph['nodes'] if n['type'] == 'SettingValue']
if settings:
    explanation = query_graph(graph, 'why-setting', settings[0]['id'])
```

The shipped tests cover identity scopes and equal labels, inclusion/exclusion/filter preservation, denied coverage, failed-page provenance, unsupported secret retention, byte-backed setting explanations, fixed query validation, edited graph rejection, distinct Atmos predicates and instances, dynamic dependencies, import/inheritance cycles, opaque dynamic values, YAML merges, declared impact, unresolved placement, effective imported instances, winning dependency provenance, unknown logical stack selectors, mismatched or unknown dependency context, implementation absence, and inconsistent effective claims after digest recomputation.
