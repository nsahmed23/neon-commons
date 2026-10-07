# R4 bounded pilot profile — proposed, not approved

This is the initial support declaration for the strict continuation contract.
It does not declare the pilot qualified or authorize activation. The initial
source is `289ee9477372825aad848f4482cf681c2ff43b02`; new candidate revisions and
artifacts must be entered in `CONTINUATION-R4-LEDGER.json` after qualification.
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
| Runtime | Existing Python engine and dependency lock; complete text CLI remains reference | Visual presentation must share engine, durable events, approvals and worker interfaces. No new UI dependency is organizationally approved by listing candidate libraries. |
| OpenTofu | Current local pin **1.13.1**, Linux AMD64 SHA-256 `a325c8c2f6834575e440b03c2ba67f94256072754ac7787fea718be6f01fef6a` | `intune_iac/native_pins.py` is the discovered current pin. Historical 1.10.0 remains for explicit reproduction, not silently substituted. Windows binaries need their own verified native pins and evidence. |
| Atmos | Current local pin **1.230.1**, Linux AMD64 SHA-256 `f3b5b42e897a2778678cc1231e7a4e2476773bc61ea2af225586dc4e96408802` | Historical 1.199.0 labs/fixtures remain preserved. Native selected route must be qualified with the actual pinned engine/provider; no invented flags or implicit bypass. |
| Provider | `registry.terraform.io/deploymenttheory/microsoft365` 1.0.0 repaired epoch build; binary SHA-256 `415097131c64a47c8435ce9528d050382996cfa4bed38d0960548f160a0b0dd3`; source lineage `1718c946b3ae111bb44c7c1d925b3e35b708cb0a` plus retained repairs | R3 native init/schema/credential-free validation is recorded. Real native import/refresh/apply/readback/convergence on Intune remains unqualified. The constant named `PRODUCTION_PINS` is not production acceptance. |
| Execution service | Common protected worker contract first; **platform choice unresolved for new deployment** | Existing handoff and repository name GitHub Actions; Azure DevOps Pipelines is proposed but not confirmed. Do not implement/deploy two platforms or treat publication authority as protected-workflow administration. Obtain the smallest organizational platform decision when deployment-specific work requires it. |
| Identity | Explicit distinct collector, provider/plan and backend/write principals as supported by the real tools | Authentic service context, tenant/cloud/audience, approved permissions and receiving-service verification are required. Ambient credentials, labels and decoded token claims alone are insufficient. No credential provisioning is authorized. |
| Backend | Integrated Azure Blob backend with explicit subscription/account/container/key, backend principal, lineage/serial and native locking | R3 separate lease/Azurite/local-state tests are narrower evidence. The live worker/backend integration and real Azure qualification remain required. A Blob lease does not fence portal/other-stack Graph writes. |
| Observation | Authenticated read-only Graph adapter feeding existing durable store; independently scheduled collection and atomic publication | Finite modeled `schedule-run` alone does not satisfy independent scheduling. Real credentials or live schedule activation require applicable authorization. No automatic rollout follows health. |
| Health | Configuration parity, service acceptance, device reporting, processing, endpoint effective state and outcome remain separate | Eight successful fresh reports of 100 targeted means 8% targeted with 92 unknown/stale, even if the reporter success rate is 100%. Unverified targeting denominator remains unknown. |
| Scale | Preserve measured 1,000-object synthetic inventory pages; maximum 1,000 rows/16 MiB per query, SQL and decoded metadata bounds remain explicit | Original R3 workload and quiet-window results are not a fleet SLA. Pilot object/device counts, collection frequency, concurrency and retention must be named before real qualification. Do not infer percentiles from a few samples. |
| Sensitive artifacts | Private state, plans, exported plan JSON, raw captures and receipts; reviewed encryption/access/retention/key recovery | Native state/plan encryption does not encrypt exported JSON automatically. Public handoffs require a reviewed allowlist and explicit private omissions. |
| Host boundary | Explicit reviewed worker filesystem, egress, secret, supervisor and artifact-verifier boundary | Restricted lab network denial stays intact. Cooperative restart/process cleanup is not power-loss or hostile-host containment. Those require actual suitable authorized hosts and protected independent evidence. |

The first actual user journey to qualify is: discover a policy absent from the
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
