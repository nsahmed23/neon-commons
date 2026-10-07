# Inactive native Windows observation jobs

This component runs the existing finite Graph reader and atomic observation publisher through the native Windows target. It does not enable the ordinary Windows Workbench profile, register or start a scheduled task, provision a credential, or establish native Windows qualification. Linux `workbench observer-*` behavior and its platform guard remain unchanged.

The separate component CLI is `scripts/intune-windows-observer.py` with `create`, `run`, `status` and `prepare-task`. The same typed engine APIs back this CLI and local qualification. Use `--help` on the exact packaged script; no service is installed by any subcommand.

## Identity, bytes and durability

A job binds the exact native store directory and database identities, tenant, immutable reader client/principal/object IDs, current owner SID, interpreter/application files and immutable job configuration. Every due run rechecks these before collecting and before publishing. Source or restored-database identity change requires a new reviewed job. Serialized captures or persisted database rows cannot reconstruct authenticated reader authority.

The job stores an immutable chain of events under a native private directory. Each event binds its sequence, previous hash, configuration and complete state. Creation and publication use the existing Win32 private-file, file-flush and mandatory namespace-flush operations. `LockFileEx` prevents overlapping processes; Task Scheduler's overlap setting is an additional control. Unknown files, partial stages, forks, replaced files or failed barriers stop automatic continuation. The component never deletes them to produce clean closure.

An interrupted collector may have committed the SQLite batch before its job receipt. A new process queries the exact `reader:<job>:<attempt>:` publication domain under the pinned store identity. It records the persisted run IDs as local publication evidence, preserving the original interrupted status. It does not reauthenticate an old capture, overwrite the original result, or repeat old reads. A later due cycle obtains new credentials, a new identity observation and new capture capabilities. Failed capture bytes, `storage_outcome` and `observation_outcome` survive separately. Unknown retained-byte measurement exhausts the retention allowance rather than permitting unlimited continued collection.

The initial native profile supports at most 200 cycles, 100 selected objects, 512 MiB retained capture bytes, intervals of 60–86400 seconds and a 1–300 second finite collection budget. Before every object attempt it reserves the native writer’s maximum 56 MiB (8 MiB total raw pages plus three documents each bounded at 16 MiB). A partial failed capture consumes its independently measured retained bytes before another reservation is considered. Insufficient room for the full next reservation stops that object without truncating source or capture bytes, so collection can stop while actual retained bytes remain below 512 MiB. An unreadable partial capture charges the remaining allowance and blocks further reads; `capture_bytes_basis=unknown_conservative_budget_charge` explicitly distinguishes this accounting sentinel from measured bytes. The status view exposes cycle/capture/store-receipt limits, a preservation-oriented next action, declared object IDs, last attempted/ended timestamps and incomplete last-attempt scope. The existing native store's independent receipt bound can stop a job earlier. These are safety bounds, not an operational SLA or measured fleet capacity.

The runtime binding checks the declared native interpreter and application source files through native handles. It is not a claim that the entire Windows DLL loader, OS trust store, installed Python distribution or host is qualified. The narrow file-access component currently requires private approved runtime paths; an ordinary shared installation may remain unsupported until its actual protection policy is separately admitted. Native TLS needs an approved usable trust store; no CA is installed by this component.

## Existing credential only

Live runs use `windows_observer_credentials.CredentialReference` and the sealed `NativeCredentialSource`. The reference names one existing Generic Credential target `IntuneWorkbench/observer/<reviewed-name>`, owner SID and client UUID. Creation, status and task rendering do not read the credential.

A due live run invokes only `CredReadW` under that SID. It requires Generic type, the exact target and client UUID as `UserName`, no aliases/attributes, a session/local-machine persistence class and a bounded UTF-8 secret acceptable to the existing `ClientSecretHandle`. The native buffer is cleared and freed; the Python handle is closed. Python cannot guarantee erasure of every string copy, so process memory remains a host responsibility. The downstream OAuth and immutable service-principal check establish actual service identity; a credential label is insufficient.

There is no `CredWrite`, `CredDelete`, account creation, default Azure credential chain, environment fallback or privilege change. No credential value appears in the job configuration, task XML, command line or receipt. An organization must supply and authorize its existing credential route before a live run; this component does not create one. Laboratory jobs instead use explicit recorded-response fixtures and a synthetic in-memory credential, with laboratory provenance retained.

## Disabled task preparation

`prepare-task --owner-sid <same-bound-SID>` writes new `observer-task.xml` and `scheduler-receipt.json` files. Both task and time trigger are disabled. The only action launches the exact pinned native Python executable with `-I -B`, the exact component script and `run --job <bound-job>`. It uses an explicit SID, `InteractiveToken`, `LeastPrivilege`, one action, `IgnoreNew` overlap behavior, a finite execution timeout, and no restart-on-failure action. No shell or arbitrary argument suffix is admitted. Percent-bearing paths/arguments are rejected so Task Scheduler environment expansion cannot substitute the reviewed executable, script or job. The explicit task account must match both the immutable credential reference and native job owner SID.

