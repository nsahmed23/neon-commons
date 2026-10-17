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
    cli.parser(). The classification of the leaves fails closed: LEAF_TABLE names each of the 139 as text (cli.main prints it
    through _write_text; read from main's source), a session (the wizard, the workspace, the line terminal, the companion, the
    provider wizard) or a machine form (the JSON document), a leaf the table lacks fails, every text and session leaf is driven by the
    sweep LEAF_DRIVERS names (cli._write_text is wrapped to record the leaf each call ran for, and each sweep records the session it
    opened), and the product is scanned by reference, not by call: every reference to an output-capable name or stream (print, input,
    builtins, sys.stdout and the other streams, os.write, os.fdopen, subprocess, logging ...) or to a primitive that reaches one by
    name (getattr on sys, __import__, exec, eval, globals, importlib ...), and every write that is not inside `with open(...)`, is a
    site that OUTPUT_SITES or NOT_A_TERMINAL lists by file and function with its count and its reason, so a leaf that prints in any
    way is a new site and fails until it is classified, listed and driven.
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
import builtins
import collections
import contextlib
import copy
import functools
import hashlib
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
    """True when the text is one JSON document, or a stream of them (JSON lines, or documents one after another): a machine form,
    which is not read. A text with anything else beside the documents is not, and is read."""
    decoder, at, text = json.JSONDecoder(), 0, text.strip()
    while at < len(text):
        try:
            _, at = decoder.raw_decode(text, at)
        except ValueError:
            return False
        while at < len(text) and text[at].isspace():
            at += 1
    return bool(text)


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


CURRENT_SWEEP = []                                   # the sweeps running now, innermost last
DRIVEN = collections.defaultdict(set)                # parser leaf -> the names of the sweeps that drove it


def driven(leaf):
    """Record that the sweep running now drove a parser leaf, given as a string of words or as a tuple of them: a session it opened
    and saw through, or a text route cli.main printed for."""
    if CURRENT_SWEEP:
        DRIVEN[tuple(leaf.split()) if isinstance(leaf, str) else tuple(leaf)].add(CURRENT_SWEEP[-1])


def named_sweep(function):
    """A sweep that knows its name, so the leaves it drives are recorded under it, and that records the routes of cli.main it reaches
    through the helpers of other test modules."""
    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        CURRENT_SWEEP.append(function.__name__)
        try:
            with recording_routes():
                return function(*args, **kwargs)
        finally:
            CURRENT_SWEEP.pop()
    return wrapper


@functools.lru_cache(maxsize=None)
@named_sweep
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
        driven('workbench workspace')                   # the visual session, opened by keys and closed by q
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
            leaf = leaf_of(seen['parser'], seen['namespace'])
            WRITTEN[leaf] += 1
            driven(leaf)
        return real_write(rows)
    write.records_routes = True
    with patch.object(cli, 'parser', parser), patch.object(cli, '_write_text', write):
        yield


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


# -- every parser leaf, classified, and every place the product writes to a terminal -------------------------------------------------
#
# A leaf of cli.parser() shows itself to a person in one of three ways, and the classification fails closed: LEAF_TABLE names every leaf
# (139 today); a leaf the parser has and the table lacks fails, and so does an entry with no leaf.
#   text     cli.main prints its screen through cli._write_text (text_leaves_by_code reads from main's source which leaves can).
#   session  a terminal session or a prompt flow with its own input and output.
#   machine  prints the JSON document of cli.main, or serves a protocol; nothing a person reads.
# Each text and session leaf is driven by the sweep LEAF_DRIVERS names, and the recorder says what each sweep drove (DRIVEN). What stops
# a leaf from reaching a person by a road the recorder cannot see is the scan of the product by reference (site_nodes): each reference to an
# output-capable name or stream, called or not, each primitive that reaches one by name, and each write that is not inside
# `with open(...)` is listed in OUTPUT_SITES (it serves a leaf) or NOT_A_TERMINAL (it reaches no terminal, and says why) by file and
# function, with its count, and anything unlisted fails, so a new leaf that prints in any way fails until it is classified, listed and driven.

LEAF_TABLE = {
    'text': ('start', 'catalog', 'engineering', 'simulate', 'signin status', 'signin collect', 'workbench workflow'),
    'session': ('wizard', 'workbench workspace', 'workbench terminal', 'workbench companion', 'provider wizard'),
    'machine': (
        'action', 'adoption attach', 'adoption cancel', 'adoption prepare', 'adoption recover',
        'adoption recovery-plan-attach', 'adoption recovery-plan-cancel', 'adoption recovery-plan-prepare',
        'adoption recovery-plan-recover', 'adoption recovery-plan-review', 'adoption recovery-plan-status',
        'adoption review', 'adoption status', 'artifact inspect', 'artifact restore', 'artifact seal', 'capture', 'doctor',
        'generate', 'graph build', 'graph query', 'inspect', 'judge', 'mcp', 'plan review', 'provider execute',
        'provider prepare', 'provider reconcile', 'provider review', 'provider status', 'repository inspect',
        'repository native', 'repository resolve', 'service attach', 'service cancel', 'service prepare',
        'service recover', 'service review', 'service status', 'simulation create', 'simulation prepare',
        'simulation reconcile', 'simulation run', 'synthetic generate', 'synthetic inspect', 'target authenticate',
        'target collect', 'target compare', 'target inspect', 'verify', 'workbench adopt', 'workbench adoption-history',
        'workbench adoption-lineage', 'workbench adoption-link', 'workbench adoption-preview', 'workbench backup',
        'workbench collect', 'workbench collection', 'workbench collection-history', 'workbench compare',
        'workbench delivery', 'workbench deployment-import', 'workbench deployment-record',
        'workbench device-evidence-import', 'workbench diagnostics', 'workbench dictionary', 'workbench estate-overview',
        'workbench evidence-history', 'workbench evidence-link', 'workbench execute', 'workbench families',
        'workbench field-semantics', 'workbench health', 'workbench history', 'workbench history-recent',
        'workbench import-capture', 'workbench init', 'workbench inspect', 'workbench lab-create', 'workbench lab-init',
        'workbench lineage', 'workbench migrate', 'workbench observer-create', 'workbench observer-run',
        'workbench observer-scheduler', 'workbench observer-status', 'workbench operations', 'workbench overview',
        'workbench ownership-import', 'workbench ownership-scan', 'workbench propose', 'workbench propose-from-intent',
        'workbench provider-refresh-import', 'workbench queue', 'workbench queue-amend', 'workbench queue-review',
        'workbench queue-review-history', 'workbench queue-review-template', 'workbench reconcile',
        'workbench reference-compare', 'workbench reference-import', 'workbench references', 'workbench relationships',
        'workbench repository-entry', 'workbench repository-import', 'workbench repository-refresh',
        'workbench repository-status', 'workbench restore', 'workbench restore-propose', 'workbench review',
        'workbench schedule-create', 'workbench schedule-run', 'workbench schedule-status', 'workbench search',
        'workbench service-link', 'workbench settings', 'workbench source-acceptance-propose', 'workbench views',
        'workbench workflow-import', 'workbench workflows', 'worker attach', 'worker cancel', 'worker prepare',
        'worker reconcile', 'worker review', 'worker run', 'worker status',
    ),
}

# The sweep that drives each text and session leaf (functions of this module, which the test runs; DRIVEN says what each one did).
LEAF_DRIVERS = {
    'start': 'sweep_start_and_catalog', 'catalog': 'sweep_start_and_catalog', 'engineering': 'sweep_workflow_and_engineering',
    'simulate': 'sweep_simulate', 'signin status': 'sweep_signin', 'signin collect': 'sweep_signin',
    'workbench workflow': 'sweep_workflow_and_engineering', 'wizard': 'sweep_wizards',
    'workbench workspace': ('sweep_state', 'sweep_workflow_and_engineering'),      # the session; and its Ctrl-C sentences, through cli.main
    'workbench terminal': 'sweep_terminal', 'workbench companion': 'sweep_companion', 'provider wizard': 'sweep_provider_wizard',
}


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


def leaf_table(table=None):
    """{leaf path: kind} for a table of LEAF_TABLE's shape. A leaf named twice, in one kind or in two, raises."""
    found = {}
    for kind, names in (LEAF_TABLE if table is None else table).items():
        for name in names:
            path = tuple(name.split())
            if path in found:
                raise ValueError('the leaf %r is named twice (%s and %s)' % (name, found[path], kind))
            found[path] = kind
    return found


def leaf_table_problems(parser, table=None, drivers=None):
    """[str] for what is wrong with the classification of the leaves of a parser: a leaf the parser has and the table lacks, an entry
    the parser has no leaf for, a leaf named twice, a text or session leaf with no driver, a driver for a leaf that is neither, and a
    driver that is not a function of this module."""
    try:
        classified = leaf_table(table)
    except ValueError as error:
        return [str(error)]
    leaves = set(leaf_paths(parser))
    problems = ['the parser has the leaf %r and the table does not name it' % ' '.join(path) for path in sorted(leaves - set(classified))]
    problems += ['the table names %r and the parser has no such leaf' % ' '.join(path) for path in sorted(set(classified) - leaves)]
    drivers = LEAF_DRIVERS if drivers is None else drivers
    human = {' '.join(path) for path, kind in classified.items() if kind != 'machine'}
    problems += ['the %s leaf %r has no driver' % (classified[tuple(name.split())], name) for name in sorted(human - set(drivers))]
    problems += ['%r has a driver and is not a text or session leaf' % name for name in sorted(set(drivers) - human)]
    for name, sweeps in sorted(drivers.items()):
        for sweep in ((sweeps,) if isinstance(sweeps, str) else sweeps):
            if not callable(globals().get(sweep)):
                problems.append('the driver %r of %r is not a function of this module' % (sweep, name))
    return problems


