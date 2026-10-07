# Persistent authenticated observation

The reader connects the existing bounded Graph capture adapter to the existing
Workbench SQLite history. It has a separate reader identity and needs no Azure
backend credential. The local implementation and explicit laboratory response
profile are executable. Authentic Graph, organizational secret delivery and
installed scheduling require their own approved environment and evidence.

The actual commands are `workbench observer-create`, `observer-run`,
`observer-status` and `observer-scheduler` under `scripts/intune-iac.py`.
Creation and scheduler preparation perform no authentication or collection.
`observer-run` performs one due cycle as its own process, independent of the text
terminal or visual workspace. It does not spawn a privileged worker or invoke a
mutation. The prior modeled `schedule-*` commands retain their separate profile.

## Identity and scope

An explicit nonzero tenant UUID, application/client UUID, service-principal
object UUID and sorted, unique set of 1–100 policy UUIDs define a job. The
credential is obtained only from the exact environment variable named at job
creation; there is no account discovery, CLI cache, default credential chain,
credential persistence or token decoding. The worker exchanges that credential
at the tenant-specific Microsoft OAuth endpoint and independently reads the
exact Graph service principal, requiring matching object ID, app ID and
`accountEnabled:true`. Public-cloud TLS and destinations are fixed. Redirects
and mismatches fail closed. Token lifetime and total execution time are bounded.

The organizational permission review must cover the required service-principal
read (normally application `Application.Read.All`) and Intune configuration
reads (`DeviceManagementConfiguration.Read.All`) for this route. Those names
are preparation, not a grant or a claim of least privilege in an actual tenant.
Observed successful reads do not prove absence of excess permissions. No
permissions, principals or credentials are provisioned by these commands.

The existing capture contract reads the **tenant-wide configuration-policy
listing**, then settings and assignments for each selected immutable ID. A
selected policy list is not an Intune authorization boundary, and raw policy
listing pages can contain other policy metadata. Job configuration and receipts
state this read scope. There is no Graph write route, arbitrary URL option or
scope expansion through continuation URLs. The narrow existing Settings Catalog
mapper remains authoritative; unknown fields/shapes remain explicit unsupported
evidence with restricted raw bytes.

Only the fixed native constructor can create `LiveGraphReader`. Injected
recorded responses create `LaboratoryGraphReader` and remain
`graph_reader_laboratory`, with `source_authenticity_verified:false`. Neither
JSON nor a boolean assertion can create a reader capability. The ordinary
`import-capture` command remains `graph_capture_unverified`, including when its
bytes came from a prior reader job. Persisted receipts provide local provenance;
they are not independently authenticated, tamper-proof capabilities.

## Durable publication and recovery

Every cycle writes an in-flight journal before credential lookup. Captures are
staged in a new private per-attempt directory. A single SQLite transaction
publishes all selected-scope outcomes and their coverage. Complete supported
policies publish their exact mapped observation; denied, partial and unsupported
policies retain last-good values. An atomic publication error publishes none of
that batch and retains staged raw files. Missing credentials and identity errors
become visible failed attempts with unknown coverage, not empty assignments.

Publication is idempotent for the exact process-held job/attempt/capture binding.
A changed binding for an existing attempt is rejected. Reuse of the exact same
capture in a new attempt preserves the attempt but does not invent another
service observation. New independently collected timestamps remain distinct
observations even when content is unchanged. Older captures remain inspectable
history and cannot replace newer object heads. Partial evidence is never
normalized into complete empty desired state.

A nonblocking per-job lock rejects overlapping collectors. Source, interpreter,
virtual-environment configuration, store directory and database identities are
bound at creation and checked again before publication. A changed installed
source requires an explicitly created, reviewed new job; do not rewrite a
saved job's hashes to make it run. This is cooperative local identity checking,
not isolation against a malicious account owner.

On restart, an unfinished attempt is marked interrupted. Recovery checks for a
prior atomic SQLite publication, preserves any committed observations, and
records failed unknown scopes when no publication exists. It never restores
authentication from disk or automatically imports staged bytes as authentic.
The next due cycle authenticates again and makes new bounded reads. Due times,
missed cycles, last attempt, last success, failure and interruption counts remain
visible with the terminal closed. `observer-status` reports collection
freshness, not device health or rollout authority.

