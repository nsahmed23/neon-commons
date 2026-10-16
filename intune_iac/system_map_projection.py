"""The system map's projection: one selected policy's deployment path as typed nodes inside boundaries, joined by typed edges.

Pure. The read model's own values go in (the Inspector's states, the repository intent's recorded sources, the integration
manifest's pinned setup context, the policy's adoption records and, for its newest operation, that operation's delivery);
one projection comes out. Nothing here asks the engine, opens a file, infers a link from a name or a string, or writes a
sentence: a node's state is read from a named record and field (its `basis`), its `reason` is a code those records hold,
and an edge exists only where a record establishes it, with that record and field as its evidence basis.

Rules the map keeps:
  * The node list is fixed. A step that is not configured or not recorded is a node in the `not_configured` or `unknown`
    state, never left out, so a drawing never changes shape with a state.
  * A state changes a node's state word and the revision; it never adds, removes or renames a node or an id.
  * An edge exists only where a record establishes it. A missing record leaves the edge absent, never `unknown`.
  * `layer` is the node's place in the deployment path, from topology alone; a renderer places nodes by it and by the
    fixed node order, never by a state.

The revision is the digest of the projection's canonical form, so it changes exactly when a node, a state, a basis, a
recorded identity or an edge changes; it does not change with the clock reading of a later read of the same records.
"""
from __future__ import annotations

import hashlib
import json

from .io import AppError
from .workflow_projection import VERIFIED_CLASSES

SCHEMA = 'system-map/1'
# The closed set of states. Each is a statement about a record, never a guess. The words are what a screen prints.
STATES = ('recorded', 'configured', 'not_configured', 'unknown', 'stale', 'unverified')
STATE_WORDS = {'recorded': 'recorded', 'configured': 'configured', 'not_configured': 'not configured',
               'unknown': 'unknown', 'stale': 'stale', 'unverified': 'unverified'}
# The three boundaries, in drawing order.
BOUNDARIES = (('host', 'this host'), ('repository', 'the repository'), ('cloud', 'the cloud'))
EDGE_TYPES = ('cites', 'generates', 'applies-through', 'reads-back', 'observes')
# The fixed nodes, in order: id, kind, boundary and layer (the place in the path; two nodes may share a layer).
NODES = (('repo.source', 'repository_source', 'repository', 0),
         ('atmos.component', 'atmos_component', 'repository', 1),
         ('tofu.engine', 'opentofu', 'host', 2),
         ('tofu.backend', 'backend', 'host', 2),
         ('provider', 'provider', 'host', 3),
         ('service', 'service', 'cloud', 4),
         ('readback', 'readback', 'host', 5),
         ('observation', 'observation', 'host', 5))
NODE_IDS = tuple(node[0] for node in NODES)
# The surface Enter opens, as the workflow map keys it: 9 Repository, 2 Coverage, v Delivery. A node whose record no
# surface owns opens nothing.
OPENS = {'repo.source': '9', 'atmos.component': '9', 'tofu.engine': None, 'tofu.backend': '9', 'provider': None,
         'service': '2', 'observation': '2', 'readback': 'v'}
# The recorded diagnostics code behind each repository intent status that is not current.
INTENT_REASONS = {'changed': 'repository_stale', 'consumer_changed': 'repository_consumer_mismatch',
                  'unreadable': 'repository_unavailable', 'not_checked': 'not_checked'}
RECORD_INTENT, RECORD_MANIFEST = 'repository_intent', 'integration_manifest'
RECORD_OBSERVATION, RECORD_DELIVERY, RECORD_ADOPTION = 'observation', 'delivery', 'adoption'


def _fail(message):
    raise AppError('system_map_projection_invalid', message)


def _dict(value):
    return value if isinstance(value, dict) else {}


def _text(value):
    return value if isinstance(value, str) and value else None


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False, default=str)


def _basis(record, field, record_id=None):
    return {'record': record, 'field': field, 'record_id': record_id}


def _node(identifier, state, identity, basis, reason=None, facts=None, opens=None):
    kind, boundary, layer = next((node[1], node[2], node[3]) for node in NODES if node[0] == identifier)
    return {'id': identifier, 'kind': kind, 'boundary': boundary, 'layer': layer, 'state': state,
            'identity': identity, 'basis': basis, 'reason': reason,
            'facts': {key: value for key, value in (facts or {}).items() if value is not None},
            'opens': opens}