# Every place the product could put text in front of a person by a road other than cli._write_text. The scan flags by reference: an
# output-capable name or stream is a site wherever it appears in the product, called or not, because a call is only one way to use it
# (`p = print`, `functools.partial(print)`, `builtins.print`, an alias imported from builtins, `getattr(builtins, "print")`), and so is
# a primitive that reaches one by name. Each site is listed below by file, function and kind with its number of references, and with
# the leaf it serves or the reason it reaches no terminal; an unlisted site, another number, and a listed site that is gone all fail.
# What a name stands for is every binding it has anywhere in the file, in any scope (an import of it, an assignment to it from a name, a
# chain on a name or a choice between such), and a load is a site if any one of them makes it one: `import os as channel` is not undone
# by `import json as channel` elsewhere in the file, and a builtin keeps its meaning whatever else its name is bound to. A name of the
# product's own that is a scan name (the text sink _write_text) is a site however it is reached: from .cli import _write_text as emit,
# cli._write_text, intune_iac.cli._write_text, or the string "_write_text", and so is the relative import that brings it. The native
# routes that can reach a terminal or run code by a road of their own (fcntl, termios, signal, pickle, marshal, shelve, readline, tty,
# code, pdb, curses, msvcrt, _winapi and the rest of SCAN_MODULES) are sites at the import and at every use; the product uses fcntl,
# termios and signal.
# The kinds, one per reference:
#   print, input, exec, eval, compile, __import__, globals, locals, __builtins__, breakpoint, _write_text    the name, in load context
#   sys.stdout, sys.stderr, sys.stdin, sys.__stdout__, sys.__stderr__, sys.__stdin__, sys.modules          the attribute (aliases resolved)
#   os.write, os.fdopen, os.dup2, os.system, os.popen, os.dup, os.exec*, os.spawn*, ...                    the attribute (SCAN_OS)
#   builtins, subprocess, pty, importlib, logging, ctypes, ...                                              a module of SCAN_MODULES, any reference
#   import M, import sys.stdout, import os.fdopen                  the import of one of those, or of a flagged name from sys or os
#   sys as a value, os as a value       the module kept or handed on instead of reading an attribute of it (getattr(sys, name))
#   dynamic access                      an attribute that opens the interpreter's own tables (SCAN_DUNDERS)
#   device path                         a string that names a terminal device or the process table
#   standard descriptor                 fd 0, 1 or 2, given as a number to open, os.fdopen, os.dup, os.dup2, os.write and the like
#   child on the terminal               subprocess.Popen, run, call, check_call or check_output without stdout and stderr taken by pipes
#   write                               a .write(, .writelines(, .write_text( or .write_bytes( call, other than on the name a
#                                       `with open(...) as name:` binds
#   parser-output                       print_usage, print_help or error on a parser
#   exit-text                           an exit whose argument is not plainly a status: the interpreter writes it to standard error
#   console, import console             a Win32 console call that writes, or chooses where the output goes (WriteConsole and every form of it,
#                                       GetStdHandle, SetStdHandle, AllocConsole, AttachConsole, CreateConsoleScreenBuffer,
#                                       SetConsoleActiveScreenBuffer): as an attribute of anything, a name, a string or an import
#   namespace, route value stored       an object that can carry route values of its own (a Namespace, or what parse_args returns), and a
#                                       store to one: what the route conditions of the reachability check read as the command line's (see
#                                       the note on what a machine leaf can run)
# Exempt, exactly: a print that can emit one JSON document and nothing else (one positional argument that is a json.dumps(...) call, no
# sep or file argument, no end but whitespace); and a write lexically inside `with open(...) as name:` on that name, where the block does
# not bind the name again and open takes neither a descriptor nor a device. Everything else is a site, however it got there.
# The reasons that more than one site gives, by a short name.
REASON_FDOPEN = 'a file object on a descriptor from os.open, mkstemp or os.dup of one: a store file, never fd 0, 1 or 2'
REASON_FDWRITE = 'writes the file the function opened with os.fdopen on its own descriptor'
REASON_DUP = 'duplicates a descriptor from os.open so the same file can be read again; never fd 0, 1 or 2'
REASON_CHILD = 'starts a child with stdin DEVNULL and stdout and stderr PIPE: the program reads what it prints, no terminal sees it'
REASON_READINESS = 'imports intune_iac.readiness by a literal name, to call placeholders_in_words on a sentence'
REASON_PROBE = 'asks the stream whether it is a terminal, its width or its encoding; writes nothing'
REASON_JSONERR = 'a JSON document on standard error (machine form)'
REASON_MAINOUT = 'asks its encoding and whether it is a terminal; flushes it after the JSON document; reads its descriptor'
REASON_PROVIDERCRED = 'duplicates the credential descriptor its caller passes in, to read the credential from it'
REASON_IMPORTLIB = 'asks which modules are installed or loaded (see its importlib sites)'
REASON_CHILDMODULE = 'the child process this module starts (see its subprocess sites)'
REASON_FLOCK = 'fcntl.flock: an advisory lock on a lock or store file, with its LOCK_ constants; writes nothing'
REASON_LOCALSIGNAL = 'a local variable named signal (a loop target over attention signals), not the module: every load of the name counts'
REASON_SELFINT = 'sends SIGINT to its own process when the worker it monitors has stopped'
REASON_KILLGROUP = 'SIGKILL to the process group of a child it started'
REASON_IMPORTFCNTL = 'imports fcntl for the advisory locks of this module (see its fcntl sites)'
REASON_IMPORTSIGNAL = 'imports signal for the process control of this module (see its signal sites)'
OUTPUT_SITES = {
    ('cli.py', '_Parser.error', 'exit-text'): (1, None, '26b92f33aeff'),
    ('cli.py', '_Parser.error', 'parser-output'): (1, None, '7e52ea8290dd'),
    ('cli.py', '_Parser.error', 'sys.stderr'): (1, None, '4d69426e4503'),
    ('cli.py', '_write_text', 'print'): (1, None, '55eea42e8e32'),
    ('cli.py', '_write_text', 'sys.stdout'): (1, None, 'f52d77748758'),
    ('cli.py', 'main', '_write_text'): (7, None, '3822dda82db2'),
    ('journey.py', 'run_journey', 'input'): (1, 'wizard', 'd7c1b9d3194b'),
    ('journey.py', 'run_journey', 'print'): (1, 'wizard', '9f3fa7bb066f'),
    ('provider_journey.py', 'run_provider_wizard', 'input'): (2, 'provider wizard', '32c43fe3c8f8'),
    ('provider_journey.py', 'run_provider_wizard', 'print'): (2, 'provider wizard', 'b6c3bce9b4c4'),
    ('windows_terminal.py', 'NativeConsole.session', 'write'): (2, 'workbench workspace', 'b9434dce89d5'),
    ('windows_terminal.py', 'NativeConsole.write', 'write'): (1, 'workbench workspace', 'ca6d6e7eb425'),
    ('windows_terminal.py', '_Win32.__init__', 'console'): (2, 'workbench workspace', 'a603dab5bd21'),  # the signature table names GetStdHandle and WriteConsoleW as strings, to give them their argument and result types
    ('windows_terminal.py', '_Win32.__init__', 'ctypes.WinDLL'): (1, 'workbench workspace', '4a6c32409595'),  # kernel32 for the console: the API of NativeConsole, which makes it and nothing else does (windows_directory has a class of the same name, for the storage layer)
    ('windows_terminal.py', '_Win32.handles', 'console'): (2, 'workbench workspace', '9ae07c41d2fe'),  # GetStdHandle for the input and output handles of the console, which it reads and writes through
    ('windows_terminal.py', '_Win32.write', 'console'): (1, 'workbench workspace', 'fead57fd021a'),  # WriteConsoleW: the one call that writes text to the console
    ('wizard.py', '_run_wizard', 'input'): (1, 'wizard', 'de76bcd7d16d'),
    ('wizard.py', '_run_wizard', 'print'): (1, 'wizard', 'f8512bed4462'),
    ('wizard.py', 'run_wizard', 'input'): (1, 'wizard', '51cbdac7e975'),
    ('wizard.py', 'run_wizard', 'print'): (1, 'wizard', '142e944872cc'),
    ('workbench.py', '_render', 'print'): (1, 'workbench terminal', 'ffb62bc101c9'),
    ('workbench.py', '_run_terminal', 'input'): (4, 'workbench terminal', 'c5df38a88916'),
    ('workbench.py', '_run_terminal', 'print'): (3, 'workbench terminal', 'b5e7443804ae'),
    ('workbench.py', '_run_terminal.present', 'print'): (1, 'workbench terminal', 'e238186b959b'),
    ('workbench.py', 'command', 'print'): (2, 'workbench companion', '19935d7de576'),
    ('workbench.py', 'run_terminal', 'input'): (1, 'workbench terminal', '5911f9c2f2cb'),
    ('workbench.py', 'run_terminal', 'print'): (4, 'workbench terminal', '6c9161b99549'),
    ('workbench_tui.py', 'Workspace.__init__', 'sys.stdin'): (3, 'workbench workspace', 'f7da42e33196'),
    ('workbench_tui.py', 'Workspace.__init__', 'sys.stdout'): (3, 'workbench workspace', '18a2a3e6ec0d'),
    ('workbench_tui.py', 'Workspace.draw', 'write'): (1, 'workbench workspace', '3af44074b7ab'),
    ('workbench_tui.py', 'run_workspace', 'sys.stdin'): (6, 'workbench workspace', '946d14cd7847'),
    ('workbench_tui.py', 'run_workspace', 'sys.stdout'): (6, 'workbench workspace', '31e8a54bddc3'),
    ('workbench_tui.py', 'run_workspace.read_line', 'sys.stdin'): (2, 'workbench workspace', '34c631c20d57'),
    ('workbench_tui.py', 'run_workspace.read_line', 'sys.stdout'): (2, 'workbench workspace', '6316137f1bd9'),
    ('workbench_tui.py', 'run_workspace.read_line', 'write'): (1, 'workbench workspace', 'e692b91120b2'),
    ('workbench_tui.py', 'run_workspace.write_line', 'print'): (1, 'workbench workspace', '416dcbaa4a22'),
    ('workbench_tui.py', 'run_workspace.write_line', 'sys.stdout'): (1, 'workbench workspace', '33d06c658ce5'),
    ('workbench_tui.py', 'terminal_session', 'import termios'): (1, 'workbench workspace', '762ddc5a3bf2'),
    ('workbench_tui.py', 'terminal_session', 'sys.stdin'): (1, 'workbench workspace', 'c8574cd88bd4'),
    ('workbench_tui.py', 'terminal_session', 'sys.stdout'): (4, 'workbench workspace', '0965d2cbc568'),
    ('workbench_tui.py', 'terminal_session', 'termios'): (10, 'workbench workspace', 'f577d8e74fec'),
    ('workbench_tui.py', 'terminal_session', 'write'): (2, 'workbench workspace', 'f4e0356a7ac0'),
    ('workflow.py', 'run_guided_workflow', 'input'): (1, 'wizard', 'e0163dc531ee'),
    ('workflow.py', 'run_guided_workflow', 'print'): (1, 'wizard', '2ea9571341e1'),
}
NOT_A_TERMINAL = {
    ('approval_authority.py', '<module>', 'import fcntl'): (1, REASON_IMPORTFCNTL, '393427b28453'),
    ('approval_authority.py', 'ApprovalAuthority._verify', 'os.dup'): (1, REASON_DUP, 'cedbfd560e41'),
    ('approval_authority.py', 'ApprovalAuthority._verify', 'os.fdopen'): (2, REASON_FDOPEN, '331097a528bf'),
    ('approval_authority.py', 'ApprovalAuthority._verify', 'write'): (1, REASON_FDWRITE, '343c166df939'),
    ('approval_authority.py', 'ApprovedExecution.__enter__', 'fcntl'): (3, REASON_FLOCK, '9e6a77dbac20'),
    ('approval_authority.py', '_validator', 'ctypes.CDLL'): (1, 'loads the copy of the approved native validator library', '6d35fa56281b'),
    ('approval_authority.py', '_validator', 'os.fdopen'): (2, REASON_FDOPEN, '738e5cef3cbf'),
    ('approval_authority.py', '_validator', 'write'): (1, REASON_FDWRITE, '488ef32ad94e'),
    ('artifact_vault.py', '_read', 'os.fdopen'): (1, REASON_FDOPEN, 'd69c7bef3771'),
    ('artifact_vault.py', '_write_new', 'os.fdopen'): (1, REASON_FDOPEN, 'c7281f385745'),
    ('artifact_vault.py', '_write_new', 'write'): (1, REASON_FDWRITE, '855bf42b4c65'),
    ('azure_backend.py', 'AzureBackendAdapter.publish', 'os.fdopen'): (1, REASON_FDOPEN, '25c5a0065d5d'),
    ('azure_backend.py', 'AzureBackendAdapter.publish', 'write'): (1, REASON_FDWRITE, '3b579431e2a0'),
    ('azure_backend.py', 'AzureBackendAdapter.verify_published', 'os.fdopen'): (1, REASON_FDOPEN, 'e8cf89891a0e'),
    ('capture.py', '_capture', 'write'): (3, 'the files of a capture, through its output_factory', 'b1c226742603'),
    ('capture.py', '_write', 'os.fdopen'): (1, REASON_FDOPEN, '0a7862d9ee13'),
    ('capture.py', '_write', 'write'): (1, REASON_FDWRITE, '93114bae4ad6'),
    ('capture_adapter.py', '_read', 'os.fdopen'): (1, REASON_FDOPEN, '3fa339724f42'),
    ('cli.py', '<module>', 'import importlib'): (2, REASON_IMPORTLIB, 'aaacb36da458'),
    ('cli.py', '_lf_only', 'sys.stderr'): (1, 'sets the line ending of the two streams; writes nothing', '778db188df4c'),
    ('cli.py', '_lf_only', 'sys.stdout'): (1, 'sets the line ending of the two streams; writes nothing', '40d856f1901c'),
    ('cli.py', 'doctor', 'importlib'): (3, 'asks whether a dependency is installed and its version; prints nothing itself', 'a3d061fbebed'),
    ('cli.py', 'execute.progress', 'print'): (1, REASON_JSONERR, '952fc6495858'),
    ('cli.py', 'execute.progress', 'sys.stderr'): (1, REASON_JSONERR, '243fb0fd2963'),
    ('cli.py', 'main', 'namespace'): (1, 'the parse that gives the route: the command line of the leaf itself, which the route conditions of the reachability check read', 'd12542958194'),
    ('cli.py', 'main', 'os.dup2'): (1, 'points fd 1 at /dev/null after a broken pipe, so that nothing more is written', 'd277c4093d5c'),
    ('cli.py', 'main', 'print'): (3, REASON_JSONERR, '1fb085ba1ae4'),
    ('cli.py', 'main', 'sys.stderr'): (3, REASON_JSONERR, '04c6e9a90b90'),
    ('cli.py', 'main', 'sys.stdout'): (4, REASON_MAINOUT, '8b8397890b17'),
    ('clock.py', 'Floor.locked', 'fcntl'): (2, REASON_FLOCK, 'ee11c857c8fd'),
    ('clock.py', 'Floor.locked', 'import fcntl'): (1, REASON_IMPORTFCNTL, 'db72c825680a'),
    ('companion.py', 'write_static', 'os.fdopen'): (1, REASON_FDOPEN, '19f32abc2939'),
    ('companion.py', 'write_static', 'write'): (1, REASON_FDWRITE, '04363bee99d5'),
    ('companion_live.py', 'Handler._send', 'write'): (1, 'the HTTP response of the companion page, to a socket', '5464e4c55dff'),
    ('engineering_view.py', 'output_width', 'sys.stdout'): (2, REASON_PROBE, 'c100b4372c8e'),
    ('execution.py', '_exclusive_json', 'os.fdopen'): (1, REASON_FDOPEN, '73ff2d4ec0d6'),
    ('execution.py', '_exclusive_json', 'write'): (1, REASON_FDWRITE, '07556dba2333'),
    ('host_capabilities.py', '<module>', 'import importlib'): (1, REASON_IMPORTLIB, '6d287ac395d4'),
    ('host_capabilities.py', '_facts', 'os as a value'): (1, 'hasattr(os, key) over a fixed tuple of constants: a capability probe', '6c01a1024120'),
    ('host_capabilities.py', '_module_has', 'importlib'): (1, 'imports a module by name to test that it exists', 'faf4d30a5246'),
    ('io.py', 'read_bytes', 'os.fdopen'): (1, REASON_FDOPEN, 'fdd8c0b1f67b'),
    ('io.py', 'write_json', 'os.fdopen'): (1, REASON_FDOPEN, '26c8f54bc537'),
    ('io.py', 'write_json', 'write'): (1, REASON_FDWRITE, '5d823c24e4d4'),
    ('journey.py', 'run_journey', 'os.fdopen'): (1, REASON_FDOPEN, 'ce37de5eaecc'),
    ('journey.py', 'run_journey', 'write'): (1, REASON_FDWRITE, '36f536b000aa'),
    ('journey_native_atmos.py', '_tool', 'os.fdopen'): (1, REASON_FDOPEN, 'e3cc97ecc851'),
    ('maintenance.py', '<module>', 'import fcntl'): (1, REASON_IMPORTFCNTL, '10c621b42e9c'),
    ('maintenance.py', '_lock', 'fcntl'): (3, REASON_FLOCK, 'eff8ceef8b45'),
    ('mcp.py', 'serve', 'sys.stdin'): (2, 'the MCP server input stream (JSON-RPC lines), a protocol', '7bc738556d82'),
    ('mcp.py', 'serve', 'sys.stdout'): (1, 'the MCP server output stream (JSON-RPC lines), a protocol', '7f4433eeff36'),
    ('mcp.py', 'serve.send', 'sys.stdout'): (2, 'the MCP server output stream (JSON-RPC lines), a protocol', '3926e5224d12'),
    ('mcp.py', 'serve.send', 'write'): (1, 'the MCP protocol: one JSON message per line on the server stream', '5ee69a0133a7'),
    ('modeled_service.py', '<module>', 'import fcntl'): (1, REASON_IMPORTFCNTL, '916aa0dd878b'),
    ('modeled_service.py', 'ModeledService.request', 'fcntl'): (3, REASON_FLOCK, '02b3731c9b61'),
    ('native_atmos.py', 'resolve_native_atmos', 'write'): (1, 'writes a file of the native snapshot at a path under its directory (Path.write_bytes)', '6fafcb045e54'),
    ('orchestration_export.py', '<module>', 'os as a value'): (1, 'hasattr(os, name) over a fixed tuple of constants: a capability probe', '2cd4967f3683'),
    ('orchestration_export.py', '_open_checked', 'os.fdopen'): (1, REASON_FDOPEN, '5ff0e4162c98'),
    ('output_edit.py', 'classify', 'write'): (1, 'writes the stack file of the generated output that it was asked to edit (Path.write_bytes)', '15daa834b8e0'),
    ('protected.py', '<module>', 'import signal'): (1, REASON_IMPORTSIGNAL, 'ef1ac4df107b'),
    ('protected.py', '<module>', 'import subprocess'): (1, REASON_CHILDMODULE, 'e2505557b727'),
    ('protected.py', '_cleanup_process_group', 'signal'): (3, REASON_KILLGROUP, '87edc0f93bd6'),
    ('protected.py', '_cleanup_process_group', 'subprocess'): (1, 'names subprocess.TimeoutExpired in a test of an exception; starts nothing', 'dd699783ae7d'),
    ('protected.py', '_create', 'os.fdopen'): (1, REASON_FDOPEN, 'cec9e565b5cd'),
    ('protected.py', '_create', 'write'): (1, REASON_FDWRITE, 'f0b7d8a0a57c'),
    ('protected.py', '_defer_spawn_interrupt', 'signal'): (13, 'defers SIGINT while a child is spawned, then restores the handler and the mask', '8bd7a6d94b5a'),
    ('protected.py', '_defer_spawn_interrupt.child_guard', 'signal'): (4, 'defers SIGINT while a child is spawned, then restores the handler and the mask', 'ae48072b4654'),
    ('protected.py', '_exclusive', 'os.fdopen'): (1, REASON_FDOPEN, '01ff21961955'),
    ('protected.py', '_exclusive', 'write'): (1, REASON_FDWRITE, '66ea73b2f6cf'),
    ('protected.py', '_network_filter', 'ctypes.CDLL'): (1, 'loads libseccomp, to install a network filter', '0b7beee5f152'),
    ('protected.py', '_run', 'os.dup'): (1, REASON_DUP, '9b908a2681ef'),
    ('protected.py', '_run', 'os.fdopen'): (1, REASON_FDOPEN, '1cdea539add4'),
    ('protected.py', '_sha', 'os.fdopen'): (1, REASON_FDOPEN, '6439597b4128'),
    ('protected.py', '_supervise', 'subprocess'): (4, REASON_CHILD, '34a833a52227'),
    ('protected_worker.py', 'WorkerJob._apply', 'os.dup'): (2, REASON_DUP, 'b0870aa593b3'),
    ('protected_worker.py', 'WorkerJob._apply', 'os.fdopen'): (2, REASON_FDOPEN, '6e1a542867ed'),
    ('provider_execution.py', '<module>', 'import fcntl'): (1, REASON_IMPORTFCNTL, 'd67cb5a58bed'),
    ('provider_execution.py', '<module>', 'import signal'): (1, REASON_IMPORTSIGNAL, '19d9f90c07ed'),
    ('provider_execution.py', '<module>', 'import subprocess'): (1, REASON_CHILDMODULE, 'cd99a0a7e735'),
    ('provider_execution.py', 'ProviderExecutor._lock', 'fcntl'): (3, REASON_FLOCK, '5212621c4da0'),
    ('provider_execution.py', 'ProviderExecutor._run', 'os.dup'): (1, REASON_DUP, '2929b0f3ac7f'),
    ('provider_execution.py', 'ProviderExecutor._run', 'os.fdopen'): (1, REASON_FDOPEN, '03712bf0241c'),
    ('provider_execution.py', 'ProviderExecutor.prepare', 'write'): (1, 'writes lock.sha256 under the executor root (Path.write_text)', 'c96b5c089fa6'),
    ('provider_execution.py', '_copy_pin', 'os.fdopen'): (1, REASON_FDOPEN, '1189cbc1e0cd'),
    ('provider_execution.py', '_copy_pin', 'write'): (1, REASON_FDWRITE, '0ff1564c083b'),
    ('provider_execution.py', '_create', 'write'): (1, 'writes the tofu.rc file of the executor root (Path.write_text)', '458355f404e1'),
    ('provider_execution.py', '_network_guard', 'ctypes.CDLL'): (1, 'loads libseccomp, to install a network filter', '0cc7ba3770f7'),
    ('provider_execution.py', '_sealed_plan', 'fcntl'): (2, 'seals the memfd that holds the sealed plan (F_ADD_SEALS, F_GET_SEALS)', 'eed09398fbac'),
    ('provider_execution.py', '_sealed_plan', 'os.dup'): (1, 'duplicates the memfd that holds the sealed plan, so it can be read again', 'd7d2ebd1097b'),
    ('provider_execution.py', '_sealed_plan', 'os.fdopen'): (2, REASON_FDOPEN, '00e7ae154d0b'),
    ('provider_execution.py', '_sealed_plan', 'write'): (1, REASON_FDWRITE, 'f92f6581619a'),
    ('provider_execution.py', '_sha', 'os.fdopen'): (1, REASON_FDOPEN, 'c60493c614fb'),
    ('provider_execution.py', '_supervise', 'subprocess'): (4, REASON_CHILD, '49c64e4711ae'),
    ('provider_journey.py', '<module>', 'import fcntl'): (1, REASON_IMPORTFCNTL, '62be1296afdd'),
    ('provider_journey.py', '_bounded_private_json', 'os.fdopen'): (1, REASON_FDOPEN, '8c6db9a3e15b'),
    ('provider_journey.py', 'read_credential_fd', 'fcntl'): (6, 'sets the credential descriptor non-blocking while it is read, then restores its flags', 'ee806a64157b'),
    ('provider_journey.py', 'read_credential_fd', 'os.dup'): (1, REASON_PROVIDERCRED, '3cf971095738'),
    ('repository.py', '_Repository._read', 'os.fdopen'): (1, REASON_FDOPEN, 'ee2e8141702d'),
    ('runner.py', '_dispatch', 'os.fdopen'): (1, REASON_FDOPEN, '4a54778c1c07'),
    ('runner.py', '_dispatch', 'write'): (1, REASON_FDWRITE, 'cda85d7c787a'),
    ('runner.py', 'run', 'os.fdopen'): (1, REASON_FDOPEN, 'e39ec6c7329a'),
    ('runner.py', 'run', 'write'): (1, REASON_FDWRITE, 'a0392b1c8b70'),
    ('signin.py', '<module>', 'import signal'): (1, REASON_IMPORTSIGNAL, '12a6a2fcbcd2'),
    ('signin.py', '<module>', 'import subprocess'): (1, REASON_CHILDMODULE, '8db6dc17950c'),
    ('signin.py', '_bounded', 'subprocess'): (5, REASON_CHILD, 'cbed676779c3'),
    ('signin.py', '_kill', 'signal'): (1, REASON_KILLGROUP, 'e43e195bbb5f'),
    ('signin.py', 'collect', 'os.write'): (1, 'the token, written to the pipe of the collecting child', '97d1ca87ec62'),
    ('sim_cli.py', 'text_lines', 'sys.stdout'): (1, REASON_PROBE, '47415ec2ecdb'),
    ('sim_fixture.py', '<module>', 'exit-text'): (1, 'raise SystemExit(main()): the status main returns, when the module runs as a script', '04d89e0f6d85'),
    ('sim_fixture.py', 'main', 'namespace'): (1, 'the parse of a separate program (python -m intune_iac.sim_fixture) with a command line of its own; cli.main never calls it, and a machine leaf that did is walked by the reach check like any function', 'b46536bf23cc'),
    ('synthetic.py', 'write_estate', 'write'): (1, 'writes a synthetic estate file (Path.write_text)', '161549ab81e5'),
    ('validity.py', '<module>', 'import fcntl'): (1, REASON_IMPORTFCNTL, '4c72edfd437e'),
    ('validity.py', 'critical', 'fcntl'): (2, REASON_FLOCK, '5641776858a0'),
    ('windows_directory.py', '_Win32.__init__', 'ctypes.WinDLL'): (2, 'kernel32 and advapi32, for directory and file calls: the base of the Windows storage classes (windows_storage, windows_observer_credentials), not the console API', 'd6b3b50af8b6'),
    ('windows_observation_jobs.py', '_IO.publish', 'write'): (1, 'a file of the observer store, through its Windows file API', '038416f0508c'),
    ('windows_observation_jobs.py', '_create_job', 'write'): (2, 'files of the observer store, through its Windows file API', 'be9ab9517fe5'),
    ('windows_observation_jobs.py', 'scheduler_artifacts', 'import subprocess'): (1, 'imports subprocess for list2cmdline only', '50126ff26b38'),
    ('windows_observation_jobs.py', 'scheduler_artifacts', 'subprocess'): (1, 'list2cmdline quotes an argument of the task file; starts nothing', 'cbd6ed60cc4c'),
    ('windows_observation_jobs.py', 'scheduler_artifacts', 'write'): (2, 'files of the observer store, through its Windows file API', '732fcf064e8f'),
    ('windows_storage.py', '_create_file', 'write'): (1, 'the Windows file API: a handle the function created', 'c1600b6921ce'),
    ('windows_workspace_context.py', '_ContextCore._validate', 'namespace'): (1, 'a stand-in with one field, store, handed to Workspace._validate_context; not a namespace of the command line', '0a9499f7b1a1'),
    ('wizard.py', '_WizardSession.handle_restart', 'write'): (1, 'writes the copy of the session file kept before a restart, at a path it builds (open(candidate, "xb"))', 'b919a38ebfa3'),
    ('wizard.py', 'run_wizard', 'os.fdopen'): (1, REASON_FDOPEN, '4c983a7cc5c6'),
    ('wizard.py', 'run_wizard', 'write'): (1, REASON_FDWRITE, '42120b8a910d'),
    ('workbench.py', '<module>', 'import signal'): (1, REASON_IMPORTSIGNAL, '48fad532600b'),
    ('workbench.py', '_actions', 'signal'): (7, REASON_LOCALSIGNAL, '5f9993431c85'),
    ('workbench.py', '_attention', 'signal'): (4, REASON_LOCALSIGNAL, '136b2ec50b0c'),
    ('workbench.py', '_intent_blocker', 'signal'): (3, REASON_LOCALSIGNAL, '43f6ac53b6ac'),
    ('workbench.py', '_next_actions', 'signal'): (3, REASON_LOCALSIGNAL, '76b26303868f'),
    ('workbench.py', '_referenced_operations', 'signal'): (4, REASON_LOCALSIGNAL, '86739a8d85e4'),
    ('workbench.py', '_states', 'signal'): (3, REASON_LOCALSIGNAL, 'e21941b9df49'),
    ('workbench.py', '_with_collect_cures', 'signal'): (5, REASON_LOCALSIGNAL, 'ca8ec75699a1'),
    ('workbench.py', 'interrupted_lines', '__import__'): (2, REASON_READINESS, '4bfac0699512'),
    ('workbench.py', 'run_terminal', 'signal'): (6, 'installs a SIGINT handler for the line terminal so that Ctrl-C ends the session cleanly; writes nothing', 'c308f181e5ab'),
    ('workbench.py', 'run_terminal.receive_interrupt', 'signal'): (1, 'installs a SIGINT handler for the line terminal so that Ctrl-C ends the session cleanly; writes nothing', '65ee405d7a15'),
    ('workbench_adoption.py', '<module>', 'import fcntl'): (1, REASON_IMPORTFCNTL, '33d66622e658'),
    ('workbench_adoption.py', '_lock', 'fcntl'): (3, REASON_FLOCK, 'f5e0fb762ad1'),
    ('workbench_queue.py', 'template', 'write'): (1, 'writes the review form at the fresh path it is given (open(path, "x")), after refusing an existing one', '305e2bd5e20a'),
    ('workbench_revision.py', 'verify_revision', 'os.dup'): (1, REASON_DUP, '1f15440d67c7'),
    ('workbench_revision.py', 'verify_revision', 'os.fdopen'): (1, REASON_FDOPEN, 'aaa964abeeb6'),
    ('workbench_scheduler.py', '<module>', 'import fcntl'): (1, REASON_IMPORTFCNTL, '8e01eb5a5079'),
    ('workbench_scheduler.py', '_lock', 'fcntl'): (3, REASON_FLOCK, '313d8b968ecc'),
    ('workbench_scheduler.py', '_open_pinned', 'os.dup'): (1, REASON_DUP, '82281dbaa8b2'),
    ('workbench_scheduler.py', '_open_pinned', 'os.fdopen'): (1, REASON_FDOPEN, '29e9ec9e58c2'),
    ('workbench_scheduler.py', '_save_bytes', 'os.fdopen'): (1, REASON_FDOPEN, 'd112c1c63e8b'),
    ('workbench_scheduler.py', '_save_bytes', 'write'): (1, REASON_FDWRITE, '55d5afb72e95'),
    ('workbench_screens.py', '<module>', '__import__'): (1, REASON_READINESS, 'fb9d8222b700'),
    ('workbench_screens.py', 'queue_lines', '__import__'): (2, REASON_READINESS, '0bce5abe25d3'),
    ('workbench_screens.py', 'repository_lines', '__import__'): (1, REASON_READINESS, '67b37923d7ce'),
    ('workbench_screens.py', 'review_lines', '__import__'): (1, REASON_READINESS, '0459870a33f2'),
    ('workbench_screens.py', 'state_lines', '__import__'): (1, REASON_READINESS, '391075c8ad25'),
    ('workbench_tui.py', 'Workspace._plan_record', 'dynamic access'): (1, 'the instance dictionary as a cache: setdefault of a private key', '5bd5d26a6a6a'),
    ('workbench_tui.py', 'Workspace._strip_note', 'dynamic access'): (1, 'the instance dictionary as a cache: setdefault of a private key', '9fd4728f60c5'),
    ('workbench_tui.py', 'Workspace.input', '__import__'): (1, REASON_READINESS, '9c7e65b5810d'),
    ('workbench_tui.py', 'visual_supported', 'import termios'): (1, 'asks whether stdin is a terminal that can be put in raw mode; writes nothing', '2fb79941c201'),
    ('workbench_tui.py', 'visual_supported', 'sys.stdin'): (2, 'asks whether stdin and stdout are terminals that can be put in raw mode; writes nothing', '9530699c7431'),
    ('workbench_tui.py', 'visual_supported', 'sys.stdout'): (1, 'asks whether stdin and stdout are terminals that can be put in raw mode; writes nothing', '4f5705fd67a7'),
    ('workbench_tui.py', 'visual_supported', 'termios'): (1, 'asks whether stdin is a terminal that can be put in raw mode; writes nothing', '05cbff8da8e9'),
    ('workbench_views.py', 'propose_source_acceptance', 'os.fdopen'): (1, REASON_FDOPEN, '5250c02ef0d6'),
    ('workbench_views.py', 'propose_source_acceptance', 'write'): (1, REASON_FDWRITE, '1460362c3198'),
    ('worker_adoption.py', '<module>', 'import signal'): (1, REASON_IMPORTSIGNAL, '348a342a8f64'),
    ('worker_adoption.py', 'AdoptionJob._dispatch.monitor', 'signal'): (1, REASON_SELFINT, '631d197d57da'),
    ('worker_adoption.py', '_authenticate', 'os.dup'): (1, REASON_DUP, 'f5adcb043f76'),
    ('worker_adoption.py', '_authenticate', 'os.fdopen'): (1, REASON_FDOPEN, '61ec7699198d'),
    ('worker_adoption_plan_recovery.py', 'AdoptionPlanRecoveryPolicy._verified', 'os.dup'): (1, REASON_DUP, 'aae037cf41d2'),
    ('worker_adoption_plan_recovery.py', 'AdoptionPlanRecoveryPolicy._verified', 'os.fdopen'): (1, REASON_FDOPEN, '10260e6aa0b7'),
    ('worker_adoption_reconcile.py', '<module>', 'import signal'): (1, REASON_IMPORTSIGNAL, '16b435b1ff09'),
    ('worker_adoption_reconcile.py', 'RecoveryPlanJob._dispatch.monitor', 'signal'): (1, REASON_SELFINT, '368c80b80493'),
    ('worker_adoption_reconcile.py', '_authenticate', 'os.dup'): (1, REASON_DUP, '76e086a9995c'),
    ('worker_adoption_reconcile.py', '_authenticate', 'os.fdopen'): (1, REASON_FDOPEN, '931cb82f1d4f'),
    ('worker_adoption_recovery.py', 'AdoptionRecoveryPolicy._verified', 'os.dup'): (1, REASON_DUP, 'c48a0b814b1a'),
    ('worker_adoption_recovery.py', 'AdoptionRecoveryPolicy._verified', 'os.fdopen'): (1, REASON_FDOPEN, 'd7d44e8b8fb3'),
    ('worker_adoption_state.py', '_retain', 'os.fdopen'): (1, REASON_FDOPEN, '60fb40a46198'),
    ('worker_adoption_state.py', '_retain', 'write'): (1, REASON_FDWRITE, 'f4f6592f7133'),
    ('worker_committed_readback.py', 'collect', 'os.fdopen'): (1, REASON_FDOPEN, 'd9abf5fc59f8'),
    ('worker_committed_recovery.py', 'CommittedRecoveryPolicy._verified', 'os.dup'): (1, REASON_DUP, '4fb001b26c91'),
    ('worker_committed_recovery.py', 'CommittedRecoveryPolicy._verified', 'os.fdopen'): (1, REASON_FDOPEN, 'd2d856ceae55'),
    ('worker_completed_readback.py', 'collect', 'os.fdopen'): (1, REASON_FDOPEN, 'fbd3d91b0c13'),
    ('worker_evidence_posix.py', 'DetachedVerifier.__call__', 'os.dup'): (1, REASON_DUP, '39d2c22c765c'),
    ('worker_evidence_posix.py', 'DetachedVerifier.__call__', 'os.fdopen'): (1, REASON_FDOPEN, '5a73903b8a2f'),
    ('worker_evidence_posix.py', '_capture', '__import__'): (1, 'imports re by a literal name, to match a file name', '3228b59bf2ff'),
    ('worker_evidence_posix.py', '_locked_now', 'fcntl'): (2, REASON_FLOCK, 'be46003b2163'),
    ('worker_evidence_posix.py', '_locked_now', 'import fcntl'): (1, REASON_IMPORTFCNTL, 'ac641f0249cb'),
    ('worker_evidence_posix.py', 'reopen', '__import__'): (1, 'imports re by a literal name, to match a file name', 'c29fac004384'),
    ('worker_host.py', '<module>', 'import signal'): (1, REASON_IMPORTSIGNAL, '6ee08dbbcb71'),
    ('worker_host.py', '<module>', 'import subprocess'): (1, REASON_CHILDMODULE, '3e0c051bccd7'),
    ('worker_host.py', '_Docker.run', 'os.dup'): (1, REASON_DUP, '063e19680e04'),
    ('worker_host.py', '_Docker.run', 'os.fdopen'): (1, REASON_FDOPEN, 'e59a53a227f1'),
    ('worker_host.py', '_Docker.run', 'subprocess'): (4, REASON_CHILD, '956bbc98cb91'),
    ('worker_host.py', '_bytes', 'os.fdopen'): (1, REASON_FDOPEN, 'a3eb2ab705e0'),
    ('worker_host.py', '_bytes', 'write'): (1, REASON_FDWRITE, '353b4f30cfde'),
    ('worker_host.py', '_hash_file', 'os.fdopen'): (1, REASON_FDOPEN, 'd4e341f2cdb9'),
    ('worker_host.py', 'launch', 'signal'): (7, 'ignores SIGINT around the launch of the container child, then restores the handler', '93ff6148a072'),
    ('worker_lease_recovery.py', 'RecoveryPolicy._verified', 'os.dup'): (1, REASON_DUP, '5ca8d6d5809c'),
    ('worker_lease_recovery.py', 'RecoveryPolicy._verified', 'os.fdopen'): (1, REASON_FDOPEN, 'a5fee3681458'),
    ('worker_provider.py', 'publish_files', 'os.fdopen'): (1, REASON_FDOPEN, 'cd0273abafe4'),
    ('worker_provider.py', 'publish_files', 'write'): (1, REASON_FDWRITE, '0bbe30481352'),
    ('worker_recovery.py', '<module>', 'exit-text'): (1, 'raise SystemExit(main()): the status main returns, when the module runs as a script', '6ff0ce264664'),
    ('worker_recovery.py', 'main', 'namespace'): (1, 'the parse of a separate program (python -m intune_iac.worker_recovery) with a command line of its own; cli.main never calls it, and a machine leaf that did is walked by the reach check like any function', '0ea5128c4059'),
    ('worker_recovery.py', 'main', 'os.write'): (1, 'the bytes of the output file it opened, to its own descriptor', '6356b272db12'),
    ('worker_recovery.py', 'main', 'print'): (2, 'a JSON document made by canonical (machine form)', 'ee0ad592e885'),
    ('worker_runtime_identity.py', '<module>', 'import importlib'): (1, REASON_IMPORTLIB, 'd73e82e694f5'),
    ('worker_runtime_identity.py', 'inventory', 'ctypes.CDLL'): (1, 'loads libseccomp for the runtime inventory', '68f71f7d6493'),
    ('worker_runtime_identity.py', 'inventory', 'importlib'): (1, 'importlib.util.source_from_cache: the path of a loaded module, for the inventory', 'bb43f62fd239'),
    ('worker_runtime_identity.py', 'inventory', 'sys.modules'): (1, 'lists the loaded modules for the runtime inventory', 'cb370e5fae3d'),
    ('worker_service.py', '<module>', 'import signal'): (1, REASON_IMPORTSIGNAL, 'ad48e0e9e620'),
    ('worker_service.py', 'ServiceJob.run.monitor', 'signal'): (1, REASON_SELFINT, '64e54e3b1c31'),
    ('worker_service.py', 'ServicePolicy._authenticate', 'os.dup'): (1, REASON_DUP, 'c35b927b6559'),
    ('worker_service.py', 'ServicePolicy._authenticate', 'os.fdopen'): (1, REASON_FDOPEN, 'f9ed740fb7e9'),
    ('worker_service.py', '_bounded_private_json', 'os.fdopen'): (1, REASON_FDOPEN, 'eecb2a0abbf3'),
    ('worker_successor.py', '_authenticated', 'os.dup'): (1, REASON_DUP, 'ef57d61f9692'),
    ('worker_successor.py', '_authenticated', 'os.fdopen'): (1, REASON_FDOPEN, 'd61d775a9594'),
    ('workflow.py', 'run_guided_workflow', 'os.fdopen'): (1, REASON_FDOPEN, 'bd45e44b8aeb'),
    ('workflow.py', 'run_guided_workflow', 'write'): (1, REASON_FDWRITE, '062e09ebb4b0'),
}
SCAN_NAMES = frozenset(('print', 'input', 'exec', 'eval', 'compile', '__import__', 'globals', 'locals', '__builtins__', 'breakpoint',
                        '_write_text'))
