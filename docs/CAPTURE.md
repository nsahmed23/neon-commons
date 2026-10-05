# Read-only Settings Catalog capture

The capture adapter collects public-cloud Microsoft Graph beta policy, settings and assignment pages. It sends GET requests only. It never performs token acquisition, directory discovery, policy writes, imports, plans or applies. Capture is explicitly invoked; the plugin's read-only MCP inspection tools do not start it automatically.

Capture requires a supported POSIX host with no-follow directory descriptors. Native Windows returns `capture_platform_unavailable`; use a supported POSIX host for this operation. Bash and PowerShell command rendering elsewhere in the plugin does not establish native capture support.

Provide an already authorized read token through the explicitly selected environment variable. The adapter defaults to `INTUNE_GRAPH_TOKEN`; it does not search other environment variables, log in, discover an SDK account or save the token. Microsoft documents `DeviceManagementConfiguration.Read.All` for settings listing. Reference-object verification would require a separate evidenced workflow and is outside this collector.

```bash
python scripts/intune-iac.py capture \
  --tenant 11111111-1111-4111-8111-111111111111 \
  --policy 22222222-2222-4222-8222-222222222222 \
  --output ./new-capture \
  --token-env INTUNE_GRAPH_TOKEN \
  --max-pages 100

python scripts/intune-iac.py inspect \
  --input ./new-capture/export.json --context ./new-capture/context.json

python scripts/intune-iac.py generate \
  --input ./new-capture/export.json --context ./new-capture/context.json \
  --output ./new-review
```

The UUIDs above are examples. Tenant ID is **caller asserted**. Policy pages do not authenticate that tenant assertion. The receipt and returned summary explicitly say `source_authenticity_verified:false`, `provider_qualified:false` and `execution_authorized:false`. Hashes prove which bytes were retained; they do not prove server authenticity, an atomic snapshot or execution approval. `reference-dev` and `intune-reference` in generated context are proposed review labels; they do not establish an organization target or ownership.

The collector requests these trusted roots:

| Collection | First request |
| --- | --- |
| Policies | `https://graph.microsoft.com/beta/deviceManagement/configurationPolicies` |
| Selected policy settings | `https://graph.microsoft.com/beta/deviceManagement/configurationPolicies/{policy_uuid}/settings` |
| Selected policy assignments | `https://graph.microsoft.com/beta/deviceManagement/configurationPolicies/{policy_uuid}/assignments` |

Each first request is unfiltered. The adapter follows the entire returned `@odata.nextLink` only on the same HTTPS origin and exact collection path. It does not reconstruct skip tokens, follow redirects, cross to another collection, accept credentials/ports/fragments in URLs or infer the next page. A terminal empty assignment collection can be complete; a missing or denied assignment response cannot become a successful empty assignment array. Duplicate source IDs, a missing selected policy, malformed/non-UTF-8 JSON, duplicate JSON keys, error envelopes, untrusted links and loops stop that chain as partial. Response bodies remain unchanged in restricted raw evidence. The selected policy must occur exactly once in the completed root listing.

Every captured record needs a nonempty string ID. Policy and assignment UUIDs are compared without letter-case differences; setting IDs remain opaque and case-sensitive. This comparison never rewrites response bytes. Any supplied `@odata.count` must be a nonnegative integer and equal the total rows across the completed chain. Missing IDs, malformed counts, contradictory page counts, and terminal count mismatches produce partial coverage.

Limits are 100 total request attempts by default (configurable from 1 through 10,000), 4 MiB per response, 8 MiB total retained raw bytes, 20 seconds per built-in HTTP operation and a 120-second guard between requests. No automatic retry occurs. A byte limit retains only a bounded received prefix; that page's receipt says `raw_capture_complete:false`, and its hash is explicitly the stored prefix hash. Malformed JSON keeps original bytes even when `export.json` cannot contain a parsed body; the envelope then uses an empty body object with partial coverage, never an invented successful `value:[]`.

Native urllib GET transport has a per-operation timeout; the elapsed guard is checked before requests and is not an asynchronous cancellation mechanism. Injected transports must impose their own blocking-call timeout. The elapsed guard, limits and failures leave evidence with bounded codes; diagnostic summaries never echo response text, unknown keys, request headers or exception messages.

