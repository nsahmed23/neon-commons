"""The isometric companion page (requirement 17 UX-VIS, second slice, item 1: the page).

The page is drawn from the same typed graph projection the terminal map reads (the UXVIS-1 fixture: one policy,
three groups including an exclusion, one filter, two scope tags, one repository source), so the identifiers and the
keyboard order are the terminal map's. The structure checks are the brief's: nothing external of any kind, every
label escaped, every node's identifier the projection's, a legend and a text alternative. The replay cases are
Astra's: a state change moves nothing, reordered input draws the same, duplicate labels stay distinguishable by
identifier, filtering and deletion change the revision, and a thousand-policy corpus keeps the page bounded.
Temporary directories only; no network.
"""
import base64
from collections import Counter
import copy
import hashlib
import html
from html.parser import HTMLParser
import re
import tempfile
import unittest

from intune_iac.workbench_tui import safe_text
from plugin_tests.test_graph_projection import synthetic_policy

STATES = ('queued', 'running', 'waiting', 'blocked', 'failed', 'cancelled', 'unknown', 'verified')
STATE_TEXT = re.compile(r'(<text class="st"[^>]*>)[^<]*(</text>)')
DATA_STATE = re.compile(r'data-(state|operation)="[^"]*"')
EXTERNAL = re.compile(r'(?i)(https?:|ftp:|wss?:|//[a-z0-9]|(?-i:\burl\s*\()|@import|\bsrc\s*=|xlink:href|<link|<img|<iframe|<object|'
                      r'<embed|<base|<form|<video|<audio|<source)')


def masked(svg):
    """The drawing with every state mark and word replaced: what a state change is allowed to differ in."""
    return DATA_STATE.sub(r'data-\1="M"', STATE_TEXT.sub(r'\1M\2', svg))


class Page(HTMLParser):
    """The page as a reader sees it: tags, attributes and text, in order."""
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.tags, self.stack, self.texts, self.attrs = [], [], {}, []
        self.script, self.style = '', ''
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attrs.append((tag, dict(attrs)))
        self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in self.stack:
            while self.stack.pop() != tag:
                pass

    def handle_data(self, data):
        if self.stack and self.stack[-1] == 'script':
            self.script += data
        elif self.stack and self.stack[-1] == 'style':
            self.style += data

    def where(self, tag, **wanted):
        return [attrs for name, attrs in self.attrs if name == tag and all(attrs.get(k) == v for k, v in wanted.items())]

    def nodes(self):
        return [attrs for name, attrs in self.attrs if name == 'g' and 'node' in (attrs.get('class') or '').split()]


def section(text, ident):
    """The inner markup of the element with this id (the page nests no section in a section)."""
    match = re.search(r'<(\w+)[^>]*\bid="%s"[^>]*>(.*?)</\1>' % re.escape(ident), text, re.S)
    return match.group(2) if match else None


def svg_of(text):
    match = re.search(r'<svg\b.*?</svg>', text, re.S)
    return match.group(0) if match else ''


class Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.store, cls.value, cls.truth, cls.policy = synthetic_policy(cls.temp.name)
        cls.object_id = cls.policy['id']

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def graph(self, value=None, **kw):
        from intune_iac.graph_projection import project
        return project(self.value if value is None else value, **kw)

    def page(self, value=None, *, live=None, mode_class='synthetic_local_process_only', tree=True, **kw):
        from intune_iac.companion_page import render_page
        from intune_iac.workbench_screens import relationship_lines
        value = self.value if value is None else value
        graph = self.graph(value, **kw)
        lines = relationship_lines(value, 100, 'unicode') if tree else None
        return render_page(graph, mode_class=mode_class, tenant=self.truth['tenant_id'], observed_at='2026-10-15T12:00:00Z',
                           tree_lines=lines, live=live)

    def groups(self):
        return sorted(node['id'] for node in self.graph()['nodes'] if node['kind'] == 'group')


