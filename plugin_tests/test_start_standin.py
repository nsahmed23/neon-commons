"""PKG-START-STANDIN: the start screen prints no stand-in (DIRECTORY, ROOT, ID, PATH) as the operand of a copyable command.

A directory, or a path inside it, that a screen may not show (readiness.display_refused) is said in words on the start screen,
exactly as the catalog says it (PKG-CATALOG-6); a name that can be shown keeps its real, quoted operand. The hostile names are
built at run time, so no source line holds a credential shape or a control character.
"""
import contextlib
import hashlib
import io
import json
import os
import re
import shlex
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from plugin_tests.test_start_goal import Fixtures

# assembled here, never written as a literal
CREDENTIAL = 'tok' + 'en_' + 'gh' + 'p_' + 'A1b2C3d4' * 5
HIDDEN_NAMES = {'credential': CREDENTIAL, 'control': 'bad' + chr(27) + 'name', 'long': 'd' * 70,
                'combining': 'cafe' + chr(0x301)}
ORDINARY = 'estate dir'
WIDTHS = (120, 80, 60)
GOALS = (None, 'inspect', 'discover', 'adopt', 'change')
STAND_INS = ('DIRECTORY', 'ROOT', 'ID', 'PATH')
CANNOT = 'the directory cannot be shown here'


def estate(parent, name, rename=None):
    """A copy of the start tests' full estate (a store, a service, a session, a repository ...) at parent/name. rename maps a
    path inside it to a new name (a surveyed path the screen may not show)."""
    target = Path(parent) / name
    shutil.copytree(Fixtures.get()['full'], target)
    for old, new in (rename or {}).items():
        (target / old).rename(target / new)
    return target


def in_directory(parent, call):
    old = os.getcwd()
    os.chdir(parent)
    try:
        return call()
    finally:
        os.chdir(old)


def render(route, parent, name, width, goal):
    """The start screen's rows for the surveyed parent/name, typed from parent. route: built (the builders' own value), plain
    (the same value after a JSON round trip, which has no text build) or cli (main(['start', ...]))."""
    from intune_iac import cli, entry

    def run():
        if route == 'cli':
            out = io.StringIO()
            argv = ['start', name] + (['--goal', goal] if goal else [])
            with patch('shutil.get_terminal_size', return_value=os.terminal_size((width, 40))), contextlib.redirect_stdout(out):
                assert cli.main(argv) == 0
            return out.getvalue().split('\n')
        survey = entry.survey(name, relative_to=os.getcwd())
        view = host_free(entry.goal_readiness(survey, goal)) if goal else None
        if route == 'plain':
            survey = json.loads(json.dumps(survey))
            view = json.loads(json.dumps(view)) if view else None
        return entry.start_lines(survey, width, view, goal_hint=view is None)
    return in_directory(parent, run)


def host_free(view):
    """The readiness view with this machine's own facts (operating system, platform, machine, Python) replaced by fixed words, so
    that a golden does not depend on the host the test runs on."""
    import platform
    import sys
    text = json.dumps(view)
    facts = {os.name: 'posix', sys.platform: 'linux', platform.machine(): 'x86_64', '%d.%d.%d' % sys.version_info[:3]: '3.12.3'}
    for real, fixed in facts.items():
        text = text.replace('"%s"' % real, '"%s"' % fixed)
    return json.loads(text)


def logical_rows(lines):
    """The rows with every backslash continuation joined, as a shell reads a copied command."""
    rows, held = [], ''
    for line in lines:
        if line.endswith(' \\'):
            held += line[:-1].strip() + ' '
            continue
        rows.append((held + line.strip()).strip())
        held = ''
    return rows + ([held.strip()] if held else [])


def is_stand_in(token):
    return token in STAND_INS or any(token.startswith(word + '/') for word in STAND_INS)


