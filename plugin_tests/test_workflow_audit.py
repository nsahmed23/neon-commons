"""Regressions reproduced independently in the v0.2.0 workflow audit."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from intune_iac.wizard import run_wizard

ROOT = Path(__file__).resolve().parents[1]


class WorkflowAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'export.json'
        self.context = self.root / 'context.json'
        self.session = self.root / 'session.json'
        self.output = self.root / 'project'
        self.source.write_bytes((ROOT / 'examples/supported/input/export.json').read_bytes())
        self.context.write_bytes((ROOT / 'examples/context.json').read_bytes())
        self.messages = []

    def state(self, step='review'):
        return {'schema_version': '1.0.0', 'step': step,
                'paths': {'input': str(self.source), 'context': str(self.context), 'output': str(self.output)},
                'fingerprints': {}, 'generated': None, 'conflict_reason': None}

    def run_answers(self, answers, supplied=True):
        queue = iter(answers)
        def read(_prompt):
            value = next(queue, None)
            if value is None:
                raise EOFError()
            return value() if callable(value) else value
        supplied_paths = {'input_path': self.source, 'context_path': self.context, 'output_path': self.output} if supplied else {}
        return run_wizard(self.session, input_fn=read, output_fn=self.messages.append, **supplied_paths)

    def test_review_without_generation_cannot_claim_completion(self):
        self.session.write_text(json.dumps(self.state()))
        before = self.session.read_bytes()
        result = self.run_answers(['finish'], supplied=False)
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['error'], 'invalid_wizard_session')
        self.assertEqual(self.session.read_bytes(), before)
        self.assertFalse(self.output.exists())
        self.assertFalse(any('proposal verified' in line for line in self.messages))

    def test_conflict_without_reason_is_rejected_without_traceback(self):
        self.session.write_text(json.dumps(self.state('conflict')))
        result = self.run_answers(['review'], supplied=False)
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['error'], 'invalid_wizard_session')

    def test_session_inside_output_is_rejected_before_creating_output(self):
        self.session = self.output / 'session.json'
        result = self.run_answers(['save'])
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['error'], 'wizard_path_conflict')
        self.assertFalse(self.output.exists())

    def test_saved_output_scope_cannot_contain_session(self):
        state = self.state('preview')
        state['paths']['output'] = str(self.root)
        self.session.write_text(json.dumps(state))
        original = self.session.read_bytes()
        result = self.run_answers(['save'], supplied=False)
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['error'], 'wizard_path_conflict')
        self.assertEqual(self.session.read_bytes(), original)
        self.assertFalse((self.root / 'attempts').exists())

    def test_session_alias_to_source_preserves_source(self):
        self.session = self.source
        original = self.source.read_bytes()
        result = self.run_answers(['save'])
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['error'], 'wizard_path_conflict')
        self.assertEqual(self.source.read_bytes(), original)

    def test_concurrent_session_cannot_overwrite_progress(self):
        nested_results = []
        def concurrent():
            nested_results.append(run_wizard(self.session, input_path=self.source,
                context_path=self.context, output_path=self.root / 'other-project',
                input_fn=lambda _: 'save', output_fn=lambda _: None))
            return 'save'
        outer = self.run_answers([concurrent])
        self.assertEqual(outer['status'], 'suspended')
        self.assertEqual(nested_results[0]['status'], 'blocked')
        self.assertEqual(nested_results[0]['error'], 'wizard_session_locked')
        self.assertEqual(json.loads(self.session.read_text())['paths']['output'], str(self.output))
        self.assertFalse(list(self.root.glob('.intune-wizard-lock-*')))

    def test_interrupt_saves_and_releases_session_lock(self):
        def interrupt():
            raise KeyboardInterrupt()
        result = self.run_answers([interrupt])
        self.assertEqual(result['status'], 'suspended')
        self.assertTrue(self.session.is_file())
        self.assertFalse(list(self.root.glob('.intune-wizard-lock-*')))
        resumed = self.run_answers(['review'], supplied=False)
        self.assertEqual(resumed['status'], 'review_only')

    def test_path_alias_uses_same_session_lock(self):
        nested_results = []
        sibling = self.root / 'existing-directory'
        sibling.mkdir()
        alias = sibling / '..' / self.session.name
        def concurrent():
            nested_results.append(run_wizard(alias, input_fn=lambda _: 'save', output_fn=lambda _: None))
            return 'save'
        self.run_answers([concurrent])
        self.assertEqual(nested_results[0]['error'], 'wizard_session_locked')

    def test_abandoned_session_lock_is_preserved_for_manual_recovery(self):
        digest = hashlib.sha256(str(self.session.resolve()).encode()).hexdigest()[:32]
        lock = self.root / ('.intune-wizard-lock-' + digest)
        lock.write_text('{"operation":"interrupted"}')
        original = lock.read_bytes()
        result = self.run_answers(['save'])
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['error'], 'wizard_session_locked')
        self.assertEqual(lock.read_bytes(), original)
        self.assertFalse(self.session.exists())

    def test_editing_output_to_session_parent_preserves_saved_session(self):
        self.run_answers(['save'])
        original = self.session.read_bytes()
        result = self.run_answers(['edit output', str(self.root)], supplied=False)
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['error'], 'wizard_path_conflict')
        self.assertEqual(self.session.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
