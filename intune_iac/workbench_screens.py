"""Readable workspace screens over typed engine results.

Pure functions: an engine result and a width in, inert text lines out. Values
are shown as exact JSON, so strings are quoted and null, empty and absent stay
distinct. Every untrusted string passes through the workspace's own escaping.
Nothing is normalized, inferred or hidden; the complete typed evidence is one
key away from each screen (e typed details, r raw record).
"""
from __future__ import annotations

import json

from .workbench_tui import cell_width, fit, pad, safe_text

WIDE = 96
LABEL = 16
SHORT_TABS = {'Estate': 'Est', 'Inspector': 'Insp', 'Relationships': 'Rel', 'History': 'Hist', 'Plan': 'Plan',
              'Execution': 'Exec', 'Coverage': 'Cov', 'Help': 'Help', 'Repository': 'Repo'}


def tab_line(tabs, active, width):
    """Numbered surfaces with the active one bracketed, shortening in tiers until the line fits.

    Full names, then short names. Narrower than that, the line never becomes bare digits: it names the active
    surface and says how to reach and list the others.
    """
    def line(names, gap):
        return gap.join(('[%d %s]' if index == active else '%d %s') % (index + 1, name) for index, name in enumerate(names))
    short = [SHORT_TABS.get(name, name) for name in tabs]
    tiers = (line(tabs, '  '), line(short, ' '),
             '[%d %s]  keys 1-9 switch surfaces; ? lists them' % (active + 1, tabs[active]),
             '[%d %s]  1-9: surfaces, ? lists them' % (active + 1, short[active]),
             '[%d %s]  1-9, ?' % (active + 1, short[active]))
    return next((text for text in tiers if cell_width(text) <= width), tiers[-1])


def short_id(value):
    """The first eight characters of an identity, for orientation only; exact identities appear on each surface."""
    return value[:8] if isinstance(value, str) else str(value)


# Shorter words for long states, used only when nothing else lets the strip fit.
SHORT_STATES = {'succeeded_verified': 'verified', 'not checked': 'unchecked', 'outcome_unknown': 'unknown',
                'recorded_intent_not_revalidated': 'not revalidated', 'desired_state_observed': 'observed'}


# States that are a hazard for the selected policy. When the strip is too long, routine states give way first.
HAZARD_STATES = {'OBSERVED': {'stale'}, 'REPOSITORY': {'stale', 'unavailable', 'consumer mismatch', 'needs attention'},
                 'OPERATION': {'outcome_unknown', 'diverged', 'records disagree', 'unreadable'}}


def context_strip(tenant, selected, facts, width, mode_class=None):
    """Where the engineer is: evidence mode, tenant, policy, observation, repository and operation state, as last reported.

    The mode and the tenant lead every form, so synthetic and live evidence cannot be confused at any width. When the
    line is too long, labels and words shorten first; then routine states give way, and hazards last of all (the
    hazard band below the strip always carries the primary one).
    """
    lead = [mode_word(mode_class), 'TENANT ' + short_id(tenant)]
    if not selected:
        return ' | '.join(lead + ['POLICY none selected'])
    policy = 'POLICY ' + str(facts.get('name', '(name not yet read)')) + ' (' + short_id(selected) + ')'
    states = [('OBSERVED', 'OBS', facts.get('observation', 'unknown')), ('REPOSITORY', 'REPO', facts.get('repository', 'not checked'))]
    if facts.get('operation'):
        states.append(('OPERATION', 'OP', facts['operation']))
    bare = 'POLICY ' + short_id(selected)
    routine = [state for state in states if str(state[2]) not in HAZARD_STATES[state[0]]]
    hazards = [state for state in states if state not in routine]
    kept, shrinking = list(states), []
    for state in list(reversed(routine)) + list(reversed(hazards)):
        kept = [item for item in kept if item is not state]
        shrinking.append(list(kept))
    tiers = [(policy, False, False, states), (policy, True, False, states), (bare, True, False, states),
             (bare, True, True, states)] + [(bare, True, True, remaining) for remaining in shrinking]
    for name, compact, brief, remaining in tiers:
        text = ' | '.join(lead + [name] + [(short if compact else long) + ' ' + (SHORT_STATES.get(str(value), str(value)) if brief else str(value))
                                           for long, short, value in remaining])
        if cell_width(safe_text(text)) <= width:
            return text
    return text


# The primary hazard's ranking, its words and the key that offers its response (a: the action list).
BAND_RANK = ('operation_outcome_unknown', 'operation_diverged', 'operation_record_disagrees', 'operation_unreadable',
             'collection_failed', 'collection_not_finished', 'repository_stale', 'repository_consumer_mismatch',
             'repository_unavailable', 'observation_stale')
OPERATION_SIGNAL = {'outcome_unknown': 'operation_outcome_unknown', 'diverged': 'operation_diverged',
                    'records disagree': 'operation_record_disagrees', 'unreadable': 'operation_unreadable'}


