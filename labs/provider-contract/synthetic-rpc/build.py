#!/usr/bin/env python3
"""Build a clearly separate test-only RPC provider from pinned full resource source."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
spec=importlib.util.spec_from_file_location('qualification',ROOT/'scripts/qualify-provider-contract.py')
q=importlib.util.module_from_spec(spec);spec.loader.exec_module(q)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('upstream','go','module-cache','build-cache','output'):p.add_argument('--'+name,required=True)
    args=p.parse_args();source=Path(args.upstream).resolve(strict=True);go=Path(args.go).resolve(strict=True);cache=Path(args.module_cache).resolve(strict=True);buildcache=Path(args.build_cache).resolve(strict=True);out=Path(args.output).absolute()
    for protected in (source,ROOT,cache,buildcache):
        if out.resolve().is_relative_to(protected):raise ValueError('output overlaps protected inputs')
    out.mkdir(mode=0o700,parents=False,exist_ok=False);work=out/'module';work.mkdir();bindir=out/'bin';bindir.mkdir()
    full=json.loads((q.LAB/'full-source-manifest.json').read_text());patch=json.loads((q.LAB/'completion-manifest.json').read_text())
    records=q.verify_sources(source,full['files'])
    for row in records:
        destination=work/row['path'];destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/row['path'],destination)
    q.apply_completion_candidate(work,q.LAB/'completion',patch['files'])
    entry=work/'cmd/intune-synthetic-fixture';entry.mkdir(parents=True)
    for name in ('main.go','fixture.json'):shutil.copyfile(HERE/name,entry/name)
    env={'PATH':str(go.parent)+':/usr/bin:/bin','HOME':str(out),'GOMODCACHE':str(cache),'GOCACHE':str(buildcache),'GOTOOLCHAIN':'local','GOPROXY':'off','GOSUMDB':'off','GOTELEMETRY':'off','CGO_ENABLED':'0','GOMAXPROCS':'1','GOGC':'20','GOMEMLIMIT':'5GiB'}
    receipt={'production_qualified':False,'production_provider':False,'scope':'test-only provider Configure plus actual repaired resource; GET-only synthetic transport','provider_commit':full['provider_commit'],'candidate_manifest_sha256':hashlib.sha256((q.LAB/'completion-manifest.json').read_bytes()).hexdigest(),'go_sha256':q.verify_go(go),'fixture_sources':{name:hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in ('main.go','fixture.json','main.tf.json.txt','run.py','build.py')}}
    binary=bindir/'terraform-provider-microsoft365';command=[str(go),'build','-buildvcs=false','-mod=readonly','-p=1','-o',str(binary),'./cmd/intune-synthetic-fixture'];receipt['command']=command
    try:
        code,_=q.run_logged(command,work,env,out,1800);receipt.update(status='built-test-only-provider' if code==0 else 'failed',returncode=code)
        if code==0:receipt['binary_sha256']=hashlib.sha256(binary.read_bytes()).hexdigest()
    except Exception as exc:receipt.update(status='failed',error=type(exc).__name__+': '+str(exc))
    (out/'result.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({k:v for k,v in receipt.items() if k in ('status','binary_sha256','error')}))

if __name__=='__main__':main()
