import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from intune_iac import runner


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'capture.json'
        self.context = self.root / 'context.json'
        self.source.write_text('{"policy": 1}')
        self.context.write_text('{"tenant": 1}')
        self.params = {'input': str(self.source), 'context': str(self.context)}
        self.state = self.root / 'state'

    def test_unknown_and_arbitrary_action_rejected(self):
        for action in ['shell', 'python', 'rm -rf /', 'unknown']:
            answer = runner.run(action, {'command': 'secret'}, self.state)
            self.assertEqual(answer['status'], 'rejected')
            self.assertEqual(answer['error']['code'], 'unknown_action')
        self.assertFalse(self.state.exists())
        self.assertEqual(runner.preview('cloud_apply', {}, self.state)['status'], 'unavailable')

    def test_preview_no_dispatch_or_writes(self):
        before = sorted(str(p) for p in self.root.rglob('*'))
        with patch.object(runner, '_dispatch', side_effect=AssertionError('dispatch')):
            answer = runner.preview('inspect', self.params, self.state)
        self.assertEqual(answer['status'], 'ready')
        self.assertEqual(before, sorted(str(p) for p in self.root.rglob('*')))
        self.assertEqual(len(answer['proposal']['evidence']['input']['sha256']), 64)

    def test_strict_parameters(self):
        for params in [dict(self.params, command='secret'), {'input': True, 'context': str(self.context)}, {'input': str(self.source)}]:
            self.assertEqual(runner.preview('inspect', params, self.state)['error']['code'], 'invalid_parameters')

    def test_changed_input_before_dispatch(self):
        original = runner._recheck
        def change(proposal):
            self.source.write_text('{"policy": 2}')
            return original(proposal)
        with patch.object(runner, '_recheck', side_effect=change), patch.object(runner, '_dispatch') as dispatch:
            answer = runner.run('inspect', self.params, self.state)
        self.assertEqual(answer['status'], 'rejected')
        self.assertEqual(answer['error']['code'], 'evidence_changed')
        dispatch.assert_not_called()

    def test_graph_output_conflict_has_no_dispatch(self):
        target = self.root / 'graph.json'
        target.write_text('owned by someone else')
        params = {'input': str(self.source), 'output': str(target)}
        with patch.object(runner, '_dispatch') as dispatch:
            answer = runner.run('graph_build', params, self.state)
        self.assertEqual(answer['error']['code'], 'output_conflict')
        self.assertEqual(target.read_text(), 'owned by someone else')
        dispatch.assert_not_called()

    def test_stale_lock_and_uncertain_outcome_blocks_other_state_dir(self):
        target = self.root / 'generated'
        params = dict(self.params, output=str(target))
        with patch.object(runner, '_dispatch', side_effect=RuntimeError('SECRET error')):
            first = runner.run('generate', params, self.state)
        self.assertEqual(first['status'], 'outcome_unknown')
        self.assertEqual(runner.preview('generate', params, self.root / 'third')['status'], 'needs_review')
        with patch.object(runner, '_dispatch') as dispatch:
            second = runner.run('generate', params, self.root / 'other_state')
        self.assertEqual(second['error']['code'], 'target_locked')
        dispatch.assert_not_called()
        combined = ''.join(p.read_text() for p in self.state.glob('*.json'))
        self.assertNotIn('SECRET', combined)
        self.assertNotIn('policy', combined)

    def test_interruption_leaves_attempt_and_target_lock(self):
        params = dict(self.params, output=str(self.root / 'generated'))
        with patch.object(runner, '_dispatch', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                runner.run('generate', params, self.state)
        attempts = list(self.state.glob('*.attempt.json'))
        self.assertEqual(len(attempts), 1)
        self.assertEqual(json.loads(attempts[0].read_text())['status'], 'running')
        self.assertEqual(runner.run('generate', params, self.root / 'new')['error']['code'], 'target_locked')

    def test_verified_read_receipts_are_safe_and_distinct(self):
        with patch.object(runner, '_dispatch', return_value={'status': 'ready', 'preservation_verified': True, 'source_sha256': runner.file_sha(self.source), 'context_sha256': runner.file_sha(self.context)}):
            answer = runner.run('inspect', self.params, self.state)
        self.assertEqual(answer['status'], 'succeeded_verified')
        attempt = json.loads(Path(answer['receipt_paths']['attempt']).read_text())
        outcome = json.loads(Path(answer['receipt_paths']['result']).read_text())
        self.assertEqual(attempt['status'], 'running')
        self.assertEqual(outcome['status'], 'succeeded_verified')
        self.assertEqual(attempt['proposal_id'], outcome['proposal_id'])
        self.assertNotIn('result', outcome)

    def test_state_scope_overlap_rejected_without_write(self):
        self.assertEqual(runner.preview('inspect', self.params, self.source)['error']['code'], 'unsafe_path')
        params = {'input': str(self.source), 'atmos_root': str(self.root), 'output': str(self.root.parent / 'outside-graph.json')}
        self.assertEqual(runner.preview('graph_build', params, self.state)['error']['code'], 'unsafe_path')
        self.assertFalse(self.state.exists())

    def test_real_inspect_generate_and_safe_conflict(self):
        project = Path(__file__).resolve().parents[1]
        params = {'input': str(project / 'examples/supported/input/export.json'), 'context': str(project / 'examples/context.json')}
        inspected = runner.run('inspect', params, self.state)
        self.assertEqual(inspected['status'], 'succeeded_verified')
        self.assertTrue(inspected['result']['preservation_verified'])
        output = self.root / 'project'
        generated = runner.run('generate', dict(params, output=str(output)), self.state)
        self.assertEqual(generated['status'], 'succeeded_verified')
        again = runner.run('generate', dict(params, output=str(output)), self.root / 'other_state')
        self.assertEqual(again['result']['status'], 'unchanged')
        (output / 'user.txt').write_text('preserve me')
        conflict = runner.run('generate', dict(params, output=str(output)), self.state)
        self.assertEqual(conflict['status'], 'failed_no_effect_verified')
        self.assertEqual(conflict['error']['code'], 'output_conflict')
        self.assertEqual((output / 'user.txt').read_text(), 'preserve me')
        self.assertFalse(runner._lock_path(output).exists())

    def test_real_graph_build_and_query(self):
        project = Path(__file__).resolve().parents[1]
        target = self.root / 'graph.json'
        built = runner.run('graph_build', {'input': str(project / 'examples/supported/input/export.json'), 'context': str(project / 'examples/context.json'), 'output': str(target)}, self.state)
        self.assertEqual(built['status'], 'succeeded_verified')
        self.assertGreater(built['result']['node_count'], 0)
        queried = runner.run('graph_query', {'graph': str(target), 'query': 'policies'}, self.state)
        self.assertEqual(queried['status'], 'succeeded_verified')
        self.assertIsInstance(queried['result'], dict)

    def test_no_effect_not_claimed_when_output_verification_fails(self):
        params = dict(self.params, output=str(self.root / 'generated'))
        with patch.object(runner, '_dispatch', return_value={'status': 'created', 'outcome': 'succeeded_verified', 'preservation_verified': True}):
            answer = runner.run('generate', params, self.state)
        self.assertEqual(answer['status'], 'outcome_unknown')


if __name__ == '__main__':
    unittest.main()