def stand_in_operands(lines):
    """Every operand of a printed command that is a stand-in: DIRECTORY, ROOT, ID or PATH alone or at the start of a path. A
    command is a row that starts with the program name, or the program name inside a sentence up to the sentence's end; the
    workspace's own :repository-entry command is read the same way."""
    found = []
    for row in logical_rows(lines):
        commands = [row] if row.startswith('intune-iac ') else row.split('intune-iac ')[1:]
        commands += re.findall(r':repository-entry\s+(.*)', row)
        for command in commands:
            command = re.split(r'\s\(|[.;:](?:\s|$)', command)[0]
            try:
                tokens = shlex.split(command)
            except ValueError:
                tokens = command.split()
            found += [token for token in tokens if is_stand_in(token)]
    return found


def flat(lines):
    return ' '.join(' '.join(lines).replace(' \\ ', ' ').split())


def tearDownModule():
    Fixtures.release()


class Estates(unittest.TestCase):
    """A parent directory holding one copy of the estate per name, built once per class."""
    names = {}
    rename = None

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.parent = cls.temp.name
        for name in cls.names.values():
            estate(cls.parent, name, cls.rename)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()


class HiddenDirectoryCommandTests(Estates):
    """Item 1: a directory the screen may not show is never the operand of a start-screen command; it is said in words."""
    names = dict(HIDDEN_NAMES, ordinary=ORDINARY)
    ROUTES = ('built', 'plain', 'cli')

    def test_no_start_command_has_a_stand_in_operand_for_a_hidden_directory(self):
        for label, name in HIDDEN_NAMES.items():
            for route in self.ROUTES:
                for goal in GOALS:
                    with self.subTest(name=label, route=route, goal=goal):
                        lines = render(route, self.parent, name, 100, goal)
                        self.assertEqual(stand_in_operands(lines), [], flat(lines))

    def test_the_next_steps_say_the_command_and_what_it_is_run_on_in_words(self):
        for label, name in HIDDEN_NAMES.items():
            with self.subTest(name=label):
                text = flat(render('built', self.parent, name, 100, None))
                self.assertIn('Resume with the wizard command using this saved session; its path cannot be shown here.', text)
                self.assertIn('Open the workspace with the workbench workspace command using this saved store; '
                              'its path cannot be shown here.', text)
                self.assertNotIn('workbench workspace --root', text)

    def test_the_sign_in_note_and_the_catalog_pointer_are_the_catalogs_own_sentences(self):
        from intune_iac import readiness
        pointer = ('Catalog of what this build supports and where each goal stands: '
                   + readiness.IN_WORDS % 'catalog')
        self.assertIn(CANNOT, pointer)
        for label, name in HIDDEN_NAMES.items():
            for route in self.ROUTES:
                with self.subTest(name=label, route=route):
                    text = flat(render(route, self.parent, name, 100, 'discover'))
                    self.assertIn(pointer, text)
                    self.assertIn(readiness.NO_CHECK_HIDDEN % 'discover', text)
                    self.assertNotIn('--goal discover --check-signin azure (it runs', text)
                    hint = flat(render(route, self.parent, name, 100, None))
                    self.assertIn(pointer, hint)

    def test_a_displayable_directory_keeps_its_real_quoted_operand_in_every_command(self):
        for route in self.ROUTES:
            with self.subTest(route=route):
                text = flat(render(route, self.parent, ORDINARY, 120, 'discover'))
                # plain data has no relative_to: the directory in full, quoted; the builders and the command line write it
                # relative to where the command is typed
                operand = shlex.quote(str(Path(self.parent) / ORDINARY)) if route == 'plain' else "'estate dir'"
                self.assertIn("intune-iac catalog %s" % operand, text)
                self.assertIn("intune-iac start %s --goal discover --check-signin azure" % operand, text)
                if route != 'plain':
                    self.assertIn("intune-iac workbench workspace --root 'estate dir/store' --service-root 'estate dir/service'",
                                  text)
                self.assertNotIn(CANNOT, text)
                self.assertEqual(stand_in_operands(render(route, self.parent, ORDINARY, 120, 'discover')), [])


