# Task 3 — execution and reconciliation implementation

Status: **implemented and tested for read-only plan review plus local filesystem simulation; enterprise external execution remains unavailable**.

This implements Task 3 of `docs/superpowers/plans/2026-09-30-enterprise-execution.md`. The runtime files are `intune_iac/execution.py` and `intune_iac/reconciliation.py`. Integration signatures and limitations are documented in `docs/EXECUTION.md`. Root owns CLI and release integration.

## Delivered behavior

The plan reviewer consumes actual `show -json` plans. It checks supported versions; missing/unknown fields; both prior and planned resource/output denominators and known before/after-value consistency; actions, replacements, deletions and forgetting; drift, deferred/incomplete/errored plans; import identity; masks, checks and provisioners. Its output contains safe hashes and static codes, not user values or names. A no-change result is advisory and never execution authority.

The coordinator performs actual separate local policy and assignment writes through one fixed adapter. It binds plan/configuration/tool/target hashes; checks the initial state and every step boundary; writes durable started/verified/completed receipts; verifies actual file readback; and uses a target-local operation lock across different receipt locations. No subprocess, native binary, provider or cloud operation is dispatched. A JSON approval cannot activate an external adapter.

Reconciliation rereads current state and the closed receipt chain. Desired, precondition, partial, diverged and unknown observations are distinguished. No classification authorizes replay or releases an uncertain lock. A receipt-write failure after an effect remains uncertain, rather than being mislabeled as an operation that failed before effects.

## Verification

Command:

```text
/workspace/scratch/26b6d364cfda/plugin-clean-venv/bin/python -m unittest plugin_tests.test_execution plugin_tests.test_reconciliation
```

At the Task 3 checkpoint: **47 tests passed, zero failures, errors or skips**. The exact console receipt is `green-tests.txt`. A broader concurrent-checkpoint run of `python -m unittest discover -s plugin_tests` passed **375 tests**, zero failures/errors/skips in 21.162 seconds (`all-plugin-tests-checkpoint.txt`). After the final repairs and decomposition, a fresh plugin-test discovery passed **381 tests**, zero failures/errors/skips in 21.987 seconds (`all-plugin-tests-final.txt`). These are the plugin-test discovery scopes at those moments, not the final integrated full/core verifier; root will run that after all workstreams stabilize. Tests perform real temporary local writes; fault injection is at adapter/receipt boundaries and includes before-effect exceptions, lost responses after policy writes, readback mismatch, failed initial/final/mid-operation receipt writes, abrupt interruption, changed artifacts and concurrent live attempts with independent adapter instances and separate journals.

The first 31 tests were run before runtime implementation and failed with assertions that the implementation was absent, not harness errors (`red-tests.txt`). Follow-up failures were reproduced and repaired:

- `red-plan-denominator.txt`: incomplete planned-value denominator, contradictory known values, silently ignored malformed fields, and bool-versus-number no-op equality.
- `red-journal-and-race.txt`: an impossible but hash-consistent event sequence, substituted desired values after the started receipt, and changed policy identity.
- `red-output-denominator.txt`: output values hidden outside `output_changes`.
- `red-prior-state.txt`: existing resources/outputs omitted from both after-side collections, contradictory known-before values and missing/future/malformed prior state.
- `red-lock-owner.txt`: substituted lock ownership must not be removed by the earlier operation.

The independent security reviewer identified canonical type equality, strict receipt transitions, and output-denominator checking. The implementer identified the desired-snapshot dispatch race and immutable fixture identity gap. A separate independent reviewer found the missing prior-state denominator and verified its repair with eight direct native controls/counterexamples (`independent-prior-state-review.json`). Their covering tests are now green. Journal reads also bound directory enumeration and reject unexpected fields, including payloads that could leak raw values.

`native-plans/` contains four byte-preserved JSON outputs from the earlier actual OpenTofu 1.10.0 adoption lab, with their original source paths and hashes in `native-plan-reviews.json`. The current reviewer accepts the two ordinary no-change plans and blocks the update/create plans because they contain computed unknown values. This is a replay of real native outputs, not another native run or a live-provider qualification. The imported-identity file is a no-change plan after import, not proof that the importer itself ran in this task.

A separate execution receipt (`local-operation-receipt.json`) records nine assertions over actual local writes for completed, fail-before and lost-response scenarios. Only result hashes and static outcome codes are retained.

The plan reviewer was decomposed into named sections during the repair: Radon complexity fell from 47 to 4 for `review_plan`, and from 39 to 11 for `_review_change`; the final maximum function complexity is 18. Exact reports are `complexity-before.json` and `complexity-after.json`. This is maintainability evidence, not a correctness proof.

## Research decisions

Six raw source units across four pinned repositories and three official documentation pages were inspected. `source-ledger.json` records commits, licenses, raw-file hashes, inspected ranges, URLs and use decisions. No upstream source code was copied, no skill was installed, and no upstream CI or acceptance test was executed by this workstream.

- **tfmigrate:** source shows two separately ordered state pushes and history persistence after application. This directly informed write-ahead receipts and retention of unknown/partial outcomes. Its force/skipped-plan options are not exposed.
- **Atmos:** the inspected newer source allows compatibility flags to override declarative defaults and treats saved-plan apply differently from planning. Its behavior is not assumed for the older installed qualification version. A future adapter must fix and qualify its command contract.
- **HashiCorp agent-skills:** typed values, ID comparison across steps and explicit pre/post-refresh checks are useful acceptance-test concepts. One example deserves correction: after applying an updated configuration, switching back to the original normally requires a change; an empty `PreApply` expectation at that moment is not a reliable general no-op test. This is an inference from the example sequence, not an executed defect report against the upstream repository.
- **Anton Babenko terraform-skill:** selected useful ideas are saved-plan artifact handoff, environment protection, keyless identity and restricted plan artifacts. Floating tool versions, unlocked examples and automatic apply examples are not copied into this executor. Guidance is not evidence of an approved enterprise pipeline.
- **Official JSON/apply documentation:** structured effects and masks guide inspection; passing a saved plan bypasses an interactive approval prompt. Therefore plan review cannot itself be considered authenticated approval.

## Rulings and remaining boundary

1. External execution stays unavailable because no qualified authenticated privileged adapter exists. The concrete local adapter allows the orchestration and failure semantics to be exercised now. Cost: no production deployment can be performed by these APIs yet.
2. Any unknown/sensitive/deferred effect blocks this initial plan-review slice. Some harmless computed fields therefore block routine plans; relaxing this requires provider-aware proof, not ignoring those values.
3. Format versions 1.0–1.2 are syntactically supported, with actual native corpus evidence only for 1.2 and engine version 1.10.0. Unknown fields/minors block even though upstream compatibility guidance permits ignoring additive minor fields.
4. Receipts prove local consistency, not origin. An adversarial writer can replace a whole consistent history; protected delivery/storage and authenticated principals remain separate requirements.
5. The filesystem protocol assumes cooperative private POSIX storage. It does not qualify distributed locks, hostile local filesystem races, deployment-filesystem power loss or Windows.
6. No automatic unlock/retry is exposed. Unknown histories must be reconciled and explicitly resolved by a future qualified operational process.

E04 and E05 advance from contracts toward tested implementation, but neither enterprise gate is closed. Still open: binary-plan provenance, authenticated effective target and writer, protected approval, native state lock/operation concurrency across machines, restricted credentials, actual provider/service readback, partial cloud failure recovery and authorized pilot evidence. The LLM judge remains advisory.
