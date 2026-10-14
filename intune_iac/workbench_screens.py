"""Readable workspace screens over typed engine results.

Pure functions: an engine result and a width in, inert text lines out. Values
are shown as exact JSON, so strings are quoted and null, empty and absent stay
distinct. Every untrusted string passes through the workspace's own escaping.
Nothing is normalized, inferred or hidden; the complete typed evidence still
follows each screen.
"""
from __future__ import annotations

import json

from .workbench_tui import cell_width, pad, safe_text

WIDE = 96
LABEL = 16
SHORT_TABS = {'Estate': 'Est', 'Inspector': 'Insp', 'Relationships': 'Rel', 'History': 'Hist', 'Plan': 'Plan',
              'Execution': 'Exec', 'Coverage': 'Cov', 'Help': 'Help', 'Repository': 'Repo'}


def tab_line(tabs, active, width):
    """Numbered surfaces with the active one bracketed, shortening in tiers until the line fits.

    Full names, then short names, then numbers with only the active surface named, then numbers alone.
    """
    def line(names, gap):
        return gap.join(('[%d %s]' if index == active else '%d %s') % (index + 1, name) for index, name in enumerate(names))
    short = [SHORT_TABS.get(name, name) for name in tabs]
    tiers = (line(tabs, '  '), line(short, ' '),
             ' '.join('[%d %s]' % (index + 1, name) if index == active else str(index + 1) for index, name in enumerate(short)),
             ' '.join(('[%d]' if index == active else '%d') % (index + 1) for index in range(len(tabs))))
    return next((text for text in tiers if cell_width(text) <= width), tiers[-1])


def short_id(value):
    """The first eight characters of an identity, for orientation only; exact identities appear on each surface."""
    return value[:8] if isinstance(value, str) else str(value)


def context_strip(tenant, selected, facts, width):
    """Where the engineer is: tenant, policy, observation, repository and operation state, as last reported."""
    if not selected:
        return 'TENANT ' + short_id(tenant) + ' | POLICY none selected'
    policy = 'POLICY ' + str(facts.get('name', '(name not yet read)')) + ' (' + short_id(selected) + ')'
    states = [('OBSERVED', 'OBS', facts.get('observation', 'unknown')), ('REPOSITORY', 'REPO', facts.get('repository', 'not checked'))]
    if facts.get('operation'):
        states.append(('OPERATION', 'OP', facts['operation']))
    bare = 'POLICY ' + short_id(selected)
    for prefix, name, compact in ((['TENANT ' + short_id(tenant)], policy, False), ([], policy, False),
                                  ([], policy, True), ([], bare, True)):
        text = ' | '.join(prefix + [name] + [(short if compact else long) + ' ' + str(value) for long, short, value in states])
        if cell_width(safe_text(text)) <= width:
            return text
    return text


def utc_time(value):
    """An epoch number as an ISO 8601 UTC time; anything else unchanged."""
    from datetime import datetime, timezone
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return value
    try:
        return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
    except (OverflowError, OSError, ValueError):
        return value


def word_wrap(value, width):
    """Wrap escaped text at spaces where possible; split a token only when it cannot fit.

    Leading indentation is kept on every wrapped line.
    """
    text = safe_text(value)
    body = text.lstrip(' ')
    indent = len(text) - len(body)
    if indent and indent < width:
        return [' ' * indent + line for line in word_wrap(body, width - indent)]
    width = max(1, width)
    lines, line = [], ''
    for word in body.split(' '):
        candidate = word if not line else line + ' ' + word
        if cell_width(candidate) <= width:
            line = candidate
            continue
        if line:
            lines.append(line)
        line = ''
        while cell_width(word) > width:
            cut, used = '', 0
            for char in word:
                size = cell_width(char)
                if used + size > width:
                    break
                cut += char; used += size
            lines.append(cut or word[:1]); word = word[len(cut or word[:1]):]
        line = word
    lines.append(line)
    return lines


def _value(value):
    return safe_text(json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True))


def _target(item):
    if isinstance(item, dict) and isinstance(item.get('type'), str):
        text = item['type']
        if 'group_id' in item:
            text += ' group ' + str(item['group_id'])
        if item.get('filter_type') not in (None, 'none'):
            text += ' filter ' + str(item['filter_type']) + ' ' + str(item.get('filter_id'))
        return safe_text(text)
    return _value(item)


def _rows(changes):
    """(label, before, after) rows; before is None for a row that is a single statement."""
    rows = []
    for change in changes:
        field, kind = change.get('field'), change.get('kind')
        if field == 'settings':
            label = 'settings ' + str(change.get('setting_id')) + ' ' + str(change.get('setting_definition_id') or '')
            if kind == 'changed':
                for leaf in change.get('differences', []):
                    rows.append((label + ' ' + str(leaf.get('path', '')),
                                 _value(leaf['before']) if 'before' in leaf else '(absent)',
                                 _value(leaf['after']) if 'after' in leaf else '(absent)'))
            elif kind in ('added', 'removed'):
                rows.append((label + '  ' + kind, None, None))
            elif kind == 'reordered':
                rows.append(('settings order  ' + ', '.join(map(str, change.get('before_order', []))) + '  ->  '
                             + ', '.join(map(str, change.get('after_order', []))), None, None))
        elif kind == 'changed':
            rows.append((str(field), _value(change.get('before')), _value(change.get('after'))))
        elif kind in ('added', 'removed'):
            rows.append((str(field) + '  ' + ('+ ' if kind == 'added' else '- ') + _target(change.get('value')), None, None))
    return rows


def change_lines(changes, width, before_label='BEFORE (observed)', after_label='AFTER (desired)'):
    """A field-change list as a table (wide) or stacked before and after rows (narrow)."""
    status = changes.get('status') if isinstance(changes, dict) else None
    if status == 'no_change':
        return ['NO CONFIGURATION CHANGE'] + word_wrap(
            'The desired body equals the observed body under the execution plan\'s equality.', width)
    if status != 'changed':
        lines = ['CHANGE COMPARISON UNKNOWN']
        for blocker in (changes.get('blockers', []) if isinstance(changes, dict) else []):
            lines += word_wrap('  %s %s %s' % (blocker.get('side', ''), blocker.get('path') or '/', blocker.get('code', '')), width)
        return lines
    count = len(changes.get('changes', []))
    lines = word_wrap('%d FIELD CHANGE%s  (exact values; strings are quoted)' % (count, '' if count == 1 else 'S'), width)
    if not changes.get('complete', True):
        lines += word_wrap('Only the first changes are listed; the complete result follows below.', width)
    rows = _rows(changes.get('changes', []))
    column = (width - LABEL - 2) // 2
    if width >= WIDE:
        lines.append(pad('FIELD', LABEL) + pad(before_label, column) + '  ' + pad(after_label, column).rstrip())
    for label, before, after in rows:
        if before is None:
            lines += word_wrap(label, width)
        elif width >= WIDE and cell_width(label) < LABEL and max(cell_width(before), cell_width(after)) < column:
            lines.append((pad(label, LABEL) + pad(before, column) + '  ' + after).rstrip())
        else:
            # A value too long for its column keeps the full width rather than
            # being split mid-identifier between two columns.
            lines += word_wrap(label, width)
            for prefix, value in (('  before  ', before), ('  after   ', after)):
                for index, part in enumerate(word_wrap(value, width - len(prefix))):
                    lines.append((prefix if index == 0 else ' ' * len(prefix)) + part)
    return lines


