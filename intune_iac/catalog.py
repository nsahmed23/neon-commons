"""The integration catalog: what this build holds, built from recorded facts only.

One record per integration in the capability manifest (today one: Intune). For each goal the record keeps six states
apart, because a fresh engineer must be able to tell them apart:

    available        this build implements the goal for the integration (the manifest lists its operations)
    configured       the local inputs the goal needs are present (readiness rows for mode, tools, repository, IaC target
                     and backend); the service, execution route and secret rows are not "configuration" and stay out
    authenticated    a usable existing sign-in, only when the engineer asked for the check (signin verdict); otherwise
                     "not checked". A sign-in is never permission for an operation.
    operation-ready  the readiness model's status for the goal is ready
    blocked          the first prerequisite the readiness model reports as not ready, with its next action
    unsupported      an operation the manifest does not list, plus the live blockers and live status as recorded

An object kind shows a qualification word only where the manifest's level record establishes it; otherwise it reads
"unknown (no record establishes it)". Nothing is inferred from a family name, and nothing the manifest does not hold is
listed. The module reads no network, no credential and no environment value; the sign-in verdict is given to it.
"""
from __future__ import annotations

from . import integration_manifest, readiness as readiness_model

VERSION = 'integration-catalog/1'
STATES = ('available', 'configured', 'authenticated', 'operation_ready', 'blocked', 'unsupported')
UNKNOWN_LEVEL = 'unknown (no record establishes it)'
NO_OTHERS = 'No other integration is available in this build.'
# The product's own reading of each goal as manifest operation names. It is a mapping of words, not a claim about
# qualification; a goal whose operations the manifest does not list is reported unsupported.
GOAL_OPERATIONS = {
    'inspect': ('inventory', 'selection', 'validation'),
    'discover': ('discovery',),
    'adopt': ('ownership', 'mapping', 'adoption'),
    'change': ('plan', 'approval', 'execute', 'reconcile'),
}
# Readiness rows that are local inputs; the service, execution route and secret rows are not configuration.
CONFIGURATION_ROWS = ('mode_goal', 'tools_host', 'repository', 'iac_target', 'backend')
SIGNIN_CHECK = ('Sign-in is not checked. Run: intune-iac catalog %s--check-signin azure (it runs az account list '
                '--output json and nothing else, and reads no token).')
NOT_PERMISSION = 'A sign-in is not permission for any operation; access to Graph, Intune and state storage is not established.'


def _available(manifest, goal):
    listed = {}
    for kind in manifest['object_kinds']:
        for operation in kind['operations']:
            listed.setdefault(operation['name'], set()).add(operation['evidence_class'])
    wanted = GOAL_OPERATIONS[goal]
    present = [name for name in wanted if name in listed]
    missing = [name for name in wanted if name not in listed]
    classes = sorted({cls for name in present for cls in listed[name]})
    kinds = [kind['id'] for kind in manifest['object_kinds']
             if any(operation['name'] in wanted for operation in kind['operations'])]
    state = 'available' if wanted and not missing else 'not_available'
    return {'state': state, 'operations': present, 'missing_operations': missing, 'evidence_classes': classes,
            'object_kinds': kinds}


def _configured(operation):
    rows = [row for row in operation['rows'] if row['needed'] and row['id'] in CONFIGURATION_ROWS]
    lacking = [row['label'] for row in rows if row['state'] != 'ready']
    if any(row['state'] == 'missing' for row in rows):
        state = 'no'
    elif lacking:
        state = 'unknown'
    else:
        state = 'yes'
    return {'state': state, 'inputs_checked': [row['label'] for row in rows], 'not_ready': lacking}


def _authenticated(signin, goal_flag):
    verdict = (signin or {}).get('azure')
    if not verdict:
        return {'state': 'not_checked', 'message': SIGNIN_CHECK % goal_flag, 'permission': NOT_PERMISSION}
    status = verdict.get('status')
    if verdict.get('usable') is True:
        state = 'authenticated'
    elif status == 'unknown':
        state = 'unknown'
    else:
        state = 'not_authenticated'
    return {'state': state, 'status': status, 'message': verdict.get('message'), 'next_step': verdict.get('next_step'),
            'permission': NOT_PERMISSION}


def _blocked(operation):
    for row in operation['rows']:
        if row['needed'] and row['state'] != 'ready':
            return {'state': 'blocked', 'row': row['label'], 'row_state': row['state'],
                    'missing': row['missing'][0] if row['missing'] else None, 'next_action': row['next_action']}
    return {'state': 'not_blocked', 'row': None, 'row_state': None, 'missing': None, 'next_action': None}


def _unsupported(available, manifest):
    reasons = ['The manifest lists no %s operation for any object kind.' % name for name in available['missing_operations']]
    return {'state': 'unsupported' if reasons else 'none_recorded', 'reasons': reasons,
            'live_blockers': list(manifest['live_blockers'])}


def _goal(manifest, model, signin, goal, flag):
    operation = model['operations'][goal]
    available = _available(manifest, goal)
    return {'goal': goal, 'available': available, 'configured': _configured(operation),
            'authenticated': _authenticated(signin, flag),
            'operation_ready': {'state': 'yes' if operation['status'] == 'ready' else 'no', 'status': operation['status']},
            'blocked': _blocked(operation), 'unsupported': _unsupported(available, manifest)}


def _kind(manifest, kind):
    classes = sorted({operation['evidence_class'] for operation in kind['operations']})
    record = kind['level_record']
    return {'id': kind['id'], 'label': kind['label'], 'family': kind['family'],
            'level': kind['level'] if record else UNKNOWN_LEVEL, 'level_record': record['path'] if record else None,
            'scope': kind['level_note'], 'evidence_classes': classes,
            'operations': [operation['name'] for operation in kind['operations']]}


def _family(entry):
    live = entry['live']
    return {'family': entry['family'], 'release_stage': entry['release_stage'] or 'not recorded',
            'live': 'not run' if live == 'not_run' else (live.replace('_', ' ') if live else 'not recorded'),
            'object_kind': entry['object_kind']}


def build(survey, doctor=None, signin=None, manifest=None, goal=None):
    """The catalog as plain data. `survey` is entry.survey's result; `doctor` the doctor result (default: the offline
    one that looks up no executable); `signin` the detect result when the engineer asked for the check."""
    manifest = manifest if manifest is not None else integration_manifest.load()
    if doctor is None:
        from . import cli
        doctor = cli.doctor(executables=False)
    model = readiness_model.readiness(survey, doctor.get('host_capabilities'), doctor, signin=signin)
    flag = '' if goal is None else '--goal %s ' % goal
    goals = [goal] if goal else list(readiness_model.OPERATIONS)
    integration = manifest['integration']
    record = {'id': integration['id'], 'label': integration['label'], 'product': integration['product'],
              'product_version': integration['product_version'],
              'goals': [_goal(manifest, model, model.get('signin'), name, flag) for name in goals],
              'object_kinds': [_kind(manifest, kind) for kind in manifest['object_kinds']],
              'families': [_family(entry) for entry in manifest['families']],
              'live_blockers': list(manifest['live_blockers'])}
    return {'schema_version': VERSION, 'directory': survey.get('directory') if isinstance(survey, dict) else None,
            'integrations': [record], 'other_integrations': NO_OTHERS, 'signin_checked': bool(model.get('signin')),
            'execution_authorized': False, 'cloud_authority': False}
