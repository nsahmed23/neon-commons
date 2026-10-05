# Independent offline preservation oracle repair

Implemented in `reference/invariants.py`; executable mutation checks in
`evaluations/test_repaired_oracle.py`.

`compare(source, normalized, files=None, context=None)` preserves the public
2-argument API. Repaired callers pass restricted original bytes, the independently
validated tenant/selected-policy context, and emitted files before writing. The
return value contains safe error codes only. Correctly blocked, inactive partial
review is accepted; a supported capture falsely marked blocked is rejected.

The oracle imports no normalizer, generator, validation, field-accounting, or
contract-model helpers. It reads local declarative schemas and the exact worked
capability registry directly and independently implements its parser, whitelist,
provider configuration projection, capture validation, reference derivation,
canonical digest, UUID resource key, and field rule/destination derivation. Unknown
keys and secret values are represented by opaque retention IDs with restricted
original-source locators. Container nodes, null, empty arrays, and leaves are
accounted for independently. Dropped setting/assignment/reference records shift
remaining desired destinations correctly without shifting observed slots.

Original-byte parsing independently rejects duplicate JSON keys, invalid Unicode,
nonfinite numbers, floats, integers outside the safe exact integer range, excessive
depth, and oversized inputs. Raw-byte and version-1 compact UTF-8 sorted-key
canonical digests are checked separately. Original bytes plus emitted files require
a source receipt; missing receipts fail safely. Legacy dict callers cannot verify
original-byte hashes and retain optional receipts.
This canonical convention is not a claim of RFC8785/JCS equivalence.

Actual emitted HCL is parsed by genuine `python-hcl2==8.1.4`, with explicit
serialization options. The oracle interprets parsed resource/provider/local/import
blocks and verifies the selected resource address, import ID, field expressions,
input JSON, provider pin, and inactive guard. It rejects additional resource
blocks and unqualified `.tf.json` instead of using a regular-expression fallback.
Genuine PyYAML interprets the exact Atmos/stack target and false qualification
guard, using duplicate-key rejection. Import and lifecycle attribute sets, full
command-card contracts, and separately rendered Bash/PowerShell proposals must
match. Active HCL must be in the intended component paths; additional HCL,
variable files, stack YAML, or active scripts are rejected. Missing
parser/dependency conditions produce safe failure codes. Partial records
cannot contain active infrastructure or command cards. Generated map, coverage,
accounting, capability, command identity, source receipts, and ownership manifest
hashes are checked too.

Verification command:

```text
PYTHONPATH=/workspace/scratch/26b6d364cfda/correction-validation-deps PYTHONDONTWRITEBYTECODE=1 python -m unittest evaluations.test_repaired_oracle -v
```

Result: 18 tests passed (latest focused run: 5.472 seconds). Positive checks include all four actual fixtures and the
legacy two-argument call. Tests mutate tenant/policy/key/digest, technologies,
scope tags, observed identity, settings ID/value/type/children/wrapper,
assignment inclusion/exclusion/filter/deletion/addition, reference
removal/duplication/contradiction, every accounting disposition and loss flag,
destination/rule/version/reason, generated HCL address/import ID/resource fields,
generated settings JSON ID/value, object-map ID, and forbidden canaries.
Review-driven mutations also cover import provider aliases, lifecycle
ignore_changes, substituted command executables and previews, changed stack
qualification guards, relocated main/import HCL, extra data blocks, and
additional variable/stack configuration files. Tests
also establish that first-page omission, dangling nextLink, or an HTTP200 error
member cannot be accepted as complete, and that blanket refusal is not success.

Limits remain explicit: this is a bounded offline interpretation of supplied
captures. It establishes neither service authenticity/freshness nor pinned
provider serialization and refresh equivalence, native CLI behavior, real target
identity, protected approval, or live tenant execution. The capability registry
supports only the exact worked Windows/MDM choice definition/value with empty
children. Canary checks demonstrate these controlled markers; they are not a
universal redaction proof. Two-argument callers cannot independently establish
selection intent without a separate trusted context.
