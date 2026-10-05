# Bounded Graph capture candidates

The plugin's `inspect`, `generate`, and wizard paths now dispatch explicitly to production mapping contract `production-1.2.0` only when the export has `synthetic:false` and exporter `intune-iac-settings-catalog-graph@1.0.0`. Synthetic reference mapping remains unchanged. Other exporters remain unqualified review inputs; changing one Boolean does not qualify them.

This is an offline proposal, not general Settings Catalog support, provider validation, or tenant qualification. Candidate generation never runs OpenTofu, Terraform, Atmos, authentication, an import, a plan, or an apply. Every Terraform candidate ends in `.tf.txt`. No executable command cards are produced. Candidate HCL contains an impossible execution precondition as an additional guard; renaming a file does not establish qualification.

## Supported proposal

The bounded configuration proposal accepts exactly one Windows 10 / MDM policy and one existing worked privacy choice setting:

- Definition: `device_vendor_msft_policy_config_privacy_letappsaccesslocation`.
- Choice: `device_vendor_msft_policy_config_privacy_letappsaccesslocation_2`.
- Empty choice children, with absent or null template references.
- Original setting ID `0`, retained unchanged. No setting ID is rewritten or renumbered.
- Explicitly observed `source:direct` group assignments and group exclusions, including explicit include/exclude filters on included groups. Filter mode `none` requires an absent/null filter ID; filtered exclusions and all other target shapes remain unsupported.

The selected policy, settings and assignments collections must each have a verified complete chain. Validation begins at the fixed public beta collection root, follows each exact returned same-route nextLink, and requires the final page to omit nextLink. Returned `$skip` links are preserved verbatim. Missing, denied, failed or truncated assignment reads cannot turn into an empty assignment list. A complete successful `value:[]` does preserve an empty assignment list.

When supplied, each collection `@odata.count` must agree with the total captured rows across the complete chain. The selected policy's `isAssigned` must agree with whether assignment rows were observed. Contradictions block a candidate; they may indicate incomplete or changing capture evidence and do not prove a service defect. UUID case differences cannot hide duplicate policy/assignment identities or assignment targets. The original spelling is preserved in observations and configuration.

Wrapper `@odata.type` is optional because the collection route identifies the wrapper resource type. If supplied, its exact supported spelling is checked and preserved. Nested setting/value annotations remain required with the `#microsoft.graph.` spelling; this release does not normalize alternate spellings. Policy template metadata may be absent, null, or an empty template reference with `templateFamily:none`. The documented template annotation with or without `#` is accepted without modifying it.

Safe component, stack and implementation selectors may contain slash-separated ASCII alphanumeric, underscore and hyphen segments. Absolute paths, dots, parent traversal, interpolation and control characters are rejected. A supplied engine/provider version must equal the pinned proposal. Repository context may omit these versions: the candidate itself explicitly proposes OpenTofu 1.10.0 and `deploymenttheory/microsoft365` 1.0.0, without claiming they were detected or installed.

## Resource budget

The production mapper accepts at most 10,000 JSON nodes in the entire export, including every container, scalar, unselected policy and metadata value. The producer and independent oracle check this limit before constructing per-node lineage. The existing 16 MiB input/file limits also remain in force. Exceeding the node budget returns `capture_node_limit` before output is written. A small input containing many tiny values can otherwise expand into a much larger review ledger.

Keep complete captures intact. Do not truncate records, remove pages, filter the fixed initial root or relabel incomplete evidence to fit the budget. Larger inventories require a separately qualified batching or streaming adapter with its own complete capture boundary; this release does not supply that adapter.

## Observation, configuration, request and state

| Layer | What the review records |
| --- | --- |
| Observation | Supported record fields exactly as supplied, including opaque setting IDs and null/absent distinctions. Unrecognized record shapes use an empty observation object plus a blocker and source digests. |
| Configuration proposal | Known provider-facing fields and settings wrapper, with original setting IDs unchanged. It exists only if all mapping gates pass. |
| Request projection | `not_constructed`. Reviewed provider constructor evidence says it does not copy configuration setting IDs; serializer and request behavior are not qualified. No generated request body is claimed. |
| State expectations | Original observed setting IDs plus `unqualified` / `roundtrip_verified:false`. Refresh equivalence is not asserted. |

Opaque, GUID or nonsequential setting IDs stay in observation and the source-ID accounting receipt. They produce `unsupported_setting_configuration_id` and no complete configuration candidate. They are not coerced to the numeric IDs accepted by the proposed provider input contract.

