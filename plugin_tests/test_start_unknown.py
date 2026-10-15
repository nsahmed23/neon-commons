"""start never prints Python's None for a value it does not know; it says what is not known.

An operation directory the product cannot read is built in a temporary directory; the other
kinds are covered with the item shapes the survey produces when a field is missing.
"""
import tempfile
import unittest
from pathlib import Path

from plugin_tests.test_start_goal import run_cli

STATES = {'discovered': True, 'configured': False, 'authenticated': 'no_live_connection', 'qualified': 'not_qualified',
          'configured_reason': 'maintenance_evidence_changed'}


class StartUnknownTests(unittest.TestCase):
    def test_an_operation_without_a_status_says_what_is_not_known(self):
        from intune_iac.entry import _summary
        text = _summary({'kind': 'operation', 'path': 'op', 'states': STATES})
        self.assertNotIn('None', text)
        self.assertIn('status not known', text)
        self.assertNotIn('no configuration change', text)

    def test_an_operation_that_is_known_keeps_its_summary(self):
        from intune_iac.entry import _summary
        self.assertEqual(_summary({'kind': 'operation', 'path': 'op', 'status': 'planned', 'changes': [],
                                   'states': dict(STATES, configured=True)}), 'planned | no configuration change')
        self.assertEqual(_summary({'kind': 'operation', 'path': 'op', 'status': 'planned', 'changes': ['a', 'b'],
                                   'states': dict(STATES, configured=True)}), 'planned | a, b')

    def test_an_unreadable_operation_directory_prints_no_none_on_the_screen(self):
        with tempfile.TemporaryDirectory() as temp:
            operation = Path(temp) / 'operation-1'
            operation.mkdir()
            (operation / 'plan.json').write_text('{}')
            (operation / 'journal.json').write_text('{}')
            code, text = run_cli(temp)
            self.assertEqual(code, 0)
            self.assertIn('operation-1', text)
            self.assertIn('status not known', text)
            self.assertNotIn('None', text)

    def test_no_kind_prints_none_for_a_missing_value(self):
        from intune_iac.entry import LABELS, _summary
        states = {'discovered': True, 'configured': True, 'authenticated': 'no_live_connection', 'qualified': 'not_qualified'}
        for kind in LABELS:
            for extra in ({}, {'valid': True}):
                text = _summary({'kind': kind, 'path': 'x', 'states': states, 'number': 1, **extra})
                self.assertNotIn('None', text, (kind, extra))

    def test_a_known_value_is_still_shown_as_it_is(self):
        from intune_iac.entry import _summary
        item = {'kind': 'context', 'path': 'c.json', 'tenant_id': '11111111-1111-4111-8111-111111111111', 'stack': 's',
                'component': 'k', 'states': dict(STATES, configured=True)}
        self.assertEqual(_summary(item), 'tenant 11111111-1111-4111-8111-111111111111 | s / k')
        item['tenant_id'] = None
        self.assertEqual(_summary(item), 'tenant not known | s / k')


if __name__ == '__main__':
    unittest.main()