class StructureTests(Fixture):
    def test_the_page_is_self_contained_and_its_policy_allows_nothing_external(self):
        text = self.page()
        self.assertIsNone(EXTERNAL.search(text), EXTERNAL.search(text) and EXTERNAL.search(text).group(0))
        parsed = Page(text)
        counts = Counter(parsed.tags)
        self.assertEqual((counts['script'], counts['style']), (1, 1))
        for tag in ('link', 'img', 'iframe', 'object', 'embed', 'base', 'form', 'input', 'audio', 'video', 'source', 'a'):
            if tag == 'a':
                for attrs in parsed.where('a'):
                    self.assertTrue(attrs.get('href', '').startswith('#'), attrs)
            else:
                self.assertEqual(counts[tag], 0, tag)
        for _, attrs in parsed.attrs:
            self.assertNotIn('style', attrs, 'an inline style attribute would need unsafe-hashes')
            self.assertFalse([name for name in attrs if name.startswith('on')], attrs)
        meta = parsed.where('meta', **{'http-equiv': 'Content-Security-Policy'})
        self.assertEqual(len(meta), 1)
        policy = dict(part.strip().split(' ', 1) for part in meta[0]['content'].split(';') if part.strip())
        self.assertEqual(policy['default-src'], "'none'")
        self.assertEqual(policy['connect-src'], "'none'")
        self.assertEqual(policy['base-uri'], "'none'")
        self.assertEqual(policy['form-action'], "'none'")
        for directive, body in (('script-src', parsed.script), ('style-src', parsed.style)):
            wanted = "'sha256-%s'" % base64.b64encode(hashlib.sha256(body.encode('utf-8')).digest()).decode('ascii')
            self.assertEqual(policy[directive], wanted, directive)
        for value in policy.values():
            self.assertNotIn('unsafe', value)
            self.assertNotIn('*', value)
            self.assertNotIn('http', value)
            self.assertNotIn('data:', value)

    def test_a_live_page_may_ask_only_its_own_origin_for_the_snapshot(self):
        text = self.page(live={'snapshot': 'snapshot', 'poll_seconds': 3, 'idle_seconds': 1800})
        parsed = Page(text)
        meta = parsed.where('meta', **{'http-equiv': 'Content-Security-Policy'})[0]['content']
        self.assertIn("connect-src 'self'", meta)
        self.assertIn("default-src 'none'", meta)
        self.assertIsNone(EXTERNAL.search(text))
        body = parsed.where('body')[0]
        self.assertEqual((body['data-live'], body['data-snapshot']), ('1', 'snapshot'))
        # The script holds no write channel: it reads one relative address and never sends a body or a method.
        for word in ('POST', 'PUT', 'DELETE', 'method', 'XMLHttpRequest', 'WebSocket', 'sendBeacon', 'postMessage',
                     'localStorage', 'sessionStorage', 'eval(', 'Function(', 'innerHTML', 'outerHTML', 'document.write',
                     'import(', 'window.open', 'target='):
            self.assertNotIn(word, parsed.script, word)
        self.assertEqual(parsed.script.count('fetch('), 1)
        self.assertEqual(parsed.script.count('location.replace('), 1)
        self.assertNotIn('reload(', parsed.script)

    def test_every_label_is_escaped(self):
        hostile = '<script>alert(1)</script>"&\'\x1b[31m‮'
        trap = '"><img src=x onerror=alert(1)>'
        groups = self.groups()
        value = dict(self.value, name=hostile)
        text = self.page(value, names={groups[0]: trap, groups[1]: '</script><svg onload=alert(2)>'})
        parsed = Page(text)
        self.assertEqual(Counter(parsed.tags)['script'], 1)
        for tag in ('img', 'svg'):
            self.assertEqual(Counter(parsed.tags)[tag], 1 if tag == 'svg' else 0, tag)
        self.assertNotIn('<img', text)
        self.assertNotIn('\x1b', text)
        self.assertNotIn('‮', text)
        self.assertIn('\\u202e', text)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', text)
        self.assertIn('&lt;/script&gt;&lt;svg onload=alert(2)&gt;', text)
        self.assertIn('&quot;&gt;&lt;img src=x onerror=alert(1)&gt;', text)
        # No attribute became an event handler or a new element.
        for _, attrs in parsed.attrs:
            self.assertFalse([name for name in attrs if name.startswith('on')], attrs)
            self.assertNotIn('src', attrs)

    def test_every_nodes_identifier_is_the_projections(self):
        graph = self.graph()
        parsed = Page(self.page())
        drawn = [(attrs['data-ref'], attrs['data-id'], attrs['data-kind']) for attrs in parsed.nodes()]
        self.assertEqual(sorted(drawn), sorted((node['ref'], node['id'], node['kind']) for node in graph['nodes']))
        self.assertEqual(len(drawn), len({ref for ref, _, _ in drawn}))
        policy = [attrs for attrs in parsed.nodes() if attrs['data-kind'] == 'policy']
        self.assertEqual([attrs['data-id'] for attrs in policy], [self.object_id])
        # The detail panel names the same identifier in full for every node.
        details = section(self.page(), 'details')
        for node in graph['nodes']:
            self.assertIn(node['id'], details)

    def test_an_unresolved_group_stays_an_unresolved_identity_with_its_identifier(self):
        text = self.page()
        groups = self.groups()
        self.assertEqual(len(groups), 3)
        for identifier in groups:
            self.assertIn(identifier, text)
            self.assertIn('Unresolved group identity %s' % identifier[:8], svg_of(text))
        self.assertNotIn('All Users', text)
        self.assertNotIn('All Devices', text)
        # A name the read model resolved is shown beside the identity, never instead of it.
        named = self.page(names={groups[0]: 'Pilot devices'})
        self.assertIn('Pilot devices (%s)' % groups[0][:8], svg_of(named))
        self.assertIn(groups[0], named)

    def test_the_legend_states_every_connector_and_every_mark(self):
        from intune_iac.companion_page import EDGE_STYLES
        legend = section(self.page(), 'legend')
        self.assertIsNotNone(legend)
        for relation in ('assignment', 'exclusion', 'filter', 'setting', 'scope_tag', 'generated_from', 'repository'):
            self.assertIn(relation, EDGE_STYLES)
        patterns = [style['dash'] for style in EDGE_STYLES.values()]
        self.assertEqual(len(patterns), len(set(patterns)), 'every connector type has its own line pattern')
        for relation in ('assignment', 'exclusion', 'filter', 'setting', 'scope tag', 'repository'):
            self.assertIn(relation, legend)
        for word in STATES:
            self.assertIn(word, legend)
        for mark in ('[x] verified', '[+] running', '[.] queued', '[:] waiting', '[!] blocked', '[#] failed', '[-] cancelled',
                     '[?] unknown'):
            self.assertIn(mark, legend)
        for sentence in ('focus', 'selected', 'colour', 'position'):
            self.assertIn(sentence, legend.lower())
        self.assertIn('no measure', legend.lower())

    def test_the_canonical_text_tree_is_the_text_alternative(self):
        from intune_iac.workbench_screens import relationship_lines
        text = self.page()
        alternative = section(text, 'text-alternative')
        self.assertIsNotNone(alternative)
        self.assertIn('<pre', alternative)
        for line in relationship_lines(self.value, 100, 'unicode'):
            self.assertIn(html.escape(safe_text(line), quote=True), alternative)
        self.assertIn('[TYPED RELATIONSHIPS]', alternative)
        for node in self.graph()['nodes']:
            self.assertIn(node['id'], alternative)
        self.assertIn('href="#text-alternative"', text)
        # Without a tree from the caller the page still carries one, read from the same graph.
        bare = self.page(tree=False)
        self.assertIn(self.object_id, section(bare, 'text-alternative'))

    def test_the_page_carries_the_revision_the_capture_time_and_the_evidence_mode(self):
        graph = self.graph()
        text = self.page()
        header = section(text, 'snapshot-line')
        self.assertIn(graph['revision'], header)
        self.assertIn('2026-10-15T12:00:00Z', header)
        self.assertIn('SYNTHETIC', section(text, 'evidence'))
        self.assertIn('SYNTHETIC', header)
        self.assertEqual(Page(text).where('body')[0]['data-revision'], graph['revision'])
        for mode, word in (('graph_capture_unverified', 'CAPTURE'), ('graph_reader_laboratory', 'LABORATORY'),
                           ('graph_authenticated_observation', 'LIVE READ-ONLY'), ('mixed_observations', 'MIXED'),
                           (None, 'MODE UNKNOWN'), ('invented', 'MODE UNKNOWN')):
            self.assertIn(word, section(self.page(mode_class=mode), 'evidence'), mode)
        # Without a time the page says so; it never invents one.
        from intune_iac.companion_page import render_page
        self.assertIn('observation time unknown', render_page(graph, mode_class='synthetic'))

    def test_a_static_page_says_plainly_that_it_does_not_update_itself(self):
        text = self.page()
        status = section(text, 'live')
        self.assertIn('STATIC FILE', status)
        self.assertIn('does not update itself', status)
        self.assertIn(self.graph()['revision'][:12], status)
        self.assertNotIn('data-live', Page(text).where('body')[0])

    def test_a_live_page_names_stale_and_disconnected_and_never_redraws_by_itself(self):
        script = Page(self.page(live={'snapshot': 'snapshot', 'poll_seconds': 3, 'idle_seconds': 1800})).script
        self.assertIn('STALE', script)
        self.assertIn('DISCONNECTED', script)
        self.assertIn('was not redrawn', script)
        # The only way to a newer drawing is the reader's own click on the reload button.
        reload_at = script.index('location.replace(')
        self.assertIn("addEventListener('click'", script[:reload_at][-200:])
        self.assertNotIn('replaceChildren', script)
        self.assertNotIn('appendChild', script)
        text = self.page(live={'snapshot': 'snapshot', 'poll_seconds': 3, 'idle_seconds': 1800})
        status = section(text, 'live')
        self.assertIn('LIVE', status)
        self.assertIn('checking', status)
        self.assertIn('30 minutes', text)
        self.assertEqual(len(Page(text).where('button', id='reload')), 1)

    def test_the_page_is_deterministic_and_uses_line_feeds_only(self):
        self.assertEqual(self.page(), self.page())
        self.assertNotIn('\r', self.page())
        text = self.page()
        self.assertTrue(text.startswith('<!DOCTYPE html>\n'))
        self.assertTrue(text.endswith('</html>\n'))
        parsed = Page(text)
        self.assertEqual(parsed.where('html')[0]['lang'], 'en')
        self.assertEqual(len(parsed.where('meta', charset='utf-8')), 1)
        self.assertEqual(len(parsed.where('title')), 1)


