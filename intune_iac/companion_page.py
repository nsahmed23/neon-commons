"""The isometric companion page: one self-contained HTML document drawn from the typed graph projection.

Requirement 17 UX-VIS, second slice. The terminal map and this page read the same projection (graph_projection), so
they agree on identifiers, kinds, edge types, order, state words and the revision; neither reads a relationship out
of a displayed string. Pure: a graph in, text out. Nothing here opens a file, a socket or a browser, and the page
carries no operation: it cannot approve, execute or navigate the workbench.

The drawing is an oblique isometric view in SVG: one plate per relation group, in the terminal's order, a block per
object, fine outlines, and typed connectors from the selected policy. Geometry comes from topology and identifier
order alone, in fixed cells, so a state change moves nothing: the state is a mark and a word in a text of its own
(state_text) and a data attribute, and every other byte of the drawing is the same. The page names its revision,
its observation time and its evidence mode, and says whether it updates itself. In live mode its script asks the
local listener for the current snapshot and reports STALE or DISCONNECTED; it never redraws the drawing it holds.

The page is bounded: one selected object and one hop, at most PLATE_LIMIT objects per plate with "N more not drawn",
and at most TEXT_LINE_LIMIT lines of the text alternative, whatever the estate holds.
"""
from __future__ import annotations

import base64
import hashlib
import html
import re

from .graph_projection import DISTINCT_KINDS, STATES, count_words, distinct_labels, drawn_layers, traversal_order
from .io import AppError, unique_prefixes
from .workbench_tui import cell_width, fit, safe_text

SCHEMA = 'workbench-companion-page/1'
PLATE_LIMIT = 12
TEXT_LINE_LIMIT = 600
LABEL_CELLS = 80
CHAR_WIDTH = 7.3
CENTER_HEADING = 'SELECTED POLICY'
# The one way the companion command is named wherever it is named (the actions entry, its long text and this page): the
# product's own flags. The address a --serve run listens on is printed by the product; the engineer never supplies it.
COMPANION_WRITE = 'intune-iac workbench companion --root STORE --object ID --out FILE'
COMPANION_SERVE = 'intune-iac workbench companion --root STORE --object ID --serve'

# Geometry, in drawing units. One step along a plate is (STEP_X, STEP_Y), the 30 degree isometric axis.
STEP_X, STEP_Y = 45, 26
LEFT, TOP, GAP = 130, 70, 64
SPINE_X = LEFT - 70
MIN_WIDTH = 760
BLOCK_HALF, BLOCK_DEPTH = 14, 8
MARKS_DX, SELECT_DX, STATE_DX, LABEL_DX = 22, 36, 54, 224
LABEL_ROOM = 48
WORD_CELLS = 18

# The typed connectors. Each has its own line pattern, so none depends on colour, and the legend states its meaning.
EDGE_STYLES = {
    'assignment': {'dash': 'none', 'name': 'assignment', 'meaning': 'the policy is assigned to the group or target at the end'},
    'exclusion': {'dash': '8 5', 'name': 'exclusion', 'meaning': 'the policy excludes the group at the end'},
    'filter': {'dash': '1 4', 'name': 'filter',
               'meaning': 'an assignment filter applies to one assignment, not to the policy: the line under the filter says '
                          'which ("applies to"), and the line under that assignment names the filter ("+ filter")'},
    'setting': {'dash': '10 4 2 4', 'name': 'setting', 'meaning': 'the policy holds the setting at the end'},
    'scope_tag': {'dash': '14 6', 'name': 'scope tag', 'meaning': 'the policy carries the scope tag at the end'},
    'generated_from': {'dash': '4 3', 'name': 'generated', 'meaning': 'the policy was generated from the file at the end'},
    'repository': {'dash': '12 4 2 4 2 4', 'name': 'repository', 'meaning': 'the repository scope the engineer selected'},
    'other': {'dash': '6 6 1 6', 'name': 'other relation', 'meaning': 'a relation the read model named; the detail states it'},
}
# What the policy's recorded operation word is marked with, where the eight state words have no mark for it.
OPERATION_MARKS = {'none recorded': '_', 'expired': '~', 'prepared': 'o'}
NO_INSPECT = ('This %s has no inspect route; only a policy opens in the Inspector (key 2 in the workbench). '
              'This page changes nothing.')

