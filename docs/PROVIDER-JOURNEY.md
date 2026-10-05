# Provider preparation, approval and recovery

The provider journey exposes a fixed CLI over `intune_iac.provider_execution` and `intune_iac.approval_authority`. It opens an executor that the protected host has already generated and pinned. It does not accept arbitrary HCL, repositories, provider binaries, commands, backend options or signing keys, and it does not create an executor or sign an approval receipt. The host provisions the executor and the independent approver supplies a receipt for the resulting operation.

Only `laboratory` and `native_provider_network_denied` modes are admitted. Both keep the provider's IP network access denied. Laboratory success establishes the fixture's behavior; native mode uses the pinned provider candidate within the same network restriction. Neither mode qualifies a live Intune lifecycle, authenticates an execution target, or proves that generated configuration was correctly admitted from a capture. Public operation evidence retains `execution_authorized: false`, and lifecycle results retain `production_qualified: false`.

The current provider adapter binds exact OpenTofu 1.13.1 bytes and an explicit
`engine_version` in its toolchain manifest. Generated configuration, plan/show
headers, nested prior-state headers, review and reconstructed convergence must
match that binding. OpenTofu 1.10.0 remains available only through explicit
laboratory fixture pins. A missing, unknown or inconsistent version is rejected;
there is no implicit downgrade. Changing a pin requires a new executor and
review, not relabelling an existing saved plan or approval.

This admission change does not establish OpenTofu 1.13.1 provider RPC or full
resource-lifecycle compatibility. Those assertions require the exact rebuilt
provider, actual native RPC and a supported host. Existing in-process provider
resource tests, modeled adapter tests and resource-free native OpenTofu tests
remain separate evidence. The generic resource-plan parser is not widened by
the provider-specific version contract.

The provider journey and signed-approval runtime currently support Linux x86_64 only. `doctor` and the CLI report an explicit platform limitation elsewhere. Existing portable offline review commands remain separate. The inherited-descriptor identity command requires a Unix host. A supported platform does not itself establish native-provider or live-service qualification.

## Operator policy

`--authority-config` names a strict private JSON file controlled by the operator, outside both the reviewed repository and the executor tree. The policy selects the persistent authority store, pins the verifier and public-key validator, defines trusted approvers, and allowlists the exact executor root, manifest digest and mode. Requests, plans, receipts and sessions cannot supply or replace these trust roots.

The policy has this shape; the bracketed values are placeholders, not usable pins or a provisioned authority:

```json
{
  "schema_version": "provider-operator-policy/1.0",
  "authority_root": "/absolute/private/provider-authority",
  "verifier": {
    "executable": "/absolute/pinned/openssl",
    "sha256": "<sha256>",
    "validator_library": "/absolute/pinned/libsodium.so",
    "validator_sha256": "<sha256>"
  },
  "approvers": [
    {
      "issuer": "operator-approval-service",
      "key_id": "provider-key-1",
      "approver_id": "provider-reviewer",
      "public_key_hex": "<ed25519-public-key-hex>",
      "permitted_modes": ["laboratory"],
      "permitted_actions": ["provider_update", "provider_no_change"]
    }
  ],
  "executors": [
    {
      "root": "/absolute/private/preprovisioned-executor",
      "manifest_sha256": "<manifest-digest>",
      "mode": "laboratory"
    }
  ]
}
```

All fields are explicit. Unknown fields and unsupported values fail closed. Policy, receipt and session files must be regular, private operator-owned files (0600); policy/session parent directories and the executor root must be private (0700). Session files must be outside the executor and authority trees. Add `native_provider_network_denied` to an approver's permitted modes only when the operator intentionally authorizes that mode, and provision a matching executor entry. A file inside an imported project is not an operator policy merely because it has this schema. Keep issuer private keys in the approver's separate security domain. Retain the authority store across sessions and releases: it holds consumed-operation/nonce, revoked-key, dispatch and outcome records; deleting it defeats the durable history.

## Fixed commands

Every provider command requires `--executor-root`, `--session`, and `--authority-config`. Use absolute paths. The same values identify the same journey on later invocations.

```bash
python scripts/intune-iac.py provider prepare \
  --executor-root /absolute/private/preprovisioned-executor \
  --session /absolute/private/provider-session.json \
  --authority-config /absolute/private/operator-policy.json

python scripts/intune-iac.py provider review \
  --executor-root /absolute/private/preprovisioned-executor \
  --session /absolute/private/provider-session.json \
  --authority-config /absolute/private/operator-policy.json
```

| Command | Effect |
| --- | --- |
| `provider prepare` | Runs the closed executor preparation sequence: pinned initialization/schema validation, import into its local state, preservation checks, refresh-only review, and an ordinary saved plan. Creates the operation to review. |
| `provider review` | Revalidates the prepared operation and presents its action, mode and bindings for independent approval. It grants no execution capability. |
| `provider execute --receipt /absolute/approval.json` | Verifies the externally signed receipt against the operator policy and exact operation, obtains a process-local authorization, and attempts the saved plan once. |
| `provider reconcile` | Reobserves the provider through refresh-only readback and a second ordinary plan. It never imports, applies or retries the write. |
| `provider status` | Reports persisted journey/operation evidence and recovery state. A displayed approval or completion label supplies no authority. |
| `provider wizard` | Runs the same preparation, review, approval, execution and recovery flow interactively. |

Preparation creates local executor state and saved plans; it is not an emit-only preview. It does not apply the desired update. Only the closed generated executor slice is supported, with one selected Settings Catalog resource and local state. The preparation binds the saved binary plan, rederived plan JSON, source/admission/target digests, object scope, configuration, toolchain, implementation files, provider schema and lock, executor manifest, and pre-state bytes/lineage/serial. A supplied digest records a binding; it does not independently establish the correctness of capture-to-configuration admission. Changed implementation bytes require a newly provisioned executor and review.

