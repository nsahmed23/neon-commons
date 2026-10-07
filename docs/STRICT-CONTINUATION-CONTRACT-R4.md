Intune Workbench — strict continuation goal and acceptance contract

Prepared 2026-10-07. Paste this brief into the existing ChatGPT Work/Codex project. It defines requested work and acceptance criteria; it is not evidence that any new implementation or external qualification has passed.

Goal

Continue the existing Intune/Atmos/OpenTofu workbench from verified 0.8.0 source commit 289ee9477372825aad848f4482cf681c2ff43b02. Complete the remaining implementation, integrate the real execution and observation paths, deliver the specified visual terminal experience, and qualify one explicitly bounded operating profile for an organizational production pilot. Preserve the current engine, all six work threads, original inputs, artifacts and contrary evidence. Work through implementation, independent verification, repair and delivery; producing another plan, increasing a test count, or demonstrating only a simulator does not complete this goal.

The engineer must be able to discover an existing policy, understand settings and targeting, distinguish repository intent from observed changes, adopt it without unintended changes, prepare a reviewed correction, execute the exact approved operation through the authorized platform, verify service and endpoint evidence separately, recover from interruption, and reopen current history and health after collection has run with the terminal closed.

Complete every authorized and independently actionable task. Keep laboratory completion, platform qualification and organizational production approval as three separate outcomes. When an external prerequisite is unavailable, finish the corresponding local implementation, negative tests, reproducible qualification procedure and review package, then continue other work. Do not claim production completion until real evidence and accountable approval exist.

1. Recover and reconcile the exact baseline first

Authoritative starting points:

• Release: https://github.com/nsahmed23/neon-commons/releases/tag/intune-r3-handoff-20261007
• Source: https://github.com/nsahmed23/neon-commons/tree/289ee9477372825aad848f4482cf681c2ff43b02
• Handoff: https://github.com/nsahmed23/neon-commons/tree/3bf60e3ed150ec1d147ef2c07b7bea88f7ad480e/intune-workbench/r3-20261007
• Under that handoff, read work/CHECKPOINT-20261007-R3.md, work/docs/CONTINUATION-ACCEPTANCE-20261007-R3.json, work/docs/EXECUTION-SEQUENCE-20261007-R3.md, and guides/EXTERNAL-QUALIFICATION-R3.md.
• Read applicable AGENTS.md, README.md, WORK_THREADS.md, execution directives, source manifests, architecture decisions and current acceptance ledgers at their actual discovered locations. Do not invent absent paths.

Recovery has three required layers. GitHub’s automatic source ZIP is not the complete repository handoff.

|Layer                        |Expected bytes|SHA-256                                                           |
|-----------------------------|-------------:|------------------------------------------------------------------|
|Complete R2 repository       |2,289,864,715 |`7117ab67ce6ae1912aa2c984774e6370216f3eb28be1510d0c6814cb4c295d0b`|
|Exact 0.8.0 source ZIP       |16,627,882    |`4a0e56e4e01dd58e911a7fd0ad87c8f0be851630f3beb9c40d7ccc0b1b4c8590`|
|Exact 0.8.0 runtime ZIP      |513,895       |`cce47f620f5e1e7d3dbdab1e030624fae3991cbf88376737a4eda07e6c703515`|
|Entire R3 evidence supplement|1,013,682,416 |`a133c651f2df19885d8b1706944bd953f5a5be67960955ee7021600707b62a35`|

Reuse an already verified local recovery. Otherwise follow the pinned distribution manifests, concatenate only explicitly returned ordered paths, verify bytes and digest before extraction, and extract into new directories using type-aware traversal/link protections. Retain literal negative-test symlinks without following them. Do not replace the complete corpus with a reduced bundle.

The published baseline records 1,242/1,242 strict tests and a 64-check, 34-command, 10-Linux-PTY connected journey. Preserve their local scopes and the separate 1,141-test 0.7.0 result. Reuse evidence only when its dependencies and exact bytes remain applicable. Preserve failed candidates, SIGINT/cleanup repair evidence, security limitations, unexplained files/reappearance, commit-actor attribution gaps and Wally’s 87 completed reviews, nine timeouts and no demonstrated benefit. A successful new run does not close historical provenance findings.

