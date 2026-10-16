"""PKG-CATALOG-6 rounds 7 and 8: the fail-closed net (readiness._fail_closed) against the real shell, not hand cases.

bash is asked what words each of about ninety thousand strings is, and the net must replace the part exactly when those words hold
the token DIRECTORY. The strings are over the letters of DIRECTORY plus x and -, a single and a double quote, a backslash, a
newline, a space, a tab, a carriage return, $, { and }; there is no ( ` < > ; | & * ? [ ~ or #, so bash can neither run, glob,
redirect nor start a comment: every command word is an unknown name, and a handler records the words of every command. bash runs
under env -i, so no variable is set (the specials $$ and $- are the exception, see CONSERVATIVE). Strings that spell DIRECTORY
with quotes, $"" $'' ${x} $x, tabs and carriage returns inserted are added, because a random string almost never holds nine letters.
"""
import itertools
import os
import random
import re
import shutil
import subprocess
import unittest

ALPHABET = ['D', 'I', 'R', 'E', 'C', 'T', 'O', 'Y', 'x', '-', "'", '"', '\\', '\n', ' ', '\t', '\r', '$', '{', '}']
NOISE = ["'", '"', '\\', '\n', ' ', '\t', '\r', '$""', "$''", '${x}', '$x', '$', '${x-', '}', '$@', '$1',
         '$?', '$#', '$0', '${0-', '${x:=', '${x=', '${x:?', '${x?', '${x:=}', '${x=}']
TOKEN = re.compile(r'(?<![A-Za-z0-9_])DIRECTORY(?![A-Za-z0-9_])')
# One bash process (env -i, no rc files, $0 empty). Each input is read up to a NUL from stdin; eval runs it with globbing off; the
# handler records the words of every command bash could not find (all of them: no name in the alphabet is a command); the status
# after eval is not 0 for a syntax or substitution error, which the main shell survives.
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
# The declared conservative classes (precision is not asked of a string in one of them; safety always is):
# - special parameters ($0-$9 $@ $* $# $? $- $$ $! and their brace forms): their values at copy time are digits, the shell's name
#   or option letters, none of which can spell DIRECTORY, and the net reads them as empty (or as their default word), which can
#   only replace more;
# - assignment expansions (${NAME=w} ${NAME:=w} ${NAME?w} ${NAME:?w}): they carry state, so the net does not model them and any
#   part holding one is replaced;
# - strings bash fails on (an unclosed quote or brace, a bad substitution): the net must still be safe on them;
# - comments (a # at the start of a word makes bash drop the rest; the grammar has no comments, the net reads the rest);
# - CONSERVATIVE is the $$ and $- part of the first class, reported separately.
SPECIAL = re.compile(r'\$[0-9@*#?$!-]|\$\{[0-9@*#?$!-]')
ASSIGNMENT = re.compile(r'\$\{[A-Za-z_0-9@*#?$!-]*:?[=?]')
CONSERVATIVE = re.compile(r'\$[$-]|\$\{[$-]')
# Targeted inputs: the special parameters and the assignment expansions alone, and one that carries state across words.
TARGETED = ['DIREC$?TORY', 'DIREC$#TORY', 'DIREC$0TORY', 'DIREC$1TORY', 'DIREC$9TORY', '${0-DIRECTORY}', '${0:-DIRECTORY}',
            '${?-DIRECTORY}', 'X ${x:=DIREC} ${x}TORY', 'X ${x=DIREC} ${x}TORY', 'X ${x:?DIRECTORY}', 'X ${x?DIRECTORY}',
            'D${x:=IRECTORY}', 'D${x=IRECTORY}', '${x:=DIRECTORY}', '${x=DIRECTORY}', 'X "${x:=DIREC}${x}TORY"',
            'DIREC${x:=}TORY', '${x:=DIREC}${x}TORY', 'X ${y:=DIR} ${y}ECTORY']


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
    generator = random.Random(20261017)
    for text in TARGETED:
        yield text
        for noise in NOISE:               # each targeted input behind and inside noise
            yield noise + text
            yield text[:4] + noise + text[4:]
    for _ in range(50000):
        yield ''.join(generator.choice(ALPHABET) for _ in range(generator.randint(1, 8)))
    for _ in range(3000):
        yield ''.join(generator.choice(ALPHABET) for _ in range(generator.randint(6, 12)))
    # DIRECTORY with noise inserted: 8000 seeded pairs of insertions, then 15000 seeded strings with 1 to 6 insertions
    word = 'DIRECTORY'
    for _ in range(8000):
        first = generator.randint(0, len(word))
        text = word[:first] + generator.choice(NOISE) + word[first:]
        at = generator.randint(0, len(text))
        yield text[:at] + generator.choice(NOISE) + text[at:]
    for _ in range(15000):
        text = word
        for _ in range(generator.randint(1, 6)):
            at = generator.randint(0, len(text))
            text = text[:at] + generator.choice(NOISE) + text[at:]
        yield text


