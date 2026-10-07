#!/usr/bin/env python3
"""Independent read-only capacity regression oracle over a preserved 1000-object store.

Preparation copies and hashes the earlier actual-import fixture; it never repeats
ingestion. A second explicitly SQL-seeded copy adds denial/pending observations.
Product operations use cold CLI processes and a real Linux PTY. No product module
is imported; the retained independent performance grader supplies measurement.
"""
from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pty
import select
import shutil
import signal
import sqlite3
import struct
import subprocess
import sys
import termios
import time
import traceback

GRADER_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('independent_performance_measurement', GRADER_ROOT/'scripts/qualify-workbench-performance.py')
measurement = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(measurement)
ORIGINAL_HELPER = GRADER_ROOT/'scripts/qualify-workbench-performance.py'
dump, exact, sha = measurement.dump, measurement.exact, measurement.sha
oid, expected_body = measurement.object_id, measurement.expected_body
DEFINITION = measurement.DEFINITION
PLAN = {
    'schema_version': 'workbench-capacity-repair-preregistration/1',
    'repetitions': 3,
    'thresholds': copy.deepcopy(measurement.PLAN['thresholds']),
    'threshold_policy': 'Retain the original 2s/5s/15s startup/ordinary/capacity wall ceilings and CPU/RSS ceilings; every gated sample must pass, no outlier removal or post-result adjustment.',
    'workloads': [
        'A byte-identical private copy of 1000 captures previously imported by actual CLI; no reingestion.',
        'Three first/last scoped inspection samples and three 50-row first/last-page samples.',
        'Twenty explicit 50-object pages whose union is exactly the 1000 independently known IDs/bodies, without duplicates or omissions.',
        'Global unique-name/setting search, scoped settings/health/dictionary and reference listing.',
        'SQL-seeded separate copy adds one denied existing-object attempt and one never-complete pending object; page and inspect must distinguish stale last-good from unknown.',
        'Real PTY startup, next/previous, unique search, select final object, inspect/settings/dictionary/health and quit.',
        'Unpaged full-inventory byte rejection and invalid page bounds remain enforced; all original/copied database bytes stay unchanged during product queries.',
    ],
    'pagination_contract': {'container': 'pagination', 'fields': ['total_objects','returned_objects','limit','offset','has_more','next_offset','complete','scope'],
        'complete': 'offset zero and all filtered matching objects returned', 'scope': 'page for an explicit limit; global inventory count remains separately visible'},
    'measurement': 'Fresh Linux CLI process, kernel wait4 child CPU/RSS, monotonic spawn-through-reap wall. Warm OS caches remain uncontrolled. Final timings require coordinator quiet-window; development runs record diagnostics but cannot qualify performance.',
    'limitations': ['Synthetic/caller-asserted captured data; no live Graph, device, fleet SLA or organizational approval.',
        'Copied store originates from preserved 1000 actual imports; denial/pending variant is explicitly independent SQL fixture construction, not imported-device evidence.',
        'Linux process/PTY only; no Windows/macOS or hostile-host/power-loss qualification.'],
}


def configure(project):
    measurement.PROJECT = project
    measurement.PLAN = PLAN
    measurement.__file__ = str(Path(__file__).resolve())
    def source_map():
        paths = [project/'scripts/intune-iac.py']
        for name in ('intune_iac','reference','contracts','corrections/contracts'):
            paths += [p for p in (project/name).rglob('*') if p.is_file() and p.suffix in ('.py','.json')]
        return {str(p.relative_to(project)):sha(p) for p in sorted(set(paths))}
    measurement.source_map = source_map


