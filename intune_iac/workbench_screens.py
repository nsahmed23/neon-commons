"""Readable workspace screens over typed engine results.

Pure functions: an engine result and a width in, inert text lines out. Values
are shown as exact JSON, so strings are quoted and null, empty and absent stay
distinct. Every untrusted string passes through the workspace's own escaping.
Nothing is normalized, inferred or hidden; the complete typed evidence is one
key away from each screen (e typed details, r raw record).
"""
from __future__ import annotations

import json
import re

from .workbench_diagnostics import (CLOCK_HOLD_CAUSES, CLOCK_HOLD_REASONS, CLOCK_HOLD_STEPS, clock_hold, CLOCK_HOLD_WORDS,
                                    clock_times, command_arg, with_clock_times)
from .workbench_tui import cell_width, fit, pad, safe_text
from .graph_projection import DISTINCT_KINDS, KIND_WORDS

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


def short_id(value, prefixes=None):
    """An identity shortened for orientation: the read model's unique prefix for it when one is given (at least eight
    characters, extended where another identity shares them), else its first eight characters. Exact identities
    appear on each surface."""
    if not isinstance(value, str):
        return str(value)
    known = prefixes.get(value) if isinstance(prefixes, dict) else None
    if isinstance(known, str) and len(known) >= 8 and value.startswith(known):
        return known
    return value[:8]


# Shorter words for long states, used only when nothing else lets the strip fit.
SHORT_STATES = {'succeeded_verified': 'verified', 'not checked': 'unchecked', 'outcome_unknown': 'unknown',
                'recorded_intent_not_revalidated': 'not revalidated', 'desired_state_observed': 'observed',
                'age unknown': 'age?', 'age unknown (stamped ahead)': 'age?', 'stale (later collection incomplete)': 'stale'}
# The middle form of a state whose full words do not fit but whose cause can still be named (the Context help lists both).
MEDIUM_STATES = {'age unknown (stamped ahead)': 'age unknown', 'stale (later collection incomplete)': 'stale (collection incomplete)'}


# States that are a hazard for the selected policy. When the strip is too long, routine states give way first.
# The proposal's own observation checks, in the strip's words: fresh by age does not apply once the service moved on.
OBSERVED_FROM_ELIGIBILITY = {'service_changed': 'source changed', 'policy_changed': 'policy changed',
                             'source_mismatch': 'other source', 'tenant_mismatch': 'other tenant'}


def observation_word(freshness, reasons):
    """The strip's word for an observation's freshness, naming the cause the record gives where one word would stand
    for several: a clock hold or a stamp ahead of this host's clock means the age is not known (never stale), and a
    stale observation whose only cause is a later collection that did not complete says so."""
    from .workbench_diagnostics import clock_hold
    reasons = reasons if isinstance(reasons, list) else []
    if freshness == 'fresh':
        return 'fresh'
    if clock_hold(reasons):
        return 'age unknown'
    if freshness == 'stale' and 'stamped_after_now' in reasons:
        return 'age unknown (stamped ahead)'
    if freshness == 'stale' and reasons == ['later_collection_not_complete']:
        return 'stale (later collection incomplete)'
    return freshness


def observed_state(facts, default='unknown'):
    """The observation's state for the strip: the failed proposal check when there is one, otherwise freshness."""
    eligibility = facts.get('eligibility') if isinstance(facts.get('eligibility'), dict) else {}
    return OBSERVED_FROM_ELIGIBILITY.get(eligibility.get('reason')) or facts.get('observation', default)


def _strip_severity(state):
    """The band's order of hazards, for the strip: a store for another tenant, then the operation, the repository,
    the observation. The strip keeps the most severe longest, so it and the band lead with the same condition."""
    if state[0] == 'OBSERVED' and state[2] == 'other tenant':
        return 0
    if state[0] == 'OBSERVED' and state[2] == 'age unknown':
        return 1.5  # a clock hold blocks every proposal, so it outlasts a repository change (as in the band)
    return {'OPERATION': 1, 'REPOSITORY': 2, 'OBSERVED': 3}.get(state[0], 4)


HAZARD_STATES = {'OBSERVED': {'stale', 'age unknown', 'age unknown (stamped ahead)', 'stale (later collection incomplete)',
                              'source changed', 'policy changed', 'other source', 'other tenant'},
                 'REPOSITORY': {'stale', 'unavailable', 'consumer mismatch', 'needs attention'},
                 # executing: the strip's word while execute runs, when its outcome is not yet known (run 12, frame 32)
                 'OPERATION': {'outcome_unknown', 'diverged', 'records disagree', 'unreadable', 'held', 'executing'}}


def _newest_operation_id(facts):
    states = facts.get('states') if isinstance(facts.get('states'), dict) else {}
    newest = states.get('operation') if isinstance(states.get('operation'), dict) else {}
    return newest.get('operation_id') if isinstance(newest.get('operation_id'), str) else None


def _operation_from_states(facts):
    """The newest operation's state from the last read of the policy, in the strip's words; None when none is recorded.
    A prepared operation whose approval window closed reads expired, as everywhere else."""
    states = facts.get('states') if isinstance(facts.get('states'), dict) else {}
    operation = states.get('operation') if isinstance(states.get('operation'), dict) else None
    state = (operation.get('journal_status') or operation.get('status')) if operation else None
    if not isinstance(state, str):
        return None
    return 'expired' if state == 'prepared' and operation.get('approval_window') in ('closed', 'closed_recorded') else state


# What each abbreviated width form of the strip stands for, by the key a form reports: 'T' and 'P' for the tenant and
# the policy, otherwise the full state value whose short word the strip shows. The pinned forms are unchanged
# (P-PRES-15); the screen defines each one it shows, once (run 11 item 12).
STRIP_DEFINITIONS = {
    'T': 'T = tenant', 'P': 'P = policy',
    # Each row says what the word stands for and what it means for the next action, not the state's own words again
    # (run 12 item 6). The Context help (help_lines) keeps the full state words beside each short word.
    'succeeded_verified': 'verified = executed and read back as desired; v shows the rest',
    'not checked': 'unchecked = the repository was not compared with the recorded intent',
    'outcome_unknown': 'unknown = the change may have reached the service; reconcile it (a)',
    'recorded_intent_not_revalidated': 'not revalidated = shown from the recorded intent; repository not re-read',
    'desired_state_observed': 'observed = a readback found the service already holds the desired state',
    # Cause only: a clock hold or a stamp ahead is not cured by collecting (the band and Diagnostics say so; review 18).
    'age unknown': "age? = the observation's age is not known; 2 Inspector says why",
    'age unknown (stamped ahead)': "age? = stamped ahead of this host's clock; 2 Inspector says why",
    'stale (later collection incomplete)': 'stale = a later collection did not finish; collect again (a)'}


# What a strip that leaves states out ends with: how many, and the key that shows them in full (Help prints the line).
STRIP_MORE = '+%d more: ?'


def strip_rows(text, width):
    """The strip as rows: one, or at the narrowest widths, where the mode, the tenant and the policy fill the row, the
    marker on a row of its own so it is never cut."""
    if cell_width(safe_text(text)) <= width:
        return [text]
    head, separator, marker = text.rpartition(' | +')
    if separator and re.fullmatch(r'\d+ more: \?', marker):
        return [head, '+' + marker]
    return [text]


def strip_layout(text, definitions, width):
    """The rows under the title and tab line for the strip and for the definitions of its abbreviated forms:
    (strip rows, key rows). Where the marker had to take a row of its own, it shares that row with the definitions
    (and no key row follows the prompt) rather than costing the body a second row (run10-R1); otherwise the two are
    as strip_rows and strip_key_rows say."""
    rows = strip_rows(text, width)
    keys = strip_key_rows(definitions, width)
    if len(rows) == 2 and keys:
        return rows[:1] + strip_key_rows([rows[1]] + list(definitions), width), []
    return rows, keys


def context_strip(tenant, selected, facts, width, mode_class=None):
    """The strip's text; see strip_choice."""
    return strip_choice(tenant, selected, facts, width, mode_class)[0]


def strip_choice(tenant, selected, facts, width, mode_class=None):
    """Where the engineer is: evidence mode, tenant, policy, observation, repository and operation state, as last reported.

    The mode and the tenant lead every form, so synthetic and live evidence cannot be confused at any width. When the
    line is too long, labels and words shorten first; then routine states give way, and hazards last of all (the
    hazard band below the strip always carries the primary one).

    Returns (text, definitions): the form chosen and the definition of each abbreviated width form it shows.
    """
    lead = [mode_word(mode_class), 'TENANT ' + short_id(tenant)]
    tight = [mode_word(mode_class), 'T ' + short_id(tenant)]
    if not selected:
        forms = [(' | '.join(lead + ['POLICY none selected']), []), (' | '.join(tight + ['no policy']), ['T']),
                 (' | '.join(tight), ['T'])]
        return _chosen(forms, width)
    own = short_id(selected, facts.get('identity_prefixes'))
    policy = 'POLICY ' + str(facts.get('name', '(name not yet read)')) + ' (' + own + ')'
    states = [('OBSERVED', 'OBS', observed_state(facts)), ('REPOSITORY', 'REPO', facts.get('repository', 'not checked'))]
    operation = facts.get('operation') or _operation_from_states(facts)
    if operation:
        states.append(('OPERATION', 'OP', operation))
    # An operation that is not the newest for the policy is named, so the strip and the Operation row agree.
    shown = facts.get('operation_id') if facts.get('operation') else None
    newest = _newest_operation_id(facts)
    named = short_id(shown, facts.get('identity_prefixes')) if shown and newest and shown != newest else ''
    bare = 'POLICY ' + own
    routine = [state for state in states if str(state[2]) not in HAZARD_STATES[state[0]]]
    # Hazards give way least severe first, so the one the band leads with is the last to go.
    hazards = sorted((state for state in states if state not in routine), key=_strip_severity)
    kept, shrinking = list(states), []
    for state in list(reversed(routine)) + list(reversed(hazards)):
        kept = [item for item in kept if item is not state]
        shrinking.append(list(kept))
    # One spelling of each segment (OBS, REPO, OP) at every width. The policy's name outlasts the shortest state words
    # and the tenant's label before it gives way to the bare identity, so the name shows whenever any form holds it.
    # The words shorten in three steps: all of them, then the cause named in fewer words, then the short word.
    tiers = [(policy, 0, lead, states), (policy, 1, lead, states), (policy, 2, lead, states), (policy, 2, tight, states),
             (bare, 0, lead, states), (bare, 2, lead, states)] + [(bare, 2, lead, remaining) for remaining in shrinking]

    def segment(short, value, brief):
        word = (SHORT_STATES.get(str(value), _as_words(value)) if brief == 2 else
                MEDIUM_STATES.get(str(value), _as_words(value)) if brief == 1 else _as_words(value))
        return short + (' ' + named if short == 'OP' and named else '') + ' ' + word

    def short_words(remaining):
        # The keys of the state values whose short word the line shows.
        return [str(value) for long, short, value in remaining if str(value) in SHORT_STATES and str(value) in STRIP_DEFINITIONS]

    def more(remaining):
        # A form that leaves states out says how many, and the key that shows them in full: nothing is dropped silently.
        left = len(states) - len(remaining)
        return [STRIP_MORE % left] if left else []

    def labelled(name, brief, head, remaining):
        text = ' | '.join(head + [name] + [segment(short, value, brief) for long, short, value in remaining] + more(remaining))
        return text, (['T'] if head is tight else []) + (short_words(remaining) if brief == 2 else [])

    def narrow(remaining):
        # Short labels and the whole short policy id.
        text = ' | '.join(tight + ['P ' + own] + [segment(short, SHORT_STATES.get(str(value), str(value)), 0)
                                                 for long, short, value in remaining] + more(remaining))
        return text, ['T', 'P'] + short_words(remaining)

    def keeps_hazard(remaining):
        return not hazards or any(state in remaining for state in hazards)

    # Words shorten before the last hazard gives way; without a hazard the order is unchanged.
    forms = ([labelled(*tier) for tier in tiers if keeps_hazard(tier[3])]
             + [narrow([state for state in states if state in hazards[:count]]) for count in range(len(hazards), 0, -1)]
             + [labelled(*tier) for tier in tiers if not keeps_hazard(tier[3])] + [narrow([])])
    return _chosen(forms, width)


def _chosen(forms, width):
    """The first (text, keys) that fits the width, with the definitions of the abbreviated forms it shows."""
    text, keys = next((form for form in forms if cell_width(safe_text(form[0])) <= width), forms[-1])
    return text, [STRIP_DEFINITIONS[key] for key in dict.fromkeys(keys)]


def strip_key_rows(definitions, width):
    """The definitions of the abbreviated forms the strip shows, packed into as few rows as fit; a definition wider than
    the row wraps whole and is never cut. [] when the strip shows no abbreviated form."""
    rows = []
    for definition in definitions:
        if rows and cell_width(rows[-1] + ' | ' + definition) <= width:
            rows[-1] += ' | ' + definition
        elif cell_width(definition) <= width:
            rows.append(definition)
        else:
            rows.extend(word_wrap(definition, width))
    return rows


# The primary hazard's ranking, its words and the key that offers its response (a: the action list).
BAND_RANK = ('observation_tenant_mismatch', 'operation_outcome_unknown', 'operation_diverged', 'operation_record_disagrees',
             'operation_unreadable', 'operation_approval_held', 'collection_failed', 'collection_not_finished', 'repository_stale',
             'repository_consumer_mismatch', 'repository_unavailable', 'observation_stale', 'observation_service_changed',
             'observation_policy_changed', 'observation_source_mismatch', 'conditions_not_reread')
# The proposal's own observation checks that diagnostics does not record, shown in the band when they fail.
BAND_ELIGIBILITY = ('tenant_mismatch', 'service_changed', 'policy_changed', 'source_mismatch')
OPERATION_SIGNAL = {'outcome_unknown': 'operation_outcome_unknown', 'diverged': 'operation_diverged',
                    'records disagree': 'operation_record_disagrees', 'unreadable': 'operation_unreadable',
                    'held': 'operation_approval_held'}


def _band_forms(primary, prefixes=None):
    """Longest to shortest wording of one hazard; every form keeps its response, named as the actions list names it.

    The key opens that list (a: actions); it never performs the named action itself. The shortest form of each
    response fits 40 columns, so at the minimum width the hazard and its response share a row.
    """
    code, evidence = primary.get('code'), primary.get('evidence') if isinstance(primary.get('evidence'), dict) else {}
    operation = short_id(evidence.get('operation_id'), prefixes) if evidence.get('operation_id') else ''
    if code == 'operation_outcome_unknown':
        return ['! Operation %s: outcome unknown. Next: Reconcile it (a: actions); it never replays the change' % operation
                if operation else '! Operation outcome unknown. Next: Reconcile it (a: actions); it never replays the change',
                '! Outcome unknown%s. Reconcile, never replays (a: actions)' % (' (op %s)' % operation if operation else ''),
                # 60 columns drops OP from the strip, so this form keeps the operation's id (run 12, frame 35).
                *(['! Op %s unknown. Reconcile, never replays (a: actions)' % operation] if operation else []),
                '! Outcome unknown. Reconcile; it never replays (a: actions)',
                '! Outcome unknown. Reconcile (a actions)']
    if code == 'observation_tenant_mismatch':
        return ['! The configured service is for another tenant than this store. Restart with the right --service-root',
                '! Service is for another tenant. Fix --service-root', '! Other tenant. Fix --service-root']
    if code == 'observation_service_changed':
        # Captured recently can still be out of date: the source has a newer revision than the one captured.
        return ['! Source changed since capture (revision %s, now %s). Next: Collect again (a: actions)'
                % (evidence.get('observed_revision'), evidence.get('service_revision')),
                '! Source changed since capture. Collect again (a: actions)', '! Source changed. Collect (a actions)']
    if code == 'observation_policy_changed':
        return ['! This policy changed at the source since capture. Next: Collect again (a: actions)',
                '! Policy changed at the source. Collect again (a: actions)', '! Policy changed. Collect (a actions)']
    if code == 'observation_source_mismatch':
        return ['! The observation came from another service. Next: Collect again from this one (a: actions)',
                '! Observation from another service. Collect (a: actions)', '! Other source. Collect (a actions)']
    if code == 'conditions_not_reread':
        command = evidence.get('command') or 'the last command'
        return ['! Conditions not re-read after %s. 2: re-read' % command, '! Not re-read after %s. 2: re-read' % command,
                '! Not re-read. 2: re-read']
    if code == 'operation_approval_held':
        # The clock holds the change; waiting or the proposal action are the responses, and a lists that action.
        return ['! Operation %s approval held: the host clock reads earlier than it recorded. Wait, or Prepare a proposal '
                'from the recorded intent (a: actions)' % operation,
                '! Approval held by the clock. Wait, or Prepare a proposal from the recorded intent (a: actions)',
                '! Held: clock behind. Wait (a actions)']
    if code == 'operation_unreadable':
        # No reconcile is offered for records that cannot be read; diagnostics say which and why.
        return ['! Operation %s records unreadable. i: details' % operation, '! Op records unreadable. i: details']
    if code in ('operation_diverged', 'operation_record_disagrees'):
        words, shortest = {'operation_diverged': ('diverged from its plan', '! Op diverged. Reconcile (a actions)'),
                           'operation_record_disagrees': ('records disagree', '! Records differ. Reconcile (a actions)')}[code]
        return ['! Operation %s %s. Next: Reconcile it again (a: actions); i: details' % (operation, words),
                '! Operation %s. Reconcile again (a: actions)' % words, shortest]
    if code == 'collection_failed':
        status = str(evidence.get('status') or 'failed')
        return ['! Last collection %s; the kept observation is stale. Next: Collect again (a: actions)' % status,
                '! Last collection %s. Collect again (a: actions)' % status, '! Collection %s. Collect (a actions)' % status]
    if code == 'collection_not_finished':
        return ['! A collection started and recorded no end. Next: Collect again (a: actions)',
                '! No collection end. Collect (a actions)']
    if code in ('repository_stale', 'repository_consumer_mismatch'):
        words, short = (('changed since its intent', 'changed') if code == 'repository_stale' else
                        ('no longer consumes this policy', 'consumer changed'))
        return ['! Repository %s. 9: difference. Next: Refresh the repository intent (a: actions)' % words,
                '! Repository %s. Refresh the intent (a: actions)' % short, ('! Repo changed. Refresh (a actions)' if code == 'repository_stale' else '! Consumer changed. Refresh (a actions)')]
    if code == 'repository_unavailable':
        return ['! Repository intent cannot be read. 9: repository, i: details', '! Repository unreadable. 9: repository']
    hold = clock_hold(evidence.get('freshness_reasons'))
    if hold == 'clock_moved_backward':
        # The age cannot be established and collecting again does not clear it, so the band names no collection and
        # it outranks a stamp ahead and the generic stale line.
        return ['! Observation age unknown: host clock behind a recorded time. Correct the clock, then restart (i: details)',
                '! Age unknown: clock behind. Correct it, restart (i)', '! Clock behind. i: details']
    if hold == 'clock_floor_invalid':
        return ['! Observation age unknown: the recorded time cannot be read. Changes stay held until it can (i: details)',
                '! Age unknown: recorded time unreadable. Held until readable (i)', '! Time record unreadable. i: details']
    if 'stamped_after_now' in (evidence.get('freshness_reasons') or []) and evidence.get('collect_cures'):
        # The read model judged that a new collection from this session's service becomes current.
        # The State row says why (the stamp and both times); the band says what that means for the age.
        return ['! Observation age unknown. Next: Collect again (a: actions)',
                '! Age unknown. Collect again (a: actions)', '! Age unknown. Collect (a actions)']
    if 'stamped_after_now' in (evidence.get('freshness_reasons') or []):
        # Not cured by collecting now from this session's service (an imported capture keeps its capture time).
        return ["! Observation stamped after this host's clock; stale until the clock passes it. i: details",
                '! Observation stamped ahead of the clock. i: details', '! Stamped ahead of clock. i: details']
    return ['! Observation stale. Next: Collect again (a: actions)', '! Observation stale. Collect (a actions)']


def _record_before_collect(form):
    """A band form whose response is a collection, with the deployment record named first: one first action on every
    surface, the one the actions list and Delivery's Next also name."""
    return re.sub(r'(Next: )?Collect( again)?(?![a-z])', lambda found: (found.group(1) or '') + 'Record the deployment, then collect'
                  + (found.group(2) or ''), form)


def hazard_band(facts, signals, width):
    """The band's first row: the primary hazard and the key for its response, or None when nothing is recorded."""
    rows = hazard_rows(facts, signals, width)
    return rows[0] if rows else None


# Words a hazard's band keeps while any form that has them fits a row by itself: what makes its response safe.
BAND_ESSENTIAL = {'operation_outcome_unknown': 'never replays'}


# Key routes in the band's wording; dropped where no surface or key can take them (below the minimum, while typing).
BAND_ROUTES = ((' (a: actions)', ''), (' (a actions)', ''), (' (i: details)', ''), (' (i)', ''),
               (' 9: difference.', ''), ('; i: details', ''),
               ('. i: details', '.'), (' i: details', ''))


def _without_routes(text):
    for route, replacement in BAND_ROUTES:
        text = text.replace(route, replacement)
    return text


# The action the band's response names, by the primary hazard: the list's entry the band points at while the list is open.
BAND_ACTION_KIND = {'operation_outcome_unknown': 'reconcile', 'operation_diverged': 'reconcile',
                    'operation_record_disagrees': 'reconcile', 'collection_failed': 'collect',
                    'collection_not_finished': 'collect', 'repository_stale': 'repository-refresh',
                    'repository_consumer_mismatch': 'repository-refresh', 'observation_stale': 'collect',
                    'observation_service_changed': 'collect', 'observation_policy_changed': 'collect',
                    'observation_source_mismatch': 'collect', 'operation_approval_held': 'propose-from-intent'}


def _band_entry(primary, facts, kind):
    """The 1-based place in the actions list of the action the band's response names, or None when the list has none."""
    actions = [action for action in facts.get('actions') or [] if isinstance(action, dict)]
    evidence = primary.get('evidence') if isinstance(primary.get('evidence'), dict) else {}
    kind = kind or BAND_ACTION_KIND.get(primary.get('code'))
    places = [index for index, action in enumerate(actions, 1) if action.get('kind') == kind]
    exact = [index for index in places if evidence.get('operation_id')
             and (actions[index - 1].get('binding') or {}).get('operation_id') == evidence['operation_id']]
    return (exact or places or [None])[0]


def _in_list(form, entry):
    """A band form while the actions list is open: `a` is not a key there, so the response points at its entry."""
    for route in (' (a: actions)', ' (a actions)'):
        form = form.replace(route, ' (entry %d)' % entry if entry else '')
    return form