CSS = """
:root { color-scheme: light dark; --bg: #ffffff; --ink: #14181d; --muted: #4a5360; --rule: #3a4350; --soft: #c9d0d9;
  --sel: #dbe6f5; --halo: #ffffff; --warn: #8a5a00; --bad: #9b1c1c; }
@media (prefers-color-scheme: dark) { :root { --bg: #14181d; --ink: #e8ecf1; --muted: #aeb7c3; --rule: #aeb7c3;
  --soft: #3a4350; --sel: #26364d; --halo: #14181d; --warn: #e0b34f; --bad: #ff9a9a; } }
@media (forced-colors: active) { :root { --bg: Canvas; --ink: CanvasText; --muted: CanvasText; --rule: CanvasText;
  --soft: GrayText; --sel: Canvas; --halo: Canvas; --warn: CanvasText; --bad: CanvasText; } }
* { box-sizing: border-box; }
body { margin: 0; padding: 0 1rem 2rem; background: var(--bg); color: var(--ink);
  font: 15px/1.45 system-ui, "Segoe UI", sans-serif; }
code, pre, svg text { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
h1 { font-size: 1.25rem; margin: 1rem 0 .25rem; }
h2 { font-size: 1.05rem; margin: 1.25rem 0 .4rem; }
h3 { font-size: .95rem; margin: 0 0 .3rem; }
p { margin: .25rem 0; }
code { word-break: break-all; }
.skip { position: absolute; left: -999px; }
.skip:focus { position: static; }
#live { padding: .4rem .6rem; border: 2px solid var(--rule); }
#live[data-state="stale"] { border-style: dashed; border-width: 3px; }
#live[data-state="disconnected"] { border-style: double; border-width: 5px; }
button { font: inherit; padding: .25rem .7rem; border: 1px solid var(--rule); background: var(--bg); color: var(--ink);
  border-radius: 4px; cursor: pointer; }
button:focus-visible, #stage:focus-visible { outline: 3px solid var(--ink); outline-offset: 2px; }
#controls { display: flex; gap: .5rem; align-items: center; margin: .4rem 0; flex-wrap: wrap; }
#stage { border: 1px solid var(--soft); overflow: hidden; background: var(--bg); }
#drawing { display: block; width: 100%; height: auto; max-height: 80vh; }
.layout { display: grid; grid-template-columns: minmax(0, 1fr) 22rem; gap: 1rem; align-items: start; }
@media (max-width: 60rem) { .layout { grid-template-columns: minmax(0, 1fr); } }
#details { border: 1px solid var(--soft); padding: .6rem .8rem; }
.js .detail { display: none; }
.js .detail.open { display: block; }
.detail { list-style: none; margin: 0 0 .8rem; padding: 0; }
dl { margin: 0; } dt { font-weight: 600; margin-top: .35rem; } dd { margin: 0; }
ol#detail-list { padding: 0; margin: 0; }
pre { white-space: pre-wrap; overflow-x: auto; border: 1px solid var(--soft); padding: .6rem; }
.plate polygon { fill: none; stroke: var(--rule); stroke-width: 1; vector-effect: non-scaling-stroke; }
.plate text { fill: var(--muted); font-size: 12px; }
.spine, .edge, .blk, .arrow { fill: none; stroke: var(--rule); stroke-width: 1; vector-effect: non-scaling-stroke; }
.arrow { fill: var(--rule); }
.spine { stroke: var(--soft); }
.node .fl { font-size: 10px; }
.node text { fill: var(--ink); font-size: 12px; paint-order: stroke; stroke: var(--halo); stroke-width: 3px; stroke-linejoin: round; }
.node .blk { fill: var(--bg); }
.node.focus .blk { stroke-width: 3px; stroke-dasharray: 3 2; }
.node.focus .lb { text-decoration: underline; }
.node.selected .lb { font-weight: 700; }
.node.selected .blk { fill: var(--sel); stroke-width: 2px; }
.swatch { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; white-space: pre; }
ul.plain { list-style: none; padding: 0; }
@media (prefers-reduced-motion: no-preference) { .node .blk { transition: stroke-width .12s; } }
@media (prefers-reduced-motion: reduce) { * { animation: none !important; transition: none !important; scroll-behavior: auto !important; } }
"""

