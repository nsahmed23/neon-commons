#!/usr/bin/env python3
"""Independent finite approval/recovery model. Imports no product code.

Atomic transitions model a durable lock, one immutable grant identity per writer,
durable consumption and journal records, volatile in-process authority, and an
observable shared external value. This is not a proof of the Python runtime.
"""
from collections import Counter, deque
from dataclasses import dataclass, replace
from hashlib import sha256
import json
from pathlib import Path

BOUND = 18
WRITERS = 2


@dataclass(frozen=True)
class Writer:
    phase: str = 'idle'
    grant: bool = False                 # volatile: lost on crash
    consumed: bool = False              # durable, immutable grant identity
    started: bool = False               # durable dispatch uncertainty marker
    effect: bool = False                # remote outcome, survives crash
    readback: bool = False              # durable verified observation
    receipt: bool = False               # durable completion receipt
    success: bool = False
    dispatches: int = 0
    crashes: int = 0
    automatic_retry: bool = False       # history needed by a safety invariant
    recovered_readback: bool = False    # history for a nonvacuous recovery witness


@dataclass(frozen=True)
class State:
    writers: tuple = (Writer(), Writer())
    locks: int = 0                      # bit per writer; valid model has <=1
    remote_value: int = -1


def changed(state, index, *, locks=None, remote_value=None, **fields):
    writers = list(state.writers)
    writers[index] = replace(writers[index], **fields)
    return State(tuple(writers), state.locks if locks is None else locks,
                 state.remote_value if remote_value is None else remote_value)


def successors(state, weakness=None):
    for index, writer in enumerate(state.writers):
        bit = 1 << index
        owns_lock = bool(state.locks & bit)

        def step(action, **changes):
            return f'w{index}:{action}', changed(state, index, **changes)

        # A fresh operator decision can reissue an UNCONSUMED grant after a
        # pre-dispatch crash. It cannot revive a consumed immutable grant ID.
        if writer.phase in ('idle', 'closed') and not writer.consumed:
            yield step('grant', phase='granted', grant=True)
        if writer.phase == 'granted' and writer.grant:
            if state.locks in (0, bit) or weakness == 'nonexclusive_lock':
                yield step('lock', phase='locked', locks=state.locks | bit)
        if writer.phase == 'locked' and writer.grant and owns_lock:
            if not writer.consumed or weakness == 'replay_consumed_grant':
                yield step('consume', phase='consumed', consumed=True)
        if writer.phase == 'consumed' and writer.grant and owns_lock:
            yield step('start', phase='started', started=True,
                       dispatches=writer.dispatches + 1)
        if writer.phase == 'started' and owns_lock:
            yield step('remote-write', phase='written', effect=True,
                       remote_value=index)
        if writer.phase == 'written' and owns_lock and state.remote_value == index:
            yield step('readback', phase='readback', readback=True)
        if writer.phase == 'readback' and owns_lock:
            yield step('receipt', phase='receipted', receipt=True)
        if writer.phase == 'receipted' and owns_lock:
            yield step('complete', phase='success', success=True, grant=False,
                       locks=state.locks & ~bit)

        # One crash/restart episode per writer bounds histories without treating
        # volatile capability memory as durable. The lock is NEVER age-released.
        if writer.phase in ('granted', 'locked', 'consumed', 'started',
                            'written', 'readback', 'receipted') and writer.crashes == 0:
            yield step('crash', phase='crashed', grant=False, crashes=1)
        if writer.phase == 'crashed':
            if writer.started:
                yield step('restart', phase='recovery')
            else:
                yield step('restart-close', phase='closed', locks=state.locks & ~bit)
        if writer.phase == 'recovery' and owns_lock:
            if writer.receipt and writer.readback:
                yield step('verify-receipt', phase='success', success=True,
                           locks=state.locks & ~bit)
            elif writer.effect and state.remote_value == index:
                yield step('recover-readback', phase='readback', readback=True,
                           recovered_readback=True)
            elif not writer.effect:
                # A settled no-effect observation closes the attempt, consumes
                # its identity forever, and grants NO automatic retry authority.
                yield step('recover-no-effect', phase='closed', locks=state.locks & ~bit)

        # Deliberately weakened models are mutation/negative controls. They are
        # not alternative production behavior and are never imported by runtime.
        if weakness == 'replay_consumed_grant' and writer.phase == 'recovery' and writer.consumed:
            yield step('explicit-regrant-consumed-ID', phase='granted', grant=True)
        if weakness == 'automatic_uncertain_retry' and writer.phase == 'recovery' and owns_lock and not writer.receipt:
            yield step('automatic-retry-dispatch', phase='started', grant=True,
                       automatic_retry=True, dispatches=writer.dispatches + 1)
        if weakness == 'early_success' and writer.phase == 'started':
            yield step('unverified-success', phase='success', success=True,
                       grant=False, locks=state.locks & ~bit)


def violations(state):
    failed = []
    if state.locks.bit_count() > 1:
        failed.append('lock_exclusivity')
    if any(writer.dispatches > 1 for writer in state.writers):
        failed.append('at_most_once_dispatch_per_grant')
    if any(writer.automatic_retry for writer in state.writers):
        failed.append('no_automatic_retry_after_uncertain_outcome')
    if any(writer.success and not (writer.started and writer.effect and
           writer.readback and writer.receipt) for writer in state.writers):
        failed.append('no_success_before_readback_and_receipt')
    return failed


def trace_to(state, parents):
    trace = []
    while parents[state] is not None:
        previous, action = parents[state]
        trace.append(action)
        state = previous
    return list(reversed(trace))


