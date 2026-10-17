"""PKG-TEMPLATE-WORDS, the primary guard: a rendered sweep of every human surface.

A command assembled at run time can carry a placeholder that a check of the constants never sees (signin.rerun_command builds NAME
from one constant and NEW_DIR from another; a format string introduces OBJECT_ID). So this module does not read the source. It
drives the product to every human text surface, takes the text a person would read after all formatting and concatenation, reads
the commands in it with the product's own reader (readiness.commands_in: the shell, the workbench line terminal and the wizard
prompts) and fails on any operand that entry.is_fill_in calls a template. It writes no second reader.

What it covers
  * The workspace (the visual terminal): thirteen states of a store, each driven by keys through the real engine; in each state
    every surface (1 to 9, v and the other letters), every layer and prompt (the actions layer with each action focused and staged,
    help, the catalog, the workflow map with each stage focused, the queue, the typed details, the filters, the ":" command line),
    at 120x40, 80x24, 60x20 and 40x12, every page of each. The observed-estate state is read in both rule styles at every size.
  * The command line's text routes, in process with stdout and stderr captured: start and the catalog (every fixture, goal and
    width), sign-in status and collect with the collector stubbed (every golden case, with and without --account), the workflow map
    text, the engineering view, the interrupted-session sentences, and the --help and the usage error of every route found in
    cli.parser(). Every parser leaf is classified as text (cli.main prints it through _write_text; read from main's source), a
    session (the wizard, the workspace, the line terminal) or a machine form (the JSON document); cli._write_text is wrapped to record
    the leaf each call ran for, and a text leaf that no sweep drove through cli.main fails the test.
  * The wizard, the guided workflow and the journey: every prompt handed to the person and every line printed, scripted through
    the answers a person types, with and without a repository-owned edit of the generated output.
  * simulate --format text, with the snapshot and revision documents test_sim_render_cli builds. start and catalog with
    --check-signin, with az and gh stubbed as the sign-in tests stub them (FakeClis; no real tool, no network). The views behind
    the service, adoption and adoption-plan navigation (review, status, attach, cancel, recover), with the hand-authored
    presentation fixtures of their TUI tests (the service one through plugin_tests/service_presentation_fixtures.py, which holds no
    docker import).

service-link, adoption-link, evidence-link and evidence-history (and the history of adoptions) are driven with the responses of
plugin_tests/link_presentation_fixtures.py: the rows the product's own store writes for the links and the real history of received
evidence, fed through the workspace like the others, at every size, in the summary and the typed details.

Not driven, and why: the real protected journals behind the service views. Their fixtures are
test_worker_service_r4.WorkerServiceR4Tests, test_worker_service_readback_r4 and test_worker_evidence_r4 (used by
test_workbench_service_views_r4, test_workbench_service_tui_r4.ServiceEntrypointTests and test_workbench_evidence_views_r4), which
import the pinned docker and relay of scripts/qualification_tools and build a TLS probe with /usr/bin/gcc; the real adoption
recovery plan fixture (test_worker_adoption_plan_recovery_r4) refuses the controller's standard-library links on this machine.
What a person reads is the response as the workspace draws it, which the presentation fixtures reach without any of that.
It excludes only machine forms: --json output, the non-terminal JSON document of the line terminal and the raw record layer of the
workspace (r), which shows that same JSON document.

The allowlist is the :help listing and the help legend (the synopses of workbench.HELP and of the legend's Changes and Workflow map
rows), and only on a surface that also shows the convention sentence (SYNOPSIS_CONVENTION of test_template_words): words in capitals
there are metavariables, and the sentence says so. Nothing else is allowed. Until a surface shows the sentence, its synopses fail.
An argparse usage block (the `usage:` rows of --help and of a usage error) is allowed on the same condition: only in an output that
itself shows the sentence. The sweep of every route's --help and usage error fails for each output that prints a block without it.

A second check, the independent net, does not use the reader's context rules: a form the reader misses is missed by the renderer
and by the check above alike. In every visual block of every surface, help included (a command wrapped over rows is one command; a
sentence, a blank row, a list item and a list's heading end it), a token that is a member of entry.FILL_IN_TEMPLATES, or is shaped
like a placeholder (capitals and digits with an underscore, or a bare FILE, PATH, ROOT, ID, NAME, VALUE, STAGE, FIELD, SERVICE,
REVISION, COMMIT, REPO, DIGEST, STORE, POLICY, DIRECTORY, SUBSCRIPTION, USER or ACCOUNT), after a word the product's own tables name
as a command, is a hit. The command words are the product's tables and the external programs it prints commands for (az, gh, tofu
and git today), which external_programs derives from the product's source, never from a list here. Two readings need no table, so a
program the product only prints is found too: a placeholder after a lead (run, type, use, try: `Run: kubectl apply -f MANIFEST_FILE`)
and a placeholder right after an option (`-f MANIFEST_FILE`, `--root STORE`). On the help surfaces a hit is
excused only inside a synopsis the product writes verbatim, on a surface that shows the convention sentence. Its other false
positives are the entries of NET_ALLOWED, each with its reason. Both checks are reported.
"""
import argparse
import ast
import collections
import contextlib
import copy
import functools
import inspect
import io
import json
import os
import re
import shlex
import shutil
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from plugin_tests.service_presentation_fixtures import ServiceFixtures
from plugin_tests.test_workflow_map import LayerFixture, OBJECT, TENANT, typed

try:
    from plugin_tests.test_template_words import SYNOPSIS_CONVENTION
except ImportError:                                           # pragma: no cover: the sentence the other package names
    SYNOPSIS_CONVENTION = 'words in capitals stand for values you supply'

SIZES = ((120, 40), (80, 24), (60, 20), (40, 12))
RULE_STYLES = ('unicode', 'ascii')
# Each size in one of the two rule styles (the text is the same; the rules and a few glyphs differ), so each style is read at two
# sizes; the observed-estate state is read in both styles at every size (FULL_SCHEDULE).
SCHEDULE = (((120, 40), 'unicode'), ((80, 24), 'ascii'), ((60, 20), 'unicode'), ((40, 12), 'ascii'))
FULL_SCHEDULE = tuple((size, style) for size in SIZES for style in RULE_STYLES)
ANSI = re.compile(r'\x1b\[[0-9;?]*[A-Za-z]')
MAX_PAGES = 400
WIDTHS = (120, 80, 60, 40)                                    # the command line's widths


# -- the reader: the product's own, and the judgment of its operands -------------------------------------------------------------

def _bare(word):
    """A word without the quotes, backslashes and dollar signs that only change how a shell spells it (as the reader does)."""
    return word.strip("\\'\"$")


def _strings(operand):
    """Every string of an operand: the operand itself, or each string of an (option, value) pair."""
    if operand is None:
        return []
    if isinstance(operand, str):
        return [operand]
    return [text for part in operand for text in _strings(part)]


TEMPORARY = re.compile(r'/tmp/tmp\w+|operation-[0-9a-f]{8}-[0-9a-f]{12}')


def scrubbed(text):
    """The text on one line, with the name of a temporary directory or an operation replaced by a fixed word, so one site is one
    finding in every run."""
    return TEMPORARY.sub(lambda m: '/tmp/<temp>' if m.group().startswith('/') else 'operation-<id>', ' '.join(text.split()))


def unresolved(text):
    """[(command as the reader reads it, [its unresolved operands])] for the commands readiness.commands_in finds in text."""
    from intune_iac import entry, readiness
    found = []
    for begin, end, head, items in readiness.commands_in(text):
        bad = [string for item in items for string in _strings(item) if entry.is_fill_in(_bare(string))]
        if bad:
            found.append((scrubbed(text[begin:end]), bad))
    return found


ITEM = re.compile(r'(?:\d+[.)]|[-*])\s')                      # a numbered or bulleted row starts its own item
HEADING = re.compile(r'[A-Za-z][\w -]*  \(\d+\)\Z')           # a list's heading in the typed details: its name, two spaces, its size


def starts_block(text):
    """Whether a row (stripped, not blank) begins a block of its own: a numbered or bulleted item, or the heading of a list."""
    return bool(ITEM.match(text) or HEADING.match(text))


def paragraphs(rows):
    """The rows as a person reads them: a row that ends in a backslash continues on the next, and the rows of one block are one
    line (a wrapped command is one command); a blank row, a numbered or bulleted row and a list's heading begin a block. The wrapping
    is undone and nothing else is changed."""
    blocks, held = [], []
    for row in rows:
        text = row.strip()
        if not text:
            if held:
                blocks.append(' '.join(held))
                held = []
            continue
        if held and starts_block(text):
            blocks.append(' '.join(held))
            held = []
        held.append(text[:-1].rstrip() if text.endswith('\\') else text)
    if held:
        blocks.append(' '.join(held))
    return blocks


def readable(rows):
    """The texts to read for some rows: each row alone and the blocks they form (a union: nothing is missed by joining)."""
    rows = [row.strip() for row in rows]
    return [row for row in rows if row] + paragraphs(rows)


def machine_form(text):
    """True when the text is a JSON document: a machine form, which is not read."""
    try:
        json.loads(text)
    except ValueError:
        return False
    return bool(text.strip())


# -- the independent net -----------------------------------------------------------------------------------------------------------
#
# readiness.commands_in decides where a command begins and ends, so a form it does not read is missed by the renderer and by the
# check above alike (`collect --root STORE --service-root SERVICE` is one; so is a command with a recorded word before its first
# placeholder). The net judges every row with no context rules at all. After a word the product's own tables name as a command,
# any token of the same row that is a member of entry.FILL_IN_TEMPLATES, or is shaped like a placeholder, is a hit. No command has
# to be read: the word and the token only have to share a row. It is run on every surface except the help synopsis surfaces.

# A bare word that is a placeholder whether or not the product has a template for it yet (the last four stand in the commands it
# prints for the Azure CLI: az account set --subscription SUBSCRIPTION, az logout --username NAME, az login ... USER).
BARE_PLACEHOLDERS = frozenset(('FILE', 'PATH', 'ROOT', 'ID', 'NAME', 'VALUE', 'STAGE', 'FIELD', 'SERVICE', 'REVISION', 'COMMIT',
                               'REPO', 'DIGEST', 'STORE', 'POLICY', 'DIRECTORY', 'SUBSCRIPTION', 'USER', 'ACCOUNT', 'SUBSCRIPTION_ID'))
SHAPED = re.compile(r'[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\Z')              # capitals and digits, with at least one underscore
PACKAGE = Path(__file__).resolve().parents[1] / 'intune_iac'
RUNNERS = re.compile(r'run|popen|check_output|check_call|call|spawn|exec', re.I)       # the names of calls that start a process
# A word of a row. What joins alternatives (a/b, a|b), an option to its value (--root=STORE) or sits around a word does not belong
# to it, so `back STAGE/edit FIELD VALUE/resume` is the words back, STAGE, edit, FIELD, VALUE and resume.
WORDS = re.compile(r"[^\s/|=,;()\[\]{}<>\"'`]+")


def parser_options(parser):
    """Every option string of the command line's parser, at every depth."""
    found = []
    for action in parser._actions:
        found += action.option_strings
        if isinstance(action, argparse._SubParsersAction):
            for sub in action.choices.values():
                found += parser_options(sub)
    return found


@functools.lru_cache(maxsize=1)
def package_strings():
    """Every string constant of the product's modules, docstrings aside: what a screen or a recorded step can print, and (with the
    calls) what the product runs."""
    texts = []
    for path in sorted(PACKAGE.glob('*.py')):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        docs = {id(node.body[0].value) for node in ast.walk(tree)
                if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                and node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant)}
        texts += [node.value for node in ast.walk(tree)
                  if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs]
    return tuple(texts)


@functools.lru_cache(maxsize=1)
def external_programs():
    """The programs other than its own that the product prints commands for, derived from its source and never listed here. A
    candidate is a program the product runs (the first word of a literal argv list handed to a call that starts a process:
    signin.py runs az and gh) or that its parser can be pointed at (an option --atmos-executable, --tofu-executable, --git-executable).
    It is kept when some string the product holds has the program followed by a lowercase word or an option, which is how a printed
    command reads (az login --tenant ..., az account set ..., tofu state list). A program the parser names and no string prints a
    command for (atmos, today) is not a command word; it becomes one the day a string prints it."""
    from intune_iac import cli
    candidates = set()
    for path in sorted(PACKAGE.glob('*.py')):
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if not (isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.List) and len(node.args[0].elts) >= 2):
                continue
            callee = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, 'id', '')
            first, second = node.args[0].elts[:2]
            if (RUNNERS.search(callee) and all(isinstance(item, ast.Constant) and isinstance(item.value, str) for item in (first, second))
                    and re.fullmatch(r'[a-z][a-z0-9-]*', first.value)):
                candidates.add(first.value)
    for option in parser_options(cli.parser()):
        found = re.fullmatch(r'--([a-z][a-z0-9]*)-executable', option)
        if found:
            candidates.add(found.group(1))
    texts = package_strings()
    return frozenset(program for program in candidates
                     if any(re.search(r'(?<![\w./-])%s\s+(?:--?[a-z]|[a-z][a-z-]*)' % re.escape(program), text) for text in texts))


@functools.lru_cache(maxsize=1)
def command_words():
    """Every word the product's own tables name as a command: the program, every route of the command line's parser at every depth,
    every word the line terminal and the wizard's prompts accept (readiness.dialects), and the external programs it prints commands
    for (external_programs). Matched exactly, in lower case."""
    from intune_iac import readiness
    shell, typed = readiness.dialects()
    words, pending = {readiness.PROGRAM} | set(typed) | set(external_programs()), [shell]
    while pending:
        for name, sub in pending.pop().items():
            words.add(name)
            pending.append(sub)
    return frozenset(words)


def placeholder_like(word):
    from intune_iac import entry
    return word in BARE_PLACEHOLDERS or bool(SHAPED.match(word)) or entry.is_fill_in(word)


Hit = collections.namedtuple('Hit', 'index word token previous shown exact')
# Two readings of a row that need no table of the product's: what introduces a command in a sentence (`Run: kubectl apply -f FILE`,
# `type FILE`, `Use PATH`), and an option followed by a placeholder (`--root STORE`, `-f MANIFEST_FILE`). Neither knows a program, so a
# program the product only prints (kubectl) is still found.
LEADS = frozenset(('run', 'type', 'use', 'try'))
OPTION = re.compile(r'-{1,2}[A-Za-z][\w-]*\Z')
BREAKS = re.compile(r'[\w)\]"\'][.!?]+[)\]"\']*(?=\s|\Z)')    # where a sentence ends: its last word, the full stop, the closers
PATHS = re.compile(r'(?<![\w.\-/])/[^\s()\[\]{}<>"\'`,;]+')   # an absolute path: its segments are names, not words of a command