def _band_forms(primary):
    """Longest to shortest wording of one hazard; every form keeps its response."""
    code, evidence = primary.get('code'), primary.get('evidence') if isinstance(primary.get('evidence'), dict) else {}
    operation = short_id(evidence.get('operation_id')) if evidence.get('operation_id') else ''
    if code == 'operation_outcome_unknown':
        return ['! Operation %s: outcome unknown. a: reconcile (never replays)' % operation if operation else
                '! Operation outcome unknown. a: reconcile (never replays)',
                '! Outcome unknown%s. a: reconcile' % (' (op %s)' % operation if operation else ''), '! Outcome unknown. a: reconcile']
    if code in ('operation_diverged', 'operation_record_disagrees', 'operation_unreadable'):
        words = {'operation_diverged': 'diverged from its plan', 'operation_record_disagrees': 'records disagree',
                 'operation_unreadable': 'records unreadable'}[code]
        return ['! Operation %s %s. a: reconcile, i: details' % (operation, words), '! Operation %s. a: reconcile' % words]
    if code == 'collection_failed':
        status = str(evidence.get('status') or 'failed')
        return ['! Last collection %s; the kept observation is stale. a: collect again' % status,
                '! Last collection %s. a: collect' % status]
    if code == 'collection_not_finished':
        return ['! A collection started and recorded no end. a: collect again', '! Collection unfinished. a: collect']
    if code in ('repository_stale', 'repository_consumer_mismatch'):
        words = 'changed since its intent' if code == 'repository_stale' else 'no longer consumes this policy'
        return ['! Repository %s. 9: difference, a: refresh' % words, '! Repository %s. a: refresh' % words.split(' since')[0]]
    if code == 'repository_unavailable':
        return ['! Repository intent cannot be read. 9: repository, i: details', '! Repository unreadable. 9: repository']
    return ['! Observation stale. a: collect again', '! Observation stale. a: collect']


def hazard_band(facts, signals, width):
    """The primary hazard for the selected policy and the key for its response, or None when nothing is recorded.

    The operation's live status (from this session's results) wins over an older recorded signal: a reconciled
    operation is no longer a hazard, and one known only from this session still is. Other recorded signals are
    counted, with the key that lists them all.
    """
    operation, operation_id = facts.get('operation'), facts.get('operation_id')
    live = [item for item in signals or [] if isinstance(item, dict)]

    def about(item):
        evidence = item.get('evidence') if isinstance(item.get('evidence'), dict) else {}
        return evidence.get('operation_id')
    if operation_id and operation not in OPERATION_SIGNAL:
        # This session's newer result for that operation resolved it; only that operation's older signal is set aside.
        live = [item for item in live if not (item.get('area') == 'operations' and about(item) == operation_id)]
    if operation in OPERATION_SIGNAL and not any(item.get('code') == OPERATION_SIGNAL[operation]
                                                 and (not operation_id or about(item) in (None, operation_id)) for item in live):
        # Known from this session's own result before diagnostics recorded it.
        live.append({'area': 'operations', 'code': OPERATION_SIGNAL[operation],
                     'evidence': {'operation_id': operation_id} if operation_id else {}})
    unique = {}
    for item in live:
        unique.setdefault((item.get('code'), about(item)), item)
    live = list(unique.values())
    ranked = sorted((item for item in live if item.get('code') in BAND_RANK), key=lambda item: BAND_RANK.index(item['code']))
    primary = ranked[0] if ranked else None
    if primary is None:
        return None
    # Every other finding is counted, the same kind for another operation included.
    others = len([item for item in live if item is not primary])
    more = '  +%d more: i' % others if others else ''
    forms = _band_forms(primary)
    for text in [form + more for form in forms] + forms:
        if cell_width(text) <= width:
            return text
    return fit(forms[-1], width)


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
        if line and cell_width(word) > width and width - cell_width(line) - 1 >= 4:
            # The word must be split anyway: start it after the current text rather than leave that text alone.
            word, line = line + ' ' + word, ''
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
                # The whole setting record is in the change; its exact value is shown against its absence.
                record = change.get('value') if isinstance(change.get('value'), dict) else {}
                shown = _setting_value(record.get('settingInstance')) if record else '(not in this result)'
                rows.append((label + '  ' + kind, '(absent)' if kind == 'added' else shown, shown if kind == 'added' else '(absent)'))
            elif kind == 'reordered':
                rows.append(('settings order  ' + ', '.join(map(str, change.get('before_order', []))) + '  ->  '
                             + ', '.join(map(str, change.get('after_order', []))), None, None))
        elif kind == 'changed':
            rows.append((str(field), _value(change.get('before')), _value(change.get('after'))))
        elif kind in ('added', 'removed'):
            rows.append((str(field) + '  ' + ('+ ' if kind == 'added' else '- ') + _target(change.get('value')), None, None))
    return rows


def change_lines(changes, width, before_label='BEFORE (observed)', after_label='AFTER (desired)', remainder=None):
    """A field-change list as a table (wide) or stacked before and after rows (narrow).

    A comparison cut at its limit says so. ``remainder`` names where the complete bodies are, for callers whose
    result holds them; without it nothing beyond the cut is claimed.
    """
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
        lines += word_wrap('Only the first %d changes are listed: the comparison stopped there, and this result holds no list '
                           'beyond it%s.' % (count, '; ' + remainder if remainder else ''), width)
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