def ask_bash(bash, inputs):
    """[(words, failed)] for each input, from one bash process run under env -i."""
    data = b''.join(text.encode('ascii') + b'\0' for text in inputs)
    run = subprocess.run([shutil.which('env'), '-i', bash, '--norc', '--noprofile', '-c', SCRIPT, ''], input=data,
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


@unittest.skipUnless(bash_available(), 'no working bash and env on this host: the differential test needs the real shell to ask')
class NetAgainstBashTests(unittest.TestCase):
    def test_safety_and_precision_of_the_net_against_bash(self):
        """Safety, exact, for every string: whenever bash's words hold DIRECTORY the net replaces the part. Precision, for every
        string outside the declared conservative classes: the net replaces only when bash reads DIRECTORY."""
        from intune_iac import readiness
        inputs = list(strings())
        results = ask_bash(bash_available(), inputs)
        self.assertEqual(len(results), len(inputs))
        safety, precision = [], []
        count = dict(positives=0, dollar_positives=0, failed=0, special=0, assignment=0, comment=0, dollar_dash=0, conservative_replaced=0)
        for text, (words, error) in zip(inputs, results):
            replaced = readiness._fail_closed(text) != text
            named = bool(TOKEN.search(' '.join(words)))
            count['positives'] += named
            count['dollar_positives'] += named and '$' in text
            if named and not replaced:
                safety.append((text, 'bash words %r, not replaced' % (words,)))
            if error:
                count['failed'] += 1
                if TOKEN.search(readiness._shell_flatten(text)) and not replaced:
                    safety.append((text, 'bash failed, token after flattening, not replaced'))
                continue
            special, assignment = bool(SPECIAL.search(text)), bool(ASSIGNMENT.search(text))
            comment = '#' in text          # the targeted $# noise can leave a # at the start of a word, where bash begins a comment
            count['special'] += special
            count['assignment'] += assignment
            count['comment'] += comment
            count['dollar_dash'] += bool(CONSERVATIVE.search(text))
            if special or assignment or comment:
                count['conservative_replaced'] += replaced and not named
                continue
            if replaced != named:
                precision.append((text, 'bash words %r, replaced %r' % (words, replaced)))
        type(self).compared = (len(inputs), count, len(safety), len(precision))
        self.assertGreater(count['positives'], 1000, 'the comparison must see bash read the token often, or it proves nothing')
        self.assertGreater(count['dollar_positives'], 200, 'and often through a $ construct')
        for name in ('failed', 'special', 'assignment', 'dollar_dash', 'conservative_replaced'):
            self.assertGreater(count[name], 20, 'the %s class is exercised' % name)
        self.assertEqual(safety[:20], [], 'safety: a stand-in bash reads would be kept')
        self.assertEqual(precision[:20], [], 'precision outside the declared classes')
        print('differential: %d strings; %s; safety violations %d; precision mismatches %d' % type(self).compared)


if __name__ == '__main__':
    unittest.main()
