"""PKG-CATALOG-6 rounds 12 and 13: the rule of readiness.without_stand_in against the real shell, part by part.

The rule: a part of a recorded step (a line is cut at ' && ', ' || ', ' | ' and '; ') is replaced when it holds a GENERATING
character ($ ` ~ { } * ? [ ] ! ^ < >) or an extended-glob opener (@( or +(), with which bash can produce text that is not in its
input, or when the uppercase letters D I R E C T O R Y appear in it in order. The argument: without generating characters bash can
only delete characters (quote removal, backslash removal, comments, word splitting), so every letter it outputs appears in the input
in order, and any DIRECTORY among its words is such a subsequence. The scope: bash reading the text as written, with no user alias
or function redefining a command word (an alias is the user's own configuration, outside the guarantee), with or without extglob
and globbing.

bash is asked what words each PART is, run alone, and these are asserted for every part. The implementation's decision equals the
rule's. Safety, exact: whenever bash's words hold the token DIRECTORY, the part is replaced. The argument: a part with no generating
character and no such subsequence never has DIRECTORY among bash's words. And per line: a line is replaced exactly when one of its
parts is.

Invocations: (1) under env -i with $0 and the positional parameters empty and globbing off; (2) with $0 and $1 to $9 all set to
DIRECTORY; (3) with extglob on and globbing ON, in a temporary directory (not the product tree) that holds a directory named
DIRECTORY and the near misses DIRECTOR, IRECTORY and directory, so a glob can match a directory named DIRECTORY. Every part is
asked behind a command name X, so that no word is a builtin or an assignment; the handler records the words of every command.

The strings are random over the letters of DIRECTORY plus x, the shell's special characters (quotes, backslash, $, braces, glob
characters, blanks, newline, CR), the prose characters ( ) ; , @ +; DIRECTORY with noise inserted; the letters of DIRECTORY with any
characters between them; near misses with a letter missing; and glob patterns. There is no backtick < > | & or ~ in the random
alphabet, and no $( anywhere (a command substitution would run commands; the unit tests cover it).
"""
import os
import random
import re
import shutil
import subprocess
import tempfile
import unittest

ALPHABET = ['D', 'I', 'R', 'E', 'C', 'T', 'O', 'Y', 'x', '-', "'", '"', '\\', '\n', ' ', '\t', '\r', '$', '{', '}', '(', ')', ';', ',',
            '*', '?', '[', ']', '@', '+']
NOISE = ["'", '"', '\\', '\n', ' ', '\t', '\r', '$""', "$''", '${x}', '$x', '$', '${x-', '}', '$@', '$1', '(', ')', '; ', ',',
         '$?', '$#', '$0', '${0-', '${x:=', '${x=', '${x:?', '${x?', '${x:=}', '${x=}', ' #', '\t#', '\n#', '#', '$*', '${#}',
         '*', '?', '[', ']', '@', '+', '+(', '@(', '?(', '*(', '!(', '[D]', '*Y', '\\\n', '+\\\n(', '@\\\n(', '\\\n\\\n']
TOKEN = re.compile(r'(?<![A-Za-z0-9_])DIRECTORY(?![A-Za-z0-9_])')
GENERATING = frozenset('$`~{}*?[]!^<>')
SEPARATOR = re.compile(r'( && | \|\| | \| |; )')
# One bash process (env -i, no rc files). Each input is read up to a NUL from stdin; eval runs it; the handler records the words of
# every command bash could not find; the status after eval is not 0 for a syntax or substitution error, which the main shell
# survives. {PRELUDE} is `set -f` for the first two invocations and `shopt -s extglob` for the third.
SCRIPT = r"""
{PRELUDE}
command_not_found_handle() { local w; for w in "$@"; do printf 'W%s\0' "$w"; done; return 0; }
while IFS= read -r -d '' s; do
  if [[ $s == *'{'* || $s == *'('* ]]; then
    ( eval "$s" ) 2>/dev/null     # a bad substitution ends a non-interactive shell, so ${ and ( run in a subshell
  else
    eval "$s" 2>/dev/null
  fi
  printf 'S%s\0' "$?"
done
"""
TARGETED = ['DIREC$?TORY', 'DIREC$#TORY', 'DIREC$0TORY', 'DIREC$1TORY', '${0-DIRECTORY}', '${0:-DIRECTORY}', 'X ${x:=DIREC} ${x}TORY',
            'X ${x=DIREC} ${x}TORY', 'X ${x:?DIRECTORY}', 'D${x:=IRECTORY}', 'X "${x:=DIREC}${x}TORY"', 'X $0 $1 $@ $*', "X '$0'",
            '# DIRECTORY', 'X #DIRECTORY', 'X\t#DIRECTORY', 'X DIREC #TORY', 'DIRECTORY #', 'X a#DIRECTORY', "X '#' DIRECTORY",
            'X\n#DIRECTORY\nY', "D\t#IREC'TORY\n$*", 'DIRECTORY', "'DIRECTORY'", 'X DIRECTORY', "X 'DIREC' TORY", "X 'DIREC''TORY'",
            'X (DIRECTORY)', 'X a, DIRECTORY; Y', "X 'a (b; c)' \"d\" DIRECTORY",
            '+(Y|R|O|T|C|E|I|D)', '@(DIRECTORY)', 'D*', '?IRECTORY', 'DIRECTOR[Y]', '+(D|I|R|E|C|T|O|R|Y)', '*', 'X *', 'X ?(D)IRECTORY',
            'X !(a)', 'X @(DIRECTORY|x)', 'X +(DIRECTORY)', 'X D+(I)RECTORY', 'X [D]IRECTORY', 'X DIRECTOR?', 'X *DIRECTORY*',
            'X a@b.example', 'X 1+1', "X '+(a)'", 'X \\+(a)',
            'command echo +\\\n(Y|R|O|T|C|E|I|D)', 'X @\\\n(DIRECTORY)', 'X +\\\n(DIRECTORY)', 'X ?\\\n(D)IRECTORY', 'X *\\\n(a)',
            'X D\\\nIRECTORY', 'X DIREC\\\nTORY', 'X D\\\n*', 'X $\\\nx', 'X +\\\n\\\n(D|I|R|E|C|T|O|R|Y)']