def hazard_rows(facts, signals, width, *, routes=True, here=False, listed=False, repository_here=False, surface=True):
    """The band: the primary hazard with its response, in the longest wording that fits, and the count of other
    findings and any re-read that failed, beside it or on a row of their own so neither is cut. A window too narrow
    for the shortest wording gets it wrapped with the response kept whole. [] when nothing is recorded.

    listed: the actions list is open, where a is not a key; the response names its entry in the list instead.
    repository_here: surface 9 is drawn, which is where the band's 9 would point, so the band does not point at it.
    surface: the count names the surface that lists the other findings; False only below the minimum window, where no
    surface can be shown (the constrained frame)."""
    primary, others = _band_primary(facts, signals)
    if primary is None:
        return []
    # routes=False where no key can be taken (below the minimum, or while a command is typed): the band names the
    # response without its key.
    reread = (['not re-read after %s: 2 re-reads' % facts['unverified']]
              if facts.get('unverified') and primary.get('code') != 'conditions_not_reread' else [])
    # One fact reads in one form on every surface and in every mode (run 12, frames 34, 37, 54, 55): "+N more findings
    # (2 Inspector)" names the surface by its number, the one the tab line above shows and Help explains. It is a name,
    # not a key press, so it stands while a command is typed and on the Inspector itself, which lists them under NEEDS
    # ATTENTION. (here is kept for callers; the wording no longer differs by it.)
    more = '+%d more %s' % (others, 'finding' if others == 1 else 'findings')
    counts = [[more + (' (2 Inspector)' if surface else '')]] if others else [[]]
    forms = _band_forms(primary, facts.get('identity_prefixes'))
    if repository_here:
        forms = [re.sub(r'\. 9: repository(?:, |$)', lambda found: '. ' if found.group(0).endswith(' ') else '.',
                        form.replace(' 9: difference.', '')) for form in forms]
    named = None
    if any(isinstance(action, dict) and action.get('kind') == 'deployment-record' and action.get('available')
           for action in facts.get('actions') or []):
        # The actions list puts the record first, so the band names the order: record the deployment, then collect.
        recorded = [_record_before_collect(form) for form in forms]
        named = 'deployment-record' if recorded != forms else None
        forms = recorded
    if listed and routes:
        entry = _band_entry(primary, facts, named)
        forms = [_in_list(form, entry) for form in forms]
    if not routes:
        forms = [_without_routes(form) for form in forms]
        reread = [_without_routes(note).replace(': 2 re-reads', '') for note in reread]
    # The essential words outrank keeping the count on the band's row: while a form that keeps them fits a row by
    # itself, the count moves to a row of its own. Only when none fits does a shorter form drop them.
    essential = BAND_ESSENTIAL.get(primary.get('code'))
    whole = [form for form in forms if essential in form] if essential else []
    for candidates in ([whole] if whole else []) + [forms]:
        keep = next((form for form in candidates if cell_width(form) <= width), None) if candidates is whole else None
        if keep is not None:
            # One fact reads in one form on every surface: the longest form that keeps the essential words and fits a
            # row alone, never a shorter one chosen to make room for a longer count. The count joins its row in the
            # longest wording that fits there, else it takes a row of its own, written out in full.
            for count in counts:
                notes = count + reread
                suffix = '  ' + ' | '.join(notes) if notes else ''
                if cell_width(keep + suffix) <= width:
                    return [keep + suffix]
            return [keep] + _pack(counts[0] + reread, width)
        for count in counts:
            notes = count + reread
            suffix = '  ' + ' | '.join(notes) if notes else ''
            for form in candidates:
                if cell_width(form + suffix) <= width:
                    return [form + suffix]
    notes = counts[-1] + reread
    rows = next(([form] for form in forms if cell_width(form) <= width), None)
    if rows is None:
        if '. ' in forms[-1]:
            condition, response = forms[-1].rsplit('. ', 1)
            rows = word_wrap(condition + '.', width) + word_wrap(response, width)
        else:
            rows = word_wrap(forms[-1], width)
    return rows + _pack(notes, width)


def _pack(items, width):
    """Items joined by ' | ' into as few lines as fit the width; an item wider than the width is cut."""
    lines = []
    for item in items:
        if lines and cell_width(lines[-1] + ' | ' + item) <= width:
            lines[-1] += ' | ' + item
        else:
            lines.append(item if cell_width(item) <= width else fit(item, width))
    return lines


def constrained_rows(tenant, selected, facts, mode_class, width, height, need, prompt, typing=False, layer='summary'):
    """The window below the minimum size: (lines, band_rows), never the body.

    When rows run out they are kept in this order: the primary hazard with its response, the evidence mode with the
    constraint, the prompt, the tenant and policy with their hazard states, the keys. They are shown top to bottom as
    mode, identities, hazard, prompt, keys.
    """
    mode = mode_word(mode_class)
    header = next((text for text in ('%s | window below %s: enlarge it' % (mode, need), '%s; window below %s' % (mode, need),
                                     '%s; below %s' % (mode, need), 'Below %s' % need) if cell_width(text) <= width),
                  fit('Below %s' % need, width))
    if layer == 'catalog':
        # The catalog is a layer of the Help surface; it says what it needs rather than a generic size line.
        header = next((text for text in ('Catalog needs a larger window (%s)' % need, 'Catalog needs a larger window',
                                         'Catalog: larger window') if cell_width(text) <= width), fit('Catalog: larger window', width))
    if layer == 'workflow':
        # The workflow map is a layer over the Inspector; below the frame minimum it says what it needs, the same way.
        header = next((text for text in ('Workflow map needs a larger window (%s)' % need, 'Workflow map needs a larger window',
                                         'Workflow map: larger window') if cell_width(text) <= width),
                      fit('Workflow map: larger window', width))
    states = [('OBSERVED', 'OBS', observed_state(facts, None)), ('REPOSITORY', 'REPO', facts.get('repository')),
              ('OPERATION', 'OP', facts.get('operation'))]
    items = ['T ' + short_id(tenant), 'P ' + short_id(selected, facts.get('identity_prefixes')) if selected else 'no policy'] + [
        short + ' ' + SHORT_STATES.get(str(value), str(value)) for label, short, value in states
        if selected and str(value) in HAZARD_STATES[label]]
    # Only keys that work here: while a command is typed q is part of it, so Enter and Esc are the keys.
    forms = (('Enter submits; Esc discards', 'Esc discards') if typing else ('q exits; enlarge for the surfaces', 'q exits'))
    if layer == 'workflow' and not typing:
        forms = ('Esc closes the map; q exits', 'Esc closes; q exits', 'q exits')
    keys = next((text for text in forms if cell_width(text) <= width), '')
    # The abbreviated forms the strip shows are defined in the rows the window has left, after the keys.
    shown = ['T'] + (['P'] if selected else []) + [str(value) for label, short, value in states
                                                   if selected and str(value) in HAZARD_STATES[label]
                                                   and str(value) in SHORT_STATES and str(value) in STRIP_DEFINITIONS]
    groups = {'header': [header], 'strip': _pack(items, width), 'prompt': [prompt], 'keys': [keys] if keys else [],
              'band': hazard_rows(facts, facts.get('signals') or [], width, routes=False, surface=False) if selected else [],
              'legend': strip_key_rows([STRIP_DEFINITIONS[key] for key in dict.fromkeys(shown)], width)}
    if layer == 'workflow':
        # The one sentence, whole: what the map needs and the plain-text command that prints it anywhere.
        groups['header'] = workflow_unavailable_lines(width)
    budget, kept = height, {}
    for name in ('band', 'header', 'prompt', 'strip', 'keys', 'legend'):
        kept[name] = groups[name][:max(0, budget)]
        budget -= len(kept[name])
    lines, band_rows = [], []
    for name in ('header', 'strip', 'band', 'prompt', 'keys', 'legend'):
        for line in kept[name]:
            if name == 'band':
                band_rows.append(len(lines))
            lines.append(line)
    return lines, band_rows


def _band_rank(item):
    """A finding's place in the band's order. A clock hold on the observation blocks every proposal and nothing in
    the workbench clears it, so it leads a repository change; the other findings keep BAND_RANK."""
    code = item['code']
    evidence = item.get('evidence') if isinstance(item.get('evidence'), dict) else {}
    if code == 'observation_stale' and clock_hold(evidence.get('freshness_reasons')):
        return BAND_RANK.index('repository_stale') - 0.5
    return BAND_RANK.index(code)


def _band_primary(facts, signals):
    """The primary hazard and the number of other findings, or (None, 0).

    The operation's live status (from this session's results) wins over an older recorded signal: a reconciled
    operation is no longer a hazard, and one known only from this session still is. Other recorded signals are
    counted, with the key that lists them all.
    """
    # A recorded condition is retired only by a newer read (the workspace reads again after any command that may
    # write), never by a status from a result, which can describe the journal and not the condition.
    operation, operation_id = facts.get('operation'), facts.get('operation_id')
    live = [item for item in signals or [] if isinstance(item, dict)]

    def about(item):
        evidence = item.get('evidence') if isinstance(item.get('evidence'), dict) else {}
        return evidence.get('operation_id')
    eligibility = facts.get('eligibility') if isinstance(facts.get('eligibility'), dict) else {}
    if eligibility.get('reason') in BAND_ELIGIBILITY:
        live.append({'area': 'eligibility', 'code': 'observation_' + eligibility['reason'], 'evidence': dict(eligibility)})
    if operation in OPERATION_SIGNAL and not any(item.get('code') == OPERATION_SIGNAL[operation]
                                                 and (not operation_id or about(item) in (None, operation_id)) for item in live):
        # Known from this session's own result before diagnostics recorded it.
        live.append({'area': 'operations', 'code': OPERATION_SIGNAL[operation],
                     'evidence': {'operation_id': operation_id} if operation_id else {}})
    if facts.get('unverified') and not live:
        live.append({'area': 'workspace', 'code': 'conditions_not_reread', 'evidence': {'command': facts['unverified']}})
    unique = {}
    for item in live:
        unique.setdefault((item.get('code'), about(item)), item)
    live = list(unique.values())
    ranked = sorted((item for item in live if item.get('code') in BAND_RANK), key=_band_rank)
    primary = ranked[0] if ranked else None
    if primary is None:
        return None, 0
    # Every other finding is counted, the same kind for another operation included.
    return primary, len([item for item in live if item is not primary])


from .io import readable_time  # noqa: E402  (shared with the engine's sentences)


# Freshness reasons the store records, in plain words.
FRESHNESS_REASON_WORDS = {'later_collection_not_complete': 'a later collection did not complete',
                          'older_than_window': 'older than the freshness window',
                          'stamped_after_now': "stamped after this host's clock", **CLOCK_HOLD_WORDS}
# The proposal's own observation check, as part of the observation's state.
ELIGIBILITY_STATE_WORDS = {
    'service_changed': 'the source has changed since capture (revision %(observed_revision)s, now %(service_revision)s)',
    'policy_changed': 'this policy has changed at the source since capture',
    'source_mismatch': 'it came from another service than the one configured',
    'tenant_mismatch': 'the configured service is for another tenant'}
INTENT_STATE_WORDS = {'current': 'current with the repository', 'changed': 'the repository changed since',
                      'consumer_changed': 'the component no longer consumes this policy',
                      'unreadable': 'the repository cannot be read now', 'not_checked': 'not checked'}


def strip_operation_shown(facts):
    """The operation the context strip reports when it is not the newest for the policy (its id and the strip's word for
    its state), else None: the same condition on which the strip names the operation itself."""
    shown = facts.get('operation_id') if facts.get('operation') else None
    newest = _newest_operation_id(facts)
    if shown and newest and shown != newest:
        return {'operation_id': shown, 'state': facts['operation']}
    return None


def state_lines(states, width, heading='STATE', prefixes=None, reviewing=None, strip_operation=None, sources_below=False):
    """Observation, repository intent and the newest operation, each its own line, from the read model's states.

    reviewing: the operation a surface shows below (the Plan review); when it is not the newest, the line says so.
    strip_operation: the operation the strip reports when it is not the newest (strip_operation_shown); the row says so.
    sources_below: the surface lists the changed files itself (Repository status), so the row does not list them again.
    """
    observation = states.get('observation') if isinstance(states.get('observation'), dict) else {}
    source = [evidence_words(observation.get('evidence_class'))]
    if observation.get('run_id') is not None:
        source.append('run %s' % observation['run_id'])
    source.append(readable_time(observation.get('observed_at')) or 'time not recorded')
    parts = [', '.join(source)]
    if observation.get('coverage'):
        parts.append(coverage_words(observation['coverage']))
    freshness = observation.get('freshness')
    hold = clock_hold(observation.get('freshness_reasons')) if freshness != 'fresh' else None
    # A held age is not known, so the line does not say stale; the cause is the clock's own words, said once.
    # A stamp ahead of this host's clock leaves the age just as unknown. The row's first part already prints the stamp,
    # so the reason adds only the clock's reading: the stamp time is on screen once.
    ahead = freshness != 'fresh' and not hold and 'stamped_after_now' in (observation.get('freshness_reasons') or [])
    read = readable_time(observation.get('freshness_checked_at'))
    ahead_words = "stamped after this host's clock" + (": this host's clock read %s" % read if read else '')
    reasons = ([CLOCK_HOLD_CAUSES[hold]] if hold else []) + [
        ahead_words if ahead and reason == 'stamped_after_now' else FRESHNESS_REASON_WORDS.get(reason, reason)
        for reason in observation.get('freshness_reasons') or []
        if reason not in (CLOCK_HOLD_REASONS if hold else ())]
    eligibility = observation.get('eligibility') if isinstance(observation.get('eligibility'), dict) else {}
    # Recency is not currentness: an observation captured recently is out of date once the source moved on.
    moved = eligibility.get('reason') in ('service_changed', 'policy_changed')
    parts.append(('captured recently (fresh by age)' if freshness == 'fresh' and moved else 'fresh by age'
                  if freshness == 'fresh' else 'age not known' if hold or ahead else str(freshness or 'freshness not recorded'))
                 + (' (%s)' % '; '.join(reasons) if reasons and freshness != 'fresh' else ''))
    if eligibility.get('reason') in ELIGIBILITY_STATE_WORDS:
        parts.append(ELIGIBILITY_STATE_WORDS[eligibility['reason']] % eligibility)
    lines = [''] + word_wrap(heading, width) + _labelled('  Observation', '; '.join(parts), width, 15)
    intent = states.get('intent') if isinstance(states.get('intent'), dict) else {}
    if intent.get('status') in (None, 'none'):
        text = 'none recorded; repository-entry REPOSITORY finds where this policy is maintained'
    else:
        scope = intent.get('scope') if isinstance(intent.get('scope'), dict) else {}
        revision = intent.get('source_revision')
        verified = ('content verified' if intent.get('revision_content_verified') else
                    'asserted, not verified against the files')
        reason = intent.get('reason')
        if reason and sources_below and ': ' in reason:
            # The surface lists the files under SOURCES; this row says only that the repository changed.
            reason = reason.split(': ', 1)[0] + ' (the files are under SOURCES below)'
        text = '%s from %s / %s at %s (%s); %s' % (
            short_id(intent.get('artifact_id'), prefixes), scope.get('stack'), scope.get('component'),
            short_id(revision) if revision else 'no revision', verified,
            _clause(reason) if reason else INTENT_STATE_WORDS.get(intent.get('status'), str(intent.get('status'))))
    lines += _labelled('  Intent', text, width, 15)
    operation = states.get('operation') if isinstance(states.get('operation'), dict) else None
    if operation is None:
        text = 'none recorded for this policy'
    else:
        journal, recorded = operation.get('journal_status'), operation.get('status')
        # Status words read as words; the exact values stay in the typed details and the raw record.
        text = '%s %s' % (short_id(operation.get('operation_id'), prefixes),
                          _as_words(journal or recorded or 'status not recorded'))
        if journal and recorded and journal != recorded:
            text += ' (the store records %s)' % _as_words(recorded)
        if operation.get('classification'):
            text += '; %s %s' % ("reconcile's readback:" if journal == 'reconciled' else 'readback',
                                 _as_words(operation['classification']))
        if operation.get('approval_window') in WINDOW_STATE_WORDS:
            text += '; ' + WINDOW_STATE_WORDS[operation['approval_window']]
        if operation.get('recorded_at'):
            # The store's own registration time: the journal can disagree with the store (review 35).
            text += '; store last registered %s' % readable_time(operation['recorded_at'])
        if reviewing and operation.get('operation_id') != reviewing:
            text = 'newest for this policy: %s. The plan below is a different operation, %s.' % (
                text, short_id(reviewing, prefixes))
        elif (strip_operation and not reviewing
                and strip_operation.get('operation_id') != operation.get('operation_id')):
            # The strip reports another operation than the newest; this row says which one it shows.
            text += '. The strip shows operation %s (%s), not the newest.' % (
                short_id(strip_operation['operation_id'], prefixes), strip_operation.get('state'))
    lines += _labelled('  Operation', text, width, 15)
    return lines


# A prepared operation's approval window, as the state line says it (the states of maintenance.approval_window).
WINDOW_STATE_WORDS = {'open': 'approval window open', 'closed': 'approval window closed',
                      'closed_recorded': 'approval window closed (recorded)',
                      'clock_moved_backward': "approval held: this host's clock reads earlier than a time it recorded",
                      'unknown': 'approval window cannot be judged'}


def _as_words(value):
    return str(value).replace('_', ' ')


def _words_with_code(value):
    """A code in words with the code itself in parentheses after it, as a lookup key; a code that is already plain
    words stands as it is."""
    words = _as_words(value)
    return words if words == str(value) else '%s (%s)' % (words, value)


def _path_words(value):
    """A path as a screen shows it: shell-quoted when it holds a space or another character a shell would split on,
    so it reads and copies as one path; a plain path is shown as it is."""
    import shlex
    return shlex.quote(safe_text(str(value)))


def _clause(text):
    """A recorded sentence as a clause after a semicolon: first letter lower case, no closing full stop."""
    text = str(text).strip().rstrip('.')
    return text[:1].lower() + text[1:]


def utc_time(value):
    """An epoch number as an ISO 8601 UTC time; anything else unchanged."""
    from datetime import datetime, timezone
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return value
    try:
        return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
    except (OverflowError, OSError, ValueError):
        return value


# A change's path through the existing surfaces (P-PRES-15): numbers unchanged, where you are, what comes next.
# Delivery has no surface number of its own: v opens it, and the line says so where it names the key.
LIFECYCLE = ((8, '9 Repository'), (4, '5 Plan'), (5, '6 Execution'), (None, 'Delivery (v opens it)'))
# The band and a screen name one first action. Where a deployment record is available and the band's response is a
# collection, both say record the deployment, then collect (PKG-PRES-RUN10 item 5): the order the change moves in, since
# Delivery's stage 8 waits for a collection after the change. It is advice, not a rule the product enforces:
# deployment-record reads the operation, its readback and the cited intent, never the observation, so nothing refuses
# collecting first (run 8, frames 19 to 21).
# Reconcile's step, worded as the band words it; one sentence whose parentheses close where the key is named.
RECONCILE_NEXT = 'Reconcile it (a: actions); it never replays the change. v shows every delivery stage'


def newest_open_operation(facts, reviewing, prefixes=None):
    """The short id of the newest operation for the policy when its approval window is open and it is not the plan under
    review, else None (the read model's state row says the same: `approval window open`)."""
    states = facts.get('states') if isinstance(facts, dict) and isinstance(facts.get('states'), dict) else {}
    newest = states.get('operation') if isinstance(states.get('operation'), dict) else {}
    identity = newest.get('operation_id')
    if newest.get('approval_window') == 'open' and isinstance(identity, str) and identity != reviewing:
        return short_id(identity, prefixes)
    return None


def lifecycle_next(tab, value, now, eligibility=None, newest_open=None):
    """The next step for the change shown, from its own recorded state; never a step that state refuses.

    newest_open: the newest operation for the policy when it is another one and its approval window is open (a closed
    plan's step then names it; run 12, frame 70)."""
    value = value if isinstance(value, dict) else {}
    if tab == 8:
        freshness = value.get('freshness') if isinstance(value.get('freshness'), dict) else {}
        if freshness.get('status') == 'current' and isinstance(eligibility, dict) and eligibility.get('code'):
            return 'a proposal is blocked now (%s); 2 Inspector says why and what to do' % eligibility['code']
        if freshness.get('status') == 'current':
            return 'Prepare a proposal from the recorded intent (a: actions); 5 Plan reviews it'
        return 'Refresh the repository intent first (a: actions); a proposal follows from the new intent'
    if tab == 5:
        if value.get('status') == 'outcome_unknown':
            return RECONCILE_NEXT
        result = value.get('result') if isinstance(value.get('result'), dict) else value
        if 'reconciled' in (result.get('journal_status'), result.get('status')):
            # A reconcile follows an unknown outcome, so the operation has no verified readback of its own and cannot
            # become a deployment record (Delivery's Deployment stage says so); the line promises none.
            return 'v shows every delivery stage'
        return 'v shows every delivery stage, including the deployment record'
    status = value.get('status')
    repository = value.get('repository') if isinstance(value.get('repository'), dict) else {}
    if status == 'prepared':
        if repository.get('context_changed'):
            # The Context file row and the digest line say why; this line is the step.
            return 'Prepare a proposal from the recorded intent (a: actions)'
        if repository.get('cited') and repository.get('freshness') not in (None, 'current'):
            return ('the repository changed since its intent, so execute refuses it; Refresh the repository intent (a: actions), '
                    'then Prepare a proposal from the recorded intent')
        judged = value.get('approval_window') if isinstance(value.get('approval_window'), dict) else {}
        if judged.get('state') == 'clock_moved_backward':
            return ("this host's clock reads earlier than this operation's recorded time, so execute holds it; "
                    'correct the clock and restart, or wait, or Prepare a proposal from the recorded intent (a: actions)')
        if judged.get('state') == 'unknown':
            return ("this operation's recorded time cannot be read, so execute refuses it; "
                    'Prepare a proposal from the recorded intent (a: actions)')
        expires = value.get('expires_at')
        if judged.get('state') in ('closed', 'closed_recorded') or (
                not judged and isinstance(expires, (int, float)) and not isinstance(expires, bool) and expires <= now):
            # The Next sits above the Expiry and Approval window rows (run 16, frames 70 and 72), so it gives the reason
            # itself and never points at them by position.
            closed_at = _readable_epoch(expires) if isinstance(expires, (int, float)) and not isinstance(expires, bool) else None
            reason = ('its approval window closed at %s' % closed_at) if isinstance(closed_at, str) \
                else 'its approval window is closed'
            if newest_open:
                return ('Prepare a proposal from the recorded intent (a: actions), or review the newest operation, %s, '
                        'whose approval window was open at the last read of this policy; this plan cannot run because %s'
                        % (newest_open, reason))
            return 'Prepare a proposal from the recorded intent (a: actions); this plan cannot run because %s' % reason
        # The command stands on its own row after the sentence, so a copied row carries no words (run 9, frame 18).
        # The real directory when the review names it (a review always does); the template only where it does not.
        operation = command_arg(value['operation_root']) if isinstance(value.get('operation_root'), str) else 'OPERATION_DIR'
        if value.get('no_configuration_change') is True or value.get('changes') == []:
            # As maintenance.execute does it: a plan with no change still needs the digest and is run, but nothing is sent
            # to the service (service_no_change, mutation_dispatched False); the readback confirms the desired state.
            return ('Nothing to apply: the desired body equals the observed body. execute with the review digest sends no '
                    'change to the service; it runs the operation and reads the service back (6 Execution shows the '
                    'result). ' + _execute_forms(operation))
        return 'approve and run it with the review digest (6 Execution shows the result). ' + _execute_forms(operation)
    if status == 'outcome_unknown':
        return RECONCILE_NEXT
    return 'v shows every delivery stage of this operation'


