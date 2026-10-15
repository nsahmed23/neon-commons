"""P3b: records made before a bound file changed stay readable as history; execution stays exactly as strict.

Every record (protected operation, journey, native Atmos receipt, adoption) binds the digest of the implementation files
that made it. After one of those files changes, the record no longer equals the current implementation. These tests
check the split the advisors asked for (lanes/advisor-pin-migration/DECISION-P3b.md):

* history reads (implementation='recorded') accept a record whose implementation the inventory recognises and report the
  relation, the recorded and the current digest and the bound component set; they refuse tampered and unknown records;
* every execution path keeps the current-implementation comparison, and a pre-upgrade request that is still fresh and
  unconsumed is refused by name before anything is written or dispatched;
* recovery reports the relation and never authorizes anything; adoption refuses a new handoff of a journey whose
  relation is not same and verifies an existing complete handoff without changing its bytes.

The upgrade is real: the tests copy the package, append one byte to a bound file of the copy and run the copy in a
subprocess, as test_pre_pin_migration does for its frozen root and interpreter.
"""
import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from intune_iac import implementation_history as history
from intune_iac import journey_native_atmos as jna
from intune_iac import protected, protected_worker as worker
from intune_iac.io import AppError, canonical, digest, load_json, write_json
from plugin_tests import test_journey_native_atmos as atmos_base
from plugin_tests import test_pre_pin_migration as frozen
from plugin_tests import test_protected_worker_r4 as worker_base

ROOT = Path(__file__).resolve().parents[1]
FROZEN_DIGEST = 'c3ebd0c1c769e4d500406abb9b5b8ba716cea6f6da7108b8fec901daa875dc9c'
BOUND_FILE = 'native_pins.py'
UNKNOWN_DIGEST = 'ab' * 32
OPERATION = 'd65bd73123014765922143bd45956e76'
STAGES = ('discovery', 'target', 'inventory', 'selection', 'preservation', 'mapping', 'ownership', 'atmos', 'generation',
          'validation', 'adoption', 'plan', 'approval', 'execute', 'reconcile', 'convergence', 'handoff')
BEFORE_PLAN = list(STAGES[:STAGES.index('plan')])

