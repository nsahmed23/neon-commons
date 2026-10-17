"""Presentation round M-33: the after-exit shell text (items 1 and 2) and the plan review's first viewport (items 3 and 4).

Temporary directories only.
"""
import json
import shlex
import tempfile
import unittest

from plugin_tests.test_workbench_map import Fixture
from pathlib import Path


def parse(line):
    """The printed command through the CLI's own parser (SystemExit if the parser refuses it)."""
    from intune_iac import cli
    return cli.parser().parse_args(shlex.split(line)[1:])


class AfterExitReconcileTests(unittest.TestCase):
    """Item 1 (frame 33, M-33): the printed reconcile names the operation by its short id beside the directory. The
    reconcile parser takes only --operation (the plan records its own store), so the command is complete without
    --root; a --root would be refused by the parser."""
    OPERATION_ID = 'c0e8470422ca4504916bf759d495698d'

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.operation = str(Path(self.temp.name) / 'operation 22222222')
        Path(self.operation).mkdir()
        (Path(self.operation) / 'plan.json').write_text(json.dumps({'operation_id': self.OPERATION_ID}))

    def lines(self, verb='execute'):
        from intune_iac.workbench import interrupted_lines
        return interrupted_lines({'interrupted_during': {'command': verb, 'operation_root': self.operation},
                                  'store_root': '/w/store'})

    def test_the_command_parses_complete_with_the_operation_directory(self):
        for verb in ('execute', 'reconcile'):
            command = next(line for line in self.lines(verb) if line.startswith('  intune-iac workbench reconcile'))
            namespace = parse(command)
            self.assertEqual((namespace.workbench_command, namespace.operation), ('reconcile', self.operation))

    def test_the_parser_refuses_a_root_so_none_is_printed(self):
        with self.assertRaises(SystemExit):
            parse('intune-iac workbench reconcile --root /w/store --operation /w/op')
        self.assertNotIn('--root', next(line for line in self.lines() if 'workbench reconcile' in line))

    def test_the_sentence_names_the_short_id_beside_the_directory(self):
        for verb, word in (('execute', 'executing'), ('reconcile', 'reconciling')):
            self.assertEqual(self.lines(verb)[0], 'Interrupted while %s operation c0e84704 (directory %s).'
                             % (word, shlex.quote(self.operation)))

    def test_an_unreadable_plan_leaves_the_directory_only_sentence(self):
        from intune_iac.workbench import interrupted_lines
        lines = interrupted_lines({'interrupted_during': {'command': 'execute', 'operation_root': '/nonexistent/op'}})
        self.assertEqual(lines[0], 'Interrupted while executing operation /nonexistent/op.')


class AfterExitOneLineTests(unittest.TestCase):
    """Item 2 (frame 41): every after-exit shell command is one physical line, with no inserted newline and no backslash."""
    STORE = '/w/journey 28 run 14/store'
    SERVICE = '/w/journey 28 run 14/handoff/service'

    def test_a_narrow_terminal_still_gets_one_line_per_command(self):
        from intune_iac.workbench import interrupted_lines, interrupted_text
        result = {'interrupted_during': {'command': 'collect', 'service_root': self.SERVICE}, 'store_root': self.STORE}
        for width in (40, 60, 100, 120):
            text = interrupted_text(result, width)
            commands = [line for line in text if line.startswith('  intune-iac workbench')]
            self.assertEqual(commands, [line for line in interrupted_lines(result) if line.startswith('  intune-iac workbench')], width)
            self.assertFalse([line for line in text if line.rstrip().endswith('\\')], (width, text))
            namespace = parse(commands[0])
            self.assertEqual((namespace.root, namespace.service_root), (self.STORE, self.SERVICE))

    def test_the_reconcile_command_is_one_line_too(self):
        from intune_iac.workbench import interrupted_text
        result = {'interrupted_during': {'command': 'execute', 'operation_root': '/w/journey 28 run 14/operation-22222222-b29ebd66ff89'}}
        text = interrupted_text(result, 40)
        self.assertEqual(len([line for line in text if 'workbench reconcile' in line]), 1)
        self.assertFalse([line for line in text if line.rstrip().endswith('\\')])


