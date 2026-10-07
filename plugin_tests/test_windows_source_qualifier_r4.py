"""Qualification-preparation target binding, not native OS evidence."""
import copy
import importlib.util
from pathlib import Path
import unittest
from intune_iac import windows_source_edit

PATH=Path(windows_source_edit.__file__).parents[1]/'scripts/qualify-windows-source-edit.py'
spec=importlib.util.spec_from_file_location('source_edit_qualifier',PATH)
qualifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(qualifier)
class TargetBindingTests(unittest.TestCase):
    def setUp(self):
        self.case={'repo':r'C:\private\repo','source_path':'stacks/defaults.yaml','proposal':r'C:\private\proposal','digest':'b'*64,'tenant':'a'*36,'before_sha256':'c'*64,'after_sha256':'d'*64}
        self.review={'source_root':self.case['repo'],'proposal_path':self.case['proposal'],'proposal_sha256':self.case['digest'],'tenant_id':self.case['tenant'],'protected_plan_approval':False,'organizational_approval':False,'authoritative_source':{'path':self.case['source_path'],'before_sha256':self.case['before_sha256'],'after_sha256':self.case['after_sha256']}}
    def test_exact_review_target_passes(self):qualifier._bind_review(self.case,self.review)
    def test_wrong_review_target_identity_is_rejected(self):
        for field in ('source_root','proposal_path','proposal_sha256','tenant_id'):
            with self.subTest(field=field):
                review=copy.deepcopy(self.review);review[field]='different'
                with self.assertRaises(ValueError):qualifier._bind_review(self.case,review)
    def test_wrong_review_authoritative_path_or_oracle_hash_is_rejected(self):
        for field in ('path','before_sha256','after_sha256'):
            with self.subTest(field=field):
                review=copy.deepcopy(self.review);review['authoritative_source'][field]='different'
                with self.assertRaises(ValueError):qualifier._bind_review(self.case,review)
    def test_equal_oracle_hash_and_escaping_paths_are_rejected(self):
        for path in ('../other.yaml','/other.yaml','stacks\\other.yaml','stacks//other.yaml',''):
            with self.subTest(path=path):
                case=dict(self.case,source_path=path);review=copy.deepcopy(self.review);review['authoritative_source']['path']=path
                with self.assertRaises(ValueError):qualifier._bind_review(case,review)
        case=dict(self.case,after_sha256=self.case['before_sha256']);review=copy.deepcopy(self.review);review['authoritative_source']['after_sha256']=case['after_sha256']
        with self.assertRaises(ValueError):qualifier._bind_review(case,review)
    def test_authority_cannot_be_promoted_by_review_metadata(self):
        for field in ('protected_plan_approval','organizational_approval'):
            review=dict(self.review,**{field:True})
            with self.assertRaises(ValueError):qualifier._bind_review(self.case,review)
if __name__=='__main__':unittest.main()
