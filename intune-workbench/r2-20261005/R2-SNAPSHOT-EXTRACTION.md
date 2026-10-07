# R2 full continuation snapshot: extraction precautions

The R2 ZIP preserves the complete working continuation, including deliberately invalid symlink/hardlink fixtures and the actual native qualification provider-cache symlinks. Literal symlink targets refer to the original workspace. They are evidence, not portable execution instructions.

Before extraction, compare the archive size and SHA-256 to `CONTINUATION-SNAPSHOT-R2-RECEIPT.json`. Inspect `Intune_Atmos_Wally_Continuation_R2/CONTINUATION-SNAPSHOT-R2-MANIFEST.json` and its typed link inventory. Validate every archive path and reject duplicate names, absolute entry names and parent traversal. Read and verify every regular payload's size/hash against the manifest; do not treat matching self-supplied hashes as external authenticity.

Extract into a new directory with descriptor-based no-follow ancestor/final handling. Quarantine entries marked as symlinks as inert literal-target evidence outside the executable source tree; do not dereference them or recreate absolute targets automatically. Preserve the ZIP and manifest unchanged so the exact fixtures remain recoverable. The manifest also records hardlink groups; ordinary copies retain their bytes but do not reproduce hardlink rejection fixtures unless those links are deliberately recreated within an isolated lab. Inspect native provider-cache link targets before rebuilding them as local links in the relocated mirror.

Do not use blanket `extractall`/`unzip` or execute from an unreviewed extraction. No extraction helper for the R2 link-bearing ZIP has been qualified in this delivery. The existing `restore_release.py` is for the original release archive and is **not** claimed to support this R2 bundle. This delivery's verifier checks every ZIP member to EOF (CRC), every manifest payload SHA-256 and the archive checksum; it does not qualify downstream extraction.

Original archive receipts and the historical three unexpected temporary files remain preserved and unresolved. These deliberate new test/native links do not close or reproduce that historical discrepancy.
