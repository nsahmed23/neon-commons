# Operations and external qualification

This document applies to the 2026-10-04 engineering epoch. It does not grant a
tenant permission or record an organizational appointment. Local synthetic
qualification, actual tool observations, model reviews and live service evidence
have separate acceptance decisions.

## Operator entry and support

Use the exact archive receipt and `scripts/verify-release-artifact.py` before
installation. Install the ten hash-locked wheels into a fresh CPython 3.12.14
Linux x86_64 environment; run `scripts/verify-dependencies.py` and `pip check`.
The observed host used kernel 6.18.44 and glibc 2.39. Other builds require their
own replay; compatibility within a minor Python version is not qualification.
Run with an absolute, reviewed interpreter path and isolated Python startup:

```sh
/absolute/venv/bin/python -I /absolute/intune-iac/scripts/intune-iac.py doctor
```

The invoking shell and interpreter are trusted host components. Starting a
wrapper cannot undo commands already executed by a compromised shell profile.
Do not run from a shell session with untrusted startup code. The protected
provider path is Linux x86_64 only and rejects other platforms. Windows,
PowerShell and Git Bash qualification is a separate required gate before those
profiles can be advertised; a Linux script replay is not that evidence.

Local filesystem assertions assume private, stable paths and cooperative
writers using the product's locks. They do not contain another process with
the same OS identity or an attacker able to swap ancestor directories, mount
points or runtime libraries. Current provider controls do not supply a complete
filesystem/Unix-socket allowlist or aggregate descendant memory/process limit.
An independently enforced and qualified execution boundary is a release gate,
not a deployment configuration that this runbook supplies.

The admitted policy and identity restrictions remain in PRODUCTION-MAPPING.md,
IDENTITY-BINDING.md and PROVIDER-JOURNEY.md. This epoch's modeled service is a
fixture, never an alternative authentication mode for production. Do not
convert its settings coverage into additional supported provider policy types.

## Monitoring and evidence

The execution owner must collect exit status and the exact operation, plan,
source, toolchain, target, backend and state bindings from the protected
receipts. Alert on incomplete inventory, rejected approval, changed dependencies,
lease loss, missing state/receipt, cancellation after dispatch, mismatched readback
and unknown outcomes. A missing result is not successful execution.

Preserve the private authority database across restarts and upgrades. A public
hash chain alone cannot prove dispatch, prevent a writer from rewriting history,
or replace an independently protected receipt. Keep source exports, state and
saved plans in access-controlled storage; plans and state can contain secrets
even when the terminal masks values. Capture minimal diagnostics and redact
credentials before any human or model review. No external telemetry destination
is enabled by this runbook.

The organization must set retention periods and incident-preservation overrides
for captures, plans, state versions, approval records and audit logs. Do not
delete the only uncertain-outcome evidence during cleanup. Cleanup must be
restricted to recorded task-owned paths and processes.

## Credential and approval revocation

1. Stop new dispatches for the affected tenant and backend. Preserve the current
   source/tool/plan hashes, state lineage/serial and bounded event records.
2. The authorized identity owner revokes the affected application credential or
   grants, determines token lifetime and residual access, and rotates the
   credential using the organization's protected secret delivery mechanism.
3. The approval owner revokes affected signing key IDs in the private authority
   store using its documented `revoke_key(issuer, key_id)` API. Pending receipts
   do not survive revocation or expiry. Never erase the replay database as a
   shortcut to make another attempt eligible.
4. Reauthenticate Graph/provider and backend identities independently. Reobserve
   object IDs and backend state; regenerate and review an exact new plan. A
   credential change must not reuse old approval evidence.
5. Record the identity owner's and AppSec reviewer's findings before admitting
   a replacement execution profile.

## Interrupted or uncertain operations

Before dispatch, cancellation may safely return to review. After dispatch, a
lost response or missing durable receipt requires read-only reconciliation.
Preserve partial policy and assignment effects separately. Do not repeat a
create/apply merely because the client timed out, and do not assume restoring
state restores the remote objects.

For the admitted provider route, run the documented `provider status` and
`provider reconcile` commands with the original executor, session and authority
configuration. These commands reconstruct evidence; they do not grant a fresh
approval. If identity, lineage, serial, object ownership or service readback
cannot be established, remain blocked and require investigation. A second
ordinary saved plan and independent settings/targeting comparison must show the
intended state before declaring convergence.

Two retained workspace PTY runs exposed unexplained restart/replan behavior:
one successful exit left a session lock; another replan retained old plan
receipt bytes. Later instrumented workspace and `/tmp` runs passed, which does
not explain or close the earlier observations. See
`security/findings-final-v13.json` and `wizard/pty-navigation-v2`,
`wizard/pty-navigation-v3`, and `wizard/storage-diagnostic-01` in the epoch
evidence. Do not delete a stale lock or replace a stale receipt to force resume.
Preserve their bytes and file identities, reconstruct the operation from the
original artifacts, and keep the affected profile blocked until independent
root-cause and restart qualification close this gap.

## Concrete external gate procedure

The host maintainer reruns the exact source suite, native adoption, locking,
provider schema/import/refresh/ordinary-plan lifecycle and terminal security
qualifiers from this epoch's replay index on each proposed host. Retain failures
and skips. The AF_UNIX test must execute; removing it or using an unrelated
transport does not qualify the missing provider RPC path.

The AppSec and execution-service owners review the filesystem, egress and
descendant boundary, protected key delivery, approval issuer, replay database,
state backend integration and unresolved findings. They must independently
challenge the exact packaged revision; no LLM statement grants risk acceptance.

Before the tenant pilot, its owner supplies an approved record containing the
tenant/cloud, separate provider/backend principals, permission grants, exact
policy/group/filter IDs, storage account/container/blob, allowed actions,
approver, expiry, scale, stop conditions and incident contacts. Credentials are
not part of that record or the source archive. Use a disposable authorized scope.

The pilot must observe: authenticated complete inventory; independent semantic
preservation; immutable-ID import; refresh-only and ordinary saved plans; bound
approval; execution of that exact saved plan; service readback; second-plan
convergence; targeting/exclusion/filter equivalence; then authorized interruption,
revocation, partial-write and concurrent-change recovery scenarios. Stop on
unauthorized mutation, credential exposure, cross-tenant effects, approval bypass,
missing mandatory evidence or an unresolved high-impact path.

A future live-capable worker and integrated Azure backend remain separate gates
where absent. The current network-denied provider profile must not be changed
to an unrestricted profile to make this procedure appear executable.

## Update and incident response

Requalify affected assertions after changes to source, dependencies, providers,
tools, host, model, skill, identity, permission or backend. Check advisory records
for the exact pins; historical clean scans are not current assurance. Install an
update in a fresh reviewed directory and preserve configuration, state, private
authority data and evidence. Do not overwrite project rules or shell profiles.

For suspected compromise, stop dispatch, isolate the affected host using the
organization's authorized process, preserve evidence, revoke credentials and
approval keys, identify affected objects/state versions, and reconcile using a
known-good host. Recovery is a new reviewed operation. External disclosure or
third-party log upload requires the applicable authorization.
