#!/usr/bin/env python3
"""Independent R3 connected CLI/PTY journey; no product modules in assertions.

The retained independent R2 oracle provides literal semantics and corruption
controls. Actual product commands perform all actions. A separate fixture child
uses only the GET capture API with injected responses, never a live credential.
Raw service files and SQLite are independently read. This is a cooperative
Linux laboratory, not host isolation, authenticated Graph, device or production
qualification. Every invocation creates new evidence and preserves failures.
"""
from __future__ import annotations
import argparse
import copy
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pty
import select
import shlex
import signal
import sqlite3
import struct
import subprocess
import sys
import termios
import time
import traceback

FIXTURE_ROOT = Path(__file__).resolve().parents[1]
PROJECT = FIXTURE_ROOT
SPEC = importlib.util.spec_from_file_location('retained_independent_workbench_oracle', PROJECT / 'scripts/qualify-workbench.py')
old = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(old)
T, P, Q, D = old.TENANT, old.POLICY, old.UNRELATED, old.DEFINITION
read, dump, exact = old.read, old.dump, old.exact


def canon(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def digest(value):
    return hashlib.sha256(canon(value)).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def one_estate(value=None):
    return {'schema_version': 'intune-semantic-estate/1.0', 'tenant_id': T, 'cloud': 'public',
            'objects': {P: old.expected_policy(value)}}


def tree_hashes(root):
    return {str(p.relative_to(root)): file_hash(p) for p in sorted(root.rglob('*')) if p.is_file()}


class Run(old.Run):
    def __init__(self, root, python):
        old.PROJECT = PROJECT
        self.root, self.python = root, python
        self.root.mkdir(mode=0o700, parents=True, exist_ok=False)
        self.checker = Path(__file__).resolve()
        self.results = {'status':'RUNNING', 'started_at':time.time(), 'python':sys.version,
            'product_root':str(PROJECT), 'fixture_root':str(FIXTURE_ROOT), 'checks':[], 'commands':[],
            'limitations':['Cooperative same-user Linux laboratory; no hostile-process isolation'],
            'checker':{'path':str(self.checker),'sha256':file_hash(self.checker)},
            'source_sha256':{str(p.relative_to(PROJECT)):file_hash(p) for p in
                [PROJECT/'scripts/intune-iac.py', *sorted((PROJECT/'intune_iac').glob('*.py'))]},
            'fixture_sha256':{str(p.relative_to(FIXTURE_ROOT)):file_hash(p) for p in
                [FIXTURE_ROOT/'examples/supported/input/export.json', FIXTURE_ROOT/'examples/context.json']}}
        self.store = root / 'store'
        self.results['schema_version'] = 'workbench-connected-independent-qualification/1.0'
        self.results['evidence_class'] = 'modeled_wizard_adoption_maintenance_actual_CLI_PTY_raw_SQL_oracles'
        self.results['checker_dependencies'] = {str(Path(__file__).resolve()): file_hash(__file__),
            str(FIXTURE_ROOT / 'scripts/qualify-workbench.py'): file_hash(FIXTURE_ROOT / 'scripts/qualify-workbench.py')}
        self.results['limitations'] += ['PTY coverage is Linux xterm; not native Windows/Git Bash/PowerShell/macOS',
            'Capture input uses injected GET responses, not an authenticated Graph endpoint',
            'Real terminal SIGINT is distinct from modeled post-commit lost response',
            'No live service, endpoint, GitHub/Azure workflow or organizational approval is inferred']
        self.save()

    def command(self, *args, stdin=None, allowed=(0,), structured=True, timeout=120):
        argv = [self.python, '-B', str(PROJECT / 'scripts/intune-iac.py'), *map(str, args)]
        return self.process(argv, stdin=stdin, allowed=allowed, structured=structured, timeout=timeout)

    def cli(self, *args, stdin=None, allowed=(0,)):
        return self.command('workbench', *args, stdin=stdin, allowed=allowed, structured=stdin is None)

    def process(self, argv, *, stdin=None, allowed=(0,), structured=True, timeout=120):
        index = len(self.results['commands']) + 1
        started = time.time()
        value = subprocess.run(argv, input=stdin, text=True, capture_output=True, cwd=PROJECT,
            env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONPATH': str(PROJECT)}, timeout=timeout)
        prefix = '%03d-command' % index
        (self.root / (prefix + '.stdout')).write_text(value.stdout)
        (self.root / (prefix + '.stderr')).write_text(value.stderr)
        self.results['commands'].append({'argv': argv, 'stdin': stdin, 'returncode': value.returncode,
            'stdout': prefix + '.stdout', 'stderr': prefix + '.stderr', 'seconds': time.time() - started})
        self.save()
        if value.returncode not in allowed:
            raise AssertionError('%s exit %s: %s %s' % (prefix, value.returncode, value.stderr[-1500:], value.stdout[-1500:]))
        return json.loads(value.stdout or value.stderr) if structured else value.stdout

    def db(self, query, args=(), store=None):
        path = (store or self.store) / 'observations.sqlite3'
        with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute(query, args)]

    def head(self, store=None):
        rows = self.db('SELECT s.body_json FROM object_heads h JOIN observations o USING(observation_id) '
                       'JOIN snapshots s USING(snapshot_id) WHERE h.object_id=? AND h.present=1', (P,), store)
        exact(1, len(rows)); return json.loads(rows[0]['body_json'])

    def pty(self, store, service, commands, *, columns=100, resize_at=None):
        argv = [self.python, '-B', str(PROJECT / 'scripts/intune-iac.py'), 'workbench', 'terminal', '--root', str(store)]
        if service is not None: argv += ['--service-root', str(service)]
        master, slave = pty.openpty()
        baseline = termios.tcgetattr(slave)
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 24, columns, 0, 0))
        process = subprocess.Popen(argv, stdin=slave, stdout=slave, stderr=slave, cwd=PROJECT,
            env={**os.environ, 'TERM': 'xterm', 'PYTHONDONTWRITEBYTECODE': '1'}, start_new_session=True)
        output = bytearray(); sent = prompts_seen = 0; resized = False
        started = time.time(); deadline = time.monotonic() + 120
        log = '%03d-connected-pty.stdout' % (len(self.results['commands']) + 1)
        restored = False
        try:
            while time.monotonic() < deadline:
                ready, _, _ = select.select([master], [], [], .05)
                if ready:
                    block = os.read(master, 65536)
                    if not block: break
                    output.extend(block)
                    if len(output) > 8 * 1024 * 1024: raise AssertionError('PTY output bound exceeded')
                    prompts = output.count(b'workbench> ')
                    if prompts > prompts_seen and sent < len(commands):
                        if resize_at is not None and sent == resize_at:
                            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 17, 43, 0, 0))
                            os.kill(process.pid, signal.SIGWINCH); resized = True
                        command = commands[sent]
                        if command == '<SIGINT>': os.kill(process.pid, signal.SIGINT)
                        elif command == '<EOF>': os.write(master, b'\x04')
                        else: os.write(master, (command + '\n').encode('utf-8'))
                        sent += 1; prompts_seen = prompts
                if process.poll() is not None and not ready: break
            code = process.wait(timeout=max(0.0, deadline - time.monotonic()))
            restored = termios.tcgetattr(slave) == baseline
        finally:
            if process.poll() is None:
                process.kill(); process.wait(timeout=2)
            os.close(master); os.close(slave)
            (self.root / log).write_bytes(output)
            self.results['commands'].append({'argv': argv, 'mode': 'actual_PTY', 'term': 'xterm',
                'initial_columns': columns, 'resized_to_columns': 43 if resized else None,
                'commands': commands, 'commands_sent': sent, 'returncode': process.returncode,
                'terminal_attributes_restored': restored, 'seconds': time.time() - started, 'stdout': log})
            self.save()
        exact(2 if '<SIGINT>' in commands else 0, code); exact(len(commands), sent); exact(True, restored)
        if resize_at is not None: exact(True, resized)
        return output.decode('utf-8')

    def source_end(self):
        super().source_end()
        for path, checksum in self.results['checker_dependencies'].items():
            exact(checksum, file_hash(path))