DRIVER = r'''
import json, sys
from pathlib import Path
import intune_iac
assert Path(intune_iac.__file__).resolve().parent == Path(__file__).resolve().parent / 'intune_iac', 'not the copy'
from intune_iac import implementation_history as history, journey, protected
from intune_iac.io import canonical, digest, file_sha, write_json


def out(value):
    print('RESULT ' + json.dumps(value, sort_keys=True))


def failure(exc):
    return {'error': getattr(exc, 'code', type(exc).__name__), 'message': str(exc)}


def kwargs(mode):
    return {} if mode == 'default' else {'implementation': mode}


def tree_digest(base):
    import hashlib
    h = hashlib.sha256()
    for path in sorted(Path(base).rglob('*')):
        if path.is_file():
            h.update(str(path.relative_to(base)).encode()); h.update(path.read_bytes())
    return h.hexdigest()


command = sys.argv[1]
if command == 'digest':
    out({'current': history.protected_digest(protected._implementation_files())})
elif command == 'progress':
    session = Path(sys.argv[2])
    try:
        state = journey._load(session)
        out(journey._progress(session, state, journey._observe(session, state), **kwargs(sys.argv[3])))
    except Exception as exc:
        out(failure(exc))
elif command == 'reconstruct':
    session = Path(sys.argv[2])
    out({'progress': journey.reconstruct_progress(session), 'plan_action': journey.check_action(session, 'plan')})
elif command == 'validate':
    session = Path(sys.argv[2]); root = journey._root(session)
    request = json.loads((root / 'native-request.json').read_text())
    try:
        out({'result': protected.validate_native_operation(request, executor=protected.SyntheticExecutor(root / 'synthetic-executor'), **kwargs(sys.argv[3]))})
    except Exception as exc:
        out(failure(exc))
elif command == 'reconcile':
    session = Path(sys.argv[2]); root = journey._root(session)
    request = json.loads((root / 'native-request.json').read_text())
    out(protected.reconcile_native_operation(request['operation_id'], root / 'operations',
                                             executor=protected.SyntheticExecutor(root / 'synthetic-executor'), **kwargs(sys.argv[3])))
elif command == 'forge':
    # Whoever holds the code can rewrite every unsigned local record and recompute every hash that chains them.
    session = Path(sys.argv[2]); root = journey._root(session)
    current = history.protected_digest(protected._implementation_files())
    new = current if sys.argv[3] == 'current' else sys.argv[3]
    history.PROTECTED_INVENTORY = history.PROTECTED_INVENTORY + ({'label': 'forgery', 'implementation_sha256': new, 'files': {}},)
    request = json.loads((root / 'native-request.json').read_text())
    request['bindings']['implementation_sha256'] = new
    request['binding_sha256'] = digest(request['bindings'])
    for path in (root / 'native-request.json', root / 'synthetic-executor/preparation.json'):
        path.write_bytes(canonical(request))
    operation = root / 'operations' / request['operation_id']
    previous = '0' * 64
    for index in range(5):
        path = operation / ('%02d.json' % index)
        event = json.loads(path.read_text())
        event['previous_sha256'] = previous
        if index == 0: event['payload'] = {'request': request}
        if index == 1: event['payload']['request_sha256'] = digest(request)
        if index == 2: event['payload'] = {'binding_sha256': request['binding_sha256']}
        if index == 4: event['payload']['request_sha256'] = digest(request)
        path.write_bytes(canonical(event)); previous = file_sha(path)
    consumed = root / 'synthetic-executor/consumed.json'
    consumed.write_bytes(canonical(dict(json.loads(consumed.read_text()), request_sha256=digest(request))))
    result = json.loads((root / 'native-result.json').read_text())
    (root / 'native-result.json').write_bytes(canonical(dict(result, receipt_sha256=previous)))
    state = journey._load(session); observed = journey._observe(session, state)
    dependencies = {}; cache = {}
    for stage in journey.STAGES:
        path = journey._receipt_path(session, stage)
        if journey.STAGES.index(stage) >= journey.STAGES.index('plan'):
            write_json(path, journey._receipt(stage, session, state, observed, dependencies, cache, implementation='recorded'))
        dependencies[stage] = file_sha(path)
    out({'forged_with': new})
elif command == 'prepare':
    work = Path(sys.argv[2])
    executor = protected.create_synthetic_executor(work / 'executor', initial_value={'a': 1}, desired_value={'a': 2})
    request = protected.prepare_native_operation(executor, ttl_seconds=300)
    (work / 'request.json').write_bytes(canonical(request))
    protected.approve_synthetic_operation(request, executor=executor)  # control: a fresh request is approvable now
    out({'operation_id': request['operation_id'], 'control_approval': 'accepted'})
elif command == 'refuse':
    work = Path(sys.argv[2])
    executor = protected.SyntheticExecutor(work / 'executor')
    request = json.loads((work / 'request.json').read_text())
    result = {}
    try:
        protected.approve_synthetic_operation(request, executor=executor); result['approve'] = 'accepted'
    except Exception as exc:
        result['approve'] = failure(exc)
    result['execute'] = protected.execute_native_operation(request, work / 'state', executor=executor, approval=None)
    out(result)
elif command == 'grant_then_upgrade':
    from unittest.mock import patch
    # One process from preparing to the refusal, so a step of the host clock between processes cannot matter.
    work = Path(sys.argv[2])
    executor = protected.create_synthetic_executor(work / 'executor', initial_value={'a': 1}, desired_value={'a': 2})
    request = protected.prepare_native_operation(executor, ttl_seconds=300)
    grant = protected.approve_synthetic_operation(request, executor=executor)  # touches the clock floor, legitimately
    files = protected._implementation_files()
    before = tree_digest(work)
    with patch.object(protected, '_implementation_files', return_value=dict(files, **{'io.py': 'c' * 64})):
        result = protected.execute_native_operation(request, work / 'state', executor=executor, approval=grant)
    out({'execute': result, 'unchanged': tree_digest(work) == before, 'state_dir_created': (work / 'state').exists()})
else:
    raise SystemExit('unknown command')
'''


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def tree(base):
    base = Path(base)
    return {p.relative_to(base).as_posix(): p.read_bytes() for p in sorted(base.rglob('*')) if p.is_file()}


class PackageCopy:
    """A disposable copy of the package, optionally with one byte appended to a bound file, run in a subprocess."""

    def __init__(self, base, *, append=None):
        self.root = Path(base)
        shutil.copytree(ROOT / 'intune_iac', self.root / 'intune_iac', ignore=shutil.ignore_patterns('__pycache__'))
        for name in ('contracts', 'corrections', 'reference'):  # the data and packages intune_iac reads beside itself
            shutil.copytree(ROOT / name, self.root / name, ignore=shutil.ignore_patterns('__pycache__'))
        (self.root / 'scripts').mkdir()
        shutil.copyfile(ROOT / 'scripts/intune-iac.py', self.root / 'scripts/intune-iac.py')
        (self.root / '_driver.py').write_text(DRIVER)
        if append is not None:
            with open(self.root / 'intune_iac' / append, 'ab') as stream:
                stream.write(b'\n')

    def current_digest(self):
        files = [sha256((self.root / 'intune_iac' / name).read_bytes()) for name in protected.PROTECTED_COMPONENTS]
        return digest(files)

    def append(self, name):
        with open(self.root / 'intune_iac' / name, 'ab') as stream:
            stream.write(b'\n')

    def run(self, *args):
        result = subprocess.run([sys.executable, '-B', str(self.root / '_driver.py'), *map(str, args)], text=True,
                                capture_output=True, cwd='/tmp', timeout=180,
                                env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=''))
        if result.returncode != 0:
            raise AssertionError(result.stderr + result.stdout)
        lines = [line for line in result.stdout.splitlines() if line.startswith('RESULT ')]
        if len(lines) != 1:
            raise AssertionError(result.stderr + result.stdout)
        return json.loads(lines[0][len('RESULT '):])

    def cli(self, *args):
        return subprocess.run([sys.executable, '-B', str(self.root / 'scripts/intune-iac.py'), *map(str, args)],
                              text=True, capture_output=True, cwd='/tmp', timeout=180,
                              env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=''))


