# Frozen R4 evidence production

`scripts/build-evidence-layer.py` creates a deterministic typed supplement from
the entire frozen R4 evidence epoch. It does not replace the complete repository,
qualify the application, execute fixture code, or approve public disclosure.
The separately preserved stopped provider candidate can use the same typed
format with its own input directory and provenance; it remains unqualified.

Freeze writers first. Put the provenance JSON, optional IPC omission document,
output archive and receipts outside the input directory. Independently review
and pin both documents. The provenance object must record the exact tested
source commit, existing recovery layer identities, intended public/private
disposition and the evidence epoch's scope; the producer records these claims
and their pinned document identity, not their truth or organizational approval.

```text
PINNED_PYTHON -B scripts/build-evidence-layer.py \
  --epoch EXACT_FROZEN_EPOCH \
  --output NEW_PRIVATE_PARENT/Intune_R4_Evidence_20261007.zip \
  --provenance REVIEWED_PROVENANCE_JSON \
  --provenance-sha256 EXACT_DOCUMENT_SHA256
```

Output and every ancestor must be real POSIX directories, not symlinks. Existing
archive, `.partial` or `.receipt.json` paths are refused without replacement.
The builder opens source directories without following links, inventories
every name and type, and holds file descriptors while checking identity,
size and bytes. It repeats the complete census and verifies source root identity
before accepting the result. Unanticipated files and changed inputs cause
failure; original evidence and failed partial archives stay available.

Every regular file is included, including failed attempts, nested `.git` data,
archives, source snapshots and deliberately hostile filenames. Literal symlinks
are stored as their exact target bytes and are never traversed. Hardlink groups
are documented but every named member receives its own exact payload. Names
with POSIX control/format characters stay literal and diagnostics are JSON
escaped. This does not qualify restoration on Windows. The fixed ZIP timestamp,
sorted traversal and canonical manifest produce identical archive bytes when
the same frozen input metadata, pinned documents and Python/zlib implementation
are used. The external receipt's wall-clock timestamps do not enter the archive.

The inner root is `Intune_R4_Evidence_20261007`; the manifest is
`R4-EVIDENCE-MANIFEST.json`, schema `intune-r4-evidence-supplement/1`.
The producer rereads every ZIP member, verifies CRC, SHA-256, sizes, types and the
exact member set before final publication. The receipt records the exact archive
and inner-manifest pins for the separately qualified
`scripts/restore-evidence-layer.py`. Restore regular payloads into a new private
directory and create literal links last. Never use blanket `extractall` or
execute recovered nested repositories.

After creating the final archive name without replacement, the producer opens
that name without following links and independently checks its identity and
exact bytes against the still-held written archive before accepting it or
removing the partial name. A substituted final name remains present with a FAIL
result. If recording a failure also fails, the original failure remains primary
and the escaped secondary diagnostic is retained on stderr. Both defects have
preserved independent failing-before and passing-after evidence; the earlier
successful ordinary fixture alone did not establish these boundaries.

Only explicitly declared transient sockets and FIFOs may lack transferable
payloads. They remain untouched at the source. Supply
`--ipc-omissions JSON --ipc-omissions-sha256 SHA256` with exactly this schema:

```json
{
  "schema_version": "intune-r4-ipc-omissions/1",
  "entries": [
    {"path": "relative/retired-fixture.sock", "type": "socket", "reason": "Retired local IPC endpoint; preserve its metadata, not a live listener."}
  ]
}
```

An absent declaration, missing declared path, changed type, duplicate path,
regular file/directory/link omission or other special file blocks the build.
The manifest records exact omission metadata, reason and document pin. With any
IPC omissions it reports `complete_evidence_epoch: false` and
`complete_archivable_evidence_epoch: true`; it never recreates an endpoint or
silently calls the original complete file set restorable. Retain the original
endpoint metadata and corresponding historical negative evidence.

Bounds match the extraction profile: fewer than 200,000 entries, 32 GiB regular
payload, 16 GiB individual file, 64 MiB manifest and 128 path components. A corpus
outside these limits requires review; removing evidence to fit is forbidden.

The focused developer tests use literal payload/hash/type assertions and actual
CLI build and restore commands, including preserved negative controls. Their
success qualifies this bounded helper, not an as-yet-unbuilt final multi-gigabyte
archive. Final public-suitability review, exact source/package linkage, full
layer identities, extraction/readback and production decisions remain distinct.
The historical three unexpected files remain unresolved regardless of a new
archive's result.
