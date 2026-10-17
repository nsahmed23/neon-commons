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


def is_path_stand_in(token):
    """DIRECTORY, ROOT, ID or PATH alone or at the start of a path: the stand-ins for a path."""
    return token in STAND_INS or any(token.startswith(word + '/') for word in STAND_INS)


def is_stand_in(token):
    """An operand that is a fill-in template: every member of the product's shared set (entry.FILL_IN_TEMPLATES), alone or at the
    start of a path (DIRECTORY/store, NEW_SESSION.json)."""
    from intune_iac import entry
    names = getattr(entry, 'FILL_IN_TEMPLATES', STAND_INS)
    return any(token == name or token.startswith((name + '/', name + '.')) for name in names)


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
# the change, and taken again where a screen changed on purpose: round 2 (the step "Start from the export" in words), round 3
# (the goal block's recorded commands in words) and round 4, which routes the next steps through the one transform
# (readiness.placeholders_in_words) so that the same step now describes each operand from readiness.TEMPLATE_WORDS. All 33
# changed in round 4, because that step is on every screen of this fixture and nothing else on them changed.
# key: route|width|goal. The temporary parent and fixture directories are written PARENT and FIXTURES first, and the
# readiness view is host-free (host_free). Linux with a temporary directory of /tmp only: a longer path wraps differently.
GOLDEN = {
    'built|120|-': '7c2cd51d03a89e17',
    'built|120|adopt': '75ba3de828ed411e',
    'built|120|change': '55ff2a7d8760faf5',
    'built|120|discover': '1b2041dc222fcdd9',
    'built|120|inspect': '0d528f7b89e8396c',
    'built|60|-': '69987efd1f648f2f',
    'built|60|adopt': 'c99f1068896c0155',
    'built|60|change': '39da1bd40cb23f7d',
    'built|60|discover': 'b362f6f206427b19',
    'built|60|inspect': '91c1734b5d88cb89',
    'built|80|-': '5cffba962628686f',
    'built|80|adopt': '215dfaa9317e2234',
    'built|80|change': '820c3eca3df0cc42',
    'built|80|discover': '94f6f56b56913312',
    'built|80|inspect': 'f4c7626393b42943',
    'cli|120|-': '61242f00ecb3f77d',
    'cli|60|-': 'febc80b09bb71595',
    'cli|80|-': '7f0de19b6a129b31',
    'plain|120|-': 'af0d91bcbf1d7f36',
    'plain|120|adopt': '3db86cb1b739fd4e',
    'plain|120|change': 'e56cbed4531880a7',
    'plain|120|discover': '00599f2f0f674f8c',
    'plain|120|inspect': 'c3b56586900c238b',
    'plain|60|-': '37f16056f037466a',
    'plain|60|adopt': 'e95b6dc3d0232271',
    'plain|60|change': '9cd2e745e8831815',
    'plain|60|discover': '7947546a3ef2b5bb',
    'plain|60|inspect': '1f8ffdbb455383b8',
    'plain|80|-': '1dc47487dcb7f69e',
    'plain|80|adopt': '632be0fd1ae7bc2f',
    'plain|80|change': 'af1b3bbcd35d2f38',
    'plain|80|discover': '730677928655e789',
    'plain|80|inspect': 'd9f72665760a8d4f',
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
                'REPOSITORY', 'NEW_OUTPUT_DIR', 'NEW_SESSION', 'POLICY', 'NEW_DIR', 'TOKEN_VARIABLE_NAME', 'TARGET_JSON', 'FD',
                'REPOSITORY_DIRECTORY', 'SESSION', 'STACK', 'COMPONENT')

    @staticmethod
    def templates():
        from intune_iac import entry
        return getattr(entry, 'FILL_IN_TEMPLATES', frozenset())

    def test_the_set_holds_every_fill_in_name_the_start_screen_can_print(self):
        for name in self.REQUIRED:
            self.assertIn(name, self.templates())

    def test_every_fill_in_word_of_a_command_in_entry_readiness_and_catalog_is_in_the_set(self):
        """Round 3: the walk covers the recorded steps of readiness.py and the resume commands of catalog.py too, and reads a
        command the way the display transform does (readiness.command_operands), so a prose word such as GET or GUID is not one."""
        import ast
        from intune_iac import readiness
        operands = getattr(readiness, 'command_operands', lambda text: [])
        word = re.compile(r'^[A-Z][A-Z0-9_]*[A-Z0-9](?:\.[a-z]+)?$')
        found = {}
        for module in ('entry.py', 'readiness.py', 'catalog.py'):
            path = Path(__file__).resolve().parents[1] / 'intune_iac' / module
            tree = ast.parse(path.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                    continue
                # %s after a flag is a value; any other %s is the program name
                text = re.sub(r'(--[a-z-]+ )?%s', lambda m: (m.group(1) + 'value') if m.group(1) else 'intune-iac', node.value)
                for token in operands(text):
                    if word.match(token):
                        found.setdefault(token.split('.')[0], set()).add(module)
        required = {'STORE', 'TENANT_ID', 'NEW_SESSION', 'NEW_OUTPUT_DIR', 'CONTEXT_JSON', 'EXPORT_JSON', 'REPOSITORY', 'POLICY',
                    'NEW_DIR', 'TOKEN_VARIABLE_NAME', 'TARGET_JSON', 'FD', 'REPOSITORY_DIRECTORY', 'SESSION', 'STACK', 'COMPONENT',
                    'PATH', 'DIRECTORY'}
        self.assertTrue(required <= set(found), sorted(required - set(found)))        # the walk found the producers
        self.assertEqual(sorted(set(found) - self.templates()), [])
        self.assertTrue({'readiness.py', 'catalog.py', 'entry.py'} <= set().union(*found.values()), found)

    def test_an_operand_is_a_template_when_it_is_one_or_starts_one(self):
        from intune_iac import entry
        is_fill_in = getattr(entry, 'is_fill_in', lambda token: False)
        for token in ('STORE', 'DIRECTORY/store', 'NEW_SESSION.json', 'PATH', 'SERVICE_ROOT', 'ID', 'POLICY', 'NEW_DIR',
                      'TOKEN_VARIABLE_NAME', 'TARGET_JSON', 'FD', 'REPOSITORY_DIRECTORY'):
            self.assertTrue(is_fill_in(token), token)
        for token in ('estate dir/store', 'STOREROOM', 'store', 'session.json', '--root'):
            self.assertFalse(is_fill_in(token), token)


def unresolved_operands(lines):
    """Every operand of a printed command that is a fill-in template (see is_stand_in)."""
    return stand_in_operands(lines)


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
        'Start from a supported export: the wizard command, naming your export file, your context file and a new output folder',
        'Or start from an Atmos repository you maintain, beginning with a store: the workbench init command, naming your store '
        'folder and your tenant id',
        'Then list the policies it holds and the exact command to record each: the workbench repository-entry command, naming '
        'your store folder and your repository folder')
    STORE_FIRST = 'Create a store first: the workbench init command, naming your store folder and your tenant id'
    MIXED = {
        'emptystore': 'Collect into estate dir/store: the workbench collect command, naming your service folder',
        'export': 'Start from the export estate dir/export.json: the wizard command, naming a new session file and a new output '
                  'folder',
        'repository': 'the workbench repository-entry command, naming your store folder'}

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
                                self.assertEqual(unresolved_operands(lines), [], flat(lines))

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
        self.assertIn('the wizard command, naming a new session file and a new output folder', plain)

    def test_a_command_whose_operands_are_all_resolved_keeps_its_exact_form(self):
        text = flat(render('built', self.parents['emptystore'], ORDINARY, 100, None))
        self.assertIn("intune-iac workbench workspace --root 'estate dir/store'", text)
        text = flat(render('built', self.parents['export'], ORDINARY, 100, None))
        self.assertIn("intune-iac workbench workspace --root 'estate dir/store'", text)
        self.assertIn("intune-iac workbench repository-entry --root 'estate dir/store' --repo 'estate dir/repository'", text)