class UpgradedFrozenCase(frozen.FrozenRootCase):
    """The frozen journey, its adoption and an upgraded copy of the package (one byte appended to a bound file)."""
    kinds = ('journey', 'adoption')
    needs_interpreter = True

    def setUp(self):
        super().setUp()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.copy = PackageCopy(Path(temporary.name) / 'pkg', append=BOUND_FILE)
        self.session = frozen.FROZEN_ROOT / 'journey/session.json'
        self.store = frozen.FROZEN_ROOT / 'adoption/store'
        self.handoff = frozen.FROZEN_ROOT / 'adoption/handoff'
        self.evidence = frozen.FROZEN_ROOT / 'journey/session.json.journey'

    def restore_journey(self):
        for name, entry in frozen.MANIFEST['files'].items():
            if name.startswith('journey/') and not name.endswith('/synthetic-executor/tool'):
                target = frozen.FROZEN_ROOT / name
                os.chmod(target, 0o600)  # the frozen executor files are read-only
                target.write_bytes((frozen.FIXTURES / name).read_bytes())
                os.chmod(target, int(entry['mode'], 8))

    def edit_json(self, relative, change):
        path = self.evidence / relative
        value = json.loads(path.read_text())
        change(value)
        path.write_bytes(canonical(value))


class FrozenJourneyAcrossAnUpgradeTests(UpgradedFrozenCase):
    def test_recorded_reconstruction_completes_and_reports_known_earlier_with_both_digests(self):
        progress = self.copy.run('progress', self.session, 'recorded')
        self.assertEqual(progress['verified_completed'], list(STAGES))
        self.assertIsNone(progress['invalid_at'])
        self.assertEqual(progress['next_state'], 'complete_simulation')
        self.assertFalse(progress['execution_authorized'])
        found = progress['implementation']
        self.assertEqual(found['relation'], 'known_earlier')
        self.assertEqual(found['recorded_implementation_sha256'], FROZEN_DIGEST)
        self.assertEqual(found['current_implementation_sha256'], self.copy.current_digest())
        self.assertNotEqual(found['recorded_implementation_sha256'], found['current_implementation_sha256'])
        self.assertEqual(found['bound_components'], list(protected.PROTECTED_COMPONENTS))
        self.assertIn('claim', found['recorded_implementation_basis'])
        self.assertFalse(found['current_implementation_eligible'])
        self.unchanged('journey/')

    def test_current_stops_at_the_first_implementation_bound_stage_by_keyword_and_by_default(self):
        for mode in ('current', 'default'):
            with self.subTest(mode=mode):
                progress = self.copy.run('progress', self.session, mode)
                self.assertEqual(progress['invalid_at'], 'plan')
                self.assertEqual(progress['verified_completed'], BEFORE_PLAN)
                self.assertNotIn('implementation', progress)
        self.unchanged('journey/')

    def test_display_reconstruction_is_recorded_and_the_action_check_stays_current(self):
        both = self.copy.run('reconstruct', self.session)
        self.assertEqual(both['progress']['verified_completed'], list(STAGES))
        self.assertEqual(both['progress']['implementation']['relation'], 'known_earlier')
        # Under the current implementation the frozen journey is back at plan, so planning again is the allowed action.
        self.assertIs(both['plan_action']['allowed'], True)
        self.unchanged('journey/')

    def test_existing_complete_handoff_verifies_with_its_frozen_binding_and_reports_the_relation(self):
        journal = json.loads((self.handoff / 'adoption.json').read_text())
        result = self.copy.cli('workbench', 'adopt', '--root', self.store, '--session', self.session, '--output', self.handoff)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        result = json.loads(result.stdout)
        self.assertEqual(result['status'], 'adopted_local_model')
        self.assertEqual(result['binding_sha256'], journal['binding_sha256'])
        self.assertEqual(result['implementation']['relation'], 'known_earlier')
        self.assertEqual(result['implementation']['recorded_implementation_sha256'], FROZEN_DIGEST)
        self.assertEqual(result['implementation']['current_implementation_sha256'], self.copy.current_digest())
        self.assertFalse(result['execution_authorized'])
        self.assertEqual(json.loads((self.handoff / 'adoption.json').read_text()), journal)
        self.unchanged('journey/')
        self.unchanged('adoption/handoff/')