def _execute_forms(operation):
    """Where the plan review's execute is typed, as Delivery frames its commands: the workspace's command bar, or a
    shell with the complete program form. DIGEST stays a placeholder: the engineer copies the digest from the review
    they approve, and it is never filled in (run 12, frames 18, 31, 53, 63, 64)."""
    return ('In the workspace:' + COMMAND_BREAK + '  execute %s DIGEST' % operation + COMMAND_BREAK + 'From a shell:'
            + COMMAND_BREAK + '  intune-iac workbench execute --operation %s --approve-digest DIGEST' % operation
            + COMMAND_BREAK + 'The shell form takes no --root: the operation directory names its store.')


def lifecycle_lines(tab, width, value=None, now=None, eligibility=None, band_names_refresh=False, band_has_next=False,
                    newest_open=None):
    """Where this surface sits in a change's path and the next step for the state shown, in one line.

    band_names_refresh: the hazard band above already names Refresh as the next step for a changed repository, so this
    line says what follows from it and does not name the same action a second time (run 9, frames 11 to 16, 75, 77).
    band_has_next: the band carries the screen's Next, so an execution result adds no second one (a plan review keeps
    its step, which prints the command to run; run 11, frames 19, 38, 54).
    """
    if tab not in (8, 4, 5):
        return []
    import time
    path = ' > '.join(name + (' (here)' if index == tab else '') for index, name in LIFECYCLE)
    freshness = (value or {}).get('freshness') if isinstance((value or {}).get('freshness'), dict) else {}
    if tab == 8 and band_names_refresh and freshness.get('status') != 'current':
        return word_wrap('Lifecycle: %s. A proposal follows from the new intent.' % path, width)
    step = lifecycle_next(tab, value, time.time() if now is None else now, eligibility, newest_open)
    # A step that prints a command ends with it: the sentence comes first and no full stop follows the command.
    head, _, command = step.partition(COMMAND_BREAK)
    if band_has_next and tab == 5:
        return word_wrap('Lifecycle: %s.' % path, width)
    lines = word_wrap('Lifecycle: %s. Next: %s%s' % (path, head, '' if command else '.'), width)
    return lines + (step_rows(command, width) if command else [])


def _when(value, missing='time not recorded'):
    """A recorded time for a summary, to the second with its zone; the exact value stays in the evidence layers."""
    if value is None or value == '':
        return missing
    return readable_time(value) if isinstance(value, str) else str(value)


def _readable_epoch(value):
    """An epoch number as a readable UTC time to the second; anything else unchanged."""
    converted = utc_time(value)
    return readable_time(converted) if isinstance(converted, str) else converted


def _quote_units(words, width):
    """The words of a line, a single-quoted argument that holds spaces kept whole when the line can hold it (a
    shell-quoted path in a command shown for copying). An apostrophe inside a word is not a quote, and a quote
    that never closes nearby, or is wider than the line, stays words."""
    import re
    units, index = [], 0
    while index < len(words):
        start = words[index].lstrip('(')
        closed = lambda word: len(word) > 1 and re.search(r"'[).,;:]*$", word) is not None
        if start.startswith("'") and not closed(start):
            end = next((at for at in range(index + 1, min(len(words), index + 12)) if closed(words[at])), None)
            # A quoted path with spaces stays one unit even where it cannot fit: it is then split at a "/", never at
            # one of its spaces (word_wrap), so no row ends or starts inside the path on a space.
            if end is not None and (cell_width(' '.join(words[index:end + 1])) <= width or start.startswith("'/")):
                units.append(' '.join(words[index:end + 1]))
                index = end + 1
                continue
        units.append(words[index])
        index += 1
    return units


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
    import re
    words = []
    for token in body.split(' '):
        # A date, its time and its zone stay together: a row never begins with a lone "UTC" or a time without its date.
        if words and re.fullmatch(r'UTC[).,;:]*', token) and re.search(r'\d\d:\d\d:\d\d$', words[-1]):
            words[-1] += ' ' + token
        elif words and re.fullmatch(r'\d\d:\d\d:\d\d', token) and re.search(r'\d{4}-\d\d-\d\d$', words[-1]):
            words[-1] += ' ' + token
        else:
            words.append(token)
    for word in _quote_units(words, width):
        candidate = word if not line else line + ' ' + word
        if cell_width(candidate) <= width:
            line = candidate
            continue
        if (line and cell_width(word) > width and width - cell_width(line) - 1 >= 4
                and not any(mark in word for mark in ('/', '.', '["'))):
            # The word must be split anyway: start it after the current text rather than leave that text alone. A word
            # with delimiters starts its own row instead, so it can break at one of them (below).
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
            keep = max(cut.rfind('/') + 1, cut.rfind('.') + 1, cut.rfind('["') + 2 if '["' in cut else 0)
            if len(cut) < len(word) and keep * 2 >= len(cut) > 0:
                # Cut after a delimiter (a path's "/", an address's `.` or `["`) rather than inside an identifier or a
                # word, when that leaves at least half a row; a quoted path breaks here, never at a space inside it.
                cut = cut[:keep]
            lines.append(cut or word[:1]); word = word[len(cut or word[:1]):]
        line = word
    lines.append(line)
    return lines


def _value(value):
    return safe_text(json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True))


UNRESOLVED_GROUP = 'Unresolved group identity'


def group_words(group_id, names=None):
    """A group target in words: its captured name beside its identity, or what it is when no name was captured."""
    names = names if isinstance(names, dict) else {}
    identity = safe_text(str(group_id))
    if group_id in names:
        return '%s "%s"' % (identity, safe_text(str(names[group_id])))
    return '%s %s' % (UNRESOLVED_GROUP, identity)


def _target(item):
    if isinstance(item, dict) and isinstance(item.get('type'), str):
        text = item['type']
        if 'group_id' in item:
            text += ' ' + group_words(item['group_id'])
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


def review_lines(value, width):
    """A maintenance review: the form written, the current annotation, none recorded, or its history."""
    finding = _as_words(value.get('finding', 'finding'))
    if value.get('status') == 'review_form_written':
        lines = word_wrap('[REVIEW FORM WRITTEN] %s' % _path_words(value.get('path')), width)
        lines += word_wrap('For %s of policy %s. Fill in the rationale (required), the owner, the review due and '
                           'exception expiry times (with their zone, or null; the expiry not before the review date) and '
                           'any linked operation IDs.' % (finding, value.get('object_id')), width)
        prior = value.get('expected_prior') or 'none'
        lines += word_wrap('Then record the form you filled in. A review is an annotation, never approval or execution. '
                           'The last word of the command is the earlier review it replaces' + (
                               '; none means this finding has no earlier review to replace.' if prior == 'none' else '.')
                           + ' In the workspace:', width)
        lines += word_wrap("  queue-amend '%s' %s" % (value.get('path'), prior), width)
        return lines
    if value.get('schema_version') == 'workbench-queue-history/1':
        rows = [row for row in value.get('amendments') or [] if isinstance(row, dict)]
        lines = word_wrap('[REVIEW HISTORY] %s: %s, oldest first; every version is kept' % (
            finding, _plural(len(rows), 'version')), width)
        for row in rows:
            data = row.get('data') if isinstance(row.get('data'), dict) else {}
            lines += word_wrap('  version %s recorded %s | owner %s | %s' % (
                data.get('version'), _when(row.get('recorded_at')), data.get('owner') or 'none recorded',
                data.get('rationale') or 'no rationale'), width)
        return lines
    if value.get('status') != 'recorded':
        return (word_wrap('[REVIEW] No review recorded for %s of this policy. Write the form to fill with:' % finding, width)
                + word_wrap('  :queue-review-template %s NEW_JSON' % value.get('finding'), width))
    def flag(when, state, yes, no):
        return 'none' if when is None else '%s (%s)' % (_when(when), yes if state else no if state is False else 'unknown')
    lines = word_wrap('[REVIEW] %s, version %s, recorded %s' % (finding, value.get('version'), _when(value.get('recorded_at'))), width)
    lines += word_wrap('Owner: %s' % ('%s (an unverified annotation)' % value['owner'] if value.get('owner') else 'none recorded'), width)
    lines += word_wrap('Review due: ' + flag(value.get('review_due'), value.get('review_overdue'), 'overdue', 'not overdue'), width)
    lines += word_wrap('Exception expiry: ' + flag(value.get('exception_expiry'), value.get('exception_expired'), 'expired',
                                                   'not expired'), width)
    lines += word_wrap('Rationale: %s' % (value.get('rationale') or 'none'), width)
    linked = [str(item) for item in value.get('linked_proposals') or []]
    lines += word_wrap('Linked operations: %s' % (', '.join(item[:12] for item in linked) or 'none'), width)
    for text in value.get('limitations') or []:
        lines += word_wrap('Limitation: ' + str(text), width)
    return lines


def filter_lines(choices, focus, current, width):
    """The estate filters by dimension, the focus marked >, the filter in use marked *."""
    lines = word_wrap('FILTERS  Up and Down choose; Enter applies one as a read-only query of the estate, keeping the '
                      'others; Esc closes. * marks the filter in use.', width)
    previous = None
    for index, (dimension, value) in enumerate(choices):
        if dimension != previous:
            lines += ['', dimension.upper()]
            previous = dimension
        words = _as_words(value) if value else 'any (no %s filter)' % dimension
        in_use = current.get(dimension) == value
        lines += word_wrap('%s %s%s' % ('>' if index == focus else ' ', '* ' if in_use else '', words), width)
    lines += [''] + word_wrap('Typed form: :views-page LIMIT OFFSET QUERY OWNERSHIP COVERAGE HEALTH (- means no filter).', width)
    return lines


def filter_words(filters):
    """The estate filters in words: what was searched and which filters apply, or that none do."""
    applied = []
    for key, item in (filters or {}).items():
        if item in (None, '', [], {}):
            continue
        applied.append('search "%s"' % safe_text(str(item)) if key == 'query' else
                       '%s %s' % (str(key).replace('_', ' '), _as_words(item)))
    return 'Filters: %s.' % '; '.join(applied) if applied else 'No filters applied.'


def baseline_words(baseline):
    """A comparison baseline in words: what it is, its identities shortened, its time readable; never a JSON dump."""
    if not isinstance(baseline, dict):
        return _as_words(baseline) if baseline is not None else 'not recorded'
    text = _as_words(baseline.get('kind', 'baseline'))
    for key in ('snapshot_id', 'artifact_id'):
        if isinstance(baseline.get(key), str):
            text += ' ' + baseline[key][:12]
    if isinstance(baseline.get('operation_id'), str):
        text += ' of operation ' + baseline['operation_id'][:12]
    if isinstance(baseline.get('plan_sha256'), str):
        text += ' (plan ' + baseline['plan_sha256'][:12] + ')'
    for key, label in (('observed_at', 'observed'), ('recorded_at', 'recorded')):
        value = baseline.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            text += ', %s %s' % (label, _readable_epoch(value))
        elif isinstance(value, str):
            text += ', %s %s' % (label, _when(value))
    return text


# What the execution plan's equality is, as workbench_diff.field_changes compares (BAGS are compared as bags, so a repeat
# counts and order does not; every other field is exact, and the settings list is exact in order too).
PLAN_EQUALITY = ('(assignments, technologies and role scope tags match in any order, each repeat counting; every other '
                 'field, including the order of settings, must match exactly)')
PLAN_SAME = 'The desired body equals the observed body under the execution plan\'s equality %s.' % PLAN_EQUALITY
# What repository status compares (workbench_repository.intent_freshness): the recorded intent against the repository now.
REPOSITORY_SAME = ('The recorded intent\'s desired body equals the repository\'s body now at the intent pointer, under the '
                   'execution plan\'s equality %s. The observation is not part of this comparison.' % PLAN_EQUALITY)


def change_lines(changes, width, before_label='BEFORE (observed)', after_label='AFTER (desired)', remainder=None,
                 same=PLAN_SAME):
    """A field-change list as a table (wide) or stacked before and after rows (narrow).

    A comparison cut at its limit says so. ``remainder`` names where the complete bodies are, for callers whose
    result holds them; without it nothing beyond the cut is claimed. ``same`` names the two sides when they are equal.
    """
    status = changes.get('status') if isinstance(changes, dict) else None
    if status == 'no_change':
        return ['NO CONFIGURATION CHANGE'] + word_wrap(same, width)
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


# A step that prints a command writes the command after a line break, indented two spaces, so the command stands on its
# own rows: a copied row carries no words, and the sentence before or after it is a separate row (run 9, frame 20).
COMMAND_BREAK = '\n'


def step_rows(text, width, label=''):
    """The rows of a step whose text may hold commands after line breaks: each part wraps by itself (a command wraps
    between its arguments, never inside a quoted path), and only the first part carries the label."""
    rows = []
    for index, part in enumerate(str(text).split(COMMAND_BREAK)):
        rows += word_wrap((label if index == 0 else '') + part, width)
    return rows


def _labelled_steps(label, text, width, size=13):
    """_labelled for a step that may hold commands after line breaks: the label leads the first part, every part's rows
    sit under the text column, and a command keeps its own indent."""
    rows = []
    for index, part in enumerate(str(text).split(COMMAND_BREAK)):
        rows += _labelled(label if index == 0 else '', part, width, size)
    return rows


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
        text += '  ' + group_words(row['group_id'])
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


def collection_result_lines(value, width, tab=None):
    """What a collection run recorded: the run, what it read and when, its effect, and the next step.

    tab: the surface drawn (0-based; 1 is the Inspector). On the Inspector the Next does not name key 2 as if it led
    elsewhere (run 12, frames 24, 43, 46)."""
    count = value.get('object_count')
    head = 'Run %s: %s' % (value.get('run_id'), _as_words(value.get('status') or 'status not recorded'))
    if isinstance(count, int):
        head += '; %d %s observed' % (count, 'policy' if count == 1 else 'policies')
    if readable_time(value.get('observed_at')):
        head += ' at %s' % readable_time(value['observed_at'])
    lines = ['[COLLECTION RESULT]'] + word_wrap(head + '.', width)
    lines += word_wrap('Read: %s.' % coverage_words(value.get('coverage')), width)
    if value.get('error_code'):
        lines += word_wrap('Error: %s' % value['error_code'], width)
    lines += word_wrap('Effect: recorded collection run %s; no policy was changed.' % value.get('run_id'), width)
    reread = ('Next: press 2 again to read this policy with this observation; this screen shows the collection result.'
              if tab == 1 else 'Next: 2 reads this policy again with this observation.')
    lines += word_wrap(reread if value.get('status') == 'complete'
                       else 'Next: the earlier observation is kept; collect again (a: actions), and i shows what '
                            'was not read.', width)
    return lines


def is_collection_run(value):
    """Whether a result is one collection run's record (what collect returns)."""
    return (isinstance(value, dict) and type(value.get('run_id')) is int and 'coverage' in value
            and 'object_count' in value and 'started_at' in value)


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
                + _labelled('', 'No verified meaning is available for this value. Press d to open the setting dictionary and inspect the available setting metadata.', width, 8))
    return lines + _labelled('', '= ' + _setting_value(instance), width, 6)


def inspector_lines(value, width, strip_operation=None):
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
    if isinstance(value.get('states'), dict):
        # Three distinct states replace the one provenance line; nothing is folded into the observation's freshness.
        lines += state_lines(value['states'], width, prefixes=value.get('identity_prefixes'), strip_operation=strip_operation)
        lines += _attention_lines(value, width)
        return lines + _evidence_says(value, body, width)
    # Where the evidence comes from, then what that run covered, then its freshness: each a separate clause.
    source = [evidence_words(value.get('evidence_class'))]
    if value.get('run_id') is not None:
        source.append('run %s' % value['run_id'])
    source.append(_when(value.get('observed_at')))
    clauses = [', '.join(source)]
    clauses += [coverage_words(value['coverage'])] if value.get('coverage') else []
    clauses += [str(value['freshness'])] if value.get('freshness') else []
    lines += _labelled('From', '; '.join(clauses), width, 10)
    lines += _attention_lines(value, width)
    return lines + _evidence_says(value, body, width)


def _evidence_says(value, body, width):
    """What the evidence says the policy does: settings, targets, description and management."""
    lines = ['', 'WHAT THE EVIDENCE SAYS IT DOES']
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
        # Each group says on its own line whether its name was captured; nothing is said once for all of them.
        lines += word_wrap('  %s' % _count(len(assignments), 'target', 'targets'), width)
        for row in assignments:
            if not isinstance(row, dict):
                lines += word_wrap('    ' + _value(row), width)
                continue
            text = TARGET_WORDS.get(row.get('type'), safe_text(str(row.get('type'))))
            if 'group_id' in row:
                text += '  ' + group_words(row['group_id'], names)
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
    if isinstance(value.get('states'), dict):
        managed = 'ownership %s' % value.get('ownership', 'unknown')  # the intent has its own state line above
    lines += _labelled('  Managed', managed, width, 15)
    return lines


def _state_says_stamped_ahead(value, evidence):
    """Whether the State row on this screen already says the observation is stamped after this host's clock, so the
    attention item need not say it again (run 9, frame 44): the row names the stamp and both clock readings."""
    states = value.get('states') if isinstance(value.get('states'), dict) else {}
    observation = states.get('observation') if isinstance(states.get('observation'), dict) else {}
    reasons = observation.get('freshness_reasons') or []
    return ('stamped_after_now' in reasons and not clock_hold(reasons) and observation.get('freshness') != 'fresh'
            and readable_time(evidence.get('observed_at')) is not None)


def _attention_lines(value, width):
    """What diagnostics records as needing attention, the areas it could not examine, and the next steps."""
    lines = []
    attention = value.get('attention') if isinstance(value.get('attention'), dict) else None
    if attention is not None:
        lines += ['', 'NEEDS ATTENTION']
        signals = [signal for signal in attention.get('signals') or [] if isinstance(signal, dict)]
        areas = attention.get('checked') if isinstance(attention.get('checked'), dict) else {}
        eligibility = value.get('observation_eligibility') if isinstance(value.get('observation_eligibility'), dict) else {}
        checked_now = ELIGIBILITY_FINDINGS.get(eligibility.get('reason'))
        if attention.get('status') == 'unavailable':
            lines += word_wrap('  Diagnostics could not be read (%s); i shows the details.' % attention.get('error_code'), width)
        elif not signals and not checked_now:
            clear = ', '.join(area.replace('_', ' ') for area, state in areas.items() if state == 'clear')
            # Scoped to what diagnostics reads; the maintenance queue holds reporting completeness and ownership.
            lines += word_wrap('  No signal in the areas checked%s; reporting completeness and ownership are reviewed in the '
                               'maintenance queue (m opens it).' % (' (%s)' % clear if clear else ''), width)
        guided = isinstance(value.get('actions'), list)
        for signal in signals:
            evidence = signal.get('evidence') if isinstance(signal.get('evidence'), dict) else {}
            named = evidence.get('operation_id')

            def short(text, named=named):
                # The band and the Operation row name an operation by its short id; so does the finding.
                return text.replace(named, short_id(named, value.get('identity_prefixes'))) if isinstance(named, str) and named else text
            observed = short(str(signal.get('observed')))
            if signal.get('code') == 'observation_stale' and _state_says_stamped_ahead(value, evidence):
                # The State row above says why and prints the stamp and the clock reading; this item says only what follows.
                observed = 'The newest observation is not known to be fresh.'
            lines += _labelled('  !', observed, width, 4)
            if guided and signal.get('next_step'):
                # Each condition carries its own response, so issue and action are read together.
                lines += _labelled_steps('    Next', short(str(signal.get('next_step'))), width, 10)
        if checked_now:
            # Not a recorded signal: the check a proposal makes, read now against the configured service.
            lines += _labelled('  !', checked_now[0] % eligibility, width, 4)
            lines += _labelled_steps('    Next', checked_now[1], width, 10)
        # Areas that were not examined stay named as such: nothing is known about them either way.
        unknown = ['%s %s' % (area.replace('_', ' '), AREA_STATE_WORDS[state]) for area, state in areas.items()
                   if state in AREA_STATE_WORDS]
        if unknown:
            lines += word_wrap('  Not fully checked: %s.' % '; '.join(unknown), width)
    if isinstance(value.get('actions'), list):
        offered = [action for action in value['actions'] if isinstance(action, dict)]
        if offered:
            lines += ['', 'ACTIONS']
            lines += word_wrap('  a opens the actions; Enter there stages one for review, and nothing runs until you submit '
                               'it.', width)
            for number, action in enumerate(offered, 1):
                blocked = action.get('blocked') or {}
                reasons = [blocked] + [other for other in blocked.get('also') or [] if isinstance(other, dict)]
                state = ' (available)' if action.get('available') else ' (blocked: %s)' % '; '.join(
                    _compact_block_words(item) for item in reasons)
                lines += _labelled('  %d.' % number, str(action.get('label')) + state, width, 6)
        return lines
    actions = [action for action in value.get('next_actions') or [] if isinstance(action, dict)]
    if actions:
        lines += ['', 'NEXT']
        for action in actions:
            lines += _labelled_steps('  ', str(action.get('step')), width, 2)
    return lines


# The proposal's own observation checks as findings: (what was found, from the recorded facts; the response).
ELIGIBILITY_FINDINGS = {
    'service_changed': ('The source changed since this observation was captured (revision '
                        '%(observed_revision)s, now %(service_revision)s); a proposal needs a new collection.',
                        'Collect again; a lists it with the other actions.'),
    'policy_changed': ('This policy changed at the source since this observation was captured; a proposal '
                       'needs a new collection.', 'Collect again; a lists it with the other actions.'),
    'source_mismatch': ('This observation came from another service than the one configured.', 'Collect again from '
                        'the configured service; a lists it with the other actions.'),
    'tenant_mismatch': ('The configured service is for another tenant than this store.', 'Restart with the '
                        '--service-root for this store\'s tenant.')}