class CheckerTests(unittest.TestCase):
    """Round 2, item 3: the reader of printed commands knows every member of the shared set, so an empty result means the screen
    has none and not that the reader could not see them."""

    def test_the_reader_finds_every_template_of_the_shared_set_as_an_operand(self):
        from intune_iac import entry
        names = getattr(entry, 'FILL_IN_TEMPLATES', frozenset())
        self.assertGreaterEqual(len(names), 12)
        for name in sorted(names):
            with self.subTest(name=name):
                self.assertEqual(stand_in_operands(['intune-iac workbench workspace --root %s' % name]), [name])
                self.assertEqual(stand_in_operands(['  intune-iac workbench workspace --root \\', '      %s/store' % name]),
                                 [name + '/store'])
        self.assertEqual(stand_in_operands(['intune-iac wizard --session NEW_SESSION.json --output NEW_OUTPUT_DIR']),
                         ['NEW_SESSION.json', 'NEW_OUTPUT_DIR'])
        self.assertEqual(stand_in_operands(["intune-iac workbench init --root STORE --tenant TENANT_ID"]), ['STORE', 'TENANT_ID'])
        self.assertEqual(stand_in_operands(["intune-iac workbench workspace --root 'estate dir/store'"]), [])

    def test_a_hidden_directory_with_nothing_recognized_prints_none_because_it_prints_words(self):
        with tempfile.TemporaryDirectory() as parent:
            Path(parent, CREDENTIAL).mkdir()
            for route in ('built', 'plain', 'cli'):
                for goal in (None, 'discover'):
                    with self.subTest(route=route, goal=goal):
                        lines = render(route, parent, CREDENTIAL, 100, goal)
                        text = flat(lines)
                        steps = [row for row in lines if re.match(r'  \d\. ', row)]
                        self.assertEqual(len(steps), 3, lines)                   # the three fallback steps are there ...
                        self.assertIn('naming your store folder and your tenant id', text)  # ... in words
                        self.assertEqual(stand_in_operands(lines), [])
                        # the reader does see the templates of the old step, so [] above is not blindness
                        old = 'intune-iac workbench init --root STORE --tenant TENANT_ID'
                        self.assertEqual(stand_in_operands([old]), ['STORE', 'TENANT_ID'])


