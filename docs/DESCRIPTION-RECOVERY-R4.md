# Bounded partial-commit recovery state admission

This is a separate bounded development profile, locally qualified against exact native refresh-plan bytes and independent sealed observations. The ordinary update profile continues to reject all resource drift. Protected native recovery application and its final state require their own evidence; construction and unit tests do not establish completion.

The retained assignment-failure fixture contains persisted state serial 13, original description `Fixture only`, and independently observed Graph description `Fixture intentionally corrected`. Only the policy PUT succeeded; assignment POST returned a conformant 403. Graph settings, targeting, immutable identity, and scope tags stayed exact. The backend state did not advance. The failed operation, held lease, metadata, and scope reservation remain evidence; a new successful operation must not rewrite that history.

## Dependency sequence

1. Independently inspect the stopped worker, original broker journal, exact backend identity, current state bytes/ETag, lease and Terraform lock metadata.
2. Prepare and separately sign the exceptional exact-lease recovery operation. Never reuse original apply approval. Clear recorded stale metadata only through a separately authorized typed action if required. Preserve the original operation's uncertain result and ownership until explicit successor/reconciliation authority exists.
3. Prepare a fresh native Atmos/OpenTofu plan against the actual recovered backend, without repeating import and without disabling locking. Retain binary plan and exported JSON. A new plan is reviewed and signed before any new apply.
4. Compare three distinct values: original persisted state, provider-refreshed prior state in the new plan, and fresh sealed independent Graph capture. The sealed capture must explain the provider refresh exactly; no refresh-only apply makes the old repository intent accepted.
5. For this narrow profile, admit one existing Settings Catalog object and a description-only desired correction. Drift may alter only description and the observed last-modified timestamp. Reject changed IDs, settings, types, null semantics, assignments/exclusions/filters, scope tags, provider identity, additional resources, address moves, import/delete/create, outputs, deferred changes and unknown fields beyond the two already admitted computed attributes.
6. Preserve persisted state lineage/serial increment, resource metadata, private data, sensitivity and identity. The expected final state is derived from the original persisted state, replacing only exact approved attributes and explicitly projected native check results. The contract binds both original and refreshed digests, original drift entry and original plan bytes; it never erases the drift evidence.
7. Drive existing preconditions before policy/assignment writes and require independently verified desired completion. Only settings count and last-modified timestamp come from that final sealed capture. Read-to-write races remain explicit.
8. Reconcile the NEW operation with independent Graph and backend readback and a no-change second native plan. Keep the original failed operation and its recovery link visible.

## Projection version

`settings-catalog-description-recovery/1` is intentionally bounded to the pinned provider's complete observed attribute schema. Policy scalar fields map exactly; platform is windows10 and technology is mdm. Settings JSON is parsed and compared losslessly, including all IDs, unknown fields, order, types, null and absent. Scope tags are unique typed string sets. Provider assignment rows correspond to exact unique Graph targets; supported direct group include/exclusion targets retain group ID, filter ID/type. Extra fields in target or provider assignment reject. Assignment response metadata and raw captures remain preserved by the existing precondition even where the provider state does not contain them.

This projection is not a new claim that the existing management adapter supports setting ID 37 or all assignment metadata. Those mapping blockers remain visible. Other provider refresh drift remains unsupported. No normalizer, state push, lease break, arbitrary unknowns or force-unlock is introduced.

## Required independent negative controls

Wrong object/identity; mismatched persisted-before; drift after versus resource-change before; plan prior-state mismatch; non-description drift; changed settings IDs/type/order/null; changed target filters/exclusions/group; duplicate assignments/tags; forged/unsealed/stale/incomplete capture; new resource/module/address; unexpected computed field; altered private/sensitive/identity/lineage/serial; state body not matching approved after; approval replay; uncertain release; reappearing worker; stale metadata or lease mismatch.

Timestamp projection follows the already qualified pinned provider's Go `time.RFC3339` rendering: preserve timezone offset, omit fractional seconds, render UTC as `Z`. Raw capture timestamps and bytes are retained unchanged. The stored/provider-refreshed timestamp must equal this rendering, be nonregressing from persisted state and no more than 60 seconds ahead of the reader's clock; fractional or otherwise unsupported native representations fail this bounded profile. This is a versioned projection, not a claim of service-side atomicity.

The source test route is `python -B -m unittest -v plugin_tests.test_worker_state_recovery_r4`. It currently contains 24 focused cases and literal synthetic native fixtures under `labs/worker-recovery/description-native-fixture`; fixture manifests identify all bytes and the separately retained private binary plan. No real service data or credentials are included.
