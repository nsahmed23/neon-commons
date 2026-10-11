# Minimal native receipt producer repair

Proposed public text for review. This changes exactly two source lines, one in
each external helper. The helpers are outside the unchanged C25 source/runtime
packages. It does not establish a native run result or global laboratory pass.

The repair serializes each ordered SQLite `broker_attempts` row as a JSON array.
Internal tuple assertions and the strict canonical helper remain unchanged.
The failed original run, partial outcomes and retained evidence remain valid
historical records. No successful receipt is relabeled or replaced.

The zero-context patch below requires exact before-file identities in the
paired source disposition. It is not a standalone replay or recovery bundle.
Full helpers, fixture keys, native profile, closed loader, reuse inputs and raw
capsules are deliberately excluded; they have no public clearance here.

Exact patch: 1,668 bytes, SHA-256 `626e5fc68cab04e8be288f96da71d021f9eb672e323d56362d162a584fb64c46`.

```diff
--- a/helpers/native_ordinary_qualification.py
+++ b/helpers/native_ordinary_qualification.py
@@ -181 +181 @@
-            receipt.update(status='PASS',classification='expected_partial_or_unknown_native_operation',actual_operation_status=outcome['status'],assertions=checks,injection=fired,broker_attempts=attempts)
+            receipt.update(status='PASS',classification='expected_partial_or_unknown_native_operation',actual_operation_status=outcome['status'],assertions=checks,injection=fired,broker_attempts=[list(row) for row in attempts])
--- a/helpers/native_ordinary_partial.py
+++ b/helpers/native_ordinary_partial.py
@@ -335 +335 @@
- receipt.update(status='PASS' if all(checks.values()) else 'FAIL',classification='expected_description_state_commit_outcome_unknown',assertions=checks,operation_id=job.identifier,manifest_sha256=digest(manifest),job_root=str(job_root),policy_path=str(trust_path),state_sha256=hashlib.sha256(state_raw).hexdigest(),injection=fired,broker_attempts=attempts,scope='Actual selected native worker and cancel CLI, receiving timing supplied by nonforwarding fixture; no native Windows/live service claim.')
+ receipt.update(status='PASS' if all(checks.values()) else 'FAIL',classification='expected_description_state_commit_outcome_unknown',assertions=checks,operation_id=job.identifier,manifest_sha256=digest(manifest),job_root=str(job_root),policy_path=str(trust_path),state_sha256=hashlib.sha256(state_raw).hexdigest(),injection=fired,broker_attempts=[list(row) for row in attempts],scope='Actual selected native worker and cancel CLI, receiving timing supplied by nonforwarding fixture; no native Windows/live service claim.')
```

Application remains an explicitly reviewed local preparation step with original
helper bytes preserved and a newly bound closed profile; native dispatch and
qualification require their separate authorization and evidence. Author
recommendation and independent public-text review remain pending.