# Where an observation came from, in words; anything else is shown as recorded.
EVIDENCE_WORDS = {'synthetic': 'synthetic observation', 'graph_capture_unverified': 'unverified capture',
                  'graph_authenticated_observation': 'live read-only observation',
                  'graph_reader_laboratory': 'laboratory observation (recorded responses; source not authenticated)',
                  'graph_reader_attempt': 'failed read (no policy body)',
                  'mixed_observations': 'observations of more than one kind',
                  'synthetic_local_process_and_modeled_service_only': 'synthetic (modeled service)'}
# The mode word that leads the context strip, so synthetic, laboratory and live evidence cannot be confused.
# Exact classes only: a class not listed here is MODE UNKNOWN, never the nearest-sounding mode.
MODE_WORDS = {'synthetic': 'SYNTHETIC', 'synthetic_local_process_only': 'SYNTHETIC',
              'synthetic_local_process_and_modeled_service_only': 'SYNTHETIC',
              'graph_capture_unverified': 'CAPTURE', 'graph_reader_laboratory': 'LABORATORY',
              'graph_reader_attempt': 'READ FAILED', 'graph_authenticated_observation': 'LIVE READ-ONLY',
              'mixed_observations': 'MIXED'}


# An observation's coverage in words: complete means this run read all three collections in full.
COVERAGE_WORDS = {'complete': 'policy list, settings and assignments read in full'}


def coverage_words(coverage):
    return COVERAGE_WORDS.get(coverage, 'collection %s (i shows what was not read)' % str(coverage).replace('_', ' '))


# Diagnostics area states that mean the area was not examined, in words.
AREA_STATE_WORDS = {'not_recorded': '(no intent recorded)', 'not_imported': '(not imported)',
                    'partly_checked': '(partly read)', 'unavailable': '(could not be read)'}


def evidence_words(evidence_class):
    return EVIDENCE_WORDS.get(evidence_class, str(evidence_class or 'unknown evidence').replace('_', ' '))


def mode_word(evidence_class):
    return MODE_WORDS.get(evidence_class, 'MODE UNKNOWN') if isinstance(evidence_class, str) else 'MODE UNKNOWN'


def _setting_summary(instance, width):
    """A setting as the evidence records it: its definition and value. A choice value's meaning is not translated."""
    if not isinstance(instance, dict):
        return word_wrap('    unreadable setting instance (r shows the record)', width)
    lines = word_wrap('    ' + str(instance.get('settingDefinitionId')), width)
    kind = str(instance.get('@odata.type', ''))
    if 'ChoiceSettingInstance' in kind and isinstance(instance.get('choiceSettingValue'), dict):
        choice = instance['choiceSettingValue']
        children = choice.get('children') or []
        text = '= %s%s' % (_value(choice.get('value')), '  (%s)' % _count(len(children), 'child setting', 'child settings') if children else '')
        return (lines + _labelled('', text, width, 6)
                + _labelled('', 'meaning not established; d shows what is known', width, 8))
    return lines + _labelled('', '= ' + _setting_value(instance), width, 6)


def inspector_lines(value, width):
    """One policy: what it is, what the evidence says it does, what needs attention, and what can be done next."""
    body = value.get('body') if isinstance(value.get('body'), dict) else {}
    lines = word_wrap('POLICY  ' + str(value.get('name') or '(no name in this result)'), width)
    identity = [str(value.get('object_id', 'unknown'))]
    if body:
        technologies = body.get('technologies')
        tags = body.get('role_scope_tag_ids')
        identity += [str(body.get('platforms')), ', '.join(map(str, technologies)) if isinstance(technologies, list) else _value(technologies),
                     'scope tags ' + (' '.join(_value(tag) for tag in tags) if isinstance(tags, list) else _value(tags))]
    lines += _labelled('Identity', ' | '.join(identity), width, 10)
    # Where the evidence comes from, then what that run covered, then its freshness: each a separate clause.
    source = [evidence_words(value.get('evidence_class'))]
    if value.get('run_id') is not None:
        source.append('run %s' % value['run_id'])
    source.append(str(value['observed_at']) if value.get('observed_at') else 'time not recorded')
    clauses = [', '.join(source)]
    clauses += [coverage_words(value['coverage'])] if value.get('coverage') else []
    clauses += [str(value['freshness'])] if value.get('freshness') else []
    lines += _labelled('From', '; '.join(clauses), width, 10)
    lines += _attention_lines(value, width)
    lines += ['', 'WHAT THE EVIDENCE SAYS IT DOES']
    settings = body.get('settings', {}).get('settings') if isinstance(body.get('settings'), dict) else None
    if isinstance(settings, list):
        lines.append('  ' + _count(len(settings), 'setting', 'settings'))
        for row in settings:
            lines += _setting_summary(row.get('settingInstance') if isinstance(row, dict) else None, width)
    else:
        lines.append('  Settings are not in this result.')
    assignments = body.get('assignments')
    if isinstance(assignments, list):
        names = value.get('target_names') if isinstance(value.get('target_names'), dict) else {}
        grouped = any(isinstance(row, dict) and 'group_id' in row for row in assignments)
        note = '; group names were not captured' if grouped and not names else ''
        lines += word_wrap('  %s%s' % (_count(len(assignments), 'target', 'targets'), note), width)
        for row in assignments:
            if not isinstance(row, dict):
                lines += word_wrap('    ' + _value(row), width)
                continue
            text = TARGET_WORDS.get(row.get('type'), safe_text(str(row.get('type'))))
            if 'group_id' in row:
                text += '  ' + safe_text(str(row['group_id'])) + (('  "%s"' % safe_text(str(names[row['group_id']]))) if row['group_id'] in names else '')
            lines += _labelled('', text, width, 4)
            if row.get('filter_type') not in (None, 'none'):
                lines += _labelled('', 'filter ' + safe_text(str(row['filter_type'])) + ' ' + safe_text(str(row.get('filter_id'))), width, 13)
    elif body:
        lines.append('  Targets ' + ('were not collected (null).' if assignments is None else 'are unreadable.'))
    if body:
        lines += _labelled('  Description', _value(body.get('description')), width, 15)
    repository = value.get('selected_repository') if isinstance(value.get('selected_repository'), dict) else None
    scope = repository.get('scope') if repository and isinstance(repository.get('scope'), dict) else {}
    managed = 'ownership %s; %s' % (value.get('ownership', 'unknown'), 'repository intent recorded from %s (%s / %s)' % (
        scope.get('repository'), scope.get('stack'), scope.get('component')) if repository else 'no repository intent recorded')
    lines += _labelled('  Managed', managed, width, 15)
    return lines