# Why an action is blocked, in a few words; the actions layer (a) gives the engine's full meaning.
BLOCK_WORDS = {'maintenance_observation_stale': 'the observation is not fresh',
               'maintenance_observation_incomplete': 'the observation is incomplete',
               'maintenance_observation_source_mismatch': 'the observation came from another source',
               'workbench_repository_stale': 'the repository changed since its intent',
               'workbench_repository_unavailable': 'the repository cannot be read',
               'service_required': 'needs a modeled service (--service-root)',
               'workbench_attention_not_established': 'diagnostics not read yet',
               # Which observation check failed, when the engine's code covers several.
               'service_changed': 'the source changed since capture', 'policy_changed': 'the policy changed at the '
               'source since capture', 'not_fresh': 'the observation is not fresh', 'last_attempt_incomplete':
               'the last collection did not complete', 'coverage_incomplete': 'the observation is incomplete',
               'source_mismatch': 'the observation came from another service', 'tenant_mismatch': 'the observation is '
               'for another tenant', 'repository_changed': 'the repository changed since its intent',
               'consumer_changed': 'the component no longer consumes this policy',
               'repository_unreadable': 'the repository cannot be read',
               'workbench_fresh_output_required': 'no fresh operation directory'}


def consumer_words(status):
    """The consumer state as a screen says it. `verified` is what consumer_contract established: the component's files, as
    read, consume exactly this policy. It says nothing of the revision, which is shown on its own row (run 12, L-verified)."""
    words = _as_words(status)
    return "verified (the component's files, as read, consume exactly this policy)" if status == 'verified' else words


def refresh_result_lines(value, width, header=True):
    """A recorded repository intent and what the refresh established, read back: the new intent and, when the
    result says so, the previous intent kept as history. Nothing is said about effects the result does not carry."""
    data = value.get('data') if isinstance(value.get('data'), dict) else {}
    effects = value.get('effects') if isinstance(value.get('effects'), dict) else {}
    recorded = effects.get('intent_recorded', value.get('created', True))
    lines = []
    if header:
        lines = ['[NEW REPOSITORY INTENT RECORDED]' if recorded else '[REPOSITORY INTENT ALREADY RECORDED]']
        lines += word_wrap('Intent: ' + str(value.get('artifact_id'))[:12], width)
    lines += word_wrap('Revision: %s (%s)' % (data.get('source_revision'), 'content verified' if
                       data.get('revision_content_verified') else 'caller asserted, not checked against the files'),
                       width)
    lines += word_wrap('Consumer: ' + consumer_words((data.get('consumer') or {}).get('status', 'not recorded')), width)
    previous = effects.get('previous_intent')
    if recorded and isinstance(previous, str) and previous != value.get('artifact_id'):
        lines += word_wrap('Previous intent %s is kept as history. Reviews prepared from it do not cover this intent; '
                           'they remain inspectable (4 History, 5 Plan).' % previous[:12], width)
    elif not recorded:
        lines += word_wrap('No new intent was recorded; this is the latest intent already.', width)
    # A value outside the capability map is said here, when it is recorded, with the explanation a proposal gives.
    if isinstance(data.get('desired'), dict) and (data.get('consumer') or {}).get('status') == 'verified':
        from .workbench_repository import capability_explanation
        problem = capability_explanation(data['desired'])
        if problem:
            lines += word_wrap('%s A proposal from this intent will be refused; change that setting in the stack '
                               'input to a supported value and refresh again.' % problem, width)
    lines += word_wrap('9 reads the repository again and compares it with this intent.', width)
    return lines


def _blocked_meaning(blocked):
    """The discriminating message when the engine's code covers several causes or the message names something
    particular (a setting, a value); otherwise the code's general meaning."""
    code = blocked.get('code')
    message = str(blocked.get('message') or '')
    return (message if blocked.get('reason') or code not in REFUSALS or (message and _names_specifics(message))
            else REFUSALS[code][0])


# Blocked actions whose own recovery is said beside the reason, as the refusal says it (journey 28 run 8, frame 80).
BLOCK_RECOVERY_CODES = ('workbench_desired_capability',)
# The same recoveries read inside the actions list, where a is not a key and the actions a refusal names are not all
# there: the refresh is offered only once the repository reads as changed, and the proposal is the entry itself.
BLOCK_RECOVERY_IN_LIST = {
    'workbench_desired_capability': (
        "Change that setting in the repository's stack input to a supported value. Once the repository reads as changed, "
        'this list offers Refresh the repository intent; after it, this entry, Prepare a proposal from the recorded '
        'intent, can be staged.')}


def _blocked_words(blocked):
    """Why an action is blocked: the meaning in words first, then the recovery where the code has one, the engine's
    code kept last in parentheses. It is read inside the actions list, where a is not a key, so the recovery says where
    each action it names is (run 11, frame 80)."""
    meaning, code = _blocked_meaning(blocked), blocked.get('code')
    if code in BLOCK_RECOVERY_CODES and code in BLOCK_RECOVERY_IN_LIST:
        meaning = meaning.rstrip() + ' ' + BLOCK_RECOVERY_IN_LIST[code]
    return '%s (%s)' % (meaning.rstrip(), code) if code else meaning


def _compact_block_words(item):
    """A blocked action's reason in a few words. An observation whose age is not known (a stamp after this host's clock,
    or a clock hold) is not known to be fresh: the record does not establish that it is not fresh."""
    reasons = item.get('freshness_reasons') or []
    if item.get('reason') == 'not_fresh' and (item.get('clock_hold') or clock_hold(reasons) or 'stamped_after_now' in reasons):
        return 'the observation is not known to be fresh'
    return (BLOCK_WORDS.get(item.get('reason')) or BLOCK_WORDS.get(item.get('code'))
            or (_code_words(item['code']) if item.get('code') else 'not available'))


def actions_lines(actions, focus, width, name=None, object_id=None, submit='Enter', prefixes=None):
    """The guided actions for the selected policy: what each is, whether it is available, its exact command and what
    it does. A blocked action says why, with the engine's own code."""
    lines = word_wrap('ACTIONS  for %s (%s)' % (name or 'the selected policy', short_id(object_id, prefixes)), width)
    lines += word_wrap('Nothing runs until you submit it: Enter puts the focused command in the command bar for review, '
                       '%s there submits it, Esc discards it.' % submit, width)
    for index, action in enumerate(actions):
        lines.append('')
        focused = index == focus
        state = 'available' if action.get('available') else 'blocked'
        lines += _labelled('%s %d.' % ('>' if focused else ' ', index + 1), '%s  (%s)' % (action.get('label'), state), width, 5)
        # One description per entry: the essential effect, or for the focused entry the full text that includes it, so
        # the effect is stated once (run 11, frames 21, 37, 62, 80); then the exact command or the reason it is blocked.
        described = (action.get('effects') if focused else None) or action.get('summary') or action.get('effects')
        lines += _labelled('', str(described), width, 5)
        if action.get('available') and not focused:
            names = ' and '.join(str(need).split(':')[0] for need in action.get('needs') or [])
            if names:
                lines += _labelled('', 'needs  ' + names, width, 5)
        elif action.get('available'):
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
            lines += _labelled('', 'blocked  ' + _blocked_words(blocked), width, 5)
            # Every other reason that blocks the same action, so a second hazard is not hidden behind the first.
            for other in blocked.get('also') or []:
                if isinstance(other, dict):
                    lines += _labelled('', 'also blocked  ' + _blocked_words(other), width, 5)
    return lines


def details_lines(value, width):
    """Every field of an engine result as a readable outline: words for absent and yes/no values, lists numbered."""
    lines = []

    def scalar(item):
        if item is None:
            return 'not recorded'
        if isinstance(item, bool):
            return 'yes' if item else 'no'
        if item == '':
            return '"" (empty text)'  # recorded and empty, never read as missing
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
                shown = scalar(child) if not isinstance(child, (dict, list)) else (
                    '[] (empty list)' if isinstance(child, list) else '{} (empty map)')
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


# Keys first, one per row, in the order an engineer reaches for them (P-PRES-10). Each is bound in the workspace.
HELP_KEYS = (
    ('1-9', 'switch surface: 1 Estate, 2 Inspector, 3 Relationships, 4 History, 5 Plan, 6 Execution, 7 Coverage, '
            '8 Help, 9 Repository'),
    ('Tab', 'next surface'),
    ('Up, Down', 'choose; Enter selects (a policy on Estate, an operation on Plan and Execution)'),
    ('PgUp, PgDn', 'scroll'),
    ('n', 'next page of a long list'),
    ('p', 'previous page of a long list'),
    ('e', 'typed details of the result shown; e again or Esc returns to the summary'),
    ('r', 'the complete raw engine record; r again or Esc returns to the summary'),
    ('a', 'actions for the selected policy, each with its exact command, what it does and whether it is available; '
          'Enter stages one in the command bar for review'),
    ('/', 'search the estate'),
    ('f', 'estate filters: a list of ownership, coverage and health filters; Enter applies one, keeping the others'),
    (':', 'command bar: Enter submits (Ctrl+Enter in the native Windows console), Esc discards; nothing runs until it '
          'is submitted'),
    ('b', 'back to the previous read-only view (also :back); never re-sends a change'),
    ('o', 'relationship overview of the estate'),
    ('d', 'setting dictionary'),
    ('l', 'lineage: where each effective value comes from in the repository'),
    ('h', 'health'),
    ('m', 'maintenance queue'),
    ('i', 'diagnostics: every recorded finding and what could not be checked'),
    ('v', 'delivery of the active operation'),
    ('s', 'survey: what exists beside the store'),
    ('?', 'this help'),
    ('q', 'exit the workbench'),
    ('Ctrl-C', 'stop a running call; the session ends'),
)
# The words the screens use, then how changes and the session work.
HELP_WORDS = (
    ('Mode', 'The first word of the line under the tabs says where the evidence comes from: SYNTHETIC (a modeled '
             'service), CAPTURE (an unverified export), LABORATORY (recorded responses; the source is not '
             'authenticated), LIVE READ-ONLY (an authenticated read), MIXED (more than one of these), READ FAILED '
             '(a read returned no policy) or MODE UNKNOWN (nothing observed yet, or a kind this version does not name).'),
    ('Context', 'Then the tenant and the selected policy (in the narrowest windows T stands for TENANT and P for POLICY). OBS (observed) fresh means the newest complete observation is '
                'inside the freshness window and no later collection of it failed or is pending; source changed '
                'means the source has a newer revision than the one captured, so a proposal needs a new '
                'collection; the observation itself stays as captured. '
                'REPO (repository) current means the recorded repository intent still matches the repository files and '
                'effective configuration. OP is the newest operation\'s recorded status; when it reports another '
                'operation (the plan under review), OP names that operation\'s id.'),
    ('Short words', "When the line is narrow it shortens a state: verified means succeeded verified; unchecked means not "
                    'checked; unknown means outcome unknown; not revalidated means recorded intent not revalidated; observed '
                    "means desired state observed; age? means age unknown (a clock hold, or a stamp after this host's "
                    'clock); stale means stale from any cause (older than the freshness window, or a later collection did '
                    'not complete; 2 Inspector says which). One step before that, age unknown (stamped ahead) reads age '
                    'unknown, and stale (later collection incomplete) reads stale (collection incomplete).'),
    ('+N more: ?', 'When the line cannot hold every state it ends with this, N counting the states it left out; this '
                   'help prints the line in full under Context.'),
    ('! line', 'The bold line under it names the most important recorded condition and the key for its response; '
               '+N more: 2 counts the others, which the Inspector lists.'),
    ('STATE', 'The Inspector, the Repository status and the Plan review show the observation, the repository intent '
              'and the newest operation as three separate states.'),
    ('Workflow map', ":workflow draws the selected policy's change path over the Inspector, one lane for each stage: observe, "
                     'adopt, intent, propose, review, approve and execute, readback (reconcile branches from it), record, '
                     'observed after and maintain. A lane shows the state its records give: x done, + current, : waiting, '
                     '! blocked, # refused, ? unknown, _ not recorded, - not applicable. @ marks where the records say the '
                     "policy has got to and > the focus. Up and Down move the focus; Enter opens that stage's surface for "
                     'the same policy; b and Esc return. It reads and records nothing in the store. intune-iac workbench '
                     'workflow --root ROOT --policy ID prints the same lines.'),
    ('Changes', 'propose DESIRED_JSON NEW_OPERATION_DIR or propose-from-intent NEW_OPERATION_DIR prepares a proposal; '
                'execute OPERATION_DIR EXACT_REVIEW_DIGEST runs it only with the digest from its review; reconcile '
                'OPERATION_DIR reads the service when an outcome is unknown and never replays. Moving around never '
                'proposes, approves or executes. Every command the engine accepts is in the typed details of this '
                'page (e).'),
    ('Session', 'The next start reopens the last read-only view of the selected policy; Delivery and '
                'repository-entry views, which hold paths, are not reopened. :clear-selection clears the selected '
                'policy. Between commands nothing is running, so :cancel cancels nothing.'),
)


# What a node row of a kind that has no operation shows in the state column, by the rules in use: never a state word.
# In ASCII it is the word n/a, not a drawing character: -- is also a tree branch (|--), and a dash that means two things
# on one screen is read as either. The legend and the help define it.
MAP_NO_STATE = {'ascii': 'n/a', 'unicode': '—'}

# Named only where a relationship map can be shown (a selected policy and a window with room for it).
HELP_MAP_KEYS = (
    ('Map', 'on Relationships (3) Up, Down move to the next or previous node; Enter opens the Inspector on the policy, '
            'and says so when a node has no inspect route (only a policy has one)'),
    ('Order', 'the map draws the layers in the order of the tree below (targeting, configuration, source and lineage) '
                 'and sorts each layer by identifier; the tree lists each group as the read model gives it'),
    ('Left, Right', 'pan the map when it is wider than the window'),
    ('Home', "follow the focused node's edge to its other end; from the policy, to its first neighbour"),
    ('Marks', 'x verified, + running, . queued, : waiting, ! blocked, # failed, - cancelled, ? unknown, ~ expired, o prepared, '
              '_ none recorded: only a policy has one, beside the word the read model recorded. [ ] with %s (%s in ASCII) '
              'means the kind has no operation state, and a node with it shows no state at all' % (MAP_NO_STATE['unicode'], MAP_NO_STATE['ascii'])),
)


STRIP_FIELDS = ('OBS', 'REPO', 'OP')  # the labels the full strip prints before its states


def hidden_strip_fields(full, shown):
    """The states the strip left out at this size, from its full text and the text it shows: [(label, value)]."""
    shown_segments = shown.split(' | ')
    names = '|'.join(STRIP_FIELDS)
    hidden = []
    for label in STRIP_FIELDS:
        found = re.search(r'(?: \| )%s (.*?)(?= \| (?:%s) |$)' % (label, names), full)
        if found and not any(seg.startswith(label + ' ') for seg in shown_segments):
            hidden.append((label, found.group(1)))
    return hidden


def hidden_strip_rows(hidden, width):
    """The rows that name the states the strip left out, with their values. Each `LABEL value` stays whole and fields that
    share a row are joined by ' | '. A break falls between two fields and takes the separator with it, so a row never ends
    with `|` (journey 29 run 13, frame 37, rows 6 and 7) and a label is never left apart from its value."""
    rows = word_wrap('Hidden in the strip at this size (+%d more):' % len(hidden), width)
    current, started = rows.pop(), False
    for label, value in hidden:
        field = '%s %s' % (label, value)
        joined = current + (' | ' if started else ' ') + field
        if cell_width(joined) <= width:
            current = joined
        else:
            rows.append(current)
            parts = word_wrap(field, width)
            rows += parts[:-1]
            current = parts[-1]
        started = True
    return rows + [current]


def help_lines(width, map_keys=False, strip=None, strip_shown=None):
    """The one reference: keys first, one per row, then the words the screens use.

    map_keys: add the keys of the relationship map, after Up, Down.
    strip: the context line in full, printed under Context for the states the narrow line left out (+N more: ?).
    strip_shown: the line the strip shows at this size; the states it left out are listed first, with their values, so
    the first screen answers the +N more: ? that sent the engineer here (journey 29 N4)."""
    lines = ['HELP']
    hidden = hidden_strip_fields(strip, strip_shown) if strip and strip_shown else []
    if hidden:
        lines += hidden_strip_rows(hidden, width)
    lines.append('KEYS')
    for key, text in HELP_KEYS:
        lines += _labelled('  ' + key, text, width, 14)
        if map_keys and key == 'Up, Down':
            for map_key, map_text in HELP_MAP_KEYS:
                lines += _labelled('  ' + map_key, map_text, width, 14)
    lines += ['', 'WORDS AND RULES']
    for name, text in HELP_WORDS:
        lines += _labelled('  ' + name, text, width, 14)
        if name == 'Context' and strip:
            lines += _labelled('  Line now', strip, width, 14)
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
            lines += _labelled('Source', ' | '.join(str(part) for part in (
                source.get('publisher'), 'updated ' + _when(source.get('published_update_at'), 'not recorded'),
                'retrieved ' + _when(source.get('retrieved_at'), 'not recorded'), source.get('url')) if part), width)
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
    if relation in ('assignment', 'exclusion') and details.get('group_id'):
        text = group_words(target)
    if relation == 'assignment' and details.get('filter_type') not in (None, 'none'):
        text += '  filter ' + safe_text(str(details['filter_type'])) + ' ' + safe_text(str(details.get('filter_id')))
    return text


# The typed tree: a branch, the last branch and the rail a continuation line keeps while its branch is open, in each rules.
TREES = {'ascii': ('|-- ', '`-- ', '|   '), 'unicode': ('├── ', '└── ', '│   ')}


def _count(number, singular, plural):
    return '%d %s' % (number, singular if number == 1 else plural)


def _users(ids, verb, short=None):
    shown = ', '.join(short_id(str(item), short) for item in ids[:4]) + (', ...' if len(ids) > 4 else '')
    return '%s %s (%s)' % (verb, _count(len(ids), 'policy', 'policies'), shown)


def overview_lines(value, width, rules='ascii', focus=None, selected=None):
    """The estate's relationships: shared groups, filters, scope tags and settings first, then each policy."""
    tree = TREES.get(rules, TREES['ascii'])
    counts = value.get('counts') or {}
    from .io import unique_prefixes
    # Each kind of identity is shortened to the shortest prefix unique among those this screen shows.
    rows_of = lambda key: [row for row in value.get(key) or [] if isinstance(row, dict)]
    users = [item for key in ('groups', 'broad_targets', 'filters', 'scope_tags', 'shared_settings') for row in rows_of(key)
             for field in ('included_by', 'excluded_by', 'used_by') for item in row.get(field) or []]
    policy_short = unique_prefixes([str(row.get('object_id')) for row in rows_of('policies')] + [str(item) for item in users])
    group_short = unique_prefixes([str(row.get('group_id')) for row in rows_of('groups')])
    filter_short = unique_prefixes([str(row.get('filter_id')) for row in rows_of('filters')])
    owners = ', '.join('%s %d' % item for item in sorted((value.get('ownership') or {}).items())) or 'none recorded'
    lines = ['[ESTATE OVERVIEW]']
    lines += word_wrap('%s of %s policies read | %s without a complete observation | ownership: %s' % (
        counts.get('policies_read'), counts.get('policies_total'), counts.get('without_complete_observation'), owners), width)
    lines += word_wrap('What several policies share comes first. Up and Down move between policies below (> focus, * selected); '
                       'Enter selects one.', width)

    def section(heading, rows, describe, empty='none observed'):
        lines.extend(['', heading])
        if not rows:
            lines.append('  ' + empty)
        for index, row in enumerate(rows):
            last = index == len(rows) - 1
            head, cont = '  ' + (tree[1] if last else tree[0]), '  ' + ('    ' if last else tree[2])
            for number, part in enumerate(word_wrap(describe(row), max(1, width - len(head)))):
                lines.append((head if number == 0 else cont) + part)

    # Said once for the list: no group name is captured, so each line is an unresolved group identity.
    section('TARGETED GROUPS  (%s)' % UNRESOLVED_GROUP if value.get('groups') else 'TARGETED GROUPS', value.get('groups') or [], lambda row: '%s  %s' % (short_id(str(row['group_id']), group_short), ', '.join(
        part for part in ((_users(row['included_by'], 'included by', policy_short) if row.get('included_by') else ''),
                          (_users(row['excluded_by'], 'excluded by', policy_short) if row.get('excluded_by') else '')) if part)))
    broad = value.get('broad_targets') or []
    if broad:
        # Targets that name no group, kept apart so they are never read as groups.
        section('ALL-DEVICE AND ALL-USER TARGETS', broad, lambda row: '%s  %s' % (
            TARGET_WORDS.get(row.get('target'), safe_text(str(row.get('target')))), _users(row['used_by'], 'targeted by', policy_short)))
    section('FILTERS', value.get('filters') or [], lambda row: '%s  %s' % (short_id(str(row['filter_id']), filter_short),
                                                                       _users(row['used_by'], 'used by', policy_short)))
    section('SCOPE TAGS', value.get('scope_tags') or [], lambda row: '"%s"  %s' % (row['tag'], _users(row['used_by'], 'used by', policy_short)))
    section('SHARED SETTINGS  (%s distinct in the estate)' % value.get('distinct_settings', 'unknown'),
            value.get('shared_settings') or [], lambda row: '%s  %s' % (row['setting'], _users(row['used_by'], 'used by', policy_short)),
            empty='none used by more than one policy')
    lines.extend(['', 'POLICIES'])
    for index, policy in enumerate(value.get('policies') or []):
        found = policy.get('findings') or []
        reach = ', '.join('targets ' + TARGET_WORDS.get(target, safe_text(str(target))) for target in policy.get('broad_targets') or [])
        text = '%s (%s)  %s, %s, %s, %s%s | owner %s | %s%s' % (
            policy.get('name') or '(no name)', short_id(str(policy.get('object_id')), policy_short),
            _count(policy.get('included_groups', 0), 'group', 'groups'), _count(policy.get('excluded_groups', 0), 'exclusion', 'exclusions'),
            _count(policy.get('filters', 0), 'filter', 'filters'), _count(policy.get('settings', 0), 'setting', 'settings'),
            ', ' + reach if reach else '', policy.get('ownership'), policy.get('freshness'), '' if found else ' | no findings')
        # As in Estate: > is the keyboard focus, * the pinned selection every surface shows.
        mark = ('>' if index == focus else ' ') + ('*' if selected and policy.get('object_id') == selected else ' ') + ' '
        for number, part in enumerate(word_wrap(text, max(1, width - 3))):
            lines.append((mark if number == 0 else '   ') + part)
        if found:
            lines += word_wrap('    %s: %s' % (_count(len(found), 'finding', 'findings'), ', '.join(_as_words(item) for item in found)), width)
    lines.extend(['', 'NOT ESTABLISHED'])
    missing = value.get('not_established') or []
    if not missing:
        lines += word_wrap('  Nothing was left out: every policy in the store has a complete observation; freshness is shown '
                           'for each policy below.', width)
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
    # The same words as the map's header: a selected repository is listed in the tree but is not a relationship.
    from .graph_projection import count_phrase, counts_of
    lines += word_wrap('%s | coverage %s | observed %s' % (
        count_phrase(counts_of(value)), value.get('coverage', 'unknown'), readable_time(value.get('observed_at')) or 'unknown'), width)
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
            lead = pad(label, 13) if cell_width(label) < 13 else label + '  '
            text = _edge_target(edge) + ('' if shared else '  [' + safe_text(str(edge.get('assertion_class', 'unknown'))) + ']')
            # A wrapped part continues the target, so it starts under the target's column, not under the label's.
            for number, part in enumerate(word_wrap(text, width - len(connector) - cell_width(lead)) or ['']):
                lines.append((connector + lead if number == 0 else guide + ' ' * cell_width(lead)) + part)
    ownership = value.get('ownership_evidence') if isinstance(value.get('ownership_evidence'), dict) else {}
    lines.append('OWNERSHIP')
    reason = ownership.get('reason')
    lines += word_wrap('  ' + tree[1] + pad('writer', 13) + _as_words(value.get('ownership', 'unknown'))
                       + (' (%s)' % _as_words(reason) if reason else ''), width)
    return lines


