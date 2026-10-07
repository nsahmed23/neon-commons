# R4 bounded pilot profile — proposed, not approved

This is the initial support declaration for the strict continuation contract.
It does not declare the pilot qualified or authorize activation. The recovered baseline
is `289ee9477372825aad848f4482cf681c2ff43b02`; the current **0.9.0 engineering
candidate** continues that source. Its final commit, packages and applicability
are recorded in `CONTINUATION-R4-LEDGER.json`; this profile does not substitute
a version label for exact artifact qualification.
The complete acceptance text is `STRICT-CONTINUATION-CONTRACT-R4.md`.

| Dimension | Declared initial profile | Qualification and limit |
| --- | --- | --- |
| Policy family | Narrow supported Windows Settings Catalog configuration-policy JSON route, preserving settings IDs/types/values, assignments, includes/exclusions, assignment filters and scope tags | Exact per-field mapping/collection semantics must be versioned and inspected. Unsupported fields stay visible and block an operation that cannot preserve them. This is not all Intune families, native OIB adoption or dynamic Atmos support. |
| Pilot write scope | Proposed first qualification: one explicitly named disposable policy, one selected stack/component/backend writer and explicitly named groups, exclusions and filters | Actual IDs, cohort, permitted operation and recovery require the tenant/device owners. A shared policy change can affect every assigned ring. No tenant or object scope is authorized by this document. |
| Inspection identity | Tenant/cloud plus immutable object ID; cross-stack/component/backend declared scope | Names and OIB markers do not prove ownership. Complete, fresh declared search is required before “no ownership found”; otherwise unknown. |
| Repository | Exact selected Git revision and effective Atmos inputs, source/inheritance hashes, provider/tool locks | The bounded literal resolver is distinct from native Atmos execution. Repository, snapshot-to-snapshot, provider-state and verified-deployment comparisons have separate baselines. |
| Operator host | **Native Windows with Git Bash is required**; mintty and the actual organizationally chosen terminal need separate observations | Linux PTY results do not qualify Windows/MSYS path conversion, Unicode width, startup, ACLs/reparse points or process cleanup. Windows store operations are currently UNSUPPORTED; isolated Win32 components do not activate support. Text/help is retained, with actual functionality gated by host capabilities. |
| PowerShell | Native **PowerShell 7** route, exact build to be pinned on the provided host; Windows PowerShell 5.1 is unsupported by the supplied launcher | Check every native exit code; preserve the primary failure if cleanup also fails. Linux PowerShell history is preserved and is not native Windows evidence. |
| Local development host | Existing Linux x86_64 with retained CPython 3.12 environment and pinned wheel lock | This is the available disposable engineering environment. Exact version/host observations belong to new receipts; no inferred cross-platform support. |
| Runtime | Existing Python engine and dependency lock; complete text CLI remains reference | The Linux visual and text presentations share the existing engine, durable events and worker interfaces. Native Windows observation, console, inspection, current-source, intent/proposal and bounded source-edit/recovery components are integrated through explicit inactive qualification routes. Native host support remains unqualified; portable authenticated worker evidence is still being integrated. No new UI dependency is organizationally approved by listing candidate libraries. |
| OpenTofu | Current local pin **1.13.1**, Linux AMD64 SHA-256 `a325c8c2f6834575e440b03c2ba67f94256072754ac7787fea718be6f01fef6a` | `intune_iac/native_pins.py` is the discovered current pin. Historical 1.10.0 remains for explicit reproduction, not silently substituted. Windows binaries need their own verified native pins and evidence. |
| Atmos | Current local pin **1.230.1**, Linux AMD64 SHA-256 `f3b5b42e897a2778678cc1231e7a4e2476773bc61ea2af225586dc4e96408802` | Historical 1.199.0 labs/fixtures remain preserved. Native selected route must be qualified with the actual pinned engine/provider; no invented flags or implicit bypass. |
| Provider | `registry.terraform.io/deploymenttheory/microsoft365` 1.0.0 repaired epoch build; binary SHA-256 `415097131c64a47c8435ce9528d050382996cfa4bed38d0960548f160a0b0dd3`; source lineage `1718c946b3ae111bb44c7c1d925b3e35b708cb0a` plus retained repairs | R3 native init/schema/credential-free validation is recorded. Actual pinned native import/refresh/apply/readback/convergence has local nonforwarding TLS-fixture evidence, including partial and committed-state interruption recovery. The corresponding real Intune route remains unqualified; the malformed-error SDK crash remains an unresolved release blocker. The constant named `PRODUCTION_PINS` is not production acceptance. |
| Execution service | Integrated protected Linux native worker/broker/backend/controller; **organizational platform choice unresolved for deployment** | Existing handoff and repository name GitHub Actions; Azure DevOps Pipelines is proposed but not confirmed. Do not implement/deploy two platforms or treat publication authority as protected-workflow administration. Obtain the smallest organizational platform decision when deployment-specific work requires it. |
| Identity | Explicit distinct collector, provider/plan and backend/write principals as supported by the real tools | Authentic service context, tenant/cloud/audience, approved permissions and receiving-service verification are required. Ambient credentials, labels and decoded token claims alone are insufficient. No credential provisioning is authorized. |
| Backend | Integrated Azure Blob backend with explicit subscription/account/container/key, backend principal, lineage/serial and native locking | R3 separate lease/Azurite/local-state tests are narrower evidence. R4 now integrates the actual native worker/backend protocol locally: exact approved binary plan, authenticated-interface role separation, phase-aware reads, native lease/state, separate readback and new-operation recovery. Real Azure identity/RBAC, concurrency and lease semantics remain unqualified; local fixture success does not supply them. A Blob lease does not fence portal/other-stack Graph writes. |
| Observation | Authenticated read-only Graph adapter feeding existing durable store; independently scheduled collection and atomic publication | Reader-to-store integration and independent observer process entrypoints exist. Generated timer/cron adapters install nothing. Both actual BusyBox scheduler attempts failed before launching any observer; closed-terminal OS scheduling remains blocked on a host with the required scheduler capability. Real credentials or schedule activation require applicable authorization. No automatic rollout follows health. |
| Health | Configuration parity, service acceptance, device reporting, processing, endpoint effective state and outcome remain separate | Eight successful fresh reports of 100 targeted means 8% targeted with 92 unknown/stale, even if the reporter success rate is 100%. Unverified targeting denominator remains unknown. |
| Scale | Preserve measured 1,000-object synthetic inventory pages; maximum 1,000 rows/16 MiB per query, SQL and decoded metadata bounds remain explicit | Original R3 workload and quiet-window results are not a fleet SLA. Pilot object/device counts, collection frequency, concurrency and retention must be named before real qualification. Do not infer percentiles from a few samples. |
| Sensitive artifacts | Private state, plans, exported plan JSON, raw captures and receipts; reviewed encryption/access/retention/key recovery | Native state/plan encryption does not encrypt exported JSON automatically. Public handoffs require a reviewed allowlist and explicit private omissions. |
| Host boundary | Explicit reviewed worker filesystem, egress, secret, supervisor and artifact-verifier boundary | Restricted lab network denial stays intact. Cooperative restart/process cleanup is not power-loss or hostile-host containment. Those require actual suitable authorized hosts and protected independent evidence. |