# ---- the repository and Atmos nodes: the repository intent's own record ----------------------------------------------

def _intent_reading(states):
    """(status, scope, intent) of the repository intent as the Inspector's states hold it; status None when there is none."""
    intent = _dict(states.get('intent'))
    status = intent.get('status')
    return (None if status in (None, 'none') else status), _dict(intent.get('scope')), intent


def _repo_source(status, intent, record):
    basis = _basis(RECORD_INTENT, 'status, source_revision, resolution.sources', _text(intent.get('artifact_id')))
    if status is None:
        return _node('repo.source', 'not_configured', {'revision': None, 'source_files': []}, _basis(RECORD_INTENT, 'status'),
                     'no_repository_intent', opens=OPENS['repo.source'])
    files = [row['path'] for row in _dict(record).get('sources') or [] if isinstance(row, dict) and _text(row.get('path'))]
    identity = {'revision': _text(intent.get('source_revision')), 'source_files': files}
    facts = {'recorded_at': intent.get('recorded_at'), 'revision_content_verified': intent.get('revision_content_verified'),
             'effective_pointer': _dict(record).get('effective_pointer')}
    if identity['revision'] is None:
        state, reason = 'unknown', 'revision_not_recorded'
    elif status == 'current':
        state, reason = 'recorded', None
    elif status == 'changed':
        state, reason = 'stale', INTENT_REASONS[status]
    elif status == 'consumer_changed':
        # The sources are what was recorded; it is the component that no longer consumes the policy (the Atmos node's).
        state, reason = 'recorded', None
    elif status == 'not_checked':
        state, reason = 'unverified', INTENT_REASONS[status]
    else:
        state, reason = 'unknown', INTENT_REASONS.get(status) or str(status)
    return _node('repo.source', state, identity, basis, reason, facts, OPENS['repo.source'])


def _atmos(status, scope, intent, pins):
    if status is None:
        return _node('atmos.component', 'not_configured', {'stack': None, 'component': None}, _basis(RECORD_INTENT, 'status'),
                     'no_repository_intent', opens=OPENS['atmos.component'])
    basis = _basis(RECORD_INTENT, 'scope.stack, scope.component, status', _text(intent.get('artifact_id')))
    identity = {'stack': _text(scope.get('stack')), 'component': _text(scope.get('component'))}
    facts = {'pinned_atmos_version': _text(_dict(pins).get('atmos_version'))}
    if identity['stack'] is None or identity['component'] is None:
        state, reason = 'unknown', 'scope_incomplete'
    elif status == 'current':
        state, reason = 'recorded', None
    elif status in ('changed', 'consumer_changed'):
        state, reason = 'stale', INTENT_REASONS[status]
    elif status == 'not_checked':
        state, reason = 'unverified', INTENT_REASONS[status]
    else:
        state, reason = 'unknown', INTENT_REASONS.get(status) or str(status)
    return _node('atmos.component', state, identity, basis, reason, facts, OPENS['atmos.component'])


def _backend(status, scope, intent):
    if status is None:
        return _node('tofu.backend', 'not_configured', {'backend': None}, _basis(RECORD_INTENT, 'status'),
                     'no_repository_intent', opens=OPENS['tofu.backend'])
    backend = _text(scope.get('backend'))
    basis = _basis(RECORD_INTENT, 'scope.backend', _text(intent.get('artifact_id')))
    if backend is None:
        return _node('tofu.backend', 'not_configured', {'backend': None}, basis, 'backend_not_named', opens=OPENS['tofu.backend'])
    return _node('tofu.backend', 'recorded', {'backend': backend}, basis, opens=OPENS['tofu.backend'])


# ---- the OpenTofu and provider nodes: the integration manifest's pinned setup context --------------------------------

def _pins(read):
    """(pinned, label, unread_reason): the manifest's pinned setup context, its integration label, and why neither was read."""
    pins = read.get('setup_pins')
    if not isinstance(pins, dict):
        return {}, None, 'setup_pins_not_read'
    if _text(pins.get('error_code')):
        return {}, None, pins['error_code']
    return _dict(pins.get('pinned')), _text(pins.get('integration_label')), None


