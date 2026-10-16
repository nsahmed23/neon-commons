"""PKG-CATALOG-6 item 1: no stand-in inside a copyable command in the catalog's human output.

`DIRECTORY` is a valid relative path, so a copied `intune-iac catalog DIRECTORY ...` can address a real, unintended folder. Where
the catalog would print a command whose directory operand cannot be shown (refused by the display rule, absent, or wider than its
row), it prints a notice that names what is missing instead (the form the workflow layer uses). The `--json` form is unchanged.
Directory names are built at runtime and go through the product's builders and the real workspace layer.
"""
import contextlib
import io
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from plugin_tests import test_catalog as tc
from plugin_tests import test_readiness as tr
from plugin_tests.test_catalog_layer import TENANT, rows_of, workspace

SIZES = ((40, 12), (59, 24), (80, 19))
# a credential-shaped name is assembled here, not written as a literal
CREDENTIAL = 'tok' + 'en_' + 'gh' + 'p_' + 'A1b2C3d4' * 5
NAMES = {'credential': CREDENTIAL, 'control': 'bad\x1bname', 'long': 'd' * 70}
CANNOT = 'the directory cannot be shown here'
# a stand-in operand: DIRECTORY or PATH where a path stands (alone or as the start of a path), in a command
STAND_IN = re.compile(r'intune-iac\s+(?:\S+\s+)*?(?:DIRECTORY|PATH)(?:/\S*)?(?=\s|$)')
STAND_IN_ANY = re.compile(r'(?<![A-Z_])(?:DIRECTORY|PATH)/')


def make_directory(name):
    """parent/name holding a store, so the saved-projects section has a resume command; (parent, directory)."""
    from intune_iac.workbench_store import WorkbenchStore
    temp = tempfile.TemporaryDirectory()
    parent = Path(temp.name)
    directory = parent / name
    directory.mkdir()
    WorkbenchStore.create(directory / 'store', TENANT)
    return temp, parent, directory


def run_catalog_text(parent, name, *argv, width=100):
    from intune_iac import cli
    out = io.StringIO()
    old = os.getcwd()
    os.chdir(parent)
    try:
        with patch('shutil.get_terminal_size', return_value=os.terminal_size((width, 40))), contextlib.redirect_stdout(out):
            code = cli.main(['catalog', name, *argv])
    finally:
        os.chdir(old)
    assert code == 0, code
    return out.getvalue()


def built(parent, directory):
    from intune_iac import catalog, entry
    old = os.getcwd()
    os.chdir(parent)
    try:
        return catalog.build(entry.survey(directory, relative_to=os.getcwd()), doctor=tc.doctor(), relative_to=os.getcwd())
    finally:
        os.chdir(old)


def layer_text(value, size):
    with tempfile.TemporaryDirectory() as scratch:
        ws = workspace(scratch, size=size)
        ws.value, ws.layer, ws.tab, ws.last_command = value, 'catalog', 7, 'catalog'
        return rows_of(ws)


def joined(rows):
    return ' '.join(' '.join(row.strip(' |+-') for row in rows).split())


