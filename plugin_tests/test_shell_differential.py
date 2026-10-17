"""PKG-CATALOG-6 round 12: the rule of readiness.without_stand_in against the real shell.

The rule: a part of a recorded step is replaced when it holds a GENERATING character ($ ` ~ { } * ? [ ] ! ^ < >, with which bash can
produce text that is not in the input) or when the uppercase letters D I R E C T O R Y appear in it in order. The argument: without
generating characters bash can only delete characters (quote removal, backslash removal, comments, word splitting), so every
letter it outputs appears in the input in order, and any DIRECTORY among its words is such a subsequence. bash is asked what words
each string is, and these are asserted. Safety, exact, for every string and both invocations below: whenever bash's words hold the
token DIRECTORY, the net replaces the part. The argument itself: a string with no generating character and no such subsequence
never has DIRECTORY among bash's words. The implementation equals the contract: the net replaces exactly the strings the rule
names.

Invocations: the default one, under env -i with $0 and the positional parameters empty; and one with $0 and $1 to $9 all set to
DIRECTORY (safety only), because a parameter can hold anything at copy time. Every string is asked behind a command name X, so
that no word is a shell builtin or an assignment; the handler records the words of every command bash could not find.

The strings are random over the letters of DIRECTORY plus x, the shell's special characters (quotes, backslash, $, braces, blanks,
newline, CR) and prose characters ( ) ; and a comma; DIRECTORY with noise inserted; the letters of DIRECTORY with any characters
between them; and near misses with a letter missing. There is no backtick < > | & * ? [ or ~ in the random alphabet, so bash can
neither glob nor redirect.
"""
import random
import re
import shutil
import subprocess
import unittest

ALPHABET = ['D', 'I', 'R', 'E', 'C', 'T', 'O', 'Y', 'x', '-', "'", '"', '\\', '\n', ' ', '\t', '\r', '$', '{', '}', '(', ')', ';', ',']
NOISE = ["'", '"', '\\', '\n', ' ', '\t', '\r', '$""', "$''", '${x}', '$x', '$', '${x-', '}', '$@', '$1', '(', ')', '; ', ',',
         '$?', '$#', '$0', '${0-', '${x:=', '${x=', '${x:?', '${x?', '${x:=}', '${x=}', ' #', '\t#', '\n#', '#', '$*', '${#}']