def contains(text, tokens):
    compact = text.replace('\r', '').replace('\n', '')
    for token in tokens:
        if token not in compact: raise AssertionError('Terminal omitted literal token ' + repr(token))
    return {'tokens': tokens}


def observed_model(service, value=None):
    snapshot = read(service / 'service.json')
    old.semantic_estate(one_estate(value), snapshot['current'])
    return snapshot


def patch_count(service):
    return sum(row['method'] == 'PATCH' for row in read(service / 'service.json')['requests'])


def capture_fixture(run, directory, *, denied=False):
    # Fixture generation is explicitly a different child process. The grader
    # does not import its product parser/normalizer or derive expected semantics.
    worker = r'''
import copy,json,sys
from pathlib import Path
from intune_iac.capture import capture
fixture=json.loads(Path(sys.argv[1]).read_text()); denied=sys.argv[3]=='denied'
responses={p['request_url']:(p['http_status'],copy.deepcopy(p['body'])) for c in fixture['collections'] for p in c['pages']}
for url, (status, body) in responses.items():
    if url.endswith('/assignments'):
        for row in body['value']: row.update(source='direct',sourceId=None)
def transport(url):
    if denied and url.endswith('/assignments'): return 403,b'{"error":{"message":"RAW-ONLY-ERROR-CANARY"}}'
    status,body=responses[url]; return status,json.dumps(body).encode()
print(json.dumps(capture('11111111-1111-4111-8111-111111111111','22222222-2222-4222-8222-222222222222',sys.argv[2],transport=transport)))
'''
    worker_path = run.root / ('capture-fixture-denied.py' if denied else 'capture-fixture.py')
    worker_path.write_text(worker)
    run.process([run.python, '-B', str(worker_path), str(FIXTURE_ROOT / 'examples/supported/input/export.json'),
                 str(directory), 'denied' if denied else 'complete'])


