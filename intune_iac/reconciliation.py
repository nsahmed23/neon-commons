"""Independent current-state reconciliation; no retry or lock-release authority."""
from __future__ import annotations

from . import execution
from .io import AppError, digest


def reconcile_operation(operation_id, state_dir, *, adapter=None):
    """Compare current facet hashes to saved boundaries without inferring history.

    A currently matching precondition cannot prove a remote effect never happened.
    A desired state cannot prove which actor caused it. No result replays an action
    or unlocks a target; missing readback and corrupt evidence remain unknown.
    """
    result = {'version': '1.0.0', 'classification': 'unknown', 'assurance': 'local_simulation_only',
              'retry_authorized': False, 'lock_released': False, 'facets': {name: 'unknown' for name in execution.FACETS}}
    if type(adapter) is not execution.LocalFixtureAdapter:
        result['reason'] = 'qualified_adapter_absent'; return result
    try:
        journal = execution.read_operation(operation_id, state_dir)
        prepared = journal['events'][0]
        initial = prepared['initial_hashes']; desired = prepared['desired_hashes']
        execution._facet_hashes(initial); execution._facet_hashes(desired)
        if prepared['binding'] != adapter.binding():
            result['reason'] = 'binding_changed'; return result
        request = execution.prepare_operation(adapter, operation_id)
        if initial != request['before'] or desired != request['after'] or prepared['request_sha256'] != digest(request):
            result['reason'] = 'request_mismatch'; return result
        # A retained lock must name this exact operation; never reinterpret another
        # operation's effects using a consistent but unrelated saved receipt.
        if adapter.lock_path.exists():
            owner = execution._read_local(adapter.lock_path / 'owner.json')
            expected = {'operation_id': operation_id, 'request_sha256': digest(request),
                        'state_path_sha256': digest(str(execution._path(state_dir)))}
            if owner != expected:
                result['reason'] = 'lock_owner_mismatch'; return result
        observed = adapter.readback(); execution._facet_hashes(observed)
        for name in execution.FACETS:
            if initial[name] == desired[name] == observed[name]: result['facets'][name] = 'unchanged'
            elif observed[name] == desired[name]: result['facets'][name] = 'desired'
            elif observed[name] == initial[name]: result['facets'][name] = 'precondition'
            else: result['facets'][name] = 'diverged'
        states = set(result['facets'].values())
        if 'diverged' in states: result['classification'] = 'diverged'
        elif states <= {'desired', 'unchanged'}: result['classification'] = 'desired_state_observed'
        elif states <= {'precondition', 'unchanged'}: result['classification'] = 'matches_precondition'
        else: result['classification'] = 'partial_effects_observed'
        result['journal_sha256'] = journal['journal_sha256']
        result['observation_sha256'] = digest(observed)
        result['reason'] = 'current_observation_does_not_authorize_replay'
    except (AppError, OSError, ValueError, TypeError, KeyError, RuntimeError):
        result['reason'] = 'missing_invalid_or_unreadable_evidence'
    return result
