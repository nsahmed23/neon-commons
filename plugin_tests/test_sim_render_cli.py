"""NT-2 item 4: the JSON and text renderers and the plain `intune-iac simulate` command.

Cases: both renderers refuse a result that does not validate; JSON is canonical and round-trips; the text states
bounds as ranges, shows an unbounded upper plainly, never prints a verdict of "safe", and always says the result
authorizes nothing; the command reads files only, writes none, and reports bad input as a coded error.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from intune_iac import sim_profile, sim_render, sim_result
from intune_iac.cli import main
from intune_iac.io import AppError
from intune_iac.synthetic import generate_estate
from plugin_tests import sim_support as s
from plugin_tests.sim_cases import V1, V2, simulate

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'scripts/intune-iac.py'
DEFAULT_PROFILE = sim_profile.load_profile({})


def scenario():
    doc = s.snapshot_doc(
        devices=[s.device('a'), s.device('b'), s.device('c')], groups=[s.group('gA'), s.group('gB')],
        memberships=[s.member('gA', 'a'), s.member('gA', 'b'), s.member('gB', 'b'), s.member('gB', 'c')],
        rings=[{'ring_id': 'r1', 'name': 'Wave 0', 'order': 0, 'device_ids': [s.uid('device/a'), s.uid('device/b')]}],
        policies=[s.policy('p1', [s.include('gA')], [s.choice(s.DEF, V1)])])
    revision = s.revision_doc([s.policy('p2', [s.include('gB')], [s.choice(s.DEF, V2)])])
    return doc, revision


class Renderers(unittest.TestCase):
    def setUp(self):
        self.doc, self.revision = scenario()
        _, self.out = simulate(self.doc, self.revision)

    def test_json_is_canonical_and_round_trips(self):
        text = sim_render.render_json(self.out)
        self.assertEqual(json.loads(text), self.out)
        self.assertEqual(text, sim_render.render_json(json.loads(text)))
        self.assertEqual(list(json.loads(text)), sorted(json.loads(text)))
        self.assertTrue(text.endswith('\n'))

    def test_both_renderers_refuse_a_result_that_does_not_validate(self):
        broken = json.loads(sim_render.render_json(self.out))
        broken['live_execution_authorized'] = True
        for render in (sim_render.render_json, sim_render.render_text):
            with self.assertRaises(AppError):
                render(broken)

    def test_text_names_the_result_the_bounds_and_the_findings(self):
        text = ' '.join('\n'.join(sim_render.render_text(self.out)).split())
        self.assertIn(self.out['simulation_id'], text)
        self.assertIn('synthetic_snapshot_simulation', text)
        self.assertIn('newly targeted', text)
        self.assertIn('Ring r1', text)
        self.assertIn('predicted_configuration_conflict', text)
        self.assertIn('definite_under_model', text)
        self.assertIn('not an observed endpoint failure', text)

    def test_text_says_the_result_authorizes_nothing_and_claims_no_endpoint_effect(self):
        lines = sim_render.render_text(self.out)
        self.assertIn('does not authorize execution', lines[-1])
        self.assertIn('no endpoint effect', lines[-1])

    def test_text_lines_respect_the_width(self):
        for width in (60, 100):
            self.assertTrue(all(len(line) <= width for line in sim_render.render_text(self.out, width)))

    def test_a_bound_is_a_range_and_an_unbounded_upper_is_stated(self):
        doc = s.snapshot_doc(devices=[s.device('a'), s.device('b')], groups=[s.group('gA', complete=False)],
                             memberships=[s.member('gA', 'a')], collections={'devices': {'complete': False, 'reason': 'query_ceiling'}})
        _, out = simulate(doc, s.revision_doc([s.policy('p', [s.include('gA')], settings=[])]))
        text = '\n'.join(sim_render.render_text(out))
        self.assertIn('1 to 2', text)
        self.assertIn('unbounded', text)
        self.assertNotIn('None', text)

    def test_an_incomplete_snapshot_has_no_safe_verdict_and_never_says_safe(self):
        doc = s.snapshot_doc(devices=[s.device('a')], groups=[s.group('gA')], memberships=[s.member('gA', 'a')],
                             collections={'policies': {'complete': False, 'reason': 'query_ceiling'}})
        _, out = simulate(doc, s.revision_doc([s.policy('p', [s.include('gA')], settings=[])]))
        text = '\n'.join(sim_render.render_text(out))
        self.assertIn('Verdict: no safe verdict', text)
        self.assertNotIn('safe', text.replace('no safe verdict', ''))

    def test_a_complete_snapshot_without_findings_still_is_not_called_safe(self):
        doc = s.snapshot_doc(devices=[s.device('a')], groups=[s.group('gA')], memberships=[s.member('gA', 'a')])
        _, out = simulate(doc, s.revision_doc([s.policy('p', [s.include('gA')], settings=[])]))
        text = '\n'.join(sim_render.render_text(out))
        self.assertIn('Verdict: no findings under the model', text)
        self.assertNotIn('safe', text.lower())

    def test_the_text_is_deterministic(self):
        self.assertEqual(sim_render.render_text(self.out), sim_render.render_text(json.loads(sim_render.render_json(self.out))))


class Command(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)
        self.doc, self.revision = scenario()
        self.snapshot_path = self.write('snapshot.json', self.doc)
        self.revision_path = self.write('revision.json', self.revision)

    def write(self, name, value):
        path = self.dir / name
        path.write_text(json.dumps(value), encoding='utf-8')
        return path

    def cli(self, *args):
        return subprocess.run([sys.executable, str(CLI), *map(str, args)], text=True, capture_output=True, cwd=str(self.dir))

    def test_the_command_is_listed_in_the_help(self):
        result = self.cli('--help')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('simulate', result.stdout)

    def test_json_output_is_the_schema_result_and_matches_the_library(self):
        result = self.cli('simulate', '--snapshot', self.snapshot_path, '--revision', self.revision_path)
        self.assertEqual(result.returncode, 0, result.stderr)
        out = json.loads(result.stdout)
        sim_result.validate_result(out)
        _, expected = simulate(self.doc, self.revision, DEFAULT_PROFILE)
        self.assertEqual(out, expected)

    def test_text_output_is_the_text_rendering(self):
        result = self.cli('simulate', '--snapshot', self.snapshot_path, '--revision', self.revision_path, '--format', 'text')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Verdict:', result.stdout)
        self.assertIn('does not authorize execution', result.stdout)
        _, expected = simulate(self.doc, self.revision, DEFAULT_PROFILE)
        self.assertEqual(result.stdout, '\n'.join(sim_render.render_text(expected, 100)) + '\n')

    def test_a_profile_file_is_honoured_and_changes_the_semantics_hash(self):
        plain = json.loads(self.cli('simulate', '--snapshot', self.snapshot_path, '--revision', self.revision_path).stdout)
        path = self.write('profile.json', {'external_management_collected': True})
        custom = json.loads(self.cli('simulate', '--snapshot', self.snapshot_path, '--revision', self.revision_path,
                                     '--profile', path).stdout)
        self.assertNotEqual(plain['input_binding']['semantics_sha256'], custom['input_binding']['semantics_sha256'])
        self.assertNotIn('external_management_unknown', custom['coverage']['unresolved_reasons'])

    def test_an_estate_and_a_population_can_be_simulated_directly(self):
        estate = generate_estate(seed=7, policy_count=1)
        g0, g1, g2 = estate['truth']['groups']
        population = {
            'devices': [s.device('a'), s.device('b')], 'group_domains': {g0: 'device', g1: 'device', g2: 'device'},
            'complete_groups': [g0, g1, g2],
            'memberships': [{'group_id': g1, 'member_id': s.uid('device/a'), 'member_kind': 'device', 'certainty': 'known'}]}
        revision = s.revision_doc()
        revision['removed_policy_ids'] = [estate['truth']['policies'][0]['id']]
        result = self.cli('simulate', '--estate', self.write('estate.json', estate), '--population',
                          self.write('population.json', population), '--revision', self.write('rev.json', revision))
        self.assertEqual(result.returncode, 0, result.stderr)
        out = json.loads(result.stdout)
        sim_result.validate_result(out)
        self.assertFalse(out['coverage']['snapshot_complete'])

    def test_the_command_reads_files_and_writes_none(self):
        before = sorted(os.listdir(self.dir))
        self.cli('simulate', '--snapshot', self.snapshot_path, '--revision', self.revision_path)
        self.cli('simulate', '--snapshot', self.snapshot_path, '--revision', self.revision_path, '--format', 'text')
        self.assertEqual(sorted(os.listdir(self.dir)), before)

    def test_a_missing_file_is_a_coded_error_with_a_nonzero_exit(self):
        result = self.cli('simulate', '--snapshot', self.dir / 'nope.json', '--revision', self.revision_path)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '')
        self.assertIn('"status"', result.stderr)

    def test_an_invalid_snapshot_is_refused_with_its_code(self):
        bad = dict(self.doc, surprise=True)
        result = self.cli('simulate', '--snapshot', self.write('bad.json', bad), '--revision', self.revision_path)
        self.assertEqual(result.returncode, 3)
        self.assertEqual(json.loads(result.stderr)['error']['code'], 'sim_snapshot_invalid')

    def test_snapshot_and_estate_are_mutually_exclusive_and_one_is_required(self):
        both = self.cli('simulate', '--snapshot', self.snapshot_path, '--estate', self.snapshot_path, '--revision', self.revision_path)
        none = self.cli('simulate', '--revision', self.revision_path)
        self.assertNotEqual(both.returncode, 0)
        self.assertNotEqual(none.returncode, 0)

    def test_main_returns_zero_and_prints_one_json_document(self):
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(['simulate', '--snapshot', str(self.snapshot_path), '--revision', str(self.revision_path)])
        self.assertEqual(code, 0)
        self.assertEqual(len(out.getvalue().strip().splitlines()), 1)
        sim_result.validate_result(json.loads(out.getvalue()))


if __name__ == '__main__':
    unittest.main()