def visual_blocks(rows):
    """The rows grouped as a person reads them, as indexes: [[index, ...], ...]. The groups are the ones `paragraphs` joins: a
    blank row, a numbered or bulleted row and a list's heading begin a block; a row that ends in a backslash continues on the next."""
    blocks, held = [], []
    for index, row in enumerate(rows):
        text = row.strip()
        if not text:
            if held:
                blocks.append(held)
                held = []
            continue
        if held and starts_block(text):
            blocks.append(held)
            held = []
        held.append(index)
    if held:
        blocks.append(held)
    return blocks


def net_scan(rows, synopses=False):
    """[Hit] for the rows of one rendered output: each placeholder-like token that has a command word before it.

    The word is carried over the rows of a visual block, so a command wrapped over rows (`Run: collect --root` and then
    `STORE --service-root SERVICE`) or continued with a backslash is one command, and a token is judged against the nearest command
    word before it wherever the wrap put that word. A sentence ends the command, wherever in a row it ends, so prose that follows it
    is not read as the command's operands; the segments of an absolute path are not words. A hit carries the row of its token
    (index), the word right before it (previous), the rows the command spans as one text (shown) and whether it lies inside a
    synopsis the product writes verbatim (exact; only looked for when `synopses` is true, which is the help surfaces that show the
    convention sentence)."""
    commands, hits = command_words(), []
    for indexes in visual_blocks(rows):
        parts = [' '.join(rows[index].split()) for index in indexes]
        parts = [part[:-1].rstrip() if part.endswith('\\') else part for part in parts]
        text, bases = '', []
        for part in parts:
            text += (' ' if text else '') + part
            bases.append(len(text) - len(part))
        spans = exact_spans(text) if synopses else ()
        last = before = origin = where = None
        for number, part in enumerate(parts):
            breaks = [found.end() for found in BREAKS.finditer(part)]
            for found in WORDS.finditer(PATHS.sub(lambda path: ' ' * len(path.group()), part)):
                while breaks and found.start() >= breaks[0]:
                    breaks.pop(0)
                    last = before = origin = where = None
                word = found.group().strip('.:!?*')
                if not word:
                    continue
                if placeholder_like(word) and (last is not None or OPTION.match(before or '')):
                    offset = bases[number] + found.start()
                    anchor, first = (last, origin) if last is not None else (before, where)
                    hits.append(Hit(indexes[number], anchor, word, before, ' '.join(parts[first:number + 1]),
                                    any(begin <= offset < end for begin, end in spans)))
                elif word in commands or word.lower() in LEADS:
                    last, origin = word, number
                before, where = word, number
            if breaks:
                last = before = origin = where = None
    return hits


def scan(row):
    """[(nearest command word before it, token, the word right before the token)] for a row: each placeholder-like token that has
    a command word before it."""
    return [(hit.word, hit.token, hit.previous) for hit in net_scan([row])]


def net_hits(row):
    """[(nearest command word before it, token)] for a row."""
    return [(command, token) for command, token, _ in scan(row)]


def usage_rows(rows):
    """The indexes of the rows of argparse usage blocks: a `usage:` row and the indented rows that continue it."""
    found, inside = set(), False
    for index, row in enumerate(rows):
        if row.lstrip().startswith('usage:'):
            inside = True
        elif not (row.strip() and row[:1].isspace()):
            inside = False
        if inside:
            found.add(index)
    return found


def shows_convention(rows):
    """True when the rows of one rendered output, read as one text (the wrapping undone), hold SYNOPSIS_CONVENTION: the sentence
    that says words in capitals stand for values to supply."""
    return SYNOPSIS_CONVENTION in ' '.join(' '.join(rows).split())


def section_rows(rows):
    """The indexes of the indented rows of each section argparse prints under a title that ends in a colon (`options:`, `positional
    arguments:`), up to the blank row that ends it."""
    found, inside = set(), False
    for index, row in enumerate(rows):
        stripped = row.strip()
        if not stripped:
            inside = False
        elif not row[:1].isspace():
            inside = stripped.endswith(':') and len(stripped.split()) <= 3 and not stripped.startswith('usage:')
        elif inside:
            found.add(index)
    return found


def first_column(row):
    """The words of the first column of an argparse option row: the option and its metavariable, before the gap that precedes the
    help text."""
    return re.match(r'\s*(.*?)(?:\s{2,}|\Z)', row).group(1).split()


def in_argparse_layout(state, rows, index, previous, token):
    """A row of an argparse usage block, or the option and metavariable of a row of one of its sections (not the help text beside
    it), in an output that also shows the convention sentence. The sentence is what turns the metavariables into a stated notation;
    without it they are unresolved operands like any other."""
    if not shows_convention(rows):
        return False
    return index in usage_rows(rows) or (index in section_rows(rows) and token in first_column(rows[index]))


def id_after_a_noun(state, rows, index, previous, token):
    """ID right after a plain lowercase word that is not a command word ("object ID", "tenant ID")."""
    return token == 'ID' and bool(previous) and previous.isalpha() and previous.islower() and previous not in command_words()


def directory_stand_in(state, rows, index, previous, token):
    """DIRECTORY printed in the place of a directory name the screen does not show, on a screen that says what it stands for: the
    sentence that defines it (readiness.DIRECTORY_NOT_SHOWN_STEM) starts with it, or the row is the label `Directory: DIRECTORY`."""
    from intune_iac.readiness import DIRECTORY_NOT_SHOWN_STEM
    row = ' '.join(rows[index].split())
    return (token == 'DIRECTORY' and DIRECTORY_NOT_SHOWN_STEM in ' '.join(' '.join(rows).split())
            and (previous == 'Directory' or bool(re.search(r'\bDIRECTORY(?: is\b|\Z)', row))))


def block_text(rows, index):
    """The text of the visual block that holds the row, its rows joined as a person reads them."""
    block = next(block for block in visual_blocks(rows) if index in block)
    return ' '.join(' '.join(rows[number].split()) for number in block)


def strip_label(state, rows, index, previous, token):
    """REPO as the strip's own label for the state of the repository (`MODE | TENANT x | POLICY y | OBS fresh | REPO current | OP`)."""
    text = block_text(rows, index)
    return token == 'REPO' and '| REPO ' in text and '| TENANT ' in text


# The net's false positives: one entry each, (name, the states it applies to or None for any, what it excuses, the reason that is not a
# defect). What an entry excuses is a function of the screen's rows, the row's index, the word before the token and the token, so an
# entry excuses only what it names and the rest of the screen is still read. There is no other allowance.
NET_ALLOWED = (
    ('argparse usage and option rows', ('help', 'usage error'), in_argparse_layout,
     "argparse writes the parser's own synopsis with each option's metavariable (--root ROOT, --service-root SERVICE_ROOT), and "
     "lists each option with its metavariable in its first column: the standard notation of a command line, generated from the "
     "parser, printed by --help or after a usage error and never as a step to copy. Its choices can even be command words "
     "({simulation,live}). It is excused only in an output that also shows the convention sentence (SYNOPSIS_CONVENTION), as a "
     "synopsis is on the help page: without the sentence a reader cannot tell a metavariable from an operand left unresolved. The "
     "description and the help text beside each option are still read."),
    ('ID after a noun', None, id_after_a_noun,
     "ID right after a plain noun is the abbreviation of identifier in a sentence ('the Intune object ID it manages', 'tenant ID'), "
     "not a placeholder. An ID that is an operand follows an option (--object ID) or a command word (select ID), and stays a hit."),
    ('directory stand-in', None, directory_stand_in,
     "A directory whose name the screen must not print (a credential shape, a control character) is named DIRECTORY, and the "
     "screen says so in a sentence that starts with the word (readiness.DIRECTORY_NOT_SHOWN_STEM) or in the label `Directory:`. The "
     "word is defined where it is shown; a command that carries it as an operand is not excused, and stays a hit."),
    ('strip label', None, strip_label,
     "The strip under the tabs names the repository state REPO (`| OBS stale (later collection incomplete) | REPO stale |`), and the "
     "help legend prints the strip as it reads now. REPO there is the label of a state, not the operand of the word collection "
     "before it, which is ordinary English there."),
)


def net_excuse(state, rows, index, previous, token):
    """The name of the allowlist entry that excuses a hit, or None."""
    for name, states, excuses, reason in NET_ALLOWED:
        if (states is None or state in states) and excuses(state, rows, index, previous, token):
            return name
    return None


# -- the allowlist: the :help listing and the help legend ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=1)
def synopsis_corpus():
    """The synopses the product itself writes: the :help listing (workbench.HELP) and the help legend's rows that give command
    syntax. A command is a synopsis when its text is part of one of them."""
    from intune_iac import workbench, workbench_screens
    parts = [entry for value in workbench.HELP.values() if isinstance(value, list) for entry in value]
    parts += [text for name, text in workbench_screens.HELP_WORDS if name in ('Changes', 'Workflow map')]
    return ' '.join(' '.join(part.split()) for part in parts)


def is_synopsis(command):
    return ' '.join(command.split()) in synopsis_corpus()


@functools.lru_cache(maxsize=1)
def synopsis_sources():
    """The two tables of synopses the product prints on its help surfaces, each entry whole and with its whitespace collapsed:
    (the entries of the :help listing, the (label, text) rows of the help legend that give command syntax)."""
    from intune_iac import workbench, workbench_screens
    listing = frozenset(' '.join(entry.split()) for value in workbench.HELP.values() if isinstance(value, list) for entry in value)
    legend = tuple((name, ' '.join(text.split())) for name, text in workbench_screens.HELP_WORDS if name in ('Changes', 'Workflow map'))
    keys = tuple(str(key).replace('_', ' ') for key, value in workbench.HELP.items() if not isinstance(value, list))
    return listing, legend, keys


LISTING_ITEM = re.compile(r'\d+\.\s+')


def exact_spans(text):
    """The character spans of the text of one visual block that are exactly a synopsis the product writes: the whole block being a
    numbered entry of the :help listing (the numbering aside; the label of the table's next key, a row that is not a list, may follow
    the last entry because the listing prints no blank row between them), or a row of the help legend (its label and its text)
    verbatim. Whatever else the block holds, however close to an entry (a word added to it, a sentence after it), lies outside every
    span, so `review OPERATION_DIR immediately` is not the entry `review OPERATION_DIR`."""
    listing, legend, keys = synopsis_sources()
    spans = []
    numbered = LISTING_ITEM.match(text)
    if numbered:
        rest = text[numbered.end():]
        ends = [len(rest)] + [rest.find(' %s ' % key) for key in keys]
        for end in ends:
            if end > 0 and rest[:end] in listing:
                spans.append((0, numbered.end() + end))
                break
    for name, words in legend:
        spans += [found.span() for found in re.finditer(re.escape(name) + ' ?' + re.escape(words), text)]
    return spans


# The only surfaces that may hold a synopsis: the help page (8, ?) and its typed listing (e). The same words on any other surface
# (the actions layer's command row, the Inspector, the Repository surface, a prompt) are an instruction, not a synopsis.
HELP_SURFACES = ('8 Help', '? Help', '? Help, typed details (e)')


# -- findings --------------------------------------------------------------------------------------------------------------------

def size_word(size):
    return '%dx%d' % size if size[1] else '%d columns' % size[0]


class Sweep:
    """What a sweep saw: the unresolved commands (where each was printed) and how many screens were read, by state and surface."""

    def __init__(self):
        self.found = collections.OrderedDict()                 # (command, operands) -> {(state, surface, size)}
        self.synopses = collections.OrderedDict()              # a synopsis printed on a surface without the convention sentence
        self.coverage = collections.Counter()                  # (state, surface, size) -> screens read
        self.net = collections.OrderedDict()                   # (command word, token) -> {'where': {...}, 'rows': {...}}
        self.excused = collections.Counter()                   # allowlist entry -> hits it excused
        self.printed = collections.Counter()                   # (state, route) -> rows a route printed (a route that prints nothing
                                                               # is not a sweep)

    def cast(self, state, surface, size, rows, convention=False):
        """The independent net over the rows of one screen, on every surface. On a help surface that shows the convention sentence
        the synopses the product writes verbatim are excused (exact_spans); nothing else on it is."""
        seen = set()
        for hit in net_scan(rows, synopses=convention and surface in HELP_SURFACES):
            if (hit.word, hit.token, hit.shown) in seen:
                continue
            seen.add((hit.word, hit.token, hit.shown))
            reason = 'exact synopsis' if hit.exact else net_excuse(state, rows, hit.index, hit.previous, hit.token)
            if reason:
                self.excused[reason] += 1
                continue
            held = self.net.setdefault((hit.word, hit.token), {'where': set(), 'rows': set()})
            held['where'].add((state, surface, size))
            held['rows'].add(scrubbed(hit.shown))

    def read(self, state, surface, size, texts, convention=False, rows=()):
        """Judge the texts of one screen. convention: the surface shows SYNOPSIS_CONVENTION (all its pages). rows: the rows as
        printed, for the net."""
        self.coverage[(state, surface, size)] += 1
        self.cast(state, surface, size, rows, convention)
        seen = set()
        for text in texts:
            for command, operands in unresolved(text):
                if (command, tuple(operands)) in seen:
                    continue
                seen.add((command, tuple(operands)))
                if surface in HELP_SURFACES and is_synopsis(command):
                    if convention:
                        continue
                    self.synopses.setdefault((command, tuple(operands)), set()).add((state, surface, size))
                else:
                    self.found.setdefault((command, tuple(operands)), set()).add((state, surface, size))

    def text(self, state, surface, size, text):
        """Judge a text a route printed (rows as printed; a JSON document is a machine form and is not read)."""
        if machine_form(text):
            self.coverage[(state, surface, size, 'machine form')] += 1
            return
        self.printed[(state, surface)] += sum(1 for row in text.split('\n') if row.strip())
        self.read(state, surface, size, readable(text.split('\n')), rows=text.split('\n'))

    def net_failures(self):
        """The net's failure lines: one per (command word, token), with the longest row it was seen in and where."""
        lines = []
        for (word, token), held in self.net.items():
            lines.append('independent net: %r after the %s %r, in the row %r' % (
                token, 'option' if OPTION.match(word) else 'command word', word, max(held['rows'], key=len)))
            places = collections.OrderedDict()
            for state, surface, size in sorted(held['where']):
                places.setdefault((surface, state), []).append(size)
            for (surface, state), sizes in places.items():
                lines.append('    on %r, in state %r, at %s' % (surface, state, ' '.join(size_word(s) for s in sizes)))
        return lines

    def failures(self):
        """The failure lines: one per command, naming every surface, state and size it was printed on."""
        lines = []
        for table, why in ((self.found, 'a command with an unresolved operand'),
                           (self.synopses, 'a synopsis on a surface without "%s"' % SYNOPSIS_CONVENTION)):
            for (command, operands), where in table.items():
                places = collections.OrderedDict()
                for state, surface, size in sorted(where):
                    places.setdefault((surface, state), []).append(size)
                lines.append('%s: %r, unresolved %s' % (why, command, list(operands)))
                for (surface, state), sizes in places.items():
                    lines.append('    on %r, in state %r, at %s' % (surface, state, ' '.join(size_word(s) for s in sizes)))
        return lines

    def count(self):
        return len(self.found) + len(self.synopses)

    def merge(self, other):
        for mine, theirs in ((self.found, other.found), (self.synopses, other.synopses)):
            for item, where in theirs.items():
                mine.setdefault(item, set()).update(where)
        for item, held in other.net.items():
            mine = self.net.setdefault(item, {'where': set(), 'rows': set()})
            mine['where'] |= held['where']
            mine['rows'] |= held['rows']
        self.coverage.update(other.coverage)
        self.excused.update(other.excused)
        return self


