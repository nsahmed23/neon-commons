# Exact ordered continuation transfer

`download-complete-layers.py` and `stage-release-git.py` adapt the retained R3
delivery procedure to the complete eight-layer continuation contract. The R2/R3
helpers and archives remain unchanged. These tools transfer bytes; they do not
grant cloud execution, platform qualification or production approval.

The required order is `r2-complete`, `r3-source`, `r3-runtime`, `r3-evidence`,
`r4-source`, `r4-runtime`, `r4-evidence`, `r4-provider-candidate`. The stopped
provider candidate remains explicitly unqualified. The complete R2 base and
each newer source/runtime/evidence generation stay separate. Original release
provenance, literal negative links, capsule coverage and the historical three
unexpected files remain in the complete manifest; a transfer cannot close that
historical discrepancy.

The outer manifest uses `intune-complete-continuation-layers/1`, all final archive,
part, inner-manifest and source-commit pins, and the existing qualified extraction
helper pins. `preparation`, null and placeholder pins block before output. The
download tool additionally requires immutable HTTPS URLs at the declared
`raw.githubusercontent.com/nsahmed23/neon-commons/FULL_COMMIT/intune-workbench/`
origin. Query strings, credentials, mutable branches, unsafe paths, duplicate
URLs and redirects are refused. No Authorization header or cookie is supplied.
Existing execution-network proxy configuration can carry the HTTPS request.

From independently reviewed published tool and manifest pins:

```text
python -B scripts/download-complete-layers.py --manifest FINAL_OUTER.json --manifest-sha256 OUTER_SHA256 --validator-sha256 RESTORE_COMPLETE_HELPER_SHA256 --output NEW_PRIVATE_DOWNLOAD_ROOT
```

The local outer document must already have its independently trusted digest.
The validator pin binds the exact neighboring `restore-complete-layers.py`
before importing its contract; the downloader itself must also be verified
against its independent delivery-tool receipt before invocation. All eight
layers validate before the first transfer. New private directories and exclusive
partial files preserve prior output. Each part is hashed while received, then
read back from its held descriptor and final no-follow name. Ordered part
streams must match the whole archive pin. Every final physical part is reopened
and rehashed, and every layer name set is re-enumerated before a PASS receipt.
Unexpected files and changed bytes are retained with failure evidence.

`RETURNED-PARTS.json` contains exactly the ordered absolute paths returned by
this transfer, bound to the outer manifest digest. It is the only discovery
input to the complete restorer; no wildcard or directory scan selects parts:

```text
python -B scripts/restore-complete-layers.py --manifest FINAL_OUTER.json --manifest-sha256 OUTER_SHA256 --returned-parts NEW_PRIVATE_DOWNLOAD_ROOT/RETURNED-PARTS.json --output NEW_COMPLETE_RESTORATION_ROOT
```

Downloading and stream verification do not imply extraction or physical file-set
closure of the restored archive contents. The final complete wrapper requires
sufficient capacity for all eight archives and their separate extracted layers.
Prior verified R2/R3 recovery/readback evidence remains reusable at its exact
scope; it cannot be relabelled as a fresh simultaneous eight-layer restoration.

For offline fixture qualification only, the downloader accepts
`--local-fixture-map MAP.json --local-fixture-sha256 MAP_SHA256`. This maps exactly
the declared URLs to bounded, no-follow local regular files. Its result says
`PASS_LOCAL_FIXTURE_ONLY`, records no network attempt, and cannot establish
anonymous public availability. Unknown map entries, unsafe input paths and
existing output remain refused.

The publisher stages only the four new R4 layers; R2/R3 public parts are retained
by immutable reference. Its pinned `intune-release-git-inputs/1` document has
exactly `schema_version`, `manifest_sha256`, and `layers`, with ordered entries
`{id, archive}` for those four absolute archive paths. The manifest declares
the actual part boundaries and hashes; the tool never silently re-splits or
repackages them. Use the established 96,000,000-byte Git chunk profile so every
blob stays below the public host's file-size limit. The public R2 route has24
parts, whereas its older local-delivery split had two; archive identity is the
same, but those part manifests are not interchangeable.

```text
python -B scripts/stage-release-git.py --manifest PINNED_OUTER_WITH_FINAL_ARCHIVE_PINS.json --manifest-sha256 OUTER_SHA256 --inputs ARCHIVE_INPUTS.json --inputs-sha256 INPUTS_SHA256 --repository NEW_BARE_REPOSITORY --branch intune-r4-evidence-data-20261007 --git-executable PINNED_GIT --git-sha256 GIT_SHA256 --validator-sha256 RESTORE_COMPLETE_HELPER_SHA256 --helper-sha256 DOWNLOAD_HELPER_SHA256
```

Default staging is offline. It verifies whole archive inputs before creating
output, streams exact declared parts directly into Git objects without duplicate
chunk working files, and independently reads every stored blob back. Input
archives are rechecked after streaming. Git uses an isolated configuration,
empty templates, disabled hooks/filters/fsmonitor and deterministic commit
metadata. The receipt includes exact blob/tree/commit identities and immutable
candidate public URLs. Source/runtime/evidence source-commit equality does not
replace the separate raw Git source-linkage gate or package qualification.

After review of the exact frozen archive public disposition, explicit `--push`
additionally requires `--expected-remote-main FULL_UNRELATED_MAIN_COMMIT`,
`--gh-executable PINNED_GH`, and `--gh-sha256 GH_SHA256`. It uses only existing
credential transport, refuses an existing proposed R4 branch or changed Neon
main, and never force-pushes. It verifies the returned new branch and unchanged
main. A failure after requesting push records remote outcome as uncertain and
does not retry automatically. A prepared bare repository can instead be pushed
by the same explicitly reviewed Git command; no new credentials are provisioned.

Publish the final outer manifest only after inserting the actual returned data
commit URLs; its final digest changes when those URLs are added. Preserve the
prepublication pinned manifest used to stage the archive bytes as a separate
link in the delivery record. A staged commit or a successful push is not fresh
anonymous readback. That final readback must verify independently published
helper/outer pins, exact part and archive bytes, then qualify the exact new
packages and typed evidence extraction. No publication has been performed by
the local fixture tests.

Focused local replay is `python -B -m unittest plugin_tests.test_release_transfer_r4 -v`.
It includes actual CLIs, real Git blobs, deterministic commits, the eight-layer
restorer, corruption/order/path/pin negatives and retained unexpected files.
Modeled HTTPS/remote-ref controls test dispatch contracts, not live public
availability. Earlier late-file closure failure and process-pipe warning logs
remain preserved alongside the repairs. Cooperative private-workspace checks
do not establish hostile same-account process isolation.