def _engine(pinned, unread):
    basis = _basis(RECORD_MANIFEST, 'setup_context.pinned.engine, setup_context.pinned.engine_version')
    if unread:
        return _node('tofu.engine', 'unknown', {'engine': None, 'version': None}, basis, unread, opens=OPENS['tofu.engine'])
    engine, version = _text(pinned.get('engine')), _text(pinned.get('engine_version'))
    identity = {'engine': engine, 'version': version}
    if engine and version:
        return _node('tofu.engine', 'configured', identity, basis, opens=OPENS['tofu.engine'])
    return _node('tofu.engine', 'not_configured', identity, basis, 'engine_pin_not_recorded', opens=OPENS['tofu.engine'])


def _provider(pinned, unread):
    basis = _basis(RECORD_MANIFEST, 'setup_context.pinned.provider_source, setup_context.pinned.provider_version')
    if unread:
        return _node('provider', 'unknown', {'source': None, 'version': None}, basis, unread, opens=OPENS['provider'])
    source, version = _text(pinned.get('provider_source')), _text(pinned.get('provider_version'))
    identity = {'source': source, 'version': version}
    if source and version:
        return _node('provider', 'configured', identity, basis, opens=OPENS['provider'])
    if not source and not version:
        return _node('provider', 'not_configured', identity, basis, 'provider_pin_not_recorded', opens=OPENS['provider'])
    return _node('provider', 'unknown', identity, basis, 'provider_pin_incomplete', opens=OPENS['provider'])


# ---- the service, observation and readback nodes ----------------------------------------------------------------------

def _observation_state(observation):
    """(state, reason) of the latest collection: fresh only when its age, its source and its coverage all agree."""
    from .workbench_diagnostics import clock_hold
    if not observation:
        return 'unknown', 'no_observation'
    reasons = [item for item in observation.get('freshness_reasons') or [] if isinstance(item, str)]
    # An age that cannot be established (a clock hold, a stamp ahead of this host's clock) is unknown, never stale.
    unestablished = clock_hold(reasons) or ('stamped_after_now' if 'stamped_after_now' in reasons else None)
    if unestablished:
        return 'unknown', unestablished
    freshness = observation.get('freshness')
    if freshness == 'stale':
        return 'stale', reasons[0] if reasons else 'stale'
    eligibility = _text(_dict(observation.get('eligibility')).get('reason'))
    if freshness == 'fresh' and eligibility:
        # Fresh by age and no longer current with its source: stale, with the reason the proposal check recorded.
        return 'stale', eligibility
    if freshness != 'fresh':
        return 'unknown', _text(freshness) or 'freshness_not_recorded'
    if observation.get('coverage') != 'complete':
        return 'unverified', 'coverage_%s' % (_text(observation.get('coverage')) or 'not_recorded')
    return 'recorded', None


def _observation(observation):
    state, reason = _observation_state(observation)
    run_id = observation.get('run_id') if observation else None
    identity = {'run_id': run_id, 'observed_at': observation.get('observed_at') if observation else None}
    facts = {'coverage': observation.get('coverage'), 'freshness': observation.get('freshness')} if observation else {}
    return _node('observation', state, identity, _basis(RECORD_OBSERVATION, 'freshness, coverage, run_id',
                                                        None if run_id is None else str(run_id)),
                 reason, facts, OPENS['observation'])


def _service(observation, read, label):
    evidence = _text(observation.get('evidence_class')) if observation else None
    identity = {'service': label, 'evidence_class': evidence}
    basis = _basis(RECORD_OBSERVATION, 'evidence_class', None if not observation or observation.get('run_id') is None
                   else str(observation['run_id']))
    if not observation:
        return _node('service', 'unknown', identity, basis, 'no_observation', opens=OPENS['service'])
    if evidence is None:
        return _node('service', 'unknown', identity, basis, 'evidence_class_not_stated', opens=OPENS['service'])
    return _node('service', 'recorded', identity, basis, opens=OPENS['service'])


def _stages(delivery):
    stages = [stage for stage in _dict(delivery).get('stages') or [] if isinstance(stage, dict)]
    return {stage.get('stage'): stage for stage in stages}


