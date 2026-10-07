#!/usr/bin/env python3
"""Qualification-only native capture→SQLite→text journey using invented Graph replies.

No credentials are loaded and no network is used. A native PASS establishes
only the recorded laboratory service route on the named Windows/SQLite host.
"""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from intune_iac.io import AppError,canonical,parse_json
from intune_iac.identity_binding import ClientSecretHandle
from intune_iac.observation_reader import ReaderSpec,bind_laboratory_reader
from intune_iac.observation_jobs import _Fixture
from intune_iac.synthetic import generate_estate
from intune_iac.windows_workbench import WindowsWorkbenchStore
from intune_iac.windows_observation import bind_native_target
from intune_iac.windows_storage import create_private_directory

REQUIRED_FILES=tuple(sorted(str(path.relative_to(ROOT)).replace('\\','/') for path in (ROOT/'intune_iac').glob('*.py')))+(
    'scripts/intune-windows-inspect.py','scripts/qualify-windows-observation.py')
CLIENT='11111111-1111-4111-8111-111111111111';PRINCIPAL='33333333-3333-4333-8333-333333333333'
SECRET='WINDOWS-OBSERVATION-INVENTED-SECRET';TOKEN='WINDOWS-OBSERVATION-INVENTED-TOKEN'


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def fixture(estate):
    from urllib.parse import urlsplit
    tenant=estate['truth']['tenant_id'];oid=estate['truth']['policies'][0]['id']
    rows=[dict(method='POST',host='login.microsoftonline.com',path='/'+tenant+'/oauth2/v2.0/token',status=200,
        body={'token_type':'Bearer','expires_in':3600,'access_token':TOKEN}),
        dict(method='GET',host='graph.microsoft.com',path="/v1.0/servicePrincipals(appId='"+CLIENT+"')?$select=id,appId,accountEnabled",status=200,
            body={'id':PRINCIPAL,'appId':CLIENT,'accountEnabled':True})]
    for kind in ('policies','settings','assignments'):
        collection=next(item for item in estate['capture']['collections'] if item['kind']==kind and item['owner_id']==(None if kind=='policies' else oid))
        for page in collection['pages']:
            url=urlsplit(page['request_url']);body=parse_json(canonical(page['body']))
            if kind=='assignments':
                for assignment in body['value']:assignment.update(source='direct',sourceId=None)
            rows.append(dict(method='GET',host='graph.microsoft.com',path=url.path+('?' +url.query if url.query else ''),status=200,body=body))
    return {'schema_version':'intune-observer-fixture/1','responses':rows}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qualification-only',action='store_true',required=True)
    for name in ('disposable-parent','output'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--source-pins');parser.add_argument('--source-pins-sha256');args=parser.parse_args(argv)
    output=Path(args.output).absolute()
    if output.exists() or output.is_symlink() or output.resolve().is_relative_to(ROOT) or any(p.is_symlink() for p in output.parents):parser.error('new_output_outside_package_required')
    if os.name=='nt' and sys.platform=='win32':
        try:create_private_directory(str(output.parent),output.name)
        except AppError as error:
            print(json.dumps({'status':'BLOCKED','code':error.code,'native_checks':0,'commands':0,
                'private_output_established':False,'retained_output_path':str(output),'storage_outcome':getattr(error,'storage_outcome',None)}));return 3
    else:output.mkdir(parents=True,mode=0o700)
    files={name:sha(ROOT/name) for name in REQUIRED_FILES}
    result={'schema_version':'intune-windows-observation-qualification/1','status':'BLOCKED','checks':[],
        'commands':[],'source_files':files,'blockers':[],'platform_qualified':False,'production_approved':False,
        'workbench_profile_enabled':False,'service_authenticity_qualified':False,
        'environment':{'platform':sys.platform,'python':sys.version,'sqlite':sqlite3.sqlite_version,'executable_sha256':sha(sys.executable)},
        'scope':'Actual native storage/capture/publication and readonly text; invented service replies, no network, no device or host-crash qualification.'}
    def check(name,passed):result['checks'].append({'id':name,'pass':bool(passed)})
    def finish(code):
        result['source_files_after']={name:sha(ROOT/name) for name in REQUIRED_FILES}
        if result['source_files_after']!=files:result['status']='FAIL';code=1
        (output/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'status':result['status'],'native_checks':len(result['checks']),'commands':len(result['commands'])}));return code
    if os.name!='nt' or sys.platform!='win32':
        result['blockers'].append({'code':'native_windows_host_required','owner':'Windows endpoint/runner owner'});return finish(3)
    target=None;credential=None;reader=None
    try:
        if sys.version_info[:2]!=(3,12) or ctypes.sizeof(ctypes.c_void_p)!=8:raise ValueError('native_cpython_312_64bit_required')
        pins=Path(args.source_pins or '')
        if sha(pins)!=args.source_pins_sha256:raise ValueError('source_pin_manifest_mismatch')
        body=pins.read_bytes()
        if len(body)>1024*1024:raise ValueError('source_pin_manifest_limit')
        manifest=parse_json(body)
        if set(manifest)!={'source_commit','files'} or not re.fullmatch('[a-f0-9]{40}',manifest['source_commit']) or manifest['files']!=files:raise ValueError('exact_source_files_required')
        result['declared_source_commit']=manifest['source_commit'];(output/'source-pins.json').write_bytes(body)
        estate=generate_estate(seed=840,policy_count=1);tenant=estate['truth']['tenant_id'];oid=estate['truth']['policies'][0]['id']
        root=Path(args.disposable_parent)/('observation-'+uuid.uuid4().hex)
        create_private_directory(str(root.parent),root.name);result['retained_disposable_root']=str(root)
        store=WindowsWorkbenchStore.create(str(root/'store'),tenant);target=bind_native_target(str(root/'store'),tenant)
        replies=fixture(estate);(output/'invented-fixture.json').write_bytes(canonical(replies)+b'\n')
        transport=_Fixture(canonical(replies));credential=ClientSecretHandle(SECRET)
        reader=bind_laboratory_reader(ReaderSpec(tenant,CLIENT,PRINCIPAL,(oid,)),credential=credential,transport=transport)
        capture=target.capture(reader,oid,str(root/'capture'))
        first=target.publish([capture],job_id='a'*32,attempt_id='b'*32)[0]
        check('native-capture-and-publication-complete',first['status']=='complete')
        check('physical-native-does-not-promote-source',first['evidence_class']=='graph_reader_laboratory' and first['assurance']['source_authenticity_verified'] is False)
        check('byte-exact-raw-page',(root/'capture'/'raw'/'page-000000.json').read_bytes()==canonical(replies['responses'][2]['body']))
        check('same-operation-replay-idempotent',target.publish([capture],job_id='a'*32,attempt_id='b'*32)[0]==first)
        second=target.publish([capture],job_id='a'*32,attempt_id='c'*32)[0]
        check('new-attempt-duplicate-recorded',second['source']['duplicate_of_run_id']==first['run_id'])
        with sqlite3.connect(root/'store'/'observations.sqlite3') as db:
            check('independent-two-attempts-one-observation',tuple(db.execute('SELECT COUNT(*) FROM '+name).fetchone()[0] for name in ('collection_runs','observations','snapshots'))==(2,1,1))
            check('independent-no-authenticated-label',db.execute("SELECT count(*) FROM run_details WHERE evidence_class='graph_authenticated_observation'").fetchone()[0]==0)
        for operation,tail in (('inspect',[oid]),('raw',[oid]),('history',[oid]),('storage-status',[])):
            command=[sys.executable,'-B',str(ROOT/'scripts/intune-windows-inspect.py'),'--qualification-only','--store',str(root/'store'),'--tenant',tenant,operation,*tail]
            row={'id':operation,'argv':command,'exit':None};result['commands'].append(row)
            try:child=subprocess.run(command,capture_output=True,timeout=30,shell=False)
            except subprocess.TimeoutExpired as error:
                (output/(operation+'.stdout.raw')).write_bytes(error.stdout or b'');(output/(operation+'.stderr.raw')).write_bytes(error.stderr or b'');row['timed_out']=True;raise
            row['exit']=child.returncode;(output/(operation+'.stdout.raw')).write_bytes(child.stdout);(output/(operation+'.stderr.raw')).write_bytes(child.stderr)
            value=parse_json(child.stdout) if child.returncode==0 else {}
            check('actual-text-'+operation,child.returncode==0 and value.get('qualification_only') is True and value.get('platform_qualified') is False)
        capture._source.update(evidence_class='graph_authenticated_observation',source_authenticity_verified=True,source_is_synthetic=False)
        rejected=False
        try:target.publish([capture],job_id='a'*32,attempt_id='d'*32)
        except AppError as error:rejected=error.code=='reader_capture_changed'
        check('source-label-mutation-rejected',rejected)
        with sqlite3.connect(root/'store'/'observations.sqlite3') as db:
            check('rejected-source-did-not-publish',db.execute('SELECT COUNT(*) FROM collection_runs').fetchone()[0]==2)
        check('all-reader-requests-consumed',transport.position==len(transport.rows))
        check('no-secret-in-retained-capture',all(SECRET.encode() not in path.read_bytes() and TOKEN.encode() not in path.read_bytes() for path in (root/'capture').rglob('*') if path.is_file()))
        result['status']='PASS' if all(item['pass'] for item in result['checks']) else 'FAIL'
        return finish(0 if result['status']=='PASS' else 1)
    except (AppError,OSError,ValueError,TypeError,subprocess.SubprocessError) as error:
        result['status']='UNSUPPORTED' if getattr(error,'code',None)=='windows_storage_namespace_flush_unavailable' else 'FAIL'
        result['blockers'].append({'code':getattr(error,'code',type(error).__name__),'owner':'Native implementation/qualification owner',
            'storage_outcome':getattr(error,'storage_outcome',None),'observation_outcome':getattr(error,'observation_outcome',None)})
        return finish(1)
    finally:
        if reader is not None:reader.close()
        if credential is not None:credential.close()
        if target is not None:target.close()

if __name__=='__main__':raise SystemExit(main())
