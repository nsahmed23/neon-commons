# Protected Unix egress broker — R4

`intune_iac.worker_broker` is the HTTPS mediation component for the separate
`worker_host` network-none container. It is a controller library, not a terminal
command or permission grant. The old network-denied execution factories are
unchanged. The integrated pinned native-provider/Azure-protocol journey passes against a
nonforwarding local TLS fixture; live activation and real Azure/Graph remain
unqualified.

The host must install and pin the policy and trusted controller. `EgressBroker`
requires a process-held `BrokerGuard`, an independently private SQLite journal,
and either the fixed public-cloud `NativeUpstream` or the separately typed
loopback-TLS `LaboratoryUpstream`. A live guard requires the existing authenticated
`LiveIdentityBinding` and a callback that checks actual signed-job authority,
expiry, cancellation, coordinator ownership and immutable bindings. A policy file,
a token claim, a caller role label or possession of the Unix socket is not approval.
The controller is trusted code; calling its Python factories in a hostile process
cannot establish a protected service boundary.

`UnixBrokerServer` admits only its declared Unix peer UID, then one exact CONNECT
to a declared host on 443, TLS interception using its pinned public CA, and one
bounded HTTP/1.1 request. It rejects arbitrary CONNECT destinations, alternate
ports, redirects, duplicate headers, conflicting framing, method overrides, unknown
behavior headers, incorrect query values and substituted bodies. The separate
native upstream always uses HTTPS443 and the system trust store, without ambient
proxy or CA fallback. The lab transport reaches only its fixed loopback TLS server.

Policy schema `protected-egress-policy/1.0` contains operation/execution-binding/expiry,
worker UID, separate tenant/client identities and a closed route array. Routes
bind exact host, method, path, query values, required headers, role, audience,
effect and attempt budget. An OAuth route also binds exact form bytes, client ID,
client-credentials grant and scope to the tenant token endpoint. Only a token
actually returned by that request may be used for its captured role and audience.
The registry is process memory; restarting requires a newly admitted OAuth call.
It never trusts an arbitrary decoded bearer token or places tokens in the journal.

Every admitted dispatch is committed before forwarding. A mutating request has
one attempt. Lost, malformed or redirected responses retain `outcome_unknown`;
restart cannot retry it. Response receipt is not service convergence. Native lease
routes require backend/storage/blob origin, PUT, empty body, exact `comp=lease`
and acquire/renew/release semantics. This prevents a Graph PUT from being relabeled
as a repeatable lease operation. Coordinator and native-state leases remain distinct.

Generated state bytes have a separate closed `NativeStateWriteContract` in
`azure_backend.py`. A `state_write` route supplies its contract digest and expected
semantic digest; the controller supplies the actual process-held contract. The
candidate must equal the state independently projected from exact baseline and
saved-plan JSON: schema4/OpenTofu1.13.1, existing root resources only, unchanged
immutable IDs/schema versions/private metadata, fully known updates, preserved
output types/sensitivity, identical lineage and serial+1. Unknown values, drift,
creates/deletes/imports/moves/indexed resources/modules are unsupported. Every field
must match; formatting may differ. The journal hashes the actual request bytes.
This content admission grants no write authority and does not prove atomic service
freshness. The native protocol extension below handles the locally observed SDK lease headers. Unknown headers still fail shut; local protocol qualification is not Azure qualification.

`native/worker-relay/relay.c` is a static, no-argument relay that binds only
127.0.0.1:18080 and connects only `/broker/egress.sock`. It has four concurrent
connections, 20-second connection deadlines, 2MiB request/18MiB response limits,
and no destination configuration. It is not the authorization boundary: the
network-none container, read-only mounts, exact tool pins and host-side broker
are mandatory. Its role is compatible with the pinned Alpine image without
installing Python or changing that image. Broker directory/socket stay private
0700/0600 under the worker's existing UID; never make them world-accessible.

Local replay:

```sh
python3 -B -m unittest plugin_tests.test_worker_broker_r4 -v
/usr/bin/gcc -static -O2 -fstack-protector-strong -D_FORTIFY_SOURCE=2 -Wall -Wextra -Werror -pthread -Wl,-z,relro,-z,now -o /new/private/output/intune-worker-relay native/worker-relay/relay.c
```

