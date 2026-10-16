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


class StandInCommandSegmentTests(unittest.TestCase):
    """Round 2 (Sol, Medium): the safety must not depend on one serialized spelling. A start or catalog command whose directory
    operand a hidden directory supplies is replaced as a whole by words, however it is spelled."""

    SPELLINGS = (
        "Run: intune-iac {verb} DIRECTORY --goal discover --check-signin azure",
        "Run: intune-iac {verb} 'DIRECTORY' --goal discover --check-signin azure",
        'Run: intune-iac {verb} "DIRECTORY" --goal discover',
        'Run:   intune-iac    {verb}     DIRECTORY     --goal   discover',
        'Run: intune-iac {verb} --goal discover DIRECTORY --check-signin azure',
        'Run: intune-iac {verb} --check-signin azure --goal discover DIRECTORY',
        'Choose one tenant, then run: intune-iac {verb} DIRECTORY. Then: intune-iac capture --tenant T',
        'Run: intune-iac {verb} DIRECTORY and pass its result to this check.',
    )

    def test_no_spelling_leaves_a_copyable_stand_in(self):
        from intune_iac import readiness
        for verb in ('start', 'catalog'):
            for spelling in self.SPELLINGS:
                with self.subTest(verb=verb, spelling=spelling):
                    said = readiness.without_stand_in(spelling.format(verb=verb))
                    self.assertNotIn('DIRECTORY', said)
                    self.assertNotIn('intune-iac %s' % verb, said)
                    self.assertIn('the %s command with this directory (%s)' % (verb, CANNOT), said)

    QUOTED = (
        ("Run: intune-iac 'start' DIRECTORY --goal discover", 'start'),
        ('Run: intune-iac "catalog" DIRECTORY', 'catalog'),
        ('Run: intune-iac "start" \'DIRECTORY\' --goal discover', 'start'),
        ("Run: intune-iac start --goal 'discover' 'DIRECTORY'", 'start'),
        ('Run: intune-iac start "--goal" discover DIRECTORY', 'start'),
        ("Run: intune-iac catalog '--check-signin' azure DIRECTORY", 'catalog'),
        ("Run: 'intune-iac' start DIRECTORY", 'start'),
        ('Run: "intune-iac" \'catalog\' "DIRECTORY"', 'catalog'),
        ('Run: intune-iac start "DIRECTORY --goal discover', 'start'),           # a quote that never closes
        ("Run: intune-iac 'catalog DIRECTORY", 'catalog'),
    )
    # Round 4: a program word whose shell value is exactly intune-iac counts, however it is quoted or escaped
    PROGRAM_SPELLINGS = (
        ('Run: intune-"iac" start DIRECTORY', 'start'),
        ('Run: intune\\-iac start DIRECTORY', 'start'),
        ("Run: 'intune'-iac catalog DIRECTORY", 'catalog'),
        ('Run: "intune-iac" \'start\' "DIRECTORY"', 'start'),
        ("Run: 'intune-'\"iac\" catalog DIRECTORY", 'catalog'),
        ('Run: intu\\ne-iac start DIRECTORY', 'start'),         # the shell reads \\n as n: still the program
        ('Run: intune-"iac"x start DIRECTORY', None),           # another program: its value is not intune-iac
    )
    NO_OPERAND = (
        'Run: intune-"iac" start --goal discover',
        'Run: intune\\-iac catalog --check-signin azure',
        'Run: echo ok; intune-iac start --goal discover',
        'Run: intune-iac start "--goal" discover',
        "Run: intune-iac start '--check-signin' azure",
        "Run: intune-iac 'catalog' \"--goal\" 'discover'",
        'Run: intune-iac "start" --goal "discover"',
    )

    def test_quoting_is_read_as_the_shell_reads_it(self):
        from intune_iac import readiness
        for step, verb in self.QUOTED:
            with self.subTest(step=step):
                said = readiness.without_stand_in(step)
                self.assertNotIn('DIRECTORY', said)
                self.assertNotIn('intune-iac', said)
                self.assertIn('the %s command with this directory (%s)' % (verb, CANNOT), said)

    def test_the_program_word_is_read_as_the_shell_reads_it(self):
        from intune_iac import readiness
        for step, verb in self.PROGRAM_SPELLINGS:
            with self.subTest(step=step):
                said = readiness.without_stand_in(step)
                if verb is None:      # not our program, but it holds the stand-in: replaced whole, fail closed (round 5)
                    self.assertEqual(said, 'this step names the directory, which cannot be shown here')
                    continue
                self.assertNotIn('DIRECTORY', said)
                self.assertIn('the %s command with this directory (%s)' % (verb, CANNOT), said)

    OPERATORS = (
        ('Run: echo ok; intune-iac start DIRECTORY', 'Run: echo ok; the start command with this directory (%s)' % CANNOT),
        ('true && intune-iac catalog DIRECTORY --goal discover', 'true && the catalog command with this directory (%s)' % CANNOT),
        ('intune-iac start DIRECTORY && echo ok', 'the start command with this directory (%s) && echo ok' % CANNOT),
        ('intune-iac start DIRECTORY || echo no', 'the start command with this directory (%s) || echo no' % CANNOT),
        ('intune-iac start DIRECTORY | cat', 'the start command with this directory (%s) | cat' % CANNOT),
        ('intune-iac start --goal discover && intune-iac catalog DIRECTORY',
         'intune-iac start --goal discover && the catalog command with this directory (%s)' % CANNOT),
        ('intune-iac start --goal discover | intune-iac catalog DIRECTORY',
         'intune-iac start --goal discover | the catalog command with this directory (%s)' % CANNOT),
        ('intune-iac start DIRECTORY; intune-iac start --goal discover',
         'the start command with this directory (%s); intune-iac start --goal discover' % CANNOT),
    )

    def test_each_part_of_a_line_is_its_own_command(self):
        from intune_iac import readiness
        for step, expected in self.OPERATORS:
            with self.subTest(step=step):
                self.assertEqual(readiness.without_stand_in(step), expected)
        for step in ('intune-iac catalog | cat', 'echo ok; intune-iac start --goal discover || true'):
            with self.subTest(step=step):
                self.assertEqual(readiness.without_stand_in(step), step)

    def test_a_part_that_still_names_the_stand_in_is_replaced_whatever_it_is_fail_closed(self):
        """Round 5: this part is not a start or catalog command, but it holds the token DIRECTORY, so the rule fails closed on it
        (round 4 kept it unchanged); the part without the token keeps its bytes."""
        from intune_iac import readiness
        said = readiness.without_stand_in('intune-iac start --goal discover && echo DIRECTORY')
        self.assertEqual(said, 'intune-iac start --goal discover && this step names the directory, which cannot be shown here')

    # Round 6: the flattening is quote-aware. (text, what the shell reads in it, hand-worked): a part goes to words exactly when the
    # shell would read the token DIRECTORY. Single quotes keep every backslash; double quotes keep a backslash unless it escapes
    # $, a backtick, ", \ or a newline; outside quotes a backslash escapes the next character.
    SHELL_READS = (
        ("echo 'D\\IRECTORY'", False),         # single quotes: D\IRECTORY
        ('echo "D\\IRECTORY"', False),         # double quotes keep the backslash before I: D\IRECTORY
        ('echo D\\IRECTORY', True),            # unquoted: \I is I, so DIRECTORY
        ('echo "D\\\\IRECTORY"', False),       # double quotes: \\ is one backslash: D\IRECTORY
        ('echo D\\\\IRECTORY', False),         # unquoted: \\ is one backslash: D\IRECTORY
        ('echo "D\\$IRECTORY"', False),        # \$ is $: D$IRECTORY
        ('echo D"\\IRECTORY"', False),         # D then "\I" kept: D\IRECTORY
        ('echo D\\"IRECTORY', False),          # unquoted \" is a quote character: D"IRECTORY
        ('echo "DIRECT\\ORY"', False),         # DIRECT\ORY
        ("echo 'DIRECTORY'", True),
        ('echo "DIRECTORY"', True),
        ('echo D"IR"ECTORY', True),
        ("echo 'D'\\I'RECTORY'", True),        # D, \I is I, RECTORY: DIRECTORY
        ("echo 'D\\'IRECTORY", False),         # single quotes end at the second quote: D\ then IRECTORY
    )

    # Round 8: the $ class. (text, does bash read the token DIRECTORY in it, with no variable set). Worked by hand.
    DOLLARS = (
        ('echo DIREC$""TORY', True),             # $"..." is a double-quoted string: empty
        ('echo DIREC$\'\'TORY', True),            # $'..' likewise
        ('echo DIREC$xTORY', False),              # $xTORY is one name (greedy): unset, so DIREC
        ('echo DIREC${x}TORY', True),             # ${x} is empty
        ('echo D${x-IRECTORY}', True),            # ${x-w} is w when x is unset
        ('echo D${x+IRECTORY}', False),           # ${x+w} is empty when x is unset
        ('echo DIREC$@TORY', True),
        ('echo DIREC$*TORY', True),
        ('echo DIREC$1TORY', True),               # $1 is one digit: empty
        ('echo DIREC$!TORY', True),
        ('echo "DIREC$xTORY"', False),
        ('echo "DIREC${x}TORY"', True),
        ('echo "DIREC$""TORY"', False),            # inside double quotes $" is a literal $ then the quote ends: DIREC$ and TORY
        ("echo 'DIREC$xTORY'", False),             # single quotes keep the $
        ('echo DIREC\\$""TORY', False),           # \\$ is a literal $: DIREC$TORY
        ('echo "DIREC\\$x"', False),
        ('echo $', False),
        ('echo D$ IRECTORY', False),
    )
    SUBSTITUTIONS = (
        ('echo $(date)', True), ('echo `date`', True), ('echo "$(date)"', True), ('echo "`date`"', True),
        ("echo '$(date)'", False), ("echo '`date`'", False), ('echo \\`date', False), ('echo \\$(date)', False),
        ('echo $((1+1))', True),
        # Round 9: an assignment expansion carries state to later words, so any part holding one fails closed, with or without
        # the token in sight; the forms that carry no state (-, :-, +, :+) and single-quoted text are read as before.
        ('echo ${x:=DIREC} ${x}TORY', True), ('echo ${x=DIREC} ${x}TORY', True), ('echo ${x:=a}', True), ('echo ${x=a}', True),
        ('echo ${x?a}', True), ('echo ${x:?a}', True), ('echo "${x:=a}"', True), ("echo '${x:=a}'", False),
        ('echo ${x-a}', False), ('echo ${x:-a}', False), ('echo ${x+a}', False), ('echo ${x:+a}', False),
        ('echo \\${x:=a}', False),
        # Round 10: a parameter can hold anything at copy time (the shell's own name, a caller's arguments), so every ACTIVE
        # special-parameter expansion fails closed, plain or braced, bare or in double quotes, with or without the token in sight;
        # in single quotes, ANSI-C quotes or after a backslash it is inactive text.
        ('echo $0', True), ('echo $1', True), ('echo $9', True), ('echo $@', True), ('echo $*', True), ('echo $#', True),
        ('echo $?', True), ('echo $-', True), ('echo $$', True), ('echo $!', True), ('echo "$@"', True), ('echo "$0"', True),
        ('echo ${0}', True), ('echo ${1}', True), ('echo ${@}', True), ('echo ${#}', True), ('echo "${?}"', True),
        ('echo ${0-a}', True), ('echo ${#+a}', True), ("echo '$?'", False), ("echo $'$?'", False), ('echo \\$?', False),
        ("echo '${0}'", False), ('echo $x $xy $_a', False), ('echo ${x}', False),
        # a comment is not in the grammar; a word-start # hides what follows from a quote reader (an apostrophe in it, a $* after
        # its newline), so a part with one fails closed. A # inside a word, quoted or escaped is text.
        ("X #a'b\n$*", True), ('X #a', True), ('X\t#a', True), ('# a', True), ("X a#b", False), ("X '#a'", False),
        ('X "#a"', False), ('X \\#a', False), ('X ${x-#a}', False), ('X $x#a', False),
    )

    def test_dollar_constructs_are_read_as_the_shell_reads_them(self):
        from intune_iac import readiness
        generic = 'this step names the directory, which cannot be shown here'
        for text, names_it in self.DOLLARS + self.SUBSTITUTIONS:
            with self.subTest(text=text):
                said = readiness.without_stand_in(text)
                self.assertEqual(said, generic if names_it else text)

    def test_an_unquoted_backslash_newline_is_removed_as_the_shell_removes_it(self):
        """Round 7: outside quotes the shell drops a backslash followed by a newline, so DIREC, backslash, newline, TORY is DIRECTORY."""
        from intune_iac import readiness
        generic = 'this step names the directory, which cannot be shown here'
        self.assertEqual(readiness.without_stand_in('echo DIREC\\\nTORY'), generic)
        self.assertEqual(readiness.without_stand_in('echo D\\\nIRE\\\nCTORY'), generic)
        said = readiness.without_stand_in('Run: intune-iac start DIREC\\\nTORY --goal discover')
        self.assertNotIn('DIREC', said)
        self.assertIn('the start command with this directory (%s)' % CANNOT, said)
        for text in ('echo DIREC\\\\\nTORY', 'echo "DIREC\\IRECTORY"', "echo 'DIREC\\\nTORY'"):   # a backslash pair, or quoted
            self.assertEqual(readiness.without_stand_in(text), text, text)

    def test_the_net_reads_quoting_as_the_shell_does(self):
        from intune_iac import readiness
        for text, names_it in self.SHELL_READS:
            with self.subTest(text=text):
                said = readiness.without_stand_in(text)
                if names_it:
                    self.assertEqual(said, 'this step names the directory, which cannot be shown here')
                else:
                    self.assertEqual(said, text)       # byte for byte

    SPELLINGS_R5 = (
        ('Run: intune-"iac"\tstart DIRECTORY', 'start'),
        ('Run: intune-iac\tstart\tDIRECTORY', 'start'),
        ('Run: intune-iac \t start  DIRECTORY', 'start'),
        ("Run: $'intune-iac' start DIRECTORY", 'start'),
        ("Run: intune-$'iac' start DIRECTORY", 'start'),
        ("Run: $'intune'-$'iac' catalog $'DIRECTORY'", 'catalog'),
        ("Run: intune-iac $'start' DIRECTORY", 'start'),
        ("Run: intune-iac start $'DIRECTORY' --goal discover", 'start'),
    )

    def test_tabs_and_ansi_c_quoting_leave_no_stand_in(self):
        from intune_iac import readiness
        for step, verb in self.SPELLINGS_R5:
            with self.subTest(step=step):
                said = readiness.without_stand_in(step)
                self.assertNotIn('DIRECTORY', said)
                self.assertIn('the %s command with this directory (%s)' % (verb, CANNOT), said)
        for step in ("Run: $'intune-iac' start --goal discover", 'Run: intune-iac\tstart\t--goal\tdiscover'):
            with self.subTest(step=step):
                self.assertEqual(readiness.without_stand_in(step), step)

    @staticmethod
    def shell_reads(text):
        """The text as an approximate shell reads it: quote characters, backslashes and the $ of $'..' gone, blanks one space."""
        text = re.sub(r"\$(?=')", '', text)
        text = re.sub(r"""['"\\]""", '', text)
        return re.sub(r'[ \t]+', ' ', text)

    @staticmethod
    def producer_strings():
        """Every string constant in readiness.py and catalog.py that holds the word DIRECTORY (an AST walk, not a list)."""
        import ast
        found = []
        for name in ('readiness.py', 'catalog.py'):
            path = Path(__file__).resolve().parents[1] / 'intune_iac' / name
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and 'DIRECTORY' in node.value:
                    found.append(node.value)
        return sorted(set(found))

    @classmethod
    def variants(cls, text):
        """The producer string spelled every way the closed grammar allows: each word quoted four ways, blanks as tabs, behind
        another command."""
        words = text.split(' ')
        out = [text, text.replace(' ', '\t'), 'echo ok; ' + text, 'true && ' + text, text.replace(' ', ' \t '), 'x | ' + text]
        for index, word in enumerate(words):
            for wrap in ("'%s'", '"%s"', "$'%s'", None):
                said = (wrap % word) if wrap else ('\\' + word if word else word)
                out.append(' '.join(words[:index] + [said] + words[index + 1:]))
        return out

    def test_every_producer_string_with_the_stand_in_loses_it_in_every_spelling(self):
        from intune_iac import readiness
        strings = self.producer_strings()
        self.assertGreater(len(strings), 8)           # the walk found the producers (readiness.py and catalog.py)
        generated = 0
        token = re.compile(r'(?<![A-Za-z0-9_])DIRECTORY(?![A-Za-z0-9_])')
        for text in strings:
            self.assertIsNone(token.search(self.shell_reads(readiness.without_stand_in(text))), text)
            for variant in self.variants(text):
                generated += 1
                with self.subTest(variant=variant):
                    self.assertIsNone(token.search(self.shell_reads(readiness.without_stand_in(variant))), variant)
        type(self).producer_counts = (len(strings), generated)
        self.assertGreater(generated, 100)

    def test_a_quoted_option_or_option_value_is_not_a_directory_operand(self):
        from intune_iac import readiness
        for step in self.NO_OPERAND:
            with self.subTest(step=step):
                self.assertEqual(readiness.without_stand_in(step), step)

    def test_the_rest_of_the_step_survives_and_other_commands_are_untouched(self):
        from intune_iac import readiness
        said = readiness.without_stand_in('Choose one tenant, then run: intune-iac start DIRECTORY. Then: intune-iac capture --tenant T')
        self.assertTrue(said.startswith('Choose one tenant, then run: the start command with this directory'), said)
        self.assertIn('Then: intune-iac capture --tenant T', said)
        self.assertIn('.', said.split('(')[1])        # the full stop the command swallowed is back
        for untouched in ('Run: intune-iac doctor to see the host profiles', 'Run: intune-iac start --goal discover',
                          'Run: intune-iac catalog --check-signin azure', 'Run: intune-iac capture --output NEW_DIR', ''):
            self.assertEqual(readiness.without_stand_in(untouched), untouched)

    def test_the_catalog_applies_it_to_every_recorded_step_of_a_hidden_directory(self):
        from intune_iac import catalog
        for spelling in self.SPELLINGS:
            step = spelling.format(verb='start')
            goals = [{'goal': 'discover', 'next_action': step, 'blocked': {'next_action': step, 'missing': step}}]
            catalog._shown_goal_steps(goals, 'DIRECTORY', True)
            for text in (goals[0]['next_action'], goals[0]['blocked']['next_action'], goals[0]['blocked']['missing']):
                self.assertNotIn('DIRECTORY', text, spelling)


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