class KeyboardAndAccessibilityTests(Fixture):
    def test_the_dom_order_is_the_terminal_maps_traversal_order(self):
        from intune_iac.workbench_screens import map_order
        graph = self.graph()
        order = [attrs['data-ref'] for attrs in Page(self.page()).nodes()]
        self.assertEqual(order, map_order(graph))
        self.assertEqual(order[0], graph['center'])
        for index, attrs in enumerate(Page(self.page()).nodes()):
            self.assertEqual(attrs['id'], 'n%d' % index)
            self.assertEqual(attrs['data-node'], str(index))

    def test_the_stage_is_one_tab_stop_and_names_its_keys(self):
        text = self.page()
        parsed = Page(text)
        stage = parsed.where('div', id='stage')[0]
        self.assertEqual(stage['tabindex'], '0')
        self.assertEqual(stage['role'], 'listbox')
        self.assertEqual(stage['aria-activedescendant'], 'n0')
        self.assertIn('aria-label', stage)
        self.assertEqual(stage['aria-describedby'], 'keys')
        keys = section(text, 'keys')
        for key in ('Up', 'Down', 'Home', 'Enter', 'Escape', 'Left', 'Right', '+', '-', '0'):
            self.assertIn(key, keys)
        for attrs in parsed.nodes():
            self.assertEqual(attrs['role'], 'option')
            self.assertIn(attrs['aria-selected'], ('true', 'false'))
            self.assertTrue(attrs['aria-label'])
            self.assertTrue(attrs['aria-describedby'])
        script = parsed.script
        for key in ('ArrowDown', 'ArrowUp', 'ArrowLeft', 'ArrowRight', 'Home', 'Enter', 'Escape'):
            self.assertIn("'%s'" % key, script)

    def test_zoom_and_fit_are_reachable_by_key_and_by_button(self):
        text = self.page()
        parsed = Page(text)
        buttons = {attrs['data-act']: attrs for attrs in parsed.where('button') if 'data-act' in attrs}
        self.assertEqual(set(buttons), {'zoom-in', 'zoom-out', 'fit'})
        for attrs in buttons.values():
            self.assertEqual(attrs['type'], 'button')
            self.assertTrue(attrs['aria-label'])
        self.assertIn("'+'", parsed.script)
        self.assertIn("'-'", parsed.script)
        self.assertIn("'0'", parsed.script)
        self.assertEqual(len(parsed.where('span', id='zoom-level')), 1)
        # The drawing's viewBox holds the whole drawing, so Fit is the starting state and zoom is reversible.
        box = Page(text).where("svg")[0]["viewbox"].split()
        self.assertEqual(box[:2], ['0', '0'])

    def test_focus_is_drawn_distinct_from_selection(self):
        text = self.page()
        parsed = Page(text)
        self.assertIn('.node.focus', parsed.style)
        self.assertIn('.node.selected', parsed.style)
        focus_rule = re.search(r'\.node\.focus[^{]*\{([^}]*)\}', parsed.style).group(1)
        selected_rule = re.search(r'\.node\.selected[^{]*\{([^}]*)\}', parsed.style).group(1)
        self.assertNotEqual(focus_rule, selected_rule)
        for rule in (focus_rule, selected_rule):
            self.assertNotRegex(rule, r'^\s*(fill|stroke)\s*:[^;]*;?\s*$')
        # Both are also marks in the text: the first node starts focused and selected, the rest carry neither.
        svg = svg_of(text)
        self.assertEqual(len(re.findall(r'<text class="fm"[^>]*>&gt;</text>', svg)), 1)
        self.assertEqual(len(re.findall(r'<text class="sm"[^>]*>\*</text>', svg)), 1)
        nodes = parsed.nodes()
        self.assertEqual([attrs['aria-selected'] for attrs in nodes], ['true'] + ['false'] * (len(nodes) - 1))
        legend = section(text, 'legend')
        self.assertIn('&gt; focus', legend)
        self.assertIn('* selected', legend)

    def test_reduced_motion_leaves_no_motion(self):
        css = Page(self.page()).style
        self.assertIn('prefers-reduced-motion: reduce', css)
        reduce_block = css[css.index('prefers-reduced-motion: reduce'):]
        self.assertIn('animation: none', reduce_block)
        self.assertIn('transition: none', reduce_block)
        self.assertIn('scroll-behavior: auto', reduce_block)
        # Motion exists only where the reader has not asked for less.
        outside = css.replace(reduce_block, '')
        for word in ('animation', 'transition', 'scroll-behavior'):
            for match in re.finditer(word, outside):
                self.assertIn('prefers-reduced-motion: no-preference', outside[:match.start()].rsplit('@media', 1)[-1],
                              'motion outside the no-preference query: ' + outside[match.start() - 40:match.start() + 40])
        # No progress is invented: the page has no percentage, estimate or progress element.
        text = self.page()
        self.assertNotIn('<progress', text)
        self.assertNotRegex(text, r'\bETA\b')

    def test_no_meaning_rests_on_colour_alone(self):
        text = self.page()
        svg = svg_of(text)
        nodes = Page(text).nodes()
        states = re.findall(r'<text class="st"[^>]*>([^<]*)</text>', svg)
        self.assertEqual(len(states), len(nodes))
        for word in states:
            self.assertRegex(word, r'^(\[[x+.:!#?_~o-]\] [a-z_ ]+|\(no state\))$')
        # Every connector carries its relation as a word in its node's label as well as a line pattern.
        labels = re.findall(r'<text class="lb"[^>]*>([^<]*)</text>', svg)
        self.assertEqual(len(labels), len(nodes))
        self.assertEqual(sum(label.startswith('exclusion') for label in labels), 1)
        # A label that already names its relation does not say it twice.
        for twice in ('filter  filter', 'filter filter', 'scope tag  scope tag', 'scope tag scope tag'):
            self.assertNotIn(twice, svg)
        self.assertEqual(sum(label.startswith('filter ') for label in labels), 1)
        self.assertEqual(sum(label.startswith('scope tag ') for label in labels), 2)
        edges = re.findall(r'<path class="edge[^"]*"[^>]*stroke-dasharray="([^"]*)"[^>]*data-type="([^"]*)"', svg)
        by_type = {}
        for pattern, relation in edges:
            by_type.setdefault(relation, set()).add(pattern)
        self.assertTrue(all(len(patterns) == 1 for patterns in by_type.values()))
        self.assertEqual(len({next(iter(patterns)) for patterns in by_type.values()}), len(by_type))
        # No colour is named in the markup: colours live in the style sheet, as variables, and the text is complete without them.
        self.assertNotRegex(svg, r'(?i)(fill|stroke|color)="#?[a-z0-9]+"')

    def test_every_node_has_a_detail_to_drill_into(self):
        text = self.page()
        parsed = Page(text)
        details = parsed.where('li', **{'class': 'detail'})
        self.assertEqual(sorted(attrs['data-for'] for attrs in details), sorted(attrs['id'] for attrs in parsed.nodes()))
        panel = section(text, 'details')
        self.assertIn('no inspect route', panel)
        self.assertIn('Inspector', panel)
        # Without the script every detail is on the page; with it only the open one shows.
        self.assertIn('.js .detail', parsed.style)