If the workspace is newer, inspect its ancestry, changes and receipts before choosing the continuation point. Never overwrite newer valid work to recreate this baseline. Separate baseline integrity, new implementation and new qualification.

2. Establish an executable work plan and continue through it

Create a dependency-ordered plan and requirement-to-evidence ledger, then begin the first actionable implementation. Do not end the task after planning or pause automatically between milestones. Inspect existing commands and help before publishing runnable instructions; names below describe capabilities unless confirmed in the repository.

Each requirement needs: ID, description, required profile, status, evidence class, observed source revision, applicable revision, artifact SHA-256, test/procedure ID, evidence path, environment, limitation, next action and blocker owner. Use normalized statuses NOT_STARTED, IMPLEMENTED, PASS, FAIL, BLOCKED, UNSUPPORTED, or NOT_APPLICABLE; preserve historical ledger statuses verbatim in their original records. Record evidence reuse separately. PASS requires a precise scope; required unsupported, blocked or skipped cases do not satisfy release gates. Excluding a required case from the suite does not remove the requirement.

Report at each meaningful work increment: what changed, what independently demonstrated it, what remains, and the next action. Save a durable checkpoint after each completed milestone, consequential discovery, failed attempt or repair. Include current commit, working-tree changes, evidence paths and exact resume command. State honestly if a session or tool limit stops execution; do not imply background work continues after the session ends.

Keep work on a dedicated continuation branch. Do not alter Neon Commons’ default branch or unrelated application. Reuse existing external-publication authorization within its scope. Do not publish raw tenant captures, credentials, state, saved plans or restricted evidence to the public repository. Public artifacts must be specifically suitable for publication, with omissions explicitly recorded rather than silently called a complete private corpus.

3. Milestone A — accurate inspection, comparisons and ownership

Deliver four connected views with stable tenant/object identity and explicit coverage:

|View      |Required meaning                                                                                                                         |
|----------|-----------------------------------------------------------------------------------------------------------------------------------------|
|Repository|Selected revision and resolved stack/component inputs, compared with a recorded successful deployment configuration when one exists.     |
|Observed  |Independently collected service snapshots, timestamps, freshness, collection coverage and observed changes.                              |
|Proposed  |Exact saved plan’s intended operations, target, identities, provenance, approval and unresolved risks.                                   |
|Coverage  |What discovery, management, mapping and qualification actually cover; show unknown, denied, unsupported and unmanaged objects explicitly.|

Keep comparisons separate: collector snapshot to prior snapshot; provider refresh to the persisted state revision actually used; and current evidence to the last verified deployment where a receipt and readback exist. Label the actual baseline and time. State can change through import, refresh or state operations, so do not universally label provider drift “since last apply.” A plan covers configured/state-tracked resources; discovery must also include supported objects absent from the selected state.

Build or integrate an ownership index across declared stacks, components and backends, including freshness and completeness. Distinguish owned here, owned elsewhere, conflicting claims, no ownership found in a completely searched declared scope, and unknown. A display name, one state file or an OIB marker does not establish ownership. Keep one declared writer per object and assignment collection. Attribute actors only where audit evidence supports the association; a pipeline principal alone does not identify an approved run.

Adapters must declare per-field ordered sequence, set or keyed-collection semantics, including duplicate handling. Preserve raw capture bytes and original order. Preserve type, null, absent, empty, unknown fields, settings IDs, includes, exclusions, filters and scope tags. Make every normalization rule inspectable and versioned. Do not use ignore_changes, dropped fields or a permissive grader to manufacture preservation or convergence.

Accepting a tenant change means a bounded edit to the actual authoritative repository source, reviewed through the normal change process, followed by a fresh plan. Show any shared-inheritance impact. Do not promise no resource changes until the actual plan establishes it; do not silently use refresh-only apply as acceptance of new intent.

Acceptance: independent fixtures distinguish a merged desired change, an observed portal-side change, both occurring together, an object absent from state, a conflicting owner, a stale ownership index and an incomplete collection. Known-bad IDs, exclusions, filters, types and array semantics must fail. These results must be navigable through the actual application.