BUILTINS_SCANNED = SCAN_NAMES | {'SystemExit', 'exit', 'quit'}                # names a load stands for even where the file imports nothing
SCAN_STREAMS = ('sys.stdout', 'sys.stderr', 'sys.stdin', 'sys.__stdout__', 'sys.__stderr__', 'sys.__stdin__', 'sys.modules')
SCAN_OS = re.compile(r'(?:write|writev|pwrite|pwritev|sendfile|copy_file_range|splice|fdopen|dup|dup2|system|popen|startfile|openpty|forkpty|fork|exec\w*'
                     r'|spawn\w*|posix_spawn\w*)\Z')
SCAN_MODULES = frozenset(('builtins', 'subprocess', 'pty', 'importlib', 'logging', 'warnings', 'traceback', 'getpass', 'curses', 'cmd',
                          'code', 'pdb', 'pprint', 'rich', 'click', 'typer', 'tqdm', 'colorama', 'webbrowser', 'asyncio',
                          'multiprocessing', 'concurrent', 'runpy', 'imp', 'fcntl', 'termios', 'signal', 'pickle', 'marshal',
                          'shelve', 'readline', 'tty', 'msvcrt', '_winapi'))
SCAN_LOADERS = frozenset(('CDLL', 'cdll', 'PyDLL', 'pythonapi', 'windll', 'WinDLL', 'oledll', 'OleDLL'))      # ctypes: loads a native library
SCAN_DUNDERS = frozenset(('__dict__', '__globals__', '__builtins__', '__subclasses__', '__getattribute__', '__loader__', '__code__',
                          '__closure__', '__mro__', '__bases__', '__base__'))
PARSER_OUTPUT = ('print_usage', 'print_help', 'error')
NAMESPACES = ('Namespace', 'SimpleNamespace')                    # an object that can carry route values of its own
PARSE_CALLS = ('parse_args', 'parse_known_args', 'parse_intermixed_args', 'parse_known_intermixed_args')    # argparse: a namespace from an argv
SCAN_CONSOLE = re.compile(r'(?:WriteConsole\w*|GetStdHandle|SetStdHandle|AllocConsole|AttachConsole|CreateConsoleScreenBuffer'
                          r'|SetConsoleActiveScreenBuffer)\Z')      # the Win32 calls that write to the console, or choose where its output goes
DESCRIPTOR_CALLS = frozenset(('os.fdopen', 'os.dup', 'os.dup2', 'os.write', 'os.writev', 'os.pwrite', 'os.pwritev', 'os.sendfile',
                              'os.copy_file_range', 'os.splice'))                     # calls whose descriptor argument may be fd 0, 1 or 2
CHILD_CALLS = frozenset(('subprocess.Popen', 'subprocess.run', 'subprocess.call', 'subprocess.check_call', 'subprocess.check_output'))
DEVICE_PATH = re.compile(r'/dev/(?:tty|pts/|stdout|stderr|stdin|console|fd/)|/proc/(?:self|\d+)/fd/[012]\b|CONOUT\$|CONIN\$')


def package_sources():
    """{file name: source text} of the product's modules, read from disk."""
    return {str(path.relative_to(PACKAGE)): path.read_text(encoding='utf-8') for path in sorted(PACKAGE.rglob('*.py'))}


def not_a_status(node):
    """An exit argument that is not plainly a status: the interpreter writes anything but an integer or None to standard error."""
    return not (isinstance(node, ast.Constant) and (node.value is None or isinstance(node.value, int)))


INSIDE = ('body', 'orelse', 'finalbody', 'handlers', 'cases')      # the fields of a compound statement that hold other statements


def canon(node):
    """The code of a node as text that depends on nothing but the code: its class and the fields that are set, no line or column."""
    if isinstance(node, ast.AST):
        fields = ' '.join('%s=%s' % (field, canon(getattr(node, field))) for field in node._fields
                          if getattr(node, field, None) not in (None, []))
        return '(%s%s)' % (type(node).__name__, ' ' + fields if fields else '')
    if isinstance(node, list):
        return '[' + ' '.join(canon(item) for item in node) + ']'
    return repr(node)


def header(statement):
    """A statement without the statements inside it: the line of code, or the head of a compound one."""
    fields = ' '.join('%s=%s' % (field, canon(getattr(statement, field))) for field in statement._fields
                      if field not in INSIDE and getattr(statement, field, None) not in (None, []))
    return '(%s%s)' % (type(statement).__name__, ' ' + fields if fields else '')


def binds_name(target, name):
    """The assignment target binds the name."""
    if isinstance(target, ast.Name):
        return target.id == name
    if isinstance(target, (ast.Tuple, ast.List)):
        return any(binds_name(item, name) for item in target.elts)
    return isinstance(target, ast.Starred) and binds_name(target.value, name)


def site_nodes(source):
    """[(function chain, kind, node, code)] for every site in the source of one module (see the note above); the chain is the names of
    the functions and classes around the node, and the code is the text of the statement the node is in and of the statements that bind
    the names that statement reads, so that a site whose code changes can be told from one that only moved. What a name stands for is every binding it has anywhere in the file, in any scope: each
    import of it and each assignment to it whose value is a name, a chain on a name, or a choice between such. A load is judged against
    all of them and is a site if any one makes it a site, so a name bound to os in one function and to json in another is both:
    `import os as channel` is not undone by an `import json as channel` elsewhere. A builtin keeps its builtin meaning whatever else
    the name is bound to."""
    tree = ast.parse(source)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    bindings = collections.defaultdict(set)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                bindings[alias.asname or alias.name.split('.')[0]].add(alias.name if alias.asname else alias.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            base = '.' * node.level + (node.module or '')
            for alias in node.names:
                bindings[alias.asname or alias.name].add(base + ('' if base.endswith('.') else '.') + alias.name)

    def possible(name):
        """Every qualified name a load of this name may stand for."""
        return bindings[name] | ({name} if name in BUILTINS_SCANNED else set())

    def dotted(node):
        """Every qualified name a chain rooted at a name may stand for: the root taken as each of its bindings, o.system as os.system."""
        parts = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        return {'.'.join([root] + parts[::-1]) for root in possible(node.id)} if isinstance(node, ast.Name) else set()

    def flows(expression):
        """What an expression may evaluate to, when it is a name, a chain on a name, or a choice between such."""
        if isinstance(expression, ast.IfExp):
            return flows(expression.body) | flows(expression.orelse)
        if isinstance(expression, ast.BoolOp):
            return set().union(*(flows(item) for item in expression.values))
        if isinstance(expression, ast.NamedExpr):
            return flows(expression.value)
        return dotted(expression) if isinstance(expression, (ast.Name, ast.Attribute)) else set()

    for _ in range(5):                                             # an assignment from a name that an assignment bound: to a fixed point
        before = sum(len(names) for names in bindings.values())
        for node in ast.walk(tree):
            pairs = ([(target, node.value) for target in node.targets] if isinstance(node, ast.Assign)
                     else [(node.target, node.value)] if isinstance(node, (ast.AnnAssign, ast.NamedExpr)) and node.value is not None
                     else [])
            for target, value in pairs:
                if isinstance(target, ast.Name):
                    bindings[target.id] |= flows(value)
        if sum(len(names) for names in bindings.values()) == before:
            break

    def where(node):
        names = []
        while node in parents:
            node = parents[node]
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.append(node.name)
        return '.'.join(reversed(names)) or '<module>'

    def route(qualified):
        """The kind of site a qualified name is, or None."""
        parts = (qualified or '').split('.')
        if parts[0] in SCAN_MODULES:
            return parts[0]
        for stream in SCAN_STREAMS:
            if qualified == stream or (qualified or '').startswith(stream + '.'):
                return stream
        if parts[0] == 'os' and len(parts) > 1 and SCAN_OS.match(parts[1]):
            return 'os.' + parts[1]
        if parts[0] == 'ctypes' and len(parts) > 1 and parts[1] in SCAN_LOADERS:
            return 'ctypes.' + parts[1]
        return None

    def classify(qualified):
        """The kind of site a qualified name is, or None: a builtin or the text sink by its bare name; a route of the standard library;
        or a name of the product's own that is a scan name, however it is reached (from .cli import _write_text as emit)."""
        if qualified in SCAN_NAMES:
            return qualified
        if route(qualified):
            return route(qualified)
        last = qualified.rsplit('.', 1)[-1]
        if last in SCAN_NAMES and (last == '_write_text' or qualified.startswith('.') or qualified.split('.')[0] == PACKAGE.name):
            return last
        return None

    def kinds_of(names):
        return {classify(name) for name in names} - {None}

    def machine_print(call):
        """The whole call can emit exactly one JSON document and nothing else, and print is the builtin and nothing else."""
        if (len(call.args) != 1 or not isinstance(call.args[0], ast.Call) or dotted(call.args[0].func) != {'json.dumps'}
                or bindings['print']):
            return False
        for keyword in call.keywords:
            end = keyword.arg == 'end' and isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str) \
                and not keyword.value.value.strip()
            if not (keyword.arg == 'flush' or end):                  # sep, file, **options, end that is not whitespace
                return False
        return True

    def a_known_path(call):
        """open( of a path that is written in the source: its first argument (or file=) is a string that names no terminal device. A path
        that is a name or an expression, a descriptor or a device is not known to be a file here, and the write is a site."""
        arguments = call.args[:1] + [keyword.value for keyword in call.keywords if keyword.arg == 'file']
        return (len(arguments) == 1 and isinstance(arguments[0], ast.Constant) and isinstance(arguments[0].value, str)
                and not DEVICE_PATH.search(arguments[0].value))

    def rebinds(body, name):
        """The block binds the name again: an assignment, a loop or with target, a handler, an import, a def, a parameter, a global."""
        for statement in body:
            for inner in ast.walk(statement):
                if (isinstance(inner, ast.Name) and inner.id == name and not isinstance(inner.ctx, ast.Load)) \
                        or (isinstance(inner, ast.arg) and inner.arg == name) \
                        or (isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and inner.name == name) \
                        or (isinstance(inner, ast.ExceptHandler) and inner.name == name) \
                        or (isinstance(inner, (ast.Global, ast.Nonlocal)) and name in inner.names) \
                        or (isinstance(inner, (ast.Import, ast.ImportFrom))
                            and any((alias.asname or alias.name.split('.')[0]) == name for alias in inner.names)):
                    return True
        return False

    def inside_open(call):
        """The call is a write lexically inside `with open(...) as name:` on that name, with no function between the two."""
        receiver, child, node = call.func.value, call, parents.get(call)
        if not isinstance(receiver, ast.Name) or bindings['open']:
            return False
        while node is not None:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
                return False
            if isinstance(node, ast.With) and child in node.body:
                for item in node.items:
                    opened = item.context_expr
                    if (isinstance(item.optional_vars, ast.Name) and item.optional_vars.id == receiver.id
                            and isinstance(opened, ast.Call) and isinstance(opened.func, ast.Name) and opened.func.id == 'open'
                            and a_known_path(opened) and not rebinds(node.body, receiver.id)):
                        return True
            child, node = node, parents.get(node)
        return False

    def anchor(node):
        """The statement, or exception handler, a node is part of."""
        while node is not None and not isinstance(node, (ast.stmt, ast.ExceptHandler)):
            node = parents.get(node)
        return node

    def reads(statement):
        """The names a statement reads on its own line, not those of the statements inside it."""
        names = set()
        for field in statement._fields:
            value = getattr(statement, field, None)
            for item in ([] if field in INSIDE else value if isinstance(value, list) else [value]):
                if isinstance(item, ast.AST):
                    names |= {inner.id for inner in ast.walk(item) if isinstance(inner, ast.Name) and isinstance(inner.ctx, ast.Load)}
        return names

    def outermost_function(node):
        outer = None
        while node in parents:
            node = parents[node]
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                outer = node
        return outer

    module_level, pending = [], list(tree.body)
    while pending:                                                   # the module without the insides of its functions and classes
        item = pending.pop()
        module_level.append(item)
        if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            pending.extend(ast.iter_child_nodes(item))
    binders_of = {}

    def loads(node):
        return {inner.id for inner in ast.walk(node) if isinstance(inner, ast.Name) and isinstance(inner.ctx, ast.Load)}

    def binders(scope, name):
        """{(code, the names it reads)} for the code that binds a name in a scope (the outermost function around a site, or the module): the
        head of each statement that assigns it, takes it as a loop or with target, handles it, imports it or defines it, the arguments of
        each function that takes it."""
        if (id(scope), name) not in binders_of:
            found_here = set()
            for inner in (module_level if scope is None else ast.walk(scope)):
                if (isinstance(inner, ast.Assign) and any(binds_name(item, name) for item in inner.targets)
                        or isinstance(inner, (ast.AnnAssign, ast.AugAssign)) and binds_name(inner.target, name)
                        or isinstance(inner, (ast.For, ast.AsyncFor)) and binds_name(inner.target, name)
                        or isinstance(inner, ast.With) and any(item.optional_vars is not None and binds_name(item.optional_vars, name)
                                                               for item in inner.items)
                        or isinstance(inner, ast.ExceptHandler) and inner.name == name
                        or isinstance(inner, (ast.Import, ast.ImportFrom))
                        and any((alias.asname or alias.name.split('.')[0]) == name for alias in inner.names)
                        or isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and inner.name == name):
                    found_here.add((header(inner), frozenset(reads(inner))))
                if isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)) and name in {
                        item.arg for item in ast.walk(inner.args) if isinstance(item, ast.arg)}:
                    found_here.add((canon(inner.args), frozenset(loads(inner.args))))
                if isinstance(inner, ast.comprehension) and binds_name(inner.target, name):
                    found_here.add((canon(inner), frozenset(loads(inner.iter)) | {n for test in inner.ifs for n in loads(test)}))
            binders_of[(id(scope), name)] = found_here
        return binders_of[(id(scope), name)]

    def around(statement):
        """The heads of the compound statements and handlers the statement is inside, outermost first."""
        heads, enclosing = [], parents.get(statement)
        while enclosing is not None:
            if isinstance(enclosing, (ast.stmt, ast.ExceptHandler)):
                heads.append(header(enclosing))
            enclosing = parents.get(enclosing)
        return heads[::-1]

    def code_of(node):
        statement = anchor(node)
        if statement is None:
            return canon(node)
        scope, bound, seen, frontier = outermost_function(statement), set(), set(), reads(statement)
        for _ in range(3):                                         # the code that binds what is read, and what that code reads
            fresh = set()
            for name in sorted(frontier - seen):
                seen.add(name)
                for code, names in binders(scope, name) | (binders(None, name) if scope is not None else set()):
                    bound.add(code)
                    fresh |= names
            frontier = fresh
        return ' / '.join(around(statement) + [header(statement)]) + ' <- ' + ' ; '.join(sorted(bound))

    found = []
    for node in ast.walk(tree):
        parent, kinds = parents.get(node), set()
        in_call = isinstance(parent, ast.Call) and parent.func is node
        is_root = isinstance(parent, ast.Attribute) and parent.value is node
        if isinstance(node, ast.Import):
            kinds = {'import ' + alias.name.split('.')[0] for alias in node.names if alias.name.split('.')[0] in SCAN_MODULES}
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or '').split('.')[0]
            if node.level or root == PACKAGE.name:
                kinds = {'import ' + alias.name for alias in node.names if alias.name in SCAN_NAMES}     # from .cli import _write_text
            elif root in SCAN_MODULES:
                kinds = {'import ' + root}
            elif root in ('sys', 'os', 'ctypes'):
                kinds = {'import %s.%s' % (root, alias.name) for alias in node.names
                         if alias.name == '*' or route('%s.%s' % (root, alias.name))}
            kinds |= {'import _write_text' for alias in node.names if alias.name == '_write_text'}      # from wherever it is imported
            kinds |= {'import console' for alias in node.names if SCAN_CONSOLE.match(alias.name)}
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if DEVICE_PATH.search(node.value):
                kinds = {'device path'}
            elif node.value == '_write_text':
                kinds = {'_write_text as a string'}                    # getattr(cli, "_write_text"): the product's own text sink by name
            elif node.value in PARSE_CALLS:
                kinds = {'namespace'}                                  # getattr(parser, "parse_args"): a namespace of its own
            elif SCAN_CONSOLE.match(node.value):
                kinds = {'console'}                                    # a table of signatures keyed by the name, getattr(kernel32, "WriteConsoleW")
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id in SCAN_NAMES and not (node.id == 'print' and in_call and machine_print(parent)):
                kinds.add(node.id)                                     # the builtin, whatever else the name is bound to
            if node.id in NAMESPACES or any(name.rsplit('.', 1)[-1] in NAMESPACES for name in bindings[node.id]):
                kinds.add('namespace')
            if SCAN_CONSOLE.match(node.id):
                kinds.add('console')
            if not is_root:                                            # the root of a chain is judged with the chain
                kinds |= kinds_of(bindings[node.id])
                for module in sorted({'sys', 'os'} & bindings[node.id]):
                    probe = (isinstance(parent, ast.Call) and isinstance(parent.func, ast.Name) and parent.func.id in ('getattr', 'hasattr')
                             and parent.args[:1] == [node] and len(parent.args) > 1 and isinstance(parent.args[1], ast.Constant)
                             and isinstance(parent.args[1].value, str) and not route('%s.%s' % (module, parent.args[1].value)))
                    if not probe:
                        kinds.add(module + ' as a value')
            if node.id in ('SystemExit', 'exit', 'quit'):
                holder = parent
                while isinstance(holder, (ast.Tuple, ast.List)):
                    holder = parents.get(holder)
                names_the_class = ((isinstance(holder, ast.Call) and isinstance(holder.func, ast.Name)
                                    and holder.func.id in ('isinstance', 'issubclass'))
                                   or (isinstance(holder, ast.ExceptHandler) and holder.type is not None)
                                   or (isinstance(holder, ast.Raise) and holder.exc is node))
                if not in_call and not names_the_class:
                    kinds.add('exit-text')                              # handed on: what it carries is not seen here
        elif isinstance(node, ast.Attribute) and not isinstance(node.ctx, ast.Load):
            holder = node.value
            if SCAN_CONSOLE.match(node.attr):
                kinds.add('console')                                    # kernel32.WriteConsoleW = ...
            if (node.attr == 'command' or node.attr.endswith('_command')) and (
                    (isinstance(holder, ast.Name) and holder.id not in ('self', 'cls'))
                    or (isinstance(holder, ast.Attribute) and holder.attr in ('args', 'namespace'))):
                kinds.add('route value stored')                         # args.workbench_command = ..., not self.command
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            if node.attr in NAMESPACES or node.attr in PARSE_CALLS:
                kinds.add('namespace')
            if SCAN_CONSOLE.match(node.attr):
                kinds.add('console')                                    # of anything: api.k.WriteConsoleW, d.k.GetStdHandle
            if node.attr in SCAN_DUNDERS:
                kinds.add('dynamic access')
            if not is_root and kinds_of(dotted(node)):
                kinds |= kinds_of(dotted(node))                         # the outermost link of a chain names the site once
            elif node.attr in PARSER_OUTPUT and not is_root:
                kinds.add('parser-output')
            if node.attr == 'exit' and not in_call:
                kinds.add('exit-text')
        elif isinstance(node, ast.Call):
            func = node.func
            called = dotted(func) if isinstance(func, (ast.Attribute, ast.Name)) else set()
            if isinstance(func, ast.Name) and func.id in ('setattr', 'vars') and node.args and (
                    (isinstance(node.args[0], ast.Name) and node.args[0].id == 'args')
                    or (func.id == 'setattr' and len(node.args) > 1 and isinstance(node.args[1], ast.Constant)
                        and isinstance(node.args[1].value, str) and (node.args[1].value == 'command' or node.args[1].value.endswith('_command')))):
                kinds.add('route value stored')                         # setattr(args, ...), vars(args)[...] = ..., setattr(x, "..._command", ...)
            if isinstance(func, ast.Attribute) and func.attr in ('write', 'writelines', 'write_text', 'write_bytes'):
                if not inside_open(node) and not any((classify(name) or '').startswith('os.') for name in called):
                    kinds.add('write')                                  # os.write is its own kind
            if ((isinstance(func, ast.Name) and func.id in ('SystemExit', 'exit', 'quit'))
                    or (isinstance(func, ast.Attribute) and func.attr == 'exit')) and any(not_a_status(item) for item in node.args):
                kinds.add('exit-text')
            if called & DESCRIPTOR_CALLS or (isinstance(func, ast.Name) and func.id == 'open' and not bindings['open']):
                given = node.args[:2] + [keyword.value for keyword in node.keywords if keyword.arg in ('fd', 'file', 'out_fd', 'dst')]
                if any(isinstance(item, ast.Constant) and isinstance(item.value, int) and not isinstance(item.value, bool)
                       and item.value in (0, 1, 2) for item in given):
                    kinds.add('standard descriptor')                    # the terminal itself, however it is opened or copied to
            if called & CHILD_CALLS:
                ends = {keyword.arg: dotted(keyword.value) for keyword in node.keywords if keyword.arg in ('stdout', 'stderr')}
                if not (ends.get('stdout') and ends['stdout'] <= {'subprocess.PIPE', 'subprocess.DEVNULL'}
                        and ends.get('stderr') and ends['stderr'] <= {'subprocess.PIPE', 'subprocess.DEVNULL', 'subprocess.STDOUT'}):
                    kinds.add('child on the terminal')                  # a child whose output is not taken writes where it likes
        if kinds:
            code = code_of(node)
            found += [(where(node), kind, node, code) for kind in sorted(kinds)]
    return found


