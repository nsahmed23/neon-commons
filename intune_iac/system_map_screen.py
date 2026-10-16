"""The system map's renderer: a `system-map/1` snapshot as terminal rows, plain text and JSON (requirement 17 UX-VIS, part B).

Pure. The projection's own snapshot goes in; rows of text, or one JSON value, come out. Nothing here reads a record, asks
the engine or infers a link:
  * Only a `system-map/1` snapshot with valid states is drawn. Anything else is a "System map unavailable" result that says
    why, never a partial map drawn as fine (`unavailable_reason`).
  * A node's place comes from its position in the supplied list, its `layer` and its `boundary`, and from nothing else: a
    state or an edge changes a word, never a coordinate.
  * Only the supplied edges are drawn, each with its own state, type and basis. A link keeps its own state whatever the state
    of the nodes at its ends.
  * Record-derived text goes through `safe_text` before it is measured, and is measured in cells (`cell_width`). A row too
    narrow for an identity shortens the identity (with an ellipsis) or wraps the detail; a state word is never shortened.
  * ASCII and Unicode, colour and no colour, give the same words. Colour is a fixed SGR pair around a state word, added after
    the row is measured; record text never reaches a terminal as a control.
  * JSON is the snapshot itself, in its own order, with nothing around it. Terminal escaping does not apply to it.

The shared presentation helpers are imported from the modules that own them; neither of those imports this one.
"""
from __future__ import annotations

import json
import re

from .system_map_projection import EDGE_TYPES, SCHEMA, STATE_WORDS, STATES
from .workbench_screens import word_wrap
from .workbench_tui import cell_width, clip, pad, safe_text

MIN_SIZE = (60, 20)
NEEDS = ("The system map needs a larger window (at least %dx%d). Plain text: intune-iac workbench system-map, with this "
         "workspace's --root and --policy.")
UNAVAILABLE = 'System map unavailable: '
UNAVAILABLE_SCHEMA = 'system-map-unavailable/1'
HAZARD = 'recorded means on record, not current or successful.'
READ_ONLY = 'This view is read-only: it reads the recorded state of the policy and writes nothing.'
LABELS = {'repo.source': 'repository', 'atmos.component': 'atmos', 'tofu.engine': 'opentofu', 'tofu.backend': 'backend',
          'provider': 'provider', 'service': 'service', 'readback': 'readback', 'observation': 'observation'}
SURFACES = {'9': '9 Repository', '2': '2 Coverage', 'v': 'v Delivery'}
GLYPHS = {'ascii': {'spine': '|-', 'arrow': '->', 'ellipsis': '...'},
          'unicode': {'spine': '├─', 'arrow': '→ ', 'ellipsis': '…'}}
ELLIPSIS_CELLS = 3            # both forms cut where the three-dot form cuts, so the same words survive in each
LABEL_WIDTH = 11
WORD_WIDTH = 14               # the widest state word, "not configured"
TYPE_WIDTH = 15               # the longest edge type, "applies-through"
MAX_LAYER = 5
EVIDENCE_ROOM = 24            # the longest evidence class the producer names, "graph_capture_unverified"
NODE_LEFT = MAX_LAYER * 2 + 2 + 1 + LABEL_WIDTH       # the indent of the deepest layer, the spine, a space, the label
NODE_FIXED = 1 + 1 + 1 + 1 + NODE_LEFT + 1 + WORD_WIDTH + 1      # focus mark, tag, their spaces, the left cell, the word column
STYLES = {'recorded': '32', 'configured': '32', 'not_configured': '2', 'unknown': '33', 'stale': '33', 'unverified': '33'}
RESET = '\x1b[0m'
SGR = re.compile(r'\x1b\[[0-9;]*m')


# ---- what is drawn at all ---------------------------------------------------------------------------------------------

def _shown(value, room=48):
    text = safe_text(value)
    return text if cell_width(text) <= room else clip(text, room - 3) + '...'