class ReplayTests(Fixture):
    def test_a_state_change_keeps_every_nodes_position(self):
        from intune_iac.companion_page import drawing
        groups = self.groups()
        base = drawing(self.graph(freshness='fresh'))
        seen = set()
        for state in ('queued', 'running', 'blocked', 'unknown', 'verified', 'failed'):
            states = {self.object_id: state, groups[0]: state, groups[2]: STATES[(STATES.index(state) + 3) % 8]}
            changed = drawing(self.graph(freshness='fresh', states=states))
            seen.add(changed)
            self.assertEqual(masked(changed), masked(base), state)
        self.assertGreater(len(seen), 1, 'the states are drawn, so the unmasked drawings differ')
        # The coordinates are a function of identity and topology alone.
        def coordinates(svg):
            return re.findall(r'data-c[xy]="\d+"|\sd="[^"]*"|points="[^"]*"|\sx="\d+" y="\d+"', svg)
        self.assertEqual(coordinates(drawing(self.graph(states={self.object_id: 'running'}))), coordinates(base))

    def test_a_state_change_changes_the_revision_and_only_the_state_marks_in_the_drawing(self):
        from intune_iac.companion_page import drawing
        a, b = self.graph(), self.graph(states={self.object_id: 'blocked'})
        self.assertNotEqual(a['revision'], b['revision'])
        self.assertIn('[!] blocked', drawing(b))
        self.assertNotIn('[!] blocked', drawing(a))
        self.assertNotIn(b['revision'], drawing(b), 'the revision is on the page header, not in the drawing')

    def test_reordered_input_gives_the_same_drawing(self):
        from intune_iac.companion_page import drawing
        reordered = dict(self.value, relationships=list(reversed(self.value['relationships'])))
        shuffled = dict(self.value, relationships=self.value['relationships'][3:] + self.value['relationships'][:3])
        base = drawing(self.graph(freshness='fresh'))
        self.assertEqual(drawing(self.graph(reordered, freshness='fresh')), base)
        self.assertEqual(drawing(self.graph(shuffled, freshness='fresh')), base)
        self.assertEqual(self.graph(reordered)['revision'], self.graph()['revision'])
        order = lambda value: [attrs['data-ref'] for attrs in Page(self.page(value)).nodes()]
        self.assertEqual(order(reordered), order(self.value))

    def test_duplicate_labels_stay_distinguishable_by_identifier(self):
        from intune_iac.companion_page import drawing
        groups = self.groups()
        names = {groups[0]: 'Pilot devices', groups[1]: 'Pilot devices', groups[2]: 'Pilot devices'}
        text = self.page(names=names)
        svg = svg_of(text)
        labels = [label for label in re.findall(r'<text class="lb"[^>]*>([^<]*)</text>', svg) if 'Pilot devices' in label]
        self.assertEqual(len(labels), 3)
        self.assertEqual(len(set(labels)), 3, labels)
        ids = {attrs['data-id'] for attrs in Page(text).nodes() if attrs['data-kind'] == 'group'}
        self.assertEqual(ids, set(groups))
        for identifier in groups:
            self.assertEqual(sum(identifier in label or identifier[:8] in label for label in labels), 1)
        # Two groups that share their first eight characters are told apart by a longer prefix, as in the terminal map.
        close = ['0123abcd-0000-4000-8000-000000000001', '0123abcd-0000-4000-8000-000000000002']
        value = dict(self.value, relationships=[
            {'relation': 'assignment', 'target_id': ident, 'details': {'group_id': ident}, 'assertion_class': 'observed'}
            for ident in close])
        labels = re.findall(r'<text class="lb"[^>]*>([^<]*)</text>', svg_of(self.page(value)))
        self.assertEqual(len({label for label in labels if 'Unresolved' in label}), 2)
        self.assertTrue(drawing(self.graph(value)))

    def test_filtering_and_deletion_change_the_revision_and_the_page(self):
        base = self.graph()
        without = lambda relation: dict(self.value, relationships=[e for e in self.value['relationships'] if e['relation'] != relation])
        filtered, scoped = self.graph(without('filter')), self.graph(without('scope_tag'))
        group = self.groups()[0]
        deleted = self.graph(dict(self.value, relationships=[e for e in self.value['relationships'] if e['target_id'] != group]))
        gone = self.graph(dict(self.value, relationships=[]))
        revisions = {base['revision'], filtered['revision'], scoped['revision'], deleted['revision'], gone['revision']}
        self.assertEqual(len(revisions), 5)
        page = self.page(dict(self.value, relationships=[e for e in self.value['relationships'] if e['target_id'] != group]))
        self.assertIn(deleted['revision'], page)
        self.assertNotIn(group, svg_of(page))
        self.assertNotIn(base['revision'], page)
        # A policy with nothing read still draws, says so on each plate, and invents no node.
        empty = self.page(dict(self.value, relationships=[], selected_repository=None))
        self.assertEqual(len(Page(empty).nodes()), 1)
        self.assertIn('none read', svg_of(empty))

    def test_a_thousand_policy_corpus_keeps_every_page_bounded(self):
        from intune_iac.companion_page import PLATE_LIMIT, render_page
        sizes, cut_pages = [], 0
        for number in range(1000):
            identifier = '%08x-0000-4000-8000-%012x' % (number, number)
            relations = []
            for index in range(number % 7 + 1):
                group = '%08x-1111-4000-8000-%012x' % ((number + index) % 60, index)
                relations.append({'relation': 'assignment' if index % 3 else 'exclusion', 'target_id': group,
                                  'details': {'group_id': group}, 'assertion_class': 'observed'})
            relations += [{'relation': 'setting', 'target_id': 'setting_%03d' % index, 'details': {}, 'assertion_class': 'observed'}
                          for index in range(number % 40)]
            value = {'object_id': identifier, 'name': 'Policy %d' % number, 'relationships': relations, 'observed_at': None}
            graph = self.graph(value)
            page = render_page(graph, mode_class='synthetic', tenant='t', observed_at=None, tree_lines=['[TYPED RELATIONSHIPS]'])
            sizes.append(len(page))
            settings = number % 40
            if settings > PLATE_LIMIT:
                cut_pages += 1
                self.assertIn('%d more not drawn' % (settings - PLATE_LIMIT), page)
            self.assertLessEqual(len(Page(page).nodes()), 1 + 3 * PLATE_LIMIT + 6)
        self.assertGreater(cut_pages, 500)
        self.assertLess(max(sizes), 120000)
        self.assertLess(max(sizes), 2 * min(sizes) + 60000, 'the page does not grow with the corpus or the policy')

    def test_a_policy_with_a_thousand_edges_draws_a_bounded_page_and_says_how_many_are_not_drawn(self):
        from intune_iac.companion_page import PLATE_LIMIT, TEXT_LINE_LIMIT
        relations = [{'relation': 'setting', 'target_id': 'setting_%04d' % index, 'details': {}, 'assertion_class': 'observed'}
                     for index in range(1000)]
        value = dict(self.value, relationships=relations, selected_repository=None)
        text = self.page(value)
        self.assertIn('%d more not drawn' % (1000 - PLATE_LIMIT), svg_of(text))
        self.assertEqual(len(Page(text).nodes()), 1 + PLATE_LIMIT)
        self.assertLess(len(text), 150000)
        alternative = section(text, 'text-alternative')
        self.assertLessEqual(alternative.count('\n'), TEXT_LINE_LIMIT + 3)
        self.assertRegex(alternative, r'\d+ more lines not shown')
        # What was cut is said, never silently dropped: the graph's own count of nodes is on the page.
        self.assertIn('1000 relationships', section(text, 'summary'))


