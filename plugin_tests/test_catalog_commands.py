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
                # round 2: the operation stays as prose; no command, no hidden operand
                flat = ' '.join(text.split())
                self.assertIn('Resume with the workbench workspace command using this saved store; its path cannot be shown here.',
                              flat)
                self.assertNotIn('Resume: no command', flat)
                self.assertNotIn('intune-iac workbench workspace', flat)

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


class RefusedFileNameTests(unittest.TestCase):
    """Round 2 (Sol, Medium): PATH stands for a surveyed file whose own name the display rule refuses. It is a valid relative
    path too, so no catalog command may carry it as an operand; the row says what to do in words."""

    FILES = {'credential': 'ex' + 'ghp_' + 'A1b2C3d4' * 5 + '.json', 'control': 'ex\x1bport.json'}

    def workspace(self, file_name):
        import shutil
        from plugin_tests.test_start_goal import ROOT
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        parent = Path(temp.name)
        folder = parent / 'work'
        folder.mkdir()
        shutil.copyfile(ROOT / 'examples/context.json', folder / 'context.json')
        try:
            shutil.copyfile(ROOT / 'examples/supported/input/export.json', folder / file_name)
        except OSError:
            self.skipTest('this file system refuses that name')
        return parent

    def test_a_refused_export_name_is_never_a_stand_in_operand_in_a_catalog_command(self):
        for label, file_name in self.FILES.items():
            parent = self.workspace(file_name)
            for argv in ((), ('--goal', 'discover')):
                with self.subTest(file=label, argv=argv):
                    text = run_catalog_text(parent, 'work', *argv)
                    flat = ' '.join(text.replace(' \\', '').split())
                    self.assertIn('Export PATH', flat)      # the row is there, its name is not shown
                    for line in text.split('\n'):
                        self.assertIsNone(STAND_IN.search(line.replace(' \\', '')), line)
                    self.assertNotIn('--input PATH', flat)
                    self.assertIn('Resume with the wizard command using this export; its path cannot be shown here.', flat)

    def test_an_ordinary_export_name_keeps_its_resume_command(self):
        parent = self.workspace('export.json')
        text = ' '.join(run_catalog_text(parent, 'work').replace(' \\', '').split())
        self.assertIn('Resume: intune-iac wizard --session NEW_SESSION.json --input work/export.json', text)