def evidence_inputs(run):
    stamp = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    doc = {'schema_version':'1.0.0','synthetic':True,'as_of':stamp,'freshness_seconds':3600,
      'cohort':{'version':'independent-r3','eligible_ids':['device-%d'%i for i in range(100)],
                'targeted_ids':['device-%d'%i for i in range(100)],'excluded_ids':[]},
      'rows':[{'id':'row-%d'%i,'device_id':'device-%d'%i,'stage':'execution','status':'success',
               'observed_at':stamp,'source_file':'local.json','source_pointer':'/%d'%i,
               'coverage':'complete','synthetic':True} for i in range(8)],
      'capture':{'timezone':'UTC','clock_skew_seconds':None,'logging_enabled':None,'truncated':False,'access_errors':[]},
      'promotion_thresholds':{'min_reporting_ratio':1,'min_success_ratio':1}}
    path = run.root / "device evidence café 'one'.json"
    dump(path, {'schema_version':'workbench-device-evidence/1','tenant_id':T,'object_id':P,'evidence':doc})
    return path


def legacy_store(path):
    """Reviewed literal V1 fixture schema, independent from current product SQL."""
    path.mkdir(mode=0o700)
    db_path = path / 'observations.sqlite3'; db_path.touch(mode=0o600)
    with sqlite3.connect(db_path) as db:
        db.executescript('''
                BEGIN IMMEDIATE;
                CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE collection_runs(run_id INTEGER PRIMARY KEY, tenant_id TEXT NOT NULL,
                    started_at REAL NOT NULL, observed_at REAL NOT NULL, completed_at REAL,
                    status TEXT NOT NULL, coverage TEXT NOT NULL, error_code TEXT, object_count INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE snapshots(snapshot_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
                    object_id TEXT NOT NULL, body_json TEXT NOT NULL);
                CREATE TABLE observations(observation_id INTEGER PRIMARY KEY,
                    run_id INTEGER NOT NULL REFERENCES collection_runs(run_id),
                    snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id),
                    tenant_id TEXT NOT NULL, object_id TEXT NOT NULL, observed_at REAL NOT NULL, source_json TEXT NOT NULL,
                    UNIQUE(run_id, object_id));
                CREATE INDEX observation_history ON observations(tenant_id,object_id,observed_at);
                CREATE TABLE relationships(snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id),
                    relation TEXT NOT NULL,target_id TEXT NOT NULL,details_json TEXT NOT NULL,
                    PRIMARY KEY(snapshot_id,relation,target_id,details_json));
                CREATE TABLE deployments(run_id INTEGER PRIMARY KEY REFERENCES collection_runs(run_id), data_json TEXT NOT NULL);
                CREATE TABLE operations(sequence INTEGER PRIMARY KEY, operation_id TEXT NOT NULL,
                    object_id TEXT, data_json TEXT NOT NULL, recorded_at REAL NOT NULL);
                PRAGMA user_version=1;
                COMMIT;
            ''')
        db.execute('INSERT INTO metadata VALUES(?,?)', ('tenant_id', T))
        moment=time.time()-3600; body=old.expected_policy(); snapshot=digest({'tenant_id':T,'object_id':P,'body':body})
        db.execute('INSERT INTO collection_runs VALUES(?,?,?,?,?,?,?,?,?)',(1,T,moment,moment,moment,'complete','complete',None,1))
        db.execute('INSERT INTO snapshots VALUES(?,?,?,?)',(snapshot,T,P,json.dumps(body)))
        db.execute('INSERT INTO observations VALUES(?,?,?,?,?,?,?)',(1,1,snapshot,T,P,moment,'{}'))
    return db_path