class CliTextTests(unittest.TestCase):
    def test_a_directory_the_screen_may_not_show_is_never_a_stand_in_inside_a_command(self):
        for label, name in NAMES.items():
            temp, parent, _ = make_directory(name)
            self.addCleanup(temp.cleanup)
            for argv in ((), ('--goal', 'discover'), ('--check-signin', 'azure')):
                if argv == ('--check-signin', 'azure'):
                    continue  # runs the sign-in detector; the unchecked message is the one under test
                with self.subTest(name=label, argv=argv):
                    text = run_catalog_text(parent, name, *argv)
                    for line in text.split('\n'):
                        self.assertIsNone(STAND_IN.search(line.replace(' \\', '')), line)
                        self.assertIsNone(STAND_IN_ANY.search(line), line)
                    flat = ' '.join(text.split())
                    self.assertIn(CANNOT, flat)

    def test_the_unchecked_sign_in_message_names_what_is_missing_and_prints_no_catalog_command_for_the_directory(self):
        for label, name in NAMES.items():
            temp, parent, _ = make_directory(name)
            self.addCleanup(temp.cleanup)
            with self.subTest(name=label):
                text = ' '.join(run_catalog_text(parent, name, '--goal', 'discover').split())
                self.assertNotIn('intune-iac catalog DIRECTORY', text)
                self.assertIn('--check-signin azure (%s' % CANNOT, text)

    def test_a_resume_command_that_would_name_the_directory_is_not_printed_and_says_why(self):
        for label, name in NAMES.items():
            temp, parent, _ = make_directory(name)
            self.addCleanup(temp.cleanup)
            with self.subTest(name=label):
                text = run_catalog_text(parent, name)
                self.assertNotIn('workbench workspace --root DIRECTORY', text)
                self.assertIn('Resume: no command (the command names a path whose name is not shown here)', text)

    def test_the_recorded_start_command_is_not_printed_with_a_stand_in_either(self):
        for label, name in NAMES.items():
            temp, parent, _ = make_directory(name)
            self.addCleanup(temp.cleanup)
            with self.subTest(name=label):
                text = run_catalog_text(parent, name)
                self.assertNotIn('start DIRECTORY', text)

    def test_an_ordinary_name_prints_exactly_as_before(self):
        temp, parent, _ = make_directory('estate dir')
        self.addCleanup(temp.cleanup)
        text = run_catalog_text(parent, 'estate dir', '--goal', 'discover')
        flat = ' '.join(text.replace(' \\', '').split())
        self.assertIn("intune-iac catalog 'estate dir' --goal discover --check-signin azure", flat)
        self.assertIn("Resume: intune-iac workbench workspace --root 'estate dir/store'", flat)
        self.assertNotIn(CANNOT, flat)
        self.assertNotIn('DIRECTORY is the directory this screen is about', flat)


class LayerRouteTests(unittest.TestCase):
    def test_the_narrow_route_row_prints_a_notice_never_a_command_with_a_stand_in(self):
        for label, name in NAMES.items():
            temp, parent, directory = make_directory(name)
            self.addCleanup(temp.cleanup)
            value = built(parent, directory)
            for size in SIZES:
                with self.subTest(name=label, size=size):
                    rows = layer_text(value, size)
                    text = joined(rows)
                    self.assertIn('larger window', text)
                    self.assertIn(CANNOT, text.lower())
                    self.assertNotIn('catalog DIRECTORY', text)
                    self.assertNotIn('catalog PATH', text)
                    for row in rows:
                        self.assertLessEqual(len(row), size[0], row)
                    if size[0] >= 59:
                        self.assertIn("Plain text: intune-iac catalog, with this workspace's directory (%s)" % CANNOT, text)

    def test_an_absent_directory_says_it_is_not_known(self):
        value = tc.catalog(tr.repository_item())
        value['directory'] = None
        from intune_iac import catalog
        value = catalog.build(dict(tr.survey_of(tr.repository_item()), directory=None), doctor=tc.doctor())
        for size in SIZES:
            with self.subTest(size=size):
                text = joined(layer_text(value, size))
                self.assertNotIn('catalog DIRECTORY', text)
                self.assertIn('the directory is not known here', text.lower())

    def test_a_name_wider_than_the_row_is_a_notice_and_a_name_that_fits_is_the_command_as_before(self):
        temp, parent, directory = make_directory('estate dir')  # quoted: 12 cells; 'Text: intune-iac catalog ' is 25 of 36
        self.addCleanup(temp.cleanup)
        text = joined(layer_text(built(parent, directory), (40, 12)))
        self.assertNotIn('catalog DIRECTORY', text)
        self.assertIn(CANNOT, text.lower())
        fits_temp, fits_parent, fits = make_directory('estate')
        self.addCleanup(fits_temp.cleanup)
        text = joined(layer_text(built(fits_parent, fits), (40, 12)))
        self.assertIn('Text: intune-iac catalog estate', text)
        self.assertNotIn(CANNOT, text)

    def test_an_ordinary_name_prints_the_plain_text_command_as_before_at_the_wider_sizes(self):
        temp, parent, directory = make_directory('estate dir')
        self.addCleanup(temp.cleanup)
        value = built(parent, directory)
        for size in ((59, 24), (80, 19)):
            with self.subTest(size=size):
                self.assertIn("Plain text: intune-iac catalog 'estate dir'", joined(layer_text(value, size)))


if __name__ == '__main__':
    unittest.main()