@functools.lru_cache(maxsize=None)
def file_sites(source):
    """(((function, kind), references, codes), ...) for the source of one module: how many references the site has, and the code of each,
    sorted. Cached by source, so a test that adds or changes one module reads the product's other modules once."""
    found = collections.defaultdict(list)
    for chain, kind, _, code in site_nodes(source):
        found[(chain, kind)].append(code)
    return tuple((site, len(codes), tuple(sorted(codes))) for site, codes in found.items())


def output_sites(sources=None):
    """{(file, function, kind): references} for every site in the sources (the product's modules by default)."""
    found = collections.Counter()
    for name, source in (package_sources() if sources is None else sources).items():
        for (function, kind), count, _ in file_sites(source):
            found[(name, function, kind)] += count
    return found


def output_fingerprints(sources=None):
    """{(file, function, kind): fingerprint} for every site in the sources: a hash of the code of its references (see site_nodes), its file,
    its function and its kind. The code is the AST of the statement and of the statements that bind what it reads, with no line or column,
    so a site that moves keeps its fingerprint and a site whose code changes does not, though it has as many references as before."""
    found = {}
    for name, source in (package_sources() if sources is None else sources).items():
        for (function, kind), _, codes in file_sites(source):
            found[(name, function, kind)] = hashlib.sha256('\n'.join((name, function, kind) + codes).encode('utf-8')).hexdigest()[:12]
    return found


def output_site_problems(sources=None, listed=None, table=None, others=None):
    """[str] for what differs between the sites of the sources and OUTPUT_SITES with NOT_A_TERMINAL: a site that is not listed, a site
    with another number of references, a listed site that is gone, a site listed in both, a site that serves a leaf the table does not
    classify as text or session, and a session leaf that no site serves. A listed site also fails when its code is not the code that was
    listed (its fingerprint), though it has as many references as before."""
    listed = OUTPUT_SITES if listed is None else listed
    others = NOT_A_TERMINAL if others is None else others
    found = output_sites(sources)
    prints = output_fingerprints(sources)
    problems = ['%s: %s %s is listed as a terminal site and as a site that reaches no terminal' % site for site in sorted(set(listed) & set(others))]
    counts = {site: value[0] for site, value in list(others.items()) + list(listed.items())}
    listed_prints = {site: value[2] for site, value in list(others.items()) + list(listed.items())}
    for site, calls in sorted(found.items()):
        if site not in counts:
            problems.append('%s: %s has %d unlisted %s site(s)' % (site[0], site[1], calls, site[2]))
        elif counts[site] != calls:
            problems.append('%s: %s has %d %s site(s), %d listed' % (site[0], site[1], calls, site[2], counts[site]))
        elif prints[site] != listed_prints[site]:
            problems.append('%s: %s %s: its code changed (fingerprint %s, listed %s)' % (site + (prints[site], listed_prints[site])))
    problems += ['%s: %s %s is listed and the sources have no such site' % site for site in sorted(set(counts) - set(found))]
    kinds = {' '.join(path): kind for path, kind in leaf_table(table).items()}
    for site, (calls, serves, _) in sorted(listed.items(), key=str):
        if serves is not None and kinds.get(serves) not in ('session', 'text'):
            problems.append('the site %s: %s serves %r, which the table does not classify as text or session' % (site[0], site[1], serves))
    served = {value[1] for value in listed.values()}
    problems += ['the session leaf %r is served by no listed site' % leaf for leaf, kind in sorted(kinds.items())
                 if kind == 'session' and leaf not in served]
    return problems


# -- what a machine leaf can run ---------------------------------------------------------------------------------------------------------
#
# The scan above says where the product can put text in front of a person; it does not say who can get there. A leaf that LEAF_TABLE calls a
# machine form must not run a function that holds a terminal site (a site of OUTPUT_SITES; the usage error of every route, which the help
# sweep drives, is not one), unless that site is behind a route condition the leaf fails. The call graph of intune_iac is static and
# conservative. A direct name, and a name imported from a module of the product, resolve exactly: to that function, or to the __init__ of
# that class. An attribute call x.m(...), or an attribute passed on as a value, reaches every function or method named m in the product
# (and every getter of a property named m, on any load); super().m(...) reaches the m of the bases. A name or an attribute of an imported
# module of the standard library reaches nothing of the product. `with` reaches every __enter__ and __exit__, an import reaches the module,
# a function reached reaches the functions it names. The if-chains of cli.main, of cli.execute and of every function that dispatches on
# args.<route> (or on a name that holds it) are read as route conditions: a route expression is true, false or unknown for the leaf (only a
# comparison of a route attribute with words is known; and, or and not follow Kleene's rules), and a branch is skipped only when the known
# comparisons decide the whole expression against it, so an operand that is not a route comparison keeps both branches. A reach
# that follows direct names only is exact; every other reach needs an attribute name, which is how a function that shares its name with an
# attribute some reached function uses is reached though nothing calls it. Both are listed (EXACT_REACHES, NAME_REACHES), by leaf and holder.
# Those conditions are the command line's own, so whatever makes another command line has to be seen: a namespace or a parse of an argv of its
# own is a site of the scan (namespace), and a call of cli.main from any function but the entry, by a name or by an attribute name, is a
# reach to REENTRY that no listing allows, so a leaf that runs the command line again with an argv of its own fails.

ESCAPES_NOT = (ast.Compare, ast.UnaryOp, ast.BinOp, ast.FormattedValue, ast.JoinedStr, ast.Expr, ast.Assert, ast.AugAssign)
INIT_METHODS = ('__init__', '__new__', '__post_init__', '__call__')
Ref = collections.namedtuple('Ref', 'kind name guards')
REENTRY = ('cli.py', 'main again')                                   # not a function: the command line run again, from a function other than the entry
FileReach = collections.namedtuple('FileReach', 'definitions classes refs imports guards')


def dotted_module(filename):
    """intune_iac.cli for cli.py, intune_iac.sub.x for sub/x.py, intune_iac for __init__.py."""
    parts = filename[:-3].split('/')
    return '.'.join([PACKAGE.name] + (parts[:-1] if parts[-1] == '__init__' else parts))


def route_attribute(node, aliases):
    """The route attribute an expression reads: args.dest, getattr(args, 'dest', ...), either of them in a walrus, or a name that holds one."""
    if isinstance(node, ast.NamedExpr):
        node = node.value
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == 'args':
        return node.attr
    if (isinstance(node, ast.Call) and getattr(node.func, 'id', '') == 'getattr' and len(node.args) >= 2 and isinstance(node.args[0], ast.Name)
            and node.args[0].id == 'args' and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str)):
        return node.args[1].value
    return aliases.get(node.id) if isinstance(node, ast.Name) else None


def route_aliases(body):
    """{local name: dest} for `name = args.dest`, `name = getattr(args, 'dest', None)` and the walrus form of both, when nothing else in the
    statements binds the name."""
    found, stores = {}, collections.Counter()
    for statement in body:
        for node in ast.walk(statement):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                stores[node.id] += 1
            if (isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)) or isinstance(node, ast.NamedExpr):
                dest = route_attribute(node.value, {})
                if dest:
                    found[(node.targets[0] if isinstance(node, ast.Assign) else node.target).id] = dest
    return {name: dest for name, dest in found.items() if stores[name] == 1}


def route_expression(test, aliases):
    """The route expression of an `if` test as a tree: ('and' | 'or', items), ('not', item), ('eq', attribute, words) for a comparison of a
    route attribute with a word, or with a tuple, list or set of words only (== and in), and ('unknown',) for everything else."""
    if isinstance(test, ast.BoolOp):
        return ('and' if isinstance(test.op, ast.And) else 'or', tuple(route_expression(item, aliases) for item in test.values))
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        return ('not', route_expression(test.operand, aliases))
    if isinstance(test, ast.NamedExpr):
        return route_expression(test.value, aliases)
    if isinstance(test, ast.Compare) and len(test.ops) == 1 and isinstance(test.ops[0], (ast.Eq, ast.In)):
        dest, right = route_attribute(test.left, aliases), test.comparators[0]
        if dest:
            items = ([right] if isinstance(test.ops[0], ast.Eq)
                     else right.elts if isinstance(right, (ast.Tuple, ast.List, ast.Set)) else [])
            if items and all(isinstance(item, ast.Constant) and isinstance(item.value, str) for item in items):
                return ('eq', dest, tuple(sorted({item.value for item in items})))
    return ('unknown',)


def route_value(tree, chosen, dests):
    """True, False or None (unknown): what a route expression is for a leaf whose route values are `chosen`. Only a comparison of a route
    attribute with words is known; and, or and not follow Kleene's rules, so an expression is decided only where the known comparisons
    decide it: an and with a false clause is false whatever else it holds, an and with a true clause and an unknown one is unknown."""
    if tree[0] == 'eq':
        return chosen.get(tree[1]) in tree[2] if tree[1] in dests else None
    if tree[0] == 'not':
        value = route_value(tree[1], chosen, dests)
        return None if value is None else not value
    if tree[0] in ('and', 'or'):
        values = [route_value(item, chosen, dests) for item in tree[1]]
        decided = tree[0] == 'or'
        return decided if decided in values else None if None in values else not decided
    return None


def value_escapes(node, parents):
    """The value of a name or attribute load leaves the place it is written in: passed on, kept, returned or put in a container. A
    comparison, an operand, a test, the object of an attribute or a subscript, and a bare expression statement do not pass it on."""
    parent = parents.get(node)
    if isinstance(parent, ESCAPES_NOT) or (isinstance(parent, ast.Call) and parent.func is node):
        return False
    if isinstance(parent, (ast.If, ast.While, ast.IfExp)) and parent.test is node:
        return False
    return not (isinstance(parent, (ast.Attribute, ast.Subscript)) and parent.value is node)


@functools.lru_cache(maxsize=None)
def file_reach(source, filename):
    """FileReach for one module: its functions (qualified name, name, whether a property getter) and classes (qualified name, name, bases as
    they are written, methods); what each function and the module body refer to (Ref: kind, name, the route conditions around it); what the module imports;
    and the route conditions around every node, by position. Cached by source and file name."""
    tree = ast.parse(source)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    module_name = dotted_module(filename)
    package = module_name if filename.endswith('__init__.py') else module_name.rsplit('.', 1)[0]

    def from_base(node):
        if not node.level:
            return node.module or ''
        parts = package.split('.')
        return '.'.join(parts[:len(parts) - (node.level - 1)] + ([node.module] if node.module else []))
    imports = collections.defaultdict(list)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports[alias.asname or alias.name.split('.')[0]].append(('import', alias.name if alias.asname else alias.name.split('.')[0]))
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imports[alias.asname or alias.name].append(('from', from_base(node), alias.name))

    def outside_the_product(name):
        """Every binding of the name in this file is a module or a name of the standard library or of another package."""
        return bool(imports.get(name)) and all(item[1].split('.')[0] != PACKAGE.name for item in imports[name])

    def qualified(node):
        names = [node.name]
        while node in parents:
            node = parents[node]
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.append(node.name)
        return '.'.join(reversed(names))

    def base_ref(item):
        """A base of a class as it is written: ('name', 'X'); ('module', ('a', ('b', 'X'))) for a.b.X; ('by name', 'X') for an attribute of
        something that is not a name; None for what is not a name at all. A subscript (Generic[T], Base[int]) is the class it subscripts."""
        if isinstance(item, ast.Subscript):
            item = item.value
        if isinstance(item, ast.Name):
            return ('name', item.id)
        if not isinstance(item, ast.Attribute):
            return None
        chain, root = [], item
        while isinstance(root, ast.Attribute):
            chain.append(root.attr)
            root = root.value
        return ('module', (root.id, tuple(reversed(chain)))) if isinstance(root, ast.Name) else ('by name', item.attr)

    definitions, classes = [], []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            is_property = any((isinstance(item, ast.Name) and item.id in ('property', 'cached_property'))
                              or (isinstance(item, ast.Attribute) and item.attr in ('setter', 'getter', 'deleter'))
                              for item in node.decorator_list)
            definitions.append((qualified(node), node.name, is_property))
        elif isinstance(node, ast.ClassDef):
            bases = tuple(ref for ref in (base_ref(item) for item in node.bases) if ref)
            classes.append((qualified(node), node.name, bases, tuple(
                (member.name, qualified(member)) for member in node.body if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)))))
    guards_by_position, refs = {}, {}

    def scan_scope(body, key):
        aliases, found = route_aliases(body), []

        def visit(root, guards):
            for node in ast.walk(root):
                if hasattr(node, 'lineno'):
                    guards_by_position[(node.lineno, node.col_offset)] = guards
                parent = parents.get(node)
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                    if (isinstance(parent, ast.Call) and parent.func is node) or value_escapes(node, parents):
                        found.append(Ref('name', node.id, guards))
                elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
                    chain, base = [], node
                    while isinstance(base, ast.Attribute):
                        chain.append(base.attr)
                        base = base.value
                    if isinstance(base, ast.Name) and outside_the_product(base.id):
                        continue                                    # an attribute of a module of the standard library
                    found.append(Ref('property', node.attr, guards))   # a getter runs on any load
                    is_call = isinstance(parent, ast.Call) and parent.func is node
                    if not (is_call or value_escapes(node, parents)):
                        continue
                    if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) and node.value.func.id == 'super':
                        owner = node
                        while owner in parents and not isinstance(owner, ast.ClassDef):
                            owner = parents[owner]
                        found.append(Ref('super', (node.attr, qualified(owner) if isinstance(owner, ast.ClassDef) else None), guards))
                    elif isinstance(base, ast.Name) and base.id in imports:
                        found.append(Ref('module', (base.id, tuple(reversed(chain))), guards))
                    else:
                        found.append(Ref('call' if is_call else 'value', node.attr, guards))
                elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'getattr' and len(node.args) >= 2
                      and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str)):
                    found.append(Ref('call', node.args[1].value, guards))

        def walk(statements, guards):
            for statement in statements:
                if hasattr(statement, 'lineno'):
                    guards_by_position[(statement.lineno, statement.col_offset)] = guards
                if isinstance(statement, ast.If):
                    tree = route_expression(statement.test, aliases)
                    visit(statement.test, guards)
                    walk(statement.body, guards + ((tree, False),))
                    walk(statement.orelse, guards + ((tree, True),))
                    continue
                if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for expression in statement.decorator_list + [statement.args] + ([statement.returns] if statement.returns else []):
                        visit(expression, guards)
                    continue
                if isinstance(statement, ast.ClassDef):
                    for expression in statement.decorator_list + statement.bases + [item.value for item in statement.keywords]:
                        visit(expression, guards)
                    walk(statement.body, guards)
                    continue
                if isinstance(statement, ast.With):
                    found.append(Ref('with', None, guards))
                if isinstance(statement, ast.Import):
                    found.extend(Ref('import', alias.name, guards) for alias in statement.names)
                elif isinstance(statement, ast.ImportFrom):
                    found.append(Ref('import', from_base(statement), guards))
                    found.extend(Ref('import', from_base(statement) + '.' + alias.name, guards) for alias in statement.names)
                inner = []
                for field in statement._fields:
                    value = getattr(statement, field, None)
                    for item in (value if isinstance(value, list) else [value]):
                        if isinstance(item, ast.stmt):
                            inner.append(item)
                        elif isinstance(item, ast.ExceptHandler):
                            if item.type is not None:
                                visit(item.type, guards)
                            inner += item.body
                        elif isinstance(item, ast.match_case):
                            inner += item.body
                        elif isinstance(item, ast.withitem):
                            visit(item.context_expr, guards)
                            if item.optional_vars is not None:
                                visit(item.optional_vars, guards)
                        elif isinstance(item, ast.AST):
                            visit(item, guards)
                walk(inner, guards)
        walk(body, ())
        refs[key] = tuple(found)

    scan_scope(tree.body, '<module>')
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            scan_scope(node.body, qualified(node))
    return FileReach(tuple(definitions), tuple(classes), refs, dict(imports), guards_by_position)