TOKEN = re.compile(r'(?<![A-Za-z0-9_])DIRECTORY(?![A-Za-z0-9_])')
GENERATING = frozenset('$`~{}*?[]!^<>')
# One bash process (env -i, no rc files). Each input is read up to a NUL from stdin; eval runs it with globbing off; the handler
# records the words of every command bash could not find; the status after eval is not 0 for a syntax or substitution error,
# which the main shell survives.
SCRIPT = r"""
set -f
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
            'X (DIRECTORY)', 'X a, DIRECTORY; Y', "X 'a (b; c)' \"d\" DIRECTORY"]


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
    generator = random.Random(20261020)
    for text in TARGETED:
        yield text
        for noise in NOISE:
            yield noise + text
            yield text[:4] + noise + text[4:]
    for _ in range(12000):
        yield ''.join(generator.choice(ALPHABET) for _ in range(generator.randint(1, 8)))
    for _ in range(1500):
        yield ''.join(generator.choice(ALPHABET) for _ in range(generator.randint(6, 12)))
    word = 'DIRECTORY'
    for _ in range(6000):                     # DIRECTORY with noise inserted
        first = generator.randint(0, len(word))
        text = word[:first] + generator.choice(NOISE) + word[first:]
        at = generator.randint(0, len(text))
        yield text[:at] + generator.choice(NOISE) + text[at:]
    for _ in range(8000):
        text = word
        for _ in range(generator.randint(1, 6)):
            at = generator.randint(0, len(text))
            text = text[:at] + generator.choice(NOISE) + text[at:]
        yield text
    for _ in range(6000):                     # the letters in order with any characters between them
        yield ''.join(generator.choice(ALPHABET) * generator.randint(0, 1) + letter for letter in word) + generator.choice(['', ' ', ','])
    for _ in range(6000):                     # near misses: a letter missing, or two swapped, with prose characters around
        letters = list(word)
        if generator.random() < 0.5:
            del letters[generator.randrange(len(letters))]
        else:
            k = generator.randrange(len(letters) - 1)
            letters[k], letters[k + 1] = letters[k + 1], letters[k]
        yield ''.join(generator.choice(ALPHABET) * generator.randint(0, 1) + letter for letter in letters)


def ask_bash(bash, inputs, parameters=()):
    """[(words, failed)] for each input, asked behind a command name X, from one bash process run under env -i."""
    data = b''.join(('X ' + text).encode('ascii') + b'\0' for text in inputs)
    arguments = list(parameters) or ['']
    run = subprocess.run([shutil.which('env'), '-i', bash, '--norc', '--noprofile', '-c', SCRIPT, *arguments], input=data,
                         capture_output=True, timeout=1800)
    results, words = [], []
    for item in run.stdout.split(b'\0')[:-1]:
        kind, rest = item[:1], item[1:].decode('ascii')
        if kind == b'W':
            words.append(rest)
        else:
            results.append((words, rest != '0'))
            words = []
    return results


def must_replace(text):
    """The rule, written again here from the contract: some part (cut at ' && ', ' || ', ' | ', '; ') has a generating character
    or the letters of DIRECTORY in order."""
    for part in re.split(r'( && | \|\| | \| |; )', text)[::2]:
        letters = iter(part)
        if any(char in GENERATING for char in part) or all(letter in letters for letter in 'DIRECTORY'):
            return True
    return False


@unittest.skipUnless(bash_available(), 'no working bash and env on this host: the differential test needs the real shell to ask')
class RuleAgainstBashTests(unittest.TestCase):
    def test_safety_the_argument_and_the_implementation_against_bash(self):
        from intune_iac import readiness
        inputs = list(strings())
        results = ask_bash(bash_available(), inputs)
        self.assertEqual(len(results), len(inputs))
        safety, argument, contract = [], [], []
        count = dict(positives=0, dollar_positives=0, failed=0, generating=0, in_order=0, kept=0, kept_checked_by_bash=0)
        for text, (words, error) in zip(inputs, results):
            replaced = readiness.without_stand_in(text) != text
            words = words[1:]                      # the command name X
            named = bool(TOKEN.search(' '.join(words)))
            count['positives'] += named
            count['dollar_positives'] += named and '$' in text
            count['failed'] += error
            if replaced != must_replace(text):
                contract.append((text, 'replaced %r, the rule says %r' % (replaced, must_replace(text))))
            if named and not replaced:
                safety.append((text, 'bash words %r, not replaced' % (words,)))
            if any(char in GENERATING for char in text):
                count['generating'] += 1
            elif must_replace(text):
                count['in_order'] += 1
            else:
                count['kept'] += 1
                count['kept_checked_by_bash'] += not error
                if named:
                    argument.append((text, 'no generating character and no letters in order, bash words %r' % (words,)))
        # the same strings once more with $0 and $1 to $9 set to DIRECTORY: a parameter can hold anything at copy time. Only the
        # strings that can expand a parameter need asking again.
        with_parameters = [text for text in inputs if '$' in text]
        again = ask_bash(bash_available(), with_parameters, ['DIRECTORY'] * 10)
        self.assertEqual(len(again), len(with_parameters))
        parameter_positives = 0
        for text, (words, error) in zip(with_parameters, again):
            if TOKEN.search(' '.join(words[1:])):
                parameter_positives += 1
                if readiness.without_stand_in(text) == text:
                    safety.append((text, 'parameters DIRECTORY: bash words %r, not replaced' % (words,)))
        type(self).compared = (len(inputs), count, len(with_parameters), parameter_positives, len(safety), len(argument), len(contract))
        self.assertGreater(count['positives'], 1000, 'the comparison must see bash read the token often, or it proves nothing')
        self.assertGreater(count['dollar_positives'], 200, 'and often through a $ construct')
        self.assertGreater(count['kept'], 5000, 'and test the argument on many strings that the rule keeps')
        self.assertGreater(count['in_order'], 1000)
        self.assertGreater(parameter_positives, 200, 'and with the parameters set to DIRECTORY')
        self.assertEqual(safety[:20], [], 'safety: a stand-in bash reads would be kept')
        self.assertEqual(argument[:20], [], 'the argument: bash cannot read DIRECTORY out of text without them')
        self.assertEqual(contract[:20], [], 'the implementation is the rule')
        print('differential: %d strings (%d asked again with the parameters set to DIRECTORY, %d of them read as DIRECTORY); %s; '
              'safety violations %d; strings the rule keeps where bash read DIRECTORY %d; implementation differs from the rule %d' % (
                  type(self).compared[0], type(self).compared[2], type(self).compared[3], type(self).compared[1],
                  type(self).compared[4], type(self).compared[5], type(self).compared[6]))


if __name__ == '__main__':
    unittest.main()
