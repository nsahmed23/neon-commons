# Provider and service qualification: proposed, NOT executed

## Pinned target and boundary

Keep `deploymenttheory/microsoft365` 1.0.0 at `1718c946b3ae111bb44c7c1d925b3e35b708cb0a`, OpenTofu1.10.0 and Atmos1.199.0. Provider source go.mod selects Go1.25.8, beta SDK0.165.0 and Kiota JSON writer1.1.4. Source review does not establish binary distribution compatibility or enterprise approval. No dependency upgrade is part of this correction.

### Gate P0 — acquire and inspect the remaining small closure

The validator path is now resolved in source record P01. Verify any newly acquired raw bytes against returned Git blob IDs and compute separate SHA256. Acquire resource/assignment schema, constructors, shared typed models/JSON tags, modifiers, state mapping, custom settings GET helper, SDK assignment request builder, Entity model and Kiota writer. Follow only selected simple/choice branches and referenced helpers first. Inspect constructors for logged sensitive input, nil/error handling and silently omitted unsupported values. Preserve applicable source notices; this dossier redistributes no upstream implementation.

The read caller's `.Get().GetValue()` is evidence of one returned page at that point, not proof the SDK transparently traverses all pages. Locate actual nextLink loops or establish their absence in the complete selected call path. Do not replace that investigation with broad documentation about Graph pagination.

### Gate P1 — offline pinned-provider validation/serialization

Requires separate availability/approval for the exact binaries/dependencies and an isolated test environment; not run here. Inspect setup for module downloads/toolchain auto-downloads, credential inheritance and hidden live tests before running. No live network fallback or provider authentication.

Call the actual pinned SettingsCatalogJSONValidator on (a) the old golden, (b) the corrected configuration, (c) missing IDs, extra wrapper discriminator, nonsequential IDs, empty records, wrong value/children types, template references, invalid GUID/filter cases and description boundaries. Check actual diagnostics; our local schemas are not a reimplementation proof of all provider behavior.

Then exercise the actual constructor and SDK writer against a recording transport. Observe: wrapper ID copied or omitted; default Entity discriminator; exact null/absent template forms; empty choice children; integer/string fidelity; order; supplied sibling retention; unsupported-field handling; assignment null/empty behavior; and logged artifacts. Keep provider-config expected JSON distinct from wire expected JSON.

Feed recorded synthetic read responses through the actual state mapper, including wrapper @odata.type, service IDs, omitted/null fields, malformed response, reordered fields and arrays. Compare semantic intent and exact provider state separately. Explicitly test the read-error path that returns old settings: a retained state string must not be reported as fresh evidence. Test both config attribute modifier and resource ModifyPlan. The latter is a placeholder in the reviewed file.

No-op acceptance requires independent observed provider refresh/plan behavior. A local source-equivalence check, provider validator pass, or source comment is insufficient. An actual provider process against a fixture transport is stronger than our Python contract model but remains distinct from live service evidence.

## Unsettled service questions

| Question | Current evidence | Needed discriminator |
|---|---|---|
| Does assign replace or merge? | A distinct assign action and outgoing assignments array; no verified replacement/merge contract retrieved here. | Supported service documentation or controlled disjoint/subset read-back experiment. |
| Omitted vs explicit empty assignments? | Pinned constructor sends empty for null/unknown; caller sends assign after policy update. | Service read-back for separate omitted/empty cases; never probe with production targeting. |
| All assignment/settings pages read? | One response is consumed by the inspected caller; helper/SDK traversal not fully closed. | Complete source path plus mock multiple-page response assertions; later large lab policy if needed. |
| Filter defaults and empty values? | Explicit schema/default and constructor branching; read normalization needs full mapping. | Complete tuple roundtrip, explicit none/include/exclude/default cases. |
| Atomic update/retry safety? | Separate policy and assignment operations; no demonstrated transaction. | Fault injection between operations and explicit reconciliation behavior. |
| No unintended change on import? | Import ID shape and source transforms inspected. | Baseline service snapshot, authorized import, fresh provider plan plus independent cloud read-back. |

Attempts to open the official assign/list pages did not yield usable content, and the resource-page action link resolved to a failing relative URL. This is a retrieval gap, not evidence that the operation is absent or broken. The historical Microsoft msgraph `$ref` fix concerns another provider and operation; do not use it as an oracle here.

## Gate P2 — disposable-policy experiment (requires new authorization)

Use an isolated test tenant and disposable policy; never select a real fleet policy. Use preapproved empty security groups A, B and E, an approved filter F, and no all-device/all-user targets. Group membership must be independently confirmed empty, with no dynamic membership that can unexpectedly enroll devices. Define a resource-ID allowlist, operator, time/budget, recovery owner, limited principal and evidence location. Broad Graph application scopes may not enforce this object boundary: add an independent request allowlist/controlled runner and record the residual limitation.

Capture all policy/settings/assignment pages using the trusted boundary, baseline digests and reference IDs. Save raw originals only in the restricted store. Establish requests complete before writing. Create test-policy clones separately for cases below; do not run cases serially against the same evolving fixture unless explicitly designed.

Case A: baseline assignments {include A, include B with filter F, exclude E}; submit a documented assign request containing only include A. Read back every page with bounded consistency polling. Result {A} supports replacement for this API/context; {A,BF,E} supports merge for this context; any other result is discrepancy, not an inferred pass. Restore/reconcile according to the approved operator plan.

Case B: start from the same baseline on a different clone; submit an explicitly empty set. Observe whether the service clears, rejects or preserves. Case C: omit the assignments property in an independently approved request; observe separately. Never equate the outcomes or infer intended semantics from HTTP200.

Case D: begin from full complete targeting, apply a settings-only provider update through the approved lab workflow. Observe whether the provider still issues assign and whether all references survive. Record request bodies/effects, not merely plan counts. Filter none/include/exclude and scope metadata need independent equality checks.

Case E: inject a synthetic transport failure after policy PUT but before assignment POST in an offline transport first. For a separately approved live ambiguity test, reconcile current policy/settings/assignment state before any retry. Do not automatically replay POST or blindly roll state backwards. Preserve partial-update evidence and distinguish policy success from assignment failure.

Case F: authorized import of a clone followed by provider refresh and plan. Compare source IDs, desired settings/assignments, actual provider request trace and current complete service read-back. State-only reconciliation, no remote write, real update and replacement are different outcomes. Do not claim no-change adoption from an action label alone.

Abort immediately on wrong cloud/tenant/policy ID, unexpected group membership, out-of-allowlist request, lost exclusion/filter, collection capture gap, secret exposure, unbounded retries, unexplained replacement, or disagreement between provider and service evidence. Stop mutation, retain evidence, and hand off to the recovery owner. Cleanup of disposable resources is an explicit authorized operator action, not implicit test teardown on arbitrary objects. Existing source policies are never cleanup targets.

Return a receipt per case: source/API/binary versions, target and principal, capture window, pre-state, actual request trace, independently observed post-state, assertion results, pending/unknown/error, and recovery disposition. Any unresolved ambiguity keeps G02/G05 partial.