class TruthTests(Fixture):
    """PKG-UXVIS-1b part A on the page: what is known, and no more."""

    def states_of(self, text):
        svg = svg_of(text)
        return {attrs['data-kind'] + ':' + attrs['data-id']: attrs for attrs in Page(text).nodes()}, \
            re.findall(r'<text class="st"[^>]*>([^<]*)</text>', svg)

    def test_a_kind_without_an_operation_reads_no_state_and_never_unknown(self):
        text = self.page()
        nodes = Page(text).nodes()
        shown = re.findall(r'<text class="st"[^>]*>([^<]*)</text>', svg_of(text))
        for attrs, word in zip(nodes, shown):
            if attrs['data-kind'] == 'policy':
                continue
            self.assertEqual(word, '(no state)', attrs['data-kind'])
            self.assertEqual((attrs['data-state'], attrs['data-operation']), ('none', 'none'))
        self.assertEqual(sum('unknown' in word for word in shown), 0)

    def test_the_policy_shows_the_recorded_operation_word(self):
        for word, mark in (('expired', '~'), ('prepared', 'o'), ('verified', 'x'), ('blocked', '!'), ('running', '+')):
            text = self.page(states={self.object_id: word})
            first = re.findall(r'<text class="st"[^>]*>([^<]*)</text>', svg_of(text))[0]
            self.assertEqual(first, '[%s] %s' % (mark, word))
            self.assertEqual(Page(text).nodes()[0]['data-operation'], word)
        none = re.findall(r'<text class="st"[^>]*>([^<]*)</text>', svg_of(self.page()))[0]
        self.assertEqual(none, '[_] none recorded')
        # A word the page has no mark for keeps the recorded word and a question mark, never a different word.
        other = re.findall(r'<text class="st"[^>]*>([^<]*)</text>', svg_of(self.page(states={self.object_id: 'dispatched'})))[0]
        self.assertEqual(other, '[?] dispatched')
        legend = section(self.page(), 'legend')
        for text in ('[~] expired', '[o] prepared', '[_] none recorded', '(no state)'):
            self.assertIn(text, legend)

    def test_frame_21_an_expired_operation_and_a_repository(self):
        text = self.page(states={self.object_id: 'expired'}, freshness='fresh')
        words = re.findall(r'<text class="st"[^>]*>([^<]*)</text>', svg_of(text))
        self.assertEqual(words[0], '[~] expired')
        self.assertEqual(words.count('(no state)'), len(words) - 1)
        self.assertNotIn('unknown', ''.join(words))
        repository = [a for a in Page(text).nodes() if a['data-kind'] == 'repository'][0]
        self.assertEqual(repository['data-state'], 'none')
        panel = section(text, 'details')
        self.assertIn('no operation state applies', panel)

    def test_a_state_change_still_moves_nothing_and_a_non_policy_never_changes_the_drawing(self):
        from intune_iac.companion_page import drawing
        groups = self.groups()
        base = drawing(self.graph(freshness='fresh'))
        for word in ('expired', 'prepared', 'running', 'dispatched'):
            self.assertEqual(masked(drawing(self.graph(freshness='fresh', states={self.object_id: word}))), masked(base), word)
        # A state given for a group is not drawn: a group has no operation.
        self.assertEqual(drawing(self.graph(freshness='fresh', states={groups[0]: 'running'})), base)

    def test_the_filter_sits_on_its_assignment_and_the_assignment_on_its_filter(self):
        svg = svg_of(self.page())
        notes = re.findall(r'<text class="fl"[^>]*data-for="([^"]*)"[^>]*>([^<]*)</text>', svg)
        graph = self.graph()
        group = next(edge for edge in graph['edges'] if edge['filter'])['target']
        flt = graph['edges'][[e['type'] for e in graph['edges']].index('filter')]['target']
        by = dict(notes)
        self.assertEqual(set(by), {group, flt})
        self.assertRegex(by[group], r'^\+ filter 5aa36291 include$')
        self.assertRegex(by[flt], r'^applies to b564fc9a$')
        details = section(self.page(), 'details')
        self.assertIn('filter 5aa36291-9c32-5f60-b5ef-a48382c20714, include', details)
        # No other node claims a filter.
        self.assertEqual(len(notes), 2)

    def test_the_counts_name_the_relationships_and_the_sources_apart(self):
        summary = section(self.page(), 'summary')
        self.assertIn('7 relationships, 1 source', summary)
        self.assertNotIn('8 edges', summary)
        tree_header = [line for line in __import__('intune_iac.workbench_screens', fromlist=['x']).relationship_lines(self.value, 100, 'unicode')
                       if 'edges |' in line][0]
        self.assertIn('7 edges', tree_header)
        one = dict(self.value, relationships=self.value['relationships'][:1], selected_repository=None)
        self.assertIn('1 relationship, 0 sources', section(self.page(one), 'summary'))

    def test_labels_carry_their_kind_word_and_never_print_alike_when_cut(self):
        prefix = 'device_vendor_msft_policy_config_'
        value = dict(self.value, selected_repository={
            'evidence_class': 'recorded_repository_intent',
            'scope': {'repository': '/home/user/work/a-very-long-folder-name/with/many/parts/and/more/parts/repo-one', 'stack': 'dev', 'component': 'c'}},
            relationships=[
                {'relation': 'setting', 'target_id': prefix + 'privacy_letappsaccesslocation_in_the_workplace', 'details': {}, 'assertion_class': 'observed'},
                {'relation': 'setting', 'target_id': prefix + 'privacy_letappsaccesscamera_in_the_workplace', 'details': {}, 'assertion_class': 'observed'},
                {'relation': 'generated_from', 'target_id': '/home/user/work/a-very-long-folder-name/with/many/parts/and/more/parts/main.tf',
                 'details': {}, 'assertion_class': 'historical_local_adoption'}])
        svg = svg_of(self.page(value))
        labels = re.findall(r'<text class="lb"[^>]*>([^<]*)</text>', svg)
        self.assertEqual(len(labels), len(set(labels)), labels)
        settings = [label for label in labels if label.startswith('setting  ')]
        self.assertEqual(len(settings), 2)
        self.assertTrue(any(label.endswith('workplace') for label in settings))
        self.assertEqual([label for label in labels if label.startswith('generated  source ')].__len__(), 1)
        self.assertEqual([label for label in labels if label.startswith('repository  ')].__len__(), 1)
        for label in labels:
            self.assertLessEqual(len(label), 80)
        self.assertIn('\u2026', svg)
        # The detail still names each identifier in full.
        details = section(self.page(value), 'details')
        self.assertIn(prefix + 'privacy_letappsaccesscamera_in_the_workplace', details)
        self.assertIn('/home/user/work/a-very-long-folder-name/with/many/parts/and/more/parts/main.tf', details)