class TamperedRecordsAreRefusedInHistoryTests(UpgradedFrozenCase):
    """Each one on its own; the unchanged frozen journey is accepted in recorded mode (the test above)."""

    def recorded(self):
        return self.copy.run('progress', self.session, 'recorded')

    def test_an_edited_receipt_is_refused_at_its_stage_including_the_terminal_one(self):
        for stage, kept in (('execute', STAGES[:STAGES.index('execute')]), ('handoff', STAGES[:-1])):
            with self.subTest(stage=stage):
                self.restore_journey()
                self.edit_json('receipts/%s.json' % stage, lambda v: v.update(cloud_authority=True))
                progress = self.recorded()
                self.assertEqual(progress['invalid_at'], stage)
                self.assertEqual(progress['verified_completed'], list(kept))
                self.assertNotEqual(progress['next_state'], 'complete_simulation')

    def test_a_binding_changed_without_its_digest_is_refused(self):
        self.edit_json('native-request.json', lambda v: v['bindings'].update(before_serial=v['bindings']['before_serial'] + 1))
        refused = self.copy.run('validate', self.session, 'recorded')
        self.assertEqual(refused['error'], 'invalid_binding')
        progress = self.recorded()
        self.assertEqual((progress['invalid_at'], progress['verified_completed']), ('plan', BEFORE_PLAN))

    def test_the_forgery_helper_is_faithful_a_current_digest_with_every_hash_recomputed_reads_as_same(self):
        # Documents the limit. Local evidence is unsigned, so a record relabelled with the current digest, with every
        # hash recomputed, is indistinguishable from a genuine one; the result names the digest as the record's claim.
        self.copy.run('forge', self.session, 'current')
        progress = self.recorded()
        self.assertEqual(progress['verified_completed'], list(STAGES))
        found = progress['implementation']
        self.assertEqual(found['relation'], 'same')
        self.assertEqual(found['recorded_implementation_sha256'], self.copy.current_digest())
        self.assertIn('claim', found['recorded_implementation_basis'])
        self.assertIn('not authentication', found['recognition_limit'])
        # And under the current implementation it simply verifies, which is why the record cannot be told apart.
        strict = self.copy.run('progress', self.session, 'current')
        self.assertEqual(strict['verified_completed'], list(STAGES))

    def test_an_unknown_digest_with_every_downstream_hash_recomputed_is_refused(self):
        self.copy.run('forge', self.session, UNKNOWN_DIGEST)
        refused = self.copy.run('validate', self.session, 'recorded')
        self.assertEqual(refused['error'], 'implementation_unknown')
        progress = self.recorded()
        self.assertEqual((progress['invalid_at'], progress['verified_completed']), ('plan', BEFORE_PLAN))
        self.assertEqual(progress['implementation']['relation'], 'unknown')
        self.assertEqual(progress['implementation']['recorded_implementation_sha256'], UNKNOWN_DIGEST)

    def test_a_changed_plan_is_refused(self):
        plan = self.evidence / 'synthetic-executor/work/plan.json'
        plan.write_bytes(plan.read_bytes() + b' ')
        self.assertEqual(self.copy.run('validate', self.session, 'recorded')['error'], 'evidence_changed')
        progress = self.recorded()
        self.assertEqual(progress['invalid_at'], 'plan')

    def test_a_changed_source_is_refused(self):
        source = Path(json.loads(self.session.read_text())['paths']['input'])
        source.write_bytes(source.read_bytes() + b'\n')
        progress = self.recorded()
        # The inventory receipt is the first to bind the source bytes; it and everything after it stop verifying.
        self.assertEqual((progress['invalid_at'], progress['verified_completed']), ('inventory', ['discovery', 'target']))


class UnknownOutcomeAcrossAnUpgradeTests(UpgradedFrozenCase):
    def reconcile(self, mode):
        return self.copy.run('reconcile', self.session, mode)

    def make_outcome_unknown(self):
        operation = self.evidence / 'operations' / OPERATION
        for name in ('03.json', '04.json'):
            (operation / name).unlink()

    def test_recorded_reconcile_reads_without_replay_and_reports_the_relation(self):
        self.make_outcome_unknown()
        before = tree(self.evidence)
        result = self.reconcile('recorded')
        self.assertEqual(result['classification'], 'desired_state_observed')
        self.assertFalse(result['replay_authorized'])
        self.assertFalse(result['execution_authorized'])
        self.assertEqual(result['implementation']['relation'], 'known_earlier')
        self.assertEqual(result['implementation']['recorded_implementation_sha256'], FROZEN_DIGEST)
        self.assertEqual(result['implementation']['current_implementation_sha256'], self.copy.current_digest())
        self.assertEqual(tree(self.evidence), before, 'reconcile wrote or replayed something')

    def test_strict_reconcile_reports_the_relation_instead_of_a_bare_unknown(self):
        self.make_outcome_unknown()
        before = tree(self.evidence)
        for mode in ('current', 'default'):
            with self.subTest(mode=mode):
                result = self.reconcile(mode)
                self.assertEqual(result['classification'], 'unknown')
                self.assertFalse(result['replay_authorized'])
                self.assertEqual(result['failure_code'], 'evidence_changed')
                self.assertIn('upgrade', result['reason'])
                self.assertEqual(result['implementation']['relation'], 'known_earlier')
        self.assertEqual(tree(self.evidence), before)

    def test_recorded_reconcile_of_an_unknown_digest_stays_unknown_and_says_why(self):
        self.copy.run('forge', self.session, UNKNOWN_DIGEST)  # the forgery needs the complete journal
        self.make_outcome_unknown()
        result = self.reconcile('recorded')
        self.assertEqual(result['classification'], 'unknown')
        self.assertEqual(result['failure_code'], 'implementation_unknown')
        self.assertEqual(result['implementation']['relation'], 'unknown')
        self.assertFalse(result['replay_authorized'])