class ConflictSessionTests(unittest.TestCase):
    """Round 2, item 4: a wizard session in conflict keeps the sentence that says what to resolve, whether or not the directory
    can be shown; the command after it is a command only when its path can be shown."""
    REASONS = {'repository_owned_edit': 'Review the repository-owned edit, or hand it off to the repository workflow',
               'output_changed': 'Resolve the changed output (new-path, review or cancel)',
               'output_conflict': 'Resolve the output conflict (new-path, review or cancel)',
               'outcome_unknown': 'Review the uncertain generation outcome before any retry'}
    RESUME = 'Resume with the wizard command using this saved session; its path cannot be shown here.'

    def actions(self, name, session):
        from intune_iac import entry
        with tempfile.TemporaryDirectory() as parent:
            root = Path(parent) / name
            item = dict({'kind': 'wizard_session', 'path': 'session.json', 'valid': True}, **session)
            return entry._next_actions([item], root, parent, entry.text_paths(root, parent)[:2],
                                       lambda: entry.text_paths(root, parent))

    def test_a_hidden_directory_keeps_the_conflict_sentence_before_the_resume_words(self):
        for reason, sentence in self.REASONS.items():
            with self.subTest(reason=reason):
                actions = self.actions(CREDENTIAL, {'step': 'conflict', 'conflict_reason': reason})
                self.assertEqual(actions, ['%s. %s' % (sentence, self.RESUME)])
                self.assertEqual(stand_in_operands(actions), [])
                self.assertNotIn('intune-iac', actions[0])

    def test_a_hidden_directory_without_a_conflict_says_only_the_resume_words(self):
        for session in ({'step': 'review'}, {'step': 'conflict', 'conflict_reason': 'something_new'}):
            with self.subTest(session=session):
                self.assertEqual(self.actions(CREDENTIAL, session), [self.RESUME])

    def test_an_ordinary_directory_keeps_the_conflict_sentence_and_its_command(self):
        actions = self.actions(ORDINARY, {'step': 'conflict', 'conflict_reason': 'output_changed'})
        self.assertEqual(actions, ['Resolve the changed output (new-path, review or cancel): intune-iac wizard --session '
                                   "'estate dir/session.json'"])


