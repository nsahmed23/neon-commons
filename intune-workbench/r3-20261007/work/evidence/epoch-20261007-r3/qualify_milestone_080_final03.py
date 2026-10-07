#!/usr/bin/env python3
"""Local immutable-artifact qualification orchestration; no cloud operations."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import zipfile

ROOT=Path('/workspace/intune-continuation/work/projects/intune')
EVIDENCE=Path('/workspace/intune-continuation/work/evidence/epoch-20261007-r3/milestone-0.8.0-final03')
RELEASE=Path('/workspace/intune-continuation/work/releases/continuation-0.8.0-r3-final03')
PYTHON='/workspace/intune-runtime/bin/python'
VALIDATOR='/workspace/intune-continuation/work/evidence/epoch-20261005/approval-prerequisite/libsodium.so.23.3.0'
TOFU='/workspace/intune-recovery/native-reprobe/tools/tofu'
PROVIDER='/workspace/intune-recovery/native-reprobe/tools/terraform-provider-microsoft365'
ENV={'PATH':'/workspace/intune-runtime/bin:/usr/local/bin:/usr/bin:/bin',
     'HOME':os.environ['HOME'],'LANG':'C.UTF-8','LC_ALL':'C.UTF-8',
     'PYTHONDONTWRITEBYTECODE':'1','INTUNE_TEST_VALIDATOR_LIBRARY':VALIDATOR,
     'INTUNE_TEST_TOFU_EXECUTABLE':TOFU}

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()
def write(path,value):
    with Path(path).open('x') as stream:json.dump(value,stream,indent=2);stream.write('\n')
def command(name,argv,cwd):
    start=time.monotonic();started=datetime.now(timezone.utc).isoformat()
    stdout=EVIDENCE/(name+'.stdout');stderr=EVIDENCE/(name+'.stderr')
    with stdout.open('xb') as out,stderr.open('xb') as err:
        process=subprocess.run(argv,cwd=cwd,env=ENV,stdout=out,stderr=err,timeout=1200)
    result={'command':argv,'cwd':str(cwd),'started_at':started,
            'finished_at':datetime.now(timezone.utc).isoformat(),'elapsed_seconds':time.monotonic()-start,
            'exit_code':process.returncode,'stdout':{'path':str(stdout),'sha256':sha(stdout)},
            'stderr':{'path':str(stderr),'sha256':sha(stderr)},
            'environment_profile':'minimal PATH/HOME/LANG/LC_ALL; PYTHONDONTWRITEBYTECODE=1; explicit exact validator and ToFu paths'}
    write(EVIDENCE/(name+'.command.json'),result)
    return result

def snapshot(root):
    return {p.relative_to(root).as_posix():sha(p) for p in sorted(root.rglob('*')) if p.is_file()}
def expected_archive(archive):
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.testzip() is None
        return {n.partition('/')[2]:hashlib.sha256(bundle.read(n)).hexdigest() for n in bundle.namelist()}
def prereqs():
    pins={VALIDATOR:'fe00408090ea084504d7cb0130af56a22554fe299034b864551b65a64ca8a7b5',
          TOFU:'a325c8c2f6834575e440b03c2ba67f94256072754ac7787fea718be6f01fef6a',
          PROVIDER:'415097131c64a47c8435ce9528d050382996cfa4bed38d0960548f160a0b0dd3',
          '/tmp/intune-native-completion/tofu':'0a9eda0f0898896969492504a6ce778f310675e8a1eb960434c26806cd252627'}
    rows=[]
    for path,expected in pins.items():
        actual=sha(path);rows.append({'path':path,'sha256':actual,'expected_sha256':expected,'matches':actual==expected})
    assert all(r['matches'] for r in rows),rows
    return rows

def build(commit, resume=False):
    if not resume: EVIDENCE.mkdir(mode=0o700,exist_ok=False)
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==commit
    assert not subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip()
    if not resume:
        write(EVIDENCE/'prerequisites.json',prereqs())
        result=command('build',[PYTHON,'-B','scripts/build-release.py','--output-dir',str(RELEASE)],ROOT)
        assert result['exit_code']==0,result
    else:
        assert json.loads((EVIDENCE/'build.command.json').read_text())['exit_code']==0
        prereqs()
    receipt=json.loads((RELEASE/'Intune_IaC_Plugin_Archive_Receipt.json').read_text())
    source=next(a for a in receipt['archives'] if a['filename'].endswith('_Source.zip'))
    runtime=next(a for a in receipt['archives'] if not a['filename'].endswith('_Source.zip'))
    archive=RELEASE/source['filename'];assert sha(archive)==source['sha256']
    tree=subprocess.check_output(['git','ls-tree','-rz',commit],cwd=ROOT).split(b'\0')
    git_blobs={row.split(b'\t',1)[1].decode():row.split(b' ',2)[2].split(b'\t',1)[0].decode() for row in tree if row}
    historical_manifest_blob=git_blobs.pop('SHA256SUMS',None)
    with zipfile.ZipFile(archive) as bundle:
        blobs={}
        for name in bundle.namelist():
            relative=name.partition('/')[2]
            if relative=='SHA256SUMS':continue
            data=bundle.read(name)
            blobs[relative]=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
    assert blobs==git_blobs,{'missing':sorted(set(git_blobs)-set(blobs)),'extra':sorted(set(blobs)-set(git_blobs)),
                             'changed':[n for n in blobs.keys()&git_blobs.keys() if blobs[n]!=git_blobs[n]]}
    extraction=EVIDENCE/'source-extracted'
    result=command('extract',[PYTHON,'-B','scripts/verify-release-artifact.py','--archive',str(archive),
                             '--sha256',source['sha256'],'--extract',str(extraction)],ROOT)
    assert result['exit_code']==0,result
    extracted=extraction/'intune-iac-source'
    expected=expected_archive(archive);before=snapshot(extracted);assert expected==before
    write(EVIDENCE/'source-before.json',before)
    write(EVIDENCE/'artifact-binding.json',{'commit':commit,'source_payloads_match_git':True,
          'excluded_git_metadata':{'SHA256SUMS':historical_manifest_blob},
          'excluded_metadata_reason':'Historical preserved root manifest; release generates and independently verifies its own exact contents manifest.',
          'source_payloads':len(blobs),'source':source,'runtime':runtime,'release':str(RELEASE),
          'extracted_source':str(extracted),'archive_and_extracted_file_maps_match':True})
    runtime_result=command('extract-runtime',[PYTHON,'-B','scripts/verify-release-artifact.py','--archive',str(RELEASE/runtime['filename']),'--sha256',runtime['sha256'],'--extract',str(EVIDENCE/'runtime-extracted')],ROOT)
    assert runtime_result['exit_code']==0,runtime_result
    write(EVIDENCE/'runtime-before.json',snapshot(EVIDENCE/'runtime-extracted/intune-iac'))
    print(json.dumps({'stage':'build','success':True,'commit':commit,'source':source,'extracted_source':str(extracted)},indent=2),flush=True)

def qualify():
    binding=json.loads((EVIDENCE/'artifact-binding.json').read_text());source=Path(binding['extracted_source'])
    before=json.loads((EVIDENCE/'source-before.json').read_text());assert snapshot(source)==before
    prereqs()
    previous=EVIDENCE.parent/'milestone-0.8.0-final02'
    old=json.loads((previous/'QUALIFICATION.json').read_text())
    assert old['strict']['passed']==1241 and old['strict']['failures']==1 and old['strict']['errors']==0
    assert old['source_integrity']['source_unchanged'] and old['source_integrity']['runtime_unchanged']
    old_binding=json.loads((previous/'artifact-binding.json').read_text())
    old_release=Path(old_binding['release'])
    old_map=expected_archive(old_release/old_binding['source']['filename'])
    new_map=expected_archive(RELEASE/binding['source']['filename'])
    assert old_map.keys()==new_map.keys()
    changed=sorted(n for n in old_map if old_map[n]!=new_map[n])
    assert changed==['SHA256SUMS','plugin_tests/test_native_smoke_observation_epoch.py'],changed
    runtime_equal=(old_release/old_binding['runtime']['filename']).read_bytes()==(RELEASE/binding['runtime']['filename']).read_bytes()
    assert runtime_equal and binding['runtime']==old_binding['runtime']
    reused={name:value for name,value in old['commands'].items() if name not in ('strict','connected-source','rebuild')}
    assert all(row['exit_code']==0 for row in reused.values())
    reuse={'status':'PASS_BYTE_EQUIVALENT_SCOPE_REUSE','current_commit':binding['commit'],
       'prior_commit':old_binding['commit'],'current_source':binding['source'],'prior_source':old_binding['source'],
       'runtime_archive_byte_identical':runtime_equal,'runtime':binding['runtime'],
       'source_archive_changed_paths':changed,'application_grader_fixture_and_harness_files_unchanged':True,
       'prior_strict_failure_preserved':old['strict'],'prior_qualification_sha256':sha(previous/'QUALIFICATION.json'),
       'reused_commands_with_original_paths_and_hashes':reused,
       'scope':'Only test and regenerated contents manifest changed. All product, checker, fixture and native harness bytes remain identical. Prior successful scoped commands retain their original source/archive identities; the failed strict result is not reused as a pass. Exact unchanged runtime native/capacity evidence remains applicable. New source strict, connected CLI/PTY and rebuild run separately.'}
    write(EVIDENCE/'REUSED-QUALIFICATION-EVIDENCE.json',reuse)
    jobs={'strict':[PYTHON,'-B','scripts/verify-plugin.py','--include-core','--output',str(EVIDENCE/'strict-suite')],
      'connected-source':[PYTHON,'-B','scripts/qualify-workbench-connected.py','--plugin',str(source),'--python',PYTHON,'--output',str(EVIDENCE/'connected-source')],
      'rebuild':[PYTHON,'-B','scripts/build-release.py','--output-dir',str(EVIDENCE/'independent-rebuild')]}
    results={}
    with ThreadPoolExecutor(max_workers=2) as pool:
      futures={pool.submit(command,name,argv,source):name for name,argv in jobs.items()}
      for future in as_completed(futures):
        name=futures[future]
        try: results[name]=future.result()
        except BaseException as exc:
          results[name]={'exception':type(exc).__name__,'detail':str(exc),'exit_code':None};write(EVIDENCE/(name+'.exception.json'),results[name])
        print(json.dumps({'completed':name,'result':results[name]}),flush=True)
    after=snapshot(source);write(EVIDENCE/'source-after.json',after)
    equality={'source_unchanged':before==after,'source_matches_archive':after==new_map,'archives':[]}
    for row in (binding['source'],binding['runtime']):
      original=RELEASE/row['filename'];rebuilt=EVIDENCE/'independent-rebuild'/row['filename']
      actual=sha(rebuilt) if rebuilt.is_file() else None
      equality['archives'].append({'filename':row['filename'],'original_sha256':sha(original),'rebuilt_sha256':actual,
        'byte_identical':actual==row['sha256'] and original.read_bytes()==rebuilt.read_bytes() if rebuilt.is_file() else False})
    runtime_after=snapshot(EVIDENCE/'runtime-extracted/intune-iac');write(EVIDENCE/'runtime-after.json',runtime_after)
    equality['runtime_unchanged']=runtime_after==json.loads((EVIDENCE/'runtime-before.json').read_text())
    equality['runtime_matches_archive']=runtime_after==expected_archive(RELEASE/binding['runtime']['filename'])
    write(EVIDENCE/'reproducibility.json',equality)
    strict=json.loads((EVIDENCE/'strict-suite/result.json').read_text()) if (EVIDENCE/'strict-suite/result.json').is_file() else None
    journey=json.loads((EVIDENCE/'connected-source/receipt.json').read_text()) if (EVIDENCE/'connected-source/receipt.json').is_file() else None
    journey_pass=bool(journey and journey.get('status')=='PASS' and len(journey.get('checks',[]))==64)
    qualified=(journey_pass and all(r.get('exit_code')==0 for r in results.values()) and bool(strict and strict.get('success'))
       and equality['source_unchanged'] and equality['source_matches_archive'] and equality['runtime_unchanged'] and equality['runtime_matches_archive'] and all(r['byte_identical'] for r in equality['archives']))
    report={'candidate':binding,'commands':results,'source_integrity':equality,'strict':strict,
       'new_connected_source_qualified':journey_pass,'reused_scoped_evidence':reuse,'local_candidate_qualified':qualified,
       'production_qualified':False,'live_service_qualified':False,
       'limits':'Exact final03 source strict/connected/rebuild; byte-identical runtime and unchanged application/harness scopes reuse identified final02 successful receipts. No missing live/platform/organizational gate is passed; historical failures and actor-attribution gap remain open.'}
    write(EVIDENCE/'QUALIFICATION.json',report)
    print(json.dumps({'stage':'qualify','local_candidate_qualified':qualified,'strict':strict},indent=2),flush=True)
    return 0 if qualified else 1

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=('build','qualify'));parser.add_argument('--commit');parser.add_argument('--resume',action='store_true');args=parser.parse_args()
    if args.stage=='build':build(args.commit,args.resume)
    else:raise SystemExit(qualify())