class FixRoundPageTests(Fixture):
    """Sol's review of a1bafb6, items 5 and 8 on the page."""

    LIVE = {'snapshot': 'snapshot', 'poll_seconds': 3, 'idle_seconds': 1800}

    def script(self):
        return Page(self.page(live=self.LIVE)).script

    def test_the_page_scrubs_the_token_from_the_address_and_history_and_reload_still_works(self):
        script = self.script()
        self.assertIn('var home = location.href;', script)
        self.assertIn("history.replaceState(null, '', '/')", script)
        self.assertLess(script.index('var home = location.href;'), script.index('history.replaceState'))
        # The button goes back to the address held in memory, replacing the entry rather than adding one.
        self.assertIn('location.replace(home)', script)
        text = self.page(live=self.LIVE)
        note = section(text, 'note')
        self.assertIn('secret', note.lower())
        self.assertIn('not isolated', note.lower())
        self.assertIn('Load the newer snapshot', text)
        self.assertIn('address bar', note)

    def test_a_snapshot_record_is_validated_before_it_resets_the_failure_count(self):
        script = self.script()
        check = script.index("snapshot.schema_version === 'workbench-companion-page/1'")
        reset = script.index('failures = 0;')
        self.assertLess(check, reset)
        for word in ("'object_unavailable'", "typeof snapshot.revision === 'string'", "typeof snapshot.mode === 'string'",
                     "snapshot.status === 'ok'", 'snapshot === null', "typeof snapshot !== 'object'"):
            self.assertIn(word, script)
        self.assertIn("throw new Error('invalid')", script)
        # An invalid record is handled as a failed poll: the same catch counts it.
        self.assertLess(script.index("throw new Error('invalid')"), script.index('.catch(function ()'))

    def test_a_change_of_evidence_mode_alone_is_named(self):
        script = self.script()
        self.assertIn('the evidence mode changed from', script)
        self.assertIn('snapshot.revision === revision', script)