The output directory must be new and its parent must already exist. Existing directories/files are preserved. Ancestors are opened without following symlinks, and new files are created exclusively through anchored directory descriptors. Directories have mode `0700`; files have mode `0600`. These permissions protect local capture evidence but are not encryption.

| Output | Meaning |
| --- | --- |
| `raw/page-000000.json`, etc. | Exact response bytes received, or a clearly marked bounded prefix when a size limit was reached. Raw error/secret payloads can appear here; keep this directory restricted. |
| `export.json` | Versioned normalized intake envelope with complete original decoded response bodies, `synthetic:false`, truthful adapter identity, explicit per-collection coverage, `references:[]`, `ownership:[]`. |
| `context.json` | Pinned provider/engine/Atmos proposed-review context with `source_is_synthetic:false`, caller-selected UUIDs, public cloud and `authorization:emit_only`. |
| `capture-receipt.json` | Per-page request/status/time, byte count/path/hash and truncation flag; whole export/context byte hashes; caller-asserted identity and unperformed qualification assurance. |

`captured` in the safe result means all required chains were captured within these boundaries. It does not mean every setting maps to the selected provider. `partial` means at least one chain failed, exhausted a limit or lacked the selected object. Both results preserve source IDs and null/absent distinctions. No group/filter/scope-tag existence or external ownership is fabricated: relationship reference resolution remains unknown, and repository-writer ownership requires a separate decision.

The known capture exporter is dispatched to the separate [production mapping contract](PRODUCTION-MAPPING.md). A complete capture can produce inactive candidate configuration for the documented privacy choice setting and direct group assignments. That path accepts exact returned same-route continuation links including `$skip`. Unknown exporters, opaque/nonsequential setting IDs, policy-set assignments, unsupported templates/polymorphs and unmapped metadata remain review cases. Unsupported content stays in restricted input. Active reference generation retains its synthetic scope. Capture completeness, candidate mapping and provider qualification are separate results.

The production emitter writes `BLOCKED.json`, `review/normalized.json` and empty command cards. When the bounded mapping is complete, it also writes inactive `.tf.txt` candidate files and configuration/target receipts; it never emits active production `.tf` configuration or import commands. `inspect` and `generate` still report blocked execution even when a candidate is available. A missing selected policy or malformed required input may prevent normalization entirely; raw capture evidence remains available for restricted inspection.

The Python interface is:

```python
capture(tenant_id, policy_id, output_path,
        token_env="INTUNE_GRAPH_TOKEN", max_pages=100, transport=None)
```

For offline tests, `transport` is a callable taking the exact trusted GET URL and returning `(http_status_integer, original_response_bytes)`. Injected transport skips all credential lookup. The same parsing, boundary, byte-receipt, persistence and completeness code executes. A replay fixture is evidence of collector behavior, not a claim that Graph was contacted. This release does not import arbitrary page manifests.

In the source distribution, `plugin_tests/test_capture.py` covers exact raw-byte receipts and permissions, full continuation URLs, access denial, malformed/error/duplicate-key/non-UTF-8 JSON, duplicate record identity, missing selected policy, malicious links and loops, page/byte limits, exception redaction, no-token failure, symlink/existing-output protection, platform unavailability and explicit token/GET/redirect behavior with a fake urllib opener. An end-to-end fixture includes documented extra policy metadata and an opaque setting ID, then passes capture through independently checked engine inspection and blocked review generation. No test calls live Graph.

Primary shape references: [policy list](https://learn.microsoft.com/en-us/graph/api/intune-deviceconfigv2-devicemanagementconfigurationpolicy-list?view=graph-rest-beta), [settings list](https://learn.microsoft.com/en-us/graph/api/intune-deviceconfigv2-devicemanagementconfigurationsetting-list?view=graph-rest-beta), [policy relationships](https://learn.microsoft.com/en-us/graph/api/resources/intune-deviceconfigv2-devicemanagementconfigurationpolicy?view=graph-rest-beta), [assignment resource](https://learn.microsoft.com/en-us/graph/api/resources/intune-deviceconfigv2-devicemanagementconfigurationpolicyassignment?view=graph-rest-beta), [Microsoft Graph paging](https://learn.microsoft.com/en-us/graph/paging). These moving beta documents support API shape review; they do not replace provider/schema/tenant qualification.
