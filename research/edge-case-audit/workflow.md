# Workflow, execution, reconciliation, and evaluation edge audit

Scope: current guided workflow, local two-facet execution and independent reconciliation, judge adapter and evaluation receipts. No cloud, model inference, paid benchmark, native host installation, or service behavior experiment ran.

## Reproduced findings and repairs

**W01 — replacement session lock deleted by previous owner.** During a live guided input prompt, remove its lock and create another owner's lock at the same path. The old invocation previously saved and unconditionally unlinked the replacement in its `finally` clause. The independent invariant is that a session may neither continue authoring after detecting lost ownership nor remove another operation's lock. Normal save is the positive control.

Repair: fresh unpredictable owner token, device/inode and content checks; checks following user input, before checkpoint receipts, generation dispatch and final persistence; cleanup only when the lock still matches this invocation. Additional regressions cover in-place owner alteration, replacement immediately before `generate`, and replacement with a symlink. This is cooperative filesystem locking. The check and filesystem mutation are not atomic against an adversarial process with equivalent filesystem privileges; no hostile race-proof claim is made.

**W02 — malformed persisted state crashes instead of blocking.** Replace valid saved_state with JSON array `["object_selection"]`. Membership lookup in a dictionary raised uncaught TypeError. The invariant is a structured blocked result, no output creation, and no external authority for malformed local persistence. Repair checks string type before lookup.

Initial correct-environment receipt: `workflow-red.txt`, 5 tests, 3 passes and 2 assertion failures, zero harness errors. A preliminary invocation using system Python lacked jsonschema and produced three environment errors; that invocation is not defect evidence. Qualified interpreter is `/workspace/scratch/26b6d364cfda/plugin-clean-venv/bin/python`.

Final scoped receipt: `workflow-green.txt`, 37 tests, zero failures/errors/skips (8 new edge test methods, 23 existing guided workflow methods, 6 enterprise CLI methods). There are six independently injected journal-write subcases within one edge method; do not describe those as six extra test methods.

## Failure-boundary coverage added

For each of six journal event writes, injected OSError before persistence. Independent expected current facets follow the documented local operation order, not journal interpretation:

| Receipt boundary | Expected reconciliation |
| --- | --- |
| prepared | unknown (no complete preparation evidence) |
| policy step_started | matches_precondition |
| policy step_verified | partial_effects_observed |
| assignments step_started | partial_effects_observed |
| assignments step_verified | desired_state_observed |
| completed | desired_state_observed |

Every case retains its lock, returns reconciliation_required, refuses replay, leaves observed facets unchanged on the refused replay, and never grants retry or unlock authority. Completed positive control writes both desired facets and removes its own lock. These are local disk-failure simulations, not Intune transaction or service retry guarantees.

## Eval interpretation and missing qualification

- Root separately owns repair of verifier empty-suite, skipped, expected-failure and subtest accounting. Passing unittest semantics alone are insufficient as a production gate; check denominator, selected scope and receipt counters.
- Existing judge tests exercise HTTP protocol with synthetic probabilities and synthetic encoder/head files. Those establish serialization/validation/abstention boundaries, not learned-model precision, calibration, prompt-injection resistance or production latency.
- The judge exposes advisory_only=true and execution_authorized=false, and the action path accepts only the shipped concrete LocalFixtureAdapter. No judge verdict should ever substitute for target identity, required receipts, approval or provider qualification.
- Softmax probabilities are candidate-relative. Evaluate held-out supported/contradicted/insufficient evidence sets, including incomplete evidence with confident-looking prose, mixed supported and unsupported conjuncts, conflicting sources, reordered distractors, source instructions/prompt injection, paraphrases, missing policy/assignment relationships and service-vs-local scope confusion. Independently label expected decisions before running the model.
- Evaluate selective risk at each acceptance threshold and report abstention coverage, false-support rate, uncertainty intervals, worst-case slice performance and per-model identity. Include changed threshold settings as separate runs even where source evidence/configuration hashes otherwise match.
- Measure cold and warm latency and timeout/failure behavior separately; report hardware/concurrency, encoder/head/tokenizer identity and evidence sizes. Alias equality does not authenticate server weights.
- Native-host benchmark fixtures remain proposed harness inputs. Structural fixture validation, static Plugin Eval scoring, unit tests, and actual agent task performance are distinct measurements. Do not aggregate them into a single pass rate or call static score a behavioral benchmark.
- Mutation tests must mutate independent evidence/behavioral invariants, not merely update fixtures to match new algorithms. Important remaining controlled qualifications: kill-process/power-loss filesystem durability, concurrent actual processes, Windows ACL/PowerShell behavior, cloud partial policy/assignment updates and remote readback consistency. Their absence remains visible.

No finite suite proves that all edge cases are covered. This increment expands concrete failure boundaries and preserves explicit unqualified categories.