def render_catalog(route, parent, name, width, goal):
    """The catalog's rows for parent/name, typed from parent: built (the builders' own value), plain (after a JSON round trip) or
    cli (main(['catalog', ...]))."""
    from intune_iac import catalog, cli, entry
    from plugin_tests import test_catalog as tc

    def run():
        if route == 'cli':
            out = io.StringIO()
            argv = ['catalog', name] + (['--goal', goal] if goal else [])
            with patch('shutil.get_terminal_size', return_value=os.terminal_size((width, 40))), contextlib.redirect_stdout(out):
                assert cli.main(argv) == 0
            return out.getvalue().split('\n')
        survey = entry.survey(name, relative_to=os.getcwd())
        value = catalog.build(survey, doctor=tc.doctor(), goal=goal, relative_to=os.getcwd())
        if route == 'plain':
            value = json.loads(json.dumps(value))
        return catalog.catalog_lines(value, width)
    return in_directory(parent, run)


class DisplayTransformTests(unittest.TestCase):
    """Round 3, item 2: one display transform (readiness.placeholders_in_words) says a recorded step's command in words when it has
    a placeholder as an operand: the step's own lead, then "the <command> command, naming" and one description per placeholder from
    one table. A legend that only explained the placeholders goes; anything else in it stays; a part without a placeholder stays."""
    CAPTURE = ('Provide the read token only to this one command: intune-iac capture --tenant TENANT_ID --policy POLICY --output '
               'NEW_DIR --token-env TOKEN_VARIABLE_NAME (TENANT_ID is the tenant id the context names; POLICY is the policy id, a '
               'GUID; NEW_DIR is a folder that does not exist yet; TOKEN_VARIABLE_NAME is the name of the environment variable that '
               'holds your read token; through the environment variable that flag names; never on a command line)')

    @staticmethod
    def words(step):
        from intune_iac import readiness
        return getattr(readiness, 'placeholders_in_words', lambda text: text)(step)

    def test_a_capture_step_is_its_lead_the_command_and_what_to_name(self):
        self.assertEqual(self.words(self.CAPTURE),
                         'Provide the read token only to this one command: the capture command, naming your tenant id, the policy '
                         'id (a GUID), a new folder for the output and the name of the environment variable that holds the token '
                         '(through the environment variable that flag names; never on a command line)')

    def test_a_legend_that_only_explained_the_placeholders_goes(self):
        from intune_iac import readiness
        step = readiness.with_legend('intune-iac target authenticate --input TARGET_JSON --provider-secret-fd FD')
        self.assertIn('TARGET_JSON is', step)
        self.assertEqual(self.words('Run: ' + step),
                         'Run: the target authenticate command, naming the path of your target JSON file and a file descriptor '
                         'number your shell has open on the secret')

    def test_a_resolved_command_and_a_part_without_a_placeholder_stay_as_they_are(self):
        for step in ('Run: intune-iac doctor and pass its result, with the host report, to this check.',
                     'No action needed.',
                     "Run: intune-iac workbench workspace --root 'estate dir/store'",
                     'Review the changed output (new-path, review or cancel)',
                     'Run: intune-iac capture --tenant 11111111-1111-4111-8111-111111111111 and read the output'):
            with self.subTest(step=step):
                self.assertEqual(self.words(step), step)

    def test_the_prose_after_a_command_stays_and_follows_after_a_comma(self):
        self.assertEqual(self.words('Run: intune-iac start DIRECTORY and pass its result to this check.'),
                         'Run: the start command, naming the directory to survey, and pass its result to this check.')

    def test_every_command_of_a_step_is_read_and_a_workspace_command_too(self):
        route = ('If you rely on a pinned executable, pass it with intune-iac wizard --session SESSION --journey --repo REPOSITORY '
                 '--atmos-executable PATH --tofu-executable PATH, or intune-iac repository native --root REPOSITORY --stack STACK '
                 '--component COMPONENT --executable PATH; then run: intune-iac doctor')
        said = self.words(route)
        self.assertEqual(said, 'If you rely on a pinned executable, pass it with the wizard command, naming a session file, your '
                               'repository folder and the path of the executable, or the repository native command, naming your '
                               'repository folder, the stack name, the component name and the path of the executable; then run: '
                               'intune-iac doctor')
        entry_step = ('See the policies: intune-iac workbench repository-entry --root STORE --repo REPOSITORY '
                      '(in the workspace: :repository-entry REPOSITORY)')
        self.assertEqual(self.words(entry_step),
                         'See the policies: the workbench repository-entry command, naming your store folder and your repository '
                         'folder (in the workspace: the :repository-entry command, naming your repository folder)')

    def test_the_transform_is_stable_and_the_table_has_a_description_for_every_template(self):
        from intune_iac import entry, readiness
        table = getattr(readiness, 'TEMPLATE_WORDS', {})
        self.assertEqual(sorted(entry.FILL_IN_TEMPLATES - set(table)), [])
        for step in (self.CAPTURE, 'Run: intune-iac start DIRECTORY and pass its result to this check.'):
            once = self.words(step)
            self.assertEqual(self.words(once), once)