def _readback(operation, delivery):
    operation_id = _text(_dict(operation).get('operation_id'))
    identity = {'operation_id': operation_id, 'classification': None}
    opens = OPENS['readback'] if operation_id else None
    if not operation_id:
        return _node('readback', 'unknown', identity, _basis(RECORD_DELIVERY, 'stages.readback.status'), 'no_operation', opens=opens)
    basis = _basis(RECORD_DELIVERY, 'stages.readback.status, stages.readback.classification, stages.execution.status', operation_id)
    by = _stages(delivery)
    readback, execution = by.get('readback'), by.get('execution')
    if not readback or not execution:
        return _node('readback', 'unknown', identity, basis,
                     _text(_dict(delivery).get('error_code')) or 'delivery_unreadable', opens=opens)
    status = readback.get('status')
    classification = _text(readback.get('classification'))
    identity['classification'] = classification
    facts = {'second_plan': _text(readback.get('second_plan')), 'mismatch_count': readback.get('mismatch_count')}
    if status == 'not_started':
        return _node('readback', 'unknown', identity, basis, 'not_started', facts, opens)
    if status == 'pending':
        return _node('readback', 'unverified', identity, basis, 'visibility_pending', facts, opens)
    if execution.get('status') == 'unknown' or status in ('not_recorded', 'failed'):
        # Dispatch is recorded and a verified readback of its own is not: the outcome stays unknown.
        return _node('readback', 'unknown', identity, basis,
                     _text(execution.get('error_code')) or _text(status) or 'outcome_unknown', facts, opens)
    if status == 'done':
        if classification in VERIFIED_CLASSES:
            return _node('readback', 'recorded', identity, basis, classification, facts, opens)
        return _node('readback', 'unverified', identity, basis, classification or 'classification_not_recorded', facts, opens)
    return _node('readback', 'unknown', identity, basis, _text(status), facts, opens)


# ---- the edges: each exists only where a record establishes it --------------------------------------------------------

def _edge(kind, source, target, basis, state):
    return {'id': '%s:%s>%s' % (kind, source, target), 'type': kind, 'from': source, 'to': target, 'state': state,
            'basis': basis}


def _adoption_generated(adoptions, object_id):
    """(artifact id, manifest digest) from the newest valid adoption record, or None.

    The newest record is chosen first (a valid record names its artifact; the greatest sequence wins, a missing one is 0),
    and only it is read for this policy's generated files: an older record never supplies what the newest no longer names.
    Two valid records sharing the newest sequence cannot be ordered, so neither is chosen and nothing is established."""
    rows = [row for row in adoptions if isinstance(row, dict) and _text(row.get('artifact_id'))] \
        if isinstance(adoptions, (list, tuple)) else []
    if not rows:
        return None

    def sequence(row):
        value = row.get('sequence')
        return value if isinstance(value, int) and not isinstance(value, bool) else 0
    newest = max(sequence(row) for row in rows)
    tied = [row for row in rows if sequence(row) == newest]
    if len(tied) != 1:
        return None
    row = tied[0]
    generated = _dict(_dict(_dict(row.get('data')).get('binding')).get('generated')).get(object_id)
    digest = _text(_dict(generated).get('manifest_sha256'))
    return (row['artifact_id'], digest) if digest else None