def qualify(run):
    root, store = run.root, run.store
    paths = root / "paths café 'quote' space"; paths.mkdir(mode=0o700)
    run.check('retained_literal_oracle_negative_controls', old.negative_controls)
    session = paths / 'wizard session.json'; generated = paths / 'generated'
    repo=paths/'existing repository';(repo/'stacks').mkdir(parents=True,mode=0o700)
    (repo/'components/terraform/intune-reference').mkdir(parents=True,mode=0o700)
    (repo/'atmos.yaml').write_text('stacks:\n  base_path: stacks\n  included_paths: ["reference-dev"]\ncomponents:\n  terraform:\n    base_path: components/terraform\n    command: tofu\n')
    (repo/'stacks/defaults.yaml').write_text('vars:\n  region: inherited\n')
    (repo/'stacks/reference-dev.yaml').write_text('import: [defaults]\ncomponents:\n  terraform:\n    intune-reference:\n      vars:\n        region: local\n        approved: false\n')
    original_repo=tree_hashes(repo)
    answers = ['continue'] * 3 + [P] + ['continue'] * 4 + ['generate'] + ['continue'] * 2 + ['plan','approve','execute','reconcile','continue','finish']
    wizard = run.command('wizard','--journey','--session',session,'--input',FIXTURE_ROOT/'examples/supported/input/export.json',
        '--context',FIXTURE_ROOT/'examples/context.json','--output',generated,'--repo',repo,stdin='\n'.join(answers)+'\n',structured=False)
    run.check('completed_actual_wizard', lambda: exact('complete_simulation', read(session)['lifecycle']))
    journey = Path(str(session) + '.journey'); frozen_journey = tree_hashes(journey)
    frozen_generated = tree_hashes(generated)
    run.cli('init','--root',store,'--tenant',T)
    preview = run.cli('adoption-preview','--root',store,'--session',session)
    run.check('preview_never_publishes_observations', lambda: exact([], run.db('SELECT * FROM observations')))
    terminal = run.pty(store, None, ['adoption-preview '+shlex.quote(str(session)),
        'adopt '+shlex.quote(str(session))+' '+shlex.quote(str(paths/'handoff')),'select '+P,'adoption-lineage','lineage /vars/region','history','back','cancel','quit'])
    run.check('actual_terminal_adoption_and_lineage', lambda: contains(terminal, ['adopted_local_model','adoption','selection_cleared']))
    # Obtain the bound maintenance model from the persisted adoption artifact,
    # without projecting model semantics or trusting terminal presentation.
    lineage = run.cli('adoption-lineage','--root',store,'--object',P)
    repository_lineage=run.cli('lineage','--root',store,'--object',P,'--pointer','/vars/region')
    field=repository_lineage['fields'][0]
    run.check('literal_repository_override_winner',lambda: exact(('stacks/reference-dev.yaml','/components/terraform/intune-reference/vars/region',6),
        (field['winner']['path'],field['winner']['pointer'],field['winner']['line'])))
    run.check('literal_repository_inheritance_history',lambda: exact(['stacks/defaults.yaml','stacks/reference-dev.yaml'],[row['path'] for row in field['history']]))
    run.check('lineage_is_value_free_and_not_native_atmos_authority',lambda: exact((False,False),
        (repository_lineage['effective_values_included'],repository_lineage['native_atmos_qualified'])))
    service = paths / 'handoff/service'
    run.check('adoption_raw_service_equals_literal_selected_policy', lambda: observed_model(service))
    run.check('adoption_raw_sql_snapshot_equals_literal', lambda: exact(old.expected_policy(), run.head()))
    inspected = run.cli('inspect','--root',store,'--object',P)
    run.check('reopened_inspection_matches_raw_sql', lambda: exact(run.head(), inspected['body']))
    initial_history = run.db('SELECT * FROM observations WHERE object_id=? ORDER BY observation_id',(P,))
    run.check('adoption_persisted_history', lambda: exact(1, len(initial_history)))
    desired = paths / 'desired change.json'; dump(desired, old.expected_policy(D+'_1'))
    operation = paths / 'maintenance operation'
    terminal = run.pty(store, service, ['select '+P,'propose '+shlex.quote(str(desired))+' '+shlex.quote(str(operation)),
        'review '+shlex.quote(str(operation)),'quit'])
    run.check('actual_terminal_proposal_review', lambda: contains(terminal,['settings_changed','approval_digest']))
    review = run.cli('review','--operation',operation)
    run.check('exact_review_digest_is_raw_canonical_plan', lambda: exact(digest(read(operation/'plan.json')),review['approval_digest']))
    run.check('only_intended_setting_change_reviewed', lambda: exact([P+':settings_changed'],review['changes']))
    denied = run.cli('execute','--operation',operation,'--approve-digest','0'*64,allowed=(3,))
    run.check('wrong_approval_rejected_before_write', lambda: exact('maintenance_approval_required',denied['error']['code']))
    run.check('no_patch_before_exact_approval', lambda: exact(0,patch_count(service)))
    terminal = run.pty(store, service, ['execute '+shlex.quote(str(operation))+' '+review['approval_digest'],'quit'])
    run.check('actual_terminal_exact_protected_execute', lambda: contains(terminal,['succeeded_verified']))
    run.check('independent_raw_model_intended_change_only',lambda: observed_model(service,D+'_1'))
    run.cli('collect','--root',store,'--service-root',service)
    run.check('independent_sql_readback_changed_only_setting',lambda: exact(old.expected_policy(D+'_1'),run.head()))
    second = run.cli('propose','--root',store,'--service-root',service,'--object',P,'--desired',desired,'--output',paths/'no change')
    run.check('second_plan_no_change',lambda: old.assert_no_change(second))
    # Explicit lost-response plus delayed service visibility. Exactly one new
    # committed PATCH; every reconciliation uses fresh GET, never a retry write.
    recovery_desired = paths/'recovery desired.json'; dump(recovery_desired,old.expected_policy(D+'_0'))
    recovery = paths/'recovery operation'
    run.cli('propose','--root',store,'--service-root',service,'--object',P,'--desired',recovery_desired,'--output',recovery)
    recovery_review = run.cli('review','--operation',recovery)
    lost = run.cli('execute','--operation',recovery,'--approve-digest',recovery_review['approval_digest'],
        '--fault','lost-response','--visibility-delay-reads','2',allowed=(3,))
    run.check('postcommit_response_loss_remains_unknown',lambda: exact('outcome_unknown',lost['status']))
    run.check('raw_committed_service_changed_despite_response_loss',lambda: observed_model(service,D+'_0'))
    patches = patch_count(service); run.check('exactly_two_total_writes',lambda: exact(2,patches))
    run.check('unknown_execution_does_not_publish_unobserved_database_state',lambda: exact(old.expected_policy(D+'_1'),run.head()))
    reconciliations=[]
    for index in range(3):
        result=run.cli('reconcile','--operation',recovery,allowed=(0,2,3));reconciliations.append(result)
        if index<2:
            run.check('pending_read_%d_retains_uncertain_journal'%(index+1),lambda: exact('outcome_unknown',read(recovery/'journal.json')['status']))
            run.check('pending_read_%d_retains_visibility_pending'%(index+1),lambda: exact(('visibility_pending',True,False),
                (result['second_plan']['status'],result['visibility']['pending'],result['replay_authorized'])))
            run.check('pending_read_%d_returns_literal_prior_state'%(index+1),lambda: old.semantic_estate(one_estate(D+'_1'),result['observed_estate']))
    run.check('first_delayed_read_does_not_close_uncertainty',lambda: exact('matches_precondition',reconciliations[0]['classification']))
    run.check('second_delayed_read_does_not_close_uncertainty',lambda: exact('matches_precondition',reconciliations[1]['classification']))
    run.check('eventual_fresh_read_resolves',lambda: exact('desired_state_observed',reconciliations[2]['classification']))
    run.check('eventual_visibility_proves_no_change_second_plan',lambda: exact(('no_change',False,'reconciled'),
        (reconciliations[2]['second_plan']['status'],reconciliations[2]['visibility']['pending'],read(recovery/'journal.json')['status'])))
    replay = run.cli('execute','--operation',recovery,'--approve-digest',recovery_review['approval_digest'],allowed=(3,))
    run.check('mutation_replay_rejected',lambda: exact('maintenance_replay_forbidden',replay['error']['code']))
    run.check('all_recovery_reads_preserve_exact_patch_count',lambda: exact(patches,patch_count(service)))
    old_head = run.head(); old_count = len(run.db('SELECT * FROM observations'))
    denied = run.cli('collect','--root',store,'--service-root',service,'--fault','deny',allowed=(0,2))
    run.check('denied_collection_retains_last_good_bytes',lambda: exact(old_head,run.head()))
    run.check('denied_collection_never_publishes_empty_estate',lambda: exact(old_count,len(run.db('SELECT * FROM observations'))))
    run.check('denied_collection_marks_stale',lambda: exact('stale',run.cli('inspect','--root',store,'--object',P)['freshness']))
    # Finite scheduler is executed only after the prior PTY process has exited.
    job = paths/'closed terminal schedule'
    scheduled_terminal = run.pty(store,service,['schedule-create '+shlex.quote(str(job))+' 0.1','quit'])
    run.check('actual_terminal_schedule_created_before_closure',lambda: contains(scheduled_terminal,['job_id','synthetic']))
    schedule = run.cli('schedule-run','--job',job,'--max-runs','2','--max-duration-seconds','10')
    run.check('closed_terminal_schedule_restores_fresh_model',lambda: exact(old.expected_policy(D+'_0'),run.head()))
    state = read(job/'state.json')
    run.check('finite_scheduler_two_successes',lambda: exact((2,2,0),(state['run_count'],state['success_count'],state['failure_count'])))
    terminal = run.pty(store,service,['select '+P,'inspect','history','health','collection-history','operations','schedule-status '+shlex.quote(str(job)),'schedule-run '+shlex.quote(str(job))+' 1 10','back','cancel','quit'],resize_at=3)
    run.check('resize_reopen_history_health',lambda: contains(terminal,['history_persisted','rollout_ready','unknown','selection_cleared']))
    before_interrupt = file_hash(service/'service.json')
    interrupted = run.pty(store,service,['select '+P,'<SIGINT>'])
    run.check('actual_sigint_terminal_restored',lambda: contains(interrupted,['interrupted']))
    ended = run.pty(store,service,['<EOF>'])
    run.check('actual_eof_terminal_restored',lambda: contains(ended,['history_persisted']))
    run.check('navigation_interruptions_dispatch_no_mutation',lambda: exact(before_interrupt,file_hash(service/'service.json')))
    extended_routes(run,paths,service,operation)
    run.check('completed_wizard_receipt_tree_preserved',lambda: exact(frozen_journey,tree_hashes(journey)))
    run.check('generated_adoption_source_tree_preserved',lambda: exact(frozen_generated,tree_hashes(generated)))
    run.check('original_literal_repository_bytes_preserved',lambda: exact(original_repo,tree_hashes(repo)))
    run.check('frozen_source_and_both_independent_checkers_unchanged',run.source_end)


