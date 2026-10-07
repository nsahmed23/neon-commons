# Native lease recovery inspection — R4

An interrupted OpenTofu Azure backend can leave an infinite native state lease.
The broker's pre-dispatch journal retains its proposed/active UUID and exact
Terraform lock metadata. Cancellation denies subsequent traffic; reopening an
expired broker never revives execution authority.

`worker_recovery` provides a separate **read-only** inspection command:

```sh
python3 -B -m intune_iac.worker_recovery inspect \
  --journal /private/operation/broker.sqlite3 \
  --policy /private/operation/exact-approved-broker-policy.json \
  --output /private/recovery/new-inspection.json
```

It checks private files, exact journal/policy digest, declared route/lease target,
closed metadata and unchanged journal bytes. It opens SQLite read-only and never
constructs a broker, identity, transport or lease-release capability. Expiry is
reported without being reset in the stored policy. Receipt creation is exclusive
0600; stdout contains only its path/hash and zero-remote-actions assertion.
Hot rollback/WAL/shared-memory sidecars are preserved and reported as blocked,
not silently repaired, removed or ignored. A private journal may contain sensitive
lease authority-bearing IDs: encrypt exported recovery receipts and restrict
access just as the source journal.

The receipt proves local persisted facts only. It does not prove the current
remote lease, current Blob state, service convergence or safe release.

Recovery procedure for the still-unqualified real Azure route:

1. Preserve the signed service operation, scope reservation, original policy,
   broker database and sidecars, host cleanup evidence, native output and exact
   source/tool/plan identities. Run the inspection command into a new private
   location. Do not repeat execution, import or force-unlock.
2. Use the independently authenticated exact backend identity and bound account,
   container and key to issue read-only HEAD/GET for that blob. Record current
   ETag/version, lineage/serial/content hash, Blob lease state and Terraform lock
   metadata. Independently inspect the exact Graph policy/settings/assignments
   using the separate reader identity. Preserve partial/unknown outcomes.
3. Compare the current lock ID and metadata with the pre-dispatch record, native
   operation, current state and service outcomes. A missing/foreign lock, changed
   ETag/context, another active worker or unresolved state-write uncertainty
   stops automatic progression. Keep coordination ownership while unresolved.
4. Prepare a new separately reviewed recovery operation, binding all observations
   and the exact existing lease UUID. The only candidate release request is
   `PUT https://<bound-account>.blob.core.windows.net/<bound-container>/<bound-key>?comp=lease`
   with empty body, `x-ms-lease-action: release`, exact `x-ms-lease-id`, pinned
   supported storage version and authenticated backend bearer supplied through a
   protected host channel. Never use `break`, acquire another lease, or pass a
   bearer token on a command line. Approval must cover this recovery operation,
   not reuse the consumed/cancelled execution approval.
5. After an authorized release, independently HEAD/GET and verify unlocked state
   and unchanged expected content, reconcile policy/assignment/state outcome,
   retain the original uncertainty, and only then resolve ownership through the
   service recovery route. A fresh correction requires a new exact plan/review.

Step 4 now has a separate process-held authorization adapter in
[`worker_lease_recovery`](WORKER-LEASE-RECOVERY-R4.md), with a new signature domain,
exact backend observation and one-use consumption in the original service
authority. The inspection CLI itself remains read-only. The adapter's local TLS
qualification is distinct from real nonproduction Azure interruption/release
qualification and an organization's explicit recovery authorization. Existing
`tofu force-unlock`, `az` or arbitrary REST tools must not bypass that authority
path. No production release has been performed or authorized here.

Local verification:

```sh
python3 -B -m unittest plugin_tests.test_worker_recovery_r4 -v
```

The five checks cover the real module CLI/private exclusive output, expired
inspection without byte changes, substituted policy/target rejection and retained
hot-journal blocking. SQLite fixtures do not qualify an Azure lease release.

The actual signed native worker cancellation control subsequently passed14
independent assertions at
`worker-broker/native-cancel-acquire-01/qualification-receipt.json` (SHA256
`f17166cb16fc383195f72e6342b608c655ecaa2bdc67e305079c3057ace947c8`). A
nonforwarding fixture triggered the real service cancel CLI only after the pinned
native backend acquired its lease. The broker retained `outcome_unknown`, the
exact proposal was recoverable from the journal, state/Graph bytes stayed
unchanged, no provider writes or implicit unlock occurred, ownership remained
reserved, and Docker confirmed stopped/removed cleanup. The synthetic remote
lease remains preserved for investigation. The happy-journey runner's expected
failure is retained separately from this negative-control acceptance receipt.
This does not qualify live Azure recovery or authorize lease release.