def _attention_lines(value, width):
    """What diagnostics records as needing attention, the areas it could not examine, and the next steps."""
    lines = []
    attention = value.get('attention') if isinstance(value.get('attention'), dict) else None
    if attention is not None:
        lines += ['', 'NEEDS ATTENTION']
        signals = [signal for signal in attention.get('signals') or [] if isinstance(signal, dict)]
        areas = attention.get('checked') if isinstance(attention.get('checked'), dict) else {}
        if attention.get('status') == 'unavailable':
            lines += word_wrap('  Diagnostics could not be read (%s); i shows the details.' % attention.get('error_code'), width)
        elif not signals:
            clear = ', '.join(area.replace('_', ' ') for area, state in areas.items() if state == 'clear')
            lines += word_wrap('  Nothing recorded needs attention%s.' % (' (checked: %s)' % clear if clear else ''), width)
        guided = isinstance(value.get('actions'), list)
        for signal in signals:
            lines += _labelled('  !', str(signal.get('observed')), width, 4)
            if guided and signal.get('next_step'):
                # Each condition carries its own response, so issue and action are read together.
                lines += _labelled('    Next', str(signal.get('next_step')), width, 10)
        # Areas that were not examined stay named as such: nothing is known about them either way.
        unknown = ['%s %s' % (area.replace('_', ' '), AREA_STATE_WORDS[state]) for area, state in areas.items()
                   if state in AREA_STATE_WORDS]
        if unknown:
            lines += word_wrap('  Not fully checked: %s.' % '; '.join(unknown), width)
    if isinstance(value.get('actions'), list):
        offered = [action for action in value['actions'] if isinstance(action, dict)]
        if offered:
            lines += ['', 'ACTIONS']
            lines += word_wrap('  a stages one for review; nothing runs until you submit it.', width)
            for number, action in enumerate(offered, 1):
                blocked = action.get('blocked') or {}
                state = '' if action.get('available') else ' (blocked: %s)' % BLOCK_WORDS.get(
                    blocked.get('code'), str(blocked.get('code') or 'not available'))
                lines += _labelled('  %d.' % number, str(action.get('label')) + state, width, 6)
        return lines
    actions = [action for action in value.get('next_actions') or [] if isinstance(action, dict)]
    if actions:
        lines += ['', 'NEXT']
        for action in actions:
            lines += _labelled('  ', str(action.get('step')), width, 2)
    return lines


# Why an action is blocked, in a few words; the actions layer (a) gives the engine's full meaning.
BLOCK_WORDS = {'maintenance_observation_stale': 'the observation is not fresh',
               'maintenance_observation_incomplete': 'the observation is incomplete',
               'maintenance_observation_source_mismatch': 'the observation came from another source',
               'workbench_repository_stale': 'the repository changed since its intent',
               'workbench_repository_unavailable': 'the repository cannot be read',
               'service_required': 'needs a modeled service (--service-root)',
               'workbench_attention_not_established': 'diagnostics not read yet',
               'workbench_fresh_output_required': 'no fresh operation directory'}


