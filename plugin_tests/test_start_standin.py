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


# sha256 (first 16 hex digits) of the screen's rows for an ordinary name. Taken on the base of this package (04260b8) before
# the change; all 33 were taken again in round 2 (PKG-START-STANDIN), because the next step "Start from the export" of this
# fixture is now said in words (its command held NEW_SESSION.json and NEW_OUTPUT_DIR), and nothing else on the screen changed.
# key: route|width|goal. The temporary parent and fixture directories are written PARENT and FIXTURES first, and the
# readiness view is host-free (host_free). Linux with a temporary directory of /tmp only: a longer path wraps differently.
GOLDEN = {
    'built|120|-': '408f5d8deb11b2f3',
    'built|120|adopt': 'd9e76687a0ee3209',
    'built|120|change': '9feaf63eac2ad467',
    'built|120|discover': '2e96a6893e1648e4',
    'built|120|inspect': 'd6cb074befe6f1e8',
    'built|60|-': 'd7ecef7a29dc844c',
    'built|60|adopt': '648ed36df9625d33',
    'built|60|change': '471a954f01977bef',
    'built|60|discover': '74c94dbeba3b0e00',
    'built|60|inspect': 'fa9f05ec9a11fee6',
    'built|80|-': 'a2d46f429067021e',
    'built|80|adopt': '9a3f7009034e9749',
    'built|80|change': '21ef20cc4f64163a',
    'built|80|discover': 'f1f87aa3c82314d7',
    'built|80|inspect': '5348da356099d53f',
    'cli|120|-': '1b346448b55b6f0d',
    'cli|60|-': '8ce31278ea4f0458',
    'cli|80|-': '190a13af2934097f',
    'plain|120|-': '493952215c3b7477',
    'plain|120|adopt': 'e92da6e362bb7517',
    'plain|120|change': '665074fe39bbb73f',
    'plain|120|discover': 'b39b6dc16e5eccd7',
    'plain|120|inspect': 'aabf7bd2fc85f81a',
    'plain|60|-': 'c71aad4dcbce1f46',
    'plain|60|adopt': '5560bb3990fc00a1',
    'plain|60|change': '8887c0e1fc969d67',
    'plain|60|discover': '7763603b91fc1439',
    'plain|60|inspect': '38e65b2841068bdb',
    'plain|80|-': '553f2eecaffac66e',
    'plain|80|adopt': '20bc7b8e667de2a2',
    'plain|80|change': 'ec450c40db817198',
    'plain|80|discover': '8aca92c77cff7e44',
    'plain|80|inspect': '1c04e145f7b31865',
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


class SharedTemplateSetTests(unittest.TestCase):
    """Round 2, item 1: one explicit set of fill-in templates, defined once (entry.FILL_IN_TEMPLATES) and used by the product and
    by these tests: a word a command may hold only until the person replaces it."""
    REQUIRED = ('DIRECTORY', 'PATH', 'ROOT', 'ID', 'SERVICE_ROOT', 'TENANT_ID', 'STORE', 'CONTEXT_JSON', 'EXPORT_JSON',
                'REPOSITORY', 'NEW_OUTPUT_DIR', 'NEW_SESSION')

    @staticmethod
    def templates():
        from intune_iac import entry
        return getattr(entry, 'FILL_IN_TEMPLATES', frozenset())

    def test_the_set_holds_every_fill_in_name_the_start_screen_can_print(self):
        for name in self.REQUIRED:
            self.assertIn(name, self.templates())

    def test_every_fill_in_word_of_a_command_string_in_entry_py_is_in_the_set(self):
        import ast
        path = Path(__file__).resolve().parents[1] / 'intune_iac' / 'entry.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        word = re.compile(r'^[A-Z][A-Z0-9_]*[A-Z0-9](?:\.[a-z]+)?$')
        found = set()
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            if not re.search(r'(?:intune-iac|%s) +(?:workbench|wizard|capture|start|catalog)\b', node.value):
                continue                                        # a command string, not a heading or a sentence
            for token in node.value.split():
                token = token.strip("'\"(),.;:")
                if word.match(token):
                    found.add(token.split('.')[0])
        self.assertTrue({'STORE', 'TENANT_ID', 'NEW_SESSION', 'NEW_OUTPUT_DIR', 'CONTEXT_JSON', 'EXPORT_JSON',
                         'REPOSITORY'} <= found, found)         # the walk found the producers
        self.assertEqual(sorted(found - self.templates()), [])

    def test_an_operand_is_a_template_when_it_is_one_or_starts_one(self):
        from intune_iac import entry
        is_fill_in = getattr(entry, 'is_fill_in', lambda token: False)
        for token in ('STORE', 'DIRECTORY/store', 'NEW_SESSION.json', 'PATH', 'SERVICE_ROOT', 'ID'):
            self.assertTrue(is_fill_in(token), token)
        for token in ('estate dir/store', 'STOREROOM', 'store', 'session.json', '--root'):
            self.assertFalse(is_fill_in(token), token)


def unresolved_operands(lines):
    """Every operand of a printed command that is a fill-in template (entry.FILL_IN_TEMPLATES): a stand-in for a path the screen may
    not show, or a placeholder the person is to replace. Read as stand_in_operands reads a command."""
    from intune_iac import entry
    # the product's own set; the required names stand in for it on a source that does not have one (to show a test red there)
    names = getattr(entry, 'FILL_IN_TEMPLATES', SharedTemplateSetTests.REQUIRED)
    pattern = re.compile(r'(?:%s)(?:[/.].*)?\Z' % '|'.join(sorted(names, key=len, reverse=True)), re.DOTALL)
    is_fill_in = lambda token: bool(pattern.match(token))
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
            found += [token for token in tokens if is_fill_in(token)]
    return found


def variant_estate(parent, name, kind):
    """parent/name holding what makes the start screen print a next step with a placeholder in it."""
    from intune_iac.workbench_store import WorkbenchStore
    from plugin_tests.test_catalog_layer import TENANT
    target = Path(parent) / name
    if kind == 'empty':                       # nothing recognized: the three fallback steps
        target.mkdir()
    elif kind == 'repository':                # a repository and no store: a store first, then repository-entry with STORE
        shutil.copytree(Fixtures.get()['repository'], target)
    elif kind == 'export':                    # an export no session used: the wizard with NEW_SESSION.json and NEW_OUTPUT_DIR
        estate(parent, name)
        (target / 'session.json').unlink()
    elif kind == 'emptystore':                # an empty store and no service: collect with SERVICE_ROOT
        target.mkdir()
        WorkbenchStore.create(target / 'store', TENANT)
    return target


class PlaceholderCommandTests(unittest.TestCase):
    """Round 2, item 2: a next step whose command still holds a placeholder the person must replace is said in words, for a hidden
    directory and an ordinary one alike; a command whose operands are all resolved keeps its exact form."""
    KINDS = ('empty', 'repository', 'export', 'emptystore')
    NAMES = {'credential': CREDENTIAL, 'ordinary': ORDINARY}
    FALLBACKS = (
        'Start from a supported export with the wizard command, naming a new session file, your export file, your context file '
        'and a new output folder.',
        'Or start from an Atmos repository you maintain, beginning with a store: create it with the workbench init command, naming '
        'its folder and your tenant id.',
        'Then list the policies it holds and the exact command to record each: use the workbench repository-entry command, naming '
        'your store and your repository.')
    STORE_FIRST = 'Create a store first with the workbench init command, naming its folder and your tenant id.'
    MIXED = {
        'emptystore': 'Collect into estate dir/store: use the workbench collect command, naming the operands it still needs.',
        'export': 'Start from the export estate dir/export.json: use the wizard command, naming the operands it still needs.',
        'repository': 'use the workbench repository-entry command, naming the operands it still needs.'}

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.parents = {}
        for kind in cls.KINDS:
            parent = Path(cls.temp.name) / kind
            parent.mkdir()
            for name in cls.NAMES.values():
                variant_estate(parent, name, kind)
            cls.parents[kind] = str(parent)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_no_next_step_holds_a_placeholder_as_the_operand_of_a_command(self):
        for kind in self.KINDS:
            for label, name in self.NAMES.items():
                for route in ('built', 'plain', 'cli'):
                    for width in (120, 60):
                        for goal in (None, 'discover'):
                            with self.subTest(kind=kind, name=label, route=route, width=width, goal=goal):
                                lines = render(route, self.parents[kind], name, width, goal)
                                # the next steps and what precedes them; the goal block's recorded readiness steps (the capture
                                # command and its placeholders) are readiness.py's, a separate package
                                stop = next((i for i, row in enumerate(lines) if row.startswith('GOAL READINESS')), len(lines))
                                self.assertEqual(unresolved_operands(lines[:stop]), [], flat(lines))

    def test_the_fallback_steps_and_the_store_first_step_are_said_in_words(self):
        for label, name in self.NAMES.items():
            for route in ('built', 'plain', 'cli'):
                with self.subTest(name=label, route=route):
                    empty = flat(render(route, self.parents['empty'], name, 100, None))
                    for sentence in self.FALLBACKS:
                        self.assertIn(sentence, empty)
                    repository = flat(render(route, self.parents['repository'], name, 100, None))
                    self.assertIn(self.STORE_FIRST, repository)

    def test_a_step_that_mixes_a_real_path_with_a_placeholder_is_said_in_words_for_an_ordinary_directory(self):
        for kind, sentence in self.MIXED.items():
            for route in ('built', 'cli'):
                with self.subTest(kind=kind, route=route):
                    text = flat(render(route, self.parents[kind], ORDINARY, 100, None))
                    self.assertIn(sentence, text)
        plain = flat(render('plain', self.parents['export'], ORDINARY, 100, None))
        self.assertIn('use the wizard command, naming the operands it still needs.', plain)

    def test_a_command_whose_operands_are_all_resolved_keeps_its_exact_form(self):
        text = flat(render('built', self.parents['emptystore'], ORDINARY, 100, None))
        self.assertIn("intune-iac workbench workspace --root 'estate dir/store'", text)
        text = flat(render('built', self.parents['export'], ORDINARY, 100, None))
        self.assertIn("intune-iac workbench workspace --root 'estate dir/store'", text)
        self.assertIn("intune-iac workbench repository-entry --root 'estate dir/store' --repo 'estate dir/repository'", text)