class GoalRowTests(unittest.TestCase):
    """Round 3, item 2: the start screen's goal block and the catalog's goal rows print the recorded steps through the transform, on
    every directory, together with the rule for a hidden one."""
    CAPTURE_FULL = ('the capture command, naming the policy id (a GUID), a new folder for the output and the name of the '
                    'environment variable that holds the token')
    CAPTURE_NO_TENANT = ('the capture command, naming your tenant id, the policy id (a GUID), a new folder for the output and the '
                         'name of the environment variable that holds the token')
    CONTACT = 'The capture command sends the token to graph.microsoft.com in GET requests only'

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.parents = {}
        for kind in ('full', 'repository'):
            parent = Path(cls.temp.name) / kind
            parent.mkdir()
            for name in (CREDENTIAL, ORDINARY):
                variant_estate(parent, name, 'repository') if kind == 'repository' else estate(parent, name)
            cls.parents[kind] = str(parent)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_the_start_screens_goal_block_says_the_capture_command_in_words(self):
        for kind, capture in (('full', self.CAPTURE_FULL), ('repository', self.CAPTURE_NO_TENANT)):
            for name in (ORDINARY, CREDENTIAL):
                for route in ('built', 'plain', 'cli'):
                    with self.subTest(kind=kind, name=name == ORDINARY, route=route):
                        text = flat(render(route, self.parents[kind], name, 100, 'discover'))
                        self.assertIn(capture, text)
                        self.assertIn(self.CONTACT, text)                          # the sentence about the token stays
                        self.assertNotIn('--token-env', text)
                        self.assertNotIn('TOKEN_VARIABLE_NAME', text)
                        self.assertIn('never on a command line', text)             # a legend's note is kept

    def test_a_goal_step_that_runs_start_on_the_directory_is_words_on_an_ordinary_directory_too(self):
        text = flat(render('built', self.parents['repository'], ORDINARY, 100, 'discover'))
        self.assertIn('then run: the start command, naming the directory to survey', text)
        self.assertNotIn('start DIRECTORY', text)

    def test_the_catalogs_goal_rows_say_the_recorded_commands_in_words(self):
        # the catalog prints the next action of the first row that blocks the goal: the capture command here, the start command there
        for kind, said in (('full', self.CAPTURE_FULL), ('repository', 'then run: the start command, naming the directory to survey')):
            for name in (ORDINARY, CREDENTIAL):
                for route in ('built', 'plain', 'cli'):
                    with self.subTest(kind=kind, name=name == ORDINARY, route=route):
                        text = flat(render_catalog(route, self.parents[kind], name, 100, 'discover'))
                        if kind == 'repository' and name == CREDENTIAL:    # the rule for a hidden directory says it, not the table
                            said = 'the start command with this directory (the directory cannot be shown here)'
                        self.assertIn(said, text)
                        for command in ('--token-env', 'TOKEN_VARIABLE_NAME', 'start DIRECTORY'):
                            self.assertNotIn(command, text)

    def test_the_catalogs_resume_command_with_placeholders_is_words(self):
        for name in (ORDINARY, CREDENTIAL):
            for route in ('built', 'plain', 'cli'):
                with self.subTest(name=name == ORDINARY, route=route):
                    text = flat(render_catalog(route, self.parents['repository'], name, 100, None))
                    self.assertNotIn('--tenant TENANT_ID', text)
                    if route != 'plain':
                        self.assertIn('Resume with the workbench init command, naming your store folder and your tenant id.', text)