def extended_routes(run, paths, service, operation):
    store = paths/'capture store'; run.cli('init','--root',store,'--tenant',T)
    captured = paths/"captured café 'one'"; denied = paths/'denied capture'
    capture_fixture(run,captured); capture_fixture(run,denied,denied=True)
    device = evidence_inputs(run)
    fixture = read(FIXTURE_ROOT/'examples/supported/input/export.json')
    reference_body = copy.deepcopy(fixture['collections'][0]['pages'][0]['body']['value'][0])
    reference_body.update(id='99999999-9999-4999-8999-999999999999', name='Independent community reference',
        description='OIBID:88888888-8888-4888-8888-888888888888 Reference\x1b]52;c;CONTROL-CANARY\x07\u202e',settings=copy.deepcopy(fixture['collections'][1]['pages'][0]['body']['value']))
    reference = paths/"reference café 'one'.json"; dump(reference,reference_body)
    terminal = run.pty(store,None,['import-capture '+shlex.quote(str(captured)),'select '+P,'inspect','settings','relationships',
        'device-evidence-import '+shlex.quote(str(device)),'health','reference-import '+shlex.quote(str(reference))+' '+file_hash(reference)+' '+'a'*40+' https://example.invalid/policy.json CC0-1.0',
        'references','dictionary letappsaccesslocation','collection-history','collection 1','back','cancel','quit'])
    run.check('all_capture_device_reference_routes_reached',lambda: contains(terminal,['graph_capture_unverified','source_reference','device_evidence','collection','selection_cleared']))
    run.check('captured_literal_policy_independent_sql',lambda: exact(old.expected_policy(),run.head(store)))
    run.check('control_payload_not_rendered_as_terminal_control',lambda: exact(False,any(c in terminal for c in ('\x1b','\x07','\u202e'))))
    artifacts = run.db('SELECT kind,data_json,artifact_id FROM artifacts ORDER BY sequence',store=store)
    reference_row = next(row for row in artifacts if row['kind']=='source_reference')
    run.check('raw_reference_control_bytes_preserved_as_evidence',lambda: exact(True,'\\u001b' in reference_row['data_json']))
    snapshot = run.db('SELECT snapshot_id FROM observations ORDER BY observation_id',store=store)[-1]['snapshot_id']
    workflow = paths/"workflow café 'one'.json"
    dump(workflow,{'schema_version':'workbench-workflow-run/1','tenant_id':T,'object_id':P,
        'run_url':'https://github.com/example/repo/actions/runs/42','repository_revision':'b'*40,'run_id':'42','status':'success',
        'observed_at':datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),'observed_after':snapshot})
    terminal = run.pty(store,None,['select '+P,'reference-compare '+reference_row['artifact_id'],
        'workflow-import '+shlex.quote(str(workflow)),'workflows','relationships','import-capture '+shlex.quote(str(denied)),
        'inspect','history','collection-history','collection 2','back','cancel','quit'],resize_at=4)
    run.check('reference_workflow_denied_capture_terminal_routes',lambda: contains(terminal,['automatic_overwrite','workflow_run','caller_asserted','denied','stale']))
    run.check('raw_error_payload_never_exposed_in_terminal',lambda: exact(False,'RAW-ONLY-ERROR-CANARY' in terminal))
    run.check('failed_capture_preserves_prior_body',lambda: exact(old.expected_policy(),run.head(store)))
    health = run.cli('health','--root',store,'--object',P); stage = health['stages']['execution']
    run.check('health_denominators_independent_arithmetic',lambda: exact((100,8,8,92,100,8),
        (stage['targeted'],stage['reporting'],stage['successful'],stage['unknown'],stage['reporting_success_percent'],stage['targeted_success_percent'])))
    run.check('collection_execution_and_device_effectiveness_distinct',lambda: exact((False,'unknown',0),
        (health['rollout_ready'],health['endpoint_outcome'],health['stages']['effective_state']['reporting'])))
    legacy = paths/'legacy store'; legacy_path=legacy_store(legacy); backup=paths/"migration café 'backup'.sqlite3"
    legacy_before = file_hash(legacy_path)
    terminal = run.pty(legacy,None,['overview','migrate '+shlex.quote(str(backup)),'overview','quit'])
    run.check('explicit_terminal_migration_completed',lambda: contains(terminal,['from_version','to_version']))
    with sqlite3.connect(backup) as db: version_before=db.execute('PRAGMA user_version').fetchone()[0]
    with sqlite3.connect(legacy_path) as db: version_after=db.execute('PRAGMA user_version').fetchone()[0]
    run.check('migration_backup_v1_and_destination_v2',lambda: exact((1,2),(version_before,version_after)))
    run.check('populated_legacy_snapshot_preserved',lambda: exact(old.expected_policy(),run.head(legacy)))
    with sqlite3.connect(backup) as db:
        original_body=json.loads(db.execute('SELECT body_json FROM snapshots').fetchone()[0])
    run.check('backup_retains_original_legacy_snapshot',lambda: exact(old.expected_policy(),original_body))
    run.check('migration_does_not_claim_live_qualification',lambda: exact(False,health['cloud_authority']))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--python',default=sys.executable)
    parser.add_argument('--plugin','--project',dest='plugin',type=Path,help='Exact source or runtime product root; fixtures/checker remain separately bound')
    parser.add_argument('--oracle-self-test',action='store_true')
    args=parser.parse_args(argv)
    global PROJECT
    if args.plugin: PROJECT=args.plugin.absolute()
    run=Run(args.output.absolute(),args.python)
    try:
        if args.oracle_self_test: run.check('retained_literal_oracle_negative_controls',old.negative_controls)
        else: qualify(run)
        run.results['status']='PASS'; code=0
    except Exception as error:
        run.results.update(status='FAIL',error=repr(error),traceback=traceback.format_exc());code=1
    finally:
        run.results['finished_at']=time.time();run.save()
    print(json.dumps({'status':run.results['status'],'checks':len(run.results['checks']),'commands':len(run.results['commands']),
                      'receipt':str(run.root/'receipt.json'),'error':run.results.get('error')}))
    return code


if __name__=='__main__':raise SystemExit(main())
