# Dictionary fact provenance

`workbench dictionary` and the identical terminal/workspace command now expose `workbench-dictionary-provenance/1`. The top-level `fact_provenance_contract` defines each category. Every entry’s `fact_provenance.categories` supplies an explicit availability, record count and JSON pointers into that same entry’s existing exact records. The change does not replace, normalize or remove any prior fields.

| Category | Exact source | Authority and absence |
|---|---|---|
| `vendor_documentation` | Release-pinned documentation summaries and citations | Caller reference imports cannot populate this category. Missing documentation stays absent. It does not establish current Graph semantics or endpoint applicability. |
| `observed_value` | `actual_uses` from the observation store | Each record retains its own evidence class, timestamp, coverage and freshness. The category itself does not authenticate a service. |
| `community_advice` | References imported with `community_reference` | Caller-asserted advice, never ownership, vendor documentation or approval. |
| `company_annotation` | References imported with `organization_annotation` | Caller-asserted annotation, not authenticated organizational approval or a source edit. |
| `local_mapping` | The existing release mapping contract and its digest | Bounded implementation semantics, not native provider lifecycle qualification. |
| `ai_interpretation` | No records or ingestion route implemented | Explicit `not_implemented`, zero records and no pointers. No model call or AI-generated explanation is fabricated. |

An empty dictionary still returns the category contract. Entries with an unknown setting ID explicitly show absent vendor documentation and local mapping. Matching names, URLs or setting IDs do not change a record’s category. In particular, importing a file from an official-looking URL with a community assertion does not make its contents vendor facts. Unknown keys such as `vendor_documentation` or `ai_interpretation` inside a supplied reference remain inert raw reference content; they do not install records in those categories.

The existing `reference-import --assertion-class` allowlist remains exactly `community_reference` or `organization_annotation`. Both the application parser and the provenance function reject AI, vendor and observed/service-fact claims. Supporting a future AI annotation would require a separately reviewed input schema and evidence contract; it could not confer execution or organizational authority. No new parser, model service, network request or runtime dependency is introduced here.

The release-pinned `corrections/contracts/vendor-documentation.json` is unchanged: SHA-256 `c758641e932f85014e5ec3451073828ad0f04a20fb850196ae6bb1b0f699bcd8`. Its earlier acquisition limitations, unknown Graph enum translation and unqualified device applicability remain as recorded in [the vendor/reference handoff](VENDOR-REFERENCE-LINEAGE.md). A new taxonomy is not a new acquisition or authenticity claim.

Use the existing actual commands:

```sh
/workspace/intune-runtime/bin/python -B scripts/intune-iac.py workbench dictionary --root /absolute/private/store --query Privacy
/workspace/intune-runtime/bin/python -B scripts/intune-iac.py workbench terminal --root /absolute/private/store
```

Inside either terminal presentation, `dictionary` remains the same engine query. To verify the changed scope:

```sh
/workspace/intune-runtime/bin/python -B -m unittest plugin_tests.test_workbench_dictionary_taxonomy_r4 plugin_tests.test_workbench_provenance plugin_tests.test_workbench_vendor_lineage -v
```

The changed-scope run comprises six new taxonomy cases and forty existing reference/vendor/lineage regressions, counted once within the 46-case run. It exercises real CLI import/dictionary/collection routes, literal category expectations, exact raw reference retention, unsupported AI/vendor/service import rejection, unknown identifiers and the unchanged vendor pin. It does not qualify live collection, organizational authorship, AI interpretation quality or a new policy family.
