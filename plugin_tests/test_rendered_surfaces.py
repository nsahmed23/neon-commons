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
    --check-signin, with az and gh stubbed as the sign-in tests stub them (FakeClis; no real tool, no network): each canned answer has a
    result of its own that every run (route, directory, width) must show, and the fake's log must hold exactly the calls the provider
    means, so a stub that was not in effect for one run is a failure and not a pass of the others. The views behind
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
rows), and only on a page that also shows the convention sentence (SYNOPSIS_CONVENTION of test_template_words): words in capitals
there are metavariables, and the sentence says so. A page is the rows on screen at one scroll position at one size, so a sentence on
the first page of a long listing licenses nothing on the second. Nothing else is allowed. Until a page shows the sentence, the
synopses on it fail.
An argparse usage block (the `usage:` rows of --help and of a usage error) is allowed on the same condition, with the whole output
as the unit (it is not paged): only in an output that itself shows the sentence. The sweep of every route's --help and usage error
fails for each output that prints a block without it.

A second check, the independent net, does not use the reader's context rules: a form the reader misses is missed by the renderer
and by the check above alike. In every visual block of every surface, help included (a command wrapped over rows is one command; a
sentence, a blank row, a list item and a list's heading end it), a token that is a member of entry.FILL_IN_TEMPLATES, or is shaped
like a placeholder (capitals and digits with an underscore, or a bare FILE, PATH, ROOT, ID, NAME, VALUE, STAGE, FIELD, SERVICE,
REVISION, COMMIT, REPO, DIGEST, STORE, POLICY, DIRECTORY, SUBSCRIPTION, USER or ACCOUNT), after a word the product's own tables name
as a command, is a hit. The command words are the product's tables and the external programs it prints commands for (az, gh, tofu
and git today), which external_programs derives from the product's source, never from a list here. Two readings need no table, so a
program the product only prints is found too: a placeholder after a lead (run, type, use, try: `Run: kubectl apply -f MANIFEST_FILE`)
and a placeholder right after an option (`-f MANIFEST_FILE`, `--root STORE`). On the help surfaces a hit is
excused only inside a synopsis the product writes verbatim, on a page that shows the convention sentence (every page that shows the
row, for a row two pages repeat). Its other false
positives are the entries of NET_ALLOWED, each with its reason. Both checks are reported.

Every exception, in both checks, is an exact allowed text matched by span, with the surface or route it holds on: a hit carries its own
span in the text of its visual block, and it is excused only when that span lies inside the span of the allowed text. Allowed text
elsewhere in the block, on the screen or in the output excuses nothing (a `--root ROOT  Run: kubectl apply ROOT` row has one allowed
ROOT and one hit; so has `Run: kubectl inspect object ID. its object ID cannot be read from the repository`). The reader judges a
synopsis place by place for the same reason (synopsis_verdict).
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


Hit = collections.namedtuple('Hit', 'index word token previous shown exact block begin end')
# A visual block as the net reads it: the rows' indexes, their whitespace-collapsed parts, the parts joined by single spaces (text) and
# where each part starts in it (bases). Every hit carries its own span in the text of its block, and so does every exception: a hit
# is excused only when its span lies inside the span of the exact text an exception allows (see NET_ALLOWED).
Block = collections.namedtuple('Block', 'indexes parts text bases')
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


def blocks_of(rows):
    """[Block] for the rows of one rendered output: the visual blocks, each joined as a person reads it (see Block)."""
    found = []
    for indexes in visual_blocks(rows):
        parts = [' '.join(rows[index].split()) for index in indexes]
        parts = [part[:-1].rstrip() if part.endswith('\\') else part for part in parts]
        text, bases = '', []
        for part in parts:
            text += (' ' if text else '') + part
            bases.append(len(text) - len(part))
        found.append(Block(indexes, parts, text, bases))
    return found


def row_span(block, index):
    """The span in the text of a block of one of its rows."""
    number = block.indexes.index(index)
    return block.bases[number], block.bases[number] + len(block.parts[number])


def rows_in(block, begin, end):
    """The indexes of the rows of a block that a span of its text runs over."""
    return [index for number, index in enumerate(block.indexes)
            if block.bases[number] < end and block.bases[number] + len(block.parts[number]) > begin]


def net_scan(rows, synopses=False):
    """[Hit] for the rows of one rendered output: each placeholder-like token that has a command word before it.

    The word is carried over the rows of a visual block, so a command wrapped over rows (`Run: collect --root` and then
    `STORE --service-root SERVICE`) or continued with a backslash is one command, and a token is judged against the nearest command
    word before it wherever the wrap put that word. A sentence ends the command, wherever in a row it ends, so prose that follows it
    is not read as the command's operands; the segments of an absolute path are not command words (a placeholder in one still is a
    hit). A hit carries the row of its token (index), the word right before it (previous), the rows the command spans as one text
    (shown), its block and its own span in the text of that block (begin, end), and whether that span lies inside a synopsis the
    product writes verbatim (exact; only looked for when `synopses` is true, which is the help surfaces)."""
    commands, hits = command_words(), []
    for block in blocks_of(rows):
        indexes, parts, text, bases = block
        spans = exact_spans(text) if synopses else ()
        last = before = origin = where = None
        for number, part in enumerate(parts):
            breaks = [found.end() for found in BREAKS.finditer(part)]
            paths = [found.span() for found in PATHS.finditer(part)]
            for found in WORDS.finditer(part):
                while breaks and found.start() >= breaks[0]:
                    breaks.pop(0)
                    last = before = origin = where = None
                word = found.group().strip('.:!?*')
                if not word:
                    continue
                if placeholder_like(word) and (last is not None or OPTION.match(before or '')):
                    begin = bases[number] + found.start() + found.group().find(word)
                    anchor, first = (last, origin) if last is not None else (before, where)
                    hits.append(Hit(indexes[number], anchor, word, before, ' '.join(parts[first:number + 1]),
                                    any(a <= begin and begin + len(word) <= b for a, b in spans), block, begin, begin + len(word)))
                elif (word in commands or word.lower() in LEADS) and not any(a <= found.start() < b for a, b in paths):
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


def argparse_spans(rows, block):
    """The spans an argparse output allows, in an output that also shows the convention sentence (without it the metavariables are
    unresolved operands like any other): each row of a usage block, whole, and the first column of each row of an option section (the
    option and its metavariable), and nothing beside the column. The help text after it is still read, so `--root ROOT  Run: kubectl
    apply ROOT` has one allowed ROOT and one hit."""
    if not shows_convention(rows):
        return []
    usage, section = usage_rows(rows), section_rows(rows)
    spans = []
    for index in block.indexes:
        begin, end = row_span(block, index)
        if index in usage:
            spans.append((begin, end))
        elif index in section:
            spans.append((begin, begin + len(' '.join(first_column(rows[index])))))
    return spans


