#!/usr/bin/env python3
"""Subprocess qualification of the synthetic workbench, with independent truth.

The grader imports no product code. The CLI supplies all product behavior; its
observations are checked through read-only SQLite and raw modeled-service JSON.
These processes share a host/user: this is not hostile-process oracle isolation,
provider RPC, live Graph, native GitHub, endpoint, or production qualification.
Every run must use a new output directory; failed runs and logs are retained.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import pty
import select
import sqlite3
import subprocess
import sys
import termios
import struct
import fcntl
import time
import traceback

PROJECT = Path(__file__).resolve().parents[1]
POLICY = '22222222-2222-4222-8222-222222222222'
UNRELATED = '33333333-3333-4333-8333-333333333333'
TENANT = '11111111-1111-4111-8111-111111111111'
DEFINITION = 'device_vendor_msft_policy_config_privacy_letappsaccesslocation'


def expected_policy(value=None):
    """Reviewed literal expectation, deliberately not derived by a projector."""
    return {
        'name': 'Windows Privacy Pilot',
        'description': 'Synthetic reference; not production advice.',
        'platforms': 'windows10', 'technologies': ['mdm'],
        'role_scope_tag_ids': ['0'],
        'settings': {'settings': [{
            'id': '0', 'settingInstance': {
                '@odata.type': '#microsoft.graph.deviceManagementConfigurationChoiceSettingInstance',
                'settingDefinitionId': DEFINITION,
                'settingInstanceTemplateReference': None,
                'choiceSettingValue': {
                    '@odata.type': '#microsoft.graph.deviceManagementConfigurationChoiceSettingValue',
                    'settingValueTemplateReference': None,
                    'value': value or DEFINITION + '_2', 'children': [],
                },
            },
        }]},
        'assignments': [
            {'type': 'groupAssignmentTarget', 'group_id': '44444444-4444-4444-8444-444444444444',
             'filter_type': 'include', 'filter_id': '77777777-7777-4777-8777-777777777777'},
            {'type': 'groupAssignmentTarget', 'group_id': '55555555-5555-4555-8555-555555555555',
             'filter_type': 'none'},
            {'type': 'exclusionGroupAssignmentTarget', 'group_id': '66666666-6666-4666-8666-666666666666',
             'filter_type': 'none'},
        ],
    }


def expected_estate(value=None):
    return {'schema_version': 'intune-semantic-estate/1.0', 'tenant_id': TENANT,
            'cloud': 'public', 'objects': {POLICY: expected_policy(value), UNRELATED: expected_policy()}}


def exact(expected, actual, path='$'):
    """Type-sensitive independent equality, including bool versus int."""
    if type(expected) is not type(actual):
        raise AssertionError(f'{path}: type {type(actual).__name__} != {type(expected).__name__}')
    if isinstance(expected, dict):
        if set(expected) != set(actual):
            raise AssertionError(f'{path}: keys differ: {set(expected) ^ set(actual)}')
        for key in expected:
            exact(expected[key], actual[key], path + '.' + key)
    elif isinstance(expected, list):
        if len(expected) != len(actual):
            raise AssertionError(f'{path}: list length differs')
        for index, value in enumerate(expected):
            exact(value, actual[index], f'{path}[{index}]')
    elif expected != actual:
        raise AssertionError(f'{path}: value {actual!r} != {expected!r}')


def semantic_estate(expected, actual):
    """Only model-declared unordered bags may reorder; multiplicity is retained."""
    def ordered(value):
        result = copy.deepcopy(value)
        for body in result.get('objects', {}).values():
            if not isinstance(body, dict):
                continue
            for field in ('assignments', 'technologies', 'role_scope_tag_ids'):
                if isinstance(body.get(field), list):
                    body[field].sort(key=lambda item: json.dumps(item, sort_keys=True, separators=(',', ':')))
        return result
    exact(ordered(expected), ordered(actual))


def negative_controls():
    controls = {}
    source = expected_estate()
    mutations = {}
    bad = copy.deepcopy(source); bad['objects']['00000000-0000-4000-8000-000000000000'] = bad['objects'].pop(POLICY); mutations['wrong_id'] = bad
    bad = copy.deepcopy(source); bad['objects'][POLICY]['assignments'].pop(); mutations['missing_exclusion'] = bad
    bad = copy.deepcopy(source); bad['objects'][POLICY]['assignments'][0]['filter_type'] = 'none'; mutations['wrong_filter'] = bad
    bad = copy.deepcopy(source); bad['objects'][POLICY]['settings']['settings'][0]['settingInstance']['choiceSettingValue']['value'] = True; mutations['wrong_setting_type'] = bad
    bad = copy.deepcopy(source); del bad['objects'][UNRELATED]; mutations['missing_unrelated_object'] = bad
    bad = copy.deepcopy(source); bad['objects'][POLICY]['settings']['settings'][0]['settingInstance']['settingInstanceTemplateReference'] = ''; mutations['null_changed'] = bad
    semantic_estate(source, copy.deepcopy(source)); controls['known_good'] = True
    alternate = copy.deepcopy(source)
    for body in alternate['objects'].values():
        body['assignments'].reverse()
    semantic_estate(source, alternate); controls['known_good_bag_permutation'] = True
    try:
        exact({'value': 1}, {'value': True})
    except AssertionError:
        controls['boolean_integer_distinction'] = True
    else:
        raise AssertionError('Oracle accepts bool/int corruption')
    for name, value in mutations.items():
        try:
            semantic_estate(source, value)
        except AssertionError:
            controls[name] = True
        else:
            raise AssertionError('Oracle accepts ' + name)
    return controls


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


class Run:
    def __init__(self, root, python):
        self.root, self.python = root, python
        self.root.mkdir(mode=0o700, parents=True, exist_ok=False)
        self.results = {'schema_version': 'workbench-independent-qualification/1.0',
            'status': 'RUNNING', 'evidence_class': 'synthetic_cli_with_independent_persisted_state_assertions',
            'limitations': ['shared user/host; no hostile-process oracle isolation',
                'modeled service and synthetic approval; not provider RPC or Graph',
                'no native GitHub/Azure/Entra, device, or organizational approval evidence'],
            'python': sys.version, 'platform': platform.platform(), 'started_at': time.time(),
            'source_sha256': {}, 'checks': [], 'commands': []}
        # Keep an external checker distinguishable from the product being graded.
        self.checker = Path(__file__).resolve()
        self.results['checker'] = {'path': str(self.checker),
            'sha256': hashlib.sha256(self.checker.read_bytes()).hexdigest()}
        files = [PROJECT / 'scripts/intune-iac.py', PROJECT / 'examples/supported/input/export.json']
        if self.checker.is_relative_to(PROJECT):
            files.insert(0, self.checker)
        files += sorted((PROJECT / 'intune_iac').glob('*.py'))
        for path in files:
            self.results['source_sha256'][str(path.relative_to(PROJECT))] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.save()

    def save(self):
        dump(self.root / 'receipt.json', self.results)

    def source_end(self):
        self.results['checker']['end_sha256'] = hashlib.sha256(self.checker.read_bytes()).hexdigest()
        if self.results['checker']['end_sha256'] != self.results['checker']['sha256']:
            raise AssertionError('Independent checker changed during qualification')
        self.results['source_end_sha256'] = {name: hashlib.sha256((PROJECT / name).read_bytes()).hexdigest()
            for name in self.results['source_sha256']}
        changed = [name for name, digest in self.results['source_sha256'].items()
                   if self.results['source_end_sha256'][name] != digest]
        self.results['source_changed_during_run'] = changed
        if changed:
            raise AssertionError('Source changed during qualification; retain run and rerun frozen source: ' + repr(changed))

    def check(self, name, fn):
        item = {'name': name, 'status': 'RUNNING'}
        self.results['checks'].append(item)
        try:
            result = fn()
            item.update(status='PASS', details=result)
        except Exception as exc:
            item.update(status='FAIL', error=repr(exc))
            raise
        finally:
            self.save()

    def cli(self, *args, stdin=None, allowed=(0,)):
        argv = [self.python, '-B', str(PROJECT / 'scripts/intune-iac.py'), 'workbench', *map(str, args)]
        n = len(self.results['commands']) + 1
        started = time.time()
        result = subprocess.run(argv, input=stdin, text=True, capture_output=True, cwd=PROJECT,
                                env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}, timeout=60)
        prefix = f'{n:03d}-{args[0]}'
        (self.root / (prefix + '.stdout')).write_text(result.stdout)
        (self.root / (prefix + '.stderr')).write_text(result.stderr)
        self.results['commands'].append({'argv': argv, 'stdin': stdin, 'returncode': result.returncode,
            'seconds': time.time() - started, 'stdout': prefix + '.stdout', 'stderr': prefix + '.stderr'})
        self.save()
        if result.returncode not in allowed:
            raise AssertionError(f'{prefix} exit {result.returncode}: {result.stderr[-1000:]} {result.stdout[-1000:]}')
        if stdin is not None:
            return result.stdout
        return json.loads(result.stdout or result.stderr)

    def terminal_pty(self, store, service, commands, columns=80):
        """Actual PTY: sequential prompt-triggered input and bounded termination."""
        argv = [self.python, '-B', str(PROJECT / 'scripts/intune-iac.py'), 'workbench',
                'terminal', '--root', str(store), '--service-root', str(service)]
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 24, columns, 0, 0))
        process = subprocess.Popen(argv, stdin=slave, stdout=slave, stderr=slave, cwd=PROJECT,
                                   env={**os.environ, 'TERM': 'xterm', 'PYTHONDONTWRITEBYTECODE': '1'}, start_new_session=True)
        os.close(slave)
        output = bytearray()
        sent = 0
        prompt_count = 0
        deadline = time.monotonic() + 30
        started = time.time()
        log_name = f'{len(self.results["commands"]) + 1:03d}-terminal-pty.stdout'
        try:
            while time.monotonic() < deadline:
                ready, _, _ = select.select([master], [], [], .1)
                if ready:
                    try:
                        block = os.read(master, 65536)
                    except OSError:
                        break
                    if not block:
                        break
                    output.extend(block)
                    if len(output) > 2 * 1024 * 1024:
                        raise AssertionError('PTY output limit')
                    prompts = output.count(b'workbench> ')
                    if prompts > prompt_count and sent < len(commands):
                        os.write(master, (commands[sent] + '\n').encode())
                        sent += 1
                        prompt_count = prompts
                if process.poll() is not None and not ready:
                    break
            # PTY EOF/EIO can precede waitpid visibility. Use only the
            # remaining original deadline to observe exit before declaring it late.
            try:
                code = process.wait(timeout=max(0.0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                process.kill()
                raise AssertionError('PTY did not terminate within 30 seconds')
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=2)
            os.close(master)
            (self.root / log_name).write_bytes(output)
            self.results['commands'].append({'argv': argv, 'mode': 'PTY', 'columns': columns,
                'rows': 24, 'term': 'xterm', 'commands': commands, 'commands_sent': sent,
                'returncode': process.returncode, 'seconds': time.time() - started,
                'stdout': log_name})
            self.save()
        if code != 0 or sent != len(commands):
            raise AssertionError(f'PTY exited {code}, sent {sent}/{len(commands)}')
        return output.decode('utf-8')

    def db(self, query, args=()):
        path = self.root / 'store/observations.sqlite3'
        with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as connection:
            connection.row_factory = sqlite3.Row
            return [dict(row) for row in connection.execute(query, args)]

    def persisted_estate(self):
        rows = self.db('SELECT s.object_id,s.body_json FROM snapshots s JOIN observations o '
                       'ON o.snapshot_id=s.snapshot_id WHERE o.run_id=(SELECT MAX(run_id) FROM observations)')
        return {'schema_version': 'intune-semantic-estate/1.0', 'tenant_id': TENANT,
                'cloud': 'public', 'objects': {row['object_id']: json.loads(row['body_json']) for row in rows}}


def qualify(run):
    root = run.root
    store, service = root / 'store', root / 'service'
    capture = read(PROJECT / 'examples/supported/input/export.json')
    for original in list(capture['collections']):
        if original.get('owner_id') == POLICY:
            additional = copy.deepcopy(original)
            additional['owner_id'] = UNRELATED
            for page in additional['pages']:
                page['request_url'] = page['request_url'].replace(POLICY, UNRELATED)
            capture['collections'].append(additional)
    dump(root / 'capture.json', capture)
    dump(root / 'expected-initial.json', expected_estate())
    desired = expected_policy(DEFINITION + '_1')
    dump(root / 'desired.json', desired)
    dump(root / 'deployment.json', {'targeted': 100, 'reporting': 8, 'successful': 8})
    run.check('independent_oracle_negative_controls', negative_controls)
    run.cli('lab-create', '--service-root', service, '--input', root / 'capture.json', '--object', POLICY, '--object', UNRELATED)
    run.check('literal_initial_service_semantics', lambda: exact(expected_estate(), read(service / 'service.json')['current']))
    run.cli('init', '--root', store, '--tenant', TENANT)
    run.cli('collect', '--root', store, '--service-root', service, '--deployment', root / 'deployment.json')
    run.check('closed_terminal_collection_persisted', lambda: exact(expected_estate(), run.persisted_estate()))
    run.check('independent_typed_relationships_persisted', lambda: assert_relationships(run))
    output = run.cli('terminal', '--root', store, '--service-root', service,
                     stdin=f'search Privacy\nselect {POLICY}\nsettings\nrelationships\nhistory\nhealth\nback\nquit\n')
    run.check('actual_terminal_search_select_inspect', lambda: assert_contains(output, [POLICY, 'exclusionGroupAssignmentTarget', DEFINITION]))
    pty_output = run.terminal_pty(store, service, ['search Privacy', 'select ' + POLICY, 'settings',
        'relationships', 'history', 'health', 'back', 'cancel', 'quit'])
    run.check('actual_pty_search_inspect_history_navigation', lambda: assert_contains(pty_output,
        [POLICY, 'selection_cleared', 'exclusionGroupAssignmentTarget', 'history_persisted']))
    run.cli('inspect', '--root', store, '--object', POLICY)
    run.cli('history', '--root', store, '--object', POLICY)
    health = run.cli('health', '--root', store)
    run.check('health_retains_targeted_and_reporting_denominators', lambda: assert_health(health))
    proposal_terminal = run.terminal_pty(store, service, ['select ' + POLICY,
        f'propose "{root / "desired.json"}" "{root / "operation"}"', f'review "{root / "operation"}"', 'quit'])
    run.check('actual_pty_prepares_reviewable_maintenance', lambda: assert_contains(proposal_terminal,
        ['approval_digest', 'settings_changed']))
    review = run.cli('review', '--operation', root / 'operation')
    approval_digest = review['approval_digest']
    run.check('review_binds_only_intended_change', lambda: assert_review(root / 'operation', review))
    wrong = run.cli('execute', '--operation', root / 'operation', '--approve-digest', '0' * 64, allowed=(3,))
    run.check('wrong_approval_rejected_before_mutation', lambda: assert_rejection(run, wrong, 'maintenance_approval_required', 0))
    sealed = root / 'operation/executor/work/saved.tfplan'
    original_plan = sealed.read_bytes()
    (root / 'pre-substitution-saved-plan.bin').write_bytes(original_plan)
    sealed.write_bytes(original_plan + b'\nINERT_SUBSTITUTION_CONTROL\n')
    substituted = run.cli('execute', '--operation', root / 'operation', '--approve-digest', approval_digest, allowed=(3,))
    run.check('saved_plan_substitution_rejected_before_mutation', lambda: assert_no_patch(run, 0))
    (root / 'substituted-saved-plan.bin').write_bytes(sealed.read_bytes())
    sealed.write_bytes(original_plan)
    execution_terminal = run.terminal_pty(store, service,
        [f'review "{root / "operation"}"', f'execute "{root / "operation"}" {approval_digest}', 'quit'])
    run.check('actual_pty_executes_exact_reviewed_operation', lambda: assert_contains(execution_terminal,
        ['succeeded_verified', 'native_provider_qualified']))
    run.check('independent_service_change_only_one_setting', lambda: semantic_estate(expected_estate(DEFINITION + '_1'), read(service / 'service.json')['current']))
    run.cli('collect', '--root', store, '--service-root', service, '--deployment', root / 'deployment.json')
    run.check('independent_readback_converges_to_desired', lambda: exact(expected_estate(DEFINITION + '_1'), run.persisted_estate()))
    history = run.db('SELECT snapshot_id FROM observations WHERE object_id=? ORDER BY observation_id', (POLICY,))
    comparison = run.cli('compare', '--root', store, '--object', POLICY, '--before', history[0]['snapshot_id'], '--after', history[-1]['snapshot_id'])
    run.check('historical_comparison_is_one_setting_change', lambda: assert_equal([item['field'] for item in comparison['changes']], ['settings']))
    second = run.cli('propose', '--root', store, '--service-root', service, '--object', POLICY,
                     '--desired', root / 'desired.json', '--output', root / 'no-change')
    run.check('no_change_second_comparison', lambda: assert_no_change(second))
    before = run.persisted_estate()
    count = len(run.db('SELECT observation_id FROM observations'))
    denied = run.cli('collect', '--root', store, '--service-root', service, '--fault', 'deny', allowed=(0, 2))
    run.check('denied_collection_retains_last_good', lambda: assert_last_good(run, before, count))
    retained = run.cli('overview', '--root', store)
    run.check('failed_collection_marks_last_good_stale', lambda: assert_equal(retained['freshness'], 'stale'))
    run.cli('inspect', '--root', store, '--object', POLICY)
    # A separate operation intentionally commits and loses its response. Recovery
    # is a fresh subprocess and is required to perform readback without replay.
    dump(root / 'recovery-desired.json', expected_policy(DEFINITION + '_0'))
    run.cli('collect', '--root', store, '--service-root', service)
    run.cli('propose', '--root', store, '--service-root', service, '--object', POLICY,
            '--desired', root / 'recovery-desired.json', '--output', root / 'recovery-operation')
    recovery_review = run.cli('review', '--operation', root / 'recovery-operation')
    lost = run.cli('execute', '--operation', root / 'recovery-operation', '--approve-digest', recovery_review['approval_digest'],
                   '--fault', 'lost-response', allowed=(3,))
    run.check('lost_response_stays_uncertain', lambda: assert_equal(lost['status'], 'outcome_unknown'))
    patches = sum(row['method'] == 'PATCH' for row in read(service / 'service.json')['requests'])
    reconciled = run.cli('reconcile', '--operation', root / 'recovery-operation')
    run.check('fresh_process_recovery_resolves_by_readback', lambda: assert_equal(reconciled['classification'], 'desired_state_observed'))
    replay = run.cli('execute', '--operation', root / 'recovery-operation', '--approve-digest', recovery_review['approval_digest'], allowed=(3,))
    run.check('replay_explicitly_rejected', lambda: assert_equal(replay['error']['code'], 'maintenance_replay_forbidden'))
    run.check('recovery_never_replays_patch', lambda: assert_equal(sum(row['method'] == 'PATCH' for row in read(service / 'service.json')['requests']), patches))
    run.check('recovered_service_preserves_all_other_semantics', lambda: exact(expected_estate(DEFINITION + '_0'), read(service / 'service.json')['current']))
    stale = run.cli('execute', '--operation', root / 'no-change', '--approve-digest', second['approval_digest'], allowed=(3,))
    run.check('stale_plan_rejected_without_replan', lambda: assert_rejection(run, stale, 'maintenance_plan_stale', patches))
    run.cli('collect', '--root', store, '--service-root', service, '--deployment', root / 'deployment.json')
    run.check('reopened_history_retains_observations', lambda: assert_history(run))
    run.cli('terminal', '--root', store, '--service-root', service,
            stdin=f'select {POLICY}\nhistory\nhealth\nquit\n')
    dump(root / 'independent-final-service-readback.json', read(service / 'service.json'))
    dump(root / 'independent-final-observed-estate.json', run.persisted_estate())
    run.check('frozen_source_unchanged_during_qualification', run.source_end)


def assert_equal(actual, expected):
    exact(expected, actual)


def assert_no_patch(run, expected):
    assert_equal(sum(row['method'] == 'PATCH' for row in read(run.root / 'service/service.json')['requests']), expected)


def assert_rejection(run, result, code, expected_patches):
    assert_equal(result['error']['code'], code)
    assert_no_patch(run, expected_patches)


def assert_relationships(run):
    rows = run.db('SELECT r.relation,r.target_id,r.details_json FROM relationships r '
                  'JOIN snapshots s USING(snapshot_id) WHERE s.object_id=?', (POLICY,))
    got = {(row['relation'], row['target_id']) for row in rows}
    expected = {('assignment', '44444444-4444-4444-8444-444444444444'),
                ('assignment', '55555555-5555-4555-8555-555555555555'),
                ('exclusion', '66666666-6666-4666-8666-666666666666'),
                ('filter', '77777777-7777-4777-8777-777777777777'),
                ('setting', DEFINITION), ('scope_tag', '0')}
    if got != expected:
        raise AssertionError('Typed relationship set differs from explicit fixture: ' + repr(got))
    filtered = next(json.loads(row['details_json']) for row in rows if row['relation'] == 'filter')
    assert_equal(filtered['mode'], 'include')
    return {'typed_edges': len(got)}


def assert_review(operation, review):
    exact([POLICY + ':settings_changed'], review['changes'])
    exact(expected_policy(), review['before'])
    exact(expected_policy(DEFINITION + '_1'), review['desired'])
    plan = read(operation / 'plan.json')
    raw = json.dumps(plan, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    assert_equal(review['approval_digest'], hashlib.sha256(raw).hexdigest())
    prep = read(operation / 'executor/preparation.json')
    assert_equal(prep['bindings']['saved_plan_sha256'], hashlib.sha256((operation / 'executor/work/saved.tfplan').read_bytes()).hexdigest())
    exact(expected_estate(DEFINITION + '_1'), read(operation / 'executor/work/plan.json')['planned_values']['outputs']['fixture']['value'])
    return {'approval_digest': review['approval_digest'], 'saved_plan_sha256': prep['bindings']['saved_plan_sha256'],
            'boundary': 'existing protected synthetic executor; not OpenTofu/provider qualification'}


def assert_contains(text, values):
    for value in values:
        if value not in text:
            raise AssertionError(f'Actual terminal output omitted {value}')


def assert_health(health):
    # The actual shape is intentionally traversed without the product helper.
    def candidates(value):
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from candidates(child)
        elif isinstance(value, list):
            for child in value:
                yield from candidates(child)
    for row in candidates(health):
        if row.get('targeted') == 100 and row.get('reporting') == 8 and row.get('successful') == 8:
            if row.get('reporting_success_percent') != 100 or row.get('targeted_success_percent') != 8:
                raise AssertionError('Health percentages use the wrong denominators')
            if row.get('unknown_or_stale') != 92 or row.get('rollout_ready') is not False:
                raise AssertionError('Unreported devices falsely authorize rollout')
            if row.get('endpoint_outcome') != 'unknown' or row.get('endpoint_health') != 'unknown':
                raise AssertionError('Aggregate reports were promoted to endpoint success')
            return {'targeted': 100, 'reporting': 8, 'successful': 8,
                    'successful_of_reporting': 1.0, 'successful_of_targeted': .08,
                    'endpoint_effective_state': 'unknown'}
    raise AssertionError('Health lost the 100 targeted / 8 reporting / 8 successful distinction')


def assert_no_change(result):
    if result.get('status') not in ('no_change', 'no_changes') and result.get('changes') != []:
        raise AssertionError('Second comparison does not report no change: ' + repr(result))


def assert_last_good(run, expected, count):
    exact(expected, run.persisted_estate())
    assert_equal(len(run.db('SELECT observation_id FROM observations')), count)
    latest = run.db('SELECT * FROM collection_runs ORDER BY run_id DESC LIMIT 1')[0]
    if latest['status'] in ('complete', 'succeeded', 'success') or latest['coverage'] == 'complete':
        raise AssertionError('Denied read reported as successful complete collection')
    return latest


def assert_history(run):
    rows = run.db('SELECT * FROM observations WHERE object_id=? ORDER BY observation_id', (POLICY,))
    if len(rows) < 4 or len({row['snapshot_id'] for row in rows}) != 3:
        raise AssertionError('History lost repeated observations or changed setting snapshots')
    return {'observations': len(rows), 'distinct_snapshots': 3}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path, help='new evidence directory (never overwritten)')
    parser.add_argument('--python', default=sys.executable)
    parser.add_argument('--oracle-self-test', action='store_true')
    args = parser.parse_args(argv)
    run = Run(args.output.absolute(), args.python)
    try:
        if args.oracle_self_test:
            run.check('independent_oracle_negative_controls', negative_controls)
            run.check('frozen_source_unchanged_during_qualification', run.source_end)
        else:
            qualify(run)
        run.results['status'] = 'PASS'
        returncode = 0
    except Exception as exc:
        run.results.update(status='FAIL', error=repr(exc), traceback=traceback.format_exc())
        returncode = 1
    finally:
        run.results['finished_at'] = time.time()
        run.save()
    print(json.dumps({'status': run.results['status'], 'checks': len(run.results['checks']),
                      'receipt': str(run.root / 'receipt.json'), 'error': run.results.get('error')}))
    return returncode


if __name__ == '__main__':
    raise SystemExit(main())
