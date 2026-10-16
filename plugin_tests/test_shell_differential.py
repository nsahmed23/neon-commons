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
NOISE = ["'", '"', '\\', '\n', ' ', '\t', '\r', '$""', "$''", '${x}', '$x', '$', '${x-', '}', '$@', '$1']
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
# The values of $$ and $- are not empty in bash (a process id, the option letters), and the net reads them as empty, which can only
# make it replace more. A string with one of them may be replaced without bash reading the token; nothing else may differ.
CONSERVATIVE = re.compile(r'\$[$-]|\$\{[$-]')


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
    def test_the_net_replaces_a_part_exactly_when_bash_reads_the_token(self):
        from intune_iac import readiness
        inputs = list(strings())
        results = ask_bash(bash_available(), inputs)
        self.assertEqual(len(results), len(inputs))
        mismatches, failed, positives, dollar_positives, conservative = [], 0, 0, 0, 0
        for text, (words, error) in zip(inputs, results):
            replaced = readiness._fail_closed(text) != text
            if error:
                failed += 1
                if TOKEN.search(readiness._shell_flatten(text)) and not replaced:
                    mismatches.append((text, 'bash failed, token after flattening, not replaced'))
                continue
            named = bool(TOKEN.search(' '.join(words)))
            positives += named
            dollar_positives += named and '$' in text
            if replaced and not named and CONSERVATIVE.search(text):
                conservative += 1
                continue
            if replaced != named:
                mismatches.append((text, 'bash words %r, replaced %r' % (words, replaced)))
        type(self).compared = (len(inputs), failed, positives, dollar_positives, conservative, len(mismatches))
        self.assertGreater(positives, 1000, 'the comparison must see bash read the token often, or it proves nothing')
        self.assertGreater(dollar_positives, 200, 'and often through a $ construct')
        self.assertEqual(mismatches[:20], [], 'compared %d strings' % len(inputs))
        print('differential: %d strings, %d bash failures, %d read as DIRECTORY, %d of them through $, %d conservative, '
              '%d mismatches' % type(self).compared)


if __name__ == '__main__':
    unittest.main()
