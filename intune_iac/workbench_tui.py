"""Event-driven terminal workspace over the complete workbench command engine.

Presentation is not authority. Only explicit engine commands dispatch actions;
restoration is a strict allowlist of read-only navigation. No new dependency,
network client, subprocess launcher or approval implementation lives here.
"""
from __future__ import annotations

from collections import deque
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import select
import shlex
import sys
import unicodedata

from .io import AppError, load_json, write_json

MAX_COMMAND = 16384
MAX_RENDER_LINES = 200000
CONTEXT_VERSION = 'intune-workspace-context/1'
SERVICE_NAVIGATION_VERSION = 'workbench-service-navigation/1'
ADOPTION_NAVIGATION_VERSION = 'workbench-adoption-navigation/1'
ADOPTION_PLAN_NAVIGATION_VERSION = 'workbench-adoption-recovery-plan-navigation/1'
SERVICE_READ_ACTIONS = frozenset({'review', 'status', 'attach'})
SERVICE_ACTIONS = SERVICE_READ_ACTIONS | {'cancel', 'recover'}
READ_VIEWS = {'overview', 'inspect', 'settings', 'relationships', 'lineage',
              'history', 'history-recent', 'evidence-history', 'health', 'operations', 'views', 'help',
              'repository-status', 'dictionary', 'queue', 'start', 'diagnostics', 'families'}
TABS = ('Estate', 'Inspector', 'Relationships', 'History', 'Plan', 'Execution', 'Coverage', 'Help', 'Repository')
# Typed `cancel` between commands; short enough for an 80-column notice line (journey 28 run 3, frame 66).
CANCEL_NOTICE = 'Nothing is running to cancel; Esc discards a typed command (? lists all keys).'


def running_notice(command):
    """The RUNNING line while a command runs: which operation or read, and that its outcome is not yet known."""
    try:
        words = shlex.split(command)
    except ValueError:
        words = command.split()
    verb = words[0] if words else ''
    target = os.path.basename(words[1].rstrip('/')) if len(words) > 1 else ''
    if verb == 'execute' and target:
        return 'RUNNING: executing operation %s; its outcome is not yet known.' % target
    if verb == 'reconcile' and target:
        return 'RUNNING: reconciling operation %s (a read; it never replays the change).' % target
    if verb == 'collect':
        return 'RUNNING: collecting from the service; the new observation is not yet recorded.'
    return 'RUNNING: waiting for the engine; outcome is not yet known.'


TAB_COMMANDS = ('overview', 'inspect', 'relationships', 'history-recent', 'operations', 'operations', 'views', 'help',
                'repository-status')
ANSI_START = '\x1b[?1049h\x1b[?25l\x1b[?2004h'
ANSI_END = '\x1b[0m\x1b[?2004l\x1b[?25h\x1b[?1049l'


def _service_path(value):
    return (type(value) is str and 1 <= len(value) <= 4096 and Path(value).is_absolute()
            and '..' not in Path(value).parts and not any(ord(c) < 32 or ord(c) == 127 for c in value))


def _service_command(action, navigation):
    return 'service-' + action + ' ' + shlex.quote(navigation['job_root']) + ' ' + shlex.quote(navigation['policy_path'])


def _service_parts(parts):
    return (len(parts) == 3 and parts[0] in {'service-' + action for action in SERVICE_READ_ACTIONS}
            and all(_service_path(value) for value in parts[1:]))


def _valid_service_navigation(value):
    return (type(value) is dict and set(value) == {'schema_version', 'job_root', 'policy_path', 'read_action'}
            and value['schema_version'] == SERVICE_NAVIGATION_VERSION
            and type(value['read_action']) is str and value['read_action'] in SERVICE_READ_ACTIONS
            and _service_path(value['job_root']) and _service_path(value['policy_path']))


def _adoption_command(action, navigation):
    return 'adoption-' + action + ' ' + shlex.quote(navigation['job_root']) + ' ' + shlex.quote(navigation['policy_path'])


def _adoption_parts(parts):
    return (len(parts) == 3 and parts[0] in {'adoption-' + action for action in SERVICE_READ_ACTIONS}
            and all(_service_path(value) for value in parts[1:]))


def _valid_adoption_navigation(value):
    return (type(value) is dict and set(value) == {'schema_version', 'job_root', 'policy_path', 'read_action'}
            and value['schema_version'] == ADOPTION_NAVIGATION_VERSION
            and type(value['read_action']) is str and value['read_action'] in SERVICE_READ_ACTIONS
            and _service_path(value['job_root']) and _service_path(value['policy_path']))


def _adoption_plan_command(action, navigation):
    return 'adoption-plan-' + action + ' ' + shlex.quote(navigation['job_root']) + ' ' + shlex.quote(navigation['policy_path'])


def _adoption_plan_parts(parts):
    return (len(parts) == 3 and parts[0] in {'adoption-plan-' + action for action in SERVICE_READ_ACTIONS}
            and all(_service_path(value) for value in parts[1:]))


def _valid_adoption_plan_navigation(value):
    return (type(value) is dict and set(value) == {'schema_version', 'job_root', 'policy_path', 'read_action'}
            and value['schema_version'] == ADOPTION_PLAN_NAVIGATION_VERSION
            and type(value['read_action']) is str and value['read_action'] in SERVICE_READ_ACTIONS
            and _service_path(value['job_root']) and _service_path(value['policy_path']))


def safe_text(value):
    """Escape controls/format/combining characters; preserve inspectable bytes in DB.

    Width uses Unicode East Asian W/F=2, all other displayed codepoints=1.
    Combining/format sequences are escaped so they cannot obscure identity or
    forge status. Emoji grapheme composition is intentionally not interpreted.
    """
    result = []
    for char in str(value):
        number = ord(char)
        if char == '\n': result.append('\\n')
        elif char == '\r': result.append('\\r')
        elif char == '\t': result.append('\\t')
        elif unicodedata.category(char)[0] in 'CM' or number == 127:
            result.append('\\u%04x' % number if number <= 65535 else '\\U%08x' % number)
        else: result.append(char)
    return ''.join(result)


def cell_width(value):
    return sum(2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1 for c in value)


def clip(value, width):
    text = safe_text(value)
    if width <= 0: return ''
    result, used = [], 0
    for char in text:
        count = 2 if unicodedata.east_asian_width(char) in ('W', 'F') else 1
        if used + count > width: break
        result.append(char); used += count
    return ''.join(result)


def pad(value, width):
    result = clip(value, width)
    return result + ' ' * max(0, width - cell_width(result))


def wrap(value, width):
    """Wrap every escaped value without omitting hidden overflow."""
    width = max(1, width)
    line, used = '', 0
    for char in safe_text(value):
        count = 2 if unicodedata.east_asian_width(char) in ('W', 'F') else 1
        if used + count > width and line:
            yield line
            line, used = '', 0
        # Minimum display width is >= 12; this only affects direct helper use.
        if count > width: char, count = '?', 1
        line += char; used += count
    yield line


# Views shown on a surface that is not their own; the title names both, so the tab and the body agree.
SUBVIEWS = {'estate-overview': 'Relationship overview', 'diagnostics': 'Diagnostics', 'health': 'Health', 'queue': 'Maintenance queue', 'delivery': 'Delivery',
            'families': 'Families', 'start': 'Start', 'dictionary': 'Setting dictionary', 'dictionary-page': 'Setting dictionary',
            'lineage': 'Lineage', 'repository-entry': 'Repository entry', 'workflows': 'CI runs'}
# From this many body cells, the readable summary and the exact engine record sit side by side.
WIDE = 150
# The documented minimum window (columns, rows): the hazard's shortest wording, its response and the whole short
# identities fit. Below it a constrained state shows the session, the hazard and the prompt, never the body.
MIN_SIZE = (40, 12)
# Evidence classes whose mode word may stand in for them when the footer is narrow.
MODE_CLASSES = frozenset({'synthetic', 'synthetic_local_process_only', 'synthetic_local_process_and_modeled_service_only',
                          'graph_capture_unverified', 'graph_reader_laboratory', 'graph_reader_attempt',
                          'graph_authenticated_observation', 'mixed_observations'})
def operation_list(records):
    """One row per operation, in the order first recorded: its latest record and how many journal records it has."""
    latest, counts, order = {}, {}, []
    for row in records:
        if not isinstance(row, dict) or not isinstance(row.get('operation_root'), str):
            continue
        key = row.get('operation_id')
        if key not in latest:
            order.append(key)
        counts[key] = counts.get(key, 0) + 1
        latest[key] = row  # records arrive in store order, so the last one is the latest
    return [dict(latest[key], journal_records=counts[key]) for key in order]


# What a staged action does and does not do, said before how to submit it: longest form first, each complete; the
# shortest fits 40 columns (TASK-11 2.6 item 1).
STAGED_BOUNDARY = {
    'repository-refresh': ('STAGED refresh: records a new intent only; no Git commit, approval or apply.',
                           'STAGED refresh: no Git commit, approval or apply.',
                           'STAGED refresh: no commit, approval or apply.', 'New intent only; no commit/approve/apply'),
    'reconcile': ('STAGED reconcile: checks the outcome and records it; it never repeats the change.',
                  'STAGED reconcile: never repeats the change.', 'Reconcile: never repeats the change.'),
    'collect': ('STAGED collect: reads the modeled service and records the result; it changes no policy.',
                'STAGED collect: reads and records only.', 'Collect: reads and records only.'),
    'propose-from-intent': ('STAGED proposal: a local proposal for review; nothing is approved or sent.',
                            'STAGED proposal: nothing approved or sent.', 'Local proposal; nothing approved or sent'),
    'propose': ('STAGED proposal: a local proposal for review; nothing is approved or sent.',
                'STAGED proposal: nothing approved or sent.', 'Local proposal; nothing approved or sent'),
    'deployment-record': ('STAGED deployment record: a receipt in this store; nothing is sent.',
                          'STAGED record: a local receipt; nothing sent.', 'Record: local receipt; nothing sent.'),
    'repository-entry': ('STAGED repository survey: reads the repository; it records nothing.',
                         'STAGED survey: reads only.', 'Survey: reads only.'),
    'diagnostics': ('STAGED diagnostics: shows what diagnostics recorded; it records nothing.',
                    'STAGED diagnostics: records nothing.', 'Diagnostics: records nothing.'),
}
# Short names for a staged action, so its instruction fits beside it; the full label stays in the action list.
STAGED_NAMES = {'reconcile': 'reconcile', 'collect': 'collect', 'repository-refresh': 'refresh',
                'propose-from-intent': 'proposal', 'propose': 'proposal', 'repository-entry': 'repository survey',
                'diagnostics': 'diagnostics', 'deployment-record': 'deployment record'}
# The longest that fits is shown, so narrow terminals get every key and no cut-off word.
# a actions stays down to 48 columns: it is the route to every guided action (journey 27 review, Sonnet 19).
HELP_LINES = ('? help | a actions | : command | / search | e details | r raw record | b back | q exit',
              '? help | a actions | : command | / search | e details | r raw | b back | q exit',
              '? help | a actions | : command | e details | r raw | b back | q exit',
              '? help | a actions | : command | e details | b back | q exit',
              '? help | a actions | : command | b back | q exit',
              '? help | : command | b back | q exit')
# Read-only views that b (back) may return to; nothing that prepares, approves, executes or records is ever re-sent.
VIEW_COMMANDS = frozenset({'overview', 'select', 'inspect', 'relationships', 'history', 'history-recent', 'views',
                           'help', 'health', 'queue', 'start', 'families', 'dictionary', 'dictionary-page', 'lineage',
                           'diagnostics', 'estate-overview', 'repository-status', 'delivery', 'repository-entry',
                           'operations', 'review', 'workflows', 'search', 'search-page', 'views-page'})
LAYERS = {'details': 'typed details', 'raw': 'raw record', 'actions': 'actions', 'filters': 'filters'}
# The repository state the strip shows when the Inspector's diagnostics checked it.
REPOSITORY_FROM_CHECK = {'clear': 'current', 'attention': 'needs attention', 'not_recorded': 'none recorded',
                         'unavailable': 'not checked', 'partly_checked': 'not checked'}
# Recorded repository signals named in the Repository view's own words.
REPOSITORY_FROM_SIGNAL = {'repository_stale': 'stale', 'repository_unavailable': 'unavailable',
                          'repository_consumer_mismatch': 'consumer mismatch'}
# Recorded operation conditions, in the strip's words.
OPERATION_FROM_SIGNAL = {'operation_outcome_unknown': 'outcome_unknown', 'operation_diverged': 'diverged',
                         'operation_record_disagrees': 'records disagree', 'operation_unreadable': 'unreadable'}


def title_line(tab, last_command, value, layer='summary'):
    """The surface, the view shown on it when that view is not the surface's own, and the evidence layer."""
    name = last_command.split(' ', 1)[0] if isinstance(last_command, str) else ''
    sub = SUBVIEWS.get(name) if isinstance(value, dict) and value.get('status') != 'error' else None
    return 'INTUNE WORKBENCH  /  ' + tab + ('  /  ' + sub if sub else '') + ('  /  ' + LAYERS[layer] if layer in LAYERS else '')