class FixRound2PageTests(Fixture):
    """Sol's verification of d6900b4: findings 5 (address) and 8 (mode) on the page."""

    LIVE = {'snapshot': 'snapshot', 'poll_seconds': 3, 'idle_seconds': 1800}

    def script(self):
        return Page(self.page(live=self.LIVE)).script

    def test_the_snapshot_address_is_resolved_before_the_address_bar_is_scrubbed(self):
        script = self.script()
        resolved = "var address = new URL(body.getAttribute('data-snapshot'), location.href).href;"
        self.assertIn(resolved, script)
        self.assertLess(script.index(resolved), script.index('history.replaceState'))
        self.assertLess(script.index(resolved), script.index('var home = location.href;'))
        # The poll uses the resolved address, never the relative name again after the scrub.
        self.assertIn('fetch(address,', script)
        after = script[script.index('history.replaceState'):]
        self.assertNotIn("getAttribute('data-snapshot')", after)
        self.assertNotIn("fetch('snapshot'", script)

    def test_an_unavailable_record_must_still_carry_its_mode_as_text(self):
        script = self.script()
        branch = script[script.index("snapshot.status === 'object_unavailable'"):]
        branch = branch[:branch.index('}')]
        self.assertIn("snapshot.revision === null", branch)
        self.assertIn("typeof snapshot.mode === 'string'", branch)


