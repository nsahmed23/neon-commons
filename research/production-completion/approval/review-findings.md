# Independent approval review, 2026-10-04

Scope: current `intune_iac/approval_authority.py`, its 15 supplied tests, and its
reachable use in `ProviderExecutor.apply()` / the provider process launcher. This
reviewer did not implement those files and only added the independent test module
and `review-*` evidence. Every signing key, database, execution target and marker
used here is a disposable local fixture. No tenant credentials, paid service,
production mutation, or performance benchmark was used.

The findings below concern the root agent's **newly implemented approval module
and integration in this engineering pass**. They are not presented as inherited
bugs in the previously delivered source. The root agent repaired its own module
after this independent review; this reviewer retained the tests and original RED
evidence separately.

## Confirmed findings before repair

1. **Expiry is checked before, but not after, the host guard callback.** A callback
   representing a slow freshness check can return after `expires_at` while
   `ApprovedExecution.__enter__()` and `ExecutionPermit.check_active()` still
   succeed. Two deterministic tests advance the clock from inside the callback;
   both failed their expected-rejection assertion. The provider repeats active
   checks, but repeating the same ordering does not close this check-to-use gap.
   Current impact is the permitted local/network-denied scope; this must be fixed
   before relying on the primitive for a privileged live dispatcher.

2. **The provider launcher starts the child before its first active-authority
   check.** The real `_supervise()` spawned a local Python child that created a
   harmless marker even though the supplied authority checker denied on every
   invocation. The test waits briefly inside that first denial solely to make the
   already-started child observable. It does not mock Popen or disable the network
   guard. Calling the check immediately before launch is necessary; ongoing checks
   still cannot atomically revoke an already-dispatched remote side effect.

3. **A weak installed Ed25519 public key permits a signature forgery.** The
   constructor accepted the compressed identity point (`01` followed by 31 zero
   bytes) as an issuer key. The installed OpenSSL verifier then accepted the static
   64-byte signature `R=identity, S=0` for the approval message, without possession
   of a private key. An all-zero public key/signature also succeeded in a separate
   exploratory case; the retained regression uses the deterministic identity case.
   This requires installing an invalid weak trust key: it is **not** a demonstrated
   forgery against a correctly generated trusted Ed25519 key. Trust-policy
   admission must reject invalid/weak keys rather than relying on hexadecimal
   length and verifier exit status alone.

The local failure logs are `review-independent-red.log` (three failing assertions:
two expiry variants and prelaunch ordering) and `review-weak-key-red.log` (identity
key forgery). The severity is medium for the current narrowly confined local
capability, and these are blockers before expanding to privileged live dispatch.
The weak-key condition would break the approval boundary if such a key were
installed; properly generated keys were not shown vulnerable.

## Independently exercised protections

The original 15 tests passed in `review-original-tests.log`. New passing checks
used a genuinely different generated private key, the wrong signature domain,
noncanonical signature scalar, changed full-request fields, two independent OS
processes racing one receipt, an fsync failure after database commit, and database
symlink/hardlink substitution. The durability fault blocked context entry while
leaving the committed receipt spent. Exactly one racing process entered.

`review-modeled-integration.log` additionally connects the real signature,
authority, replay store and permit classes to the actual provider orchestration
with its existing **modeled provider fixture**. It completed one modeled apply and
retained `production_qualified:false`. That is an integration test, not native
provider/service acceptance or a new real-provider measurement.

## Trust and coverage limits

- Only the host Python API was found to construct this authority. Imported JSON
  does not acquire a key, typed guard or permit. The test suite's module replacement
  for modeled authority is confined to tests and is not a product entry point.
- The callback is trusted executable host policy. Initially both a no-op and a
  false-returning callback completed normally. The final repair requires a `None`
  success result and rejects predicate values such as `False` or `True`; callbacks
  can also raise to deny. A no-op still satisfies that return contract. The factory
  itself does not authenticate a tenant, derive target identity, or independently
  inspect plan/state. Those duties must be implemented by an actual host adapter.
  Treating callback availability alone as evidence those duties ran would be wrong.
