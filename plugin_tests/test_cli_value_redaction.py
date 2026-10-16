"""No argument value is ever echoed by the parser: a token pasted where a number or a name belongs stays unprinted.

Real processes, so the exact usage-error path is what runs. The canary is random per run and shaped like a token.
"""
import os
from pathlib import Path
import secrets
import subprocess
import sys
import unittest

PROJECT = Path(__file__).resolve().parents[1]
BASE = ['capture', '--tenant', '11111111-1111-4111-8111-111111111111', '--policy',
        '22222222-2222-4222-8222-222222222222', '--output', 'unused-output']
COLLECT = ['target', 'collect', '--input', 'unused.json']


def canary():
    return 'ghp_' + secrets.token_hex(18) + 'Zz'


def run(argv):
    env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8'}
    return subprocess.run([sys.executable, '-I', '-B', str(PROJECT / 'scripts/intune-iac.py'), *argv], cwd='/tmp',
                          env=env, capture_output=True, timeout=60)


class ParserNeverEchoesValues(unittest.TestCase):
    def check(self, argv, value, label):
        result = run(argv)
        text = result.stdout + result.stderr
        self.assertNotIn(value.encode(), text, label + ': the value was echoed')
        self.assertEqual(result.returncode, 2, label + ': ' + text.decode(errors='replace'))
        self.assertIn(b'error', result.stderr, label)
        return result.stderr.decode()

    def test_exact_descriptor_flags_with_a_token_value(self):
        for flags in (BASE + ['--token-fd'], COLLECT + ['--graph-token-fd'], COLLECT + ['--management-token-fd'],
                      ['target', 'authenticate', '--input', 'x', '--backend-secret-fd', '4', '--provider-secret-fd']):
            value = canary()
            with self.subTest(flag=flags[-1]):
                text = self.check(flags + [value], value, flags[-1])
                self.assertIn('expects the number of an inherited file descriptor', text)
                self.assertIn(flags[-1], text)

    def test_abbreviations_of_the_descriptor_flags_are_no_longer_accepted(self):
        for flags, abbreviation in ((BASE, '--token-f'), (COLLECT, '--graph-token-f'), (COLLECT, '--management-token-f')):
            value = canary()
            with self.subTest(abbreviation=abbreviation):
                text = self.check(flags + [abbreviation, value], value, abbreviation)
                self.assertIn('unrecognized arguments', text)

    def test_unrecognized_token_flag_and_other_value_errors(self):
        cases = [(BASE + ['--token'], 'unrecognized'), (COLLECT + ['--graph-token'], 'unrecognized'),
                 (['start', '--goal'], 'invalid choice'), (BASE + ['--max-pages'], 'invalid value')]
        for flags, wording in cases:
            value = canary()
            with self.subTest(flags=flags[-1]):
                self.assertIn(wording, self.check(flags + [value], value, flags[-1]))
        value = canary()
        text = self.check(['--version-' + value], value, 'unknown top-level option')
        value = canary()
        self.check([value], value, 'unknown command')
        value = canary()
        self.check(BASE + ['--token=' + value], value, 'equals form')

    def test_missing_argument_keeps_option_names(self):
        result = run(BASE + ['--token-fd'])
        self.assertIn(b'expected one argument', result.stderr)

    def test_a_valid_descriptor_number_still_parses(self):
        sys.path.insert(0, str(PROJECT))
        from intune_iac import cli
        args = cli.parser().parse_args(BASE + ['--token-fd', '7'])
        self.assertEqual(args.token_fd, 7)
        for bad in ('-1', '1.5', ' 7', '٣', '1' * 12, ''):
            with self.subTest(bad=bad), self.assertRaises(SystemExit):
                cli.parser().parse_args(BASE + ['--token-fd=' + bad])


class AbbreviationIsOffEverywhere(unittest.TestCase):
    def test_every_parser_and_subparser_rejects_abbreviations(self):
        import argparse
        from intune_iac import cli

        def walk(parser, trail):
            self.assertIs(parser.allow_abbrev, False, trail)
            for action in parser._actions:
                if isinstance(action, argparse._SubParsersAction):
                    for name, sub in action.choices.items():
                        walk(sub, trail + '/' + name)
        walk(cli.parser(), 'intune-iac')


if __name__ == '__main__':
    unittest.main()