Evidence is in `work/evidence/epoch-20261007-r4/worker-broker/` and independent
lease-classification before/after evidence under the R4 `independent/` directory.
Actual TLS tests use an ephemeral synthetic CA and synthetic OAuth secrets,
assert upstream effects and durable journals, and make no Azure/Graph calls.
Real provider HTTP shapes, native backend lease lifecycle, host isolation,
organizational CA custody, protected CI identity, encrypted runtime volumes,
independent authenticated readback and live service/device outcomes are separate
gates. Private keys/tokens/raw tenant bodies must remain in restricted storage;
this broker's journal excludes OAuth bodies, tokens and tenant state bodies. Exact native lease IDs/lock metadata are additionally retained as private recovery authority-bearing data.

## Host-held credential replacement

`broker_credentials(binding=..., backend_credential=..., execution_binding_sha256=...)`
constructs a nonserializable host object using the existing identity binding and
its exact backend credential handle. `worker_environment()` returns declared IDs
and per-role placeholders only. A native-policy broker requires this object. It
checks role/tenant/client/execution binding, admits the exact placeholder OAuth
form, then replaces only `client_secret` in host memory before the fixed AAD
request. Actual client secrets never enter worker environment variables, scripts,
Docker inspect metadata, arguments, the policy or journal. Returned bearer tokens
remain sensitive worker/broker memory and must not enter native debug logs,
captures, receipts or exported state. The state projection independently rejects
unapproved added content.

The two-role client-secret strategy preserves existing provider/backend identity
separation. A reader credential is not implicitly interchangeable; this vault
currently supports provider/backend roles only. Its exported environment is not
live authentication. Actual SDK placeholder handling, default scopes and broker
transport must be observed using the pinned SDK/provider before native release.
The retained pinned MSAL source requires the exact optional scope suffix
`openid offline_access profile` and form charset suffix; these alternatives are
admitted only alongside the declared resource audience and exact form hash.

The local TLS canary test independently observes different host-side provider and
backend secrets upstream while proving their absence from worker environment,
policy, repr and SQLite bytes. That is fixture evidence, not real authentication.


The execution binding is deliberately distinct from the full signed manifest
hash: it binds the immutable operation core first, allowing placeholders and
control files to be generated without a hash cycle. The final signed service
manifest then binds this execution binding, the full broker policy hash, exact
control/source/tool/plan bytes and native state contract. The service permit
checks the full signed manifest before every request. Possessing or repeating the
execution-binding string alone has no authority.

Actual pinned Atmos/OpenTofu/provider OAuth captures now establish the two AAD
metadata GETs, exact MSAL claims/form/scope fields, and acceptance of placeholders
inside a real network-none container. The explicit `discovery` effect permits
only those tenant-specific metadata routes, without bearer authorization; token
and preferred-network destinations are checked. Identical tenant discovery routes
must be deduplicated across roles because metadata does not confer a resource
credential. Upstream responses are requested with identity encoding so bounded
body parsing cannot be bypassed with compression. Native backend workspace
listing is limited to the bound container and exact `<state-key>env:` prefix with
an empty initial marker; additional pages require a separately qualified contract.

Native credential bindings also constrain backend routes to the authenticated
storage account and state key, or that exact workspace listing, and the bound ARM
subscription/account reads. A coordination blob is not a substitute native state
key. Storage writes cannot be relabeled as ordinary Graph mutations; state PUTs
require the native state projection, and lease actions require their separate
closed contract. Server-side copy/method override headers are rejected.

Relay v3 adds a fixed exclusive0600 `/job/relay.ready` file containing `READY`
after bind/listen. A stale file fails startup; recovery preserves and investigates
it before preparing a fresh host dispatch. Original v1/v2 binaries and the failing
half-close reproduction remain preserved. The v2 source is retained verbatim;
v1 source was reconstructed from the known patch and matches its original SHA,
which is explicitly recorded rather than presented as a fresh original capture.


## Native protocol and independent prewrite checks

The `laboratory_native_protocol` profile uses real SDK hostnames but only the
fixed loopback TLS transport and laboratory identity capabilities. It cannot
forward to Azure or Graph. `azure_public_pilot` requires the fixed native
transport and live identity/reader types. These are separate capability classes.

Actual Kiota PUT/assign POST requests use HTTP/1.1 chunking. The parser admits
only the exact single `chunked` encoding with bounded decoded bytes/chunk count;
Content-Length conflicts, extensions, trailers and other encodings are denied.
The decoded body must equal the approved hash. Forwarding generates a new
Content-Length request; untrusted chunk framing never reaches the service.

