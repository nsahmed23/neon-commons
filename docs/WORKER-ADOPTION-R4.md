# Protected state-only adoption

The integrated native import uses an independent signature and the existing
service authority. Ordinary saved-plan apply permissions remain separate.
Checkpoint12 (`72c090f3`) qualified the actual pinned native import, first no-change
plan and subsequent same-authority maintenance. `NATIVE-ADOPTION-EVIDENCE-INDEX-02.json`
records those historical source and assertion scopes. External qualification,
organizational approval and qualification of the exact final package remain
separate gates; later repairs do not rewrite those earlier receipts.

`worker_adoption.py` uses the same physical `service.sqlite3` `jobs`, `ownership`,
`consumed`, `revoked` and `events` tables as `ServiceJob`. Its additive
`adoption_operations` table identifies the distinct operation and one first-plan
attempt. The existing object-plus-assignment scope and physical state-blob scope
are unchanged. A prepared import blocks ordinary apply and vice versa. Cancellation
releases only an undispatched import's own reservations; any possible dispatch
retains them until independent qualification. Reopening never redispatches.

The review document is `native-state-adoption/1`. The separate approval payload is
`signed-native-state-adoption-approval/1`; signed bytes are
`b'intune-workbench:native-state-adoption-approval:v1\x00' + canonical(payload)`.
The delimiter is an actual terminal NUL. Ordinary apply signatures, wrong
manifest/identity/source/ref/attempt/expiry, JSON runtime claims and spent
approvals confer no import permission. Cryptographic verification uses the
existing pinned verifier and independently configured external signer policy.

The signed `intended_writer` identifies the exact selected scope and bound provider principal as both intended policy and assignment writer. It explicitly leaves organizational sole-writer approval and absence of external writers unestablished.

The manifest binds the original empty receiving-state bytes and strong revision,
independent complete Graph preimage, exact provider/source/lock/runtime inventory,
identity/host-storage/run capabilities, reviewed ownership search and fixed native
import command. It also binds a separate fresh host and Plan-only broker policy
for one first-plan verification. Neither operation permits Graph writes; the
verification policy permits no state-content PUT. Native Azure lease/metadata
operations remain explicit backend mutations in their reviewed narrow lifecycle.

`OwnershipAdmission` re-reads the latest actual native-state-file ownership scan,
the scan declaration, its original state bytes and every indexed repository
scope. Imported ownership JSON cannot supply the capability. This initial profile
requires exactly one complete declared backend and rejects additional indexed
scopes, stale/incomplete/owned/conflicting evidence and any changed source. The
selected repository, stack, component and physical backend URI must exactly match
the reviewed run context. The result establishes no owner within that complete
declared scope; it does not establish absence of external writers or authenticate
the local copy of state. A distinct actual receiving Azure GET and process-held
identity binding must match those bytes immediately before dispatch. The service
read-to-write race remains bounded but non-atomic; no global Graph fencing is
claimed.

The trusted controller creates `laboratory_runtime(...)` or `live_runtime(...)`
using exact typed capabilities and the closed `NativeAdoptionProviderAdapter`.
It calls `AdoptionJob.run(signed_receipt, runtime=runtime)` once. Before any native
work, a durable common-authority transaction consumes approval, fixes the owner
process identity and records the authenticated baseline plus canonical exact signed receipt and SHA in the shared `approval_transcripts` table. The caller receipt is snapshotted once before verification; later caller mutation cannot replace its transcript. A transcript insert failure rolls back consumption before dispatch. Historical rows without a transcript remain explicitly unretained. The worker uses the
existing isolated Docker host, fixed relay, broker, Atmos, OpenTofu and provider.
The actual generated source and control bytes must match the closed adapter;
manifest strings cannot supply arbitrary commands or environment values.