The profile admits intervals of 60–86,400 seconds, cycles of 1–300 seconds,
10,000 retained cycles, and 512 MiB of retained capture bytes. A final bounded
capture can cross the storage threshold; the next capture/cycle fails visibly.
Each capture retains the existing 100-attempt, 4 MiB page, 8 MiB total-response,
120-second and three-attempts-per-page caps, including qualified Retry-After
handling. The existing 2 MiB store-document and 16 MiB query bounds still apply;
oversized publication fails instead of dropping content. No retention cleanup
deletes old evidence automatically.

## Preparing an approved external schedule

Use `--help` to inspect exact arguments. With already approved identifiers and
fresh private paths, preparation is:

```text
python -B scripts/intune-iac.py workbench observer-create --root STORE --tenant TENANT_UUID --client APPLICATION_UUID --principal SERVICE_PRINCIPAL_UUID --object POLICY_UUID --secret-env APPROVED_READER_SECRET_VARIABLE --interval-seconds 300 --max-duration-seconds 120 --output NEW_JOB
python -B scripts/intune-iac.py workbench observer-scheduler --job NEW_JOB --output NEW_SCHEDULER_REVIEW
python -B scripts/intune-iac.py workbench observer-status --job NEW_JOB
```

These commands create an inactive Linux user-systemd oneshot service, timer and
receipt with exact argv, credential-variable name, source binding and cron
command. They never install, enable, start or modify a daemon, profile, crontab
or cloud schedule. The service's `EnvironmentFile` is a deliberate unresolved
placeholder; the organization must select and qualify its private secret
delivery route before installing it. Do not put a secret into an argument,
repository, terminal prompt, evidence log or public handoff. Systemd file
quoting and `%` specifier escaping are explicit; paths with unsupported control
or non-ASCII characters are rejected for unit generation rather than guessed.
The one-shot CLI continues to support ordinary Unicode paths.

After host and identity approval, the same exact command is the execution
entrypoint:

```text
python -B scripts/intune-iac.py workbench observer-run --job APPROVED_JOB
python -B scripts/intune-iac.py workbench collection-history --root STORE --object POLICY_UUID
python -B scripts/intune-iac.py workbench inspect --root STORE --object POLICY_UUID
```

An authorized service owner must independently verify timer execution with all
terminals closed, process identity, secret-file permissions, real TLS/service
identity, pagination/denial/throttling, restart and concurrent-run rejection,
raw capture hashes, SQLite observations, last-success/freshness and the next due
time. Test credential revocation and rotation without logging credentials.
Stop/disable the approved timer to prevent further collection. An interrupted
read does not mutate the service; preserve its journal and partial captures,
then inspect/restart only under the same approved scope.

Linux scheduling is the admitted implementation profile. Other host scheduler
routes are rejected, while parser registration preserves the complete text
interface. This does not qualify Windows/Git Bash, macOS or an installed user
systemd service. The generated units require native host execution evidence.

## Laboratory and external acceptance

The explicit `--laboratory-fixture FILE` creation option pins a local recorded
response file and permanently labels the job laboratory. Its schema is
`intune-observer-fixture/1`, with `responses` containing ordered objects with
`method`, `host`, `path`, `status`, JSON `body`, and optional header pairs. It
checks the real request sequence but performs no network request. Synthetic
credential values are required through the named variable. No fixture flag or
file is accepted by the native live constructor.

Focused replay from the project root:

```text
/workspace/intune-runtime/bin/python -B -m unittest -v plugin_tests.test_observation_reader_r4 plugin_tests.test_observation_jobs_r4
```

These tests qualify identity mismatch/expiry, forbidden promotion, escaped
pagination, raw-byte substitution, denied assignment preservation, atomic
publication failure, duplicate/out-of-order handling, real independent CLI
processes, missing credentials, overlap, restart, source substitution, freshness
and inactive scheduler artifacts. Raw first failures and corrected runs are
retained under the R4 observation evidence epoch; overlapping reruns are not
additional unique test counts. Independent application acceptance is recorded
separately.

The private SQLite and raw-capture directories use the existing restrictive
filesystem and transactional durability profile. They are **not encrypted** by
this module. Before a pilot, the organization must qualify encrypted storage,
access controls, protected backup/retention, key recovery, real scheduler and
secret delivery, service identity and enrolled device evidence. Store
backup/migration/restore remains the existing application route; separately
preserve job configuration, journals and captures in approved protected storage.
Restoring a database changes its file identity and requires a fresh reviewed
job. A local history restore is not infrastructure rollback. No platform or
organizational production approval follows from laboratory success.