SCRIPT = """
(function () {
  'use strict';
  var doc = document;
  var body = doc.body;
  doc.documentElement.className += ' js';
  var stage = doc.getElementById('stage');
  var svg = doc.getElementById('drawing');
  var items = Array.prototype.slice.call(svg.querySelectorAll('.node'));
  var details = Array.prototype.slice.call(doc.querySelectorAll('.detail'));
  var zoomText = doc.getElementById('zoom-level');
  var panKey = doc.getElementById('key-pan');
  var base = svg.getAttribute('viewBox').split(' ').map(Number);
  var levels = [1, 1.5, 2, 3, 4];
  var level = 0;
  var view = base.slice();
  var focusAt = 0;
  var selectedAt = 0;

  function paint() {
    items.forEach(function (node, index) {
      var focused = index === focusAt;
      var selected = index === selectedAt;
      node.classList.toggle('focus', focused);
      node.classList.toggle('selected', selected);
      node.setAttribute('aria-selected', selected ? 'true' : 'false');
      node.querySelector('.fm').textContent = focused ? '>' : '';
      node.querySelector('.sm').textContent = selected ? '*' : '';
    });
    stage.setAttribute('aria-activedescendant', items[focusAt].id);
  }

  function openDetail(index) {
    details.forEach(function (detail) {
      detail.classList.toggle('open', detail.getAttribute('data-for') === items[index].id);
    });
  }

  function setView() {
    view[2] = base[2] / levels[level];
    view[3] = base[3] / levels[level];
    view[0] = Math.max(base[0], Math.min(view[0], base[0] + base[2] - view[2]));
    view[1] = Math.max(base[1], Math.min(view[1], base[1] + base[3] - view[3]));
    svg.setAttribute('viewBox', view.join(' '));
    zoomText.textContent = 'Zoom ' + Math.round(levels[level] * 100) + '%';
    // The pan keys are listed only while the drawing is larger than the view, that is, zoomed in.
    panKey.hidden = level === 0;
  }

  function zoom(next) {
    var middleX = view[0] + view[2] / 2;
    var middleY = view[1] + view[3] / 2;
    level = Math.max(0, Math.min(levels.length - 1, next));
    view[0] = middleX - base[2] / levels[level] / 2;
    view[1] = middleY - base[3] / levels[level] / 2;
    setView();
  }

  function fit() {
    level = 0;
    view = base.slice();
    setView();
  }

  function reveal() {
    if (level === 0) { return; }
    var node = items[focusAt];
    var x = Number(node.getAttribute('data-cx'));
    var y = Number(node.getAttribute('data-cy'));
    if (x < view[0] + 40 || x + 380 > view[0] + view[2] || y < view[1] + 20 || y > view[1] + view[3] - 40) {
      view[0] = x - view[2] / 4;
      view[1] = y - view[3] / 2;
    }
    setView();
  }

  function pan(dx, dy) {
    view[0] += dx * view[2] * 0.15;
    view[1] += dy * view[3] * 0.3;
    setView();
  }

  stage.addEventListener('keydown', function (event) {
    if (event.ctrlKey || event.metaKey || event.altKey) { return; }
    var key = event.key;
    var handled = true;
    if (key === 'ArrowDown') { focusAt = Math.min(items.length - 1, focusAt + 1); }
    else if (key === 'ArrowUp') { focusAt = Math.max(0, focusAt - 1); }
    else if (key === 'Home') { focusAt = focusAt === 0 ? Math.min(1, items.length - 1) : 0; }
    else if (key === 'Enter' || key === ' ') { selectedAt = focusAt; openDetail(selectedAt); }
    else if (key === 'Escape') { selectedAt = 0; openDetail(0); }
    else if (key === '+' || key === '=') { zoom(level + 1); }
    else if (key === '-' || key === '_') { zoom(level - 1); }
    else if (key === '0') { fit(); }
    else if (key === 'ArrowLeft') { pan(-1, 0); }
    else if (key === 'ArrowRight') { pan(1, 0); }
    else if (key === 'PageUp') { pan(0, -1); }
    else if (key === 'PageDown') { pan(0, 1); }
    else { handled = false; }
    if (handled) {
      event.preventDefault();
      paint();
      reveal();
    }
  });

  svg.addEventListener('click', function (event) {
    var node = event.target.closest ? event.target.closest('.node') : null;
    if (!node) { return; }
    focusAt = items.indexOf(node);
    selectedAt = focusAt;
    openDetail(selectedAt);
    paint();
    stage.focus();
  });

  Array.prototype.forEach.call(doc.querySelectorAll('button[data-act]'), function (button) {
    button.addEventListener('click', function () {
      var act = button.getAttribute('data-act');
      if (act === 'zoom-in') { zoom(level + 1); }
      else if (act === 'zoom-out') { zoom(level - 1); }
      else { fit(); }
    });
  });

  paint();
  openDetail(0);
  setView();

  var status = doc.getElementById('live');
  var reloadButton = doc.getElementById('reload');
  if (body.getAttribute('data-live') !== '1' || !status || !reloadButton) { return; }
  var revision = body.getAttribute('data-revision');
  var mode = body.getAttribute('data-mode');
  var observed = body.getAttribute('data-observed') || 'time unknown';
  var address = new URL(body.getAttribute('data-snapshot'), location.href).href;
  var every = Number(body.getAttribute('data-poll')) || 3000;
  var home = location.href;
  try { history.replaceState(null, '', '/'); } catch (ignored) { home = location.href; }

  function valid(snapshot) {
    if (snapshot === null || typeof snapshot !== 'object') { return false; }
    if (snapshot.schema_version === 'workbench-companion-page/1' && snapshot.status === 'ok') {
      return typeof snapshot.revision === 'string' && typeof snapshot.mode === 'string';
    }
    return snapshot.schema_version === 'workbench-companion-page/1' && snapshot.status === 'object_unavailable' && snapshot.revision === null && typeof snapshot.mode === 'string';
  }

  var failures = 0;
  var busy = false;
  var short = function (value) { return String(value).slice(0, 12); };

  function say(kind, text) {
    status.setAttribute('data-state', kind);
    status.textContent = text;
    reloadButton.hidden = kind !== 'stale';
  }

  function poll() {
    if (busy) { return; }
    busy = true;
    var abort = new AbortController();
    var timer = setTimeout(function () { abort.abort(); }, 4000);
    fetch(address, { cache: 'no-store', credentials: 'omit', redirect: 'error', signal: abort.signal })
      .then(function (reply) {
        if (!reply.ok) { throw new Error('status'); }
        return reply.json();
      })
      .then(function (snapshot) {
        if (!valid(snapshot)) { throw new Error('invalid'); }
        failures = 0;
        if (snapshot.revision === revision && snapshot.mode === mode) {
          say('current', 'LIVE: this drawing is the current snapshot (revision ' + short(revision) + ', observed ' + observed + ').');
        } else if (snapshot.revision === null) {
          say('stale', 'STALE: the object can no longer be read; it may have been deleted. This drawing still shows revision ' + short(revision) + ', observed ' + observed + ', and was not redrawn.');
        } else if (snapshot.revision === revision) {
          say('stale', 'STALE: the evidence mode changed from ' + mode + ' to ' + snapshot.mode + '. This drawing still shows revision ' + short(revision) + ', observed ' + observed + ', and was not redrawn.');
        } else {
          say('stale', 'STALE: a newer snapshot exists (revision ' + short(snapshot.revision) + '). This drawing still shows revision ' + short(revision) + ', observed ' + observed + ', and was not redrawn.');
        }
      })
      .catch(function () {
        failures += 1;
        if (failures >= 2) {
          say('disconnected', 'DISCONNECTED: the local listener is not answering. Showing the last snapshot: revision ' + short(revision) + ', observed ' + observed + '.');
        }
      })
      .then(function () {
        clearTimeout(timer);
        busy = false;
      });
  }

  reloadButton.addEventListener('click', function () { location.replace(home); });
  poll();
  setInterval(poll, every);
})();
"""