`job.verify_first_plan(runtime=runtime)` first independently authenticates and
reads the imported state, verifies the closed successor projection and freshly
captures Graph parity. It then consumes the one preapproved Plan-only attempt,
runs the separately pinned native controls and retains the binary/JSON/exit code.
A successful host return causes a bounded guarded read of the exact binary,
JSON and exit-code bytes. New exclusive archived copies and a receipt bind their
hashes to that host outcome before durable result publication. A recording error
or cancellation preserves the host outcome, unknown status and reservations.
`worker_plan_evidence.py` checks the complete fixed native representation: exit0,
no-op, no drift/output/deferred changes, exact immutable identity, before/after/
planned/prior full values equal the independently received state, and literal
configuration equal the reviewed source and intended values. JSON booleans,
integers and floats remain distinct; assignments include the full exclusion and
include-filter targeting. Both working and archived bytes, the reviewed source
and receiving-state bytes are checked again before reconciliation releases
ownership as `adopted_verified`. The helper establishes content relationships;
it cannot authenticate receiving state, mint a completion or grant authority.
The binary/JSON relation relies on the closed pinned host command and the
authenticated controller's immediate capture, not a decoder for opaque plan
binaries. Local trusted-controller custody remains an explicit profile boundary.
Unsupported management mapping cannot become apply permission or endpoint-health
evidence. Historical pending first-plan outcomes without this retained output
capture fail closed; their records are not rewritten or silently upgraded.

Primary, cleanup and recording failures remain distinguishable. A secondary
recording failure cannot silently discard the first cause; real KeyboardInterrupt
or SystemExit during cleanup retains cancellation intent with the primary cause.
An uncertain authority commit or missing archive never causes import replay.

The text interface is deliberately limited:

```
python -B scripts/intune-iac.py adoption prepare --job-root NEW --policy POLICY --manifest MANIFEST
python -B scripts/intune-iac.py adoption review --job-root JOB --policy POLICY
python -B scripts/intune-iac.py adoption status --job-root JOB --policy POLICY
python -B scripts/intune-iac.py adoption attach --job-root JOB --policy POLICY
python -B scripts/intune-iac.py adoption cancel --job-root JOB --policy POLICY
python -B scripts/intune-iac.py adoption recover --job-root JOB --policy POLICY
```

The shared terminal also exposes `adoption-review/status/attach/cancel/recover
JOB POLICY`, requiring the active tenant and selected immutable object to match.
There is no terminal run, signing-key import, live-capability JSON or arbitrary
native command route. Normal `service` APIs reject adoption manifests explicitly.

Initial recovery cancels authority, refuses cleanup while the exact controller
is alive, stops only its recorded container and preserves uncertain ownership.
It cannot automatically release an Azure lease, re-import, reconstruct an old
captured-observation capability from files or mark unknown execution successful.
Fresh-process original-contract observation, distinct signed initial-import
lease recovery and the separately signed Plan-only recovery bridge are now
integrated. Their current code and focused local contracts do not establish a
new native interruption/release/reconciliation pass. The shared no-op repair
closes retained parser counterexamples; the new native route and exact final
package must be qualified against its new source. A distinct stopped-Plan phase
adapter for initial verification or a recovery Plan's own interrupted lease
remains separately staged until reviewed and qualified. No original import or
Plan is replayed. Ordinary apply/committed-state recovery gates are not broadened.

The historical admission replay is `qualify_adoption_contracts.py --output NEW` under the R4
service evidence directory, using `INTUNE_TEST_VALIDATOR_LIBRARY` to name the
retained exact validator where needed. Its receipt separates actual loopback
identity/read operations, real independent signatures and raw shared SQLite
assertions from injected recording faults. It performs zero native imports.
Historical failed gate receipts and before-source snapshots remain unchanged.

After actual native completion, append a new ownership scan from the independently
received imported state and publish a fresh authenticated observation. Keep the
original empty-state scan/source, import receipt and first-plan artifacts intact.
The protected adoption journal remains reachable through its own text interface. `workbench adoption-link --root STORE --object UUID --job-root JOB --policy POLICY` appends a distinct `adoption_receipt` navigation artifact; `workbench adoption-history --root STORE --object UUID` and selected four views reopen that exact registered adoption journal. The shared terminal offers the same adoption-link/history paths. State-only adoption never supplies a Graph deployment or last-apply comparison baseline. The inactive native Windows reader surfaces the protected journal as unsupported without opening it. Do not pass adoption to ordinary `service-link`.

The controller can publish the exact final proof capture through `job.completion().captured_observation(job)` immediately after successful verification. This accessor returns only the fresh process-held sealed observation used in reconciliation; a reopened job or supplied JSON cannot recreate it. A separate later capture remains a distinct observation.

No real Azure/Graph authorization, production encrypted-host custody, CI identity,
device effectiveness, enterprise host qualification or accountable organizational
approval is established by these laboratory controls.