The connected journey already exercised locally, and still required on the declared actual platform, is: discover a policy absent from the
selected state; inspect exact settings/targeting and complete ownership scope;
adopt without unintended first-plan changes; prepare one bounded authoritative
source change; review and approve exact saved-plan bytes; dispatch the durable
protected operation; detach/reopen without cancellation or replay; independently
read back policy and assignments; establish a second no-change plan; retain
uncertainty during an interrupted response; and reopen fresh history after a
collector ran without the terminal. Device effect is a separate final
observation, never inferred from Graph acceptance.

Laboratory completion, platform qualification and production approval are
separate ledger outcomes. The R3 1,242-test result, 64-check connected journey,
and R2 1,141-test result keep their original revisions and scopes. They are not
new R4 passes. A new source change requires affected-scope evidence; unaffected
evidence reuse needs explicit dependency/byte equivalence.

Required external owners are: Windows host owner; execution-service owner;
tenant/identity/backend owners; device/pilot owner; AppSec/risk owners; and
operations/release owner. Their decisions and authorizations are absent here.
Historical temporary-file/reappearance findings and the c122 commit-command
attribution gap remain open until attributable evidence or an accountable
scoped disposition exists. The assistant cannot accept those risks.

R4 native local testing found a malformed-Graph-error SDK nil dereference in
the unchanged pinned provider. The failure, conformant-error controls and exact
unchanged state evidence remain under `worker-provider/provider-negative/`.
Its isolated source repair is untested, no replacement binary exists, and an
automated agent-execution rejection stopped that repair task. It remains a
release blocker; successful local lifecycle evidence does not close it.


