# Private encrypted archival

`artifact seal`, `artifact inspect` and `artifact restore` archive exact bytes
using the existing pinned libsodium implementation of XChaCha20-Poly1305-IETF.
State, binary plans, exported plan JSON, raw captures, receipts and observation
backups use the same bounded format. This is archival implementation, not a
claim that the running worker, SQLite store or Azure storage is encrypted.

The host supplies a 32-byte key through an inherited descriptor numbered at
least 3. No command generates a key or grants access to a service. Key material
is absent from arguments, output and receipts. A private key file must be owned
by the invoking UID with no group/other permissions; a pipe is also accepted
with a two-second read bound. Python cannot guarantee erasure of every in-memory
copy. Host compromise and debugger access are outside this boundary.

Inputs are regular private files, at most 64 MiB. Outputs require an existing
private parent directory and a new destination; symlinks and overwrites are
rejected. Publication stages, fsyncs and exclusively links the completed file.
Every ancestor is opened without following links, and reads and publication
use names relative to the held parent directory descriptor. Replacing a parent
pathname after admission cannot redirect bytes into its replacement. If another
process renames that directory, an operation can finish in the original inode
at its new location; this is not same-account hostile-process isolation. Protect
the archival directory from concurrent administrative moves during a procedure.
Original plaintext inputs remain unchanged. Encryption uses a random 24-byte
nonce; archives intentionally differ while recovered plaintext is byte-exact.

The authenticated header binds format, algorithm, artifact kind, expected
operation/context SHA-256, exact plaintext length/hash, key identifier and
retention date. Header metadata is not encrypted, so the archive and its receipt
remain private. `inspect` labels all metadata unauthenticated. Only successful
`restore` authenticates it, after checking the independently supplied expected
kind and context. Possessing an archive or key never authorizes execution.

Actual entrypoints (replace uppercase paths/digests with reviewed values):

```bash
PYTHON -B scripts/intune-iac.py artifact seal --help
PYTHON -B scripts/intune-iac.py artifact restore --help
PYTHON -B scripts/intune-iac.py artifact inspect --input PRIVATE_ARCHIVE
```

For sealing/restoring, the invoking host opens the private key on descriptor 3
and passes `--key-fd 3 --library PINNED_LIBRARY --library-sha256 LIBRARY_SHA256`.
Seal additionally requires `--input`, `--output`, `--kind`,
`--context-sha256`, `--key-id`, and `--retain-until` (UTC epoch seconds).
Restore requires the same expected kind/context, input and new output paths.
The native implementation is currently Linux only; the parser remains
available elsewhere without claiming native qualification.

The retained validation library is
`work/evidence/epoch-20261005/approval-prerequisite/libsodium.so.23.3.0`, SHA-256
`fe00408090ea084504d7cb0130af56a22554fe299034b864551b65a64ca8a7b5`.
**Use the actual receipt/library digest, not a copied filename, for admission.**

Recovery procedure:

1. The artifact/key owners retain the immutable archive, its independent hash
   receipt, context manifest and separately access-controlled key backup.
2. On a new private recovery directory, verify the archive's independent hash
   and the pinned native library. Restore using the backup key, expected kind
   and expected context. A wrong key, changed header/body or truncation must
   produce no output.
3. Independently compare the restored bytes/hash against the retained original
   receipt. For a database backup, use the existing `workbench restore` into a
   new store, then independently inspect identity/history/last-good values.
   For state or a plan, restoration itself does not permit apply/replay.
4. Record operator, source/archive hashes, recovery output hash, result and
   custody. Reopen key access only through the organizational key owner's
   established process; key provisioning is not authorized by this runbook.

`retain_until` is authenticated policy metadata, not a host deletion lock.
This module has no automatic expiry deletion. Retention/legal-hold disposition,
key rotation/revocation and deletion require the artifact/key owners' policy;
revoked/compromised key archives must be quarantined and re-encrypted under an
authorized replacement with linked receipts. Old archives and failures are
preserved according to that policy. A host owner who can delete files or keys
can defeat availability; this module does not claim otherwise.

Qualification: `plugin_tests.test_artifact_vault_r4` drives the actual CLI for
all six artifact kinds and independently compares exact restored bytes,
including binary NUL/CRLF/non-UTF8. It tests separate archive/key backup recovery,
random nonces, wrong key/context/type, changed header/ciphertext, truncation,
append, private permissions, symlink/overwrite denial, size and native pin
rejection. This does not replace external AppSec review, encrypted runtime
volumes, Azure storage controls, credential custody or tested organizational
key recovery.

`plugin_tests.test_artifact_path_race_r4` preserves two deterministic
failing-before/passing-after controls at the actual read/staging open boundary.
The native library must successfully initialize and report the expected key,
nonce and authentication-tag sizes before any encryption or decryption.
