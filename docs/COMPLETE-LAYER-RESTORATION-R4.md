# Complete continuation layers

`scripts/restore-complete-layers.py` restores a pinned set of already transferred local artifacts. It does not download anything or search directories for matching filenames. It requires all nine layers, in order:

1. The complete R2 continuation, source commit `74130d0db99febf2f41cf4f4ebe2920a5d4dffb7`.
2. Exact R3 source, verified commit `289ee9477372825aad848f4482cf681c2ff43b02`.
3. Exact R3 runtime.
4. The full R3 evidence supplement.
5. Exact final R4 source.
6. Exact final R4 runtime.
7. The complete R4 epoch evidence supplement.
8. The separately pinned R4 external task-root evidence supplement, with exact root/capsule/IPC coverage.
9. The stopped external provider candidate, preserved as explicitly unqualified source and evidence.

The original named complete repository archive remains separately preserved unchanged. Its exact public-release identity is retained in the outer template's provenance. R2 supplies the complete continuation base; a small source/runtime ZIP or evidence supplement is never substituted for that base. All six saved engineering threads, original inputs and prior failures remain part of the required complete continuation layers. The stopped candidate is never built, loaded as a provider, executed or described as qualified by restoration.

## Final pins are required

`docs/CONTINUATION-LAYERS-R4.template.json` deliberately has status `preparation`, null R4 source/artifact pins and conspicuous pending names. The actual CLI rejects it before creating any output. Null, zero or malformed hashes cannot become valid through a Boolean flag. Finalization requires a frozen source commit, exact final archive sizes/SHA-256 values, exact ordered part sizes/hashes, the two reviewed helper hashes, and each typed evidence archive's root/schema/inner-manifest identity. All R4 source/runtime/evidence layers must bind one final source commit; the stopped candidate retains its separate unqualified status.

Populate a new final outer manifest outside the frozen source and evidence trees. Preserve the template and any failed candidates. Obtain its SHA-256 independently from the accountable delivery receipt. The wrapper verifies that pin before trusting any contents. An outer manifest binds declared source/artifact identities; it does not replace the independent source-to-tested-commit/package qualification receipts.

The wrapper executes only its two fixed adjacent helpers after verifying their source bytes against the pinned outer manifest: `restore-evidence-layer.py` and `verify-release-artifact.py`. It does not execute a helper named by archive contents. Extraction behavior and the POSIX no-follow prerequisites are described in `EVIDENCE-RESTORATION-R4.md`.

## Exact returned local paths

Record the paths returned by the authorized transfer/reassembly process in a separate local JSON document. There must be one entry for each required layer, in the same order as the outer manifest, and exactly one absolute local path for each declared byte part, in order. Do not glob for parts, derive replacement paths, silently ignore extra results, or infer a missing final part.

```json
{
  "schema_version": "intune-local-layer-parts/1",
  "manifest_sha256": "EXACT_FINAL_OUTER_MANIFEST_SHA256",
  "layers": [
    {"id": "r2-complete", "parts": ["/exact/returned/part01", "/exact/returned/part02"]},
    {"id": "r3-source", "parts": ["/exact/returned/source.zip"]},
    {"id": "r3-runtime", "parts": ["/exact/returned/runtime.zip"]},
    {"id": "r3-evidence", "parts": ["/exact/returned/each-declared-part-in-order"]},
    {"id": "r4-source", "parts": ["/exact/returned/final-source.zip"]},
    {"id": "r4-runtime", "parts": ["/exact/returned/final-runtime.zip"]},
    {"id": "r4-evidence", "parts": ["/exact/returned/each-declared-r4-part-in-order"]},
    {"id": "r4-external-evidence", "parts": ["/exact/returned/each-declared-r4-external-part-in-order"]},
    {"id": "r4-provider-candidate", "parts": ["/exact/returned/stopped-candidate.zip"]}
  ]
}
```

This illustration is not an executable delivery manifest. For example, the retained R3 evidence manifest currently declares eleven parts, which must each have their own returned path; the single illustrative string above cannot substitute for that list.

```sh
python -B scripts/restore-complete-layers.py \
  --manifest /absolute/path/final-layer-manifest.json \
  --manifest-sha256 EXACT_FINAL_OUTER_MANIFEST_SHA256 \
  --returned-parts /absolute/path/exact-returned-part-paths.json \
  --output /absolute/existing/parent/NEW-complete-restoration
```

The output layout is `archives/` plus `layers/r2-complete`, `layers/r3-source`, and one corresponding new directory for every other layer. Nothing overlays the recovered baseline or an earlier source generation. Input paths and every ancestor are opened without following symlinks. Each part's count/hash and unchanged descriptor identity are checked while reading; concatenation uses exactly the returned array order. Completed archives are published without replacement. A failure retains the partial archive and any already verified archives.

Every assembled archive is verified before the first layer is extracted. A corrupt final candidate part therefore prevents **all** extraction rather than leaving a misleading partially qualified baseline. Typed evidence uses the qualified literal-link-last extractor. Source/runtime packages first pass the existing bounded ZIP/`SHA256SUMS` verifier, then are written through anchored exclusive no-follow helpers and read back. The final wrapper independently enumerates its entire physical tree against the exact expected map, including every retained archive and layer receipt. Unexpected files or changed bytes block the complete PASS receipt and remain preserved. The final generated `COMPLETE-LAYER-RECEIPT.json` records declared source bindings and exact per-layer receipts.

The current complete-wrapper limits are nine required layers, at most 1,000 parts per layer, 32 GiB per archive, 128 GiB total archive bytes, and a 4 MiB outer/local-path document. Every layer retains the evidence helper's 200,000-entry and bounded-depth profile. Final readback composes those unchanged bounded layer checks with exact anchored root, archive and layer namespaces; the aggregate map is bounded to nine layer budgets plus structural/receipt entries. No unknown path is excluded from final closure. A real corpus exceeding a declared bound must receive an explicitly reviewed implementation/profile change; no payload may be dropped to fit.

## Scoped qualification

`plugin_tests/test_restore_complete_layers_r4.py` creates independently authored literal nine-layer fixtures and drives the actual CLI. It checks separate exact layers, archive/part pin failures, reordered/missing/extra paths, no directory discovery, unresolved final pins, no overlays, helper substitution, symlink ancestors, preserved partials and stopped-candidate status. A separate in-process injected unexpected file checks complete file-set refusal and preservation. No large old R2/R3 archive is extracted again by these tests.

```sh
INTUNE_COMPLETE_RESTORE_TEST_EVIDENCE=/absolute/existing/parent/NEW-complete-layer-tests \
  python -B -m unittest plugin_tests.test_restore_complete_layers_r4 -v
```

The template remains blocked until actual final pins exist. Passing fixture tests qualify orchestration and safety behavior only. Exact final source/runtime packages, full R4/candidate evidence archives, final complete-layer restoration, delivery readback and the accountable release decision still need their own exact artifact evidence. Laboratory qualification, real platform qualification and organizational production approval remain separate; this wrapper grants none of the latter two.

The earlier eight-layer template, implementation and qualification remain historical evidence. The current contract intentionally refuses an eight-layer selection: both R4 supplements and the stopped candidate are required. Two supplements bound census metadata and sequential build/readback space without reducing the selected original corpus. Final complete restoration still requires enough storage for all original layers, archives and extracted trees; per-layer two-pass build qualification is a narrower claim.