## Current bounded outcome and executable prerequisites

The local native worker is implemented. Its laboratory evidence includes actual
pinned Atmos/OpenTofu/provider processes, independently read policy/settings and
assignments, exact state admission, a no-change second plan, real cancellation
input at lease/policy/state stages, separately signed exact lease release,
description-only fresh-plan recovery and reconciliation that preserves unknown
execution provenance. The four inspection views retain unsupported raw evidence
and separate ownership/coverage and drift baselines. This is not a real-service
or device qualification claim. See [native implementation and evidence](WORKER-PROVIDER-R4.md)
and `work/evidence/epoch-20261007-r4/worker-provider/NATIVE-SERVICE-EVIDENCE-INDEX-04.json`.
The 79-file source snapshot for the completed description case bounds reuse;
subsequent runtime changes need explicit linkage or a new final gate.

| Outcome | Current conclusion | Required next evidence |
| --- | --- | --- |
| Laboratory completion | **Not globally declared complete.** Protected native adoption and same-authority maintenance have precise passing laboratory scopes at checkpoint12. Interrupted adoption recovery, source-to-execution binding, portable evidence, the stopped provider finding, failed real OS scheduler attempts and exact final-package gates remain explicit. | Finish independently executable remaining implementations and exact-package gates; preserve each failed/stopped scope. |
| Platform qualification | **Not qualified.** Native Windows/Git Bash/mintty/PowerShell, protected CI, real Azure/Graph/provider identity/state and enrolled devices lack required evidence. | Execute G01–G10 in [the external gate register](EXTERNAL-GATES-R4.md) on the named approved environments. |
| Organizational production approval | **Not approved.** No accountable risk, operations or pilot decision has been recorded. | Named owners sign the exact qualified profile, remaining-risk disposition, monitoring/recovery and intended use. An assistant or test suite cannot grant approval. |

The first external decision is the protected execution platform and its owner;
GitHub validation already exists, while a privileged GitHub deployment or Azure
DevOps replacement is not authorized merely by that fact. GitHub runs
[37572241575](https://github.com/nsahmed23/neon-commons/actions/runs/37572241575)
and [37570928891](https://github.com/nsahmed23/neon-commons/actions/runs/37570928891)
on the exact 0.8.0 source failed before creating jobs because job-level `env`
used unavailable `runner.temp`. R4 repairs that source locally; final GitHub
admission and execution, protected ref controls and exact-plan authority remain
separate external gates. Read-only evidence found the source/handoff branches
unprotected; publication access is not permission to administer those controls.

A private disposable Linux cron environment with its normal user/group setup,
or an approved available user-systemd timer, is the specific scheduler need.
Do not treat the two failed BusyBox attempts as missing implementation or as
permission to expand privileges. The already implemented observer/scheduler
preparation can be reviewed without starting a service. See G06 for the exact
commands, credential-delivery preparation, stop procedure and required receipts.

Native adoption now has a separately signed durable route through `adoption prepare/review/status/attach/cancel/recover` and trusted `AdoptionJob.run`. Checkpoint12 qualifies its actual pinned native import and first no-change plan, followed by same-authority exact-plan correction/readback/convergence. `NATIVE-ADOPTION-EVIDENCE-INDEX-02.json` retains precise source, fixture and assertion scopes. These are nonforwarding laboratory protocols; actual tenant qualification remains required. Interrupted-adoption recovery and explicit source-to-execution binding remain separate local work. The old network-denied provider preparation and modeled Workbench adoption keep their distinct scopes.