def _t(value):
    """A value as page text: escaped the way the terminal escapes it (controls, marks, bidirectional overrides as
    \\u escapes), then as HTML."""
    return html.escape(safe_text(value), quote=True)


def _short(value):
    from .workbench_screens import short_id
    return short_id(value)


def _count(number, singular, plural):
    return '%d %s' % (number, singular if number == 1 else plural)


def _csp(script, style, live):
    def source(body):
        return "'sha256-%s'" % base64.b64encode(hashlib.sha256(body.encode('utf-8')).digest()).decode('ascii')
    return "; ".join(("default-src 'none'", 'script-src ' + source(script), 'style-src ' + source(style),
                      "connect-src " + ("'self'" if live else "'none'"), "base-uri 'none'", "form-action 'none'"))


def _live(value):
    """The live settings, checked: a relative snapshot name, a poll interval and the listener's idle limit."""
    if value is None:
        return None
    if (not isinstance(value, dict) or not isinstance(value.get('snapshot'), str)
            or not re.fullmatch(r'[A-Za-z0-9_-]{1,32}', value['snapshot'])
            or not isinstance(value.get('poll_seconds'), int) or isinstance(value.get('poll_seconds'), bool)
            or not 1 <= value['poll_seconds'] <= 60
            or not isinstance(value.get('idle_seconds'), int) or isinstance(value.get('idle_seconds'), bool)
            or value['idle_seconds'] < 1):
        raise AppError('companion_live_invalid', 'Live settings need a relative snapshot name, a poll interval of 1 to 60 seconds and an idle limit.')
    return value


def state_text(node):
    """What a node's state column says: for a policy its mark and the operation word the read model recorded (none
    recorded, expired, prepared, running...), so colour never carries a state; for a kind that has no operation, that
    no state applies. Never "unknown" for a word that is known, and never a state for what cannot have one."""
    from .workbench_screens import MAP_STATE_MARKS
    if not node['state_applies']:
        return '(no state)'
    word = node['operation']
    return '[%s] %s' % (OPERATION_MARKS.get(word) or MAP_STATE_MARKS[node['state']], fit(word, WORD_CELLS, '...'))


def _plates(graph):
    """The plates top to bottom: the selected policy, then every relation group (an empty group stays a plate, so a
    relation appearing later does not move the others) and any other group the graph names."""
    from .workbench_screens import RELATION_GROUPS
    headings = [heading for heading, _ in RELATION_GROUPS]
    headings += [heading for heading in graph['layers'] if heading not in headings]
    drawn = {heading: (edges, cut) for heading, edges, cut in drawn_layers(graph, PLATE_LIMIT)}
    plates = [{'heading': CENTER_HEADING, 'edges': [], 'cut': 0, 'every': [], 'nodes': [graph['center']]}]
    placed = {graph['center']}
    for heading in headings:
        edges, cut = drawn.get(heading, ([], 0))
        nodes = []
        for edge in edges:
            if edge['target'] not in placed:
                placed.add(edge['target'])
                nodes.append(edge['target'])
        plates.append({'heading': heading, 'edges': edges, 'cut': cut, 'nodes': nodes,
                       'every': [edge for edge in graph['edges'] if edge['layer'] == heading]})
    return plates


def _geometry(graph):
    """Where everything goes: from the plates' order and the identifier order inside them, never from a state."""
    positions, plates, y = {}, [], TOP
    for plate in _plates(graph):
        slots = max(len(plate['nodes']), 1) + (1 if plate['cut'] else 0)
        for index, ref in enumerate(plate['nodes']):
            positions[ref] = (LEFT + STEP_X * index, y + STEP_Y * (index + 1))
        plates.append(dict(plate, y=y, slots=slots))
        y += STEP_Y * (slots + 1) + GAP
    return positions, plates, y - GAP + 40


