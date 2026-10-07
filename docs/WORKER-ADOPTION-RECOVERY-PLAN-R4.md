# Adoption interruption: separately reviewed verification and typed disposition

This is an additive staged design, not an active permission route. Initial native adoption and its preapproved first plan remain unchanged.

- Original stopped AdoptionJob, original manifest/signature/dispatch/outcome and its same-authority ownership rows remain intact throughout recovery. No imported capture, caller StateRevision or JSON completion can authorize release.
- The baseline branch is owned by worker_adoption_disposition.py: exact Live/LaboratoryAdoptionRecoveryCompletion proving authenticated original bytes, unchanged fresh Graph, unlocked backend and empty metadata permits a typed read-only disposition. It records adoption_not_observed_execution_unknown, preserves the old unknown outcome and spent import, and releases only original scope rows. Any existing initial verification or recovery-plan record blocks this branch. Future import requires a new ownership scan and new approval.
- The successor branch is worker_adoption_reconcile.py. A new native-adoption-recovery-plan/1 manifest and signed-native-adoption-recovery-plan-approval/1 payload use actual NUL-separated domain intune-workbench:native-adoption-recovery-plan-approval:v1\0. The new approval permits exactly one pinned Atmos first-plan/show operation. It cannot run import or apply and admits no Graph or state-content write routes.
- The new manifest binds the exact stopped original facts, verified lease recovery facts, independent adopted-state revision and fresh capture projection, current separately bound identity/storage/run capability, original source/effective inputs/lock/object/provider principals, reviewed current runtime inventory, fresh closed host/control and broker policy. Only backend state serial/hash and freshly observed ETag may advance to the independently proved successor; source/resource/target/principals cannot change.
- The trusted controller supplies exact process-held runtime and exact fresh recovery completion. Preparation is inert. Before dispatch, canonical signed receipt is snapshotted once; verification, complete approval transcript and one-use consumed nonce are committed atomically to the SAME physical service.sqlite3 authority. The separate adoption_recovery_plans table never acquires or transfers the original rows. The original remains the sole owner, so ordinary apply and another adoption remain blocked.
- Plan permit checks current reviewed source/identity/policy, exact original stopped facts and ownership, and a separate current controller PID/start row. Cancellation revokes only this Plan permit. Original cancelled state is historical and cannot be treated as permission to bypass cancellation of the new plan. The Plan uses the existing broker, pinned native host and fixed provider adapter; no second command engine, arbitrary callback, credential map or native command is introduced.
- Plan failure/timeout/cancellation/recording uncertainty preserves original ownership and both histories. Stop/reattach never reruns a plan. Native lease uncertainty from this separately approved Plan remains independently visible and blocks final disposition.
- Final reconciliation requires a NEW exact recovery completion after the Plan (fresh identity if metadata changed ETag), byte-identical adopted state and Graph projection, empty metadata/unlocked backend, actual host cleanup, exact binary/JSON/exit0 no-change plan and durable Plan receipt. It records adopted_verified_execution_unknown, nests the original unknown outcome and independent Plan report, and atomically releases only the original scopes. The original dispatch count stays one and no import receipt is reused.

Initial staged bridge intentionally rejects an already attempted initial first-plan verification until that phase's separate stopped-host and native-lease facts are explicitly supported. This remains a local implementation gap rather than an external credential prerequisite.

All laboratory authentication and loopback fixtures remain labeled laboratory. Native host/process tests, actual platform tests, and accountable organizational approval remain separate gates.

## Prepared entrypoints and replay

The proposed product CLI uses the existing command parser and shared engine:

```text
intune-iac adoption recovery-plan-prepare --job-root NEW --policy POLICY --original-job-root ORIGINAL --manifest REVIEWED_MANIFEST
intune-iac adoption recovery-plan-review --job-root PLAN_JOB --policy POLICY
intune-iac adoption recovery-plan-status --job-root PLAN_JOB --policy POLICY
intune-iac adoption recovery-plan-attach --job-root PLAN_JOB --policy POLICY
intune-iac adoption recovery-plan-cancel --job-root PLAN_JOB --policy POLICY
intune-iac adoption recovery-plan-recover --job-root PLAN_JOB --policy POLICY
```

The selected Workbench object exposes `adoption-plan-review/status/attach/cancel/recover JOB_ROOT POLICY_PATH`. Each checks the active tenant and exact object before observation or cancellation. The existing Plan/Execution tabs retain a distinct `workbench-adoption-recovery-plan-navigation/1` context and restore only review/status/attach. Neither text nor TUI constructs a runtime, signs an approval or calls `run`. The original adoption history shows the recovered classification, original unknown result, final independently observed state/capture and exact capture publication; it never becomes a Graph deployment or last-apply baseline.

Trusted controller preparation uses `make_manifest(original=AdoptionJob, completion=sealed_recovery_completion, ...)`, then the independent operator admits its exact digest through the existing ServicePolicy. A new external signature is verified by `RecoveryPlanJob.run(signed_receipt, runtime=exact_RecoveryPlanRuntime, completion=fresh_sealed_completion)`. The host/controller run and encrypted-storage capabilities are still mandatory. Fresh post-plan `recovery.completion(...)` is required by `plan_job.reconcile(completion)`; then `plan_job.captured_observation()` exposes the exact already checked capture for authenticated publication. These are process-held capabilities and cannot be reconstructed by loading the review JSON.

Replay scripts `qualify_contracts.py`, `qualify_presentation.py`, and `qualify_final.py NEW_OUTPUT` remain in the complete R4 evidence layer. Product tests are `plugin_tests.test_worker_adoption_reconcile_r4` (9 self-contained signature/parser/cleanup methods) and `plugin_tests.test_workbench_adoption_recovery_tui_r4` (5 presentation methods). These overlap the external11 boundary methods and22 presentation scope; do not sum them. The retained receipt-envelope test executes the exact bounded source admission region using historical native manifest/receipt bytes; it is not an integrated recovery run.

At this staged checkpoint, actual signed native Plan dispatch, fresh receiving proof, same-authority transactional negatives, actual CLI/PTY recovery navigation and initial first-plan-phase recovery have not yet been qualified. Recovery of a newly interrupted recovery Plan's own native lease is also a distinct requirement. None of these gaps is a production approval or a credential-only blocker.
