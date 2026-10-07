# Native worker host boundary (R4)

`intune_iac.worker_host` admits an exact reviewed payload to a real nonroot Linux/amd64 Docker container. It is a host adapter, not an approval authority. `launch()` always reports `execution_authorized: false` and `production_qualified: false`; a separately reviewed service controller must establish operation authority, identity, ownership and service preconditions before invoking it.

The qualified profile is Docker client/server 28.4.0, client SHA-256 `27f239f97492c434e091a70b41b8796c698f0aa2b6052c6f9c28da4ee7ae888b`, Alpine digest `sha256:3e9b4b680bfc9fb5269227cffbd6d42be39fbf7c0b908123913864aa4447e764` and image ID `sha256:c83674e1999044d33d751661371b873539f47e5b5c5ca3320c7e0377acca6238`. It uses the already available image with `--pull=never`. No package installation, daemon configuration, privilege expansion or system service activation occurs.

## Application API

```python
from intune_iac.worker_host import HostSpec, PinnedTool, directory_binding, launch, recover

spec = HostSpec(
    docker_path='/usr/local/bin/docker',
    source_root='/private/prepared/source',
    source_sha256=directory_binding('/private/prepared/source')['sha256'],
    control_root='/private/prepared/control',
    control_sha256=directory_binding('/private/prepared/control')['sha256'],
    job_root='/private/empty/job',
    tools=(PinnedTool('tofu', '/operator/pinned/tofu', '<approved-sha256>'),),
)
receipt = launch(spec, '/private/fresh-evidence')
# After interrupted controller recovery: only stop/remove the recorded container.
recovery = recover('/private/fresh-evidence')
```

Directories are distinct; the job and evidence roots are owner-private. Source and control contents, modes and every admitted tool digest are checked before execution and after normal completion. Tool roles are closed to `tofu`, `provider`, `atmos`, and `relay`. The sole entrypoint is `/bin/sh /control/worker.sh`, reviewed and pinned as part of the control directory. No arbitrary host command, Docker argument or ambient environment map is accepted.

The fixed container runs as the calling nonroot UID/GID (qualified as 1000:1000), with a read-only root filesystem, read-only source/control/tools, a private read-write job, no Internet interface, all capabilities dropped, `no-new-privileges`, private IPC and cgroup namespace, no Docker socket/device/host PID namespace, and bounded tmpfs. Resource settings are one CPU, 1 GiB memory with no additional swap, 128 PIDs, 256 descriptors, no core dump and 256 MiB maximum individual file size. Wall time is 1–300 seconds; combined stdout/stderr is 1 KiB–16 MiB. Docker daemon logging is disabled so those output limits are not bypassed by an unbounded daemon log. Private captured output is retained as raw bytes and is not copied into terminal text.

The adapter verifies actual Docker inspect fields before running the payload and after normal completion. Journals precede container creation; labels bind a unique operation and the exact host manifest. Cancellation, timeout and output exhaustion trigger bounded descendant cleanup, container stop, removal and a final missing-container inspection. Recovery checks the saved manifest and labels before stopping/removing that exact container. It never repeats the payload. Primary failure and cleanup failure remain separate; failed cleanup reports `cleanup_unconfirmed`.

## Broker boundary

Optional service transport mounts a private directory containing only `egress.sock` read-only at `/broker`. The socket and parent must belong to the admitted UID and deny other users. The public broker CA is an exact pinned `/control/broker-ca.pem`; private CA/signing keys remain outside the container. A separately pinned static `/tools/relay` forwards only container loopback `127.0.0.1:18080` to `/broker/egress.sock`. The exact control script starts the relay. The host sets only fixed proxy/CA variables; no network interface is granted. Broker policy and operation authority remain separate controls.

No real credentials are supplied by this adapter. The reviewed provider control can contain identity-bound opaque placeholders issued by `BrokerCredentials`; the broker substitutes actual process-held credentials only for its exact approved OAuth route. That service integration requires its own acceptance evidence and must not be inferred from this host proof.

## Independent effects exercised

`work/evidence/epoch-20261007-r4/worker-host/qualified-01/RECEIPT.json` records 9 passing tests with unchanged source hashes. These launch actual containers and retain raw inspect records, command status, stdout/stderr, payloads and journals. They assert nonroot identity; denied root/source/control writes; absence of host socket and inherited secret canary; denied direct IP connection; loopback-only network; effective capabilities zero; no-new-privileges and seccomp; exact limits and mounts; actual pinned OpenTofu 1.13.1 version execution; timeout/descendant termination; combined output bounds; SIGINT cleanup; controller SIGKILL followed by separate recovery; prelaunch hash substitution rejection; literal complex mount paths; and native static relay request/reply over the sole mounted Unix socket.

Replay from the project:

```sh
INTUNE_WORKER_HOST_TEST_EVIDENCE=/private/NEW-evidence \
  /workspace/intune-runtime/bin/python -B -m unittest -v plugin_tests.test_worker_host_r4
```

The retained `worker-host/replay.py` captures before/after source identity and raw output in a fresh destination. Existing tests assume the declared Docker/image and pinned local tool locations; an absent prerequisite is a failure, never a simulated pass.

The first development run used an incorrect inherited OpenTofu hash and exposed a real relay half-close defect. The host correctly rejected the incorrect tool. The actual installed pinned OpenTofu binary is version 1.13.1, SHA-256 `a325c8c2f6834575e440b03c2ba67f94256072754ac7787fea718be6f01fef6a`. `relay-before-02` preserves the old relay receiving the request but dropping the reply after client half-close; `qualified-01` preserves the passing same request/reply assertion with repaired relay SHA-256 `2e321b0efa62fcd710401b814a18b8afd3140ea0202fd1b516875bd814564697`. A first retention attempt exceeded the Unix socket pathname limit and is preserved separately in `relay-before`; tests now use short runtime paths and copy regular artifacts unchanged. Closed runtime socket nodes are represented explicitly by type/mode/owner metadata, not claimed as copied regular files. Overlapping reruns are not additional unique tests.

## Qualification boundaries and remaining gates

This is actual native Linux Docker host qualification, not live Microsoft Graph/Azure/provider/device evidence. The relay assertion is socket transport only, not a TLS or OAuth integration claim. The OpenTofu assertion is version execution only, not plan/apply or backend qualification. Synthetic canaries and test code are clearly laboratory inputs.

The host and Docker daemon are trusted. Read-only mounts constrain the worker, not a compromised host changing files in place. The writable job bind mount lacks an aggregate filesystem quota: individual file, descriptor, memory, PID, CPU and time bounds do not establish complete disk-exhaustion isolation. An organizational host must provide and qualify a bounded job volume/quota and private encrypted artifact storage, recovery, retention and cleanup policy. This implementation does not install or provision those controls.

Organizational operation further requires independently installed service trust policy and signer separation, actual signed exact-plan approval, real authenticated identities and least privilege, lease/state/ownership preconditions, approved TLS broker interception trust, native Atmos/provider/backend lifecycle evidence, CI runner attestation, device validation and accountable production approval. These gates remain explicit even when the nine host tests pass.
The inspection verifier rejects added capabilities, additional seccomp/AppArmor
security options, device cgroup allowances and automatic container restart.
Pinned native tools and the Docker client cannot reside beneath the worker's
writable job directory: mounting the same file read-only at `/tools` would not
remove its writable `/job` alias. These are pre-dispatch admission requirements.
The R4 independent counterexamples and focused before/after results remain under
`worker-host/` and `independent/`; the original nine-check host receipt retains
its original source scope.
