"""Actual offline delivery CLIs with literal parts and independent raw Git reads.

No real publication, live service, remote download or external credential use.
Existing tiny nine-layer payload fixtures are reused, not their test results.
"""
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

from plugin_tests import test_restore_complete_layers_r4 as fixtures

PROJECT=Path(__file__).resolve().parents[1]
DOWNLOAD=PROJECT/'scripts/download-complete-layers.py'
STAGE=PROJECT/'scripts/stage-release-git.py'
VALIDATOR=PROJECT/'scripts/restore-complete-layers.py'
GIT=Path('/usr/bin/git')
def sha(raw):return hashlib.sha256(raw).hexdigest()


class ReleaseTransferTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.CompleteLayersTests('test_actual_cli_all_required_layers_exact_separate_and_no_glob')
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups);self.root=self.fixture.root
        self.manifest=self.fixture.manifest;self.mapping={};self.calls=[]
        for layer,local in zip(self.manifest['layers'],self.fixture.returned['layers']):
            for part,path in zip(layer['archive']['parts'],local['parts']):
                url='https://raw.githubusercontent.com/nsahmed23/neon-commons/'+'a'*40+'/intune-workbench/fixture/'+layer['id']+'/'+part['name']
                part['url']=url;self.mapping[url]=path
        self.map_path=self.root/'fixture-map.json';self.input_path=self.root/'git-inputs.json'
        self.downloaded=self.root/'downloaded';self.repository=self.root/'new-data.git'
        self.save()
        retained=os.environ.get('INTUNE_TRANSFER_TEST_EVIDENCE');self.evidence=Path(retained)/self._testMethodName if retained else None
        if self.evidence:self.evidence.mkdir(parents=True,exist_ok=False);self.addCleanup(self.preserve)
    def save(self):
        self.fixture.save();self.map_path.write_text(json.dumps(self.mapping,sort_keys=True))
        self.input_path.write_text(json.dumps({'schema_version':'intune-release-git-inputs/1','manifest_sha256':self.fixture.manifest_sha,
            'layers':[{'id':layer['id'],'archive':str(self.fixture.inputs/(layer['id']+'.zip'))}for layer in self.manifest['layers'][4:]]},sort_keys=True))
    def preserve(self):
        (self.evidence/'commands.json').write_text(json.dumps(self.calls,indent=2)+'\n')
        shutil.copytree(self.root,self.evidence/'retained',symlinks=True)
    def invoke(self,script,values,env=None):
        argv=[sys.executable,'-B',str(script)]
        for key,value in values.items():
            argv.append('--'+key)
            if value is not True:argv.append(str(value))
        result=subprocess.run(argv,cwd='/tmp',env=env,capture_output=True,text=True,timeout=30)
        self.calls.append({'argv':argv,'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr});return result
    def dl(self,**overrides):
        values={'manifest':self.fixture.manifest_path,'manifest-sha256':self.fixture.manifest_sha,'validator-sha256':sha(VALIDATOR.read_bytes()),
            'output':self.downloaded,'local-fixture-map':self.map_path,'local-fixture-sha256':sha(self.map_path.read_bytes())};values.update(overrides)
        return self.invoke(DOWNLOAD,values)
    def st(self,env=None,**overrides):
        values={'manifest':self.fixture.manifest_path,'manifest-sha256':self.fixture.manifest_sha,'inputs':self.input_path,'inputs-sha256':sha(self.input_path.read_bytes()),
            'repository':self.repository,'branch':'intune-r4-offline-fixture','git-executable':GIT,'git-sha256':sha(GIT.read_bytes()),
            'validator-sha256':sha(VALIDATOR.read_bytes()),'helper-sha256':sha(DOWNLOAD.read_bytes())};values.update(overrides)
        return self.invoke(STAGE,values,env)
    def denied(self,result,*,path=None,absent=True):
        self.assertEqual(result.returncode,1,result.stdout+result.stderr);self.assertEqual(json.loads(result.stderr)['status'],'FAIL')
        if path is not None and absent:self.assertFalse(path.exists())
    def module(self,path):
        spec=importlib.util.spec_from_file_location('transfer_test_'+path.stem,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
    def test_actual_download_cli_exact_ordered_bytes_then_actual_complete_restore(self):
        before={p:p.read_bytes()for p in self.fixture.inputs.iterdir()};result=self.dl();self.assertEqual(result.returncode,0,result.stderr)
        receipt=json.loads(result.stdout);self.assertEqual(receipt['status'],'PASS_LOCAL_FIXTURE_ONLY');self.assertFalse(receipt['network_attempted']);self.assertTrue(receipt['final_part_readback_verified'])
        returned=json.loads((self.downloaded/'RETURNED-PARTS.json').read_text());self.assertEqual([x['id']for x in returned['layers']],list(fixtures.IDS))
        for layer in returned['layers']:self.assertEqual(b''.join(Path(p).read_bytes()for p in layer['parts']),self.fixture.archives[layer['id']])
        result=self.invoke(VALIDATOR,{'manifest':self.fixture.manifest_path,'manifest-sha256':self.fixture.manifest_sha,
            'returned-parts':self.downloaded/'RETURNED-PARTS.json','output':self.root/'restored-via-transfer'})
        self.assertEqual(result.returncode,0,result.stderr);self.assertTrue(json.loads(result.stdout)['complete_physical_file_set_and_type_map_verified'])
        self.assertEqual({p:p.read_bytes()for p in before},before)
    def test_actual_download_rejects_wrong_manifest_validator_map_pins_before_output(self):
        for key in ('manifest-sha256','validator-sha256','local-fixture-sha256'):self.denied(self.dl(**{key:'f'*64}),path=self.downloaded)
    def test_actual_unfinalized_or_wrong_layer_order_blocks_download_and_stage(self):
        self.manifest['status']='preparation';self.save();self.denied(self.dl(),path=self.downloaded);self.denied(self.st(),path=self.repository)
        self.manifest['status']='ready';self.manifest['layers'].reverse();self.save();self.denied(self.dl(),path=self.downloaded);self.denied(self.st(),path=self.repository)
    def test_actual_download_wrong_part_or_aggregate_hash_retains_all_partial_bytes(self):
        path=Path(self.fixture.returned['layers'][-1]['parts'][-1]);path.write_bytes(path.read_bytes()[:-1]+b'X')
        self.denied(self.dl(),absent=False);self.assertFalse((self.downloaded/'DOWNLOAD-RECEIPT.json').exists());self.assertTrue((self.downloaded/'DOWNLOAD-FAILURE.json').exists())
        self.assertTrue((self.downloaded/'parts/r4-provider-candidate/r4-provider-candidate.part2.partial').exists())
        self.assertEqual((self.downloaded/'parts/r2-complete/r2-complete.part1').read_bytes(),self.fixture.archives['r2-complete'][:len(self.fixture.archives['r2-complete'])//2])
    def test_actual_download_refuses_unsafe_mutable_or_cross_origin_urls(self):
        original=self.manifest['layers'][0]['archive']['parts'][0]['url']
        for url in ('http://example.invalid/x','https://raw.githubusercontent.com/nsahmed23/neon-commons/main/intune-workbench/x',original+'?secret=x',original.replace('/fixture/','/../'),original.replace('raw.githubusercontent.com','user@raw.githubusercontent.com')):
            self.manifest['layers'][0]['archive']['parts'][0]['url']=url;self.save();self.denied(self.dl(),path=self.downloaded)
    def test_actual_download_existing_destination_parent_alias_and_input_alias_rejected(self):
        alias=self.root/'alias';alias.symlink_to(self.root,target_is_directory=True);self.denied(self.dl(output=alias/'new'),path=self.root/'new')
        self.downloaded.mkdir();sentinel=self.downloaded/'keep';sentinel.write_bytes(b'UNCHANGED');self.denied(self.dl(),absent=False);self.assertEqual(sentinel.read_bytes(),b'UNCHANGED')
        link=self.root/'input-link';link.symlink_to(next(iter(self.mapping.values())));self.mapping[next(iter(self.mapping))]=str(link);self.save()
        output=self.root/'input-denied';self.denied(self.dl(output=output),absent=False);self.assertTrue((output/'DOWNLOAD-FAILURE.json').exists());self.assertFalse((output/'DOWNLOAD-RECEIPT.json').exists())
    def test_download_final_part_substitution_detected_by_independent_readback(self):
        m=self.module(DOWNLOAD);original=m.write_verified
        def injected(fd,name,chunks,expected):
            result=original(fd,name,chunks,expected)
            if name=='r4-provider-candidate.part2':(self.downloaded/'parts/r2-complete/r2-complete.part1').write_bytes(b'RETAINED-UNEXPECTED-CHANGE')
            return result
        with patch.object(m,'write_verified',injected),self.assertRaises(ValueError):
            m.download(self.fixture.manifest_path,self.fixture.manifest_sha,sha(VALIDATOR.read_bytes()),self.downloaded,
                fixture_map=self.map_path,fixture_sha256=sha(self.map_path.read_bytes()))
        self.assertEqual((self.downloaded/'parts/r2-complete/r2-complete.part1').read_bytes(),b'RETAINED-UNEXPECTED-CHANGE')
        self.assertFalse((self.downloaded/'DOWNLOAD-RECEIPT.json').exists())
    def test_download_unexpected_file_preserved_without_pass(self):
        m=self.module(DOWNLOAD);original=m.write_verified
        def injected(fd,name,chunks,expected):
            result=original(fd,name,chunks,expected)
            if name=='r4-provider-candidate.part2':(self.downloaded/'unexpected-file').write_bytes(b'KEEP')
            return result
        with patch.object(m,'write_verified',injected),self.assertRaises(ValueError):
            m.download(self.fixture.manifest_path,self.fixture.manifest_sha,sha(VALIDATOR.read_bytes()),self.downloaded,
                fixture_map=self.map_path,fixture_sha256=sha(self.map_path.read_bytes()))
        self.assertEqual((self.downloaded/'unexpected-file').read_bytes(),b'KEEP');self.assertFalse((self.downloaded/'DOWNLOAD-RECEIPT.json').exists())
    def test_download_late_unexpected_file_in_earlier_layer_is_preserved_without_pass(self):
        m=self.module(DOWNLOAD);original=m.write_verified
        def injected(fd,name,chunks,expected):
            result=original(fd,name,chunks,expected)
            if name=='r4-provider-candidate.part2':(self.downloaded/'parts/r2-complete/unexpected-late-file').write_bytes(b'KEEP-LATE')
            return result
        with patch.object(m,'write_verified',injected),self.assertRaises(ValueError):
            m.download(self.fixture.manifest_path,self.fixture.manifest_sha,sha(VALIDATOR.read_bytes()),self.downloaded,
                fixture_map=self.map_path,fixture_sha256=sha(self.map_path.read_bytes()))
        self.assertEqual((self.downloaded/'parts/r2-complete/unexpected-late-file').read_bytes(),b'KEEP-LATE')
        self.assertFalse((self.downloaded/'DOWNLOAD-RECEIPT.json').exists())
    def test_modeled_https_contract_has_no_origin_auth_and_refuses_changed_response(self):
        m=self.module(DOWNLOAD);seen=[];owner=self
        class Response(io.BytesIO):
            status=200
            def __init__(self,url):
                self.url=url;raw=Path(owner.mapping[url]).read_bytes();super().__init__(raw);self.headers={'Content-Length':str(len(raw))}
            def geturl(self):return self.url
        class Opener:
            def open(self,request,timeout):
                seen.append(request);owner.assertEqual(timeout,45)
                owner.assertFalse(any(k.lower()in ('authorization','cookie')for k,v in request.header_items()))
                return Response(request.full_url)
        with patch.object(m.urllib.request,'build_opener',return_value=Opener()):
            result=m.download(self.fixture.manifest_path,self.fixture.manifest_sha,sha(VALIDATOR.read_bytes()),self.downloaded)
        self.assertEqual(len(seen),18);self.assertTrue(result['final_part_readback_verified'])
        self.assertFalse(result['origin_authentication_supplied']);self.assertFalse(result['proxy_credential_values_inspected'])
        self.assertTrue(result['existing_proxy_configuration_inherited']);self.assertIn('origin request headers',result['authentication_scope'])
        # This is deliberately a modeled HTTP adapter; the actual CLI/local
        # test receipt is the evidence scope, not the mocked response label.
        class WrongURL(Opener):
            def open(self,request,timeout):
                value=super().open(request,timeout);value.url='https://outside.invalid/changed';return value
        with patch.object(m.urllib.request,'build_opener',return_value=WrongURL()),self.assertRaises(ValueError):
            m.download(self.fixture.manifest_path,self.fixture.manifest_sha,sha(VALIDATOR.read_bytes()),self.root/'wrong-url')
        with self.assertRaises(ValueError):m.NoRedirect().redirect_request(None,None,302,'fixture',{},'https://outside.invalid')
    def test_actual_staging_cli_git_blob_bytes_and_reproducible_commit_no_network(self):
        result=self.st();self.assertEqual(result.returncode,0,result.stderr);receipt=json.loads(result.stdout)
        self.assertEqual(receipt['status'],'LOCAL_STAGED_AND_BLOB_READBACK_VERIFIED');self.assertFalse(receipt['remote_mutation_requested'])
        self.assertFalse(any(r['network']for r in receipt['commands']));self.assertEqual([x['id']for x in receipt['layers']],list(fixtures.IDS[4:]))
        metadata=json.loads(subprocess.check_output([str(GIT),'--git-dir='+str(self.repository),'cat-file','blob',receipt['data_commit']+':intune-workbench/r4-evidence-20261007/DATA-RECEIPT.json']))
        self.assertEqual(metadata['scope'],'Five exact new continuation layers; unchanged complete R2 and R3 layers remain required.')
        self.assertEqual([row['id'] for row in metadata['layers']],['r4-source','r4-runtime','r4-evidence','r4-external-evidence','r4-provider-candidate'])
        for layer in receipt['layers']:
            chunks=[]
            for part in layer['parts']:
                raw=subprocess.check_output([str(GIT),'--git-dir='+str(self.repository),'cat-file','blob',receipt['data_commit']+':'+part['repository_path']])
                self.assertEqual((len(raw),sha(raw)),(part['bytes'],part['sha256']));chunks.append(raw)
            self.assertEqual(b''.join(chunks),self.fixture.archives[layer['id']])
        second=self.st(repository=self.root/'reproduced.git');self.assertEqual(second.returncode,0,second.stderr);self.assertEqual(json.loads(second.stdout)['data_commit'],receipt['data_commit'])
    def test_actual_staging_isolates_inherited_git_configuration_and_template_hooks(self):
        marker=self.root/'must-not-exist';template=self.root/'hostile-template';(template/'hooks').mkdir(parents=True)
        hook=template/'hooks/pre-commit';hook.write_text('#!/bin/sh\ntouch '+str(marker)+'\n');hook.chmod(0o700)
        env=dict(os.environ,GIT_CONFIG_COUNT='1',GIT_CONFIG_KEY_0='core.hooksPath',GIT_CONFIG_VALUE_0=str(template/'hooks'),GIT_TEMPLATE_DIR=str(template),GIT_OBJECT_DIRECTORY=str(self.root/'unexpected-objects'))
        result=self.st(env=env);self.assertEqual(result.returncode,0,result.stderr);self.assertFalse(marker.exists());self.assertFalse((self.root/'unexpected-objects').exists())
        self.assertFalse((self.repository/'hooks').exists())
    def test_actual_staging_pin_branch_order_and_existing_output_negatives(self):
        for key in ('manifest-sha256','inputs-sha256','git-sha256','validator-sha256','helper-sha256'):self.denied(self.st(**{key:'f'*64}),path=self.repository)
        self.denied(self.st(branch='main'),path=self.repository)
        inp=json.loads(self.input_path.read_text());inp['layers'].reverse();self.input_path.write_text(json.dumps(inp));self.denied(self.st(),path=self.repository)
        self.save();self.repository.mkdir();sentinel=self.repository/'keep';sentinel.write_bytes(b'KEEP');self.denied(self.st(),absent=False);self.assertEqual(sentinel.read_bytes(),b'KEEP')
    def test_actual_staging_requires_each_of_five_named_new_layers_before_git_effects(self):
        original=json.loads(self.input_path.read_text())
        for scenario in ('omit-external','omit-candidate','extra-layer','duplicate-layer','swap-evidence'):
            value=copy.deepcopy(original)
            if scenario=='omit-external':value['layers']=[row for row in value['layers'] if row['id']!='r4-external-evidence']
            elif scenario=='omit-candidate':value['layers']=[row for row in value['layers'] if row['id']!='r4-provider-candidate']
            elif scenario=='extra-layer':value['layers'].append({'id':'unlisted-evidence','archive':value['layers'][0]['archive']})
            elif scenario=='duplicate-layer':value['layers'][-1]=copy.deepcopy(value['layers'][0])
            else:value['layers'][2:4]=reversed(value['layers'][2:4])
            self.input_path.write_text(json.dumps(value))
            with self.subTest(scenario=scenario):
                result=self.st();self.denied(result,path=self.repository)
                self.assertIn('All five new layers required in exact declared order',json.loads(result.stderr)['error'])
        self.save()
    def test_ordinary_assertion_failures_keep_unittest_failure_type(self):
        with self.assertRaises(self.failureException):self.assertEqual('required literal','contrary literal')
    def test_actual_staging_wrong_input_or_symlink_rejected_before_new_repository(self):
        path=self.fixture.inputs/'r4-source.zip';raw=path.read_bytes();path.write_bytes(raw+b'X');self.denied(self.st(),path=self.repository);path.write_bytes(raw)
        link=self.root/'archive-link';link.symlink_to(path);value=json.loads(self.input_path.read_text());value['layers'][0]['archive']=str(link);self.input_path.write_text(json.dumps(value));self.denied(self.st(),path=self.repository)
    def test_actual_staging_wrong_part_boundary_retains_failed_bare_repository(self):
        self.manifest['layers'][4]['archive']['parts'][0]['sha256']='f'*64;self.save();self.denied(self.st(),absent=False)
        self.assertTrue((self.repository/'STAGING-FAILURE.json').exists());self.assertFalse((self.repository/'STAGING-RECEIPT.json').exists())
    def test_staging_input_change_after_preflight_is_preserved_and_rejected(self):
        m=self.module(STAGE);original=m.subprocess.run;archive=self.fixture.inputs/'r4-source.zip';initial=archive.read_bytes();owned=[];popen=m.subprocess.Popen
        def process(*args,**kwargs):
            child=popen(*args,**kwargs);owned.append(child);return child
        def injected(argv,*args,**kwargs):
            result=original(argv,*args,**kwargs)
            if 'init'in argv:archive.write_bytes(initial[:-1]+b'X')
            return result
        with patch.object(m.subprocess,'run',injected),patch.object(m.subprocess,'Popen',process),self.assertRaises(ValueError):
            m.stage(self.fixture.manifest_path,self.fixture.manifest_sha,self.input_path,sha(self.input_path.read_bytes()),self.repository,
                'intune-r4-input-change',GIT,sha(GIT.read_bytes()),sha(VALIDATOR.read_bytes()),sha(DOWNLOAD.read_bytes()))
        self.assertEqual(archive.read_bytes(),initial[:-1]+b'X');self.assertTrue((self.repository/'STAGING-FAILURE.json').exists())
        self.assertFalse((self.repository/'STAGING-RECEIPT.json').exists())
        self.assertTrue(owned);self.assertTrue(all(child.poll() is not None for child in owned))
        self.assertTrue(all(stream is None or stream.closed for child in owned for stream in (child.stdin,child.stdout,child.stderr)))
    def test_modeled_publication_contract_rejects_existing_ref_without_push(self):
        m=self.module(STAGE);original=m.subprocess.run;network=[]
        def remote(argv,*args,**kwargs):
            if 'ls-remote'in argv:
                network.append('ls-remote');return subprocess.CompletedProcess(argv,0,('1'*40+'\trefs/heads/main\n'+'2'*40+'\trefs/heads/intune-r4-collision\n').encode(),b'')
            if 'push'in argv:raise AssertionError('Existing remote branch must prevent push')
            return original(argv,*args,**kwargs)
        gh=Path('/usr/bin/gh')
        with patch.object(m.subprocess,'run',remote),self.assertRaises(ValueError):
            m.stage(self.fixture.manifest_path,self.fixture.manifest_sha,self.input_path,sha(self.input_path.read_bytes()),self.repository,
                'intune-r4-collision',GIT,sha(GIT.read_bytes()),sha(VALIDATOR.read_bytes()),sha(DOWNLOAD.read_bytes()),
                push=True,expected_remote_main='1'*40,gh_executable=gh,gh_sha256=sha(gh.read_bytes()))
        self.assertEqual(network,['ls-remote']);self.assertFalse((self.repository/'STAGING-RECEIPT.json').exists())
        self.assertFalse(json.loads((self.repository/'STAGING-FAILURE.json').read_text())['remote_outcome_uncertain'])
    def test_modeled_concurrent_same_commit_branch_cannot_report_new_publication(self):
        m=self.module(STAGE);original=m.subprocess.run;network=[];commit=None
        def remote(argv,*args,**kwargs):
            nonlocal commit
            if 'ls-remote'in argv:
                network.append('ls-remote');raw='1'*40+'\trefs/heads/main\n'
                if commit is not None:raw+=commit+'\trefs/heads/intune-r4-raced\n'
                return subprocess.CompletedProcess(argv,0,raw.encode(),b'')
            if 'push'in argv:
                network.append('push');commit=argv[-1].split(':',1)[0]
                self.assertIn('--force-with-lease=refs/heads/intune-r4-raced:',argv)
                raw='To https://github.com/nsahmed23/neon-commons.git\n=\t'+commit+':refs/heads/intune-r4-raced\t[up to date]\nDone\n'
                return subprocess.CompletedProcess(argv,0,raw.encode(),b'')
            return original(argv,*args,**kwargs)
        gh=Path('/usr/bin/gh')
        with patch.object(m.subprocess,'run',remote),self.assertRaises(ValueError):
            m.stage(self.fixture.manifest_path,self.fixture.manifest_sha,self.input_path,sha(self.input_path.read_bytes()),self.repository,
                'intune-r4-raced',GIT,sha(GIT.read_bytes()),sha(VALIDATOR.read_bytes()),sha(DOWNLOAD.read_bytes()),
                push=True,expected_remote_main='1'*40,gh_executable=gh,gh_sha256=sha(gh.read_bytes()))
        self.assertEqual(network,['ls-remote','push']);self.assertFalse((self.repository/'STAGING-RECEIPT.json').exists())
        self.assertTrue(json.loads((self.repository/'STAGING-FAILURE.json').read_text())['remote_outcome_uncertain'])
    def test_modeled_new_branch_requires_exact_lease_status_and_final_remote_readback(self):
        m=self.module(STAGE);original=m.subprocess.run;network=[];commit=None
        def remote(argv,*args,**kwargs):
            nonlocal commit
            if 'ls-remote'in argv:
                network.append('ls-remote');raw='1'*40+'\trefs/heads/main\n'
                if commit is not None:raw+=commit+'\trefs/heads/intune-r4-new-fixture\n'
                return subprocess.CompletedProcess(argv,0,raw.encode(),b'')
            if 'push'in argv:
                network.append('push');commit=argv[-1].split(':',1)[0]
                self.assertIn('--force-with-lease=refs/heads/intune-r4-new-fixture:',argv)
                raw='To https://github.com/nsahmed23/neon-commons.git\n*\t'+commit+':refs/heads/intune-r4-new-fixture\t[new branch]\nDone\n'
                return subprocess.CompletedProcess(argv,0,raw.encode(),b'')
            return original(argv,*args,**kwargs)
        gh=Path('/usr/bin/gh')
        with patch.object(m.subprocess,'run',remote):
            result=m.stage(self.fixture.manifest_path,self.fixture.manifest_sha,self.input_path,sha(self.input_path.read_bytes()),self.repository,
                'intune-r4-new-fixture',GIT,sha(GIT.read_bytes()),sha(VALIDATOR.read_bytes()),sha(DOWNLOAD.read_bytes()),
                push=True,expected_remote_main='1'*40,gh_executable=gh,gh_sha256=sha(gh.read_bytes()))
        self.assertEqual(network,['ls-remote','push','ls-remote']);self.assertTrue(result['expected_absent_ref_lease'])
        self.assertTrue(result['new_branch_porcelain_verified']);self.assertEqual(result['remote_commit'],commit)
    def test_actual_publish_requires_separate_gh_and_main_pins_before_any_network(self):
        self.denied(self.st(push=True),path=self.repository)
        self.denied(self.st(**{'push':True,'expected-remote-main':'1'*40,'gh-executable':GIT,'gh-sha256':'f'*64}),path=self.repository)
        self.denied(self.st(**{'expected-remote-main':'1'*40}),path=self.repository)


if __name__=='__main__':unittest.main()
