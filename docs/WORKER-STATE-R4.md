# Computed native state admission — R4

`ComputedNativeStateWriteContract` completes one existing root Settings Catalog
resource's `settings_count` and `last_modified_date_time` from an independently
verified desired Graph completion. It is a content contract, never approval or a
state lock. The original fully known `NativeStateWriteContract` is unchanged.

The constructor binds exact baseline bytes, saved-plan JSON/binary identity,
execution binding, preimage and sealed precondition binding. The bounded profile
requires OpenTofu 1.13.1/state schema4, one existing update, identical immutable
resource/provider/schema/identity/private metadata, no outputs, no drift,
imports, moves, modules, indexed resources or other computed fields. Native
simple variable-check results must be passing and exactly bound to the plan.
The new serial is exactly baseline+1 and the lineage cannot change.

Only an exact `LiveGraphCompletion` or `LaboratoryGraphCompletion` with the same
precondition binding may complete the projection. Arbitrary JSON, a raw recent
capture or a boolean callback cannot substitute for desired-state verification.
The sealed precondition compares all raw fields and admitted policy/settings/
assignment projections before issuing the completion. Count must equal the
complete setting collection. Time uses the pinned provider's Go `time.RFC3339`
conversion, retaining the observed timezone and omitting fractional seconds.
Every other candidate field must equal its exact approved projection.

Collection completeness is distinct from management mapping. A complete raw
capture can remain `unsupported` in Workbench's normalized view. Its status and
all mapping blockers are preserved in both contract and admission; they are
never converted to complete or production-qualified. This permits exact raw
state serialization checks without claiming implementation of unsupported
Workbench mappings. State admission does not settle references, ownership,
provider/service/device qualification or organizational approval.

API:

```python
contract = ComputedNativeStateWriteContract(
    baseline_raw=baseline, plan_json_raw=plan_json,
    saved_plan_sha256=saved_plan_sha256,
    execution_binding_sha256=execution_binding_sha256,
    preimage=preimage, precondition=precondition)
route["state_contract_sha256"] = digest(contract.binding())
route["body_sha256"] = contract.binding()["admission_template_sha256"]
# Broker invokes this after its native Apply-lease and bearer checks:
admission = contract.admit(candidate, completion=precondition.completion())
```

`admission_template_sha256` is a template identity, not a claimed final byte
hash. The receipt separately records the exact admitted candidate byte hash.
The broker journal binds those actual bytes before forwarding. The protected
service must independently GET current Blob state and Graph after execution;
returning from a provider process or admitting a state request is not that proof.

Replay: `python3 -B -m unittest plugin_tests.test_worker_state_r4 -v`.

Retained real native before/plan/after bytes are checked without rerunning the
provider by `work/evidence/epoch-20261007-r4/worker-broker/state-admission/qualify_retained_native_state.py NEW_OUTPUT`.
`native-admit-01` preserves the initial mistaken raw/normalized-completeness
coupling; `native-admit-02/receipt.json` records the corrected separate assertions
and still-visible unsupported mapping. All observation responses in that replay
are local recorded fixtures, not real Graph or Azure evidence.


The exact computed-state adapter subsequently ran in the connected signed native
service journey03: the real pinned provider generated the candidate, this broker
required independent sealed desired Graph completion, the local Azure-protocol
fixture received PUT201, and independent Blob readback confirmed the exact
state before reconciliation. The same receipt preserves unsupported mapping and
sets platform_qualified/production_approved false. This is stronger local
integration evidence than the retained-byte replay; it still is not real service
authentication or device evidence.
