"""Presentation-only responses for the four routes that link a protected record into the persistent views: service-link,
adoption-link, evidence-link and evidence-history.

The rendered-surface sweep (test_rendered_surfaces) feeds them through the workspace, as it feeds the review, status, attach, cancel
and recover responses, so the text a person reads after one of these commands is judged like every other screen. They are for the
presentation boundary only: the real journals behind the links need the pinned docker and a TLS probe built with gcc, and the signed
evidence needs a verifier and a trust policy; none of that is needed to draw the response.

Each response has the shape the product produces. The three links are the rows the product's own store writes: the data is the dict
that workbench_service_views.link, workbench_adoption_views.link and workbench_evidence_views.link record, handed to the real
WorkbenchStore.record_artifact, whose return value is the response. The history of received evidence is the real
workbench_evidence_views.history (the envelope, and the row of an entry whose evidence cannot be reopened); only the entry that
reopening would give is written here, in the shape of workbench_evidence_views.proposed. shape_problems() compares every shape written
here with the dict literal of the product function that writes it, so a key added or dropped there fails a test instead of leaving
this module describing a response that no longer exists.
"""
import ast
import inspect
import textwrap
from unittest.mock import patch

TENANT = '11111111-1111-4111-8111-111111111111'
OBJECT = '22222222-2222-4222-8222-222222222222'
OPERATION = 'service-op-12071'
MANIFEST = 'a' * 64
PLAN = 'c' * 64
REQUEST = 'b' * 64
BUNDLE = 'd' * 64


def literal_keys(function, marker):
    """The keys of the dict literal in a product function that holds the key `marker`: the shape the function writes."""
    for node in ast.walk(ast.parse(textwrap.dedent(inspect.getsource(function)))):
        if isinstance(node, ast.Dict) and any(isinstance(key, ast.Constant) and key.value == marker for key in node.keys):
            return {key.value for key in node.keys if isinstance(key, ast.Constant)}
    raise LookupError('%s writes no dict with the key %r' % (function.__name__, marker))


def service_data(store, job_root, policy_path):
    from intune_iac import workbench_service_views as views
    return {'schema_version': 'workbench-service-link/1', 'tenant_id': store.tenant_id, 'target_object_id': OBJECT,
            'job_root': job_root, 'policy_path': policy_path, 'operation_id': OPERATION, 'manifest_sha256': MANIFEST,
            'evidence_class': views.KIND, 'baseline_admissible': False, 'cloud_authority': False, 'execution_authorized': False}


def adoption_data(store, job_root, policy_path):
    from intune_iac import workbench_adoption_views as views
    return {'schema_version': 'workbench-protected-adoption-link/1', 'tenant_id': store.tenant_id, 'target_object_id': OBJECT,
            'job_root': job_root, 'policy_path': policy_path, 'operation_id': 'adoption-op-12072', 'manifest_sha256': MANIFEST,
            'evidence_class': views.KIND, 'state_only_adoption': True, 'graph_deployment': False,
            'last_apply_baseline_promoted': False, 'baseline_admissible': False, 'cloud_authority': False,
            'execution_authorized': False}


def evidence_data(store, evidence_store, trust_path, verifier_path, scratch, request=REQUEST):
    from intune_iac import workbench_evidence_views as views
    return {'schema_version': 'workbench-worker-evidence-link/1', 'tenant_id': store.tenant_id, 'target_object_id': OBJECT,
            'evidence_class': views.KIND, 'evidence_store': evidence_store, 'request_sha256': request, 'trust_path': trust_path,
            'verifier_path': verifier_path, 'scratch': scratch, 'bundle_sha256': BUNDLE, 'operation_id': OPERATION,
            'manifest_sha256': MANIFEST, 'baseline_admissible': False, 'cloud_authority': False, 'execution_authorized': False}


def evidence_entry(row, note=None):
    """One entry of the history as workbench_evidence_views.proposed gives it for evidence that reopens."""
    risks = ['Signed local evidence is not live CI, native platform or organization approval.',
             'Historical-only evidence cannot establish current worker status or an active comparison baseline.']
    status = {'status': 'completed_verified', 'dispatches': 1, 'cancel_requested': False, 'outcome': None}
    return {'status': 'recorded', 'evidence_class': 'signed_worker_evidence_review', 'link_artifact_id': row['artifact_id'],
            'operation_id': OPERATION, 'saved_plan_sha256': PLAN, 'approval_digest': MANIFEST,
            'target': {'tenant_id': TENANT, 'object_id': OBJECT},
            'review': {'manifest_sha256': MANIFEST, 'action': 'apply_saved_plan', 'profile': 'native_docker_laboratory_tls',
                       'expires_at': 1791500000},
            'journal_status': 'completed_verified', 'service_journal': status,
            'run_context': {'repository_revision': 'f' * 40, 'stack': 'orgs/reference/dev'},
            'evidence': {'operation_id': OPERATION, 'bundle_sha256': BUNDLE, 'manifest_sha256': MANIFEST, 'historical_only': False,
                         'baseline_admissible': False, 'worker_status': 'completed_verified', 'journal_snapshot': status,
                         'proof': {'plan_sha256': PLAN}, 'snapshot_read_at': 1791400000},
            'platform_qualified': False, 'execution_authorized': False,
            'unresolved_risks': risks if note is None else [note] + risks}