class ReachGraph:
    """The static call graph of a set of modules (a dict of file name to source; the product's by default). edges(function) are
    (target, the route conditions around the reference, whether the name was resolved exactly)."""

    def __init__(self, sources=None):
        sources = package_sources() if sources is None else sources
        self.files = {name: file_reach(source, name) for name, source in sources.items()}
        self.modules = {dotted_module(name): name for name in sources}
        self.functions = {(name, '<module>') for name in sources}
        self.by_name, self.properties = collections.defaultdict(set), collections.defaultdict(set)
        self.classes = collections.defaultdict(dict)
        for name, reach in self.files.items():
            for qualname, simple, is_property in reach.definitions:
                self.functions.add((name, qualname))
                self.by_name[simple].add((name, qualname))
                if is_property:
                    self.properties[simple].add((name, qualname))
            for qualname, simple, bases, methods in reach.classes:
                self.classes[simple][(name, qualname)] = (bases, dict(methods))
        self.cache, self.edge_cache, self.base_cache, self.ancestor_cache = {}, {}, {}, {}

    def named_classes(self, file, name, trail=()):
        """(keys, known): the classes of the product that a plain name stands for in a file, by the classes the file defines and the names it
        imports (a name that another module only re-exports is followed). known is False when the file does not say, a name it neither
        defines nor imports, and the caller then falls back on every class of that name, by name alone. A builtin, and a name that comes
        from outside the product, stand for no class of the product."""
        defined = {key for key in self.classes.get(name, {}) if key[0] == file}
        if defined:
            return defined, True
        items = self.files[file].imports.get(name, ())
        if not items:
            return set(), hasattr(builtins, name)
        keys, known = set(), True
        for item in items:
            if item[0] == 'from' and item[1] in self.modules and (file, name) not in trail:
                found, said = self.named_classes(self.modules[item[1]], item[2], trail + ((file, name),))
                keys |= found
                known = known and said
        return keys, known

    def module_classes(self, file, root, chain):
        """(keys, known) for a base written as a chain on an imported name, a.b.X: the class X of the module that a.b names, by the imports of
        the file. A chain on a module of the standard library, or of another package, stands for no class of the product."""
        items = self.files[file].imports.get(root, ())
        if not items:
            return set(), False
        keys, known = set(), True
        for item in items:
            prefix = item[1] if item[0] == 'import' else item[1] + '.' + item[2]
            if prefix.split('.')[0] != PACKAGE.name:
                continue
            module = '.'.join([prefix] + list(chain[:-1]))
            if module in self.modules:
                found, said = self.named_classes(self.modules[module], chain[-1])
                keys |= found
                known = known and said
            else:
                known = False
        return keys, known

    def base_classes(self, file, base):
        """(resolved, fallback): the classes a base written in a file stands for, found by the file's own definitions and imports; and, when
        they do not say, every class of that simple name anywhere in the product, which is an edge by name and never an exact one."""
        if (file, base) not in self.base_cache:
            kind, name = base
            if kind == 'name':
                keys, known, simple = *self.named_classes(file, name), name
            elif kind == 'module':
                keys, known, simple = *self.module_classes(file, name[0], name[1]), name[1][-1]
            else:
                keys, known, simple = set(), False, name
            self.base_cache[(file, base)] = (keys, set() if known else set(self.classes.get(simple, {})) - keys)
        return self.base_cache[(file, base)]

    def ancestors(self, key):
        """{class key: exact} for the bases of a class, their bases and so on, not the class itself. Exact when every link was found by the
        definitions and imports of the file that names the base, not by the name alone."""
        if key not in self.ancestor_cache:
            found, todo = {}, [(key, True)]
            while todo:
                current, exact = todo.pop()
                for base in self.classes.get(current[1].split('.')[-1], {}).get(current, ((), {}))[0]:
                    resolved, fallback = self.base_classes(current[0], base)
                    for target, link in [(item, exact) for item in sorted(resolved)] + [(item, False) for item in sorted(fallback)]:
                        if target != key and (target not in found or (link and not found[target])):
                            found[target] = link
                            todo.append((target, link))
            self.ancestor_cache[key] = found
        return self.ancestor_cache[key]

    def inits_of(self, keys, exact_start=True):
        """(exact, loose): the __init__, __new__, __post_init__ and __call__ of these classes and of their bases. What a base gives is exact
        when the class is (exact_start) and every link to it was resolved by the file that names it; a base found by its name alone gives
        edges by name."""
        exact, loose = set(), set()
        for key in keys:
            for target, link in [(key, True)] + sorted(self.ancestors(key).items()):
                methods = self.classes[target[1].split('.')[-1]][target][1]
                (exact if exact_start and link else loose).update((target[0], qualname) for method, qualname in methods.items()
                                                                   if method in INIT_METHODS)
        return exact, loose

    def inits(self, simple, only_file=None):
        """(exact, loose) for the classes with that name (in one file, when only_file is given): see inits_of."""
        return self.inits_of([key for key in self.classes.get(simple, {}) if only_file in (None, key[0])])

    def resolve(self, file, ref):
        """(exact targets, by-name targets) of a reference made in a file."""
        key = (file, ref.kind, ref.name)
        if key in self.cache:
            return self.cache[key]
        imports, exact, loose = self.files[file].imports, set(), set()
        if ref.kind == 'name':
            for item in imports.get(ref.name, ()):
                module, member = (item[1], None) if item[0] == 'import' else (item[1], item[2])
                if member is None:
                    if module in self.modules:
                        exact.add((self.modules[module], '<module>'))
                    continue
                if module in self.modules:
                    inherited, by_name = self.inits_of(self.named_classes(self.modules[module], member)[0])
                    exact |= inherited | {(self.modules[module], member), (self.modules[module], '<module>')}
                    loose |= by_name
                if module + '.' + member in self.modules:
                    exact.add((self.modules[module + '.' + member], '<module>'))
            inherited, by_name = self.inits(ref.name, file)
            exact |= {target for target in self.by_name.get(ref.name, ()) if target[0] == file} | inherited
            loose |= by_name
        elif ref.kind == 'module':
            root, chain = ref.name
            for item in imports.get(root, ()):
                prefix = item[1] if item[0] == 'import' else item[1] + '.' + item[2]
                for count in range(len(chain)):                      # the longest prefix of the chain that is a module of the product
                    module = '.'.join([prefix] + list(chain[:count]))
                    if module in self.modules:
                        inherited, by_name = self.inits(chain[count], self.modules[module])
                        exact |= {(self.modules[module], chain[count])} | inherited
                        loose |= by_name
            if not exact:
                loose |= set(self.by_name.get(chain[-1], ())) | set().union(*self.inits(chain[-1]))
        elif ref.kind in ('call', 'value'):
            loose = set(self.by_name.get(ref.name, ())) | set().union(*self.inits(ref.name))
        elif ref.kind == 'property':
            loose = set(self.properties.get(ref.name, ()))
        elif ref.kind == 'with':
            loose = set(self.by_name.get('__enter__', ())) | set(self.by_name.get('__exit__', ()))
        elif ref.kind == 'import':
            if ref.name in self.modules:
                exact.add((self.modules[ref.name], '<module>'))
        elif ref.kind == 'super':
            attribute, owner = ref.name
            for ancestor, link in sorted(self.ancestors((file, owner)).items()) if owner else ():
                methods = self.classes[ancestor[1].split('.')[-1]][ancestor][1]
                if attribute in methods:
                    (exact if link else loose).add((ancestor[0], methods[attribute]))
        self.cache[key] = (exact & self.functions, loose & self.functions)
        return self.cache[key]

    def edges(self, key):
        """[(target, guards, exact)] from a function (file, qualified name) or from a module body (file, '<module>')."""
        if key not in self.edge_cache:
            found = []
            for ref in self.files[key[0]].refs.get(key[1], ()):
                exact, loose = self.resolve(key[0], ref)
                found += [(target, ref.guards, True) for target in sorted(exact) if target != key]
                found += [(target, ref.guards, False) for target in sorted(loose - exact) if target != key]
            self.edge_cache[key] = found
        return self.edge_cache[key]


def passes(guards, chosen, dests):
    """A statement behind these route conditions can run for a leaf whose route values are `chosen`: none of its conditions is decided
    against it. The body of an `if` is out when its route expression is false for the leaf, and the else branch when it is true; an
    expression that is unknown (an operand that is not a route comparison keeps it open) takes neither branch out."""
    return all(route_value(tree, chosen, dests) is not negated for tree, negated in guards)


@functools.lru_cache(maxsize=None)
def terminal_positions(source):
    """{(function chain, kind): ((line, column), ...)} for the references of one module's source."""
    found = collections.defaultdict(list)
    for chain, kind, node, _ in site_nodes(source):
        found[(chain, kind)].append((node.lineno, node.col_offset))
    return {site: tuple(positions) for site, positions in found.items()}


def trail(parent, key):
    """The functions from a root to key, along the parents that the walk recorded."""
    path = []
    while key is not None:
        path.append(key)
        key = parent[key]
    return tuple(reversed(path))


def machine_reaches(sources=None, listed=None, table=None, leaves=None, graph=None):
    """{(leaf, (file, function)): ('exact' | 'name', path)} for every machine leaf and every function that holds a terminal site (a site of
    the listing, but cli._Parser.error) that the leaf can run: 'exact' along direct names only, 'name' when an attribute name is needed;
    the path is the functions from cli.main. A call of cli.main from a function other than the entry is a reach to REENTRY. leaves: the
    names of the leaves to judge, all the machine leaves by default."""
    from intune_iac import cli
    sources = package_sources() if sources is None else sources
    listed = OUTPUT_SITES if listed is None else listed
    graph, parser = ReachGraph(sources) if graph is None else graph, cli.parser()
    dests = parser_dests(parser)
    holders = collections.defaultdict(list)                               # (file, function) -> [(line, column)]
    for (name, chain, kind) in listed:
        if (name, chain) != ('cli.py', '_Parser.error') and name in sources:
            holders[(name, chain)] += terminal_positions(sources[name]).get((chain, kind), ())
    roots = [('cli.py', '<module>'), ('cli.py', 'main')]
    found = {}
    for leaf in sorted(' '.join(path) for path, kind in leaf_table(table).items() if kind == 'machine'):
        if leaves is not None and leaf not in leaves:
            continue
        chosen = route_dests(parser, tuple(leaf.split()))
        for exact_only in (True, False):
            parent, queue = {root: None for root in roots}, collections.deque(roots)
            while queue:
                key = queue.popleft()
                for target, guards, exact in graph.edges(key):
                    if not ((exact or not exact_only) and passes(guards, chosen, dests)):
                        continue
                    if target == ('cli.py', 'main') and key not in roots and (leaf, REENTRY) not in found:
                        found[(leaf, REENTRY)] = ('exact' if exact_only else 'name', trail(parent, key) + (REENTRY,))
                    if target not in parent:
                        parent[target] = key
                        queue.append(target)
            for holder, positions in holders.items():
                if holder in parent and (leaf, holder) not in found and any(
                        passes(graph.files[holder[0]].guards.get(position, ()), chosen, dests) for position in positions):
                    found[(leaf, holder)] = ('exact' if exact_only else 'name', trail(parent, holder))
    return found


def reach_problems(sources=None, listed=None, table=None, exact=None, by_name=None):
    """[str] for what differs between the reaches of the machine leaves and EXACT_REACHES with NAME_REACHES: a reach that is not listed,
    in either kind, and a listed reach that is gone or is of the other kind."""
    exact = EXACT_REACHES if exact is None else exact
    by_name = NAME_REACHES if by_name is None else by_name
    sources = package_sources() if sources is None else sources
    graph = ReachGraph(sources)
    found = machine_reaches(sources, listed, table, graph=graph)
    problems = ['the site %s: %s is in no function that the call graph knows, so no reach to it can be judged' % holder
                for holder in sorted({(name, chain) for name, chain, _ in (OUTPUT_SITES if listed is None else listed)
                                      if name in sources and (name, chain) != ('cli.py', '_Parser.error')
                                      and (name, chain) not in graph.functions})]
    for (leaf, holder), (kind, path) in sorted(found.items()):
        if (kind == 'exact' and (leaf, holder) not in exact) or (kind == 'name' and leaf not in by_name.get(holder, ('', ()))[1]):
            how = 'by direct names' if kind == 'exact' else 'by an attribute name'
            what = ('runs the command line again (cli.py: main) %s, so the route conditions no longer describe what it runs' % how
                    if holder == REENTRY else 'reaches %s: %s %s' % (holder[0], holder[1], how))
            problems.append('the machine leaf %r %s, along %s, and the reach is not listed'
                            % (leaf, what, ' > '.join('%s:%s' % step for step in path[-6:])))
    problems += ['the listed exact reach of %r to %s: %s is gone' % (leaf, holder[0], holder[1]) for leaf, holder in sorted(exact)
                 if found.get((leaf, holder), ('',))[0] != 'exact']
    problems += ['the listed reach by name of %r to %s: %s is gone, or no longer needs a name' % (leaf, holder[0], holder[1])
                 for holder, (_, leaves) in sorted(by_name.items()) for leaf in leaves if found.get((leaf, holder), ('',))[0] != 'name']
    return problems


# The machine leaves, as LEAF_TABLE names them. Each reaches, by an attribute name, every function below that holds a terminal site and shares its
# name with an attribute that a function it reaches uses. None reaches such a function along direct names (EXACT_REACHES is empty).
NAME_REACH_LEAVES = (
    'action', 'adoption attach', 'adoption cancel', 'adoption prepare', 'adoption recover', 'adoption recovery-plan-attach',
    'adoption recovery-plan-cancel', 'adoption recovery-plan-prepare', 'adoption recovery-plan-recover', 'adoption recovery-plan-review',
    'adoption recovery-plan-status', 'adoption review', 'adoption status', 'artifact inspect', 'artifact restore', 'artifact seal',
    'capture', 'doctor', 'generate', 'graph build', 'graph query', 'inspect', 'judge', 'mcp', 'plan review', 'provider execute',
    'provider prepare', 'provider reconcile', 'provider review', 'provider status', 'repository inspect', 'repository native',
    'repository resolve', 'service attach', 'service cancel', 'service prepare', 'service recover', 'service review', 'service status',
    'simulation create', 'simulation prepare', 'simulation reconcile', 'simulation run', 'synthetic generate', 'synthetic inspect',
    'target authenticate', 'target collect', 'target compare', 'target inspect', 'verify', 'workbench adopt', 'workbench adoption-history',
    'workbench adoption-lineage', 'workbench adoption-link', 'workbench adoption-preview', 'workbench backup', 'workbench collect',
    'workbench collection', 'workbench collection-history', 'workbench compare', 'workbench delivery', 'workbench deployment-import',
    'workbench deployment-record', 'workbench device-evidence-import', 'workbench diagnostics', 'workbench dictionary',
    'workbench estate-overview', 'workbench evidence-history', 'workbench evidence-link', 'workbench execute', 'workbench families',
    'workbench field-semantics', 'workbench health', 'workbench history', 'workbench history-recent', 'workbench import-capture',
    'workbench init', 'workbench inspect', 'workbench lab-create', 'workbench lab-init', 'workbench lineage', 'workbench migrate',
    'workbench observer-create', 'workbench observer-run', 'workbench observer-scheduler', 'workbench observer-status',
    'workbench operations', 'workbench overview', 'workbench ownership-import', 'workbench ownership-scan', 'workbench propose',
    'workbench propose-from-intent', 'workbench provider-refresh-import', 'workbench queue', 'workbench queue-amend',
    'workbench queue-review', 'workbench queue-review-history', 'workbench queue-review-template', 'workbench reconcile',
    'workbench reference-compare', 'workbench reference-import', 'workbench references', 'workbench relationships',
    'workbench repository-entry', 'workbench repository-import', 'workbench repository-refresh', 'workbench repository-status',
    'workbench restore', 'workbench restore-propose', 'workbench review', 'workbench schedule-create', 'workbench schedule-run',
    'workbench schedule-status', 'workbench search', 'workbench service-link', 'workbench settings', 'workbench source-acceptance-propose',
    'workbench views', 'workbench workflow-import', 'workbench workflows', 'worker attach', 'worker cancel', 'worker prepare',
    'worker reconcile', 'worker review', 'worker run', 'worker status',
)
NOT_REACHING_DRAW = (
    'action', 'capture', 'doctor', 'judge', 'mcp', 'provider execute', 'provider prepare', 'provider reconcile', 'provider review',
    'provider status', 'repository inspect', 'repository native', 'repository resolve', 'simulation prepare', 'simulation reconcile',
    'simulation run',
)
EXACT_REACHES = {}
NAME_REACHES = {
    ('windows_terminal.py', 'NativeConsole.session'): (
        'an attribute named session that provider_journey.ProviderJourney._save passes on is a function value'
        " named session, and reaches every function named session; this one is the Windows console's context "
        'manager, which only windows_workspace_binding makes, and no machine leaf reaches that along direct '
        'names',
        NAME_REACH_LEAVES),
    ('windows_terminal.py', 'NativeConsole.write'): (
        'every stream.write(data) of a file writer (cli.execute > runner.run) is an attribute call named '
        "write, and an attribute call reaches every function named write; this one is the Windows console's, "
        'which only windows_workspace_binding makes, and no machine leaf reaches that along direct names',
        NAME_REACH_LEAVES),
    ('windows_terminal.py', '_Win32.handles'): (
        'repository._Repository.__init__ calls self._initialize(), an attribute call named _initialize, which reaches every function named '
        "_initialize; NativeConsole._initialize is the Windows console's, and it calls api.handles(). The console API is made only by "
        'NativeConsole.__init__, which only windows_workspace_binding makes, and no machine leaf reaches either along direct names',
        NAME_REACH_LEAVES),
    ('windows_terminal.py', '_Win32.write'): (
        'every stream.write(data) of a file writer (cli.execute > runner.run) is an attribute call named write, and an attribute call '
        "reaches every function named write; this one is the Windows console API's, which only NativeConsole.__init__ makes, and that is made "
        'only by windows_workspace_binding; no machine leaf reaches either along direct names',
        NAME_REACH_LEAVES),
    ('workbench_tui.py', 'Workspace.draw'): (
        'artifact_vault.command passes on an attribute named input, which reaches Workspace.input, whose '
        'self.draw() is an attribute call named draw; Workspace is made only by run_workspace and by '
        'windows_workspace_binding, and no machine leaf reaches either along direct names',
        tuple(leaf for leaf in NAME_REACH_LEAVES if leaf not in NOT_REACHING_DRAW)),
}


KINDS = ('empty', 'repository', 'export', 'emptystore', 'full', 'context')


@functools.lru_cache(maxsize=1)
@named_sweep
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
@named_sweep
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
@named_sweep
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
@named_sweep
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
@named_sweep
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
    assert sweep.coverage and any(route.startswith('wizard') for (_, route, *_) in sweep.coverage), 'the wizard sessions printed nothing'
    driven('wizard')
    return sweep


@functools.lru_cache(maxsize=1)
@named_sweep
def sweep_terminal():
    """workbench terminal through cli.main: the line terminal with its own input and output, the typed lines scripted. What a person
    reads there is the prompt it hands to input and what it prints; the JSON documents it prints are a machine form (a stream of them
    is not read), so a sentence added beside them would be."""
    sweep = Sweep()
    fx = Estate()
    fx.setUp()
    try:
        build_observed(fx)
        typed, prompts = iter(['overview', 'select ' + OBJECT, 'inspect']), []

        def fake_input(prompt=''):
            prompts.append(prompt)
            try:
                return next(typed)
            except StopIteration:
                raise EOFError()
        with patch.object(builtins, 'input', fake_input):
            code, text, err = run_cli(['workbench', 'terminal', '--root', str(fx.store.root)], 100)
        assert prompts and prompts[0] == 'workbench> ', prompts
        for prompt in sorted(set(prompts)):
            sweep.read('terminal session', 'workbench terminal (prompt)', (100, 0), readable([prompt]), rows=[prompt])
        sweep.text('terminal session', 'workbench terminal', (100, 0), text)
        sweep.text('terminal session', 'workbench terminal (stderr)', (100, 0), err)
        driven('workbench terminal')
    finally:
        fx.doCleanups()
    return sweep


@functools.lru_cache(maxsize=1)
@named_sweep
def sweep_companion():
    """workbench companion through cli.main, live for a second (the listener binds this machine's loopback and nobody connects) and as
    a file: the address notice and the sentence before the JSON end line are printed with print(), outside _write_text."""
    sweep = Sweep()
    fx = Estate()
    fx.setUp()
    try:
        build_observed(fx)
        root = str(fx.store.root)
        code, text, err = run_cli(['workbench', 'companion', '--root', root, '--object', OBJECT, '--serve', '--idle-seconds', '1'], 100)
        assert 'Listening on' in text and 'its address no longer answers' in text, text
        sweep.text('companion, live', 'workbench companion --serve', (100, 0), text)
        sweep.text('companion, live', 'workbench companion --serve (stderr)', (100, 0), err)
        with tempfile.TemporaryDirectory() as temp:
            code, text, err = run_cli(['workbench', 'companion', '--root', root, '--object', OBJECT, '--out', str(Path(temp) / 'page.html')], 100)
        sweep.text('companion, file', 'workbench companion --out', (100, 0), text)
        driven('workbench companion')
    finally:
        fx.doCleanups()
    return sweep


class StandInJourney:
    """Presentation only: the canned results, in the shapes the real provider journey returns, for provider wizard's own prompts."""

    def __init__(self, executor_root, session, authority_config):
        self._authorization = self._reviewed_sha = None

    def approve(self, receipt):
        return {'status': 'approved', 'receipt': receipt}

    def suspend(self, reason='save'):
        return {'status': 'suspended', 'reason': reason}

    def __getattr__(self, name):
        if name in ('prepare', 'review', 'execute', 'reconcile', 'status'):
            return lambda: {'status': name}
        raise AttributeError(name)


@functools.lru_cache(maxsize=1)
@named_sweep
def sweep_provider_wizard():
    """provider wizard through cli.main with a stand-in journey (the real one needs an admitted executor) and the lines typed: the
    prompts it hands to input and the two lines it prints with print(), before its JSON results."""
    sweep = Sweep()
    typed, prompts = iter(['prepare', 'approve', 'receipt.json', 'bogus', 'status', 'save']), []

    def fake_input(prompt=''):
        prompts.append(prompt)
        try:
            return next(typed)
        except StopIteration:
            raise EOFError()
    with patch('intune_iac.provider_journey.ProviderJourney', StandInJourney), patch.object(builtins, 'input', fake_input):
        code, text, err = run_cli(['provider', 'wizard', '--executor-root', '/executor', '--session', '/session', '--authority-config',
                                   '/authority'], 100)
    assert set(prompts) == {'provider> ', 'Receipt file: '} and text.startswith('Provider journey:'), (prompts, text)
    for prompt in sorted(set(prompts)):
        sweep.read('provider wizard session', 'provider wizard (prompt)', (100, 0), readable([prompt]), rows=[prompt])
    sweep.text('provider wizard session', 'provider wizard', (100, 0), text)
    sweep.text('provider wizard session', 'provider wizard (stderr)', (100, 0), err)
    driven('provider wizard')
    return sweep


# -- simulate, --check-signin, and the protected service and adoption views ------------------------------------------------------------

@functools.lru_cache(maxsize=1)
@named_sweep
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
@named_sweep
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
@named_sweep
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


@named_sweep
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


def run_every_sweep():
    """Run, once (they are cached), the sweep each text and session leaf names; the recorder then says what each one drove."""
    for sweeps in LEAF_DRIVERS.values():
        for name in ((sweeps,) if isinstance(sweeps, str) else sweeps):
            globals()[name]('empty store') if name == 'sweep_state' else globals()[name]()