def _block(x, y):
    h, d = BLOCK_HALF, BLOCK_DEPTH
    return ('M%d %d L%d %d L%d %d L%d %d L%d %d L%d %d Z M%d %d L%d %d L%d %d M%d %d L%d %d'
            % (x, y - d, x + h, y, x + h, y + d, x, y + 2 * d, x - h, y + d, x - h, y,
               x - h, y, x, y + d, x + h, y, x, y + d, x, y + 2 * d))


def _shorts(graph):
    return {kind: unique_prefixes([node['id'] for node in graph['nodes'] if node['kind'] == kind])
            for kind in ('group', 'filter')}


def _short_of(shorts, ref):
    kind, identifier = ref.split(':', 1)
    return shorts.get(kind, {}).get(identifier, identifier[:8])


def _filter_notes(graph):
    """A line under a node that a filter bears on: the group an assignment applies a filter to says which filter and its
    type, and the filter says which assignment it applies to, both as the read model stated them."""
    shorts, notes = _shorts(graph), {}
    for edge in graph['edges']:
        if edge['filter'] and edge['target'] not in notes:
            notes[edge['target']] = '+ filter %s %s' % (_short_of(shorts, edge['filter']['ref']), edge['filter']['type'])
        if edge['applies_to'] and edge['target'] not in notes:
            notes[edge['target']] = 'applies to %s' % _short_of(shorts, edge['applies_to'])
    return notes


def _labels(graph):
    """Each drawn node's label: the terminal map's own words, with the relation that reaches it in front. Paths and long
    setting identifiers are cut around an ellipsis so that no two print alike, and carry their kind word."""
    from .workbench_screens import RELATION_LABELS, _map_label
    shorts = _shorts(graph)
    cuts = distinct_labels(graph, LABEL_ROOM, '\u2026')
    first = {}
    for edge in graph['edges']:
        first.setdefault(edge['target'], edge['type'])
    labels = {}
    for node in graph['nodes']:
        relation = 'policy' if node['ref'] == graph['center'] else RELATION_LABELS.get(first.get(node['ref']), (first.get(node['ref']) or 'related').replace('_', ' '))
        if node['kind'] in DISTINCT_KINDS:
            label = ('%s ' % node['kind_word'] if node['kind_word'] != relation else '') + cuts[node['ref']]
        else:
            label = _map_label(node, shorts, None)
        labels[node['ref']] = (relation, label)
    return labels


