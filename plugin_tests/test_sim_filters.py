"""NT-2 item 2: the bounded filter grammar and its three-valued evaluation.

Expressions are parsed into an AST by a small grammar; they are never evaluated as Python, PowerShell or JavaScript.
The tests state the truth tables by hand: T and F are known results, U is missing knowledge and is not an observed
null (SIMULATOR_MODEL.md section 4).
"""
import unittest

from intune_iac import sim_filters as f
from intune_iac import sim_model, sim_profile
from plugin_tests import sim_support as s

PROFILE = sim_profile.load_profile({})


def device(**properties):
    doc = s.snapshot_doc(devices=[s.device('x', **properties)])
    return sim_model.load_snapshot(doc).devices[0]


def run(expression, **properties):
    parsed = f.parse_filter(expression, PROFILE)
    return f.evaluate(parsed, device(**properties), PROFILE)


class Grammar(unittest.TestCase):
    def test_equality_is_case_insensitive_text(self):
        self.assertEqual(run('device.manufacturer -eq "dell"', manufacturer='Dell')[0], 'T')
        self.assertEqual(run('device.manufacturer -ne "dell"', manufacturer='Dell')[0], 'F')

    def test_contains_starts_with_and_in(self):
        self.assertEqual(run('device.model -contains "lat"', model='Latitude 5420')[0], 'T')
        self.assertEqual(run('device.model -notContains "lat"', model='Latitude 5420')[0], 'F')
        self.assertEqual(run('device.model -startsWith "Lati"', model='Latitude 5420')[0], 'T')
        self.assertEqual(run('device.model -in ["A", "Latitude 5420"]', model='Latitude 5420')[0], 'T')
        self.assertEqual(run('device.model -notIn ["A", "B"]', model='Latitude 5420')[0], 'T')

    def test_dotted_versions_compare_numerically_never_lexicographically(self):
        self.assertEqual(run('device.osVersion -ge "10.0.9"', osVersion='10.0.19045')[0], 'T')
        self.assertEqual(run('device.osVersion -lt "10.0.9"', osVersion='10.0.19045')[0], 'F')
        self.assertEqual(run('device.osVersion -eq "10.0"', osVersion='10.0.0')[0], 'T')
        self.assertEqual(run('device.osVersion -gt "9.99"', osVersion='10.0')[0], 'T')

    def test_an_unparseable_version_is_unknown_not_false(self):
        value, reasons = run('device.osVersion -ge "10.0"', osVersion='ten')
        self.assertEqual(value, 'U')
        self.assertIn('version_unparseable:osVersion', reasons)

    def test_logic_and_parentheses_with_not_binding_tighter_than_and_tighter_than_or(self):
        props = dict(model='M1', manufacturer='Dell', osVersion='10.0.1')
        self.assertEqual(run('device.model -eq "M1" -and device.manufacturer -eq "HP"', **props)[0], 'F')
        self.assertEqual(run('device.model -eq "M1" -or device.manufacturer -eq "HP" -and device.model -eq "Z"', **props)[0], 'T')
        self.assertEqual(run('(device.model -eq "M1" -or device.manufacturer -eq "HP") -and device.model -eq "Z"', **props)[0], 'F')
        self.assertEqual(run('-not device.model -eq "M1"', **props)[0], 'F')
        self.assertEqual(run('-not (device.model -eq "Z" -and device.model -eq "M1")', **props)[0], 'T')

    def test_whitespace_does_not_change_the_ast_hash(self):
        a = f.parse_filter('device.model -eq "M1"', PROFILE)
        b = f.parse_filter('  (device.model   -EQ   "M1")  ', PROFILE)
        self.assertEqual(a.sha256, b.sha256)
        self.assertNotEqual(a.sha256, f.parse_filter('device.model -eq "M2"', PROFILE).sha256)


class Unsupported(unittest.TestCase):
    def test_unknown_operator_property_and_syntax_are_unknown_never_evaluated(self):
        for text in ('device.model -match "M.*"', 'device.nonsense -eq "x"', 'device.model == "x"',
                     'device.model -eq x', '__import__("os").system("x")', 'device.model -eq "x"); drop',
                     '', 'device.model -eq', '((device.model -eq "x")'):
            parsed = f.parse_filter(text, PROFILE)
            self.assertIsNone(parsed.ast, text)
            self.assertTrue(parsed.reason, text)
            self.assertEqual(f.evaluate(parsed, device(model='x'), PROFILE)[0], 'U', text)

    def test_oversized_or_deeply_nested_expressions_are_refused(self):
        self.assertIsNone(f.parse_filter('(' * 200 + 'device.model -eq "x"' + ')' * 200, PROFILE).ast)
        self.assertIsNone(f.parse_filter(' -or '.join(['device.model -eq "x"'] * 5000), PROFILE).ast)

    def test_a_filter_whose_expression_fact_is_not_known_is_unknown(self):
        parsed = f.parse_filter(None, PROFILE, presence='unknown')
        value, reasons = f.evaluate(parsed, device(model='x'), PROFILE)
        self.assertEqual(value, 'U')
        self.assertIn('filter_expression_unknown', reasons)


class ThreeValued(unittest.TestCase):
    UNKNOWN = {'presence': 'unknown'}

    def test_truth_tables(self):
        known_true = 'device.model -eq "M1"'
        known_false = 'device.model -eq "Z"'
        unknown = 'device.manufacturer -eq "Dell"'
        props = dict(model='M1', manufacturer=self.UNKNOWN)
        self.assertEqual(run(f'-not {unknown}', **props)[0], 'U')
        self.assertEqual(run(f'{known_false} -and {unknown}', **props)[0], 'F')
        self.assertEqual(run(f'{known_true} -and {unknown}', **props)[0], 'U')
        self.assertEqual(run(f'{known_true} -or {unknown}', **props)[0], 'T')
        self.assertEqual(run(f'{known_false} -or {unknown}', **props)[0], 'U')

    def test_observed_null_follows_the_profile_table_and_unavailable_does_not(self):
        null = {'presence': 'observed_null'}
        self.assertEqual(run('device.model -eq "x"', model=null)[0], 'F')
        self.assertEqual(run('device.model -ne "x"', model=null)[0], 'T')
        self.assertEqual(run('device.model -contains "x"', model=null)[0], 'F')
        self.assertEqual(run('device.model -notContains "x"', model=null)[0], 'T')
        for presence in ('unknown', 'redacted', 'unsupported'):
            value, reasons = run('device.model -ne "x"', model={'presence': presence})
            self.assertEqual(value, 'U', presence)
            self.assertIn(f'property_{presence}:model', reasons)
        value, reasons = run('device.model -ne "x"')
        self.assertEqual(value, 'U')
        self.assertIn('property_absent:model', reasons)


if __name__ == '__main__':
    unittest.main()