def describe(state):
    return {'locks': [i for i in range(WRITERS) if state.locks & (1 << i)],
            'remote_value': state.remote_value,
            'writers': [vars(writer) for writer in state.writers]}


def explore(weakness=None):
    initial = State()
    pending = deque([(initial, 0)])
    parents = {initial: None}
    depths = Counter({0: 1})
    actions = Counter()
    transitions = 0
    both_success = None
    recovery_success = None
    recovered_no_effect = None
    frontier = 0
    while pending:
        state, depth = pending.popleft()
        failed = violations(state)
        if failed:
            return {'variant': weakness, 'status': 'COUNTEREXAMPLE',
                    'states_discovered': len(parents), 'transitions_examined': transitions,
                    'violated_invariants': failed, 'counterexample_length': depth,
                    'counterexample': trace_to(state, parents), 'final_state': describe(state)}
        if both_success is None and all(writer.success for writer in state.writers):
            both_success = trace_to(state, parents)
        if recovery_success is None and any(writer.success and writer.recovered_readback for writer in state.writers):
            recovery_success = trace_to(state, parents)
        if recovered_no_effect is None and any(writer.phase == 'closed' and writer.started
                and not writer.effect for writer in state.writers):
            recovered_no_effect = trace_to(state, parents)
        if depth == BOUND:
            frontier += 1
            continue
        for action, following in successors(state, weakness):
            transitions += 1
            actions[action.split(':', 1)[1]] += 1
            if following not in parents:
                parents[following] = (state, action)
                depths[depth + 1] += 1
                pending.append((following, depth + 1))
    return {'variant': 'intended', 'status': 'PASS_WITHIN_BOUND',
            'states_discovered': len(parents), 'transitions_examined': transitions,
            'states_at_depth_bound': frontier, 'states_by_minimum_depth': dict(sorted(depths.items())),
            'transition_coverage': dict(sorted(actions.items())),
            'positive_witnesses': {'both_writers_complete': both_success,
                                   'completion_after_uncertain_write_and_fresh_readback': recovery_success,
                                   'uncertain_no_effect_closed_without_retry': recovered_no_effect}}


def main():
    variants = ('nonexclusive_lock', 'replay_consumed_grant',
                'automatic_uncertain_retry', 'early_success')
    expected = {'nonexclusive_lock': 'lock_exclusivity',
                'replay_consumed_grant': 'at_most_once_dispatch_per_grant',
                'automatic_uncertain_retry': 'no_automatic_retry_after_uncertain_outcome',
                'early_success': 'no_success_before_readback_and_receipt'}
    normal = explore()
    controls = [explore(variant) for variant in variants]
    passed = normal['status'] == 'PASS_WITHIN_BOUND' and all(normal['positive_witnesses'].values())
    passed = passed and all(item['status'] == 'COUNTEREXAMPLE' and
                           expected[item['variant']] in item['violated_invariants'] for item in controls)
    result = {'schema_version': 'independent-protocol-model/1',
              'status': 'PASS' if passed else 'FAIL',
              'method': 'breadth-first exhaustive reachable-state exploration with state deduplication',
              'source_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
              'bounds': {'writers': WRITERS, 'immutable_grant_identities_per_writer': 1,
                         'crashes_per_writer': 1, 'maximum_transitions_per_trace': BOUND},
              'assumptions': [
                  'Transitions are atomic; durable consume/start/readback/receipt records survive crashes.',
                  'A crash loses in-process authority and retains the durable lock and remote outcome.',
                  'Lock acquisition is atomic; filesystem, storage and OS are trusted.',
                  'The external write settles before recovery observation; no delayed in-flight effects.',
                  'Readback is accurate; the modeled remote value is observable and has no unmodeled writers.',
                  'One immutable operation/grant identity per writer; new operations and expiry are outside scope.',
                  'Safety only; fairness, availability, starvation and eventual completion are not proved.'],
              'not_established': ['Correspondence with Python implementation', 'OS/filesystem isolation',
                                  'real distributed-storage or Graph semantics', 'unbounded safety/liveness'],
              'intended_model': normal, 'weakened_controls': controls}
    directory = Path(__file__).resolve().parent
    (directory/'results.json').write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
    rows = '\n'.join(f"| {item['variant']} | {item['counterexample_length']} | {', '.join(item['violated_invariants'])} |" for item in controls)
    report = f'''# Independent bounded approval/recovery model

Result: **{result['status']}**. The intended model satisfies four safety invariants
within the stated bound; all four deliberately weakened models produce retained
counterexamples. This is a check of an authored abstraction, **not proof of the
Python implementation**.

Two writers, one immutable grant identity each, at most one crash/restart episode
per writer, and traces of at most {BOUND} atomic transitions were explored by BFS
with complete-state deduplication. The intended run visited
**{normal['states_discovered']} states** and examined
**{normal['transitions_examined']} transitions**;
**{normal['states_at_depth_bound']} states** reached the depth boundary.

The model includes grant, lock, durable consume, dispatch start, external write,
verified readback, durable receipt, completion, crash, restart and explicit
reconciliation. It asserts lock exclusivity, at most one dispatch per grant, no
automatic retry after an uncertain outcome, and no success before readback and
receipt. Positive witnesses cover both writers completing, recovery completion
after a crash, and an uncertain no-effect attempt closing without replay.

| Deliberate weakening | Shortest counterexample length | Violated invariant(s) |
| --- | ---: | --- |
{rows}

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
'''
    (directory/'README.md').write_text(report)
    print(json.dumps({'status': result['status'], 'states': normal['states_discovered'],
                      'transitions': normal['transitions_examined'],
                      'depth_bound': BOUND, 'negative_controls': len(controls)}, sort_keys=True))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
