# State-only update is a code-path fact, not an action-count heuristic

The pinned Microsoft provider v0.5.0 commit 058dd7651d92d741d48e868d815826edec669229 contains `MSGraphResource.Update` in internal/services/msgraph_resource.go. The branch whose URL ends in /$ref sets output/state and returns before the remote update code. PR148 added the import regression test expecting update rather than replacement. See source record msgraph-ref-update and https://github.com/microsoft/terraform-provider-msgraph/pull/148 .

This supports a narrow source-level state-only classification for that Update branch. It does not prove every operation in a whole plan is non-mutating, prove a particular runtime reached that branch, or establish Intune assignment semantics. The typed Settings Catalog provider uses its separate PUT/assign sequence and has no equivalent blanket exception here.

Plan fixtures under evaluations/plans are synthetic fragments. `classify_plan` is advisory and accepts a caller-supplied source-contract label; it is not an execution gate. Before using the label, a future verifier must match pinned binary/provider schema, resource type, resolved URL and exact planned change and observe qualified effects. Do not treat an untrusted label as authorization. A no-op plan also does not establish downstream endpoint outcome.