def phrase_spans(noun, phrases):
    """An entry's spans: the ID of `noun ID` inside each occurrence of an exact phrase the product prints. The hit itself must be that
    ID, so another `noun ID` in the same block, before or after the phrase, is not licensed by it."""
    assert all(noun + ' ID' in phrase for phrase in phrases), (noun, phrases)

    def spans(rows, block):
        found = []
        for phrase in phrases:
            at = phrase.index(noun + ' ID') + len(noun) + 1
            start = block.text.find(phrase)
            while start != -1:
                found.append((start + at, start + at + len('ID')))
                start = block.text.find(phrase, start + 1)
        return found
    return spans


def directory_spans(rows, block):
    """The spans of DIRECTORY that stand in for a directory name the screen does not show: the word that begins the exact defining
    sentence (readiness.DIRECTORY_NOT_SHOWN_STEM) where the product starts it, at the start of a row or in a bracket, and the word of
    a row that is exactly the label `Directory: DIRECTORY`. The same words inside a command row are neither."""
    from intune_iac.readiness import DIRECTORY_NOT_SHOWN_STEM
    found, starts = [], set(block.bases)
    start = block.text.find(DIRECTORY_NOT_SHOWN_STEM)
    while start != -1:
        if start in starts or block.text[start - 1:start] == '(':
            found.append((start, start + len('DIRECTORY')))
        start = block.text.find(DIRECTORY_NOT_SHOWN_STEM, start + 1)
    for part, base in zip(block.parts, block.bases):
        if part == 'Directory: DIRECTORY':
            found.append((base + len('Directory: '), base + len(part)))
    return found


@functools.lru_cache(maxsize=1)
def strip_patterns():
    """The strip as the product writes it, for the REPO label: `MODE | TENANT id | POLICY name (id) | OBS word | REPO word | OP word`
    (the legend's `Line now`, with its optional segments dropped at small sizes), and the line of the states the strip left out
    (`Hidden in the strip at this size (+2 more):` then `OBS word | REPO word`). The state words are the product's own."""
    from intune_iac.workbench_screens import HAZARD_STATES, SHORT_STATES
    from intune_iac.workbench_tui import REPOSITORY_FROM_CHECK, REPOSITORY_FROM_SIGNAL
    states = set(REPOSITORY_FROM_CHECK.values()) | set(REPOSITORY_FROM_SIGNAL.values()) | set(HAZARD_STATES['REPOSITORY']) | {'not checked'}
    states |= {SHORT_STATES[state] for state in states if state in SHORT_STATES}
    word = '(?:%s)' % '|'.join(re.escape(state) for state in sorted(states, key=len, reverse=True))
    end = r'(?= \||\Z| (?=[A-Z+!]))'
    head = r'(?<![\w-])(?:Line now )?[A-Z][A-Z -]*? \| (?:TENANT|T) \S+(?: \| (?:POLICY [^|]+?|no policy))?(?: \| OBS [^|]+?)?'
    return (re.compile(head + r' \| (REPO) ' + word + end),
            re.compile(r'Hidden in the strip at this size \(\+\d+ more\): (?:OBS [^|]+? \| )?(REPO) ' + word + end))


def strip_spans(rows, block):
    """The spans of the word REPO that label the repository state inside a strip the product writes (see strip_patterns): a strip
    that begins with its mode and tenant and holds only strip segments up to the label. `Run: kubectl apply | REPO stale` is not one."""
    return [found.span(1) for pattern in strip_patterns() for found in pattern.finditer(block.text)]


Allowed = collections.namedtuple('Allowed', 'name states surfaces spans reason')

# The net's exceptions: one entry each, and every one is an exact allowed text matched by span. states: the states it applies to, None
# for any. surfaces: the prefixes of the surfaces it applies to, None for any (a named site). spans(rows, block): the spans in the text
# of a visual block of the exact text it allows. A hit is excused only when its own span lies inside one of them, so allowed text
# elsewhere in the block, on the screen or in the output excuses nothing. reason: why it is not a defect. There is no other allowance.
NET_ALLOWED = tuple(Allowed(*entry) for entry in (
    ('argparse usage and option rows', ('help', 'usage error'), None, argparse_spans,
     "argparse writes the parser's own synopsis with each option's metavariable (--root ROOT, --service-root SERVICE_ROOT), and "
     "lists each option with its metavariable in its first column: the standard notation of a command line, generated from the "
     "parser, printed by --help or after a usage error and never as a step to copy. Its choices can even be command words "
     "({simulation,live}). It is excused only in an output that also shows the convention sentence (SYNOPSIS_CONVENTION), as a "
     "synopsis is on the help page: without the sentence a reader cannot tell a metavariable from an operand left unresolved. Only "
     "the span of a usage row or of a first column is allowed; the help text beside each option is still read."),
    ('object ID in the repository entry', None, (':repository-entry',),
     phrase_spans('object', ('its object ID cannot be read from the repository', 'the Intune object ID it manages')),
     "The repository-entry candidate whose key does not encode the policy's object says, in two exact sentences of "
     "repository_entry.py:146-148, that `its object ID cannot be read from the repository` and to supply `the Intune object ID it "
     "manages`: ID is the abbreviation of identifier in a sentence, not a placeholder. Only the ID inside those phrases, on the "
     "repository-entry surfaces; any other `... ID`, a `review operation ID` among them, is an operand or a new sentence, and stays a hit."),
    ('commit ID in the actions layer', None, ('a Actions',),
     phrase_spans('commit', ('the full 40-character commit ID',)),
     "The actions layer says what the repository refresh needs, `the full 40-character commit ID` (the needs row, and the staged "
     "instruction of workbench_tui.py:2489): ID is the abbreviation of identifier in a sentence, not a placeholder. Only the ID inside "
     "that phrase, on the actions layer; any other `... ID` stays a hit."),
    ('object ID in the refusal for no selection', None, ('evidence-history, refused: no object selected',),
     phrase_spans('object', ('Select an exact immutable object ID first',)),
     "The typed details of a refusal print the engine's own message, and for selection_required that is `Select an exact immutable "
     "object ID first.` (workbench.py, raised where a link or history command needs a selected policy): ID is the abbreviation of "
     "identifier in a sentence, not a placeholder. Only the ID inside that sentence, on the typed details of the refused "
     "evidence-history that the link sweep drives; any other `... ID` stays a hit."),
    ('directory stand-in', None, ('start', 'catalog'), directory_spans,
     "A directory whose name a start or catalog screen must not print (a credential shape, a control character) is named DIRECTORY "
     "(entry.py:917), and the screen defines the word in the exact sentence readiness.DIRECTORY_NOT_SHOWN_STEM, which begins with it, "
     "or prints the exact row `Directory: DIRECTORY`. Only the DIRECTORY that begins that sentence where the product starts it, and "
     "the one in that row, are allowed; a command that carries the word as an operand is a hit, whatever the screen defines."),
    ('strip label', None, None, strip_spans,
     "The strip under the tabs names the repository state REPO, and the help legend prints the strip as it reads now and, at a small "
     "size, the line of the states the strip left out (`OBS stale (later collection incomplete) | REPO stale`). REPO there is the "
     "label of a state, not the operand of the word collection before it, which is ordinary English there. Only the REPO of a strip "
     "or of that line, as the product writes them (strip_patterns), is allowed; the same words after a command are a hit."),
))