def drawing(graph):
    """The SVG: plates, the spine, one typed connector per drawn edge and one block per drawn node, in keyboard order."""
    from .workbench_screens import _layer_evidence
    positions, plates, height = _geometry(graph)
    nodes = {node['ref']: node for node in graph['nodes']}
    labels = _labels(graph)
    order = traversal_order(graph, PLATE_LIMIT)
    # The relation that reaches a node leads its label, unless the label already says it (a filter, a scope tag).
    texts = {ref: fit(labels[ref][1] if labels[ref][1].startswith(labels[ref][0] + ' ') else '%s  %s' % labels[ref],
                      LABEL_CELLS, '\u2026') for ref in order}
    notes = _filter_notes(graph)
    width = max([MIN_WIDTH] + [LEFT + STEP_X * plate['slots'] + 20 for plate in plates]
                + [int(positions[ref][0] + LABEL_DX + CHAR_WIDTH * cell_width(texts[ref])) + 20 for ref in order])
    out = ['<svg id="drawing" viewBox="0 0 %d %d" role="presentation" focusable="false">' % (width, height)]
    for plate in plates:
        x, y, length = LEFT, plate['y'], plate['slots']
        corners = [(x, y), (x + length * STEP_X, y + length * STEP_Y), (x + (length - 1) * STEP_X, y + (length + 1) * STEP_Y),
                   (x - STEP_X, y + STEP_Y)]
        heading = plate['heading'] + ('  ' + _layer_evidence(plate['every']) if plate['every'] else '')
        out.append('<g class="plate" data-layer="%s"><polygon points="%s"/><text x="%d" y="%d">%s</text>'
                   % (_t(plate['heading']), ' '.join('%d,%d' % corner for corner in corners), x + 8, y - 8, _t(heading)))
        if not plate['nodes']:
            out.append('<text x="%d" y="%d">none read</text>' % (x + 22, y + STEP_Y + 4))
        if plate['cut']:
            row = max(len(plate['nodes']), 0)
            out.append('<text x="%d" y="%d">%d more not drawn; the workbench Relationships tree lists them all</text>'
                       % (x + STEP_X * row + 22, y + STEP_Y * (row + 1) + 4, plate['cut']))
        out.append('</g>')
    cx, cy = positions[graph['center']]
    reached = [positions[edge['target']][1] for plate in plates for edge in plate['edges']]
    out.append('<path class="spine" d="M%d %d H%d V%d"/>' % (cx - BLOCK_HALF, cy, SPINE_X, max(reached + [cy])))
    for plate in plates:
        for edge in plate['edges']:
            x, y = positions[edge['target']]
            style = EDGE_STYLES.get(edge['type'], EDGE_STYLES['other'])
            out.append('<path class="edge" d="M%d %d H%d" stroke-dasharray="%s" data-from="%s" data-to="%s" data-type="%s"/>'
                       % (SPINE_X, y, x - BLOCK_HALF - 6, style['dash'], _t(edge['source']), _t(edge['target']), _t(edge['type'])))
            out.append('<path class="arrow" d="M%d %d L%d %d L%d %d Z"/>'
                       % (x - BLOCK_HALF - 6, y - 3, x - BLOCK_HALF, y, x - BLOCK_HALF - 6, y + 3))
    for index, ref in enumerate(order):
        node = nodes[ref]
        x, y = positions[ref]
        relation, label = labels[ref]
        kind = node['kind_word']
        text = texts[ref]
        aria = '%s: %s; identifier %s%s' % (kind, label, node['id'], ('; ' + notes[ref]) if ref in notes else '')
        applies = node['state_applies']
        first = index == 0
        note = ('<text class="fl" data-for="%s" x="%d" y="%d">%s</text>' % (_t(ref), x + LABEL_DX, y + 17, _t(notes[ref]))
                if ref in notes else '')
        out.append(
            '<g id="n%d" class="node kind-%s" role="option" aria-selected="%s" aria-label="%s" aria-describedby="s%d" '
            'data-node="%d" data-ref="%s" data-id="%s" data-kind="%s" data-state="%s" data-operation="%s" data-cx="%d" data-cy="%d">'
            '<path class="blk" d="%s"/>'
            '<text class="fm" x="%d" y="%d">%s</text><text class="sm" x="%d" y="%d">%s</text>'
            '<text class="st" id="s%d" x="%d" y="%d">%s</text><text class="lb" x="%d" y="%d">%s</text>%s</g>'
            % (index, _t(node['kind']), 'true' if first else 'false', _t(aria), index, index, _t(node['ref']), _t(node['id']),
               _t(node['kind']), _t(node['state'] if applies else 'none'), _t(node['operation'] if applies else 'none'),
               x, y, _block(x, y),
               x + MARKS_DX, y + 4, '&gt;' if first else '', x + SELECT_DX, y + 4, '*' if first else '',
               index, x + STATE_DX, y + 4, _t(state_text(node)), x + LABEL_DX, y + 4, _t(text), note))
    out.append('</svg>')
    return ''.join(out)


def _swatch(dash):
    """A line pattern as text, so the legend shows each connector's pattern without a second drawing."""
    if dash == 'none':
        return '─' * 8
    numbers = [int(part) for part in dash.split()]
    out = ''
    for position, number in enumerate(numbers):
        out += (('─' * max(1, round(number / 4))) if number > 2 else '·') if position % 2 == 0 else ' ' * max(1, round(number / 4))
    return (out * 2)[:16]


def _legend():
    from .workbench_screens import MAP_STATE_MARKS
    rows = ['<li><span class="swatch">%s</span> %s: %s</li>' % (_t(_swatch(style['dash'])), _t(style['name']), _t(style['meaning']))
            for style in EDGE_STYLES.values()]
    states = ' '.join('<code>%s</code>' % _t('[%s] %s' % (MAP_STATE_MARKS[word], word)) for word in STATES)
    return (
        '<section id="legend" aria-labelledby="h-legend"><h2 id="h-legend">Legend</h2>'
        '<p>Each plate is one relation group, in the terminal map\'s order. Each block is one object. A connector runs from the '
        'selected policy (the line down the left) to the item at its end; its line pattern is its relation, and the same word '
        'starts that item\'s label.</p>'
        '<ul class="plain">%s</ul>'
        '<p>State, always a mark and a word: %s</p>'
        '<p>Only a policy has operations. On a policy the word is the one the read model recorded, so it can be '
        '<code>[_] none recorded</code>, <code>[~] expired</code>, <code>[o] prepared</code> or another recorded word '
        'marked <code>[?]</code>; every other item reads <code>(no state)</code>, which is not a state.</p>'
        '<p><code>&gt; focus</code>: where the keyboard is. <code>* selected</code>: the item whose detail is open. '
        'They are different marks; focus also draws a dashed, heavier outline and selection a bold label.</p>'
        '<p>Colour never carries meaning alone. Position only orders items by identifier within a plate: distance, height and '
        'closeness mean nothing, and no measure is drawn. A connector states a relation the read model reported, with its '
        'evidence class and freshness on its plate, not that anything depends on anything else.</p></section>'
        % (''.join(rows), states))


def _state_detail(node):
    if not node['state_applies']:
        return _t('no operation state applies to a %s' % node['kind_word'])
    # The words the terminal map shows: the operation the read model recorded, and nothing else. The workbench's own
    # state word is the mark, not a second claim, and is never printed as "unknown" beside a word the read model gave.
    return _t('operation %s (recorded by the read model)' % node['operation'])