class HiddenPathCommandTests(Estates):
    """A path inside a displayable directory that the screen may not show is not a command operand either."""
    names = {'ordinary': ORDINARY}
    rename = {'session.json': CREDENTIAL + '.json'}

    def test_a_surveyed_path_the_screen_may_not_show_is_never_a_stand_in_operand(self):
        for route in ('built', 'plain', 'cli'):
            for goal in GOALS:
                with self.subTest(route=route, goal=goal):
                    lines = render(route, self.parent, ORDINARY, 100, goal)
                    self.assertEqual(stand_in_operands(lines), [], flat(lines))
                    self.assertNotIn(CREDENTIAL, '\n'.join(lines))

    def test_the_commands_for_the_paths_that_can_be_shown_are_unchanged(self):
        text = flat(render('built', self.parent, ORDINARY, 100, None))
        self.assertIn("intune-iac workbench workspace --root 'estate dir/store' --service-root 'estate dir/service'", text)
        self.assertIn('Resume with the wizard command using this saved session; its path cannot be shown here.', text)


class ProducerStringTests(Estates):
    """Item 2: every string constant in entry.py that holds a stand-in token (an ast walk, not a list), and every string in
    readiness.py and catalog.py that holds DIRECTORY (what the goal rows record), is shown to lose the token under a hidden
    directory: planted as the recorded step and note of a goal row, and as a recorded note of the survey, in the quoting variants
    of the CATALOG-6 producer test."""
    names = {'credential': CREDENTIAL}
    # a stand-in word: DIRECTORY, ROOT, ID or PATH, alone or as a piece of a placeholder such as SERVICE_ROOT or TENANT_ID
    TOKEN = re.compile(r'(?<![A-Za-z0-9])(?:DIRECTORY|ROOT|ID|PATH)(?![A-Za-z0-9])')
    DIRECTORY_TOKEN = re.compile(r'(?<![A-Za-z0-9_])DIRECTORY(?![A-Za-z0-9_])')
    counts = {}

    @staticmethod
    def strings(modules, token):
        """Every string constant of the modules (docstrings aside) that holds the token, whitespace made single, the program name
        written in for %s."""
        import ast
        found = set()
        for name in modules:
            path = Path(__file__).resolve().parents[1] / 'intune_iac' / name
            tree = ast.parse(path.read_text(encoding='utf-8'))
            # a docstring is documentation, not a string the product can print
            docs = {id(node.body[0].value) for node in ast.walk(tree)
                    if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                    and node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant)}
            for node in ast.walk(tree):
                if (isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs
                        and token.search(node.value)):
                    found.add(' '.join(node.value.replace('%s', 'intune-iac').split()))
        return sorted(found)

    def screen(self, text):
        """The start screen of the hidden directory, with text planted as the recorded step and note of every needed goal row and
        as a recorded note of the survey (plain data), at a width that wraps nothing."""
        from intune_iac import entry

        def run():
            survey = entry.survey(CREDENTIAL, relative_to=os.getcwd())
            view = host_free(entry.goal_readiness(survey, 'discover'))
            for row in view['rows']:
                if row['needed']:
                    row['state'], row['missing'], row['next_action'] = 'missing', [text], text
            view['not_established'] = [text]
            plain = json.loads(json.dumps(survey))
            plain['missing'] = [text]
            return entry.start_lines(plain, 400, view)
        return in_directory(self.parent, run)

    def shown(self, lines):
        """The rows without the three the screen is allowed to say DIRECTORY on: the header, the statement under it, and the
        Directory: line of the goal block."""
        from intune_iac import readiness
        allowed = ('DIRECTORY | offline', readiness.DIRECTORY_NOT_SHOWN_SENTENCE, 'Directory: DIRECTORY')
        return [line for line in lines if not line.startswith(allowed)]

    def check(self, variant):
        lines = self.screen(variant)
        rows = self.shown(lines)
        self.assertEqual(stand_in_operands(lines), [], variant)
        self.assertIsNone(self.DIRECTORY_TOKEN.search('\n'.join(rows).replace("'", '')), variant)

    def test_every_stand_in_string_of_entry_py_and_every_quoting_variant_loses_the_token_on_a_hidden_screen(self):
        from plugin_tests import test_catalog_commands as commands
        strings = self.strings(('entry.py',), self.TOKEN)
        # the walk found the producers: the two placeholders, the fill-in placeholder SERVICE_ROOT and the two init templates
        for expected in ('DIRECTORY', 'PATH', 'SERVICE_ROOT'):
            self.assertIn(expected, strings)
        self.assertGreaterEqual(len(strings), 5, strings)
        count = 0
        for text in strings:
            for variant in [text] + commands.StandInRuleTests.variants(text):
                count += 1
                with self.subTest(variant=variant[:120]):
                    self.check(variant)
        type(self).counts['entry.py'] = (len(strings), count)

    def test_every_recorded_step_of_readiness_and_the_catalog_loses_the_token_on_a_hidden_screen(self):
        from plugin_tests import test_catalog_commands as commands
        strings = [text for text in self.strings(('readiness.py', 'catalog.py'), self.DIRECTORY_TOKEN) if len(text) < 400]
        self.assertGreater(len(strings), 8)
        count = 0
        for text in strings:
            for variant in [text] + commands.StandInRuleTests.variants(text)[:12]:
                count += 1
                with self.subTest(variant=variant[:120]):
                    self.check(variant)
        type(self).counts['readiness.py and catalog.py'] = (len(strings), count)


