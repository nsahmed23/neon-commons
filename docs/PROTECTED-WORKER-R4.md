# Protected worker continuation

The `worker` command separates durable job preparation and inspection from a
separately invoked execution process. It uses the existing engine, pinned native
OpenTofu adapter, signed approval authority and unchanged network-denied process
supervisor. Current admitted adapters are `synthetic_local_process_only` and
`native_local_opentofu_only`; the latter applies a generated local output fixture,
not a Microsoft365 resource. Live-profile claims are rejected explicitly.

The job context binds repository/revision, source file hashes, workflow/verifier
revision, run ID/attempt, tenant/cloud, stack/component, provider/backend principal,
effective-input/lock digests, backend declaration and object/assignment ownership.
The native request binds actual executable, configuration, saved-plan, plan JSON,
state lineage/serial/digest and implementation bytes. The enclosing independently
signed request binds the complete job manifest, so a changed run attempt or source
cannot reuse approval. Context fields in the current laboratory profile remain
declared labels, not authenticated CI or service identities.

An owner-private host policy outside the repository admits exact executors and
context digests and pins public approval keys plus the existing verifier/library.
Its separate authority directory stores one-time consumption, dispatch, outcomes,
events and per-object ownership reservations in SQLite with full synchronous
transactions. Job-local JSON cannot forge a completed authority outcome. Sharing
the host UID or controlling that directory defeats this boundary; deployed host
isolation and independently protected receipts remain qualification requirements.

The approver supplies a real signed receipt using the existing
`signed-operation-approval/1.0` format and domain. No private signing key is part
of a job or worker policy. The existing laboratory approval envelope is reused
only for these explicit local adapters; its legacy `provider_update` action label
does not claim the output fixture wrote a real provider resource.

Actual routes, inspectable with `--help`:

```text
python3 -B scripts/intune-iac.py worker prepare --job-root JOB --executor-root EXECUTOR --context CONTEXT --policy POLICY
python3 -B scripts/intune-iac.py worker review --job-root JOB --policy POLICY
python3 -B scripts/intune-iac.py worker run --job-root JOB --policy POLICY --receipt RECEIPT
python3 -B scripts/intune-iac.py worker attach --job-root JOB --policy POLICY
python3 -B scripts/intune-iac.py worker status --job-root JOB --policy POLICY
python3 -B scripts/intune-iac.py worker cancel --job-root JOB --policy POLICY
python3 -B scripts/intune-iac.py worker reconcile --job-root JOB --policy POLICY
```

Run belongs to a separately supervised service process. Prepare/review clients
may exit; attach/status never dispatch, duplicate or requeue work. This increment
does not install a daemon or deploy CI. The native qualification invokes the
service with no terminal stdin and its own process session after preparation and
review clients have exited.

Before dispatch, the worker checks unchanged source, policy, implementation,
executor, native plan and exact state; consumes independent signed approval; then
durably records dispatch before launching a child. The saved plan is copied into
a sealed anonymous file and applied by its exact descriptor. Authority expiry,
revocation, source/policy invalidation and cancellation are checked throughout
the bounded subprocess. A new plan is never silently substituted.

Cancellation before dispatch records `cancelled_before_dispatch` and releases
the cooperative reservation. A cancellation after dispatch, lost response, or
unverified readback records `outcome_unknown`, preserves a single mutation attempt
and keeps the ownership reservation. Recovery only observes existing state;
desired state does not establish that the approved execution completed. A new
receipt cannot replay an already dispatched job. Native completion additionally
checks a distinct second no-change plan. The synthetic subprocess profile
explicitly has no native second-plan assertion.

Changed-scope tests use actual Ed25519 signatures and real subprocess writes:

```text
INTUNE_TEST_VALIDATOR_LIBRARY=/path/to/the/qualified/libsodium.so.23.3.0 python3 -B -m unittest plugin_tests.test_protected_worker_r4 -v
```

The library location may vary; its qualified digest remains enforced by
`plugin_tests/signing_fixture.py`. A default-host library mismatch is retained as
a failed prerequisite, not repaired by accepting a different digest. R4 evidence
also retains the first actual CLI review failure and repair: the original review
returned an object in the scalar status field and failed the common CLI exit-code
contract. Native replay then passed prepare, review, separate service apply,
attach, replay denial and read-only reconciliation with independent raw-state
assertions.

The next adapter must integrate the real provider, native Azure backend and an
enforced reviewed egress/secret/filesystem boundary. `AZURE-BACKEND-R4.md` specifies
separate state versus coordination leases and state transition handling. Do not
pass production tokens to these local adapters, disable their network denial,
treat a Docker image or CI label as isolation evidence, or claim that the common
contract completes platform qualification.

The R4 recovery refinement keeps attested history/status and cancellation usable
when the reviewed source has changed. It reports `execution_validation=invalidated`
and the failure code while execution still performs every original admission
check. An approval consumed before the worker dispatch record is shown explicitly;
a dispatch without a durable outcome is pending or unknown, never proof of a
running process. Source review is bounded to 16MiB total, context32KiB and manifest
64KiB. These limits fail before publishing an unreadable job.

`protected-worker/source-inspection-before.txt` preserves the real failing-before
case where changed source prevented even inspection/cancellation. The current
focused result `green-06.txt` is 16/16 checks (superseding, not adding to, the earlier
13). `green-04.txt` preserves an incorrectly configured local replay without the
pinned validator environment; `green-05.txt` replays with the required library.
`native-03/receipt.json` qualifies the current worker/backend source through six
actual CLI invocations and a separate service process using pinned OpenTofu1.13.1:
review, exact-plan apply, independent raw state, no-change second plan, attach,
replay denial and read-only reconciliation. Its scope remains local output only.