def unavailable_reason(snapshot):
    """Why a snapshot cannot be drawn, or None when it can: not a `system-map/1` snapshot, or a state, type, boundary, node or
    edge the map does not define. A renderer that guessed here would draw a state the records never held."""
    if not isinstance(snapshot, dict):
        return 'the result is not a system map'
    if snapshot.get('schema_version') != SCHEMA:
        return 'the schema is %s, and this reads %s' % (_shown(snapshot.get('schema_version')), SCHEMA)
    nodes, edges, boundaries = snapshot.get('nodes'), snapshot.get('edges'), snapshot.get('boundaries')
    if not isinstance(nodes, list) or not nodes or not all(isinstance(node, dict) for node in nodes):
        return 'it holds no nodes'
    if not isinstance(edges, list) or not all(isinstance(edge, dict) for edge in edges):
        return 'its edges are not a list'
    if not isinstance(boundaries, list) or not all(isinstance(item, dict) and isinstance(item.get('id'), str)
                                                    for item in boundaries):
        return 'its boundaries are not a list'
    known, seen = [item['id'] for item in boundaries], []
    for node in nodes:
        identifier = node.get('id')
        if not isinstance(identifier, str) or not identifier or identifier in seen:
            return 'a node has no identifier, or one that repeats'
        seen.append(identifier)
        if node.get('state') not in STATES:
            return 'node %s has the state %s' % (_shown(identifier), _shown(node.get('state')))
        if node.get('boundary') not in known:
            return 'node %s names the boundary %s' % (_shown(identifier), _shown(node.get('boundary')))
        layer = node.get('layer')
        if not isinstance(layer, int) or isinstance(layer, bool):
            return 'node %s has no layer' % _shown(identifier)
    for edge in edges:
        name = _shown(edge.get('id'))
        if edge.get('state') not in STATES:
            return 'edge %s has the state %s' % (name, _shown(edge.get('state')))
        if edge.get('type') not in EDGE_TYPES:
            return 'edge %s has the type %s' % (name, _shown(edge.get('type')))
        if edge.get('from') not in seen or edge.get('to') not in seen:
            return 'edge %s joins a node the map does not hold' % name
    return None


def unavailable_lines(reason, width):
    return word_wrap(UNAVAILABLE + reason + '.', width)


def no_map_lines(width, rows_needed=MIN_SIZE[1]):
    """What the map says where there is no room for it: that it needs a larger window, and the plain-text route in words.
    A copyable command never holds a stand-in operand (ROOT, ID), so the operands are named, not written, as the workflow
    map's small-window notice does when it cannot show the real ones."""
    return word_wrap(NEEDS % (MIN_SIZE[0], max(rows_needed, MIN_SIZE[1])), width)


# ---- the words of one node and one edge -------------------------------------------------------------------------------

def _label(identifier):
    return LABELS.get(identifier) or _shown(identifier, LABEL_WIDTH)


def _word(state):
    return STATE_WORDS[state]


def _text(value):
    if value is None or value == [] or value == '':
        return None
    if isinstance(value, bool):
        return 'yes' if value else 'no'
    if isinstance(value, (list, tuple)):
        parts = [_text(item) for item in value]
        return ', '.join(part for part in parts if part) or None
    return safe_text(value)


def _pairs(mapping):
    """(name, text) of each recorded value a record holds, in its own order; a null is not a value."""
    return [(safe_text(name), text) for name, value in (mapping.items() if isinstance(mapping, dict) else ())
            if (text := _text(value)) is not None]


def _identity(node):
    pairs = _pairs(node.get('identity'))
    return ' '.join(text for _, text in pairs) or 'none recorded'


def _basis(basis):
    basis = basis if isinstance(basis, dict) else {}
    where = '%s: %s' % (_text(basis.get('record')) or 'no record', _text(basis.get('field')) or 'no field')
    return where + (' [%s]' % _text(basis.get('record_id')) if _text(basis.get('record_id')) else '')


def _reason(node):
    return 'reason ' + safe_text(node['reason']) if node.get('reason') else 'no reason recorded'


def _opens(node):
    opens = node.get('opens')
    return 'Enter opens ' + SURFACES.get(opens, safe_text(opens)) if opens else 'Enter opens nothing'


def _fit(text, room, glyphs):
    """The text within `room` cells: whole, or cut with an ellipsis, or nothing where even a cut will not fit."""
    if cell_width(text) <= room:
        return text
    if room <= ELLIPSIS_CELLS:
        return ''
    return clip(text, room - ELLIPSIS_CELLS) + glyphs['ellipsis']


def _styled(word, state, colour):
    return '\x1b[%sm%s%s' % (STYLES[state], word, RESET) if colour else word


def _hang(label, text, width, size=10):
    """A labelled value, wrapped under its label."""
    rows = word_wrap(text, max(1, width - size))
    return [(pad(label, size) if index == 0 else ' ' * size) + row for index, row in enumerate(rows)]


def _facts(node):
    pairs = _pairs(node.get('facts'))
    return '; '.join('%s %s' % (name.replace('_', ' '), text) for name, text in pairs)


# ---- the map ----------------------------------------------------------------------------------------------------------

def _shorter(text, room):
    """An identity within `room` cells, cut with a single `~` (the whole value is in the plain-text form and the detail)."""
    return text if cell_width(text) <= room else clip(text, room - 1) + '~'


