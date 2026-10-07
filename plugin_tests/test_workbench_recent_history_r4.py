"""Bounded history against 1,001 independently seeded retained observations.

The seed is an explicit SQLite retention fixture built from one real modeled
collection. It is not evidence of 1,001 scheduler runs or authenticated Graph.
"""
import copy
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest

from intune_iac.io import AppError, digest
from intune_iac.modeled_service import ModeledService
from intune_iac.synthetic import generate_estate
from intune_iac.workbench_store import WorkbenchStore

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'scripts/intune-iac.py'


def retained_fixture(directory, count=1001):
    estate = generate_estate(seed=12071, policy_count=1)
    oid = estate['truth']['policies'][0]['id']
    service = ModeledService.create(directory / 'service', estate['capture'], [oid])
    store = WorkbenchStore.create(directory / 'store', estate['truth']['tenant_id'])
    started = time.time() - count - 1
    store.collect(service, observed_at=started)
    with sqlite3.connect(store.path) as db:
        db.row_factory = sqlite3.Row
        first = db.execute('SELECT * FROM observations').fetchone()
        body = json.loads(db.execute('SELECT body_json FROM snapshots').fetchone()[0])
        detail = db.execute('SELECT * FROM run_details').fetchone()
        coverage = list(db.execute('SELECT * FROM collection_coverage'))
        for number in range(2, count + 1):
            stamp = started + number - 1
            changed = dict(body, description='Independent retained value %04d' % number)
            sid = digest({'tenant_id': store.tenant_id, 'object_id': oid, 'body': changed})
            db.execute('INSERT INTO collection_runs VALUES(?,?,?,?,?,?,?,?,?)',
                       (number, store.tenant_id, stamp, stamp, stamp, 'complete', 'complete', None, 1))
            db.execute('INSERT INTO snapshots VALUES(?,?,?,?)',
                       (sid, store.tenant_id, oid, json.dumps(changed)))
            db.execute('INSERT INTO observations VALUES(?,?,?,?,?,?,?)',
                       (number, number, sid, store.tenant_id, oid, stamp, first['source_json']))
            db.execute('INSERT INTO run_details VALUES(?,?,?,?,?)',
                       (number, detail['scope_json'], detail['source_json'], detail['evidence_class'], detail['domain']))
            db.execute('INSERT INTO run_scope_objects VALUES(?,?)', (number, oid))
            for row in coverage:
                db.execute('INSERT INTO collection_coverage VALUES(?,?,?,?,?,?)',
                           (number, row['kind'], row['owner_id'], row['coverage'], row['reason'], row['page_count']))
        db.execute('UPDATE object_heads SET run_id=?,observation_id=?,observed_at=? WHERE object_id=?',
                   (count, count, started + count - 1, oid))
    return store, oid


class RecentHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.store, self.oid = retained_fixture(Path(self.temp.name))

    def cli(self, command, *arguments, expected=0, input=None):
        result = subprocess.run([sys.executable, '-B', str(CLI), 'workbench', command,
            '--root', str(self.store.root), *arguments], input=input, text=True,
            capture_output=True, timeout=20)
        self.assertEqual(result.returncode, expected, result.stderr)
        return json.loads(result.stdout) if expected == 0 and command != 'terminal' else result

    def test_four_views_after_1001_retained_observations_actual_cli(self):
        value = self.cli('views', '--object', self.oid)
        current = value['observed']
        delta = value['comparisons']['collector_snapshot_delta']
        self.assertEqual(current['body']['description'], 'Independent retained value 1001')
        self.assertEqual(delta['current']['snapshot_id'], current['snapshot_id'])
        self.assertEqual(delta['current']['observed_at'], current['observed_at'])
        self.assertEqual(delta['baseline']['snapshot_id'], self.store.recent_history(self.oid, limit=2)[1]['snapshot_id'])
        self.assertEqual(delta['changed_fields'], ['description'])
        with sqlite3.connect(self.store.path) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM observations').fetchone()[0], 1001)
            raw = db.execute('SELECT body_json FROM snapshots WHERE snapshot_id=?',
                             (delta['baseline']['snapshot_id'],)).fetchone()[0]
            self.assertEqual(json.loads(raw)['description'], 'Independent retained value 1000')
        print('actual_cli_1001_four_views: current=1001 baseline=1000 retained=1001')

    def test_newest_pages_and_legacy_chronological_cli_remain_distinct(self):
        first = self.cli('history-recent', '--object', self.oid)
        self.assertEqual([r['run_id'] for r in first['history']], list(range(1001,991,-1)))
        self.assertEqual(first['pagination']['total_observations'], 1001)
        self.assertEqual(first['pagination']['next_offset'], 10)
        last = self.cli('history-recent', '--object', self.oid, '--limit', '2', '--offset', '1000')
        self.assertEqual([r['run_id'] for r in last['history']], [1])
        self.assertIsNone(last['pagination']['next_offset'])
        empty = self.cli('history-recent', '--object', self.oid, '--offset', '1001')
        self.assertEqual(empty['history'], [])
        self.assertEqual(empty['pagination']['total_observations'], 1001)
        old = self.cli('history', '--object', self.oid, '--limit', '2')
        self.assertEqual([r['run_id'] for r in old['history']], [1,2])
        refused = self.cli('history', '--object', self.oid, expected=3)
        self.assertEqual(json.loads(refused.stderr)['error']['code'], 'workbench_query_limit')

    def test_bounds_and_same_timestamp_tie_breaker(self):
        for limit, offset in ((None,0),(True,0),(0,0),(-1,0),(1001,0),(1,-1),(1,True),(1,1000000001)):
            with self.subTest(limit=limit, offset=offset), self.assertRaises(AppError) as error:
                self.store.recent_history(self.oid, limit=limit, offset=offset)
            self.assertEqual(error.exception.code, 'workbench_query_invalid')
        for args in (('--limit','0'),('--limit','1001'),('--offset','-1')):
            refused = self.cli('history-recent', '--object', self.oid, *args, expected=3)
            self.assertEqual(json.loads(refused.stderr)['error']['code'], 'workbench_query_invalid')
        with sqlite3.connect(self.store.path) as db:
            db.execute('UPDATE observations SET observed_at=(SELECT observed_at FROM observations WHERE observation_id=1001) WHERE observation_id=1000')
        recent = self.cli('history-recent', '--object', self.oid, '--limit', '2')
        self.assertEqual([r['run_id'] for r in recent['history']], [1001,1000])

    def test_current_head_mismatch_never_claims_latest_snapshot_is_current(self):
        with sqlite3.connect(self.store.path) as db:
            db.execute('UPDATE object_heads SET run_id=1000,observation_id=1000,observed_at=(SELECT observed_at FROM observations WHERE observation_id=1000)')
        value = self.cli('views', '--object', self.oid)
        self.assertEqual(value['observed']['body']['description'], 'Independent retained value 1000')
        self.assertEqual(value['comparisons']['collector_snapshot_delta'],
                         {'status':'unknown','reason':'history_current_observation_mismatch'})

    def test_terminal_recent_history_paging_keeps_selected_identity(self):
        from intune_iac.workbench import run_terminal
        commands = iter(['select '+self.oid,'history-recent 2','next','inspect','previous','history 1','quit'])
        values = []
        result = run_terminal(self.store.root, input_fn=lambda _:next(commands), result_fn=values.append)
        self.assertEqual(result['status'], 'closed')
        pages = [v for v in values if v.get('pagination',{}).get('scope')=='history_page']
        self.assertEqual([[r['run_id'] for r in p['history']] for p in pages],
                         [[1001,1000],[999,998],[1001,1000]])
        self.assertTrue(all(v['object_id']==self.oid for v in pages))
        self.assertFalse(any(v.get('status')=='error' for v in values))
        self.assertEqual(values[-1]['history'][0]['run_id'],1)

    def test_workspace_history_context_is_bounded_and_readonly(self):
        from intune_iac.workbench_tui import Workspace, CONTEXT_VERSION
        ui = Workspace(self.store.root, stdin=io.StringIO(), stdout=io.StringIO())
        ui.selected = self.oid
        self.assertEqual(ui._tab_command(3), 'history-recent')
        ui.receive(self.store.recent_history_page(self.oid, limit=2, offset=10))
        self.assertEqual(ui.view_command, 'history-recent 2 10')
        ui.last_command = 'next'
        ui.receive(self.store.recent_history_page(self.oid, limit=2, offset=12))
        self.assertEqual(ui.selected, self.oid)
        restored = Workspace(self.store.root, stdin=io.StringIO(), stdout=io.StringIO())
        self.assertEqual(list(restored.pending), ['overview','select '+self.oid,'history-recent 2 12'])
        base = {'schema_version':CONTEXT_VERSION,'tenant_id':self.store.tenant_id,'selected':self.oid,
                'tab':3,'view_command':'history-recent 2 12','page_command':'overview'}
        for command in ('history-recent 0','history-recent 1001','history-recent 1 -1',
                        'history-recent 1 1000000001','history-recent 1 0 execute',
                        'history-recent 1;execute','history-recent\nexecute','history-recent '+'9'*5000):
            with self.subTest(command=command), self.assertRaises(AppError):
                restored._validate_context(dict(base, view_command=command))
        with self.assertRaises(AppError): restored._validate_context(dict(base, selected=None))
        restored.last_command = 'back'; restored.receive({'status':'selection_cleared'})
        self.assertIsNone(restored.selected)
        self.assertEqual(restored.view_command,'overview')
        self.assertEqual(self.store.operations(), [])

    def test_workflow_old_snapshot_binding_beyond_latest_page_actual_cli(self):
        from datetime import datetime, timezone
        with sqlite3.connect(self.store.path) as db:
            sid, stamp = db.execute('SELECT snapshot_id,observed_at FROM observations WHERE observation_id=1').fetchone()
        value = {'schema_version':'workbench-workflow-run/1','tenant_id':self.store.tenant_id,
                 'object_id':self.oid,'run_url':'https://example.invalid/actions/runs/12071',
                 'repository_revision':'a'*40,'run_id':'12071','status':'success',
                 'observed_at':datetime.fromtimestamp(stamp+1,timezone.utc).isoformat(),'observed_after':sid}
        path = Path(self.temp.name)/'workflow.json'; path.write_text(json.dumps(value))
        accepted = self.cli('workflow-import','--input',str(path))
        self.assertEqual(accepted['data']['relationships'], [{'relation':'observed_after','target_id':sid,
            'assertion_class':'caller_asserted_time_order','local_target_verified':True}])
        self.assertFalse(accepted['data']['external_execution_verified'])
        # The exact published timestamp retains the previous history contract,
        # even when the internal REAL value lies between microseconds.
        rounded_source = int(stamp)+.1234568
        with sqlite3.connect(self.store.path) as db:
            db.execute('UPDATE observations SET observed_at=? WHERE observation_id=1',(rounded_source,))
        self.assertTrue(self.store.has_observed_snapshot(self.oid,sid,
            at_or_before=datetime.fromtimestamp(rounded_source,timezone.utc).isoformat()))
        for change in ({'observed_after':'f'*64},
                       {'observed_at':datetime.fromtimestamp(stamp-1,timezone.utc).isoformat()},
                       {'observed_at':'unknown'}):
            path.write_text(json.dumps(dict(value, **change)))
            rejected = self.cli('workflow-import','--input',str(path),expected=3)
            self.assertIn(json.loads(rejected.stderr)['error']['code'],
                          ('workbench_workflow_snapshot_unknown','workbench_evidence_time'))
        self.assertEqual(len(self.store.artifacts(kind='workflow_run',object_id=self.oid)),1)


if __name__ == '__main__': unittest.main()
