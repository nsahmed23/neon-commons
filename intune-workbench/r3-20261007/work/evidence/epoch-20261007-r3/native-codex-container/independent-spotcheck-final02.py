#!/usr/bin/env python3
"""Read-only independent cross-check; writes only its own review receipt."""
import datetime, hashlib, json, pathlib, tarfile, tomllib, zipfile
root=pathlib.Path(__file__).resolve().parent
case=root/'final-runtime-02'; out=case/'output'
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_text())
def response(label): return read(out/(label+'.stdout'))
checks=[]
def check(name, value): checks.append({'name':name,'passed':bool(value)})
receipt=read(case/'receipt.json'); assertions=read(case/'assertions.json')
check('all_raw_receipt_file_hashes_match',all(digest(case/p)==h for p,h in receipt['file_sha256'].items()))
check('26_claimed_assertions_have_explicit_pass',len(assertions['checks'])==26 and all(x['passed'] is True for x in assertions['checks']) and assertions['passed']==26 and assertions['failed']==0)
check('grader_driver_receipt_bytes_match_claim',digest(root/'grade-native.py')==assertions['grader_sha256'] and digest(root/'qualify-native.py')==assertions['driver_sha256'] and digest(case/'receipt.json')==assertions['native_receipt_sha256'])
zpath=pathlib.Path(assertions['runtime_zip'])
with zipfile.ZipFile(zpath) as z:
 zipfiles={n.removeprefix('intune-iac/'):hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if not n.endswith('/')}
check('final_runtime_identity_size_hash_count',zpath.stat().st_size==513895 and digest(zpath)=='cce47f620f5e1e7d3dbdab1e030624fae3991cbf88376737a4eda07e6c703515' and len(zipfiles)==130)
before=read(case/'package-before.json');after=read(case/'package-after.json')
check('zip_mount_and_before_after_exact',zipfiles==before==after and all(digest(pathlib.Path(receipt['plugin_path'])/p)==h for p,h in before.items()))
def members(name):
 with tarfile.open(out/name) as t:
  ms=t.getmembers()
  check(name+'_no_links_or_special_members',all(m.isdir() or m.isfile() for m in ms))
  return {m.name.removeprefix('./'):t.extractfile(m).read() for m in ms if m.isfile()}
installed=members('installed-home.tar');final=members('final-home.tar')
prefix='.codex/plugins/cache/intune-iac-local/intune-iac/0.8.0/'
cache={k.removeprefix(prefix):hashlib.sha256(v).hexdigest() for k,v in installed.items() if k.startswith(prefix)}
check('130_installed_regular_payloads_exact',cache==zipfiles and len(cache)==130)
conf=tomllib.loads(installed['.codex/config.toml'].decode())
check('local_marketplace_and_enabled_configuration',conf['marketplaces']['intune-iac-local']=={'source_type':'local','source':'/input/plugin'} and conf['plugins']['intune-iac@intune-iac-local']['enabled'] is True)
check('final_home_only_empty_config_no_auth',set(final)=={'.codex/config.toml'} and tomllib.loads(final['.codex/config.toml'].decode())=={} and not any(pathlib.PurePosixPath(n).name in {'auth.json','credentials.json'} for n in installed))
expected={
 '01-version':['--version'],
 '02-marketplace-add':['plugin','marketplace','add','/input/plugin','--json'],
 '03-list-available':['plugin','list','--marketplace','intune-iac-local','--available','--json'],
 '03b-invalid-install':['plugin','add','nonexistent-synthetic@intune-iac-local','--json'],
 '04-install':['plugin','add','intune-iac@intune-iac-local','--json'],
 '05-list-installed':['plugin','list','--marketplace','intune-iac-local','--json'],
 '06-uninstall':['plugin','remove','intune-iac@intune-iac-local','--json'],
 '07-list-after-uninstall':['plugin','list','--marketplace','intune-iac-local','--json'],
 '08-remove-marketplace':['plugin','marketplace','remove','intune-iac-local','--json'],
 '09-marketplaces-after-remove':['plugin','marketplace','list','--json']}