TARGET_WORDS = {'groupAssignmentTarget': 'include', 'exclusionGroupAssignmentTarget': 'exclude',
                'allDevicesAssignmentTarget': 'all devices', 'allLicensedUsersAssignmentTarget': 'all licensed users'}


def _labelled(label, text, width, size=13):
    """A label column followed by wrapped text, continuation lines indented under the text."""
    lines = []
    for index, part in enumerate(word_wrap(text, max(1, width - size))):
        lines.append((pad(label, size) if index == 0 else ' ' * size) + part)
    return lines


def _setting_value(instance):
    """The exact configured value of one setting instance, by instance kind."""
    if not isinstance(instance, dict):
        return 'unreadable instance (see exact evidence)'
    kind = str(instance.get('@odata.type', ''))
    if 'ChoiceSettingInstance' in kind and isinstance(instance.get('choiceSettingValue'), dict):
        value = instance['choiceSettingValue']
        children = value.get('children') or []
        return 'choice  ' + _value(value.get('value')) + ('  (%d child settings)' % len(children) if children else '')
    if 'SimpleSettingCollectionInstance' in kind:
        values = instance.get('simpleSettingCollectionValue')
        return 'ordered list  ' + _value([v.get('value') if isinstance(v, dict) else v for v in values] if isinstance(values, list) else values)
    if 'SimpleSettingInstance' in kind and isinstance(instance.get('simpleSettingValue'), dict):
        return 'value  ' + _value(instance['simpleSettingValue'].get('value'))
    return safe_text(kind or 'unknown instance') + ' (see exact evidence)'


def _target_line(row):
    if not isinstance(row, dict):
        return _value(row)
    text = TARGET_WORDS.get(row.get('type'), safe_text(str(row.get('type'))))
    if 'group_id' in row:
        text += '  group ' + safe_text(str(row['group_id']))
    if row.get('filter_type') not in (None, 'none'):
        text += '  filter ' + safe_text(str(row['filter_type'])) + ' ' + safe_text(str(row.get('filter_id')))
    return text


def inspector_lines(value, width):
    """One policy as an engineer reads it: identity, observation, settings and targeting, exact values."""
    lines = ['[POLICY INSPECTOR]']
    lines += word_wrap(str(value.get('name') or '(no name in this result)'), width)
    body = value.get('body') if isinstance(value.get('body'), dict) else {}
    lines += _labelled('Identity', str(value.get('object_id', 'unknown')), width)
    if body:
        technologies = body.get('technologies')
        lines += _labelled('Platform', str(body.get('platforms')) + ' | technologies ' + (
            ', '.join(map(str, technologies)) if isinstance(technologies, list) else _value(technologies)), width)
        tags = body.get('role_scope_tag_ids')
        lines += _labelled('Scope tags', ' '.join(_value(tag) for tag in tags) if isinstance(tags, list) else _value(tags), width)
    observed = [str(value[key]) for key in ('observed_at', 'coverage', 'freshness') if value.get(key)]
    if value.get('snapshot_id'):
        observed.append('snapshot ' + str(value['snapshot_id'])[:12])
    lines += _labelled('Observed', ' | '.join(observed) or 'unknown', width)
    lines += _labelled('Ownership', str(value.get('ownership', 'unknown')), width)
    if body:
        lines += _labelled('Description', _value(body.get('description')), width)
    settings = body.get('settings', {}).get('settings') if isinstance(body.get('settings'), dict) else None
    if isinstance(settings, list):
        lines.append('SETTINGS (%d)' % len(settings))
        for row in settings:
            instance = row.get('settingInstance') if isinstance(row, dict) else None
            definition = instance.get('settingDefinitionId') if isinstance(instance, dict) else None
            lines += word_wrap('  ' + str(row.get('id') if isinstance(row, dict) else '?') + '  ' + str(definition), width)
            lines += word_wrap('     ' + _setting_value(instance), width)
    else:
        lines.append('SETTINGS not in this result')
    assignments = body.get('assignments')
    if isinstance(assignments, list):
        lines.append('TARGETING (%d)' % len(assignments))
        for row in assignments:
            lines += word_wrap('  ' + _target_line(row), width)
    elif body:
        lines.append('TARGETING ' + ('not collected (null)' if assignments is None else 'unreadable'))
    lines += word_wrap('Keys: d dictionary for these settings | 3 relationships | 4 history | 9 repository', width)
    return lines


def _availability(entry, category):
    record = ((entry.get('fact_provenance') or {}).get('categories') or {}).get(category) or {}
    return str(record.get('availability', 'unknown')).replace('_', ' ')


def dictionary_lines(value, width):
    """Dictionary entries with vendor documentation, local mapping and observed use kept apart."""
    lines = ['[SETTING DICTIONARY]']
    entries = value.get('entries') if isinstance(value.get('entries'), list) else []
    if not entries:
        return lines + ['No dictionary entries for this query.']
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        lines.append('')
        lines += word_wrap(str(entry.get('identifier')), width)
        for vendor in entry.get('vendor_documentation') or []:
            if not isinstance(vendor, dict):
                continue
            lines += _labelled('Name', str(vendor.get('name')) + '  (vendor documentation)', width)
            lines += _labelled('Meaning', str(vendor.get('meaning')), width)
            if vendor.get('aliases'):
                lines += _labelled('Aliases', ', '.join(map(str, vendor['aliases'])), width)
            lines += _labelled('CSP', '%s | %s | default %s' % (vendor.get('csp_uri'), vendor.get('data_type'), _value(vendor.get('default_value'))), width)
            allowed = vendor.get('allowed_values') or []
            lines += _labelled('CSP values', ' | '.join('%s %s' % (_value(item.get('value')), item.get('meaning')) for item in allowed if isinstance(item, dict)) or 'not documented', width)
            if vendor.get('graph_value_translation_verified') is not True:
                lines += _labelled('', 'Graph value to CSP value translation NOT verified: ' + str(vendor.get('association_basis', 'no attestation')), width)
            applies = vendor.get('applicability') or {}
            lines += _labelled('Applies to', ' | '.join(str(part) for part in (applies.get('scope'), applies.get('minimum_windows_release'),
                               ', '.join(applies.get('editions') or [])) if part) or 'not documented', width)
            source = vendor.get('documentation') or {}
            lines += _labelled('Source', ' | '.join(str(part) for part in (source.get('publisher'), 'updated ' + str(source.get('published_update_at')),
                               'retrieved ' + str(source.get('retrieved_at')), source.get('url')) if part), width)
        for mapping in entry.get('local_mapping') or []:
            rule = mapping.get('entry') if isinstance(mapping, dict) else None
            if isinstance(rule, dict):
                lines += _labelled('Mapping', str(rule.get('support_status')) + ' | permitted Graph values ' +
                                   ', '.join(_value(v) for v in rule.get('permitted_values') or []) +
                                   ' | deferred: ' + ', '.join(map(str, rule.get('deferred_qualification') or [])), width)
        uses = entry.get('actual_uses') or []
        for use in uses:
            if isinstance(use, dict):
                lines += _labelled('In use' if use is uses[0] else '', '%s (%s) %s | %s | %s | %s' % (
                    use.get('name'), use.get('object_id'), _setting_value(use.get('instance')),
                    use.get('freshness'), use.get('coverage'), use.get('evidence_class')), width)
        if not uses:
            lines += _labelled('In use', 'no observed use', width)
        lines += word_wrap('Company annotation %s | community advice %s | AI interpretation %s' % (
            _availability(entry, 'company_annotation'), _availability(entry, 'community_advice'),
            _availability(entry, 'ai_interpretation')), width)
    return lines


