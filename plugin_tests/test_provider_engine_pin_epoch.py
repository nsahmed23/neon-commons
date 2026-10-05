"""Version binding, not a claim of OpenTofu/provider RPC compatibility."""
from dataclasses import asdict
import copy
import tempfile
from pathlib import Path
import unittest

from intune_iac import provider_execution as pe
from intune_iac.io import AppError, digest, load_json, write_json
from intune_iac.native_pins import OPENTOFU_CURRENT_SHA256, OPENTOFU_PINS
from plugin_tests.test_provider_execution_v5 import FIXTURE, OBJECT_ID, SCHEMA, plan, shown


class ProviderEnginePinTests(unittest.TestCase):
    def test_current_route_has_no_legacy_default(self):
        self.assertEqual(pe.PRODUCTION_PINS.tofu_sha256, OPENTOFU_CURRENT_SHA256)
        self.assertEqual(pe.PRODUCTION_PINS.engine_version, '1.13.1')

    def test_plan_and_nested_prior_state_must_match_bound_version(self):
        config=pe._configuration(FIXTURE)
        ordinary=plan(config,config);ordinary['terraform_version']='1.13.1'
        with self.assertRaises(AppError):
            pe._plan(ordinary,OBJECT_ID,config,config,engine_version='1.13.1')
        ordinary['prior_state']['terraform_version']='1.13.1'
        self.assertEqual(pe._plan(ordinary,OBJECT_ID,config,config,engine_version='1.13.1'),'no-op')
        for expected in ('1.10.0','1.13.2',None):
            with self.subTest(expected=expected),self.assertRaises(AppError):
                pe._plan(ordinary,OBJECT_ID,config,config,engine_version=expected)
        refresh=plan(config,config,refresh=True);refresh['terraform_version']='1.13.1'
        with self.assertRaises(AppError):
            pe._plan(refresh,OBJECT_ID,config,config,engine_version='1.13.1',refresh=True)
        refresh['prior_state']['terraform_version']='1.13.1'
        self.assertEqual(pe._plan(refresh,OBJECT_ID,config,config,engine_version='1.13.1',refresh=True),config)

    def test_show_version_cannot_be_relabelled(self):
        document=shown(pe._configuration(FIXTURE))
        with self.assertRaises(AppError):pe._resource_values(document,engine_version='1.13.1')
        self.assertIn('id',pe._resource_values(document,engine_version='1.10.0'))

    def test_missing_manifest_version_fails_before_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            write_json(root/'executor.json',{'laboratory':True,'pins':{'tofu_sha256':'1'*64,
                'provider_sha256':'2'*64,'selected_schema_sha256':'3'*64,'source_revision':'modeled'}})
            with self.assertRaises(AppError):pe.ProviderExecutor(root)

    def test_known_binary_and_claimed_version_must_agree_even_in_lab(self):
        for engine_version in ('1.10.0','1.13.2',None):
            with tempfile.TemporaryDirectory() as tmp,self.subTest(engine_version=engine_version):
                pins=asdict(pe.PRODUCTION_PINS);pins['engine_version']=engine_version
                write_json(Path(tmp)/'executor.json',{'laboratory':True,'pins':pins})
                with self.assertRaises(AppError):pe.ProviderExecutor(tmp)

    def test_explicit_lab_configuration_and_manifest_bind_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);binary=root/'modeled';binary.write_bytes(b'not-a-native-binary');sha=pe._sha(binary)
            config=pe._configuration(FIXTURE)
            for version in ('1.10.0','1.13.1'):
                pins=pe.ProviderPins(sha,sha,digest(SCHEMA),'modeled',version)
                ex=pe.create_laboratory_executor(root/version,pins=pins,tofu=binary,provider=binary,
                    initial_configuration=config,admitted_configuration=config,object_id=OBJECT_ID,
                    source_sha256='1'*64,admission_sha256='2'*64,target_sha256='3'*64)
                self.assertEqual(ex.manifest['pins']['engine_version'],version)
                self.assertEqual(load_json(ex.work/'main.tf.json')['terraform']['required_version'],'= '+version)
                manifest=load_json(ex.root/'executor.json');manifest['pins']['engine_version']='1.13.1' if version=='1.10.0' else '1.10.0'
                write_json(ex.root/'executor.json',manifest)
                with self.assertRaises(AppError):ex._integrity()
                with self.assertRaises(AppError):pe.ProviderExecutor(ex.root)._integrity()


if __name__=='__main__':unittest.main()
