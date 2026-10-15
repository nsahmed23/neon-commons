"""The tool profiles admit exactly their own versions to plan review; the current one does not widen file admission."""
from pathlib import Path
import copy
import tempfile
import unittest
from intune_iac import execution, protected
from intune_iac.io import AppError
from intune_iac.native_pins import OPENTOFU_PINS, OPENTOFU_CURRENT_SHA256

class NativePinProfilesEpochTests(unittest.TestCase):
    def test_general_parser_admits_exactly_the_versions_of_the_two_profiles(self):
        # Round 2 of the pin migration: the general parser reviews a plan that names the current engine version (and the
        # legacy one, labelled, for reproduction). Any other version is still refused.
        def review(version):
            return execution.review_plan({'format_version':'1.2', 'terraform_version':version,
                'planned_values':{'root_module':{}}, 'resource_changes':[], 'configuration':{'root_module':{}}})
        for version, profile in (('1.13.1','current_local_qualification'), ('1.10.0','legacy_reproduction_only')):
            result = review(version)
            self.assertNotIn('unqualified_engine_version', [x['code'] for x in result['blockers']])
            self.assertEqual(result['pin_profile'], profile)
        for version in ('1.13.2', '1.12.0', '1.14.0'):
            self.assertIn('unqualified_engine_version', [x['code'] for x in review(version)['blockers']])

    def test_current_output_parser_rejects_resources_and_malformed_shapes(self):
        base = {'format_version':'1.2', 'terraform_version':'1.13.1',
            'planned_values':{'root_module':{}},'resource_changes':[],
            'configuration':{'root_module':{'outputs':{}}},
            'prior_state':{'format_version':'1.0','terraform_version':'1.13.1','values':{'root_module':{}}}}
        mutations = [('resource_changes',[{'address':'cloud.policy'}]),
                     ('planned_values',{'root_module':{'resources':[]}}),
                     ('configuration',{'root_module':{'outputs':{},'provider_configs':{}}}),
                     ('configuration',None),('prior_state',[])]
        for key,value in mutations:
            with self.subTest(key=key,value=value):
                doc=copy.deepcopy(base);doc[key]=value
                with self.assertRaises(AppError):
                    execution.review_local_output_plan(doc,engine_version='1.13.1')
        with self.assertRaises(AppError):
            execution.review_local_output_plan(base,engine_version='1.13.2')

    def test_pinned_hash_does_not_admit_wrong_sized_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'tool';path.write_bytes(b'wrong')
            with self.assertRaises(AppError):
                protected._native_profile(path,OPENTOFU_CURRENT_SHA256)
            with self.assertRaises(AppError):
                protected._native_profile(path,'0'*64)

    def test_profiles_label_legacy_without_promoting_it(self):
        self.assertEqual(OPENTOFU_PINS[OPENTOFU_CURRENT_SHA256]['profile'],'current_local_qualification')
        self.assertEqual([p['version'] for p in OPENTOFU_PINS.values() if p['profile']=='legacy_reproduction_only'],['1.10.0'])
