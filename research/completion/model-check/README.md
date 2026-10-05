# Independent bounded approval/recovery model

Result: **PASS**. The intended model satisfies four safety invariants
within the stated bound; all four deliberately weakened models produce retained
counterexamples. This is a check of an authored abstraction, **not proof of the
Python implementation**.

Two writers, one immutable grant identity each, at most one crash/restart episode
per writer, and traces of at most 18 atomic transitions were explored by BFS
with complete-state deduplication. The intended run visited
**565 states** and examined
**878 transitions**;
**26 states** reached the depth boundary.

The model includes grant, lock, durable consume, dispatch start, external write,
verified readback, durable receipt, completion, crash, restart and explicit
reconciliation. It asserts lock exclusivity, at most one dispatch per grant, no
automatic retry after an uncertain outcome, and no success before readback and
receipt. Positive witnesses cover both writers completing, recovery completion
after a crash, and an uncertain no-effect attempt closing without replay.

| Deliberate weakening | Shortest counterexample length | Violated invariant(s) |
| --- | ---: | --- |
| nonexclusive_lock | 4 | lock_exclusivity |
| replay_consumed_grant | 10 | at_most_once_dispatch_per_grant |
| automatic_uncertain_retry | 7 | at_most_once_dispatch_per_grant, no_automatic_retry_after_uncertain_outcome |
| early_success | 5 | no_success_before_readback_and_receipt |

`results.json` retains exact shortest counterexample traces, final states,
transition coverage, positive witnesses and the checker source hash.

Assumptions: transitions and lock acquisition are atomic; durable records survive
crashes; authority is volatile; locks survive crashes; remote writes settle before
reconciliation; readback is accurate; no unmodeled external writer exists. The
one-crash and one-grant bounds, settled-effect assumption and absence of expiry,
network partitions, storage failures, fairness and liveness are deliberate limits.
No OS isolation, distributed-service guarantee, unbounded safety, or correspondence
between this state graph and production code is established.

Reproduce from the repository root:
`/workspace/scratch/e2e4042ea5fd/.venv/bin/python research/completion/model-check/model_check.py`.
The script uses only the Python standard library, imports no production code,
performs no native/cloud calls, and writes only this model-check directory.