def net_excuse(state, surface, rows, hit, memo=None):
    """The name of the exception that allows the span of a hit, or None. memo: a dict that keeps an entry's spans for a block."""
    memo = {} if memo is None else memo
    for entry in NET_ALLOWED:
        if (entry.states is None or state in entry.states) and (entry.surfaces is None or surface.startswith(entry.surfaces)):
            key = (entry.name, hit.block.indexes[0])
            if key not in memo:
                memo[key] = entry.spans(rows, hit.block)
            if any(begin <= hit.begin and hit.end <= end for begin, end in memo[key]):
                return entry.name
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


def occurrences(blocks, command):
    """[(block, begin, end)] for every place the text of a command is printed, found in the visual blocks joined as a person reads
    them, so a command wrapped over rows (or pages) is one place."""
    wanted = ' '.join(command.split())
    found = []
    for block in blocks if wanted else ():
        start = block.text.find(wanted)
        while start != -1:
            found.append((block, start, start + len(wanted)))
            start = block.text.find(wanted, start + 1)
    return found


def synopsis_verdict(command, blocks, shown, convention, spans=None):
    """Judge, place by place, a command the reader found on a help surface whose text is part of a synopsis the product writes.
    'excused': every place it is printed lies inside a synopsis the product writes verbatim (exact_spans), on rows whose pages show
    the convention sentence (shown, as net_input gives it). 'unlicensed': it lies inside one, on a page without the sentence.
    'found': some place is not a synopsis at all, an instruction or a sentence that happens to use the same words, or the command
    cannot be placed in the rows, so it is read like any other. Only a caller that gives no rows' flags (a test of the reader alone)
    gets the whole screen's judgment (convention). blocks: blocks_of(rows); spans: a dict that keeps exact_spans for a block."""
    if shown is None:
        return 'excused' if convention else 'unlicensed'
    places = occurrences(blocks, command)
    if not places:
        return 'found'
    verdict, spans = 'excused', {} if spans is None else spans
    for block, begin, end in places:
        if block.indexes[0] not in spans:
            spans[block.indexes[0]] = exact_spans(block.text)
        if not any(a <= begin and end <= b for a, b in spans[block.indexes[0]]):
            return 'found'
        if not all(shown[index] for index in rows_in(block, begin, end)):
            verdict = 'unlicensed'
    return verdict


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
        self.synopses = collections.OrderedDict()              # a synopsis read on a help surface where a page lacks the sentence
        self.coverage = collections.Counter()                  # (state, surface, size) -> screens read
        self.net = collections.OrderedDict()                   # (command word, token) -> {'where': {...}, 'rows': {...}}
        self.excused = collections.Counter()                   # allowlist entry -> hits it excused
        self.printed = collections.Counter()                   # (state, route) -> rows a route printed (a route that prints nothing
                                                               # is not a sweep)

    def cast(self, state, surface, size, rows, convention=False, shown=None):
        """The independent net over the rows of one screen, on every surface. On a help surface the synopses the product writes
        verbatim are excused (exact_spans), row by row and only where the page that shows the row shows the convention sentence
        (shown, one flag a row, as net_input gives it; without it, convention for the whole screen); nothing else on it is."""
        seen, memo = set(), {}
        for hit in net_scan(rows, synopses=surface in HELP_SURFACES):
            if (hit.index, hit.begin) in seen:                       # an occurrence is judged once, and only on its own account
                continue
            seen.add((hit.index, hit.begin))
            licensed = convention if shown is None else shown[hit.index]
            reason = 'exact synopsis' if hit.exact and licensed else net_excuse(state, surface, rows, hit, memo)
            if reason:
                self.excused[reason] += 1
                continue
            held = self.net.setdefault((hit.word, hit.token), {'where': set(), 'rows': set(), 'unlicensed': set()})
            held['where'].add((state, surface, size))
            held['rows'].add(scrubbed(hit.shown))
            if hit.exact:
                held['unlicensed'].add((state, surface, size))        # a synopsis the product writes, on a page without the sentence

    def read(self, state, surface, size, texts, convention=False, rows=(), shown=None):
        """Judge the texts of one screen. convention: every page of the surface shows SYNOPSIS_CONVENTION. rows: the rows as printed,
        for the net; shown: for each row, whether every page that shows it shows the sentence (net_input). Both checks excuse a
        synopsis by the page it is on and only for the occurrence that is one: the net hit by hit (its span inside an exact
        synopsis, on a shown row), the reader place by place (synopsis_verdict); without shown, by convention for the whole screen."""
        self.coverage[(state, surface, size)] += 1
        self.cast(state, surface, size, rows, convention, shown)
        seen, blocks, spans = set(), None, {}
        for text in texts:
            for command, operands in unresolved(text):
                if (command, tuple(operands)) in seen:
                    continue
                seen.add((command, tuple(operands)))
                verdict = 'found'
                if surface in HELP_SURFACES and is_synopsis(command):
                    blocks = blocks_of(rows) if blocks is None else blocks
                    verdict = synopsis_verdict(command, blocks, shown, convention, spans)
                if verdict == 'excused':
                    continue
                table = self.synopses if verdict == 'unlicensed' else self.found
                table.setdefault((command, tuple(operands)), set()).add((state, surface, size))

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
                bare = [size for size in sizes if (state, surface, size) in held.get('unlicensed', ())]
                lines.append('    on %r, in state %r, at %s%s' % (
                    surface, state, ' '.join(size_word(s) for s in sizes),
                    ' (a synopsis the product writes, on a page without the convention sentence at %s)' % ' '.join(size_word(s) for s in bare)
                    if bare else ''))
        return lines

    def failures(self):
        """The failure lines: one per command, naming every surface, state and size it was printed on."""
        lines = []
        for table, why in ((self.found, 'a command with an unresolved operand'),
                           (self.synopses, 'a synopsis on a help page without "%s"' % SYNOPSIS_CONVENTION)):
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
            mine = self.net.setdefault(item, {'where': set(), 'rows': set(), 'unlicensed': set()})
            mine['where'] |= held['where']
            mine['rows'] |= held['rows']
            mine['unlicensed'] |= held.get('unlicensed', set())
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