4. Milestone B — real execution worker, backend and deployment receipts

The 0.8.0 modeled executor and separate backend controls are not a live implementation. Implement the missing routes under an explicit reviewed architecture. Preserve the restricted laboratory path; do not obtain live support by removing its network denial or passing production tokens into it.

Determine the real execution platform from the project’s authoritative configuration and the user’s organizational direction. The existing handoff names GitHub Actions; Azure DevOps Pipelines has also been proposed but is not confirmed. Record the decision. If unresolved, implement the common execution contract and local qualification, and request only the choice needed for platform-specific deployment. Do not implement two complete CI systems or treat a proposal as authorization.

The terminal prepares and observes operations; normal production apply belongs to the approved protected execution service. Closing the terminal detaches from a run and must not cancel, duplicate or requeue its mutation. Reopening attaches to the same durable operation. Local lab and exceptional recovery profiles must remain explicit.

Bind exact repository/revision, workflow/verifier revision, run and attempt, tenant/cloud, stack/component, effective input digest, provider/toolchain locks, provider principal, backend principal, Azure subscription/account/container/key where applicable, state lineage/serial and exact saved-plan bytes. Bind approval to this manifest, operation and expiry; verify again before dispatch. Store a durable receipt/journal before mutation and record partial or uncertain results afterward. Never generate and silently execute a replacement plan after approval. Qualify the pinned Atmos route with the actual engine/provider; do not invent flags or bypass it silently.

Implement native backend identity, lease/locking, concurrency and state-revision handling. Qualify wrong-target rejection, stale state, lock contention, lease loss, interruption and recovery. Saved-plan state checks do not prove fresh tenant state, unchanged external inputs or valid approval. Assess live preconditions using supported service/provider behavior; explicitly record residual races where atomic enforcement is unavailable.

Protect privileged workflows, verifiers, artifacts and write identities from untrusted branches and PR content. Test approval rejection, unauthorized ref, artifact substitution, rerun, concurrency and cancellation. Environment approval alone is not proof of exact-plan authorization. Separate collector, plan/provider and backend/write permissions as the real tools permit. Separate connections or ring names do not themselves enforce Intune scope; editing one shared policy can affect every assigned ring.

Keep secrets out of arguments, prompts, UI events and logs. Protect state, binary plans, exported plan JSON, raw captures and receipts using appropriate encryption, access controls, retention and tested key recovery. Native state/plan encryption does not imply exported JSON is encrypted. Preserve exact artifact bytes independently of text newline settings. Pin and qualify agent images/tools and cleanup; agent type alone is not evidence of isolation.

Acceptance: local contract and fault tests must drive the actual worker interfaces. Platform acceptance additionally requires a real authorized run using pinned native tools, exact-plan approval/application, authenticated independent readback, a no-change second plan and a complete receipt. Until that occurs, report implementation and modeled tests separately from platform qualification.

5. Milestone C — persistent authentic observation and bounded fleet operation

Connect the supported Graph reader to the existing store and history. Implement and locally qualify the scheduling adapter so collection can operate independently of the TUI; an invoked finite modeled timer alone does not finish this milestone. Activation of real credentials or a live schedule requires the applicable authorization.

Stage captures and publish observation batches atomically. Retain every attempt and last-good values when reads are denied, partial, stale or interrupted. Validate pagination destinations before request; use bounded read retries and qualified retry delays. Preserve raw responses securely with coverage and timestamps. Handle duplicate and out-of-order captures without inventing history or replacing newer observations silently.

Expose last attempted collection, last successful collection, missing scopes, freshness and next action. Maintain inspectable typed relationships, versioned history, workflow receipts and a maintenance queue with ownership, rationale, review/expiry dates and linked proposals. Dictionary facts must distinguish vendor documentation, community advice, observations, company annotations and AI interpretation. Keep stable generic identity/evidence concepts in the core and service-specific semantics in adapters; do not rewrite the engine to pursue a universal framework.

