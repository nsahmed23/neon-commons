# Fresh Graph mutation preconditions

`intune_iac.worker_precondition` connects the existing authenticated read-only Graph reader to the protected worker. It adds no write permission and does not make a read followed by a write atomic. The supported comparison profile is Windows 10/MDM Settings Catalog with complete policy, settings and assignments captures. Device effectiveness remains separate.

The live factory requires an exact process-held `LiveGraphReader` and sealed `CapturedObservation`; the laboratory factory requires `LaboratoryGraphReader`. JSON, a callback, a saved receipt or a lab capability cannot construct live authority. Bind `gate.binding()` into the worker's signed execution manifest. The binding includes tenant, reader principal, object, independent identity observation, initial capture, exact approved request-body digests, versioned semantics and execution-binding digest. It is not itself approval.

```python
gate = create_live_precondition(
    reader=reader, preimage=preimage,
    execution_binding_sha256=execution_binding_sha256,
    approved_policy_body=exact_put_bytes,
    approved_assignment_body=exact_assign_bytes,
    evidence_root=new_private_directory)
stage = gate.stage_for_request(method, path, decoded_request_bytes)
gate.check_before_mutation(stage=stage, request_body=decoded_request_bytes)
# The protected broker forwards only its separately admitted exact request.
# After both mutation stages, before completing native state:
completed = gate.capture_completed()
```

The broker must enforce its independent approval, host, identity, lease and uncertain-write controls. Closing a terminal does not create or reconstruct this capability. A restarted worker needs independently re-established reader and operation authority; receipts do not supply them.

1. Immediately before the policy PUT, fresh complete reads must match the captured preimage.
2. Immediately before assignment POST, reads must match the admitted policy/settings result and the unchanged original assignments. Only actual observed `lastModifiedDateTime` and the setting count may differ as computed fields; timestamps cannot regress or be in the future.
3. `capture_completed()` reads again and returns the actual sealed capture only when policy/settings and exact unique desired targets match. Existing target metadata remains exact except for independently observed service assignment IDs. New targets require known direct-assignment metadata; unsupported unknown metadata fails closed. This does not prove that the worker performed a mutation, an endpoint processed it, or a device became effective.

`semantics()` exposes version `worker-graph-lossless-semantics/1`: raw bytes and original order remain in private captures; scope tags are a unique string set, settings and initial assignments are keyed by exact IDs, choice-value children are keyed by setting definition ID, and all other arrays remain ordered. Unknown fields, numeric versus string values, null, absence and empty values remain distinct. The comparison uses the full raw capture, not the older provider mapping normalizer, so it does not erase nonordinal setting IDs or unmapped fields. It does not widen provider management coverage.

Every phase writes a started attempt before the read, then a matched or failed outcome. Partial, denied, cancelled, stale, out-of-scope and substituted captures cannot satisfy a phase. A failed phase cannot retry silently. Concurrent calls cannot execute one phase twice. Capabilities reject process changes, serialization, expiration and changed projection/capture bytes. The private host and Python process are a cooperative trust boundary, not protection from their owner.

`gate.completion()` performs a fresh desired readback and returns an exact `LiveGraphCompletion` or `LaboratoryGraphCompletion`. Its `verified()` method returns the execution binding, precondition binding hash, approved projection hash, capture hash, identity and the actual sealed capture under `capture`. This ties parity to evidence instead of accepting a raw successful capture or JSON label. Repeated completion is read-only, stores a new numbered capture directory and never repeats mutation phases. It expires with the reader and fresh-capture time limit. A failed reobservation invalidates completion authority.

Graph collection reads are not a transactional snapshot; neither the collection sequence nor the later write is atomic. No `If-Match` guarantee, tenant writer fence, endpoint assertion or organizational approval is invented. A real authorized service run, native protected worker integration and independent security review remain required.

## Verification and preserved attempts

From the source root:

```sh
python -m unittest plugin_tests.test_worker_precondition_r4 -v
PYTHONPATH=. python /workspace/intune-continuation/work/evidence/epoch-20261007-r4/worker-precondition/qualify.py NEW_PRIVATE_OUTPUT_DIRECTORY
```

The final focused run is 27/27 local recorded-response tests in `work/evidence/epoch-20261007-r4/worker-precondition/tests-05.txt`. The persisted connected journey has 12 independent literal assertions and 22 actual reader-interface HTTP requests against a nonforwarding in-process response fixture, with all raw captures retained in `connected-01/`. The journey overlaps the unit scope and is not added to its test count. None is authenticated tenant, native provider, backend or device qualification.

`tests-01.txt` retains the initial identity binding failure caused by a tuple/list representation mismatch between reader and sealed capture. Exact canonical identity comparison repaired it. `tests-02.txt` retains five incorrect fixture request-count assumptions: the real fixture has three assignment pages, five collection requests per capture. The assertions were corrected to match independently inspected requests, without reducing required collection coverage. `tests-03.txt` preserves the 22-test intermediate pass; `tests-04.txt` adds the unknown-assignment-metadata and inherited-assignment negative checks. `tests-05.txt` adds sealed desired-completion and read-only recovery checks. The separate provider malformed-error repair lane remains stopped and unresolved; these results do not close it.