RELATION_GROUPS = (('TARGETING', ('assignment', 'exclusion', 'filter')),
                   ('CONFIGURATION', ('setting', 'scope_tag')),
                   ('SOURCE AND LINEAGE', ('generated_from', 'repository')))
RELATION_LABELS = {'scope_tag': 'scope tag', 'generated_from': 'generated'}


def _edge_target(edge):
    relation, target = edge.get('relation'), edge.get('target_id')
    if relation == 'scope_tag':
        return _value(target)
    text = safe_text(str(target))
    details = edge.get('details') if isinstance(edge.get('details'), dict) else {}
    if relation == 'assignment' and details.get('filter_type') not in (None, 'none'):
        text += '  filter ' + safe_text(str(details['filter_type'])) + ' ' + safe_text(str(details.get('filter_id')))
    return text


def relationship_lines(value, width):
    """Typed edges grouped by what they mean, each with its exact target and its evidence class."""
    lines = ['[TYPED RELATIONSHIPS]']
    edges = [edge for edge in value.get('relationships') or [] if isinstance(edge, dict)]
    lines += word_wrap('%s (%s)' % (value.get('name', '(no name)'), value.get('object_id', 'unknown')), width)
    lines += word_wrap('%d edges | coverage %s | observed %s' % (
        len(edges), value.get('coverage', 'unknown'), value.get('observed_at', 'unknown')), width)
    if not edges:
        lines.append('No typed relationships in this result.')
    repository = value.get('selected_repository')
    if isinstance(repository, dict) and isinstance(repository.get('scope'), dict):
        scope = repository['scope']
        edges = edges + [{'relation': 'repository', 'assertion_class': repository.get('evidence_class', 'unknown'),
                          'target_id': '%s  %s / %s' % (scope.get('repository'), scope.get('stack'), scope.get('component'))}]
    groups = list(RELATION_GROUPS)
    others = [edge.get('relation') for edge in edges if not any(edge.get('relation') in members for _, members in RELATION_GROUPS)]
    if others:
        groups.append(('OTHER RELATIONSHIPS', tuple(dict.fromkeys(others))))
    for heading, members in groups:
        rows = [edge for edge in edges if edge.get('relation') in members]
        if not rows:
            continue
        # One evidence class for the whole group is stated once, on its heading.
        classes = {str(edge.get('assertion_class', 'unknown')) for edge in rows}
        shared = classes.pop() if len(classes) == 1 else None
        lines.append(heading + ('  [' + safe_text(shared) + ']' if shared else ''))
        for index, edge in enumerate(rows):
            connector = '  `-- ' if index == len(rows) - 1 else '  |-- '
            label = RELATION_LABELS.get(edge.get('relation'), str(edge.get('relation')).replace('_', ' '))
            text = pad(label, 13) + _edge_target(edge) + ('' if shared else '  [' + safe_text(str(edge.get('assertion_class', 'unknown'))) + ']')
            for number, part in enumerate(word_wrap(text, width - len(connector))):
                lines.append((connector if number == 0 else ' ' * len(connector)) + part)
    ownership = value.get('ownership_evidence') if isinstance(value.get('ownership_evidence'), dict) else {}
    lines.append('OWNERSHIP')
    reason = ownership.get('reason')
    lines += word_wrap('  `-- ' + pad('writer', 13) + str(value.get('ownership', 'unknown')) + (': ' + str(reason) if reason else ''), width)
    return lines


def history_lines(value, width):
    """Observations newest first, each with what changed since the one before it on this page."""
    from .workbench_diff import field_changes
    lines = ['[OBSERVATION HISTORY]']
    page = value.get('pagination') if isinstance(value.get('pagination'), dict) else {}
    items = [item for item in value.get('history') or [] if isinstance(item, dict)]
    lines += word_wrap('%s (%s)' % (value.get('name') or (items[0].get('name') if items else None) or '(no name)',
                                    value.get('object_id', 'unknown')), width)
    lines += word_wrap('%s observations | this page %d from offset %s' % (
        page.get('total_observations', 'unknown'), len(items), page.get('offset', value.get('offset', 0))), width)
    if value.get('order') == 'observed_at_desc_observation_id_desc':
        lines += word_wrap('Newest first; n shows older observations, p shows newer observations.', width)
    lines += word_wrap('Observation time is when collection saw the configuration; it does not establish who changed it or when.', width)
    for index, item in enumerate(items):
        lines.append('')
        lines += word_wrap('%s | run %s | %s | snapshot %s' % (
            item.get('observed_at', 'unknown'), item.get('run_id', 'unknown'), item.get('coverage', 'unknown'),
            str(item.get('snapshot_id', 'unknown'))[:12]), width)
        lines += word_wrap('  %s | changed at %s | attribution %s' % (
            item.get('evidence_class', 'evidence unknown'), item.get('changed_at') or 'unknown', item.get('attribution') or 'unknown'), width)
        accounting = item.get('field_accounting') if isinstance(item.get('field_accounting'), dict) else {}
        partial = sorted('%s %s' % (field, status) for field, status in accounting.items() if status != 'observed_complete')
        if partial:
            lines += word_wrap('  Not completely observed: ' + ', '.join(partial), width)
        if index + 1 == len(items):
            lines += word_wrap('  Earliest observation on this page' + ('; n shows older observations.' if page.get('has_more') else '.'), width)
            continue
        previous = items[index + 1]
        changes = field_changes(previous.get('body'), item.get('body'))
        if changes.get('status') == 'no_change':
            lines += word_wrap('  No configuration change since the previous observation.', width)
            continue
        heading = 'Changed since the previous observation' if changes.get('status') == 'changed' else 'Comparison with the previous observation'
        lines += word_wrap('  %s (%s):' % (heading, previous.get('observed_at', 'unknown')), width)
        lines += ['  ' + line for line in change_lines(changes, width - 2, 'BEFORE (previous)', 'AFTER (this observation)')]
    if not items:
        lines.append('No observations on this page.')
    return lines


CELLS = (('#', 'success'), ('x', 'failure'), ('~', 'pending'), ('?', 'reported unknown'), ('.', 'no fresh report'))
MAX_CELLS = 400
NOT_COUNTED = ('missing', 'stale', 'partial', 'access_denied', 'future', 'membership_conflicts', 'conflicting')


def _counts(stage):
    """(targeted, reported, success, failure, pending, reported unknown, no fresh report), or None without evidence."""
    if not isinstance(stage, dict) or any(type(stage.get(key)) is not int for key in ('targeted', 'reporting', 'successful')):
        return None
    targeted, reporting, success = stage['targeted'], stage['reporting'], stage['successful']
    failure = stage['failed'] if type(stage.get('failed')) is int else 0
    pending = stage['pending'] if type(stage.get('pending')) is int else 0
    return (targeted, reporting, success, failure, pending, reporting - success - failure - pending, targeted - reporting)