Separate configuration parity, service acceptance, device reporting, processing, effective endpoint state and user/device outcomes. Display both reporting and targeted denominators. Eight successful reports out of 100 targeted is 8% of targeted with 92 unknown/stale, regardless of reporter success rate. No automatic rollout or new write follows from a health indicator.

Acceptance: closed-terminal execution, restart, denied and missing pages, throttling exhaustion, concurrent runs, partial publication, duplicate/out-of-order observations, freshness expiry and backup/migration/restore must have independent state assertions. Actual authenticated service and device claims require their own evidence.

6. Milestone D — the requested visual terminal workspace

Build the presentation over the existing commands, typed results and durable operation events. The complete text interface remains the reference route; a richer TUI must use the same engine, approvals and execution contract. Choose a compatible approved dependency only after inspecting the existing stack. Gum, Textual, Bubble Tea or other packages are options, not required rewrites or assumed company approvals.

Deliver a calm engineering workspace with deep navy/charcoal surfaces, thin outlines, aligned monospaced labels, restrained cyan/blue accents, labeled statuses and optional warm-light theme. Use the supplied visual direction as design input, not telemetry or evidence.

|Surface                  |Required behavior                                                                                                                                    |
|-------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------|
|Estate/navigation        |Search policies/settings, filter ownership/coverage/health, page large inventories and select immutable identities.                                  |
|Selected-policy inspector|Exact settings, assignments/exclusions/filters, provenance, coverage, ownership and evidence freshness.                                              |
|Relationship/lineage view|Typed, labeled edges through settings, targeting, source files, Atmos inheritance and deployment history; each edge exposes evidence and uncertainty.|
|History/comparison       |The distinct baselines from Milestone A, exact values and source/observation timestamps.                                                             |
|Plan review              |Dedicated readable review of the exact operation, target, assignments, affected scope, provenance and approval identity.                             |
|Execution/recovery       |Active stage, completed/failed/unknown checks, input needed, durable journal, uncertainty and permitted recovery.                                    |
|Status/help              |Active environment, selection, shortcuts, operation and meaningful next action.                                                                      |

Preserve investigation context across views and recovery. Selected objects and relevant connections should stand out while unrelated content recedes. Graphs must also have text/table equivalents. Use dots, segmented bars and sparklines only when their meaning and denominator are defined. Percentages require a known total; ETAs require measured progress; missing observations remain gaps. Motion reflects actual events and reduced-motion mode retains all information. Pause appears only where safe pause/resume is implemented. Distinguish cancellation requested, stopped and outcome uncertain.

Acceptance: drive the complete investigation/change/recovery journey with real key/input sequences and independent operation/state assertions, alongside terminal captures. Exercise narrow layout, resize, Unicode width, non-color cues, reduced motion, no-TTY output, untrusted control sequences, back/edit/cancel/resume and terminal restoration. Keep performance thresholds preregistered and workload-specific; do not infer fleet performance from a few samples or UI screenshots.

7. Milestone E — qualify the declared operating profile

Declare the initial supported policy families, mapping coverage, host/shell, terminal, runtime, engine/provider versions, CI platform, identity route, backend and scale envelope. The requested workplace route includes Windows/Git Bash; native Windows qualification is required before claiming that route supported. A Linux lab pass is useful but does not close it.

For Git Bash, scope MSYS argument exclusions to the specific native invocation and argument prefixes. Test slash-prefixed Graph paths alongside real filesystem paths; do not disable path conversion globally. Exercise spaces, leading hyphens, Unicode, quotes and CRLF. Normalize reviewed source text appropriately while keeping binary plans/captures byte-exact. Test mintty and the actual chosen terminal; retain usable text mode when optional TUIs are unsupported. Native PowerShell must check native exit codes and preserve the primary failure when cleanup also fails.

Run the supported native lifecycle on explicitly authorized disposable objects: capture, identity-preserving import/adoption, no unintended first plan, one bounded reviewed change, independent policy and assignment readback, convergence and recovery. Prove preservation with independent expected values, not a shared product normalizer. Verify the receiving service’s tenant/principal context independently of caller-supplied labels.