def _edges(read, nodes, status, scope, intent, operation, delivery):
    by_id = {node['id']: node for node in nodes}
    edges = []
    artifact = _text(intent.get('artifact_id'))
    if status is not None and artifact and by_id['atmos.component']['identity']['stack'] \
            and by_id['atmos.component']['identity']['component']:
        # The intent names the stack and component it was read from; it is stale when the repository moved on since.
        edges.append(_edge('cites', 'repo.source', 'atmos.component',
                           _basis(RECORD_INTENT, 'scope.stack, scope.component', artifact), by_id['atmos.component']['state']))
    if status is not None and artifact and _text(scope.get('backend')):
        edges.append(_edge('cites', 'atmos.component', 'tofu.backend',
                           # The backend is named by the same intent and status as the component, so the link is as current
                           # as the component's reading of that intent; the backend node's own state is not the link's.
                           _basis(RECORD_INTENT, 'scope.backend', artifact), by_id['atmos.component']['state']))
    generated = _adoption_generated(read.get('adoptions'), read.get('object_id'))
    if generated:
        edges.append(_edge('generates', 'atmos.component', 'tofu.engine',
                           _basis(RECORD_ADOPTION, 'binding.generated.%s.manifest_sha256' % read['object_id'], generated[0]),
                           'recorded'))
    operation_id = _text(_dict(operation).get('operation_id'))
    by = _stages(delivery)
    execution = by.get('execution') if operation_id else None
    if execution and execution.get('status') in ('done', 'unknown'):
        if _text(execution.get('engine_status')):
            verified = execution['status'] == 'done' and execution['engine_status'] == 'succeeded_verified'
            edges.append(_edge('applies-through', 'tofu.engine', 'provider',
                               _basis(RECORD_DELIVERY, 'stages.execution.engine_status', operation_id),
                               'recorded' if verified else 'unverified'))
        if execution.get('service_status') is not None:
            edges.append(_edge('applies-through', 'provider', 'service',
                               _basis(RECORD_DELIVERY, 'stages.execution.service_status', operation_id),
                               'recorded' if execution['status'] == 'done' else 'unverified'))
    readback = by.get('readback') if operation_id else None
    if readback and readback.get('status') in ('done', 'pending', 'failed'):
        edges.append(_edge('reads-back', 'service', 'readback',
                           _basis(RECORD_DELIVERY, 'stages.readback.status', operation_id),
                           'recorded' if by_id['readback']['state'] == 'recorded' else 'unverified'))
    observation = by_id['observation']
    if observation['identity']['run_id'] is not None:
        edges.append(_edge('observes', 'service', 'observation',
                           _basis(RECORD_OBSERVATION, 'run_id', str(observation['identity']['run_id'])), observation['state']))
    return edges


# ---- the projection -------------------------------------------------------------------------------------------------

def project(read):
    """The system map of one policy.

    read: the read model's values for the policy, as `workbench._system_map_read` collects them: object_id, tenant_id, name,
      evidence_class; states (observation, intent, newest operation); repository_record (the newest intent's recorded
      sources, effective pointer and resource address, or None); setup_pins (the manifest's pinned setup context and
      integration label, or {'error_code': ...} when it could not be read, or None); adoptions (the policy's adoption
      records); delivery (the newest operation's, or {'error_code': ...}, or None).
    """
    read = _dict(read)
    object_id = read.get('object_id')
    if not isinstance(object_id, str) or not object_id:
        _fail('A system map needs a result that names its policy by identifier.')
    states = _dict(read.get('states'))
    status, scope, intent = _intent_reading(states)
    observation = states.get('observation') if isinstance(states.get('observation'), dict) else None
    operation = states.get('operation') if isinstance(states.get('operation'), dict) else None
    delivery = read.get('delivery') if isinstance(read.get('delivery'), dict) else None
    pinned, label, unread = _pins(read)
    built = {'repo.source': _repo_source(status, intent, read.get('repository_record')),
             'atmos.component': _atmos(status, scope, intent, pinned),
             'tofu.engine': _engine(pinned, unread), 'tofu.backend': _backend(status, scope, intent),
             'provider': _provider(pinned, unread), 'service': _service(observation, read, label),
             'readback': _readback(operation, delivery), 'observation': _observation(observation)}
    nodes = [built[identifier] for identifier in NODE_IDS]
    edges = _edges(read, nodes, status, scope, intent, operation, delivery)
    body = {'schema_version': SCHEMA, 'object_id': object_id, 'tenant_id': read.get('tenant_id'),
            'name': read.get('name') if isinstance(read.get('name'), str) else None,
            'evidence_class': _text(_dict(observation).get('evidence_class')) or _text(read.get('evidence_class')),
            'boundaries': [{'id': identifier, 'label': label_} for identifier, label_ in BOUNDARIES],
            'nodes': nodes, 'edges': edges,
            'operation': None if operation is None else {key: operation.get(key) for key in
                                                          ('operation_id', 'operation_root', 'journal_status') if key in operation},
            'read_only': True, 'execution_authorized': False, 'cloud_authority': False}
    revision = hashlib.sha256(_canonical(body).encode('utf-8')).hexdigest()
    return dict(body, revision=revision)
