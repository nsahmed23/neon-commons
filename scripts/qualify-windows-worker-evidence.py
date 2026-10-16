#!/usr/bin/env python3
"""Real native pinned DLL vectors and signed bundle; no platform activation."""
import argparse,base64,hashlib,json,os,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from intune_iac import windows_worker_evidence as native,windows_capture as capture,windows_storage as storage
from intune_iac.io import AppError,parse_json,canonical

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('vectors','vectors-sha256','verifier-pin','verifier-pin-sha256','scratch','source-pins','source-pins-sha256','envelope','request','trust','expected','expected-sha256','evidence-store','output'):parser.add_argument('--'+name,required=True)
    args=parser.parse_args();output=Path(args.output)
    if output.exists() or output.is_symlink():parser.error('new_output_required')
    result={'schema_version':'windows-worker-evidence-qualification/1','status':'BLOCKED','native_calls':0,'checks':[],
        'platform_qualified':False,'workbench_profile_enabled':False,'production_approved':False,'execution_authorized':False}
    if os.name!='nt' or sys.platform!='win32':
        output.mkdir(mode=0o700);result['blocker']='native_windows_host_required';(output/'RESULT.json').write_bytes(canonical(result));print(json.dumps(result));return 3
    try:
        storage.create_private_directory(str(output.parent),output.name)
        api=native._NativeAPI();read=lambda path: capture._reference_bytes(path,api,16*1024*1024)
        def pinned(path,expected):
            raw=read(path)
            if hashlib.sha256(raw).hexdigest()!=expected:raise AppError('qualification_input_changed','Qualification input pin changed.')
            return parse_json(raw)
        pins=pinned(args.source_pins,args.source_pins_sha256);root=Path(__file__).resolve().parents[1]
        def source_hashes():
            files={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'intune_iac').glob('*.py')}
            files.update({name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ('scripts/intune-windows-evidence.py','scripts/qualify-windows-worker-evidence.py')})
            return files
        actual=source_hashes()
        if pins.get('files')!=actual or type(pins.get('source_commit')) is not str or not native.contract.REV.fullmatch(pins['source_commit']):raise AppError('qualification_source_changed','Exact source pins required.')
        result['source_files']=actual;result['declared_source_commit']=pins['source_commit']
        vectors=pinned(args.vectors,args.vectors_sha256);pin=pinned(args.verifier_pin,args.verifier_pin_sha256);expected=pinned(args.expected,args.expected_sha256)
        if type(vectors) is not list or not 4<=len(vectors)<=100 or not any(v.get('accepted') is True for v in vectors) or not any(v.get('accepted') is False for v in vectors):raise AppError('qualification_vectors_invalid','Independent positive and negative vectors required.')
        with native._verifier(pin,args.scratch,api) as verifier:
            for index,row in enumerate(vectors):
                native.contract.shape(row,'public_key_hex message_base64 signature_base64 accepted')
                if type(row['accepted']) is not bool:raise AppError('qualification_vectors_invalid','Literal expected outcome required.')
                result['native_calls']+=1
                try:verifier(row['public_key_hex'],base64.b64decode(row['message_base64'],validate=True),base64.b64decode(row['signature_base64'],validate=True));accepted=True
                except AppError:accepted=False
                result['checks'].append({'id':'independent-vector-'+str(index),'pass':accepted is row['accepted']})
        from intune_iac.windows_workbench import WindowsWorkbenchStore
        from intune_iac.windows_worker_evidence_store import ingest_windows_evidence,reopen_windows_evidence
        from intune_iac import workbench_evidence_views as views
        from intune_iac.workbench_views import views as four_views
        # Current admissibility needs a store (a loose file has no durable clock mark): ingest into the retained scratch store,
        # then judge the reopened result. Loose-file inspection is historical-only.
        store=WindowsWorkbenchStore.create(args.evidence_store,expected['tenant_id'])
        received=ingest_windows_evidence(args.evidence_store,args.envelope,args.request,args.trust,args.verifier_pin,args.scratch)
        observed=reopen_windows_evidence(args.evidence_store,native.contract.digest(parse_json(read(args.request))),args.trust,args.verifier_pin,args.scratch)
        for key in ('tenant_id','object_id','operation_id','manifest_sha256','evidence_class','baseline_admissible'):
            result['checks'].append({'id':'independent-'+key,'pass':key in expected and observed[key]==expected[key] and type(observed[key]) is type(expected[key])})
        result['observed_result_sha256']=hashlib.sha256(canonical(observed)).hexdigest()
        reopened=reopen_windows_evidence(args.evidence_store,observed['request_sha256'],args.trust,args.verifier_pin,args.scratch)
        link=views.link(store,expected['object_id'],args.evidence_store,observed['request_sha256'],args.trust,args.verifier_pin,args.scratch)
        display=four_views(store,expected['object_id']);history=views.history(store,expected['object_id'])
        result['checks'].extend([
            {'id':'exact-received-reopened-bundle','pass':received['bundle_sha256']==reopened['bundle_sha256']==observed['bundle_sha256']},
            {'id':'native-received-link-inert','pass':link['data']['baseline_admissible'] is False and link['data']['execution_authorized'] is False},
            {'id':'native-shared-proposed-review','pass':display['proposed'].get('approval_digest')==expected['manifest_sha256']},
            {'id':'native-persistent-history','pass':bool(history['entries']) and history['entries'][0]['evidence']['bundle_sha256']==observed['bundle_sha256']},
            {'id':'native-baseline-independent-expectation','pass':(display['deployment']['status']!='unknown') is expected['baseline_admissible']},
            {'id':'source-unchanged-after','pass':source_hashes()==actual}])
        result['source_files_after']=source_hashes()
        result['native_calls_scope']='Count is independently supplied vector calls only; native signed inspect/ingest/reopen/shared views additionally run and are recorded by separate checks.'
        result['retained_evidence_store']=args.evidence_store
        result['status']='PASS' if all(c['pass'] for c in result['checks']) else 'FAIL'
        storage.create_new_file(str(output),'observed.json',canonical(observed))
        storage.create_new_file(str(output),'shared-views.json',canonical(display))
        storage.create_new_file(str(output),'history.json',canonical(history))
    except (AppError,OSError,ValueError,TypeError,KeyError) as error:result.update(status='FAIL',error_code=getattr(error,'code',type(error).__name__))
    try:storage.create_new_file(str(output),'RESULT.json',canonical(result))
    except (AppError,OSError) as recording:
        result.update(status='FAIL',recording_error=getattr(recording,'code',type(recording).__name__),output_preserved=True)
    print(json.dumps({'status':result['status'],'checks':len(result['checks']),'native_calls':result['native_calls']}));return 0 if result['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