A native mutation profile requires exactly the approved policy PUT and assignment
POST plus a sealed `LiveGraphPrecondition` or `LaboratoryGraphPrecondition`.
Tenant, object, execution binding, profile and both body hashes must match. The
broker serializes the complete read/dispatch/response cycle. After token, route,
lease and durable replay checks, the independent reader refreshes all three raw
collections immediately before each stage. Cancellation, authority and native
Apply-lease state are rechecked after those reads and before durable dispatch.
Graph read/write remains non-atomic; native Blob locking does not fence portal
writers. This residual race needs an explicit operating-profile risk decision.

Native lease acquisition admits one generated UUID, infinite lease duration and
the exact state blob. Terraform lock metadata admits only the pinned 1.13.1
shape, matching UUID/path/container identity and recent timestamp. Apply metadata
is required before Graph or state writes. Metadata clearing/release are separate
exact routes. Any lease/metadata failure invalidates the cached lock; any uncertain
write durably bars further writes. Policy-installed effects cannot relabel a
Graph mutation as replayable metadata/lease traffic.

`ComputedNativeStateWriteContract` in `worker_state.py` admits the actual pinned
provider's two computed fields only through the exact sealed desired completion.
The broker calls `precondition.completion()` at state PUT, records the content
admission, and exposes `graph_completion` / `state_admissions` to the protected
service's independent readback. These values do not assert service convergence
or release scope ownership on their own.

## Interrupted native leases

Before forwarding any lease/metadata operation, private SQLite records the exact
blob host/path, proposed or active lease ID and lock metadata, linked to the
normal durable dispatch outcome. `native_recovery_record()` reads these facts
without any remote action, even after reopen. IDs and metadata are sensitive
recovery inputs and must remain private/encrypted when exported.

Cancellation still denies every further request. A killed native process may
leave an infinite Azure lease. There is deliberately no automatic force-unlock,
reacquire or cleanup exception to cancellation. Preserve the signed operation,
reservation, broker journal, state/version observations and host cleanup receipt.
An authorized recovery controller must independently read the current exact blob
and metadata, compare its ETag/lineage/serial/lease context, independently read
Graph outcomes, and prepare a separately approved narrowly scoped release if the
recorded lease still matches. The live recovery authorization adapter and actual
Azure interruption/release evidence remain release gates; these local recovery
facts alone do not close that gate.

Additional replay commands:

```sh
python3 -B -m unittest plugin_tests.test_worker_broker_precondition_r4 plugin_tests.test_worker_state_r4 -v
```

## Native CONNECT envelope repair

The first composed signed native attempt reached no broker request: OpenTofu's
Go HTTP client adds `User-Agent: Go-http-client/1.1` to CONNECT, while the earlier
envelope admitted only Host/Proxy-Connection. A separate pinned network-none
host probe captured five identical native119-byte CONNECT requests against a
Unix logger that denied all connections and never forwarded. Source and host
cleanup receipts are in `worker-broker/native-connect-before-01`.

`connect-contract-before-01` preserves a focused Unix handshake failing with403.
The repaired envelope admits only that exact optional User-Agent metadata value;
it grants no route/credential/approval authority. Proxy authorization, framing,
method overrides, foreign metadata and unapproved destinations remain denied.
`connect-contract-after-01` records31/31 actual Unix/TLS broker checks at exact
source SHA1d38819c9e4004dfb743a9163ba62d4858462433a686aa5473c09629c45ce6cc.
This run overlaps the earlier46-case combined scope; counts must not be added.
The fresh signed composed native attempt03 reused the same prepared plan and
passed after this repair. It is still local protocol qualification, not real Azure.


## Connected signed native journey

`worker-provider/native-service-journey-03/receipt.json` (SHA256
`e10ed6da4841e210b6d8736f34e4c8c4ce084a43a7d03dcfbb8c5aeb9ae614af`)
records the actual pinned network-none Atmos/OpenTofu/provider through the signed
service, Unix relay, this broker and stateful nonforwarding Graph/Azure TLS
fixture. Thirty-three broker requests include exact policy PUT/assign POST,
independent fresh stage checks, computed state PUT201, metadata clear and native
lease release. Sealed independent Graph/Blob readback reconciles convergence and
releases scope ownership; a separate actual native plan reports no change and
preserves state bytes. Seventeen independent assertions include exact plan,
immutable object/settings/assignments/tags, lineage and single serial advance.
Boolean approval and replay are denied. Unsupported management mapping remains
visible; endpoint effectiveness, real receiving services and organizational
approval remain unestablished. Failed attempts01/02 and their no-effect proofs
remain preserved. The assertions overlap earlier native and focused scopes;
request counts are not test totals.
