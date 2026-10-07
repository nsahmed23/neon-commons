# R3 evidence supplement distribution tooling

The R3 ZIP contains the **entire `epoch-20261007-r3` evidence directory**, including raw receipts, failed attempts, fixture data, complete development source copies, provider binaries, caches, and literal negative-test symlinks. It is an explicit evidence supplement—not a replacement for the complete R2 repository snapshot. The published R2 snapshot remains unchanged and separately required; the handoff also supplies exact R3 source/runtime ZIPs and current checkpoint/acceptance documents.

`build_r3_evidence.py` inventories every entry without following links, archives every regular payload and directory, retains symlink target bytes and hardlink group metadata, and embeds `R3-EVIDENCE-MANIFEST.json`. It verifies every ZIP member's CRC and payload SHA-256, then requires the input epoch's exact file set and metadata to remain unchanged before publishing a new completed archive. Existing output files are never replaced. Failed partial archives and diagnostic receipts remain available; unexpected source files are not deleted.

The ZIP must be created only after the evidence epoch is frozen. Builder and output paths stay outside the epoch to prevent recursive inclusion. Example:

```sh
python3 build_r3_evidence.py --epoch /path/to/epoch-20261007-r3 \
  --provenance FINAL-PROVENANCE.json --output /other/path/Intune_R3_Evidence_20261007.zip
```

`restore_r3_evidence.py` downloads and reassembles the public byte chunks, checking each chunk plus the **independently supplied final ZIP size and SHA-256**. It uses no credentials or third-party dependencies. Python 3.10+ and a POSIX filesystem with directory descriptors and `O_NOFOLLOW` are required. Use the actual manifest URL, byte count and checksum published with the R3 handoff:

```sh
python3 restore_r3_evidence.py --manifest PUBLIC_R3_DISTRIBUTION_MANIFEST_URL \
  --output Intune_R3_Evidence_20261007.zip \
  --bytes PUBLISHED_EXACT_SIZE --sha256 PUBLISHED_FULL_SHA256
```

The helper does **not extract anything or execute any archived file**. It does not contain the R2 fixed archive pins. Existing completed output is never replaced; interrupted downloads retain `OUTPUT.partial` and may resume after prior complete chunks are verified. Partial bytes are not a valid completed archive until every part and the final ZIP match their pins. Integrity failures preserve suspect partial bytes for investigation.

Distribution manifest schema is `intune-r3-evidence-split-release/1`: `archive` has `name`, `bytes`, `sha256`; ordered `parts` each have `name`, `bytes`, `sha256`, `url`. Additional provenance fields link the immutable R2 base, R3 source commit and exact product packages. Chunks are ordinary Git blobs below 96 MB, reached by public URLs pinned to their full data commit SHA. GitHub release-upload authentication previously returned 401; this uses the already authorized Git transport without new credentials or privileges.

The evidence ZIP intentionally retains symlinks as **literal link entries**. Do not use blanket `extractall`/`unzip`, follow the targets, or execute from an unreviewed extraction. If extraction is independently implemented, validate exact paths/types/member sets and each payload against the embedded manifest, use a new destination with no-follow descriptors, and quarantine literal link targets outside the executable source tree. This delivery helper qualifies reassembly only; it makes no new downstream extraction claim. Original fixture link semantics remain recoverable from the unchanged ZIP and typed inventory.

`test_r3_delivery.py` tests exact evidence preservation, link typing, hardlink inventory, existing-destination rejection, forbidden recursive output, special-file rejection, changed-epoch failure preservation, independent caller pins, byte reassembly/resume, corrupt chunks and HTTPS Range validation. Tests use tiny standalone fixtures and remain distinct from Intune product qualification. Run `python3 -B test_r3_delivery.py`.

`publish_r3_git_chunks.py` avoids duplicating all chunk bytes in a working tree: it streams each 96 MB range directly into a fresh bare Git repository, records every chunk's SHA-256, and stages its Git blob ID. It checks the complete streamed ZIP against the builder receipt before committing. The dedicated branch is `intune-r3-evidence-data-20261007`; the existing handoff checkout and unrelated default branch are untouched. `--push` explicitly publishes only a new branch and rejects an already-existing remote branch. Without that flag, no remote mutation occurs. The resulting manifest pins each public raw URL to the complete data commit SHA.

`verify_public_r3_download.py` downloads the separately checksum-pinned helper and manifest without an Authorization header, runs actual public reassembly, and independently rehashes the resulting complete ZIP. It preserves the command, stdout/stderr and a separate `PUBLIC-R3-DOWNLOAD-RECEIPT.json`. It does not extract the supplement.
