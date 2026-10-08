"""Public recovery-plan readers under a real writer reservation.

Rows are explicit modeled stopped jobs; no native dispatch or live authority.
"""
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch
from intune_iac import worker_adoption_reconcile as bridge,worker_service as service
from intune_iac.io import AppError,write_json,digest
from plugin_tests import test_worker_adoption_phase_successor_r4 as fixtures

class PublicRecoveryReadonlyTests(unittest.TestCase):
    def setUp(self):
        fixtures.PhaseReadOnlyOpenTests.setUp(self)
        self.plan_manifest['profile']='native_docker_laboratory_protocol'
        write_json(self.plan_root/'manifest.json',self.plan_manifest)
        with self.policy.connection() as db:db.execute('UPDATE adoption_recovery_plans SET manifest_sha256=? WHERE operation_id=?',(digest(self.plan_manifest),self.plan_manifest['operation_id']))
    tearDown=fixtures.PhaseReadOnlyOpenTests.tearDown
    def held(self,*,cli):
        before=self.policy.database.read_bytes();db=sqlite3.connect(self.policy.database,timeout=0,isolation_level=None)
        try:
            db.execute('BEGIN IMMEDIATE');db.execute('UPDATE adoption_recovery_plans SET cancelled=1')
            for action in ('status','attach'):
                if cli:
                    run=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve().parents[1]/'scripts/intune-iac.py'),
                        'adoption','recovery-plan-'+action,'--job-root',str(self.plan_root),'--policy',str(self.policy_path)],capture_output=True,timeout=15)
                    self.assertEqual(run.returncode,3,run.stderr.decode());self.assertTrue(run.stdout,run.stderr.decode());value=json.loads(run.stdout)
                else:
                    calls=[];connect=sqlite3.connect
                    def trace(*args,**kwargs):
                        connection=connect(*args,**kwargs);connection.set_trace_callback(calls.append);return connection
                    with patch.object(service.sqlite3,'connect',side_effect=trace):value=getattr(bridge.RecoveryPlanJob(self.plan_root,self.policy_path),action)()
                    self.assertFalse(any(q.startswith(('BEGIN IMMEDIATE','CREATE','ALTER','INSERT','UPDATE','DELETE')) for q in calls),calls)
                self.assertEqual(value['operation_id'],self.plan_manifest['operation_id']);self.assertEqual(value['status'],'outcome_unknown')
                self.assertEqual(value['dispatches'],1);self.assertFalse(value['cancel_requested']);self.assertEqual(value['outcome'],{'modeled':True})
                self.assertEqual(self.policy.database.read_bytes(),before)
        finally:db.execute('ROLLBACK');db.close()
        self.assertEqual(self.policy.database.read_bytes(),before)
    def test_public_status_attach_with_reserved_writer(self):self.held(cli=False)
    def test_actual_cli_status_attach_with_reserved_writer(self):self.held(cli=True)
    def test_public_readonly_keeps_registered_reference_checks(self):
        write_json(self.plan_root/'original.json',{**self.reference,'manifest_sha256':'f'*64})
        with self.assertRaises(AppError):bridge.RecoveryPlanJob(self.plan_root,self.policy_path)
        write_json(self.plan_root/'original.json',self.reference)
        write_json(self.plan_root/'manifest.json',{**self.plan_manifest,'changed':True})
        with self.assertRaises(AppError):bridge.RecoveryPlanJob(self.plan_root,self.policy_path)
        write_json(self.plan_root/'manifest.json',self.plan_manifest)
        with self.policy.connection() as db:db.execute('DELETE FROM adoption_recovery_plans')
        with self.assertRaises(AppError):bridge.RecoveryPlanJob(self.plan_root,self.policy_path)
