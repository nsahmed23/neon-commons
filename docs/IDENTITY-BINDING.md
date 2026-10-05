# Explicit identity and service binding

`intune_iac.identity_binding` supplies a host-only constructor for an authenticated observation of provider identity and backend identity/state. It does not authorize an Intune update, approve an operation, acquire writer ownership, or execute a provider. The older `target-evidence/1.0` supplied-consistency schema is unchanged; its authentication-method restrictions are not relaxed or silently translated.

The initial supported contract is public Azure, application `client_secret` authentication, standard Azure Blob endpoints, and one existing OpenTofu state blob. Certificate, workload federation, managed identity, user/device authentication, national clouds, Azure DNS zone storage endpoints, and empty/new state initialization remain unsupported. They require separate reviewed implementations; there is no fallback authentication chain.

## Host API

The protected host constructs immutable `IdentitySpec(tenant_id, client_id, principal_object_id, auth_method='client_secret')` values for the provider and backend. `BackendSpec` requires the subscription, full storage resource ID, exact blob origin, container, key, workspace, expected lineage, serial, and SHA-256 of the exact state bytes. `BindingConfig(provider, backend_identity, backend, cloud='public')` combines these explicit host expectations.

The host separately injects two `ClientSecretHandle` objects, then calls:

```python
bound = bind_live(
    host_config,
    provider_credential=provider_handle,
    backend_credential=backend_handle,
    timeout=10,
    total_timeout=60,
    max_age=60,
)
```

`bind_live` accepts no transport, arbitrary URL, alternate authority, token, environment selector, or clock override. Its return type is exactly `LiveIdentityBinding`. A failed read returns no partial capability. Credentials must come from trusted host code and its protected secret provisioning; do not place secrets in prompts, command arguments, configuration artifacts, logs, plan JSON, or evidence. The module never discovers credentials in the environment. The two roles are explicit and independently authenticated even if the host intentionally chooses the same application for both.

`bind_laboratory` additionally accepts `transport` and `clock` for deterministic recordings. It returns exactly `LaboratoryIdentityBinding`, branded `laboratory_recorded_responses`. `require_live_binding` rejects that object, subclasses, and all JSON. Neither credentials nor contexts support pickle serialization. These distinctions protect the host API boundary, not a Python process that can monkeypatch module internals.

## Fixed service exchanges

Every token request is an HTTPS form POST to `login.microsoftonline.com/{explicit-tenant-guid}/oauth2/v2.0/token` containing only the explicit client ID, that role's secret, one fixed scope, and `grant_type=client_credentials`. No `common` or `organizations` authority is accepted. The credentials are used only at this origin.

| Role and purpose | Scope / request | Required service facts |
| --- | --- | --- |
| Provider identity | `https://graph.microsoft.com/.default`; Graph v1.0 `servicePrincipals(appId='{client-id}')?$select=id,appId,accountEnabled` | Exact configured client and principal object IDs; Boolean `accountEnabled=true` |
| Backend identity | Separate backend Graph token and the same self-read form | Backend client and principal object IDs; enabled account |
| Backend subscription | `https://management.azure.com/.default`; subscription GET, API `2022-12-01` | Exact subscription ID, backend tenant ID, and `Enabled` state |
| Backend storage resource | Same backend ARM token; exact resource GET, API `2023-05-01` | Exact resource ID and primary blob endpoint |
| Existing state blob | `https://storage.azure.com/.default`; HEAD, conditional GET, conditional HEAD | Same ETag, length, BlockBlob type; exact state v4 lineage, integer serial, and byte SHA-256 |

The identity conclusion combines the configured tenant-specific OAuth exchange with Graph's matching service-principal response. It does not come from caller-supplied token claims. Graph and other Microsoft access tokens remain opaque; only token-response `expires_in` is used for lifetime. Microsoft documents both this opaque-token requirement and the service principal's ability to read its own details without any application permissions. Consequently, this module does not request `Application.Read.All` or organization-wide reads merely to establish identity.

Resource and blob addresses are derived from validated fixed components. Redirects, non-HTTPS origins, alternate storage origins, proxies, cookies, retries, and service pagination are not followed. The state GET and second HEAD send the first HEAD's `If-Match` value. Any 412, changed ETag/length, incomplete response, malformed JSON, wrong lineage/serial/hash, or missing blob fails closed. Nondefault workspaces resolve as `key + 'env:' + workspace`, with the colon percent-encoded in the request path.