# sha256 (first 16 hex digits) of the JSON forms, taken on 9687896 before round 3: `start --json` and `catalog --json` of the four
# fixtures, with no goal and with each goal. The machine forms keep the recorded steps, placeholders and legends included; only the
# human text says them in words. The fixture directory is written FIXTURES and this machine's own facts are made fixed first.
JSON_GOLDEN = {
    'catalog|context|-': 'c9f93c8cd71feca1',
    'catalog|context|adopt': 'eb1bdb9a1cb84212',
    'catalog|context|change': '11ea9714a191bc0c',
    'catalog|context|discover': '22c1b78cd5f3dc8b',
    'catalog|context|inspect': 'df065fd96efc04f1',
    'catalog|full|-': 'bf9ace0c91432b4b',
    'catalog|full|adopt': '0851548c2f8bdd5b',
    'catalog|full|change': '6ef296b54f96514c',
    'catalog|full|discover': 'fa727032f051aff8',
    'catalog|full|inspect': '828864452f4187c3',
    'catalog|offline|-': 'ee2e02e36caaf5e5',
    'catalog|offline|adopt': '15756c3587cd8478',
    'catalog|offline|change': '13f90cb0d18ab49e',
    'catalog|offline|discover': '5bf89ab1272a4bdb',
    'catalog|offline|inspect': '00c2570d3b15330b',
    'catalog|repository|-': '30f927594f88c20e',
    'catalog|repository|adopt': '53781916434b1965',
    'catalog|repository|change': 'e35a35ae1fa2ac33',
    'catalog|repository|discover': 'e1e16923fa9462e6',
    'catalog|repository|inspect': 'f20a046378acdc0c',
    'start|context|-': '294054ccbb2cc379',
    'start|context|adopt': '1d3159d82df1aa6d',
    'start|context|change': '86700a9353961285',
    'start|context|discover': 'f263de09ab799395',
    'start|context|inspect': 'ccd3dafa5bd2d95f',
    'start|full|-': '22a102575e422562',
    'start|full|adopt': 'befb45f7edd4302e',
    'start|full|change': '3a5c6f5c10ab045a',
    'start|full|discover': '7d518e258599f0e4',
    'start|full|inspect': '8ee589bcf2cbdeb9',
    'start|offline|-': '4b69aa90a9b2fd8c',
    'start|offline|adopt': '2825e01433a3bec5',
    'start|offline|change': '0d43a1ae8c481493',
    'start|offline|discover': 'cdd285ddcaf84d2b',
    'start|offline|inspect': '6dda309a5bdd26b1',
    'start|repository|-': '895316c63fed83eb',
    'start|repository|adopt': '095cf4592a4fba52',
    'start|repository|change': '84ce949e877760e5',
    'start|repository|discover': 'c57f2a237029c562',
    'start|repository|inspect': 'df505d92cf976103',
}