class ExecutionIsRefusedAcrossAnUpgradeTests(unittest.TestCase):
    """A request prepared and still fresh and unconsumed, then a bound file changes."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.copy = PackageCopy(self.base / 'pkg')
        self.work = self.base / 'work'
        self.work.mkdir()

    def assert_names_the_upgrade_and_the_recovery(self, message):
        self.assertIn('upgrade', message)
        self.assertIn('current implementation', message)
        self.assertIn('Prepare the operation again', message)

    def test_approval_and_execution_refuse_with_the_upgrade_reason_and_change_nothing(self):
        self.copy.run('prepare', self.work)
        before = tree(self.work)
        self.copy.append(BOUND_FILE)
        result = self.copy.run('refuse', self.work)
        self.assertEqual(result['approve']['error'], 'evidence_changed')
        self.assert_names_the_upgrade_and_the_recovery(result['approve']['message'])
        execute = result['execute']
        self.assertEqual(execute['status'], 'rejected')
        self.assertEqual(execute['error']['code'], 'evidence_changed')
        self.assert_names_the_upgrade_and_the_recovery(execute['error']['reason'])
        self.assertEqual(tree(self.work), before, 'a refused request changed state')
        self.assertFalse((self.work / 'state').exists(), 'a journal directory was created: something was dispatched')
        self.assertFalse((self.work / 'executor/consumed.json').exists())
        self.assertFalse((self.work / 'executor/.operation-lock').exists())

    def test_a_grant_obtained_before_the_upgrade_does_not_execute_after_it(self):
        found = self.copy.run('grant_then_upgrade', self.work)
        result = found['execute']
        self.assertEqual(result['status'], 'rejected')
        self.assertEqual(result['error']['code'], 'evidence_changed')
        self.assertTrue(found['unchanged'], 'a refused execution changed state after the grant')
        self.assertFalse(found['state_dir_created'])

    def test_the_request_is_approvable_before_the_change_so_the_refusal_is_the_upgrade(self):
        # The control inside prepare approves the same request, in the same process, under the unchanged copy: the
        # request is fresh and valid, so the refusal in the tests above is the upgrade and nothing else.
        prepared = self.copy.run('prepare', self.work)
        self.assertEqual(prepared['control_approval'], 'accepted')


class NativeAtmosHistoryTests(unittest.TestCase):
    """journey_native_atmos.reconstruct: recorded accepts a recognised earlier inventory; current does not."""

    def setUp(self):
        earlier = dict(history.NATIVE_ATMOS_INVENTORY[0]['files'])
        with patch.object(jna, '_implementation', return_value=dict(earlier)):
            atmos_base.NativeAtmosReceiptTests.setUp(self)
        self.earlier = earlier
        self.current_files = dict(earlier, **{'io.py': 'c' * 64})
        patcher = patch.object(jna, '_implementation', return_value=dict(self.current_files))
        patcher.start()
        self.addCleanup(patcher.stop)

    reconstruct = atmos_base.NativeAtmosReceiptTests.reconstruct

    def rewrite(self, change, *, rehash=True):
        evidence = load_json(self.receipt)
        change(evidence)
        if rehash:
            evidence['evidence_sha256'] = digest({k: v for k, v in evidence.items() if k != 'evidence_sha256'})
        write_json(self.receipt, evidence)

    def recorded(self, report=None):
        return jna.reconstruct(self.repo, 'physical', 'policy', 'fixture-tool', self.receipt, implementation='recorded', report=report)

    def test_current_refuses_a_receipt_made_under_an_earlier_inventory(self):
        for call in (self.reconstruct,
                     lambda: jna.reconstruct(self.repo, 'physical', 'policy', 'fixture-tool', self.receipt, implementation='current')):
            with self.assertRaises(AppError):
                call()

    def test_recorded_accepts_it_returns_the_same_result_and_reports_the_relation_outside_it(self):
        report = {}
        result = self.recorded(report)
        self.assertEqual(result['status'], 'verified')
        self.assertNotIn('implementation', result)
        found = report['native_atmos']
        self.assertEqual(found['relation'], 'known_earlier')
        self.assertEqual(found['recorded_implementation_sha256'], digest(self.earlier))
        self.assertEqual(found['current_implementation_sha256'], digest(self.current_files))
        self.assertEqual(found['bound_components'], list(self.current_files))  # the consumer's own current set

    def test_an_altered_inventory_with_its_evidence_hash_recomputed_is_refused_as_unknown(self):
        self.rewrite(lambda e: e['implementation'].update({'io.py': 'd' * 64}))
        with self.assertRaises(AppError) as raised:
            self.recorded()
        self.assertEqual(raised.exception.code, 'implementation_unknown')

    def test_an_altered_inventory_without_its_hash_is_refused_by_the_hash(self):
        self.rewrite(lambda e: e['implementation'].update({'io.py': 'd' * 64}), rehash=False)
        with self.assertRaises(AppError) as raised:
            self.recorded()
        self.assertNotEqual(raised.exception.code, 'implementation_unknown')

    def test_a_relabelled_current_inventory_is_accepted_as_same_and_named_as_the_records_claim(self):
        self.rewrite(lambda e: e.update(implementation=dict(self.current_files)))
        report = {}
        self.recorded(report)
        self.assertEqual(report['native_atmos']['relation'], 'same')
        self.assertIn('claim', report['native_atmos']['recorded_implementation_basis'])

    def test_every_other_check_stays_in_recorded_mode(self):
        p = self.repo / 'stacks/physical.yaml'
        p.write_text(p.read_text().replace('value: 1', 'value: 2'))
        with self.assertRaises(AppError):
            self.recorded()
        with self.assertRaises(AppError):
            jna.reconstruct(self.repo, 'other', 'policy', 'fixture-tool', self.receipt, implementation='recorded')

    def test_an_unknown_purpose_is_refused(self):
        with self.assertRaises(ValueError):
            jna.reconstruct(self.repo, 'physical', 'policy', 'fixture-tool', self.receipt, implementation='whatever')


class AtmosStageWiringTests(unittest.TestCase):
    """The journey's atmos stage passes its purpose to the receipt reconstruction and nothing else changes."""

    def derive(self, **kwargs):
        from intune_iac import journey
        seen = {}

        def reconstruct(*args, **options):
            seen.update(options)
            return {'status': 'verified'}
        with tempfile.TemporaryDirectory() as temporary:
            state = {'atmos_executable': 'tool', 'repository': 'repo'}
            observed = {'context': {'stack': 's', 'component': 'c'}, 'fingerprints': {'target': 't'}, 'discovery': {}}
            with patch.object(jna, 'reconstruct', reconstruct):
                journey._derive_payload('atmos', Path(temporary) / 'session.json', state, observed, {}, **kwargs)
        return seen

    def test_default_is_current_and_recorded_is_passed_through(self):
        self.assertEqual(self.derive().get('implementation', 'current'), 'current')
        self.assertEqual(self.derive(implementation='current').get('implementation', 'current'), 'current')
        self.assertEqual(self.derive(implementation='recorded')['implementation'], 'recorded')