class MapLine(str):
    """A row of a map surface: geometry, not prose.

    draw() neither wraps it (a wrap at a space would split a connector row and break the spine) nor lets the pane's
    row scrolling alone reach it: the pane's horizontal viewport applies to map rows only. `focused` marks the row
    of the focused node, so the pane can keep it in view."""
    focused = False


def _map_row(text, focused=False):
    row = MapLine(text)
    row.focused = focused
    return row


def slice_cells(text, start, cells):
    """The `cells` cells of `text` from cell `start`; a wide character cut by either edge becomes a blank."""
    result, position, end = [], 0, start + cells
    for char in text:
        size = cell_width(char)
        if position >= start and position + size <= end:
            result.append(char)
        elif position + size > start and position < end:
            result.append(' ' * (min(position + size, end) - max(position, start)))
        position += size
        if position >= end:
            break
    return ''.join(result)


def _has_ink(text, low, high):
    """Whether a character that is not blank space lies, wholly or partly, in the cells low to high of text."""
    position = 0
    for char in text:
        size = cell_width(char)
        if position < high and position + size > low and not char.isspace():
            return True
        position += size
        if position >= high:
            break
    return False


def viewport_row(text, hscroll, cells, gutter, ellipsis):
    """One map row as the pane's horizontal viewport shows it: the `gutter` cells (the focus and selection marks) where
    they are, then the part of the row from `hscroll` cells past the gutter, `cells` cells wide in all.

    A row the window cuts says so. When more of the row lies to the right of the window, the last cells are the ellipsis;
    when the window starts past some of the row, the first cells after the gutter are the ellipsis. Blank space is not a
    continuation, so a row that is only padded past the edge, or has nothing left of the window, claims nothing. This is
    what keeps a state word cut to "no" from reading as the word "no"."""
    room = max(0, cells - gutter)
    start = gutter + hscroll
    body = slice_cells(text, start, room)
    cut_left = hscroll > 0 and _has_ink(text, gutter, start)
    cut_right = _has_ink(text, start + room, cell_width(text))
    size = cell_width(ellipsis)
    if cut_right:
        body = pad(body, room)
        body = slice_cells(body, 0, max(0, room - size)) + ellipsis
    if cut_left:
        body = ellipsis + slice_cells(body, size, max(0, room - size))
    return slice_cells(text, 0, gutter) + body


# The relationship map: fixed geometry from topology and stable identity only. Every node cell is a mark, a label and
# the state word padded to one width, in the same columns on every row and at every window size, so a state change
# changes the mark and the word, never a coordinate. A window narrower than the map pans it (Left, Right); the first
# MAP_GUTTER cells of every row (the focus and selection marks) stay where they are while the rest pans.
MAP_MIN_SIZE = (60, 20)
MAP_LAYER_LIMIT = 6
MAP_STATE_MARKS = {'queued': '.', 'running': '+', 'waiting': ':', 'blocked': '!', 'failed': '#', 'cancelled': '-',
                   'unknown': '?', 'verified': 'x'}
# The policy's recorded operation words the eight state words have no mark for.
MAP_OPERATION_MARKS = {'none recorded': '_', 'expired': '~', 'prepared': 'o'}
# The widest word the state column holds ("none recorded"); a longer recorded word is cut there and whole in the FOCUS rows.
MAP_WORD_WIDTH = 13
MAP_GUTTER = 3
MAP_STATE_COLUMN = 62
MAP_WIDTH = MAP_STATE_COLUMN + MAP_WORD_WIDTH
MAP_RELATION_WIDTH = 10
# What fits a label column after a kind word, for the kinds whose labels are cut around an ellipsis.
MAP_DISTINCT_WIDTH = 27
MAP_DISTINCT_KINDS = DISTINCT_KINDS
# No glyph of the tree is also a mark: the ASCII branch is a bar and a dash, never "+", which is the running mark.
MAP_GLYPHS = {'ascii': {'branch': '|- ', 'last': '`- ', 'guide': '|  ', 'arrow': ' -> '},
              'unicode': {'branch': '├─ ', 'last': '└─ ', 'guide': '│  ', 'arrow': ' ─→ '}}
# The one table of kind words, shared with the projection and the page (graph_projection owns it).
MAP_KIND_WORDS = KIND_WORDS
# The marks a node row can carry, in words, and the focus and selection marks of the gutter.
MAP_STATE_LEGEND = ('[x] verified', '[+] running', '[.] queued', '[:] waiting', '[!] blocked', '[#] failed', '[-] cancelled',
                    '[?] unknown')
MAP_OPERATION_LEGEND = ('[~] expired', '[o] prepared', '[_] none recorded')
MAP_FOCUS_LEGEND = '> focus * selected'


def map_legends(rules='ascii'):
    """The legend's forms by the rows they take, widest first, as tuples of rows. Fixed text: a form depends on the width
    (the first whose every row fits) and on the rules (the word a no-state row shows), never on a state. The forms that
    can hold every mark name each one and say what the no-state word means; the narrower ones keep saying where the rest
    are listed (the help screen, which lists them all), and the narrowest says only the gutter's marks."""
    word = MAP_NO_STATE.get(rules, MAP_NO_STATE['ascii'])
    states, operations = ' '.join(MAP_STATE_LEGEND), ' '.join(MAP_OPERATION_LEGEND)
    return (
        ('%s %s | [ ] %s means the kind has no operation state | %s' % (states, operations, word, MAP_FOCUS_LEGEND),),
        (states, '%s | [ ] %s means the kind has no operation state | %s' % (operations, word, MAP_FOCUS_LEGEND)),
        ('%s | %s means no operation state | marks: ? help' % (MAP_FOCUS_LEGEND, word),),
        # The 60x20 pane: the rows show the no-state word, so this form defines it in the fewest words.
        ('%s | %s means no state | marks: ? help' % (MAP_FOCUS_LEGEND, word),),
        ('%s | marks: ? help lists them' % MAP_FOCUS_LEGEND,),
        (MAP_FOCUS_LEGEND,),
    )


class PinnedRow(str):
    """A row the pane keeps in view when the map is taller than the pane: the legend and the focused node's rows."""


def map_fits(size):
    """Whether a window of `size` (columns, rows) has room for the map; below it the view says there is none."""
    return size[0] >= MAP_MIN_SIZE[0] and size[1] >= MAP_MIN_SIZE[1]


def map_unavailable_lines(width, graph=True):
    """What the Relationships view says where there is no map: that it is not drawn, and where the relationships are."""
    first = 'MAP NOT DRAWN (needs %dx%d)' % MAP_MIN_SIZE if graph else 'MAP NOT DRAWN (this result names no object)'
    sentence = 'The tree below lists every relationship.'
    if cell_width(sentence) > width:
        # The narrowest body (36 columns) holds the sentence whole in its short form, never cut mid-sentence (run10-R1).
        sentence = 'PgDn: tree lists all relationships'
    return [first] + word_wrap(sentence, width) + ['']


def _drawn_layers(graph):
    """Each layer of the graph with the edges drawn (the first MAP_LAYER_LIMIT, in order) and how many are not."""
    layers = []
    for heading in graph['layers']:
        edges = [edge for edge in graph['edges'] if edge['layer'] == heading]
        layers.append((heading, edges[:MAP_LAYER_LIMIT], max(0, len(edges) - MAP_LAYER_LIMIT)))
    return layers


def map_order(graph):
    """The node references the map draws, in the order the keyboard visits them: the policy, then layer by layer."""
    order = [graph['center']]
    for _, edges, _ in _drawn_layers(graph):
        for edge in edges:
            if edge['target'] not in order:
                order.append(edge['target'])
    return order


def map_node(graph, ref):
    return next((node for node in graph['nodes'] if node['ref'] == ref), None)


def _map_label(node, shorts, prefixes):
    kind, identifier, name = node['kind'], node['id'], node['name']
    short = shorts.get(kind, {}).get(identifier, identifier[:8])
    if kind == 'policy':
        return '%s (%s)' % (name or '(no name)', short_id(identifier, prefixes))
    if kind == 'group':
        return '%s (%s)' % (name, short) if name else '%s %s' % (UNRESOLVED_GROUP, short)
    if kind == 'filter':
        return 'filter ' + short
    if kind == 'scope_tag':
        return 'scope tag "%s"' % identifier
    if kind == 'target':
        return TARGET_WORDS.get(identifier, identifier)
    return identifier


def _repository_path_label(identifier, width, ellipsis):
    """The repository node's row label: its local path alone, cut around an ellipsis (the folder's own name kept).

    The node's identity is `PATH  STACK / COMPONENT`; cutting that whole text kept the head of the path and the tail of
    the component, which read as one path that is not recorded (run10-3). The full identity stays in the focus rows."""
    path = identifier.rpartition(' / ')[0].rpartition('  ')[0] or identifier
    if len(path) <= width:
        return path
    room = width - len(ellipsis)
    tail = min(room - 8, len(path) - len(path.rstrip('/').rpartition('/')[0]))
    return path[:room - tail] + ellipsis + path[len(path) - tail:]


def _map_legend(width, rules='ascii'):
    forms = map_legends(rules)
    return next((form for form in forms if all(cell_width(row) <= width for row in form)), forms[-1])


def _map_cell(prefix, node, label, label_width, ellipsis, rules='ascii'):
    """One node cell on a row: mark, label and the state column, ending MAP_WIDTH cells from the row's start.

    A policy shows the operation word the read model recorded and the mark for it; a kind that has no operation shows no
    mark and a dash. Nothing here says "unknown" for a word that is known, or any state for what cannot have one."""
    if node.get('state_applies', node['kind'] == 'policy'):
        word = node.get('operation') or 'none recorded'
        state = node['state'] if node['state'] in MAP_STATE_MARKS else 'unknown'
        mark, shown = MAP_OPERATION_MARKS.get(word) or MAP_STATE_MARKS[state], fit(word, MAP_WORD_WIDTH, ellipsis)
    else:
        mark, shown = ' ', MAP_NO_STATE.get(rules, MAP_NO_STATE['ascii'])
    return '%s[%s] %s %s' % (prefix, mark, pad(fit(label, label_width, ellipsis), label_width), pad(shown, MAP_WORD_WIDTH))


def _layer_evidence(edges):
    classes = {edge['provenance'] for edge in edges}
    fresh = {edge['freshness'] for edge in edges}
    if len(classes) == 1 and len(fresh) == 1:
        return '[%s, %s]' % (safe_text(classes.pop().replace('_', ' ')), safe_text(fresh.pop()))
    return '[mixed evidence: the tree below names each]'


def _focus_lines(graph, node, width):
    """The map's inspector rows: the focused node exactly, the edges that reach it and whether it can be inspected."""
    first = 'FOCUS %s  %s' % (MAP_KIND_WORDS.get(node['kind'], node['kind']), node['id'])
    name = node['name'] or ('(unresolved identity)' if node['kind'] == 'group' else None)
    if node['ref'] == graph['center']:
        second = 'selected policy | operation %s | Enter opens the Inspector (2)' % (node.get('operation') or 'none recorded')
    else:
        edges = [edge for edge in graph['edges'] if edge['target'] == node['ref']]
        second = '%s edge | %s | %s | no operation state | no inspect route' % (
            ', '.join(sorted({edge['type'].replace('_', ' ') for edge in edges})),
            ', '.join(sorted({edge['provenance'].replace('_', ' ') for edge in edges})),
            ', '.join(sorted({edge['freshness'] for edge in edges})))
    # The identity row is the one the pane keeps in view; the name and the row of detail follow it in the flow.
    return ([PinnedRow(part) for part in word_wrap(first, width)],
            (word_wrap(name, width) if name else []) + word_wrap(second, width))


def _filter_notes(graph, shorts):
    """A row under a node a filter bears on, as the read model stated it: the group an assignment applies a filter to says
    which filter and its type, and the filter says which assignment it applies to."""
    notes = {}
    for edge in graph['edges']:
        if edge.get('filter') and edge['target'] not in notes:
            ref = edge['filter']['ref']
            notes[edge['target']] = '+ filter %s %s' % (shorts['filter'].get(edge['filter']['id'], edge['filter']['id'][:8]),
                                                       edge['filter']['type'])
        if edge.get('applies_to') and edge['target'] not in notes:
            kind, identifier = edge['applies_to'].split(':', 1)
            notes[edge['target']] = 'applies to %s' % shorts.get(kind, {}).get(identifier, identifier[:8])
    return notes


def map_lines(graph, width, rules='ascii', focus=None, selected=None, prefixes=None, hscroll=0, strip_key=()):
    """The one-hop relationship map, then its legend and the focused node's rows, for a pane `width` cells wide.

    Layered by relation group in the order of RELATION_GROUPS, each layer sorted by identifier, one hop only: a layer
    longer than MAP_LAYER_LIMIT says how many are not drawn (the typed tree below lists them all). The rows are
    MapLines; the header and the pan statement are ordinary text; the legend and the focused node's rows are PinnedRows,
    which the pane keeps in view when the map is taller than it. strip_key: the definitions of the abbreviated forms
    the context strip shows, which the pinned legend carries on this screen (run 11 item 12)."""
    from .graph_projection import count_words, distinct_labels
    from .io import unique_prefixes
    glyph = MAP_GLYPHS.get(rules, MAP_GLYPHS['ascii'])
    ellipsis = '…' if rules == 'unicode' else '...'
    focus = focus if map_node(graph, focus) is not None else graph['center']
    shorts = {kind: unique_prefixes([node['id'] for node in graph['nodes'] if node['kind'] == kind])
              for kind in ('group', 'filter')}
    cuts = distinct_labels(graph, MAP_DISTINCT_WIDTH, ellipsis)
    notes = _filter_notes(graph, shorts)
    noted = set()
    nodes = {node['ref']: node for node in graph['nodes']}
    # The revision is not drawn: it changes with every state, and a state change must change the mark and the word only.
    header = '[MAP] one hop | ' + count_words(graph)
    if graph.get('excluded'):
        header += ' | %s without a target not drawn' % _count(graph['excluded'], 'edge', 'edges')
    lines = word_wrap(header, width)
    if MAP_WIDTH > width:
        start = max(0, min(hscroll, MAP_WIDTH - width))
        lines += word_wrap('Left/Right pan: showing %d-%d of %d, states at %d.' % (
            1 if start == 0 else start + MAP_GUTTER + 1, start + width, MAP_WIDTH, MAP_STATE_COLUMN + 1), width)
    center = nodes[graph['center']]
    marks = lambda ref: ('>' if ref == focus else ' ') + ('*' if ref == graph['center'] and selected == center['id'] else ' ') + ' '
    lines.append(_map_row(_map_cell(marks(center['ref']), center, _map_label(center, shorts, prefixes),
                                    MAP_STATE_COLUMN - 3 - 5, ellipsis, rules), focus == center['ref']))
    layers = _drawn_layers(graph)
    for layer_number, (heading, edges, cut) in enumerate(layers):
        final_layer = layer_number == len(layers) - 1
        every = [edge for edge in graph['edges'] if edge['layer'] == heading]
        lines.append(_map_row('   ' + glyph['last' if final_layer else 'branch'] + heading + '  ' + _layer_evidence(every)))
        guide = '   ' if final_layer else glyph['guide']
        for index, edge in enumerate(edges):
            node = nodes[edge['target']]
            last = index == len(edges) - 1 and not cut
            label = RELATION_LABELS.get(edge['type'], edge['type'].replace('_', ' '))
            prefix = (marks(edge['target']) + guide + glyph['last' if last else 'branch']
                      + pad(fit(label, MAP_RELATION_WIDTH, ellipsis), MAP_RELATION_WIDTH) + glyph['arrow'])
            if node['kind'] in MAP_DISTINCT_KINDS:
                words = MAP_KIND_WORDS.get(node['kind'], node['kind'])
                shown = ('%s ' % words if words != label else '') + (
                    _repository_path_label(node['id'], MAP_DISTINCT_WIDTH, ellipsis) if node['kind'] == 'repository'
                    else cuts[node['ref']])
            else:
                shown = _map_label(node, shorts, prefixes)
            lines.append(_map_row(_map_cell(prefix, node, shown, MAP_STATE_COLUMN - cell_width(prefix) - 5, ellipsis, rules),
                                  focus == edge['target']))
            if edge['target'] in notes and edge['target'] not in noted:
                noted.add(edge['target'])
                # The rail of the layer and of the branch carries on past the node's row, so the note stays attached to it.
                lines.append(_map_row('   ' + guide + ('   ' if last else glyph['guide']) + ' ' * (MAP_RELATION_WIDTH + cell_width(glyph['arrow']))
                                      + '    ' + '(' + notes[edge['target']] + ')'))
        if cut:
            lines.append(_map_row('   ' + guide + glyph['last'] + '%d more not drawn; the tree below lists them' % cut))
    lines.extend(PinnedRow(row) for row in _map_legend(width, rules))
    lines.extend(PinnedRow(row) for row in strip_key_rows(strip_key, width))
    identity, detail = _focus_lines(graph, nodes[focus], width)
    return lines + identity + detail


# The workflow map (requirement 17 UX-VIS, PKG-UXVIS-5): one policy's change path, one lane per stage in the projection's
# order. Every lane is the same fixed-width cell (the focus and position marks, the spine, the state mark, the stage's
# label and the state word padded to one width), so a state change changes the mark and the word and never a coordinate;
# the reconcile branch hangs inside readback as a side lane. Only the lanes and the legend are geometry: the focused
# stage's detail below them is prose, and its length follows the records.
WORKFLOW_MIN_SIZE = (60, 20)
WORKFLOW_COMMAND = 'intune-iac workbench workflow --root ROOT --policy ID'
WORKFLOW_NEEDS = 'The workflow map needs a larger window (at least %dx%d); %s prints it as plain text.' % (
    WORKFLOW_MIN_SIZE + (WORKFLOW_COMMAND,))
WORKFLOW_LABELS = {'observe': 'observe', 'adopt': 'adopt', 'intent': 'intent', 'propose': 'propose', 'review': 'review',
                   'approve_execute': 'approve, execute', 'readback': 'readback', 'reconcile': 'reconcile',
                   'record': 'record', 'observed_after': 'observed after', 'maintain': 'maintain'}
# One mark per state of the projection; a state it does not name reads unknown here, never a state it was not given.
WORKFLOW_MARKS = {'done': 'x', 'current': '+', 'waiting': ':', 'blocked': '!', 'refused': '#', 'unknown': '?',
                  'not_recorded': '_', 'not_applicable': '-'}
WORKFLOW_LABEL_WIDTH = 16
WORKFLOW_WORD_WIDTH = 14          # the widest state word, "not applicable"
WORKFLOW_BRANCH_INDENT = 3
WORKFLOW_DETAIL_LABEL = 9
# Where Enter goes from a stage, as the keys name the surfaces.
WORKFLOW_SURFACES = {'2': '2 Inspector', '3': '3 Relationships', '5': '5 Plan', '7': '7 Coverage', '9': '9 Repository',
                     'v': 'v Delivery'}
WORKFLOW_FACT_WORDS = (
    ('run_id', 'run'), ('observed_at', 'observed'), ('coverage', 'coverage'), ('freshness', 'freshness'),
    ('proposal_check', 'proposal check'), ('recorded_at', 'recorded'), ('stack', 'stack'), ('component', 'component'), ('source_revision', 'revision'),
    ('repository_intent_id', 'cited intent'), ('intent_freshness', 'intent'), ('intent_id', 'intent'),
    ('field_changes', 'field changes'), ('opens_at', 'approval window opened'), ('closes_at', 'approval window closes'),
    ('closed_at', 'approval window closed'), ('classification', 'readback'), ('second_plan', 'second plan'),
    ('mismatch_count', 'mismatches'), ('previous_status', 'after'), ('count', 'reconciliations'),
    ('journal_status', 'journal'), ('service_revision', 'service revision'), ('before_revision', 'before revision'),
    ('baseline_admissible', 'baseline admissible'), ('context_changed', 'context changed'))


def workflow_fits(size):
    """Whether a window of `size` (columns, rows) has room for the workflow map; below it the layer says there is none."""
    return size[0] >= WORKFLOW_MIN_SIZE[0] and size[1] >= WORKFLOW_MIN_SIZE[1]


def workflow_unavailable_lines(width):
    """What the workflow layer says where there is no map: that it needs a larger window, and the plain-text command."""
    return word_wrap(WORKFLOW_NEEDS + ' Esc closes it; nothing else here has changed.', width)


def workflow_legends():
    """The legend's forms, widest first, each one row: the marks in words, then the keys only, so the width picks the form
    and a state never does."""
    keys = '> focus @ position'
    marks = ' '.join('[%s] %s' % (mark, state.replace('_', ' ')) for state, mark in WORKFLOW_MARKS.items())
    return ('%s | %s' % (marks, keys), 'marks: ? help | %s' % keys, keys)


def _workflow_state(value):
    """(mark, word) of a projection state: a state the map does not know reads unknown, never a state."""
    state = value if value in WORKFLOW_MARKS else 'unknown'
    return WORKFLOW_MARKS[state], state.replace('_', ' ')


def _workflow_fact(name, value):
    if name in ('observed_at', 'recorded_at'):
        return readable_time(value) or str(value)
    if name in ('opens_at', 'closes_at', 'closed_at'):
        return str(_readable_epoch(value))
    if name in ('repository_intent_id', 'intent_id', 'source_revision'):
        return short_id(value)
    return ('yes' if value else 'no') if isinstance(value, bool) else str(value)