class JsonFormsUnchangedTests(unittest.TestCase):
    """Round 3, item 3: the display transform is for the text forms only."""

    def test_the_json_of_start_and_the_catalog_is_byte_for_byte_what_it_was(self):
        seen = 0
        for key, path in sorted(Fixtures.get().items()):
            for command in ('start', 'catalog'):
                for goal in GOALS:
                    argv = [command, str(path), '--json'] + (['--goal', goal] if goal else [])
                    out = io.StringIO()
                    from intune_iac import cli
                    with contextlib.redirect_stdout(out):
                        self.assertEqual(cli.main(argv), 0)
                    data = host_free(json.loads(out.getvalue().replace(str(path.parent), 'FIXTURES')))
                    seen += 1
                    with self.subTest(command=command, fixture=key, goal=goal):
                        self.assertEqual(hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16],
                                         JSON_GOLDEN['%s|%s|%s' % (command, key, goal or '-')])
        self.assertEqual(seen, len(JSON_GOLDEN))

    def test_the_json_still_records_the_commands_with_their_placeholders_and_legends(self):
        from plugin_tests.test_start_goal import Fixtures as F
        out = io.StringIO()
        from intune_iac import cli
        with contextlib.redirect_stdout(out):
            cli.main(['start', str(F.get()['full']), '--json', '--goal', 'discover'])
        text = out.getvalue()
        self.assertIn('--policy POLICY --output NEW_DIR --token-env TOKEN_VARIABLE_NAME', text)
        self.assertIn('POLICY is the policy id, a GUID', text)
        self.assertNotIn('the capture command, naming', text)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.main(['catalog', str(F.get()['repository']), '--json', '--goal', 'discover'])
        self.assertIn('intune-iac start DIRECTORY', out.getvalue())
        self.assertNotIn('the start command, naming', out.getvalue())


def template_beside_command(text):
    """The places where a printed sentence holds a template word beside the word command ("the start DIRECTORY command"), or says
    that operands are still needed without saying which: a command in words names what the person is to supply."""
    from intune_iac import entry
    names = '|'.join(sorted(getattr(entry, 'FILL_IN_TEMPLATES', STAND_INS), key=len, reverse=True))
    found = re.findall(r'(?<![A-Za-z0-9_])(?:%s)(?:[/.]\S*)?\s+command\b' % names, text)
    found += re.findall(r'\bcommand,? (?:naming )?(?:%s)\b(?![A-Za-z0-9_])' % names, text)
    return found + re.findall(r'the operands it still needs', text)


class FullSetEverywhereTests(unittest.TestCase):
    """Round 3, item 4: the reader checks the whole shared set on the whole screen, goal block and catalog rows included: every
    fixture, directory name, goal and width, through the builders, the plain data and the command line, for start and the catalog."""
    KINDS = ('empty', 'repository', 'export', 'emptystore', 'full', 'context')
    NAMES = {'credential': CREDENTIAL, 'control': 'bad' + chr(27) + 'name', 'ordinary': ORDINARY}

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.parents = {}
        for kind in cls.KINDS:
            parent = Path(cls.temp.name) / kind
            parent.mkdir()
            for name in cls.NAMES.values():
                if kind == 'full':
                    estate(parent, name)
                elif kind == 'context':
                    shutil.copytree(Fixtures.get()['context'], parent / name)
                else:
                    variant_estate(parent, name, kind)
            cls.parents[kind] = str(parent)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def sweep(self, draw):
        count = 0
        for kind in self.KINDS:
            for label, name in self.NAMES.items():
                for route in ('built', 'plain', 'cli'):
                    for width in (120, 60):
                        for goal in GOALS:
                            with self.subTest(kind=kind, name=label, route=route, width=width, goal=goal):
                                lines = draw(route, self.parents[kind], name, width, goal)
                                count += 1
                                self.assertEqual(stand_in_operands(lines), [], flat(lines))
                                self.assertEqual(template_beside_command(flat(lines)), [], flat(lines))
        self.assertEqual(count, len(self.KINDS) * len(self.NAMES) * 3 * 2 * len(GOALS))

    def test_no_row_of_the_start_screen_has_a_template_as_an_operand(self):
        self.sweep(render)

    def test_no_row_of_the_catalog_has_a_template_as_an_operand(self):
        self.sweep(render_catalog)

    def test_the_reader_does_read_the_goal_block(self):
        goal_block = ['GOAL READINESS: discover (status: unknown)',
                      '    intune-iac capture --tenant TENANT_ID --policy POLICY --output \\',
                      '        NEW_DIR --token-env TOKEN_VARIABLE_NAME']
        self.assertEqual(stand_in_operands(goal_block), ['TENANT_ID', 'POLICY', 'NEW_DIR', 'TOKEN_VARIABLE_NAME'])