class WorkerReportsTheRelationTests(unittest.TestCase):
    """protected_worker status and reconcile report the relation; nothing is authorized because history passed.

    The upgrade is simulated in process: the protected module's current implementation files and the worker's own
    inventory change, and the table is told the old protected digest is a release (a stand-in for the entry a real
    release appends). test_pre_pin_migration and the copy tests above cover the real file change.
    """
    setUp = worker_base.ProtectedWorkerTests.setUp
    prepare = worker_base.ProtectedWorkerTests.prepare
    job = worker_base.ProtectedWorkerTests.job
    receipt = worker_base.ProtectedWorkerTests.receipt
    state = worker_base.ProtectedWorkerTests.state

    def lost_response_dispatch(self):
        self.prepare()
        original = worker.WorkerJob._apply

        def lost(job, permit):
            original(job, permit)
            raise AppError('fixture_response_lost', 'Simulated response loss after actual subprocess write.')
        with patch.object(worker.WorkerJob, '_apply', lost):
            self.assertEqual(self.job().run(self.receipt())['status'], 'outcome_unknown')

    def upgraded(self, *, recognised=True, worker_recognised=False):
        """recognised: the protected inventory holds the recorded digest. worker_recognised: the worker inventory holds
        the job's recorded worker files (a release registers both). The branch registers its own current digests, so
        the current files are first taken out of both inventories: the job below was prepared under them."""
        recorded_files = protected._implementation_files()
        recorded = history.protected_digest(recorded_files)
        recorded_worker = worker._implementation()
        inventory = tuple(e for e in history.PROTECTED_INVENTORY if e['files'] != recorded_files)
        if recognised:
            inventory = inventory + ({'label': 'test-release', 'implementation_sha256': recorded, 'files': recorded_files},)
        worker_inventory = tuple(e for e in history.WORKER_INVENTORY if e['files'] != recorded_worker)
        if worker_recognised:
            worker_inventory = worker_inventory + ({'label': 'test-release', 'files': recorded_worker},)
        stack = [patch.object(protected, '_implementation_files', return_value=dict(recorded_files, **{'io.py': 'c' * 64})),
                 patch.object(worker, '_implementation', return_value=dict(recorded_worker, **{'protected.py': 'f' * 64})),
                 patch.object(history, 'PROTECTED_INVENTORY', inventory),
                 patch.object(history, 'WORKER_INVENTORY', worker_inventory)]
        for item in stack:
            item.start()
            self.addCleanup(item.stop)
        return recorded

    def test_status_across_an_upgrade_reports_the_relation_beside_the_invalidated_execution(self):
        self.prepare()
        recorded = self.upgraded()
        status = self.job().status()
        self.assertEqual(status['execution_validation']['status'], 'invalidated')
        self.assertEqual(status['execution_validation']['failure_code'], 'worker_implementation_changed')
        found = status['implementation']
        self.assertEqual(found['relation'], 'known_earlier')
        self.assertEqual(found['recorded_implementation_sha256'], recorded)
        self.assertNotEqual(found['current_implementation_sha256'], recorded)
        self.assertFalse(status['retry_authorized'])
        self.assertFalse(status['production_authorized'])

    def test_status_without_an_upgrade_reports_same(self):
        self.prepare()
        self.assertEqual(self.job().status()['implementation']['relation'], 'same')

    def test_reconcile_after_an_unknown_outcome_observes_only_and_reports_the_relation(self):
        self.lost_response_dispatch()
        after = self.state()
        recorded = self.upgraded(worker_recognised=True)
        result = self.job().reconcile()
        self.assertTrue(result['desired_state_observed'])
        self.assertFalse(result['execution_confirmed'])
        self.assertFalse(result['retry_authorized'])
        self.assertEqual(result['implementation']['relation'], 'known_earlier')
        self.assertEqual(result['implementation']['recorded_implementation_sha256'], recorded)
        self.assertEqual(self.state(), after, 'reconcile changed the target')
        status = self.job().status()
        self.assertEqual(status['mutation_attempts'], 1)
        event = [e for e in status['events'] if e['kind'] == 'reconciliation_observed'][-1]
        self.assertEqual(event['payload']['implementation']['relation'], 'known_earlier')
        with self.assertRaises(AppError):
            self.job().run(self.receipt())
        self.assertEqual(self.job().status()['mutation_attempts'], 1)
        self.assertEqual(self.state(), after)

    def test_reconcile_of_an_unrecognised_implementation_refuses_and_writes_no_event(self):
        self.lost_response_dispatch()
        self.upgraded(recognised=False)
        before = len(self.job().status()['events'])
        with self.assertRaises(AppError) as raised:
            self.job().reconcile()
        self.assertEqual(raised.exception.code, 'implementation_unknown')
        self.assertEqual(len(self.job().status()['events']), before)

    def test_recorded_reconcile_refuses_unpinned_worker_only_drift(self):
        # A known protected upgrade must not waive the comparison of the worker's own bound files (review F2).
        self.lost_response_dispatch()
        self.upgraded()  # the protected relation becomes known_earlier; the worker files are not registered
        changed = dict(worker._implementation(), **{'provider_execution.py': 'e' * 64})
        with patch.object(worker, '_implementation', return_value=changed):
            with self.assertRaises(AppError) as raised:
                self.job().reconcile()
        self.assertEqual(raised.exception.code, 'worker_implementation_changed')

    def test_recorded_reconcile_accepts_a_registered_worker_release(self):
        self.lost_response_dispatch()
        self.upgraded(worker_recognised=True)
        recorded = worker._implementation()  # the patched current set; the job recorded the real files
        events = len(self.job().status()['events'])
        drifted = dict(recorded, **{'provider_execution.py': 'e' * 64})
        with patch.object(worker, '_implementation', return_value=drifted):
            result = self.job().reconcile()  # the recorded files are a registered release: observation only
        self.assertEqual(result['implementation']['worker_relation'], 'known_earlier')
        self.assertEqual(len(self.job().status()['events']), events + 1)

    def worker_relation(self, registered):
        self.prepare()
        if registered is not None:
            self.upgraded(worker_recognised=registered)
        return self.job().status()['implementation']['worker_relation']

    def test_status_reports_the_worker_relation_same(self):
        self.assertEqual(self.worker_relation(None), 'same')

    def test_status_reports_the_worker_relation_unknown_when_unregistered(self):
        self.assertEqual(self.worker_relation(False), 'unknown')

    def test_status_reports_the_worker_relation_known_earlier_when_registered(self):
        self.assertEqual(self.worker_relation(True), 'known_earlier')

    def test_a_changed_worker_file_with_the_same_protected_digest_still_refuses_reconcile(self):
        self.lost_response_dispatch()
        recorded = worker._implementation()
        unregistered = tuple(e for e in history.WORKER_INVENTORY if e['files'] != recorded)
        for patcher in (patch.object(worker, '_implementation', return_value=dict(recorded, **{'io.py': 'f' * 64})),
                        patch.object(history, 'WORKER_INVENTORY', unregistered)):
            patcher.start()
            self.addCleanup(patcher.stop)
        with self.assertRaises(AppError) as raised:
            self.job().reconcile()
        self.assertEqual(raised.exception.code, 'worker_implementation_changed')