# -- the workspace: what a frame holds, and how to draw every page of a surface ------------------------------------------------------

def frame_rows(ws):
    ws.stdout.seek(0)
    ws.stdout.truncate()
    ws.draw()
    return [ANSI.sub('', row) for row in ws.stdout.getvalue().split('\x1b[H')[-1].replace('\x1b[J', '').split('\r\n')]


Page = collections.namedtuple('Page', 'above body below more offset')


def split_frame(rows):
    """(above the box, inside it with the side rules off, below it, whether the box says more is below it)."""
    above, body, below, phase, more = [], [], [], 0, False
    for row in rows:
        plain = row.rstrip()
        if phase == 0 and plain[:1] in ('+', '┌') and plain[-1:] in ('+', '┐'):
            phase = 1
        elif phase == 1 and plain[:1] in ('+', '└') and plain[-1:] in ('+', '┘'):
            phase, more = 2, 'more below: PgDn' in row
        elif phase == 0:
            above.append(row.strip())
        elif phase == 1:
            body.append(plain[1:-1].strip() if plain[:1] in ('|', '│') and plain[-1:] in ('|', '│') else plain.strip())
        else:
            below.append(row.strip())
    return above, body, below, more


def surface_pages(ws, size, rules):
    """Every page of the surface the workspace shows, drawn at this size as a person would page it. A clone is drawn, so the
    workspace under test keeps its own scroll, size and paging."""
    clone = copy.copy(ws)
    clone.stdout = io.StringIO()
    clone._terminal_size = lambda: size
    clone.size, clone.rules, clone.scroll, clone.page_move = size, rules, 0, 0
    clone._page_trail = list(getattr(ws, '_page_trail', []))
    pages, previous = [], None
    for _ in range(MAX_PAGES):
        rows = frame_rows(clone)
        if rows == previous:
            break
        pages.append(Page(*split_frame(rows), clone.scroll))        # the offset is read after the draw has clamped the scroll
        previous = rows
        if not pages[-1].more:
            break
        if clone.layer in ('catalog', 'workflow'):
            clone.page_move = 1                       # their paging keeps a command whole
        else:
            clone.scroll += max(1, len(pages[-1].body))
    return pages, clone.layer


def whole_body(pages):
    """The body rows of all the pages of a surface as one list, each row once. The last page of a scroll is drawn from the row
    that fills it, so it repeats the rows it shares with the page before it; the offset of each page says how many."""
    rows, end = [], 0
    for page in pages:
        rows += page.body[max(0, end - page.offset):]
        end = max(end, page.offset + len(page.body))
    return rows


def screen_texts(pages, layer):
    """The texts to read on a surface: the chrome of each page, and the body of all its pages (a command may run over a page
    boundary where the surface does not keep it whole, so the pages join; a layer that pages by commands is not joined)."""
    texts = []
    for page in pages:
        texts += readable(page.above) + readable(page.below)
    if layer in ('catalog', 'workflow'):
        for page in pages:
            texts += readable(page.body)
    else:
        texts += readable([row for page in pages for row in page.body])
    return texts


def net_rows(pages, layer):
    """The rows the net reads, in the groups screen_texts reads: the chrome above and below the box of each page, and the body (its
    pages joined, each row once, unless the layer pages by commands). A blank row ends each group, so no visual block runs over
    from one group into the next."""
    rows = []
    for page in pages:
        for row in page.above + page.below:                  # the chrome (title, tabs, strip, band, status, keys): each row is a line
            rows += [row, '']                                # of its own, so a blank row after it keeps the next from joining it
    if layer in ('catalog', 'workflow'):
        for page in pages:
            rows += page.body + ['']
    else:
        rows += whole_body(pages) + ['']
    return rows


class Look:
    """Not a key but a request: read the screen now, when every earlier key has taken effect and the engine has answered."""

    def __init__(self, label):
        self.label = label


class Feed:
    """The keys the workspace is fed, one at a time, from a generator that sees the workspace."""

    def __init__(self, ws, plan, look):
        self.generator, self.look, self.ws, self.quit = plan(ws), look, ws, False

    def read(self):
        for item in self.generator:
            if isinstance(item, Look):
                self.look(self.ws, item.label)
                continue
            return item
        if not self.quit:
            self.quit = True
            return ('text', 'q')
        return 'eof'


def key(char):
    return ('text', char)


def read_screen(sweep, ws, state, label, schedule=SCHEDULE):
    """Read the surface the workspace shows now, at every size of the schedule (in its rule style), with both checks."""
    for size, style in schedule:
        pages, layer = surface_pages(ws, size, style)
        body = ' '.join(' '.join(row for page in pages for row in page.body).split())
        sweep.read(state, label, size, screen_texts(pages, layer), SYNOPSIS_CONVENTION in body, net_rows(pages, layer))


def drive(root, service_root, plan, state, sweep, schedule=SCHEDULE):
    """Run the real engine behind a Workspace fed by plan; at every Look read the screen at every size (in its rule style)."""
    from intune_iac.workbench import run_terminal
    from intune_iac.workbench_tui import Workspace

    def look(ws, label):
        read_screen(sweep, ws, state, label, schedule)

    ws = Workspace(root, stdout=io.StringIO(), stdin=io.StringIO(), no_color=True)
    ws.rules = 'unicode'
    ws._terminal_size = lambda: (120, 40)
    ws.size = (120, 40)
    ws.key_reader = Feed(ws, plan, look)
    return run_terminal(root, service_root=service_root, input_fn=ws.input, output_fn=lambda line: None, result_fn=ws.receive)


# -- the states a store can be in, and the keys that open every surface in each -----------------------------------------------------

class Estate(LayerFixture):
    """The workflow tests' fixture (a real store, modeled service, repository copy and maintenance engine), for building a state."""

    def __init__(self):                                       # built by hand, not collected as a test (it has no test method)
        super().__init__('prepare')


# The surfaces every state is read on, by the label the failure messages use: the nine numbered surfaces, v and the other letters.
NUMBERED = ('1 Estate', '2 Inspector', '3 Relationships', '4 History', '5 Plan', '6 Execution', '7 Coverage', '8 Help', '9 Repository')
LETTERED = ('v Delivery', 'h Health', 'd Dictionary', 'i Diagnostics', 'l Lineage', 'o Estate overview', 'm Queue', 's Start')


def surfaces_plan(selected=False, operation=None, repository=None, help_surfaces=False):
    """The keys of every surface and layer for a state. selected: a policy is selected first. operation: the directory of a
    prepared operation, which is reviewed (so Plan, Execution and v have one). repository: a directory to survey with the
    :repository-entry command. help_surfaces: also read the help page and its typed details (the :help listing)."""

    def plan(ws):
        yield Look('1 Estate')
        if selected:
            yield from typed('select ' + OBJECT)
            yield Look('2 Inspector (after select)')
        if operation:
            yield from typed('review ' + shlex.quote(str(operation)))
            yield Look('5 Plan (after :review)')
        for number, name in enumerate(NUMBERED[1:] + NUMBERED[:1], 2):
            yield key(str(number if number < 10 else 1))
            yield Look(name)
        for char, name in zip('vhdilomS'.lower(), LETTERED):
            yield key(char)
            yield Look(name)
        if help_surfaces:
            yield key('?')
            yield Look('? Help')
            yield key('e')                                     # the typed details of the help page: the :help listing
            yield Look('? Help, typed details (e)')
            yield key('e')
        if selected:
            for char, name in (('2', '2 Inspector, typed details (e)'), ('9', '9 Repository, typed details (e)')):
                yield key(char)
                yield key('e')
                yield Look(name)
                yield key('e')
        yield key('2' if selected else '1')
        yield key('f')
        yield Look('f Filters')
        yield 'down'
        yield Look('f Filters, second choice')
        yield 'escape'
        yield key(':')
        yield Look(': command line (empty)')
        for char in 'review ':
            yield key(char)
        yield Look(': command line (typing)')
        yield 'escape'
        yield from typed('catalog')
        yield Look(':catalog')
        yield 'escape'
        if repository:
            yield from typed('repository-entry ' + shlex.quote(str(repository)))
            yield Look(':repository-entry (candidates)')
            yield 'down'
            yield Look(':repository-entry (second candidate)')
            yield 'enter'
            yield Look(':repository-entry (candidate staged in the command bar)')
            yield 'escape'
        if selected:
            yield key('2')
            yield key('a')
            yield Look('a Actions')
            for number in range(len(ws._actions())):
                if number:
                    yield 'down'
                yield Look('a Actions, action %d focused' % (number + 1))
                yield 'enter'
                yield Look('a Actions, action %d staged' % (number + 1))
                yield 'escape'
            yield 'escape'
            yield from typed('workflow')
            yield Look(':workflow')
            for number in range(11):
                yield 'down'
                yield Look(':workflow, stage %d focused' % (number + 2))
            yield 'escape'
    return plan


def build_observed(fx):
    return {}


def build_import(fx):
    fx.import_intent()
    return {}


def build_stale(fx):
    fx.import_intent()
    fx.edit_description('Edited in the repository.')
    return {}


def build_proposal(fx):
    fx.prepare()
    return {}


def build_approved(fx):
    fx.prepare()
    return {'operation': fx.operation}


def build_lost(fx):
    from intune_iac import maintenance
    review = fx.prepare()
    maintenance.execute(fx.operation, approve_digest=review['approval_digest'], fault='lost-response')
    return {'operation': fx.operation}


def build_queue(fx):
    from intune_iac import workbench_queue
    from intune_iac.io import write_json
    fx.import_intent()
    path = fx.root / 'review.json'
    write_json(path, {'schema_version': 'workbench-queue-review-input/1', 'tenant_id': TENANT, 'object_id': OBJECT,
                      'finding': 'ownership_unknown', 'owner': 'Endpoint operations',
                      'rationale': 'Confirm stack ownership before any proposed change.', 'review_due': '2026-11-01T12:00:00Z',
                      'exception_expiry': '2026-11-02T12:00:00Z', 'linked_proposals': []})
    workbench_queue.amend(fx.store, path, expected_prior=None)
    return {}


def build_diagnostics(fx):
    """The conditions the diagnostics screen explains at once: an unknown outcome, a stale repository, a failed collection."""
    from intune_iac import maintenance
    from intune_iac.workbench_repository import propose_from_intent, refresh_intent
    fx.import_intent()
    fx.edit_description('Edited in the repository.')
    refresh_intent(fx.store, OBJECT, 'b' * 40)
    review = propose_from_intent(fx.store.root, fx.service.root, OBJECT, fx.root / 'operation')
    maintenance.execute(fx.root / 'operation', approve_digest=review['approval_digest'], fault='lost-response')
    fx.edit_description('Edited again after the proposal.')
    fx.store.collect(fx.service, fault='deny')
    return {'operation': fx.root / 'operation'}


def entry_commit(repository, sha='c' * 40):
    git = Path(repository) / '.git'
    (git / 'refs' / 'heads').mkdir(parents=True, exist_ok=True)
    (git / 'HEAD').write_text('ref: refs/heads/main\n')
    (git / 'refs' / 'heads' / 'main').write_text(sha + '\n')


def build_needs_object(fx):
    """A repository whose policy key does not encode the object it manages (the candidate needs an object)."""
    import yaml
    from plugin_tests.test_workbench_repository import KEY, STACK
    entry_commit(fx.repo)
    document = yaml.safe_load((fx.repo / STACK).read_text())
    policies = document['components']['terraform']['intune-reference']['vars']['policies']
    policies['windows_privacy'] = policies.pop(KEY)
    (fx.repo / STACK).write_text(yaml.safe_dump(document))
    return {'repository': fx.repo}


def build_no_commit(fx):
    """A repository with no readable commit (the candidate needs a choice: the commit)."""
    return {'repository': fx.repo}


def build_other_tenant(fx):
    """The same repository, entered from a store for another tenant."""
    from intune_iac.workbench_store import WorkbenchStore
    entry_commit(fx.repo)
    WorkbenchStore.create(fx.root / 'other-store', '99999999-9999-4999-8999-999999999999')
    return {'repository': fx.repo, 'store': fx.root / 'other-store'}


def build_empty(fx):
    from intune_iac.workbench_store import WorkbenchStore
    WorkbenchStore.create(fx.root / 'empty-store', TENANT)
    return {'store': fx.root / 'empty-store', 'service': False}


# name -> (builder, plan options). A state is a store as the person finds it; the plan opens every surface in it.
STATES = collections.OrderedDict([
    ('empty store', (build_empty, {'help_surfaces': True})),
    ('observed estate, no selection', (build_observed, {'help_surfaces': True})),
    ('selected policy', (build_observed, {'selected': True})),
    ('repository intent current', (build_import, {'selected': True})),
    ('repository intent stale', (build_stale, {'selected': True})),
    ('proposal awaiting review', (build_proposal, {'selected': True})),
    ('approved operation awaiting execute', (build_approved, {'selected': True, 'help_surfaces': True})),
    ('lost response, outcome unknown', (build_lost, {'selected': True})),
    ('queue with items', (build_queue, {'selected': True})),
    ('diagnostics (unknown outcome, stale repository, failed collection)', (build_diagnostics, {'selected': True})),
    ('repository-entry: needs an object', (build_needs_object, {'selected': True})),
    ('repository-entry: needs a commit', (build_no_commit, {'selected': True})),
    ('repository-entry: other tenant', (build_other_tenant, {})),
])