class OneTransformTests(unittest.TestCase):
    """Round 4: the start screen's next steps and MISSING rows go through readiness.placeholders_in_words, the one transform; every
    operand is described from readiness.TEMPLATE_WORDS, the one table."""

    def test_a_step_that_runs_start_on_the_directory_names_what_the_directory_is(self):
        from intune_iac import entry
        self.assertEqual(entry.screen_action('Then run: intune-iac start DIRECTORY'),
                         'Then run: the start command, naming the directory to survey')
        self.assertEqual(entry.screen_action('Then run: intune-iac start DIRECTORY and pass its result.'),
                         'Then run: the start command, naming the directory to survey, and pass its result.')

    def test_a_positional_placeholder_is_described_not_left_in_the_command_name(self):
        from intune_iac import entry
        for step, said in (('Run: intune-iac repository inspect POLICY', 'Run: the repository inspect command, naming the policy id (a GUID)'),
                           ('Run: intune-iac start STORE', 'Run: the start command, naming your store folder')):
            with self.subTest(step=step):
                self.assertEqual(entry.screen_action(step), said)
                self.assertEqual(template_beside_command(entry.screen_action(step)), [])

    def test_the_steps_with_a_placeholder_by_design_are_described_from_the_one_table(self):
        from intune_iac import entry, readiness
        self.assertEqual(entry.screen_action(entry.STORE_FIRST_STEP),
                         'Create a store first: the workbench init command, naming your store folder and your tenant id')
        for text in entry.FALLBACK_STEPS:
            said = entry.screen_action(text)
            with self.subTest(text=text):
                self.assertEqual(said, readiness.placeholders_in_words(text))
                self.assertEqual(template_beside_command(said), [])

    def test_a_missing_note_goes_through_the_same_transform(self):
        from intune_iac import entry, readiness
        note = 'Run: intune-iac start DIRECTORY and pass its result to this check.'
        with tempfile.TemporaryDirectory() as parent:
            Path(parent, ORDINARY).mkdir()

            def run():
                survey = json.loads(json.dumps(entry.survey(ORDINARY, relative_to=os.getcwd())))
                survey['missing'] = [note]
                return flat(entry.start_lines(survey, 200))
            text = in_directory(parent, run)
        self.assertIn(readiness.placeholders_in_words(note), text)
        self.assertEqual(template_beside_command(text), [])

    def test_there_is_one_table_of_operand_descriptions(self):
        import ast
        from intune_iac import entry, readiness
        root = Path(__file__).resolve().parents[1] / 'intune_iac'
        tables = {}
        for module in ('entry.py', 'readiness.py', 'catalog.py'):
            for node in ast.parse((root / module).read_text(encoding='utf-8')).body:
                if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
                    keys = {key.value for key in node.value.keys if isinstance(key, ast.Constant) and isinstance(key.value, str)}
                    if len(keys & set(getattr(entry, 'FILL_IN_TEMPLATES', ()))) >= 3:
                        tables[node.targets[0].id] = module
        # the description table, and the legend wording the JSON forms record (frozen, and used only to write and to strip a legend)
        self.assertEqual(tables, {'TEMPLATE_WORDS': 'readiness.py', 'PLACEHOLDER_MEANINGS': 'readiness.py'})
        self.assertTrue(set(readiness.PLACEHOLDER_MEANINGS) <= set(readiness.TEMPLATE_WORDS))
        self.assertFalse(hasattr(entry, 'placeholder_words'))
        self.assertFalse(hasattr(entry, 'FIXED_STEP_WORDS'))