Send the exact reviewed operation to the separately operated approver. Its `signed-operation-approval/1.0` receipt binds the operation ID and complete request digest, issuer/key/approver identity, issuance and expiry times, and a one-use nonce. The detached Ed25519 signature is checked through the operator-pinned verifier; the CLI offers no receipt-signing command.

```bash
python scripts/intune-iac.py provider execute \
  --executor-root /absolute/private/preprovisioned-executor \
  --session /absolute/private/provider-session.json \
  --authority-config /absolute/private/operator-policy.json \
  --receipt /absolute/private/signed-approval.json
```

The authorization is specific to the reviewed request and permitted mode/action. It is consumed durably before dispatch. Expiry, key revocation, changed artifacts/state, a busy scope, a reused nonce or a previously attempted operation blocks execution. A changed receipt directory or a restarted process cannot make a consumed approval reusable. Host code, its pinned cryptographic runtime, the operating system and the operator-controlled authority store remain trusted boundaries.

## Wizard and interruption

Start the interactive journey with the same three path arguments:

```bash
python scripts/intune-iac.py provider wizard \
  --executor-root /absolute/private/preprovisioned-executor \
  --session /absolute/private/provider-session.json \
  --authority-config /absolute/private/operator-policy.json
```

The wizard accepts `prepare`, `review`, `approve`, `execute`, `status`, `back`, `edit`, `cancel`, `save`, `resume`, and `reconcile`. Enter bare `approve`, then supply the external receipt path at the separate `Receipt file:` prompt. Typing `approve` is not a substitute for a signature. `execute` uses only the authorization verified in that running process.

The verified authorization remains in memory. Save/suspension, EOF, Ctrl-C, cancellation, moving back, editing and process exit discard it. `save` and `cancel` exit the wizard. Resume reconstructs persisted evidence and requires a fresh approval verification before execution. The session stores binding hashes, with no authoritative phase or approval field; it cannot reconstruct the capability. `back` and `edit` clear the in-memory grant and direct configuration changes to a fresh host-admitted executor root. They do not rewrite the pinned configuration. Back and resume do not undo provider effects, erase the durable consumption record or clear an uncertain attempt.

Execution records its mutation boundary before dispatch. Interruption or failure after that boundary can leave the outcome unknown even when no completed result exists. Use `status` and `reconcile`; never infer that an absent success receipt means the update did not happen. Reconciliation can report verified readback, divergent/partial values, converged service values with unreconciled local state, or unresolved readback. Every result keeps `retry_authorized: false`. Any further change requires separate investigation and a newly reviewed operation; the journey never automatically replays a write.

Restart validates a journal against the separate authority store's exact consumed request. A verified result additionally requires the privately recorded execution outcome confirming that the exact saved plan returned, plus current state and saved readback/second-plan checks. A matching state, no-change plan or spent approval alone does not prove that the saved plan ran. Without that execution outcome, convergence is reported as `desired_state_observed_execution_unconfirmed`, with a nonzero CLI exit status. Incomplete dispatch markers reconstruct as `outcome_unknown`; writable journal flags cannot manufacture completion.

## Explicit target authentication

`target authenticate` is a separate read-only identity observation, using the explicit provider/backend identity and existing state configuration described in [IDENTITY-BINDING.md](IDENTITY-BINDING.md):

```text
python scripts/intune-iac.py target authenticate \
  --input /absolute/private/identity-config.json \
  --provider-secret-fd 3 \
  --backend-secret-fd 4
```

The input is the exact `dataclasses.asdict(BindingConfig)` structure, with no credential fields:

| Object | Required fields |
| --- | --- |
| Top level | `provider`, `backend_identity`, `backend`, `cloud` |
| `provider` and `backend_identity` | `tenant_id`, `client_id`, `principal_object_id`, `auth_method` |
| `backend` | `subscription_id`, `storage_account_resource_id`, `blob_endpoint`, `container`, `key`, `workspace`, `state_lineage`, `state_serial`, `state_sha256` |

Use `cloud: "public"` and `auth_method: "client_secret"`. The identity and backend fields must satisfy the strict host contract in [IDENTITY-BINDING.md](IDENTITY-BINDING.md); there is no endpoint, identity or state discovery fallback.

The protected launcher must open and supply distinct read-only descriptors numbered at least 3. Each must be a private regular file or pipe containing at most 4,096 raw printable ASCII bytes, a restricted UTF-8 representation of the client secret. Reads require EOF within five seconds; path-only descriptors and sockets are rejected. The command does not strip newlines; newline-terminated input is rejected. Descriptor contents are not a path, JSON document, token or environment-variable name. Do not put secrets in prompts, model-visible arguments, input JSON, shell history or logs. There is no ambient credential discovery or model-supplied-secret fallback, and the provider and backend credentials are read independently.

The command performs the fixed tenant-specific OAuth and service observations, emits redacted evidence, closes its credential handles, and exits. That output cannot recreate a `LiveIdentityBinding` in another process or authorize `provider execute`. The handle's lifetime ends with this command. It does not transfer credentials into the provider journey, enable network access, acquire a backend writer lease, establish Intune write permission or connect the provider's local state to the observed Azure blob.

## Evidence limits

The CLI and wizard connect existing bounded components and preserve their failure/recovery boundaries. Their local tests can qualify command dispatch, strict policy loading, receipt verification, process-local approval, interruption, replay denial and evidence reconstruction. They do not demonstrate a real tenant import/update/readback, native cloud backend locking, complete generation admission, or production convergence. Those claims require separately retained evidence from the protected host and actual services. Laboratory fixtures, successful signatures and status labels cannot close those gates.