@functools.lru_cache(maxsize=None)
def sweep_state(name):
    """Build the state and read every surface in it. Returns the Sweep."""
    builder, options = STATES[name]
    fx = Estate()
    fx.setUp()
    try:
        made = builder(fx)
        root = made.get('store', fx.store.root)
        service = None if made.get('service') is False else fx.service.root
        plan = surfaces_plan(selected=options.get('selected', False), operation=made.get('operation'),
                             repository=made.get('repository'), help_surfaces=options.get('help_surfaces', False))
        sweep = Sweep()
        result = drive(root, service, plan, name, sweep, FULL_SCHEDULE if name == 'observed estate, no selection' else SCHEDULE)
        if result.get('status') != 'closed':
            raise AssertionError('the session did not close: %r' % (result,))
        return sweep
    finally:
        fx.doCleanups()


# -- the command line's text routes --------------------------------------------------------------------------------------------------

WRITTEN = collections.Counter()      # parser leaf (a tuple of words) -> times cli.main printed text for it, through cli._write_text


def leaf_of(parser, namespace):
    """The parser leaf an argparse namespace selected, as the tuple of words that name it: each subparsers action stores the word it
    took in the attribute it was given as dest."""
    path = []
    while True:
        action = next((item for item in parser._actions if isinstance(item, argparse._SubParsersAction)), None)
        name = getattr(namespace, action.dest, None) if action is not None else None
        if name not in (action.choices if action is not None else ()):
            return tuple(path)
        path.append(name)
        parser = action.choices[name]


@contextlib.contextmanager
def recording_routes():
    """Record, whenever cli.main prints text (cli._write_text), the parser leaf it was run for, in WRITTEN. The parser's parse_args is
    wrapped to keep the namespace it returns, and _write_text to read it: no sweep says which route it drove, cli.main does."""
    from intune_iac import cli
    if getattr(cli._write_text, 'records_routes', False):
        yield
        return
    seen = {}
    real_parser, real_write = cli.parser, cli._write_text

    def parser():
        built = real_parser()
        parse = built.parse_args

        def parse_args(*args, **kwargs):
            seen['namespace'], seen['parser'] = parse(*args, **kwargs), built
            return seen['namespace']
        built.parse_args = parse_args
        return built

    def write(rows):
        if 'namespace' in seen:
            WRITTEN[leaf_of(seen['parser'], seen['namespace'])] += 1
        return real_write(rows)
    write.records_routes = True
    with patch.object(cli, 'parser', parser), patch.object(cli, '_write_text', write):
        yield


def records_routes(function):
    """A sweep that reaches cli.main through a helper of another test module records the routes it drives."""
    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        with recording_routes():
            return function(*args, **kwargs)
    return wrapper


class Tty(io.StringIO):
    """Standard output that is a terminal (cli.main prints some sentences only to one)."""

    def isatty(self):
        return True


def run_cli(argv, width=100, tty=False, execute=None):
    """(exit code, stdout, stderr) of cli.main(argv) in process, as a terminal `width` columns wide would show it. tty: standard
    output is a terminal. execute: the result cli.execute gives instead of running the command (for a route that needs a session)."""
    from intune_iac import cli
    out, err = (Tty() if tty else io.StringIO()), io.StringIO()
    with recording_routes(), patch('shutil.get_terminal_size', return_value=os.terminal_size((width, 40))), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
            (patch.object(cli, 'execute', return_value=execute) if execute is not None else contextlib.nullcontext()):
        try:
            code = cli.main(list(argv))
        except SystemExit as stop:
            code = stop.code
    return code, out.getvalue(), err.getvalue()


def routes(parser, path=()):
    """Every route of the command line, found in its parser: (path, whether it has subroutes, whether it needs an argument)."""
    found = []
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, sub in action.choices.items():
                subroutes = routes(sub, path + (name,))
                needs = any(getattr(item, 'required', False) and not isinstance(item, argparse._SubParsersAction)
                            for item in sub._actions)
                found.append((path + (name,), bool(subroutes), needs))
                found += subroutes
    return found


# -- every parser leaf, classified: text a person reads, a session, or a machine form ----------------------------------------------
#
# A leaf of cli.parser() shows itself to a person in one of three ways. 'text': cli.main prints its screen through cli._write_text
# (the leaves that satisfy the conditions that enclose a _write_text call, read from cli.main's source by text_leaves_by_code, never
# listed here). 'session': a terminal session or prompt flow with its own input and output (SESSION_LEAVES, declared). 'machine': every
# other leaf, which prints the JSON document of cli.main. The sweeps must drive each text leaf through cli.main, which recording_routes
# observes; a leaf that prints text and is not driven fails the test until it is.

SESSION_LEAVES = {('wizard',): 'sweep_wizards (the plain wizard, the guided workflow and the journey, scripted)',
                  ('workbench', 'workspace'): 'sweep_state (the workspace, in thirteen states)',
                  ('workbench', 'terminal'): 'sweep_state (the engine under the workspace is the line terminal)'}


def leaf_paths(parser):
    return [path for path, has_subroutes, _ in routes(parser) if not has_subroutes]


def parser_dests(parser):
    """The namespace attributes the subparsers actions of a parser tree set: {'command', 'workbench_command', 'signin_command', ...}."""
    found = set()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            found.add(action.dest)
            for sub in action.choices.values():
                found |= parser_dests(sub)
    return found


def route_dests(parser, path):
    """{attribute: word} that parsing a leaf sets: ('signin', 'status') -> {'command': 'signin', 'signin_command': 'status'}."""
    found = {}
    for name in path:
        action = next(item for item in parser._actions if isinstance(item, argparse._SubParsersAction))
        found[action.dest] = name
        parser = action.choices[name]
    return found


def route_constraints(test):
    """[(attribute, {words})] the route conditions of an `if` test: its `and` clauses that compare args.<attribute>, or
    getattr(args, '<attribute>', None), with a word or a tuple of words (== and in). Any other clause says nothing about the route."""
    found = []
    for clause in (test.values if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.And) else [test]):
        if not (isinstance(clause, ast.Compare) and len(clause.ops) == 1 and isinstance(clause.ops[0], (ast.Eq, ast.In))):
            continue
        left, right = clause.left, clause.comparators[0]
        if isinstance(left, ast.Attribute) and isinstance(left.value, ast.Name) and left.value.id == 'args':
            dest = left.attr
        elif (isinstance(left, ast.Call) and getattr(left.func, 'id', '') == 'getattr' and len(left.args) >= 2
              and isinstance(left.args[0], ast.Name) and left.args[0].id == 'args' and isinstance(left.args[1], ast.Constant)):
            dest = left.args[1].value
        else:
            continue
        words = {item.value for item in (right.elts if isinstance(right, (ast.Tuple, ast.List, ast.Set)) else [right])
                 if isinstance(item, ast.Constant) and isinstance(item.value, str)}
        if words:
            found.append((dest, words))
    return found


def main_text_branches(source=None):
    """One list of route constraints for each `_write_text(...)` call in cli.main (or in the source of a function like it): what the
    conditions that enclose the call say about the route."""
    from intune_iac import cli
    tree = ast.parse(textwrap.dedent(source if source is not None else inspect.getsource(cli.main)))
    branches = []

    def visit(node, tests):
        if isinstance(node, ast.Call) and getattr(node.func, 'id', None) == '_write_text':
            branches.append([constraint for test in tests for constraint in route_constraints(test)])
        for child in ast.iter_child_nodes(node):
            visit(child, tests + [node.test] if isinstance(node, ast.If) and child in node.body else tests)
    visit(tree, [])
    return branches


def text_leaves_by_code(parser, source=None):
    """The leaves of a parser for which some `_write_text` call of cli.main can run: those that satisfy every route condition that
    encloses the call. A condition on anything but the route (--json, --format, the result) is not read, so a leaf stays admitted
    when only such a condition would turn the text off."""
    dests = parser_dests(parser)
    found = set()
    for constraints in main_text_branches(source):
        for path in leaf_paths(parser):
            chosen = route_dests(parser, path)
            if all(chosen.get(dest) in words for dest, words in constraints if dest in dests):
                found.add(path)
    return found


KINDS = ('empty', 'repository', 'export', 'emptystore', 'full', 'context')


@functools.lru_cache(maxsize=1)
@records_routes
def sweep_start_and_catalog():
    """start and catalog for every fixture directory, with no goal and with each goal, at each width, for an ordinary directory
    name and for one the screen may not show (a credential shape)."""
    from plugin_tests import test_start_standin as standin
    from plugin_tests.test_start_goal import Fixtures
    sweep = Sweep()
    with tempfile.TemporaryDirectory() as temp:
        parents = {}
        for kind in KINDS:
            parent = Path(temp) / kind
            parent.mkdir()
            for name in (standin.ORDINARY, standin.CREDENTIAL):
                if kind == 'full':
                    standin.estate(parent, name)
                elif kind == 'context':
                    shutil.copytree(Fixtures.get()['context'], parent / name)
                else:
                    standin.variant_estate(parent, name, kind)
            parents[kind] = str(parent)
        for kind, parent in parents.items():
            for hidden, name in ((False, standin.ORDINARY), (True, standin.CREDENTIAL)):
                for goal in standin.GOALS:
                    for width in (WIDTHS if not hidden else (120, 40)):
                        state = '%s directory, %s name' % (kind, 'hidden' if hidden else 'ordinary')
                        for command, render in (('start', standin.render), ('catalog', standin.render_catalog)):
                            lines = render('cli', parent, name, width, goal)
                            sweep.read(state, command + (' --goal ' + goal if goal else ''), (width, 0),
                                       readable(lines), rows=lines)
    return sweep


@functools.lru_cache(maxsize=1)
@records_routes
def sweep_signin():
    """signin status and signin collect, the CLIs and the collecting child stubbed as the sign-in tests do: every golden case
    (partial, failed, withheld, blocked, collected ...), each with and without --account, at two widths."""
    from plugin_tests.signin_golden_cases import CASES
    from plugin_tests.test_signin_collect_readable import run_text
    sweep = Sweep()
    for name in sorted(CASES):
        for account in ((), ('--account', 'alex@example.test')):
            for width in (100, 60):
                code, text, err = run_text(name, width=width, extra=list(account))
                route = ' '.join(CASES[name][1][:2]) + (' --account' if account else '')
                state = name
                sweep.text(state, route, (width, 0), text)
                sweep.text(state, route + ' (stderr)', (width, 0), err)
    return sweep


@functools.lru_cache(maxsize=1)
def sweep_workflow_and_engineering():
    """workbench workflow in its text form (a prepared change, an unknown outcome, nothing observed to propose from), the
    engineering view with no records, and the sentences that follow an interrupt, for each kind of interrupt."""
    sweep = Sweep()
    for name, builder in (('selected policy', build_observed), ('proposal awaiting review', build_proposal),
                          ('lost response, outcome unknown', build_lost), ('repository intent stale', build_stale)):
        fx = Estate()
        fx.setUp()
        try:
            builder(fx)
            for width in (120, 80, 60):
                code, text, err = run_cli(['workbench', 'workflow', '--root', str(fx.store.root), '--policy', OBJECT,
                                           '--service-root', str(fx.service.root)], width)
                sweep.text(name, 'workbench workflow', (width, 0), text)
                sweep.text(name, 'workbench workflow (stderr)', (width, 0), err)
        finally:
            fx.doCleanups()
    for width in WIDTHS:
        code, text, err = run_cli(['engineering'], width)
        sweep.text('no records configured', 'engineering', (width, 0), text)
        # a collect with no service root is a session that was started without one (the sentence then has no service to name)
        for during in (None, {'command': 'execute', 'operation_root': '/ops/one'}, {'command': 'reconcile', 'operation_root': '/ops/one'},
                       {'command': 'collect', 'service_root': '/svc'}, {'command': 'collect', 'service_root': None},
                       {'command': 'diagnostics'}, {'command': 'review'}):
            result = {'status': 'interrupted', 'store_root': '/stores/one', 'interrupted_during': during}
            # through cli.main on a terminal, with the session's result handed back (the route prints these sentences only then)
            code, text, err = run_cli(['workbench', 'workspace', '--root', '/stores/one'], width, tty=True, execute=result)
            state = 'interrupted during %s%s' % ((during or {}).get('command', 'nothing'),
                                                 ' with no service root' if during and during.get('command') == 'collect'
                                                 and not during.get('service_root') else '')
            sweep.text(state, 'workbench workspace (after Ctrl-C)', (width, 0), text)
            sweep.text(state, 'workbench workspace (after Ctrl-C) (stderr)', (width, 0), err)
    return sweep


@functools.lru_cache(maxsize=1)
def sweep_help_and_usage():
    """--help of every route, and the usage error of every route that needs an argument (it fails before it does anything)."""
    from intune_iac import cli
    sweep = Sweep()
    count = 0
    for path, has_subroutes, needs in [((), True, False)] + routes(cli.parser()):
        code, text, err = run_cli(list(path) + ['--help'], 100)
        sweep.text('help', ' '.join(('intune-iac',) + path + ('--help',)), (100, 0), text)
        count += 1
        if needs and not has_subroutes:
            code, text, err = run_cli(list(path), 100)
            sweep.text('usage error', ' '.join(('intune-iac',) + path), (100, 0), err)
            count += 1
    sweep.routes_read = count
    return sweep


# -- the wizard, the guided workflow and the journey ----------------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
POLICY = '22222222-2222-4222-8222-222222222222'
EDITED = '"description": "Synthetic reference; reviewed repository edit."'
ORIGINAL = '"description": "Synthetic reference; not production advice."'
BEFORE_GENERATE = ['continue'] * 3 + [POLICY] + ['continue'] * 4
AFTER_GENERATE = ['generate', 'continue', 'continue', 'plan', 'approve', 'execute', 'reconcile', 'continue', 'finish']


