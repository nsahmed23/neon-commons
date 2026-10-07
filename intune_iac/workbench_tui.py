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
import select
import shlex
import sys
import unicodedata

from .io import AppError, load_json, write_json

MAX_COMMAND = 16384
MAX_RENDER_LINES = 200000
CONTEXT_VERSION = 'intune-workspace-context/1'
READ_VIEWS = {'overview', 'inspect', 'settings', 'relationships', 'lineage',
              'history', 'history-recent', 'health', 'operations', 'views', 'help'}
TABS = ('Estate', 'Inspector', 'Relationships', 'History', 'Plan', 'Execution', 'Coverage', 'Help')
TAB_COMMANDS = ('overview', 'inspect', 'relationships', 'history-recent', 'operations', 'operations', 'views', 'help')
ANSI_START = '\x1b[?1049h\x1b[?25l\x1b[?2004h'
ANSI_END = '\x1b[0m\x1b[?2004l\x1b[?25h\x1b[?1049l'


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


class Workspace:
    """UI state contains navigation only. Typed engine values remain authoritative."""
    def __init__(self, root, *, theme='dark', no_color=False, reduced_motion=True, stdin=None, stdout=None):
        from .workbench_store import WorkbenchStore, _private
        self.store = WorkbenchStore(root)
        self.context_path = self.store.root / 'workspace-context.json'
        self.stdin = sys.stdin if stdin is None else stdin
        self.stdout = sys.stdout if stdout is None else stdout
        self.theme = theme
        self.color = not no_color and 'NO_COLOR' not in os.environ
        self.reduced_motion = reduced_motion  # Both modes are event-driven: no decorative motion.
        self.value = {}
        self.selected = None
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
        self.pending = deque()
        self.size = terminal_size(self.stdout)
        self.key_reader = None
        self._detail_cache = None
        self.context_valid = False
        if self.context_path.exists() or self.context_path.is_symlink():
            _private(self.context_path)
            value = load_json(self.context_path)
            self._validate_context(value)
            self.selected = value['selected']
            self.view_command = value['view_command']
            self.page_command = value['page_command']
            self.tab = value['tab']
            # Never replay saved user commands or operation paths.
            self.pending.append(self.page_command)
            if self.selected:
                self.pending.append('select ' + shlex.quote(self.selected))
            if self.view_command != self.page_command and (self.selected or self.view_command in ('help', 'health', 'operations', 'views')):
                self.pending.append(self.view_command)
            self.context_valid = True

    def _validate_context(self, value):
        from .workbench_store import _identity
        required = {'schema_version', 'tenant_id', 'selected', 'view_command', 'page_command', 'tab'}
        if (not isinstance(value, dict) or set(value) != required or value['schema_version'] != CONTEXT_VERSION
                or value['tenant_id'] != self.store.tenant_id or type(value['tab']) is not int or not 0 <= value['tab'] < len(TABS)):
            raise AppError('workspace_context_invalid', 'Workspace context is invalid; preserve it for inspection before reopening.')
        if value['selected'] is not None: _identity(value['selected'])
        for key in ('view_command', 'page_command'):
            command = value[key]
            if type(command) is not str or len(command) > MAX_COMMAND:
                raise AppError('workspace_context_invalid', 'Workspace navigation exceeds its bounds.')
            parts = shlex.split(command)
            valid = (len(parts) == 1 and parts[0] in READ_VIEWS)
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
        _private(self.store.root, True)
        if self.context_path.exists() or self.context_path.is_symlink(): _private(self.context_path)
        value = {'schema_version': CONTEXT_VERSION, 'tenant_id': self.store.tenant_id,
                 'selected': self.selected, 'view_command': self.view_command,
                 'page_command': self.page_command, 'tab': self.tab}
        self._validate_context(value)
        write_json(self.context_path, value)

    def receive(self, value):
        """Callback after the SAME engine has validated/executed an input."""
        if not isinstance(value, dict): value = {'result': value}
        # Initial help should not displace restored selection/navigation.
        self.value = value
        self.scroll = 0
        if value.get('status') == 'error':
            self.notice = 'ERROR: ' + str(value.get('error', {}).get('code', 'unknown'))
        else:
            object_id = value.get('object_id')
            if object_id and self.last_command.startswith('select '):
                if self.selected != object_id:
                    self.active_operation = None; self.execution_result = None
                self.selected = object_id
                self.view_command = 'inspect'
            history_page = value.get('pagination', {}).get('scope') == 'history_page'
            if value.get('status') == 'selection_cleared' or (self.last_command in ('next', 'previous') and not history_page): self.selected = None
            if self.selected is None and self.view_command.startswith('history-recent'):
                self.view_command = 'overview'
            if history_page and isinstance(value.get('history'), list):
                self.selected = value['object_id']
                self.view_command = 'history-recent %d %d' % (value['pagination']['limit'], value['pagination']['offset'])
            if 'objects' in value and isinstance(value['objects'], list):
                self.rows = [row for row in value['objects'] if isinstance(row, dict) and isinstance(row.get('object_id'), str)]
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
                self.operation_rows = [row for row in value['operations'] if isinstance(row, dict) and isinstance(row.get('operation_root'), str)]
                self.operation_highlight = min(self.operation_highlight, max(0, len(self.operation_rows) - 1))
            if isinstance(value.get('operation_root'), str):
                if self.active_operation != value['operation_root']: self.execution_result = None
                self.active_operation = value['operation_root']
            try: parts = shlex.split(self.last_command)
            except ValueError: parts = []
            if len(parts) >= 2 and parts[0] in ('execute', 'reconcile'):
                self.active_operation = parts[1]
                self.execution_result = value
            if self.last_command in READ_VIEWS and not history_page: self.view_command = self.last_command
            # Persist only after successful result. Rendering never stores raw
            # commands, approvals, paths, captures or credential material.
            self.save_context()
            self.notice = 'Ready. : opens the complete text command bar; Esc cancels editing.'
        self.draw()

    def _surface_summary(self, width):
        value = self.value
        rows = []
        def field(label, item):
            rendered = json.dumps(item, ensure_ascii=False, allow_nan=False) if not isinstance(item, str) else item
            rows.extend(wrap(label + ': ' + rendered, width))
        if self.tab == 1 and value.get('object_id'):
            rows.append('[POLICY INSPECTOR]')
            for label, key in (('Identity', 'object_id'), ('Name', 'name'), ('Observed at', 'observed_at'),
                               ('Coverage', 'coverage'), ('Freshness', 'freshness'), ('Ownership', 'ownership')):
                field(label, value.get(key, 'unknown'))
            body = value.get('body', value)
            for key in ('settings', 'assignments'):
                items = body.get(key) if isinstance(body, dict) else None
                field(key.capitalize() + ' in this result', len(items) if isinstance(items, list) else 'unknown')
            rows.append('[EXACT VALUES AND TARGETING] Full typed evidence follows.')
        elif self.tab == 2 and isinstance(value.get('relationships'), list):
            rows.append('[TYPED RELATIONSHIPS]')
            for edge in value['relationships'][:20]:
                if isinstance(edge, dict):
                    field(str(edge.get('relation', 'unknown')) + ' ->', edge.get('target_id', 'unknown'))
                    field('  Evidence class', edge.get('assertion_class', 'See exact edge details; not independently authenticated'))
            if len(value['relationships']) > 20: rows.append('[SUMMARY] First 20 edges; complete edge records follow.')
            rows.append('[EDGE EVIDENCE AND UNCERTAINTY]')
        elif self.tab == 3 and isinstance(value.get('history'), list):
            rows.append('[OBSERVATION HISTORY]')
            if value.get('order') == 'observed_at_desc_observation_id_desc':
                field('Order', 'Newest first; n shows older observations, p shows newer observations.')
                field('History page', value.get('pagination', {}))
            rows.extend(wrap('Comparison baseline: collected snapshot to collected snapshot. Observation time does not establish actor or change time.', width))
            for item in value['history'][:12]:
                if isinstance(item, dict):
                    field('Observed', item.get('observed_at', 'unknown'))
                    field('Snapshot', item.get('snapshot_id', 'unknown'))
            if len(value['history']) > 12: rows.append('[SUMMARY] First 12 records; full result follows.')
            rows.append('[EXACT HISTORY]')
        elif self.tab == 4 and value.get('operation_id'):
            rows.append('[EXACT PLAN REVIEW]')
            for label, key in (('Operation', 'operation_id'), ('Tenant', 'tenant_id'), ('Object', 'object_id'),
                               ('Status', 'status'), ('Plan SHA-256', 'saved_plan_sha256'),
                               ('Approval binding', 'approval_digest'), ('Expiry', 'expires_at'), ('Evidence class', 'evidence_class')):
                field(label, value.get(key, 'unknown'))
            rows.append('[BEFORE / DESIRED / TARGETING / RISKS] Exact engine values follow.')
        elif self.tab == 5 and ('result' in value or 'operation_id' in value):
            result = value.get('result', value)
            rows.append('[EXECUTION AND RECOVERY]')
            field('Observation scope', value.get('display_scope', 'current engine result'))
            if isinstance(result, dict):
                for label, key in (('Operation', 'operation_id'), ('Status', 'status'), ('Readback', 'classification'),
                                   ('Error', 'error_code'), ('Evidence class', 'evidence_class')):
                    field(label, result.get(key, 'unknown'))
            rows.extend(wrap('Next: inspect durable receipts; explicitly reconcile uncertain outcomes. No automatic replay or approval.', width))
            rows.append('[CHECKS / JOURNAL / RESULT]')
        elif self.tab == 6 and value.get('schema_version') == 'workbench-four-views/1':
            rows.append('[REPOSITORY / OBSERVED / PROPOSED / COVERAGE]')
            for label in ('repository', 'observed', 'proposed'):
                facet = value.get(label, {})
                field(label.capitalize(), facet.get('status', 'unknown') if isinstance(facet, dict) else 'unknown')
            coverage = value.get('coverage', {})
            if isinstance(coverage, dict):
                for label, key in (('Observation coverage', 'observation'), ('Management', 'management'),
                                   ('State tracked', 'state_tracked'), ('Mapping', 'mapping'), ('Platform qualified', 'platform_qualified')):
                    field(label, coverage.get(key, 'unknown'))
                own = coverage.get('ownership', {})
                if isinstance(own, dict):
                    field('Ownership scope complete', own.get('declared_scope_complete', 'unknown'))
                    field('Ownership freshness', own.get('fresh', 'unknown'))
            rows.append('[DISTINCT COMPARISON BASELINES]')
            for label, comparison in value.get('comparisons', {}).items():
                if isinstance(comparison, dict):
                    field(label, comparison.get('status', 'unknown'))
                    field('  Baseline', comparison.get('baseline', comparison.get('reason', 'not recorded')))
            rows.append('[COMPLETE VIEW EVIDENCE]')
        elif self.tab == 7:
            rows.append('[WORKSPACE SHORTCUTS]')
            for text in ('1 Estate | 2 Inspector | 3 Relationships | 4 History',
                         '5 Exact plan | 6 Execution/recovery | 7 Coverage | 8 Help',
                         ': Complete text commands | / Search | f Global filters | q Detach',
                         'Arrows select or scroll | Enter selects exact identity',
                         'Escape discards edit | Ctrl-U clears edit | no automatic approval'):
                rows.extend(wrap(text, width))
            rows.append('[COMPLETE ENGINE COMMANDS]')
        if rows: rows.append('')
        return rows

    def _data_lines(self, width):
        if self.tab == 0 and self.rows and isinstance(self.value.get('objects'), list):
            lines = ['[SELECT] Exact identity / name / ownership / coverage / health']
            if isinstance(self.value.get('filters'), dict):
                lines.extend(wrap('Global filters: ' + json.dumps(self.value['filters'], ensure_ascii=False), width))
                page = self.value.get('pagination', {})
                lines.extend(wrap('Matching objects: %s / inventory: %s | page offset: %s' %
                    (page.get('total_objects', 'unknown'), self.value.get('total_inventory_objects', 'unknown'), page.get('offset', 'unknown')), width))
            for index, row in enumerate(self.rows):
                mark = '>' if index == self.highlight else ' '
                lines.extend(wrap('%s %s' % (mark, row['object_id']), width))
                coverage = row.get('coverage', 'unknown')
                owner = coverage.get('management', 'unknown') if isinstance(coverage, dict) else row.get('ownership', 'unknown')
                coverage = coverage.get('observation', 'unknown') if isinstance(coverage, dict) else coverage
                health = row.get('health', {})
                lines.extend(wrap('  %s | owner=%s | coverage=%s | health=%s | freshness=%s' %
                                  (row.get('name', 'unknown'), owner, coverage,
                                   health.get('status', 'unknown') if isinstance(health, dict) else 'unknown', row.get('freshness', 'unknown')), width))
            lines.append('')
            lines.append('[EVIDENCE] Page metadata and exact result follow below')
        elif self.tab in (4, 5) and self.operation_rows and isinstance(self.value.get('operations'), list):
            lines = ['[OPERATIONS] Enter reviews exact current plan; no approval or execution.']
            for index, row in enumerate(self.operation_rows):
                mark = '>' if index == self.operation_highlight else ' '
                lines.extend(wrap('%s %s | recorded=%s | status=%s' %
                                  (mark, row.get('operation_id'), row.get('recorded_at', 'unknown'), row.get('status', 'unknown')), width))
                lines.extend(wrap('  ' + row['operation_root'], width))
            lines.extend(['', '[EVIDENCE] Recorded receipts; Enter revalidates current plan.'])
        else: lines = self._surface_summary(width)
        cache_key = (id(self.value), width)
        if self._detail_cache is not None and self._detail_cache[0] == cache_key:
            return lines + self._detail_cache[1]
        detail = []
        for line in json.dumps(self.value, ensure_ascii=False, indent=2, allow_nan=False).splitlines():
            detail.extend(wrap(line, width))
            if len(detail) > MAX_RENDER_LINES:
                # Data remains in the complete text interface. This boundary is
                # explicit rather than silent truncation or false completeness.
                detail = detail[:MAX_RENDER_LINES]
                detail.append('[VIEW LIMIT] Use the paged text interface for this result.')
                break
        self._detail_cache = (cache_key, detail)
        return lines + detail

    def draw(self):
        self.size = terminal_size(self.stdout)
        width, height = self.size
        inner = width - 2
        header = 'INTUNE WORKBENCH  /  ' + TABS[self.tab]
        selection = self.selected or 'none'
        labels = '  '.join('%d %s' % (i + 1, name) for i, name in enumerate(TABS))
        available = max(0, height - 8)
        data = self._data_lines(inner)
        self.scroll = max(0, min(self.scroll, max(0, len(data) - available)))
        visible = data[self.scroll:self.scroll + available]
        status = 'tenant=%s | selected=%s' % (self.store.tenant_id, selection)
        scope = self.value.get('evidence_class', 'unknown')
        footer = '[%s] rows %d-%d/%d | no automatic approval' % (scope, min(self.scroll + 1, len(data)), min(self.scroll + available, len(data)), len(data))
        if self.mode:
            prefix = '/' if self.mode == 'search' else ':'
            before_cursor = safe_text(self.buffer[:self.cursor])
            after_cursor = safe_text(self.buffer[self.cursor:])
            tail, used = [], 0
            for char in reversed(before_cursor):
                cells = 2 if unicodedata.east_asian_width(char) in ('W', 'F') else 1
                if used + cells > max(1, width - 5): break
                tail.append(char); used += cells
            before_cursor = ''.join(reversed(tail))
            prompt = prefix + before_cursor + '|' + after_cursor
        else: prompt = self.notice
        frame = [pad(header, width), pad(labels, width), pad(status, width), '+' + '-' * inner + '+']
        frame.extend('|' + pad(line, inner) + '|' for line in visible)
        frame.extend('|' + ' ' * inner + '|' for _ in range(available - len(visible)))
        frame.extend(['+' + '-' * inner + '+', pad(footer, width), pad(prompt, width), pad('Arrows select/scroll | PgUp/PgDn | : command | / search | f filters | q detach', width)])
        if self.color:
            background, foreground, accent = ('48;5;234', '38;5;252', '38;5;81') if self.theme == 'dark' else ('48;5;230', '38;5;237', '38;5;24')
            painted = ['\x1b[%s;%sm%s\x1b[0m' % (background, accent if i in (0, 1, len(frame) - 2) else foreground, line)
                       for i, line in enumerate(frame)]
        else: painted = frame
        self.stdout.write('\x1b[H' + '\r\n'.join(painted) + '\x1b[J')
        self.stdout.flush()

    def _send(self, command):
        try: name = shlex.split(command)[0]
        except (ValueError, IndexError): name = ''
        tabs = {'overview': 0, 'search': 0, 'search-page': 0, 'views-page': 0, 'select': 1, 'inspect': 1, 'settings': 1,
                'relationships': 2, 'lineage': 2, 'history': 3, 'history-recent': 3, 'compare': 3, 'review': 4,
                'propose': 4, 'execute': 5, 'reconcile': 5, 'restore-propose': 4, 'views': 6, 'help': 7}
        if name in tabs: self.tab = tabs[name]
        self.last_command = command
        self.scroll = 0
        self.mode = None
        self.buffer = ''
        self.cursor = 0
        self.input_overflow = False
        self.notice = 'RUNNING: waiting for the engine; outcome is not yet known.'
        self.draw()
        return command

    def _tab_command(self, tab):
        self.tab = tab
        command = TAB_COMMANDS[tab]
        if tab == 4 and self.active_operation:
            return self._send('review ' + shlex.quote(self.active_operation))
        if tab == 5 and self.execution_result is not None:
            self.value = {'display_scope': 'last engine result in this interface; refresh durable operations for later activity',
                          'operation_root': self.active_operation, 'result': self.execution_result,
                          'recovery': 'Use :reconcile OPERATION_DIR for explicit independent readback; never blindly replay execution.'}
            self.scroll = 0
            self.notice = 'LAST RESULT: no action dispatched. :operations refreshes durable receipts.'
            self.save_context(); self.draw()
            return None
        if tab == 6 and self.active_operation and self.selected is not None:
            return self._send('views ' + shlex.quote(self.active_operation))
        if command in ('inspect', 'relationships', 'history', 'history-recent', 'views') and self.selected is None:
            self.notice = 'Select an exact identity from Estate first.'
            self.draw()
            return None
        return self._send(command)

    def input(self, _prompt):
        if self.pending:
            return self._send(self.pending.popleft())
        if self.key_reader is None: self.key_reader = KeyReader(self.stdin)
        self.draw()
        while True:
            key = self.key_reader.read()
            if key is None:
                if terminal_size(self.stdout) != self.size: self.draw()
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
                    self.mode = None; self.buffer = ''; self.cursor = 0; self.input_overflow = False
                    self.notice = 'EDIT CANCELLED: no command submitted; active external runs are unchanged.'
                elif key == 'enter':
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
            if key == 'escape': self.notice = 'No edit to cancel. Use :cancel to clear engine selection; no run is cancelled.'
            elif key == 'tab':
                command = self._tab_command((self.tab + 1) % len(TABS))
                if command: return command
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
                    self.mode = 'command'
                    self.buffer = self.page_command if self.page_command.startswith('views-page ') else 'views-page 10 0 - - - -'
                    self.cursor = len(self.buffer)
                elif char in '12345678':
                    command = self._tab_command(int(char) - 1)
                    if command: return command
                elif char == 'q': return self._send('quit')
                elif char == 'n': return self._send('next')
                elif char == 'p': return self._send('previous')
                elif char == 'b': return self._send('back')
                elif char == 'h': return self._send('health')
                elif char == 'l': return self._send('lineage')
                elif char == '?': return self._send('help')
            self.draw()


def run_workspace(root, *, service_root=None, theme='dark', no_color=False, reduced_motion=True, stdin=None, stdout=None):
    """Open visual POSIX profile or retain the entire reference text interface."""
    from .workbench import run_terminal
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    if theme not in ('dark', 'light'): raise AppError('workspace_theme_invalid', 'Choose dark or light theme.')
    if not visual_supported(stdin, stdout):
        input_closed = False
        def read_line(prompt):
            nonlocal input_closed
            if input_closed: raise EOFError
            stdout.write(prompt); stdout.flush()
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
                if value and not value.endswith('\n'): input_closed = True
                return 'x' * (MAX_COMMAND + 1)
            return value.rstrip('\r\n')
        return run_terminal(root, service_root=service_root, input_fn=read_line,
                            output_fn=lambda line: print(line, file=stdout))
    workspace = Workspace(root, theme=theme, no_color=no_color, reduced_motion=reduced_motion, stdin=stdin, stdout=stdout)
    with terminal_session(stdin, stdout):
        return run_terminal(root, service_root=service_root, input_fn=workspace.input,
                            output_fn=lambda line: None, result_fn=workspace.receive)