# sha256 (first 16 hex digits) of the screen's rows for an ordinary name, taken on the base of this package (04260b8), before the change.
# key: route|width|goal. The temporary parent and fixture directories are written PARENT and FIXTURES first, and the readiness view
# is host-free (host_free). Linux with a temporary directory of /tmp only: a longer path wraps differently.
GOLDEN = {
    'built|120|-': 'a378d6120b76d906',
    'built|120|adopt': '08df25b99b104d1d',
    'built|120|change': '5cb589f43e20aa9f',
    'built|120|discover': '9e471c49391f738a',
    'built|120|inspect': '16b417bb3d36ef4f',
    'built|60|-': '4dd1a37651fe1184',
    'built|60|adopt': '011ef338f0416c00',
    'built|60|change': '6b1e29c803c34b9a',
    'built|60|discover': '7197bf7cdca696bf',
    'built|60|inspect': '632aafc1873b5204',
    'built|80|-': 'b8dedd1d4e806713',
    'built|80|adopt': '9ba55ab31194e532',
    'built|80|change': '0c99c0468a9f11d8',
    'built|80|discover': 'c9d2cc4e355b80f7',
    'built|80|inspect': '9174395b60defe96',
    'cli|120|-': '13cd9bf05125923d',
    'cli|60|-': 'bcc756f2b922978d',
    'cli|80|-': '92f23aa461921b09',
    'plain|120|-': '089fefbc753d6101',
    'plain|120|adopt': 'ea2557176a1eeb1e',
    'plain|120|change': '401a644c07efb973',
    'plain|120|discover': '8752ce11b44cf056',
    'plain|120|inspect': '174f7fa1b981102d',
    'plain|60|-': 'da5e9d61168a82cd',
    'plain|60|adopt': '4d65eb0a523a01a6',
    'plain|60|change': '7de75fffd85a1ef6',
    'plain|60|discover': 'd5aa7a495f1e2dda',
    'plain|60|inspect': '4ea2be94fc58b73b',
    'plain|80|-': '56d736abaa814071',
    'plain|80|adopt': 'd9749a8e20419e30',
    'plain|80|change': '76b106d5986da03b',
    'plain|80|discover': 'a0efc3d448b3ca3b',
    'plain|80|inspect': 'e916c3790f443c86',
}