def _header(snapshot, width):
    """The title row: the policy's name, its identity and its evidence class. The name and the identity shorten first; the
    evidence class (what kind of observation this is) keeps its words up to EVIDENCE_ROOM cells, and a name that cannot share
    the row takes a row of its own."""
    name = snapshot.get('name') if isinstance(snapshot.get('name'), str) and snapshot['name'] else None
    ident = safe_text(snapshot.get('object_id') or '')
    evidence = _shorter(safe_text(snapshot.get('evidence_class') or 'evidence class not recorded'), EVIDENCE_ROOM)
    for id_width in (cell_width(ident), 12, 8):
        tail = '(%s) | %s' % (_shorter(ident, id_width), evidence)
        room = width - 13 - 1 - cell_width(tail)
        if room >= 4 or (name is None and room >= 0):
            return ['[SYSTEM MAP] ' + (_fit_name(name, room) + ' ' if name else '') + tail]
    first = '[SYSTEM MAP] ' + (safe_text(name) if name else '(no name)')
    return [clip(first, width)] + word_wrap('(%s) | %s' % (_shorter(ident, 12), evidence), width)


def _fit_name(name, room):
    text = safe_text(name)
    return text if cell_width(text) <= room else clip(text, room - 3) + '...'


def _tag(identifier):
    """The one-cell letter a boundary is tagged with: the first letter of its escaped id, upper-cased, when that is exactly
    one printable ASCII cell (an escape's backslash is not a letter), else `?`. A raw slice could be a newline, nothing, a wide
    character or a letter that upper-cases to two."""
    first = safe_text(identifier)[:1].upper()
    plain = len(first) == 1 and first.isascii() and first.isprintable() and first != '\\' and cell_width(first) == 1
    return first if plain else '?'


def _tags(snapshot):
    return {item['id']: _tag(item['id']) for item in snapshot['boundaries']}


def _node_row(node, tag, focused, width, glyphs, colour):
    layer = max(0, min(node['layer'], MAX_LAYER))
    left = pad('%s%s %s' % ('  ' * layer, glyphs['spine'], _label(node['id'])), NODE_LEFT)
    word = _word(node['state'])
    identity = _fit(_identity(node), width - NODE_FIXED, glyphs)
    row = '%s %s %s %s%s' % ('>' if focused else ' ', tag.get(node['boundary'], '?'), left, _styled(word, node['state'], colour),
                             ' ' * (WORD_WIDTH - cell_width(word)))
    return (row + ' ' + identity).rstrip() if identity else row.rstrip()


def _edge_row(edge, width, glyphs, colour, wide):
    word = _word(edge['state'])
    row = '  %s %s %s %s %s%s' % (pad(_label(edge['from']), LABEL_WIDTH), glyphs['arrow'], pad(_label(edge['to']), LABEL_WIDTH),
                                pad(edge['type'], TYPE_WIDTH), _styled(word, edge['state'], colour),
                                ' ' * (WORD_WIDTH - cell_width(word)))
    fixed = 2 + LABEL_WIDTH + 1 + 2 + 1 + LABEL_WIDTH + 1 + TYPE_WIDTH + 1 + WORD_WIDTH + 1
    basis = _fit(_basis(edge.get('basis')), width - fixed, glyphs) if wide else ''
    return (row + ' ' + basis).rstrip() if basis else row.rstrip()


def _detail(snapshot, node, width):
    """The focused node in words: state, reason and where Enter goes, then its identity, basis, recorded values and links."""
    parts = ['FOCUS ' + _label(node['id']), _word(node['state']), _reason(node), _opens(node)]
    rows = _hang('', ' | '.join(parts), width, 0)
    rows += _hang('identity', '; '.join('%s %s' % pair for pair in _pairs(node.get('identity'))) or 'none recorded', width)
    rows += _hang('basis', _basis(node.get('basis')), width)
    facts = _facts(node)
    if facts:
        rows += _hang('recorded', facts, width)
    for edge in snapshot['edges']:
        if node['id'] in (edge['from'], edge['to']):
            rows += _hang('link', '%s %s -> %s | %s | %s' % (edge['type'], _label(edge['from']), _label(edge['to']),
                                                              _word(edge['state']), _basis(edge.get('basis'))), width)
    return rows


def render(snapshot, width, height, *, colour=False, unicode=False, focus=None):
    """The map as rows for a window `width` x `height`: each row within `width` cells, never more than `height` rows once
    the map itself is drawn.

    The map is complete before anything else is added: the header, one row per node, one row per supplied edge, the boundary
    letters and the sentence that says what `recorded` means. The focused node's detail takes the rows that are left."""
    # One exit: whatever is said, a window shows at most its own height, from the first row (the start of the notice or the
    # refusal), never a fragment from the middle.
    return _render(snapshot, width, height, colour, unicode, focus)[:max(0, height)]


