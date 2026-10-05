# Materials verifier format repair

The clean-extraction materials scan had two format failures unrelated to the native runtime. This repair changes the external Python verification tool, one acquired artifact's filename, the two source inventories that named that artifact, and focused regression tests. It does not change acquired content, native runtime or build inputs, installed binaries, or the original release ZIP.

The verifier previously checked every `*.schema.json` with `Draft202012Validator`, even when an acquired schema declared another dialect. `research/enterprise-dependencies/bom-1.6.schema.json` declares `http://json-schema.org/draft-07/schema#`. Its valid Draft 7 tuple-style `items` at `definitions/licenseChoice/oneOf/1/items` caused the forced Draft 2020-12 check to raise `SchemaError` because that draft requires an object or boolean there. The repaired tool selects known declared dialects with `jsonschema.validators.validator_for(schema, default=None)`, then calls that validator's `check_schema`. Unknown or malformed declarations fail. A missing declaration retains the existing Draft 2020-12 policy; tests prove that an undeclared Draft 7 tuple schema still fails. Boolean schemas remain supported. The acquired CycloneDX schema has not been edited.

The acquired Go module download output consists of six pretty-printed JSON objects separated by whitespace. Its former `.jsonl` name incorrectly implied one complete record per line, so the first line, `{`, raised `JSONDecodeError: Expecting property name enclosed in double quotes: line 1 column 2 (char 1)`. The artifact is now `research/provider-qualification/evidence/module-acquisition.jsonstream`, with identical bytes. Only the existing path entries in `release-source-files.txt` and `native-candidate-source-files.txt` were substituted. The verifier has an explicit `.jsonstream` branch and reports `jsonstream_records` separately. Its parser consumes complete JSON values with JSON whitespace separators and rejects duplicate keys, nonfinite values (including float overflow), malformed records, missing separators, and trailing junk. `.jsonl` still requires one complete value per nonblank line. All JSON formats use the same strict decoder.

Retained SHA-256 values:

| Acquired artifact | SHA-256 |
| --- | --- |
| `research/enterprise-dependencies/bom-1.6.schema.json` | `3e92dddbc30cf7f6a02b80f0942b1a4cfd4fb1c26f1dfc4310afa9d613cafb93` |
| `research/provider-qualification/evidence/module-acquisition.jsonstream` (before and after rename) | `bb6a3022e99c52fe995db5c273c333d6a9afc88a8bf58fc8e76ba8a27b465889` |

From `/workspace/scratch/26b6d364cfda/intune-iac-plugin`, the pinned validation environment ran:

```bash
PYTHONDONTWRITEBYTECODE=1 /workspace/scratch/26b6d364cfda/plugin-clean-venv/bin/python -B -m unittest discover -s research/verification-repair/tests -p test_material_formats.py -v
sha256sum research/provider-qualification/evidence/module-acquisition.jsonstream research/enterprise-dependencies/bom-1.6.schema.json
```

All 15 focused tests passed. These tests cover dialect selection and rejection, the missing-dialect policy, acquired schema and stream byte identities, valid pretty-printed streams, strict JSONL, duplicate keys, malformed input, separators, trailing junk, and nonfinite numbers. A separate targeted scan called `check_json_schema(parse_json(path.read_text()))` for all 23 `*.schema.json` files and passed; the acquired stream parsed into six records. The former behavior was reproduced directly with the forced Draft 2020-12 check and strict JSONL parser, confirming the original failure mechanisms.

The full materials command is reserved for the owner's subsequent clean extraction, with receipts outside that repository:

```bash
/workspace/scratch/26b6d364cfda/plugin-clean-venv/bin/python tools/verify-materials.py --output /workspace/scratch/26b6d364cfda/material-verifier-clean-receipt
```

No broad scan was run in the live checkout, which contains native binaries outside the source distribution and would trigger the verifier's text-only scanning assumption. This report does not claim that the clean-extraction integration scan has already passed.
