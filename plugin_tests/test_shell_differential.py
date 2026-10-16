"""PKG-CATALOG-6 round 11: the allowlist (readiness.without_stand_in) against the real shell.

The net reads text by a grammar, not by a shell parser: SIMPLE text is words of [A-Za-z0-9_./:,-] or single-quoted strings of those
and spaces, separated by spaces; anything else is always replaced. bash is asked what words each string is, and three properties are
asserted. Safety, exact, for every string and for both invocations below: whenever bash's words hold the token DIRECTORY, the net
replaces the part. Exactness for simple strings: the trivial reading (strip the single quotes, split on spaces) equals bash's words,
and the net replaces exactly when they hold the token. Fail closed for the rest: a string that is not simple is always replaced.

Invocations: the default one, under env -i with $0 and the positional parameters empty; and one with $0 and $1 to $9 all set to
DIRECTORY (safety only), because a parameter can hold anything at copy time. Every string is asked behind a command name X, so
that no word is a shell builtin or an assignment; the handler records the words of every command bash could not find.

The strings are random over the letters of DIRECTORY plus x and the shell's special characters (quotes, backslash, $, braces, blanks,
newline, CR), random over the simple characters, and DIRECTORY with noise inserted ($"" $'' ${x} $x, parameters, assignments,
comments, quotes, blanks). There is no ( ` < > ; | & * ? [ or ~, so bash can neither run, glob nor redirect.
"""
import random
import re
import shutil
import subprocess
import unittest

ALPHABET = ['D', 'I', 'R', 'E', 'C', 'T', 'O', 'Y', 'x', '-', "'", '"', '\\', '\n', ' ', '\t', '\r', '$', '{', '}']
SIMPLE_ALPHABET = ['D', 'I', 'R', 'E', 'C', 'T', 'O', 'Y', 'x', '-', '.', '/', ':', ',', '_', ' ', ' ', "'", "'"]
NOISE = ["'", '"', '\\', '\n', ' ', '\t', '\r', '$""', "$''", '${x}', '$x', '$', '${x-', '}', '$@', '$1',
         '$?', '$#', '$0', '${0-', '${x:=', '${x=', '${x:?', '${x?', '${x:=}', '${x=}', ' #', '\t#', '\n#', '#', '$*', '${#}']
SIMPLE_NOISE = [' ', "'", '-', '.', '/', ':', ',', '_', 'x', "' '"]
TOKEN = re.compile(r'(?<![A-Za-z0-9_])DIRECTORY(?![A-Za-z0-9_])')
# The allowlist, written again here from the contract (not imported from the code under test).
SIMPLE_WORD = r"(?:[A-Za-z0-9_./:,-]|'[A-Za-z0-9_./:, -]*')+"
SIMPLE = re.compile(r' *(?:%s(?: +%s)*)? *' % (SIMPLE_WORD, SIMPLE_WORD))
# One bash process (env -i, no rc files). Each input is read up to a NUL from stdin; eval runs it with globbing off; the handler
# records the words of every command bash could not find; the status after eval is not 0 for a syntax or substitution error,
# which the main shell survives.
SCRIPT = r"""
set -f
command_not_found_handle() { local w; for w in "$@"; do printf 'W%s\0' "$w"; done; return 0; }
while IFS= read -r -d '' s; do
  if [[ $s == *'{'* ]]; then
    ( eval "$s" ) 2>/dev/null     # a bad substitution ends a non-interactive shell, so ${ runs in a subshell
  else
    eval "$s" 2>/dev/null
  fi
  printf 'S%s\0' "$?"
done
"""
TARGETED = ['DIREC$?TORY', 'DIREC$#TORY', 'DIREC$0TORY', 'DIREC$1TORY', '${0-DIRECTORY}', '${0:-DIRECTORY}', 'X ${x:=DIREC} ${x}TORY',
            'X ${x=DIREC} ${x}TORY', 'X ${x:?DIRECTORY}', 'D${x:=IRECTORY}', 'X "${x:=DIREC}${x}TORY"', 'X $0 $1 $@ $*', "X '$0'",
            '# DIRECTORY', 'X #DIRECTORY', 'X\t#DIRECTORY', 'X DIREC #TORY', 'DIRECTORY #', 'X a#DIRECTORY', "X '#' DIRECTORY",
            'X\n#DIRECTORY\nY', "D\t#IREC'TORY\n$*", 'DIRECTORY', "'DIRECTORY'", 'X DIRECTORY', "X 'DIREC' TORY", "X 'DIREC''TORY'"]


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
    generator = random.Random(20261019)
    for text in TARGETED:
        yield text
        for noise in NOISE:
            yield noise + text
            yield text[:4] + noise + text[4:]
    for _ in range(12000):
        yield ''.join(generator.choice(ALPHABET) for _ in range(generator.randint(1, 8)))
    for _ in range(1500):
        yield ''.join(generator.choice(ALPHABET) for _ in range(generator.randint(6, 12)))
    for _ in range(10000):                    # random over the simple characters
        yield ''.join(generator.choice(SIMPLE_ALPHABET) for _ in range(generator.randint(1, 14)))
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
    cores = ['DIRECTORY', "'DIRECTORY'", "DIREC''TORY", "'DIREC'TORY", "'a DIRECTORY b'", 'DIRECTORY/x', 'x/DIRECTORY', 'DIRECTORY.',
             'DIRECTORY,', 'DIRECTORYx', 'xDIRECTORY', "'DIRECTORY x'"]
    for _ in range(8000):                     # DIRECTORY (whole, quoted or broken) between simple text: mostly simple, many with the token
        around = [''.join(generator.choice(SIMPLE_ALPHABET) for _ in range(generator.randint(0, 5))) for _ in range(2)]
        yield around[0] + generator.choice(cores) + around[1]


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