class StandInRuleTests(unittest.TestCase):
    """PKG-CATALOG-6 round 12: on a screen that may not show the directory, each part of a recorded step (a line is cut at
    ' && ', ' || ', ' | ' and '; ') is replaced by words when it holds a GENERATING character ($ ` ~ { } * ? [ ] ! ^ < >, which
    can make bash produce text that is not in the input) or when the uppercase letters D I R E C T O R Y appear in it in order
    (without generating characters bash can only delete characters, so any DIRECTORY it outputs is such a subsequence of the
    input). Every other part stays byte for byte: prose with parentheses, double quotes and semicolons included. The cost is
    over-replacement when the letters happen to appear in order. Round 11 replaced all non-simple text; under this rule that
    stand-in-free text is kept again (each such test says so)."""

    GENERIC = 'this step names the directory, which cannot be shown here'
    MAY = 'this step may name the directory, which cannot be shown here'
    START = 'the start command with this directory (%s)' % CANNOT
    CATALOG = 'the catalog command with this directory (%s)' % CANNOT
    GENERATING = tuple('$`~{}*?[]!^<>')

    REPLACED = (
        ('Run: intune-iac start DIRECTORY', START),
        ("Run: intune-iac start 'DIRECTORY' --goal discover --check-signin azure", START),
        ('Run: intune-iac catalog DIRECTORY --goal discover', CATALOG),
        ('Run: intune-iac start --goal discover DIRECTORY', START),
        ('Run: intune-iac start "DIRECTORY"', START),
        ('Run: intune-iac start DIRECTORY and pass its result to this check.', START),
        ('Name the tenant as a GUID, then run: intune-iac start DIRECTORY', START),
        ('Run:   intune-iac    start     DIRECTORY     --goal   discover', START),
        ('x DIRECTORY', GENERIC), ("x 'a DIRECTORY'", GENERIC), ('DIRECTORY/store', GENERIC), ('x DIRECTORY.', GENERIC),
        # the command sentence is chosen on a quote- and backslash-normalized copy and accepts a tab (wording only)
        ('Run: intune-"iac"\tstart DIRECTORY', START), ('Run: intune-iac "start" DIRECTORY', START), ("Run: 'intune-iac' catalog\tDIRECTORY", CATALOG),
        ('Run: intune\\-iac start DIRECTORY', START), ('echo\tDIRECTORY', GENERIC), ('echo DIRECTORY\n', GENERIC),
        ('echo DIRECTORY;', GENERIC), ('echo (DIRECTORY)', GENERIC), ('echo "DIRECTORY"', GENERIC), ('echo DIREC\\\nTORY', GENERIC),
        # the letters in order, not spelling the word: over-replacement, the declared cost
        # (the wording reads the normalized copy, where D\IRECTORY is the word: it says "names"; the decision does not depend on it)
        ('echo D\\IRECTORY', GENERIC), ('echo "D\\IRECTORY"', GENERIC), ("echo 'D\\IRECTORY'", GENERIC),
        ('echo D x I y R z E w C v T u O t R s Y', MAY),
        # extended globs: with extglob on, +(Y|R|O|T|C|E|I|D) matches a directory named DIRECTORY
        ('echo +(Y|R|O|T|C|E|I|D)', MAY), ('echo @(a|b)', MAY), ('echo +(a)', MAY), ('echo a@(b)', MAY),
        # bash joins a backslash-newline before it tokenizes, so a continuation cannot hide an opener
        ('command echo +\\\n(Y|R|O|T|C|E|I|D)', MAY), ('echo @\\\n(a)', MAY), ('echo +\\\n(a)', MAY), ('echo $\\\nHOME', MAY),
        ('echo *\\\n(a)', MAY), ('echo D\\\nIRECTORY', GENERIC),
        ('Disk Input Report: Error Count Total Of Rows, Yes', MAY),
        # the letters of DIRECTORY inside two other words (a producer's own REPOSITORY_DIRECTORY): replaced too, the declared cost
        ('Run intune-iac start REPOSITORY_DIRECTORY from a Git checkout', START), ('x DIRECTORYX XDIRECTORY', MAY),
    )
    # stand-in free, no generating character, letters not in order: byte for byte (prose with parentheses, quotes, semicolons)
    KEPT = (
        'Run: intune-iac start --goal discover', 'Run: intune-iac catalog --check-signin azure',
        'Run: intune-iac doctor to see the host profiles and which tools are on the search path.',
        "intune-iac catalog 'estate dir'",
        'x', '', 'See examples/context.json', "x 'a b' c", 'echo # a', 'echo "a"', 'echo (a)',
        'Run: intune-iac start "--goal" discover', 'Run: intune-iac\tstart\t--goal\tdiscover', 'echo a\\ b', 'echo DIRECT',
        'echo DIRECTOR', 'echo directory', 'echo YROTCERID', 'echo user@host (x)', 'echo a\\\nb', 'echo user@\\\nhost (x)', 'echo 1+\\\n1 (2)', 'echo 1+1 (2)', 'echo a+ (b)', 'echo a @ (b)', 'echo DIRECTORY'[:-3].lower(),
        'Provide a bounded context JSON (tenant, cloud, stack and component), then run: intune-iac start --goal discover',
        'Put one selectable stack and component from "selectable" into the context JSON (examples/context.json shows the shape)',
        'to enter a repository you maintain, run: intune-iac workbench repository-entry --root STORE --repo REPOSITORY '
        '(in the workspace: :repository-entry REPOSITORY)',
    )
    OPERATORS = (
        ('Run: echo ok; intune-iac start DIRECTORY', 'Run: echo ok; ' + START),
        ('true && intune-iac catalog DIRECTORY --goal discover', 'true && ' + CATALOG),
        ('intune-iac start DIRECTORY && echo ok', START + ' && echo ok'),
        ('intune-iac start DIRECTORY || echo no', START + ' || echo no'),
        ('intune-iac start DIRECTORY | cat', START + ' | cat'),
        ('intune-iac start --goal discover && intune-iac catalog DIRECTORY', 'intune-iac start --goal discover && ' + CATALOG),
        ('intune-iac start --goal discover | intune-iac catalog DIRECTORY', 'intune-iac start --goal discover | ' + CATALOG),
        ('intune-iac start DIRECTORY; intune-iac start --goal discover', START + '; intune-iac start --goal discover'),
        ('echo ok; echo $(date)', 'echo ok; ' + MAY),
        ('intune-iac start --goal discover && echo DIRECTORY', 'intune-iac start --goal discover && ' + GENERIC),
        ('echo ok | echo "a DIRECTORY"', 'echo ok | ' + GENERIC),
        ('Provide a bounded context JSON (tenant, cloud; examples/context.json shows the shape), then run: intune-iac start DIRECTORY',
         'Provide a bounded context JSON (tenant, cloud; ' + START),
    )

    def test_a_part_with_the_letters_in_order_or_a_generating_character_is_words(self):
        from intune_iac import readiness
        for text, expected in self.REPLACED:
            with self.subTest(text=text):
                self.assertEqual(readiness.without_stand_in(text), expected)

    def test_every_generating_character_fails_closed_alone(self):
        from intune_iac import readiness
        for char in self.GENERATING:
            for text in ('echo a%sb' % char, 'echo %s' % char, "echo '%s'" % char, 'echo "%s"' % char, 'echo \\%s' % char):
                with self.subTest(text=text):
                    self.assertEqual(readiness.without_stand_in(text), self.MAY)

    def test_every_other_part_stays_byte_for_byte_including_the_prose_round_11_replaced(self):
        from intune_iac import readiness
        for text in self.KEPT:
            with self.subTest(text=text):
                self.assertEqual(readiness.without_stand_in(text), text)

    def test_the_producer_steps_round_11_replaced_are_kept_when_they_hold_no_stand_in(self):
        from intune_iac import readiness
        capture = readiness.with_legend('intune-iac capture --tenant 11111111-1111-4111-8111-111111111111 --policy POLICY '
                                        '--output NEW_DIR --token-env TOKEN_VARIABLE_NAME')
        self.assertIn('(POLICY is the policy id, a GUID; NEW_DIR is a folder', capture)
        self.assertEqual(readiness.without_stand_in(capture), capture)
        self.assertEqual(readiness.without_stand_in(readiness.with_legend('intune-iac target authenticate --input TARGET_JSON '
                                                    '--provider-secret-fd FD --backend-secret-fd FD')), readiness.with_legend(
            'intune-iac target authenticate --input TARGET_JSON --provider-secret-fd FD --backend-secret-fd FD'))

    def test_a_line_is_cut_only_at_the_simple_separators_and_each_part_is_read_alone(self):
        from intune_iac import readiness
        for text, expected in self.OPERATORS:
            with self.subTest(text=text):
                self.assertEqual(readiness.without_stand_in(text), expected)

    @staticmethod
    def producer_strings():
        """Every string constant in readiness.py and catalog.py that holds the word DIRECTORY (an AST walk, not a list), with the
        program name written in for %s."""
        import ast
        found = []
        for name in ('readiness.py', 'catalog.py'):
            path = Path(__file__).resolve().parents[1] / 'intune_iac' / name
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and 'DIRECTORY' in node.value:
                    found.append(node.value.replace('%s', 'intune-iac'))
        return sorted(set(found))

    TOKEN = re.compile(r'(?<![A-Za-z0-9_])DIRECTORY(?![A-Za-z0-9_])')

    @staticmethod
    def must_replace(text):
        """The rule, written again here from the contract: some part (cut at the separators) has a generating character or the
        letters of DIRECTORY in order."""
        for part in re.split(r'( && | \|\| | \| |; )', text)[::2]:
            part = part.replace('\\\n', '')          # bash joins a backslash-newline before it tokenizes
            letters = iter(part)
            if (any(char in '$`~{}*?[]!^<>' for char in part) or '@(' in part or '+(' in part
                    or all(letter in letters for letter in 'DIRECTORY')):
                return True
        return False

    @classmethod
    def variants(cls, text):
        """The producer string spelled other ways: each word quoted four ways, blanks as tabs, behind another command."""
        words = text.split(' ')
        out = [text, text.replace(' ', '\t'), 'echo ok; ' + text, 'true && ' + text, text.replace(' ', ' \t '), 'x | ' + text,
               "x '" + text.replace("'", '')[:40] + "'"]
        for index, word in enumerate(words):
            for wrap in ("'%s'", '"%s"', "$'%s'", None):
                said = (wrap % word) if wrap else ('\\' + word if word else word)
                out.append(' '.join(words[:index] + [said] + words[index + 1:]))
        return out

    def test_every_producer_string_and_every_variant_loses_the_stand_in_and_is_otherwise_kept(self):
        from intune_iac import readiness
        strings = self.producer_strings()
        self.assertGreater(len(strings), 8)           # the walk found the producers (readiness.py and catalog.py)
        generated = kept = 0
        for text in strings:
            for variant in [text] + self.variants(text):
                generated += 1
                said = readiness.without_stand_in(variant)
                with self.subTest(variant=variant):
                    self.assertIsNone(self.TOKEN.search(said.replace("'", '')), variant)
                    if self.must_replace(variant):
                        self.assertNotEqual(said, variant)
                    else:
                        self.assertEqual(said, variant)       # kept byte for byte
                        kept += 1
        type(self).producer_counts = (len(strings), generated, kept)
        self.assertGreater(generated, 100)
        self.assertGreater(kept, 5)

    def test_the_catalog_applies_it_to_every_recorded_step_of_a_hidden_directory(self):
        from intune_iac import catalog
        for text, expected in self.REPLACED[:8]:
            goals = [{'goal': 'discover', 'next_action': text, 'blocked': {'next_action': text, 'missing': text}}]
            catalog._shown_goal_steps(goals, 'DIRECTORY', True)
            for said in (goals[0]['next_action'], goals[0]['blocked']['next_action'], goals[0]['blocked']['missing']):
                with self.subTest(text=text):
                    self.assertEqual(said, expected)


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
                    if size[0] >= 80:     # the full notice only where it and the sentence above fit three rows
                        self.assertIn("Plain text: intune-iac catalog, with this workspace's directory (%s)" % CANNOT, text)

    def test_no_route_notice_is_cut_in_a_frame_with_only_three_body_rows(self):
        """Round 2 (Sol, Low): at 12 rows the body holds three rows, two of them the larger-window sentence at 40 to 59 columns."""
        for label, name in NAMES.items():
            temp, parent, directory = make_directory(name)
            self.addCleanup(temp.cleanup)
            value = built(parent, directory)
            for size in ((40, 12), (50, 12), (59, 12)):
                with self.subTest(name=label, size=size):
                    rows = layer_text(value, size)
                    self.assertNotIn('more below', ' '.join(rows))          # nothing is scrolled out of view
                    text = joined(rows)
                    self.assertIn(CANNOT, text.lower())
                    body = [row.strip(' |') for row in rows if row.startswith('|') and row.strip(' |')]
                    self.assertTrue(body[-1].lower().endswith('here'), body)    # the notice's last words are on screen
                    self.assertLessEqual(len(body), 3, rows)

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