def actions_lines(actions, focus, width, name=None, object_id=None, submit='Enter'):
    """The guided actions for the selected policy: what each is, whether it is available, its exact command and what
    it does. A blocked action says why, with the engine's own code."""
    lines = word_wrap('ACTIONS  for %s (%s)' % (name or 'the selected policy', short_id(object_id)), width)
    lines += word_wrap('Nothing runs until you submit it: Enter puts the focused command in the command bar for review, '
                       '%s there submits it, Esc discards it.' % submit, width)
    for index, action in enumerate(actions):
        lines.append('')
        state = 'available' if action.get('available') else 'blocked'
        lines += _labelled('%s %d.' % ('>' if index == focus else ' ', index + 1), '%s  (%s)' % (action.get('label'), state), width, 5)
        if action.get('available'):
            # A missing input is named where it goes, as the command bar's cursor will be.
            command, cursor = str(action.get('command') or ''), action.get('cursor')
            names = ' '.join(str(need).split(':')[0] for need in action.get('needs') or [])
            if names and isinstance(cursor, int) and 0 <= cursor <= len(command):
                command = (command[:cursor] + names + ' ' + command[cursor:].lstrip()).rstrip()
            lines += _labelled('', 'command  ' + command.rstrip(), width, 5)
            for need in action.get('needs') or []:
                lines += _labelled('', 'needs  ' + str(need), width, 5)
        else:
            blocked = action.get('blocked') or {}
            code = blocked.get('code')
            meaning = REFUSALS[code][0] if code in REFUSALS else blocked.get('message')
            lines += _labelled('', 'blocked  %s: %s' % (code, meaning), width, 5)
        lines += _labelled('', str(action.get('effects')), width, 5)
    return lines