def squeeze(text):
    return ' '.join(text.split())


@unittest.skipUnless(bash_available(), 'no working bash and env on this host: the differential test needs the real shell to ask')
class AllowlistAgainstBashTests(unittest.TestCase):
    def test_safety_exactness_for_simple_text_and_fail_closed_for_the_rest(self):
        from intune_iac import readiness
        inputs = list(strings())
        results = ask_bash(bash_available(), inputs)
        self.assertEqual(len(results), len(inputs))
        safety, exactness, open_ones = [], [], []
        count = dict(simple=0, simple_with_token=0, non_simple=0, positives=0, dollar_positives=0, failed=0)
        for text, (words, error) in zip(inputs, results):
            replaced = readiness.without_stand_in(text) != text
            words = words[1:]                      # the command name X
            named = bool(TOKEN.search(' '.join(words)))
            count['positives'] += named
            count['dollar_positives'] += named and '$' in text
            count['failed'] += error
            if named and not replaced:
                safety.append((text, 'bash words %r, not replaced' % (words,)))
            if SIMPLE.fullmatch(text):
                count['simple'] += 1
                trivial = squeeze(text.replace("'", ''))
                if squeeze(' '.join(words)) != trivial:
                    exactness.append((text, 'bash words %r, trivial reading %r' % (words, trivial)))
                token = bool(TOKEN.search(trivial))
                count['simple_with_token'] += token
                if replaced != token:
                    exactness.append((text, 'token %r, replaced %r' % (token, replaced)))
            else:
                count['non_simple'] += 1
                if not replaced:
                    open_ones.append(text)
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
        type(self).compared = (len(inputs), count, len(with_parameters), parameter_positives, len(safety), len(exactness),
                               len(open_ones))
        self.assertGreater(count['positives'], 1000, 'the comparison must see bash read the token often, or it proves nothing')
        self.assertGreater(count['dollar_positives'], 200, 'and often through a $ construct')
        self.assertGreater(count['simple_with_token'], 1000, 'and often in simple text')
        self.assertGreater(count['simple'], 5000)
        self.assertGreater(count['non_simple'], 5000)
        self.assertGreater(parameter_positives, 200, 'and with the parameters set to DIRECTORY')
        self.assertEqual(safety[:20], [], 'safety: a stand-in bash reads would be kept')
        self.assertEqual(exactness[:20], [], 'simple text is read trivially, exactly as bash reads it')
        self.assertEqual(open_ones[:20], [], 'text that is not simple is always replaced')
        print('differential: %d strings (%d asked again with the parameters set to DIRECTORY, %d of them read as DIRECTORY); %s; '
              'safety violations %d; simple-text mismatches %d; non-simple not replaced %d' % (
                  type(self).compared[0], type(self).compared[2], type(self).compared[3], type(self).compared[1],
                  type(self).compared[4], type(self).compared[5], type(self).compared[6]))


if __name__ == '__main__':
    unittest.main()
