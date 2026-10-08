"""Real bounded SQLite parser negatives, not service or native authentication.

Only the prevalidated phase-method seam is bypassed in these parser controls.
The separate retained native Plan2/TLS journey exercises the full actual selector,
identity, capture, container absence, same-authority registration and refresh.
"""
import hashlib
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from intune_iac import worker_adoption_plan_observation as observation,worker_adoption_plan_phase as phases
from intune_iac.io import AppError,digest


class UnacquiredPlanJournalContracts(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='iw-unacquired-');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.path=self.root/'broker.sqlite3'
        self.route={'id':'provider-instance','host':'login.microsoftonline.com','path':'/common/discovery/instance',
            'method':'GET','role':'provider','audience':'graph','effect':'discovery','body_sha256':hashlib.sha256(b'').hexdigest(),'headers':{}}
        self.policy={'routes':[self.route]};self.selected=object.__new__(phases.RecoveryPlanPhase)
        self.selected.journal=self.path;self.selected.broker_policy=self.policy
        self.guard=patch.object(phases.RecoveryPlanPhase,'_check',lambda self:None);self.guard.start();self.addCleanup(self.guard.stop)
        with sqlite3.connect(self.path) as db:
            db.executescript('CREATE TABLE binding(digest TEXT); CREATE TABLE attempts(sequence INTEGER,route TEXT,status TEXT,response_code INTEGER,request_sha256 TEXT,response_sha256 TEXT); CREATE TABLE native_lease_requests(sequence INTEGER,host TEXT,path TEXT,action TEXT,lease_id TEXT,lock_metadata TEXT);')
            db.execute('INSERT INTO attempts VALUES(1,?,?,?,?,?)',('provider-instance','response_received',200,'a'*64,'b'*64))
        self.path.chmod(0o600);self.rebind()
    def rebind(self):
        with sqlite3.connect(self.path) as db:db.execute('DELETE FROM binding');db.execute('INSERT INTO binding VALUES(?)',(digest(self.policy),))
    def inspect(self):return observation.inspect_unacquired(self.selected)
    def test_actual_sqlite_readonly_positive_and_exact_bytes(self):
        before=self.path.read_bytes();facts=self.inspect()
        self.assertEqual(facts['journal_sha256'],hashlib.sha256(before).hexdigest());self.assertEqual(facts['backend_attempt_count'],0)
        self.assertEqual(len(facts['attempts']),1);self.assertEqual(self.path.read_bytes(),before)
        self.assertFalse(facts['release_performed']);self.assertFalse(facts['execution_authorized'])
    def test_backend_read_even_uncertain_is_rejected(self):
        self.route.update(role='backend',audience='storage',effect='readonly');self.rebind()
        with sqlite3.connect(self.path) as db:db.execute("UPDATE attempts SET status='outcome_unknown',response_code=NULL,response_sha256=NULL")
        with self.assertRaises(AppError):self.inspect()
    def test_backend_oauth_attempt_rejected(self):
        self.route.update(role='backend',audience='storage',effect='oauth',method='POST');self.rebind()
        with self.assertRaises(AppError):self.inspect()
    def test_provider_oauth_intentionally_outside_narrow_readonly_profile(self):
        self.route.update(effect='oauth',method='POST');self.rebind()
        with self.assertRaises(AppError):self.inspect()
    def test_uncertain_state_write_not_absence_of_effect(self):
        self.route.update(role='backend',audience='storage',effect='state_write',method='PUT');self.rebind()
        with sqlite3.connect(self.path) as db:db.execute("UPDATE attempts SET status='dispatch_started',response_code=NULL,response_sha256=NULL")
        with self.assertRaises(AppError):self.inspect()
    def test_lease_route_without_lease_row_is_not_absence_of_effect(self):
        self.route.update(role='backend',audience='storage',effect='lease',method='PUT',headers={'x-ms-lease-action':'acquire'});self.rebind()
        with self.assertRaises(AppError):self.inspect()
    def test_orphan_lease_row_denied(self):
        with sqlite3.connect(self.path) as db:db.execute('INSERT INTO native_lease_requests VALUES(99,?,?,?,?,NULL)',('x.blob.core.windows.net','/c/k','acquire','aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'))
        with self.assertRaises(AppError):self.inspect()
    def test_provider_mutation_denied(self):
        self.route.update(effect='mutation',method='PUT');self.rebind()
        with self.assertRaises(AppError):self.inspect()
    def test_nonempty_readbody_denied(self):
        self.route['body_sha256']='c'*64;self.rebind()
        with self.assertRaises(AppError):self.inspect()
    def test_hot_journal_denied_without_recovery_or_deletion(self):
        path=Path(str(self.path)+'-journal');path.write_bytes(b'explicit-model-sidecar');before=self.path.read_bytes()
        with self.assertRaises(AppError):self.inspect()
        self.assertEqual(path.read_bytes(),b'explicit-model-sidecar');self.assertEqual(self.path.read_bytes(),before)
    def test_changed_policy_binding_denied(self):
        self.route['path']='/different'
        with self.assertRaises(AppError):self.inspect()
    def test_unlisted_route_or_malformed_hash_denied(self):
        with sqlite3.connect(self.path) as db:db.execute("UPDATE attempts SET request_sha256='not-a-hash'")
        with self.assertRaises(AppError):self.inspect()
        with sqlite3.connect(self.path) as db:db.execute("UPDATE attempts SET request_sha256=?,route='unknown'",('a'*64,))
        with self.assertRaises(AppError):self.inspect()
    def test_no_json_authority_or_noop_release_api(self):
        for action in (lambda:observation.inspect_unacquired({}),lambda:observation.observe(context={},output=self.root/'new'),
                lambda:observation.refresh('a'*36,context={},output=self.root/'new')):
            with self.assertRaises(AppError):action()
        self.assertFalse((self.root/'new').exists());self.assertFalse(hasattr(observation,'execute'));self.assertFalse(hasattr(observation,'SIGNATURE_DOMAIN'))

    def test_output_guard_protects_entire_common_jobs_namespace_before_creation(self):
        roots={k:self.root/k for k in ('authority','jobs','source','preimage','phase-source')}
        for path in roots.values():path.mkdir(mode=0o700)
        original=roots['jobs']/'original';original.mkdir();selected=roots['jobs']/'selected';selected.mkdir();host=selected/'host-run';host.mkdir()
        context=SimpleNamespace(job=SimpleNamespace(policy=SimpleNamespace(root=roots['authority'],jobs_root=roots['jobs']),root=original),
            phase=SimpleNamespace(host_root=host,host_spec={'source_root':str(roots['phase-source'])}),source_root=roots['source'],original_capture_root=roots['preimage'])
        for target in (selected/'evidence',roots['jobs']/'new',roots['authority']/'new',original/'new'):
            with self.subTest(target=target),self.assertRaises(AppError):observation._new_root(context,target)
            self.assertFalse(target.exists())
