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
    """Numbered surfaces with the active one bracketed; compact names when the full line does not fit."""
    def line(names, gap):
        return gap.join(('[%d %s]' if index == active else '%d %s') % (index + 1, name) for index, name in enumerate(names))
    full = line(tabs, '  ')
    return full if cell_width(full) <= width else line([SHORT_TABS.get(name, name) for name in tabs], ' ')


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