- Scope locks coordinate cooperating processes using the **same authority store**
  and scope digest. The store has no distributed lease, remote fencing token,
  shared-runner audience, or protection against copying/resetting the replay store.
  One root/store and retention policy must be part of the host deployment contract.
  A caller-selected scope hash must be independently checked against actual target
  identity by the host; a valid signature only binds the asserted request bytes.
- `_SEAL`, private-looking attributes and exact Python types are API guardrails,
  not isolation from arbitrary Python execution. A compromised interpreter,
  trusted verifier/library, same-user store writer, or malicious administrator can
  cross this boundary. No test here claims protection against those actors.
- The new multi-process race and injected fsync fault are finite local tests, not
  proof of all power-loss, filesystem, host-clock, distributed concurrency, or
  revocation races. External approval issuance and real organizational approver
  identity were not tested; fixture keys are not organizational trust evidence.

Implementation repair is owned by the root agent. These initial RED logs remain
historical evidence even after subsequent GREEN reruns.

## Review of the first repairs

The initial expiry, prelaunch and identity-key regressions all passed after root
repairs (`review-independent-green-first.log`, 12 tests). The key repair introduces
an additional native trust dependency: a pinned libsodium point validator, while
signature verification still uses the pinned OpenSSL executable. The tested local
stack was Python 3.12.14 / OpenSSL 3.0.13, with libsodium at
`/usr/lib/x86_64-linux-gnu/libsodium.so.23.3.0` pinned to
`fe00408090ea084504d7cb0130af56a22554fe299034b864551b65a64ca8a7b5`.
This is a Linux-specific qualification, not a portable or dependency-free claim.

The official [libsodium point-arithmetic documentation](https://doc.libsodium.org/advanced/point-arithmetic)
warns that versions through 1.0.20 can admit some mixed-order points and specifies
an additional subgroup check. The repair applies that published check. Independent
tests rejected the zero, identity and order-two points, a noncanonical identity
encoding, and a mixed-order point constructed by adding the order-two point to a
legitimate generated key. The legitimate key still passed. Wrong library hashes
also failed closed.

Two follow-up problems were reproduced in `review-validator-red.log`:

- Reusing `/proc/self/fd/N` for `ctypes.CDLL` after closing the previous descriptor
  can return the dynamic loader's cached *previous* library. After priming that
  pathname with libsodium, an authority configured with a correct hash of libc
  incorrectly succeeded even though libc has no validator API. The public
  constructor regression demonstrates an image/pin mismatch across validator
  changes in one process. It does not forge a valid-key signature or assume the
  attacker controls a trusted library. Loaded-library descriptor identity must
  remain stable for its lifetime, or an equivalent loader isolation mechanism is
  needed.
- A missing validator file raised raw `FileNotFoundError` instead of the fixed
  `AppError` failure contract. It **did fail closed**; this is a diagnostic/API
  consistency defect, not an authorization bypass.

These findings were sent to the implementation owner immediately. No additional
production or performance claim follows from adding the native validator.

## Final repair verification

The root agent changed the loader to use a fresh private copy of the verified
library bytes under a unique pathname and a bounded cache keyed by verified
content. The source bytes are checked on every use, the admitted library size is
at most 16 MiB, and the cache admits at most eight images. Missing dependencies now
produce the fixed AppError contract. The descriptor-reuse and missing-library
regressions passed afterward. These controls do not authenticate transitive native
dependencies or protect a compromised host process.

`review-independent-final.log` is the final independent-suite record. All retained
confirmed defects are repaired within the tested local scope. An additional guard
contract test checks `False`, `True`, and string predicate rejection and then
accepts a `None` checker without consuming the receipt on the earlier failures.
No production qualification, organizational signature identity, native service
readback, Windows behavior, or distributed fencing is established by this result.
