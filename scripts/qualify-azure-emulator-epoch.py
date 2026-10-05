#!/usr/bin/env python3
"""Actual OpenTofu 1.10 Azure backend against local Azurite 3.35, not live Azure.

No global trust/host configuration is changed. TLS remains verified using a lab
certificate passed only to child processes. A fail-closed CONNECT proxy routes
one synthetic blob hostname to loopback. Metadata and emulator listen only on
127.0.0.1. No model or candidate program is executed by this harness.
"""
import argparse,base64,datetime,hashlib,hmac,http.client,http.server,json,os
from pathlib import Path
import select,shutil,signal,socket,socketserver,ssl,subprocess,threading,time,urllib.parse,uuid

ACCOUNT='epochaccount'
# Public synthetic emulator key, never an Azure credential.
KEY=base64.b64encode(b'epoch-synthetic-only-key-not-live!'*2).decode()
TOFU_SHA='0a9eda0f0898896969492504a6ce778f310675e8a1eb960434c26806cd252627'

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,value):path.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
def stop(p):
    if p is not None and p.poll() is None:
        os.killpg(p.pid,signal.SIGTERM)
        try:p.wait(timeout=5)
        except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=5)

def run(args):
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    tofu=args.tofu.resolve();azurite=args.azurite.resolve();node=Path(shutil.which('node')).resolve()
    package=json.loads((azurite/'package.json').read_text())
    if package['version']!='3.35.0':raise ValueError('Pinned Azurite 3.35.0 required')
    if args.tofu_sha256 != TOFU_SHA or digest(tofu)!=TOFU_SHA:raise ValueError('OpenTofu hash mismatch')
    result={'status':'INCOMPLETE','scope':'Actual OpenTofu Azure backend + Azurite emulator; adapted endpoint metadata and loopback transport; no live Azure/RBAC/OIDC qualification','commands':[],'assertions':{},'requests':[],'proxy':[],'metadata_requests':[], 'versions':{'azurite':package['version'],'tofu_sha256':digest(tofu),'node_sha256':digest(node),'harness_sha256':digest(Path(__file__))}}
    save(out/'preregistration.json',{'cases':['backend init','saved plan identity','actual apply holds remote lease','competing plan lock refusal','persisted lineage serial and object identity','second plan convergence','remote lease wrong-owner write denial','owner release permits write','emulator restart retains state'], 'expected_native_version':'1.10.0','live_requests_authorized':False,'telemetry':False,'expected_network_targets':'loopback only','no_outcomes_observed':True})
    (out/'home').mkdir();(out/'empty-mirror').mkdir();(out/'emulator').mkdir();(out/'config').mkdir()
    cli=out/'tofurc';cli.write_text('disable_checkpoint = true\nprovider_installation {\n filesystem_mirror {\n  path = "'+str(out/'empty-mirror')+'"\n }\n}\n')
    env={'HOME':str(out/'home'),'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','TF_IN_AUTOMATION':'1','CHECKPOINT_DISABLE':'1','TF_CLI_CONFIG_FILE':str(cli)}
    def command(label,argv,timeout=45,check=True):
        started=time.monotonic();p=subprocess.Popen([str(x) for x in argv],cwd=out/'config',env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True)
        try:raw=p.communicate(timeout=timeout)[0];timed=False
        except subprocess.TimeoutExpired:stop(p);raw=p.communicate()[0];timed=True
        (out/(label+'.log')).write_bytes(raw)
        row={'label':label,'argv':[str(x) for x in argv],'exit_code':p.returncode,'timeout':timed,'elapsed_s':time.monotonic()-started,'stdout_sha256':hashlib.sha256(raw).hexdigest()};result['commands'].append(row);save(out/'receipt.json',result)
        if check and (p.returncode!=0 or timed):raise RuntimeError(label+' failed; inspect log')
        return raw,p.returncode
    version=json.loads(command('version',[tofu,'version','-json'])[0])
    if version.get('terraform_version')!='1.10.0':raise ValueError('Pinned OpenTofu 1.10.0 required')
    result['versions']['tofu']=version;result['versions']['node']=subprocess.check_output([node,'--version'],env=env,text=True).strip()
    cert=out/'lab-cert.pem';key=out/'lab-key.pem'
    command('lab-cert',['/usr/bin/openssl','req','-x509','-newkey','rsa:2048','-sha256','-nodes','-keyout',key,'-out',cert,'-days','1','-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost,DNS:'+ACCOUNT+'.blob.localhost,IP:127.0.0.1'])
    os.chmod(key,0o600)
    with socket.socket() as s:s.bind(('127.0.0.1',0));blob_port=s.getsockname()[1]
    blob_host=f'{ACCOUNT}.blob.localhost:{blob_port}'
    tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);tls.load_cert_chain(cert,key)
    class Metadata(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            result['metadata_requests'].append(self.path)
            if self.path!='/metadata/endpoints?api-version=2020-06-01':self.send_error(403);return
            body=json.dumps([{'name':'epoch','suffixes':{'storage':f'localhost:{blob_port}','keyVaultDns':'localhost'},'authentication':{'loginEndpoint':'https://127.0.0.1:1/never','audiences':['https://127.0.0.1:1/never'],'tenant':'synthetic','identityProvider':'AAD'},'resourceManager':'https://127.0.0.1:1/never','graph':'https://127.0.0.1:1/never'}]).encode()
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def log_message(self,*a):pass
    metadata=http.server.ThreadingHTTPServer(('127.0.0.1',0),Metadata);metadata.socket=tls.wrap_socket(metadata.socket,server_side=True)
    class Proxy(socketserver.StreamRequestHandler):
        def handle(self):
            first=self.rfile.readline(8192).decode('ascii','replace').strip();parts=first.split()
            if len(parts)!=3:return
            while True:
                line=self.rfile.readline(8192)
                if line in (b'\r\n',b'\n',b''):break
            allowed=parts[0]=='CONNECT' and parts[1]==blob_host
            result['proxy'].append({'request_line':first,'allowed':allowed,'destination':'127.0.0.1' if allowed else None})
            if not allowed:self.wfile.write(b'HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n');self.wfile.flush();return
            with socket.create_connection(('127.0.0.1',blob_port),timeout=5) as upstream:
                self.wfile.write(b'HTTP/1.1 200 Connection Established\r\n\r\n');self.wfile.flush();upstream.settimeout(None)
                pair=[self.connection,upstream]
                while True:
                    ready,_,_=select.select(pair,[],[],30)
                    if not ready:return
                    for src in ready:
                        data=src.recv(65536)
                        if not data:return
                        (upstream if src is self.connection else self.connection).sendall(data)
    class Server(socketserver.ThreadingTCPServer):allow_reuse_address=False;daemon_threads=True
    proxy=Server(('127.0.0.1',0),Proxy)
    for service in [metadata,proxy]:threading.Thread(target=service.serve_forever,daemon=True).start()
    env.update({'ARM_ACCESS_KEY':KEY,'SSL_CERT_FILE':str(cert),'HTTPS_PROXY':f'http://127.0.0.1:{proxy.server_address[1]}','HTTP_PROXY':f'http://127.0.0.1:{proxy.server_address[1]}','NO_PROXY':'127.0.0.1'})
    az_env={k:v for k,v in env.items() if not k.startswith(('ARM_','TF_','HTTP','NO_PROXY'))};az_env['AZURITE_ACCOUNTS']=ACCOUNT+':'+KEY
    az_command=[str(node),str(azurite/'dist/src/blob/main.js'),'--blobHost','127.0.0.1','--blobPort',str(blob_port),'--location',str(out/'emulator'),'--cert',str(cert),'--key',str(key),'--disableTelemetry','--debug',str(out/'azurite-debug.log')]
    result['emulator_argv']=az_command
    az=None;apply=None
    context=ssl.create_default_context(cafile=str(cert))
    def request(method,path,body=b'',headers=None):
        parsed=urllib.parse.urlsplit(path);heads={'x-ms-date':__import__('email.utils',fromlist=['formatdate']).formatdate(usegmt=True),'x-ms-version':'2018-11-09','Content-Length':str(len(body)),'Host':blob_host};heads.update(headers or {})
        lower={k.lower():v for k,v in heads.items()}
        fixed=[method,'','',str(len(body)) if body else '',lower.get('content-md5',''),lower.get('content-type',''),'','',lower.get('if-match',''),'','','']
        canonical=''.join(k+':'+v.strip()+'\n' for k,v in sorted(lower.items()) if k.startswith('x-ms-'))
        resource='/'+ACCOUNT+parsed.path
        for k,v in sorted(urllib.parse.parse_qs(parsed.query).items()):resource+='\n'+k.lower()+':'+','.join(sorted(v))
        signed='\n'.join(fixed)+'\n'+canonical+resource
        heads['Authorization']='SharedKey '+ACCOUNT+':'+base64.b64encode(hmac.new(base64.b64decode(KEY),signed.encode(),hashlib.sha256).digest()).decode()
        conn=http.client.HTTPSConnection('127.0.0.1',blob_port,context=context,timeout=5)
        try:
            conn.request(method,path,body,heads);res=conn.getresponse();data=res.read(1024*1024);h=dict(res.getheaders());status=res.status
        finally:conn.close()
        result['requests'].append({'method':method,'path':path,'status':status,'body_sha256':hashlib.sha256(data).hexdigest(),'request_body_sha256':hashlib.sha256(body).hexdigest(),'lease_state':h.get('x-ms-lease-state'),'lease_status':h.get('x-ms-lease-status'),'etag':h.get('ETag')})
        return status,data,h
    def start_emulator():
        nonlocal az
        log=open(out/'azurite.log','ab');az=subprocess.Popen(az_command,env=az_env,cwd=out,start_new_session=True,stdout=log,stderr=subprocess.STDOUT);log.close()
        end=time.monotonic()+15
        while time.monotonic()<end:
            if az.poll() is not None:raise RuntimeError('Azurite startup failed')
            try:
                status,_,_=request('GET','/?comp=list')
                if status==200:return
            except (OSError,http.client.HTTPException):pass
            time.sleep(.1)
        raise RuntimeError('Azurite readiness deadline')
    try:
        start_emulator()
        status,_,_=request('PUT','/states?restype=container');assert status==201,status
        (out/'config'/'main.tf').write_text('''terraform {
 required_version = "=1.10.0"
 backend "azurerm" {
  storage_account_name = "'''+ACCOUNT+'''"
  container_name = "states"
  key = "terraform.tfstate"
  environment = "epoch"
  metadata_host = "127.0.0.1:'''+str(metadata.server_address[1])+'''"
  timeout_seconds = 15
 }
}
resource "terraform_data" "sentinel" {
 input = { identity = "epoch-local-only", generation = 1 }
 provisioner "local-exec" { command = "sleep 6" }
}
output "identity" { value = terraform_data.sentinel.id }
''')
        command('init',[tofu,'init','-input=false','-no-color']);result['assertions']['native_backend_init']=True
        command('plan',[tofu,'plan','-input=false','-no-color','-out=approved.tfplan']);plan=out/'config'/'approved.tfplan';plan_hash=digest(plan);result['saved_plan_sha256']=plan_hash
        log=open(out/'apply.log','wb');apply=subprocess.Popen([str(tofu),'apply','-input=false','-no-color','approved.tfplan'],env=env,cwd=out/'config',stdout=log,stderr=subprocess.STDOUT,start_new_session=True);log.close()
        end=time.monotonic()+5;leased=False
        while time.monotonic()<end:
            status,_,heads=request('HEAD','/states/terraform.tfstate')
            if heads.get('x-ms-lease-state')=='leased':leased=True;break
            time.sleep(.1)
        result['assertions']['native_apply_holds_remote_lease']=leased
        raw,code=command('competing-plan',[tofu,'plan','-input=false','-no-color','-lock-timeout=1s'],check=False)
        result['assertions']['competing_plan_refused']=code==1 and b'Error acquiring the state lock' in raw
        apply.wait(timeout=30);result['commands'].append({'label':'saved-apply','argv':[str(tofu),'apply','-input=false','-no-color','approved.tfplan'],'exit_code':apply.returncode,'stdout_sha256':digest(out/'apply.log')})
        result['assertions']['saved_plan_unchanged']=digest(plan)==plan_hash
        result['assertions']['native_apply_succeeded']=apply.returncode==0
        raw,code=command('state-pull',[tofu,'state','pull']);state=json.loads(raw);save(out/'state-before-restart.json',state)
        resources=state['resources'];rid=resources[0]['instances'][0]['attributes']['id']
        result['assertions']['state_lineage_serial_identity']=bool(state['lineage']) and type(state['serial']) is int and state['serial']>0 and bool(rid) and state['outputs']['identity']['value']==rid
        raw,code=command('convergence',[tofu,'plan','-input=false','-no-color','-detailed-exitcode'],check=False);result['assertions']['second_plan_no_change']=code==0
        # Direct REST negative controls act on a separate blob, never native state.
        testpath='/states/lease-negative-control';status,_,_=request('PUT',testpath,b'original',{'x-ms-blob-type':'BlockBlob'});assert status==201,status
        owner=str(uuid.uuid4());wrong=str(uuid.uuid4())
        status,_,_=request('PUT',testpath+'?comp=lease',headers={'x-ms-lease-action':'acquire','x-ms-proposed-lease-id':owner,'x-ms-lease-duration':'15'});result['assertions']['lease_acquire']=status==201
        status,_,_=request('PUT',testpath+'?comp=lease',headers={'x-ms-lease-action':'acquire','x-ms-proposed-lease-id':wrong,'x-ms-lease-duration':'15'});result['assertions']['competing_lease_refused']=status==409
        status,_,_=request('PUT',testpath,b'unauthorized',{'x-ms-blob-type':'BlockBlob','x-ms-lease-id':wrong});result['assertions']['wrong_lease_write_refused']=status==412
        status,data,_=request('GET',testpath);result['assertions']['rejected_write_has_no_effect']=status==200 and data==b'original'
        status,_,_=request('PUT',testpath+'?comp=lease',headers={'x-ms-lease-action':'release','x-ms-lease-id':owner});result['assertions']['owner_release']=status==200
        status,_,_=request('PUT',testpath,b'legitimate',{'x-ms-blob-type':'BlockBlob'});result['assertions']['released_blob_write']=status==201
        stop(az);start_emulator()
        raw,_=command('state-after-restart',[tofu,'state','pull']);after=json.loads(raw);result['assertions']['emulator_restart_preserves_state']=state==after
        save(out/'state-after-restart.json',after)
        result['assertions']['proxy_no_unapproved_target']=bool(result['proxy']) and all(x['allowed'] for x in result['proxy'])
        result['assertions']['metadata_no_oauth']=bool(result['metadata_requests']) and set(result['metadata_requests'])=={'/metadata/endpoints?api-version=2020-06-01'}
        result['status']='PASS' if all(result['assertions'].values()) else 'FAIL'
    except BaseException as exc:
        result['error']={'type':type(exc).__name__,'text':str(exc)};result['status']='FAIL'
    finally:
        stop(apply);stop(az)
        for service in [proxy,metadata]:service.shutdown();service.server_close()
        result['assertions']['children_reaped']=all(p is None or p.poll() is not None for p in [apply,az]);save(out/'receipt.json',result)
    print(json.dumps({'status':result['status'],'assertions':result['assertions'],'error':result.get('error'),'output':str(out)},indent=2))
    return 0 if result['status']=='PASS' else 1

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--tofu',type=Path,required=True);p.add_argument('--tofu-sha256',required=True);p.add_argument('--azurite',type=Path,required=True);p.add_argument('--output',type=Path,required=True);raise SystemExit(run(p.parse_args()))
