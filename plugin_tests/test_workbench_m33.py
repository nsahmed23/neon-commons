"""Presentation round M-33: the after-exit shell text (items 1 and 2) and the plan review's first viewport (items 3 and 4).

Temporary directories only.
"""
import json
import shlex
import tempfile
import unittest
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
