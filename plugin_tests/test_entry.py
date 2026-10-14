"""Guided entry: what already exists in a working directory, and what to do next.

The working directory is built with the product's own routes (the classic
wizard, the modeled service, the store); the expected survey is written by hand.
"""
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
OBJECT = '22222222-2222-4222-8222-222222222222'
TENANT = '11111111-1111-4111-8111-111111111111'


class EntryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / 'work'
        self.root.mkdir()

    def build(self):
        from intune_iac.modeled_service import ModeledService
        from intune_iac.wizard import run_wizard
        from intune_iac.workbench_store import WorkbenchStore
        shutil.copyfile(ROOT / 'examples/supported/input/export.json', self.root / 'export.json')
        shutil.copyfile(ROOT / 'examples/context.json', self.root / 'context.json')
        answers = iter([str(self.root / 'export.json'), str(self.root / 'context.json'), str(self.root / 'project'), 'generate', 'save'])
        run_wizard(self.root / 'session.json', input_fn=lambda prompt: next(answers), output_fn=lambda line: None)
        capture = json.loads((self.root / 'export.json').read_text())
        ModeledService.create(self.root / 'service', capture, [OBJECT])
        store = WorkbenchStore.create(self.root / 'store', TENANT)
        store.collect(ModeledService(self.root / 'service'))
        shutil.copytree(self.root / 'project', self.root / 'repository')
        (self.root / 'repository/.git/refs/heads').mkdir(parents=True)
        (self.root / 'repository/.git/HEAD').write_text('ref: refs/heads/main\n')
        (self.root / 'repository/.git/refs/heads/main').write_text('a' * 40 + '\n')
        (self.root / 'notes.json').write_text('{"hello": 1}')

    def survey(self, directory=None):
        from intune_iac.entry import survey
        value = survey(directory or self.root)
        self.assertEqual(value['schema_version'], 'workbench-start/1')
        self.assertFalse(value['execution_authorized'])
        self.assertEqual(value['connection'], 'offline')
        return value

    def by_kind(self, value):
        found = {}
        for item in value['items']:
            found.setdefault(item['kind'], []).append(item)
        return found

    def test_an_empty_directory_explains_how_to_start(self):
        value = self.survey()
        self.assertEqual(value['items'], [])
        joined = '\n'.join(value['next_actions'])
        self.assertIn('intune-iac wizard --session', joined)
        self.assertIn('--input EXPORT_JSON', joined)
        self.assertIn('workbench repository-entry', joined)

    def test_existing_work_is_recognized_with_distinct_states(self):
        self.build()
        value = self.survey()
        found = self.by_kind(value)
        self.assertEqual(sorted(found), ['context', 'export', 'generated_project', 'modeled_service', 'repository', 'store', 'wizard_session'])
        export = found['export'][0]
        # The supported export carries two policies; the wizard selected the first.
        self.assertEqual((export['path'], export['synthetic'], export['policies']),
                         ('export.json', True, [OBJECT, '33333333-3333-4333-8333-333333333333']))
        self.assertEqual(export['states']['qualified'], 'synthetic_only')
        session = found['wizard_session'][0]
        self.assertEqual((session['path'], session['step'], session['output']), ('session.json', 'review', 'project'))
        self.assertTrue(session['states']['configured'])
        generated = {item['path']: item for item in found['generated_project']}
        self.assertEqual(generated['project']['classification'], 'unchanged')
        self.assertEqual(generated['project']['session'], 'session.json')
        # A generated project committed to Git is the engineer's repository, not generated output.
        self.assertNotIn('repository', generated)
        store = found['store'][0]
        self.assertEqual((store['path'], store['tenant_id'], store['objects']), ('store', TENANT, 1))
        self.assertEqual(store['states'], {'discovered': True, 'configured': True, 'authenticated': 'no_live_connection', 'qualified': 'synthetic_only'})
        repository = found['repository'][0]
        self.assertEqual((repository['path'], repository['git_revision']), ('repository', 'a' * 40))
        self.assertIn('orgs/reference/dev', repository['stacks'])
        self.assertEqual(found['modeled_service'][0]['objects'], [OBJECT])
        self.assertNotIn('notes.json', [item['path'] for item in value['items']])
        joined = '\n'.join(value['next_actions'])
        self.assertIn('intune-iac wizard --session session.json', joined)
        self.assertIn('intune-iac workbench workspace --root store --service-root service', joined)
        self.assertIn('intune-iac workbench repository-entry --root store --repo repository', joined)

    def test_an_edited_generated_project_is_named_as_a_repository_owned_edit(self):
        self.build()
        stack = self.root / 'project/stacks/orgs/reference/dev.yaml'
        stack.write_text(stack.read_text().replace('Synthetic reference; not production advice.', 'Synthetic reference; reviewed repository edit.'))
        generated = {item['path']: item for item in self.by_kind(self.survey())['generated_project']}
        self.assertEqual(generated['project']['classification'], 'repository_owned_policy_edit')
        self.assertIn('/vars/policies/', generated['project']['pointer'])

    def test_journey_output_is_classified_against_its_journey(self):
        from intune_iac import journey
        shutil.copyfile(ROOT / 'examples/supported/input/export.json', self.root / 'export.json')
        shutil.copyfile(ROOT / 'examples/context.json', self.root / 'context.json')
        answers = iter(['continue'] * 3 + [OBJECT] + ['continue'] * 4 + ['generate', 'save'])
        journey.run_journey(self.root / 'journey.json', input_fn=lambda prompt: next(answers), output_fn=lambda line: None,
                            input_path=self.root / 'export.json', context_path=self.root / 'context.json', output_path=self.root / 'out')
        found = self.by_kind(self.survey())
        self.assertEqual(found['journey_session'][0]['next_state'], 'validation')
        generated = found['generated_project'][0]
        self.assertEqual((generated['path'], generated['session'], generated['classification']), ('out/' + OBJECT, 'journey.json', 'unchanged'))
        self.assertIn('Resume the journey: intune-iac wizard --journey --session journey.json', '\n'.join(self.survey()['next_actions']))

    def test_a_restart_backup_is_listed_as_kept_not_as_a_session_to_resume(self):
        from intune_iac.wizard import run_wizard
        self.build()
        answers = iter(['restart', 'save'])
        run_wizard(self.root / 'session.json', input_fn=lambda prompt: next(answers), output_fn=lambda line: None)
        value = self.survey()
        found = self.by_kind(value)
        self.assertEqual([item['path'] for item in found['session_backup']], ['session.json.restart-1.json'])
        self.assertEqual(found['session_backup'][0]['session'], 'session.json')
        self.assertNotIn('session.json.restart-1.json', '\n'.join(value['next_actions']))

    def test_links_are_not_followed_and_nothing_is_written(self):
        self.build()
        outside = self.root.parent / 'outside'
        outside.mkdir(); shutil.copyfile(self.root / 'export.json', outside / 'export.json')
        os.symlink(outside, self.root / 'link')
        before = {str(p): (p.stat().st_mtime_ns, p.stat().st_size) for p in self.root.rglob('*') if p.is_file() and not p.is_symlink()}
        value = self.survey()
        self.assertFalse([item for item in value['items'] if item['path'].startswith('link')])
        self.assertIn('link', value['skipped_links'])
        after = {str(p): (p.stat().st_mtime_ns, p.stat().st_size) for p in self.root.rglob('*') if p.is_file() and not p.is_symlink()}
        self.assertEqual(after, before)

    def test_the_text_screen_fits_and_names_the_next_step(self):
        from intune_iac.entry import start_lines
        from intune_iac.workbench_tui import cell_width
        self.build()
        lines = start_lines(self.survey(), 80)
        joined = '\n'.join(lines)
        self.assertEqual(lines[0], 'INTUNE WORKBENCH: START')
        for heading in ('FOUND', 'NEXT'):
            self.assertIn(heading, lines)
        self.assertIn('Store', joined); self.assertIn('synthetic only', joined)
        for line in lines:
            self.assertLessEqual(cell_width(line), 80, line)


class StartCommandTests(unittest.TestCase):
    def run_cli(self, *argv):
        import contextlib, io
        from intune_iac.cli import main
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(['start', *argv])
        return code, out.getvalue()

    def test_start_prints_the_readable_screen_and_json_on_request(self):
        with tempfile.TemporaryDirectory() as temp:
            shutil.copyfile(ROOT / 'examples/supported/input/export.json', Path(temp) / 'export.json')
            code, text = self.run_cli(temp)
            self.assertEqual(code, 0)
            self.assertTrue(text.startswith('INTUNE WORKBENCH: START\n'))
            self.assertIn('export.json', text)
            self.assertIn('An export needs a bounded context JSON', text)
            code, text = self.run_cli(temp, '--json')
            self.assertEqual(code, 0)
            value = json.loads(text)
            self.assertEqual(value['schema_version'], 'workbench-start/1')
            self.assertEqual([item['kind'] for item in value['items']], ['export'])


if __name__ == '__main__':
    unittest.main()
