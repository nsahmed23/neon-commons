# Signed approval and execution boundary

The host owns `ApprovalAuthority`, its private directory, the replay database,
trusted public keys and verifier pins. Those inputs are installation policy, not
fields imported from an Intune policy, Atmos repository, model response, or plan.
The signing private key belongs to an independent operator/approval service and
is never loaded by the executor. Local fixture keys only qualify mechanisms.

The signed payload is canonical JSON prefixed by the domain bytes
`intune-iac:operation-approval:v1` and a NUL. It binds the entire prepared request
hash, operation UUID, issuer, key, approver, issue/expiry times and random nonce.
The request binds saved plan, displayed plan, configuration, source/admission,
target, scope, state lineage/serial, toolchain, provider schema and lock file.
Signing the display alone is insufficient. Approvers must review the exact
request and independently rendered plan; this implementation does not provide
organizational identity verification or approval delivery infrastructure.

Verification grants no mutation until the context is entered. Entry takes a
cooperative scope lock, rechecks bound host policy, and commits one-time
consumption using SQLite FULL synchronization before returning an in-process
permit. Operation IDs and issuer/nonces cannot be reused across restarts in the
same retained authority store. Scope exit never refunds a consumed approval.
The permit records dispatch and the exact outcome hash in that private store.
Approval consumption alone does not prove dispatch. A writable operation journal
or converged state cannot substitute for the private outcome record; read-only
recovery without it retains unconfirmed execution provenance.
The provider adapter verifies permit type, request hash and mode, checks again
before spawning, and polls liveness while the child is running. Expiry and key
revocation are checked on both sides of a potentially slow guard callback.

Only `laboratory` and `native_provider_network_denied` are admitted. There is no
JSON field or CLI flag that converts these into live tenant authorization.
`make_laboratory_guard` is a trusted host API. Its callback must return None only
on success and raise on failure; it cannot be supplied through an MCP JSON call.
The adapter, not that callback's name, implements the IP-network denial.

## Qualified cryptographic dependencies

The current Linux x86-64 fixture uses OpenSSL 3.0.13:

- Executable `/usr/bin/openssl` SHA-256
  `204951390b4f82d39f98b0dd0fa54502f27256c8d2fd08b55a5e3781408ae83b`.
- Key validation uses libsodium 1.0.18, exact library
  `/usr/lib/x86_64-linux-gnu/libsodium.so.23.3.0`, SHA-256
  `fe00408090ea084504d7cb0130af56a22554fe299034b864551b65a64ca8a7b5`.
- Both are explicit host dependencies. OpenSSL dynamic libraries and OS trust
  remain trusted host components; hashing one executable does not authenticate
  every loaded component or establish supply-chain provenance.

Independent tests reproduced static signatures accepted by OpenSSL under weak
configured Ed25519 public keys. The trust loader now rejects invalid, weak and
mixed-order points using libsodium's canonical point check and its documented
L-1 multiplication/addition workaround. The latter is necessary because the
maintainer documents incomplete subgroup checking in versions through 1.0.20.
Python implements no curve arithmetic or signature algorithm. A replacement
verifier/library needs explicit pins and qualification; do not loosen hashes
just to run on another host.

The native key validator is loaded from a bounded private copy under a unique
temporary directory and cached by content hash. Reusing a `/proc/self/fd/N`
pathname for `dlopen` was independently shown to return an old cached library
despite a different newly hashed descriptor; that loader defect is repaired.

Primary references inspected 2026-10-04:

- https://docs.openssl.org/3.0/man1/openssl-pkeyutl/
- https://doc.libsodium.org/advanced/point-arithmetic
- https://00f.net/2025/12/30/libsodium-vulnerability/

## Persistence, recovery and limitations

Keep the authority directory owned by the execution account and mode 0700, with
regular, single-link private files. Symlinked stores are rejected. Preserve the
database during upgrades and recovery. A copied, rolled-back or deleted database
is not an independent replay authority. Never reset it to retry an operation.
The store stops at 100,000 consumed records; archival requires an operator design
that preserves replay protection, not automatic deletion.

`revoke_key(issuer, key_id)` persists revocation and invalidates active permits at
their next poll. Credential revocation is a distinct identity/service operation.
Failed journal/state/receipt writes after remote dispatch require readback and
reconciliation; approval failure cannot establish that a dispatched mutation did
not happen. A consumed grant with no successful operation receipt is unresolved,
not permission to replay.

Scope locks coordinate processes sharing the same authority store and scope
derivation. They do not fence another administrator, another authority store or
Graph itself. An Azure Blob lease likewise does not fence all Graph mutations.
The controls cannot survive compromise of the privileged interpreter, execution
account, issuer, trusted libraries, credential store or runner. No real approval
service, enterprise approver or live tenant action was used by these tests.

Replay:

```sh
python -m unittest plugin_tests.test_approval_authority_v5 plugin_tests.test_approval_independent_v5
```

See `research/production-completion/approval/` for original failures, variants,
independent challenge and final results. Framework mappings or test counts do
not substitute for AppSec review of the installed execution boundary.