def workflow_fact_words(stage):
    """The recorded values a stage carries, in words and in a fixed order, as one list of `what value` parts."""
    facts = stage.get('facts') if isinstance(stage.get('facts'), dict) else {}
    known = [name for name, _ in WORKFLOW_FACT_WORDS]
    words = dict(WORKFLOW_FACT_WORDS)
    # A fact's name and value are record text: each part is escaped here, before it is joined or wrapped.
    return [safe_text('%s %s' % (words.get(name, name.replace('_', ' ')), _workflow_fact(name, facts[name])))
            for name in known + sorted(set(facts) - set(known)) if name in facts]


def _workflow_header(flow, width, prefixes=None):
    """The title row: the policy's name, identity and evidence words, each escaped before it is joined and wrapped."""
    name = flow.get('name') if isinstance(flow.get('name'), str) and flow['name'] else None
    return word_wrap('[WORKFLOW] %s (%s) | %s' % (
        safe_text(name) if name else '(no name)', safe_text(short_id(flow.get('object_id'), prefixes)),
        safe_text(evidence_words(flow.get('evidence_class')))), width)


def _workflow_step_parts(step):
    """A step's parts: the trusted COMMAND_BREAKs split first, so a command stays on its own rows, then each part is
    escaped on its own, so record text inside a part cannot act on a terminal or forge a row."""
    return [safe_text(part) for part in str(step).split(COMMAND_BREAK)]


def workflow_stage_label(stage):
    return WORKFLOW_LABELS.get(stage.get('id'), safe_text(str(stage.get('id')).replace('_', ' ')))


def _workflow_route(flow, stage):
    opens = stage.get('opens')
    if opens:
        return 'Enter opens ' + WORKFLOW_SURFACES.get(opens, safe_text(str(opens)))
    return 'Enter opens nothing' + (': no operation is recorded' if not flow.get('operation') else '')


def workflow_detail_rows(flow, stage, width):
    """The focused stage in words, in reading order: the identity row (state, reason, where Enter goes), its basis, the
    recorded values and the step the existing screens give. The identity row and the first rows of the step are
    PinnedRows, which the pane keeps in view when the map is taller than it; the rest scrolls."""
    _, word = _workflow_state(stage.get('state'))
    reason = stage.get('reason')
    parts = ['FOCUS ' + workflow_stage_label(stage), word,
             'reason ' + safe_text(str(reason)) if reason else 'no reason recorded', _workflow_route(flow, stage)]
    rows = [PinnedRow(row) for row in _pack(parts, width)]
    rows += _labelled('basis', safe_text(str(stage.get('basis'))), width, WORKFLOW_DETAIL_LABEL)
    facts = workflow_fact_words(stage)
    if facts:
        rows += _labelled('recorded', '; '.join(facts), width, WORKFLOW_DETAIL_LABEL)
    step = stage.get('continuation')
    if isinstance(step, str) and step:
        # A step that prints commands writes each on its own row after the sentence, as every screen does.
        first, *commands = _workflow_step_parts(step)
        head = _labelled('next', first, width, WORKFLOW_DETAIL_LABEL)
        rows += [PinnedRow(row) for row in head[:2]] + head[2:]
        rows += [row for part in commands for row in _labelled('', part, width, WORKFLOW_DETAIL_LABEL)]
    return rows


def workflow_text_legend(width):
    """The marks in words, packed into as few rows as fit, for the plain-text form: no key, no focus."""
    items = ['[%s] %s' % (mark, state.replace('_', ' ')) for state, mark in WORKFLOW_MARKS.items()] + ['@ position']
    return _pack(items, width)


def workflow_map_lines(flow, width, rules='ascii', focus=None, prefixes=None, detail=True, keyboard=True):
    """The workflow map of one policy, then its legend and the focused stage's rows, for a pane `width` cells wide.

    One lane per stage, in the projection's order. The rows of the lanes are MapLines (geometry: the pane never wraps
    them); the header is ordinary text; the legend, the focused stage's identity and the head of its step are
    PinnedRows, which the pane keeps in view when the map is taller than it. focus: a stage id (default: the position,
    else the first stage). detail=False leaves the focused stage's rows out (the plain-text form lists every stage).
    keyboard=False is the plain-text form: nothing is focused, and the legend names the marks in words, not a key."""
    glyph = MAP_GLYPHS.get(rules, MAP_GLYPHS['ascii'])
    stages = [stage for stage in flow.get('stages') or [] if isinstance(stage, dict)]
    ids = [stage.get('id') for stage in stages]
    position = flow.get('position')
    focus = focus if focus in ids else position if position in ids else (ids[0] if ids else None)
    lines = _workflow_header(flow, width, prefixes)
    for index, stage in enumerate(stages):
        branch = bool(stage.get('branch_of'))
        last = index == len(stages) - 1
        spine = (glyph['guide'] if branch else '') + glyph['last' if last or branch else 'branch']
        mark, word = _workflow_state(stage.get('state'))
        room = WORKFLOW_LABEL_WIDTH - (WORKFLOW_BRANCH_INDENT if branch else 0)
        gutter = ('>' if keyboard and stage.get('id') == focus else ' ') + ('@' if stage.get('id') == position else ' ') + ' '
        lines.append(_map_row('%s%s[%s] %s %s' % (gutter, spine, mark, pad(workflow_stage_label(stage), room),
                                                  pad(word, WORKFLOW_WORD_WIDTH)), keyboard and stage.get('id') == focus))
    if keyboard:
        forms = workflow_legends()
        lines.append(PinnedRow(next((form for form in forms if cell_width(form) <= width), forms[-1])))
    else:
        lines += workflow_text_legend(width)
    chosen = next((stage for stage in stages if stage.get('id') == focus), None)
    if detail and chosen is not None:
        lines += workflow_detail_rows(flow, chosen, width)
    return lines


WORKFLOW_LANE_WIDTH = 3 + 3 + 4 + WORKFLOW_LABEL_WIDTH + 1 + WORKFLOW_WORD_WIDTH        # gutter, spine, mark, label, word
WORKFLOW_READ_ONLY_STATEMENT = 'This view is read-only: it reads the recorded state of the policy and writes nothing.'


def workflow_text_lines(flow, width, rules='ascii', prefixes=None):
    """The plain-text form of the workflow map (`intune-iac workbench workflow`): the lanes and the legend where the width
    holds them, the position, then every stage as a block with its state, reason, basis, recorded values and step. The
    keyboard reaches one stage's detail at a time; this lists all of them, so no stage's step is left out of a pipe."""
    stages = [stage for stage in flow.get('stages') or [] if isinstance(stage, dict)]
    if width >= WORKFLOW_LANE_WIDTH:
        # The pane pads each lane to its width; a pipe has no use for that padding.
        lines = [str(row).rstrip() for row in workflow_map_lines(flow, width, rules, prefixes=prefixes, detail=False,
                                                                 keyboard=False)]
    else:
        lines = _workflow_header(flow, width, prefixes)
    here = next((stage for stage in stages if stage.get('id') == flow.get('position')), None)
    lines += [''] + word_wrap('Position: %s (the last stage with a recorded state; @ marks it in the map).' % (
        workflow_stage_label(here) if here else 'none recorded'), width)
    lines += ['', 'STAGES']
    for number, stage in enumerate(stages, 1):
        _, word = _workflow_state(stage.get('state'))
        reason = stage.get('reason')
        lines += word_wrap('%d %s: %s | %s' % (number, workflow_stage_label(stage), word,
                                               'reason ' + safe_text(str(reason)) if reason else 'no reason recorded'), width)
        lines += _labelled('  basis', safe_text(str(stage.get('basis'))), width, 11)
        facts = workflow_fact_words(stage)
        if facts:
            lines += _labelled('  recorded', '; '.join(facts), width, 11)
        step = stage.get('continuation')
        if isinstance(step, str) and step:
            for index, part in enumerate(_workflow_step_parts(step)):
                lines += _labelled('  next' if index == 0 else '', part, width, 11)
    # Said once, on the last rows, because a small terminal shows the end of the output and not its start.
    return lines + [''] + word_wrap(WORKFLOW_READ_ONLY_STATEMENT, width)


def history_lines(value, width, current=None):
    """Observations newest first, each with what changed since the one before it on this page.

    current: the run and time of the observation the store treats as current (from the last read of the policy);
    its row is marked, and a row stamped later than it is marked as not current.
    """
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
        lines += word_wrap('Newest first by observation time (a capture stamped ahead of this host\'s clock sorts above '
                           'later collections; the current observation is marked); n shows older observations, p '
                           'shows newer observations.', width)
    lines += word_wrap('Observation time is when collection saw the configuration; it does not establish who changed it or when.', width)
    for index, item in enumerate(items):
        lines.append('')
        mark = ''
        if isinstance(current, dict) and current.get('run_id') is not None:
            if item.get('run_id') == current.get('run_id'):
                mark = ' | current'
            elif str(item.get('observed_at') or '') > str(current.get('observed_at') or ''):
                mark = ' | not current: stamped later than the current observation'
        lines += word_wrap('%s | run %s | %s | snapshot %s%s' % (
            _when(item.get('observed_at'), 'unknown'), item.get('run_id', 'unknown'), item.get('coverage', 'unknown'),
            str(item.get('snapshot_id', 'unknown'))[:12], mark), width)
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
        lines += word_wrap('  %s (%s):' % (heading, _when(previous.get('observed_at'), 'unknown')), width)
        lines += ['  ' + line for line in change_lines(changes, width - 2, 'BEFORE (previous)', 'AFTER (this observation)')]
    if not items:
        lines.append('No observations on this page.')
    return lines


CELLS = (('#', 'success'), ('x', 'failure'), ('~', 'pending'), ('?', 'reported unknown'), ('.', 'no fresh report'))
MAX_CELLS = 400
NOT_COUNTED = ('missing', 'stale', 'age_unknown', 'partial', 'access_denied', 'future', 'membership_conflicts',
               'conflicting')


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
    if len(cells) <= row:
        lines = ['    [' + cells + ']']
    else:
        # Wrapped rows say which devices (or cells) they hold, so a second row never reads as a second bar.
        unit = 'devices' if per == 1 else 'cells'
        size = len('%s %d-%d ' % (unit, len(cells), len(cells)))
        row = max(1, min(50, width - 6 - size))
        lines = ['    %s[%s]' % (pad('%s %d-%d' % (unit, start + 1, min(start + row, len(cells))), size),
                                 cells[start:start + row]) for start in range(0, len(cells), row)]
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
            evidence_words(health.get('evidence_class')), _when(health.get('as_of')), health.get('cohort_version'),
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
            lines += word_wrap('%s %s | run %s | %s | error %s' % (label, _when(run.get('completed_at') or run.get('started_at')),
                               run.get('run_id'), _as_words(run.get('status')), run.get('error_code') or 'none'), width)
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
        lines.append('%s %s (%s; latest %s)' % (short_id(operation), _as_words(latest.get('status')), _plural(len(records), 'journal record'), _when(latest.get('recorded_at'))))
    return lines


def _plural(count, noun):
    return '%d %s%s' % (count, noun, '' if count == 1 else 's')


# A held observation in the maintenance queue's words (the Inspector and the band word the same two holds).
QUEUE_HOLD_WORDS = {'clock_moved_backward': 'host clock behind a recorded time',
                    'clock_floor_invalid': 'the recorded time cannot be read'}


def queue_lines(value, width, selected=None):
    """Findings as work: what, why, state, ownership, dates, compatibility, evidence and related proposals.

    The review commands act on the selected policy, so a finding of any other policy puts `select` first."""
    lines = ['[MAINTENANCE QUEUE]']
    findings = [item for item in value.get('findings') or [] if isinstance(item, dict)]
    page = value.get('pagination') if isinstance(value.get('pagination'), dict) else {}
    total = page.get('total_objects')
    lines += word_wrap('%s | %s in scope | no automatic remediation' % (
        _plural(len(findings), 'finding'), _plural(total, 'object') if type(total) is int else 'unknown objects'), width)
    if not findings:
        lines.append('No findings for the observations in scope.')
    # What each object's findings already said, so the details of one object are not repeated under every finding.
    said = {}
    for item in findings:
        lines.append('')
        lines += word_wrap('%s  %s  %s' % (item.get('priority', 'unknown'), _words_with_code(item.get('finding', 'unknown')),
                                           item.get('object_id', 'unknown')), width)
        lines += word_wrap('  Why: ' + str(item.get('priority_rationale') or 'not recorded'), width)
        evidence = item.get('evidence') if isinstance(item.get('evidence'), dict) else {}
        hold = clock_hold(evidence.get('freshness_reasons'))
        # Unknown stays unknown: a clock hold means the age is not established, so the finding does not say stale.
        freshness = ('age unknown (%s)' % QUEUE_HOLD_WORDS[hold] if hold else item.get('freshness', 'unknown'))
        # (name, lines, whether it belongs to the object, not to this finding)
        blocks = [('state', word_wrap('  State %s | owner %s | freshness %s | automatic remediation %s' % (
            _words_with_code(item.get('action_state', 'unknown')), item.get('owner_assertion', 'unknown'), freshness,
            'yes' if item.get('automatic_remediation') is True else 'no'), width), True)]
        if hold and item.get('finding') == 'observation_stale':
            blocks.append(('hold', word_wrap('  Next: ' + with_clock_times(CLOCK_HOLD_STEPS[hold], evidence.get('freshness_clock')), width), False))
        writer = item.get('writer_ownership') if isinstance(item.get('writer_ownership'), dict) else {}
        claim = item.get('source_owner_claim') if isinstance(item.get('source_owner_claim'), dict) else {}
        if writer or 'owner_role' in item:
            blocks.append(('owner', word_wrap('  Owner role %s: %s | writer %s%s | source owner claim %s' % (
                str(item.get('owner_role', 'unknown')).replace('_', ' '), item.get('owner') or 'none recorded',
                writer.get('status', 'unknown'), ': ' + _code_words(writer['reason']) if writer.get('reason') else '',
                _value(claim['value']) if claim.get('value') is not None else 'none recorded'), width), True))
        review = item.get('review_record') if isinstance(item.get('review_record'), dict) else {}
        state = str(review['reason']).replace('_', ' ') if review.get('reason') else 'review ' + str(review.get('status', 'not recorded'))
        blocks.append(('review', word_wrap('  %s | review due %s | exception expiry %s' % (
            state[:1].upper() + state[1:], item.get('review_due') or 'none', item.get('exception_expiry') or 'none'), width), True))
        # The route to record or amend a review, with the exact prior it must name; it names this finding.
        prior = review.get('artifact_id') if review.get('status') == 'recorded' and review.get('artifact_id') else 'none'
        # Each command stands on its own row, after the sentence, so a copied row carries no words (run 9, frame 47).
        # The commands act on the selected policy: another policy's finding is selected first (review 20).
        other = item.get('object_id') != selected
        blocks.append(('route', word_wrap("  This finding's review: " + (
            'this policy is not the selected one, so select it with the first command, write the form with the second, '
            'then record it with the third' if other else
            'write the form with the first command, then record it with the second')
                                          + ' (an annotation, never approval). The last word of the %s command is the '
                                          'earlier review it replaces' % ('third' if other else 'second') + (
                                              '; none means this finding has no earlier review to replace.' if prior == 'none'
                                              else '.'), width)
                       + (word_wrap('    :select %s' % item.get('object_id'), width) if other else [])
                       + word_wrap('    :queue-review-template %s NEW_JSON' % item.get('finding'), width)
                       + word_wrap('    :queue-amend FILE %s' % prior, width), False))
        compatibility = item.get('compatibility') if isinstance(item.get('compatibility'), dict) else None
        if compatibility:
            blocks.append(('compatibility', word_wrap('  Compatibility %s | native provider %squalified' % (
                _words_with_code(compatibility.get('profile', 'unknown')),
                '' if compatibility.get('native_provider_qualified') is True else 'not '), width), True))
        evidence = item.get('evidence') if isinstance(item.get('evidence'), dict) else None
        if evidence:
            blocks.append(('evidence', word_wrap('  Evidence %s | observed %s | snapshot %s' % (
                evidence.get('evidence_class', 'unknown'), _when(evidence.get('observed_at'), 'unknown'), str(evidence.get('snapshot_id', 'unknown'))[:12]), width), True))
        proposals = _proposals(item.get('related_proposals'))
        related = word_wrap('  Related operations ' + ('(%d)' % len(proposals) if proposals else 'none'), width)
        for text in proposals:
            related += word_wrap('    ' + text, width)
        blocks.append(('related', related, True))
        before = said.setdefault(item.get('object_id'), {})
        repeated = [name for name, text, owned in blocks if owned and before.get(name) == text]
        if repeated:
            lines += word_wrap('  Same object details as the finding above (%s).' % ', '.join(repeated), width)
        for name, text, owned in blocks:
            if owned:
                before[name] = text
            if name not in repeated:
                lines += text
    return lines


STAGE_LABELS = {'proposal': 'Proposal', 'review': 'Review', 'approval': 'Approval', 'execution': 'Execution',
                'readback': 'Readback', 'reconciliation': 'Reconciliation', 'deployment_record': 'Deployment',
                'observed_after': 'Observed after'}
# The marker repeats the stage's state; the words after it always say it too.
MARKS = {'done': 'x', 'matches_desired': 'x', 'waiting': ' ', 'not_yet': ' ', 'not_started': ' ', 'available': ' ',
         'not_needed': '-', 'not_applicable': '-', 'unknown': '?', 'required': '?', 'pending': '?', 'not_open': '?',
         'not_recorded': '?', 'failed': '!', 'expired': '!', 'rejected': '!', 'not_available': '~', 'differs': '!',
         'clock_uncertain': '?', 'clock_unreadable': '!'}
# The approval window as execute judges it (maintenance.approval_window); the Plan review shows these words.
WINDOW_WORDS = {'open': 'open', 'closed': 'closed',
                'closed_recorded': 'closed (recorded; a clock that reads earlier does not reopen it)',
                'clock_moved_backward': "held: this host's clock reads earlier than a time this operation recorded",
                'unknown': "unknown: this operation's recorded time cannot be read"}
# The legend names states without the alert phrases, so only its markers are tinted, never its words.
MARK_LEGEND = ('[x] done  [ ] waiting or not yet  [-] not needed  [?] unknown or required  [~] not available yet  '
               '[!] stopped: failure, expiry or refusal')


def _code_words(code):
    """A recorded code inside a sentence: its words, the code kept in parentheses as the lookup key."""
    if code in EXECUTION_ERROR_WORDS:
        return '%s (%s)' % (EXECUTION_ERROR_WORDS[code], code)
    return '%s (%s)' % (_as_words(code), code)


def _approval_text(stage, status):
    if status == 'done':
        return 'exact review digest %s supplied at dispatch | window %s to %s' % (
            str(stage.get('approval_digest'))[:12], _readable_epoch(stage.get('opens_at')), _readable_epoch(stage.get('closes_at')))
    if status == 'waiting':
        return 'waiting for the exact review digest until %s' % _readable_epoch(stage.get('closes_at'))
    if status == 'expired':
        return 'expired: the approval window closed at %s%s' % (
            _readable_epoch(stage.get('closes_at')),
            ' (recorded; a clock that reads earlier does not reopen it)' if stage.get('recorded') else '')
    if status == 'clock_uncertain':
        return ("held: this host's clock reads earlier than a time this operation recorded, so execute holds it; "
                'the window closes at %s' % _readable_epoch(stage.get('closes_at')))
    if status == 'clock_unreadable':
        return "unknown: this operation's recorded time cannot be read, so execute refuses it"
    if status == 'not_open':
        return 'not open: the local clock reads before %s' % _readable_epoch(stage.get('opens_at'))
    return str(status).replace('_', ' ')


def _execution_text(stage, status):
    if status == 'not_started':
        return 'not started'
    parts = ['engine ' + _as_words(stage.get('engine_status'))]
    if stage.get('service_status') is not None:
        parts.append('service ' + str(stage['service_status']))
    elif stage.get('no_change_dispatch'):
        parts.append('no service change dispatched')
    if stage.get('recorded_at'):
        parts.append('recorded ' + _when(stage['recorded_at']))
    if status == 'unknown':
        # Who claims what: the engine's own report is in the journal; the store never registered a verified result.
        claim = ('the engine reported %s, but the store never recorded a verified result' % _as_words(stage['engine_status'])
                 if stage.get('engine_status') else 'no engine result recorded')
        said = ([_code_words(stage['error_code'])] if stage.get('error_code') else []) + [claim] + parts[1:]
        return 'outcome unknown: ' + ' | '.join(said)
    return ' | '.join(parts)


def _receipt_text(stage, status):
    if status in ('not_started', 'not_needed'):
        return status.replace('_', ' ')
    if status == 'not_recorded':
        return 'not recorded: execution ended before its own independent readback'
    if status == 'required':
        return 'required: the outcome is unknown; reconcile before any retry'
    parts = [_as_words(stage.get('classification'))]
    if stage.get('stage') == 'readback':
        count = stage.get('mismatch_count') or 0
        parts += ['second plan ' + _as_words(stage.get('second_plan')), 'visibility ' + ('pending' if stage.get('visibility_pending') else 'settled'),
                  '%d mismatch%s' % (count, '' if count == 1 else 'es')]
    else:
        parts = ["reconcile's readback: " + _as_words(stage.get('classification')),
                 'after ' + _as_words(stage.get('previous_status'))]
        if (stage.get('count') or 1) > 1:
            parts.append('%d reconciliations' % stage['count'])
        if stage.get('recorded_at'):
            parts.append('recorded ' + _when(stage['recorded_at']))
    return ' | '.join(parts)


def _record_text(stage, status):
    if status == 'done':
        admitted = ('context file changed since; no longer admitted as a baseline' if stage.get('context_changed') else
                    'baseline admissible' if stage.get('baseline_admissible') else 'not a baseline')
        # The record's own id, as the notice and the panel print it, so the stage and the notice can be matched.
        named = ' | record %s' % str(stage['artifact_id'])[:12] if stage.get('artifact_id') else ''
        return 'recorded %s%s | intent %s | %s | %s' % (_when(stage.get('recorded_at')), named, short_id(stage.get('intent_id')),
                                                        _as_words(stage.get('evidence_class')), admitted)
    if status == 'available':
        return 'available for intent %s; deployment-record performs the full check' % short_id(stage.get('intent_id'))
    if status in ('not_available', 'not_applicable'):
        return '%s: %s' % (status.replace('_', ' '), str(stage.get('reason', 'see exact evidence')).replace('_', ' '))
    return 'not yet'


