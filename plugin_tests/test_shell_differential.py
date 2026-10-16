"""PKG-CATALOG-6 round 7: the fail-closed net (readiness._fail_closed) against the real shell, not hand cases.

For every string over a small alphabet (the letters of DIRECTORY, a single quote, a double quote, a backslash, a newline and a
space) up to length 5, and 5000 seeded random strings of length 6 to 12, bash is asked what words the string is. The net must
replace the part exactly when those words hold the token DIRECTORY. The alphabet has no $, backtick, parenthesis, ; | & < > * ? [ {{ ~ #,
so bash can neither expand nor run anything: every command word is an unknown name, and a handler records its words.
"""
import itertools
import os
import random
import re
import shutil
import subprocess
import tempfile
import unittest

ALPHABET = ['D', 'I', 'R', 'E', 'C', 'T', 'O', 'Y', "'", '"', '\\', '\n', ' ']
TOKEN = re.compile(r'(?<![A-Za-z0-9_])DIRECTORY(?![A-Za-z0-9_])')
# One bash process. Each input is read up to a NUL; eval runs it with globbing off; the handler records the words of every
# command bash could not find (all of them, since no name in the alphabet is a command); the status after eval is 2 for a syntax
# error (an unclosed quote), which the main shell survives.
SCRIPT = r"""
set -f
command_not_found_handle() { local w; for w in "$@"; do printf 'W%s\0' "$w"; done; return 0; }
while IFS= read -r -d '' s; do
  eval "$s" 2>/dev/null
  printf 'S%s\0' "$?"
done < "$1"
"""


def bash_available():
    path = shutil.which('bash')
    if not path:
        return None
    try:
        out = subprocess.run([path, '-c', 'printf ok'], capture_output=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    return path if out.stdout == b'ok' else None


def strings():
    for length in range(6):
        for chars in itertools.product(ALPHABET, repeat=length):
            yield ''.join(chars)
    generator = random.Random(20261016)
    for _ in range(5000):
        yield ''.join(generator.choice(ALPHABET) for _ in range(generator.randint(6, 12)))
    # Strings of up to 5 or random strings of 6 to 12 letters almost never spell DIRECTORY (nine letters), so the comparison would
    # see no positive. These put the nine letters in order with noise characters (quotes, backslash, newline, space) between them:
    # every pair of insertions at every pair of places, then 20000 seeded strings with 1 to 6 insertions.
    noise = ["'", '"', '\\', '\n', ' ']
    word = 'DIRECTORY'
    for first, second in itertools.product(range(len(word) + 1), repeat=2):
        for a, b in itertools.product(noise, repeat=2):
            text = word[:first] + a + word[first:]
            at = min(second, len(text))
            yield text[:at] + b + text[at:]
    for _ in range(20000):
        text = word
        for _ in range(generator.randint(1, 6)):
            at = generator.randint(0, len(text))
            text = text[:at] + generator.choice(noise) + text[at:]
        yield text


def ask_bash(bash, inputs):
    """[(words, syntax_error)] for each input, from one bash process."""
    with tempfile.TemporaryDirectory() as temp:
        data = os.path.join(temp, 'inputs')
        script = os.path.join(temp, 'ask.sh')
        with open(data, 'wb') as handle:
            for text in inputs:
                handle.write(text.encode('ascii') + b'\0')
        with open(script, 'w', newline='\n') as handle:
            handle.write(SCRIPT)
        run = subprocess.run([bash, '--norc', '--noprofile', script, data], capture_output=True, timeout=1800,
                             env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'})
    results, words = [], []
    for item in run.stdout.split(b'\0')[:-1]:
        kind, rest = item[:1], item[1:].decode('ascii')
        if kind == b'W':
            words.append(rest)
        else:
            results.append((words, rest == '2'))
            words = []
    return results


@unittest.skipUnless(bash_available(), 'no working bash on this host: the differential test needs the real shell to ask')
class NetAgainstBashTests(unittest.TestCase):
    def test_the_net_replaces_a_part_exactly_when_bash_reads_the_token(self):
        from intune_iac import readiness
        inputs = list(strings())
        results = ask_bash(bash_available(), inputs)
        self.assertEqual(len(results), len(inputs))
        mismatches, errors, positives = [], 0, 0
        for text, (words, syntax_error) in zip(inputs, results):
            replaced = readiness._fail_closed(text) != text
            if syntax_error:
                errors += 1
                if TOKEN.search(readiness._shell_flatten(text)) and not replaced:
                    mismatches.append((text, 'syntax error, token after flattening, not replaced'))
                continue
            named = bool(TOKEN.search(' '.join(words)))
            positives += named
            if replaced != named:
                mismatches.append((text, 'bash words %r, replaced %r' % (words, replaced)))
        type(self).compared = (len(inputs), errors, positives, len(mismatches))
        self.assertGreater(positives, 1000, 'the comparison must see bash read the token often, or it proves nothing')
        self.assertEqual(mismatches[:20], [], 'compared %d strings, %d syntax errors, %d positives' % (len(inputs), errors, positives))
        print('differential: %d strings, %d syntax errors, %d read as DIRECTORY, %d mismatches' % type(self).compared)


if __name__ == '__main__':
    unittest.main()
