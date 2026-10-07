#!/usr/bin/env python3
"""Actual CLI capture/import/reopen over a declared local HTTP connection seam.

Product origin admission and request construction remain unchanged. This checker
alone routes the fixed Graph connection to its owned loopback HTTP server. It
does not establish TLS, authenticated Graph identity or service semantics.
"""
import argparse
import hashlib
import http.server
import json
import os
from pathlib import Path
import selectors
import signal
import sqlite3
import subprocess
import sys
import threading
import time

T='11111111-1111-4111-8111-111111111111'
P='22222222-2222-4222-8222-222222222222'
BASE='/beta/deviceManagement/configurationPolicies'
DRIVER='''import http.client,runpy,sys
from pathlib import Path
project=Path(sys.argv.pop(1));port=int(sys.argv.pop(1))
sys.path.insert(0,str(project))
from intune_iac import identity_binding as identity
class LocalConnection(http.client.HTTPConnection):
    def __init__(self,host,*,port=443,timeout,context):
        assert host=='graph.microsoft.com' and port==443
        super().__init__('127.0.0.1',LOCAL_PORT,timeout=timeout)
LOCAL_PORT=port
identity.http.client.HTTPSConnection=LocalConnection
identity._system_tls_context=lambda: None
sys.argv[0]=str(project/'scripts/intune-iac.py')
runpy.run_path(sys.argv[0],run_name='__main__')
'''


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--project',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    project=args.project.resolve();output=args.output.resolve()
    driver=output/'local_connection_cli.py';driver.write_text(DRIVER)
    fixture=json.loads((project/'examples/supported/input/export.json').read_bytes())
    responses={}
    for collection in fixture['collections']:
        for page in collection['pages']:
            body=page['body']
            if collection['kind']=='assignments':
                for row in body['value']:row.update(source='direct',sourceId=None)
            responses[page['request_url'].removeprefix('https://graph.microsoft.com')]=json.dumps(body).encode()
    records=[];commands=[];checks=[];mode={'value':'retry','count':{}}
    release=threading.Event()
    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version='HTTP/1.1'
        def log_message(self,*args):pass
        def do_GET(self):
            key=(mode['value'],self.path);count=mode['count'].get(key,0)+1;mode['count'][key]=count
            records.append({'mode':mode['value'],'method':self.command,'path':self.path,'count':count,
                            'synthetic_token_matched':self.headers.get('Authorization')=='Bearer SYNTHETIC-ONLY-CAPTURE-TOKEN'})
            status=200;body=responses.get(self.path,b'{}');headers={}
            if mode['value']=='retry' and count==1 and self.path in (BASE,BASE+'/'+P+'/settings'):
                status=429 if self.path==BASE else 503;body=b'{"error":{"message":"RAW-ONLY-CANARY"}}';headers={'Retry-After':'0'}
            elif mode['value']=='denied' and self.path.endswith('/assignments'):
                status=403;body=b'{"error":{"message":"RAW-ONLY-CANARY"}}'
            elif mode['value'] in ('exhausted','delay','cancel') and self.path==BASE:
                status=429;body=b'{"error":{"message":"RAW-ONLY-CANARY"}}';headers={'Retry-After':{'exhausted':'0','delay':'31','cancel':'5'}[mode['value']]}
            elif mode['value']=='redirect' and self.path==BASE:
                status=302;body=b'{}';headers={'Location':'https://evil.invalid/forbidden'}
            elif mode['value']=='origin' and self.path==BASE:
                body=json.dumps({'value':[],'@odata.nextLink':'https://evil.invalid/forbidden'}).encode()
            elif mode['value']=='slow' and self.path==BASE:
                self.send_response(200);self.send_header('Content-Length','100');self.end_headers()
                self.wfile.write(b'{');self.wfile.flush();release.wait(2)
                return
            self.send_response(status)
            for key,value in headers.items():self.send_header(key,value)
            self.send_header('Content-Length',str(len(body)));self.end_headers()
            try:self.wfile.write(body)
            except (BrokenPipeError,ConnectionResetError):pass
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    env={'PATH':os.environ.get('PATH','/usr/bin:/bin'),'PYTHONDONTWRITEBYTECODE':'1','INTUNE_GRAPH_TOKEN':'SYNTHETIC-ONLY-CAPTURE-TOKEN'}
    def check(name,value):
        checks.append({'id':name,'pass':bool(value)})
        if not value:raise AssertionError(name)
    def command(name,argv,expected=0,interrupt=False):
        full=[sys.executable,'-B',str(driver),str(project),str(server.server_port),*map(str,argv)]
        started=time.monotonic()
        if interrupt:
            process=subprocess.Popen(full,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,cwd=output)
            selector=selectors.DefaultSelector();selector.register(process.stderr,selectors.EVENT_READ)
            try:
                if not selector.select(8):raise AssertionError('retry_progress_before_cancel')
                first=process.stderr.readline()
                check('known_delay_displayed_before_sigint',json.loads(first)['retry_in_seconds']==5)
                process.send_signal(signal.SIGINT)
                stdout,stderr=process.communicate(timeout=4);stderr=first+stderr
            finally:
                selector.close()
                if process.poll() is None:process.kill();process.wait()
            code=process.returncode
        else:
            result=subprocess.run(full,capture_output=True,env=env,cwd=output,timeout=12)
            stdout,stderr,code=result.stdout,result.stderr,result.returncode
        elapsed=time.monotonic()-started
        (output/(name+'.stdout')).write_bytes(stdout);(output/(name+'.stderr')).write_bytes(stderr)
        commands.append({'name':name,'argv':full,'exit_code':code,'expected_exit_code':expected,'elapsed_seconds':elapsed})
        check(name+'_exit',code==expected)
        check(name+'_presentation',b'RAW-ONLY-CANARY' not in stdout+stderr and b'SYNTHETIC-ONLY-CAPTURE-TOKEN' not in stdout+stderr)
        return json.loads(stdout),elapsed
    try:
        captured,_=command('capture-retry',['capture','--tenant',T,'--policy',P,'--output',output/'retry'])
        check('five_get_attempts_two_retries',captured['attempt_count']==5 and captured['retry_count']==2 and len(records)==5)
        receipt=json.loads((output/'retry/capture-receipt.json').read_bytes());export=json.loads((output/'retry/export.json').read_bytes())
        check('every_received_body_retained',len(receipt['pages'])==5 and all(hashlib.sha256((output/'retry'/r['raw_path']).read_bytes()).hexdigest()==r['source_byte_sha256'] for r in receipt['pages']))
        check('failed_attempts_not_successful_pages',[len(c['pages']) for c in export['collections']]==[1,1,1])
        check('retry_delay_progress_is_numeric',all(json.loads(line)['retry_in_seconds']==0 for line in (output/'capture-retry.stderr').read_text().splitlines()))
        store=output/'store'
        command('init',['workbench','init','--root',store,'--tenant',T])
        imported,_=command('import',['workbench','import-capture','--root',store,'--capture',output/'retry'])
        inspected,_=command('reopened-inspect',['workbench','inspect','--root',store,'--object',P])
        check('literal_imported_policy',inspected['body']['name']=='Windows Privacy Pilot' and len(inspected['body']['assignments'])==3)
        detail,_=command('collection',['workbench','collection','--root',store,'--run',imported['run_id']])
        check('retry_history_persisted',detail['source']['capture_attempts']['retry_count']==2 and detail['source']['capture_attempts']['attempt_count']==5)
        with sqlite3.connect(store/'observations.sqlite3') as db:
            raw=json.loads(db.execute('SELECT source_json FROM run_details WHERE run_id=?',(imported['run_id'],)).fetchone()[0])
            count=db.execute('SELECT COUNT(*) FROM observations').fetchone()[0]
        check('independent_sqlite_retry_binding',raw['capture_attempts']['retry_count']==2 and count==1 and raw['source_authenticity_verified'] is False)
        mode['value']='denied'
        command('capture-denied',['capture','--tenant',T,'--policy',P,'--output',output/'denied'],2)
        denied,_=command('import-denied',['workbench','import-capture','--root',store,'--capture',output/'denied'],2)
        check('denial_not_promoted',denied['status']=='denied')
        inspected,_=command('inspect-after-denial',['workbench','inspect','--root',store,'--object',P])
        check('last_good_preserved_stale',inspected['body']['name']=='Windows Privacy Pilot' and inspected['freshness']=='stale')
        for scenario in ('exhausted','delay','redirect','origin'):
            mode['value']=scenario
            result,_=command('capture-'+scenario,['capture','--tenant',T,'--policy',P,'--output',output/scenario],2)
            expected={'exhausted':'retry_exhausted','delay':'retry_delay_limit','redirect':'http_error','origin':'untrusted_continuation'}[scenario]
            check(scenario+'_explicit_reason',result['coverage'][0]['reason']==expected)
            command('import-'+scenario,['workbench','import-capture','--root',store,'--capture',output/scenario],2)
        mode['value']='cancel'
        result,elapsed=command('capture-cancel',['capture','--tenant',T,'--policy',P,'--output',output/'cancel'],130,True)
        check('cancel_is_bounded_and_durable',result['cancelled'] is True and result['attempt_count']==1 and elapsed<4)
        command('import-cancel',['workbench','import-capture','--root',store,'--capture',output/'cancel'],2)
        mode['value']='slow'
        result,elapsed=command('capture-deadline',['capture','--tenant',T,'--policy',P,'--output',output/'slow','--max-elapsed-seconds','.1'],2)
        release.set()
        check('body_deadline_bounds_actual_entrypoint',elapsed<2 and all(c['reason']=='time_limit' for c in result['coverage']))
        command('import-deadline',['workbench','import-capture','--root',store,'--capture',output/'slow'],2)
        check('requests_remained_get_and_scoped',all(r['method']=='GET' and r['synthetic_token_matched'] and r['path'] in responses for r in records))
        check('denied_and_redirect_not_retried',all(r['count']==1 for r in records if r['mode'] in ('denied','redirect','delay','cancel')))
        with sqlite3.connect(store/'observations.sqlite3') as db:
            states=db.execute('SELECT status FROM collection_runs ORDER BY run_id').fetchall()
            snapshots=db.execute('SELECT COUNT(*) FROM observations').fetchone()[0]
        check('failed_collections_preserve_one_success',states==[('complete',),('denied',)]+[('partial',)]*6 and snapshots==1)
    finally:
        release.set();server.shutdown();server.server_close();thread.join(timeout=2)
        (output/'requests.json').write_text(json.dumps(records,indent=2))
        (output/'receipt.json').write_text(json.dumps({'schema':'capture-retry-cli-qualification/1','commands':commands,'checks':checks,'success':bool(checks) and all(c['pass'] for c in checks),'source_hashes':{name:hashlib.sha256((project/name).read_bytes()).hexdigest() for name in ('intune_iac/capture.py','intune_iac/capture_adapter.py','intune_iac/cli.py')},'scope':'Actual CLI subprocesses and loopback HTTP, fixed-origin native request path with evaluator-only HTTPS connection substitution; no Graph/TLS/authenticity qualification. Raw SQLite assertions use literal expected values, no product normalizer.'},indent=2))
    print(json.dumps({'checks':len(checks),'commands':len(commands),'success':all(c['pass'] for c in checks)}))

if __name__=='__main__':main()