def _observed_text(stage, status):
    revision = 'service revision %s' % stage.get('service_revision')
    if status == 'matches_desired':
        return 'matches desired at %s (%s before the change) | observed %s' % (revision, stage.get('before_revision'), _when(stage.get('observed_at')))
    if status == 'differs':
        return 'differs from the desired configuration at %s | observed %s' % (revision, _when(stage.get('observed_at')))
    if status == 'not_yet':
        return 'not yet: no observation after the change' + (' (latest at %s)' % revision if stage.get('service_revision') is not None else '')
    if status == 'not_applicable':
        return 'not applicable: no configuration change was dispatched'
    return 'unknown: ' + str(stage.get('reason', 'see exact evidence')).replace('_', ' ')


def _stage_text(stage):
    name, status = stage.get('stage'), stage.get('status')
    if name == 'proposal':
        cited = stage.get('repository_intent_id')
        if stage.get('context_changed'):
            return 'recorded %s | context changed since this proposal was prepared; its citation is unknown' % (
                _when(stage.get('recorded_at')))
        return 'recorded %s | %s' % (_when(stage.get('recorded_at')),
                                     'repository intent %s (%s)' % (short_id(cited), stage.get('intent_freshness')) if cited
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
                'uncertain': 'outcome unknown', 'reconciled': 'reconciled', 'approval_refused': 'approval refused'}


# Refused approvals in the journal history, in words (the code stays beside them).
APPROVAL_REFUSED_WORDS = {'expired_request': 'the approval window had closed',
                          'clock_moved_backward': "this host's clock read earlier than a recorded time",
                          'approval_digest_mismatch': 'the digest did not match the review'}


def _event_text(event, readback_above=False):
    """What one journal event recorded, from its own fields. readback_above: the reconcile stage shown above already
    says this reconciliation's readback, so the history row does not say it again."""
    fields = event.get('fields') if isinstance(event.get('fields'), dict) else {}
    kind = event.get('kind')
    if kind == 'prepared':
        return 'approval will need digest ' + str(fields.get('approval_digest'))[:12]
    if kind == 'dispatch_started':
        return 'approved with digest ' + str(fields.get('approval_digest'))[:12]
    if kind == 'engine_result':
        result = fields.get('result') if isinstance(fields.get('result'), dict) else {}
        return 'engine reported %s (%s)' % (_as_words(result.get('status')), _as_words(result.get('assurance')))
    if kind == 'service_response':
        response = fields.get('response') if isinstance(fields.get('response'), dict) else {}
        return 'service answered status %s' % response.get('status')
    if kind == 'service_no_change':
        return 'the plan had no configuration change'
    if kind == 'verified':
        return 'readback observed the desired state | readback sha256 ' + str(fields.get('readback_sha256'))[:12]
    if kind == 'uncertain':
        return _code_words(fields['error_code']) if fields.get('error_code') else 'no error recorded'
    if kind == 'reconciled':
        if readback_above:
            return 'read the service again, after %s (its readback is in the reconciliation stage above)' % _as_words(
                fields.get('previous_status'))
        return "reconcile's readback: %s, after %s" % (_as_words(fields.get('classification')),
                                                      _as_words(fields.get('previous_status')))
    if kind == 'approval_refused':
        code = fields.get('code')
        return '%s; nothing was dispatched' % ('%s (%s)' % (APPROVAL_REFUSED_WORDS[code], code)
                                               if code in APPROVAL_REFUSED_WORDS else code)
    return 'r shows what it recorded'


def history_event_lines(history, width, readback_above=False):
    """The operation's journal events in order; a time only where the store's registration pairs with an event.

    readback_above: the reconciliation stage is shown above, so the latest reconciliation's row points to it instead of
    saying its readback a second time."""
    events = [event for event in (history or {}).get('events') or [] if isinstance(event, dict)]
    if not events:
        return []
    last = max((event.get('sequence') for event in events if event.get('kind') == 'reconciled'), default=None)
    lines = word_wrap('HISTORY  journal events in order (chain verified); a time is when the store registered the '
                      'journal after that event', width)
    for event in events:
        label = EVENT_LABELS.get(event.get('kind'), str(event.get('kind')).replace('_', ' '))
        at = _when(event.get('store_recorded_at'))  # to the second with its zone; the raw record keeps the fraction
        head = '  %-3s %-17s %-24s ' % (event.get('sequence'), label, at)
        text = _event_text(event, readback_above and event.get('sequence') == last)
        if width >= 90:
            lines += _labelled(head, text, width, len(head))
        else:
            lines += word_wrap(head.rstrip(), width) + word_wrap('      ' + text, width)
    unpaired = (history.get('registrations') or 0) - (history.get('paired') or 0)
    if unpaired > 0:
        lines += word_wrap('  %s could not be paired with an event; r shows %s.' % (
            _plural(unpaired, 'store registration'), 'it' if unpaired == 1 else 'them'), width)
    return lines


def delivery_lines(value, width, rules='ascii', band_has_next=False):
    """One operation's delivery stages in order, each with a marker, its state in words and its evidence.

    band_has_next: the hazard band carries the screen's Next, so the closing step keeps its explanation and commands
    without a second `Next:` label (run 12, frames 20 and 39).

    With box-drawing rules the stages hang from one connected spine, first to last; ASCII keeps the plain list.
    """
    lines = ['[DELIVERY]']
    lines += word_wrap('Operation %s | policy %s | journal %s' % (value.get('operation_id'), value.get('object_id'),
                                                                   _as_words(value.get('journal_status'))), width)
    stages = [stage for stage in value.get('stages') or [] if isinstance(stage, dict)]
    for number, stage in enumerate(stages, 1):
        last = number == len(stages)
        if rules == 'unicode':
            head = '──' if number == 1 and last else '┌─' if number == 1 else '└─' if last else '├─'
            cont = '  ' if last else '│ '
        else:
            head = cont = '  '
        # A recorded deployment whose bound context changed is no longer admitted, so it is not marked done.
        # A deployment that can never be recorded (its bound context changed) is stopped; one that is only not
        # available yet has its own marker.
        stopped = stage.get('context_changed') or (stage.get('status') == 'not_available' and stage.get('reason') == 'context_changed')
        mark = head + '[%s] ' % ('!' if stopped else MARKS.get(stage.get('status'), '?'))
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
    shown = {stage.get('stage'): stage for stage in stages}
    lines += history_event_lines(value.get('history') if isinstance(value.get('history'), dict) else {}, width,
                                 readback_above=shown.get('reconciliation', {}).get('status') == 'done')
    runs = [run for run in value.get('workflow_runs') or [] if isinstance(run, dict)]
    read = value.get('workflow_runs_read') if isinstance(value.get('workflow_runs_read'), dict) else {}
    if read.get('status') == 'unavailable':
        lines += word_wrap('CI workflow runs could not be read (%s); the stages above are unaffected.' % read.get('error_code'), width)
    elif runs:
        lines.append('CI WORKFLOW RUNS  (imported claims; not verified)')
        for run in runs:
            lines += word_wrap('  %s %s  claims %s | revision %s | observed %s | %s' % (
                run.get('workflow') or 'workflow', run.get('run_id'), run.get('status'), str(run.get('repository_revision'))[:12],
                _when(run.get('observed_at')), 'tied to this operation' if run.get('relation') == 'related_operation' else 'for the cited revision'), width)
            lines += word_wrap('     ' + str(run.get('run_url')), width)
    else:
        lines += word_wrap('CI workflow runs: none imported for this operation or its cited revision '
                           '(workflow-import records one; it stays an inert claim).', width)
    if read.get('status') == 'partial':
        lines += word_wrap('(only the first %s imported runs for this policy were read)' % read.get('records_read'), width)
    if read.get('cited_revision') == 'unknown':
        lines += word_wrap('(runs for the cited revision cannot be matched: the context file changed since the proposal)', width)
    lines += step_rows(value.get('next_action'), width, '' if band_has_next else 'Next: ')
    lines += word_wrap(MARK_LEGEND, width)
    # Not "Evidence": that label is the last line's, which names the two layers of evidence (e and r).
    lines += word_wrap('Evidence class %s | %s | no cloud authority' % (
        _as_words(value.get('evidence_class')), 'native-provider qualified' if value.get('native_provider_qualified') else 'not native-provider qualified'), width)
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


def repository_entry_lines(value, width, focus=0, staged=False):
    """The policies a repository holds, each with its state in this store; the focused one is marked.

    staged: a command is staged for review, so the shell-pins block is left out (it would push the screen's Next off the
    first page, run 16 N6) and the sentence that pointed at it says where the pins go instead."""
    lines = word_wrap('[REPOSITORY ENTRY] %s' % _path_words(value.get('repository')), width)
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
    from .io import unique_prefixes
    shown = unique_prefixes([str(candidate.get('object_id')) for candidate in value.get('candidates') or []
                             if isinstance(candidate, dict) and candidate.get('object_id')])
    for index, candidate in enumerate(value.get('candidates') or []):
        observed = candidate.get('observed') or {}
        short = short_id(str(candidate.get('object_id')), shown)
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
        explanation = str(candidate.get('explanation', ''))
        pinned = '--git-executable' in explanation and bool(candidate.get('command'))
        explanation = explanation.replace(
            'add --git-executable and --git-sha256 to the command to verify',
            'add --git-executable and --git-sha256 in a shell (the shell command shows when nothing is staged) to verify'
            if staged else 'add --git-executable and --git-sha256 to the shell command below to verify')
        if '--git-executable' in explanation:
            # The flags are named by the engine's explanation; what they are is said here, where they are shown (run 12).
            explanation += (' --git-executable is the path of the git program to run and --git-sha256 that program\'s SHA-256; '
                            'give both or neither.')
        lines += _labelled('', explanation, width, 5)
        if pinned and not staged:
            # The workspace's repository-import parses no pins, so the pinned form is a shell command (review 34).
            lines += _labelled('', 'The pins work only from a shell; the workspace repository-import cannot take them. '
                               'From a shell:', width, 5)
            lines += word_wrap('     %s --git-executable GIT_PATH --git-sha256 GIT_SHA256' % candidate['command'], width)
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


def recorded_lines(value, width, selected=None):
    """A record the store just accepted: what it is, whether it is new, and for a CI run what it claims."""
    kind = str(value.get('kind'))
    lines = word_wrap('[RECORDED] %s %s | %s | %s' % (
        RECORD_WORDS.get(kind, kind), str(value.get('artifact_id'))[:12],
        'new record' if value.get('created') else 'already recorded; nothing changed', _when(value.get('recorded_at'))), width)
    data = value.get('data') if isinstance(value.get('data'), dict) else {}
    if kind == 'repository_intent' and data:
        # What the refresh established (the previous intent kept), under the record's own heading.
        lines += refresh_result_lines(value, width, header=False)
    if kind == 'deployment_receipt':
        lines += word_wrap('v opens Delivery; its stage 7 shows this record.', width)
    if kind == 'queue_review' and data.get('finding') and data.get('object_id'):
        # The record's own facts (workbench_queue.amend): which finding and policy, and the way to read it back.
        lines += word_wrap('Review version %s of %s for policy %s: an annotation, never approval or execution.' % (
            data.get('version', 'unknown'), _as_words(data['finding']), short_id(str(data['object_id']))), width)
        lines += word_wrap('Next: In the workspace:', width)
        # queue-review reads the selected policy's review, so another policy is selected first (review 20).
        if data['object_id'] != selected:
            lines += word_wrap('  select %s' % data['object_id'], width)
        lines += word_wrap('  queue-review %s' % data['finding'], width)
    if kind == 'workflow_run' and data:
        links = ['linked to %s %s' % ('operation' if row.get('relation') == 'related_operation' else 'observation',
                                       str(row.get('target_id'))[:12])
                 for row in data.get('relationships') or [] if isinstance(row, dict)]
        lines += word_wrap('%s %s: %s | revision %s | observed %s | %s' % (
            data.get('workflow') or 'workflow', data.get('run_id'), data.get('status'),
            str(data.get('repository_revision'))[:12], _when(data.get('observed_at')), '; '.join(links) or 'no local links'), width)
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
        ', '.join(sorted({_as_words(row.get('live')) for row in value.get('families') or []})) or 'unknown'), width)
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
    'workbench_difference_changed': (
        'The repository changed after you reviewed its difference.',
        'Review the new difference (9), then Refresh the repository intent (a: actions).'),
    'maintenance_source_changed': (
        'A file it bound (its desired file or its context file) changed after it was prepared, so its review no longer '
        'describes what would run.',
        'Prepare a proposal from the recorded intent (a: actions); nothing from this one is used.'),
    'workbench_deployment_intent': (
        'The intent given is not exactly one repository intent recorded in this store.',
        "Use the intent this operation's plan cites: v opens Delivery, which names it, and a lists the record with it."),
    'workbench_deployment_identity': (
        'The operation was prepared from another store or tenant, or the intent is for another policy.',
        'Record the deployment in the store that prepared the operation, with the intent for the same policy '
        '(v opens Delivery, which names it).'),
    'workbench_deployment_intent_not_cited': (
        "The intent given is not the one this operation's plan cites.",
        'Record {operation} with the intent it cites (the cause above names it).'),
    'workbench_deployment_unverified': (
        "The operation was not verified by exactly one readback of its own, or the intent's desired policy is not "
        'the one this operation applied.',
        'Use the intent the operation cites (v opens Delivery, which names it). An operation whose own readback was never '
        'verified cannot be recorded; collect to observe the policy instead.'),
    'workbench_deployment_context_missing': (
        "The operation's plan bound no context, so it cites no repository intent.",
        'Only a proposal prepared from a repository intent (a: Prepare a proposal from the recorded intent) can '
        'become a deployment record.'),
    'workbench_deployment_context_mismatch': (
        'The context file the plan bound has changed since, or it does not cite this intent, scope or tenant.',
        'Use the intent the plan cites; if its context file changed, Prepare a proposal from the recorded intent '
        '(a: actions).'),
    'workbench_deployment_engine_receipt': (
        "The engine's receipt for this operation is missing, not verified, or not for this operation's request.",
        'v opens Delivery for the operation; a record needs the engine receipt the execution wrote.'),
    'workbench_deployment_readback': (
        'No single readback of this operation matches its verified event with the desired state observed, no '
        'pending visibility and a no-change second plan.',
        'Reconcile reads the service again (a lists it); a record needs the operation\'s own verified readback.'),
    'workbench_deployment_limit': (
        'The operation directory holds more readbacks than the record reads (100).',
        'Inspect the operation directory; nothing was recorded.'),
    'workbench_repository_intent_missing': (
        'No repository intent was recorded for this policy. Inspection, relationships, history, health and diagnostics '
        'work without one.',
        'To manage it from a repository: generate or adopt it with the wizard, copy the project into the repository '
        'you maintain and commit it, then run this command to list its policies and fill in the exact '
        'repository-import command for review (s shows what exists here):' + COMMAND_BREAK + '  :repository-entry REPOSITORY'),
    'selection_required': (
        'This view belongs to one policy, and none is selected.',
        'press 1 for Estate and Enter on a policy, then try again.'),
    'clock_moved_backward': (
        "This host's clock reads earlier than a time this operation already recorded, so whether its approval window is "
        'still open cannot be established. Nothing was dispatched.',
        'Correct the host clock, or wait until it reads at or after the recorded time, then submit again (restart the '
        'workbench after correcting the clock); Prepare a proposal from the recorded intent (a: actions) also works.'),
    'clock_floor_invalid': (
        'The time this operation recorded cannot be read, so its approval window cannot be judged. Nothing was '
        'dispatched.',
        'Prepare a proposal from the recorded intent (a: actions); this one stays refused.'),
    'clock_reading_invalid': (
        "This host's clock returned an unusable time, so the approval window cannot be judged. Nothing was "
        'dispatched.',
        'Correct the host clock and submit again, or Prepare a proposal from the recorded intent (a: actions).'),
    'clock_lock_unavailable': (
        'The recorded time cannot be locked on this host, so the approval window cannot be judged. Nothing was '
        'dispatched.',
        'Run the workbench on a supported Linux host, or Prepare a proposal from the recorded intent (a: actions) there.'),
    'expired_request': (
        'The plan\'s approval window has closed, or the local clock reads outside it.',
        'Prepare a proposal from the recorded intent (a: actions); v opens Delivery, which shows the window of {operation}.'),
    'maintenance_approval_required': (
        'The digest supplied does not match the reviewed plan.',
        'Review the plan (5) and approve with its exact review digest.'),
    'maintenance_replay_forbidden': (
        'This operation is no longer awaiting approval: it was already dispatched, or it was rejected. Execution is '
        'never replayed.',
        'Use reconcile for an uncertain outcome; v opens Delivery, which shows where {operation} stands.'),
    'maintenance_repository_stale': (
        'The repository changed after this proposal cited its intent, or its component no longer consumes exactly '
        'this policy.',
        'Press 9 to see which; fix the component if it no longer consumes the policy, then choose Refresh the repository '
        'intent (a: actions): it asks for the REVISION and pins the difference you reviewed. Then Prepare a proposal from '
        'the recorded intent (a: actions).'),
    'workbench_repository_stale': (
        'The repository changed since its recorded intent, or its component no longer consumes exactly this policy.',
        'Press 9 to see which; fix the component if it no longer consumes the policy, then choose Refresh the repository '
        'intent (a: actions): it asks for the REVISION and pins the difference you reviewed.'),
    'maintenance_observation_stale': (
        'The newest observation of this policy is not fresh, or the service changed after it was collected; a change '
        'is never prepared against it.',
        'Collect again, then Prepare a proposal from the recorded intent (both in a: actions); i shows the observation\'s freshness. If i says its '
        'age cannot be established (a clock hold), collecting again does not clear it: correct the host clock and '
        'restart the workbench.'),
    'maintenance_observation_incomplete': (
        'The newest observation of this policy is incomplete, or the last collection did not finish.',
        'Collect again (a: actions); i shows what was not read.'),
    'maintenance_plan_stale': (
        'The service changed while the plan was being prepared, or after it was prepared.',
        'Collect again, then Prepare a proposal from the recorded intent (both in a: actions).'),
    'unreadable_file': (
        'A file this command needs could not be read; the engine does not name it.',
        'Check that the files the command names exist and this account can read them, then submit it again.'),
    'workbench_desired_capability': (
        'The desired policy uses a setting definition, value, platform or technology outside the supported capability map.',
        "Change that setting in the repository's stack input to a supported value, then Refresh the repository "
        'intent and Prepare a proposal from the recorded intent (a: actions).'),
}


# The same codes as a restore meets them: restore-propose reads the original operation's bound files, so the wording is
# the restore's (title, cause, next). {original} is "operation" with its short id when the command named one.
RESTORE_REFUSALS = {
    'maintenance_source_changed': (
        'A file the original operation bound has changed',
        'A file the original {original} bound changed after it was prepared (its context file), so a restore cannot be '
        'derived from it.',
        "Prepare a proposal from the recorded intent (a: actions); that proposes the recorded intent's value, not the "
        "original's, and uses nothing from the original.")}

# A refusal's header in words; the code follows in parentheses as the lookup key. A code with no entry here (one the
# engine raises that this screen does not explain) reads as its own words.
REFUSAL_TITLES = {
    'workbench_difference_changed': 'The repository changed after its difference was reviewed',
    'maintenance_source_changed': 'A file the proposal bound has changed',
    'workbench_deployment_intent': 'The intent given is not recorded in this store',
    'workbench_deployment_identity': 'The operation and the intent do not belong together',
    'workbench_deployment_intent_not_cited': 'The intent given is not the one the plan cites',
    'workbench_deployment_unverified': 'The operation was not verified by a readback of its own',
    'workbench_deployment_context_missing': 'The plan cites no repository intent',
    'workbench_deployment_context_mismatch': 'The plan context file changed or does not match',
    'workbench_deployment_engine_receipt': 'The engine receipt is missing or not verified',
    'workbench_deployment_readback': 'No single readback matches the operation',
    'workbench_deployment_limit': 'The operation holds too many readbacks to read',
    'workbench_repository_intent_missing': 'No repository intent is recorded for this policy',
    'selection_required': 'No policy is selected',
    'clock_moved_backward': "This host's clock reads earlier than a recorded time",
    'clock_floor_invalid': 'The recorded time cannot be read',
    'clock_reading_invalid': "This host's clock returned an unusable time",
    'clock_lock_unavailable': 'The recorded time cannot be locked',
    'expired_request': 'The approval window has closed',
    'maintenance_approval_required': 'The review digest does not match',
    'maintenance_replay_forbidden': 'This operation cannot be replayed',
    'maintenance_repository_stale': 'The intent this proposal cited no longer matches the repository',
    'workbench_repository_stale': 'The recorded intent no longer matches the repository',
    'maintenance_observation_stale': 'The observation is not fresh',
    'maintenance_observation_incomplete': 'The observation is incomplete',
    'maintenance_plan_stale': 'The service changed around the plan',
    'unreadable_file': 'A file could not be read',
    'workbench_desired_capability': 'The desired policy is outside the capability map'}


def refusal_header(code):
    """[REFUSED], the refusal in words, and its code in parentheses."""
    words = REFUSAL_TITLES.get(code) or _as_words(code)[:1].upper() + _as_words(code)[1:]
    return '[REFUSED] %s (%s)' % (words, code)


# Words that carry no meaning of their own, so that restating a sentence is judged on what it says.
_PARTICLES = frozenset({'the', 'is', 'one', 'this', 'that', 'of', 'it', 'its', 'to', 'in', 'by', 'as', 'an', 'a', 'or', 's'})


def _words(text):
    return set(''.join(char if char.isalnum() or char == '_' else ' ' for char in text.lower()).split()) - _PARTICLES


# Refusals whose general meaning only restates their header, so "In general: ..." is never added after a specific
# message (run 8, frame 81: the header "The desired policy is outside the capability map" and then "In general: The
# desired policy uses a setting definition, value, platform or technology outside the supported capability map").
HEADER_RESTATING = frozenset({'workbench_desired_capability'})


def _restates(message, meaning):
    """True when the engine's message already says at least four fifths of what the meaning line would."""
    meant = _words(meaning)
    return bool(meant) and len(meant & _words(message)) * 5 >= len(meant) * 4


# Execution errors the engine names by code, in words; the code stays beside them.
EXECUTION_ERROR_WORDS = {'model_response_lost': "the modeled service's response was lost",
                         'partial_write': 'the modeled service applied part of the change'}


