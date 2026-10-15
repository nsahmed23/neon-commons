"""The pure target and Settings Catalog conflict evaluator.

Input: an immutable `Snapshot`, a `ProposedRevision` and a semantics `Profile`. Output: before and after cohort
bounds for every changed policy, findings with kind, certainty, reasons and evidence, and a result in the shape of
`contracts/simulation-result.schema.json`. Nothing here reads a live store, writes anything, or authorizes an
action; a result describes the captured or synthetic universe, not the endpoints.

For each policy and each context (a device, or a user on a device) the evaluator computes one of T, F, U for
"the policy applies". The lower set L holds the contexts that are T; the upper set U holds those that are T or U,
so L is always inside U. Group exclusions come first and only in their own principal domain; among the included
assignments the winning filter mode is exclude, then no filter, then include; filters of the winning mode combine
with OR (negated for exclude). When an assignment may or may not be present, every admissible branch is evaluated
and the answer is definite only if the branches agree.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import sim_settings
from .io import digest
from .sim_filters import F, T, U, and3, evaluate as evaluate_filter, not3, or3, parse_filter
from .workbench_semantics import analyze, compare

EXCLUSION = 'exclusionGroupAssignmentTarget'
GROUP = 'groupAssignmentTarget'
ALL_DEVICES = 'allDevicesAssignmentTarget'
ALL_USERS = 'allLicensedUsersAssignmentTarget'
NEXT_REVIEW = ('Review the proposed change and the cited sources; this result is not an approval and does not '
               'schedule or authorize a deployment.')
NEXT_COVERAGE = 'Collect the missing data and run the simulation again before relying on this result.'
_COVERAGE_PREFIXES = ('missing_group:', 'missing_filter:', 'filter_unsupported:', 'membership_incomplete:',
                      'context_device_not_in_universe', 'user_not_in_snapshot')


@dataclass(frozen=True)
class Unsupported:
    reasons: tuple


@dataclass(frozen=True)
class Targeting:
    lower: frozenset
    upper: frozenset
    reasons: frozenset
    contexts_unbounded: bool = False   # user-side data was not fully collected: the context upper bound is open


EMPTY = Targeting(frozenset(), frozenset(), frozenset())


@dataclass(frozen=True, eq=False)
class SimulationResult:
    schema: dict
    detail: dict

    def to_schema(self):
        import copy
        return copy.deepcopy(self.schema)


class _Index:
    """Read-only lookup structures over one snapshot; context ids 0..n-1 are devices, n.. are user-on-device pairs."""

    def __init__(self, snapshot, profile):
        self.snapshot, self.profile = snapshot, profile
        self.dev_ids = [d.id for d in snapshot.devices]
        self.dev_pos = {d: i for i, d in enumerate(self.dev_ids)}
        self.n = len(self.dev_ids)
        self.users = frozenset(u.id for u in snapshot.users)
        self.memberships_complete = snapshot.collections['memberships'].complete
        self.reasons = set()
        pairs = {}
        for c in snapshot.contexts:
            pos = self.dev_pos.get(c.device_id)
            if pos is None:
                self.reasons.add('context_device_not_in_universe')
                continue
            eligible = profile.eligibility[c.relation]
            if c.certainty != 'known':
                eligible = and3(eligible, U)
            if snapshot.devices[pos].sharing == 'shared':
                eligible = and3(eligible, profile.eligibility['shared_device'])
            pair = (c.user_id, pos)
            if pairs.get(pair) != T:
                pairs[pair] = eligible
        ordered = sorted(pairs.items())
        self.ctx_user = [p[0][0] for p in ordered]
        self.ctx_dev = [p[0][1] for p in ordered]
        self.ctx_elig = [p[1] for p in ordered]
        self._filters, self._matches, self._targets, self._support = {}, {}, {}, {}

    # -- lookups -----------------------------------------------------------------------------------------------
    def filter(self, filter_id):
        if filter_id not in self._filters:
            record = self.snapshot.filter_by_id.get(filter_id)
            if record is None:
                self._filters[filter_id] = (None, 'missing_filter:' + filter_id)
            else:
                parsed = parse_filter(record.expression.value, self.profile, record.expression.presence)
                problem = None if parsed.ast is not None else f'filter_unsupported:{filter_id}:{parsed.reason}'
                self._filters[filter_id] = (parsed, problem)
        return self._filters[filter_id]

    def match(self, filter_id, pos, loc):
        cached = self._matches.get((filter_id, pos))
        if cached is None:
            parsed, problem = self.filter(filter_id)
            if parsed is None:
                cached = (U, (problem,))
            else:
                cached = evaluate_filter(parsed, self.snapshot.devices[pos], self.profile)
                if problem:
                    cached = (cached[0], cached[1] + (problem,))
            self._matches[(filter_id, pos)] = cached
        loc.update(cached[1])
        return cached[0]

    def member(self, group_id, principal, kind, loc):
        """T/F/U membership of a principal in a group, or None when the group cannot hold this kind of principal."""
        group = self.snapshot.group_by_id.get(group_id)
        if group is None:
            loc.add('missing_group:' + group_id)
            return U
        if group.member_domain != 'mixed' and group.member_domain not in ('unknown', kind):
            return None
        if principal in self.snapshot.members_known[group_id]:
            return T
        if principal in self.snapshot.members_possible[group_id]:
            return U
        if group.membership_complete and self.memberships_complete:
            return F
        loc.add('membership_incomplete:' + group_id)
        return U

    def applicable(self, assignment_type, group_id, kind):
        if assignment_type == ALL_DEVICES:
            return kind == 'device'
        if assignment_type == ALL_USERS:
            return kind == 'user'
        group = self.snapshot.group_by_id.get(group_id)
        return group is None or group.member_domain in ('mixed', 'unknown', kind)

    # -- policy support and targeting --------------------------------------------------------------------------
    def support(self, record):
        key = (record.id, record.sha256)
        if key not in self._support:
            reasons = []
            if record.family != 'settings_catalog':
                reasons.append('unsupported_family:' + record.family)
            if record.incomplete_reason:
                reasons.append('incomplete_source:' + record.incomplete_reason)
            analysis = analyze(record.body)
            if analysis['blockers']:
                reasons.extend(sorted({b['code'] for b in analysis['blockers']}))
            self._support[key] = Unsupported(tuple(reasons)) if reasons else analysis
        return self._support[key]

    def target(self, record):
        key = (record.id, record.sha256)
        if key not in self._targets:
            analysis = self.support(record)
            self._targets[key] = analysis if isinstance(analysis, Unsupported) else self._evaluate(analysis['normalized'])
        return self._targets[key]

    def _evaluate(self, body):
        assignments = body['assignments']
        exclusions = [a['group_id'] for a in assignments if a['type'] == EXCLUSION]
        includes = [(a['type'], a.get('group_id'), a['filter_type'], a.get('filter_id'))
                    for a in assignments if a['type'] != EXCLUSION]
        loc, lower, upper, open_contexts = set(), set(), set(), False
        for kind in ('device', 'user'):
            inc = [a for a in includes if self.applicable(a[0], a[1], kind)]
            if not inc:
                continue
            exc = [g for g in exclusions if self.applicable(GROUP, g, kind)]
            if kind == 'device':
                for pos, principal in enumerate(self.dev_ids):
                    value = self._decide(kind, principal, pos, exc, inc, loc)
                    if value == T:
                        lower.add(pos)
                        upper.add(pos)
                    elif value == U:
                        upper.add(pos)
            else:
                for j, principal in enumerate(self.ctx_user):
                    value = and3(self.ctx_elig[j], self._decide(kind, principal, self.ctx_dev[j], exc, inc, loc))
                    if value == T:
                        lower.add(self.n + j)
                        upper.add(self.n + j)
                    elif value == U:
                        upper.add(self.n + j)
                # A context or user the capture missed could reach any device, so no device is ruled out and the
                # context bound is open; the lower set is untouched.
                collections = self.snapshot.collections
                if (not collections['user_device_contexts'].complete
                        or (any(a[0] == ALL_USERS for a in inc) and not collections['users'].complete)):
                    upper.update(range(self.n))
                    open_contexts = True
        self.reasons.update(r for r in loc if r.startswith(_COVERAGE_PREFIXES))
        return Targeting(frozenset(lower), frozenset(upper), frozenset(loc), open_contexts)

    def _decide(self, kind, principal, pos, exclusions, includes, loc):
        excluded = F
        for group_id in exclusions:
            excluded = or3(excluded, self.member(group_id, principal, kind, loc))
            if excluded == T:
                return F
        active = []
        for entry in includes:
            if entry[0] in (ALL_DEVICES, ALL_USERS):
                state = T
                if entry[0] == ALL_USERS and principal not in self.users:
                    loc.add('user_not_in_snapshot')
                    state = U
            else:
                state = self.member(entry[1], principal, kind, loc)
            if state != F:
                active.append((entry, state))
        if not active:
            return F
        return and3(not3(excluded), self._resolve(active, pos, loc))

    def _resolve(self, active, pos, loc):
        certain = [e for e, s in active if s == T]
        unsure = [e for e, s in active if s == U]
        if not unsure:
            return self._branch(certain, pos, loc)
        if len(unsure) > self.profile.max_uncertain:
            loc.add('too_many_uncertain_assignments')
            return U
        seen = set()
        for mask in range(1 << len(unsure)):
            chosen = certain + [e for i, e in enumerate(unsure) if mask >> i & 1]
            seen.add(self._branch(chosen, pos, loc))
            if len(seen) > 1:
                return U
        return seen.pop()

    def _branch(self, entries, pos, loc):
        """Filter-mode priority over the assignments in force: exclude, then no filter, then include."""
        excludes = [e for e in entries if e[2] == 'exclude']
        if excludes:
            hit = F
            for e in excludes:
                hit = or3(hit, self.match(e[3], pos, loc))
            return not3(hit)
        if any(e[2] == 'none' for e in entries):
            return T
        hit = F
        for e in entries:
            if e[2] == 'include':
                hit = or3(hit, self.match(e[3], pos, loc))
        return hit

    # -- projections -------------------------------------------------------------------------------------------
    def devices(self, contexts):
        return frozenset(self.ctx_dev[c - self.n] if c >= self.n else c for c in contexts)

    def user_contexts(self, contexts):
        return frozenset(c for c in contexts if c >= self.n)

    def reachable_contexts(self, target):
        """User contexts a user-scoped setting of this policy may reach: its user-domain contexts plus every
        context on a device it may target directly (a device-assigned policy reaches that device's users)."""
        by_device = {}
        for j, pos in enumerate(self.ctx_dev):
            by_device.setdefault(pos, []).append(self.n + j)
        reach = {c for c in target.upper if c >= self.n}
        for pos in (c for c in target.upper if c < self.n):
            reach.update(by_device.get(pos, ()))
        return frozenset(reach)

    def device_ids(self, device_positions):
        return frozenset(self.dev_ids[p] for p in device_positions)

    def pair_ids(self, contexts):
        return frozenset((self.ctx_user[c - self.n], self.dev_ids[self.ctx_dev[c - self.n]]) for c in contexts)


def _label(record):
    name = record.body.get('name') if record else None
    return f'{name} ({record.id})' if name else (record.id if record else '')


def _range(lower, upper):
    return str(lower) if lower == upper else f'{lower} to {upper}'


def simulate(snapshot, revision, profile):
    """Evaluate the proposed revision against the snapshot; pure, deterministic and free of I/O."""
    idx = _Index(snapshot, profile)
    before = dict(snapshot.policy_by_id)
    after = dict(before)
    after.update({p.id: p for p in revision.policies})
    for pid in revision.removed_policy_ids:
        after.pop(pid, None)
    changed = sorted(pid for pid in set(before) | set(after)
                     if (before[pid].sha256 if pid in before else None) != (after[pid].sha256 if pid in after else None))

    reasons, findings, cohorts, detail = set(idx.reasons), {}, {}, {}
    problems = [(name, state) for name, state in snapshot.collections.items() if name != 'rings' and not state.complete]
    for name, state in problems:
        reasons.add(f'collection_incomplete:{name}:{state.reason or "incomplete"}')
    complete = not problems
    scope = 'whole_declared_universe' if complete else 'observed_universe'
    universe = ('complete_declared_synthetic_fleet' if snapshot.realm_id == 'synthetic'
                else 'complete_declared_tenant_snapshot') if complete else 'captured_devices'

    def finding(fid, kind, certainty, message, refs, action=NEXT_REVIEW):
        findings[fid] = {'id': fid, 'kind': kind, 'certainty': certainty, 'message': message,
                         'source_refs': sorted(set(refs)), 'permitted_next_action': action}

    def cohort(cid, kind, unit, lower, upper, refs=(), ring=None, cohort_scope=None):
        row = {'cohort_id': cid, 'kind': kind, 'lower': lower, 'upper': upper, 'unit': unit,
               'scope': cohort_scope or scope, 'reason_refs': sorted(set(refs))}
        if ring is not None:
            row['ring_id'] = ring
        cohorts[cid] = row

    world = {'before': {}, 'after': {}}      # per changed policy: device-level and context-level sets
    supported = []
    for pid in changed:
        b, a = before.get(pid), after.get(pid)
        tb = idx.target(b) if b else EMPTY
        ta = idx.target(a) if a else EMPTY
        if isinstance(tb, Unsupported) or isinstance(ta, Unsupported):
            why = []
            for label, t in (('before', tb), ('after', ta)):
                if isinstance(t, Unsupported):
                    why.append(f'{label}: ' + ', '.join(t.reasons))
            reasons.add('unsupported_policy:' + pid)
            finding('unsupported_policy:' + pid, 'unknown_semantics', 'unknown',
                    f'Policy {_label(a or b)} is unsupported or review-only and was not evaluated ({"; ".join(why)}). '
                    'Only Windows Settings Catalog policies with a complete source are evaluated.',
                    [f'revision:policy/{pid}'] if a else [f'snapshot:policy/{pid}'], NEXT_COVERAGE)
            continue
        supported.append(pid)
        world['before'][pid], world['after'][pid] = tb, ta

    # -- per-policy cohorts ----------------------------------------------------------------------------------
    agg = {w: {'lower': set(), 'upper': set(), 'unbounded': False} for w in ('before', 'after')}
    for pid in supported:
        sets = {}
        for w in ('before', 'after'):
            t = world[w][pid]
            sets[w] = {'dl': idx.devices(t.lower), 'du': idx.devices(t.upper),
                       'cl': idx.user_contexts(t.lower), 'cu': idx.user_contexts(t.upper),
                       'cb': None if t.contexts_unbounded else idx.user_contexts(t.upper)}
            agg[w]['lower'] |= t.lower
            agg[w]['upper'] |= t.upper
            agg[w]['unbounded'] = agg[w]['unbounded'] or t.contexts_unbounded
        detail[pid] = {w: {'lower_devices': idx.device_ids(sets[w]['dl']), 'upper_devices': idx.device_ids(sets[w]['du']),
                           'lower_contexts': idx.pair_ids(sets[w]['cl']), 'upper_contexts': idx.pair_ids(sets[w]['cu'])}
                       for w in ('before', 'after')}
        rec_b, rec_a = before.get(pid), after.get(pid)
        counts = _delta(sets['before']['dl'], sets['before']['du'], sets['after']['dl'], sets['after']['du'])
        reason_codes = sorted(world['before'][pid].reasons | world['after'][pid].reasons)
        added, removed, retained = counts['added'], counts['removed'], counts['retained']
        # A null that was read is a known fact; every other reason code is a gap in what is known.
        gaps = [r for r in reason_codes if not r.startswith('property_observed_null:')]
        exact = added[0] == added[1] and removed[0] == removed[1] and not gaps
        refs = ([f'revision:policy/{pid}'] if rec_a else []) + ([f'snapshot:policy/{pid}'] if rec_b else [])
        source = (rec_a or rec_b).source_path
        fid = 'blast_radius:' + pid
        finding(fid, 'blast_radius', 'definite_under_model' if exact else 'possible',
                f'Policy {_label(rec_a or rec_b)}, in unique devices: targeted after '
                f'{_range(len(sets["after"]["dl"]), len(sets["after"]["du"]))}; newly targeted {_range(*added)}; '
                f'no longer targeted {_range(*removed)}; retained {_range(*retained)}. Counts are inside the captured universe'
                + (f'; source {source}' if source else '') + (f'; reasons: {", ".join(reason_codes[:8])}' if reason_codes else '') + '.',
                refs)
        for unit, lk, uk in (('unique_devices', 'dl', 'du'), ('user_device_contexts', 'cl', 'cb')):
            values = _delta(sets['before'][lk], sets['before'][uk], sets['after'][lk], sets['after'][uk])
            for kind, (lo, hi) in values.items():
                cohort(f'policy:{pid}:{kind}:{unit}', kind, unit, lo, hi, [fid])

    # -- findings from assignment and body changes -----------------------------------------------------------
    for pid in supported:
        _assignment_findings(idx, finding, pid, before.get(pid), after.get(pid))

    # -- aggregate cohorts and rings -------------------------------------------------------------------------
    if supported:
        a0l, a0u = frozenset(agg['before']['lower']), frozenset(agg['before']['upper'])
        a1l, a1u = frozenset(agg['after']['lower']), frozenset(agg['after']['upper'])
        for unit, project in (('unique_devices', idx.devices), ('user_device_contexts', idx.user_contexts)):
            u0, u1 = project(a0u), project(a1u)
            if unit == 'user_device_contexts':
                u0 = None if agg['before']['unbounded'] else u0
                u1 = None if agg['after']['unbounded'] else u1
            values = _delta(project(a0l), u0, project(a1l), u1)
            for kind, (lo, hi) in values.items():
                cohort(f'changed:{kind}:{unit}', kind, unit, lo, hi)
                if unit == 'unique_devices' and not complete:
                    cohort(f'changed:{kind}:{unit}:whole', kind, unit, lo, None, cohort_scope='whole_declared_universe')
        _ring_cohorts(idx, snapshot, finding, cohort, project_sets=(idx.devices(a0l), idx.devices(a0u), idx.devices(a1l), idx.devices(a1u)))

    # -- settings comparison across policies -----------------------------------------------------------------
    _conflicts(idx, snapshot, profile, supported, before, after, world, finding, cohort, reasons, scope, set(changed))

    # -- coverage ---------------------------------------------------------------------------------------------
    reasons |= idx.reasons
    for code in sorted(reasons):
        if code in findings:
            continue
        finding('coverage_gap:' + code, 'coverage_gap', 'unknown',
                f'Coverage gap {code}: the result is bounded to the captured data and there is no safe verdict; '
                'an absence of findings must not be read as an absence of conflicts.', [], NEXT_COVERAGE)

    binding = {'realm_id': snapshot.realm_id, 'snapshot_sha256': snapshot.sha256,
               'desired_source_sha256': revision.sha256, 'semantics_sha256': profile.sha256}
    doc = {'schema_version': 1, 'simulation_id': 'sim-' + digest({'binding': binding, 'revision': revision.revision_id})[:24],
           'input_binding': binding,
           'evidence_class': 'synthetic_snapshot_simulation' if snapshot.realm_id == 'synthetic' else 'approved_snapshot_simulation',
           'coverage': {'universe': universe, 'snapshot_complete': complete,
                        'outside_snapshot_population': 'none_within_declared_scope' if complete else 'unknown',
                        'unresolved_reasons': sorted(reasons)},
           'cohorts': [cohorts[k] for k in sorted(cohorts)], 'findings': [findings[k] for k in sorted(findings)],
           'live_execution_authorized': False, 'endpoint_effective': False}
    return SimulationResult(doc, {'policies': {pid: detail[pid] for pid in sorted(detail)}})


def _delta(l0, u0, l1, u1):
    """Added, removed and retained bounds from before (L0, U0) and after (L1, U1), as in the model's table.

    An upper set of None is open (the data that would bound it was not collected): its count is None, a definite
    count that would need that set drops to 0, and nothing is narrowed."""
    def size(items):
        return None if items is None else len(items)
    if u0 is None and u1 is None:
        retained_upper = None
    elif u0 is None:
        retained_upper = len(u1)
    elif u1 is None:
        retained_upper = len(u0)
    else:
        retained_upper = len(u0 & u1)
    return {'before': (len(l0), size(u0)), 'after': (len(l1), size(u1)),
            'added': (0 if u0 is None else len(l1 - u0), None if u1 is None else len(u1 - l0)),
            'removed': (0 if u1 is None else len(l0 - u1), None if u0 is None else len(u0 - l1)),
            'retained': (len(l0 & l1), retained_upper)}


def _assignment_findings(idx, finding, pid, rec_b, rec_a):
    rows_b = idx.support(rec_b)['normalized']['assignments'] if rec_b else []
    rows_a = idx.support(rec_a)['normalized']['assignments'] if rec_a else []
    refs = ([f'revision:policy/{pid}'] if rec_a else []) + ([f'snapshot:policy/{pid}'] if rec_b else [])

    def filtered(rows):
        return {(a.get('group_id') or a['type'], a.get('filter_id')): a['filter_type']
                for a in rows if a['type'] != EXCLUSION and a['filter_type'] in ('include', 'exclude')}
    mode_b, mode_a = filtered(rows_b), filtered(rows_a)
    for key in sorted(set(mode_b) & set(mode_a), key=str):
        if mode_b[key] != mode_a[key]:
            finding(f'filter_inversion:{pid}:{key[0]}', 'filter_inversion', 'definite_under_model',
                    f'Policy {_label(rec_a)} flips filter {key[1]} on {key[0]} from {mode_b[key]} to {mode_a[key]} mode; '
                    'the targeted sets are recomputed for both states.', refs)
    if rec_b and rec_a:
        removed = {a['group_id'] for a in rows_b if a['type'] == EXCLUSION} - {a['group_id'] for a in rows_a if a['type'] == EXCLUSION}
        for gid in sorted(removed):
            finding(f'exclusion_removed:{pid}:{gid}', 'exclusion_removed', 'definite_under_model',
                    f'Policy {_label(rec_a)} no longer excludes group {gid}; members that were excluded may become targeted.', refs)
        compared = compare(rec_b.body, rec_a.body)
        if compared['status'] == 'different' and set(compared['changed_fields']) <= {'name', 'description'}:
            finding('description_only_change:' + pid, 'blast_radius', 'definite_under_model',
                    f'Policy {_label(rec_a)} changes {", ".join(compared["changed_fields"])} only: no device-setting delta and '
                    'the same target set. A wire preview may still show the assignments being posted again.', refs)
    if rec_a:
        kinds = set()
        for a in rows_a:
            if a['type'] == ALL_DEVICES:
                kinds.add('all_devices')
            elif a['type'] == ALL_USERS:
                kinds.add('all_users')
        for virtual in sorted(kinds):
            finding(f'virtual_target_review_only:{pid}:{virtual}', 'unsupported_target', 'definite_under_model',
                    f'Policy {_label(rec_a)} targets {virtual.replace("_", " ")}, a virtual target that stays review-only: '
                    'the simulator shows it and implements or authorizes no write for it.', refs)
        has_user = any(a['type'] == ALL_USERS or (a['type'] == GROUP and _domain(idx, a['group_id']) in ('user', 'either'))
                       for a in rows_a)
        has_device = any(a['type'] == ALL_DEVICES or (a['type'] == GROUP and _domain(idx, a['group_id']) in ('device', 'either'))
                         for a in rows_a)
        for a in rows_a:
            if a['type'] != EXCLUSION:
                continue
            domain = _domain(idx, a['group_id'])
            if (domain == 'device' and has_user) or (domain == 'user' and has_device):
                finding(f'unsupported_cross_domain_exclusion:{pid}:{a["group_id"]}', 'unsupported_target', 'definite_under_model',
                        f'Policy {_label(rec_a)} excludes {domain} group {a["group_id"]} while including principals of the other domain. '
                        'Intune does not generally subtract across domains and neither does this simulator; the inclusion exposure is kept.', refs)
    unassigned = rec_b and rows_b and (rec_a is None or not rows_a)
    if unassigned:
        finding('csp_state_may_persist:' + pid, 'unknown_semantics', 'unknown',
                f'Policy {_label(rec_b)} is removed from intended targeting only. This is not proven endpoint rollback: '
                'configuration may persist on endpoints depending on the setting provider behavior.', refs, NEXT_COVERAGE)


def _domain(idx, group_id):
    group = idx.snapshot.group_by_id.get(group_id)
    if group is None or group.member_domain in ('mixed', 'unknown'):
        return 'either'
    return group.member_domain


def _ring_sets(idx, snapshot):
    rings = []
    for ring in snapshot.rings:
        known, possible = set(ring.device_ids), set()
        for gid in ring.group_ids:
            known |= snapshot.members_known.get(gid, frozenset())
            possible |= snapshot.members_possible.get(gid, frozenset())
        rings.append((ring, frozenset(known), frozenset(known | possible)))
    return rings


def _ring_cohorts(idx, snapshot, finding, cohort, project_sets):
    rings = _ring_sets(idx, snapshot)
    if not rings:
        return
    d0l, d0u, d1l, d1u = (idx.device_ids(s) for s in project_sets)
    shown = {'after': (d1l, d1u), 'added': (d1l - d0u, d1u - d0l)}
    for ring, known, possible in rings:
        for kind, (lo, hi) in shown.items():
            cohort(f'changed:{kind}:unique_devices:ring:{ring.ring_id}', kind, 'unique_devices',
                   len(lo & known), len(hi & possible), ring=ring.ring_id)
    seen = {}
    for ring, known, possible in rings:
        for device in d1u & possible:
            seen.setdefault(device, set()).add(ring.ring_id)
    overlap = [d for d, r in seen.items() if len(r) > 1]
    unclassified = d1u - set(seen)
    word = lambda n: f'{n} device' if n == 1 else f'{n} devices'
    if overlap:
        finding('ring_overlap', 'blast_radius', 'possible' if d1l != d1u else 'definite_under_model',
                f'{word(len(overlap))} in the targeted cohort {"belongs" if len(overlap) == 1 else "belong"} to more than one '
                'ring. Ring totals overlap and must not be added to infer a unique estate count.', [])
    if unclassified:
        finding('ring_unclassified', 'blast_radius', 'possible' if d1l != d1u else 'definite_under_model',
                f'{word(len(unclassified))} in the targeted cohort '
                f'{"belongs" if len(unclassified) == 1 else "belong"} to no configured ring.', [])


def _conflicts(idx, snapshot, profile, supported, before, after, world, finding, cohort, reasons, scope, changed):
    flat = {}

    def instances(record):
        if record.id not in flat:
            flat[record.id] = sim_settings.flatten(idx.support(record)['normalized'], profile, snapshot.realm_id, snapshot.tenant_id)
        return flat[record.id]
    by_key = {}
    for pid in sorted(after):
        record = after[pid]
        if isinstance(idx.support(record), Unsupported):
            if pid not in changed:
                reasons.add('unsupported_policy:' + pid)
            continue
        for key in instances(record):
            by_key.setdefault(key, []).append(pid)
    compared = False
    seen = set()
    for pid in supported:
        record = after.get(pid)
        if record is None:
            continue
        mine = instances(record)
        if not mine:
            continue
        compared = True
        previous = instances(before[pid]) if pid in before else None
        t_after, t_before = world['after'][pid], world['before'][pid]
        retargeted = previous is None or t_after.lower != t_before.lower or t_after.upper != t_before.upper
        keys = list(mine) if retargeted else [k for k in mine if k not in previous or previous[k].value != mine[k].value]
        for key in sorted(keys, key=str):
            for other in by_key.get(key, []):
                if other == pid:
                    continue
                pair = (min(pid, other), max(pid, other), key)
                if pair in seen:
                    continue
                seen.add(pair)
                _pair(idx, profile, finding, cohort, scope, pid, other, mine[key], instances(after[other])[key], after, changed, key)
    if compared and not profile.external_management_collected:
        reasons.add('external_management_unknown')


def _pair(idx, profile, finding, cohort, scope, pid, other, inst_a, inst_b, after, changed, key):
    ta, tb = idx.target(after[pid]), idx.target(after[other])
    da_l, da_u, db_l, db_u = idx.devices(ta.lower), idx.devices(ta.upper), idx.devices(tb.lower), idx.devices(tb.upper)
    lower, upper = da_l & db_l, da_u & db_u
    unit, shown_lower, shown_upper = 'unique_devices', len(lower), len(upper)
    if inst_a.key[3] == 'user':
        # A user-scoped setting lands on user contexts, not devices. Only a user-domain context both policies
        # definitely reach is a definite overlap; a shared device or a device-level assignment is only possible.
        lower = idx.user_contexts(ta.lower) & idx.user_contexts(tb.lower)
        if ta.contexts_unbounded or tb.contexts_unbounded:
            shown_upper = None
        else:
            upper = idx.reachable_contexts(ta) & idx.reachable_contexts(tb)
            shown_upper = len(upper)
        unit, shown_lower = 'user_device_contexts', len(lower)
    first, second = sorted((pid, other))
    ordered = (inst_a, inst_b) if first == pid else (inst_b, inst_a)
    outcome = sim_settings.classify(profile, ordered[0], ordered[1], lower, upper)
    if outcome is None:
        return
    tag = digest(list(map(str, key)))[:12]
    refs = [f'{"revision" if p in changed else "snapshot"}:policy/{p}' for p in (first, second)]
    refs.append('profile:definitions/' + inst_a.canonical_id)
    where = f'{inst_a.path}' + (f' item {inst_a.item}' if inst_a.item else '')
    values = f'{value_text_pair(ordered)}'
    words = 'user-device contexts' if unit == 'user_device_contexts' else 'unique devices'
    overlap = (f'{words} in definite overlap {shown_lower}, in possible overlap '
               f'{"unbounded" if shown_upper is None else shown_upper}')
    fid = None
    if outcome.kind:
        fid = f'{outcome.kind}:{first}:{second}:{tag}'
        if outcome.kind == 'predicted_configuration_conflict' or outcome.kind == 'potential_conflict':
            text = (f'Predicted configuration conflict by rule {outcome.rule}' if outcome.kind == 'predicted_configuration_conflict'
                    else f'Potential configuration conflict by rule {outcome.rule}')
            message = (f'{text}: policies {first} and {second} set {where} to {values}; {overlap}. '
                       'This is a configuration finding under the stated rule, not an observed endpoint failure.')
        else:
            message = f'Policies {first} and {second} on {where}: {values}; {overlap}; {outcome.detail}.'
        finding(fid, outcome.kind, outcome.certainty, message, refs)
    if outcome.admitted:
        cohort(f'conflict:{first}:{second}:{tag}', 'conflict_overlap', unit, shown_lower, shown_upper,
               [fid] if fid else [])


def value_text_pair(ordered):
    return ' versus '.join(sim_settings.value_text(i) for i in ordered)


def binding_status(result_doc, snapshot, revision, profile):
    """Whether a stored result still describes these inputs; any changed input invalidates it and says which."""
    stale = []
    bound = result_doc['input_binding']
    if bound['snapshot_sha256'] != snapshot.sha256 or bound['realm_id'] != snapshot.realm_id:
        stale.append('snapshot_changed')
    if bound['desired_source_sha256'] != revision.sha256:
        stale.append('desired_source_changed')
    if bound['semantics_sha256'] != profile.sha256:
        stale.append('semantics_changed')
    return (not stale), stale
