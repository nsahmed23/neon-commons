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
    cli.parser(). A test counts the text branches of cli.main, so a route that prints text and is not driven here fails.
  * The wizard, the guided workflow and the journey: every prompt handed to the person and every line printed, scripted through
    the answers a person types, with and without a repository-owned edit of the generated output.
It excludes only machine forms: --json output, the non-terminal JSON document of the line terminal and the raw record layer of the
workspace (r), which shows that same JSON document.

The allowlist is the :help listing and the help legend (the synopses of workbench.HELP and of the legend's Changes and Workflow map
rows), and only on a surface that also shows the convention sentence (SYNOPSIS_CONVENTION of test_template_words): words in capitals
there are metavariables, and the sentence says so. Nothing else is allowed. Until a surface shows the sentence, its synopses fail.
"""
import argparse
import collections
import contextlib
import copy
import functools
import io
import json
import os
import re
import shlex
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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


def unresolved(text):
    """[(command as the reader reads it, [its unresolved operands])] for the commands readiness.commands_in finds in text. The
    name of a temporary directory or an operation is replaced by a fixed word, so one site is one finding in every run."""
    from intune_iac import entry, readiness
    found = []
    for begin, end, head, items in readiness.commands_in(text):
        bad = [string for item in items for string in _strings(item) if entry.is_fill_in(_bare(string))]
        if bad:
            found.append((TEMPORARY.sub(lambda m: '/tmp/<temp>' if m.group().startswith('/') else 'operation-<id>',
                                        ' '.join(text[begin:end].split())), bad))
    return found


ITEM = re.compile(r'(?:\d+[.)]|[-*])\s')                      # a numbered or bulleted row starts its own item


def paragraphs(rows):
    """The rows as a person reads them: a row that ends in a backslash continues on the next, and the rows of one block are one
    line (a wrapped command is one command); a blank row, and a numbered or bulleted row, begins a block. The wrapping is undone
    and nothing else is changed."""
    blocks, held = [], []
    for row in rows:
        text = row.strip()
        if not text:
            if held:
                blocks.append(' '.join(held))
                held = []
            continue
        if held and ITEM.match(text):
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

    def read(self, state, surface, size, texts, convention=False):
        """Judge the texts of one screen. convention: the surface shows SYNOPSIS_CONVENTION (all its pages)."""
        self.coverage[(state, surface, size)] += 1
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
        self.read(state, surface, size, readable(text.split('\n')))

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
        self.coverage.update(other.coverage)
        return self


# -- the workspace: what a frame holds, and how to draw every page of a surface ------------------------------------------------------

def frame_rows(ws):
    ws.stdout.seek(0)
    ws.stdout.truncate()
    ws.draw()
    return [ANSI.sub('', row) for row in ws.stdout.getvalue().split('\x1b[H')[-1].replace('\x1b[J', '').split('\r\n')]


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
        pages.append(split_frame(rows))
        previous = rows
        if not pages[-1][3]:
            break
        if clone.layer in ('catalog', 'workflow'):
            clone.page_move = 1                       # their paging keeps a command whole
        else:
            clone.scroll += max(1, len(pages[-1][1]))
    return pages, clone.layer


def screen_texts(pages, layer):
    """The texts to read on a surface: the chrome of each page, and the body of all its pages (a command may run over a page
    boundary where the surface does not keep it whole, so the pages join; a layer that pages by commands is not joined)."""
    texts = []
    for above, body, below, _ in pages:
        texts += readable(above) + readable(below)
    if layer in ('catalog', 'workflow'):
        for _, body, _, _ in pages:
            texts += readable(body)
    else:
        texts += readable([row for _, body, _, _ in pages for row in body])
    return texts


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


def drive(root, service_root, plan, state, sweep, schedule=SCHEDULE):
    """Run the real engine behind a Workspace fed by plan; at every Look read the screen at every size (in its rule style)."""
    from intune_iac.workbench import run_terminal
    from intune_iac.workbench_tui import Workspace

    def look(ws, label):
        for size, style in schedule:
            pages, layer = surface_pages(ws, size, style)
            body = ' '.join(' '.join(row for _, part, _, _ in pages for row in part).split())
            sweep.read(state, label, size, screen_texts(pages, layer), SYNOPSIS_CONVENTION in body)

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

def run_cli(argv, width=100):
    """(exit code, stdout, stderr) of cli.main(argv) in process, as a terminal `width` columns wide would show it."""
    from intune_iac import cli
    out, err = io.StringIO(), io.StringIO()
    with patch('shutil.get_terminal_size', return_value=os.terminal_size((width, 40))), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
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


KINDS = ('empty', 'repository', 'export', 'emptystore', 'full', 'context')


@functools.lru_cache(maxsize=1)
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
                                       readable(lines))
    return sweep


@functools.lru_cache(maxsize=1)
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
    from intune_iac import workbench
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
        for during in (None, {'command': 'execute', 'operation_root': '/ops/one'}, {'command': 'reconcile', 'operation_root': '/ops/one'},
                       {'command': 'collect', 'service_root': '/svc'}, {'command': 'diagnostics'}, {'command': 'review'}):
            result = {'status': 'interrupted', 'store_root': '/stores/one', 'interrupted_during': during}
            sweep.text('interrupted during %s' % (during or {}).get('command', 'nothing'), 'workbench workspace (after Ctrl-C)',
                       (width, 0), '\n'.join(workbench.interrupted_text(result, width)))
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
        sweep.read(state, '%s (%s)' % (route, kind), (0, 0), readable(text.split('\n')))


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
        self.assertIn("':queue-amend FILE'", ' '.join(sweep.failures()))

    def test_a_failure_names_the_surface_the_state_the_size_the_command_and_its_operands(self):
        sweep = Sweep()
        sweep.read('lost response', 'm Queue', (40, 12), ['x :queue-amend FILE none'])
        text = '\n'.join(sweep.failures())
        for part in ("':queue-amend FILE'", "['FILE']", "'m Queue'", "'lost response'", '40x12'):
            self.assertIn(part, text)

    def test_json_is_a_machine_form_and_is_not_read(self):
        sweep = Sweep()
        sweep.text('state', 'start --json', (80, 0), '{"next": "intune-iac catalog DIRECTORY"}')
        self.assertEqual(sweep.count(), 0)
        sweep.text('state', 'start', (80, 0), 'Run: intune-iac catalog DIRECTORY')
        self.assertEqual(sweep.count(), 1)


class WorkspaceSweepTests(unittest.TestCase):
    """Each state of a store, every surface, layer and prompt, every size: no command with an unresolved operand."""

    def check(self, name):
        sweep = sweep_state(name)
        self.assertEqual(sweep.failures(), [], '\n' + '\n'.join(sweep.failures()))


def _state_test(name):
    return lambda self: self.check(name)


for _number, _name in enumerate(STATES):
    setattr(WorkspaceSweepTests, 'test_state_%02d_%s' % (_number, re.sub(r'\W+', '_', _name).strip('_')), _state_test(_name))


class WorkspaceCoverageTests(unittest.TestCase):
    """The sweep reads what it says it reads: every state, every surface, every size (a pass is not a sweep that saw nothing)."""
    ALWAYS = NUMBERED + LETTERED + ('f Filters', ': command line (empty)', ': command line (typing)', ':catalog')

    def test_every_state_reads_every_surface_at_every_size(self):
        for name in STATES:
            coverage = sweep_state(name).coverage
            for surface in self.ALWAYS:
                for size in SIZES:
                    with self.subTest(state=name, surface=surface, size=size):
                        self.assertGreater(coverage[(name, surface, size)], 0)

    def test_the_selected_states_read_the_actions_layer_with_each_action_and_the_workflow_map_with_each_stage(self):
        for name, (_, options) in STATES.items():
            if not options.get('selected'):
                continue
            coverage = sweep_state(name).coverage
            for size in SIZES:
                with self.subTest(state=name, size=size):
                    self.assertGreater(coverage[(name, 'a Actions', size)], 0)
                    self.assertGreater(coverage[(name, 'a Actions, action 1 focused', size)], 0)
                    self.assertGreater(coverage[(name, 'a Actions, action 1 staged', size)], 0)
                    self.assertGreater(coverage[(name, ':workflow', size)], 0)
                    self.assertGreater(coverage[(name, ':workflow, stage 12 focused', size)], 0)

    def test_the_help_and_its_listing_are_read_where_they_are_asked_for(self):
        for name, (_, options) in STATES.items():
            if options.get('help_surfaces'):
                for size in SIZES:
                    self.assertGreater(sweep_state(name).coverage[(name, '? Help, typed details (e)', size)], 0, (name, size))

    def test_the_repository_entry_candidates_are_read(self):
        for name in ('repository-entry: needs an object', 'repository-entry: needs a commit', 'repository-entry: other tenant'):
            for size in SIZES:
                self.assertGreater(sweep_state(name).coverage[(name, ':repository-entry (candidates)', size)], 0, (name, size))

    def test_the_states_are_the_ones_the_brief_names(self):
        words = ' | '.join(STATES)
        for needle in ('empty store', 'no selection', 'selected policy', 'awaiting review', 'awaiting execute', 'lost response',
                       'queue with items', 'needs an object', 'other tenant', 'diagnostics'):
            self.assertIn(needle, words)


class CommandLineSweepTests(unittest.TestCase):
    def check(self, sweep):
        self.assertEqual(sweep.failures(), [], '\n' + '\n'.join(sweep.failures()))

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

    def test_every_text_branch_of_main_is_one_this_sweep_drives(self):
        """cli.main writes a person's text from a few branches (_write_text). A new one is a new human route: drive it above."""
        import inspect
        from intune_iac import cli
        source = inspect.getsource(cli.main)
        self.assertEqual(source.count('_write_text('), 7,
                         'cli.main has a text route the sweep does not drive: add it to sweep_*, then raise this count')

    def test_every_route_of_the_parser_is_in_one_of_the_sweeps(self):
        from intune_iac import cli
        found = {path for path, has_subroutes, _ in routes(cli.parser()) if not has_subroutes}
        text_routes = {('start',), ('catalog',), ('engineering',), ('signin', 'status'), ('signin', 'collect'),
                       ('workbench', 'workflow'), ('workbench', 'workspace'), ('simulate',)}
        self.assertTrue(text_routes <= found, sorted(text_routes - found))
        # the other routes print the JSON document of cli.main (a machine form); their --help and usage errors are read above
        self.assertGreater(len(found - text_routes), 100)


class WizardSweepTests(unittest.TestCase):
    def test_the_prompts_and_lines_of_the_wizard_the_guided_workflow_and_the_journey(self):
        sweep = sweep_wizards()
        self.assertEqual(sweep.failures(), [], '\n' + '\n'.join(sweep.failures()))
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