class LeafClassificationTests(unittest.TestCase):
    """Sol B V2 finding 1: the classification of the parser's leaves fails closed. A leaf is text, a session or a machine form because the
    table says so, a leaf the table does not name fails, and a product that writes to a terminal anywhere unlisted fails."""

    @staticmethod
    def parser():
        from intune_iac import cli
        return cli.parser()

    @staticmethod
    def add_leaf(parser, *path):
        for name in path[:-1]:
            parser = next(item for item in parser._actions if isinstance(item, argparse._SubParsersAction)).choices[name]
        next(item for item in parser._actions if isinstance(item, argparse._SubParsersAction)).add_parser(path[-1])

    def test_the_table_names_every_parser_leaf_once_and_only_those(self):
        parser = self.parser()
        self.assertEqual(leaf_table_problems(parser), [])
        kinds = collections.Counter(leaf_table().values())
        self.assertEqual((kinds['text'], kinds['session'], kinds['machine']), (7, 5, 127))
        self.assertEqual(sum(kinds.values()), len(leaf_paths(parser)))                         # 139

    def test_a_leaf_the_table_does_not_name_fails_and_so_does_an_entry_with_no_leaf(self):
        for path in (('kube',), ('signin', 'whoami'), ('workbench', 'kube')):
            parser = self.parser()
            self.add_leaf(parser, *path)
            self.assertEqual(leaf_table_problems(parser), ['the parser has the leaf %r and the table does not name it' % ' '.join(path)])
        table = {kind: tuple(names) for kind, names in LEAF_TABLE.items()}
        parser = self.parser()
        self.assertEqual(leaf_table_problems(parser, dict(table, machine=table['machine'] + ('worker teleport',))),
                         ["the table names 'worker teleport' and the parser has no such leaf"])
        self.assertEqual(leaf_table_problems(parser, dict(table, machine=tuple(name for name in table['machine'] if name != 'doctor'))),
                         ["the parser has the leaf 'doctor' and the table does not name it"])
        self.assertEqual(leaf_table_problems(parser, dict(table, text=table['text'] + ('doctor',))),
                         ["the leaf 'doctor' is named twice (text and machine)"])
        drivers = dict(LEAF_DRIVERS)
        del drivers['start']
        self.assertEqual(leaf_table_problems(parser, drivers=drivers), ["the text leaf 'start' has no driver"])
        self.assertEqual(leaf_table_problems(parser, drivers=dict(LEAF_DRIVERS, doctor='sweep_signin')),
                         ["'doctor' has a driver and is not a text or session leaf"])
        self.assertEqual(leaf_table_problems(parser, drivers=dict(LEAF_DRIVERS, start='sweep_nothing')),
                         ["the driver 'sweep_nothing' of 'start' is not a function of this module"])

    def test_every_text_and_session_leaf_is_driven_by_the_sweep_the_table_names(self):
        parser = self.parser()
        run_every_sweep()
        for name, sweeps in LEAF_DRIVERS.items():
            for sweep in ((sweeps,) if isinstance(sweeps, str) else sweeps):
                self.assertIn(sweep, DRIVEN[tuple(name.split())], '%s was not driven by %s' % (name, sweep))
        kinds = leaf_table()
        by_code = text_leaves_by_code(parser)
        written = {leaf for leaf, count in WRITTEN.items() if count}
        self.assertTrue({('start',), ('catalog',), ('engineering',), ('signin', 'status'), ('signin', 'collect'), ('simulate',),
                         ('workbench', 'workflow'), ('workbench', 'workspace')} <= by_code, sorted(by_code))       # not a vacuous read
        self.assertEqual(sorted(leaf for leaf in by_code if kinds[leaf] == 'machine'), [],
                         'cli.main prints text through cli._write_text for a leaf the table calls a machine form')
        self.assertEqual(sorted(leaf for leaf, kind in kinds.items() if kind == 'text' and leaf not in by_code), [],
                         'the table calls a leaf text and cli.main prints no text through cli._write_text for it')
        self.assertEqual(sorted(by_code - written), [], 'a leaf prints text through cli._write_text and no sweep drove it through cli.main')
        self.assertEqual(sorted(written - by_code), [], 'cli.main printed text for a leaf the analysis of its source did not admit')

    def test_the_product_writes_to_a_person_only_at_the_listed_sites(self):
        self.assertEqual(output_site_problems(), [])
        found = output_sites()
        self.assertEqual(dict(found), {site: value[0] for site, value in list(OUTPUT_SITES.items()) + list(NOT_A_TERMINAL.items())})
        self.assertEqual((len(OUTPUT_SITES), len(NOT_A_TERMINAL), len(found), sum(found.values())), (44, 213, 257, 417))
        self.assertIn(('cli.py', '_write_text', 'print'), found)                                   # the scan reads the product
        self.assertTrue(all(isinstance(value[1], str) and value[1] for value in NOT_A_TERMINAL.values()))      # each has its reason

    def test_a_new_leaf_that_prints_with_print_fails_closed(self):
        """Sol V2's input: a kube leaf that prints `Run: kubectl apply PLAN_FILE` with print() was a machine form by subtraction."""
        parser = self.parser()
        self.add_leaf(parser, 'kube')
        self.assertEqual(leaf_table_problems(parser), ["the parser has the leaf 'kube' and the table does not name it"])
        sources = package_sources()
        sources['kube.py'] = "def kube(args):\n    print(%r)\n    return 0\n" % ReferenceScanTests.LINE
        self.assertEqual(output_site_problems(sources), ['kube.py: kube has 1 unlisted print site(s)'])
        sources = package_sources()
        branch = "        if args.command=='mcp':"                                                   # and inside cli.main itself
        self.assertIn(branch, sources['cli.py'])
        sources['cli.py'] = sources['cli.py'].replace(
            branch, "        if args.command=='kube':\n            print(%r)\n            return 0\n" % ReferenceScanTests.LINE + branch, 1)
        self.assertEqual(output_site_problems(sources), ['cli.py: main has 4 print site(s), 3 listed'])

    def test_a_listed_site_must_be_exact(self):
        sources = package_sources()
        sources['provider_journey.py'] = sources['provider_journey.py'].replace(
            "    print('Provider journey: network-denied", "    print('A third line')\n    print('Provider journey: network-denied", 1)
        self.assertEqual(output_site_problems(sources), ['provider_journey.py: run_provider_wizard has 3 print site(s), 2 listed'])
        sources = package_sources()
        sources['wizard.py'] = ''
        gone = sorted('wizard.py: %s %s is listed and the sources have no such site' % (site[1], site[2])
                      for site in list(OUTPUT_SITES) + list(NOT_A_TERMINAL) if site[0] == 'wizard.py')
        self.assertEqual(len(gone), 7)
        self.assertEqual(sorted(output_site_problems(sources)), gone)
        # a site that reaches no terminal is listed too, and a site is not listed as both
        others = {site: value for site, value in NOT_A_TERMINAL.items() if site[0] != 'mcp.py'}
        gone = ['mcp.py: %s has %d unlisted %s site(s)' % (site[1], count, site[2])
                for site, count in sorted(output_sites().items()) if site[0] == 'mcp.py']
        self.assertEqual(len(gone), 4)
        self.assertEqual(output_site_problems(others=others), gone)
        both = {**NOT_A_TERMINAL, ('cli.py', '_write_text', 'print'): (1, 'a socket', OUTPUT_SITES[('cli.py', '_write_text', 'print')][2])}
        self.assertEqual(output_site_problems(others=both),
                         ['cli.py: _write_text print is listed as a terminal site and as a site that reaches no terminal'])
        # a site that serves a leaf the table does not call text or session, and a session leaf no site serves
        listed = dict(OUTPUT_SITES)
        listed[('cli.py', '_write_text', 'print')] = (1, 'doctor', OUTPUT_SITES[('cli.py', '_write_text', 'print')][2])
        self.assertEqual(output_site_problems(listed=listed),
                         ["the site cli.py: _write_text serves 'doctor', which the table does not classify as text or session"])
        listed = {site: value for site, value in OUTPUT_SITES.items() if value[1] != 'provider wizard'}
        self.assertIn("the session leaf 'provider wizard' is served by no listed site", output_site_problems(listed=listed))

    def test_a_new_leaf_that_prints_text_through_write_text_fails_until_it_is_driven(self):
        """The count of _write_text calls did not move when a leaf was added to a branch that already printed text; the leaves read
        from the source do. A new branch of cli.main that prints text for a leaf of its own is found the same way."""
        from intune_iac import cli
        run_every_sweep()
        parser = self.parser()
        self.add_leaf(parser, 'signin', 'whoami')                 # under the signin branch, which prints text for every signin leaf
        self.add_leaf(parser, 'kube')                             # a leaf of its own, for a branch that main gains
        source = inspect.getsource(cli.main)
        branch = "        if args.command=='mcp':"
        self.assertIn(branch, source)
        source = source.replace(branch, "        if args.command=='kube':\n            _write_text(['Run: kubectl apply -f MANIFEST_FILE'])\n"
                                        "            return 0\n" + branch, 1)
        by_code = text_leaves_by_code(parser, source)
        written = {leaf for leaf, count in WRITTEN.items() if count}
        self.assertEqual(sorted(by_code - written), [('kube',), ('signin', 'whoami')])
        self.assertEqual(len(leaf_table_problems(parser)), 2)                                      # and the table names neither
        self.assertNotIn(('kube',), text_leaves_by_code(parser))                                   # the real main names no such branch

    def test_the_recorder_reads_the_leaf_cli_main_ran_for_and_the_sweep_that_ran_it(self):
        before = WRITTEN[('engineering',)]
        CURRENT_SWEEP.append('a probe')
        try:
            run_cli(['engineering'], 80)
            self.assertEqual(WRITTEN[('engineering',)], before + 1)
            run_cli(['engineering', '--json'], 80)                                         # the machine form prints no text
            run_cli(['engineering', '--help'], 80)
            self.assertEqual(WRITTEN[('engineering',)], before + 1)
            run_cli(['workbench', 'workspace', '--root', '/stores/one'], 80, tty=True, execute={'status': 'interrupted'})
            self.assertGreater(WRITTEN[('workbench', 'workspace')], 0)
        finally:
            CURRENT_SWEEP.pop()
        self.assertEqual({sweep for sweep in DRIVEN[('engineering',)] if sweep == 'a probe'}, {'a probe'})
        self.assertIn('a probe', DRIVEN[('workbench', 'workspace')])

    def test_a_stream_of_json_documents_is_a_machine_form_and_a_sentence_beside_it_is_not(self):
        self.assertTrue(machine_form('{"a": 1}'))
        self.assertTrue(machine_form('{"a": 1}\n{"b": [2, 3]}\n'))
        self.assertTrue(machine_form('{\n  "a": 1\n}\n{\n  "b": 2\n}'))
        self.assertFalse(machine_form('{"a": 1}\nRun: kubectl apply PLAN_FILE'))
        self.assertFalse(machine_form('Run: kubectl apply PLAN_FILE\n{"a": 1}'))
        self.assertFalse(machine_form('   '))
        sweep = Sweep()
        sweep.text('state', 'workbench terminal', (80, 0), '{"next": "Run: kubectl apply PLAN_FILE"}\n{"status": "ok"}')
        self.assertEqual(sweep.net, collections.OrderedDict())
        sweep = Sweep()
        sweep.text('state', 'workbench terminal', (80, 0), '{"status": "ok"}\nRun: kubectl apply PLAN_FILE')
        self.assertEqual(sorted(sweep.net), [('Run', 'PLAN_FILE')])