def effect_lines(effects, width):
    """What a refusal established about what changed, in words; nothing when the engine established nothing."""
    if not isinstance(effects, dict):
        return []
    said = []
    if effects.get('intent_recorded') is False:
        retained = effects.get('retained_intent')
        said.append('No new intent was recorded; the previous intent%s is retained.' % (
            ' ' + str(retained)[:12] if retained else ''))
    elif effects.get('intent_recorded') is True:
        said.append('A new intent %s exists after the refusal; 9 shows it.' % str(effects.get('retained_intent'))[:12])
    if 'files_written' in effects:
        files = [str(path) for path in effects.get('files_written') or []]
        created = effects.get('operation_created')
        head = 'No proposal was created.' if created is False else 'An operation directory exists after the refusal.'
        said.append(head + (' These input files were written and remain: %s.' % ', '.join(files) if files else
                            '') if files or created is not False else 'No proposal and no input files were created.')
    elif effects.get('operation_created') is False:
        said.append('No operation directory was created.')
    elif effects.get('operation_created') is True:
        said.append('An operation directory was created before the refusal; i shows its state.')
    if effects.get('dispatched') is False:
        said.append('Nothing was dispatched.')
    elif effects.get('dispatched') is True:
        said.append('Dispatch had started, so the outcome is unknown; reconcile it (it never replays the change).')
    if effects.get('deployment_recorded') is False:
        said.append('No deployment record was made.')
    return word_wrap('Effect: ' + ' '.join(said), width) if said else []


EXECUTION_EFFECTS = {
    'unknown': 'Dispatch started; whether the service applied the change is unknown. Reconcile checks it without '
               'replaying the change.',
    'observed_as_desired': 'The service applied the change, and an independent readback observed the desired state.',
    'no_change_needed': 'No service change was needed or sent; the readback observed the desired state.'}


def execution_effect_lines(result, width):
    """What an execution or a reconcile established about the service, from the result's own effects."""
    effects = result.get('effects') if isinstance(result.get('effects'), dict) else {}
    change = effects.get('service_change')
    if change in EXECUTION_EFFECTS:
        # The lost response is the Error row's to say, in words with its code; the effect does not repeat it.
        return word_wrap('Effect: ' + EXECUTION_EFFECTS[change], width)
    if effects.get('replayed') is False:
        return word_wrap('Effect: Reconcile read the service and recorded what it found; it did not replay the change.', width)
    return []


def refusal_lines(value, width, known=None, clock_fact=None, operation=None, verb=None, recorded=None, context_file=None, given=None,
                  desired_file=None):
    """A refusal in one shape: the refusal in words with its code in parentheses, then Cause, Effect (when the engine
    established what changed) and Next (when the code is known).

    The general meaning is left out when the engine's own message already says it. When the code covers several causes
    and the workspace's last read recorded which one applied (known), that cause replaces the general meaning.
    operation: the short id of the operation the command named, so Cause and Next name it.
    verb: the command's own word; a restore reads the code in its own terms.
    recorded: the deployment record the named operation already has, for a refused deployment-record command; the
    refusal then says so and names it, and never asks for a record that exists (run 9, frame 67).
    context_file, desired_file: the paths of the context file and the desired file the plan bound. The engine raises this
    code for either file and says which in error.effects['changed'] ('desired_source' or 'context'); the cause names
    that file by its path. Without that fact (an older record) the cause names both kinds and no path (review 19).
    given: the intent the command named, for a refused deployment-record, shown beside the cited one (run 12, frame 67).
    """
    error = value.get('error') if isinstance(value.get('error'), dict) else {}
    code = str(error.get('code', 'unknown'))
    message = str(error.get('message') or '')
    restore = RESTORE_REFUSALS.get(code) if verb == 'restore-propose' else None
    lines = word_wrap('[REFUSED] %s (%s)' % (restore[0], code) if restore else refusal_header(code), width)
    named = 'operation %s' % operation if operation else 'that operation'
    override = None
    changed = (error.get('effects') or {}).get('changed') if isinstance(error.get('effects'), dict) else None
    if code == 'maintenance_source_changed' and not restore and changed in ('desired_source', 'context'):
        # The engine says which bound file changed (run 16, N2; review 19), so the cause names that file by its path.
        kind, path = ('desired file', desired_file) if changed == 'desired_source' else ('context file', context_file)
        file = '%s %s' % (kind, command_arg(path)) if isinstance(path, str) and path else kind
        override = ('A file this proposal bound changed after %s was prepared (the %s), so its review no longer describes '
                    'what would run.' % (named if operation else 'it', file), REFUSALS[code][1])
    elif code == 'maintenance_source_changed' and not restore and operation:
        # The engine did not say which file (an older record): names the operation and both kinds of file it bound.
        override = ('A file it bound (its desired file or its context file) changed after operation %s was prepared, so its '
                    'review no longer describes what would run.' % operation, REFUSALS[code][1])
    if operation and message.startswith('This operation '):
        # The engine's message says "This operation"; with the operation known, it says which one.
        message = 'Operation %s %s' % (operation, message[len('This operation '):])
    if given and code == 'workbench_deployment_intent_not_cited':
        message = message.replace(', not the intent given', ', not the intent given (%s)' % given, 1)
    already = None
    if recorded and code == 'workbench_deployment_intent_not_cited':
        # The engine's message ends by asking to record with the cited intent; the record exists, so that clause goes.
        message = message.replace('; record the deployment with the intent it cites.', '.')
        already = '%s already has deployment record %s (v opens Delivery, where it is stage 7); there is nothing to record.' % (
            named[:1].upper() + named[1:], str(recorded.get('artifact_id'))[:12])
    if known:
        # The cause the workspace read, and the step for it; the engine's general message is one key away.
        cause, kind = known if isinstance(known, tuple) else (known, None)
        lines += word_wrap('Cause: ' + str(cause), width)
        lines += effect_lines(error.get('effects'), width)
        step = already or KNOWN_NEXT.get(kind) or (REFUSALS[code][1] if code in REFUSALS else None)
        if step and kind in ('observation_clock_moved_backward', 'observation_clock_floor_invalid'):
            step = with_clock_times(step, clock_fact)  # the recovery names the times it is about
        if step:
            lines += step_rows(step.replace('{operation}', named), width, 'Next: ')
        if message:
            lines += word_wrap("The engine's own message is in the typed details (e).", width)
        return lines
    meaning, step = override or REFUSALS.get(code, (None, None))
    if restore:
        meaning, step = restore[1].replace('{original}', named.replace('that ', '')), restore[2]
    step = already or step
    if meaning is None:
        # Unknown codes show only the engine's own message as the cause; nothing is guessed.
        lines += word_wrap('Cause: ' + message, width) if message else []
        return lines + effect_lines(error.get('effects'), width)
    # The cause is said once. The engine's message stays on screen only when it names something the general
    # meaning cannot (a setting, a path, a value); otherwise it is one key away (Gemini review K, problem 3).
    effects = effect_lines(error.get('effects'), width)
    meaning = _without_said(meaning, effects)
    specific = bool(message) and _names_specifics(message)
    if specific:
        # The message names what the general meaning cannot, so it is the cause; the meaning follows in the same
        # paragraph where it says more.
        # The general meaning follows only where it says more: not where the message already says it, and not where it
        # only restates the refusal's own header (run 8, frame 81).
        said = _restates(message, meaning) or code in HEADER_RESTATING
        lines += word_wrap('Cause: ' + message + ('' if said else ' In general: ' + meaning), width)
    else:
        lines += word_wrap('Cause: ' + meaning, width)
    # What the refusal established about what changed, from the engine's own facts, before the next step.
    lines += effects
    if step:
        lines += step_rows(step.replace('{operation}', named), width, 'Next: ')
    if message and not specific:
        lines += word_wrap("The engine's own message is in the typed details (e).", width)
    return lines


def _without_said(meaning, said):
    """The meaning without its closing sentences that the effect lines already say (journey 28 run 3, frame 24)."""
    import re
    flat = ' '.join(' '.join(said).split())
    sentences = re.split(r'(?<=\.) ', str(meaning).strip())
    while len(sentences) > 1 and sentences[-1].strip() and sentences[-1].strip() in flat:
        sentences.pop()
    return ' '.join(sentences)


def _names_specifics(message):
    """Whether an engine message names something particular: an identifier, a path, a quoted or numbered value."""
    import re
    return bool(re.search(r'[0-9_/\\"]|\w\.\w', message))


# The next step for a known cause, where the engine's code covers several.
KNOWN_NEXT = {
    'repository_changed': 'Press 9 to review the difference; then Refresh the repository intent (a: actions).',
    'consumer_changed': 'Fix the component so it consumes exactly this policy, then choose Refresh the repository intent '
                        '(a: actions): it asks for the REVISION and pins the difference you reviewed.',
    'service_changed': 'Collect again (a lists it), then Prepare a proposal from the recorded intent (a: actions).',
    'policy_changed': 'Collect again (a lists it), then Prepare a proposal from the recorded intent (a: actions).',
    'source_mismatch': 'Collect again from the configured service (a lists it), then Prepare a proposal from the recorded intent (a: actions).',
    'tenant_mismatch': "Restart with the --service-root for this store's tenant.",
    'observation_stale': 'Collect again (a lists it), then Prepare a proposal from the recorded intent (a: actions).',
    # A clock hold on the age: a new observation is judged against the same recorded time, so collecting is not the step.
    'observation_clock_moved_backward': (
        'Collecting again does not clear this: correct the host clock, or wait until it reads at or after the time this '
        'workspace recorded, then restart the workbench and Prepare a proposal from the recorded intent (a: actions).'),
    'observation_clock_floor_invalid': (
        "Collecting again does not clear this: changes stay held until the workspace's recorded time can be read again "
        '(Diagnostics shows where it is kept).'),
    # The workspace looked at the files the typed command names and found which one cannot be read.
    'unreadable_file': 'Check that the file exists and this account can read it, then submit the command again; if it '
                       'belongs to a proposal, Prepare a proposal from the recorded intent (a: actions).',
    'collection_failed': 'Collect again (a lists it) when the source is reachable, then Prepare a proposal from the recorded intent (a: actions).',
    'collection_not_finished': 'Collect again (a lists it), then Prepare a proposal from the recorded intent (a: actions).'}


# Where 'clear' could be read as more than the check establishes, the area says what was checked.
AREA_CLEAR = {'freshness': 'clear by age; whether the source changed since capture is the proposal\'s own check',
              'device_evidence': 'capture complete and cohort consistent; whether devices reported is not judged here '
                                 '(h shows the counts)'}
CHECK_WORDS = {'clear': 'clear', 'attention': 'needs attention', 'not_recorded': 'no repository intent recorded',
               'not_imported': 'no device evidence imported',
               'explained_by_collection': 'stale; explained by the failed collection above',
               'partly_checked': 'partly checked: the read bound was reached', 'unavailable': 'could not be read'}


def evidence_detail_words(evidence):
    """A signal's evidence in words: names spaced, times readable, identities shortened, reasons in words; the
    exact values stay in the typed details and the raw record."""
    parts = []
    for key, item in evidence.items():
        if item in (None, [], {}) or key == 'scope':
            continue
        label = str(key).replace('_', ' ')
        if key == 'snapshot_id' and isinstance(item, str):
            parts.append('snapshot ' + item[:12])
        elif str(key).endswith('_at') and isinstance(item, str):
            parts.append('%s %s' % (label, _when(item)))
        elif key == 'freshness_clock' and clock_times(item):
            parts.append(clock_times(item))
        elif key == 'freshness_reasons' and isinstance(item, list):
            parts.append('%s: %s' % (label, ', '.join(FRESHNESS_REASON_WORDS.get(reason, _as_words(reason)) for reason in item)))
        elif isinstance(item, list):
            parts.append('%s: %s' % (label, ', '.join(_as_words(entry) if isinstance(entry, str) else _value(entry) for entry in item)))
        elif isinstance(item, bool):
            parts.append('%s %s' % (label, 'yes' if item else 'no'))
        elif str(key).endswith('status') and isinstance(item, str):
            parts.append('%s %s' % (label, _as_words(item)))
        else:
            parts.append('%s %s' % (label, item if isinstance(item, str) else _value(item)))
    return '; '.join(parts)


def diagnostics_lines(value, width, check=None):
    """What needs attention for one policy: each observed fact, its evidence and the next step; then what is clear.

    check: the proposal's own observation check from the Inspector's last read of this policy, shown with the
    signals because diagnostics does not record it (journey 27 review, Sonnet 3 and 4)."""
    signals = [signal for signal in value.get('signals') or [] if isinstance(signal, dict)]
    check = check if isinstance(check, dict) and check.get('reason') in ELIGIBILITY_FINDINGS else None
    partial = any(state in ('partly_checked', 'unavailable') for state in (value.get('checked') or {}).values())
    queue = '; reporting completeness and ownership are reviewed in the maintenance queue (m opens it)'
    summary = ((_plural(len(signals), 'signal') + " and the proposal's observation check need attention" + queue)
               if signals and check else "the proposal's observation check needs attention" + queue if check
               else _plural(len(signals), 'signal') + (' need attention' if len(signals) != 1 else ' needs attention')
               + queue if signals
               else 'no signal, but some areas were not fully read' if partial
               else 'no signal in the areas checked below; reporting completeness and ownership are reviewed in the '
                    'maintenance queue (m opens it)')
    lines = ['[DIAGNOSTICS]']
    lines += word_wrap('%s (%s) | %s' % (value.get('name') or '(no name)', value.get('object_id'), summary), width)
    for signal in signals:
        lines.append('')
        lines += word_wrap('[!] %s  %s' % (signal.get('area'), signal.get('code')), width)
        lines += _labelled('  Observed', str(signal.get('observed')), width, 12)
        evidence = signal.get('evidence') if isinstance(signal.get('evidence'), dict) else {}
        shown = evidence_detail_words(evidence)
        if shown:
            lines += _labelled('  Evidence', shown, width, 12)
        lines += _labelled_steps('  Next', str(signal.get('next_step')), width, 12)
    if check:
        observed, step = ELIGIBILITY_FINDINGS[check['reason']]
        lines.append('')
        lines += word_wrap('[!] observation  %s (the check a proposal makes, read now)' % check.get('code'), width)
        lines += _labelled('  Observed', observed % check, width, 12)
        lines += _labelled('  Next', step, width, 12)
    lines.append('')
    lines.append('CHECKED')
    for area, state in (value.get('checked') or {}).items():
        shown = AREA_CLEAR[area] if state == 'clear' and area in AREA_CLEAR else CHECK_WORDS.get(state, str(state))
        lines += word_wrap('  %s %s' % (pad(area.replace('_', ' '), 16), shown), width)
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
        source += ' recorded ' + _when(origin['recorded_at'])
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


def adoption_lines(value, width):
    """The adoption preview (what adopt would create) and the adopt result (what it created), from their records."""
    lines = []
    field = lambda label, text: lines.extend(word_wrap('%s: %s' % (label, text), width))
    policies = lambda count: '%d %s' % (count, 'policy' if count == 1 else 'policies')
    flags = ('no cloud authority; execution not authorized; nothing imported remotely'
             if value.get('cloud_authority') is False and value.get('execution_authorized') is False
             and value.get('remote_import_performed') is False else 'authority flags not as expected; see r raw record')
    if value.get('status') == 'adopted_local_model':
        ids = [str(item) for item in value.get('object_ids') or []]
        lines += word_wrap('[ADOPTED] %s handed off to a local maintenance model' % policies(len(ids)), width)
        for object_id in ids:
            lines += word_wrap('  ' + object_id, width)
        field('Handoff', _path_words(value.get('handoff_root')))
        field('Modeled service', _path_words(value.get('service_root')))
        from .io import unique_prefixes
        listed = [str(row.get('artifact_id')) for row in value.get('adoptions') or [] if isinstance(row, dict)]
        adoptions = [short_id(item, unique_prefixes(listed)) for item in listed]
        lines += word_wrap('Collection run %s recorded in this store, with %s (%s).' % (
            value.get('collection_run_id'), _plural(len(adoptions), 'adoption record'), ', '.join(adoptions) or 'none'), width)
        field('Ownership', str(value.get('ownership')))
        lines += word_wrap('%s; %s.' % ('Original journey kept' if value.get('original_journey_preserved') else
                                         'Original journey not confirmed kept', flags), width)
        lines += word_wrap("Next: q, then reopen the workspace: it uses this handoff's modeled service for collect and "
                           'proposals without --service-root (the Estate names it); 1 Estate lists the adopted %s.'
                           % ('policy' if len(ids) == 1 else 'policies'), width)
        return lines
    binding = value.get('binding') if isinstance(value.get('binding'), dict) else {}
    ids = [str(item) for item in binding.get('object_ids') or []]
    generated = binding.get('generated') if isinstance(binding.get('generated'), dict) else {}
    lines += word_wrap('[ADOPTION PREVIEW] Ready to hand off %s into a separate local maintenance model'
                       % policies(len(ids)), width)
    for object_id in ids:
        place = generated.get(object_id) if isinstance(generated.get(object_id), dict) else {}
        lines += word_wrap('  %s  generated at %s' % (object_id, _path_words(place.get('path', 'an unrecorded path'))), width)
    field('Journey', '%s (a completed wizard journey; kept unchanged)' % _path_words(binding.get('session')))
    source = binding.get('source') if isinstance(binding.get('source'), dict) else {}
    context = binding.get('context') if isinstance(binding.get('context'), dict) else {}
    field('Source', '%s | context %s' % (_path_words(source.get('path')), _path_words(context.get('path'))))
    atmos = binding.get('atmos') if isinstance(binding.get('atmos'), dict) else {}
    field('Stack', '%s / %s (%s; Atmos, the tool that resolves stack configuration, %s)' % (
          atmos.get('stack'), atmos.get('component'), str(atmos.get('assurance')).replace('_', ' '),
          'was run' if atmos.get('native_atmos_executed') else 'was not run'))
    repository = binding.get('repository')
    field('Repository', 'none supplied (local context only)' if repository is None else str(
        _path_words(repository.get('root') if isinstance(repository, dict) else repository)))
    service = binding.get('original_service') if isinstance(binding.get('original_service'), dict) else {}
    field('Journey model', 'revision %s after %s' % (service.get('revision'), _plural(service.get('request_count') or 0, 'request')))
    field('Ownership', str(binding.get('ownership')))
    field('Evidence', '%s; %s' % (str(binding.get('evidence_class')).replace('_', ' '), flags))
    lines += word_wrap('What adopt does: creates a new handoff directory with its own modeled service built from the '
                       'captured estate, records one collection of these policies in this store and one adoption '
                       'record for each. It sends nothing to a tenant and leaves the journey unchanged.', width)
    lines += word_wrap('Next: In the workspace:', width)
    lines += word_wrap("  adopt '%s' NEW_HANDOFF_DIR" % binding.get('session'), width)
    return lines


TITLES = {'current': 'REPOSITORY MATCHES THE RECORDED INTENT',
          'stale': 'REPOSITORY CHANGED SINCE THE RECORDED INTENT',
          'unavailable': 'REPOSITORY UNAVAILABLE'}


def repository_lines(status, width, prefixes=None, next_step=True):
    """The repository-status result: what was recorded, whether it still holds, and the next step (next_step=False
    where the surface's own Lifecycle line gives it)."""
    freshness = status.get('freshness', {}) if isinstance(status.get('freshness'), dict) else {}
    state = freshness.get('status')
    lines = [TITLES.get(state, 'REPOSITORY STATUS UNKNOWN')]
    scope = status.get('scope') if isinstance(status.get('scope'), dict) else {}
    consumer = status.get('consumer') if isinstance(status.get('consumer'), dict) else {}
    logical = consumer.get('logical_stack')
    stack = str(scope.get('stack', 'unknown')) + (' (' + str(logical) + ')' if logical and logical != 'unknown' else '')
    revision = str(status.get('source_revision', 'unknown')) + (
        ' (content verified)' if status.get('revision_content_verified') else ' (caller asserted; working tree read)')
    repository = scope.get('repository', 'unknown')
    intent = status.get('repository_intent_id')
    for label, text in (('Source   ', _path_words(repository) if isinstance(repository, str) else repository),
                        ('Stack    ', stack + ' / ' + str(scope.get('component', 'unknown'))),
                        ('Pointer  ', status.get('effective_pointer', 'unknown')),
                        ('Revision ', revision),
                        ('Intent   ', short_id(intent, prefixes) if isinstance(intent, str) else 'unknown')):
        lines += word_wrap(label + str(text), width)
    reasons = consumer.get('reasons') or []
    lines += word_wrap('Consumer ' + (consumer_words('verified') if consumer.get('status') == 'verified' else str(consumer.get('status', 'unknown')))
                       + (': ' + ', '.join(map(str, reasons)) if reasons else ''), width)
    now = (freshness.get('consumer') or {}).get('status')
    if now and now != consumer.get('status'):
        lines += word_wrap('Consumer now ' + (consumer_words('verified') if now == 'verified' else str(now)), width)
    if state == 'stale':
        sources = freshness.get('sources') or {}
        lines.append('SOURCES')
        for kind, label in (('changed', 'changed  '), ('added', 'added    '), ('removed', 'removed  ')):
            for path in sources.get(kind, []):
                lines += word_wrap('  ' + label + str(path), width)
        if isinstance(freshness.get('field_changes'), dict):
            # The comparison the code makes: the recorded intent's desired body against the repository's value now.
            lines.append('RECORDED INTENT AGAINST THE REPOSITORY NOW')
            listed = sum(len(sources.get(kind) or []) for kind in ('changed', 'added', 'removed'))
            if listed and freshness['field_changes'].get('status') == 'no_change':
                # The comparison below is of the body at the pointer (intent_freshness), not of the files listed above.
                lines += word_wrap("The listed %s from the recorded %s, but %s this policy's body at the intent pointer."
                                   % (('file differs', 'one', 'it does not alter') if listed == 1 else
                                      ('files differ', 'ones', 'they do not alter')), width)
            lines += change_lines(freshness['field_changes'], width, 'BEFORE (recorded intent)', 'AFTER (repository now)',
                                  same=REPOSITORY_SAME)
        elif freshness.get('pointer_present') is False:
            lines += word_wrap('The intent pointer no longer resolves in the repository.', width)
    elif state == 'unavailable':
        lines += word_wrap('Reason ' + str(freshness.get('reason', 'unknown')), width)
    if status.get('next_action') and next_step:
        lines += word_wrap('Next: ' + str(status['next_action']), width)
    return lines


def change_words(change, prefixes=None):
    """A plan change ("<object id>:description_changed") in words, its identity shortened: "description changed (22222222)"."""
    identity, _, kind = change.rpartition(':')
    return '%s (%s)' % (_as_words(kind), short_id(identity, prefixes)) if identity else _as_words(change)


def service_words(origin):
    """Which modeled service the session uses and why, for the Estate surface."""
    if not isinstance(origin, dict):
        return 'Modeled service: none yet. Adopt a completed journey (the adopt command), or start with --service-root.'
    if origin.get('problem'):
        return ('Modeled service: unavailable. The latest adoption record %s names %s, which cannot be opened for this '
                'tenant; start with --service-root.' % (str(origin.get('artifact_id'))[:12], _path_words(origin.get('root'))))
    if origin.get('source') == 'adoption':
        return 'Modeled service: %s (from the latest adoption record %s; --service-root chooses another)' % (
            _path_words(origin['root']), str(origin.get('artifact_id'))[:12])
    return 'Modeled service: %s (--service-root)' % _path_words(origin.get('root'))