def body_owners(pages):
    """The body rows of all the pages of a surface as one list, each row once, and for each row the numbers of the pages that show
    it. The last page of a scroll is drawn from the row that fills it, so it repeats the rows it shares with the page before it; the
    offset of each page says how many, and a repeated row is shown by both pages."""
    rows, owners, end = [], [], 0
    for number, page in enumerate(pages):
        repeated = max(0, end - page.offset)
        for index in range(len(rows) - repeated, len(rows)):
            owners[index].add(number)
        rows += page.body[repeated:]
        owners += [{number} for _ in page.body[repeated:]]
        end = max(end, page.offset + len(page.body))
    return rows, owners


def whole_body(pages):
    """The body rows of all the pages of a surface as one list, each row once (see body_owners)."""
    return body_owners(pages)[0]


def page_shows(page):
    """Whether one page, the rows on screen at its scroll position at its size (above the box, in it and below it), shows the
    convention sentence."""
    return shows_convention(page.above + page.body + page.below)


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


def net_input(pages, layer, licensed=True):
    """(rows, shown): the rows the net reads, in the groups screen_texts reads: the chrome above and below the box of each page, and
    the body (its pages joined, each row once, unless the layer pages by commands). A blank row ends each group, so no visual block
    runs over from one group into the next. shown, for each row, says whether every page that shows the row also shows the
    convention sentence (None when licensed is false): a synopsis is excused page by page, not by the surface."""
    rows, owners = [], []
    for number, page in enumerate(pages):
        for row in page.above + page.below:                  # the chrome (title, tabs, strip, band, status, keys): each row is a line
            rows += [row, '']                                # of its own, so a blank row after it keeps the next from joining it
            owners += [{number}, set()]
    if layer in ('catalog', 'workflow'):
        for number, page in enumerate(pages):
            rows += page.body + ['']
            owners += [{number} for _ in page.body] + [set()]
    else:
        body, who = body_owners(pages)
        rows += body + ['']
        owners += who + [set()]
    if not licensed:
        return rows, None
    sentence = [page_shows(page) for page in pages]
    return rows, [all(sentence[number] for number in row) for row in owners]


def net_rows(pages, layer):
    """The rows the net reads (see net_input)."""
    return net_input(pages, layer, licensed=False)[0]


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
        helping = label in HELP_SURFACES
        rows, shown = net_input(pages, layer, licensed=helping)
        # A synopsis is excused per page, by both checks: by the pages that show the row it is in (net_input's flags).
        sweep.read(state, label, size, screen_texts(pages, layer), helping and all(page_shows(page) for page in pages), rows, shown)


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


SigninCase = collections.namedtuple('SigninCase', 'label provider azure github expect bare catalog', defaults=(None,))
OTHER_TENANT = '55555555-5555-4555-8555-555555555555'
# What the product asks of each CLI, in the arguments the fake logs (it logs the arguments, one line a call, not the tool): one call to
# each tool the provider names, nothing else.
EXPECTED_CALLS = {'azure': ['account list --output json'], 'github': ['auth status --json hosts'],
                  'all': ['account list --output json', 'auth status --json hosts']}


def signin_cases(context):
    """[SigninCase] for start and catalog --check-signin: the canned answers of the fake az and gh (the ones the sign-in tests give
    them, plugin_tests/signin_fakes.py; nothing real runs), and what every screen of the case must show. expect: phrases that hold in a
    directory with the example context; bare: those that hold in a directory with none (None when the case is not run there); catalog:
    the phrases of the catalog routes where they differ (the catalog screen shows the Azure verdict, and the GitHub one only when it
    blocks: the gh call is made and logged, and when gh is signed in, or beside Azure under `all`, the screen does not show it). Each
    phrase comes from the canned answer or the product's verdict on it, so a screen that shows it was made from that answer: a fake
    that was not invoked, or answered 127, shows none of them."""
    from plugin_tests.signin_fakes import azure_account, azure_list, github_hosts

    def az(*accounts, **extra):
        return dict(out=azure_list(*accounts), **extra)

    def gh(*entries, **extra):
        return dict(out=github_hosts(*entries), **extra)
    octo = ('github.com', 'octo-user', 'success', True)
    nobody = dict(out='', err='You are not logged into any GitHub hosts.', code=1)
    return (
        SigninCase('azure: signed in to the context tenant', 'azure', az(azure_account(tenant=context)), None,
                   ('Signed in to tenant %s as alex@example.test (AzureCloud)' % context,), ('Signed in to tenant %s' % context,)),
        SigninCase('azure: signed in to another tenant', 'azure', az(azure_account(tenant=OTHER_TENANT)), None,
                   ('Sign in to the tenant the context names', OTHER_TENANT), ('Signed in to tenant %s' % OTHER_TENANT,)),
        SigninCase('azure: several accounts in the tenant', 'azure',
                   az(azure_account(tenant=context), azure_account(tenant=context, user='sam@example.test', default=False)), None,
                   ('Several accounts are signed in', 'sam@example.test'), None),
        SigninCase('azure: not signed in', 'azure', az(), None, ('Not signed in to Azure',), None),
        SigninCase('azure: an answer that is not a listing', 'azure', dict(out='this is not json'), None,
                   ('could not be determined', 'malformed_answer'), None),
        SigninCase('azure: only an expired subscription', 'azure', az(azure_account(tenant=context, state='Expired')), None,
                   ('lists the subscription as Expired', 'alex@example.test'), None),
        SigninCase('azure: the CLI fails', 'azure', None, None, ('command_failed',), None),
        SigninCase('github: signed in', 'github', None, gh(octo), ('Signed in to github.com', 'octo-user'), None, catalog=()),
        SigninCase('github: several accounts', 'github', None, gh(octo, ('github.com', 'other-user', 'success', False)),
                   ('Several accounts are listed for one host',
                    'octo-user (gh state: success, active), other-user (gh state: success)'), None),
        SigninCase('github: an error state', 'github', None, gh(('github.com', 'octo-user', 'error', True)),
                   ('gh_state_error', 'octo-user (gh state: error)'), None),
        SigninCase('github: not logged in', 'github', None, nobody, ('Not signed in to GitHub',), None),
        SigninCase('both: signed in to each', 'all', az(azure_account(tenant=context)), gh(octo),
                   ('as alex@example.test (AzureCloud)', 'Signed in to github.com', 'octo-user'), None,
                   catalog=('as alex@example.test (AzureCloud)',)),
        SigninCase('both: another tenant and not logged in', 'all', az(azure_account(tenant=OTHER_TENANT)), nobody,
                   ('Sign in to the tenant the context names', OTHER_TENANT, 'Not signed in to GitHub'), None,
                   catalog=('Sign in to the tenant the context names', OTHER_TENANT)),
    )