def history(store, rows, note=None):
    """The real workbench_evidence_views.history over the link rows already recorded: the first row reopens (the entry above), the
    others cannot (the real unavailable row, with the error the product gives when the evidence is not where the link says)."""
    from intune_iac import workbench_evidence_views as views
    real = views.proposed

    def proposed(held, row):
        return evidence_entry(row, note) if row['artifact_id'] == rows[0]['artifact_id'] else real(held, row)
    with patch.object(views, 'proposed', proposed):
        return views.history(store, OBJECT)


def refusal(code, message):
    from intune_iac.io import AppError
    from intune_iac.workbench import _error_result
    return _error_result(AppError(code, message))


def responses(store, job_root, policy_path, folder, inject=None):
    """[(route, variant, command line, response)] for the four routes. inject: a text that replaces the one string field each response
    shows in full (for a test that a command in a response is read)."""
    import shlex
    from intune_iac import workbench_adoption_views, workbench_evidence_views, workbench_service_views
    shown = lambda value: inject if inject else value
    quote = shlex.quote
    evidence = [str(folder / name) for name in ('evidence store', 'trust policy.json', 'verifier', 'private scratch')]
    found = []
    service = service_data(store, job_root, shown(policy_path))
    first = store.record_artifact('deployment_receipt', None, service)
    found += [('service-link', 'a new link', 'service-link %s %s' % (quote(job_root), quote(policy_path)), first),
              ('service-link', 'a link already recorded', 'service-link %s %s' % (quote(job_root), quote(policy_path)),
               store.record_artifact('deployment_receipt', None, service))]
    found.append(('adoption-link', 'a new link', 'adoption-link %s %s' % (quote(job_root), quote(policy_path)),
                  store.record_artifact('adoption_receipt', None, adoption_data(store, job_root, shown(policy_path)))))
    links = [store.record_artifact('deployment_receipt', None, evidence_data(store, *evidence[:3], shown(evidence[3]), request=request))
             for request in (REQUEST, 'e' * 64)]
    found.append(('evidence-link', 'a new link', 'evidence-link ' + ' '.join(quote(item) for item in [evidence[0], REQUEST] + evidence[1:]),
                  links[0]))
    found.append(('evidence-history', 'one entry reopens, one cannot', 'evidence-history', history(store, links, shown(None))))
    found.append(('adoption-history', 'one linked operation that cannot be reopened', 'adoption-history',
                  workbench_adoption_views.history(store, OBJECT)))
    for route, command, code, module in (
            ('service-link', 'service-link %s %s', 'workbench_service_identity', workbench_service_views),
            ('adoption-link', 'adoption-link %s %s', 'workbench_adoption_identity', workbench_adoption_views),
            ('evidence-link', 'evidence-link %s %s', 'workbench_evidence_identity', workbench_evidence_views)):
        try:
            module._fail(code)
        except Exception as error:
            found.append((route, 'refused: ' + code, command % (quote(job_root), quote(policy_path)), refusal(error.code, error.message)))
    found.append(('evidence-history', 'refused: no object selected', 'evidence-history',
                  refusal('selection_required', 'Select an exact immutable object ID first.')))
    return found


def shape_problems(store):
    """What differs between the shapes written here and the product functions that write them: [] when they agree."""
    from intune_iac import workbench_adoption_views as adoption
    from intune_iac import workbench_evidence_views as evidence
    from intune_iac import workbench_service_views as service
    problems = []
    for name, data, function in (('service-link', service_data(store, 'j', 'p'), service.link),
                                 ('adoption-link', adoption_data(store, 'j', 'p'), adoption.link),
                                 ('evidence-link', evidence_data(store, 'e', 't', 'v', 's'), evidence.link)):
        if set(data) != literal_keys(function, 'schema_version'):
            problems.append('%s records %s, the fixture writes %s' % (name, sorted(literal_keys(function, 'schema_version')), sorted(data)))
    entry = evidence_entry({'artifact_id': 'x'})
    if set(entry) != literal_keys(evidence.proposed, 'link_artifact_id'):
        problems.append('proposed gives %s, the fixture writes %s' % (sorted(literal_keys(evidence.proposed, 'link_artifact_id')), sorted(entry)))
    return problems