actual={p.stem:p.read_text().splitlines() for p in out.glob('*.argv')}
check('exact_ten_native_commands_no_model_session',actual==expected)
check('nine_success_one_expected_rejection',all((out/(k+'.exit')).read_text().strip()==('1' if k=='03b-invalid-install' else '0') for k in expected) and 'was not found in marketplace `intune-iac-local`' in (out/'03b-invalid-install.stderr').read_text())
check('native_version_recorded',(out/'01-version.stdout').read_text().strip()=='codex-cli 0.159.0-alpha.3')
check('registered_exact_local_marketplace',response('02-marketplace-add')=={'marketplaceName':'intune-iac-local','installedRoot':'/input/plugin','alreadyAdded':False})
available=response('03-list-available');active=response('05-list-installed')
check('available_then_enabled_transition',available['installed']==[] and len(available['available'])==1 and available['available'][0]['pluginId']=='intune-iac@intune-iac-local' and available['available'][0]['version']=='0.8.0' and available['available'][0]['installed'] is False and len(active['installed'])==1 and active['installed'][0]['enabled'] is True and active['installed'][0]['installed'] is True and active['installed'][0]['pluginId']=='intune-iac@intune-iac-local')
check('uninstall_then_marketplace_removal_observed',response('06-uninstall')['pluginId']=='intune-iac@intune-iac-local' and response('07-list-after-uninstall')=={'installed':[],'available':[]} and response('08-remove-marketplace')=={'marketplaceName':'intune-iac-local','installedRoot':None} and response('09-marketplaces-after-remove')=={'marketplaces':[]} and prefix not in (out/'after-uninstall-files.sha256').read_text())
inspect=read(case/'inspect-before.stdout')[0];done=read(case/'inspect-after.stdout')[0];host=inspect['HostConfig']
status=dict(line.split(':',1) for line in (out/'process-status.txt').read_text().splitlines() if ':' in line)
check('kernel_uid_caps_seccomp_no_new_privileges',inspect['Config']['User']=='1000:1000' and 'uid=1000 gid=1000' in (out/'identity.txt').read_text() and all(status[k].strip()=='0000000000000000' for k in ['CapInh','CapPrm','CapEff','CapBnd','CapAmb']) and status['NoNewPrivs'].strip()=='1' and status['Seccomp'].strip()=='2')
check('network_none_loopback_no_routes',host['NetworkMode']=='none' and (out/'interfaces.txt').read_text().strip()=='lo' and len((out/'routes.txt').read_text().splitlines())==1)
check('no_privilege_or_host_pid_readonly_root',host['CapDrop']==['ALL'] and host['SecurityOpt']==['no-new-privileges'] and host['Privileged'] is False and host['PidMode']!='host' and host['ReadonlyRootfs'] is True)
mounts={m['Destination']:m for m in inspect['Mounts']}
check('exact_explicit_mount_allowlist',set(mounts)=={'/input/plugin','/opt/codex/codex','/input/native.sh','/out'} and mounts['/input/plugin']['Source']==receipt['plugin_path'] and mounts['/opt/codex/codex']['Source']=='/opt/codex/bin/codex' and mounts['/input/native.sh']['Source']==str(case/'native.sh') and mounts['/out']['Source']==str(out) and all(m['RW'] is (dst=='/out') for dst,m in mounts.items()))
check('private_nonroot_home_tmpfs','uid=1000,gid=1000,mode=0700' in host['Tmpfs']['/home/native'])
check('container_successful_teardown',done['State']['Running'] is False and done['State']['ExitCode']==0 and len(receipt['commands'])==5 and all(x['exit_code']==0 for x in receipt['commands']) and receipt['commands'][-1]['label']=='remove')
check('final02_assertion_identity', assertions['source_commit']=='c122e38e33641336bc5af47b9dbf06eb0e58bc32' and assertions['runtime_zip_sha256']=='cce47f620f5e1e7d3dbdab1e030624fae3991cbf88376737a4eda07e6c703515')
wrapper=read(root/'FINAL02-COMMANDS.json')
check('final02_wrapper_commands_and_raw_hashes', len(wrapper)==2 and all(c['exit_code']==0 and digest(root/c['stdout'])==c['stdout_sha256'] and digest(root/c['stderr'])==c['stderr_sha256'] for c in wrapper) and wrapper[0]['argv'][wrapper[0]['argv'].index('--output')+1]==str(case) and wrapper[1]['argv'][wrapper[1]['argv'].index('--runtime-zip')+1]==str(zpath))
result={'recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'PASS_SCOPED' if all(x['passed'] for x in checks) else 'FAIL_PRESERVED','reviewer':'independent publication_audit lane','checks':checks,'passed':sum(x['passed'] for x in checks),'failed':sum(not x['passed'] for x in checks),'raw_hash_references_checked':len(receipt['file_sha256']),'native_commands':len(actual),'cached_runtime_files':len(cache),'reviewed_assertions_sha256':digest(case/'assertions.json'),'reviewed_wrapper_sha256':digest(root/'FINAL02-COMMANDS.json'),'review_script_sha256':digest(pathlib.Path(__file__)),'scope':'Read-only review of preserved raw native lifecycle, archive, config and Docker/kernel evidence. No product imports, app invocation, container rerun, source edits or claims of model/skill invocation. Original 26 assertions were reviewed; these grouped cross-checks are separate, not additional strict-suite tests.','limitations':['Same laboratory host and saved evidence; not organizational or hostile-kernel attestation.','No authenticated model session, skill invocation, Claude workflow, Windows/macOS qualification or production approval.']}
(root/'INDEPENDENT-SPOTCHECK-FINAL02.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:result[k] for k in ['status','passed','failed','raw_hash_references_checked','native_commands','cached_runtime_files']}))