`creationSource` is observed policy metadata. Null `priorityMetaData` and `disableEntraGroupPolicyAssignment:false` are retained. A recognized non-null priority structure or disabled Entra assignment behavior is retained as observation but blocks the configuration proposal because it has no qualified mapping. Unknown metadata keys stay restricted. Assignment `source:policySets`, unknown or omitted sources, or unsupported `sourceId` semantics block; they cannot become directly owned assignments. An omitted source produces `assignment_source_unobserved`. Requiring the explicit value is a conservative local support rule: Microsoft documents direct and policy-set sources but does not establish that omission proves direct provenance.

## Truthful evidence boundaries

`candidate_mapping_complete:true` means this bounded source-to-configuration proposal is complete. It does **not** clear execution gates. `offline_mapping_complete`, `provider_qualified`, and `execution_authorized` remain false. Reference IDs discovered in supported assignments or scope tags have `coverage:unknown` and `ownership:unverified`. A capture envelope's unverified reference claims do not establish existence or access. Repository ownership remains `unknown`; capture cannot establish the current Terraform writer.

Every source node, including null values, containers, unsupported key names and values, gets an opaque pointer hash, explicit disposition, versioned rule, destination pointers and loss-blocking flag. Field-accounting rule version1.1.0 supplies a canonical value hash only for already-visible mapped scalars; restricted or loss-blocking values and every container have a null value hash. This avoids exposing low-entropy restricted values through per-field dictionary attacks. `contracts/production-field-accounting.schema.json` defines this separate production accounting contract. Mapped values name their exact observation and, when available, configuration destinations. Unsupported records/pages retain opaque references and loss-blocking dispositions; unselected objects and unverified envelope claims have explicit retention rules. Missing configuration destinations on blocked candidates do not imply successful configuration mapping. Prior production-1.0.0 and production-1.1.0 review files must be regenerated; the independently rederived contract is now production-1.2.0. Unsupported original content is retained only in the caller's restricted source. Generated files and diagnostics contain bounded codes and opaque references, never unsupported raw key names or values. Whole-source hashes remain equality evidence and are not a confidentiality guarantee when the rest of a source is known. Recognized fields such as policy names and supported identifiers remain visible for review.

`adoption/source-receipt.json` binds the exact export bytes and its canonical representation. `adoption/target-receipt.json` binds the canonical target context, including repository fingerprint and implementation selection, so context-only changes invalidate an existing proposal. Capture's original page bytes and receipt remain separate restricted evidence; this mapper does not reauthenticate them or infer tenant authenticity from an exporter name. The capture's claimed tenant and target context must agree. No atomic snapshot, freshness, server authenticity, or reference-read completeness is inferred.

The independent oracle is implemented in `intune_iac/production_oracle.py`; it does not import the mapper or its projection helpers. It rederives observations, configuration, completeness and source accounting from input bytes, and checks candidate JSON and HCL. The engine also requires exact deterministic regeneration and a closed hashed output manifest. Rewriting a manifest after modifying a candidate cannot make that candidate pass verification.

## Local source basis and remaining qualification

The provider basis is `corrections/contracts/capability-map.json`, the reviewed provider configuration fixture, and `corrections/sources/source-evidence.json` for commit `1718c946b3ae111bb44c7c1d925b3e35b708cb0a`. The recorded P01 validator expects numeric sequence IDs. P02 records that the constructor does not copy those IDs. These are reviewed source records, not acquired provider binaries, native provider schema output, or an executed serializer/refresh roundtrip.

Microsoft Graph resource documentation describes [policy metadata](https://learn.microsoft.com/en-us/graph/api/resources/intune-deviceconfigv2-devicemanagementconfigurationpolicy?view=graph-rest-beta), [assignment source/sourceId](https://learn.microsoft.com/en-us/graph/api/resources/intune-deviceconfigv2-devicemanagementconfigurationpolicyassignment?view=graph-rest-beta), and [continuation handling](https://learn.microsoft.com/en-us/graph/paging). Documentation does not prove arbitrary setting definitions, provider wire compatibility or service semantics. Release 0.2.0 acquired the checksum-verified provider and initialized a local mirror; provider schema and candidate validation were attempted but failed during plugin startup. See RELEASE-VERIFICATION.md. Tenant/state qualification remains unperformed.

Tests in `plugin_tests/test_production.py` use API-shaped synthetic examples through the honest production exporter contract. They exercise candidate generation, metadata/null preservation, opaque-ID blocking, assignment completeness and provenance, no unsupported-value leakage, safe target paths, independent mutation rejection and inactive output. They do not represent live captures.