class ReferenceScanTests(unittest.TestCase):
    """Sol B V3: the scan of the product's output sites flags by reference, not by call shape. Each case puts code into the body of an
    existing machine leaf's function (cli.doctor, the function of `doctor`, whose leaf the table calls a machine form) or into a module
    of its own, and the sites that appear beyond the listing must be exactly the ones the case names. Nothing here is run."""

    LINE = 'Run: kubectl apply PLAN_FILE'

    @staticmethod
    def mutated(snippet, function='doctor', module='cli.py'):
        """The sources of the product with the statements of a snippet at the start of the body of a function of one module, as
        ast.unparse writes that module."""
        sources = package_sources()
        tree = ast.parse(sources[module])
        target = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == function)
        target.body[0:0] = ast.parse(textwrap.dedent(snippet)).body
        sources[module] = ast.unparse(tree)
        return sources

    @staticmethod
    def delta(sources):
        """{(file, function, kind): references found minus references listed} for every site that differs from the listing."""
        listed = collections.Counter({site: value[0] for site, value in list(OUTPUT_SITES.items()) + list(NOT_A_TERMINAL.items())})
        found = output_sites(sources)
        return {site: found[site] - listed[site] for site in set(found) | set(listed) if found[site] != listed[site]}

    def inside(self, snippet, **expected):
        """The sites a snippet adds to cli.doctor: kind=count for a site of doctor itself."""
        added = {('cli.py', 'doctor', kind.replace('__dot__', '.').replace('_sp_', ' ')): count for kind, count in expected.items()}
        self.assertEqual(self.delta(self.mutated(snippet % {'line': self.LINE})), added)

    def test_the_rewrite_of_the_module_changes_no_site(self):
        self.assertEqual(self.delta(self.mutated('pass')), {})

    def test_a_print_is_exempt_only_when_the_whole_call_can_emit_one_json_document(self):
        """Sol V3 finding 1: print(json.dumps({...}), "Run: kubectl apply PLAN_FILE") was exempt because only args[0] was read."""
        for label, snippet, expected in (
                ('Sol: a sentence beside the document', 'print(json.dumps({"status": "ok"}), %(line)r)', {'print': 1}),
                ('a sep that is a sentence', 'print(json.dumps({}), json.dumps({}), sep=%(line)r)', {'print': 1}),
                ('two documents', 'print(json.dumps({}), json.dumps({}))', {'print': 1}),
                ('an end that is a sentence', 'print(json.dumps({}), end=%(line)r)', {'print': 1}),
                ('a stream', 'print(json.dumps({}), file=sys.stderr)', {'print': 1, 'sys__dot__stderr': 1}),
                ('a starred argument', 'print(*[json.dumps({})])', {'print': 1}),
                ('keyword options', 'print(json.dumps({}), **{"sep": %(line)r})', {'print': 1}),
                ('the sentence is the only argument', 'print(%(line)r)', {'print': 1}),
                ('a document of the product, not of json', 'print(canonical({}).decode())', {'print': 1})):
            with self.subTest(label):
                self.inside(snippet, **expected)
        for label, snippet in (('one document', 'print(json.dumps({"status": "ok"}))'),
                               ('one document, then a newline', 'print(json.dumps({}), end="\\n")'),
                               ('one document, flushed', 'print(json.dumps({}), flush=True)')):
            with self.subTest(label):
                self.inside(snippet)

    def test_a_write_is_exempt_only_inside_with_open_on_the_name_it_binds(self):
        """Sol V3 finding 2: a parameter bound to sys.stdout and an unreachable out = open(...) made the write look like a file's."""
        for label, snippet, expected in (
                ('Sol: a parameter and an unreachable open', 'def helper(out=sys.stdout):\n    if False:\n        out = open("result.json", "w")\n'
                                                              '    out.write(%(line)r)', {'doctor.helper': {'sys.stdout': 1, 'write': 1}}),
                ('a parameter', 'def helper(out):\n    out.write(%(line)r)', {'doctor.helper': {'write': 1}}),
                ('a file opened outside a with', 'handle = open("result.json", "w")\nhandle.write(%(line)r)', {'doctor': {'write': 1}}),
                ('the name bound again in the block', 'with open("result.json", "w") as out:\n    out = sys.stdout\n    out.write(%(line)r)',
                 {'doctor': {'sys.stdout': 2, 'write': 1}}),
                ('a path held in a name', 'path = "result.json"\nwith open(path, "w") as out:\n    out.write(%(line)r)', {'doctor': {'write': 1}}),
                ('a path given by an attribute', 'with open(self.target, "w") as out:\n    out.write(%(line)r)', {'doctor': {'write': 1}}),
                ('a path built from a device name', 'with open("/dev/" + "tty", "w") as out:\n    out.write(%(line)r)', {'doctor': {'write': 1}}),
                ('a function between the with and the write', 'with open("result.json", "w") as out:\n    def later():\n'
                                                              '        out.write(%(line)r)', {'doctor.later': {'write': 1}}),
                ('a write on another name', 'with open("result.json", "w") as out:\n    other = out\n    other.write(%(line)r)',
                 {'doctor': {'write': 1}}),
                ('an attribute of the name', 'with open("result.json", "w") as out:\n    out.buffer.write(%(line)r)', {'doctor': {'write': 1}}),
                ('a descriptor', 'with open(1, "w") as out:\n    out.write(%(line)r)',
                 {'doctor': {'write': 1, 'standard descriptor': 1}}),
                ('a terminal device', 'with open("/dev/tty", "w") as out:\n    out.write(%(line)r)', {'doctor': {'write': 1, 'device path': 1}}),
                ('os.fdopen of a descriptor', 'with os.fdopen(1, "w") as out:\n    out.write(%(line)r)',
                 {'doctor': {'os.fdopen': 1, 'write': 1, 'standard descriptor': 1}}),
                ('a path opened with open()', 'with Path("result.json").open("w") as out:\n    out.write(%(line)r)', {'doctor': {'write': 1}}),
                ('writelines', 'with open("result.json", "w") as out:\n    pass\nout.writelines([%(line)r])', {'doctor': {'write': 1}})):
            with self.subTest(label):
                added = {('cli.py', function, kind): count for function, kinds in expected.items() for kind, count in kinds.items()}
                self.assertEqual(self.delta(self.mutated(snippet % {'line': self.LINE})), added)
        for label, snippet in (('a file written in a with', 'with open("result.json", "w") as out:\n    out.write("{}")'),
                               ('two files', 'with open("a.json", "w") as one, open("b.json", "w") as two:\n    one.write("{}")\n'
                                             '    two.writelines(["{}"])')):
            with self.subTest(label):
                self.inside(snippet)

    def test_the_output_names_are_sites_by_reference_not_by_call(self):
        """Sol V3 finding 3, and the roads to the same call that a reader of the call shapes would miss."""
        for label, snippet, expected in (
                ('Sol: builtins.print', 'import builtins\nbuiltins.print(%(line)r)', {'builtins': 1, 'import builtins': 1}),
                ('Sol: print imported under an alias', 'from builtins import print as emit\nemit(%(line)r)',
                 {'builtins': 1, 'import builtins': 1}),
                ('builtins under an alias', 'import builtins as b\nb.print(%(line)r)', {'builtins': 1, 'import builtins': 1}),
                ('getattr on builtins', 'import builtins\ngetattr(builtins, "print")(%(line)r)', {'builtins': 1, 'import builtins': 1}),
                ('__import__', '__import__("builtins").print(%(line)r)', {'__import__': 1}),
                ('print held under another name', 'emit = print\nemit(%(line)r)', {'print': 2}),
                ('print handed to a function', 'list(map(print, [%(line)r]))', {'print': 1}),
                ('sys.__stdout__', 'sys.__stdout__.write(%(line)r)', {'sys.__stdout__': 1, 'write': 1}),
                ('sys.stdout held under another name', 'out = sys.stdout\nout.write(%(line)r)', {'sys.stdout': 2, 'write': 1}),
                ('sys under an alias', 'import sys as s\ns.stdout.write(%(line)r)', {'sys.stdout': 1, 'write': 1}),
                ('stdout imported from sys', 'from sys import stdout\nstdout.write(%(line)r)',
                 {'import sys.stdout': 1, 'sys.stdout': 1, 'write': 1}),
                ('sys handed to vars', 'vars(sys)["stdout"].write(%(line)r)', {'sys_sp_as a value': 1, 'write': 1}),
                ('getattr on sys', 'getattr(sys, "std" + "out").write(%(line)r)', {'sys_sp_as a value': 1, 'write': 1}),
                ('the dictionary of sys', 'sys.__dict__["stdout"].write(%(line)r)', {'dynamic_sp_access': 1, 'write': 1}),
                ('sys.modules', 'sys.modules["builtins"].print(%(line)r)', {'sys__dot__modules': 1}),
                ('importlib', 'importlib.import_module("builtins").print(%(line)r)', {'importlib': 1}),
                ('os.system', 'os.system("echo " + %(line)r)', {'os__dot__system': 1}),
                ('os.system by an alias', 'import os as o\no.system("echo " + %(line)r)', {'os__dot__system': 1}),
                ('system imported from os', 'from os import system\nsystem("echo " + %(line)r)', {'import os.system': 1, 'os__dot__system': 1}),
                ('getattr on os', 'getattr(os, "sys" + "tem")("echo " + %(line)r)', {'os_sp_as a value': 1}),
                ('os.popen', 'os.popen("echo " + %(line)r)', {'os__dot__popen': 1}),
                ('os.dup2 onto the terminal', 'os.dup2(1, 2)', {'os__dot__dup2': 1, 'standard descriptor': 1}),
                ('os.write', 'os.write(1, %(line)r.encode())', {'os__dot__write': 1, 'standard descriptor': 1}),
                ('a descriptor given to open', 'open(2, "w").write(%(line)r)', {'standard descriptor': 1, 'write': 1}),
                ('subprocess', 'import subprocess\nsubprocess.run(["echo", %(line)r])',
                 {'import subprocess': 1, 'subprocess': 1, 'child on the terminal': 1}),
                ('a child that inherits standard error', 'import subprocess\nsubprocess.run(["echo"], stdout=subprocess.PIPE)',
                 {'import subprocess': 1, 'subprocess': 2, 'child on the terminal': 1}),
                ('a child whose output is taken', 'import subprocess\nsubprocess.run(["echo"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)',
                 {'import subprocess': 1, 'subprocess': 3}),
                ('a pseudo-terminal', 'import pty\npty.spawn(["echo", %(line)r])', {'import pty': 1, 'pty': 1}),
                ('logging', 'import logging\nlogging.warning(%(line)r)', {'import logging': 1, 'logging': 1}),
                ('exec', 'exec("print(1)")', {'exec': 1}),
                ('eval', 'eval("print(1)")', {'eval': 1}),
                ('compile', 'compile("print(1)", "x", "exec")', {'compile': 1}),
                ('globals', 'globals()["__builtins__"]', {'globals': 1}),
                ('locals', 'locals()', {'locals': 1}),
                ('__builtins__', '__builtins__.print(%(line)r)', {'__builtins__': 1}),
                ('input with a prompt', 'input(%(line)r)', {'input': 1}),
                ('the text sink of the command line', '_write_text([%(line)r])', {'_write_text': 1}),
                ('an exit with a sentence', 'sys.exit(%(line)r)', {'exit-text': 1}),
                ('an exit with a variable', 'message = %(line)r\nsys.exit(message)', {'exit-text': 1}),
                ('an exit with the status of a call', 'sys.exit(len(sys.argv))', {'exit-text': 1}),
                ('a path written to', 'Path("result.json").write_text(%(line)r)', {'write': 1}),
                ('bytes written to a path', 'Path("result.json").write_bytes(b"x")', {'write': 1}),
                ('a coroutine that starts a process', 'import asyncio\nasyncio.create_subprocess_shell("echo " + %(line)r)',
                 {'import asyncio': 1, 'asyncio': 1}),
                ('a child that inherits the terminal', 'import multiprocessing\nmultiprocessing.Process(target=len).start()',
                 {'import multiprocessing': 1, 'multiprocessing': 1}),
                ('a raised exit with a sentence', 'raise SystemExit(%(line)r)', {'exit-text': 1}),
                ('the parser', 'self.error(%(line)r)', {'parser-output': 1}),
                ('a library loaded by hand', 'import ctypes\nctypes.CDLL(None).write(1, b"x", 1)', {'ctypes__dot__CDLL': 1, 'write': 1})):
            with self.subTest(label):
                self.inside(snippet, **expected)
        for label, snippet in (('a constant of os', 'getattr(os, "O_NOFOLLOW", 0)'), ('a test of os', 'hasattr(os, "fsync")'),
                               ('sys.exit with a status', 'sys.exit(2)'), ('an exception named', 'isinstance(None, (KeyboardInterrupt, SystemExit))')):
            with self.subTest(label):
                self.inside(snippet)

    def test_a_name_is_judged_by_every_binding_it_has_in_the_file(self):
        """Sol V4 finding 1: `import os as channel` in doctor and `import json as channel` in a function of the same file made
        channel.system(...) json.system, because the last binding of the name won. A load is judged against every binding its name has
        anywhere in the file, imports and assignments alike, and is a site if any one of them makes it one."""
        for label, snippet, expected in (
                ('Sol: the nested import comes last', 'import os as channel\nchannel.system("echo " + %(line)r)\n\ndef harmless():\n'
                                                      '    import json as channel\n', {'os.system': 1}),
                ('the nested import comes first', 'def harmless():\n    import json as channel\n\nimport os as channel\n'
                                                   'channel.system("echo " + %(line)r)', {'os.system': 1}),
                ('both imports in the function', 'import json as channel\nimport os as channel\nchannel.system("echo " + %(line)r)',
                 {'os.system': 1}),
                ('a from-import under the same name', 'from os import system as channel\nchannel("echo " + %(line)r)\n\ndef harmless():\n'
                                                       '    from json import dumps as channel\n',
                 {'import os.system': 1, 'os.system': 1}),
                ('an assignment under the same name', 'channel = os\nchannel.system("echo " + %(line)r)\n\ndef harmless():\n'
                                                       '    channel = json\n', {'os as a value': 1, 'os.system': 1}),
                ('an assignment from an assignment', 'first = os\nsecond = first\nsecond.system("echo " + %(line)r)',
                 {'os as a value': 2, 'os.system': 1}),
                ('a choice between a stream and None', 'out = sys.stdout if %(line)r else None\nout.write(%(line)r)',
                 {'sys.stdout': 2, 'write': 1}),
                ('print bound to something else elsewhere', 'def harmless():\n    from json import dumps as print\n\nprint(%(line)r)',
                 {'print': 1}),
                ('print bound elsewhere, and a document printed', 'def harmless():\n    from json import dumps as print\n\n'
                                                                  'print(json.dumps({}))', {'print': 1})):
            with self.subTest(label):
                added = {('cli.py', 'doctor', kind): count for kind, count in expected.items()}
                if 'print' in expected and 'dumps as print' in snippet:
                    added[('cli.py', 'main', 'print')] = 1             # main's own JSON print is the builtin's no longer: print is rebound
                self.assertEqual(self.delta(self.mutated(snippet % {'line': self.LINE})), added)
        for label, snippet in (('two modules under one name, none of them an output route',
                                'import json as channel\nchannel.dumps({})\n\ndef harmless():\n    import re as channel\n'),
                               ('an assignment to a module that is no route', 'channel = json\nchannel.dumps({})')):
            with self.subTest(label):
                self.inside(snippet)

    def test_the_native_routes_are_a_fail_closed_module_set(self):
        """Sol V4 limit 4: fcntl, termios, signal, pickle, marshal, shelve, code, pdb, readline, curses and tty can reach a terminal or run
        code by a road of their own (TIOCSTI, raw mode, a handler, a pickle that runs on load, an interactive console). Each is a module of
        SCAN_MODULES, at the import and at every use; the product uses fcntl, termios and signal, and the rest not at all. The snippets
        are parsed, never run: nothing here unpickles, loads or starts anything."""
        for module, use in (('fcntl', 'fcntl.ioctl(1, 0x5412, b"x")'), ('termios', 'termios.tcsetattr(1, 0, [])'),
                            ('signal', 'signal.raise_signal(2)'), ('pickle', 'pickle.loads(b"x")'), ('marshal', 'marshal.loads(b"x")'),
                            ('shelve', 'shelve.open("x")'), ('pdb', 'pdb.set_trace()'),
                            ('readline', 'readline.parse_and_bind("tab: complete")'), ('curses', 'curses.initscr()'),
                            ('tty', 'tty.setraw(0)')):
            with self.subTest(module):
                self.inside('import %s\n%s' % (module, use), **{'import ' + module: 1, module: 1})
        for label, snippet, expected in (
                ('code, under an alias (code is a name cli.main uses for a status)', 'import code as via_code\nvia_code.interact()',
                 {'import code': 1, 'code': 1}),
                ('fcntl imported from', 'from fcntl import ioctl as poke\npoke(1, 0x5412, b"x")', {'import fcntl': 1, 'fcntl': 1}),
                ('signal under an alias', 'import signal as via_signal\nvia_signal.signal(via_signal.SIGINT, via_signal.SIG_IGN)',
                 {'import signal': 1, 'signal': 3}),
                ('pickle by a nested import', 'def later():\n    import pickle\n    return pickle.loads(b"x")', None)):
            with self.subTest(label):
                if expected is None:
                    self.assertEqual(self.delta(self.mutated(snippet)),
                                     {('cli.py', 'doctor.later', 'import pickle'): 1, ('cli.py', 'doctor.later', 'pickle'): 1})
                else:
                    self.inside(snippet, **expected)
        kinds = {site[2] for site in output_sites()}
        used = {kind.replace('import ', '') for kind in kinds} & {'fcntl', 'termios', 'signal', 'pickle', 'marshal', 'shelve', 'code', 'pdb',
                                                                    'readline', 'curses', 'tty'}
        self.assertEqual(used, {'fcntl', 'termios', 'signal'})

    def test_a_console_win32_name_is_a_site_as_an_attribute_a_name_a_string_or_an_import(self):
        """The calls that write to the console, or choose where its output goes, are a fail-closed set (SCAN_CONSOLE). The review's input: a
        write through the handle of windows_directory's API, which no reach can see because that loader is not a terminal. The product names
        them only in windows_terminal's API (the signature table, handles and write), each listed. The snippets are parsed, never run."""
        for label, snippet, expected in (
                ('the review: a write through windows_directory\'s handle',
                 'from .windows_directory import _Win32 as D\nd = D()\nd.k.WriteConsoleW(d.k.GetStdHandle(-11), %(line)r, 28, None, None)',
                 {'console': 2}),
                ('WriteConsoleA', 'k.WriteConsoleA(h, b"x", 1, None, None)', {'console': 1}),
                ('WriteConsole itself', 'k.WriteConsole(h, "x", 1, None, None)', {'console': 1}),
                ('WriteConsoleOutputW', 'k.WriteConsoleOutputW(h, buffer, size, origin, region)', {'console': 1}),
                ('WriteConsoleOutputCharacterW', 'k.WriteConsoleOutputCharacterW(h, "x", 1, origin, count)', {'console': 1}),
                ('WriteConsoleOutputAttribute', 'k.WriteConsoleOutputAttribute(h, attributes, 1, origin, count)', {'console': 1}),
                ('WriteConsoleInputW', 'k.WriteConsoleInputW(h, records, 1, count)', {'console': 1}),
                ('GetStdHandle', 'k.GetStdHandle(-11)', {'console': 1}),
                ('SetStdHandle', 'k.SetStdHandle(-11, h)', {'console': 1}),
                ('AllocConsole', 'k.AllocConsole()', {'console': 1}),
                ('AttachConsole', 'k.AttachConsole(-1)', {'console': 1}),
                ('CreateConsoleScreenBuffer', 'k.CreateConsoleScreenBuffer(0, 0, None, 1, None)', {'console': 1}),
                ('SetConsoleActiveScreenBuffer', 'k.SetConsoleActiveScreenBuffer(h)', {'console': 1}),
                ('a chain from ctypes', 'import ctypes\nctypes.windll.kernel32.WriteConsoleW(h, "x", 1, None, None)',
                 {'console': 1, 'ctypes__dot__windll': 1}),
                ('a name', 'WriteConsoleW(h, "x", 1, None, None)', {'console': 1}),
                ('a name imported', 'from somewhere import WriteConsoleW\nWriteConsoleW(h, "x", 1, None, None)', {'import console': 1, 'console': 1}),
                ('the name as a string', 'getattr(k, "WriteConsoleW")(h, "x", 1, None, None)', {'console': 1}),
                ('a table keyed by the names', 'table = {"GetStdHandle": 1, "WriteConsoleW": 2}', {'console': 2}),
                ('an attribute stored', 'k.WriteConsoleW = None', {'console': 1}),
                ('a prototype set on it', 'k.WriteConsoleW.argtypes = []', {'console': 1})):
            with self.subTest(label):
                self.inside(snippet, **expected)
        for label, snippet in (('the console mode calls', 'k.GetConsoleMode(h, m)\nk.SetConsoleMode(h, 1)'),
                               ('reading input', 'k.ReadConsoleInputW(h, r, 1, c)\nk.WaitForSingleObject(h, 5)'),
                               ('the size of the buffer', 'k.GetConsoleScreenBufferInfo(h, info)'),
                               ('a sentence that names one', 'note = "call WriteConsoleW later"'),
                               ('a longer name that only starts like one', 'k.GetStdHandleCount(1)')):
            with self.subTest(label):
                self.inside(snippet)

    def test_the_windows_console_modules_are_in_the_fail_closed_module_set(self):
        """msvcrt.putwch and putwch_nowait write a character to the console, and _winapi.WriteFile and GetStdHandle reach any handle, the
        console's included. Both are modules of SCAN_MODULES, at the import and at every use; the product uses neither. The snippets are
        parsed, never run."""
        for label, snippet, expected in (
                ('the review: msvcrt.putwch', 'import msvcrt\nmsvcrt.putwch("R")', {'import msvcrt': 1, 'msvcrt': 1}),
                ('msvcrt.putwch_nowait', 'import msvcrt\nmsvcrt.putwch_nowait("R")', {'import msvcrt': 1, 'msvcrt': 1}),
                ('msvcrt.putch', 'import msvcrt\nmsvcrt.putch(b"R")', {'import msvcrt': 1, 'msvcrt': 1}),
                ('msvcrt imported from', 'from msvcrt import putwch\nputwch("R")', {'import msvcrt': 1, 'msvcrt': 1}),
                ('msvcrt under an alias', 'import msvcrt as console\nconsole.putwch("R")', {'import msvcrt': 1, 'msvcrt': 1}),
                ('_winapi.WriteFile', 'import _winapi\n_winapi.WriteFile(1, b"R")', {'import _winapi': 1, '_winapi': 1}),
                ('_winapi.GetStdHandle (also a console name, whatever the receiver)', 'import _winapi\n_winapi.GetStdHandle(-11)',
                 {'import _winapi': 1, '_winapi': 1, 'console': 1}),
                ('_winapi imported from', 'from _winapi import WriteFile\nWriteFile(1, b"R")', {'import _winapi': 1, '_winapi': 1})):
            with self.subTest(label):
                self.inside(snippet, **expected)
        with self.subTest('a nested import'):
            self.assertEqual(self.delta(self.mutated('def later():\n    import msvcrt\n    return msvcrt.getwch()')),
                             {('cli.py', 'doctor.later', 'import msvcrt'): 1, ('cli.py', 'doctor.later', 'msvcrt'): 1})
        for label, snippet in (('a module that only starts like one', 'import msvcrt_stand_in'), ('the name as a sentence', 'note = "msvcrt is not used"')):
            with self.subTest(label):
                self.inside(snippet)
        kinds = {site[2] for site in output_sites()}
        self.assertEqual({'msvcrt', 'import msvcrt', '_winapi', 'import _winapi'} & kinds, set())

    def test_a_namespace_of_its_own_or_a_route_value_stored_is_a_site(self):
        """What the route conditions of the reachability check read as the command line's: a handler that makes a namespace of its own, or stores
        a route value, could call a dispatcher as another route. Neither exists in the product, but for one stand-in with a single field."""
        for label, snippet, expected in (
                ('a namespace made', 'from argparse import Namespace\nNamespace(workbench_command="terminal")', {'namespace': 1}),
                ('argparse.Namespace by attribute', 'import argparse\nargparse.Namespace()', {'namespace': 1}),
                ('SimpleNamespace under an alias', 'from types import SimpleNamespace as via_ns\nvia_ns(workbench_command="terminal")', {'namespace': 1}),
                ('a route value stored', 'args.workbench_command = "terminal"', {'route value stored': 1}),
                ('a store on the namespace held by an object', 'self.args.command = "workbench"', {'route value stored': 1}),
                ('setattr on args', 'setattr(args, "workbench_command", "terminal")', {'route value stored': 1}),
                ('setattr of a route name on anything', 'setattr(options, "signin_command", "collect")', {'route value stored': 1}),
                ('vars(args)', 'vars(args)["workbench_command"] = "terminal"', {'route value stored': 1}),
                ('a parse of an argv of its own, on the parser of the product', 'from .cli import parser\nparser().parse_args(["workbench", "terminal"])',
                 {'namespace': 1}),
                ('a parse on any parser', 'import argparse\nargparse.ArgumentParser().parse_args(["x"])', {'namespace': 1}),
                ('parse_known_args', 'import argparse\nargparse.ArgumentParser().parse_known_args(["x"])', {'namespace': 1}),
                ('the method only passed on', 'import argparse\nparse = argparse.ArgumentParser().parse_args', {'namespace': 1}),
                ('the method by name', 'import argparse\ngetattr(argparse.ArgumentParser(), "parse_args")(["x"])', {'namespace': 1})):
            with self.subTest(label):
                self.inside(snippet, **expected)
        for label, snippet in (('a store that is not a route', 'args.format = "text"'), ('the typed command of an object', 'self.command = "x"')):
            with self.subTest(label):
                self.inside(snippet)

    def test_a_name_of_the_product_is_a_site_however_it_is_reached(self):
        """Sol V4 finding 2: `from .cli import _write_text as emit` resolved to .cli._write_text, which the bare-name branch skipped and
        route() did not know, and relative imports were not looked at where they are written. A resolved import whose final component
        is a scan name is classified, relative and package-qualified forms included, at the import and at every use of what it binds."""
        for label, snippet, expected in (
                ('Sol: a relative import under an alias', 'from .cli import _write_text as emit\nemit([%(line)r])',
                 {'import _write_text': 1, '_write_text': 1}),
                ('a relative import under its own name', 'from .cli import _write_text\n_write_text([%(line)r])',
                 {'import _write_text': 1, '_write_text': 1}),
                ('a package-qualified import under an alias', 'from intune_iac.cli import _write_text as emit\nemit([%(line)r])',
                 {'import _write_text': 1, '_write_text': 1}),
                ('imported from a module by its own name', 'from cli import _write_text as emit\nemit([%(line)r])',
                 {'import _write_text': 1, '_write_text': 1}),
                ('a module imported by its own name', 'import cli as c\nc._write_text([%(line)r])', {'_write_text': 1}),
                ('the module imported relatively', 'from . import cli as c\nc._write_text([%(line)r])', {'_write_text': 1}),
                ('the module imported from the package', 'from intune_iac import cli as c\nc._write_text([%(line)r])', {'_write_text': 1}),
                ('the package imported whole', 'import intune_iac.cli\nintune_iac.cli._write_text([%(line)r])', {'_write_text': 1}),
                ('the module under an alias', 'import intune_iac.cli as c\nc._write_text([%(line)r])', {'_write_text': 1}),
                ('an assignment from the module', 'from . import cli\nemit = cli._write_text\nemit([%(line)r])', {'_write_text': 2}),
                ('the name as a string', 'name = "_write_text"', {'_write_text as a string': 1}),
                ('another scan name of the product', 'from .shim import print as out\nout(%(line)r)', {'import print': 1, 'print': 1})):
            with self.subTest(label):
                self.inside(snippet, **expected)
        for label, snippet in (('a relative import of a name that is no route', 'from .io import canonical as c\nc({})'),
                               ('a standard-library name that is a scan name elsewhere', 'from re import compile as rc\nrc("x")'),
                               ('a chain on re', 'import re\nre.compile("x")')):
            with self.subTest(label):
                self.inside(snippet)

    def test_a_new_module_is_judged_the_same_way(self):
        """Sol V2's kube leaf: the same line, by every road, in a module of its own."""
        line = self.LINE
        for label, source, expected in (
                ('print', "def kube(args):\n    print(%r)\n", {'print': 1}),
                ('print to a stream', "import sys\ndef kube(args):\n    print(%r, file=sys.stderr)\n", {'print': 1, 'sys.stderr': 1}),
                ('sys.stdout.write', "import sys\ndef kube(args):\n    sys.stdout.write(%r)\n", {'sys.stdout': 1, 'write': 1}),
                ('a stream passed in', "def kube(args, stream):\n    stream.write(%r)\n", {'write': 1}),
                ('the terminal opened as a file', "import os\ndef kube(args):\n    with os.fdopen(1, 'w') as out:\n        out.write(%r)\n",
                 {'os.fdopen': 1, 'write': 1, 'standard descriptor': 1}),
                ('input as a value', "def kube(args, input_fn=input):\n    return input_fn(%r)\n", {'input': 1}),
                ('print as a value', "def kube(args, output_fn=print):\n    output_fn(%r)\n", {'print': 1}),
                ('an exit with a sentence', "import sys\ndef kube(args):\n    sys.exit(%r)\n", {'exit-text': 1}),
                ('the parser', "def kube(parser):\n    parser.error(%r)\n", {'parser-output': 1}),
                ('a module that writes by itself', "import logging\ndef kube(args):\n    logging.warning(%r)\n", None)):
            with self.subTest(label):
                sources = package_sources()
                sources['kube.py'] = source % line
                added = self.delta(sources)
                if expected is None:
                    self.assertEqual(added, {('kube.py', '<module>', 'import logging'): 1, ('kube.py', 'kube', 'logging'): 1})
                else:
                    self.assertEqual(added, {('kube.py', 'kube', kind): count for kind, count in expected.items()})
        sources = package_sources()
        sources['kube.py'] = "import json\ndef kube(args):\n    print(json.dumps({'next': %r}))\n" % line       # a JSON document is a machine form
        self.assertEqual(self.delta(sources), {})


class FingerprintTests(unittest.TestCase):
    """Sol V4 limit 1: a listing by count lets a listed site change what it does, a descriptor that becomes 1, a path that becomes a
    device, a child that inherits the terminal. Each listed site carries a fingerprint of its code (see output_fingerprints): the AST of the
    statement each reference is in and of the statements that bind the names that statement reads, with no line or column, with the
    function and the kind. A site whose code changes fails until its listing is updated, and says what the fingerprint is now."""

    @staticmethod
    def rewritten(module, function, transform):
        """The sources of the product with one function of one module changed by transform(function node), as ast.unparse writes it."""
        sources = package_sources()
        tree = ast.parse(sources[module])
        target = next(node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function)
        transform(target)
        sources[module] = ast.unparse(tree)
        return sources

    def changed(self, sources, *sites):
        """Exactly these sites report that their code changed, with the fingerprint now and the one listed, and nothing else is wrong."""
        self.assertEqual(output_sites(sources), output_sites())                  # no count moved: the old check saw nothing
        problems = output_site_problems(sources)
        self.assertEqual(len(problems), len(sites), problems)
        for problem, site in zip(problems, sorted(sites)):
            self.assertTrue(problem.startswith('%s: %s %s: its code changed (fingerprint ' % site), problem)
            now, listed = re.search(r'fingerprint (\w+), listed (\w+)\)', problem).groups()
            self.assertNotEqual(now, listed)
            self.assertEqual(listed, (OUTPUT_SITES.get(site) or NOT_A_TERMINAL[site])[2])

    def test_every_listed_site_carries_a_fingerprint_and_the_product_has_it(self):
        for table in (OUTPUT_SITES, NOT_A_TERMINAL):
            for site, value in table.items():
                self.assertEqual(len(value), 3, site)
                self.assertRegex(value[2], r'\A[0-9a-f]{12}\Z', site)
        self.assertEqual(output_fingerprints(), {site: value[2] for site, value in list(OUTPUT_SITES.items()) + list(NOT_A_TERMINAL.items())})

    def test_the_code_around_a_site_and_what_it_names_at_module_level_are_in_its_fingerprint(self):
        """The fingerprint of a site covers the conditions and handlers it is inside, and the module-level bindings of the names it reads, as
        well as its statement and the bindings in its function: a constant that becomes 1, or a condition that changes, fails the listing."""
        def prints(source, kind='os.fdopen'):
            return dict(output_fingerprints({'x.py': source}))[('x.py', 'save', kind)]
        base = "import os\nFD = %s\ndef save(data, flag):\n    %swith os.fdopen(FD, 'wb') as out:\n        out.write(data)\n"
        self.assertEqual(prints(base % (3, '')), prints(base % (3, '')))
        self.assertNotEqual(prints(base % (3, '')), prints(base % (1, '')))                       # FD = 3 becomes FD = 1
        conditional = "import os\ndef save(data, flag):\n    if %s:\n        with os.fdopen(3, 'wb') as out:\n            out.write(data)\n"
        self.assertNotEqual(prints(conditional % 'flag'), prints(conditional % 'not flag'))
        handled = "import os\ndef save(data):\n    try:\n        pass\n    except %s:\n        with os.fdopen(3, 'wb') as out:\n            out.write(data)\n"
        self.assertNotEqual(prints(handled % 'OSError'), prints(handled % 'Exception'))
        self.assertNotEqual(prints(base % (3, ''), 'write'), prints(base % (1, ''), 'write'))   # the write on the file object it opens

    def test_code_that_only_moves_keeps_its_fingerprint(self):
        sources = package_sources()
        sources['artifact_vault.py'] = '# a comment\n\n\n' + sources['artifact_vault.py']                  # every line number moves
        self.assertEqual(output_site_problems(sources), [])
        sources = package_sources()
        sources['cli.py'] = ast.unparse(ast.parse(sources['cli.py']))                                    # the module written out again
        self.assertEqual(output_site_problems(sources), [])

    def test_a_listed_site_whose_code_changes_fails_until_the_listing_is_updated(self):
        def descriptor_one(function):                                          # fd = os.open(...) becomes fd = 1
            for node in ast.walk(function):
                if isinstance(node, ast.Assign) and any(isinstance(item, ast.Name) and item.id == 'fd' for item in node.targets):
                    node.value = ast.Constant(1)

        def more_data(function):                                               # output.write(data) becomes output.write(data + b"x")
            for node in ast.walk(function):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'write':
                    node.args[0] = ast.BinOp(node.args[0], ast.Add(), ast.Constant(b'Run: kubectl apply PLAN_FILE'))

        def another_mode(function):                                            # os.fdopen(descriptor, 'wb') becomes 'ab'
            for node in ast.walk(function):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'fdopen'
                        and isinstance(node.args[1], ast.Constant) and node.args[1].value == 'wb'):
                    node.args[1] = ast.Constant('ab')

        def another_cwd(function):                                             # Popen(argv, cwd=cwd, ...) becomes cwd='/'
            for node in ast.walk(function):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'Popen':
                    for keyword in node.keywords:
                        if keyword.arg == 'cwd':
                            keyword.value = ast.Constant('/')

        def unguarded(function):                                               # print(text_guard_rows(rows)) becomes print(rows)
            for node in ast.walk(function):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'print':
                    node.args[0] = ast.Name('rows', ast.Load())
        for label, module, function, transform, sites in (
                ('the descriptor becomes a constant, in a statement of its own', 'artifact_vault.py', '_write_new', descriptor_one,
                 [('artifact_vault.py', '_write_new', 'os.fdopen'), ('artifact_vault.py', '_write_new', 'write')]),      # and what is written to it
                ('what is written changes', 'artifact_vault.py', '_write_new', more_data, [('artifact_vault.py', '_write_new', 'write')]),
                ('the mode of the file object changes', 'approval_authority.py', '_validator', another_mode,
                 [('approval_authority.py', '_validator', 'os.fdopen'), ('approval_authority.py', '_validator', 'write')]),
                ('a child is started elsewhere', 'provider_execution.py', '_supervise', another_cwd,
                 [('provider_execution.py', '_supervise', 'subprocess')]),
                ('the guard of the text sink is gone', 'cli.py', '_write_text', unguarded, [('cli.py', '_write_text', 'print')])):
            with self.subTest(label):
                self.changed(self.rewritten(module, function, transform), *sites)


