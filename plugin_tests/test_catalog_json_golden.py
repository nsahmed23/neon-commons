"""PKG-CATALOG-5: `catalog --json` prints exactly the form of 02f41d5 for the journey 33 estate.

The golden files under plugin_tests/fixtures/catalog_golden were captured from the CLI of a `git archive` export of 02f41d5 (before
any wording change of this package) on an estate built like journey 33's: a store and its modeled service, a wizard session with
its generated project, a repository, a prepared operation, and the export and context the session used, typed from the estate's
parent directory with the relative name `estate dir`. The whole document must be equal, key for key and value for value: the
readable wording of the catalog lives in the text form only. The temporary directory is written back as <TMP> so the text is the
same on every run; the fake az answers the one case that asks for the sign-in check.
"""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / 'plugin_tests' / 'fixtures' / 'catalog_golden'
OBJECT = '22222222-2222-4222-8222-222222222222'
TENANT = '11111111-1111-4111-8111-111111111111'
PLACEHOLDER = '<TMP>'
# name: the arguments after `catalog 'estate dir'`
CASES = {
    'all': ['--json'],
    'inspect': ['--goal', 'inspect', '--json'],
    'discover': ['--goal', 'discover', '--json'],
    'adopt': ['--goal', 'adopt', '--json'],
    'change': ['--goal', 'change', '--json'],
    'signin_azure': ['--check-signin', 'azure', '--json'],
}


def build_estate(parent):
    """The synthetic estate of journey 33 under parent/'estate dir', made with the product's own routes."""
    from intune_iac import maintenance
    from intune_iac.modeled_service import ModeledService
    from intune_iac.wizard import run_wizard
    from intune_iac.workbench_store import WorkbenchStore
    root = Path(parent) / 'estate dir'
    root.mkdir()
    shutil.copyfile(ROOT / 'examples/supported/input/export.json', root / 'export.json')
    shutil.copyfile(ROOT / 'examples/context.json', root / 'context.json')
    answers = iter([str(root / 'export.json'), str(root / 'context.json'), str(root / 'project'), 'generate', 'save'])
    run_wizard(root / 'session.json', input_fn=lambda prompt: next(answers), output_fn=lambda line: None)
    capture = json.loads((root / 'export.json').read_text())
    ModeledService.create(root / 'service', capture, [OBJECT])
    store = WorkbenchStore.create(root / 'store', TENANT)
    store.collect(ModeledService(root / 'service'))
    shutil.copytree(root / 'project', root / 'repository')
    (root / 'repository/.git/refs/heads').mkdir(parents=True)
    (root / 'repository/.git/HEAD').write_text('ref: refs/heads/main\n')
    (root / 'repository/.git/refs/heads/main').write_text('a' * 40 + '\n')
    current = ModeledService(root / 'service').snapshot()['current']
    desired = copy.deepcopy(current['objects'][OBJECT])
    desired['description'] = 'Journey 33 synthetic change'
    (root / 'desired.json').write_text(json.dumps(desired))
    maintenance.propose(root / 'store', root / 'service', OBJECT, root / 'desired.json', root / 'operation-1')
    (root / 'desired.json').unlink()
    return root


def run_catalog(parent, argv, columns=120, environment=None):
    """(exit code, stdout) of `intune-iac catalog 'estate dir' ...` typed from parent, at a fixed width."""
    from intune_iac import cli
    out = io.StringIO()
    old = os.getcwd()
    os.chdir(parent)
    try:
        with patch('shutil.get_terminal_size', return_value=os.terminal_size((columns, 40))), \
                patch.dict(os.environ, environment or {}), contextlib.redirect_stdout(out):
            code = cli.main(['catalog', 'estate dir', *argv])
    finally:
        os.chdir(old)
    return code, out.getvalue()


def normalized(parent, text):
    return text.replace(str(parent), PLACEHOLDER)


def golden_text(name, parent, fakes=None):
    """The normalized `catalog --json` document of one case."""
    environment = {}
    if fakes is not None:
        environment = {'PATH': fakes.path_entry() + os.pathsep + os.environ.get('PATH', '')}
    code, text = run_catalog(parent, CASES[name], environment=environment)
    assert code == 0, (name, code)
    return normalized(parent, text)


class CatalogGoldenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from plugin_tests.signin_fakes import FakeClis, azure_account, azure_list
        cls.temp = tempfile.TemporaryDirectory()
        cls.parent = Path(cls.temp.name)
        cls.estate = build_estate(cls.parent)
        cls.fakes = FakeClis()
        cls.fakes.answer('az', 'account', 'list', out=azure_list(azure_account(tenant=TENANT)))

    @classmethod
    def tearDownClass(cls):
        cls.fakes.cleanup()
        cls.temp.cleanup()

    def text(self, name):
        return golden_text(name, self.parent, self.fakes if name == 'signin_azure' else None)

    def test_every_case_has_a_golden_file_and_no_golden_file_is_orphaned(self):
        self.assertEqual({p.stem for p in GOLDEN.glob('*.json')}, set(CASES))

    def test_the_whole_document_equals_the_02f41d5_document_for_every_case(self):
        for name in CASES:
            expected = (GOLDEN / (name + '.json')).read_text(encoding='utf-8')
            self.assertEqual(self.text(name), expected, name)

    def test_the_golden_files_parse_and_hold_no_home_path_or_credential(self):
        blob = ''
        for name in CASES:
            text = (GOLDEN / (name + '.json')).read_text(encoding='utf-8')
            value = json.loads(text)
            self.assertEqual(value['schema_version'], 'integration-catalog/1', name)
            self.assertIs(value['execution_authorized'], False)
            blob += text
        for fragment in ('/home/', '/Users/', '@', 'eyJ', 'ghp_', 'Bearer'):
            self.assertNotIn(fragment, blob.replace('alex@example.test', ''), fragment)


if __name__ == '__main__':
    unittest.main()