def fit(value, width, ellipsis='...'):
    """Text that fits `width` cells, shortened at a word boundary with an ellipsis instead of cut mid-word."""
    text = safe_text(value)
    if cell_width(text) <= width:
        return text
    room = max(1, width - cell_width(ellipsis))
    cut = clip(text, room)
    space = cut.rfind(' ')
    return (cut[:space] if space > room // 2 else cut).rstrip() + ellipsis


# Inside a layer the same key returns to the summary, so its label says so.
LAYER_KEYS = {'details': (('e details', 'e summary'),), 'raw': (('r raw record', 'r summary'), ('r raw', 'r summary'))}
# Inside typed details or the raw record the key that returns to the summary comes before a actions.
LAYER_HELP_LINES = ('? help | : command | / search | e details | r raw record | b back | q exit',
                    '? help | : command | e details | r raw | b back | q exit',
                    '? help | : command | e details | b back | q exit',
                    '? help | : command | b back | q exit')
ACTION_KEY_LINES = ('? help | Up/Down choose | Enter stages | Esc closes | q exit', '? help | Enter stages | Esc closes | q exit',
                    'Enter stages | Esc closes | q exit')
# While a command or a search is typed, only the editing keys apply: q, ? and the digits are typed, not obeyed.
TYPING_KEY_LINES = ('{submit} {verb} | Esc cancels | Left/Right move | Ctrl-U clears',
                    '{submit} {verb} | Esc cancels | Ctrl-U clears', '{submit} {verb} | Esc cancels')
FILTER_KEY_LINES = ('? help | Up/Down choose | Enter applies | Esc closes | q exit', 'Enter applies | Esc closes | q exit')


def filter_choices():
    """Every estate filter, by dimension, then 'any' to clear that dimension."""
    from .workbench_views import COVERAGE_FILTERS, HEALTH_FILTERS, OWNERSHIP_FILTERS
    return [(dimension, value) for dimension, values in (('ownership', OWNERSHIP_FILTERS), ('coverage', COVERAGE_FILTERS),
                                                         ('health', HEALTH_FILTERS))
            for value in tuple(values) + (None,)]


def page_filters(page_command):
    """The limit, query and filters of the estate page in use, from the command this workspace built for it."""
    parts = shlex.split(page_command or '')
    limit = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 10
    if not parts or parts[0] != 'views-page':
        return limit, {}
    keys = ('query', 'ownership', 'coverage', 'health')
    return limit, {key: value for key, value in zip(keys, parts[3:]) if value != '-'}


def help_line(width, layer='summary', lead=()):
    """The key line for the width; keys the hazard band names (lead) come first in every form, so a key the band
    offers is never missing from the line below. The actions list has its own keys."""
    if layer in ('actions', 'filters'):
        lines = ACTION_KEY_LINES if layer == 'actions' else FILTER_KEY_LINES
        return next((line for line in lines if cell_width(line) <= width), lines[-1])
    lines = list(LAYER_HELP_LINES if layer in LAYER_KEYS else HELP_LINES)
    for old, new in LAYER_KEYS.get(layer, ()):
        lines = [line.replace(old, new) for line in lines]
    if lead:
        def led(line):
            missing = [key for key in lead if key not in line]
            return line.replace('? help | ', '? help | ' + ''.join(key + ' | ' for key in missing), 1) if missing else line
        lines = [led(line) for line in lines] + ['? help | ' + ' | '.join(lead) + ' | b back | q exit']
    return next((line for line in lines if cell_width(line) <= width), lines[-1])


def _cells_from_end(text, cells):
    """The longest end of text that fits the cells."""
    kept, used = [], 0
    for char in reversed(text):
        size = 2 if unicodedata.east_asian_width(char) in ('W', 'F') else 1
        if used + size > cells:
            break
        kept.append(char); used += size
    return ''.join(reversed(kept))


def _cells_from_start(text, cells):
    """The longest start of text that fits the cells."""
    kept, used = [], 0
    for char in text:
        size = 2 if unicodedata.east_asian_width(char) in ('W', 'F') else 1
        if used + size > cells:
            break
        kept.append(char); used += size
    return ''.join(kept)


def typing_line(width, mode, submit='Enter'):
    """The key line while a command or a search is typed: the keys that edit, submit and cancel it."""
    verb = 'searches' if mode == 'search' else 'submits'
    lines = [line.format(submit=submit, verb=verb) for line in TYPING_KEY_LINES]
    return next((line for line in lines if cell_width(line) <= width), lines[-1])


def band_keys(rows):
    """The keys a hazard band offers, as the key line names them."""
    text = ' '.join(rows or [])
    return tuple(name for keys, name in ((('a: ', '(a actions)'), 'a actions'), (('i: ',), 'i details'))
                 if any(key in text for key in keys))


def status_line(scope, first, last, total, width, ellipsis='...', short=None):
    """Evidence class, rows and the approval statement, never cut mid-word: the class, else its mode word (short),
    else nothing (the context strip leads with the mode); the statement takes its short form last."""
    rows = 'rows %d-%d/%d' % (first, last, total)
    # The class in words, else its mode word in the same case: never a snake_case or shouted label.
    scope = str(scope).replace('_', ' ') if scope else scope
    short = short.lower() if isinstance(short, str) else short
    for tail in (rows + ' | no automatic approval', rows + ' | no auto-approval'):
        for label in (scope, short):
            if label and cell_width('[%s] %s' % (label, tail)) <= width:
                return '[%s] %s' % (label, tail)
    for tail in (rows + ' | no automatic approval', rows + ' | no auto-approval'):
        if cell_width(tail) <= width:
            return tail
    return fit(rows + ' | no auto-approval', width, ellipsis)


def ruled(left, fill, right, inner, label=None):
    """A border line; a label, when it fits, sits inside it near the left corner."""
    if not label or cell_width(label) + 4 > inner:
        return left + fill * inner + right
    return left + fill * 2 + label + fill * (inner - 2 - cell_width(label)) + right


def terminal_size(stream):
    try:
        size = os.get_terminal_size(stream.fileno())
        return max(12, min(200, size.columns)), max(8, min(100, size.lines))
    except (AttributeError, OSError, ValueError): return 80, 24


def visual_supported(stdin, stdout):
    if os.name != 'posix' or os.environ.get('TERM') == 'dumb': return False
    try:
        import termios
        return stdin.isatty() and stdout.isatty() and bool(termios.tcgetattr(stdin.fileno()))
    except (AttributeError, OSError, ValueError): return False


@contextmanager
def terminal_session(stdin, stdout):
    """Always restore the saved terminal attributes and presentation modes."""
    import termios
    fd = stdin.fileno()
    before = termios.tcgetattr(fd)
    changed = list(before)
    changed[6] = list(before[6])
    changed[3] &= ~(termios.ICANON | termios.ECHO)
    changed[0] &= ~termios.IXON
    changed[6][termios.VMIN] = 1
    changed[6][termios.VTIME] = 0
    try:
        termios.tcsetattr(fd, termios.TCSANOW, changed)
        stdout.write(ANSI_START); stdout.flush()
        yield
    finally:
        primary = sys.exc_info()[1]
        failures = []
        try: termios.tcsetattr(fd, termios.TCSANOW, before)
        except (OSError, ValueError): failures.append('terminal attributes')
        try:
            stdout.write(ANSI_END); stdout.flush()
        except (OSError, ValueError): failures.append('display modes')
        if failures:
            message = 'Terminal cleanup incomplete (' + ', '.join(failures) + '); restore the terminal independently.'
            if primary is not None:
                primary.add_note(message)
            else:
                raise AppError('workspace_terminal_cleanup_failed', message)


class KeyReader:
    """Bounded byte reader; terminal escape input is data, never output."""
    SEQUENCES = {b'\x1b[A': 'up', b'\x1b[B': 'down', b'\x1b[C': 'right', b'\x1b[D': 'left',
                 b'\x1b[5~': 'pageup', b'\x1b[6~': 'pagedown', b'\x1b[H': 'home', b'\x1b[F': 'end',
                 b'\x1b[3~': 'delete', b'\x1b[200~': 'paste_start', b'\x1b[201~': 'paste_end'}

    def __init__(self, stream):
        self.fd = stream.fileno()
        self.pending = bytearray()

    def _fill(self, timeout):
        if not select.select([self.fd], [], [], timeout)[0]: return False
        data = os.read(self.fd, 256)
        if not data: raise EOFError
        self.pending.extend(data)
        return True

    def read(self):
        if not self.pending and not self._fill(0.15): return None
        if self.pending[0] == 27:
            for _ in range(64):
                value = bytes(self.pending)
                for sequence, name in self.SEQUENCES.items():
                    if value.startswith(sequence):
                        del self.pending[:len(sequence)]
                        return name
                if len(value) == 1 or any(sequence.startswith(value) for sequence in self.SEQUENCES):
                    if self._fill(0.025): continue
                break
            # Consume an unrecognized CSI/OSC escape without turning its tail
            # into command input. An isolated Escape cancels only local editing.
            count = 1
            if len(self.pending) > 1 and self.pending[1] in (ord('['), ord(']')):
                count = min(len(self.pending), 64)
            del self.pending[:count]
            return 'escape'
        first = self.pending.pop(0)
        controls = {3: 'interrupt', 4: 'eof', 9: 'tab', 10: 'enter', 13: 'enter',
                    8: 'backspace', 127: 'backspace', 21: 'clear', 12: 'redraw'}
        if first in controls: return controls[first]
        if first < 32: return 'ignored'
        raw = bytearray([first])
        needed = 1 if first < 128 else 2 if first < 224 else 3 if first < 240 else 4
        for _ in range(needed - 1):
            if not self.pending and not self._fill(0.025): return 'ignored'
            raw.append(self.pending.pop(0))
        try: return ('text', raw.decode('utf-8', errors='strict'))
        except UnicodeError: return 'ignored'


# 256-colour palette indices per theme. Every state is written in words; colour only reinforces them,
# and the information architecture is the same in every theme.
THEMES = {
    'dark': {'bg': '234', 'fg': '252', 'accent': '81', 'ok': '114', 'warn': '179', 'bad': '174'},
    # ok and warn are one step darker than the first choice: both passed AA by only about 0.1, now about 7.8 and 5.6.
    'light': {'bg': '230', 'fg': '237', 'accent': '24', 'ok': '22', 'warn': '94', 'bad': '124'},
    'blueprint': {'bg': '17', 'fg': '153', 'accent': '231', 'ok': '121', 'warn': '222', 'bad': '217'},
    'high-contrast': {'bg': '16', 'fg': '231', 'accent': '226', 'ok': '46', 'warn': '214', 'bad': '196'},
}
# Fixed phrases and markers only: a bare word such as "verified" also appears in "NOT verified".
TONES = (('ok', ('[x]', 'NO CONFIGURATION CHANGE', 'REPOSITORY MATCHES THE RECORDED INTENT', 'succeeded_verified',
                 'desired_state_observed', 'matches desired')),
         ('warn', ('[?]', 'REPOSITORY CHANGED SINCE THE RECORDED INTENT', 'CHANGE COMPARISON UNKNOWN', 'outcome unknown',
                   'outcome_unknown', 'stale')),
         ('bad', ('[!]', 'REFUSED', 'ERROR:', 'INPUT REJECTED:', 'REPOSITORY UNAVAILABLE', 'expired', 'not available', 'failed')))


def _tone_pattern():
    def phrase(text):
        pattern = re.escape(text)
        return ('(?<!\\w)' if text[0].isalnum() else '') + pattern + ('(?!\\w)' if text[-1].isalnum() else '')
    return re.compile('|'.join('(?P<%s>%s)' % (tone, '|'.join(phrase(p) for p in sorted(phrases, key=len, reverse=True)))
                               for tone, phrases in TONES))


_TONES = _tone_pattern()
# A bracketed [HEADING], or a section heading: capital words at the start, then two spaces or the line end.
_HEADING = re.compile(r'([|│]\s*)(\[[A-Z][A-Z0-9 /&,().-]*\]|[A-Z][A-Z]+(?: [A-Z]+)*(?=  |\s*[|│]?$))')
# A recorded signal line ('! ...'), emphasized in every mode so a warning never depends on colour.
_MARK = re.compile(r'([|│]\s*)(! \S.*?)(\s*[|│]?)$')
RULES = {'unicode': (('┌', '─', '┐'), '│', ('└', '─', '┘')),
         'ascii': (('+', '-', '+'), '|', ('+', '-', '+'))}


def choose_rules(encoding, term, requested='auto'):
    """Fine Unicode rules on a UTF-8 terminal that draws them; ASCII otherwise or when asked."""
    if requested == 'ascii':
        return 'ascii'
    capable = (encoding or '').lower().replace('-', '').replace('_', '') == 'utf8'
    return 'unicode' if capable and term not in ('linux', 'dumb', 'vt100', 'vt220', '') else 'ascii'


def paint(line, palette, base=None):
    """Bold a leading [HEADING] and tint fixed state phrases; the text is unchanged and the background is kept."""
    base = base or palette['fg']
    mark = _MARK.match(line)
    if mark:
        tinted = _TONES.sub(lambda m: '\x1b[38;5;%sm%s\x1b[38;5;%sm' % (palette[m.lastgroup], m.group(0), base), mark.group(2))
        return mark.group(1) + '\x1b[1m' + tinted + '\x1b[22m' + mark.group(3)
    match = _HEADING.match(line)
    head, rest = ('', line) if match is None else (match.group(1) + '\x1b[1m' + match.group(2) + '\x1b[22m', line[match.end():])
    return head + _TONES.sub(lambda m: '\x1b[38;5;%sm%s\x1b[38;5;%sm' % (palette[m.lastgroup], m.group(0), base), rest)


def emphasize(line):
    """Bold a heading and a signal line without colour, so --no-color and NO_COLOR keep the same structure."""
    mark = _MARK.match(line)
    if mark:
        return mark.group(1) + '\x1b[1m' + mark.group(2) + '\x1b[22m' + mark.group(3)
    match = _HEADING.match(line)
    return line if match is None else match.group(1) + '\x1b[1m' + match.group(2) + '\x1b[22m' + line[match.end():]


class Workspace:
    """UI state contains navigation only. Typed engine values remain authoritative."""
    def __init__(self, root, *, theme='dark', no_color=False, reduced_motion=True, stdin=None, stdout=None, _native_binding=None, rules='auto'):
        from .workbench_store import WorkbenchStore, _private
        self.native_binding = _native_binding
        if _native_binding is None:
            self.store = WorkbenchStore(root)
            self.context_path = self.store.root / 'workspace-context.json'
            self.submission_key = 'enter'
        else:
            from .windows_workspace_binding import NativeWorkspaceBinding
            if type(_native_binding) is not NativeWorkspaceBinding:
                raise AppError('workspace_native_binding_required', 'An exact native presentation capability is required.')
            _native_binding.check(root)
            self.store = _native_binding.store
            self.context_path = None
            self.submission_key = 'submit'
        self.stdin = sys.stdin if stdin is None else stdin
        self.stdout = sys.stdout if stdout is None else stdout
        self.theme = theme
        self.color = not no_color and 'NO_COLOR' not in os.environ
        self.rules = choose_rules(getattr(self.stdout, 'encoding', None), os.environ.get('TERM', ''), rules)
        self.reduced_motion = reduced_motion  # Both modes are event-driven: no decorative motion.
        self.value = {}
        self.selected = None
        # Last facts the engine reported about the selected object, for the
        # context strip only; never a source of truth and never persisted.
        self.facts = {}
        self.tab = 0
        self.highlight = 0
        self.scroll = 0
        self.mode = None
        self.buffer = ''
        self.cursor = 0
        self.pasting = False
        self.input_overflow = False
        self.notice = 'Select an immutable identity. Press : for any text command.'
        self.last_command = 'overview'
        self.view_command = 'overview'
        self.page_command = 'overview'
        self.rows = []
        self.operation_rows = []
        self.operation_highlight = 0
        self.active_operation = None
        self.execution_result = None
        self.active_service = None
        self.active_adoption = None
        self.active_adoption_plan = None
        self.entry_focus = 0
        # Focus in the estate overview; kept while the session lasts, so returning finds the same policy.
        self.overview_focus = 0
        # Each view opens as its summary; e and r show typed details and the raw record, Esc returns.
        self.layer = 'summary'
        # Read-only views visited this session, for b (back); never persisted, never a change.
        self.trail = []
        # A staged action is bound to the policy it was offered for; action_focus is the actions layer's row.
        self.staged = None
        self.action_focus = 0
        # A refresh waiting for its difference to arrive before it is staged.
        self.pending_stage = None
        # A read of the selected policy for the band and the actions only: due after a command that may have written,
        # sent when a lists the actions. Its result never replaces the screen.
        self.quiet = None
        self.current_view = None
        self.pending = deque()
        self.size = self._terminal_size()
        self.key_reader = None
        self._detail_cache = None
        self.context_valid = False
        value = None
        if self.native_binding is not None:
            value = self.native_binding.context.load()
        elif self.context_path.exists() or self.context_path.is_symlink():
            _private(self.context_path)
            value = load_json(self.context_path)
        if value is not None:
            self._validate_context(value)
            self.selected = value['selected']
            self.view_command = value['view_command']
            self.page_command = value['page_command']
            self.tab = value['tab']
            self.active_service = value.get('service_navigation')
            self.active_adoption = value.get('adoption_navigation')
            self.active_adoption_plan = value.get('adoption_plan_navigation')
            service_view = _service_parts(shlex.split(self.view_command)) or _adoption_parts(shlex.split(self.view_command)) or _adoption_plan_parts(shlex.split(self.view_command))
            # Only validated navigation resumes. Service paths carry no receipt,
            # signature, runtime capability or permission to dispatch execution.
            self.pending.append(self.page_command)
            if self.selected:
                self.pending.append('select ' + shlex.quote(self.selected))
            if self.view_command != self.page_command and (self.selected or service_view or self.view_command in ('help', 'health', 'operations', 'views', 'queue', 'start', 'families')):
                self.pending.append(self.view_command)
            self.context_valid = True

    def _terminal_size(self):
        return self.native_binding.console.size() if self.native_binding is not None else terminal_size(self.stdout)

    def _validate_context(self, value):
        from .workbench_store import _identity
        required = {'schema_version', 'tenant_id', 'selected', 'view_command', 'page_command', 'tab'}
        if (not isinstance(value, dict) or not required <= set(value) <= required | {'service_navigation', 'adoption_navigation', 'adoption_plan_navigation'} or value['schema_version'] != CONTEXT_VERSION
                or value['tenant_id'] != self.store.tenant_id or type(value['tab']) is not int or not 0 <= value['tab'] < len(TABS)):
            raise AppError('workspace_context_invalid', 'Workspace context is invalid; preserve it for inspection before reopening.')
        if value['selected'] is not None: _identity(value['selected'])
        navigation = value.get('service_navigation')
        if navigation is not None and not _valid_service_navigation(navigation):
            raise AppError('workspace_context_invalid', 'Only bounded read-only service navigation may resume.')
        adoption_navigation = value.get('adoption_navigation')
        if adoption_navigation is not None and (not _valid_adoption_navigation(adoption_navigation) or navigation is not None):
            raise AppError('workspace_context_invalid', 'Only one bounded read-only operation domain may resume.')
        plan_navigation = value.get('adoption_plan_navigation')
        if plan_navigation is not None and (not _valid_adoption_plan_navigation(plan_navigation) or navigation is not None or adoption_navigation is not None):
            raise AppError('workspace_context_invalid', 'Only one bounded read-only operation domain may resume.')
        for key in ('view_command', 'page_command'):
            command = value[key]
            if type(command) is not str or len(command) > MAX_COMMAND:
                raise AppError('workspace_context_invalid', 'Workspace navigation exceeds its bounds.')
            try: parts = shlex.split(command)
            except ValueError: raise AppError('workspace_context_invalid', 'Workspace navigation is not a complete read-only command.')
            valid = (len(parts) == 1 and parts[0] in READ_VIEWS)
            if _service_parts(parts):
                valid = plan_navigation is None and adoption_navigation is None and (navigation is None or parts[1:] == [navigation['job_root'], navigation['policy_path']])
            if _adoption_parts(parts):
                valid = plan_navigation is None and adoption_navigation is not None and parts[1:] == [adoption_navigation['job_root'], adoption_navigation['policy_path']]
            if _adoption_plan_parts(parts):
                valid = plan_navigation is not None and parts[1:] == [plan_navigation['job_root'], plan_navigation['policy_path']]
            if parts == ['adoption-history']:
                valid = value['selected'] is not None
            if parts and parts[0] == 'history-recent':
                valid = (value['selected'] is not None and 1 <= len(parts) <= 3 and
                         all(p.isascii() and p.isdigit() for p in parts[1:]) and
                         (len(parts) < 2 or len(parts[1]) <= 4 and 1 <= int(parts[1]) <= 1000) and
                         (len(parts) < 3 or len(parts[2]) <= 10 and 0 <= int(parts[2]) <= 1000000000))
            if key == 'page_command':
                valid = ((parts and parts[0] == 'overview' and len(parts) <= 3 and
                          all(p.isascii() and p.isdigit() for p in parts[1:])) or
                         (parts and parts[0] == 'search-page' and len(parts) >= 4 and
                          all(p.isascii() and p.isdigit() for p in parts[1:3])) or
                         (parts and parts[0] == 'views-page' and 3 <= len(parts) <= 7 and
                          all(p.isascii() and p.isdigit() for p in parts[1:3])))
            if not valid: raise AppError('workspace_context_invalid', 'Only bounded read-only navigation may resume.')

    def save_context(self):
        from .workbench_store import _private
        if self.native_binding is None:
            _private(self.store.root, True)
            if self.context_path.exists() or self.context_path.is_symlink(): _private(self.context_path)
        value = {'schema_version': CONTEXT_VERSION, 'tenant_id': self.store.tenant_id,
                 'selected': self.selected, 'view_command': self.view_command,
                 'page_command': self.page_command, 'tab': self.tab,
                 'service_navigation': self.active_service, 'adoption_navigation': self.active_adoption, 'adoption_plan_navigation': self.active_adoption_plan}
        self._validate_context(value)
        if self.native_binding is None:
            write_json(self.context_path, value)
        else:
            self.native_binding.context.save(value)

    def receive(self, value):
        """Callback after the SAME engine has validated/executed an input."""
        if not isinstance(value, dict): value = {'result': value}
        if value.get('status') == 'interrupted':
            self.quiet = None  # never left waiting to swallow a later result
        quiet = getattr(self, 'quiet', None)
        if quiet and quiet.get('state') == 'sent' and value.get('status') != 'interrupted':
            self.quiet = None
            self._quiet_receive(value, quiet.get('purpose'))
            return
        # Initial help should not displace restored selection/navigation.
        self.value = value
        self.scroll = 0
        if value.get('schema_version') == 'workbench-repository-entry/1':
            self.entry_focus = 0
        if value.get('status') == 'error':
            from .workbench_screens import REFUSALS
            code = (value.get('error') if isinstance(value.get('error'), dict) else {}).get('code', 'unknown')
            # The verdict is said once, in the body; the notice points to what to read there.
            self.notice = ('The cause and the next step are above.' if code in REFUSALS
                           else "The engine's message is above.")
        else:
            object_id = value.get('object_id')
            if object_id and self.last_command.startswith('select '):
                if self.selected != object_id:
                    self.staged = None
                    self.active_operation = None; self.execution_result = None
                    self.active_service = None; self.active_adoption = None; self.active_adoption_plan = None
                self.selected = object_id
                self.view_command = 'inspect'
            self._learn(value)
            history_page = value.get('pagination', {}).get('scope') == 'history_page'
            if value.get('status') == 'selection_cleared' or (self.last_command in ('next', 'previous') and not history_page): self.selected = None
            if self.selected is None and (self.view_command.startswith('history-recent') or self.view_command == 'adoption-history'):
                self.view_command = 'overview'
            if history_page and isinstance(value.get('history'), list):
                self.selected = value['object_id']
                self.view_command = 'history-recent %d %d' % (value['pagination']['limit'], value['pagination']['offset'])
            if 'objects' in value and isinstance(value['objects'], list):
                # The engine paginates mapped and pending identities together.
                # Unsupported/denied observations remain selectable evidence,
                # never silently disappear because no mapped snapshot exists.
                pending = value.get('pending_observations', [])
                candidates = value['objects'] + (pending if isinstance(pending, list) else [])
                self.rows = sorted([row for row in candidates if isinstance(row, dict) and isinstance(row.get('object_id'), str)],
                                   key=lambda row: row['object_id'])
                self.highlight = min(self.highlight, max(0, len(self.rows) - 1))
                page = value.get('pagination', {})
                limit = page.get('limit', 10)
                offset = page.get('offset', 0)
                if type(limit) is int and type(offset) is int:
                    if value.get('schema_version') == 'workbench-four-views/1' and isinstance(value.get('filters'), dict):
                        filters = value['filters']
                        self.page_command = 'views-page %d %d %s' % (limit, offset, ' '.join(
                            shlex.quote(filters.get(key) or '-') for key in ('query', 'ownership', 'coverage', 'health')))
                    else:
                        self.page_command = ('search-page %d %d %s' % (limit, offset, shlex.quote(value['query']))
                                             if isinstance(value.get('query'), str) and value['query'] else
                                             'overview %d %d' % (limit, offset))
            if isinstance(value.get('operations'), list):
                self.operation_rows = operation_list(value['operations'])
                self.operation_highlight = min(self.operation_highlight, max(0, len(self.operation_rows) - 1))
            if isinstance(value.get('operation_root'), str):
                if self.active_operation != value['operation_root']: self.execution_result = None
                self.active_operation = value['operation_root']
                self.active_service = None; self.active_adoption = None; self.active_adoption_plan = None
            try: parts = shlex.split(self.last_command)
            except ValueError: parts = []
            if len(parts) >= 2 and parts[0] in ('execute', 'reconcile'):
                self.active_operation = parts[1]
                self.execution_result = value
                self.active_service = None; self.active_adoption = None; self.active_adoption_plan = None
            action = value.get('interface_action')
            if (type(action) is str and action in SERVICE_ACTIONS and
                    type(value.get('service_job_root')) is str and type(value.get('service_policy')) is str):
                navigation = {'schema_version':SERVICE_NAVIGATION_VERSION,
                    'job_root':os.path.abspath(value['service_job_root']),
                    'policy_path':os.path.abspath(value['service_policy']),
                    'read_action':action if action in SERVICE_READ_ACTIONS else 'attach'}
                if not _valid_service_navigation(navigation):
                    raise AppError('workspace_context_invalid', 'Service navigation cannot be saved safely.')
                self.active_service = navigation; self.active_adoption = None; self.active_adoption_plan = None
                self.active_operation = None; self.execution_result = None
                self.view_command = _service_command(navigation['read_action'], navigation)
            if (type(action) is str and action in SERVICE_ACTIONS and value.get('evidence_class') == 'protected_adoption_journal'
                    and type(value.get('adoption_job_root')) is str and type(value.get('adoption_policy')) is str):
                navigation = {'schema_version': ADOPTION_NAVIGATION_VERSION,
                    'job_root': os.path.abspath(value['adoption_job_root']),
                    'policy_path': os.path.abspath(value['adoption_policy']),
                    'read_action': action if action in SERVICE_READ_ACTIONS else 'attach'}
                if not _valid_adoption_navigation(navigation):
                    raise AppError('workspace_context_invalid', 'Adoption navigation cannot be saved safely.')
                self.active_adoption = navigation; self.active_service = None; self.active_adoption_plan = None
                self.active_operation = None; self.execution_result = None
                self.view_command = _adoption_command(navigation['read_action'], navigation)
            if (type(action) is str and action in SERVICE_ACTIONS and value.get('evidence_class') == 'protected_adoption_recovery_plan_journal'
                    and type(value.get('adoption_plan_job_root')) is str and type(value.get('adoption_plan_policy')) is str):
                navigation = {'schema_version': ADOPTION_PLAN_NAVIGATION_VERSION,
                    'job_root': os.path.abspath(value['adoption_plan_job_root']),
                    'policy_path': os.path.abspath(value['adoption_plan_policy']),
                    'read_action': action if action in SERVICE_READ_ACTIONS else 'attach'}
                if not _valid_adoption_plan_navigation(navigation):
                    raise AppError('workspace_context_invalid', 'Recovery Plan navigation cannot be saved safely.')
                self.active_adoption_plan = navigation; self.active_adoption = None; self.active_service = None
                self.active_operation = None; self.execution_result = None
                self.view_command = _adoption_plan_command(navigation['read_action'], navigation)
            if self.last_command == 'adoption-history': self.view_command = self.last_command
            if self.last_command in READ_VIEWS and not history_page: self.view_command = self.last_command
            # Persist only after successful result. The explicit service route
            # saves read-only paths, never approvals, captures or credentials.
            self.save_context()
            self.notice = self._notice_for(value)
        pending, self.pending_stage = getattr(self, 'pending_stage', None), None
        if pending is not None and self.last_command == 'repository-status':
            self._stage_after_difference(pending, value)
        name = self.last_command.split(' ', 1)[0] if isinstance(self.last_command, str) else ''
        if self.selected and name and name not in VIEW_COMMANDS and value.get('status') != 'interrupted':
            # The command may have recorded something, so the band and the actions are read again, quietly.
            self.quiet = {'purpose': 'refresh', 'state': 'due'}
        self.draw()

    def _notice_for(self, value):
        """One qualified line about the result just shown: what it is, its evidence mode, and where to look next."""
        from .workbench_screens import evidence_words
        if value.get('status') == 'selection_cleared':
            # The workspace context file records the cleared selection; no recorded evidence changes.
            return 'No policy is selected now; recorded evidence is unchanged and nothing was cancelled.'
        name = self.last_command.split(' ', 1)[0] if isinstance(self.last_command, str) else ''
        if name not in VIEW_COMMANDS:
            # Only the views are known to be read-only; any other command may have prepared, recorded or run something.
            status = value.get('status')
            if isinstance(status, str):
                return '%s ran; the engine reported status %s.' % (name or 'The command', status.replace('_', ' '))
            # Results without a status still say what they recorded, never only that there was no status.
            if isinstance(value.get('journal_status'), str):
                readback = value.get('classification')
                return '%s ran; the journal is now %s%s.' % (
                    name, str(value['journal_status']).replace('_', ' '),
                    " (reconcile's readback: %s)" % str(readback).replace('_', ' ') if readback else '')
            if isinstance(value.get('artifact_id'), str) and isinstance(value.get('kind'), str):
                return '%s recorded %s %s%s.' % (
                    name, value['kind'].replace('_', ' '), value['artifact_id'][:12],
                    '' if value.get('created', True) else ' (already recorded; nothing changed)')
            return '%s ran; its result is above.' % (name or 'The command')
        view = SUBVIEWS.get(name) or TABS[self.tab]
        # Where the engineer is now; no Ready beside a hazard that is still unresolved (TASK-11 2.6 item 7).
        return 'Viewing %s.' % view

    def _learn(self, value):
        """Keep the latest engine-reported facts about the selected object for the context strip."""
        # An overview with nothing observed yet says nothing about where evidence comes from.
        empty = isinstance(value.get('objects'), list) and not value['objects'] and not value.get('pending_observations')
        if isinstance(value.get('evidence_class'), str) and ('snapshot_id' in value or isinstance(value.get('objects'), list)) and not empty:
            # Observations say where the estate's evidence comes from; the strip's first word states it.
            self.mode_class = value['evidence_class']
        if not self.selected or value.get('object_id') not in (None, self.selected):
            return
        facts = self.facts if self.facts.get('object_id') == self.selected else {'object_id': self.selected}
        if value.get('object_id') == self.selected and isinstance(value.get('name'), str):
            facts['name'] = value['name']
        # Lineage reports its own freshness and keeps the observation's beside it; its own is never the observation's.
        observed = value.get('observation_freshness') if 'provenance_origin' in value else value.get('freshness')
        if value.get('object_id') == self.selected and isinstance(observed, str):
            facts['observation'] = observed
        attention = value.get('attention') if isinstance(value.get('attention'), dict) else {}
        checked = (attention.get('checked') or {}).get('repository')
        if value.get('object_id') == self.selected and checked in REPOSITORY_FROM_CHECK:
            # The repository view's own words where a recorded signal names the condition.
            codes = [signal.get('code') for signal in attention.get('signals') or []
                     if isinstance(signal, dict) and signal.get('area') == 'repository']
            facts['repository'] = next((REPOSITORY_FROM_SIGNAL[code] for code in codes if code in REPOSITORY_FROM_SIGNAL),
                                       REPOSITORY_FROM_CHECK[checked])
        # A recorded operation condition reaches the strip even in a session that has not opened that operation.
        operation_signals = [signal for signal in attention.get('signals') or []
                             if isinstance(signal, dict) and signal.get('code') in OPERATION_FROM_SIGNAL]
        if value.get('object_id') == self.selected and operation_signals:
            facts['operation'] = OPERATION_FROM_SIGNAL[operation_signals[0]['code']]
            evidence = operation_signals[0].get('evidence') if isinstance(operation_signals[0].get('evidence'), dict) else {}
            if isinstance(evidence.get('operation_id'), str): facts['operation_id'] = evidence['operation_id']
            else: facts.pop('operation_id', None)
        elif (value.get('object_id') == self.selected and (attention.get('checked') or {}).get('operations') == 'clear'
              and facts.get('operation') in OPERATION_FROM_SIGNAL.values()):
            # A newer read checked the operations and found no hazard: one known from an earlier result is resolved.
            facts.pop('operation', None); facts.pop('operation_id', None)
        # The recorded signals feed the hazard band on every surface while this policy stays selected, and the
        # read model's actions feed the actions layer (a).
        if value.get('object_id') == self.selected and isinstance(attention.get('signals'), list):
            facts['signals'] = [signal for signal in attention['signals'] if isinstance(signal, dict)]
        if value.get('object_id') == self.selected and isinstance(value.get('actions'), list):
            facts['actions'] = [action for action in value['actions'] if isinstance(action, dict)]
        if value.get('object_id') == self.selected and isinstance(attention.get('signals'), list):
            facts.pop('unverified', None)  # a read that answered
        if value.get('object_id') == self.selected and isinstance(value.get('states'), dict):
            facts['states'] = value['states']
        if value.get('object_id') == self.selected and isinstance(value.get('identity_prefixes'), dict):
            facts['identity_prefixes'] = value['identity_prefixes']
        if value.get('object_id') == self.selected and 'observation_eligibility' in value:
            if isinstance(value['observation_eligibility'], dict): facts['eligibility'] = value['observation_eligibility']
            else: facts.pop('eligibility', None)
        if value.get('object_id') == self.selected and 'snapshot_id' in value and isinstance(value.get('evidence_class'), str):
            facts['evidence_class'] = value['evidence_class']
        repository = value.get('repository')
        if value.get('schema_version') == 'workbench-repository-status/1' and isinstance(value.get('freshness'), dict):
            facts['repository'] = str(value['freshness'].get('status'))
        elif isinstance(repository, dict) and isinstance(repository.get('freshness'), dict):
            facts['repository'] = str(repository['freshness'].get('status'))
        elif isinstance(repository, dict) and repository.get('cited') and isinstance(repository.get('freshness'), str):
            facts['repository'] = repository['freshness']
        # Execute and reconcile results name the operation, not the object; they
        # concern the selected object's active operation.
        operation_command = self.last_command.split(' ', 1)[0] in ('execute', 'reconcile')
        if (isinstance(value.get('operation_id'), str) and isinstance(value.get('status'), str)
                and (value.get('object_id') == self.selected or (value.get('object_id') is None and operation_command))):
            facts['operation'] = value['status']; facts['operation_id'] = value['operation_id']
        elif (isinstance(value.get('operation_id'), str) and isinstance(value.get('journal_status'), str)
                and value.get('object_id') is None and operation_command):
            # Reconcile states the journal status it left; the result has no status of its own.
            facts['operation'] = value['journal_status']; facts['operation_id'] = value['operation_id']
        if value.get('schema_version') == 'workbench-delivery/1' and value.get('object_id') == self.selected:
            facts['operation'] = str(value.get('journal_status'))
        self.facts = facts

    def _context_strip(self, width):
        from .workbench_screens import context_strip
        facts = self.facts if self.selected and self.facts.get('object_id') == self.selected else {}
        return context_strip(self.store.tenant_id, self.selected, facts, width, getattr(self, 'mode_class', None))

    def _surface_summary(self, width):
        from .workbench_screens import collection_result_lines, is_collection_run, word_wrap
        value = self.value
        rows = []
        if self._states_here(value):
            # The same three states as the Inspector, from the last read of this policy, before the surface's own detail.
            from .workbench_screens import state_lines
            rows.extend(state_lines(self.facts['states'], width, 'STATE (from the last read of this policy)',
                                    prefixes=self.facts.get('identity_prefixes'),
                                    reviewing=value.get('operation_id') if self.tab == 4 else None)[1:])
            rows.append('')
        def field(label, item):
            # Absent and yes/no values read as words; the exact record below keeps the literal.
            rendered = ('not recorded' if item is None else ('yes' if item else 'no') if isinstance(item, bool) else item
                        if isinstance(item, str) else json.dumps(item, ensure_ascii=False, allow_nan=False))
            rows.extend(word_wrap(label + ': ' + rendered, width))
        if value.get('status') == 'error' and isinstance(value.get('error'), dict):
            from .workbench_screens import refusal_lines
            code = (value.get('error') or {}).get('code')
            rows.extend(refusal_lines(value, width, known=self._known_cause(code)))
            rows.append('')
        elif (isinstance(value.get('artifact_id'), str) and isinstance(value.get('kind'), str)
                and isinstance(value.get('data'), dict) and 'created' in value):
            from .workbench_screens import recorded_lines
            rows.extend(recorded_lines(value, width))
        elif value.get('status') in ('ready_local_model_handoff', 'adopted_local_model'):
            from .workbench_screens import adoption_lines
            rows.extend(adoption_lines(value, width))
        elif (value.get('status') == 'review_form_written' or value.get('reason') == 'review_not_recorded'
                or value.get('schema_version') in ('workbench-queue-review/1', 'workbench-queue-history/1')):
            from .workbench_screens import review_lines
            rows.extend(review_lines(value, width))
        elif is_collection_run(value):
            rows.extend(collection_result_lines(value, width))
        elif value.get('status') == 'selection_cleared':
            rows.append('[SELECTION CLEARED]')
            rows.extend(word_wrap('No policy is selected. Press 1 for Estate and Enter on a policy to select it; nothing was '
                                  'changed or cancelled.', width))
            rows.append('')
        elif self.tab == 2 and 'provenance_origin' in value and isinstance(value.get('fields'), list):
            from .workbench_screens import lineage_lines
            rows.extend(lineage_lines(value, width))
        elif (self.tab == 0 and isinstance(value.get('objects'), list) and not value['objects']
                and not value.get('pending_observations') and isinstance(value.get('filters'), dict)
                and any(value['filters'].values())):
            filters = value['filters']
            asked = ['search "%s"' % filters['query'] if key == 'query' else '%s %s' % (key, str(filters[key]).replace('_', ' '))
                     for key in ('query', 'ownership', 'coverage', 'health') if filters.get(key)]
            total = value.get('total_inventory_objects')
            rows.append('[NO MATCH]')
            rows.extend(word_wrap('No policy matches %s (0 of %s in the inventory). f changes the filters; / searches '
                                  'again.' % (' and '.join(asked), '%d %s' % (total, 'policy' if total == 1 else 'policies')
                                              if isinstance(total, int) else 'an unknown number of policies'), width))
            rows.append('')
        elif (self.tab == 0 and isinstance(value.get('objects'), list) and not value['objects']
                and not value.get('pending_observations') and not isinstance(value.get('filters'), dict) and not value.get('query')):
            rows.append('[NO OBSERVATIONS YET]')
            rows.extend(word_wrap('This store has no observed policies. Collect from a modeled service (:collect), import a '
                                  'capture with the workbench import-capture command, or press s to see what exists beside '
                                  'the store and the next step.', width))
            rows.append('')
        elif value.get('schema_version') == 'workbench-estate-overview/1':
            from .workbench_screens import overview_lines
            policies = value.get('policies') or []
            focus = min(getattr(self, 'overview_focus', 0), max(0, len(policies) - 1)) if self.tab == 0 else None
            rows.extend(overview_lines(value, width, getattr(self, 'rules', 'ascii'), focus, self.selected))
        elif self.tab == 8 and value.get('schema_version') == 'workbench-repository-entry/1':
            from .workbench_screens import repository_entry_lines, word_wrap
            if getattr(self, 'mode', None) == 'command' and self.buffer.startswith('repository-import '):
                rows.append('[COMMAND FOR REVIEW] Submit it to record the policy; Esc discards it. Nothing has run.')
                rows.extend(word_wrap(self.buffer, width))
                rows.append('')
            rows.extend(repository_entry_lines(value, width, getattr(self, 'entry_focus', 0)))
        elif self.tab == 7 and value.get('schema_version') == 'workbench-families/1':
            from .workbench_screens import families_lines
            rows.extend(families_lines(value, width))
        elif self.tab == 7 and value.get('schema_version') == 'workbench-start/1':
            from .entry import start_lines
            rows.extend(start_lines(value, width))
        elif self.tab == 1 and isinstance(value.get('entries'), list) and 'fact_provenance_contract' in value:
            from .workbench_screens import dictionary_lines
            rows.extend(dictionary_lines(value, width))
        elif self.tab == 1 and value.get('object_id'):
            from .workbench_screens import inspector_lines
            rows.extend(inspector_lines(value, width))
            if isinstance(value.get('raw_capture_observation'), dict):
                rows.extend(word_wrap('The settings and targeting above are the normalized mapping of this observation.', width))
            capture = value.get('raw_capture_observation')
            if isinstance(capture, dict):
                field('Literal capture status', capture.get('status', 'unknown'))
                field('Literal collection coverage', capture.get('coverage', 'unknown'))
                integrity = capture.get('capture_integrity', {}).get('status', 'unknown')
                field('Literal byte integrity', integrity)
                if integrity == 'verified_local_bytes':
                    raw = capture.get('source', {}).get('raw_observed', {})
                    for key in ('settings', 'assignments'):
                        items = raw.get(key)
                        field('Captured ' + key + ' records', len(items) if isinstance(items, list) else 'unknown')
                rows.extend(word_wrap('Literal collected values are separate from normalized mapping; incomplete collection does not establish empty intent.', width))
        elif self.tab == 2 and isinstance(value.get('relationships'), list):
            from .workbench_screens import relationship_lines
            rows.extend(relationship_lines(value, width, getattr(self, 'rules', 'ascii')))
            # Shown whenever a capture exists, above all when its retained bytes no longer verify.
            if isinstance(value.get('raw_capture_observation'), dict):
                rows.append('[LITERAL CAPTURE]')
                integrity = (value.get('raw_evidence_integrity') or {}).get('status', 'unknown')
                field('Literal capture status', value.get('raw_mapping_status', 'unknown'))
                field('Literal byte integrity', integrity)
                assignments = value.get('raw_observed_assignments')
                field('Captured assignment records', len(assignments) if isinstance(assignments, list) else
                      'not in the capture' if integrity == 'verified_local_bytes' else 'not read: the bytes did not verify')
        elif self.tab == 3 and isinstance(value.get('history'), list):
            from .workbench_screens import history_lines
            facts = self.facts if getattr(self, 'facts', None) and self.facts.get('object_id') == value.get('object_id') else {}
            observation = (facts.get('states') or {}).get('observation') if isinstance(facts.get('states'), dict) else None
            rows.extend(history_lines(value, width, current=observation if isinstance(observation, dict) else None))
        elif self.tab == 3 and value.get('schema_version') == 'workbench-protected-adoption-history/1':
            rows.append('[PROTECTED STATE-ONLY ADOPTION HISTORY]')
            field('Object', value.get('object_id', 'unknown'))
            field('Linked operations', len(value.get('operations', [])))
            rows.extend(word_wrap('Adoption records state ownership and independent qualification. This history does not establish a Graph deployment or a last-apply baseline.', width))
        elif self.tab in (4, 5) and value.get('evidence_class') == 'protected_adoption_recovery_plan_journal':
            rows.append('[ADOPTION RECOVERY PLAN ' + ('REVIEW]' if self.tab == 4 else 'JOURNAL]'))
            manifest = value.get('manifest', {})
            for label, key in (('Verification operation', 'operation_id'), ('Manifest SHA-256', 'manifest_sha256'),
                    ('Original adoption', 'original_operation_id'), ('Durable status', 'status'), ('Plan dispatches', 'dispatches'),
                    ('Cancellation requested', 'cancel_requested'), ('Profile', 'profile')):
                field(label, value.get(key, manifest.get(key, 'unknown')))
            original = value.get('original', {})
            field('Original status', original.get('status', manifest.get('original_facts', {}).get('status', 'unknown')))
            field('Original recorded outcome', original.get('outcome', 'see original adoption journal'))
            rows.extend(word_wrap('This separately approved operation permits a native no-change plan only. Original import attribution remains unknown; no import or apply is replayed. Scope release requires fresh independent state and Graph readback.', width))
        elif self.tab in (4, 5) and value.get('evidence_class') == 'protected_adoption_journal':
            rows.append('[PROTECTED STATE-ONLY ADOPTION ' + ('REVIEW]' if self.tab == 4 else 'JOURNAL]'))
            manifest = value.get('manifest', {})
            for label, key in (('Operation', 'operation_id'), ('Tenant', 'tenant_id'), ('Objects', 'object_ids'),
                    ('Manifest SHA-256', 'manifest_sha256'), ('Action', 'action'), ('Profile', 'profile'),
                    ('Durable status', 'status'), ('Import dispatches', 'dispatches'),
                    ('First-plan dispatches', 'verification_dispatches'), ('First-plan status', 'verification_status'),
                    ('Cancellation requested', 'cancel_requested')):
                field(label, value.get(key, manifest.get(key, 'unknown')))
            if self.tab == 4:
                field('Intended policy and assignment writer', manifest.get('intended_writer', 'unknown'))
                field('Approval authority', value.get('authority', 'independent external signer required'))
            else:
                field('Recorded outcome', value.get('outcome') or 'not recorded; outcome unknown')
            rows.extend(word_wrap('State-only adoption does not deploy Graph changes or promote a last-apply baseline. Native import completion requires independent receiving-state, Graph and first-plan evidence.', width))
            rows.extend(word_wrap('Attach and tab navigation are read-only. Cancellation does not prove termination; recovery never replays import.', width))
        elif self.tab == 4 and value.get('evidence_class') == 'protected_service_journal':
            rows.append('[PROTECTED SERVICE REVIEW]')
            manifest = value.get('manifest', {})
            for label, key in (('Operation', 'operation_id'), ('Tenant', 'tenant_id'), ('Objects', 'object_ids'),
                               ('Manifest SHA-256', 'manifest_sha256'), ('Plan SHA-256', 'saved_plan_sha256'),
                               ('Profile', 'profile'), ('Expiry', 'expires_at'), ('Approval authority', 'authority')):
                field(label, value.get(key, manifest.get(key, 'unknown')))
            for label, key in (('Action', 'action'), ('Backend scope SHA-256', 'backend_scope_sha256'),
                               ('Execution binding SHA-256', 'execution_binding_sha256'),
                               ('Run binding SHA-256', 'run_binding_sha256'),
                               ('Storage binding SHA-256', 'storage_binding_sha256'),
                               ('Identity binding SHA-256', 'identity_binding_sha256')):
                field(label, manifest.get(key, 'unknown'))
            rows.extend(word_wrap('Review is read-only. This terminal cannot sign or dispatch the protected service operation.', width))
        elif self.tab == 5 and value.get('evidence_class') == 'protected_service_journal':
            rows.append('[PROTECTED SERVICE EXECUTION]')
            for label, key in (('Operation', 'operation_id'), ('Tenant', 'tenant_id'), ('Objects', 'object_ids'),
                               ('Manifest SHA-256', 'manifest_sha256'), ('Plan SHA-256', 'saved_plan_sha256'),
                               ('Durable status', 'status'), ('Cancellation requested', 'cancel_requested'),
                               ('Recorded dispatches', 'dispatches'), ('Profile', 'profile'),
                               ('CI attestation', 'ci_attestation')):
                field(label, value.get(key, 'unknown'))
            outcome = value.get('outcome')
            field('Recorded outcome', outcome if outcome is not None else 'not recorded; outcome unknown')
            rows.extend(word_wrap('A cancellation request does not establish termination. Host completion does not establish independent service or device convergence.', width))
            rows.extend(word_wrap('Attach reads the durable journal. Recovery is an explicit text command and never replays execution.', width))
        elif self.tab == 4 and value.get('operation_id'):
            from .workbench_screens import change_lines
            if isinstance(value.get('field_changes'), dict):
                rows.append('[CHANGE REVIEW]')
                # The review result carries both full bodies, so a cut change list can say where the rest is.
                whole = isinstance(value.get('before'), dict) and isinstance(value.get('desired'), dict)
                # The plan's before is the observation the plan was prepared from, not the newest one.
                rows.extend(change_lines(value['field_changes'], width, 'BEFORE (observed when prepared)', remainder=(
                    'the complete before and desired bodies are in e typed details and r raw record' if whole else None)))
                if isinstance(value.get('changes'), list):
                    from .workbench_screens import change_words
                    field('Plan changes', ', '.join(change_words(str(item), self.facts.get('identity_prefixes'))
                                                    for item in value['changes']) or 'none')
                repository = value.get('repository')
                if isinstance(repository, dict) and repository.get('cited'):
                    field('Cited repository intent', str(repository.get('repository_intent_id'))[:12] + ' (' + str(repository.get('freshness')) + ')')
                elif isinstance(repository, dict) and repository.get('context_changed'):
                    field('Context file', 'changed since this proposal was prepared, so its citation is unknown and '
                                          'execute refuses it (maintenance_source_changed)')
                rows.append('')
            rows.append('[PLAN REVIEW]')
            # The digest execute needs is named for what it is: a review binding, not an approval (Sonnet 22).
            from .workbench_screens import _readable_epoch, evidence_words
            for label, key in (('Operation', 'operation_id'), ('Tenant', 'tenant_id'), ('Object', 'object_id'),
                               ('Status', 'status'), ('Plan SHA-256', 'saved_plan_sha256'),
                               ('Review digest (execute needs it)', 'approval_digest'), ('Expiry', 'expires_at'),
                               ('Evidence class', 'evidence_class')):
                item = value.get(key, 'unknown')
                field(label, _readable_epoch(item) if key == 'expires_at' else str(item).replace('_', ' ')
                      if key in ('status', 'evidence_class') else item)
                judged = value.get('approval_window')
                if key == 'expires_at' and isinstance(judged, dict) and value.get('status') == 'prepared':
                    # As execute judges it (maintenance.approval_window); a view records nothing.
                    from .workbench_screens import WINDOW_WORDS
                    field('Approval window', WINDOW_WORDS.get(judged.get('state'), str(judged.get('state'))))
        elif self.tab == 5 and value.get('schema_version') == 'workbench-delivery/1':
            from .workbench_screens import delivery_lines
            rows.extend(delivery_lines(value, width, getattr(self, 'rules', 'ascii')))
        elif self.tab == 5 and ('result' in value or 'operation_id' in value):
            result = value.get('result', value)
            from .workbench_screens import execution_effect_lines
            rows.append('[EXECUTION RESULT]')
            if isinstance(result, dict):
                readback = result.get('readback') if isinstance(result.get('readback'), dict) else {}
                error = result.get('error') if isinstance(result.get('error'), dict) else {}
                field('Operation', result.get('operation_id', 'unknown'))
                if 'status' not in result and isinstance(result.get('journal_status'), str):
                    # Reconcile reports the journal status it left and the one it found.
                    field('Journal', '%s (was %s)' % (str(result['journal_status']).replace('_', ' '),
                                                      str(result.get('previous_status', 'not recorded')).replace('_', ' ')))
                else:
                    field('Status', str(result.get('status', 'unknown')).replace('_', ' '))
                rows.extend(execution_effect_lines(result, width))
                # Execute nests its independent readback; reconcile returns its own at the top level.
                reconciled = 'status' not in result and isinstance(result.get('journal_status'), str)
                field("Reconcile's readback" if reconciled else 'Readback',
                      str(result.get('classification') or readback.get('classification') or 'not recorded').replace('_', ' '))
                from .workbench_screens import EXECUTION_ERROR_WORDS
                if reconciled:
                    # Reconcile's own run has no error here; the error is the one the operation recorded before it.
                    code = result.get('previous_error_code')
                    field('Recorded before reconcile', '%s (%s)' % (EXECUTION_ERROR_WORDS[code], code)
                          if code in EXECUTION_ERROR_WORDS else code or 'no error')
                else:
                    code = result.get('error_code') or error.get('code')
                    field('Error', '%s (%s)' % (EXECUTION_ERROR_WORDS[code], code) if code in EXECUTION_ERROR_WORDS
                          else code or 'none recorded')
                field('Evidence', str(result.get('evidence_class', 'unknown')).replace('_', ' '))
            # The lifecycle line below gives the next step for this state; v shows every delivery stage.
        elif self.tab == 6 and ('collection_health' in value or isinstance(value.get('stages'), dict)):
            from .workbench_screens import health_lines
            # A single-policy health result carries no name; use the one already read for that exact identity.
            rows.extend(health_lines(value, width, self.facts.get('name') if value.get('object_id') == self.selected else None))
        elif self.tab == 6 and value.get('schema_version') == 'workbench-diagnostics/1':
            from .workbench_screens import diagnostics_lines
            facts = self.facts if self.facts.get('object_id') == value.get('object_id') else {}
            rows.extend(diagnostics_lines(value, width, check=facts.get('eligibility')))
        elif self.tab == 6 and isinstance(value.get('findings'), list):
            from .workbench_screens import queue_lines
            rows.extend(queue_lines(value, width))
        elif self.tab == 6 and value.get('schema_version') == 'workbench-four-views/1':
            rows.append('[REPOSITORY / OBSERVED / PROPOSED / COVERAGE]')
            # Each line a statement: what is recorded, qualified or fresh, never a bare yes or no (item 28).
            for label, key in (('Repository intent', 'repository'), ('Observation', 'observed'), ('Proposal', 'proposed')):
                facet = value.get(key, {})
                field(label, str(facet.get('status', 'unknown')).replace('_', ' ') if isinstance(facet, dict) else 'unknown')
            coverage = value.get('coverage', {})
            if isinstance(coverage, dict):
                for label, key in (('Observation coverage', 'observation'), ('Management', 'management'),
                                   ('State tracked', 'state_tracked'), ('Mapping', 'mapping')):
                    item = coverage.get(key, 'unknown')
                    field(label, item.replace('_', ' ') if isinstance(item, str) else item)
                said = lambda item, yes, no, unknown: yes if item is True else no if item is False else unknown
                field('Platform qualification', said(coverage.get('platform_qualified'), 'qualified', 'not qualified',
                                                     'not recorded'))
                own = coverage.get('ownership', {})
                if isinstance(own, dict):
                    field('Ownership', '%s; %s' % (
                        said(own.get('declared_scope_complete'), 'declared scope complete', 'declared scope not complete',
                             'declared scope not recorded'),
                        said(own.get('fresh'), 'ownership index fresh', 'ownership index not fresh',
                             'ownership index freshness not recorded')))
            repository = value.get('repository', {})
            if isinstance(repository, dict) and isinstance(repository.get('freshness'), dict):
                field('Repository freshness', repository['freshness'].get('status', 'unknown'))
            rows.append('[DISTINCT COMPARISON BASELINES]')
            from .workbench_screens import baseline_words
            for label, comparison in value.get('comparisons', {}).items():
                if isinstance(comparison, dict):
                    field(str(label).replace('_', ' ').capitalize(), str(comparison.get('status', 'unknown')).replace('_', ' '))
                    field('  Baseline', baseline_words(comparison.get('baseline', comparison.get('reason'))))
            versus = value.get('comparisons', {}).get('repository_vs_observed')
            if isinstance(versus, dict) and isinstance(versus.get('field_changes'), dict):
                from .workbench_screens import change_lines
                rows.append('[REPOSITORY VERSUS OBSERVED]')
                rows.extend(change_lines(versus['field_changes'], width, 'BEFORE (observed)', 'AFTER (repository)'))
        elif self.tab == 8 and value.get('schema_version') == 'workbench-repository-status/1':
            from .workbench_screens import repository_lines
            rows.append('[REPOSITORY STATUS]')
            rows.extend(repository_lines(value, width))
        elif self.tab == 8 and value.get('kind') == 'repository_intent' and isinstance(value.get('data'), dict):
            from .workbench_screens import refresh_result_lines
            rows.extend(refresh_result_lines(value, width))
        elif self.tab == 7 and isinstance(value.get('navigation'), list):
            from .workbench_screens import help_lines
            rows.extend(help_lines(width))
        if rows: rows.append('')
        return rows

    def _data_lines(self, width):
        """The body in one column: the summary by default, or the typed details or the raw record when asked."""
        from .workbench_screens import details_lines, word_wrap
        layer = getattr(self, 'layer', 'summary')
        if layer == 'details':
            return (word_wrap('TYPED DETAILS  Every field of this result, names spaced for reading; r shows the raw record '
                              'exactly as recorded, Esc returns to the summary.', width) + [''] + details_lines(self.value, width))
        if layer == 'actions':
            from .workbench_screens import actions_lines
            facts = self.facts if self.selected and getattr(self, 'facts', {}).get('object_id') == self.selected else {}
            return actions_lines(self._actions(), getattr(self, 'action_focus', 0), width, facts.get('name'), self.selected,
                                 submit=self._submit_word(), prefixes=facts.get('identity_prefixes'))
        if layer == 'filters':
            from .workbench_screens import filter_lines
            return filter_lines(filter_choices(), getattr(self, 'filter_focus', 0),
                                page_filters(getattr(self, 'page_command', ''))[1], width)
        if layer == 'raw':
            return (word_wrap('RAW RECORD  The complete engine result exactly as returned, %d lines of JSON; Esc returns to the summary.'
                              % self._raw_count(), width) + [''] + self._detail_lines(width))
        return self._summary_lines(width) + [self._evidence_line(width)]

    def _evidence_line(self, width):
        """One line naming the two evidence layers; for a plan, also what they hold beyond the summary."""
        count = self._raw_count()
        within = ' (before, desired, targeting and risks)' if self.tab == 4 and self.value.get('operation_id') else ''
        forms = ('Evidence%s: e typed details | r complete raw record (%d lines)' % (within, count),
                 'Evidence: e typed details | r complete raw record (%d lines)' % count,
                 'Evidence: e details | r raw (%d lines)' % count)
        return next((form for form in forms if cell_width(form) <= width), forms[-1])

    def _raw_count(self):
        """Lines of the raw record before wrapping, so the count does not change with the terminal width."""
        # The cache holds the value itself: an id() key could match a later value that reused a freed address.
        cached = getattr(self, '_raw_count_cache', None)
        if cached is None or cached[0] is not self.value:
            cached = (self.value, len(json.dumps(self.value, ensure_ascii=False, indent=2, allow_nan=False).splitlines()))
            self._raw_count_cache = cached
        return cached[1]

    def _body_lines(self, inner, side):
        """The body as drawn. From WIDE cells, typed details or the raw record open beside the summary."""
        if inner < WIDE or getattr(self, 'layer', 'summary') == 'summary':
            return self._data_lines(inner)
        left = (inner - 3) * 11 // 20
        right = inner - 3 - left
        summary, evidence = self._summary_lines(left), self._data_lines(right)
        return [pad(summary[index] if index < len(summary) else '', left) + ' ' + side + ' ' + (evidence[index] if index < len(evidence) else '')
                for index in range(max(len(summary), len(evidence)))]

    def _summary_lines(self, width):
        if self.tab == 0 and self.rows and isinstance(self.value.get('objects'), list):
            # Short lines first, so the marker key stays on one line down to narrow terminals.
            lines = (list(wrap('[SELECT] Exact identity / name / ownership / coverage / health', width))
                     + list(wrap('> focus, * pinned selection | Settings Catalog policies; :families shows every family '
                                 'with its support disposition.', width)))
            if 'modeled_service' in self.value:
                from .workbench_screens import service_words
                lines.extend(wrap(service_words(self.value.get('modeled_service')), width))
            if isinstance(self.value.get('filters'), dict):
                from .workbench_screens import filter_words
                lines.extend(wrap(filter_words(self.value['filters']), width))
                page = self.value.get('pagination', {})
                lines.extend(wrap('Matching objects: %s / inventory: %s | page offset: %s' %
                    (page.get('total_objects', 'unknown'), self.value.get('total_inventory_objects', 'unknown'), page.get('offset', 'unknown')), width))
            for index, row in enumerate(self.rows):
                # Temporary keyboard focus and the pinned selection other surfaces show stay distinguishable.
                mark = ('>' if index == self.highlight else ' ') + ('*' if row['object_id'] == self.selected else ' ')
                lines.extend(wrap('%s %s' % (mark, row['object_id']), width))
                coverage = row.get('coverage', 'unknown')
                owner = coverage.get('management', 'unknown') if isinstance(coverage, dict) else row.get('ownership', 'unknown')
                coverage = coverage.get('observation', 'unknown') if isinstance(coverage, dict) else coverage
                health = row.get('health', {})
                lines.extend(wrap('  %s | owner=%s | coverage=%s | health=%s | freshness=%s' %
                                  (row.get('name', 'unknown'), owner, coverage,
                                   health.get('status', 'unknown') if isinstance(health, dict) else 'unknown', row.get('freshness', 'unknown')), width))
                if row.get('pending_observation'):
                    lines.extend(wrap('  [PENDING OBSERVATION] ' + str(row.get('last_attempt', {}).get('status', 'unknown')) +
                                      '; select for literal evidence and mapping limitations.', width))
        elif self.tab in (4, 5) and isinstance(self.value.get('operations'), list) and not self.value['operations']:
            # An empty list says so, rather than a frame with nothing in it (journey 27 review, Sonnet 8).
            lines = ['[OPERATIONS] None recorded in this store yet.'] + list(wrap(
                'Prepare a proposal (a: actions); its operation appears here.', width))
        elif self.tab in (4, 5) and self.operation_rows and isinstance(self.value.get('operations'), list):
            lines = ['[OPERATIONS] Enter reviews exact current plan; no approval or execution.']
            for index, row in enumerate(self.operation_rows):
                mark = '>' if index == self.operation_highlight else ' '
                from .workbench_screens import _when
                count = row.get('journal_records')
                lines.extend(wrap('%s %s | recorded %s | %s%s' %
                                  (mark, row.get('operation_id'), _when(row.get('recorded_at'), 'unknown'),
                                   str(row.get('status', 'status unknown')).replace('_', ' '),
                                   ' (%d journal records)' % count if isinstance(count, int) and count > 1 else ''), width))
                lines.extend(wrap('  ' + row['operation_root'], width))
            lines.append('Enter reviews the highlighted plan as it is now; nothing is approved.')
        else:
            lines = self._surface_summary(width)
            if self._on_change_path(self.value):
                from .workbench_screens import lifecycle_lines
                lines = lines + [''] + lifecycle_lines(self.tab, width, self.value, eligibility=self.facts.get('eligibility')
                                                       if self.facts.get('object_id') == self.selected else None)
        return lines

    def _on_change_path(self, value):
        """Whether the result shown is a step of a change: a repository status, a plan review, an execution result."""
        if not isinstance(value, dict) or value.get('status') == 'error':
            return False
        if self.tab == 8:
            return value.get('schema_version') == 'workbench-repository-status/1'
        if self.tab == 4:
            return bool(value.get('operation_id'))
        if self.tab == 5:
            # Delivery shows every stage with its own next step; it needs no line pointing back at itself.
            if value.get('schema_version') == 'workbench-delivery/1':
                return False
            return bool(value.get('operation_id')) or 'result' in value
        return False

    def _detail_lines(self, width):
        """The exact engine record wrapped to `width`, cached per value and width."""
        cached = self._detail_cache
        if cached is not None and cached[0] is self.value and cached[1] == width:
            return cached[2]
        detail = []
        for line in json.dumps(self.value, ensure_ascii=False, indent=2, allow_nan=False).splitlines():
            detail.extend(wrap(line, width))
            if len(detail) > MAX_RENDER_LINES:
                # Data remains in the complete text interface. This boundary is
                # explicit rather than silent truncation or false completeness.
                detail = detail[:MAX_RENDER_LINES]
                detail.append('[VIEW LIMIT] The record continues past %d lines here; the text interface '
                              '(intune-iac workbench terminal) prints it complete.' % MAX_RENDER_LINES)
                break
        self._detail_cache = (self.value, width, detail)
        return detail

    def draw(self):
        self.size = self._terminal_size()
        width, height = self.size
        if width < MIN_SIZE[0] or height < MIN_SIZE[1]:
            return self._draw_constrained(width, height)
        inner = width - 2
        from .workbench_screens import hazard_rows, tab_line
        header = title_line(TABS[self.tab], getattr(self, 'last_command', ''), self.value, getattr(self, 'layer', 'summary'))
        labels = tab_line(TABS, self.tab, width)
        # The primary hazard is chrome, not body: layers, scrolling and narrow windows never move it out of view.
        selected = getattr(self, 'selected', None)
        known = self.facts if selected and getattr(self, 'facts', {}).get('object_id') == selected else {}
        # While a command is typed the band's keys are typed, not obeyed: it names the response without them.
        band = hazard_rows(known, known.get('signals') or [], width, routes=not self.mode,
                           here=self.tab == 1) if selected else []
        staged = getattr(self, 'staged', None) if self.mode == 'command' else None
        staged_rows = None
        if isinstance(staged, dict) and staged.get('boundary'):
            # A staged action's boundary and its mechanics each get a row, each in the longest complete form that fits.
            pick = lambda forms: next((form for form in forms if cell_width(form) <= width), forms[-1])
            staged_rows = [pick(staged['boundary']), pick(staged.get('mechanics') or ('',))]
        available = max(0, height - 8 - len(band) - (1 if staged_rows else 0))
        # One column of space inside each border: text never touches the frame (journey 27 review, Sonnet 23).
        content = inner - 2
        data = self._body_lines(content, RULES[getattr(self, 'rules', 'ascii')][1])
        # A row wider than the frame is wrapped at a space, never clipped mid-word (journey 27 frame 11).
        from .workbench_screens import word_wrap
        data = [part for line in data for part in (word_wrap(line, content) if cell_width(line) > content else [line])]
        self.scroll = max(0, min(self.scroll, max(0, len(data) - available)))
        visible = data[self.scroll:self.scroll + available]
        status = self._context_strip(width)
        ellipsis = '…' if getattr(self, 'rules', 'ascii') == 'unicode' else '...'
        # A view without its own evidence class shows the selected policy's, never a bare "unknown".
        facts = getattr(self, 'facts', {}) if getattr(self, 'selected', None) else {}
        scope = self._scope(facts)
        from .workbench_screens import mode_word
        footer = status_line(str(scope), min(self.scroll + 1, len(data)), min(self.scroll + available, len(data)), len(data),
                             width, ellipsis, short=mode_word(scope) if scope in MODE_CLASSES else None)
        if staged_rows:
            footer = fit(staged_rows[0], width, ellipsis)
        elif self.mode == 'command' and getattr(self, 'staged', None):
            # While a staged action's command is edited, its instruction stays on the row above the command bar.
            footer = fit(self.notice, width, ellipsis)
        prompt = self._prompt_line(width, ellipsis)
        top, side, bottom = RULES[getattr(self, 'rules', 'ascii')]
        # Content beyond the frame is announced inside the border, not only by the row counter below it.
        frame = [pad(header, width), pad(labels, width), pad(status, width)] + [pad(row, width) for row in band] + [
                 ruled(top[0], top[1], top[2], inner, ' more above: PgUp ' if self.scroll > 0 else None)]
        band_rows = set(range(3, 3 + len(band)))
        frame.extend(side + ' ' + pad(line, content) + ' ' + side for line in visible)
        frame.extend(side + ' ' * inner + side for _ in range(available - len(visible)))
        frame.extend([ruled(bottom[0], bottom[1], bottom[2], inner,
                            ' more below: PgDn ' if self.scroll + available < len(data) else None),
                      pad(footer, width)] + ([pad(fit(staged_rows[1], width, ellipsis), width)] if staged_rows else []) + [
                      pad(prompt, width),
                      pad(typing_line(width, self.mode, self._submit_word()) if self.mode else
                          help_line(width, getattr(self, 'layer', 'summary'), band_keys(band)), width)])
        if self.color:
            palette = THEMES.get(self.theme, THEMES['dark'])
            painted = []
            for i, line in enumerate(frame):
                if i in band_rows:
                    # The hazard band is bold in the warning colour; its words carry the meaning on their own.
                    painted.append('\x1b[48;5;%s;38;5;%sm\x1b[1m%s\x1b[22m\x1b[0m' % (palette['bg'], palette['warn'], line))
                    continue
                base = palette['accent'] if i in (0, 1, len(frame) - 2) else palette['fg']
                # Body lines, the context strip and the notice get word-level reinforcement; words never change.
                if line.startswith(side) or i in (2, len(frame) - 2):
                    line = paint(line, palette, base)
                painted.append('\x1b[48;5;%s;38;5;%sm%s\x1b[0m' % (palette['bg'], base, line))
        else: painted = ['\x1b[1m' + line + '\x1b[22m' if i in band_rows else emphasize(line) if line.startswith(side) else line
                         for i, line in enumerate(frame)]
        self.stdout.write('\x1b[H' + '\r\n'.join(painted) + '\x1b[J')
        self.stdout.flush()

    def _scope(self, facts):
        """The evidence class for the status row: the result's own, else the selected policy's; an estate page
        (a search or a filter of the estate) has the estate's class, learned from its observations (item 26)."""
        value = self.value if isinstance(self.value, dict) else {}
        estate = self.tab == 0 and isinstance(value.get('objects'), list) and getattr(self, 'mode_class', None)
        return value.get('evidence_class') or facts.get('evidence_class') or estate or 'evidence class not stated'

    def _prompt_line(self, width, ellipsis):
        """The command bar with its cursor while a command is typed, otherwise the notice.

        A command longer than the bar keeps its verb in view and marks each cut with an ellipsis, so the command
        Enter will submit is always named (journey 27 review, Sonnet 1 and 9)."""
        if not self.mode:
            return fit(self.notice, width, ellipsis)
        prefix = '/' if self.mode == 'search' else ':'
        before, after = safe_text(self.buffer[:self.cursor]), safe_text(self.buffer[self.cursor:])
        room, mark = max(1, width - cell_width(prefix) - 1), cell_width(ellipsis)
        if cell_width(before) + cell_width(after) <= room:
            return prefix + before + '|' + after

        def cut_after(budget):
            return after if cell_width(after) <= budget else _cells_from_start(after, max(0, budget - mark)) + ellipsis

        if cell_width(before) + min(cell_width(after), room // 3) <= room:
            # What precedes the cursor fits whole: only what follows it is cut, at the right.
            return prefix + before + '|' + cut_after(room - cell_width(before))
        shown_after = cut_after(min(cell_width(after), room // 3))
        budget = room - cell_width(shown_after)
        verb = before.split(' ', 1)[0] + ' ' if ' ' in before else ''
        head = verb + ellipsis if verb and cell_width(verb) + mark <= budget // 2 else ellipsis
        rest = before[len(verb):] if head != ellipsis else before
        return prefix + head + _cells_from_end(rest, max(0, budget - cell_width(head))) + '|' + shown_after

    def _draw_constrained_prompt(self, width, ellipsis):
        """The prompt row below the minimum: a view's name says the surface is hidden, never that it is shown."""
        notice = str(getattr(self, 'notice', ''))
        if not self.mode and notice.startswith('Viewing '):
            return fit(notice[len('Viewing '):].rstrip('.') + ' hidden; enlarge to see it', width, ellipsis)
        return self._prompt_line(width, ellipsis)

    def _draw_constrained(self, width, height):
        """Below MIN_SIZE: what the window is too small for, the session, the primary hazard and the prompt, by
        priority, never the body. Keys keep their meaning; the full frame returns when the window is large enough."""
        from .workbench_screens import constrained_rows
        ellipsis = '…' if getattr(self, 'rules', 'ascii') == 'unicode' else '...'
        selected = getattr(self, 'selected', None)
        known = self.facts if selected and getattr(self, 'facts', {}).get('object_id') == selected else {}
        lines, band_rows = constrained_rows(self.store.tenant_id, selected, known, getattr(self, 'mode_class', None), width,
                                            height, '%dx%d' % MIN_SIZE, self._draw_constrained_prompt(width, ellipsis),
                                            typing=bool(self.mode))
        frame = [pad(safe_text(line), width) for line in lines] + [' ' * width] * (height - len(lines))
        if self.color:
            palette = THEMES.get(self.theme, THEMES['dark'])
            painted = ['\x1b[48;5;%s;38;5;%sm%s%s\x1b[0m' % (palette['bg'], palette['warn'] if i in band_rows else palette['fg'],
                                                       '\x1b[1m' if i in band_rows else '', line) for i, line in enumerate(frame)]
        else:
            painted = ['\x1b[1m' + line + '\x1b[22m' if i in band_rows else line for i, line in enumerate(frame)]
        self.stdout.write('\x1b[H' + '\r\n'.join(painted) + '\x1b[J')
        self.stdout.flush()

    def _known_cause(self, code):
        """The cause the last read of this policy recorded, for a refusal code that covers several; else None."""
        facts = getattr(self, 'facts', None) or {}
        if not self.selected or facts.get('object_id') != self.selected:
            return None
        signals = [signal for signal in facts.get('signals') or [] if isinstance(signal, dict) and signal.get('observed')]
        kinds = {'repository_stale': 'repository_changed', 'repository_consumer_mismatch': 'consumer_changed',
                 'observation_stale': 'observation_stale', 'collection_failed': 'collection_failed',
                 'collection_not_finished': 'collection_not_finished'}
        if code in ('workbench_repository_stale', 'maintenance_repository_stale'):
            found = [signal for signal in signals if signal.get('code') in ('repository_stale', 'repository_consumer_mismatch')]
            return (str(found[0]['observed']), kinds[found[0]['code']]) if found else None
        if code in ('maintenance_observation_stale', 'maintenance_observation_incomplete',
                    'maintenance_observation_source_mismatch'):
            from .workbench_screens import ELIGIBILITY_FINDINGS
            eligibility = facts.get('eligibility') if isinstance(facts.get('eligibility'), dict) else {}
            if eligibility.get('code') == code and eligibility.get('reason') in ELIGIBILITY_FINDINGS:
                return ELIGIBILITY_FINDINGS[eligibility['reason']][0] % eligibility, eligibility['reason']
            found = [signal for signal in signals
                     if signal.get('code') in ('observation_stale', 'collection_failed', 'collection_not_finished')]
            return (str(found[0]['observed']), kinds[found[0]['code']]) if found else None
        return None

    def _states_here(self, value):
        """Whether this surface shows the selected policy's states: the Repository status and the Plan review."""
        facts = getattr(self, 'facts', None) or {}
        if not self.selected or facts.get('object_id') != self.selected or not isinstance(facts.get('states'), dict):
            return False
        if value.get('status') == 'error':
            return False
        return ((self.tab == 8 and value.get('schema_version') == 'workbench-repository-status/1')
                or (self.tab == 4 and bool(value.get('operation_id')) and value.get('object_id') in (None, self.selected)))

    def _overview_policies(self):
        """Policies listed by the estate overview on the Estate surface; empty elsewhere."""
        value = self.value if isinstance(self.value, dict) else {}
        if self.tab != 0 or value.get('schema_version') != 'workbench-estate-overview/1':
            return []
        return [item for item in value.get('policies') or [] if isinstance(item, dict) and item.get('object_id')]

    def _entry_candidates(self):
        """Policies of a repository survey shown on the Repository surface; empty elsewhere."""
        value = self.value if isinstance(self.value, dict) else {}
        if self.tab != 8 or value.get('schema_version') != 'workbench-repository-entry/1':
            return []
        return [item for item in value.get('candidates') or [] if isinstance(item, dict)]

    def _actions(self):
        """The guided actions the read model offered for the selected policy, as last reported."""
        facts = self.facts if self.selected and getattr(self, 'facts', {}).get('object_id') == self.selected else {}
        return [action for action in facts.get('actions') or [] if isinstance(action, dict)]

    def _read_actions(self):
        """a: read this policy's actions again through the engine, then list them over the current screen."""
        if not self.selected:
            self.notice = 'Select a policy first: 1 (Estate), then Enter.'
            return None
        self.quiet = {'purpose': 'actions', 'state': 'sent'}
        self.notice = 'READING: the actions for this policy; nothing runs until you submit one.'
        self.draw()
        return 'inspect'

    def _quiet_receive(self, value, purpose):
        """A read made for the band and the actions only; the screen keeps the result it was showing."""
        if value.get('status') == 'error' or value.get('object_id') != self.selected:
            # The conditions stay, marked as not re-read: dropping them would silently remove a warning. The actions
            # are dropped; a reads them again before listing any.
            facts = dict(self.facts)
            facts.pop('actions', None)
            command = self.last_command.split(' ', 1)[0] if isinstance(self.last_command, str) and self.last_command else ''
            facts['unverified'] = command or 'the last command'
            self.facts = facts
            if purpose == 'actions':
                self.notice = 'The actions could not be read again; 2 (Inspector) shows why.'
            else:
                self.notice = ('%s The conditions could not be read again after %s; 2 (Inspector) shows why.'
                               % (self.notice.rstrip(), facts['unverified'])).strip()
        else:
            self._learn(value)
            if purpose == 'actions':
                self._open_actions()
        self.draw()

    def _open_actions(self):
        if not self.selected:
            self.notice = 'Select a policy first: 1 (Estate), then Enter.'
        elif not self._actions():
            self.notice = 'No actions read for this policy yet; 2 (Inspector) reads them.'
        else:
            self.layer = 'actions'; self.scroll = 0; self.action_focus = 0
            self.notice = 'Up and Down choose; Enter stages the command for review.'

    def _stage(self, action):
        """Put an available action's exact command in the command bar, bound to this policy; nothing is sent.

        An action that must show something first (the source difference of a refresh) sends that view and is staged
        when it arrives, bound to what was shown; the returned command is that view.
        """
        if not action.get('available'):
            blocked = action.get('blocked') or {}
            self.notice = 'Blocked: %s. Nothing was staged.' % (blocked.get('message') or blocked.get('code') or 'not available')
            return None
        if action.get('show_first') == 'repository-status':
            self.pending_stage = dict(action)
            return self._send('repository-status')
        command = str(action.get('command') or '')[:MAX_COMMAND]
        cursor = action.get('cursor')
        self.mode = 'command'; self.buffer = command
        self.cursor = cursor if isinstance(cursor, int) and 0 <= cursor <= len(command) else len(command)
        self.staged = {'kind': action.get('kind'), 'label': action.get('label'), 'binding': dict(action.get('binding') or {}),
                       'boundary': self._boundary(action), 'mechanics': self._mechanics(action, bound=False)}
        self.notice = self._staged_notice()
        return None

    def _boundary(self, action):
        kind = action.get('kind')
        return STAGED_BOUNDARY.get(kind) or ('STAGED %s.' % (action.get('label') or kind),)

    def _mechanics(self, action, *, bound):
        """What to type and how to submit or cancel, longest form first; the last fits 40 columns."""
        submit = self._submit_word()
        needs = [str(need).split(':')[0] for need in action.get('needs') or []]
        if bound:
            return ('Type REVISION (the full 40-character commit ID) at the cursor; the digest after it pins the difference '
                    'you reviewed. %s attempts to record it; Esc cancels.' % submit,
                    'Type REVISION at the cursor; the digest after it pins the reviewed difference. %s submits; Esc '
                    'cancels.' % submit,
                    'Type REVISION. %s attempts to record this reviewed source; Esc cancels.' % submit,
                    'REVISION, then %s; Esc cancels.' % submit)
        if needs:
            names = ' and '.join(needs)
            return ('Type %s at the cursor. %s submits the command; Esc cancels.' % (names, submit),
                    'Type %s; %s submits; Esc cancels.' % (names, submit), '%s, then %s; Esc cancels.' % (names, submit))
        return ('%s submits the command below; Esc cancels.' % submit, '%s submits; Esc cancels.' % submit)

    def _staged_notice(self):
        staged = self.staged or {}
        boundary, mechanics = staged.get('boundary') or ('',), staged.get('mechanics') or ('',)
        return (boundary[min(1, len(boundary) - 1)] + ' ' + mechanics[min(1, len(mechanics) - 1)]).strip()

    def _stage_after_difference(self, action, value):
        """Stage a refresh once its difference is on screen, bound to that difference's resolution digest."""
        freshness = value.get('freshness') if isinstance(value.get('freshness'), dict) else {}
        shown = freshness.get('resolution_sha256')
        if value.get('status') == 'error' or value.get('object_id') not in (None, self.selected):
            self.notice = 'The difference could not be shown, so nothing was staged.'
            return
        if freshness.get('status') != 'stale' or not isinstance(shown, str):
            self.notice = ('The repository matches its recorded intent now; there is nothing new to record.'
                           if freshness.get('status') == 'current' else 'The difference could not be shown, so nothing was staged.')
            return
        command = (str(action.get('command') or '').rstrip() + '  ' + shown)[:MAX_COMMAND]
        cursor = action.get('cursor')
        self.mode = 'command'; self.buffer = command
        self.cursor = cursor if isinstance(cursor, int) and 0 <= cursor <= len(command) else len(command)
        self.staged = {'kind': action.get('kind'), 'label': action.get('label'),
                       'binding': dict(action.get('binding') or {}, resolution_sha256=shown),
                       'boundary': self._boundary(action), 'mechanics': self._mechanics(action, bound=True)}
        self.notice = self._staged_notice()

    def _submit_word(self):
        return 'Enter' if getattr(self, 'submission_key', 'enter') == 'enter' else 'Ctrl+Enter'

    def _back(self):
        """The previous read-only view of this session, or a notice that there is none; never a change."""
        if getattr(self, 'trail', []):
            tab, command = self.trail[-1]
            self.trail = self.trail[:-1]
            self.tab = tab
            return self._send(command, returning=True)
        self.notice = 'Nothing to go back to in this session.'
        self.draw()
        return None

    def _send(self, command, *, returning=False):
        try: name = shlex.split(command)[0]
        except (ValueError, IndexError): name = ''
        self.layer = 'summary'
        current = getattr(self, 'current_view', None)
        # A view is kept for b; so is the view shown before a command that is not a view, whose own result
        # is never re-sent. returning marks b itself, which must not push the view it leaves.
        if current is not None and not returning and current[1] != command:
            self.trail = (getattr(self, 'trail', []) + [current])[-50:]
        self.current_view = None
        tabs = {'overview': 0, 'search': 0, 'search-page': 0, 'views-page': 0, 'select': 1, 'inspect': 1, 'settings': 1,
                'relationships': 2, 'lineage': 2, 'history': 3, 'history-recent': 3, 'evidence-history': 3, 'compare': 3, 'review': 4,
                'propose': 4, 'execute': 5, 'reconcile': 5, 'restore-propose': 4, 'views': 6, 'help': 7,
                'repository-status': 8, 'repository-refresh': 8, 'propose-from-intent': 4, 'dictionary': 1, 'dictionary-page': 1,
                'health': 6, 'queue': 6, 'delivery': 5, 'start': 7, 'diagnostics': 6, 'families': 7,
                'repository-entry': 8, 'estate-overview': 0, 'service-review': 4, 'service-status': 5, 'service-attach': 5,
                'service-cancel': 5, 'service-recover': 5, 'adoption-review': 4,
                'adoption-status': 5, 'adoption-attach': 5, 'adoption-cancel': 5, 'adoption-recover': 5,
                'adoption-history': 3, 'adoption-link': 3, 'adoption-plan-review': 4,
                'adoption-plan-status': 5, 'adoption-plan-attach': 5, 'adoption-plan-cancel': 5, 'adoption-plan-recover': 5}
        if name in tabs: self.tab = tabs[name]
        self.last_command = command
        if name in VIEW_COMMANDS:
            self.current_view = (self.tab, command)
        self.scroll = 0
        self.mode = None
        self.buffer = ''
        self.cursor = 0
        self.input_overflow = False
        self.notice = running_notice(command)
        self.draw()
        return command

    def _tab_command(self, tab):
        self.tab = tab
        command = TAB_COMMANDS[tab]
        if tab in (4, 5) and self.active_adoption_plan is not None:
            return self._send(_adoption_plan_command('review' if tab == 4 else 'attach', self.active_adoption_plan))
        if tab in (4, 5) and self.active_adoption is not None:
            return self._send(_adoption_command('review' if tab == 4 else 'attach', self.active_adoption))
        if tab in (4, 5) and self.active_service is not None:
            return self._send(_service_command('review' if tab == 4 else 'attach', self.active_service))
        if tab == 4 and self.active_operation:
            return self._send('review ' + shlex.quote(self.active_operation))
        if tab == 5 and self.execution_result is not None:
            # Shown without the engine; b returns to the view before it, like any other result that is not a view.
            current = getattr(self, 'current_view', None)
            if current is not None:
                self.trail = (getattr(self, 'trail', []) + [current])[-50:]
            self.current_view = None
            self.layer = 'summary'
            self.value = {'display_scope': 'last engine result in this interface; refresh durable operations for later activity',
                          'operation_root': self.active_operation, 'result': self.execution_result,
                          'recovery': 'Use :reconcile OPERATION_DIR for explicit independent readback; never blindly replay execution.'}
            self.scroll = 0
            self.notice = 'LAST RESULT: no action dispatched. :operations refreshes durable receipts.'
            self.save_context(); self.draw()
            return None
        if tab == 6 and self.active_operation and self.selected is not None:
            return self._send('views ' + shlex.quote(self.active_operation))
        if command in ('inspect', 'relationships', 'history', 'history-recent', 'evidence-history', 'views', 'repository-status') and self.selected is None:
            self.notice = 'Select an exact identity from Estate first.'
            self.draw()
            return None
        return self._send(command)

    def input(self, _prompt):
        if self.pending:
            return self._send(self.pending.popleft())
        if getattr(self, 'quiet', None) and self.quiet.get('state') == 'due':
            if not self.selected:
                self.quiet = None
            else:
                self.quiet = dict(self.quiet, state='sent')
                return 'inspect'
        if self.key_reader is None:
            self.key_reader = self.native_binding.console.key_reader if self.native_binding is not None else KeyReader(self.stdin)
        self.draw()
        while True:
            key = self.key_reader.read()
            if key is None:
                if self._terminal_size() != self.size: self.draw()
                continue
            if key in ('interrupt', 'eof'):
                if key == 'interrupt': raise KeyboardInterrupt
                if self.mode and self.buffer: self.notice = 'Use Escape to discard the unsubmitted edit.'; self.draw(); continue
                raise EOFError
            if key == 'paste_start':
                self.pasting = True
                if self.mode is None: self.mode = 'command'; self.buffer = ''; self.cursor = 0
                continue
            if key == 'paste_end': self.pasting = False; self.draw(); continue
            if self.pasting:
                text = key[1] if isinstance(key, tuple) else ' ' if key in ('enter', 'tab') else ''
                if len(self.buffer) + len(text) <= MAX_COMMAND:
                    self.buffer = self.buffer[:self.cursor] + text + self.buffer[self.cursor:]; self.cursor += len(text)
                else:
                    self.input_overflow = True
                    self.notice = 'INPUT REJECTED: limit reached; Escape or Ctrl-U must discard this edit.'
                continue
            if self.mode:
                if key == 'escape':
                    self.mode = None; self.buffer = ''; self.cursor = 0; self.input_overflow = False; self.staged = None
                    self.notice = 'EDIT CANCELLED: nothing was submitted, and nothing already running was stopped.'
                elif key == 'enter' and self.submission_key != 'enter':
                    self.notice = 'Ctrl+Enter submits this edit; ordinary Enter does not submit pasted input.'
                elif key == self.submission_key:
                    if self.input_overflow:
                        self.mode = None; self.buffer = ''; self.cursor = 0; self.input_overflow = False
                        self.notice = 'INPUT REJECTED: oversized edit discarded; no command submitted.'
                        self.draw()
                        continue
                    command = self.buffer
                    if self.mode == 'search':
                        if self.page_command.startswith('views-page '):
                            parts = shlex.split(self.page_command)
                            parts[2] = '0'; parts[3] = command or '-'
                            command = ' '.join(shlex.quote(part) for part in parts)
                        else: command = 'search ' + shlex.quote(command)
                    if self.mode == 'command' and command.strip() in ('back', 'cancel'):
                        # In the workspace these words mean what they say: back is b; between commands there is
                        # nothing running to cancel. The text interface keeps its own meaning for both.
                        self.mode = None; self.buffer = ''; self.cursor = 0
                        if command.strip() == 'back':
                            sent = self._back()
                            if sent is not None: return sent
                            continue
                        self.notice = CANCEL_NOTICE
                        self.draw()
                        continue
                    staged, self.staged = getattr(self, 'staged', None), None
                    bound = (staged or {}).get('binding') or {}
                    mode_now = (getattr(self, 'facts', None) or {}).get('evidence_class')
                    moved = bool(staged) and (bound.get('object_id') != self.selected or bound.get('tenant_id') != self.store.tenant_id)
                    remoded = bool(staged and bound.get('evidence_class') and mode_now and bound['evidence_class'] != mode_now)
                    if staged and self.mode == 'command' and (moved or remoded):
                        # A staged action is bound to the policy, tenant and evidence mode it was offered for.
                        self.mode = None; self.buffer = ''; self.cursor = 0
                        self.notice = (('The staged action was for policy %s; the selection changed since, so it was '
                                        'discarded. Nothing was sent.' % str(bound.get('object_id'))[:8]) if moved else
                                       ('The staged action was read from %s evidence; the evidence mode changed since, so '
                                        'it was discarded. Nothing was sent.' % bound.get('evidence_class')))
                        self.draw()
                        continue
                    if command.strip(): return self._send(command)
                    self.mode = None
                elif key == 'backspace' and self.cursor:
                    self.buffer = self.buffer[:self.cursor - 1] + self.buffer[self.cursor:]; self.cursor -= 1
                elif key == 'delete': self.buffer = self.buffer[:self.cursor] + self.buffer[self.cursor + 1:]
                elif key == 'clear': self.buffer = ''; self.cursor = 0; self.input_overflow = False
                elif key == 'left': self.cursor = max(0, self.cursor - 1)
                elif key == 'right': self.cursor = min(len(self.buffer), self.cursor + 1)
                elif key == 'home': self.cursor = 0
                elif key == 'end': self.cursor = len(self.buffer)
                elif isinstance(key, tuple):
                    if len(self.buffer) < MAX_COMMAND:
                        self.buffer = self.buffer[:self.cursor] + key[1] + self.buffer[self.cursor:]; self.cursor += len(key[1])
                    else: self.input_overflow = True
                self.draw()
                continue
            if getattr(self, 'layer', 'summary') == 'actions' and key in ('up', 'down', 'enter'):
                actions = self._actions()
                if key in ('up', 'down') and actions:
                    self.action_focus = max(0, min(len(actions) - 1, getattr(self, 'action_focus', 0) + (-1 if key == 'up' else 1)))
                elif key == 'enter' and actions:
                    sent = self._stage(actions[min(getattr(self, 'action_focus', 0), len(actions) - 1)])
                    if sent: return sent
                self.draw()
                continue
            if getattr(self, 'layer', 'summary') == 'filters' and key in ('up', 'down', 'enter'):
                choices = filter_choices()
                focus = max(0, min(len(choices) - 1, getattr(self, 'filter_focus', 0) + {'up': -1, 'down': 1}.get(key, 0)))
                self.filter_focus = focus
                if key == 'enter':
                    dimension, value = choices[focus]
                    limit, current = page_filters(getattr(self, 'page_command', ''))
                    current = dict(current, **{dimension: value}) if value else {k: v for k, v in current.items() if k != dimension}
                    self.layer = 'summary'; self.tab = 0
                    return self._send('views-page %d 0 %s' % (limit, ' '.join(
                        shlex.quote(current.get(key) or '-') for key in ('query', 'ownership', 'coverage', 'health'))))
                self.draw()
                continue
            if key == 'escape' and getattr(self, 'layer', 'summary') != 'summary':
                self.layer = 'summary'; self.scroll = 0; self.notice = 'Summary shown.'
            elif key == 'escape': self.notice = 'Nothing to close. :clear-selection clears the selected policy.'
            elif key == 'tab':
                command = self._tab_command((self.tab + 1) % len(TABS))
                if command: return command
            elif key in ('up', 'down') and self._overview_policies():
                self.overview_focus = max(0, min(len(self._overview_policies()) - 1, self.overview_focus + (-1 if key == 'up' else 1)))
            elif key == 'enter' and self._overview_policies():
                policies = self._overview_policies()
                return self._send('select ' + shlex.quote(str(policies[min(self.overview_focus, len(policies) - 1)]['object_id'])))
            elif key in ('up', 'down') and self._entry_candidates():
                self.entry_focus = max(0, min(len(self._entry_candidates()) - 1, self.entry_focus + (-1 if key == 'up' else 1)))
            elif key == 'enter' and self._entry_candidates():
                candidate = self._entry_candidates()[min(self.entry_focus, len(self._entry_candidates()) - 1)]
                if candidate.get('terminal_command'):
                    self.mode = 'command'; self.buffer = candidate['terminal_command'][:MAX_COMMAND]; self.cursor = len(self.buffer)
                    self.notice = 'REVIEW: this is the exact command; submit it to record the policy, or Esc discards it.'
                else:
                    self.notice = 'Nothing to run for policy %s; its explanation is above.' % candidate.get('number', '')
            elif key in ('up', 'down') and self.tab == 0 and self.rows:
                self.highlight = max(0, min(len(self.rows) - 1, self.highlight + (-1 if key == 'up' else 1)))
            elif key in ('up', 'down') and self.tab in (4, 5) and self.operation_rows and 'operations' in self.value:
                self.operation_highlight = max(0, min(len(self.operation_rows) - 1, self.operation_highlight + (-1 if key == 'up' else 1)))
            elif key in ('up', 'down', 'pageup', 'pagedown'):
                self.scroll += {'up': -1, 'down': 1, 'pageup': -max(1, self.size[1] - 8), 'pagedown': max(1, self.size[1] - 8)}[key]
            elif key == 'enter' and self.tab == 0 and self.rows:
                self.tab = 1
                return self._send('select ' + shlex.quote(self.rows[self.highlight]['object_id']))
            elif key == 'enter' and self.tab in (4, 5) and self.operation_rows and 'operations' in self.value:
                return self._send('review ' + shlex.quote(self.operation_rows[self.operation_highlight]['operation_root']))
            elif isinstance(key, tuple):
                char = key[1]
                if char in (':', '/'):
                    self.mode = 'search' if char == '/' else 'command'; self.buffer = ''; self.cursor = 0
                elif char == 'f':
                    # A list of the filters, like the actions; the typed form stays available through :views-page.
                    self.layer = 'filters'; self.scroll = 0; self.filter_focus = 0
                    self.notice = 'Up and Down choose; Enter applies the filter (a read-only query); Esc closes.'
                elif char == 'a':
                    command = self._read_actions()
                    if command: return command
                elif char in '123456789':
                    command = self._tab_command(int(char) - 1)
                    if command: return command
                elif char == 'q': return self._send('quit')
                elif char == 'n': return self._send('next')
                elif char == 'p': return self._send('previous')
                elif char == 'b':
                    # With nothing to go back to, _back only sets the notice; the loop keeps reading keys.
                    sent = self._back()
                    if sent is not None: return sent
                elif char == 'h': return self._send('health')
                elif char == 'd': return self._send('dictionary')
                elif char == 'm': return self._send('queue')
                elif char == 's': return self._send('start')
                elif char == 'i':
                    if self.selected is not None: return self._send('diagnostics')
                    self.notice = 'Select an exact identity from Estate first.'
                elif char == 'v':
                    if self.active_operation is not None: return self._send('delivery ' + shlex.quote(self.active_operation))
                    self.notice = 'No active operation: review one first (5, or :review OPERATION_DIR).'
                elif char == 'l': return self._send('lineage')
                elif char == 'o': return self._send('estate-overview')
                elif char in ('e', 'r'):
                    wanted = 'details' if char == 'e' else 'raw'
                    self.layer = 'summary' if getattr(self, 'layer', 'summary') == wanted else wanted
                    self.scroll = 0
                    self.notice = ('Summary shown.' if self.layer == 'summary' else
                                   'Typed details shown.' if wanted == 'details' else 'Raw record shown.')
                elif char == '?': return self._send('help')
            self.draw()


def run_workspace(root, *, service_root=None, theme='dark', no_color=False, reduced_motion=True, stdin=None, stdout=None, rules='auto'):
    """Open visual POSIX profile or retain the entire reference text interface."""
    from .workbench import run_terminal
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    if theme not in THEMES: raise AppError('workspace_theme_invalid', 'Choose one of: ' + ', '.join(THEMES) + '.')
    if rules not in ('auto', 'ascii'): raise AppError('workspace_rules_invalid', 'Choose auto or ascii rules.')
    if not visual_supported(stdin, stdout):
        input_closed = output_closed = False

        def closed():
            # Nobody reads the output any more (a pipe whose reader left): end the session, never answer into it.
            nonlocal input_closed, output_closed
            input_closed = output_closed = True
            raise EOFError

        def close_input():
            nonlocal input_closed
            input_closed = True

        def write_line(line):
            if output_closed: raise EOFError
            try:
                print(line, file=stdout)
            except BrokenPipeError:
                closed()

        def read_line(prompt):
            if input_closed: raise EOFError
            try:
                stdout.write(prompt); stdout.flush()
            except BrokenPipeError:
                closed()
            value = stdin.readline(MAX_COMMAND + 2)
            if value == '': raise EOFError
            if len(value.rstrip('\r\n')) > MAX_COMMAND:
                # Reject a whole physical line. Never let an oversized line's
                # suffix become another command. Bound draining; if there is
                # no delimiter within that bound, close this input session.
                remaining = MAX_COMMAND * 4
                while value and not value.endswith('\n') and remaining:
                    value = stdin.readline(min(4096, remaining))
                    remaining -= len(value)
                if value and not value.endswith('\n'): close_input()
                return 'x' * (MAX_COMMAND + 1)
            return value.rstrip('\r\n')
        try:
            result = run_terminal(root, service_root=service_root, input_fn=read_line, output_fn=write_line)
        except EOFError:
            # Raised while an error was being answered; only a closed output ends the session this way.
            if not output_closed: raise
            result = {'status': 'closed', 'evidence_class': 'local_interface_result', 'history_persisted': True}
        return dict(result, output_closed=True) if output_closed else result
    workspace = Workspace(root, theme=theme, no_color=no_color, reduced_motion=reduced_motion, stdin=stdin, stdout=stdout, rules=rules)
    with terminal_session(stdin, stdout):
        return run_terminal(root, service_root=service_root, input_fn=workspace.input,
                            output_fn=lambda line: None, result_fn=workspace.receive)