class Transcript:
    """What a scripted session showed: every prompt it handed to the person and every line it printed."""

    def __init__(self, temp):
        self.root = Path(temp)
        self.root.mkdir(parents=True, exist_ok=True)
        self.source, self.context = self.root / 'export.json', self.root / 'context.json'
        self.source.write_bytes((ROOT / 'examples/supported/input/export.json').read_bytes())
        self.context.write_bytes((ROOT / 'examples/context.json').read_bytes())
        self.shown = []                                       # (kind, text)

    def script(self, answers):
        queue = iter(answers)

        def read(prompt):
            self.shown.append(('prompt', prompt))
            value = next(queue, None)
            if value is None:
                raise EOFError()
            return value() if callable(value) else value
        return read

    def output(self, line):
        self.shown.append(('line', str(line)))

    def edit_stack(self, output):
        stack = Path(output) / 'stacks/orgs/reference/dev.yaml'
        text = stack.read_text()
        assert text.count(ORIGINAL) == 1
        stack.write_text(text.replace(ORIGINAL, EDITED))

    def texts(self):
        return [text for _, text in self.shown]


def read_transcript(sweep, state, route, transcript):
    for kind, text in transcript.shown:
        sweep.read(state, '%s (%s)' % (route, kind), (0, 0), readable(text.split('\n')), rows=text.split('\n'))


@functools.lru_cache(maxsize=1)
def sweep_wizards():
    """The wizard, the guided workflow and the journey, scripted: a first run, a saved session reopened, a conflict, and the same
    with a repository-owned edit of the generated output, which prints the next steps and the handoff sentence."""
    from intune_iac.journey import run_journey
    from intune_iac.wizard import run_wizard
    sweep = Sweep()
    with tempfile.TemporaryDirectory() as temp:
        # the plain wizard
        def wizard(name, steps):
            transcript = Transcript(Path(temp) / re.sub(r'\W+', '-', name))
            session, output = transcript.root / 'session.json', transcript.root / 'project'
            for answers, supplied in steps(transcript, output):
                kwargs = dict(input_path=transcript.source, context_path=transcript.context, output_path=output) if supplied else {}
                with contextlib.suppress(EOFError):
                    run_wizard(session, input_fn=transcript.script(answers), output_fn=transcript.output, **kwargs)
            return transcript

        def first_run(transcript, output):
            yield [str(transcript.source), str(transcript.context), str(output), 'generate', 'finish'], False

        def edited(transcript, output):
            yield ['generate', 'save'], True
            transcript.edit_stack(output)
            yield ['review', 'handoff'], False

        def conflict(transcript, output):
            yield ['generate', 'save'], True
            (output / 'README.md').write_text('user-owned edit')
            yield ['review', 'new-path', 'cancel'], False

        for name, steps in (('wizard, first run', first_run), ('wizard, repository-owned edit handed off', edited),
                            ('wizard, output conflict', conflict)):
            read_transcript(sweep, name, 'wizard', wizard(name, steps))

        # the guided workflow
        transcript = Transcript(Path(temp) / 'guided')
        session, output = transcript.root / 'guided.json', transcript.root / 'proposals'
        paths = dict(input_path=transcript.source, context_path=transcript.context, output_path=output)
        with contextlib.suppress(EOFError):
            run_wizard(session, input_fn=transcript.script([POLICY, 'generate', 'finish']), output_fn=transcript.output, guided=True, **paths)
        transcript.edit_stack(output / POLICY)
        with contextlib.suppress(EOFError):
            run_wizard(session, input_fn=transcript.script(['handoff']), output_fn=transcript.output, guided=True)
        read_transcript(sweep, 'guided workflow, repository-owned edit handed off', 'wizard --guided', transcript)

        # the journey: a whole run, then a repository-owned edit handed off, then back and edit
        transcript = Transcript(Path(temp) / 'journey')
        session, output = transcript.root / 'journey.json', transcript.root / 'proposal'
        paths = dict(input_path=transcript.source, context_path=transcript.context, output_path=output)
        with contextlib.suppress(EOFError):
            run_journey(session, input_fn=transcript.script(BEFORE_GENERATE + AFTER_GENERATE), output_fn=transcript.output, **paths)
        read_transcript(sweep, 'journey, a whole run', 'wizard --journey', transcript)
        later = Transcript(Path(temp) / 'journey')
        later.edit_stack(output / POLICY)
        for answers in (['handoff'], ['back selection', 'save'], ['edit output ' + str(Path(temp) / 'journey' / 'new-output'), 'save']):
            with contextlib.suppress(EOFError):
                run_journey(session, input_fn=later.script(answers), output_fn=later.output)
        read_transcript(sweep, 'journey, repository-owned edit handed off, back and edit', 'wizard --journey', later)
    return sweep


# -- simulate, --check-signin, and the protected service and adoption views ------------------------------------------------------------

@functools.lru_cache(maxsize=1)
def sweep_simulate():
    """simulate --format text, with the documents test_sim_render_cli builds: its scenario (a conflict between two policies), a
    snapshot with an unbounded group, one with an incomplete collection, a complete one with no findings, and the estate and
    population route; plus a possible membership under an exclude-mode filter and a group exclusion beside a filter (test_sim_cases).
    Through cli.main with the documents as files (the route writes 100 columns when it is piped) and through the renderer at 60, 80
    and 120 columns."""
    from intune_iac import sim_profile, sim_render
    from intune_iac.synthetic import generate_estate
    from plugin_tests import sim_support as s
    from plugin_tests.sim_cases import simulate
    from plugin_tests.test_sim_render_cli import scenario
    sweep = Sweep()
    default = sim_profile.load_profile({})                     # the profile the command uses when none is given
    one = s.revision_doc([s.policy('p', [s.include('gA')], settings=[])])
    cases = collections.OrderedDict([
        ('a conflict between two policies', scenario()),
        ('an unbounded group and an incomplete device collection', (
            s.snapshot_doc(devices=[s.device('a'), s.device('b')], groups=[s.group('gA', complete=False)],
                           memberships=[s.member('gA', 'a')], collections={'devices': {'complete': False, 'reason': 'query_ceiling'}}),
            s.revision_doc([s.policy('p', [s.include('gA')], settings=[])]))),
        ('an incomplete policy collection', (
            s.snapshot_doc(devices=[s.device('a')], groups=[s.group('gA')], memberships=[s.member('gA', 'a')],
                           collections={'policies': {'complete': False, 'reason': 'query_ceiling'}}), one)),
        ('a complete snapshot with no findings', (
            s.snapshot_doc(devices=[s.device('a')], groups=[s.group('gA')], memberships=[s.member('gA', 'a')]), one)),
        ('a possible membership under an exclude-mode filter', (
            s.snapshot_doc(devices=[s.device('a', model='M1'), s.device('b', model='M1')], groups=[s.group('gA'), s.group('gB')],
                           memberships=[s.member('gA', 'a'), s.member('gA', 'b'), s.member('gB', 'a', certainty='possible')],
                           filters=[s.filt('m1', 'device.model -eq "M1"')]),
            s.revision_doc([s.policy('p', [s.include('gA'), s.include('gB', 'exclude', 'm1')])]))),
        ('a group exclusion beside an exclude-mode filter', (
            s.snapshot_doc(devices=[s.device('a', model='M1'), s.device('b', model='M2'), s.device('c', model='M2')],
                           groups=[s.group('gA'), s.group('gB')],
                           memberships=[s.member('gA', 'a'), s.member('gA', 'b'), s.member('gA', 'c'), s.member('gB', 'b')],
                           filters=[s.filt('m1', 'device.model -eq "M1"')]),
            s.revision_doc([s.policy('p', [s.include('gA', 'exclude', 'm1'), s.exclude('gB')])]))),
    ])
    with tempfile.TemporaryDirectory() as temp:
        folder = Path(temp)

        def write(name, value):
            path = folder / name
            path.write_text(json.dumps(value), encoding='utf-8')
            return str(path)
        for name, (doc, revision) in cases.items():
            code, text, err = run_cli(['simulate', '--snapshot', write('snapshot.json', doc), '--revision',
                                       write('revision.json', revision), '--format', 'text'], 100)
            sweep.text(name, 'simulate --format text', (100, 0), text)
            sweep.text(name, 'simulate --format text (stderr)', (100, 0), err)
            _, out = simulate(doc, revision, default)
            for width in (60, 80, 120):
                sweep.text(name, 'simulate --format text (renderer)', (width, 0), '\n'.join(sim_render.render_text(out, width)))
        estate = generate_estate(seed=7, policy_count=1)
        g0, g1, g2 = estate['truth']['groups']
        population = {'devices': [s.device('a'), s.device('b')], 'group_domains': {g0: 'device', g1: 'device', g2: 'device'},
                      'complete_groups': [g0, g1, g2],
                      'memberships': [{'group_id': g1, 'member_id': s.uid('device/a'), 'member_kind': 'device', 'certainty': 'known'}]}
        removal = s.revision_doc()
        removal['removed_policy_ids'] = [estate['truth']['policies'][0]['id']]
        code, text, err = run_cli(['simulate', '--estate', write('estate.json', estate), '--population', write('population.json', population),
                                   '--revision', write('removal.json', removal), '--format', 'text'], 100)
        sweep.text('a synthetic estate and a population', 'simulate --format text', (100, 0), text)
        sweep.text('a synthetic estate and a population', 'simulate --format text (stderr)', (100, 0), err)
    return sweep


def signin_cases(context):
    """(label, provider, canned az answer, canned gh answer, a phrase the screen must show) for start and catalog --check-signin. The
    answers are the ones the sign-in tests give their fake az and gh (plugin_tests/signin_fakes.py); nothing real runs."""
    from plugin_tests.signin_fakes import azure_account, azure_list, github_hosts
    other = '55555555-5555-4555-8555-555555555555'

    def az(*accounts, **extra):
        return dict(out=azure_list(*accounts), **extra)

    def gh(*entries, **extra):
        return dict(out=github_hosts(*entries), **extra)
    octo = ('github.com', 'octo-user', 'success', True)
    return (
        ('azure: signed in to the context tenant', 'azure', az(azure_account(tenant=context)), None, 'Signed in to tenant'),
        ('azure: signed in to another tenant', 'azure', az(azure_account(tenant=other)), None, 'Sign in to the tenant the context names'),
        ('azure: several accounts in the tenant', 'azure',
         az(azure_account(tenant=context), azure_account(tenant=context, user='sam@example.test', default=False)), None,
         'Several accounts are signed in'),
        ('azure: not signed in', 'azure', az(), None, 'Not signed in to Azure'),
        ('azure: an answer that is not a listing', 'azure', dict(out='this is not json'), None, 'could not be determined'),
        ('azure: only an expired subscription', 'azure', az(azure_account(tenant=context, state='Expired')), None, 'subscription'),
        ('azure: the CLI fails', 'azure', None, None, 'command_failed'),
        ('github: signed in', 'github', None, gh(octo), 'Signed in to github.com'),
        ('github: several accounts', 'github', None, gh(octo, ('github.com', 'other-user', 'success', False)), None),
        ('github: an error state', 'github', None, gh(('github.com', 'octo-user', 'error', True)), None),
        ('github: not logged in', 'github', None, dict(out='', err='You are not logged into any GitHub hosts.', code=1),
         'Not signed in to GitHub'),
        ('both: signed in to each', 'all', az(azure_account(tenant=context)), gh(octo), 'GitHub CLI sign-in'),
        ('both: another tenant and not logged in', 'all', az(azure_account(tenant=other)),
         dict(out='', err='You are not logged into any GitHub hosts.', code=1), 'Not signed in to GitHub'),
    )


@functools.lru_cache(maxsize=1)
def sweep_check_signin():
    """start --goal G --check-signin P and catalog --check-signin P (with and without a goal), with the az and gh the sign-in tests
    stub (FakeClis: canned answers on a temporary search path, no real tool, no network), for every answer in signin_cases, in a
    directory that holds the example context and in one that holds none, at two widths. sweep.unmet lists a case whose screen does
    not show its phrase (the stub was not in effect)."""
    from plugin_tests.signin_fakes import FakeClis
    sweep = Sweep()
    sweep.unmet = []
    root = Path(__file__).resolve().parents[1]
    context = json.loads((root / 'examples/context.json').read_text())['tenant_id']
    with tempfile.TemporaryDirectory() as temp:
        with_context, bare = Path(temp) / 'estate dir', Path(temp) / 'bare'
        with_context.mkdir()
        bare.mkdir()
        shutil.copyfile(root / 'examples/context.json', with_context / 'context.json')
        for index, (label, provider, azure, github, phrase) in enumerate(signin_cases(context)):
            fakes = FakeClis()
            try:
                for tool, first, second, answer in (('az', 'account', 'list', azure), ('gh', 'auth', 'status', github)):
                    if answer is not None:
                        fakes.answer(tool, first, second, **answer)
                shown = []
                with patch.dict(os.environ, {'PATH': fakes.path_entry() + os.pathsep + os.environ.get('PATH', '')}):
                    for folder, name in ((with_context, 'a context'), (bare, 'no context')):
                        if folder is bare and index > 1:
                            continue                       # the directory with no context is read for the first two answers only
                        runs = [(['start', str(folder), '--goal', goal, '--check-signin', provider], 'start --goal %s' % goal)
                                for goal in ('discover', 'adopt')]
                        runs += [(['catalog', str(folder), '--check-signin', provider], 'catalog'),
                                 (['catalog', str(folder), '--goal', 'discover', '--check-signin', provider], 'catalog --goal discover')]
                        for argv, route in runs:
                            for width in (120, 60):
                                code, text, err = run_cli(argv, width)
                                sweep.text('%s; %s' % (label, name), '%s --check-signin %s' % (route, provider), (width, 0), text)
                                sweep.text('%s; %s' % (label, name), '%s --check-signin %s (stderr)' % (route, provider), (width, 0), err)
                                shown.append(' '.join(text.split()))
            finally:
                fakes.cleanup()
            if phrase and not any(phrase in text for text in shown):
                sweep.unmet.append((label, phrase))
    return sweep


class ServiceView(ServiceFixtures, unittest.TestCase):
    """The hand-authored fixtures of the protected service views (plugin_tests/service_presentation_fixtures.py, which
    test_workbench_service_tui_r4 shares) as an object a sweep builds and cleans up by hand. It has no test method, so it is not
    collected."""

    def __init__(self):
        super().__init__('setUp')