`InteractiveToken` covers all terminals closed while the named user remains logged on. It does not cover logged-off collection or an always-running machine service. There is no authenticated Linux-to-Windows history transport in the current implementation that could silently substitute for this local native route. A different organizational service profile needs an explicit account/credential/transport decision and its own evidence.

The file is preparation material only. Registration, exported-task comparison, activation and stop/disable are separate host-owner actions requiring applicable authorization. XML settings alone do not prove the actual task token, account rights, scheduler behavior, independent timing or cleanup.

## Replay and native procedure

Local regression command after integration:

```text
python -m unittest plugin_tests.test_windows_observer_jobs_r4 -v
```

The local tests drive the job, reader, capture and publication interfaces with actual SQLite and recorded Win32 effects. They cover exact SID/credential labels, private binding, source/database replacement, overlap, complete/denied history, missed cycles and freshness, interrupted publication, uncertain storage/receipt failures, event corruption, cleanup, disabled XML and unsafe input. These are not native Windows, credential-store, Task Scheduler or Graph qualification.

On an authorized disposable Windows/NTFS host, use the exact final package and pinned native CPython 3.12 from an already approved private runtime path. The host owner prepares a private parent with the required DACL; the tool does not alter an existing account, ACL, trust store or installed scheduler. Run the credential-free native component qualifier into a NEW directory:

```text
python -I -B scripts/qualify-windows-observer-job.py --output C:\ApprovedPrivate\new-native-job-proof --start-boundary 2026-10-08T00:00:00Z
```

Use a reviewed future UTC boundary when preparing an actual task. The qualifier exercises native private creation, a new store/job, one recorded-response collection, a not-due control and disabled XML. It uses no real credential or service endpoint and registers no task. A namespace-flush failure is retained and blocks the profile; do not bypass it.

Only after the named host owner authorizes registration and the exact inactive material is reviewed:

1. Register the exact disabled laboratory task under the already existing named principal using the organization's approved procedure. Export it independently and compare command, arguments, SID, run level, logon type, repetition, timeout, overlap settings and both disabled flags. Preserve the source/package/task hashes and actual registered-task identifier.
2. Enable only the specifically approved laboratory task. Close every terminal while retaining the named logon session. Independently observe the Task Scheduler event/process creation and new database collection; reopen the component and native terminal interface to inspect history, coverage and freshness. Task activation is not performed by this repository's preparation commands.
3. Challenge overlap, source/DB replacement, missed cycles, kill before/after SQLite commit and receipt publication, restart, denied facets, stale observations and stop/disable. Correlate native SID/DACL/file IDs, lock ownership, task process identity and exact old/new SQLite/event bytes. Preserve any partial stage and unresolved native storage intent.
4. Live qualification additionally requires explicit read authorization for tenant-wide policy metadata plus selected settings/assignments, an existing reviewed Generic Credential, authenticated reader/Graph evidence, revocation/rotation negatives and approved trust roots. Native recorded fixtures cannot replace that evidence.

Release remains blocked for this route until the exact packaged native APIs, actual Task Scheduler with terminals closed, live service identity/coverage, required logoff/reboot profile and accountable operating/security decisions have their real evidence. No test count establishes organizational production approval.

The first staged review reproduced two local defects: a shadowed renderer admitted a percent expansion token, and a reader-close failure after complete captures could incorrectly increment cycle success. Their exact before source and counterexamples are retained in `windows-observer-scheduler-staging/review-before-01/`. The repaired single renderer rejects the token before writing task material; any prior cycle error keeps status failed and last-success unchanged while retaining valid captured publication and primary/secondary cleanup facts.

The second independent staged review retained two compound-fault failures at `independent/windows-scheduler-02/`: a publication error replaced an earlier reader-cleanup cause, and actual SQLite write-lock contention escaped without durably preserving that cause. The repair keeps the first failure code and phase, records publication/capture-measurement failures separately, retains both native transaction and observation-publication outcomes, and cannot advance last-success. Final receipt failure still raises the original failure with recording-failure metadata. The exact near-limit overshoot counterexample at `independent/windows-scheduler-retention-before-01/` is preserved; reservation now denies that capture before reader authentication. The new partial-failure regression uses actual small capture files with an explicitly reduced test admission budget, not a claim of 512 MiB native performance qualification.

A further independent measurement-cancellation counterexample is retained at `independent/windows-scheduler-measurement-before-01/`. A failed capture followed by `KeyboardInterrupt` while counting partial bytes now preserves the original capture failure in the durable record, records cancellation separately, conservatively exhausts the remaining budget, settles as interrupted, and rethrows the actual interruption chained to the primary. The same rule covers a final measurement interruption after reader cleanup and recording failures. It does not silently absorb cancellation or claim a measured size when measurement was interrupted.
