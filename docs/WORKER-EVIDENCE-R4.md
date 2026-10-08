# Signed read-only worker evidence

This component carries exact registered saved-plan service evidence from the
protected worker to a separate persistent reader. It does not run, approve,
recover or cancel any operation. Adoption is a distinct schema and is rejected
by this first export profile. The guarded native Windows verifier/persistence
component is implemented and remains subject to actual DLL/host qualification;
the ordinary Windows profile is unchanged.

The portable contract uses the existing Ed25519 signature and strict pinned
OpenSSL/libsodium validation. A separately configured `worker-evidence-trust/1`
policy authorizes the evidence-publisher purpose, allowed tenant/object/profile,
public keys, validity bounds and revocations. An execution approver does not
implicitly acquire publisher purpose. The tool loads no private signing key and
creates no real credentials. Organization key custody, a private artifact route,
ACL/retention and exact native Windows verifier dependencies require their own
approved environment and actual qualification.

On the protected POSIX host, `prepare` opens only existing private source files
and coherent SQLite `mode=ro` transactions. It never constructs ServicePolicy,
migrates the authority database, checkpoints WAL or recovers a hot journal. Any
journal/WAL/SHM node, non-DELETE journal mode, schema mismatch, changing source or
bounded-query failure stops the read and preserves evidence. `snapshot.read_at`
is the actual read time; signature issue time cannot refresh an old observation.
This is a cooperative protected-host filesystem contract, not protection from a
hostile process with the same account and arbitrary filesystem access.

`ServiceJob.run` freezes the signed approval once before verification, then
retains the canonical exact verified receipt, SHA-256 and consumption time in
`approval_transcripts`, in the same transaction as consumption and dispatch.
Recording failure prevents dispatch. Legacy rows remain unretained. Exported
legacy status is inspectable but cannot become an admissible portable baseline.
A historical signature is checked at its retained dispatch time and against its
original consumed nonce/manifest, never reused as a new execution permission.

The request binds tenant/object/operation, original manifest, saved plan,
execution/run digests, original source revision/content, run ID/attempt and exact
trust policy. The statement binds that request, publisher purpose/source,
original manifest/transcript, complete bounded selected-job event sequence,
status/outcome, reconciliation and the exact independent raw capture members.
The publisher's current revision is distinct from the original controller's
revision. Original run-context labels do not become external CI attestations.

The common `deployment_state` function is also used by the local service view.
It requires converged state, known host completion, released reservation, no
mutation replay and one exact reconciliation event/readback binding. Portable
promotion additionally requires original approval verification, signed publisher
scope and independently reconstructed raw capture bytes/provenance. Unsupported
normalization retains raw values; denied/incomplete capture never establishes a
baseline. Laboratory, service convergence, second no-change plan, endpoint
health, platform qualification and organization approval remain separate.

## Actual CLI and exact bytes

The staged/new entrypoint is `scripts/intune-worker-evidence.py`:

```text
python -B scripts/intune-worker-evidence.py request --manifest MANIFEST --trust TRUST --output NEW_REQUEST
python -B scripts/intune-worker-evidence.py prepare --request REQUEST --trust TRUST --publisher PUBLISHER --job-root JOB --policy WORKER_POLICY --capture-root CAPTURE --store-root WORKBENCH --output NEW_STATEMENT
python -B scripts/intune-worker-evidence.py assemble --statement STATEMENT --signature DETACHED_SIGNATURE --request REQUEST --trust TRUST --verifier VERIFIER_PIN --scratch PRIVATE_SCRATCH --output NEW_ENVELOPE
python -B scripts/intune-worker-evidence.py inspect --envelope ENVELOPE --request REQUEST --trust TRUST --verifier VERIFIER_PIN --scratch PRIVATE_SCRATCH
python -B scripts/intune-worker-evidence.py ingest --envelope ENVELOPE --request REQUEST --trust TRUST --verifier VERIFIER_PIN --scratch PRIVATE_SCRATCH --evidence-store EXISTING_PRIVATE_STORE
python -B scripts/intune-worker-evidence.py reopen --request-sha256 REQUEST_CONTENT_SHA256 --trust TRUST --verifier VERIFIER_PIN --scratch PRIVATE_SCRATCH --evidence-store EXISTING_PRIVATE_STORE
```

The existing authorized external signer signs the actual NUL-terminated domain
`intune-workbench:worker-evidence:v1` followed by canonical statement bytes.
`assemble` accepts only a 64-byte detached signature and emits a NEW envelope.
Transport the restricted evidence through the existing approved private channel;
these commands do not deploy a listener, transfer tenant captures publicly or
configure another CI platform.

