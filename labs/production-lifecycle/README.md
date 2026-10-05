# Bounded provider lifecycle

`intune_iac/provider_execution.py` owns a private, generated, one-resource OpenTofu directory. Its current factory pins OpenTofu 1.13.1 and binds an explicit engine version, the Microsoft365 provider candidate, its selected Settings Catalog schema, source revision, source/admission/target hashes, the generated configuration, provider lock file, state identity and saved plan bytes. Historical modeled fixtures specify 1.10.0 explicitly; they do not select the current runtime. This admission contract does not establish 1.13.1 provider RPC compatibility. It accepts literal attributes for one existing Windows Settings Catalog policy, including the original policy ID, setting wrapper IDs and assignment target/filter IDs. This is an engineering adapter with **local state and IP networking denied**, not a live deployment adapter.

The command set is init, provider schema, validate, import, state show, refresh-only saved plan, ordinary saved plan/show, exact saved-plan apply, fresh provider refresh readback, and a second ordinary plan. No arbitrary HCL, repositories, backend configuration, providers, provisioners, external data sources, hooks, command options, CLI arguments, mirrors with fallback, proxies or inherited credentials are accepted. The installed provider path is checked against the private pinned mirror. The saved plan is copied into a bounded anonymous memfd snapshot, matched to the approved hash, write/grow/shrink sealed, and passed by descriptor for show and apply. In-place writes to the original file cannot change the dispatched snapshot. The executor, approval authority, JSON/persistence helpers, scope admission and process isolation implementation bytes are bound to the request. Owner-private work directories are rechecked before commands.

`apply` requires the exact `ApprovedExecution` / `ExecutionPermit` objects from the host approval module, including the digest of the entire request and execution mode. The authority context spans final checks, mutation and readback. The subprocess supervisor checks authority before spawn and while the process is running; failure kills its process group. The cooperating executor lock spans each operation. The authority stores dispatch and exact outcome hashes independently of editable local journals. Public reconciliation can report verified execution only when an exact prior outcome with `exact_plan_returned: true` matches that private authority record; otherwise matching state is labeled `desired_state_observed_execution_unconfirmed`. This is a trusted-host boundary: hostile code running as the same operating-system principal or a compromised pinned tool is outside the boundary.

A durable `mutation_started` marker precedes provider dispatch. The adapter never reruns a mutation after a failed response, process timeout, assignment failure or state-write uncertainty. Reconciliation only reads/plans. It distinguishes verified convergence, partial/divergent service state, service convergence with unreconciled local state, and unresolved readback. Applying a refresh plan to repair local state is not silently authorized.

## Current evidence

| Evidence | What actually ran | Current result |
| --- | --- | --- |
| `modeled_lifecycle.py` | Real Ed25519 signatures, verifier, durable replay store, typed authority and adapter state machine; modeled provider commands/service | Success, pre-write rejection, policy/assignment partial outcome, lost response and state-write failure; repeated mutation and approval replay rejected |
| `native_smoke.py` | Exact OpenTofu and full candidate binaries; offline mirror init; schema/validate attempts under IP-denied guard | Read the exact tool pins and command observations in the latest receipt. Earlier receipts inferred schema/validate blocking from a separate AF_UNIX probe; that inference alone is insufficient. Revised receipts require an actual command Unix-socket EPERM diagnostic before classifying it as blocked. |
| Python regression tests | Adversarial configurations, identity/preservation/plan tampering, output and time limits, authorization expiry, journal faults | See current `research/production-completion/provider-execution/unit-tests.txt` |
| `sealed_plan_native.py` | Exact OpenTofu local-output saved plan, original plan overwritten after snapshot, sealed FD mutation attempts and saved-plan apply | Passed: immutable approved snapshot applied; no external provider |
| Historical selected-resource fixture | Earlier pinned resource import/read/no-change native RPC, using a separate synthetic Configure | Remains historical evidence under `research/provider-qualification/completion-20261002`; no promotion to current production Configure |
| Production Configure, provider mutation RPC, live service | Not qualified in this runtime | Blocked / not run; no live tenant authorization used |

The existing `labs/provider-contract/synthetic-rpc` fixture is GET-only. It cannot establish native provider write semantics. A future native lifecycle fixture must deliberately inject a synthetic auth/service transport into a separately identified lab binary and exercise policy and assignment mutation failure boundaries; it must not loosen the production executable pin or network guard. A live deployment additionally needs a host-managed origin-bound egress broker, identity binding, backend ownership/fencing and service readback qualification.

## Reproduce

```sh
python -m unittest plugin_tests.test_provider_execution_v5 -v
python labs/production-lifecycle/modeled_lifecycle.py --receipt /absolute/path/modeled-lifecycle.json
python labs/production-lifecycle/native_smoke.py \
  --tofu /absolute/path/tofu \
  --provider /absolute/path/terraform-provider-microsoft365 \
  --work /new/private/binary-bearing-work-directory \
  --receipt /absolute/path/native-smoke.json
```

The native work directory contains the large copied binaries and private plan/state artifacts; keep it outside the source repository. Supply a fresh receipt path: the native harness creates an exclusive adjacent `.logs` directory with private raw stdout/stderr files and hashes for each command. Its lab-only observation proxies tee bytes already read by the unchanged runtime supervisor. They preserve actual argv, environment, guard, descriptors, output bounds and return/exception behavior; no runtime source is instrumented. A truncated or missing diagnostic cannot substantiate a host-prerequisite classification. The fixture supplies no credentials and dispatches only init/schema/validate. The modeled issuer key is ephemeral and separate from the replay store and never appears in receipts.

For a separate no-credential diagnostic run, add `--provider-trace` and use fresh
work and receipt paths. This explicit lab profile adds exactly
`TF_LOG_PROVIDER=TRACE` to the original child environment; all other environment
values, commands, binaries, descriptors, guards and limits remain unchanged.
The profile rejects credential variables and arbitrary logging variables rather
than accepting an environment override. Trace output remains bounded in private
raw files. It is not a production logging option and must not be applied to a
credential-bearing execution. OpenTofu 1.13 documents this provider-only setting
at https://opentofu.org/docs/v1.13/internals/debugging/; exact-tag logging source
and its hash are retained in epoch `native-smoke-observation/trace-profile`.

The epoch final default probe initialized successfully but retained generic
schema/validate startup failures with no handshake. Its separate trace probe,
using the same final provider and OpenTofu bytes, reported actual provider
`listen unix ...: socket: operation not permitted` diagnostics for both commands.
Only the trace receipt classifies those attempts as prerequisite-blocked. The
default negative results remain unchanged, and neither profile establishes
native provider RPC, full resource lifecycle or live-service acceptance.
