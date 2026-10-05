# Contract repair verification

30 September 2026. This report covers corrected schema/model behavior and the shared contract APIs used by the repaired reference pipeline. It is not a provider, service, live-tenant, native-host, or end-to-end pipeline execution receipt.

## Repairs

- C01: All 13 GUID predicates in correction contracts enforce exactly 36 characters, plus the existing full GUID pattern and applicable zero-ID exclusions. Root and canonical session schema predicates are also exercised by the schema-copy test; those edits belong to their integration owners. Identifiers are rejected before canonicalization; no trimming is used. Assignment service IDs remain opaque strings.
- C02: The approval comparator reports a structural mismatch before descending into incompatible object/null values. Valid workload-federation ↔ managed-identity and workload-federation ↔ application-certificate branches reject in both directions with controlled paths.
- C03: Preview commands use the explicit `atmos`, `tofu`, `python`, and exact current `sys.executable` registry. Python entries exist for harmless argv roundtrip tests. Builtins, keywords, assignments, unregistered executables, and arbitrary paths are rejected. This registry does not establish installed-binary identity or execution trust. Bash `command --` does not force an external executable.
- Field rules now explicitly classify policy discriminators, required none-template metadata leaves, instance/value null template references, actual capture field names, exporter/source metadata, and container/leaf accounting. Policy `templateReference` requires an explicitly observed exact none-template shape; absent policy template metadata blocks support. Present null setting template references preserve their provider destination; absent setting references remain absent.
- `corrections/contracts/capability-map.json` supports only the worked Windows/MDM choice definition, permitted value, and empty children. The source/fixture provenance and pinned provider shape evidence are explicit. Other definitions, values, platforms, technologies, simple settings, and child combinations remain review-only. This is an offline mapping boundary, not proof of service definition applicability or provider roundtrip stability.
- `reference/validation.py` exposes package-safe schema, provider-projection, capture-chain, duplicate-reference, capability, and executable gates. Correction schemas take precedence over root schemas with the same name. Errors contain codes and safe path components; rejected raw values and unknown keys are never echoed.
- Capture completeness rejects any explicit page-body `error` member, regardless of HTTP200, a simultaneous `value` array, or an empty/malformed error envelope. The presence check blocks contradictory success/error evidence without printing error payloads.

## Reproduction before repair

Command, run with genuine `jsonschema` available:

```text
PYTHONPATH=/workspace/scratch/26b6d364cfda/correction-validation-deps PYTHONDONTWRITEBYTECODE=1 python -m unittest corrections.regressions.test_contract_models.ContractTests.test_guid_exact_length_and_nonzero corrections.regressions.test_contract_models.ContractTests.test_valid_coupled_auth_transitions corrections.regressions.test_contract_models.ContractTests.test_preview_registry_rejects_builtin_and_unknown_tokens -v
```

`contracts-before-repair.txt`: 3 test methods ran, with 16 assertion failures and 2 errors. Six GUID newline subtests failed; ten builtin/unregistered command rejection subtests failed. One error reproduced the valid authentication branch TypeError; the other demonstrated the missing harmless absolute-interpreter registration. The latter is a test compatibility gap, not an approval defect. No dependency import failure was counted as defect reproduction.

`policy-template-before-repair.txt`: 2 further failing methods reproduce absent policy `templateReference` incorrectly passing both the schema and the actual pipeline normalizer's support gate. The repaired required-property contract blocks that omission; setting-instance/value references retain their distinct optional null/absent contract.

`capture-error-before-repair.txt`: 2 further methods reproduce six accepted HTTP200/error-envelope variants and an empty-error page passing the actual normalizer support gate: 7 assertion failures, no import/startup errors. The repaired gate rejects the presence of the member, independent of its value. Integration tests also confirm that both missing-template and empty-error captures emit review-only output with no active Terraform or import command cards.

## Fresh verification after repair

```text
PYTHONPATH=/workspace/scratch/26b6d364cfda/correction-validation-deps PYTHONDONTWRITEBYTECODE=1 python -m unittest corrections.regressions.test_contract_models evaluations.test_repaired_contracts -v
```

`contracts-combined-after-repair.txt`: **42 tests PASS**. This comprises 25 correction model/schema tests, including the existing 2,184-case resume nonadvancement matrix, and 17 contract API tests including the actual normalizer/generator's missing-template and error-page rejection. Runtime identity and genuine validator module provenance are recorded in `contracts-runtime.json`. `contracts-api-during-integration.txt` retains the earlier integration-stage run with two failures in canonical session-schema nodes before that owner's v2 migration; the current combined run passes the complete schema-copy check.

Positive controls cover exact provider `{id, settingInstance}` projection; deep-copy isolation; null-versus-absent template reference preservation; recursive child order; the worked capability; Unicode description boundaries; valid GUID predicates in every schema copy; valid capture chains; valid coupled auth transitions; permitted preview identifiers; and real subprocess package import from a different working directory. Negative controls cover malformed IDs, unmapped settings, non-null templates, narrowed capture continuations, unsafe URLs, duplicate references, unregistered commands, and diagnostics canaries.

Description length tests establish Python/JSON Schema codepoint limits under the local 1,500-character contract. They do not qualify the pinned Go provider's Unicode length behavior. Projection tests establish configuration shape and preservation, not request serialization or refreshed-state equivalence. Capture tests establish declared structural completeness, not authenticity, freshness, or an atomic snapshot. Approval comparator tests establish local rejection behavior, not approval authenticity or execution authority.

## Stable API for integration

| API | Result |
| --- | --- |
| `schema_errors(name, value)` | Safe error-code list; correction name preferred, root name fallback |
| `provider_settings(records)` | Exact `{settings: [...]}` provider configuration projection; raises `ContractViolation` on rejection |
| `capture_errors(collection, expected_root)` | Safe error-code list for one collection and an independently derived trusted root |
| `reference_errors(records)` | Safe shape/duplicate error-code list; accepts the reference array |
| `capability_errors(records, platforms='windows10', technologies='mdm')` | Empty list for the worked mapping, otherwise `unqualified_setting_capability` |
| `validate_executable(token)` | Accepted registered token unchanged, otherwise `ContractViolation` |

No provider/network operations, native PowerShell execution, installer activity, or infrastructure commands were performed by this contract work. Full pipeline/oracle/workflow verification is recorded separately by its owners.
