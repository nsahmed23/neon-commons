"""Literal independently authored eight-layer fixtures through the actual CLI."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile

PROJECT=Path(__file__).resolve().parents[1]
SCRIPT=PROJECT/'scripts/restore-complete-layers.py'
IDS=('r2-complete','r3-source','r3-runtime','r3-evidence','r4-source','r4-runtime','r4-evidence','r4-provider-candidate')
TYPED={'r2-complete','r3-evidence','r4-evidence','r4-provider-candidate'}
BASE='289ee9477372825aad848f4482cf681c2ff43b02'
def sha(raw):return hashlib.sha256(raw).hexdigest()


class CompleteLayersTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.inputs=self.root/'inputs';self.inputs.mkdir();self.output=self.root/'restored'
        self.manifest_path=self.root/'outer.json';self.returned_path=self.root/'returned.json'
        self.calls=[];self.archives={};self.manifest={'schema_version':'intune-complete-continuation-layers/1','status':'ready',
            'continuation_from':BASE,'historical_three_unexpected_files_closed':False,
            'tooling':{name:sha((PROJECT/'scripts'/name).read_bytes()) for name in ('restore-evidence-layer.py','verify-release-artifact.py')},'layers':[]}
        self.returned={'schema_version':'intune-local-layer-parts/1','manifest_sha256':None,'layers':[]}
        for identity in IDS:
            archive=self.inputs/(identity+'.zip');root='Fixture_'+identity
            content=('LITERAL '+identity+'\x00\n').encode()
            if identity in TYPED:
                schema='complete-continuation-snapshot/2' if identity=='r2-complete' else 'intune-r3-evidence-supplement/1' if identity=='r3-evidence' else 'intune-r4-evidence-supplement/1'
                target='/DO-NOT-FOLLOW/'+identity
                entries=[{'path':'payload.bin','type':'file','bytes':len(content),'sha256':sha(content)},
                         {'path':'negative-link','type':'symlink','bytes':len(target),'sha256':sha(target.encode()),'link_target':target}]
                inner=json.dumps({'schema':schema,'entries':entries,'link_inventory':[{'path':'negative-link','target':target}],'hardlink_groups':[]}).encode()
                with zipfile.ZipFile(archive,'w') as bundle:
                    self.member(bundle,root+'/MANIFEST.json',inner,stat.S_IFREG)
                    self.member(bundle,root+'/payload.bin',content,stat.S_IFREG)
                    self.member(bundle,root+'/negative-link',target.encode(),stat.S_IFLNK)
                extract={'kind':'typed_evidence','directory':identity,'snapshot':{'root':root,'manifest':'MANIFEST.json','manifest_sha256':sha(inner),'schema':schema}}
            else:
                with zipfile.ZipFile(archive,'w') as bundle:
                    self.member(bundle,root+'/payload.bin',content,stat.S_IFREG)
                    self.member(bundle,root+'/SHA256SUMS',(sha(content)+'  payload.bin\n').encode(),stat.S_IFREG)
                extract={'kind':'application','directory':identity}
            raw=archive.read_bytes();self.archives[identity]=raw;mid=len(raw)//2;parts=[];paths=[]
            for index,data in enumerate((raw[:mid],raw[mid:]),1):
                name=identity+'.part'+str(index);path=self.inputs/name;path.write_bytes(data)
                parts.append({'name':name,'bytes':len(data),'sha256':sha(data)});paths.append(str(path))
            self.manifest['layers'].append({'id':identity,'archive':{'name':archive.name,'bytes':len(raw),'sha256':sha(raw),'parts':parts},
                'extract':extract,'source_commit':BASE if identity.startswith('r3-') else '74130d0db99febf2f41cf4f4ebe2920a5d4dffb7' if identity=='r2-complete' else '1'*40,
                'qualification':'preserved_unqualified_stopped_candidate' if identity=='r4-provider-candidate' else 'literal_local_restoration_fixture'})
            self.returned['layers'].append({'id':identity,'parts':paths})
        self.save()
        retained=os.environ.get('INTUNE_COMPLETE_RESTORE_TEST_EVIDENCE');self.evidence=Path(retained)/self._testMethodName if retained else None
        if self.evidence:self.evidence.mkdir(parents=True,exist_ok=False);self.addCleanup(self.preserve)

    @staticmethod
    def member(bundle,name,raw,kind):
        info=zipfile.ZipInfo(name);info.create_system=3;info.external_attr=(kind|0o600)<<16;bundle.writestr(info,raw)

    def save(self):
        raw=json.dumps(self.manifest,sort_keys=True).encode();self.manifest_path.write_bytes(raw);self.manifest_sha=sha(raw)
        self.returned['manifest_sha256']=self.manifest_sha;self.returned_path.write_text(json.dumps(self.returned))

    def preserve(self):
        (self.evidence/'commands.json').write_text(json.dumps(self.calls,indent=2)+'\n')
        shutil.copytree(self.inputs,self.evidence/'inputs',symlinks=True)
        shutil.copyfile(self.manifest_path,self.evidence/'outer.json');shutil.copyfile(self.returned_path,self.evidence/'returned.json')
        if self.output.exists():shutil.copytree(self.output,self.evidence/'partial-or-complete-output',symlinks=True)

    def invoke(self,**overrides):
        values={'manifest':str(self.manifest_path),'manifest-sha256':self.manifest_sha,
                'returned-parts':str(self.returned_path),'output':str(self.output)};values.update(overrides)
        argv=[sys.executable,'-B',str(SCRIPT)]
        for key,value in values.items():argv.extend(['--'+key,str(value)])
        result=subprocess.run(argv,cwd='/tmp',capture_output=True,text=True,timeout=15)
        self.calls.append({'argv':argv,'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr});return result

    def denied(self,result,*,before_output=True):
        self.assertEqual(result.returncode,1,result.stdout+result.stderr);self.assertEqual(json.loads(result.stderr)['status'],'FAIL')
        self.assertFalse((self.output/'COMPLETE-LAYER-RECEIPT.json').exists())
        if before_output:self.assertFalse(self.output.exists())

    def test_actual_cli_all_required_layers_exact_separate_and_no_glob(self):
        (self.inputs/'decoy.part99').write_bytes(b'not a declared returned input')
        before={p.name:p.read_bytes() for p in self.inputs.iterdir()}
        result=self.invoke();self.assertEqual(result.returncode,0,result.stderr);receipt=json.loads(result.stdout)
        self.assertEqual(receipt['required_layers_present'],list(IDS));self.assertFalse(receipt['overlay_performed'])
        self.assertTrue(receipt['complete_physical_file_set_and_type_map_verified'])
        self.assertFalse(receipt['historical_three_unexpected_files_closed']);self.assertFalse(receipt['production_approved'])
        self.assertEqual({p.name for p in (self.output/'layers').iterdir()},set(IDS))
        for identity in IDS:
            self.assertEqual((self.output/'archives'/(identity+'.zip')).read_bytes(),self.archives[identity])
            destination=self.output/'layers'/identity/('Fixture_'+identity)
            self.assertEqual((destination/'payload.bin').read_bytes(),('LITERAL '+identity+'\x00\n').encode())
            if identity in TYPED:self.assertEqual(os.readlink(destination/'negative-link'),'/DO-NOT-FOLLOW/'+identity)
        self.assertEqual({p.name:p.read_bytes() for p in self.inputs.iterdir()},before)

    def test_actual_cli_unfinalized_null_or_placeholder_pins_block_before_output(self):
        original=copy.deepcopy(self.manifest)
        for scenario in ('unfinalized','null','zero'):
            self.manifest=copy.deepcopy(original)
            if scenario=='unfinalized':self.manifest['status']='preparation'
            else:self.manifest['layers'][4]['archive']['sha256']=None if scenario=='null' else '0'*64
            self.save();self.denied(self.invoke())

    def test_actual_cli_outer_manifest_tamper_or_wrong_pin_blocks_before_output(self):
        self.manifest_path.write_bytes(self.manifest_path.read_bytes()+b' ');self.denied(self.invoke())
        self.save();self.denied(self.invoke(**{'manifest-sha256':'f'*64}))

    def test_actual_cli_missing_extra_reordered_or_duplicate_returned_layers_block(self):
        original=copy.deepcopy(self.returned)
        for scenario in ('missing','extra','reordered','duplicate'):
            self.returned=copy.deepcopy(original)
            if scenario=='missing':self.returned['layers'].pop()
            if scenario=='extra':self.returned['layers'].append(copy.deepcopy(self.returned['layers'][0]))
            if scenario=='reordered':self.returned['layers'][:2]=reversed(self.returned['layers'][:2])
            if scenario=='duplicate':self.returned['layers'][1]=copy.deepcopy(self.returned['layers'][0])
            self.returned_path.write_text(json.dumps(self.returned));self.denied(self.invoke())

    def test_actual_cli_reordered_parts_preserve_partial_before_any_extraction(self):
        self.returned['layers'][0]['parts'].reverse();self.returned_path.write_text(json.dumps(self.returned))
        self.denied(self.invoke(),before_output=False)
        self.assertTrue((self.output/'archives/r2-complete.zip.partial').exists())
        self.assertEqual(list((self.output/'layers').iterdir()),[])

    def test_actual_cli_late_corrupt_part_blocks_every_extraction_and_preserves_archives(self):
        path=Path(self.returned['layers'][-1]['parts'][-1]);raw=path.read_bytes();path.write_bytes(bytes([raw[0]^1])+raw[1:])
        self.denied(self.invoke(),before_output=False)
        self.assertEqual(list((self.output/'layers').iterdir()),[])
        self.assertEqual((self.output/'archives/r2-complete.zip').read_bytes(),self.archives['r2-complete'])
        self.assertTrue((self.output/'archives/r4-provider-candidate.zip.partial').exists())

    def test_actual_cli_cannot_overlay_layers_or_claim_candidate_qualification(self):
        original=copy.deepcopy(self.manifest)
        self.manifest['layers'][4]['extract']['directory']='r2-complete';self.save();self.denied(self.invoke())
        self.manifest=copy.deepcopy(original);self.manifest['layers'][-1]['qualification']='passed';self.save();self.denied(self.invoke())
        self.manifest=copy.deepcopy(original);self.manifest['layers'][5]['source_commit']='2'*40;self.save();self.denied(self.invoke())

    def test_actual_cli_helper_pin_substitution_and_symlink_input_are_refused(self):
        self.manifest['tooling']['restore-evidence-layer.py']='f'*64;self.save();self.denied(self.invoke())
        self.manifest['tooling']['restore-evidence-layer.py']=sha((PROJECT/'scripts/restore-evidence-layer.py').read_bytes());self.save()
        original=Path(self.returned['layers'][0]['parts'][0]);link=self.inputs/'linked-part';link.symlink_to(original)
        self.returned['layers'][0]['parts'][0]=str(link);self.returned_path.write_text(json.dumps(self.returned))
        self.denied(self.invoke(),before_output=False);self.assertEqual(list((self.output/'layers').iterdir()),[])

    def test_actual_cli_existing_destination_and_parent_alias_are_refused(self):
        self.output.mkdir();sentinel=self.output/'sentinel';sentinel.write_bytes(b'unchanged')
        self.denied(self.invoke(),before_output=False);self.assertEqual(sentinel.read_bytes(),b'unchanged')
        alias=self.root/'alias';alias.symlink_to(self.root,target_is_directory=True)
        self.denied(self.invoke(output=alias/'new'),before_output=False);self.assertFalse((self.root/'new').exists())

    def test_inprocess_unexpected_top_level_output_is_preserved_without_complete_pass(self):
        spec=importlib.util.spec_from_file_location('independent_complete_unexpected',SCRIPT);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        original=module.assemble
        def injected(layer,*args):
            result=original(layer,*args)
            if layer['id']=='r2-complete':(self.output/'unexpected-temporary-file').write_bytes(b'preserve me')
            return result
        module.assemble=injected
        with self.assertRaises(ValueError):module.restore(self.manifest_path,self.manifest_sha,self.returned_path,self.output)
        self.assertEqual((self.output/'unexpected-temporary-file').read_bytes(),b'preserve me')
        self.assertFalse((self.output/'COMPLETE-LAYER-RECEIPT.json').exists())

    def test_actual_cli_delivered_unfinalized_template_blocks_before_output(self):
        template=PROJECT/'docs/CONTINUATION-LAYERS-R4.template.json'
        self.denied(self.invoke(manifest=str(template),**{'manifest-sha256':sha(template.read_bytes())}))


if __name__=='__main__':unittest.main()
