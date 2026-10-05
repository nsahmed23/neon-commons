#!/usr/bin/env python3
"""Run seeded estates through the actual mapper and independent mutation oracle."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from intune_iac.synthetic import (CASES, generate_estate, selected_capture, compare_normalized,
                                  inspect_estate, simulate_local_transition, write_estate)
from intune_iac.engine import generate, inspect_source, verify_project


def qualify(seeds=(0, 42, 2147483647)):
    cases, mutants, alternatives = [], [], []
    for seed in seeds:
        for case in CASES:
            estate = generate_estate(seed=seed, case=case)
            for index, context in enumerate(estate['contexts']):
                with tempfile.TemporaryDirectory(prefix='intune-synthetic-') as td:
                    td = Path(td)
                    source = td / 'capture.json'; ctx = td / 'context.json'
                    source.write_text(json.dumps(selected_capture(estate, context['selected_policy_id'])))
                    ctx.write_text(json.dumps(context))
                    try:
                        inspected = inspect_source(source, ctx)
                    except Exception as error:
                        from intune_iac.io import AppError
                        if not isinstance(error, AppError): raise
                        expected = estate['truth']['expected_mapping'] == 'blocked' and index == 0
                        cases.append({'case_id': estate['case_id'], 'policy_index': index,
                                      'hard_rejection': error.code, 'passed': expected})
                        continue
                    errors = compare_normalized(estate, inspected['normalized'], context['selected_policy_id'])
                    generated = generate(source, ctx, td / 'project')
                    verified = verify_project(source, ctx, td / 'project')
                    ready = generated['offline_mapping_complete']
                    active = bool(list((td / 'project').rglob('*.tf')))
                    cases.append({'case_id': estate['case_id'], 'policy_index': index,
                                  'ready': ready, 'active_iac': active,
                                  'oracle_issues': errors, 'verified': verified['preservation_verified'],
                                  'passed': not errors and ready == active and not generated['execution_authorized']})
                    if case != 'baseline' or index != 0:
                        continue
                    good = inspected['normalized']
                    mutations = {
                        'policy-id': lambda x: x.update(object_id=estate['truth']['policies'][1]['id']),
                        'tenant-id': lambda x: x.update(tenant_id='wrong'),
                        'grant-authority': lambda x: x.update(execution_authorized=True),
                        'claim-live': lambda x: x.update(live_qualification='passed'),
                        'readiness': lambda x: x.update(offline_mapping_complete=False),
                        'policy-name': lambda x: x['desired'].update(name='replacement'),
                        'description': lambda x: x['desired'].update(description='replacement'),
                        'platform': lambda x: x['desired'].update(platforms='linux'),
                        'technology': lambda x: x['desired'].update(technologies=[]),
                        'scope-tags': lambda x: x['desired'].update(role_scope_tag_ids=[]),
                        'setting-value': lambda x: x['desired']['settings']['settings'][0]['settingInstance']['choiceSettingValue'].update(value='changed'),
                        'drop-exclusion': lambda x: x['desired']['assignments'].pop(),
                        'duplicate-assignment': lambda x: x['desired']['assignments'].append(copy.deepcopy(x['desired']['assignments'][0])),
                        'filter-mode': lambda x: x['desired']['assignments'][0].update(filter_type='exclude'),
                        'filter-id': lambda x: x['desired']['assignments'][0].update(filter_id='wrong'),
                        'group-id': lambda x: x['desired']['assignments'][0].update(group_id='wrong'),
                        'assignment-type': lambda x: x['desired']['assignments'][0].update(type='allDevicesAssignmentTarget'),
                    }
                    for name, mutate in mutations.items():
                        candidate = copy.deepcopy(good); mutate(candidate)
                        errors = compare_normalized(estate, candidate)
                        mutants.append({'seed': seed, 'name': name, 'rejected': bool(errors), 'issues': errors})
                    for name in ('assignment-order', 'tag-order', 'dict-order'):
                        candidate = copy.deepcopy(good)
                        if name == 'assignment-order': candidate['desired']['assignments'].reverse()
                        elif name == 'tag-order': candidate['desired']['role_scope_tag_ids'].reverse()
                        else: candidate['desired'] = dict(reversed(list(candidate['desired'].items())))
                        errors = compare_normalized(estate, candidate)
                        alternatives.append({'seed': seed, 'name': name, 'accepted': not errors, 'issues': errors})
    transitions = []
    for case, expected in [('baseline', 'converged'), ('stale-state', 'blocked'),
                           ('approval-replay', 'blocked'), ('wrong-target', 'blocked'),
                           ('denied', 'blocked'), ('partial-failure', 'reconciliation_required'),
                           ('wrong-cloud','blocked'), ('wrong-principal','blocked'),
                           ('wrong-backend','blocked'), ('wrong-lineage','blocked'),
                           ('expired-approval','blocked'), ('plan-substitution','blocked'), ('lease-loss','blocked')]:
        estate = generate_estate(case=case)
        result = simulate_local_transition(estate)
        passed = result['status'] == expected and result['before_state_sha256'] == result['after_state_sha256']
        transitions.append({'case': case, 'status': result['status'], 'issues': result['issues'], 'passed': passed})
    for fault in ('before-policy', 'after-policy', 'before-assignment', 'after-assignment',
                  'before-state', 'after-state', 'before-receipt', 'after-receipt'):
        result = simulate_local_transition(generate_estate(), fault=fault)
        transitions.append({'case': fault, 'status': result['status'], 'issues': result['issues'],
                            'passed': result['status'] == 'reconciliation_required' and not result['converged']})
    first = simulate_local_transition(generate_estate())
    replay = simulate_local_transition(first['estate'])
    transitions.append({'case': 'actual-modeled-replay', 'status': replay['status'],
                        'issues': replay['issues'], 'passed': replay['status'] == 'blocked'})
    # A valid alternative is a newly reviewed plan against the current serial,
    # not an oracle that rejects every state other than the first fixture.
    fresh = generate_estate(case='stale-state')
    from intune_iac.synthetic import _hash
    fresh['plan']['state_serial'] = fresh['state']['serial']
    fresh['approval']['plan_sha256'] = _hash(fresh['plan'])
    result = simulate_local_transition(fresh)
    alternatives.append({'name': 'fresh-plan-for-current-state', 'accepted': result['status'] == 'converged'})
    for seed in seeds:
        for name in ('missing-state', 'lost-assignment', 'changed-setting', 'empty-actions', 'duplicate-action', 'unexpected-action'):
            estate = generate_estate(seed=seed)
            oid = estate['truth']['policies'][0]['id']
            if name == 'missing-state': estate['state']['objects'] = {}
            elif name == 'lost-assignment': estate['state']['objects'][oid]['assignments'] = []
            elif name == 'changed-setting': estate['state']['objects'][oid]['settings'] = {}
            elif name == 'empty-actions': estate['plan']['actions'] = []
            elif name == 'duplicate-action': estate['plan']['actions'].append(copy.deepcopy(estate['plan']['actions'][0]))
            else: estate['plan']['actions'][0]['id'] = 'unrelated'
            estate['approval']['plan_sha256'] = _hash(estate['plan'])
            result = simulate_local_transition(estate)
            rejected = (not inspect_estate(estate)['success'] and result['status'] == 'blocked'
                        and not result['converged'] and result['effects'] == 0)
            mutants.append({'seed': seed, 'name': name, 'rejected': rejected, 'issues': result['issues']})
        estate = generate_estate(seed=seed)
        estate['plan']['actions'].reverse()
        estate['approval']['plan_sha256'] = _hash(estate['plan'])
        for policy in estate['state']['objects'].values():
            policy['assignments'].reverse()
            policy['role_scope_tag_ids'].reverse()
        accepted = inspect_estate(estate)['success'] and simulate_local_transition(estate)['converged']
        alternatives.append({'seed': seed, 'name': 'state-and-action-order', 'accepted': accepted})
    success = (all(r['passed'] for r in cases + transitions) and
               all(r['rejected'] for r in mutants) and all(r['accepted'] for r in alternatives))
    return {'schema_version': 'synthetic-qualification/1.0', 'success': success,
            'implementation_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                                      for name in ('intune_iac/synthetic.py', 'scripts/qualify-synthetic.py',
                                                   'intune_iac/engine.py', 'reference/core.py')},
            'seeds': list(seeds), 'estate_cases': len(seeds) * len(CASES),
            'policy_mapping_runs': len(cases), 'mutation_checks': len(mutants),
            'legitimate_alternatives': len(alternatives), 'transition_checks': len(transitions),
            'cases': cases, 'mutants': mutants, 'alternatives': alternatives, 'transitions': transitions,
            'oracle': 'Authored domain truth before capture serialization; no production or reference normalizer imports in comparison code.',
            'boundary': 'Actual Python generation and verification; state/approval transitions are pure synthetic simulation, never native or cloud execution.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--seeds', nargs='+', type=int, default=[0, 42, 2147483647])
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    result = qualify(args.seeds)
    (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('cases', 'mutants', 'alternatives', 'transitions')}, indent=2))
    return 0 if result['success'] else 1

if __name__ == '__main__': raise SystemExit(main())