def digest(text, parent):
    """The 16 hex digits of the screen's text with the two temporary directories (of equal length every time) named."""
    text = text.replace(parent, 'PARENT').replace(str(Fixtures.get()['full'].parent), 'FIXTURES')
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]


class SweepTests(Estates):
    """Item 3: hidden names (credential-shaped, a control character, too wide for the row, a combining mark) at 120, 80 and 60
    columns, through the builders, the plain data and the command line."""
    names = dict(HIDDEN_NAMES, ordinary=ORDINARY)
    ROUTES = ('built', 'plain', 'cli')

    def test_no_row_holds_a_stand_in_as_a_command_operand(self):
        count = 0
        for label, name in HIDDEN_NAMES.items():
            for route in self.ROUTES:
                for width in WIDTHS:
                    for goal in GOALS:
                        with self.subTest(name=label, route=route, width=width, goal=goal):
                            lines = render(route, self.parent, name, width, goal)
                            count += 1
                            self.assertEqual(stand_in_operands(lines), [], flat(lines))
                            text = '\n'.join(lines)
                            # nothing of the name: not whole, not as the escape a terminal guard would write for it
                            for fragment in (name, name.replace(chr(27), '\\u001b'), name.replace(chr(0x301), '\\u0301'), 'd' * 20):
                                if label != 'long' and fragment == 'd' * 20:
                                    continue
                                self.assertNotIn(fragment, text)
        self.assertEqual(count, len(HIDDEN_NAMES) * len(self.ROUTES) * len(WIDTHS) * len(GOALS))

    def test_each_notice_appears_whole_on_every_screen_that_has_its_command(self):
        from intune_iac import readiness
        said = readiness.DIRECTORY_NOT_SHOWN_SENTENCE
        pointer = 'Catalog of what this build supports and where each goal stands: ' + readiness.IN_WORDS % 'catalog'
        for label, name in HIDDEN_NAMES.items():
            for route in self.ROUTES:
                for width in WIDTHS:
                    for goal in GOALS:
                        with self.subTest(name=label, route=route, width=width, goal=goal):
                            text = flat(render(route, self.parent, name, width, goal))
                            ordinary = flat(render(route, self.parent, ORDINARY, width, goal))
                            self.assertEqual(text.count(said), 1, text)         # once, under the header
                            self.assertIn(pointer, text)                        # the screen has a catalog pointer, said whole
                            if 'No sign-in check was run. To look for an existing Azure sign-in, run:' in ordinary:
                                self.assertIn(readiness.NO_CHECK_HIDDEN % goal, text)
                            if route == 'plain':
                                self.assertIn('A next step names a path whose name is not shown here.', text)
                            else:
                                self.assertIn('Open the workspace with the workbench workspace command using this saved store; '
                                              'its path cannot be shown here.', text)
                                self.assertIn('Resume with the wizard command using this saved session; its path cannot be '
                                              'shown here.', text)

    @unittest.skipUnless(os.name == 'posix' and tempfile.gettempdir() == '/tmp', 'the goldens were taken with paths under /tmp')
    def test_an_ordinary_name_prints_byte_for_byte_what_it_printed_before(self):
        seen = 0
        for route in self.ROUTES:
            for width in WIDTHS:
                for goal in GOALS:
                    if route == 'cli' and goal:
                        continue                  # the command line reads the host itself: no golden for the goal block
                    with self.subTest(route=route, width=width, goal=goal):
                        text = '\n'.join(render(route, self.parent, ORDINARY, width, goal))
                        seen += 1
                        self.assertEqual(digest(text, self.parent), GOLDEN['%s|%d|%s' % (route, width, goal or '-')])
        self.assertEqual(seen, len(GOLDEN))
