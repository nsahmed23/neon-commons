#!/usr/bin/env python3
"""Verify existing pinned qualification inputs or rebuild exact relay bytes.

No network/download/install, Docker daemon change, image pull or tool repinning.
Outputs preserve partial failures in a new private directory. Source/tool bytes
do not establish the required native host or CI environment qualifications.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import qualification_tools as q

COMPILER_SHA='a23ecab8ff08f09ad8c80602c2c5df7f49e09c25905cb8975902e101bf72635f'
SOURCE_PINS={'relay_v2':'14a942e442439c98a90d5af3f28f12c95c261dc0693e784655fdbc05e4dd278c',
    'relay_v3':'0817bf6ee26a98c338e2c1a348d7ac3b18508b1ad34c6c2c053384592893bc66'}
# Reviewed Debian14 static build profile from retained v3 reproduction receipt.
BUILD_INPUTS={
 '/usr/bin/x86_64-linux-gnu-ld.bfd':'d2766988b6a1b1d1518cdc09242e726d1f24e151e16410ada3092b11ffd9081b',
 '/usr/lib/x86_64-linux-gnu/libc.a':'421b7c3395b35301a4626593b35842849ae1ba43582320383ffbc9790d918515',
 '/usr/lib/gcc/x86_64-linux-gnu/14/libgcc.a':'c53c33f587ceaf0fc9a4b6bb5c5437082068f64ac70eb3b7a0d899e7ac5ffd3d',
 '/usr/lib/gcc/x86_64-linux-gnu/14/libgcc_eh.a':'4622efa3af50eaea4fbb4bc520ada4c88008c5343e0ad306633821fd2432102d',
 '/usr/lib/x86_64-linux-gnu/crt1.o':'8cd1a50edd44a4ded5856bf2254dc106401b37c285dcc55a594475438cd6ec1a',
 '/usr/lib/x86_64-linux-gnu/crti.o':'78acef26a7007f5320c98633376f2903e33895e694fbc2b91d189b38addbca8a',
 '/usr/lib/gcc/x86_64-linux-gnu/14/crtbeginT.o':'d4c928492dd7f652f72fa706bd59b0e77eb3d842863d2287a9059e37b4bf5ba2',
 '/usr/lib/gcc/x86_64-linux-gnu/14/crtend.o':'8981687575c10a2e2146947bce387769cbd118f5b8c5dda489f514dc7d2ed4c7',
 '/usr/lib/x86_64-linux-gnu/crtn.o':'121f2a5f12b13471dd8c7dabe3ff334df08540c270564d1a2b3c47ecbd8d3101'}
FLAGS=['-static','-O2','-fstack-protector-strong','-D_FORTIFY_SOURCE=2','-Wall','-Wextra','-Werror','-pthread','-Wl,-z,relro,-z,now']

def new_directory(path):
    path=q.absolute(path)
    with q.parent(path) as (parent,name):
        os.mkdir(name,0o700,dir_fd=parent)
        fd=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
        info=os.fstat(fd)
        try:q.require(info.st_uid==os.geteuid() and not info.st_mode&0o077,'New preparation root must be private')
        except BaseException:os.close(fd);raise
        os.fsync(parent)
        return path,fd

def write(fd,name,raw,mode=0o600):
    child=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode,dir_fd=fd)
    with os.fdopen(child,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    os.fsync(fd)

def document(fd,name,value):write(fd,name,(json.dumps(value,indent=2,sort_keys=True,ensure_ascii=True)+'\n').encode())

def guard(root,fd):
    with q.parent(root) as (parent,name):
        observed=os.stat(name,dir_fd=parent,follow_symlinks=False);held=os.fstat(fd)
        q.require(stat.S_ISDIR(observed.st_mode) and (observed.st_dev,observed.st_ino)==(held.st_dev,held.st_ino),'Preparation root identity changed')

def prepare(output,environ=None):
    initial=q.records(environ);root,fd=new_directory(output)
    receipt={'schema_version':'intune-qualification-inputs/1','status':'RUNNING','tools':initial,
        'binary_execution':False,'network_attempted':False,'installed':False,'tool_pins_changed':False,
        'native_host_qualified':False,'ci_qualified':False,'production_approved':False}
    try:
        # The environment document contains paths only, never caller hashes or
        # credentials; consumers still independently rehash the fixed tool pins.
        values={item['environment']:item['path'] for item in initial.values()}
        q.require(q.records(values)==initial,'Qualification inputs changed during preparation')
        guard(root,fd);document(fd,'environment.json',values)
        receipt.update(status='PASS_FIXED_INPUT_REFERENCES',version_evidence='Each exact executable digest binds its retained version receipt; actual native Docker/OpenTofu execution remains the strict host tests.')
        document(fd,'receipt.json',receipt);return receipt
    except BaseException as error:
        receipt.update(status='FAIL_PRESERVED',error_type=type(error).__name__)
        try:document(fd,'failure.json',receipt)
        except BaseException as second:print(json.dumps({'secondary_receipt_failure':type(second).__name__}),file=sys.stderr)
        raise
    finally:os.close(fd)

def build_relays(output,compiler,sources):
    compiler=q.check(compiler,expected=COMPILER_SHA,executable=True)
    for name,pin in BUILD_INPUTS.items():q.check(name,expected=pin)
    for role,path in sources.items():q.check(path,expected=SOURCE_PINS[role])
    root,fd=new_directory(output);receipt={'schema_version':'intune-relay-qualification-build/1','status':'RUNNING',
        'compiler_sha256':COMPILER_SHA,'build_inputs':BUILD_INPUTS,'source_pins':SOURCE_PINS,
        'outputs':{},'network_attempted':False,'compiler_execution_attempted':False,'rebuilt_relays_executed':False,
        'native_host_qualified':False,'tool_pins_changed':False}
    try:
        for role,source in sources.items():
            guard(root,fd);source=q.check(source,expected=SOURCE_PINS[role]);q.check(compiler,expected=COMPILER_SHA,executable=True)
            # ELF's source-file symbol binds the historical literal basename.
            # Preserve reviewed input bytes while reproducing that build input.
            source_root,source_fd=new_directory(root/(role+'-source'))
            try:
                with q.opened(source,maximum=1024*1024) as (stream,_):raw=stream.read()
                q.require(hashlib.sha256(raw).hexdigest()==SOURCE_PINS[role],'Relay source changed during preparation')
                write(source_fd,'relay.c',raw)
            finally:os.close(source_fd)
            build_source=q.check(source_root/'relay.c',expected=SOURCE_PINS[role])
            target=root/role;argv=[str(compiler),*FLAGS,'-o',str(target),str(build_source)]
            receipt['compiler_execution_attempted']=True
            result=subprocess.run(argv,cwd=root,env={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','SOURCE_DATE_EPOCH':'0'},capture_output=True,timeout=60)
            write(fd,role+'.stdout',result.stdout);write(fd,role+'.stderr',result.stderr)
            q.require(result.returncode==0,'Pinned relay build failed; preserve diagnostics')
            q.check(source,expected=SOURCE_PINS[role]);q.check(compiler,expected=COMPILER_SHA,executable=True)
            for name,pin in BUILD_INPUTS.items():q.check(name,expected=pin)
            item=q.PINNED[role];q.check(target,expected=item['sha256'],size=item['bytes'],executable=True)
            receipt['outputs'][role]={'path':str(target),'sha256':item['sha256'],'bytes':item['bytes'],'argv':argv}
        guard(root,fd);receipt['status']='PASS_EXACT_RELAY_REPRODUCTION';document(fd,'receipt.json',receipt);return receipt
    except BaseException as error:
        receipt.update(status='FAIL_PRESERVED',error_type=type(error).__name__)
        try:document(fd,'failure.json',receipt)
        except BaseException as second:print(json.dumps({'secondary_receipt_failure':type(second).__name__}),file=sys.stderr)
        raise
    finally:os.close(fd)

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    inputs=sub.add_parser('verify');inputs.add_argument('--output',required=True)
    for role in q.PINNED:inputs.add_argument('--'+role.replace('_','-'),required=True)
    build=sub.add_parser('build-relays');build.add_argument('--output',required=True);build.add_argument('--compiler',required=True)
    build.add_argument('--relay-v2-source',required=True);build.add_argument('--relay-v3-source',required=True)
    args=parser.parse_args(argv)
    try:
        result=prepare(args.output,{v['environment']:getattr(args,k)for k,v in q.PINNED.items()}) if args.command=='verify' else build_relays(args.output,args.compiler,{'relay_v2':args.relay_v2_source,'relay_v3':args.relay_v3_source})
        print(json.dumps(result,ensure_ascii=True));return 0
    except (OSError,ValueError,subprocess.SubprocessError) as error:
        print(json.dumps({'status':'BLOCKED','error_type':type(error).__name__,'error':str(error)},ensure_ascii=True),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
