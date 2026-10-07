# Explicit multi-root evidence snapshot

`scripts/prepare-evidence-snapshot.py` prepares a single new private input tree for the existing `build-evidence-layer.py`. It reuses that producer's anchored/no-follow traversal, path/type/size constraints and pinned document parser, and the qualified restorer's exclusive writer and physical readback. It does not execute evidence, follow literal links, delete sources, infer public suitability or establish that a selected list is the complete private corpus.

The root map is an explicitly reviewed JSON document with exactly `schema_version: "intune-evidence-root-map/1"` and a nonempty `roots` list. Every record has exactly:

```json
{"source":"/absolute/task-owned/path","prefix":"relative-destination-prefix","type":"directory","owner":"attributable engineering owner","reason":"why complete continuation requires this retained root"}
```

The selected type is `directory`, `file` or `symlink`. This permits explicitly owned standalone failure logs and literal link roots without admitting their containing `/tmp` tree. Absolute source names are anchored without following ancestors. Source roots may not overlap each other or output. Destination prefixes may not overlap, traverse, alias by case or use the reserved `_snapshot` root. Literal source symlinks are copied as link text; their targets are never read by the helper. Hard-linked source files become independent ordinary byte copies, with original device/inode/link counts retained in the source censuses.

The CLI reads both documents through the existing pinned, no-follow reader. The lower-level Python `snapshot()` function assumes its caller already matched each supplied SHA-256 to the original JSON bytes that produced the parsed document. It checks shape/pin format and does not reconstruct or authenticate unavailable original JSON serialization. Direct callers must satisfy that precondition; a supplied digest label alone is not proof.

After all writers stop, pin the reviewed map bytes with SHA-256. Choose a NEW output directory outside every selected source root, with an existing trusted parent and sufficient space:

```text
python -B scripts/prepare-evidence-snapshot.py --roots /private/reviewed-roots.json --roots-sha256 EXACT_SHA256 --output /private/new-evidence-snapshot
```

The helper copies original ordinary bytes using exclusive creation, creates literal symlinks last, and uses the restorer's private mode policy: directories0700, files0600 or0700 based only on original execute bits. Original mode/signature metadata is preserved in `_snapshot/source-before.json` and `source-after.json`. Full hash/type/name censuses must match before and after copying, including pinned root/path identity; source metadata is checked again after output readback. Physical output must contain exactly the declared copied entries plus generated `_snapshot` metadata. Added/missing/changed files, unexpected output, renamed roots, no-follow/type failures and failed cleanup prevent PASS. Every failed partial tree remains; diagnostics are JSON escaped. Reusing an existing output or receipt never overwrites it.

The external `<output>.snapshot-receipt.json` and internal `_snapshot` records bind the selected map, source censuses and type/byte readback. A PASS describes the checked interval, not ongoing immutability after the operator resumes writers. Stop all writers for final packaging; preparation censuses from active work are not the final manifest.

## Explicit IPC and incompatible negative fixtures

Sockets and FIFOs are not ordinary bytes. They are rejected unless a separately pinned existing-contract omission document names the exact destination-relative path, type and reason:

```json
{"schema_version":"intune-r4-ipc-omissions/1","entries":[{"path":"r4/path/to/ended-ipc","type":"fifo","reason":"Retained ended disposable IPC fixture; endpoint not recreated."}]}
```

Supply `--ipc-omissions DOCUMENT --ipc-omissions-sha256 SHA256` together. Unlisted special entries, false types, missing entries and attempted omission of regular files/directories/links fail closed. Original IPC nodes remain untouched; their source stat metadata and exact omission document are retained in `_snapshot`, with `complete_selected_roots: false`. No IPC endpoint is recreated. The snapshot itself has no IPC nodes, so do not pass the original omission map to the archive producer as if its source endpoints were still present. Instead, include the snapshot receipt and its explicit incomplete-original-root scope in the archive provenance. The producer's complete physical snapshot claim does not imply a complete original IPC corpus.

The established over-depth producer counterexamples have separately pinned nested capsule coverage and relocation receipts. Their invalid nested hierarchy cannot be silently excluded, renamed, flattened or admitted by widening ordinary archive path limits. Preserve their existing exact capsules and explicit coverage provenance. Any additional incompatible source root needs a reviewed reversible representation or remains an inclusion blocker; this snapshot tool implements no generic exclusion/capsule escape hatch.

## Packaging and space procedure

1. Obtain each lane's exact owned-root list, including failed attempts, standalone logs, final package/preflight copies and contrary evidence. Reconcile currently absent paths and references explicitly. A prefix-looking filename is a candidate for attribution, not authority to ingest unrelated temporary data.
2. Freeze sources, prepare the exact pinned map/IPC records, and run the new-directory helper. Keep failures and originals. The complete R4 epoch, external stopped provider candidate and all attributable task roots are separate selections unless a qualified capsule representation explicitly covers them.
3. Review public/private suitability independently. Raw credentials, live tenant captures, state, saved plans and restricted evidence cannot be made public merely by snapshotting. Synthetic private fixture material also needs content-aware disposition.
4. Use the existing producer against the frozen snapshot. Pin exact bytes, digest, typed manifest and receipts. Independently read back the archive and verify the snapshot manifest/file map. Only after that evidence exists may the owner reclaim **this explicitly attributed duplicate snapshot copy** if space requires; retain a receipt naming its exact census/archive identity and preserve every original root. This tool never performs deletion.
5. Restore the archive through the existing type-aware extractor into another NEW directory and compare exact regular bytes, literal links, directories and explicit omission/capsule metadata. Retain unexpected files and fail closure. This layer supplements the verified original/R2/R3 layers; it never replaces them or closes the historical unexplained-file findings.

The helper requires the existing POSIX descriptor/no-follow host contract. Its literal fixtures and archive/extractor roundtrip are local packaging evidence, not Windows, service, device or production qualification.