def run_signin_case(sweep, case, folders, effective=True):
    """Run start and catalog with --check-signin for one case in each folder, and judge each run on its own: the screen shows every
    phrase the case expects for that directory, and the fake log shows exactly the calls the provider means. effective=False leaves
    the fakes off the search path (and the real tools too: the path holds an empty directory only), to show a stub that is not in
    effect is found."""
    from plugin_tests.signin_fakes import FakeClis
    fakes = FakeClis()
    try:
        for tool, first, second, answer in (('az', 'account', 'list', case.azure), ('gh', 'auth', 'status', case.github)):
            if answer is not None:
                fakes.answer(tool, first, second, **answer)
        with tempfile.TemporaryDirectory() as nothing:
            path = fakes.path_entry() if effective else nothing
            with patch.dict(os.environ, {'PATH': path + os.pathsep + os.environ.get('PATH', '') if effective else path}):
                for folder, name, wanted in folders:
                    runs = [(['start', str(folder), '--goal', goal, '--check-signin', case.provider], 'start --goal %s' % goal)
                            for goal in ('discover', 'adopt')]
                    runs += [(['catalog', str(folder), '--check-signin', case.provider], 'catalog'),
                             (['catalog', str(folder), '--goal', 'discover', '--check-signin', case.provider], 'catalog --goal discover')]
                    for argv, route in runs:
                        for width in (120, 60):
                            before = len(fakes.calls())
                            code, text, err = run_cli(argv, width)
                            calls = fakes.calls()[before:]
                            state, label = '%s; %s' % (case.label, name), '%s --check-signin %s' % (route, case.provider)
                            sweep.text(state, label, (width, 0), text)
                            sweep.text(state, label + ' (stderr)', (width, 0), err)
                            shown = ' '.join(text.split())
                            here = case.catalog if case.catalog is not None and route.startswith('catalog') and wanted == case.expect else wanted
                            missing = [phrase for phrase in here if phrase not in shown]
                            if missing:
                                sweep.unmet.append((case.label, name, label, width, missing))
                            if sorted(calls) != sorted(EXPECTED_CALLS[case.provider]):
                                sweep.badcalls.append((case.label, name, label, width, calls))
                            sweep.signin_runs += 1
    finally:
        fakes.cleanup()