class ApprovalChecksTheImplementationFirstTests(unittest.TestCase):
    """Both approvals look at the implementation before any read of the executor (review F3)."""

    def refused(self, approve, make_executor):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'executor'
            synthetic = protected.create_synthetic_executor(root, initial_value={'a': 1}, desired_value={'a': 2})
            request = protected.prepare_native_operation(synthetic)
            write_json(root / 'consumed.json', {'present': True})
            executor = synthetic if make_executor is None else object.__new__(make_executor)
            executor.root = root
            changed = dict(protected._implementation_files(), **{'io.py': 'c' * 64})
            with patch.object(protected, '_implementation_files', return_value=changed):
                with self.assertRaises(AppError) as raised:
                    approve(request, executor=executor)
            return raised.exception

    def test_synthetic_approval_names_the_upgrade_before_it_reports_consumption(self):
        error = self.refused(protected.approve_synthetic_operation, None)
        self.assertEqual(error.code, 'evidence_changed')
        self.assertIn('upgrade', error.message)

    def test_native_approval_names_the_upgrade_before_it_reports_consumption(self):
        error = self.refused(protected.approve_native_local_operation, protected.NativeLocalExecutor)
        self.assertEqual(error.code, 'evidence_changed')
        self.assertIn('upgrade', error.message)

    def test_with_the_same_implementation_a_consumed_approval_is_still_reported_as_consumed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'executor'
            executor = protected.create_synthetic_executor(root, initial_value={'a': 1}, desired_value={'a': 2})
            request = protected.prepare_native_operation(executor)
            write_json(root / 'consumed.json', {'present': True})
            with self.assertRaises(AppError) as raised:
                protected.approve_synthetic_operation(request, executor=executor)
            self.assertEqual(raised.exception.code, 'approval_already_consumed')