## Freshness and process use

`bound.evidence()` exposes fixed authentication descriptions, cloud, SHA-256 bindings and observation hashes. It contains no raw identifiers, secrets, access tokens, state contents, or credential handles. `execution_authorized` is always false. The binding digest includes the immutable configuration and all observed facts, including the state ETag.

`bound.assert_fresh(expected_binding_sha256=None)` checks the original process, handle validity, token expiry, observation age, and optional expected digest. It is a local freshness check, not a fresh query. `bound.recheck()` reacquires all four tokens and repeats every service read. It accepts only the original observed binding, renews its age/expiry, and permanently invalidates the context on failure. A new ETag requires a new context even if state bytes are unchanged. Revocation is detected when the identity authority or receiving service rejects the credential; this cannot promise instantaneous cloud-wide revocation propagation.

`bound.provider_environment()` returns exactly these four in-memory keys from the same provider handle used in the observed exchange:

```text
M365_TENANT_ID
M365_CLIENT_ID
M365_CLIENT_SECRET
M365_AUTH_METHOD=client_secret
```

The protected runner must use these only with its pinned provider and explicit sanitized subprocess environment, without merging ambient M365/Azure authentication variables or provider configuration overrides. Do not persist or log the returned mapping. Identity binding does not itself pin a provider executable or validate HCL; those are separate runner gates. Closing either credential handle immediately blocks context use. Python cannot guarantee erasure of string copies, so process and child-environment secrecy are host responsibilities.

Trusted backend adapters may call `backend_configuration(credential)` to obtain the immutable backend identity and target, and `backend_storage_token(credential, timeout=...)` to acquire only the storage audience. Both require the exact backend handle object used to mint the context. The latter returns a redacted, nonserializable `BackendStorageToken`; its host-only `_get()` rechecks context, handle, and token lifetime. Fractional positive timeouts up to 30 seconds let an adapter include OAuth within its own deadline. No arbitrary scope or endpoint is accepted. Laboratory contexts retain their laboratory transport and type; a live lease factory must separately require an exact `LiveIdentityBinding`.

These accessors do not integrate OpenTofu's Azure backend lock. An independently held lease on the state blob would conflict with OpenTofu trying to acquire its own lease. A separate lease component fences its Azure blob only; the current provider executor uses local state and denies IP networking. A lease fixture cannot promote that executor to live operation.

## Bounds and remaining gates

Each request has a caller-visible deadline including DNS, TLS, headers, and body; the full observation has a separate deadline. Defaults are 10 seconds/request and 60 seconds/observation, with maxima of 30 and 120 seconds. JSON bodies are limited to 1 MiB, state to 16 MiB, and headers to 100 entries/64 KiB. The native worker never proceeds from a cancelled connect to send credentials. An OS resolver can outlive cancellation; at most four daemon workers may exist. The host's OS CA store is trusted; `SSL_CERT_FILE` and `SSL_CERT_DIR` do not select an alternate store.

Caller interruption closes active connections, and automatic HTTP reconnection is disabled after explicit connect. A separately retained socket lets cancellation interrupt a response body even when `Connection: close` has detached it from the connection object. The worker closes the response stream before releasing its bounded worker slot. Cancellation cannot undo bytes already sent before it was observed.

401 and token-endpoint 400 mean authentication failure; 403 means permission denial. Read access establishes only these successful reads. It does not establish Intune mutation permissions or backend write/lease rights. A real execution must also bind the plan and provider artifacts, obtain independent approval, acquire native backend locking and writer ownership, perform an immediate service recheck, and verify post-operation behavior. A state can change after the final read, so a read-only ETag observation is not a lock.

The local test evidence is synthetic recorded responses plus an in-memory native-connection double. No real token exchange, tenant, Graph request, ARM request, or blob was contacted. External qualification remains necessary in a protected host with explicitly provisioned credentials. The current runner denies network socket creation; no escalation or bypass was used.

See `research/production-completion/identity/sources.md` for the primary-source basis and `verification.json` for test provenance.
