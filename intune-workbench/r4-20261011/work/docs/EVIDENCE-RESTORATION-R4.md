# Typed evidence restoration

`scripts/restore-evidence-layer.py` verifies an externally supplied exact archive size and SHA-256 before interpreting its inventory or creating output. It supports the retained R2, R3 and R4 typed evidence schemas. It is a local POSIX restoration tool; it does not download, execute archive contents, replace the original complete repository, or establish native Windows qualification.

The output must be a **new** directory under an existing real directory. The archive and every existing ancestor are opened without following symbolic links. Existing files, directories and symlinks are never overwritten. Failed archives and partial output remain available for inspection; choose a different new output directory after correcting a prerequisite.

```sh
python -B scripts/restore-evidence-layer.py \
  --archive /absolute/path/to/reviewed-evidence.zip \
  --bytes EXACT_ARCHIVE_BYTE_COUNT \
  --sha256 EXACT_ARCHIVE_SHA256 \
  --snapshot-root EXACT_SINGLE_COMPONENT_ARCHIVE_ROOT \
  --manifest EXACT_MANIFEST_FILENAME \
  --manifest-sha256 EXACT_MANIFEST_SHA256 \
  --schema intune-r4-evidence-supplement/1 \
  --output /absolute/existing/parent/NEW-evidence-directory
```

Every uppercase value above must come from the reviewed delivery manifest. A hash calculated from an otherwise untrusted archive is not an independent delivery identity. The original named full release ZIP uses its retained `restore_release.py` contract; do not feed that untyped original archive to this helper or substitute GitHub's automatic source ZIP. Original, R2, R3, R4, source and runtime layers retain their separate identities and separate restoration directories.

## Exact handling of retained evidence

Before output creation the helper rejects traversal, absolute paths, duplicate ZIP members or JSON keys, ambiguous portable names, mismatched inventories/types, unsupported nodes, missing directory parents, invalid link inventories and incoherent hard-link groups. Bounds are 200,000 archive members, 32 GiB total payload, 16 GiB per member, a 64 MiB inventory, 4,096 UTF-8 bytes per path and 128 path components. These are declared restoration limits, not permission to omit incompatible payloads. A rejected real path blocks delivery until an exact, reviewed representation is prepared.

Regular bytes are written exclusively through anchored directory descriptors. ZIP CRC, manifest size and SHA-256 must all match. Directories receive private permissions; regular files receive `0600`, or `0700` when the manifest records executable bits. Original metadata remains in the manifest. Recorded hard-link groups must name distinct declared regular members with identical byte counts and hashes. Extraction materializes separate regular files and preserves the original relationship as metadata; it does not recreate shared writable inodes.

Nested `.git` directories are ordinary evidence bytes. No Git commands, configuration, hooks or submodule initialization run. The helper does not interpret policy fixtures as instructions.

Literal negative-test symlinks are recreated **after all archive regular members and directories have been verified**. The link target bytes are hash-verified and preserved exactly, including absolute, dangling and `..` targets. These target strings are evidence and are never dereferenced. Declared members cannot have a symlink parent. No later archive payload is written through a recreated link. The final scan examines links with `lstat`/`readlink`, traverses only no-follow directory descriptors and reads regular bytes back. The generated receipt is written at the extraction root after that scan; it is not an archive payload.

The physical file set and type map must match the declared payload plus its manifest and structural root. An unexpected temporary file, substituted bytes, changed archive or wrong type prevents a PASS receipt; the discrepancy is preserved, never deleted to obtain a clean count. This observed check does **not** explain or close the three unexpected files from the earlier workspace. `historical_three_unexpected_files_closed` remains `false`.

Do not run general recursive tools that follow these reconstructed negative symlinks. Their target files are not delivered merely because their paths occur in link evidence. This new final-last literal reconstruction supersedes the initial R4 preparation proposal to quarantine all targets as plain text. The older R2/R3 helper and its quarantine receipts remain unchanged historical evidence.

Literal POSIX filenames may themselves contain terminal controls or Unicode format characters in retained negative tests. They remain exact filesystem evidence; every helper diagnostic and JSON receipt escapes those characters. Never print raw names or errors through an unescaped terminal renderer. This is explicitly a POSIX-only route and does not qualify these filenames for Windows. An independent review found unsafe raw error output, and an initial repair rejecting all such names then correctly blocked the review's own retained OSC/BEL fixture during the whole-corpus census. That blocked census is preserved. The final repair preserves literal names safely instead of omitting the inconvenient failure evidence; traversal, NUL, separators, no-follow parents and all integrity gates remain enforced.

## Qualification and limits

`plugin_tests/test_restore_evidence_layer_r4.py` constructs literal fixtures without the product inventory builder or normalizer. Its focused cases exercise the real CLI for exact binary bytes, inert nested Git configuration, negative link targets, ZIP/manifest pins, traversal/duplicates/types, CRC/hash failures, missing parents, no-overwrite and ancestor refusal. Controlled in-process fault injections separately test archive mutation after its initial pin, unexpected output files and replacement of extracted bytes before readback. These injected failures are explicitly distinct from the unexplained historical discrepancy.

Replay the focused tests into a new evidence destination:

```sh
INTUNE_RESTORE_TEST_EVIDENCE=/absolute/existing/parent/NEW-restoration-tests \
  python -B -m unittest plugin_tests.test_restore_evidence_layer_r4 -v
```

Evidence lives in `work/evidence/epoch-20261007-r4/evidence-restoration/`, including failures and preserved partial trees. The initial positive CLI fixture failed because the adapted helper omitted its platform capability function. Two later controls failed because an unexpected physical output file and invalid hard-link metadata could receive PASS. The repairs add explicit no-follow platform prerequisites, typed hard-link validation, physical inventory verification and regular-file readback. Repeated runs overlap and must not be added together.

The current R4 path census is compatibility evidence, not a frozen package. Its recorded instant had 19,968 regular files, 3,347 directories and 49 literal symlinks; maximum path depth was 18 and maximum UTF-8 path length was 193 bytes. It found no incompatible path or special IPC node. New qualification evidence subsequently adds entries. Final packaging must stop writers and record every transient IPC exclusion explicitly; devices or unknown special files remain blockers.

The retained R2 and R3 inventories are also checked read-only against their exact manifest hashes and current ZIP metadata. This does not rehash or extract the large prior layers and does not replace their valid earlier qualification. A new full R4 archive, complete layer wrapper, exact final package tests and release decision remain separate gates until delivery is frozen. Laboratory restoration qualification establishes neither the product's live platform qualification nor organizational production approval.
