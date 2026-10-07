# Complete R2 snapshot restoration

`restore_r2.py` reassembles the 24 Git byte chunks into the **unchanged** complete repository ZIP. Its 2,289,864,715 bytes exceed GitHub's per-release-asset limit. The existing authorized Git connection publishes 24 ordinary byte chunks on the dedicated `intune-r2-snapshot-data-20261007` branch (23 × 96,000,000 bytes and one × 81,864,715 bytes); the release-upload endpoint rejected upload authentication, so the same archive is distributed through Git without changed credentials or privileges. This is not a reduced bundle. The helper embeds the independently supplied ZIP size/SHA-256 and snapshot manifest SHA-256; each part is also checked against the distribution manifest.

Requires Python 3.10+ on a POSIX filesystem with directory descriptors and `O_NOFOLLOW` (Linux/WSL recommended). No additional packages, credentials, installation, tenant access, or execution of archive content is needed. The helper uses no authentication; the published manifest and chunks are publicly downloadable. The output and optional extraction parent directories must already exist and must not have symlink ancestors. Existing completed ZIP files or extraction directories are never overwritten.

```sh
python3 restore_r2.py \
  --manifest https://raw.githubusercontent.com/nsahmed23/neon-commons/intune-atmos-wally-r2-20261007/intune-workbench/r2-20261005/R2-DISTRIBUTION-MANIFEST.json \
  --output Intune_Atmos_Wally_Continuation_20261005_R2.zip \
  --extract Intune-R2-recovered
```

Replace `intune-atmos-wally-r2-20261007` with the full published handoff commit SHA supplied alongside this file. Chunk URLs in the manifest are pinned to the full data commit SHA, so branch movement cannot change the bytes requested. Manifest schema: `schema_version: intune-r2-split-release/1`; required objects are `archive` (`name`, `bytes`, `sha256`), `parts` (ordered objects with `name`, `bytes`, `sha256`, `url`), and `snapshot` (`root`, `manifest`, `manifest_sha256`). Extra provenance fields are permitted. HTTPS URLs (including commit-pinned raw GitHub URLs) and relative local part filenames are supported.

If a download is interrupted, rerun the same command. The helper keeps `OUTPUT.partial`, verifies completed parts, and resumes the unfinished part using HTTPS Range when available. A server that returns the complete part is handled by discarding its already-received prefix. Every part and the final ZIP must match their pins before publication of `OUTPUT`. An integrity failure preserves the suspect partial; investigate it and choose a new output name rather than silently deleting it. A `.partial` file is never evidence of a complete valid archive.

To verify an existing complete ZIP and safely extract without downloading another copy:

```sh
python3 restore_r2.py --manifest R2-DISTRIBUTION-MANIFEST.json \
  --archive-input Intune_Atmos_Wally_Continuation_20261005_R2.zip \
  --extract Intune-R2-recovered
```

Extraction validates every ZIP path, exact archive/manifest member sets, directory and file types, CRCs and payload hashes. Duplicate paths, traversal, special files, link-parent traversal and existing destinations are rejected. Every ancestor and output file is accessed through no-follow directory descriptors. Five symlink payloads are written as numbered **regular text files** beneath `LINK-QUARANTINE`, next to the recovered source root. Their original paths and literal targets are recorded in `EXTRACTION-RECEIPT.json`; no symlink is created or followed. Hardlink groups remain in the unchanged manifest and receipt, but are restored as separate ordinary files. Recreating those negative-fixture/native-cache links requires deliberate inspection and an isolated lab. The original ZIP remains unchanged and retains the exact fixtures.

A failed extraction is left in place with no PASS receipt; inspect it and use a new destination. The historical three unexplained temporary files remain unresolved. This helper's successful extraction does not close that historical discrepancy or qualify execution of code, native hosts, cloud providers, devices, or production deployment.

The helper is distribution tooling added after R2; it does not modify R2 source, receipts, or its archive. `test_restore_r2.py` tests byte preservation/resume, integrity failures, exact member sets, traversal/duplicates, nonreplacement, symlink quarantine and HTTPS Range handling. Run `python3 -B test_restore_r2.py`. These fixtures are separate from the original 1,141 Intune qualification tests.