@functools.lru_cache(maxsize=1)
def sweep_protected_views():
    """The views behind the service, adoption and adoption-plan navigation, as the workspace shows them: for each of review, status,
    attach, cancel and recover, the command sent and the response received, with the hand-authored responses (presentation
    fixtures) of ServicePresentationTests (through service_presentation_fixtures), AdoptionPresentationTests and
    RecoveryPlanPresentation, in the summary and in the typed details, plus an error response and the adoption history. The real
    protected journals need the pinned docker and a TLS probe built with gcc (test_worker_service_r4.WorkerServiceR4Tests,
    test_worker_service_readback_r4, test_worker_evidence_r4), which this machine does not have; service-link, adoption-link,
    evidence-link and evidence-history are driven by build_link_sweep with the presentation fixtures of
    plugin_tests/link_presentation_fixtures.py (see the module docstring)."""
    from plugin_tests.test_workbench_adoption_recovery_tui_r4 import RecoveryPlanPresentation
    from plugin_tests.test_workbench_adoption_tui_r4 import AdoptionPresentationTests
    sweep = Sweep()
    outcome = {'operation_outcome': 'host_completed_service_unverified', 'independent_service_readback': 'required', 'primary_error': None}
    error = {'status': 'error', 'error': {'code': 'service_workspace_target_mismatch'}}
    domains = (
        ('protected service', ServiceView,
         lambda case, action: case.response(action, **({'cancel_requested': True} if action in ('status', 'cancel', 'recover') else
                                                       {'outcome': outcome} if action == 'attach' else {}))),
        ('protected adoption', lambda: AdoptionPresentationTests('test_state_only_presentation_preserves_uncertainty'),
         lambda case, action: case.result(action)),
        ('adoption recovery plan', lambda: RecoveryPlanPresentation('test_unknown_original_and_planonly_restriction_displayed'),
         lambda case, action: case.result(action)),
    )
    for domain, make, reply in domains:
        prefix = {'protected service': 'service', 'protected adoption': 'adoption', 'adoption recovery plan': 'adoption-plan'}[domain]
        case = make()
        case.setUp()
        try:
            case.ui.rules = 'unicode'
            for action in ('review', 'status', 'attach', 'cancel', 'recover'):
                case.ui._send(case.command(action))
                case.ui.receive(reply(case, action))
                for layer in ('summary', 'details'):
                    case.ui.layer, case.ui.scroll = layer, 0
                    read_screen(sweep, case.ui, domain, '%s-%s (%s%s)' % (prefix, action, 'Plan' if case.ui.tab == 4 else 'Execution',
                                                                           ', typed details' if layer == 'details' else ''))
                case.ui.layer = 'summary'
            case.ui._send(case.command('review'))
            case.ui.receive(error)
            read_screen(sweep, case.ui, domain, '%s-review (an error response)' % prefix)
            if prefix == 'adoption':
                case.ui.selected = OBJECT
                case.ui._send('adoption-history')
                case.ui.receive({'operations': []})
                read_screen(sweep, case.ui, domain, 'adoption-history (no operations)')
        finally:
            case.doCleanups()
    return sweep


LINK_ROUTES = ('service-link', 'adoption-link', 'evidence-link', 'evidence-history')


def build_link_sweep(inject=None):
    """service-link, adoption-link, evidence-link and evidence-history, as the workspace shows them: for each, the command sent and
    the response received (plugin_tests/link_presentation_fixtures.py: the rows the product's own store writes for the three links,
    the real history of received evidence with one entry that reopens and one that cannot, and a refusal of each), read in the
    summary and in the typed details at every size; also the history of adoptions with a linked operation that cannot be reopened.
    inject: a text that replaces the one string each response shows in full, to prove a command in a response is read."""
    from plugin_tests import link_presentation_fixtures as links
    sweep = Sweep()
    case = ServiceView()
    case.setUp()
    try:
        case.ui.rules = 'unicode'
        case.ui.selected = OBJECT
        for route, variant, command, response in links.responses(case.store, case.job, case.policy, case.root, inject):
            case.ui._send(command)
            case.ui.receive(response)
            for layer in ('summary', 'details'):
                case.ui.layer, case.ui.scroll = layer, 0
                read_screen(sweep, case.ui, 'linked records', '%s, %s%s' % (route, variant, ', typed details' if layer == 'details' else ''))
            case.ui.layer = 'summary'
    finally:
        case.doCleanups()
    return sweep


sweep_link_views = functools.lru_cache(maxsize=1)(build_link_sweep)


# -- the tests --------------------------------------------------------------------------------------------------------------------

def tearDownModule():
    from plugin_tests.test_start_goal import Fixtures
    Fixtures.release()


class ReaderTests(unittest.TestCase):
    """The sweep can fail: the reader sees the known cases of the scans, joined as a person sees them, and leaves resolved ones."""
    BAD = (
        ('intune-iac workbench init --root STORE --tenant TENANT_ID', ['STORE', 'TENANT_ID']),
        ('Run: intune-iac signin collect --tenant T --policy P --output NEW_DIR', ['NEW_DIR']),
        ('intune-iac wizard --session NEW_SESSION.json --input export.json --output NEW_OUTPUT_DIR', ['NEW_SESSION.json', 'NEW_OUTPUT_DIR']),
        ('intune-iac workbench companion --root STORE --object ID --out FILE', ['STORE', 'ID', 'FILE']),
        ('intune-iac workbench execute --operation /ops/one --approve-digest DIGEST', ['DIGEST']),
        ('execute /ops/one DIGEST', ['DIGEST']),
        ('Use :reconcile OPERATION_DIR for readback.', ['OPERATION_DIR']),
        ('    :queue-amend FILE none', ['FILE']),
        ('companion FILE', ['FILE']),
        ('intune-iac catalog DIRECTORY', ['DIRECTORY']),
        ('propose-from-intent NEW_OPERATION_DIR', ['NEW_OPERATION_DIR']),
    )
    CLEAN = ("intune-iac workbench workspace --root 'estate dir/store'", 'Run: intune-iac doctor and pass its result.',
             'intune-iac workbench execute --operation /ops/one --approve-digest ' + 'a' * 64, 'No action needed.',
             'the signin collect command using --tenant T, naming --output as a new folder for the output')

    def test_the_reader_finds_each_known_case(self):
        for text, operands in self.BAD:
            with self.subTest(text=text):
                self.assertEqual([found for _, found in unresolved(text)], [operands])

    def test_resolved_commands_and_words_are_left_alone(self):
        for text in self.CLEAN:
            with self.subTest(text=text):
                self.assertEqual(unresolved(text), [])

    def test_a_command_wrapped_over_rows_or_continued_with_a_backslash_is_one_command(self):
        for rows in (['intune-iac workbench init --root', 'STORE --tenant TENANT_ID'],
                     ['  intune-iac workbench init --root \\', '      STORE --tenant \\', '      TENANT_ID'],
                     ['Create a store first:', '  intune-iac workbench init --root STORE', 'then go on.']):
            with self.subTest(rows=rows):
                found = [operands for text in readable(rows) for _, operands in unresolved(text)]
                self.assertIn(['STORE', 'TENANT_ID'] if 'TENANT_ID' in ' '.join(rows) else ['STORE'], found)

    def test_a_pair_of_option_and_value_is_judged_by_each_string(self):
        self.assertEqual(list(_strings(('--output', 'NEW_DIR'))), ['--output', 'NEW_DIR'])
        self.assertEqual(list(_strings(('--output', None))), ['--output'])

    def test_a_list_item_does_not_join_the_row_before_it(self):
        self.assertEqual(paragraphs(['review OPERATION_DIR', '4. delivery OPERATION_DIR']),
                         ['review OPERATION_DIR', '4. delivery OPERATION_DIR'])

    def test_a_synopsis_is_allowed_only_on_a_surface_that_shows_the_convention_sentence(self):
        for convention, expected in ((True, 0), (False, 2)):
            sweep = Sweep()
            sweep.read('state', '8 Help', (80, 24), ['propose DESIRED_JSON NEW_OPERATION_DIR', 'execute OPERATION_DIR'], convention)
            self.assertEqual(sweep.count(), expected, convention)
        sweep = Sweep()                                       # the same words are not a synopsis anywhere but on the help page
        sweep.read('state', 'a Actions, action 2 focused', (80, 24), ['propose DESIRED_JSON NEW_OPERATION_DIR'], True)
        sweep.read('state', '2 Inspector', (80, 24), ['companion FILE'], True)
        self.assertEqual((len(sweep.found), len(sweep.synopses)), (2, 0))
        sweep = Sweep()
        sweep.read('state', 'queue', (80, 24), [':queue-amend FILE none'], True)         # not a synopsis: the sentence does not help
        self.assertEqual(sweep.count(), 1)
        # the parts that matter, not one exact quote: how far the reader reads past the placeholder (a recorded word such as
        # `none` after it) is the reader's business and may change
        text = ' '.join(sweep.failures())
        self.assertIn('queue-amend', text)
        self.assertIn("unresolved ['FILE']", text)

    def test_a_failure_names_the_surface_the_state_the_size_the_command_and_its_operands(self):
        sweep = Sweep()
        sweep.read('lost response', 'm Queue', (40, 12), ['x :queue-amend FILE none'])
        text = '\n'.join(sweep.failures())
        for part, what in (('queue-amend', 'the command word'), ("unresolved ['FILE']", 'the unresolved operand'),
                           ("'m Queue'", 'the surface'), ("'lost response'", 'the state'), ('40x12', 'the size')):
            self.assertIn(part, text, what)

    def test_json_is_a_machine_form_and_is_not_read(self):
        sweep = Sweep()
        sweep.text('state', 'start --json', (80, 0), '{"next": "intune-iac catalog DIRECTORY"}')
        self.assertEqual(sweep.count(), 0)
        sweep.text('state', 'start', (80, 0), 'Run: intune-iac catalog DIRECTORY')
        self.assertEqual(sweep.count(), 1)


ALWAYS = NUMBERED + LETTERED + ('f Filters', ': command line (empty)', ': command line (typing)', ':catalog')


def coverage_problems(name, sweep):
    """What the sweep of a state did not read: every numbered and lettered surface at every size, and the layers the state's options
    call for (the actions layer with each action, the workflow map with each stage, the help listing, the repository entry)."""
    options = STATES[name][1]
    wanted = list(ALWAYS)
    if options.get('selected'):
        wanted += ['a Actions', 'a Actions, action 1 focused', 'a Actions, action 1 staged', ':workflow', ':workflow, stage 12 focused']
    if options.get('help_surfaces'):
        wanted += ['? Help', '? Help, typed details (e)']
    if name.startswith('repository-entry'):
        wanted += [':repository-entry (candidates)', ':repository-entry (second candidate)']
    return ['%s at %dx%d' % (surface, size[0], size[1]) for surface in wanted for size in SIZES
            if not sweep.coverage[(name, surface, size)]]


def judge(case, sweep):
    """The two checks of a sweep, each reported on its own: the product's reader, then the independent net."""
    with case.subTest('the product reader (readiness.commands_in)'):
        case.assertEqual(sweep.failures(), [], '\n' + '\n'.join(sweep.failures()))
    with case.subTest('the independent net (a placeholder after a command word in the same row)'):
        case.assertEqual(sweep.net_failures(), [], '\n' + '\n'.join(sweep.net_failures()))