def _render(snapshot, width, height, colour, unicode, focus):
    reason = unavailable_reason(snapshot)
    if reason:
        return unavailable_lines(reason, width)
    if width < MIN_SIZE[0] or height < MIN_SIZE[1]:
        return no_map_lines(width)
    glyphs = GLYPHS['unicode' if unicode else 'ascii']
    nodes, edges = snapshot['nodes'], snapshot['edges']
    ids = [node['id'] for node in nodes]
    focus = focus if focus in ids else ids[0]
    tags = _tags(snapshot)
    rows = _header(snapshot, width)
    rows += [_node_row(node, tags, node['id'] == focus, width, glyphs, colour) for node in nodes]
    rows += [_edge_row(edge, width, glyphs, colour, width >= 100) for edge in edges] or ['  no link is recorded']
    rows += word_wrap('  '.join('%s %s' % (tags[item['id']], safe_text(item.get('label') or item['id']))
                                for item in snapshot['boundaries']), width)
    rows += word_wrap(HAZARD, width)
    if len(rows) > height:
        # The mandatory rows alone are taller than the window: say how tall it must be, never return more rows than it has.
        return no_map_lines(width, len(rows))
    room = height - len(rows)
    if room > 0:
        rows += _detail(snapshot, next(node for node in nodes if node['id'] == focus), width)[:room]
    return rows


# ---- plain text and JSON ----------------------------------------------------------------------------------------------

def text(snapshot, width):
    """The plain-text form (`intune-iac workbench system-map`): the same words as the map, every node and every link in full,
    and no terminal control. The map rows lead where the width holds them; the blocks below are the whole record."""
    reason = unavailable_reason(snapshot)
    if reason:
        return unavailable_lines(reason, width)
    glyphs = GLYPHS['ascii']
    nodes, edges = snapshot['nodes'], snapshot['edges']
    tags = _tags(snapshot)
    rows = _header(snapshot, width)
    # The title shortens what it must; these rows hold the whole values.
    rows += _hang('name', safe_text(snapshot.get('name')) if isinstance(snapshot.get('name'), str) and snapshot['name']
                  else '(no name)', width)
    rows += _hang('policy', safe_text(snapshot.get('object_id') or '(none)'), width)
    rows += _hang('evidence', safe_text(snapshot.get('evidence_class') or 'not recorded'), width)
    rows += _hang('revision', safe_text(snapshot.get('revision') or 'none'), width)
    if width >= MIN_SIZE[0]:
        rows += [_node_row(node, tags, False, width, glyphs, False) for node in nodes]
        rows += [_edge_row(edge, width, glyphs, False, width >= 100) for edge in edges] or ['  no link is recorded']
    rows += word_wrap('  '.join('%s %s' % (tags[item['id']], safe_text(item.get('label') or item['id']))
                                for item in snapshot['boundaries']), width)
    rows += word_wrap(HAZARD, width) + ['', 'NODES']
    for number, node in enumerate(nodes, 1):
        rows += word_wrap('%d %s: %s | %s' % (number, _label(node['id']), _word(node['state']), _reason(node)), width)
        rows += _hang('  identity', '; '.join('%s %s' % pair for pair in _pairs(node.get('identity'))) or 'none recorded',
                      width, 12)
        rows += _hang('  basis', _basis(node.get('basis')), width, 12)
        if _facts(node):
            rows += _hang('  recorded', _facts(node), width, 12)
        rows += _hang('  opens', _opens(node), width, 12)
    rows += ['', 'LINKS']
    for number, edge in enumerate(edges, 1):
        rows += word_wrap('%d %s %s -> %s: %s' % (number, edge['type'], _label(edge['from']), _label(edge['to']),
                                                  _word(edge['state'])), width)
        rows += _hang('  basis', _basis(edge.get('basis')), width, 12)
    if not edges:
        rows.append('no link is recorded')
    return rows + [''] + word_wrap(READ_ONLY, width)


def to_json(snapshot):
    """One JSON value and nothing around it: the snapshot as it is, in its own order, with its nulls, identities and authority
    flags. A snapshot that cannot be drawn is an explicit unavailable value, never the snapshot passed off as a map. Non-ASCII
    is written as JSON escapes, so no raw control or line separator reaches a terminal."""
    reason = unavailable_reason(snapshot)
    body = snapshot
    if reason is None:
        try:
            return json.dumps(body, ensure_ascii=True, allow_nan=False, indent=2) + '\n'
        except (TypeError, ValueError):
            reason = 'its values cannot be written as JSON'
    received = snapshot.get('schema_version') if isinstance(snapshot, dict) else None
    body = {'schema_version': UNAVAILABLE_SCHEMA, 'available': False, 'reason': reason,
            'received_schema_version': received if isinstance(received, str) else None}
    return json.dumps(body, ensure_ascii=True, allow_nan=False, indent=2) + '\n'