NEIGHBOURS = ('DIRECTORY', 'DIRECTOR', 'IRECTORY', 'directory')


def bash_available():
    path = shutil.which('bash')
    env = shutil.which('env')
    if not path or not env:
        return None
    try:
        out = subprocess.run([env, '-i', path, '--norc', '--noprofile', '-c', 'printf ok'], capture_output=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    return path if out.stdout == b'ok' else None


def strings():
    """The inputs, without any holding $( : a command substitution would run commands (it is covered by the unit tests)."""
    for text in _strings():
        if '$(' not in text:
            yield text


def _strings():
    generator = random.Random(20261021)
    for text in TARGETED:
        yield text
        for noise in NOISE:
            yield noise + text
            yield text[:4] + noise + text[4:]
    for _ in range(10000):
        yield ''.join(generator.choice(ALPHABET) for _ in range(generator.randint(1, 8)))
    for _ in range(1500):
        yield ''.join(generator.choice(ALPHABET) for _ in range(generator.randint(6, 12)))
    word = 'DIRECTORY'
    for _ in range(5000):                     # DIRECTORY with noise inserted
        first = generator.randint(0, len(word))
        text = word[:first] + generator.choice(NOISE) + word[first:]
        at = generator.randint(0, len(text))
        yield text[:at] + generator.choice(NOISE) + text[at:]
    for _ in range(6000):
        text = word
        for _ in range(generator.randint(1, 6)):
            at = generator.randint(0, len(text))
            text = text[:at] + generator.choice(NOISE) + text[at:]
        yield text
    for _ in range(5000):                     # the letters in order with any characters between them
        yield ''.join(generator.choice(ALPHABET) * generator.randint(0, 1) + letter for letter in word) + generator.choice(['', ' ', ','])
    for _ in range(5000):                     # near misses: a letter missing, or two swapped, with prose characters around
        letters = list(word)
        if generator.random() < 0.5:
            del letters[generator.randrange(len(letters))]
        else:
            k = generator.randrange(len(letters) - 1)
            letters[k], letters[k + 1] = letters[k + 1], letters[k]
        yield ''.join(generator.choice(ALPHABET) * generator.randint(0, 1) + letter for letter in letters)
    for _ in range(4000):                     # glob patterns built from the names in the run directory
        name = generator.choice(NEIGHBOURS)
        pattern = ''.join(generator.choice([char, '?', '*', '[%s]' % char]) for char in name)
        yield generator.choice(['', 'X ', 'x ']) + generator.choice([pattern, '+(%s)' % '|'.join(sorted(set(name))),
                                                                       '@(%s)' % name, '*(%s)' % name[:3], '?(%s)' % name])


def ask_bash(bash, inputs, prelude, parameters=(), cwd=None):
    """[(words, failed)] for each input, asked behind a command name X, from one bash process run under env -i."""
    data = b''.join(('X ' + text).encode('ascii') + b'\0' for text in inputs)
    arguments = list(parameters) or ['']
    run = subprocess.run([shutil.which('env'), '-i', bash, '--norc', '--noprofile', '-c', SCRIPT.replace('{PRELUDE}', prelude), *arguments],
                         input=data, capture_output=True, timeout=1800, cwd=cwd)
    results, words = [], []
    for item in run.stdout.split(b'\0')[:-1]:
        kind, rest = item[:1], item[1:].decode('ascii')
        if kind == b'W':
            words.append(rest)
        else:
            results.append((words, rest != '0'))
            words = []
    return results


def parts_of(text):
    return SEPARATOR.split(text)[::2]


def part_must_be_replaced(part):
    """The rule, written again here from the contract (a backslash-newline is removed first: bash joins it before tokenizing)."""
    part = part.replace('\\\n', '')
    letters = iter(part)
    return (any(char in GENERATING for char in part) or '@(' in part or '+(' in part
            or all(letter in letters for letter in 'DIRECTORY'))


@unittest.skipUnless(bash_available(), 'no working bash and env on this host: the differential test needs the real shell to ask')
class RuleAgainstBashTests(unittest.TestCase):
    def test_safety_the_argument_and_the_implementation_against_bash_part_by_part(self):
        from intune_iac import readiness
        lines = list(strings())
        parts = sorted({part for line in lines for part in parts_of(line)})
        bash = bash_available()
        first = dict(zip(parts, ask_bash(bash, parts, 'set -f')))
        with_parameters = [part for part in parts if '$' in part]
        second = dict(zip(with_parameters, ask_bash(bash, with_parameters, 'set -f', ['DIRECTORY'] * 10)))
        globbing = [part for part in parts if any(char in part for char in '*?[(')]
        with tempfile.TemporaryDirectory() as run_directory:
            for name in NEIGHBOURS:
                os.mkdir(os.path.join(run_directory, name))
            third = dict(zip(globbing, ask_bash(bash, globbing, 'shopt -s extglob', cwd=run_directory)))
        self.assertEqual((len(first), len(second), len(third)), (len(parts), len(with_parameters), len(globbing)))
        safety, argument, contract = [], [], []
        count = dict(lines=len(lines), parts=len(parts), second=len(second), third=len(third), positives=0, dollar_positives=0,
                     parameter_positives=0, glob_positives=0, failed=0, replaced=0, kept=0, in_order=0, generating=0)
        for part in parts:
            replaced = readiness.without_stand_in(part) != part
            expected = part_must_be_replaced(part)
            if replaced != expected:
                contract.append((part, 'replaced %r, the rule says %r' % (replaced, expected)))
            count['replaced'] += replaced
            count['generating'] += any(char in GENERATING for char in part)
            count['in_order'] += expected and not any(char in GENERATING for char in part)
            count['kept'] += not expected
            words, error = first[part]
            named = bool(TOKEN.search(' '.join(words[1:])))
            count['positives'] += named
            count['dollar_positives'] += named and '$' in part
            count['failed'] += error
            if named and not replaced:
                safety.append((part, 'default: bash words %r, not replaced' % (words,)))
            if not expected and named:
                argument.append((part, 'default: no generating character, no letters in order, bash words %r' % (words,)))
            if part in second and TOKEN.search(' '.join(second[part][0][1:])):
                count['parameter_positives'] += 1
                if not replaced:
                    safety.append((part, 'parameters DIRECTORY: not replaced'))
            if part in third and TOKEN.search(' '.join(third[part][0][1:])):
                count['glob_positives'] += 1
                if not replaced:
                    safety.append((part, 'extglob and globbing: bash words %r, not replaced' % (third[part][0],)))
                if not expected:
                    argument.append((part, 'extglob: no generating character, no letters in order, bash words %r' % (third[part][0],)))
        for line in lines:       # a line is replaced exactly when one of its parts is
            if (readiness.without_stand_in(line) != line) != any(part_must_be_replaced(part) for part in parts_of(line)):
                contract.append((line, 'the line decision differs from its parts'))
        type(self).compared = (count, len(safety), len(argument), len(contract))
        self.assertGreater(count['positives'], 1000, 'the comparison must see bash read the token often, or it proves nothing')
        self.assertGreater(count['dollar_positives'], 200, 'and often through a $ construct')
        self.assertGreater(count['kept'], 3000,'and test the argument on many parts that the rule keeps')
        self.assertGreater(count['in_order'], 1000)
        self.assertGreater(count['parameter_positives'], 200, 'and with the parameters set to DIRECTORY')
        self.assertGreater(count['glob_positives'], 100, 'and with extglob on and globbing matching a directory named DIRECTORY')
        self.assertEqual(safety[:20], [], 'safety: a stand-in bash reads would be kept')
        self.assertEqual(argument[:20], [], 'the argument: bash cannot read DIRECTORY out of text without them')
        self.assertEqual(contract[:20], [], 'the implementation is the rule')
        print('differential: %s; safety violations %d; kept parts where bash read DIRECTORY %d; rule differences %d' % type(self).compared)


if __name__ == '__main__':
    unittest.main()