class NetTests(unittest.TestCase):
    """The independent net judges a row with no context rules: a placeholder-like token after a command word of the same row."""
    HITS = (
        ('collect --root STORE --service-root SERVICE', [('collect', 'STORE'), ('collect', 'SERVICE')]),
        ('    :queue-review-template ownership_unknown NEW_JSON', [('queue-review-template', 'NEW_JSON')]),
        ('Journey [continue/UUIDs/generate/plan/approve/execute/reconcile/finish/back STAGE/edit FIELD VALUE/resume/save/cancel]: ',
         [('back', 'STAGE'), ('edit', 'FIELD'), ('edit', 'VALUE')]),
        ('Run: intune-iac workbench companion --root STORE --object ID --out FILE',
         [('companion', 'STORE'), ('companion', 'ID'), ('companion', 'FILE')]),
        ('start from NEW_SESSION.json, then run review OPERATION_DIR.', [('start', 'NEW_SESSION.json'), ('review', 'OPERATION_DIR')]),
        ('wizard --session=SESSION', [('wizard', 'SESSION')]),                       # an option joined to its value by =
        ('intune-iac capture --token-env TOKEN_VARIABLE_NAME', [('capture', 'TOKEN_VARIABLE_NAME')]),
        ('inspect (the policy DIGEST)', [('inspect', 'DIGEST')]),                   # no punctuation hides a token
        # the commands the product prints for the programs it runs (external_programs), not its own
        ('az account set --subscription SUBSCRIPTION (the subscription id or name)', [('az', 'SUBSCRIPTION')]),
        ('az logout --username NAME (the account name to sign out)', [('az', 'NAME')]),
        ('sign in again: az login --tenant TENANT_ID --user USER', [('az', 'TENANT_ID'), ('az', 'USER')]),
        ('az account show --subscription SUBSCRIPTION_ID --account ACCOUNT', [('az', 'SUBSCRIPTION_ID'), ('az', 'ACCOUNT')]),
    )
    CLEAN = (
        'Select a policy first: 1 (Estate), then Enter.',                           # a capital S is not the command word select
        "intune-iac workbench workspace --root 'estate dir/store'",
        'the capture command, naming --tenant as your tenant id and --output as a new folder for the output',
        'FILE is the file to write; then run companion with it',                    # the token stands before the command word
        'SYNTHETIC | TENANT 11111111 | POLICY none selected',                       # no command word in the row
        'review the OBS and OP states',                                             # capitals that are not placeholder-shaped
        'az account list --output json',                                            # a resolved command of an external program
        'sign in again: az login --tenant 11111111-1111-4111-8111-111111111111; then run gh auth status --json hosts',
    )

    def test_a_token_after_a_command_word_is_a_hit_whether_or_not_a_command_can_be_read(self):
        for row, expected in self.HITS:
            with self.subTest(row=row):
                self.assertEqual(net_hits(row), expected)

    def test_prose_and_resolved_commands_are_not_hits(self):
        for row in self.CLEAN:
            with self.subTest(row=row):
                self.assertEqual(net_hits(row), [])

    def test_the_net_needs_no_command_to_be_read(self):
        # Forms the product's reader did not read on 2dc278e (no placeholder as the first operand, a word outside its vocabulary).
        # What the reader reads of them is its own business and may grow; the net hits them either way.
        for row in ('collect --root STORE --service-root SERVICE', ':queue-review-template ownership_unknown NEW_JSON'):
            self.assertTrue(net_hits(row), row)

    def test_the_external_programs_are_derived_from_the_products_own_source_and_are_command_words(self):
        from intune_iac import readiness
        programs = external_programs()
        self.assertTrue({'az', 'gh'} <= programs, programs)                          # signin.py runs both with a literal argv
        shell, typed = readiness.dialects()
        self.assertFalse(programs & (set(shell) | set(typed) | {readiness.PROGRAM}))   # none is the product's own
        self.assertTrue(programs <= command_words())
        for program in programs:                                                     # each is printed as a command somewhere
            self.assertTrue(any(re.search(r'(?<![\w./-])%s\s+(?:--?[a-z]|[a-z])' % re.escape(program), text)
                                for text in package_strings()), program)
        self.assertNotIn('docker', programs)                                         # a program nothing prints a command for

    def test_the_command_words_are_the_product_tables_and_the_placeholder_words_are_the_briefs(self):
        words = command_words()
        for word in ('intune-iac', 'workbench', 'companion', 'queue-amend', 'back', 'edit', 'collect', 'init', 'start'):
            self.assertIn(word, words)
        for word in ('Select', 'the', 'STORE'):
            self.assertNotIn(word, words)
        for word in ('NEW_JSON', 'TOKEN_VARIABLE_NAME', 'SERVICE_ROOT', 'FILE', 'ID', 'NEW_SESSION.json', 'DIRECTORY',
                     'SUBSCRIPTION', 'USER', 'ACCOUNT', 'SUBSCRIPTION_ID'):
            self.assertTrue(placeholder_like(word), word)
        for word in ('OBS', 'REPO_', 'file', 'Enter', 'UUIDs', 'KEY', '1_2'):
            self.assertFalse(placeholder_like(word), word)

    def test_a_command_wrapped_over_rows_or_continued_with_a_backslash_is_one_command_for_the_net(self):
        for rows, expected in (
                (['Run: collect --root', 'STORE --service-root SERVICE'], [('collect', 'STORE'), ('collect', 'SERVICE')]),
                (['  intune-iac workbench init --root \\', '      STORE --tenant \\', '      TENANT_ID'],
                 [('init', 'STORE'), ('init', 'TENANT_ID')]),
                (['Run:', 'collect', '--root STORE'], [('collect', 'STORE')]),
                (['select the policy:', 'review', 'OPERATION_DIR'], [('review', 'OPERATION_DIR')])):
            with self.subTest(rows=rows):
                self.assertEqual([(hit.word, hit.token) for hit in net_scan(rows)], expected)
                sweep = Sweep()
                sweep.read('state', '2 Inspector', (80, 24), [], rows=rows)
                self.assertEqual(sorted(sweep.net), sorted(expected))
        sweep = Sweep()
        sweep.read('state', '2 Inspector', (60, 20), [], rows=['Run: collect --root', 'STORE --service-root SERVICE'])
        text = '\n'.join(sweep.net_failures())
        self.assertIn('Run: collect --root STORE --service-root SERVICE', text)                 # the failure shows the whole command
        self.assertIn("'2 Inspector'", text)

    def test_the_net_does_not_carry_a_command_over_a_sentence_a_blank_row_or_a_list_item(self):
        for rows in (['Run collect.', 'FILE is the file to write'], ['Run collect', '', 'FILE is the file'],
                     ['review the plan', '1. FILE is a number'], ['review the plan', '- FILE is a number']):
            with self.subTest(rows=rows):
                self.assertEqual(net_scan(rows), [])
        blocks = [['Run: a \\', '  b', '', '1. c', 'd', '2. e'], ['x', '* y', 'z']]
        for rows in blocks:                                                                       # the same blocks the reader reads
            joined = [' '.join(part[:-1].rstrip() if part.endswith('\\') else part
                               for part in (' '.join(rows[index].split()) for index in block)) for block in visual_blocks(rows)]
            self.assertEqual(joined, paragraphs(rows))

    def test_the_pages_of_a_scroll_are_joined_once_and_the_net_reads_them_in_groups(self):
        pages = [Page(['A1'], ['a', 'b', 'c'], ['C1'], True, 0), Page(['A1'], ['d', 'e', 'f'], ['C1'], True, 3),
                 Page(['A1'], ['e', 'f', 'g'], ['C1'], False, 4)]                   # the last page is drawn from the row that fills it
        self.assertEqual(whole_body(pages), ['a', 'b', 'c', 'd', 'e', 'f', 'g'])
        self.assertEqual(net_rows(pages[:1], 'summary'), ['A1', '', 'C1', '', 'a', 'b', 'c', ''])
        self.assertEqual(net_rows(pages[:2], 'catalog'), ['A1', '', 'C1', '', 'A1', '', 'C1', '', 'a', 'b', 'c', '', 'd', 'e', 'f', ''])

    def test_help_surfaces_are_read_and_only_the_exact_synopses_are_excused(self):
        listing, legend, keys = synopsis_sources()
        entry = next(entry for entry in sorted(listing) if len(entry.split()) >= 3 and net_scan(['1. ' + entry]))
        heading = '8 Help'

        def failures(rows, convention=True, surface='? Help, typed details (e)'):
            sweep = Sweep()
            sweep.read('state', surface, (80, 24), [], convention, rows)
            return sweep
        words = entry.split()
        numbered = ['12. ' + ' '.join(words[:2]), ' '.join(words[2:])]                    # an entry as the page prints it: wrapped
        sweep = failures(numbered)
        self.assertEqual((sweep.net_failures(), sweep.excused['exact synopsis'] > 0), ([], True))
        self.assertEqual(failures(numbered + ['%s Terminal estate views default to 10 per page.' % keys[0]]).net_failures(), [])
        self.assertTrue(failures(numbered + ['also %s' % keys[0]]).net)                   # only the label of the table's next key may follow
        self.assertTrue(failures(numbered, convention=False).net)                         # no sentence on the surface: not excused
        self.assertTrue(failures(numbered, surface='2 Inspector').net)                    # not a help surface: not excused
        for rows in (['12. ' + entry + ' immediately'],                                   # an entry with a word after it
                     ['12. immediately ' + entry],                                        # and with a word before it
                     [entry],                                                             # not an item of the listing
                     ['12. ' + entry, 'Run: collect --root', 'STORE --service-root SERVICE'],        # a wrapped command on the page
                     ['Run: collect --root', 'STORE --service-root SERVICE']):
            with self.subTest(rows=rows):
                self.assertTrue(failures(rows).net, rows)
        self.assertTrue(failures(['Run: collect --root', 'STORE --service-root SERVICE'], surface=heading).net)
        def wrapped(text):
            return textwrap.wrap(text, 40, break_on_hyphens=False, break_long_words=False)
        for name, text in legend:                                                         # a legend row, verbatim, as the page wraps it
            rows = wrapped(name.ljust(12) + text)
            with self.subTest(legend=name):
                self.assertTrue(net_scan(rows), 'the legend row has an operand the net would read')
                self.assertEqual(failures(rows, surface=heading).net_failures(), [])
                self.assertTrue(failures(rows + ['Run: tofu apply PLAN_FILE'], surface=heading).net)      # a sentence added after it
                self.assertTrue(failures(wrapped(name.ljust(12) + text + ' Run: tofu apply PLAN_FILE'), surface=heading).net)
                self.assertTrue(failures(rows, convention=False, surface=heading).net)

    def test_a_net_failure_names_the_token_the_command_word_the_row_the_surface_the_state_and_the_size(self):
        sweep = Sweep()
        sweep.read('queue with items', 'm Queue', (60, 20), [], rows=['  :queue-review-template ownership_unknown NEW_JSON'])
        text = '\n'.join(sweep.net_failures())
        for part in ('NEW_JSON', 'queue-review-template', 'ownership_unknown', 'm Queue', 'queue with items', '60x20'):
            self.assertIn(part, text)

    def test_every_allowlist_entry_has_a_reason_and_excuses_only_the_rows_it_names(self):
        self.assertTrue(NET_ALLOWED)
        for name, states, excuses, reason in NET_ALLOWED:
            self.assertTrue(name and callable(excuses) and len(reason.split()) > 10, name)      # a reason, in words
        words = SYNOPSIS_CONVENTION.split()
        sentence = [' '.join(words[:4]), ' '.join(words[4:]) + '.']                    # the sentence, wrapped over two rows
        usage = ['usage: intune-iac workbench init [-h] --root ROOT --tenant TENANT',
                 '                                 [--journey-mode {simulation,live}] [--atmos-executable ATMOS_EXECUTABLE]',
                 '',
                 'Start the store; init takes --root ROOT.',                        # a description row is still read
                 'options:',
                 '  --root ROOT  the store', ''] + sentence
        sweep = Sweep()
        sweep.text('help', 'intune-iac workbench init --help', (100, 0), '\n'.join(usage))
        self.assertEqual(sorted(sweep.net), [('init', 'ROOT')])                        # only the description row is a hit
        # ROOT and ATMOS_EXECUTABLE of the usage block (TENANT is neither), and ROOT in the first column of the option row
        self.assertEqual(sweep.excused['argparse usage and option rows'], 3)
        error = Sweep()                                                                # a usage error: no blank row after the block
        error.text('usage error', 'intune-iac workbench init', (100, 0), 'usage: intune-iac workbench init [-h] --root ROOT\n'
                   'intune-iac workbench init: error: the following arguments are required: --root, --tenant\n' + '\n'.join(sentence))
        self.assertEqual(error.net_failures(), [])
        other = Sweep()                                                                # the same rows anywhere else are hits
        other.text('selected policy', 'm Queue', (100, 0), '\n'.join(usage))
        self.assertEqual(sorted(other.net), [('--root', 'ROOT'), ('init', 'ROOT'), ('simulation', 'ATMOS_EXECUTABLE')])
        # the help text beside an option is read: only the first column (the option and its metavariable) is the notation
        beside = Sweep()
        beside.text('help', 'intune-iac workbench init --help', (100, 0), 'usage: intune-iac workbench init [-h]\n\noptions:\n'
                    '  --root ROOT  Run: collect --root STORE\n\n' + '\n'.join(sentence))
        self.assertEqual(sorted(beside.net), [('collect', 'STORE')])

    def test_a_usage_block_is_excused_only_where_the_same_output_shows_the_convention_sentence(self):
        """The same usage block, with and without the sentence: a help page and a usage error without it fail, with it pass."""
        block = 'usage: intune-iac workbench init [-h] --root ROOT --service-root SERVICE_ROOT'
        error = 'intune-iac workbench init: error: the following arguments are required: --root'
        sentence = 'Note: %s.' % SYNOPSIS_CONVENTION
        for state, route, text, shown in (
                ('help', 'intune-iac workbench init --help', block + '\n\noptions:\n  -h, --help  show this help\n', False),
                ('usage error', 'intune-iac workbench init', block + '\n' + error, False),
                ('help', 'intune-iac workbench init --help', block + '\n\n' + sentence, True),
                ('usage error', 'intune-iac workbench init', block + '\n' + error + '\n' + sentence, True),
                ('usage error', 'intune-iac workbench init', block + '\n' + error + '\nwords in capitals stand for values', False)):
            with self.subTest(state=state, shown=shown):
                sweep = Sweep()
                sweep.text(state, route, (100, 0), text)
                if shown:
                    self.assertEqual((sweep.net_failures(), sweep.excused['argparse usage and option rows']), ([], 2))
                else:
                    self.assertEqual((sorted(sweep.net), sweep.excused['argparse usage and option rows']),
                                     ([('init', 'ROOT'), ('init', 'SERVICE_ROOT')], 0))
        # a sentence on another surface does not excuse a block: the sentence must be in the output that holds the block
        sweep = Sweep()
        sweep.text('help', 'intune-iac workbench init --help', (100, 0), block)
        sweep.text('help', 'intune-iac start --help', (100, 0), sentence)
        self.assertEqual(sorted(sweep.net), [('init', 'ROOT'), ('init', 'SERVICE_ROOT')])

    def test_id_is_excused_only_as_the_abbreviation_in_a_sentence(self):
        sweep = Sweep()
        sweep.read('state', '9 Repository', (80, 24), [], rows=['select the object ID you want',
                                                                 'It cannot be read from the repository: supply the Intune object ID.'])
        self.assertEqual((sweep.net_failures(), sweep.excused['ID after a noun']), ([], 2))
        for row in ('select ID', 'inspect --object ID', 'workbench workflow --root ROOT --policy ID', 'review the run ID'):
            other = Sweep()
            other.read('state', '9 Repository', (80, 24), [], rows=[row])
            self.assertTrue(other.net, row)                                              # an operand, or after a command word

    def test_a_command_the_product_only_prints_is_found_by_its_lead_or_its_option_alone(self):
        """No table of the product's names the program: `kubectl` is neither run nor an option of the parser."""
        self.assertNotIn('kubectl', command_words())
        for row, expected in (
                ('Run: kubectl apply -f MANIFEST_FILE', [('Run', 'MANIFEST_FILE')]),
                ('run: kubectl apply -f MANIFEST_FILE', [('run', 'MANIFEST_FILE')]),
                ('then type FILE and press Enter', [('type', 'FILE')]),
                ('Use PATH_TO_FILE for the page', [('Use', 'PATH_TO_FILE')]),
                ('kubectl apply -f MANIFEST_FILE', [('-f', 'MANIFEST_FILE')]),                  # no lead: the option and its value
                ('helm install --values VALUES_FILE', [('--values', 'VALUES_FILE')]),
                ('helm install --values=VALUES_FILE', [('--values', 'VALUES_FILE')]),
                ('Try: helm install --values', [])):                                          # the value is on the next row
            with self.subTest(row=row):
                self.assertEqual([(hit.word, hit.token) for hit in net_scan([row])], expected)
        for rows, expected in ((['Try: helm install --values', 'VALUES_FILE'], [('Try', 'VALUES_FILE')]),
                                (['helm install --values', 'VALUES_FILE'], [('--values', 'VALUES_FILE')])):          # wrapped
            self.assertEqual([(hit.word, hit.token) for hit in net_scan(rows)], expected)
        for row in ('kubectl apply -f manifest.yaml', 'Use the file you named', 'type approve', 'the --root option takes a path',
                    'helm install --output json', 'Run it again. FILE is a word.'):
            with self.subTest(row=row):
                self.assertEqual(net_scan([row]), [], row)
        sweep = Sweep()                                                                       # and the failure names the option
        sweep.read('state', '2 Inspector', (60, 20), [], rows=['Copy: kubectl apply -f MANIFEST_FILE'])
        self.assertIn("'MANIFEST_FILE' after the option '-f'", '\n'.join(sweep.net_failures()))

    def test_the_directory_stand_in_and_the_strip_label_are_excused_only_at_their_sites(self):
        from intune_iac.readiness import DIRECTORY_NOT_SHOWN_STEM
        sentence = DIRECTORY_NOT_SHOWN_STEM + '.'

        def net(rows):
            sweep = Sweep()
            sweep.read('state', 'start', (80, 0), [], False, rows)
            return sweep.net
        for rows in (['DIRECTORY | offline | this lists only what this build holds ' + sentence],
                     ['GOAL READINESS: discover (status: unknown) Directory: DIRECTORY', sentence],
                     ['this build holds DIRECTORY', 'is the directory this screen is about; its name is not shown here.']):
            with self.subTest(rows=rows):
                self.assertFalse(net(rows))
        for rows in (['Run: intune-iac catalog DIRECTORY'],                                         # nothing defines the word
                     ['intune-iac catalog DIRECTORY --check-signin azure', sentence],              # a command that carries it
                     ['status: unknown', 'Directory is DIRECTORY']):                               # no sentence on the screen
            with self.subTest(rows=rows):
                self.assertTrue(net(rows), rows)
        strip = 'Line now SYNTHETIC | TENANT 11111111 | POLICY Windows Privacy Pilot (22222222) | OBS stale (later collection incomplete) | REPO stale | OP outcome unknown'
        self.assertTrue(net_scan([strip]))                                                          # a hit, but for the strip's label
        self.assertFalse(net([strip]))
        self.assertEqual(sorted(net(['Collect again: collection REPO'])), [('collection', 'REPO')])