class ReachTests(unittest.TestCase):
    """Sol V4 limits 2 and 6: the scan says where the product can put text in front of a person, not who can get there. A machine leaf must
    not run a function that holds a terminal site (see the note on reachability): no reach along direct names, and the reaches that need an
    attribute name only the ones listed. Each case puts code into cli.doctor, the function of a machine leaf, or changes a dispatcher, and
    the reaches of the leaf that are not listed must be exactly the ones named. Nothing is run."""

    TERMINAL = {('workbench.py', 'run_terminal'), ('workbench.py', '_run_terminal'), ('workbench.py', '_run_terminal.present'),
                ('workbench.py', '_render')}                                    # what run_terminal runs, all of it holding a site

    @staticmethod
    def mutated(snippet, function='doctor', module='cli.py', extra=None):
        """The sources of the product with a snippet at the start of the body of a function, and text added to the end of other modules."""
        sources = package_sources()
        tree = ast.parse(sources[module])
        target = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == function)
        target.body[0:0] = ast.parse(textwrap.dedent(snippet)).body
        sources[module] = ast.unparse(tree)
        for name, addition in (extra or {}).items():
            sources[name] += addition
        return sources

    @staticmethod
    def new_reaches(sources, leaf):
        """{holder: 'exact' | 'name'} the leaf reaches in these sources and the listing does not allow."""
        return {holder: kind for (name, holder), (kind, _) in machine_reaches(sources, leaves=(leaf,)).items()
                if name == leaf and (leaf, holder) not in EXACT_REACHES and not (kind == 'name' and leaf in NAME_REACHES.get(holder, ('', ()))[1])}

    def test_no_machine_leaf_reaches_a_terminal_site_along_direct_names_and_the_rest_is_listed(self):
        found = machine_reaches()
        self.assertEqual({key for key, (kind, _) in found.items() if kind == 'exact'}, set())
        self.assertEqual(reach_problems(), [])
        by_holder = collections.Counter(holder for (_, holder) in found)
        self.assertEqual(by_holder, {('windows_terminal.py', 'NativeConsole.session'): 127, ('windows_terminal.py', 'NativeConsole.write'): 127,
                                     ('windows_terminal.py', '_Win32.handles'): 127, ('windows_terminal.py', '_Win32.write'): 127,
                                     ('workbench_tui.py', 'Workspace.draw'): 111})
        self.assertEqual(len(found), 619)
        self.assertEqual(set(NAME_REACH_LEAVES), {' '.join(path) for path, kind in leaf_table().items() if kind == 'machine'})
        for holder, (reason, leaves) in NAME_REACHES.items():
            self.assertTrue(reason and leaves and set(leaves) <= set(NAME_REACH_LEAVES), holder)

    def test_a_machine_leaf_that_calls_a_function_that_holds_a_terminal_site_fails(self):
        """The calls the scan of the sites cannot see: nothing here is a site, and each leaf now runs the line terminal."""
        for label, snippet, expected in (
                ('a name imported from the module', 'from .workbench import run_terminal\nrun_terminal("x")', 'exact'),
                ('the same name under an alias', 'from .workbench import run_terminal as go\ngo("x")', 'exact'),
                ('the function only passed on', 'from .workbench import run_terminal\nhandler = run_terminal', 'exact'),
                ('the function in a dictionary', 'from .workbench import run_terminal\nhandlers = {"x": run_terminal}', 'exact'),
                ('an attribute of the module imported relatively', 'from . import workbench\nworkbench.run_terminal("x")', 'exact'),
                ('an attribute of the package imported whole', 'import intune_iac.workbench\nintune_iac.workbench.run_terminal("x")', 'exact'),
                ('an attribute call on anything', 'service.run_terminal("x")', 'name'),
                ('an attribute passed on as a value', 'handler = service.run_terminal', 'name'),
                ('a name given to getattr', 'getattr(service, "run_terminal")("x")', 'name')):
            with self.subTest(label):
                sources = self.mutated(snippet)
                self.assertEqual(output_site_problems(sources), [])                      # the scan of the sites sees nothing
                self.assertEqual(self.new_reaches(sources, 'doctor'), {holder: expected for holder in self.TERMINAL})

    def test_a_machine_leaf_reaches_what_a_function_it_calls_calls(self):
        sources = self.mutated('from .host_capabilities import show_it\nshow_it()', extra={
            'host_capabilities.py': '\n\ndef show_it():\n    from .workbench_tui import run_workspace\n    return run_workspace("x")\n'})
        self.assertEqual(output_site_problems(sources), [])
        found = self.new_reaches(sources, 'doctor')
        self.assertEqual(found[('workbench_tui.py', 'run_workspace')], 'exact')
        self.assertEqual(found[('workbench_tui.py', 'run_workspace.read_line')], 'exact')
        self.assertEqual(found[('workbench_tui.py', 'terminal_session')], 'exact')
        sources = self.mutated('from .workbench_tui import Workspace\nWorkspace("x")')                 # a class made: its __init__ runs
        self.assertEqual(self.new_reaches(sources, 'doctor'), {('workbench_tui.py', 'Workspace.__init__'): 'exact'})

    def test_a_base_class_is_the_class_that_the_file_naming_it_defines_or_imports(self):
        """Two modules may each define a class with the same name: windows_directory and windows_terminal both define _Win32, the storage
        classes derive from the first and only NativeConsole makes the second. A base is resolved through the definitions and imports of the
        file that names it, and only then is an edge exact; a name that nothing resolves is an edge by name, never an exact one."""
        base = 'class Base:\n    def __init__(self):\n        pass\n'
        missing = 'class Missing:\n    def __init__(self):\n        pass\n'
        child = '\n\nclass Child(%s):\n    pass\n\n\ndef make():\n    return Child()\n'
        sub = '\n\nclass Child(%s):\n    def __init__(self):\n        super().__init__()\n'
        one, two = {('one.py', 'Base.__init__')}, {('two.py', 'Base.__init__')}
        both = {('one.py', 'Missing.__init__'), ('two.py', 'Missing.__init__')}
        for label, user, extra, function, expected_exact, expected_name in (
                ('imported by its name', 'from .one import Base' + child % 'Base', {}, 'make', one, set()),
                ('imported under an alias', 'from .two import Base as Root' + child % 'Root', {}, 'make', two, set()),
                ('an attribute of a module imported from the package', 'from . import one' + child % 'one.Base', {}, 'make', one, set()),
                ('an attribute of a module imported under an alias', 'import intune_iac.two as second' + child % 'second.Base', {}, 'make', two, set()),
                ('an attribute of the package imported whole', 'import intune_iac.one' + child % 'intune_iac.one.Base', {}, 'make', one, set()),
                ('a subscripted base', 'from .two import Base' + child % 'Base[int]', {}, 'make', two, set()),
                ('defined in the file itself', base + child % 'Base', {}, 'make', {('user.py', 'Base.__init__')}, set()),
                ('a base of a base, in another module', 'from .mid import Mid' + child % 'Mid',
                 {'mid.py': 'from .two import Base\n\n\nclass Mid(Base):\n    pass\n'}, 'make', two, set()),
                ('a class that another module only re-exports', 'from .mid import Base' + child % 'Base',
                 {'mid.py': 'from .two import Base\n'}, 'make', two, set()),
                ('a base from outside the product', 'import threading' + child % 'threading.Thread',
                 {'one.py': 'class Thread:\n    def __init__(self):\n        pass\n'}, 'make', set(), set()),
                ('a name that nothing resolves', child % 'Missing', {'one.py': missing, 'two.py': missing}, 'make', set(), both),
                ('an attribute of a name that is not imported', child % 'service.Missing', {'one.py': missing, 'two.py': missing}, 'make',
                 set(), both),
                ('super() through an imported base', 'from .one import Base' + sub % 'Base', {}, 'Child.__init__', one, set()),
                ('super() through a base that nothing resolves', sub % 'Missing', {'one.py': missing, 'two.py': missing}, 'Child.__init__',
                 set(), both),
                ('the class itself imported and made (control)', 'from .one import Base\n\n\ndef make():\n    return Base()\n', {}, 'make',
                 one | {('one.py', '<module>')}, set())):
            with self.subTest(label):
                graph = ReachGraph({'one.py': base, 'two.py': base, **extra, 'user.py': user})
                edges = graph.edges(('user.py', function))
                self.assertEqual({target for target, _, exact in edges if exact}, expected_exact)
                self.assertEqual({target for target, _, exact in edges if not exact}, expected_name)

    def test_the_storage_classes_do_not_inherit_the_loader_of_the_console(self):
        """windows_storage._Win32Storage, windows_observer_credentials._Win32Credentials and what derives from them inherit windows_directory's
        _Win32, which loads kernel32 for directory and file calls. windows_terminal._Win32 is the console's, and nothing but NativeConsole
        makes it. With the console's loader a terminal site no machine leaf reaches it along direct names."""
        graph = ReachGraph()
        console = ('windows_terminal.py', '_Win32.__init__')
        for file, simple in (('windows_storage.py', '_Win32Storage'), ('windows_observer_credentials.py', '_Win32Credentials'),
                             ('windows_sqlite.py', '_Win32Snapshot'), ('windows_capture.py', '_NativeAPI'), ('windows_workbench.py', '_NativeAPI')):
            with self.subTest(simple):
                exact, loose = graph.inits(simple, file)
                self.assertIn(('windows_directory.py', '_Win32.__init__'), exact)
                self.assertNotIn(console, exact | loose)
        self.assertEqual(graph.inits('NativeConsole', 'windows_terminal.py'), ({('windows_terminal.py', 'NativeConsole.__init__')}, set()))
        listed = {**OUTPUT_SITES, console + ('ctypes.WinDLL',): (1, 'workbench workspace', '')}
        found = machine_reaches(listed=listed)
        self.assertEqual(sorted(leaf for (leaf, holder), (kind, _) in found.items() if holder == console and kind == 'exact'), [])

    def test_a_machine_leaf_that_makes_the_console_api_fails(self):
        """The console's Win32 API is a terminal. windows_terminal._Win32 loads kernel32 for the console and is made by NativeConsole, which
        only the Windows workspace binding makes: a machine leaf that makes either reaches the loader along direct names. Round 9 had listed the
        loader as a site that reaches no terminal, on a reason that came from the conflation of the two classes named _Win32, and the first
        two inputs below were caught by neither the listing, the reach nor the fingerprints."""
        loader = ('windows_terminal.py', '_Win32.__init__')
        for label, snippet in (
                ('the API made, and written through', 'from .windows_terminal import _Win32\napi = _Win32()\n'
                                                      'api.k.WriteConsoleW(api.handles()[1], "Run: kubectl apply PLAN_FILE", 28, None, None)'),
                ('the console made, and written through', 'from .windows_terminal import NativeConsole\nconsole = NativeConsole()\n'
                                                          'console.api.k.WriteConsoleW(console.output_handle, "Run: kubectl apply PLAN_FILE", 28, None, None)'),
                ('the class only passed on', 'from .windows_terminal import _Win32\nfactory = _Win32'),
                ('the API made by the package attribute', 'import intune_iac.windows_terminal\nintune_iac.windows_terminal._Win32()')):
            with self.subTest(label):
                self.assertEqual(self.new_reaches(self.mutated(snippet), 'doctor').get(loader), 'exact')
        with self.subTest('the storage classes made (control: windows_directory\'s API, not the console\'s)'):
            found = self.new_reaches(self.mutated('from .windows_storage import _Win32Storage\n_Win32Storage()'), 'doctor')
            self.assertNotIn(loader, found)

    def test_a_route_expression_is_true_false_or_unknown(self):
        """Sol V5 finding 1: `if args.command == "doctor" and 0 == 1: pass / else: run_terminal(...)` pruned the live else branch for the doctor
        leaf, because both operands were comparisons and so the test counted as nothing but route comparisons. A branch is pruned only when the
        known route comparisons decide the whole expression against it; and, or and not follow Kleene's rules for true, false and unknown.
        Each case is judged on the doctor leaf itself, with the code at the start of cli.doctor (as in the review) or of cli.execute."""
        terminal = '    from .workbench import run_terminal\n    run_terminal("x")'
        for label, snippet, function, reached in (
                ('Sol: a route clause and an operand that is not one, the else branch live',
                 'if args.command == "doctor" and 0 == 1:\n    pass\nelse:\n' + terminal, 'doctor', True),
                ('Sol: a route clause and an operand that is not one, in execute',
                 'if args.command == "doctor" and 0 == 1:\n    pass\nelse:\n' + terminal, 'execute', True),
                ('Sol: or with a constant true, the body live', 'if args.command == "workbench" or 1 == 1:\n' + terminal, 'doctor', True),
                ('Sol: or with a constant true, in execute', 'if args.command == "workbench" or 1 == 1:\n' + terminal, 'execute', True),
                ('a false clause decides an and', 'if args.command == "workbench" and 0 == 1:\n' + terminal, 'execute', False),
                ('a true clause decides an or', 'if args.command == "doctor" or 0 == 1:\n    pass\nelse:\n' + terminal, 'execute', False),
                ('not of a clause that is true', 'if not (args.command == "doctor"):\n' + terminal, 'execute', False),
                ('not of an expression that is unknown', 'if not (args.command == "doctor" and 0 == 1):\n' + terminal, 'execute', True),
                ('nested: an or of two false clauses, one of them an and with an unknown operand',
                 'if (args.command == "workbench" and 0 == 1) or args.command == "worker":\n' + terminal, 'execute', False),
                ('nested: a true or inside an and with an unknown operand, the else branch live',
                 'if (args.command == "workbench" or args.command == "doctor") and 0 == 1:\n    pass\nelse:\n' + terminal, 'execute', True),
                ('a walrus on the route attribute', 'if (cmd := args.command) == "workbench":\n' + terminal, 'execute', False),
                ('a walrus, and the name it binds in the next test',
                 'if (cmd := args.command) == "workbench":\n    pass\nelif cmd == "doctor":\n    pass\nelse:\n' + terminal, 'execute', False),
                ('a walrus around a whole comparison', 'if (ok := args.command == "doctor") and 0 == 1:\n    pass\nelse:\n' + terminal,
                 'execute', True),
                ('a tuple with an operand that is not a word', 'if args.command in ("workbench", other):\n' + terminal, 'execute', True),
                ('a tuple of words the leaf is not in (control)', 'if args.command in ("workbench", "worker"):\n' + terminal, 'execute', False)):
            with self.subTest(label):
                found = self.new_reaches(self.mutated(snippet, function=function), 'doctor')
                self.assertEqual(self.TERMINAL <= set(found), reached, found)
                if not reached:
                    self.assertFalse(self.TERMINAL & set(found), found)

    def test_code_behind_a_route_condition_the_leaf_fails_is_not_run_by_it(self):
        for label, snippet in (('the command is another', 'if args.command == "workbench":\n    from .workbench import run_terminal\n'
                                                           '    run_terminal("x")'),
                               ('the command is one of others', 'if args.command in ("workbench", "worker"):\n    from .workbench import run_terminal\n'
                                                                '    run_terminal("x")'),
                               ('the usage error of every route', 'parser.error("x")')):
            with self.subTest(label):
                self.assertEqual(self.new_reaches(self.mutated(snippet), 'doctor'), {})

    def test_when_the_route_is_not_read_every_branch_is_run(self):
        """Take away what lets the dispatcher of the workbench commands be read, and the leaves of the group reach what they should not."""
        def unconditional(function):                                   # if name == 'terminal': ... becomes if True: ...
            for node in ast.walk(function):
                if isinstance(node, ast.If) and ast.unparse(node.test) == "name == 'terminal'":
                    node.test = ast.Constant(True)

        def unreadable(function):                                      # name = args.workbench_command becomes name = args.workbench_command.lower()
            for node in ast.walk(function):
                if isinstance(node, ast.Assign) and ast.unparse(node.value) == 'args.workbench_command':
                    node.value = ast.Call(ast.Attribute(node.value, 'lower', ast.Load()), [], [])
        for label, transform in (('the condition is gone', unconditional), ('the route value is a call on the attribute', unreadable)):
            with self.subTest(label):
                sources = package_sources()
                tree = ast.parse(sources['workbench.py'])
                transform(next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == 'command'))
                sources['workbench.py'] = ast.unparse(tree)
                found = self.new_reaches(sources, 'workbench overview')
                self.assertTrue(self.TERMINAL <= set(found), found)
                self.assertEqual({found[holder] for holder in self.TERMINAL}, {'exact'})

    def test_a_handler_that_calls_a_dispatcher_as_another_route_is_caught_by_the_scan_not_by_the_reach(self):
        """The route conditions of the dispatchers are the leaf's own. A handler that hands one a namespace of its own, or a parse of an argv
        of its own, is not seen as another route by the reach check, and is a site of the scan (a namespace), so the listing stops it."""
        for label, snippet in (
                ('a namespace made', 'from argparse import Namespace\nfrom . import workbench\n'
                                     'workbench.command(Namespace(workbench_command="terminal", root="x", service_root=None))'),
                ('a parse of an argv of its own', 'from . import cli, workbench\n'
                                                  'workbench.command(cli.parser().parse_args(["workbench", "terminal"]))'),
                ('a parse handed to execute', 'from . import cli\ncli.execute(cli.parser().parse_args(["workbench", "terminal"]))')):
            with self.subTest(label):
                sources = self.mutated(snippet)
                self.assertEqual(self.new_reaches(sources, 'doctor'), {})
                self.assertEqual(output_site_problems(sources), ['cli.py: doctor has 1 unlisted namespace site(s)'])

    def test_a_machine_leaf_that_runs_the_command_line_again_fails(self):
        """cli.main with an argv of its own picks another route for the code that follows: the route conditions along the way would no longer
        describe what the leaf runs. Nothing here is a site of the scan; the run again is a reach to REENTRY, which no listing allows."""
        for label, snippet, expected in (
                ('main under an alias', 'from .cli import main as again\nagain(["workbench", "terminal"])', 'exact'),
                ('main as an attribute of the module', 'from . import cli\ncli.main(["workbench", "terminal"])', 'exact'),
                ('main as an attribute of the package', 'import intune_iac.cli\nintune_iac.cli.main(["workbench", "terminal"])', 'exact'),
                ('main only passed on', 'from . import cli\nhandler = cli.main', 'exact'),
                ('an attribute call named main', 'service.main(["workbench", "terminal"])', 'name'),
                ('a name given to getattr', 'getattr(service, "main")(["workbench", "terminal"])', 'name')):
            with self.subTest(label):
                sources = self.mutated(snippet)
                self.assertEqual(output_site_problems(sources), [])
                self.assertEqual(self.new_reaches(sources, 'doctor').get(REENTRY), expected)
        problems = reach_problems(self.mutated('from . import cli\ncli.main(["workbench", "terminal"])'))
        self.assertTrue(any(problem.startswith("the machine leaf 'doctor' runs the command line again (cli.py: main) by direct names, so the route "
                                               "conditions no longer describe what it runs, along ") and 'cli.py:main again' in problem
                            for problem in problems), problems)

    def test_a_listed_terminal_site_in_no_known_function_is_a_problem(self):
        listed = {**OUTPUT_SITES, ('cli.py', 'NoSuchFunction', 'print'): (1, None, 'abcdef123456')}
        self.assertEqual(reach_problems(listed=listed),
                         ['the site cli.py: NoSuchFunction is in no function that the call graph knows, so no reach to it can be judged'])

    def test_a_listed_reach_must_be_exact_both_ways(self):
        leaves = tuple(leaf for leaf in NAME_REACH_LEAVES if leaf != 'doctor')
        holder = ('windows_terminal.py', 'NativeConsole.write')
        problems = reach_problems(by_name={**NAME_REACHES, holder: (NAME_REACHES[holder][0], leaves)})
        self.assertEqual(len(problems), 1)
        self.assertTrue(problems[0].startswith("the machine leaf 'doctor' reaches windows_terminal.py: NativeConsole.write by an attribute name"))
        problems = reach_problems(by_name={**NAME_REACHES, ('workbench_tui.py', 'Workspace.draw'): (
            NAME_REACHES[('workbench_tui.py', 'Workspace.draw')][0], tuple(NAME_REACH_LEAVES))})
        self.assertEqual(sorted(problems), sorted("the listed reach by name of %r to workbench_tui.py: Workspace.draw is gone, or no longer needs a name" % leaf
                                                  for leaf in NOT_REACHING_DRAW))
        problems = reach_problems(exact={('doctor', ('workbench.py', 'run_terminal')): 'a reason'})
        self.assertEqual(problems, ["the listed exact reach of 'doctor' to workbench.py: run_terminal is gone"])


class ConsoleWriteTests(unittest.TestCase):
    """The C1 review of round 9: inputs that put text on the Windows console through its API, each written at the start of cli.doctor, the
    function of a machine leaf. At 97f9d89 none of them failed a check: not the listing of the sites (and with it the fingerprints of the
    listed ones), not the reach of the machine leaves. Each must now be caught by one of the two, and the case says which."""

    INPUTS = (
        ('C1a: the console API made, and written through', 'from .windows_terminal import _Win32\napi = _Win32()\n'
                                                            'api.k.WriteConsoleW(api.handles()[1], "Run: kubectl apply PLAN_FILE", 28, None, None)',
         ['unlisted console site'], 'exact'),
        ('C1b: the console made, and written through', 'from .windows_terminal import NativeConsole\nconsole = NativeConsole()\n'
                                                        'console.api.k.WriteConsoleW(console.output_handle, "Run: kubectl apply PLAN_FILE", 28, None, None)',
         ['unlisted console site'], 'exact'),
        ('C1c: a write through the handle of windows_directory', 'from .windows_directory import _Win32 as D\nd = D()\n'
                                                                  'd.k.WriteConsoleW(d.k.GetStdHandle(-11), "Run: kubectl apply PLAN_FILE", 28, None, None)',
         ['unlisted console site'], None),
        ('msvcrt.putwch', 'import msvcrt\nmsvcrt.putwch("R")', ['unlisted import msvcrt site', 'unlisted msvcrt site'], None),
    )

    def test_each_input_of_the_review_is_caught(self):
        loader = ('windows_terminal.py', '_Win32.__init__')
        for label, snippet, sites, reach in self.INPUTS:
            with self.subTest(label):
                sources = ReachTests.mutated(snippet)
                problems = output_site_problems(sources)
                reaches = ReachTests.new_reaches(sources, 'doctor')
                self.assertTrue(problems or reaches, 'nothing fails')
                for site in sites:
                    self.assertTrue(any(site in problem for problem in problems), (site, problems))
                self.assertEqual(reaches.get(loader), reach, reaches)


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

    def test_the_line_terminal_the_companion_and_the_provider_wizard_through_cli_main(self):
        """The leaves that print with print() or input() rather than cli._write_text, each through cli.main with its input scripted."""
        for sweep, routes, printed in (
                (sweep_terminal(), ('workbench terminal (prompt)', 'workbench terminal'), None),
                (sweep_companion(), ('workbench companion --serve', 'workbench companion --out'),
                 ('companion, live', 'workbench companion --serve')),
                (sweep_provider_wizard(), ('provider wizard (prompt)', 'provider wizard'), ('provider wizard session', 'provider wizard'))):
            judge(self, sweep)
            self.assertTrue(set(routes) <= {route for (_, route, *_) in sweep.coverage}, routes)
            if printed:
                self.assertGreater(sweep.printed[printed], 2, printed)                      # the sentences it prints were read


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