class PlanReviewFirstViewportTests(Fixture):
    """Items 3 and 4 (run14-A1, run14-A2; P-PRES-03 and P-PRES-12): at 120x40 the plan review's Next, with its framing and
    printed command, is on the first screen; the bound files and the equality definition are still on the review."""
    OPERATION = '/w/journey 28 run 14/operation-22222222-66c3b4de6d42'
    DESIRED = OPERATION + '.intent-desired.json'
    CONTEXT = OPERATION + '.intent-context.json'

    def review(self, **kw):
        value = {'name': 'Windows Privacy Pilot', 'operation_id': 'ed8fafd1b59646d6a22d1cf14a9b1f30',
                 'operation_root': self.OPERATION, 'object_id': self.object_id,
                 'tenant_id': '11111111-1111-4111-8111-111111111111', 'status': 'prepared', 'approval_digest': 'd' * 64,
                 'saved_plan_sha256': 'b' * 64, 'expires_at': 4102444800, 'engine_version': '1.10.0',
                 'evidence_class': 'synthetic_local_process_and_modeled_service_only',
                 'approval_window': {'state': 'open'}, 'changes': [], 'no_configuration_change': True,
                 'field_changes': {'status': 'no_change', 'changes': []},
                 'repository': {'cited': True, 'repository_intent_id': 'a' * 64, 'freshness': 'current'}}
        return dict(value, **kw)

    def screen(self, size, value, plain=True):
        import os
        ws = self.workspace(size, value=value, tab=4, last_command='review')
        ws.facts.update(states={'observation': {'evidence_class': 'synthetic_local_process_and_modeled_service_only',
                                                'freshness': 'fresh'}, 'operation': {'operation_id': value['operation_id'],
                                                                                     'journal_status': 'prepared',
                                                                                     'approval_window': 'open'}})
        ws._plan_cache = {os.path.abspath(self.OPERATION): {'desired_source': {'path': self.DESIRED},
                                                            'context': {'path': self.CONTEXT}}}
        rows = self.plain(ws)
        return ws, rows, ' '.join(' '.join(rows).replace('\u2502', ' ').split())

    def expired(self):
        # Frames 70 and 72 are no-change plans past their window (three rows of equality definition above the metadata).
        return self.review(expires_at=1, approval_window={'state': 'closed'})

    def context_changed(self):
        return dict(self.expired(), approval_window={'state': 'open'}, expires_at=4102444800,
                    repository={'cited': None, 'context_changed': True, 'context_path': self.CONTEXT})

    def test_an_expired_plan_has_its_next_on_the_first_screen_and_its_files_listed(self):
        ws, rows, text = self.screen((120, 40), self.expired())
        self.assertIn('Next: Prepare a proposal from the recorded intent (a: actions)', text)
        self.assertIn("Input files bound by the plan: '%s', '%s'" % (self.DESIRED, self.CONTEXT),
                      ' '.join(' '.join(ws._summary_lines(118)).split()))

    def test_a_changed_context_plan_has_its_next_on_the_first_screen(self):
        ws, rows, text = self.screen((120, 40), self.context_changed())
        self.assertIn('Next: Prepare a proposal from the recorded intent (a: actions)', text)
        self.assertIn('Input files bound by the plan', ' '.join(' '.join(ws._summary_lines(118)).split()))

    def test_the_no_change_plan_has_its_next_framing_and_commands_on_the_first_screen(self):
        ws, rows, text = self.screen((120, 40), self.review())
        self.assertIn('Next: Nothing to apply: the desired body equals the observed body.', text)
        self.assertIn('In the workspace:', text)
        self.assertIn("the execute command using '%s', naming the digest that the review shows" % self.OPERATION, text)
        self.assertIn('From a shell:', text)
        self.assertIn("the workbench execute command using --operation '%s', naming --approve-digest as the digest that the review shows"
                      % self.OPERATION, text)
        self.assertNotIn('DIGEST', text)  # no DIGEST stand-in is printed
        summary = ' '.join(' '.join(ws._summary_lines(118)).split())
        self.assertIn("under the execution plan's equality (assignments, technologies and role scope tags match in any order",
                      summary)  # the definition is kept at its first use
        self.assertIn('Input files bound by the plan', summary)

    def test_a_prepared_plan_with_a_change_keeps_its_command_whole_on_the_first_screen(self):
        ws, rows, text = self.screen((120, 40), self.review(changes=['description_changed'], no_configuration_change=False,
                                                           field_changes={'status': 'changed', 'changes': [
                                                               {'field': 'description', 'kind': 'changed', 'before': 'a', 'after': 'b'}]}))
        self.assertIn("the workbench execute command using --operation '%s', naming --approve-digest as the digest that the review shows"
                      % self.OPERATION, text)
        self.assertNotIn('--approve-digest DIGEST', text)

    def test_the_review_digest_is_still_on_the_review(self):
        ws, rows, text = self.screen((120, 40), self.review())
        self.assertIn('Review digest (execute needs it): ' + 'd' * 64, ' '.join(' '.join(ws._summary_lines(118)).split()))
        self.assertNotIn('DIGEST' + 'd' * 64, text)

    def test_smaller_screens_and_ascii_still_draw_and_ascii_has_the_next(self):
        for size in ((60, 20), (80, 24)):
            ws, rows, text = self.screen(size, self.expired())
            self.assertEqual(len(rows), size[1])
        ws = self.workspace((120, 40), value=self.expired(), tab=4, last_command='review', rules='ascii', color=False)
        ws._plan_cache = {}
        self.assertIn('Next:', ' '.join(self.plain(ws)))

    def test_the_next_stands_before_the_metadata_block_for_the_closed_and_changed_context_plans(self):
        for value in (self.expired(), self.context_changed()):
            ws, rows, text = self.screen((120, 40), value)
            summary = ' '.join(' '.join(ws._summary_lines(118)).split())
            self.assertLess(summary.index('Next: Prepare a proposal'), summary.index('[PLAN REVIEW]'))
            self.assertIn('Input files bound by the plan', summary[summary.index('[PLAN REVIEW]'):])
