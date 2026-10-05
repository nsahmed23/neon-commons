# Independent enterprise implementation review

Review status: **complete — pass for the stated bounded local scope, after repair of IR01**. Scope is the bounded local implementation added after baseline `3fbfae8`, not acceptance of the enterprise production goal. No code edits were made by this reviewer.

## Specification verdict

The new architecture preserves the intended authority boundary: supplied target evidence is consistency evidence; three fixed service reads are explicitly partial observations; plan review cannot authorize execution; the sole execution adapter writes disposable local fixtures; reconciliation never replays or unlocks; guided milestones establish current local consistency rather than live adoption. The broader E01–E10 production goal correctly remains open.

One reproduced correctness finding in plan review was repaired and independently rechecked. No blocking finding remains in the inspected scope. The goal, implementation plan, runtime modules, tests and supporting evidence were read directly. The full suite was not repeated, because root already has integrated test evidence and there was no reason to duplicate it.

## IR01 — P2, repaired: prior-state effects could disappear from the plan denominator

Location: `intune_iac/execution.py`, `review_plan` and `_review_planned_values` in the pre-fix snapshot.

The reviewer cross-checks `resource_changes` against `planned_values`, but validates `prior_state` only as an object. Removing an existing resource from both after-side collections leaves a contradictory before-side resource invisible and can still produce `status: no_change` with no blockers. This does not authorize a cloud action, but it defeats the advertised conservative offline effect review and could mislead an operator about missing change/deletion evidence.

Reproduced with a real OpenTofu 1.10.0 show-JSON fixture already shipped in the research corpus:

```python
import json
from pathlib import Path
from intune_iac.execution import review_plan

plan = json.loads(Path(
    'research/enterprise-execution/native-plans/adopt-no-change.json'
).read_text())
removed = plan['resource_changes'].pop(0)['address']
plan['planned_values']['root_module']['resources'] = [
    row for row in plan['planned_values']['root_module']['resources']
    if row['address'] != removed
]
result = review_plan(plan)
print(removed, result['status'], result['blockers'])
```

Observed result: `terraform_data.policy no_change []`. The unchanged prior-state resource list still contains `terraform_data.policy` and `terraform_data.targeting`.

Required correction: validate the supported prior-state shape/version and the before-side resource/output denominator; compare known `before` values without conflating Boolean and numeric JSON values. Qualify special import/data/deposed/move cases explicitly, or conservatively block them. Preserve the real no-change fixtures as controls. The execution owner reproduced four failing tests in `research/enterprise-execution/red-prior-state.txt` and implemented the repair. Independent post-fix verification passed eight checks: the four real native plan controls retain their expected statuses; missing prior resources, missing prior outputs, contradictory prior values and omitted prior state now block. The independent receipt is `/workspace/scratch/26b6d364cfda/enterprise-independent-prior-state-verification.json`. The fixed reviewer uses named header/resource/output/prior-state/completion responsibilities; no further blocking finding was found in that decomposition.

## Quality observations

- The versioned APIs and fixed, redacted result shapes make authority and error behavior inspectable. Target comparison snapshots caller data; runtime collection never accepts arbitrary origins or uses token claims as authentication.
- Operation journals record intent before effects, bind exact local definitions, reread both facets, and retain target locks on uncertain outcomes. Reconciliation reports current observations without inventing historical causality.
- Guided reconstruction compares regenerated payloads and complete prior-receipt hashes, caps progress at the saved frontier, and independently verifies generated artifacts. Unknown outcomes prevent replay. Cohort intent remains separate from assignment membership.
- The graph input/work budgets, indexed edge de-duplication, restricted scalar/container hash suppression, independent oracle update, and private new-project creation modes address concrete behavior rather than merely adding a schema or documentation assertion.
- Dependency verification checks the exact bounded wheel inventory, byte hashes, metadata and archive paths. It correctly does not claim publisher authentication or a vulnerability assessment.
- Final graph validation now has a closed predicate/cardinality contract and named validation responsibilities; queries use six fixed handlers. Direct source comparison found no lost type, status, unknown, origin, fingerprint or assignment/filter condition. The before/after characterization files match exactly across 918 cases over six graphs, digest `3aebc98f7682122cd9626d922db303aece70717038d0b817b8a8fe4a62d16df2`. The implementer's additional rehashed adversarial differential receipt was also read: all 5,013 bounded cases match the pre-refactor acceptance or rejection behavior (`research/enterprise-quality/graph-differential.json`). This reviewer separately exercised four recomputed-digest mutations: false derived status, wrong endpoint type, missing setting-definition edge and missing effective provenance. All four were rejected. Receipt: `/workspace/scratch/26b6d364cfda/enterprise-independent-graph-verification.json`.
- The final legacy wizard controller preserves the lock-held state loop, revalidation before generation/handoff, invalidation, conflicts, interruption and guided delegation. Its fixed dispatch tables and named handlers make those responsibilities easier to inspect. The 54-test scoped result and 264-case saved-session differential harness/result were read; every saved-session comparison matched. These are bounded verification results, not exhaustive behavioral equivalence. `research/enterprise-quality/WIZARD-REFACTOR.md` records the additional actual PTY/repository journeys and measured complexity.
- The three new MCP tools expose only local plan review and target inspection/comparison. They cannot call the network collector or fixture executor. Arguments still pass the closed schema and bounded JSON loader; invalid/mismatched target results are marked as tool errors. No new authority path was found.
- The final wheel verifier decomposition retains lock, exact inventory, byte integrity, safe archive paths and metadata checks. Its small orchestration function delegates to named validators without replacing the checks with a score.

## Final verdicts

**Specification:** pass for the explicitly bounded local interfaces and claims reviewed here. All target, wizard, plan and simulation output continues to distinguish local consistency from authentication or execution authority. This does not mean Tasks 2–4 or enterprise gates E03–E06 are fully closed.

**Code quality:** pass for this change scope after IR01 was repaired. The graph, legacy wizard, plan reviewer and dependency verifier now have named responsibilities that can be reviewed separately. Remaining production qualification and broader maintainability work must stay visible; reduced cyclomatic complexity is not proof of correctness or readiness.

Exact reviewed file hashes are in `/workspace/scratch/26b6d364cfda/enterprise-independent-review-snapshot.json`. Root owns final integrated tests, packaging and clean-extraction verification. No implementation files or tests were edited by this reviewer.

## Documentation integration

The first read found stale `production-1.1.0` / per-node-value-hash wording in `docs/PRODUCTION-MAPPING.md`. A later direct reread confirmed the revised version and restricted/container null-hash wording, including the remaining whole-source-hash confidentiality limit. This is resolved and is not counted as a separate open implementation defect.

## Evidence limits

No tenant calls, native provider operations, cloud changes, host installation, paid model execution or organization approval were performed by this reviewer. A clean local code review does not close the declared enterprise acceptance gates. This report reviews code and bounded evidence; it is not a production release decision.