Exercise representative enrolled pilot devices with explicit cohort, monitoring, stop conditions and authorized recovery/cleanup. Distinguish assignment and service acceptance from device effectiveness. Qualify actual CI permissions/approvals and Azure identity/state behavior rather than substituting local simulations. Host crash/power-loss and hostile-process containment require suitable authorized environments; cooperative process restart is a narrower claim.

The minimum fault coverage must include wrong target/identity; changed source/locks after approval; plan substitution/replay/expiry; advanced state; concurrent writers/lease loss; denied or incomplete assignments; pagination escape; throttling; timeout after possible commit; policy success with assignment failure; cancellation during acquisition/write/evidence recording; missing device reports; historical restoration; untrusted workflow input; terminal/shell injection; duplicate names; conflicting reference updates; and Graph acceptance without endpoint evidence. Preserve every failed attempt and prove relevant known-bad controls are rejected.

8. Milestone F — release and accountable production decision

Release from the exact reviewed source. Run changed-scope tests and required gates, independent connected-journey checks, package/extraction checks and reproducible builds. Retain dependency/toolchain/license records, source-to-binary linkage and explicit scopes. Count overlapping tests once; do not replace independent oracles with assertions copied from the implementation. Wally remains optional and read-only; no favorable Wally result is a release prerequisite.

Obtain independent security review for reachable implementation and execution boundaries, and organizational disposition of remaining risks. Unresolved critical/high findings affecting the declared profile block release; unsupported or inaccessible paths cannot be treated as safe without evidence. Preserve provenance anomalies until an attributable explanation or accountable scoped disposition exists. An LLM cannot approve organizational risk.

Produce updated source/runtime packages, actual commands and runbooks, support matrix, requirement/evidence ledger, migration/restore procedures, pilot results, release receipts and continuation instructions. Preserve the full original corpus and all subsequent evidence. Layered recovery is acceptable only with a verified manifest/tool covering every required layer; clearly distinguish runnable runtime, source and complete recovery. Verify public/saved readback and archive reconstruction with exact byte/hash receipts. Never claim a link or upload succeeded without checking its result.

9. Definition of done and stopping rules

|Finish line        |Required evidence                                                                                                                                                                                          |
|-------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
|Laboratory complete|All required local implementations and actual application journeys pass independent assertions, including visual interaction and failure/recovery. Modeled dependencies and unsupported scope are explicit.|
|Platform qualified |Every required external route in the declared profile has real host/service/identity/backend/CI/device evidence tied to the released artifacts. No required blocked, failed or skipped gate remains.       |
|Production approved|Accountable organizational owners have accepted the qualified profile, security/risk dispositions, operations/support/recovery and pilot evidence, and authorized the intended use.                        |

Keep doing useful authorized work until it is complete or a concrete dependency truly prevents it. Do not stop because a milestone passed, a checkpoint was committed, a mock works, or credentials are absent for an unrelated task. Do not expand scope to arbitrary tools or new research frameworks. Investigate only focused questions that block the next implementation or qualification decision.

This brief authorizes continuation planning, code, local disposable tests, documentation and preparation within existing authority. It does not grant new tenant mutation, deployment/control administration, paid resources, credential provisioning, privilege expansion or production approval. Honor prior authorization where applicable; do not repeatedly ask for it. For a genuinely new consequential action, first finish its code, target/scope manifest, tests, recovery procedure and reviewable request. Ask for the smallest specific authorization needed, then continue unrelated work.

If fully blocked, provide a compact blocker table: exact requirement, why it cannot proceed, completed preparation/evidence, required environment or access, responsible owner/decision and exact next command/procedure. Do not hand back an undifferentiated “needs credentials” list. Never bypass a denied boundary or weaken a gate to finish.

Your final delivery must state: exact commit and artifacts; demonstrated user journeys; local, platform and production outcomes separately; remaining required failures/blockers and owners; verified recovery links; and the next concrete action. Do not describe the product as production-ready solely because tests pass.

Begin now: reconcile the exact candidate and current repository, map these requirements to existing code/evidence, record missing capabilities, and implement the first unblocked dependency. Carry the work through verification and delivery rather than returning only a plan.