@functools.lru_cache(maxsize=1)
def sweep_check_signin():
    """start --goal G --check-signin P and catalog --check-signin P (with and without a goal), with the az and gh the sign-in tests
    stub (FakeClis: canned answers on a temporary search path, no real tool, no network), for every case of signin_cases, in a
    directory that holds the example context and (for the two cases that compare tenants) in one that holds none, at two widths. Each
    run is judged on its own: sweep.unmet lists a run whose screen lacks a phrase its case expects (the stub was not in effect for
    that route, directory or width), sweep.badcalls a run whose fake log is not exactly the calls the provider means."""
    sweep = Sweep()
    sweep.unmet, sweep.badcalls, sweep.signin_runs = [], [], 0
    root = Path(__file__).resolve().parents[1]
    context = json.loads((root / 'examples/context.json').read_text())['tenant_id']
    with tempfile.TemporaryDirectory() as temp:
        with_context, bare = Path(temp) / 'estate dir', Path(temp) / 'bare'
        with_context.mkdir()
        bare.mkdir()
        shutil.copyfile(root / 'examples/context.json', with_context / 'context.json')
        for case in signin_cases(context):
            folders = [(with_context, 'a context', case.expect)] + ([(bare, 'no context', case.bare)] if case.bare else [])
            run_signin_case(sweep, case, folders)
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
        # which pages show each row, and whether they all show the sentence: the chrome by its own page, a body row by every page
        # that shows it (the last page repeats e and f)
        self.assertEqual(body_owners(pages)[1], [{0}, {0}, {0}, {1}, {1, 2}, {1, 2}, {2}])
        said = Page(['A1', SYNOPSIS_CONVENTION], ['d', 'e', 'f'], ['C1'], True, 3)
        rows, shown = net_input([pages[0], said, pages[2]], 'details')
        self.assertEqual(len(rows), len(shown))
        self.assertEqual(sorted({row for row, ok in zip(rows, shown) if ok and row}), sorted(['A1', 'C1', 'd', SYNOPSIS_CONVENTION]))
        self.assertEqual(sorted({row for row, ok in zip(rows, shown) if not ok and row}), ['A1', 'C1', 'a', 'b', 'c', 'e', 'f', 'g'])
        self.assertIsNone(net_input(pages, 'details', licensed=False)[1])

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

    def test_a_synopsis_is_excused_only_on_a_page_that_shows_the_convention_sentence(self):
        """The excuse is the page's, not the surface's: a help surface whose sentence is only on page 1 fails on page 2."""
        listing, legend, keys = synopsis_sources()
        # an item both checks read: the net as an exact entry with operands, the reader as a command that is a synopsis
        entry = next(entry for entry in sorted(listing) if len(entry.split()) >= 3 and net_scan(['1. ' + entry])
                     and unresolved('1. ' + entry) and all(is_synopsis(command) for command, _ in unresolved('1. ' + entry)))
        surface = '? Help, typed details (e)'

        def read(pages, layer='details'):
            rows, shown = net_input(pages, layer)
            sweep = Sweep()
            sweep.read('state', surface, (80, 24), screen_texts(pages, layer), all(page_shows(page) for page in pages), rows, shown)
            return sweep
        # page 1 carries the sentence in its body, as the typed listing prints it; page 2 carries a second item and no sentence
        first = Page(['TITLE'], [SYNOPSIS_CONVENTION, '', '1. ' + entry], ['STATUS'], True, 0)
        second = Page(['TITLE'], ['2. ' + entry], ['STATUS'], False, 3)
        self.assertEqual((page_shows(first), page_shows(second)), (True, False))
        sweep = read([first, second])
        text = '\n'.join(sweep.net_failures())
        self.assertTrue(sweep.excused['exact synopsis'])                                  # the item on page 1 is excused
        self.assertIn("in the row '2. ", text)                                            # the same item on page 2 is a hit
        self.assertNotIn("in the row '1. ", text)
        self.assertIn('on a page without the convention sentence at 80x24', text)         # and the failure says why
        self.assertTrue(sweep.synopses)                                                   # the reader holds the page 2 item to it too
        self.assertEqual(read([first]).net_failures() + read([first]).failures(), [])     # page 1 alone is clean in both checks
        # a page without the sentence that holds no synopsis does not take the licence from the page that does
        bare = read([first, Page(['TITLE'], ['maintenance  (12)'], ['STATUS'], False, 3)])
        self.assertEqual(bare.net_failures() + bare.failures(), [])
        # the sentence in a fixed row on page 2 (below the box, wrapped as a narrow window wraps it) licenses it
        words = SYNOPSIS_CONVENTION.split()
        fixed = Page(['TITLE'], ['2. ' + entry], ['STATUS', ' '.join(words[:3]), ' '.join(words[3:])], False, 3)
        self.assertTrue(page_shows(fixed))
        self.assertEqual(read([first, fixed]).net_failures() + read([first, fixed]).failures(), [])
        # an item that runs over the page boundary: the part on page 1 is excused, the part on page 2 is not
        halves = None
        for candidate in sorted(listing):
            parts = candidate.split()
            for at in range(1, len(parts)):
                hits = net_scan(['7. ' + ' '.join(parts[:at]), ' '.join(parts[at:])])
                before, after = {h.token for h in hits if h.index == 0}, {h.token for h in hits if h.index == 1}
                if before and after and not before & after:
                    halves = (' '.join(parts[:at]), ' '.join(parts[at:]), before, after)
                    break
            if halves:
                break
        self.assertTrue(halves, 'an entry with an operand on each side of a break')
        left, right, on_first, on_second = halves
        sweep = read([Page(['TITLE'], [SYNOPSIS_CONVENTION, '', '7. ' + left], ['STATUS'], True, 0),
                      Page(['TITLE'], [right], ['STATUS'], False, 3)])
        self.assertEqual({token for (_, token) in sweep.net}, on_second)                   # only what is on the page without the sentence
        self.assertTrue(sweep.excused['exact synopsis'])
        # a row two pages repeat (the last page of a scroll) is licensed only if both pages show the sentence
        said = Page(['TITLE', SYNOPSIS_CONVENTION], ['filler', '1. ' + entry], [], True, 0)
        last = Page(['TITLE'], ['1. ' + entry, '2. ' + entry], [], False, 1)
        self.assertEqual(body_owners([said, last])[1], [{0}, {0, 1}, {1}])
        self.assertTrue(read([said, last]).net)
        self.assertEqual(read([said, Page(['TITLE', SYNOPSIS_CONVENTION], ['1. ' + entry, '2. ' + entry], [], False, 1)]).net_failures(), [])

    def test_read_screen_excuses_a_synopsis_by_the_page_it_is_on(self):
        """The wiring: read_screen draws the pages of a surface and hands the net the pages' own flags."""
        listing, legend, keys = synopsis_sources()
        entry = next(entry for entry in sorted(listing) if len(entry.split()) >= 3 and net_scan(['1. ' + entry]))
        first = Page(['TITLE'], [SYNOPSIS_CONVENTION, '', '1. ' + entry], ['STATUS'], True, 0)
        second = Page(['TITLE'], ['2. ' + entry], ['STATUS'], False, 3)
        for label in ('? Help, typed details (e)', '8 Help', '2 Inspector'):
            sweep = Sweep()
            with patch.dict(globals(), {'surface_pages': lambda ws, size, style: ([first, second], 'details')}):
                read_screen(sweep, None, 'state', label, schedule=(((80, 24), 'ascii'),))
            rows = {row for held in sweep.net.values() for row in held['rows']}
            with self.subTest(label=label):
                self.assertTrue(any(row.startswith('2. ') for row in rows), label)          # page 2's item is a hit on every surface
                # page 1's is excused on a help surface only (the same words anywhere else are an instruction, not a synopsis)
                self.assertEqual(any(row.startswith('1. ') for row in rows), label not in HELP_SURFACES)

    def test_a_net_failure_names_the_token_the_command_word_the_row_the_surface_the_state_and_the_size(self):
        sweep = Sweep()
        sweep.read('queue with items', 'm Queue', (60, 20), [], rows=['  :queue-review-template ownership_unknown NEW_JSON'])
        text = '\n'.join(sweep.net_failures())
        for part in ('NEW_JSON', 'queue-review-template', 'ownership_unknown', 'm Queue', 'queue with items', '60x20'):
            self.assertIn(part, text)

    def test_every_allowlist_entry_has_a_reason_and_excuses_only_the_rows_it_names(self):
        self.assertTrue(NET_ALLOWED)
        for entry in NET_ALLOWED:
            self.assertTrue(entry.name and callable(entry.spans) and len(entry.reason.split()) > 10, entry.name)    # a reason, in words
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

    def test_id_is_excused_only_in_the_phrases_the_product_prints_and_only_where_it_prints_them(self):
        """`review operation ID` is a hit: a lowercase word before ID does not make it prose. The two phrases the sweeps meet are
        excused at their own surfaces and nowhere else."""
        commit = 'The repository-refresh command needs the full 40-character commit ID; it is recorded as stated.'
        object_phrase = 'This key does not encode the policy: select it, so its object ID cannot be read from the repository.'

        def net(rows, surface):
            sweep = Sweep()
            sweep.read('state', surface, (80, 24), [], rows=rows)
            return sweep
        for rows, surface, name in (([commit], 'a Actions, action 1 focused', 'commit ID in the actions layer'),
                                    ([object_phrase], ':repository-entry (candidates)', 'object ID in the repository entry'),
                                    (['select it: supply the Intune object ID it manages'], ':repository-entry (second candidate)',
                                     'object ID in the repository entry'),
                                    (['status error message Select an exact immutable object ID first.'],
                                     'evidence-history, refused: no object selected, typed details',
                                     'object ID in the refusal for no selection')):
            with self.subTest(rows=rows, surface=surface):
                sweep = net(rows, surface)
                self.assertEqual((sweep.net_failures(), sweep.excused[name]), ([], 1))
        for rows, surface in (([commit], '2 Inspector'),                                   # the phrase, off its surface
                              ([commit], ':repository-entry (candidates)'),
                              ([object_phrase], 'a Actions, action 1 focused'),
                              (['status error message Select an exact immutable object ID first.'], '9 Repository, typed details (e)'),
                              (['review operation ID'], 'a Actions, action 1 focused'),    # a lowercase word before ID is not enough
                              (['review operation ID'], ':repository-entry (candidates)'),
                              (['The repository-refresh command needs the commit ID'], 'a Actions, action 1 focused'),      # not the phrase
                              (['select the object ID you want'], ':repository-entry (candidates)'),
                              (['select ID'], '9 Repository'), (['inspect --object ID'], '9 Repository'),
                              (['workbench workflow --root ROOT --policy ID'], '9 Repository'), (['review the run ID'], '9 Repository')):
            with self.subTest(rows=rows, surface=surface):
                self.assertTrue(net(rows, surface).net, rows)

    def test_every_phrase_an_id_entry_names_is_still_printed_by_the_product(self):
        """An entry that names a phrase the product no longer prints is stale: it would excuse nothing, and a reworded sentence would
        come back as a hit. So each phrase is looked for in the strings of the product's source."""
        strings = [' '.join(text.split()) for text in package_strings()]
        phrases = ('its object ID cannot be read from the repository', 'the Intune object ID it manages',
                   'the full 40-character commit ID', 'Select an exact immutable object ID first')
        for phrase in phrases:
            self.assertTrue(any(phrase in text for text in strings), phrase)

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
        # the rows as the start and catalog screens print them: the sentence begins its own row (and wraps from there), the label is a row
        for rows in (['DIRECTORY | offline | this lists only what this build holds', sentence],
                     ['GOAL READINESS: discover (status: unknown)', 'Directory: DIRECTORY', sentence],
                     ['DIRECTORY | offline | this lists only what this build holds', 'DIRECTORY is the directory this',
                      'screen is about; its name is not', 'shown here.']):
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
        hidden = ['Hidden in the strip at this size (+2 more):', 'OBS stale (later collection incomplete) | REPO stale']
        self.assertTrue(net_scan(hidden))                                                           # the states the strip left out
        self.assertFalse(net(hidden))
        self.assertEqual(sorted(net(hidden[1:])), [('collection', 'REPO')])                         # the same row off that page
        self.assertEqual(sorted(net(['Collect again: collection REPO'])), [('collection', 'REPO')])