`ingest` first retains exact bounded incoming envelope and request bytes in a NEW
private attempt directory, including invalid JSON/signatures. It distinguishes
byte SHA-256 from canonical content SHA-256. It derives ledger/head keys only
from frozen verified content, never a caller's subsequently mutable dictionary.
Same-content repeated requests are idempotent; conflicting content for an admitted
request, decreasing event sequences and same-sequence event forks are refused.
A local receipt does not establish globally linearizable ordering across clients.
Every reopen checks retained byte hashes, signature, scope and current trust/time;
persisted success labels never replace verification. An expired bundle remains
retained historical bytes and is not current worker status.

The POSIX evidence store uses a separate database. The inactive native receiver
uses its existing Workbench store metadata transaction and guarded attempt files.
CLI verification/ingestion/reopen and shared Workbench navigation are implemented.
Native DLL, storage and platform qualification remain required before activating
the Windows profile. No `verified=true` JSON grants an execution capability.

## Qualification scope and replay

`plugin_tests/test_worker_evidence_transcript_r4.py` uses actual signatures and
SQLite transactions, with an explicit stop before native dispatch. It preserves
original missing-table failures and verifies caller mutation and recording faults.
The ordinary service's existing native Docker/TLS and shutdown controls are a
separate changed scope; counts overlap and must not be added.

`plugin_tests/test_worker_evidence_r4.py` drives actual signed CLI preparation,
assembly, ingest and reopen; exact worker source files/database bytes are
independently compared. It uses sealed laboratory Graph capture and actual TLS
backend readback, but its host-completed journal is explicitly a modeled fixture,
not new native provider execution. Controls include target/source/attempt/plan,
purpose/key/signature/revocation, stale read time, missing legacy approval,
reordered events, raw member substitutions, hot-journal preservation, exact raw
input bytes, caller mutations, primary/secondary failures and malformed/deep
CLI input. Before and after receipts remain separately pinned.

All raw fixtures, synthetic keys, compile-generated staging bytecode and failed
attempts are retained with provenance. Neither a passing signed fixture nor this
package establishes live Azure/Graph, native Windows, hosted CI, device evidence,
AppSec clearance or organizational pilot approval.

## Persistent receipt navigation and historical scope

`intune-iac.py workbench evidence-link --help` and `evidence-history --help` expose
received evidence through the same shared four-view engine. The text workspace
accepts `evidence-link EVIDENCE_STORE REQUEST_SHA256 TRUST_PATH VERIFIER_PATH PRIVATE_SCRATCH`
and `evidence-history` for its selected object. Links are inert metadata, never
execution authorization or a cached verification flag. Each read checks original
received serialization hashes, canonical signed content, current trust/signatures,
exact tenant/object/manifest and retained dispatch-time approval. Source revision,
original controller implementation and publisher implementation remain distinct.

Expired or stale snapshots can be reopened with `--historical`; this still
requires original valid signatures and current trust. Historical views retain
snapshot status but show current worker status unknown and cannot advance an
active deployment baseline. A missing old original approval transcript is not
reconstructed. Raw synthetic capture contradicting an authenticated live label is
retained as `contradictory_signed_worker_evidence` and is never an admissible live
baseline. Signed claims do not make an organizationally dishonest publisher
impossible; consistency checks prevent contradictory retained bytes from being
silently promoted.

Publisher-level ordering is shared across POSIX and the inactive native receiver.
The high-water scope deliberately excludes signing key ID, so an authorized key
rotation cannot replay an earlier selected-job sequence or fork equal-sequence
events. Byte hashes and canonical-content hashes have separate names. Original
failed received bytes remain in a new attempt directory. Signature, SQLite close,
output-recording and cleanup failures preserve primary errors and interruption
causes rather than returning success. See WINDOWS-WORKER-EVIDENCE-R4.md for the
inactive native adapter and actual remaining DLL/host/channel qualification gates.

A stored request is not automatically the latest known receipt. Both receivers
re-read their exact request index and publisher-level head after cryptographic
verification. A lower sequence is returned as `superseded_signed_snapshot`, with
historical status preserved, current status unknown and baseline false. An absent
head or equal-sequence fork fails. This closes reopening an older still-unexpired
receipt after accepting a newer one. The local index remains a cooperative client
record, not a tamper-proof global audit service.

