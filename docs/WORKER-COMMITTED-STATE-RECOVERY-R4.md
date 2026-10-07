# Recovery after the original approved state has committed

This is a separate bounded recovery contract for an interrupted original computed-state write. The original-state-only lease profile remains unchanged and rejects an advanced revision. An arbitrary freshly observed state or a successful-looking provider log is not sufficient.

## Proof and authority

`worker_committed_state` provides exact live/laboratory observer capabilities. They require the original real stopped `ServiceJob`, an actual typed independent Graph reader, and original hash-bound raw preimage, policy body, assignment body, baseline state, saved native plan and plan JSON. Historical files remain historical inputs; only the new typed reader capture establishes current Graph state.

The closed original contract must be `computed-native-state-write-contract/1.0`, with exactly the existing `settings_count` and `last_modified_date_time` computed fields. The original journal must contain exactly one state-write attempt. The fresh state must have original lineage and exactly original serial+1. Its computed count and timestamp must match a new complete independent desired policy/settings/assignments capture, using the original lossless semantics and assignment metadata rules.

Replacing only those two computed values with the original observation-bound placeholders must produce the **original signed `admission_template_sha256`**. Every other configured value, private provider state, resource identity, schema, outputs and checks is therefore bound to the original approved projection. This proves equality, not the identity of the actor responsible for the state. Management mapping blockers and laboratory provenance remain visible.

`worker_committed_recovery` then requires this exact observer inside a distinct `LiveCommittedRecoveryContext` or `LaboratoryCommittedRecoveryContext`. A new recovery observation reauthenticates the original backend target/principal and reads the original active lease UUID and Apply metadata. It captures Graph independently again. A separate reviewed manifest binds the exact state bytes, ETag, UUID, desired raw Graph digest and original approved projection.

The signature domain is `intune-workbench:committed-state-lease-recovery-approval:v1` followed by NUL. The schema/action/profile are distinct from original-state recovery. The new action is `release_exact_original_committed_state_lease`; the laboratory profile is `laboratory_committed_state_lease_recovery`. `CommittedRecoveryPolicy` admits only exact new manifest hashes and explicitly allowed keys/profiles.

Both release profiles consume the **same original common authority table**, keyed by original operation. A new domain, nonce, policy or state context cannot authorize a second release. The controller records consumption before one empty exact native `PUT ?comp=lease`, action `release`, original UUID and reviewed `If-Match`. There is no lease break/acquire, metadata clearing, state write or Graph mutation. Lost response remains unknown and spent. Original ownership stays reserved.

## Entrypoints

1. `worker_committed_state.laboratory_observer(...)` or `live_observer(...)` constructs the typed proof reader from the real job/reader and exact original bytes.
2. `worker_committed_recovery.laboratory_context(..., observer=...)` or `live_context(...)` constructs the separate context with the independently authenticated current state revision.
3. `context.observe(NEW_PRIVATE_DIRECTORY)` obtains a fresh state-and-Graph proof.
4. `prepare(observation, operation_id=NEW_UUID, expires_at=...)` creates review material. `CommittedRecoveryPolicy` and a new independent signature are required by `execute(...)`.
5. `observe_uncertain(...)` is a read-only investigation after an uncertain release; it cannot repeat the request.
6. `completion(...)` produces exact `LiveCommittedRecoveryCompletion` or `LaboratoryCommittedRecoveryCompletion` after independently observed unlocked state. `captured_observation()` verifies and returns its held fresh Graph capture for the separate final service readback/reconciliation route. It is not JSON rehydration or ownership-transfer authority.

Read-only completion records historical/current ETags and leaves any change attribution unestablished while requiring the exact state content. Mutation prewrite still requires the exact reviewed ETag. Metadata is preserved and backend readiness is not inferred from release alone.

## Qualification and remaining gates

The staged observer passed 25 independent assertions and 35 fresh local TLS requests in `worker-provider/committed-state-observer-01/receipt.json`, using the retained actual native state14 interruption. Substituted old plan/preimage/body, serial15, lineage/private/resource/settings changes, boolean counts, changed Graph IDs/filters/description and denied assignment coverage were rejected. Receiving-fixture fault resets were explicit; no state, lease or Graph write occurred.

The bounded source review found no new authority bypass; it is not an organizational AppSec approval. Final integrated signed-release/readback qualification must be recorded separately against the exact final source. Local receiving-service responses do not qualify real Azure conditional GET, lease-ID, `If-Match`, release, interruption or service-freshness behavior. No production release, tenant mutation or organizational production approval is authorized by these modules or their laboratory results.