def _details(graph, labels):
    nodes = {node['ref']: node for node in graph['nodes']}
    items = []
    for index, ref in enumerate(traversal_order(graph, PLATE_LIMIT)):
        node = nodes[ref]
        kind = node['kind_word']
        if node['name']:
            name = _t(node['name'])
        elif node['kind'] == 'group':
            name = 'unresolved identity (the read model resolved no name)'
        else:
            name = 'none stated'
        if ref == graph['center']:
            connectors, route = 'it is the selected policy', ('Open it in the workbench (Inspector, key 2). '
                                                              'This page cannot approve, run or change anything.')
        else:
            edges = [edge for edge in graph['edges'] if edge['target'] == ref]
            connectors = '; '.join(
                '%s, %s, %s' % (_t(edge['type'].replace('_', ' ')), _t(edge['provenance'].replace('_', ' ')), _t(edge['freshness']))
                + (', filter %s, %s' % (_t(edge['filter']['id']), _t(edge['filter']['type'])) if edge['filter'] else '')
                + (', applies to %s' % _t(edge['applies_to'].split(':', 1)[1]) if edge['applies_to'] else '') for edge in edges)
            route = _t(NO_INSPECT % kind)
        items.append(
            '<li class="detail" id="d%d" data-for="n%d"><h3>%s: %s</h3><dl>'
            '<dt>Identifier</dt><dd><code>%s</code></dd><dt>Kind</dt><dd>%s</dd><dt>Name</dt><dd>%s</dd>'
            '<dt>State</dt><dd class="dstate">%s</dd><dt>Connectors</dt><dd>%s</dd><dt>Inspect</dt><dd>%s</dd></dl></li>'
            % (index, index, _t(kind), _t(labels[ref][1]), _t(node['id']), _t(kind), name, _state_detail(node), connectors, route))
    return '<ol id="detail-list">%s</ol>' % ''.join(items)


def _tree(graph):
    """The text alternative when the caller gives none: the graph's edges by plate, with identifiers and evidence."""
    lines = ['[TYPED RELATIONSHIPS]', 'selected policy ' + graph['center'].split(':', 1)[1]]
    for heading, edges, cut in drawn_layers(graph):
        lines.append(heading)
        lines += ['  %s  %s  [%s, %s]' % (edge['type'].replace('_', ' '), edge['target'].split(':', 1)[1], edge['provenance'],
                                           edge['freshness']) for edge in edges]
    return lines


def _bounded(lines):
    lines = [str(line) for line in lines]
    if len(lines) <= TEXT_LINE_LIMIT:
        return lines
    return lines[:TEXT_LINE_LIMIT] + ['%d more lines not shown; the workbench Relationships tree lists them all.'
                                      % (len(lines) - TEXT_LINE_LIMIT)]


def snapshot_record(graph, mode_class=None, observed_at=None):
    """What the listener says about the current snapshot: its revision, its evidence mode and its observation time."""
    from .workbench_screens import mode_word
    return {'schema_version': SCHEMA, 'status': 'ok', 'revision': graph['revision'], 'mode': mode_word(mode_class),
            'observed_at': observed_at if isinstance(observed_at, str) and observed_at else None}