class WorkspaceSweepTests(unittest.TestCase):
    """Each state of a store, every surface, layer and prompt, every size: no command with an unresolved operand."""

    def check(self, name):
        sweep = sweep_state(name)
        # a pass is not a sweep that saw nothing: first, that every surface the state calls for was read at every size
        self.assertEqual(coverage_problems(name, sweep), [], 'the sweep did not read these')
        judge(self, sweep)


def _state_test(name):
    return lambda self: self.check(name)


for _number, _name in enumerate(STATES):
    setattr(WorkspaceSweepTests, 'test_state_%02d_%s' % (_number, re.sub(r'\W+', '_', _name).strip('_')), _state_test(_name))


class StateListTests(unittest.TestCase):
    def test_the_states_are_the_ones_the_brief_names(self):
        words = ' | '.join(STATES)
        for needle in ('empty store', 'no selection', 'selected policy', 'awaiting review', 'awaiting execute', 'lost response',
                       'queue with items', 'needs an object', 'other tenant', 'diagnostics'):
            self.assertIn(needle, words)


class CommandLineSweepTests(unittest.TestCase):
    def check(self, sweep):
        judge(self, sweep)

    def test_start_and_the_catalog_with_no_goal_and_with_each_goal(self):
        sweep = sweep_start_and_catalog()
        self.check(sweep)
        routes_read = {route for (_, route, _) in sweep.coverage}
        for command in ('start', 'catalog'):
            for goal in (None, 'inspect', 'discover', 'adopt', 'change'):
                self.assertIn(command + (' --goal ' + goal if goal else ''), routes_read)

    def test_signin_status_and_collect_with_and_without_account(self):
        sweep = sweep_signin()
        self.check(sweep)
        routes_read = {route for (_, route, *_) in sweep.coverage}
        for route in ('signin collect', 'signin collect --account', 'signin status', 'signin status --account'):
            self.assertIn(route, routes_read)
        states = {state for (state, *_) in sweep.coverage}
        for case in ('collect_partial_expired', 'collect_partial_denied', 'collect_child_fails', 'collect_withheld_full_token',
                     'collect_withheld_shape'):
            self.assertIn(case, states)

    def test_the_workflow_text_the_engineering_view_and_the_interrupted_sentences(self):
        sweep = sweep_workflow_and_engineering()
        self.check(sweep)
        routes_read = {route for (_, route, *_) in sweep.coverage}
        self.assertTrue({'workbench workflow', 'engineering', 'workbench workspace (after Ctrl-C)'} <= routes_read)

    def test_help_and_usage_of_every_route_found_in_the_parser(self):
        sweep = sweep_help_and_usage()
        self.check(sweep)
        from intune_iac import cli
        self.assertGreaterEqual(sweep.routes_read, len(routes(cli.parser())))

    @staticmethod
    def drive_every_text_route():
        for sweep in (sweep_start_and_catalog, sweep_signin, sweep_workflow_and_engineering, sweep_simulate, sweep_check_signin):
            sweep()

    def test_every_leaf_that_prints_text_is_driven_through_cli_main(self):
        """cli.main prints a person's text through _write_text for the leaves that satisfy the conditions around each call. The
        leaves are read from its source, and what the sweeps drove is recorded whenever _write_text runs (recording_routes), so a
        route the sweeps did not reach, however it got its text, is a failure and not a count that still adds up."""
        from intune_iac import cli
        self.drive_every_text_route()
        by_code = text_leaves_by_code(cli.parser())
        driven = {leaf for leaf, count in WRITTEN.items() if count}
        self.assertTrue({('start',), ('catalog',), ('engineering',), ('signin', 'status'), ('signin', 'collect'), ('simulate',),
                         ('workbench', 'workflow'), ('workbench', 'workspace')} <= by_code, sorted(by_code))       # not a vacuous read
        self.assertEqual(sorted(by_code - driven), [],
                         'a leaf prints text through cli._write_text and no sweep drove it through cli.main: drive it')
        self.assertEqual(sorted(driven - by_code), [], 'cli.main printed text for a leaf the analysis of its source did not admit')

    def test_every_parser_leaf_is_text_a_session_or_a_machine_form_and_the_sessions_are_driven(self):
        from intune_iac import cli
        parser = cli.parser()
        leaves = set(leaf_paths(parser))
        text, session = text_leaves_by_code(parser), set(SESSION_LEAVES)
        self.assertTrue(session <= leaves, sorted(session - leaves))
        machine = leaves - text - session
        self.assertEqual(len(text | session | machine), len(leaves))
        self.assertGreater(len(machine), 100)                    # the rest print the JSON document of cli.main; their --help is read above
        self.assertTrue({('doctor',), ('inspect',), ('workbench', 'init'), ('workbench', 'collect')} <= machine)
        self.assertIn('wizard, first run', {state for (state, *_) in sweep_wizards().coverage})
        self.assertTrue(sweep_state('empty store').coverage)

    def test_a_new_leaf_that_prints_text_fails_until_it_is_driven(self):
        """The count of _write_text calls did not move when a leaf was added to a branch that already printed text; the leaves read
        from the source do. A new branch of cli.main that prints text for a leaf of its own is found the same way."""
        from intune_iac import cli
        self.drive_every_text_route()
        parser = cli.parser()
        top = next(item for item in parser._actions if isinstance(item, argparse._SubParsersAction))
        group = next(item for item in top.choices['signin']._actions if isinstance(item, argparse._SubParsersAction))
        group.add_parser('whoami')                               # under the signin branch, which prints text for every signin leaf
        top.add_parser('kube')                                   # a leaf of its own, for a branch that main gains
        source = inspect.getsource(cli.main)
        branch = "        if args.command=='mcp':"
        self.assertIn(branch, source)
        source = source.replace(branch, "        if args.command=='kube':\n            _write_text(['Run: kubectl apply -f MANIFEST_FILE'])\n"
                                        "            return 0\n" + branch, 1)
        by_code = text_leaves_by_code(parser, source)
        driven = {leaf for leaf, count in WRITTEN.items() if count}
        self.assertEqual(sorted(by_code - driven), [('kube',), ('signin', 'whoami')])
        self.assertEqual(inspect.getsource(cli.main).count('_write_text('), source.count('_write_text(') - 1)
        self.assertNotIn(('kube',), text_leaves_by_code(parser))                     # the real main names no such branch

    def test_the_recorder_reads_the_leaf_cli_main_ran_for(self):
        before = WRITTEN[('engineering',)]
        run_cli(['engineering'], 80)
        self.assertEqual(WRITTEN[('engineering',)], before + 1)
        run_cli(['engineering', '--json'], 80)                                         # the machine form prints no text
        run_cli(['engineering', '--help'], 80)
        self.assertEqual(WRITTEN[('engineering',)], before + 1)
        run_cli(['workbench', 'workspace', '--root', '/stores/one'], 80, tty=True, execute={'status': 'interrupted'})
        self.assertGreater(WRITTEN[('workbench', 'workspace')], 0)


class RemainingRouteSweepTests(unittest.TestCase):
    """simulate --format text, start and catalog with --check-signin, and the protected service and adoption views."""

    def test_simulate_text_with_the_documents_its_own_tests_build(self):
        sweep = sweep_simulate()
        judge(self, sweep)
        states = {state for (state, *_) in sweep.coverage}
        self.assertEqual(len(states), 7)                                              # six snapshot documents and the estate route
        for state in states:
            self.assertGreater(sweep.printed[(state, 'simulate --format text')], 10, state)       # the route printed its screen
            self.assertEqual(sweep.printed[(state, 'simulate --format text (stderr)')], 0, state)
        widths = {size[0] for (_, route, size) in sweep.coverage if route == 'simulate --format text (renderer)'}
        self.assertEqual(widths, {60, 80, 120})

    def test_start_and_catalog_with_check_signin_against_the_stubbed_az_and_gh(self):
        sweep = sweep_check_signin()
        judge(self, sweep)
        self.assertEqual(sweep.unmet, [], 'a canned answer whose verdict the screen did not show: the stub was not in effect')
        routes_read = {route for (_, route, *_) in sweep.coverage}
        for provider in ('azure', 'github', 'all'):
            for route in ('start --goal discover', 'start --goal adopt', 'catalog', 'catalog --goal discover'):
                self.assertIn('%s --check-signin %s' % (route, provider), routes_read)
        self.assertGreaterEqual(len({state for (state, *_) in sweep.coverage}), len(signin_cases('c')))

    def test_the_views_behind_the_service_adoption_and_adoption_plan_navigation(self):
        sweep = sweep_protected_views()
        judge(self, sweep)
        for domain, prefix in (('protected service', 'service'), ('protected adoption', 'adoption'),
                               ('adoption recovery plan', 'adoption-plan')):
            for action in ('review', 'status', 'attach', 'cancel', 'recover'):
                tab = 'Plan' if action == 'review' else 'Execution'
                for suffix in ('', ', typed details'):
                    for size in SCHEDULE:
                        label = '%s-%s (%s%s)' % (prefix, action, tab, suffix)
                        self.assertGreater(sweep.coverage[(domain, label, size[0])], 0, (domain, label, size))
            for size in SCHEDULE:
                self.assertGreater(sweep.coverage[(domain, '%s-review (an error response)' % prefix, size[0])], 0, (domain, size))


class LinkedRecordSweepTests(unittest.TestCase):
    """service-link, adoption-link, evidence-link and evidence-history, which no sweep drove before (their journals need docker)."""

    def test_the_four_routes_are_read_in_the_summary_and_the_typed_details_at_every_size(self):
        sweep = sweep_link_views()
        judge(self, sweep)
        labels = {surface for (state, surface, size) in sweep.coverage}
        for route in LINK_ROUTES + ('adoption-history',):
            read = sorted(label for label in labels if label.startswith(route + ','))
            self.assertTrue(any('typed details' in label for label in read) and any('typed details' not in label for label in read), route)
            for label in read:
                for size in SCHEDULE:
                    self.assertGreater(sweep.coverage[('linked records', label, size[0])], 0, (label, size))
        for variant in ('a link already recorded', 'refused: workbench_service_identity', 'refused: workbench_adoption_identity',
                        'refused: workbench_evidence_identity', 'refused: no object selected', 'one entry reopens, one cannot'):
            self.assertTrue(any(variant in label for label in labels), variant)

    def test_a_command_in_a_response_reaches_the_net_on_each_route(self):
        """The routes are read, not only listed: a response that carries a command the product's own renderer does not know is found."""
        sweep = build_link_sweep('Run: tofu apply PLAN_FILE')
        found = {surface.split(',')[0] for held in sweep.net.values() for (_, surface, _) in held['where']
                 if any('PLAN_FILE' in row for row in held['rows'])}
        self.assertEqual(found, set(LINK_ROUTES))

    def test_the_fixtures_are_the_responses_the_products_own_functions_give(self):
        from plugin_tests import link_presentation_fixtures as links
        case = ServiceView()
        case.setUp()
        try:
            self.assertEqual(links.shape_problems(case.store), [])
            by = {(route, variant): response for route, variant, _, response in
                  links.responses(case.store, case.job, case.policy, case.root)}
            for route, kind in (('service-link', 'deployment_receipt'), ('adoption-link', 'adoption_receipt'),
                                ('evidence-link', 'deployment_receipt')):
                row = by[(route, 'a new link')]
                self.assertEqual((row['kind'], row['created'], row['evidence_class']), (kind, True, 'caller_asserted_artifact'), route)
            self.assertIs(by[('service-link', 'a link already recorded')]['created'], False)
            history = by[('evidence-history', 'one entry reopens, one cannot')]
            self.assertEqual([entry['status'] for entry in history['entries']], ['recorded', 'unavailable'])
            self.assertEqual(history['schema_version'], 'workbench-worker-evidence-history/1')
            self.assertTrue(history['entries'][1]['error_code'])
            self.assertEqual([entry['status'] for entry in by[('adoption-history', 'one linked operation that cannot be reopened')]
                              ['operations']], ['unknown'])
        finally:
            case.doCleanups()


class WizardSweepTests(unittest.TestCase):
    def test_the_prompts_and_lines_of_the_wizard_the_guided_workflow_and_the_journey(self):
        sweep = sweep_wizards()
        judge(self, sweep)
        states = {state for (state, *_) in sweep.coverage}
        for name in ('wizard, first run', 'wizard, repository-owned edit handed off', 'wizard, output conflict',
                     'guided workflow, repository-owned edit handed off', 'journey, a whole run',
                     'journey, repository-owned edit handed off, back and edit'):
            self.assertIn(name, states)

    def test_the_sessions_reached_the_prompts_that_name_a_command(self):
        sweep = sweep_wizards()
        routes_read = {route for (_, route, *_) in sweep.coverage}
        for route in ('wizard (prompt)', 'wizard (line)', 'wizard --guided (prompt)', 'wizard --journey (prompt)'):
            self.assertIn(route, routes_read)


if __name__ == '__main__':
    unittest.main()