Exact worker-service-operation/2 manifests retain the complete
`source_authoring_binding` under the same ordinary approval signature domain.
The pure decoder checks the closed top-level schema and operation/provider/source
cross-bindings while preserving all historical Git/root/materialization detail
and original limitations. It never constructs `RepositoryExecutionIntent`, reads
remote Git or re-attests an old controller. Worker-service-operation/1 remains
explicitly unassociated; no v2 field is silently discarded or relabeled as v1.
The same read-only channel accepts two closed, distinct state-only domains:
`native-state-adoption/1`, `native-adoption-recovery-plan/1`, and the distinct
phase-aware `native-adoption-recovery-plan/2`. Their original
approval schema and NUL-terminated signature domains remain distinct from an
ordinary saved-plan apply. A recovery receipt includes the exact original adoption
manifest, journal and retained original approval; missing transcripts stay
explicitly unqualified. Neither domain can become a Graph deployment baseline.
Unknown future recovery versions are rejected; there is no relabeling or
automatic migration.

The request is `worker-evidence-request/2` with an explicit operation kind,
original-manifest hash where applicable, and a literal null saved-plan hash:
state adoption and a fresh Plan do not pretend to execute a saved apply plan.
The actual export route uses the existing request/prepare/assemble commands.
For retained first-Plan qualification, add `prepare --state-raw PRIVATE_STATE_RAW`
with the exact independently recorded receiving state. The exporter reads the
registered rollback-mode SQLite journal without recovery or writes, the literal
archived plan binary/JSON/exit/receipt, and materialized source from the manifest's
source root. If artifacts are absent, history remains available with explicit
missing-evidence reasons. Hash, type, target, approval-domain or raw-content
contradictions fail; incoming bytes remain preserved by the receiver.

`worker_plan_content.py` contains the portable pure decoder extracted unchanged
from the existing native worker's content checks. The worker's existing
`worker_plan_evidence.py` reuses it, so full before/after/planned/prior state,
source expressions, assignments, exclusions, filters, types and no-op rules are
one contract. The receiving state and source byte hashes must match the signed
proof; output bytes must match the earlier durable output record and host-result
hash. This checks signed historical evidence consistency. It does not recreate a
sealed controller capability, independently contact Graph/Azure, authenticate
remote Git, establish endpoint effectiveness or confer platform approval.

All three operation kinds use the same exact-byte receiver, publisher high-water
ordering, current-trust revalidation, explicit historical demotion, shared
`evidence-history`/four views and native copy-store backup/restore. State-only
history always reports `baseline_admissible: false`, `graph_deployment: false`
and `execution_authorized: false`, even when its retained state/Plan content is
consistent. Unknown original execution remains unknown after recovery.

Source-association filesystem facts accept exactly historical inner binding/git-storage
version 1 (safe JSON integers) and current version 2 (canonical decimal uint64
strings). The latter preserves large native inode values without widening the
global JSON numeric gate. Unknown versions, signs, leading zeros and overflow
are rejected. These remain signed historical filesystem facts, not a newly
issued local repository capability.

Recovery history retains the original adoption's reviewed policy hash separately
from the currently supplied same-authority source policy hash. A later immutable
policy may admit the new Plan without rewriting the original job's policy file.
Only that nested historical original may have a different reviewed policy;
selected-job export still requires its actual current admission/binding. The
later policy is never described as attesting the earlier dispatch.

Recovery raw-capture linkage uses exactly the retained
`adoption-native-lease-recovery-observation/1.adoption_capture.capture_sha256`
field. Initial adoption uses its distinct `receiving_state.graph_capture_sha256`.
The decoder does not search alternate labels or accept a renamed shape. Plan
content proofs compare canonical typed JSON; boolean/number aliases and a
boolean false masquerading as exit code zero are rejected.

Plan v2 preserves its exact full stopped-phase original facts (including the
broker/lease fields), selected phase identity, and bounded ancestor declarations.
The read-only source transaction retains the matching registration rows,
consumed approval transcripts, immutable successor edges and observed release
rows. The pure reader cross-checks these against signed hashes and the declared
chain, and verifies retained predecessor Plan approvals in their own v1/v2
domains at their historical dispatch times. Missing old transcripts remain
unqualified; copied rows cannot mint a stopped-phase or release capability.
At most 31 ancestors are accepted for an already declared new child, matching
the worker's refusal to create a child at its 32-edge bound. Cycles, changed
phase rows, unobserved releases, unknown schemas and mismatched domains fail.
Version 2 uses exactly `adoption-plan-native-lease-recovery-observation/1` for
its capture linkage; original recovery v1 keeps its own distinct schema.
All received evidence/store/history/backup behavior remains shared.

The terminal predecessor is retained explicitly from the same read-only source
transaction. A selected v2 predecessor requires its immutable edge and remaining
chain; only the original initial verification or a v1 recovery Plan may terminate
it. Exact terminal row bytes, manifest and original approval remain bound even
after the original job's current status advances through reconciliation. The
current status is presented separately from the historical stopped-phase fact.