class ProtectedPurposeWiringTests(unittest.TestCase):
    """Which purpose each protected entry point gives the shared validation (no native binary needed)."""

    def purposes(self, make_executor, call):
        executor = object.__new__(make_executor)
        executor.root = Path('/nonexistent-executor')
        seen = []

        def spy(request, executor, **options):
            seen.append(options.get('implementation', 'current'))
            raise RuntimeError('stop at the first validation')

        def gate_spy(request, implementation):
            seen.append('gate:' + implementation)
            return request
        with patch.object(protected, '_validate_request', spy), patch.object(protected, '_implementation_gate', gate_spy):
            try:
                call(executor)
            except RuntimeError:
                pass
        return seen

    def test_approval_execution_and_a_new_second_plan_validate_the_current_implementation(self):
        # An approval checks the implementation first (the gate), then validates the whole request.
        self.assertEqual(self.purposes(protected.SyntheticExecutor, lambda e: protected.approve_synthetic_operation({}, executor=e)),
                         ['gate:current', 'current'])
        self.assertEqual(self.purposes(protected.NativeLocalExecutor, lambda e: protected.approve_native_local_operation({}, executor=e)),
                         ['gate:current', 'current'])
        self.assertEqual(self.purposes(protected.SyntheticExecutor,
                                       lambda e: protected.execute_native_operation({}, '/nonexistent-state', executor=e, approval=None)), ['current'])
        self.assertEqual(self.purposes(protected.NativeLocalExecutor, lambda e: protected.verify_native_convergence(e, {})), ['current'])

    def test_persisted_convergence_reconstruction_takes_the_purpose_and_defaults_to_current(self):
        self.assertEqual(self.purposes(protected.NativeLocalExecutor, lambda e: protected.reconstruct_native_convergence(e, {}, {})), ['current'])
        self.assertEqual(self.purposes(protected.NativeLocalExecutor,
                                       lambda e: protected.reconstruct_native_convergence(e, {}, {}, implementation='recorded')), ['recorded'])


class PurposeIsExplicitTests(unittest.TestCase):
    def test_an_unknown_purpose_is_refused_never_treated_as_current_or_recorded(self):
        with self.assertRaises(ValueError):
            protected.validate_native_operation({}, executor=None, implementation='whatever')

    def test_history_never_judges_an_approval_window(self):
        with self.assertRaises(ValueError):
            protected.validate_native_operation({}, executor=None, require_fresh=True, implementation='recorded')


if __name__ == '__main__':
    unittest.main()