def prepare(output, store):
    registration = measurement.prepare(output)
    original = store/'observations.sqlite3'
    original_sha = sha(original)
    with sqlite3.connect(original.as_uri()+'?mode=ro',uri=True) as db:
        ids = [r[0] for r in db.execute('SELECT object_id FROM object_heads WHERE present=1 ORDER BY object_id')]
        exact([oid(i) for i in range(1,1001)],ids)
        for object_id, body in db.execute('SELECT h.object_id,s.body_json FROM object_heads h JOIN observations o USING(observation_id) JOIN snapshots s USING(snapshot_id) WHERE h.present=1'):
            index = int(object_id.split('-')[-1],16)
            exact(expected_body(f'Performance capture {index:04d}'),json.loads(body))
    for name in ('store','edge-store'):
        destination = output/name;destination.mkdir(mode=0o700)
        shutil.copyfile(original,destination/'observations.sqlite3')
        (destination/'observations.sqlite3').chmod(0o600)
        exact(original_sha,sha(destination/'observations.sqlite3'))
    # A known failed attempt cannot erase last good; a never-observed policy is
    # distinct from empty assignments. These are declared fixture rows only.
    edge = output/'edge-store/observations.sqlite3'
    with sqlite3.connect(edge) as db:
        db.execute('PRAGMA foreign_keys=ON')
        source = json.loads(db.execute('SELECT source_json FROM observations WHERE object_id=?',(oid(1000),)).fetchone()[0])
        for run_id, object_id, known in ((1001,oid(1000),True),(1002,oid(1001),False)):
            imported = copy.deepcopy(source)
            imported['raw_observed']['policy'].update(id=object_id,name='Performance capture 1000' if known else 'Never observed policy 1001')
            imported['raw_observed']['assignments'] = []
            moment = 1791331200.0
            db.execute('INSERT INTO collection_runs VALUES(?,?,?,?,?,?,?,?,?)',(run_id,measurement.TENANT,moment,moment,moment,'denied','denied','capture_denied',0))
            scope = json.dumps({'kind':'policy','object_ids':[object_id]})
            db.execute('INSERT INTO run_details VALUES(?,?,?,?,?)',(run_id,scope,json.dumps(imported),'graph_capture_unverified','capture:'+object_id))
            db.execute('INSERT INTO run_scope_objects VALUES(?,?)',(run_id,object_id))
            for kind in ('policies','settings','assignments'):
                db.execute('INSERT INTO collection_coverage VALUES(?,?,?,?,?,?)',(run_id,kind,'' if kind=='policies' else object_id,'access_denied' if kind=='assignments' else 'complete','access_denied' if kind=='assignments' else None,1))
        exact([],db.execute('PRAGMA foreign_key_check').fetchall())
    registration.update(original_store=str(store),original_database_sha256=original_sha,
        copied_database_sha256=sha(output/'store/observations.sqlite3'),edge_database_sha256=sha(edge),
        helper_sha256=sha(ORIGINAL_HELPER),edge_fixture_method='Independent SQL seeding, not product ingestion or real service evidence')
    dump(output/'preregistration.json',registration)


def page_assert(result, total, limit, offset, returned):
    exact({'total_objects':total,'returned_objects':returned,'limit':limit,'offset':offset,
           'has_more':offset+returned<total,'next_offset':offset+returned if offset+returned<total else None,
           'complete':offset==0 and returned==total,'scope':'page'},result['pagination'])