class ExceptionSpanTests(unittest.TestCase):
    """Sol B V2: an exception is judged per occurrence, by span. Each test below is Sol's breaking input, or the same shape for the
    other exceptions: the hit that is not inside the exact text an exception allows stays a hit, whatever allowed text is near."""

    @staticmethod
    def read(rows, surface='2 Inspector', state='state', convention=False, shown=None, texts=()):
        sweep = Sweep()
        sweep.read(state, surface, (80, 24), list(texts), convention, rows, shown)
        return sweep

    def test_help_text_beside_an_option_cannot_hide_an_unresolved_operand(self):
        """Finding 2. In an output that shows the convention sentence, both ROOT were excused because ROOT is in the first column."""
        text = '\n'.join(['usage: intune-iac workbench init [-h] --root ROOT', '', 'options:', '  --root ROOT  Run: kubectl apply ROOT', '',
                          'Note: %s.' % SYNOPSIS_CONVENTION])
        sweep = Sweep()
        sweep.text('help', 'intune-iac workbench init --help', (100, 0), text)
        self.assertEqual(sorted(sweep.net), [('Run', 'ROOT')])                           # the ROOT in the help text is a hit
        self.assertEqual(sweep.excused['argparse usage and option rows'], 2)              # the one in the usage block and the first column are not

    def test_a_definition_on_the_screen_cannot_excuse_a_command_operand_on_another_row(self):
        """Finding 3. The defining sentence anywhere on the screen plus a row that ends in DIRECTORY excused the operand."""
        from intune_iac.readiness import DIRECTORY_NOT_SHOWN_STEM
        sweep = self.read([DIRECTORY_NOT_SHOWN_STEM + '.', 'Run: kubectl apply DIRECTORY'], surface='start')
        self.assertEqual(sorted(sweep.net), [('Run', 'DIRECTORY')])
        sweep = self.read(['Run: kubectl apply Directory: DIRECTORY', DIRECTORY_NOT_SHOWN_STEM + '.'], surface='catalog')
        self.assertEqual(sorted(sweep.net), [('Run', 'DIRECTORY')])                       # the label is not an escape either, off its own row
        self.assertFalse(self.read([DIRECTORY_NOT_SHOWN_STEM + '.', 'Run: kubectl apply DIRECTORY'], surface='2 Inspector').excused)

    def test_an_exact_id_phrase_cannot_license_another_id_in_the_same_block(self):
        """Finding 4. The first `object ID` is an operand; the permitted phrase after it excused it."""
        for surface, phrase, noun in (
                (':repository-entry (candidates)', 'its object ID cannot be read from the repository', 'object'),
                (':repository-entry (candidates)', 'the Intune object ID it manages', 'object'),
                ('a Actions, action 1 focused', 'the full 40-character commit ID', 'commit'),
                ('evidence-history, refused: no object selected, typed details', 'Select an exact immutable object ID first', 'object')):
            with self.subTest(phrase=phrase):
                sweep = self.read(['Run: kubectl inspect %s ID. %s' % (noun, phrase)], surface=surface)
                self.assertEqual(sorted(sweep.net), [('inspect', 'ID')])
                # the phrase itself, with a command word in its own sentence, is still excused at its surface
                sweep = self.read(['Run: kubectl inspect it. Select it, so %s' % phrase], surface=surface)
                self.assertEqual(sweep.net_failures(), [])

    def test_the_strip_label_excuse_covers_only_the_label_inside_a_strip(self):
        """The REPO excuse was judged per block: any `| REPO ` beside a `| TENANT ` was excused."""
        strip = ('Line now SYNTHETIC | TENANT 11111111 | POLICY Windows Privacy Pilot (22222222) | OBS stale (later collection '
                 'incomplete) | REPO stale | OP outcome unknown')
        self.assertFalse(self.read([strip], surface='8 Help').net)
        for rows in ([strip, 'Run: kubectl apply | REPO stale | TENANT 1'],                      # a second REPO in the strip's block
                     ['SYNTHETIC | TENANT 11111111 | Run: kubectl apply | REPO stale'],         # a strip-shaped row with a foreign segment
                     ['Run: kubectl apply | REPO stale | TENANT 1']):
            with self.subTest(rows=rows):
                self.assertEqual(sorted(self.read(rows, surface='8 Help').net), [('Run', 'REPO')])

    @staticmethod
    def entry():
        """A listing entry both checks read: the net as an exact entry with operands, the reader as a command that is a synopsis."""
        listing, legend, keys = synopsis_sources()
        return next(entry for entry in sorted(listing) if len(entry.split()) >= 3 and net_scan(['1. ' + entry])
                    and unresolved('1. ' + entry) and all(is_synopsis(command) for command, _ in unresolved('1. ' + entry)))

    def test_the_net_excuses_a_synopsis_by_its_own_occurrence_not_by_one_elsewhere(self):
        """The same row on a licensed page and on a page without the sentence: it was one finding, judged once, and the first
        occurrence's excuse was the second's. Now each is judged on its own."""
        entry = self.entry()
        said = Page(['TITLE', SYNOPSIS_CONVENTION], ['1. ' + entry], [], True, 0)
        silent = Page(['TITLE'], ['1. ' + entry], [], False, 1)                           # the very same row, on a page without it
        rows, shown = net_input([said, silent], 'details')
        sweep = self.read(rows, surface='? Help, typed details (e)', shown=shown)
        self.assertTrue(sweep.net, 'the second occurrence is a hit')
        self.assertTrue(sweep.excused['exact synopsis'], 'and the first is still excused')
        # a hit in the same row as an exact synopsis, outside its text, is a hit (and the row is no longer the exact entry)
        sweep = self.read(['12. ' + entry + ' Run: kubectl apply PLAN_FILE'], surface='? Help, typed details (e)',
                          convention=True, shown=[True])
        self.assertIn('PLAN_FILE', {token for (_, token) in sweep.net})

    def test_the_reader_excuses_a_synopsis_place_by_place(self):
        """The reader judged a command once by its text, so a place that merely uses the same words took the excuse of a synopsis."""
        entry = self.entry()
        said = Page(['TITLE', SYNOPSIS_CONVENTION], ['1. ' + entry], [], True, 0)
        silent = Page(['TITLE'], ['1. ' + entry], [], False, 1)
        rows, shown = net_input([said, silent], 'details')
        sweep = self.read(rows, surface='? Help, typed details (e)', shown=shown, texts=screen_texts([said, silent], 'details'))
        self.assertTrue(sweep.synopses, 'the synopsis on the page without the sentence is a finding')
        # an instruction that is only the same words as a synopsis, on a page that shows the sentence, is not a synopsis
        command = next(command for command, _ in unresolved('1. ' + entry))
        rows = [SYNOPSIS_CONVENTION, 'Run: ' + command]
        sweep = self.read(rows, surface='? Help, typed details (e)', convention=True, shown=[True, True], texts=readable(rows))
        self.assertTrue(sweep.found, 'the reader reads the instruction as a command with an unresolved operand')
        # the same words in the exact entry and in an instruction, on one licensed page: the instruction keeps the finding
        rows = [SYNOPSIS_CONVENTION, '', '1. ' + entry, '', 'Run: ' + command]
        sweep = self.read(rows, surface='? Help, typed details (e)', convention=True, shown=[True] * 5, texts=readable(rows))
        self.assertTrue(sweep.found)
        rows = [SYNOPSIS_CONVENTION, '', '1. ' + entry]                                  # the entry alone is clean
        sweep = self.read(rows, surface='? Help, typed details (e)', convention=True, shown=[True] * 3, texts=readable(rows))
        self.assertEqual((sweep.found, sweep.synopses), (collections.OrderedDict(), collections.OrderedDict()))

    def test_only_a_whole_json_document_is_a_machine_form(self):
        sweep = Sweep()
        sweep.text('state', 'start --json', (80, 0), json.dumps({'next': 'Run: kubectl apply PLAN_FILE'}))
        self.assertEqual((sweep.net, sweep.found), (collections.OrderedDict(), collections.OrderedDict()))      # the document is not read
        sweep = Sweep()
        sweep.text('state', 'workbench companion', (80, 0), 'Run: kubectl apply PLAN_FILE\n' + json.dumps({'mode': 'live'}))
        self.assertEqual(sorted(sweep.net), [('Run', 'PLAN_FILE')])                         # prose beside a document is read

    def test_a_placeholder_inside_an_absolute_path_is_still_a_hit_and_a_segment_is_not_a_command(self):
        self.assertEqual(sorted(self.read(['select /ops/OPERATION_DIR']).net), [('select', 'OPERATION_DIR')])
        self.assertFalse(self.read(['/usr/lib/repository FIELD']).net)                    # `repository` in a path is a name, not a command
        self.assertFalse(self.read(['collect --output /tmp/tmpab12/review done']).net)


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
        self.assertEqual(sweep.unmet, [], 'a run whose screen lacks what its canned answer must show: the stub was not in effect there')
        self.assertEqual(sweep.badcalls, [], 'a run whose fake log is not exactly the one call per tool the provider means')
        routes_read = {route for (_, route, *_) in sweep.coverage}
        for provider in ('azure', 'github', 'all'):
            for route in ('start --goal discover', 'start --goal adopt', 'catalog', 'catalog --goal discover'):
                self.assertIn('%s --check-signin %s' % (route, provider), routes_read)
        cases = signin_cases('c')
        self.assertGreaterEqual(len({state for (state, *_) in sweep.coverage}), len(cases))
        # every case has an expected result of its own, and every run of every case was judged against it: 4 routes at 2 widths, in
        # the directory with the context and, for the cases that have an answer for it, in the one with none
        self.assertTrue(all(case.expect for case in cases))
        self.assertEqual(len({case.expect for case in cases}), len(cases))
        self.assertEqual(sweep.signin_runs, (len(cases) + sum(1 for case in cases if case.bare)) * 8)

    def test_a_stub_that_is_not_in_effect_is_found_whatever_the_case(self):
        """With the fakes off the search path, a run shows none of what its answer must show, and its fake log is empty."""
        root = Path(__file__).resolve().parents[1]
        context = json.loads((root / 'examples/context.json').read_text())['tenant_id']
        chosen = [case for case in signin_cases(context)
                  if case.label in ('azure: signed in to the context tenant', 'github: several accounts', 'azure: the CLI fails')]
        self.assertEqual(len(chosen), 3)
        sweep = Sweep()
        sweep.unmet, sweep.badcalls, sweep.signin_runs = [], [], 0
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / 'estate dir'
            folder.mkdir()
            shutil.copyfile(root / 'examples/context.json', folder / 'context.json')
            for case in chosen:
                run_signin_case(sweep, case, [(folder, 'a context', case.expect)], effective=False)
        self.assertEqual(sweep.signin_runs, 3 * 8)
        self.assertEqual({label for label, *_ in sweep.badcalls}, {case.label for case in chosen})     # the fake was never invoked
        self.assertTrue(all(calls == [] for *_, calls in sweep.badcalls))
        self.assertEqual({label for label, *_ in sweep.unmet}, {case.label for case in chosen})     # and the screens lack what the answers give

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
