"""PKG-CATALOG-6 rounds 7 to 10: the fail-closed net (readiness._fail_closed) against the real shell, not hand cases.

bash is asked what words each of about fifty thousand strings is. Two properties are asserted.

Safety, exact, for every string and for both invocations below: whenever bash's words hold the token DIRECTORY, the net replaces
the part. Precision, for every string outside the declared classes: the net replaces only when bash reads DIRECTORY.

The classes are the same as in the docstring of readiness.without_stand_in. Fail-closed classes, where the net replaces the part
whatever it holds: ACTIVE special parameters, ACTIVE assignment expansions, and command substitution (not in the shell run, which
cannot contain a parenthesis or a backtick; the unit tests in test_catalog_commands cover it). Conservative classes, where the
net may replace more: comments (not in the producers' grammar) and text bash fails on. A class is labelled from what bash does,
by a small scanner of quotes, escapes and word starts (classify): an expansion inside single or ANSI-C quotes is not active, and
a # counts as a comment only at the start of a word.

Invocations: the default one, under env -i with $0 and the positional parameters empty; and one with $0 and $1 to $9 all set to
DIRECTORY (safety only), because a parameter can hold anything at copy time.

The strings are over the letters of DIRECTORY plus x and -, quotes, backslash, newline, space, tab, carriage return, $, { and }, and
spell DIRECTORY with noise inserted ($"" $'' ${x} $x, parameters, assignments, comments), because a random string almost never holds
nine letters. There is no ( ` < > ; | & * ? [ or ~, so bash can neither run, glob nor redirect: every command word is an unknown
name, and a handler records the words of every command.
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
         '$?', '$#', '$0', '${0-', '${x:=', '${x=', '${x:?', '${x?', '${x:=}', '${x=}', ' #', '\t#', '\n#', '#', '$*', '${#}']
TOKEN = re.compile(r'(?<![A-Za-z0-9_])DIRECTORY(?![A-Za-z0-9_])')
# One bash process (env -i, no rc files). Each input is read up to a NUL from stdin; eval runs it with globbing off; the handler
# records the words of every command bash could not find (all of them: no name in the alphabet is a command); the status after eval
# is not 0 for a syntax or substitution error, which the main shell survives.
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
# Targeted inputs: the special parameters, the assignment expansions and real comments alone, and ones that carry state or hide.
TARGETED = ['DIREC$?TORY', 'DIREC$#TORY', 'DIREC$0TORY', 'DIREC$1TORY', 'DIREC$9TORY', '${0-DIRECTORY}', '${0:-DIRECTORY}',
            '${?-DIRECTORY}', 'X ${x:=DIREC} ${x}TORY', 'X ${x=DIREC} ${x}TORY', 'X ${x:?DIRECTORY}', 'X ${x?DIRECTORY}',
            'D${x:=IRECTORY}', 'D${x=IRECTORY}', '${x:=DIRECTORY}', '${x=DIRECTORY}', 'X "${x:=DIREC}${x}TORY"',
            'DIREC${x:=}TORY', '${x:=DIREC}${x}TORY', 'X ${y:=DIR} ${y}ECTORY',
            '$0', '$1', '"$@"', '$*', 'X $0 $1 $@ $*', 'X "$0"', 'X ${0}', 'X ${1}', 'X ${@}', "X '$0'", "X $'$0'", 'X \\$0',
            '# DIRECTORY', 'X #DIRECTORY', 'X\t#DIRECTORY', 'X DIREC #TORY', "X 'a' #DIRECTORY", 'DIRECTORY #', 'X DIRECTORY # Y',
            'X a#DIRECTORY', 'X \\#DIRECTORY', "X '#' DIRECTORY", 'X\n#DIRECTORY\nY']


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
    generator = random.Random(20261018)
    for text in TARGETED:
        yield text
        for noise in NOISE:               # each targeted input behind and inside noise
            yield noise + text
            yield text[:4] + noise + text[4:]
    for _ in range(25000):
        yield ''.join(generator.choice(ALPHABET) for _ in range(generator.randint(1, 8)))
    for _ in range(3000):
        yield ''.join(generator.choice(ALPHABET) for _ in range(generator.randint(6, 12)))
    # DIRECTORY with noise inserted: seeded pairs of insertions, then seeded strings with 1 to 6 insertions
    word = 'DIRECTORY'
    for _ in range(6000):
        first = generator.randint(0, len(word))
        text = word[:first] + generator.choice(NOISE) + word[first:]
        at = generator.randint(0, len(text))
        yield text[:at] + generator.choice(NOISE) + text[at:]
    for _ in range(12000):
        text = word
        for _ in range(generator.randint(1, 6)):
            at = generator.randint(0, len(text))
            text = text[:at] + generator.choice(NOISE) + text[at:]
        yield text


SPECIALS = '@*#?$!-0123456789'


def brace_end(text, start):
    """The index of the } closing a ${ whose content begins at start (nested ${ counted, quotes and escapes skipped), or -1."""
    depth, k = 1, start
    while k < len(text):
        char = text[k]
        if char == '\\':
            k += 2
            continue
        if char in '\'"':
            end = k + 1
            while end < len(text) and text[end] != char:
                end += 2 if (char == '"' and text[end] == '\\') else 1
            if end >= len(text):
                return -1
            k = end
        elif char == '$' and text[k + 1:k + 2] == '{':
            depth += 1
            k += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                return k
        k += 1
    return -1


def classify(text, word_start=True):
    """The classes bash's own reading puts a string in: {'special', 'assignment', 'comment'}. An expansion is active outside single
    and ANSI-C quotes (and inside double quotes); a # starts a comment only at the start of a word, which ends the scan."""
    found, i, n, state = set(), 0, len(text), None
    while i < n:
        char = text[i]
        if state == "'":
            state = None if char == "'" else state
            i += 1
        elif state == '$':                      # $'..'
            if char == '\\':
                i += 2
                continue
            state = None if char == "'" else state
            i += 1
        else:
            if state == '"' and char == '"':
                state, i = None, i + 1
                continue
            if char == '\\':
                i += 2
                word_start = False
                continue
            if state is None and char == "'":
                state, i, word_start = "'", i + 1, False
                continue
            if state is None and char == '"':
                state, i, word_start = '"', i + 1, False
                continue
            if char == '$' and state is None and text[i + 1:i + 2] == "'":
                state, i, word_start = '$', i + 2, False
                continue
            if char == '$' and state is None and text[i + 1:i + 2] == '"':
                state, i, word_start = '"', i + 2, False
                continue
            if char == '$':
                following = text[i + 1:i + 2]
                if following and following in SPECIALS:
                    found.add('special')
                    i += 2
                elif following == '{':
                    close = brace_end(text, i + 2)
                    content = text[i + 2:close] if close != -1 else text[i + 2:]
                    if content[:1] and content[0] in SPECIALS:
                        found.add('special')
                    elif re.match(r'[A-Za-z_][A-Za-z0-9_]*:?[=?]', content):
                        found.add('assignment')
                    else:
                        default = re.match(r'[A-Za-z_][A-Za-z0-9_]*:?-', content)
                        if default:          # the default word of an unset name is expanded: its expansions are active
                            found |= classify(content[default.end():], word_start=False) - {'comment'}
                    i = (close + 1) if close != -1 else n
                else:
                    i += 1
                word_start = False
                continue
            if char == '#' and state is None and word_start:
                found.add('comment')
                break
            word_start = state is None and char in ' \t\n'
            i += 1
    return found


def ask_bash(bash, inputs, parameters=()):
    """[(words, failed)] for each input, from one bash process run under env -i. parameters are $0, $1, ... for the run."""
    data = b''.join(text.encode('ascii') + b'\0' for text in inputs)
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


@unittest.skipUnless(bash_available(), 'no working bash and env on this host: the differential test needs the real shell to ask')
class NetAgainstBashTests(unittest.TestCase):
    def test_classify_labels_what_bash_does_not_raw_characters(self):
        for text, expected in (
                ('X $?', {'special'}), ("X '$?'", set()), ("X $'$?'", set()), ('X "$?"', {'special'}), ('X \\$?', set()),
                ('X ${0-a}', {'special'}), ('X ${x:=a}', {'assignment'}), ("X '${x:=a}'", set()), ('X ${x-a}', set()),
                ('X $#', {'special'}), ('X #a', {'comment'}), ('X a#b', set()), ('X\t#a', {'comment'}), ('X $# #a', {'special', 'comment'}),
                ('X \\#a', set()), ("X '#a'", set()), ('X "#a"', set()), ('# a', {'comment'}), ('X ${#}', {'special'}),
                ('X #a $?', {'comment'})):
            self.assertEqual(classify(text), expected, text)

    def test_safety_and_precision_of_the_net_against_bash(self):
        """Safety, exact, for every string: whenever bash's words hold DIRECTORY the net replaces the part. Precision, for every
        string outside the declared classes: the net replaces only when bash reads DIRECTORY."""
        from intune_iac import readiness
        inputs = list(strings())
        results = ask_bash(bash_available(), inputs)
        self.assertEqual(len(results), len(inputs))
        safety, precision = [], []
        count = dict(positives=0, dollar_positives=0, failed=0, special=0, assignment=0, comment=0, replaced_in_a_class=0,
                     precision_checked=0)
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
            classes = classify(text)
            for name in classes:
                count[name] += 1
            if classes:
                count['replaced_in_a_class'] += replaced and not named
                continue
            count['precision_checked'] += 1
            if replaced != named:
                precision.append((text, 'bash words %r, replaced %r' % (words, replaced)))
        # the same strings once more with $0 and $1 to $9 set to DIRECTORY: a parameter can hold anything at copy time. Only the
        # strings that can expand a parameter need asking again.
        with_parameters = [text for text in inputs if '$' in text]
        again = ask_bash(bash_available(), with_parameters, ['DIRECTORY'] * 10)
        self.assertEqual(len(again), len(with_parameters))
        parameter_positives = 0
        for text, (words, error) in zip(with_parameters, again):
            replaced = readiness._fail_closed(text) != text
            if TOKEN.search(' '.join(words)):
                parameter_positives += 1
                if not replaced:
                    safety.append((text, 'parameters DIRECTORY: bash words %r, not replaced' % (words,)))
        type(self).compared = (len(inputs), count, len(with_parameters), parameter_positives, len(safety), len(precision))
        self.assertGreater(count['positives'], 1000, 'the comparison must see bash read the token often, or it proves nothing')
        self.assertGreater(count['dollar_positives'], 200, 'and often through a $ construct')
        self.assertGreater(parameter_positives, 500, 'and with the parameters set to DIRECTORY')
        for name in ('failed', 'special', 'assignment', 'comment'):
            self.assertGreater(count[name], 20, 'the %s class is exercised' % name)
        self.assertEqual(safety[:20], [], 'safety: a stand-in bash reads would be kept')
        self.assertEqual(precision[:20], [], 'precision outside the declared classes')
        print('differential: %d strings (%d asked again with the parameters set to DIRECTORY, %d of them read as DIRECTORY); %s; '
              'safety violations %d; precision mismatches %d' % (type(self).compared[0], type(self).compared[2],
                                                                type(self).compared[3], type(self).compared[1],
                                                                type(self).compared[4], type(self).compared[5]))


if __name__ == '__main__':
    unittest.main()
