#!/usr/bin/env python3
"""Fresh anonymous restoration with a pinned public helper and independent hash."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

HELPER_SHA256='a619056fdedcd161104bfaa64f73a060c4ce2abac2cddd5220202ed6ca7fd840'
p=argparse.ArgumentParser(description=__doc__)
for name in ('manifest-url','helper-url','sha256','directory'):p.add_argument('--'+name,required=True)
p.add_argument('--bytes',required=True,type=int);a=p.parse_args()
root=Path(a.directory);root.mkdir(mode=0o700);start=time.time()
receipt={'status':'RUNNING','started_unix':start,'manifest_url':a.manifest_url,'helper_url':a.helper_url,
         'authentication_supplied':False,'expected_bytes':a.bytes,'expected_sha256':a.sha256}

def fetch(url):
    if not url.startswith('https://'):raise ValueError('HTTPS required')
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Intune-R3-Public-Verification/1'}),timeout=60) as response:
        raw=response.read(1024*1024+1)
        if len(raw)>1024*1024:raise ValueError('Public document bound exceeded')
        return raw,{'http_status':response.status,'final_url':response.geturl(),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}

try:
    raw,receipt['helper_download']=fetch(a.helper_url)
    if hashlib.sha256(raw).hexdigest()!=HELPER_SHA256:raise ValueError('Public helper differs from qualified checksum')
    helper=root/'restore_r3_evidence.py';helper.write_bytes(raw)
    raw,receipt['manifest_download']=fetch(a.manifest_url)
    manifest=json.loads(raw);(root/'R3-EVIDENCE-DISTRIBUTION-MANIFEST.json').write_bytes(raw)
    if (manifest['archive']['bytes'],manifest['archive']['sha256'])!=(a.bytes,a.sha256):raise ValueError('Public manifest final archive pins differ')
    output=root/manifest['archive']['name']
    if output.parent!=root:raise ValueError('Manifest archive name is not a basename')
    command=[sys.executable,'-B',str(helper),'--manifest',a.manifest_url,'--output',str(output),'--bytes',str(a.bytes),'--sha256',a.sha256]
    (root/'command.json').write_text(json.dumps({'argv':command,'authentication_supplied':False},indent=2)+'\n')
    with (root/'stdout.json').open('xb') as stdout,(root/'stderr.log').open('xb') as stderr:
        result=subprocess.run(command,stdout=stdout,stderr=stderr)
    receipt['return_code']=result.returncode
    if result.returncode:raise ValueError('Public reassembly failed; stderr and provisional partial preserved')
    digest=hashlib.sha256();count=0
    with output.open('rb') as source:
        while raw:=source.read(1024*1024):count+=len(raw);digest.update(raw)
    receipt['reassembled_archive']={'path':str(output),'bytes':count,'sha256':digest.hexdigest()}
    if (count,digest.hexdigest())!=(a.bytes,a.sha256):raise ValueError('Independent complete ZIP verification failed')
    receipt.update(status='PASS',part_count=len(manifest['parts']),data_commit=manifest['data_commit'],
        fresh_public_helper_checksum_verified=True,archive_byte_identity_verified=True,
        extraction_performed=False,complete_repository=False,scope='Entire R3 evidence epoch supplement; immutable R2 base required')
except BaseException as error:
    receipt.update(status='FAIL',error_type=type(error).__name__,error=str(error));raise
finally:
    receipt.update(finished_unix=time.time(),seconds=time.time()-start)
    (root/'PUBLIC-R3-DOWNLOAD-RECEIPT.json').write_text(json.dumps(receipt,indent=2)+'\n')
