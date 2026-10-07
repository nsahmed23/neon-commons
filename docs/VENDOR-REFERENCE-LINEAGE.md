# Documentation and repository lineage

The existing `workbench dictionary` keeps observed values, bounded local mapping, community reference, organization annotation and vendor documentation separate. Its first vendor documentation entry is the Microsoft Privacy CSP `LetAppsAccessLocation` policy. Search by the exact setting definition ID or the documented name/alias:

```bash
python -B scripts/intune-iac.py workbench dictionary --root STORE --query "Let Windows apps access location"
python -B scripts/intune-iac.py workbench dictionary --root STORE --query "Privacy/LetAppsAccessLocation"
```

The `vendor_documentation` field supplies the policy meaning, CSP URI, integer type, documented values, default, device/edition/OS applicability, official URL and source dates. The separately listed observed Graph choice string stays unchanged. CSP integer `2` means Force deny in the cited document; this implementation **does not translate** a Graph choice suffix into that integer or infer applicability to the observed devices. `meaning` and `vendor_dictionary` retain their earlier unknown/unresolved Graph-definition semantics. The readable CSP meaning is explicitly under `vendor_documentation`.

These facts come from one Microsoft Learn page retrieved on 2026-10-07, with source date 2026-09-10 and published-update metadata 2026-09-23. Page SHA-256 is `b6c9c2e074b68403f400c8e2c610f41ed5b6907fb023b0e5d76ae023b703b351`. The page advertises source revision `65e6c8ea9044ee218340ea399c918edaef788782`; the public Git API lookup returned 404, so repository membership was not independently verified. The acquired bytes and focused section are retained in `work/evidence/epoch-20261007-r3/vendor-reference/acquisition/`. The runtime contains an original factual summary and citations, pinned by the implementation; it contains no copied OIB policy export or upstream executable code. Existing OIB GPL notices and raw evidence remain unchanged.

Unknown or similarly named setting IDs do not inherit this entry. Importing a community file cannot install vendor definitions, modify the pinned documentation, grant organizational approval or expand supported provider mappings. There is no network lookup during dictionary navigation. Documentation freshness is its recorded date, not a claim that it is the latest source.

Repository navigation uses the literal-resolution evidence already recorded by explicit collection or adoption:

```bash
python -B scripts/intune-iac.py workbench lineage --root STORE --object OBJECT_ID
python -B scripts/intune-iac.py workbench lineage --root STORE --object OBJECT_ID --pointer /vars/region
```

In `workbench terminal`, select an exact object ID and enter `lineage` or `lineage /vars/region`. `dictionary` entries also identify their object-specific lineage route. The view exposes effective field pointers, winning source locations, ordered earlier sources, line/column numbers, source hashes and typed `defined_in`/`precedence_before` edges. It excludes effective configuration values, including environment or provider values. An earlier map origin describes merge precedence; it does not imply that every nested value was overwritten.

Dictionary navigation remains supported when the current observation contains no repository resolution. Its `current_resolution_recorded` flag describes only that observation; `historical_resolution_status: query_required` directs the operator to query lineage for validated historical adoption evidence. It does not falsely label missing current metadata as unavailable history or label historical evidence as fresh.

Lineage never opens a displayed path or runs repository commands. It validates the captured source fingerprint, source membership, bounded pointer/history structure and winning-origin consistency. A missing resolution remains unknown. A blocked literal resolution remains blocked. Unsupported paths, inconsistent provenance, malformed pointers, absent selected fields and over-limit histories return explicit errors rather than truncated or invented lineage. The current bounds are 512 source files, 4,096 effective fields and 8,192 provenance origins per query.

When a later scheduled observation has no fresh repository resolution, the latest object-bound adoption artifact can supply **historical** lineage. Its tenant/object binding and digest must match, and the view labels `freshness: historical_not_revalidated` with the adoption artifact ID. A current observation's resolution takes precedence. This fallback does not claim the current files still match or that adoption establishes ownership. It also does not change the freshness of policy/device evidence.

This route qualifies captured local literal provenance. Native Atmos evaluation, a Graph-setting-to-variable relationship, authentic service definitions, current disk content, endpoint applicability and organization approval require their own evidence. Broader vendor definitions and unsupported OIB adoption remain outside this narrow profile.