class Run(measurement.Run):
    def __init__(self,output,python,quiet_window,development):
        super().__init__(output,python,quiet_window or 'DEVELOPMENT ONLY; performance not qualified')
        self.development = development
        self.result.update(schema_version='workbench-capacity-repair-receipt/1',development_only=development,
            grader={'path':str(Path(__file__).resolve()),'sha256':sha(Path(__file__))},
            helper={'path':str(ORIGINAL_HELPER),'sha256':sha(ORIGINAL_HELPER)})
        exact(self.registration['helper_sha256'],sha(ORIGINAL_HELPER))
        self.original = Path(self.registration['original_store'])/'observations.sqlite3'
        self.store = output/'store';self.edge = output/'edge-store'
        self.database_before = {'original':sha(self.original),'copy':sha(self.store/'observations.sqlite3'),'edge':sha(self.edge/'observations.sqlite3')}
        exact(self.registration['original_database_sha256'],self.database_before['original'])
        exact(self.registration['copied_database_sha256'],self.database_before['copy'])
        exact(self.registration['edge_database_sha256'],self.database_before['edge'])
        self.result['database_before']=self.database_before
        self.save()

    def command(self,label,*args,category='ordinary',expected_error=None):
        return self.cli(label,*args,category=None if self.development else category,expected_error=expected_error)

    def inspect(self,store,index):
        row = self.command('inspect-'+str(index),'inspect','--root',store,'--object',oid(index))
        exact(oid(index),row['object_id'])
        exact(expected_body(f'Performance capture {index:04d}'),row['body'])
        exact(False,row['cloud_authority']);exact(False,row['execution_authorized'])
        exact('stale',row['freshness'])
        return row

    def terminal(self):
        commands=['next','previous','search Performance capture 1000','select '+oid(1000),'inspect','settings','dictionary','health','quit']
        argv=[self.python,'-B',str(measurement.PROJECT/'scripts/intune-iac.py'),'workbench','terminal','--root',str(self.store)]
        master,slave=pty.openpty();fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',24,120,0,0))
        settings=termios.tcgetattr(slave);settings[3]&=~termios.ECHO;termios.tcsetattr(slave,termios.TCSANOW,settings)
        started=time.monotonic();sent=0;data=bytearray();deadline=started+30
        child=subprocess.Popen(argv,stdin=slave,stdout=slave,stderr=slave,start_new_session=True,cwd=measurement.PROJECT,
            env={'PATH':'/usr/bin:/bin','HOME':str(self.root),'LANG':'C.UTF-8','LC_ALL':'C.UTF-8','TERM':'xterm','PYTHONDONTWRITEBYTECODE':'1'})
        os.close(slave);done=False;timed_out=False
        try:
            while not done:
                if time.monotonic()>deadline or len(data)>8*1024*1024:
                    timed_out=True;os.killpg(child.pid,signal.SIGKILL)
                ready,_,_=select.select([master],[],[],.01)
                if ready:
                    try:block=os.read(master,65536)
                    except OSError:block=b''
                    data.extend(block)
                    if data.count(b'workbench> ')>sent and sent<len(commands):
                        os.write(master,(commands[sent]+'\n').encode());sent+=1
                waited,status,usage=os.wait4(child.pid,os.WNOHANG)
                if waited:
                    done=True;child.returncode=os.waitstatus_to_exitcode(status)
            # A child can exit with final output still buffered in the PTY.
            while select.select([master],[],[],0)[0]:
                try:block=os.read(master,65536)
                except OSError:break
                if not block:break
                data.extend(block)
        finally:os.close(master)
        elapsed=time.monotonic()-started
        path=self.root/'terminal-pty.stdout';path.write_bytes(data)
        row={'label':'terminal-pty','command':argv,'commands':commands,'sent':sent,'exit_code':child.returncode,'timed_out':timed_out,
            'wall_seconds':elapsed,'cpu_seconds':usage.ru_utime+usage.ru_stime,'peak_rss_kib':usage.ru_maxrss,
            'stdout':{'path':path.name,'bytes':len(data),'sha256':sha(path)},'category':None if self.development else 'capacity'}
        if not self.development:
            row['thresholds']=PLAN['thresholds']['capacity'];row['within_thresholds']=all(row[k]<=v for k,v in row['thresholds'].items())
        self.result['commands'].append(row);self.save()
        self.check('actual_pty_all_navigation_completed',sent==len(commands) and child.returncode==0 and not timed_out)
        self.check('actual_pty_no_masked_query_error',b'workbench_query_limit' not in data and b'"status": "error"' not in data)
        self.check('actual_pty_selected_last_object_visible',b'Performance capture 1000' in data and oid(1000).encode() in data)
        self.check('actual_pty_continuation_metadata_visible',b'"total_objects": 1000' in data and b'"offset": 10' in data and b'"offset": 0' in data)
        if not self.development:self.check('actual_pty_preregistered_thresholds',row['within_thresholds'])

    def execute(self):
        for _ in range(PLAN['repetitions']):
            self.inspect(self.store,1);self.inspect(self.store,1000)
            for offset in (0,950):
                page=self.command('overview-page-'+str(offset),'overview','--root',self.store,'--limit','50','--offset',offset,category='capacity')
                page_assert(page,1000,50,offset,50)
                exact([oid(i) for i in range(offset+1,offset+51)],[r['object_id'] for r in page['objects']])
        seen=[]
        for offset in range(0,1000,50):
            page=self.command('overview-complete-union','overview','--root',self.store,'--limit','50','--offset',offset,category='capacity')
            page_assert(page,1000,50,offset,50);exact(1000,page['total_inventory_objects']);exact([],page['pending_observations'])
            for row in page['objects']:
                index=int(row['object_id'].split('-')[-1],16)
                exact(expected_body(f'Performance capture {index:04d}'),row['body'])
                exact(False,row['cloud_authority']);exact(False,row['execution_authorized']);exact('stale',row['freshness'])
                seen.append(row['object_id'])
        exact([oid(i) for i in range(1,1001)],seen);self.check('all_1000_paginated_objects_exact_once',True)
        selected=self.command('global-unique-search','search','--root',self.store,'--query','Performance capture 1000','--limit','10','--offset','0')
        page_assert(selected,1,10,0,1);exact([oid(1000)],[r['object_id'] for r in selected['objects']]);self.check('search_finds_outside_initial_page',True)
        matched=self.command('global-setting-search-last-page','search','--root',self.store,'--query',DEFINITION,'--limit','50','--offset','950',category='capacity')
        page_assert(matched,1000,50,950,50);exact([oid(i) for i in range(951,1001)],[r['object_id'] for r in matched['objects']])
        empty=self.command('literal-wildcard-search','search','--root',self.store,'--query','%','--limit','10')
        page_assert(empty,0,10,0,0);exact([],empty['objects'])
        settings=self.command('scoped-settings','settings','--root',self.store,'--object',oid(1000))
        exact(expected_body()['settings'],settings['settings'])
        health=self.command('scoped-health','health','--root',self.store,'--object',oid(1000))
        exact(oid(1000),health['object_id']);exact('unknown',health['endpoint_health']);exact(False,health['rollout_ready'])
        dictionary=self.command('scoped-dictionary','dictionary','--root',self.store,'--object',oid(1000),'--query',DEFINITION)
        exact({'kind':'object','object_id':oid(1000)},dictionary['observation_scope'])
        exact([oid(1000)],[u['object_id'] for e in dictionary['entries'] for u in e['actual_uses']])
        dictionary=self.command('paged-dictionary','dictionary','--root',self.store,'--query',DEFINITION,'--limit','50','--offset','950',category='capacity')
        exact('page',dictionary['observation_scope']['kind']);page_assert(dictionary['observation_scope'],1000,50,950,50)
        exact([oid(i) for i in range(951,1001)],[u['object_id'] for e in dictionary['entries'] for u in e['actual_uses']])
        references=self.command('bounded-references','references','--root',self.store,'--limit','50');exact([],references['references'])
        self.command('retain-unpaged-byte-bound','overview','--root',self.store,category='capacity',expected_error='workbench_query_limit')
        for bad in ('0','1001'):
            self.command('invalid-page-limit','overview','--root',self.store,'--limit',bad,expected_error='workbench_query_invalid')
        self.command('invalid-page-offset','overview','--root',self.store,'--limit','10','--offset','-1',expected_error='workbench_query_invalid')
        edge=self.command('denied-pending-page','overview','--root',self.edge,'--limit','50','--offset','950',category='capacity')
        page_assert(edge,1001,50,950,50);exact('stale',edge['freshness'])
        stale=[row for row in edge['objects'] if row['object_id']==oid(1000)][0]
        exact(True,stale['retained_last_good']);exact('denied',stale['last_attempt']['status']);exact(expected_body('Performance capture 1000'),stale['body'])
        pending=self.command('pending-only-final-page','overview','--root',self.edge,'--limit','50','--offset','1000',category='capacity')
        page_assert(pending,1001,50,1000,1);exact([],pending['objects']);exact([oid(1001)],[row['object_id'] for row in pending['pending_observations']])
        row=pending['pending_observations'][0];exact(None,row['body']);exact('unknown',row['freshness']);exact(None,row['last_success']);exact('denied',row['coverage'])
        direct=self.command('inspect-never-complete','inspect','--root',self.edge,'--object',oid(1001));exact(None,direct['body']);exact('unknown',direct['freshness'])
        self.check('denied_last_good_and_unknown_pending_are_distinct',True)
        self.terminal()
        self.result['source_after']=measurement.source_map();exact(self.result['source_before'],self.result['source_after'])
        exact(self.result['grader']['sha256'],sha(Path(__file__)));exact(self.result['helper']['sha256'],sha(ORIGINAL_HELPER))
        after={'original':sha(self.original),'copy':sha(self.store/'observations.sqlite3'),'edge':sha(self.edge/'observations.sqlite3')}
        exact(self.database_before,after);self.result['database_after']=after
        self.check('all_original_and_copied_database_bytes_unchanged',True)
        self.check('product_and_independent_graders_unchanged',True)
        self.snapshot_processes('processes-after.txt')
        self.result.update(status='DEVELOPMENT_PASS' if self.development else 'PASS_SCOPED',finished_at=measurement.datetime.now(measurement.timezone.utc).isoformat())
        self.save()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',type=Path,default=GRADER_ROOT)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--store',type=Path,help='Preserved actual 1000-import fixture; required only for preparation')
    parser.add_argument('--python',default=sys.executable)
    action=parser.add_mutually_exclusive_group(required=True);action.add_argument('--prepare',action='store_true');action.add_argument('--run',action='store_true')
    parser.add_argument('--quiet-window');parser.add_argument('--development',action='store_true',help='Functional qualification only, no performance pass claim')
    args=parser.parse_args();configure(args.project.absolute())
    if args.prepare:
        if not args.store:parser.error('--prepare requires --store')
        prepare(args.output.absolute(),args.store.absolute());print(args.output/'preregistration.json');return 0
    if sys.platform!='linux' or not hasattr(os,'wait4'):parser.error('Linux wait4/PTY profile required')
    if not args.development and not args.quiet_window:parser.error('Timed run requires coordinator --quiet-window')
    run=Run(args.output.absolute(),args.python,args.quiet_window,args.development)
    try:run.execute()
    except Exception as error:
        run.result.update(status='FAIL_PRESERVED',error_type=type(error).__name__,error=str(error))
        (run.root/'failure-traceback.txt').write_text(traceback.format_exc());run.save();print(run.root/'receipt.json');return 1
    print(run.root/'receipt.json');return 0


if __name__=='__main__':raise SystemExit(main())