def details_lines(value, width):
    """Every field of an engine result as a readable outline: words for absent and yes/no values, lists numbered."""
    lines = []

    def scalar(item):
        if item is None:
            return 'not recorded'
        if isinstance(item, bool):
            return 'yes' if item else 'no'
        return str(item)

    def walk(item, indent):
        if isinstance(item, dict):
            size = min(max([cell_width(str(key)) for key in item] + [0]) + 2, max(12, (width - indent) // 2))
            for key, child in item.items():
                label = ' ' * indent + str(key).replace('_', ' ')
                if isinstance(child, (dict, list)) and child:
                    lines.extend(word_wrap(label + ('  (%d)' % len(child) if isinstance(child, list) else ''), width))
                    walk(child, indent + 2)
                    continue
                shown = scalar(child) if not isinstance(child, (dict, list)) else 'none'
                if cell_width(label) > indent + size - 2:
                    # A name longer than the label column keeps every character, with its value beneath.
                    lines.extend(word_wrap(label, width) + word_wrap(' ' * (indent + 4) + shown, width))
                else:
                    lines.extend(_labelled(label, shown, width, indent + size))
        elif isinstance(item, list):
            for number, child in enumerate(item, 1):
                if isinstance(child, (dict, list)) and child:
                    lines.append(' ' * indent + '%d.' % number)
                    walk(child, indent + 3)
                else:
                    lines.extend(_labelled(' ' * indent + '%d.' % number, scalar(child) if not isinstance(child, (dict, list)) else 'none',
                                           width, indent + 4))
        else:
            lines.extend(word_wrap(' ' * indent + scalar(item), width))

    walk(value, 0)
    return lines


def help_lines(width):
    """The one reference for keys and commands, grouped by what the engineer is doing."""
    groups = (
        ('Surfaces', '1 Estate, 2 Inspector, 3 Relationships, 4 History, 5 Plan, 6 Execution, 7 Coverage, 8 Help, 9 Repository.'),
        ('Views', 'o relationship overview, d setting dictionary, l lineage, h health, m maintenance queue, i diagnostics, '
                  'v delivery of the active operation, s what exists beside the store.'),
        ('Evidence', 'Each view opens as a summary. e shows every field as typed details, r the complete raw engine record, '
                     'Esc returns to the summary.'),
        ('Moving', 'Up and Down choose, Enter selects, PgUp and PgDn scroll, n and p page through long lists, Tab moves '
                   'to the next surface, / searches, f sets estate filters, b or :back returns to the previous view.'),
        ('Actions', 'a lists what can be done next for the selected policy, each with its exact command, what it does '
                    'and whether it is available now. Enter puts the chosen command in the command bar for review; '
                    'Enter there (Ctrl+Enter in the native Windows console) submits it and Esc discards it. Nothing '
                    'runs until you submit it.'),
        ('Commands', ': opens the command bar; Enter submits and Esc discards. Every command the engine accepts is in the '
                     'typed details of this page (e).'),
        ('Changes', 'propose DESIRED_JSON NEW_OPERATION_DIR or propose-from-intent NEW_OPERATION_DIR prepares a proposal; '
                    'execute OPERATION_DIR EXACT_REVIEW_DIGEST runs it only with the digest from its review; reconcile '
                    'OPERATION_DIR reads the service when an outcome is unknown. Moving around never proposes, approves or executes.'),
        ('Session', 'q exits the workbench; the next start reopens the last read-only view. :clear-selection clears the '
                    'selected policy. Between commands nothing is running, so :cancel cancels nothing; Ctrl-C stops a '
                    'running call and ends the session.'),
        ('Context', 'The line under the tabs: the evidence mode, the tenant and the selected policy; OBSERVED fresh '
                    'means the newest complete observation is inside the freshness window and no later collection '
                    'of it failed or is pending; REPOSITORY current means the recorded repository intent still '
                    'matches the repository files and effective configuration; OPERATION is the active '
                    'operation\'s recorded status.'),
        ('Mode', 'The first word of the line under the tabs says where the evidence comes from: SYNTHETIC (a modeled '
                 'service), CAPTURE (an unverified export), LABORATORY (recorded responses; the source is not '
                 'authenticated), LIVE READ-ONLY (an authenticated read), MIXED (more than one of these), READ FAILED '
                 '(a read returned no policy) or MODE UNKNOWN (nothing observed yet, or a kind this version does not name).'),
    )
    lines = ['HELP']
    for name, text in groups:
        lines += _labelled('  ' + name, text, width, 12)
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
RELATION_LABELS = {'scope_tag': 'scope tag', 'generated_from': 'generated',
                   'source_repository_path': 'repository', 'source_source_path': 'source path',
                   'source_atmos_stack': 'stack', 'source_component': 'component',
                   'related_operation': 'operation', 'observed_after': 'observed after'}


def _edge_target(edge):
    relation, target = edge.get('relation'), edge.get('target_id')
    if relation == 'scope_tag':
        return _value(target)
    text = safe_text(str(target))
    details = edge.get('details') if isinstance(edge.get('details'), dict) else {}
    if relation == 'assignment' and details.get('filter_type') not in (None, 'none'):
        text += '  filter ' + safe_text(str(details['filter_type'])) + ' ' + safe_text(str(details.get('filter_id')))
    return text


TREES = {'ascii': ('|-- ', '`-- ', '    '), 'unicode': ('├── ', '└── ', '│   ')}


def _count(number, singular, plural):
    return '%d %s' % (number, singular if number == 1 else plural)


def _users(ids, verb):
    shown = ', '.join(str(item)[:8] for item in ids[:4]) + (', ...' if len(ids) > 4 else '')
    return '%s %s (%s)' % (verb, _count(len(ids), 'policy', 'policies'), shown)


def overview_lines(value, width, rules='ascii', focus=None, selected=None):
    """The estate's relationships: shared groups, filters, scope tags and settings first, then each policy."""
    tree = TREES.get(rules, TREES['ascii'])
    counts = value.get('counts') or {}
    owners = ', '.join('%s %d' % item for item in sorted((value.get('ownership') or {}).items())) or 'none recorded'
    lines = ['[ESTATE OVERVIEW]']
    lines += word_wrap('%s of %s policies read | %s without a complete observation | ownership: %s' % (
        counts.get('policies_read'), counts.get('policies_total'), counts.get('without_complete_observation'), owners), width)
    lines += word_wrap('What several policies share comes first. Up and Down move between policies below (> focus, * selected); '
                       'Enter selects one.', width)

    def section(heading, rows, describe):
        lines.extend(['', heading])
        if not rows:
            lines.append('  none observed')
        for index, row in enumerate(rows):
            last = index == len(rows) - 1
            head, cont = '  ' + (tree[1] if last else tree[0]), '  ' + ('    ' if last else tree[2])
            for number, part in enumerate(word_wrap(describe(row), max(1, width - len(head)))):
                lines.append((head if number == 0 else cont) + part)

    section('TARGETED GROUPS', value.get('groups') or [], lambda row: '%s  %s' % (str(row['group_id'])[:8], ', '.join(
        part for part in ((_users(row['included_by'], 'included by') if row.get('included_by') else ''),
                          (_users(row['excluded_by'], 'excluded by') if row.get('excluded_by') else '')) if part)))
    broad = value.get('broad_targets') or []
    if broad:
        # Targets that name no group, kept apart so they are never read as groups.
        section('ALL-DEVICE AND ALL-USER TARGETS', broad, lambda row: '%s  %s' % (
            TARGET_WORDS.get(row.get('target'), safe_text(str(row.get('target')))), _users(row['used_by'], 'targeted by')))
    section('FILTERS', value.get('filters') or [], lambda row: '%s  %s' % (str(row['filter_id'])[:8], _users(row['used_by'], 'used by')))
    section('SCOPE TAGS', value.get('scope_tags') or [], lambda row: '"%s"  %s' % (row['tag'], _users(row['used_by'], 'used by')))
    section('SHARED SETTINGS  (%s distinct in the estate)' % value.get('distinct_settings', 'unknown'),
            value.get('shared_settings') or [], lambda row: '%s  %s' % (row['setting'], _users(row['used_by'], 'used by')))
    lines.extend(['', 'POLICIES'])
    for index, policy in enumerate(value.get('policies') or []):
        found = policy.get('findings') or []
        reach = ', '.join('targets ' + TARGET_WORDS.get(target, safe_text(str(target))) for target in policy.get('broad_targets') or [])
        text = '%s (%s)  %s, %s, %s, %s%s | owner %s | %s%s' % (
            policy.get('name') or '(no name)', str(policy.get('object_id'))[:8],
            _count(policy.get('included_groups', 0), 'group', 'groups'), _count(policy.get('excluded_groups', 0), 'exclusion', 'exclusions'),
            _count(policy.get('filters', 0), 'filter', 'filters'), _count(policy.get('settings', 0), 'setting', 'settings'),
            ', ' + reach if reach else '', policy.get('ownership'), policy.get('freshness'), '' if found else ' | no findings')
        # As in Estate: > is the keyboard focus, * the pinned selection every surface shows.
        mark = ('>' if index == focus else ' ') + ('*' if selected and policy.get('object_id') == selected else ' ') + ' '
        for number, part in enumerate(word_wrap(text, max(1, width - 3))):
            lines.append((mark if number == 0 else '   ') + part)
        if found:
            lines += word_wrap('    %s: %s' % (_count(len(found), 'finding', 'findings'), ', '.join(map(str, found))), width)
    lines.extend(['', 'NOT ESTABLISHED'])
    missing = value.get('not_established') or []
    if not missing:
        lines += word_wrap('  Nothing was left out: every policy in the store was read with a complete observation.', width)
    for item in missing:
        lines += word_wrap('  ' + ('%s more not read: beyond the read bound' % _count(item.get('count', 0), 'policy', 'policies')
                                   if item.get('reason') == 'beyond_read_bound' else
                                   '%s: no complete observation (last attempt %s)' % (item.get('object_id'), item.get('last_attempt'))), width)
    return lines


def relationship_lines(value, width, rules='ascii'):
    """Typed edges grouped by what they mean, each with its exact target and its evidence class."""
    tree = TREES.get(rules, TREES['ascii'])
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
            last = index == len(rows) - 1
            connector = '  ' + (tree[1] if last else tree[0])
            guide = '  ' + ('    ' if last else tree[2])
            label = RELATION_LABELS.get(edge.get('relation'), str(edge.get('relation')).replace('_', ' '))
            # A label longer than its column keeps every letter and a gap before the target.
            text = (pad(label, 13) if cell_width(label) < 13 else label + '  ') + _edge_target(edge) + ('' if shared else '  [' + safe_text(str(edge.get('assertion_class', 'unknown'))) + ']')
            for number, part in enumerate(word_wrap(text, width - len(connector))):
                lines.append((connector if number == 0 else guide) + part)
    ownership = value.get('ownership_evidence') if isinstance(value.get('ownership_evidence'), dict) else {}
    lines.append('OWNERSHIP')
    reason = ownership.get('reason')
    lines += word_wrap('  ' + tree[1] + pad('writer', 13) + str(value.get('ownership', 'unknown')) + (': ' + str(reason) if reason else ''), width)
    return lines


def history_lines(value, width):
    """Observations newest first, each with what changed since the one before it on this page."""
    from .workbench_diff import field_changes
    lines = ['[OBSERVATION HISTORY]']
    page = value.get('pagination') if isinstance(value.get('pagination'), dict) else {}
    items = [item for item in value.get('history') or [] if isinstance(item, dict)]
    lines += word_wrap('%s (%s)' % (value.get('name') or (items[0].get('name') if items else None) or '(no name)',
                                    value.get('object_id', 'unknown')), width)
    total = page.get('total_observations')
    lines += word_wrap('%s | this page %d from offset %s' % (
        _plural(total, 'observation') if isinstance(total, int) else 'unknown number of observations', len(items), page.get('offset', value.get('offset', 0))), width)
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
MARK_LEGEND = '[x] done  [ ] waiting or not yet  [-] not needed  [?] unknown or required  [!] stopped: failure, expiry or refusal'


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


EVENT_LABELS = {'prepared': 'prepared', 'dispatch_started': 'dispatch started', 'engine_result': 'engine result',
                'service_response': 'service response', 'service_no_change': 'nothing sent', 'verified': 'verified',
                'uncertain': 'outcome unknown', 'reconciled': 'reconciled'}


def _event_text(event):
    """What one journal event recorded, from its own fields."""
    fields = event.get('fields') if isinstance(event.get('fields'), dict) else {}
    kind = event.get('kind')
    if kind == 'prepared':
        return 'approval will need digest ' + str(fields.get('approval_digest'))[:12]
    if kind == 'dispatch_started':
        return 'approved with digest ' + str(fields.get('approval_digest'))[:12]
    if kind == 'engine_result':
        result = fields.get('result') if isinstance(fields.get('result'), dict) else {}
        return 'engine reported %s (%s)' % (result.get('status'), result.get('assurance'))
    if kind == 'service_response':
        response = fields.get('response') if isinstance(fields.get('response'), dict) else {}
        return 'service answered status %s' % response.get('status')
    if kind == 'service_no_change':
        return 'the plan had no configuration change'
    if kind == 'verified':
        return 'readback observed the desired state | readback sha256 ' + str(fields.get('readback_sha256'))[:12]
    if kind == 'uncertain':
        return str(fields.get('error_code'))
    if kind == 'reconciled':
        return '%s, after %s' % (fields.get('classification'), fields.get('previous_status'))
    return 'r shows what it recorded'


def history_event_lines(history, width):
    """The operation's journal events in order; a time only where the store's registration pairs with an event."""
    events = [event for event in (history or {}).get('events') or [] if isinstance(event, dict)]
    if not events:
        return []
    lines = word_wrap('HISTORY  journal events in order (chain verified); a time is when the store registered the '
                      'journal after that event', width)
    for event in events:
        label = EVENT_LABELS.get(event.get('kind'), str(event.get('kind')).replace('_', ' '))
        at = str(event.get('store_recorded_at') or 'time not recorded')
        if at.endswith('Z') and '.' in at:
            at = at.split('.')[0] + 'Z'  # to the second in the column; the raw record keeps the fraction
        head = '  %-3s %-17s %-21s ' % (event.get('sequence'), label, at)
        if width >= 90:
            lines += _labelled(head, _event_text(event), width, len(head))
        else:
            lines += word_wrap(head.rstrip(), width) + word_wrap('      ' + _event_text(event), width)
    unpaired = (history.get('registrations') or 0) - (history.get('paired') or 0)
    if unpaired > 0:
        lines += word_wrap('  %s could not be paired with an event; r shows %s.' % (
            _plural(unpaired, 'store registration'), 'it' if unpaired == 1 else 'them'), width)
    return lines


def delivery_lines(value, width, rules='ascii'):
    """One operation's delivery stages in order, each with a marker, its state in words and its evidence.

    With box-drawing rules the stages hang from one connected spine, first to last; ASCII keeps the plain list.
    """
    lines = ['[DELIVERY]']
    lines += word_wrap('Operation %s | policy %s | journal %s' % (value.get('operation_id'), value.get('object_id'), value.get('journal_status')), width)
    stages = [stage for stage in value.get('stages') or [] if isinstance(stage, dict)]
    for number, stage in enumerate(stages, 1):
        last = number == len(stages)
        if rules == 'unicode':
            head = '──' if number == 1 and last else '┌─' if number == 1 else '└─' if last else '├─'
            cont = '  ' if last else '│ '
        else:
            head = cont = '  '
        mark = head + '[%s] ' % MARKS.get(stage.get('status'), '?')
        label = '%d %s' % (number, STAGE_LABELS.get(stage.get('stage'), str(stage.get('stage'))))
        text = _stage_text(stage)
        if width >= 60:
            for index, part in enumerate(word_wrap(text, width - 24)):
                lines.append((mark + pad(label, 18) if index == 0 else cont + ' ' * 22) + part)
        else:
            lines.append(mark + label)
            lines += [cont + '    ' + part for part in word_wrap(text, width - 6)]
        if stage.get('stage') == 'observed_after' and stage.get('status') == 'differs' and isinstance(stage.get('field_changes'), dict):
            lines += [cont + '    ' + line for line in change_lines(stage['field_changes'], width - 6, 'BEFORE (desired)', 'AFTER (observed)')]
    lines += history_event_lines(value.get('history') if isinstance(value.get('history'), dict) else {}, width)
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
            candidate.get('backend_source'), candidate.get('backend_source'))) if candidate.get('backend') else 'unknown'
        # Labelled rows keep each value with its label; a long key or address wraps under its own column.
        lines += _labelled('     State', _entry_state(candidate), width, 15)
        lines += _labelled('     Key', str(candidate.get('policy_key')), width, 15)
        lines += _labelled('     Backend', backend, width, 15)
        if candidate.get('resource_address'):
            lines += _labelled('     Address', str(candidate['resource_address']), width, 15)
        lines += _labelled('', str(candidate.get('explanation', '')), width, 5)
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
    'maintenance_observation_stale': (
        'The newest observation of this policy is not fresh, or the service changed after it was collected; a change '
        'is never prepared against it.',
        'Collect again (:collect), then prepare the proposal again; i shows the observation\'s freshness. An observation '
        'stamped later than this machine\'s clock is not fresh either.'),
    'maintenance_observation_incomplete': (
        'The newest observation of this policy is incomplete, or the last collection did not finish.',
        'Collect again (:collect); i shows what was not read.'),
    'maintenance_plan_stale': (
        'The service changed while the plan was being prepared, or after it was prepared.',
        'Collect, then prepare a new proposal.'),
    'workbench_desired_capability': (
        'The desired policy uses a setting definition, value, platform or technology outside the supported capability map.',
        "Change it in the repository's stack input to something the capability map accepts (the engine's message names "
        'it), repository-refresh REVISION, then propose again.'),
}


def _words(text):
    return set(''.join(char if char.isalnum() or char == '_' else ' ' for char in text.lower()).split())


def _restates(message, meaning):
    """True when the engine's message already says at least four fifths of what the meaning line would."""
    meant = _words(meaning)
    return bool(meant) and len(meant & _words(message)) * 5 >= len(meant) * 4


def refusal_lines(value, width):
    """A refusal: the engine's code and message, then what it means and the next step when the code is known.

    The meaning is left out when the engine's own message already says it.
    """
    error = value.get('error') if isinstance(value.get('error'), dict) else {}
    code = str(error.get('code', 'unknown'))
    message = str(error.get('message') or '')
    lines = word_wrap('[REFUSED] ' + code, width)
    if message:
        lines += word_wrap(message, width)
    if code in REFUSALS:
        meaning, step = REFUSALS[code]
        if not _restates(message, meaning):
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
