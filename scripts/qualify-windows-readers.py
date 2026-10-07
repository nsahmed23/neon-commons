#!/usr/bin/env python3
"""Native reader qualification against a separately pinned local capture.

Use an owner-only NTFS fixture prepared through the native storage component.
This procedure retains all source capture bytes, creates a NEW disposable store
and exercises the actual qualification-only text entrypoint. No service calls.
"""
import argparse
import base64
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
from intune_iac.io import AppError,parse_json
from intune_iac.windows_capture import load_windows_capture
from intune_iac.windows_workbench import WindowsWorkbenchStore
from intune_iac.windows_storage import create_private_directory

REQUIRED_FILES=('intune_iac/capture_adapter.py','intune_iac/windows_capture.py',
    'intune_iac/windows_workbench.py','intune_iac/workbench_store.py','intune_iac/workbench_provenance.py',
    'intune_iac/windows_directory.py','intune_iac/windows_storage.py','intune_iac/windows_sqlite.py',
    'intune_iac/workbench_schema.py','intune_iac/observation_contract.py','intune_iac/io.py',
    'intune_iac/production.py','scripts/intune-windows-inspect.py','scripts/qualify-windows-readers.py',
    'corrections/contracts/capability-map.json','corrections/contracts/vendor-documentation.json')


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def _run(identifier, argv, output, result):
    try:child=subprocess.run(argv,capture_output=True,timeout=30,shell=False)
    except subprocess.TimeoutExpired as error:
        (output/(identifier+'.stdout.raw')).write_bytes(error.stdout or b'')
        (output/(identifier+'.stderr.raw')).write_bytes(error.stderr or b'')
        result['commands'].append({'id':identifier,'argv':argv,'exit':None,'timed_out':True})
        raise
    except OSError:
        result['commands'].append({'id':identifier,'argv':argv,'exit':None,'launch_failed':True})
        raise
    (output/(identifier+'.stdout.raw')).write_bytes(child.stdout)
    (output/(identifier+'.stderr.raw')).write_bytes(child.stderr)
    result['commands'].append({'id':identifier,'argv':argv,'exit':child.returncode})
    return child


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('capture','expected-capture-sha256','tenant','disposable-parent','output'):
        parser.add_argument('--'+name,required=True)
    parser.add_argument('--source-pins');parser.add_argument('--source-pins-sha256')
    for name in ('reference','reference-sha256','reference-revision','reference-url','reference-license'):
        parser.add_argument('--'+name)
    args=parser.parse_args(argv)
    output=Path(args.output).absolute()
    if output.exists() or output.is_symlink() or output.resolve().is_relative_to(ROOT) or any(p.is_symlink() for p in output.parents):
        parser.error('new_output_outside_package_required')
    if sys.platform=='win32' and os.name=='nt':
        try:create_private_directory(str(output.parent),output.name)
        except AppError as error:
            # Do not place raw inspection output in a namespace whose privacy
            # or required barriers failed. Retain any uncertain created root.
            print(json.dumps({'status':'BLOCKED','code':error.code,'checks':0,'commands':0,
                'private_output_established':False,'retained_output_path':str(output),
                'storage_outcome':getattr(error,'storage_outcome',None),'platform_qualified':False}))
            return 3
    else:output.mkdir(parents=True,mode=0o700)
    files={name:sha(ROOT/name) for name in REQUIRED_FILES}
    result={'schema_version':'intune-windows-readers-qualification/1','status':'BLOCKED','checks':[],
        'commands':[],'source_files':files,'blockers':[],'platform_qualified':False,
        'production_approved':False,'workbench_profile_enabled':False,
        'environment':{'platform':sys.platform,'python':sys.version,'executable_sha256':sha(sys.executable),'sqlite':sqlite3.sqlite_version},
        'scope':'Native private local capture and same-engine readonly text; no Graph, CI, device, host-crash or supported Windows profile claim.'}
    def finish(code):
        result['source_files_after']={name:sha(ROOT/name) for name in REQUIRED_FILES}
        if result['source_files_after']!=files:result['status']='FAIL';code=1
        (output/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'status':result['status'],'checks':len(result['checks']),'commands':len(result['commands'])}));return code
    if sys.platform!='win32' or os.name!='nt':
        result['blockers'].append({'code':'native_windows_host_required','owner':'Windows endpoint/runner owner'})
        return finish(3)
    def check(identifier,passed):result['checks'].append({'id':identifier,'pass':bool(passed)})
    try:
        if sys.version_info[:2]!=(3,12) or ctypes.sizeof(ctypes.c_void_p)!=8:
            raise ValueError('native_cpython_312_64bit_required')
        pins=Path(args.source_pins or '')
        if sha(pins)!=args.source_pins_sha256:raise ValueError('source_pin_manifest_mismatch')
        body=pins.read_bytes()
        if len(body)>1024*1024:raise ValueError('source_pin_manifest_limit')
        manifest=parse_json(body)
        if set(manifest)!={'source_commit','files'} or not re.fullmatch('[a-f0-9]{40}',manifest['source_commit']) or manifest['files']!=files:
            raise ValueError('exact_source_files_required')
        result['declared_source_commit']=manifest['source_commit']
        result['source_linkage_assurance']='Exact pins checked; verify linkage to reviewed commit independently.'
        (output/'source-pins.json').write_bytes(body)
        batch=load_windows_capture(args.capture,tenant_id=args.tenant)
        if batch['capture_sha256']!=args.expected_capture_sha256:raise ValueError('capture_pin_mismatch')
        if batch['status']!='complete':raise ValueError('complete_disposable_fixture_required')
        check('native-capture-exact-separate-pin',True)
        check('native-capture-no-service-authority',batch['source']['source_authenticity_verified'] is False and batch['source']['execution_authorized'] is False)
        before={row['path']:sha(row['path']) for row in list(batch['source']['artifacts'].values()) if type(row) is dict}
        before.update({row['path']:sha(row['path']) for row in batch['source']['artifacts']['raw_pages']})
        root=Path(args.disposable_parent)/('intune-readers-'+uuid.uuid4().hex)
        result['retained_fixture']=str(root)
        (output/'planned-fixture.json').write_text(json.dumps({'root':str(root),'capture':args.capture,'source_files':files})+'\n')
        store=WindowsWorkbenchStore.create(str(root),args.tenant)
        receipt=store.import_capture(args.capture)
        check('native-capture-import-complete',receipt['status']=='complete')
        # A separately pinned invented reference proves byte preservation;
        # its supplied revision/license labels establish no vendor authority.
        reference=Path(args.reference or '')
        imported=store.reference_import(str(reference),args.reference_sha256,args.reference_revision,
            args.reference_url,args.reference_license)
        with reference.open('rb') as stream:raw_reference=stream.read(512*1024+1)
        if len(raw_reference)>512*1024 or hashlib.sha256(raw_reference).hexdigest()!=args.reference_sha256:
            raise ValueError('reference_pin_mismatch')
        artifact=store.artifacts(kind='source_reference')[0]['data']
        check('reference-original-bytes-retained',base64.b64decode(artifact['raw_bytes_base64'],validate=True)==raw_reference)
        check('reference-does-not-promote-authority',artifact['source_authenticity_verified'] is False and artifact['execution_authorized'] is False and artifact['tenant_object_identity']=='not_established')
        with sqlite3.connect(root/'observations.sqlite3') as db:
            check('independent-one-attempt',db.execute('SELECT count(*) FROM collection_runs').fetchone()[0]==1)
            check('independent-one-snapshot',db.execute('SELECT count(*) FROM snapshots').fetchone()[0]==1)
        for operation,tail in (('inspect',[batch['object_id']]),('raw',[batch['object_id']]),
                ('history',[batch['object_id']]),('dictionary',['--object-id',batch['object_id']]),
                ('lineage',[batch['object_id']]),('reference-compare',[batch['object_id'],imported['artifact_id']])):
            argv=[sys.executable,'-B',str(ROOT/'scripts/intune-windows-inspect.py'),'--qualification-only',
                '--store',str(root),'--tenant',args.tenant,operation,*tail]
            child=_run(operation,argv,output,result)
            value=parse_json(child.stdout) if child.returncode==0 else {}
            check('text-'+operation,child.returncode==0 and value.get('qualification_only') is True and value.get('platform_qualified') is False)
            if operation=='raw':check('text-raw-exact-local-byte-integrity',value.get('result',{}).get('capture_integrity',{}).get('status')=='verified_local_bytes')
            if operation=='dictionary':
                check('text-dictionary-explicit-provenance',value.get('result',{}).get('fact_provenance_contract',{}).get('schema_version')=='workbench-dictionary-provenance/1')
            if operation=='reference-compare':check('text-comparison-no-execution-authority',value.get('result',{}).get('execution_authorized') is False)
        check('all-original-capture-bytes-preserved',all(sha(path)==digest for path,digest in before.items()))
        check('original-reference-bytes-preserved',sha(reference)==args.reference_sha256)
        result['status']='PASS' if all(row['pass'] for row in result['checks']) else 'FAIL'
        return finish(0 if result['status']=='PASS' else 1)
    except (AppError,OSError,ValueError,TypeError,subprocess.SubprocessError) as error:
        result['status']='UNSUPPORTED' if getattr(error,'code',None)=='windows_storage_namespace_flush_unavailable' else 'FAIL'
        result['blockers'].append({'code':getattr(error,'code',type(error).__name__),'owner':'Native platform implementation/qualification owner'})
        return finish(1)


if __name__=='__main__':raise SystemExit(main())
