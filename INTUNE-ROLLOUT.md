# Evidence, cohort and promotion contract

Stages remain separate: object, assignment, cohort, endpoint receipt, workload execution, effective state, and outcome. Azure additionally separates ARM, data-plane and network verification. Every record carries a source/pointer, timestamp, coverage and synthetic flag. Schema validity is not evidence authenticity.

Resolve the latest valid record for each device/stage relative to as_of and the configured freshness window; preserve conflicting equal-time or contradictory observations as conflicting, not a chosen success. If clocks/retention/access are uncertain, downgrade coverage. The supplied reducer accepts already reconciled one-row-per-device statuses; a production stage reconciler is an implementation task, not hidden inside arithmetic.

Eligible, targeted, excluded and reporting sets must be explicit, unique and coherent. Report successful/failed/pending/unknown using the target denominator and also show reporter denominator. Never count offline/stale/nonreporting as success. Unknown future cohort membership invalidates review or demands an explicitly approved membership policy. Organization thresholds stay null until supplied; helper returns promotion_proven=false rather than inventing 95%/99% rules.

Policy/app waves are not Windows Update rings. Reverting assignments/deleting a policy is not universal endpoint rollback. Specify setting-specific compensation, downstream evidence and recovery owner. An accepted API request does not imply device receipt or effectiveness.
