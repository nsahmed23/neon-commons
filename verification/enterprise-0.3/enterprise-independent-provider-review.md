# Independent provider source-lab review addendum

Status: **complete — pass for the stated source-lab scope after PR01 repair**. This is a separate addendum; the earlier enterprise implementation review and its 17-file snapshot remain unchanged.

## Scope and fidelity

Reviewed the local GET helper candidate, unified patch, source/schema/patch manifests, qualification runner, AST extractor, actual upstream Schema method, selected Go tests, four profile receipts and implementation report. The qualified subject is selected source plus an inert extracted receiver and synthetic in-memory HTTP responses. It is not an installed provider, provider RPC, native HCL validation, service behavior or production qualification.

Independent checks performed:

- All **32 distinct original source files** named by the core/schema manifests match their acquired raw SHA-256 values.
- Original helper, candidate and patch hashes match the patch manifest. Applying the patch to a fresh temporary pristine copy succeeds and produces byte-identical candidate source. The acquired checkout was not changed.
- The original resource source and exact byte slice match the extraction receipt. The generated method is byte-identical to that slice, including its method signature and body. Method SHA-256: `75306e588e66045ad501265832e7af317c421c7e7eed6ab0dcefb264b219d5dd`. The actual pinned method does not use receiver state. This verifies the stated selected-method extraction; the extractor is not a general proof of arbitrary Go package equivalence.
- All recorded stdout/stderr hashes in the four profile receipts match their files. Independent top-level event counts are: unchanged baseline **27 pass / 0 fail / 0 skip**; original desired-behavior regressions **2 pass / 12 fail / 0 skip**; candidate **14 pass / 0 fail / 0 skip**; extracted Schema **6 pass / 0 fail / 0 skip**.

Receipt: `/workspace/scratch/26b6d364cfda/enterprise-independent-provider-verification.json`. These were integrity checks, source inspection and fresh temporary patch application; this reviewer did not rerun the full Go suites or perform any tenant/provider operation.

## Candidate and extraction assessment

The candidate rejects error statuses and envelopes, missing/null collection values, malformed/duplicate envelope keys, invalid/foreign continuations, loops, redirect following and the declared body/page/aggregate limits. Continuations keep the complete returned query. Initial query parameters are explicitly attached. Source errors do not copy restricted response bodies. The code and tests support those bounded statements.

The patch is correctly separated from the registry/installed provider. MPL-2.0 material and local modifications are retained. The implementation report correctly identifies the shared DELETE caller, configured-client/middleware omission, incomplete assignment refresh and separate lifecycle requests. Those are open qualification requirements, not silently solved by the helper patch.

Individual record shape, duplicate observation identities, count consistency, full serializer/state equivalence and actual service collection semantics are outside this transport/envelope candidate. The review does not infer completeness or safe adoption from passing these tests. The Schema path executes selected real Framework validators/defaults but does not prove their ordering during a full provider plan.

## PR01 — P2, repaired: deadline cleanup could leave an owned descendant running

Location: `scripts/qualify-provider-contract.py`, `run_logged`, pre-fix `finally` block.

Cleanup called `os.killpg` only while `proc.poll() is None`. If the process-group leader exits but an owned descendant retains the stdout/stderr pipes, the selector correctly reaches its deadline and raises; cleanup then sees the exited leader and skips terminating the surviving descendant.

An initial local subprocess probe observed `TimeoutError` plus a remaining process ID after cleanup. Process existence alone cannot distinguish a running process from a terminated zombie, so that first probe is retained as limited exploratory evidence rather than decisive activity proof. This host also virtualizes Python process IDs, making `/proc/<Popen.pid>` an unsuitable activity oracle. The owner then used a real child heartbeat, confirmed the group leader had exited before accelerating the deadline, and reconstructed the exact pre-fix runner bytes (SHA-256 `5a7527f8ef9aa45e4ed767551be974811a1711b7ac4eb550376e04bba7e49142`). Its heartbeat grew **6 → 12** after timeout, reproducing the defect (`research/provider-qualification/descendant-cleanup-red.log`). No provider, network socket or credential was involved.

Counterexample receipt: `/workspace/scratch/26b6d364cfda/enterprise-independent-provider-runner-counterexample.json`.

The repair unconditionally terminates the owned process group in `finally`, handles an already-absent group, performs the bounded wait, and closes both pipe handles before preserving logs. The final runner suite passes **9 tests**, with resource warnings promoted to errors in the owner's run. Independent post-fix verification used a separate real heartbeat probe: leader exit was confirmed, timeout occurred, and activity stayed **6 → 6** during a 0.3-second observation after cleanup. Receipt: `/workspace/scratch/26b6d364cfda/enterprise-independent-provider-runner-verification.json`. PR01 is closed for this cooperative source-lab process-group boundary; it is not a sandbox against arbitrary processes escaping their group.

## Verdict boundary

No blocking issue was found in the exact pinned Schema extraction or candidate-source fidelity. No blocking finding remains in this reviewed source-lab scope. E02 and the wider enterprise acceptance goal remain open regardless of this review's outcome. The independent CI review is a separate addendum and does not alter these boundaries. Final reviewed code/evidence hashes are in `/workspace/scratch/26b6d364cfda/enterprise-independent-provider-review-snapshot.json`. Earlier source-experiment receipts retain their actual historical runner hashes; the cleanup-only change must not be represented as a repeat of those Go experiments.