class ProjectionAdditionTests(Fixture):
    def test_traversal_order_is_the_order_the_terminal_map_visits(self):
        from intune_iac.graph_projection import traversal_order
        from intune_iac.workbench_screens import MAP_LAYER_LIMIT, map_order
        graph = self.graph()
        self.assertEqual(traversal_order(graph, MAP_LAYER_LIMIT), map_order(graph))
        self.assertEqual(traversal_order(graph), map_order(graph))
        self.assertEqual(traversal_order(graph)[0], graph['center'])

    def test_a_per_layer_limit_cuts_in_order_and_counts_what_is_cut(self):
        from intune_iac.graph_projection import drawn_layers, traversal_order
        relations = [{'relation': 'setting', 'target_id': 'setting_%02d' % index, 'details': {}, 'assertion_class': 'observed'}
                     for index in range(9)]
        graph = self.graph(dict(self.value, relationships=self.value['relationships'] + relations))
        layers = {heading: (len(edges), cut) for heading, edges, cut in drawn_layers(graph, 4)}
        self.assertEqual(layers['CONFIGURATION'], (4, 8))
        self.assertEqual(layers['TARGETING'], (4, 0))
        self.assertEqual(len(traversal_order(graph, 4)), 1 + 4 + 4 + 1)
        self.assertEqual(len(traversal_order(graph)), len(graph['nodes']))

    def test_the_additions_leave_the_projection_unchanged(self):
        from intune_iac.graph_projection import project
        before = copy.deepcopy(self.value)
        graph = project(self.value, freshness='fresh')
        self.assertEqual(self.value, before)
        self.assertEqual(graph, project(before, freshness='fresh'))


if __name__ == '__main__':
    unittest.main()