def idle_limit_words(seconds):
    """The idle limit as a person reads it: whole minutes when it is one or more of them, else seconds, singular where
    it is 1 (journey 29 N1: a 2-second limit was printed as "1 minutes")."""
    if seconds >= 60 and seconds % 60 == 0:
        return '%d minute%s' % (seconds // 60, '' if seconds == 60 else 's')
    return '%d second%s' % (seconds, '' if seconds == 1 else 's')


def render_page(graph, *, mode_class=None, tenant=None, observed_at=None, tree_lines=None, live=None):
    """The page for one graph.

    mode_class: the estate's evidence class, as the terminal's context strip reads it (SYNTHETIC, CAPTURE, ...).
    tenant, observed_at: shown as stated; a missing time reads "observation time unknown" and is never invented.
    tree_lines: the canonical relationship tree (the terminal's relationship_lines), the page's text alternative.
    live: None for a static file, or {'snapshot': name, 'poll_seconds': n, 'idle_seconds': n} for the local listener.
    """
    from .workbench_screens import mode_word
    live = _live(live)
    mode = mode_word(mode_class)
    when = observed_at if isinstance(observed_at, str) and observed_at else None
    nodes = {node['ref']: node for node in graph['nodes']}
    center = nodes[graph['center']]
    labels = _labels(graph)
    drawn_edges = sum(len(edges) for _, edges, _ in drawn_layers(graph, PLATE_LIMIT))
    policy = '%s (%s)' % (center['name'] or '(no name)', _short(center["id"]))
    revision = graph['revision']
    if live:
        status = 'LIVE: checking the local listener for a newer snapshot...'
        note = ('Live mode ends when the command ends, or %s after this page was last loaded; after that this page '
                'shows DISCONNECTED and keeps the last snapshot. The address of this page is a secret: anyone on the same machine '
                'who has it can read this page, because users of one machine are not isolated from each other. After it loads, '
                'this page replaces the address in the address bar with "/", so use the button to load a newer snapshot, not the '
                'browser\'s reload; the browser may still keep the address in its history.'
                % idle_limit_words(live['idle_seconds']))
        body_live = (' data-live="1" data-snapshot="%s" data-poll="%d"' % (_t(live['snapshot']), live['poll_seconds'] * 1000))
    else:
        status = ('STATIC FILE: this page does not update itself. It shows revision %s, %s. To see a newer snapshot, '
                  'write the file again with %s or use live mode: from a shell, run %s instead of --out FILE; the product '
                  'prints its secret address.'
                  % (revision[:12], ('observed ' + _t(when)) if when else 'observation time unknown',
                     COMPANION_WRITE, COMPANION_SERVE))
        note = 'This file was written once; nothing on it reads the workbench again.'
        body_live = ''
    lines = _bounded(tree_lines if tree_lines is not None else _tree(graph))
    summary = '%s from the selected policy; %s drawn, %s not drawn' % (
        count_words(graph),
        _count(drawn_edges, 'item', 'items'), _count(len(graph['edges']) - drawn_edges, 'item', 'items'))
    if graph.get('excluded'):
        summary += '; %s without a target not drawn' % _count(graph['excluded'], 'edge', 'edges')
    svg = drawing(graph)
    tenant_part = (' | TENANT ' + _t(_short(tenant))) if tenant else ''
    head = (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta http-equiv="Content-Security-Policy" content="%s">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n<meta name="referrer" content="no-referrer">\n'
        '<title>Relationship companion: %s | %s</title>\n<style>%s</style>\n</head>\n'
        % (_csp(SCRIPT, CSS, bool(live)), _t(policy), _t(mode), CSS))
    body = (
        '<body data-revision="%s" data-mode="%s" data-observed="%s"%s>\n'
        '<a class="skip" href="#text-alternative">Skip to the text alternative</a>\n'
        '<header>\n<h1>Relationship companion (read only)</h1>\n'
        '<p id="evidence">%s%s | POLICY %s</p>\n'
        '<p id="snapshot-line">Snapshot revision <code>%s</code> | %s | evidence mode %s</p>\n'
        '<p id="live" role="status" aria-live="polite" data-state="%s">%s</p>\n'
        '<button type="button" id="reload" hidden>Load the newer snapshot</button>\n'
        '<noscript><p>The keyboard, zoom and live checks need this page\'s script. Without it this page does not update itself; '
        'the detail and the text alternative below are complete.</p></noscript>\n'
        '<p id="note">%s It has no approve, run or navigate operation.</p>\n</header>\n'
        '<main>\n<div class="layout">\n<section id="drawing-section" aria-labelledby="h-drawing">\n'
        '<h2 id="h-drawing">Isometric drawing</h2>\n<p id="summary">%s.</p>\n'
        '<div id="controls" role="toolbar" aria-label="Zoom">'
        '<button type="button" data-act="zoom-in" aria-label="Zoom in (plus key)">Zoom in +</button>'
        '<button type="button" data-act="zoom-out" aria-label="Zoom out (minus key)">Zoom out -</button>'
        '<button type="button" data-act="fit" aria-label="Fit the whole drawing (zero key)">Fit 0</button>'
        '<span id="zoom-level" aria-live="polite">Zoom 100%%</span></div>\n'
        '<div id="stage" tabindex="0" role="listbox" aria-label="Relationship drawing, %s, press Enter on an item for its detail" '
        'aria-describedby="keys" aria-activedescendant="n0">%s</div>\n</section>\n'
        '<section id="details" aria-labelledby="h-details"><h2 id="h-details">Detail</h2>%s</section>\n</div>\n'
        '%s\n'
        '<section id="keys" aria-labelledby="h-keys"><h2 id="h-keys">Keys</h2><ul>'
        '<li>Up, Down: move focus to the previous or next item, in the order of the terminal map.</li>'
        '<li>Home: follow the connector to the other end (from the policy to its first neighbour, from any item to the policy).</li>'
        '<li>Enter, Space: select the focused item and show its detail.</li>'
        '<li>Escape: select the policy again.</li>'
        '<li id="key-pan" hidden>Left, Right, Page Up, Page Down: pan the drawing while it is zoomed in. At 100%% the whole '
        'drawing is in view and nothing pans.</li>'
        '<li>+ zoom in, - zoom out, 0 fit the whole drawing; the buttons do the same.</li></ul></section>\n'
        '<section id="text-alternative" aria-labelledby="h-text"><h2 id="h-text">Text alternative: the relationship tree</h2>'
        '<pre>%s</pre></section>\n</main>\n<script>%s</script>\n</body>\n</html>\n'
        % (_t(revision), _t(mode), _t(when or ''), body_live, _t(mode), tenant_part, _t(policy), _t(revision),
           ('observed ' + _t(when)) if when else 'observation time unknown', _t(mode), 'live' if live else 'static', status, note,
           summary, _t(policy), svg, _details(graph, labels), _legend(), '\n'.join(_t(line) for line in lines), SCRIPT))
    return head + body