def _matrix(counts, width):
    """One cell per device (or per group of devices when the cohort is large), in a fixed category order."""
    targeted = counts[0]
    per = max(1, -(-targeted // MAX_CELLS))
    cells = ''.join(symbol * -(-count // per) for (symbol, _), count in zip(CELLS, counts[2:]))
    row = max(1, min(50, width - 6))
    lines = ['    [' + cells[start:start + row] + ']' for start in range(0, len(cells), row)]
    scale = 'each cell is 1 device' if per == 1 else 'each cell is up to %d devices; exact counts above' % per
    return lines + word_wrap('    ' + '  '.join('%s %s' % pair for pair in CELLS), width) + word_wrap('    ' + scale, width)


def _stage_lines(stages, width):
    from .workbench_health import STAGES
    names = list(STAGES) + sorted(set(stages) - set(STAGES))
    counted = [(name, _counts(stages.get(name))) for name in names]
    present = [(name, counts) for name, counts in counted if counts is not None]
    absent = [name.replace('_', ' ') for name, counts in counted if counts is None]
    if not present:
        return ['  No device evidence for any stage.']
    lines = []
    # 78 is the inner width of an 80-column terminal; the compact table keeps columns down to 51.
    wide = ((9, 'TARGETED'), (9, 'REPORTED'), (8, 'SUCCESS'), (8, 'FAILURE'), (8, 'PENDING'), (8, 'UNKNOWN'), (10, 'NO REPORT'))
    compact = tuple((5, title) for title in ('TGT', 'RPT', 'OK', 'FAIL', 'PEND', 'UNK', 'NONE'))
    columns, label = (wide, 16) if width >= 78 else (compact, 14) if width >= 51 else (None, 0)
    if columns:
        lines.append('  ' + pad('STAGE', label) + ''.join(title.rjust(size) for size, title in columns))
        for name, counts in present:
            lines.append('  ' + pad(name.replace('_', ' '), label) + ''.join(str(count).rjust(size) for (size, _), count in zip(columns, counts)))
        if columns is compact:
            lines += word_wrap('  TGT targeted | RPT reported | OK success | FAIL failure | PEND pending | UNK reported unknown | NONE no fresh report', width)
    else:
        for name, counts in present:
            lines += word_wrap('  %s: %d targeted | %d reported | %d success | %d failure | %d pending | %d unknown | %d no fresh report' % (
                (name.replace('_', ' '),) + counts), width)
    if absent:
        lines += word_wrap('  No device evidence for: ' + ', '.join(absent), width)
    reported = [(name, counts) for name, counts in present if counts[1] > 0]
    name, counts = (reported or [item for item in present if item[0] == 'execution'] or present)[-1]
    if min(counts) < 0:
        return lines + word_wrap('  Stage counts for %s are inconsistent; see the exact evidence.' % name, width)
    text = '%d of %d targeted devices reported success at %s' % (counts[2], counts[0], name.replace('_', ' '))
    for count, words in zip(counts[3:], ('reported failure', 'pending', 'reported an unknown or conflicting status', 'without a fresh report')):
        if count:
            text += '; %d %s' % (count, words)
    lines += word_wrap('  ' + text, width)
    stage = stages.get(name)
    reasons = ['%d %s' % (stage[key], key.replace('_', ' ')) for key in NOT_COUNTED if type(stage.get(key)) is int and stage[key]]
    if reasons:
        lines += word_wrap('  Not counted as fresh success: ' + ', '.join(reasons), width)
    if counts[0] > 0:
        lines += _matrix(counts, width)
    return lines


def _object_health(row, health, width):
    lines = ['']
    lines += word_wrap('%s (%s)' % (row.get('name') or '(no name)', row.get('object_id') or health.get('object_id', 'unknown')), width)
    if health.get('reason'):
        lines += word_wrap('  ' + str(health['reason']), width)
    if health.get('as_of') is not None:
        capture = health.get('capture') if isinstance(health.get('capture'), dict) else {}
        lines += word_wrap('  Evidence %s | as of %s | cohort %s%s' % (
            health.get('evidence_class'), health.get('as_of'), health.get('cohort_version'),
            ' | capture incomplete' if capture.get('truncated') or capture.get('access_errors') else ''), width)
        denominator = '  Denominator %s targeted of %s eligible, %s excluded' % (health.get('targeted'), health.get('eligible'), health.get('excluded'))
        if health.get('membership_conflicts'):
            denominator += ' | %d membership conflicts' % len(health['membership_conflicts'])
        if health.get('out_of_cohort_devices'):
            denominator += ' | %d reports from devices outside the cohort' % len(health['out_of_cohort_devices'])
        lines += word_wrap(denominator, width)
        if health.get('source_sha256'):
            lines += word_wrap('  Source %s sha256 %s' % (health.get('source_path'), str(health['source_sha256'])[:12]), width)
    stages = health.get('stages') if isinstance(health.get('stages'), dict) else {}
    lines += _stage_lines(stages, width)
    lines += word_wrap('  Endpoint health %s | endpoint outcome %s' % (health.get('endpoint_health', 'unknown'), health.get('endpoint_outcome', 'unknown')), width)
    if 'service_acceptance' in health or 'configuration_parity' in health:
        lines += word_wrap('  Service acceptance %s | configuration parity %s' % (
            health.get('service_acceptance', 'unknown'), health.get('configuration_parity', 'unknown')), width)
    lines += word_wrap('  Rollout ready %s | rollout approval %s' % (
        'yes' if health.get('rollout_ready') is True else 'no', health.get('rollout_approval', 'unknown')), width)
    return lines


def _collection_lines(value, width):
    age = value.get('age_seconds')
    age = '%dm %02ds' % divmod(int(age), 60) if isinstance(age, (int, float)) and not isinstance(age, bool) else 'unknown'
    lines = word_wrap('Collection %s (%s) | coverage %s | age %s | %s inventory objects' % (
        value.get('freshness', 'unknown'), value.get('freshness_scope', 'scope unknown'), value.get('coverage', 'unknown'),
        age, value.get('total_inventory_objects', 'unknown')), width)
    for label, key in (('Last success', 'last_success'), ('Last attempt', 'last_attempt')):
        run = value.get(key)
        if isinstance(run, dict):
            lines += word_wrap('%s %s | run %s | %s | error %s' % (label, run.get('completed_at') or run.get('started_at'),
                               run.get('run_id'), run.get('status'), run.get('error_code') or 'none'), width)
        else:
            lines += word_wrap(label + ' not recorded', width)
    if value.get('retained_last_good'):
        lines += word_wrap('Showing retained last-good observations: the last collection did not complete.', width)
    pending = value.get('pending_observations') or []
    if pending:
        lines += word_wrap('%d observations pending admission' % len(pending), width)
    aggregate = value.get('collection_health') if isinstance(value.get('collection_health'), dict) else None
    if aggregate is not None:
        counts = _counts(aggregate)
        lines += word_wrap('Collection reporting ' + ('not imported' if counts is None else '%d of %d reporting | %d success | %d failure | %d pending' % (
            counts[1], counts[0], counts[2], counts[3], counts[4])), width)
    return lines


def health_lines(value, width, name=None):
    """Collection freshness, then per policy: stage denominators, a device matrix and endpoint evidence, kept apart.

    A single-policy result carries no name; the caller may pass the name it already showed for that policy.
    """
    lines = ['[HEALTH AND REPORTING]']
    if 'objects' in value:
        lines += _collection_lines(value, width)
        for row in value.get('objects') or []:
            if isinstance(row, dict):
                lines += _object_health(row, row.get('health') if isinstance(row.get('health'), dict) else {}, width)
    else:
        lines += _object_health({'name': name}, value, width)
    for text in ([value['qualification']] if value.get('qualification') else []) + list(value.get('limitations') or []):
        lines += word_wrap('Limitation: ' + str(text), width)
    return lines


def _proposals(related):
    """Each related operation once, with its latest journal status and how many journal records it has."""
    by_operation = {}
    for record in related or []:
        if isinstance(record, dict):
            by_operation.setdefault(str(record.get('operation_id')), []).append(record)
    lines = []
    for operation, records in by_operation.items():
        latest = max(records, key=lambda record: record['sequence'] if type(record.get('sequence')) is int else -1)
        lines.append('%s %s (%s; latest %s)' % (operation[:12], latest.get('status'), _plural(len(records), 'journal record'), latest.get('recorded_at')))
    return lines


def _plural(count, noun):
    return '%d %s%s' % (count, noun, '' if count == 1 else 's')


def queue_lines(value, width):
    """Findings as work: what, why, state, ownership, dates, compatibility, evidence and related proposals."""
    lines = ['[MAINTENANCE QUEUE]']
    findings = [item for item in value.get('findings') or [] if isinstance(item, dict)]
    page = value.get('pagination') if isinstance(value.get('pagination'), dict) else {}
    total = page.get('total_objects')
    lines += word_wrap('%s | %s in scope | no automatic remediation' % (
        _plural(len(findings), 'finding'), _plural(total, 'object') if type(total) is int else 'unknown objects'), width)
    if not findings:
        lines.append('No findings for the observations in scope.')
    for item in findings:
        lines.append('')
        lines += word_wrap('%s  %s  %s' % (item.get('priority', 'unknown'), item.get('finding', 'unknown'), item.get('object_id', 'unknown')), width)
        lines += word_wrap('  Why: ' + str(item.get('priority_rationale') or 'not recorded'), width)
        lines += word_wrap('  State %s | owner %s | freshness %s | automatic remediation %s' % (
            item.get('action_state', 'unknown'), item.get('owner_assertion', 'unknown'), item.get('freshness', 'unknown'),
            'yes' if item.get('automatic_remediation') is True else 'no'), width)
        writer = item.get('writer_ownership') if isinstance(item.get('writer_ownership'), dict) else {}
        claim = item.get('source_owner_claim') if isinstance(item.get('source_owner_claim'), dict) else {}
        if writer or 'owner_role' in item:
            lines += word_wrap('  Owner role %s: %s | writer %s%s | source owner claim %s' % (
                str(item.get('owner_role', 'unknown')).replace('_', ' '), item.get('owner') or 'none recorded',
                writer.get('status', 'unknown'), ': ' + str(writer['reason']) if writer.get('reason') else '',
                _value(claim.get('value')) if claim else 'none'), width)
        review = item.get('review_record') if isinstance(item.get('review_record'), dict) else {}
        state = str(review['reason']).replace('_', ' ') if review.get('reason') else 'review ' + str(review.get('status', 'not recorded'))
        lines += word_wrap('  %s | review due %s | exception expiry %s' % (
            state[:1].upper() + state[1:], item.get('review_due') or 'none', item.get('exception_expiry') or 'none'), width)
        compatibility = item.get('compatibility') if isinstance(item.get('compatibility'), dict) else None
        if compatibility:
            lines += word_wrap('  Compatibility %s | native provider %squalified' % (
                compatibility.get('profile', 'unknown'), '' if compatibility.get('native_provider_qualified') is True else 'not '), width)
        evidence = item.get('evidence') if isinstance(item.get('evidence'), dict) else None
        if evidence:
            lines += word_wrap('  Evidence %s | observed %s | snapshot %s' % (
                evidence.get('evidence_class', 'unknown'), evidence.get('observed_at', 'unknown'), str(evidence.get('snapshot_id', 'unknown'))[:12]), width)
        proposals = _proposals(item.get('related_proposals'))
        lines += word_wrap('  Related proposals ' + ('(%d)' % len(proposals) if proposals else 'none'), width)
        for text in proposals:
            lines += word_wrap('    ' + text, width)
    return lines


STAGE_LABELS = {'proposal': 'Proposal', 'review': 'Review', 'approval': 'Approval', 'execution': 'Execution',
                'readback': 'Readback', 'reconciliation': 'Reconciliation', 'deployment_record': 'Deployment',
                'observed_after': 'Observed after'}
# The marker repeats the stage's state; the words after it always say it too.
MARKS = {'done': 'x', 'matches_desired': 'x', 'waiting': ' ', 'not_yet': ' ', 'not_started': ' ', 'available': ' ',
         'not_needed': '-', 'not_applicable': '-', 'unknown': '?', 'required': '?', 'pending': '?', 'not_open': '?',
         'not_recorded': '?', 'failed': '!', 'expired': '!', 'rejected': '!', 'not_available': '!', 'differs': '!'}
# The legend names states without the alert phrases, so only its markers are tinted, never its words.
MARK_LEGEND = '[x] done  [ ] waiting or not yet  [-] not needed  [?] unknown or required  [!] stopped: a failure, an expiry or a refusal'


def _approval_text(stage, status):
    if status == 'done':
        return 'exact review digest %s supplied at dispatch | window %s to %s' % (
            str(stage.get('approval_digest'))[:12], utc_time(stage.get('opens_at')), utc_time(stage.get('closes_at')))
    if status == 'waiting':
        return 'waiting for the exact review digest until %s' % utc_time(stage.get('closes_at'))
    if status == 'expired':
        return 'expired: the approval window closed at %s' % utc_time(stage.get('closes_at'))
    if status == 'not_open':
        return 'not open: the local clock reads before %s' % utc_time(stage.get('opens_at'))
    return str(status).replace('_', ' ')


def _execution_text(stage, status):
    if status == 'not_started':
        return 'not started'
    parts = ['engine ' + str(stage.get('engine_status'))]
    if stage.get('service_status') is not None:
        parts.append('service ' + str(stage['service_status']))
    elif stage.get('no_change_dispatch'):
        parts.append('no service change dispatched')
    if stage.get('recorded_at'):
        parts.append('recorded ' + str(stage['recorded_at']))
    if status == 'unknown':
        return 'outcome unknown: %s | %s' % (stage.get('error_code') or 'no error recorded', ' | '.join(parts))
    return ' | '.join(parts)


def _receipt_text(stage, status):
    if status in ('not_started', 'not_needed'):
        return status.replace('_', ' ')
    if status == 'not_recorded':
        return 'not recorded: execution ended before an independent readback'
    if status == 'required':
        return 'required: the outcome is unknown; reconcile before any retry'
    parts = [str(stage.get('classification'))]
    if stage.get('stage') == 'readback':
        count = stage.get('mismatch_count') or 0
        parts += ['second plan ' + str(stage.get('second_plan')), 'visibility ' + ('pending' if stage.get('visibility_pending') else 'settled'),
                  '%d mismatch%s' % (count, '' if count == 1 else 'es')]
    else:
        parts.append('after ' + str(stage.get('previous_status')))
        if (stage.get('count') or 1) > 1:
            parts.append('%d reconciliations' % stage['count'])
        if stage.get('recorded_at'):
            parts.append('recorded ' + str(stage['recorded_at']))
    return ' | '.join(parts)


def _record_text(stage, status):
    if status == 'done':
        return 'recorded %s | intent %s | %s | %s' % (stage.get('recorded_at'), str(stage.get('intent_id'))[:12], stage.get('evidence_class'),
                                                      'baseline admissible' if stage.get('baseline_admissible') else 'not a baseline')
    if status == 'available':
        return 'available for intent %s; deployment-record performs the full check' % str(stage.get('intent_id'))[:12]
    if status in ('not_available', 'not_applicable'):
        return '%s: %s' % (status.replace('_', ' '), str(stage.get('reason', 'see exact evidence')).replace('_', ' '))
    return 'not yet'


def _observed_text(stage, status):
    revision = 'service revision %s' % stage.get('service_revision')
    if status == 'matches_desired':
        return 'matches desired at %s (%s before the change) | observed %s' % (revision, stage.get('before_revision'), stage.get('observed_at'))
    if status == 'differs':
        return 'differs from the desired configuration at %s | observed %s' % (revision, stage.get('observed_at'))
    if status == 'not_yet':
        return 'not yet: no observation after the change' + (' (latest at %s)' % revision if stage.get('service_revision') is not None else '')
    if status == 'not_applicable':
        return 'not applicable: no configuration change was dispatched'
    return 'unknown: ' + str(stage.get('reason', 'see exact evidence')).replace('_', ' ')


def _stage_text(stage):
    name, status = stage.get('stage'), stage.get('status')
    if name == 'proposal':
        cited = stage.get('repository_intent_id')
        return 'recorded %s | %s' % (stage.get('recorded_at') or 'time not recorded',
                                     'repository intent %s (%s)' % (str(cited)[:12], stage.get('intent_freshness')) if cited
                                     else 'desired file; no repository intent cited')
    if name == 'review':
        changes = [c for c in ((stage.get('field_changes') or {}).get('changes') or []) if isinstance(c, dict)]
        text = ('NO CONFIGURATION CHANGE' if stage.get('no_configuration_change') else
                '%s: %s' % (_plural(len(changes), 'field change'), ', '.join(dict.fromkeys(str(c.get('field')) for c in changes))) if changes else
                'changes ' + ', '.join(map(str, stage.get('changes') or [])))
        return text + ' | plan sha256 ' + str(stage.get('saved_plan_sha256'))[:12]
    texts = {'approval': _approval_text, 'execution': _execution_text, 'readback': _receipt_text, 'reconciliation': _receipt_text,
             'deployment_record': _record_text, 'observed_after': _observed_text}
    return texts[name](stage, status) if name in texts else str(status)


def delivery_lines(value, width):
    """One operation's delivery stages in order, each with a marker, its state in words and its evidence."""
    lines = ['[DELIVERY]']
    lines += word_wrap('Operation %s | policy %s | journal %s' % (value.get('operation_id'), value.get('object_id'), value.get('journal_status')), width)
    for number, stage in enumerate(value.get('stages') or [], 1):
        if not isinstance(stage, dict):
            continue
        mark = '  [%s] ' % MARKS.get(stage.get('status'), '?')
        label = '%d %s' % (number, STAGE_LABELS.get(stage.get('stage'), str(stage.get('stage'))))
        text = _stage_text(stage)
        if width >= 60:
            for index, part in enumerate(word_wrap(text, width - 24)):
                lines.append((mark + pad(label, 18) if index == 0 else ' ' * 24) + part)
        else:
            lines.append(mark + label)
            lines += ['      ' + part for part in word_wrap(text, width - 6)]
        if stage.get('stage') == 'observed_after' and stage.get('status') == 'differs' and isinstance(stage.get('field_changes'), dict):
            lines += ['      ' + line for line in change_lines(stage['field_changes'], width - 6, 'BEFORE (desired)', 'AFTER (observed)')]
    runs = [run for run in value.get('workflow_runs') or [] if isinstance(run, dict)]
    read = value.get('workflow_runs_read') if isinstance(value.get('workflow_runs_read'), dict) else {}
    if read.get('status') == 'unavailable':
        lines += word_wrap('CI workflow runs could not be read (%s); the stages above are unaffected.' % read.get('error_code'), width)
    elif runs:
        lines.append('CI WORKFLOW RUNS  (imported claims; not verified)')
        for run in runs:
            lines += word_wrap('  %s %s  claims %s | revision %s | observed %s | %s' % (
                run.get('workflow') or 'workflow', run.get('run_id'), run.get('status'), str(run.get('repository_revision'))[:12],
                run.get('observed_at'), 'tied to this operation' if run.get('relation') == 'related_operation' else 'for the cited revision'), width)
            lines += word_wrap('     ' + str(run.get('run_url')), width)
    else:
        lines += word_wrap('CI workflow runs: none imported for this operation or its cited revision '
                           '(workflow-import records one; it stays an inert claim).', width)
    if read.get('status') == 'partial':
        lines += word_wrap('(only the first %s imported runs for this policy were read)' % read.get('records_read'), width)
    lines += word_wrap('Next: ' + str(value.get('next_action')), width)
    lines += word_wrap(MARK_LEGEND, width)
    lines += word_wrap('Evidence %s | %s | no cloud authority' % (
        value.get('evidence_class'), 'native-provider qualified' if value.get('native_provider_qualified') else 'not native-provider qualified'), width)
    return lines


ENTRY_STATES = {'ready': 'ready to record', 'recorded_elsewhere': 'recorded from another repository',
                'blocked_by_component': 'refused: the component does not consume exactly this policy',
                'needs_object': 'needs the object ID', 'other_tenant': 'belongs to another tenant'}
ENTRY_MISSING = {'revision': 'a commit', 'backend': 'the backend', 'resource_address': 'the resource address'}


def _entry_state(candidate):
    state = candidate.get('state')
    if state == 'recorded':
        return 'recorded (%s)' % (candidate.get('recorded') or {}).get('freshness', 'unknown')
    if state == 'needs_choice':
        return 'needs ' + ' and '.join(ENTRY_MISSING.get(name, name) for name in candidate.get('missing') or [])
    return ENTRY_STATES.get(state, str(state))


def _entry_key(key):
    key = str(key)
    return key[:14] + '...' + key[-8:] if len(key) > 28 else key


def repository_entry_lines(value, width, focus=0):
    """The policies a repository holds, each with its state in this store; the focused one is marked."""
    lines = word_wrap('[REPOSITORY ENTRY] %s' % value.get('repository'), width)
    revision = value.get('revision')
    lines += word_wrap(('Commit %s (read from .git)' % str(revision)[:12] if revision else 'No commit could be read from .git')
                       + ' | store tenant %s' % str(value.get('tenant_id'))[:8], width)
    for component in value.get('components') or []:
        lines += word_wrap('Stack %s, component %s: %s' % (
            component.get('stack'), component.get('component'),
            '%d %s' % (component.get('policies', 0), 'policy' if component.get('policies') == 1 else 'policies')
            if component.get('selectable') and 'reason' not in component else
            {'not_selectable': 'not selectable (abstract or unresolved)', 'no_policies_input': 'no vars.policies input'}.get(
                component.get('reason'), str(component.get('reason')))), width)
    if value.get('status') != 'discovered' and value.get('blockers'):
        lines += word_wrap('Blocked: ' + ', '.join(value['blockers']), width)
    for index, candidate in enumerate(value.get('candidates') or []):
        observed = candidate.get('observed') or {}
        short = str(candidate.get('object_id'))[:8]
        label = ('%s (%s)' % (observed.get('name'), short) if observed.get('present') else
                 'not observed in this store' + (' (%s)' % short if candidate.get('object_id') else ''))
        lines.append('')
        lines += word_wrap('%s%d  %s | %s / %s' % ('> ' if index == focus else '  ', candidate.get('number', index + 1), label,
                                                  candidate.get('stack'), candidate.get('component')), width)
        backend = '%s (%s)' % (candidate.get('backend'), {'none_declared': 'none declared', 'component_declared': 'declared by the component'}.get(
            candidate.get('backend_source'), candidate.get('backend_source'))) if candidate.get('backend') else 'backend unknown'
        lines += word_wrap('     %s | key %s | backend %s' % (_entry_state(candidate), _entry_key(candidate.get('policy_key')), backend), width)
        if candidate.get('resource_address'):
            lines += word_wrap('     address ' + str(candidate['resource_address']), width)
        lines += word_wrap('     ' + str(candidate.get('explanation', '')), width)
    lines.append('')
    lines += word_wrap('Next: ' + str(value.get('next_action')), width)
    if value.get('candidates'):
        lines += word_wrap('Enter on a policy puts its exact command in the command bar for review; nothing runs until you '
                           'submit it, and Esc discards it. Up and Down move between policies.', width)
    return lines


RECORD_WORDS = {'workflow_run': 'CI workflow run', 'device_evidence': 'device evidence', 'repository_intent': 'repository intent',
                'deployment_receipt': 'deployment record', 'source_reference': 'source reference', 'schedule': 'schedule',
                'adoption': 'adoption', 'ownership_index': 'ownership index', 'provider_refresh': 'provider refresh',
                'queue_review': 'queue review', 'adoption_receipt': 'adoption receipt'}


def recorded_lines(value, width):
    """A record the store just accepted: what it is, whether it is new, and for a CI run what it claims."""
    kind = str(value.get('kind'))
    lines = word_wrap('[RECORDED] %s %s | %s | %s' % (
        RECORD_WORDS.get(kind, kind), str(value.get('artifact_id'))[:12],
        'new record' if value.get('created') else 'already recorded; nothing changed', value.get('recorded_at')), width)
    data = value.get('data') if isinstance(value.get('data'), dict) else {}
    if kind == 'workflow_run' and data:
        links = ['linked to %s %s' % ('operation' if row.get('relation') == 'related_operation' else 'observation',
                                       str(row.get('target_id'))[:12])
                 for row in data.get('relationships') or [] if isinstance(row, dict)]
        lines += word_wrap('%s %s: %s | revision %s | observed %s | %s' % (
            data.get('workflow') or 'workflow', data.get('run_id'), data.get('status'),
            str(data.get('repository_revision'))[:12], data.get('observed_at'), '; '.join(links) or 'no local links'), width)
        lines += word_wrap('An imported claim, not verified. Delivery (v) lists it beside the stages of the operation it '
                           'links to, or of an operation whose intent cites its revision; it never marks a stage done. '
                           ':workflows lists every imported run for the selected policy.', width)
    return lines


def families_lines(value, width):
    """Each family with its stage, where it appears in the workbench, and the qualification it still needs."""
    lines = ['[POLICY FAMILIES]']
    if not value.get('available'):
        if value.get('reason') == 'family_coverage_malformed':
            return lines + word_wrap('The family coverage table could not be read: %s. Nothing from it is shown.' % value.get('detail'), width)
        return lines + word_wrap('The family coverage table is not packaged with this runtime (%s).' % value.get('reason'), width)
    source = value.get('source') or {}
    lines += word_wrap('From %s (sha256 %s); live qualification: %s.' % (
        source.get('path'), str(source.get('sha256'))[:12],
        ', '.join(sorted({str(row.get('live')) for row in value.get('families') or []})) or 'unknown'), width)
    for row in value.get('families') or []:
        lines.append('')
        lines += word_wrap(str(row.get('family')), width)
        lines += _labelled('  Stage', str(row.get('stage')), width, 15)
        lines += _labelled('  Workbench', str(row.get('workbench')), width, 15)
        lines += _labelled('  Route', '%s | %s' % (row.get('route'), row.get('material')), width, 15)
        lines += _labelled('  Still needs', str(row.get('qualification_needed')), width, 15)
    return lines


# What a refusal means and the next step, for the codes an engineer meets in ordinary work.
# Unknown codes show only the engine's own message; nothing is guessed.
REFUSALS = {
    'workbench_repository_intent_missing': (
        'No repository intent was recorded for this policy. Inspection, relationships, history, health and diagnostics '
        'work without one.',
        'To manage it from a repository: generate or adopt it with the wizard, copy the project into the repository '
        'you maintain and commit it, then :repository-entry REPOSITORY lists its policies and fills in the exact '
        'repository-import command for review (s shows what exists here).'),
    'selection_required': (
        'This view belongs to one policy, and none is selected.',
        'press 1 for Estate and Enter on a policy, then try again.'),
    'expired_request': (
        'The plan\'s approval window has closed, or the local clock reads outside it.',
        'Prepare a new proposal; v shows the window of the active operation.'),
    'maintenance_approval_required': (
        'The digest supplied does not match the reviewed plan.',
        'Review the plan (5) and approve with its exact review digest.'),
    'maintenance_replay_forbidden': (
        'This operation is no longer awaiting approval: it was already dispatched, or it was rejected. Execution is '
        'never replayed.',
        'Use reconcile for an uncertain outcome; v shows where the operation stands.'),
    'maintenance_repository_stale': (
        'The repository changed after this proposal cited its intent, or its component no longer consumes exactly '
        'this policy.',
        'Press 9 to see which; fix the component if it no longer consumes the policy, then repository-refresh REVISION '
        'records the current source, and prepare a new proposal.'),
    'workbench_repository_stale': (
        'The repository changed since its recorded intent, or its component no longer consumes exactly this policy.',
        'Press 9 to see which; fix the component if it no longer consumes the policy, then repository-refresh REVISION '
        'records the current source.'),
    'maintenance_plan_stale': (
        'The service changed while the plan was being prepared, or after it was prepared.',
        'Collect, then prepare a new proposal.'),
    'workbench_desired_capability': (
        'The desired policy uses a setting definition, value, platform or technology outside the supported capability map.',
        "Change it in the repository's stack input to something the capability map accepts (the engine's message names "
        'it), repository-refresh REVISION, then propose again.'),
}


def refusal_lines(value, width):
    """A refusal: the engine's code and message, then what it means and the next step when the code is known."""
    error = value.get('error') if isinstance(value.get('error'), dict) else {}
    code = str(error.get('code', 'unknown'))
    lines = word_wrap('[REFUSED] ' + code, width)
    if error.get('message'):
        lines += word_wrap(str(error['message']), width)
    if code in REFUSALS:
        meaning, step = REFUSALS[code]
        lines += word_wrap('What it means: ' + meaning, width)
        lines += word_wrap('Next: ' + step, width)
    return lines


CHECK_WORDS = {'clear': 'clear', 'attention': 'needs attention', 'not_recorded': 'no repository intent recorded',
               'not_imported': 'no device evidence imported',
               'explained_by_collection': 'stale; explained by the failed collection above',
               'partly_checked': 'partly checked: the read bound was reached', 'unavailable': 'could not be read'}


def diagnostics_lines(value, width):
    """What needs attention for one policy: each observed fact, its evidence and the next step; then what is clear."""
    signals = [signal for signal in value.get('signals') or [] if isinstance(signal, dict)]
    partial = any(state in ('partly_checked', 'unavailable') for state in (value.get('checked') or {}).values())
    summary = (_plural(len(signals), 'signal') + (' need attention' if len(signals) != 1 else ' needs attention') if signals
               else 'no signal, but some areas were not fully read' if partial
               else "nothing needs attention in this store's records")
    lines = ['[DIAGNOSTICS]']
    lines += word_wrap('%s (%s) | %s' % (value.get('name') or '(no name)', value.get('object_id'), summary), width)
    for signal in signals:
        lines.append('')
        lines += word_wrap('[!] %s  %s' % (signal.get('area'), signal.get('code')), width)
        lines += _labelled('  Observed', str(signal.get('observed')), width, 12)
        evidence = signal.get('evidence') if isinstance(signal.get('evidence'), dict) else {}
        shown = ', '.join('%s %s' % (key, _value(item) if not isinstance(item, str) else item) for key, item in evidence.items()
                          if item not in (None, [], {}) and key not in ('scope',))
        if shown:
            lines += _labelled('  Evidence', shown, width, 12)
        lines += _labelled('  Next', str(signal.get('next_step')), width, 12)
    lines.append('')
    lines.append('CHECKED')
    for area, state in (value.get('checked') or {}).items():
        lines += word_wrap('  %s %s' % (pad(area.replace('_', ' '), 16), CHECK_WORDS.get(state, str(state))), width)
    for text in value.get('limitations') or []:
        lines += word_wrap('Limitation: ' + str(text), width)
    return lines


ORIGIN_WORDS = {'repository_intent': 'repository intent', 'historical_adoption': 'historical adoption',
                'current_observation': 'current observation'}


def _place(origin):
    return '%s:%s:%s' % (origin.get('path'), origin.get('line'), origin.get('column'))


def lineage_lines(value, width):
    """Where each effective value is defined, and what it overrides, through Atmos inheritance."""
    import re
    lines = ['[REPOSITORY LINEAGE]']
    if value.get('status') != 'available':
        if value.get('status') == 'blocked':
            lines += word_wrap('The recorded resolution is blocked: ' + ', '.join(str(b.get('code')) for b in value.get('blockers', [])), width)
        else:
            lines += word_wrap('No repository resolution was captured or recorded for this policy (%s). Record the repository '
                               'you maintain with repository-import, or press s to see what exists here.' % value.get('reason', 'unknown'), width)
        return lines
    origin = value.get('provenance_origin') if isinstance(value.get('provenance_origin'), dict) else {}
    source = ORIGIN_WORDS.get(origin.get('kind'), str(origin.get('kind')))
    if origin.get('artifact_id'):
        source += ' ' + str(origin['artifact_id'])[:12]
    if origin.get('recorded_at'):
        source += ' recorded ' + str(origin['recorded_at'])
    if origin.get('source_revision'):
        source += ' | revision %s (%s)' % (str(origin['source_revision'])[:12], 'content verified' if origin.get('revision_content_verified') else 'caller asserted')
    lines += _labelled('Source', source + ' | ' + str(value.get('freshness')).replace('_', ' '), width, 11)
    repository = value.get('repository') if isinstance(value.get('repository'), dict) else {}
    lines += _labelled('Repository', '%s | %s / %s' % (repository.get('path'), repository.get('stack'), repository.get('component')), width, 11)
    fields = [row for row in value.get('fields') or [] if isinstance(row, dict)]
    lines += _labelled('Contents', '%s from %s; values are not shown here' % (
        _plural(len(fields), 'effective field'), _plural(len(value.get('sources') or []), 'source file')), width, 11)
    keys = sorted({match for row in fields for match in re.findall(r'p_[0-9a-f]{32}_[0-9a-f]{32}', str(row.get('effective_pointer')))})
    if len(keys) == 1:
        lines += word_wrap('<key> = ' + keys[0], width)
    for row in fields:
        pointer = str(row.get('effective_pointer'))
        if len(keys) == 1:
            pointer = pointer.replace(keys[0], '<key>')
        lines += word_wrap('  ' + pointer, width)
        winner = row.get('winner') if isinstance(row.get('winner'), dict) else {}
        lines += word_wrap('      defined in  ' + _place(winner), width)
        for earlier in reversed(row.get('earlier_origins') or []):
            if isinstance(earlier, dict):
                text = '      overrides   %s  %s' % (_place(earlier), earlier.get('pointer'))
                lines += word_wrap(text.replace(keys[0], '<key>') if len(keys) == 1 else text, width)
    return lines


TITLES = {'current': 'REPOSITORY MATCHES THE RECORDED INTENT',
          'stale': 'REPOSITORY CHANGED SINCE THE RECORDED INTENT',
          'unavailable': 'REPOSITORY UNAVAILABLE'}


def repository_lines(status, width):
    """The repository-status result: what was recorded, whether it still holds, and the next step."""
    freshness = status.get('freshness', {}) if isinstance(status.get('freshness'), dict) else {}
    state = freshness.get('status')
    lines = [TITLES.get(state, 'REPOSITORY STATUS UNKNOWN')]
    scope = status.get('scope') if isinstance(status.get('scope'), dict) else {}
    consumer = status.get('consumer') if isinstance(status.get('consumer'), dict) else {}
    logical = consumer.get('logical_stack')
    stack = str(scope.get('stack', 'unknown')) + (' (' + str(logical) + ')' if logical and logical != 'unknown' else '')
    revision = str(status.get('source_revision', 'unknown')) + (
        ' (content verified)' if status.get('revision_content_verified') else ' (caller asserted; working tree read)')
    for label, text in (('Source   ', scope.get('repository', 'unknown')),
                        ('Stack    ', stack + ' / ' + str(scope.get('component', 'unknown'))),
                        ('Pointer  ', status.get('effective_pointer', 'unknown')),
                        ('Revision ', revision),
                        ('Intent   ', str(status.get('repository_intent_id', 'unknown'))[:16])):
        lines += word_wrap(label + str(text), width)
    reasons = consumer.get('reasons') or []
    lines += word_wrap('Consumer ' + str(consumer.get('status', 'unknown')) + (': ' + ', '.join(map(str, reasons)) if reasons else ''), width)
    now = (freshness.get('consumer') or {}).get('status')
    if now and now != consumer.get('status'):
        lines += word_wrap('Consumer now ' + str(now), width)
    if state == 'stale':
        sources = freshness.get('sources') or {}
        lines.append('SOURCES')
        for kind, label in (('changed', 'changed  '), ('added', 'added    '), ('removed', 'removed  ')):
            for path in sources.get(kind, []):
                lines += word_wrap('  ' + label + str(path), width)
        if isinstance(freshness.get('field_changes'), dict):
            lines.append('DESIRED POLICY AT THE INTENT POINTER')
            lines += change_lines(freshness['field_changes'], width, 'BEFORE (recorded intent)', 'AFTER (repository now)')
        elif freshness.get('pointer_present') is False:
            lines += word_wrap('The intent pointer no longer resolves in the repository.', width)
    elif state == 'unavailable':
        lines += word_wrap('Reason ' + str(freshness.get('reason', 'unknown')), width)
    if status.get('next_action'):
        lines += word_wrap('Next: ' + str(status['next_action']), width)
    return lines
