"""The system map's projection (requirement 17 UX-VIS, PKG-UXVIS-6A): one selected policy's deployment path.

`intune_iac.system_map_projection` (schema system-map/1) is pure, so most cases pass it hand-built reads that change one
recorded field at a time. Each node and each edge is tested against the record that establishes it: every state it can
take and the case where the record is absent (the node stays, unknown or not configured; the edge is absent). The cases
that need real records run the real store, the modeled service and the maintenance engine over temporary directories,
through the read model's additive fields (`workbench._system_map_read`).
"""
import copy
import unittest

from plugin_tests import test_workbench_repository as repository_tests
from plugin_tests import test_workflow_map as flow_tests

OBJECT = repository_tests.OBJECT
NODE_IDS = ['repo.source', 'atmos.component', 'tofu.engine', 'tofu.backend', 'provider', 'service', 'readback', 'observation']
STATES = {'recorded', 'configured', 'not_configured', 'unknown', 'stale', 'unverified'}
PINS = {'pinned': {'engine': 'tofu', 'engine_version': '9.9.9', 'atmos_version': '8.8.8',
                   'provider_source': 'example/provider', 'provider_version': '7.7.7'},
        'integration_label': 'Example Service'}
RECORD = {'artifact_id': 'e927410221924400' + '0' * 48, 'effective_pointer': '/vars/policies/key',
          'resource_address': 'example_resource.policy', 'sources': [{'path': 'stacks/dev.yaml'}, {'path': 'stacks/base.yaml'}]}


def baseline():
    """A policy with a fresh complete observation, a current repository intent naming a backend, the manifest's pins and
    nothing else recorded."""
    read = flow_tests.baseline()
    read['states']['intent']['scope'] = {'repository': '/repo', 'stack': 'orgs/reference/dev', 'component': 'intune-reference',
                                         'backend': 'local'}
    read['repository_record'] = copy.deepcopy(RECORD)
    read['setup_pins'] = copy.deepcopy(PINS)
    return read


def project(read):
    from intune_iac.system_map_projection import project as run
    return run(read)


def nodes_of(flow):
    return {node['id']: node for node in flow['nodes']}


def edges_of(flow):
    return {edge['id']: edge for edge in flow['edges']}


def states_of(flow):
    return {node['id']: node['state'] for node in flow['nodes']}


def with_intent(read, **changes):
    read = copy.deepcopy(read)
    read['states']['intent'].update(changes)
    return read


def without_intent(read):
    read = copy.deepcopy(read)
    read['states']['intent'] = {'status': 'none'}
    read['repository_record'] = None
    return read


def with_observation(read, **changes):
    read = copy.deepcopy(read)
    read['states']['observation'].update(changes)
    return read


def operation_read(outcome):
    """The baseline plus a newest operation: 'prepared', 'verified', 'unknown' or 'reconciled'."""
    if outcome == 'prepared':
        return flow_tests.with_operation(baseline())
    delivery = flow_tests.executed_delivery(outcome)
    journal = {'verified': 'succeeded_verified', 'unknown': 'outcome_unknown', 'reconciled': 'reconciled'}[outcome]
    return flow_tests.with_operation(baseline(), delivery=delivery, journal=journal)


def with_adoption(read):
    read = copy.deepcopy(read)
    read['adoptions'] = [{'artifact_id': 'a1b2c3d4' + '0' * 56, 'sequence': 3,
                          'data': {'binding': {'generated': {OBJECT: {'path': '/g/' + OBJECT, 'manifest_sha256': 'c' * 64}}}}}]
    return read


class ShapeTests(unittest.TestCase):
    def test_the_nodes_are_the_fixed_ids_in_order_inside_three_named_boundaries(self):
        flow = project(baseline())
        self.assertEqual(flow['schema_version'], 'system-map/1')
        self.assertEqual([node['id'] for node in flow['nodes']], NODE_IDS)
        self.assertEqual([item['id'] for item in flow['boundaries']], ['host', 'repository', 'cloud'])
        self.assertEqual([item['label'] for item in flow['boundaries']], ['this host', 'the repository', 'the cloud'])
        self.assertEqual({node['boundary'] for node in flow['nodes']}, {'host', 'repository', 'cloud'})
        for node in flow['nodes']:
            self.assertEqual(set(node), {'id', 'kind', 'boundary', 'layer', 'state', 'identity', 'basis', 'reason', 'facts', 'opens'})
            self.assertIn(node['state'], STATES)
            self.assertEqual(set(node['basis']), {'record', 'field', 'record_id'})
        self.assertEqual({node['id']: node['boundary'] for node in flow['nodes']},
                         {'repo.source': 'repository', 'atmos.component': 'repository', 'tofu.engine': 'host',
                          'tofu.backend': 'host', 'provider': 'host', 'service': 'cloud', 'readback': 'host',
                          'observation': 'host'})

    def test_the_layers_follow_the_deployment_path_and_never_a_state(self):
        layers = {node['id']: node['layer'] for node in project(baseline())['nodes']}
        self.assertEqual(layers, {'repo.source': 0, 'atmos.component': 1, 'tofu.engine': 2, 'tofu.backend': 2, 'provider': 3,
                                  'service': 4, 'readback': 5, 'observation': 5})

    def test_the_projection_is_read_only_and_names_the_policy(self):
        flow = project(baseline())
        self.assertEqual((flow['read_only'], flow['execution_authorized'], flow['cloud_authority']), (True, False, False))
        self.assertEqual((flow['object_id'], flow['name']), (flow_tests.OBJECT, 'Windows Privacy Pilot'))

    def test_the_same_inputs_give_the_same_revision_and_any_changed_record_gives_a_new_one(self):
        base = project(baseline())
        self.assertEqual(project(baseline())['revision'], base['revision'])
        self.assertRegex(base['revision'], '^[0-9a-f]{64}$')
        for changed in (with_intent(baseline(), source_revision='c' * 40), with_intent(baseline(), status='changed'),
                        with_observation(baseline(), freshness='stale'), with_adoption(baseline()), without_intent(baseline())):
            self.assertNotEqual(project(changed)['revision'], base['revision'])
        pins = baseline()
        pins['setup_pins']['pinned']['engine_version'] = '9.9.8'
        self.assertNotEqual(project(pins)['revision'], base['revision'])

    def test_the_revision_is_the_digest_of_the_whole_canonical_projection(self):
        import hashlib
        import json
        for read in (baseline(), with_adoption(operation_read('verified')), operation_read('unknown'), without_intent(baseline())):
            flow = project(read)
            body = {key: value for key, value in flow.items() if key != 'revision'}
            canonical = json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False, default=str)
            self.assertEqual(flow['revision'], hashlib.sha256(canonical.encode('utf-8')).hexdigest())

    def test_the_node_kinds_are_fixed(self):
        self.assertEqual({node['id']: node['kind'] for node in project(baseline())['nodes']},
                         {'repo.source': 'repository_source', 'atmos.component': 'atmos_component', 'tofu.engine': 'opentofu',
                          'tofu.backend': 'backend', 'provider': 'provider', 'service': 'service', 'readback': 'readback',
                          'observation': 'observation'})

    def test_the_operation_and_the_evidence_class_are_the_recorded_ones(self):
        self.assertIsNone(project(baseline())['operation'])
        flow = project(operation_read('verified'))
        self.assertIsNotNone(flow['operation'])
        self.assertEqual(flow['operation']['operation_id'], flow_tests.OPERATION)
        self.assertEqual(flow['operation']['journal_status'], 'succeeded_verified')
        read = with_observation(baseline(), evidence_class='observation_class')
        read['evidence_class'] = 'read_class'
        self.assertEqual(project(read)['evidence_class'], 'observation_class')
        read['states']['observation'] = None
        self.assertEqual(project(read)['evidence_class'], 'read_class')

    def test_an_unnamed_policy_is_refused(self):
        from intune_iac.io import AppError
        for read in ({}, None, {'object_id': ''}, {'object_id': 3}):
            with self.assertRaises(AppError) as caught:
                project(read)
            self.assertEqual(caught.exception.code, 'system_map_projection_invalid')


class RepositoryNodeTests(unittest.TestCase):
    """repo.source reads the repository intent (status, source_revision, the recorded resolution's sources)."""

    def test_the_recorded_revision_and_source_files_are_the_identity(self):
        node = nodes_of(project(baseline()))['repo.source']
        self.assertEqual((node['state'], node['reason']), ('recorded', None))
        self.assertEqual(node['identity'], {'revision': 'b' * 40, 'source_files': ['stacks/dev.yaml', 'stacks/base.yaml']})
        self.assertEqual(node['basis']['record'], 'repository_intent')
        self.assertEqual(node['basis']['record_id'], baseline()['states']['intent']['artifact_id'])
        self.assertEqual(node['opens'], '9')
        self.assertEqual(node['facts'], {'recorded_at': '2026-10-14T19:50:01.000001Z',
                                         'effective_pointer': '/vars/policies/key'})

    def test_a_source_row_without_a_path_is_not_a_source_file(self):
        read = baseline()
        read['repository_record']['sources'] = [{'path': 'stacks/dev.yaml'}, {'sha256': 'x'}, 'text', {'path': ''}, None]
        try:
            flow = project(read)
        except Exception as error:      # a malformed row must be skipped, not raise
            self.fail('a source row without a path raised %r' % error)
        self.assertEqual(nodes_of(flow)['repo.source']['identity']['source_files'], ['stacks/dev.yaml'])

    def test_every_state_the_intent_status_can_take(self):
        table = {'current': ('recorded', None), 'changed': ('stale', 'repository_stale'),
                 'consumer_changed': ('recorded', None), 'unreadable': ('unknown', 'repository_unavailable'),
                 'not_checked': ('unverified', 'not_checked')}
        for status, expected in table.items():
            node = nodes_of(project(with_intent(baseline(), status=status)))['repo.source']
            self.assertEqual((node['state'], node['reason']), expected, status)

    def test_a_status_the_producer_does_not_define_is_unknown_with_that_word(self):
        node = nodes_of(project(with_intent(baseline(), status='odd')))['repo.source']
        self.assertEqual((node['state'], node['reason']), ('unknown', 'odd'))

    def test_a_revision_that_was_not_recorded_is_unknown(self):
        node = nodes_of(project(with_intent(baseline(), source_revision=None)))['repo.source']
        self.assertEqual((node['state'], node['reason']), ('unknown', 'revision_not_recorded'))

    def test_no_intent_is_a_node_that_is_not_configured_never_omitted(self):
        for read in (without_intent(baseline()), with_intent(baseline(), status=None)):
            flow = project(read)
            node = nodes_of(flow)['repo.source']
            self.assertEqual((node['state'], node['reason']), ('not_configured', 'no_repository_intent'))
            self.assertEqual(node['identity'], {'revision': None, 'source_files': []})
            self.assertIn('repo.source', [item['id'] for item in flow['nodes']])

    def test_an_intent_whose_resolution_was_not_carried_has_no_source_files_and_keeps_its_revision(self):
        read = baseline()
        read['repository_record'] = None
        node = nodes_of(project(read))['repo.source']
        self.assertEqual((node['state'], node['identity']), ('recorded', {'revision': 'b' * 40, 'source_files': []}))


class AtmosNodeTests(unittest.TestCase):
    """atmos.component reads the intent's scope (stack, component) and status."""

    def test_the_recorded_stack_and_component_are_the_identity_with_the_pinned_atmos_version_as_a_fact(self):
        node = nodes_of(project(baseline()))['atmos.component']
        self.assertEqual((node['state'], node['identity']), ('recorded', {'stack': 'orgs/reference/dev', 'component': 'intune-reference'}))
        self.assertEqual(node['facts'], {'pinned_atmos_version': '8.8.8'})

    def test_every_state_the_intent_status_can_take(self):
        table = {'current': ('recorded', None), 'changed': ('stale', 'repository_stale'),
                 'consumer_changed': ('stale', 'repository_consumer_mismatch'),
                 'unreadable': ('unknown', 'repository_unavailable'), 'not_checked': ('unverified', 'not_checked')}
        for status, expected in table.items():
            node = nodes_of(project(with_intent(baseline(), status=status)))['atmos.component']
            self.assertEqual((node['state'], node['reason']), expected, status)

    def test_a_scope_missing_its_stack_or_component_is_unknown(self):
        for key in ('stack', 'component'):
            read = baseline()
            del read['states']['intent']['scope'][key]
            node = nodes_of(project(read))['atmos.component']
            self.assertEqual((node['state'], node['reason']), ('unknown', 'scope_incomplete'), key)

    def test_no_intent_is_not_configured(self):
        node = nodes_of(project(without_intent(baseline())))['atmos.component']
        self.assertEqual((node['state'], node['reason'], node['identity']),
                         ('not_configured', 'no_repository_intent', {'stack': None, 'component': None}))

    def test_nothing_is_taken_from_the_name_of_the_stack(self):
        read = baseline()
        read['states']['intent']['scope'].update(stack='prod-looking-name', component='x')
        node = nodes_of(project(read))['atmos.component']
        self.assertEqual((node['state'], node['identity']['stack']), ('recorded', 'prod-looking-name'))


class BackendNodeTests(unittest.TestCase):
    """tofu.backend reads the intent's scope.backend."""

    def test_a_named_backend_is_recorded(self):
        node = nodes_of(project(baseline()))['tofu.backend']
        self.assertEqual((node['state'], node['identity']), ('recorded', {'backend': 'local'}))
        self.assertEqual(node['basis']['field'], 'scope.backend')
        self.assertEqual(node['basis']['record_id'], baseline()['states']['intent']['artifact_id'])

    def test_an_intent_that_names_no_backend_is_not_configured(self):
        read = baseline()
        del read['states']['intent']['scope']['backend']
        node = nodes_of(project(read))['tofu.backend']
        self.assertEqual((node['state'], node['reason']), ('not_configured', 'backend_not_named'))

    def test_no_intent_is_not_configured(self):
        node = nodes_of(project(without_intent(baseline())))['tofu.backend']
        self.assertEqual((node['state'], node['reason']), ('not_configured', 'no_repository_intent'))

    def test_a_repository_that_moved_on_does_not_change_the_backend_the_intent_recorded(self):
        for status in ('changed', 'consumer_changed', 'unreadable', 'not_checked'):
            node = nodes_of(project(with_intent(baseline(), status=status)))['tofu.backend']
            self.assertEqual(node['state'], 'recorded', status)


class ManifestNodeTests(unittest.TestCase):
    """tofu.engine and provider read the integration manifest's pinned setup context."""

    def test_pinned_values_are_configured(self):
        nodes = nodes_of(project(baseline()))
        self.assertEqual((nodes['tofu.engine']['state'], nodes['tofu.engine']['identity']),
                         ('configured', {'engine': 'tofu', 'version': '9.9.9'}))
        self.assertEqual((nodes['provider']['state'], nodes['provider']['identity']),
                         ('configured', {'source': 'example/provider', 'version': '7.7.7'}))
        self.assertEqual(nodes['tofu.engine']['basis']['record'], 'integration_manifest')
        self.assertEqual((nodes['tofu.engine']['opens'], nodes['provider']['opens']), (None, None))

    def test_a_manifest_that_could_not_be_read_is_unknown_with_its_code_and_nothing_else_changes(self):
        read = baseline()
        read['setup_pins'] = {'error_code': 'integration_manifest_unreadable'}
        flow = project(read)
        nodes = nodes_of(flow)
        for name in ('tofu.engine', 'provider'):
            self.assertEqual((nodes[name]['state'], nodes[name]['reason']), ('unknown', 'integration_manifest_unreadable'))
        self.assertEqual(states_of(flow)['repo.source'], 'recorded')
        read['setup_pins'] = None
        self.assertEqual(nodes_of(project(read))['provider']['reason'], 'setup_pins_not_read')

    def test_a_pin_the_manifest_does_not_hold_is_not_configured(self):
        read = baseline()
        del read['setup_pins']['pinned']['engine_version']
        node = nodes_of(project(read))['tofu.engine']
        self.assertEqual((node['state'], node['reason']), ('not_configured', 'engine_pin_not_recorded'))
        read['setup_pins']['pinned'].pop('provider_source')
        read['setup_pins']['pinned'].pop('provider_version')
        node = nodes_of(project(read))['provider']
        self.assertEqual((node['state'], node['reason']), ('not_configured', 'provider_pin_not_recorded'))

    def test_an_engine_pin_needs_both_its_name_and_its_version(self):
        read = baseline()
        del read['setup_pins']['pinned']['engine']
        node = nodes_of(project(read))['tofu.engine']
        self.assertEqual((node['state'], node['reason'], node['identity']),
                         ('not_configured', 'engine_pin_not_recorded', {'engine': None, 'version': '9.9.9'}))

    def test_half_a_provider_pin_is_unknown_not_configured(self):
        read = baseline()
        del read['setup_pins']['pinned']['provider_version']
        node = nodes_of(project(read))['provider']
        self.assertEqual((node['state'], node['reason'], node['identity']),
                         ('unknown', 'provider_pin_incomplete', {'source': 'example/provider', 'version': None}))


class ServiceAndObservationTests(unittest.TestCase):
    """service reads the latest observation's evidence class; observation reads its freshness and coverage."""

    def test_the_service_shows_the_manifests_label_and_the_observations_evidence_class(self):
        node = nodes_of(project(baseline()))['service']
        self.assertEqual((node['state'], node['identity']), ('recorded', {'service': 'Example Service', 'evidence_class': 'synthetic'}))
        self.assertEqual((node['boundary'], node['opens']), ('cloud', '2'))

    def test_without_an_observation_both_are_unknown_and_present(self):
        read = baseline()
        read['states']['observation'] = None
        nodes = nodes_of(project(read))
        self.assertEqual((nodes['service']['state'], nodes['service']['reason']), ('unknown', 'no_observation'))
        self.assertEqual((nodes['observation']['state'], nodes['observation']['reason']), ('unknown', 'no_observation'))
        self.assertEqual(nodes['observation']['identity'], {'run_id': None, 'observed_at': None})

    def test_an_observation_that_states_no_evidence_class_leaves_the_service_unknown(self):
        node = nodes_of(project(with_observation(baseline(), evidence_class=None)))['service']
        self.assertEqual((node['state'], node['reason']), ('unknown', 'evidence_class_not_stated'))

    def test_every_state_the_observation_can_take(self):
        table = [({}, ('recorded', None)),
                 ({'freshness': 'stale', 'freshness_reasons': ['older_than_limit']}, ('stale', 'older_than_limit')),
                 ({'freshness': 'stale', 'freshness_reasons': []}, ('stale', 'stale')),
                 ({'eligibility': {'reason': 'service_changed'}}, ('stale', 'service_changed')),
                 ({'freshness': 'fresh', 'freshness_reasons': ['stamped_after_now']}, ('unknown', 'stamped_after_now')),
                 ({'freshness': None}, ('unknown', 'freshness_not_recorded')),
                 ({'freshness': 'unknown'}, ('unknown', 'unknown')),
                 ({'coverage': 'partial'}, ('unverified', 'coverage_partial')),
                 ({'coverage': None}, ('unverified', 'coverage_not_recorded'))]
        for changes, expected in table:
            node = nodes_of(project(with_observation(baseline(), **changes)))['observation']
            self.assertEqual((node['state'], node['reason']), expected, changes)

    def test_a_clock_hold_is_unknown_and_never_stale(self):
        from intune_iac.workbench_diagnostics import CLOCK_HOLD_REASONS
        for hold in CLOCK_HOLD_REASONS:
            read = with_observation(baseline(), freshness='stale', freshness_reasons=[hold])
            node = nodes_of(project(read))['observation']
            self.assertEqual((node['state'], node['reason']), ('unknown', hold))

    def test_the_identity_is_the_recorded_run_and_time(self):
        node = nodes_of(project(baseline()))['observation']
        self.assertEqual(node['identity'], {'run_id': 4, 'observed_at': '2026-10-14T19:55:52.390326Z'})
        self.assertEqual(node['basis']['record_id'], '4')
        self.assertEqual(node['facts'], {'coverage': 'complete', 'freshness': 'fresh'})


class ReadbackNodeTests(unittest.TestCase):
    """readback reads the newest operation's delivery stages readback and execution."""

    def test_no_operation_is_an_unknown_node_that_opens_nothing(self):
        node = nodes_of(project(baseline()))['readback']
        self.assertEqual((node['state'], node['reason'], node['opens']), ('unknown', 'no_operation', None))

    def test_a_prepared_operation_has_not_started_its_readback(self):
        node = nodes_of(project(operation_read('prepared')))['readback']
        self.assertEqual((node['state'], node['reason'], node['opens']), ('unknown', 'not_started', 'v'))
        self.assertEqual(node['basis']['record_id'], flow_tests.OPERATION)

    def test_a_verified_readback_is_recorded_with_its_classification(self):
        node = nodes_of(project(operation_read('verified')))['readback']
        self.assertEqual((node['state'], node['identity']['classification']), ('recorded', 'desired_state_observed'))
        self.assertEqual(node['facts'], {'second_plan': 'no_change'})

    def test_an_unknown_outcome_is_unknown_never_recorded(self):
        for outcome in ('unknown', 'reconciled'):
            node = nodes_of(project(operation_read(outcome)))['readback']
            self.assertEqual((node['state'], node['reason']), ('unknown', 'maintenance_service_incomplete'), outcome)

    def test_the_reason_of_an_unknown_outcome_is_the_error_code_the_execution_recorded_not_the_readback_status(self):
        for outcome in ('unknown', 'reconciled'):
            read = operation_read(outcome)
            self.assertEqual(read['delivery']['stages'][4]['status'], 'not_recorded')
            node = nodes_of(project(read))['readback']
            self.assertEqual(node['reason'], 'maintenance_service_incomplete', outcome)

    def test_a_pending_readback_is_unverified(self):
        read = operation_read('verified')
        read['delivery']['stages'][4] = flow_tests.stage_row('readback', 'pending', classification='matches_precondition')
        node = nodes_of(project(read))['readback']
        self.assertEqual((node['state'], node['reason']), ('unverified', 'visibility_pending'))

    def test_a_classification_execute_does_not_verify_with_is_unverified(self):
        for classification, reason in (('diverged', 'diverged'), (None, 'classification_not_recorded')):
            read = operation_read('verified')
            read['delivery']['stages'][4] = flow_tests.stage_row('readback', 'done', classification=classification)
            node = nodes_of(project(read))['readback']
            self.assertEqual((node['state'], node['reason']), ('unverified', reason))

    def test_a_failed_readback_is_unknown_with_its_status(self):
        read = operation_read('verified')
        read['delivery']['stages'][4] = flow_tests.stage_row('readback', 'failed')
        node = nodes_of(project(read))['readback']
        self.assertEqual((node['state'], node['reason']), ('unknown', 'failed'))
        # The execution's own recorded error code is the reason when it holds one.
        read['delivery']['stages'][3]['error_code'] = 'service_unreachable'
        self.assertEqual(nodes_of(project(read))['readback']['reason'], 'service_unreachable')

    def test_a_dispatched_execution_with_no_verified_result_holds_even_a_done_readback_unknown(self):
        read = operation_read('verified')
        read['delivery']['stages'][3] = flow_tests.stage_row('execution', 'unknown', engine_status='succeeded_verified',
                                                             error_code='maintenance_service_incomplete')
        node = nodes_of(project(read))['readback']
        self.assertEqual((node['state'], node['reason']), ('unknown', 'maintenance_service_incomplete'))

    def test_a_readback_status_the_producer_does_not_define_is_unknown_with_that_word(self):
        read = operation_read('verified')
        read['delivery']['stages'][4] = flow_tests.stage_row('readback', 'odd_status')
        node = nodes_of(project(read))['readback']
        self.assertEqual((node['state'], node['reason']), ('unknown', 'odd_status'))

    def test_an_operation_whose_delivery_cannot_be_read_is_unknown_with_the_code(self):
        read = flow_tests.with_operation(baseline())
        read['delivery'] = {'error_code': 'operation_unreadable'}
        node = nodes_of(project(read))['readback']
        self.assertEqual((node['state'], node['reason']), ('unknown', 'operation_unreadable'))
        read['delivery'] = None
        self.assertEqual(nodes_of(project(read))['readback']['reason'], 'delivery_unreadable')


class EdgeTableTests(unittest.TestCase):
    """An edge exists only where a record establishes it, typed, with that record and field as its basis."""

    def test_the_edge_types_are_the_five_and_each_edge_carries_a_basis(self):
        from intune_iac.system_map_projection import EDGE_TYPES
        self.assertEqual(EDGE_TYPES, ('cites', 'generates', 'applies-through', 'reads-back', 'observes'))
        flow = project(with_adoption(operation_read('verified')))
        self.assertEqual({edge['type'] for edge in flow['edges']}, set(EDGE_TYPES))
        ids = set(NODE_IDS)
        for edge in flow['edges']:
            self.assertEqual(set(edge), {'id', 'type', 'from', 'to', 'state', 'basis'})
            self.assertIn(edge['from'], ids)
            self.assertIn(edge['to'], ids)
            self.assertIn(edge['state'], STATES)
            self.assertTrue(edge['basis']['record'] and edge['basis']['field'])
            self.assertEqual(edge['id'], '%s:%s>%s' % (edge['type'], edge['from'], edge['to']))

    def test_a_policy_with_an_intent_and_an_observation_has_exactly_the_edges_those_records_establish(self):
        flow = project(baseline())
        edges = edges_of(flow)
        self.assertEqual(sorted(edges), ['cites:atmos.component>tofu.backend', 'cites:repo.source>atmos.component',
                                         'observes:service>observation'])
        cited = edges['cites:repo.source>atmos.component']
        self.assertEqual((cited['basis'], cited['state']),
                         ({'record': 'repository_intent', 'field': 'scope.stack, scope.component',
                           'record_id': baseline()['states']['intent']['artifact_id']}, 'recorded'))
        self.assertEqual(edges['cites:atmos.component>tofu.backend']['basis']['field'], 'scope.backend')
        self.assertEqual(edges['observes:service>observation']['basis'],
                         {'record': 'observation', 'field': 'run_id', 'record_id': '4'})

    def test_no_intent_leaves_both_cites_edges_absent_and_the_nodes_present(self):
        flow = project(without_intent(baseline()))
        self.assertEqual(sorted(edges_of(flow)), ['observes:service>observation'])
        self.assertEqual([node['id'] for node in flow['nodes']], NODE_IDS)

    def test_a_scope_without_a_backend_has_no_backend_edge(self):
        read = baseline()
        del read['states']['intent']['scope']['backend']
        self.assertNotIn('cites:atmos.component>tofu.backend', edges_of(project(read)))

    def test_a_cites_edge_takes_the_state_of_the_record_it_rests_on(self):
        table = {'current': 'recorded', 'changed': 'stale', 'consumer_changed': 'stale', 'unreadable': 'unknown',
                 'not_checked': 'unverified'}
        for status, expected in table.items():
            edges = edges_of(project(with_intent(baseline(), status=status)))
            self.assertEqual(edges['cites:repo.source>atmos.component']['state'], expected, status)
            # The backend is named by the same intent, so its link is as current as the intent is.
            self.assertEqual(edges['cites:atmos.component>tofu.backend']['state'], expected, status)

    def test_an_adoption_record_that_names_the_generated_files_establishes_generates(self):
        edge = edges_of(project(with_adoption(baseline())))['generates:atmos.component>tofu.engine']
        self.assertEqual(edge['basis'], {'record': 'adoption', 'field': 'binding.generated.%s.manifest_sha256' % OBJECT,
                                         'record_id': 'a1b2c3d4' + '0' * 56})
        self.assertEqual(edge['state'], 'recorded')

    def test_an_adoption_that_names_no_generated_files_for_this_policy_establishes_nothing(self):
        for adoptions in ([], None, [{'artifact_id': 'x' * 8, 'data': {'binding': {}}}],
                          [{'artifact_id': 'x' * 8, 'data': {'binding': {'generated': {'other': {'manifest_sha256': 'c' * 64}}}}}],
                          [{'data': {'binding': {'generated': {OBJECT: {'manifest_sha256': 'c' * 64}}}}}]):
            read = baseline()
            read['adoptions'] = adoptions
            self.assertNotIn('generates:atmos.component>tofu.engine', edges_of(project(read)), adoptions)

    def test_the_newest_adoption_is_the_one_cited(self):
        read = with_adoption(baseline())
        older = copy.deepcopy(read['adoptions'][0])
        older.update(artifact_id='0ld0' + '0' * 60, sequence=1)
        read['adoptions'].insert(0, older)
        self.assertEqual(edges_of(project(read))['generates:atmos.component>tofu.engine']['basis']['record_id'],
                         'a1b2c3d4' + '0' * 56)

    def test_an_older_adoption_does_not_resurrect_a_generation_the_newest_no_longer_names(self):
        key = 'generates:atmos.component>tofu.engine'
        read = with_adoption(baseline())
        older = copy.deepcopy(read['adoptions'][0])
        older.update(artifact_id='0ld0' + '0' * 60, sequence=1)
        for newer_binding in ({}, {'generated': {}}, {'generated': {'other': {'manifest_sha256': 'c' * 64}}},
                              {'generated': {OBJECT: {'path': '/g'}}}, {'generated': {OBJECT: {'manifest_sha256': ''}}}):
            newest = dict(copy.deepcopy(with_adoption(baseline())['adoptions'][0]), sequence=5, artifact_id='e5f6a7b8' + '0' * 56,
                          data={'binding': newer_binding})
            read['adoptions'] = [older, newest]
            self.assertNotIn(key, edges_of(project(read)), newer_binding)
        # The same holds whatever order the records arrive in.
        read['adoptions'].reverse()
        self.assertNotIn(key, edges_of(project(read)))

    def test_two_adoptions_with_the_same_newest_sequence_establish_nothing(self):
        key = 'generates:atmos.component>tofu.engine'
        read = with_adoption(baseline())
        twin = copy.deepcopy(read['adoptions'][0])
        twin['artifact_id'] = 'b2c3d4e5' + '0' * 56
        read['adoptions'].append(twin)
        self.assertNotIn(key, edges_of(project(read)))
        # A tie below the newest sequence does not matter.
        low_a, low_b = copy.deepcopy(twin), copy.deepcopy(twin)
        low_a.update(sequence=1, artifact_id='c3d4e5f6' + '0' * 56)
        low_b.update(sequence=1, artifact_id='d4e5f6a7' + '0' * 56)
        read['adoptions'] = [low_a, low_b, with_adoption(baseline())['adoptions'][0]]
        self.assertEqual(edges_of(project(read))[key]['basis']['record_id'], 'a1b2c3d4' + '0' * 56)

    def test_a_newest_record_without_an_identifier_is_not_a_valid_adoption_and_is_passed_over(self):
        read = with_adoption(baseline())
        newest = copy.deepcopy(read['adoptions'][0])
        newest.update(sequence=9)
        del newest['artifact_id']
        read['adoptions'].append(newest)
        self.assertEqual(edges_of(project(read))['generates:atmos.component>tofu.engine']['basis']['record_id'],
                         'a1b2c3d4' + '0' * 56)

    def test_a_prepared_operation_has_executed_nothing_so_it_has_no_apply_or_readback_edge(self):
        edges = edges_of(project(operation_read('prepared')))
        self.assertEqual(sorted(edges), sorted(edges_of(project(baseline()))))

    def test_a_verified_execution_establishes_both_applies_through_edges_and_the_readback_edge(self):
        edges = edges_of(project(operation_read('verified')))
        engine, service = edges['applies-through:tofu.engine>provider'], edges['applies-through:provider>service']
        self.assertEqual((engine['basis'], engine['state']),
                         ({'record': 'delivery', 'field': 'stages.execution.engine_status', 'record_id': flow_tests.OPERATION},
                          'recorded'))
        self.assertEqual((service['basis']['field'], service['state']), ('stages.execution.service_status', 'recorded'))
        readback = edges['reads-back:service>readback']
        self.assertEqual((readback['basis']['field'], readback['state']), ('stages.readback.status', 'recorded'))

    def test_a_lost_response_keeps_the_engine_edge_unverified_and_has_no_service_or_readback_edge(self):
        edges = edges_of(project(operation_read('unknown')))
        self.assertEqual(edges['applies-through:tofu.engine>provider']['state'], 'unverified')
        self.assertNotIn('applies-through:provider>service', edges)
        self.assertNotIn('reads-back:service>readback', edges)

    def test_a_readback_that_is_pending_or_failed_is_an_unverified_edge(self):
        for status in ('pending', 'failed'):
            read = operation_read('verified')
            read['delivery']['stages'][4] = flow_tests.stage_row('readback', status)
            self.assertEqual(edges_of(project(read))['reads-back:service>readback']['state'], 'unverified', status)

    def test_a_readback_the_journal_does_not_hold_has_no_edge(self):
        for status in ('not_started', 'not_recorded'):
            read = operation_read('verified')
            read['delivery']['stages'][4] = flow_tests.stage_row('readback', status)
            self.assertNotIn('reads-back:service>readback', edges_of(project(read)), status)

    def test_an_observation_edge_takes_the_observations_state_and_needs_a_recorded_run(self):
        edge = edges_of(project(with_observation(baseline(), freshness='stale', freshness_reasons=['older_than_limit'])))
        self.assertEqual(edge['observes:service>observation']['state'], 'stale')
        read = baseline()
        read['states']['observation'] = None
        self.assertNotIn('observes:service>observation', edges_of(project(read)))
        self.assertNotIn('observes:service>observation', edges_of(project(with_observation(baseline(), run_id=None))))

    def test_nothing_is_inferred_from_a_name_or_a_string(self):
        read = baseline()
        read['name'] = 'applies-through readback generates cites observes stale unknown unverified not configured'
        read['states']['intent']['scope']['backend'] = 'generates'
        before, after = project(baseline()), project(read)
        self.assertEqual(sorted(edges_of(after)), sorted(edges_of(before)))
        self.assertEqual(states_of(after), states_of(before))

    def test_the_cites_edges_need_the_intent_record_its_scope_and_a_status(self):
        read = baseline()
        del read['states']['intent']['scope']['stack']
        self.assertNotIn('cites:repo.source>atmos.component', edges_of(project(read)))
        read = baseline()
        del read['states']['intent']['artifact_id']
        self.assertEqual(sorted(edges_of(project(read))), ['observes:service>observation'])
        # A scope that is carried but belongs to no recorded intent establishes nothing.
        read = without_intent(baseline())
        read['states']['intent']['scope'] = dict(baseline()['states']['intent']['scope'])
        read['states']['intent']['artifact_id'] = 'e927410221924400' + '0' * 48
        self.assertEqual(sorted(edges_of(project(read))), ['observes:service>observation'])

    def test_an_engine_edge_needs_a_recorded_engine_status_and_is_verified_only_by_the_verified_one(self):
        read = operation_read('verified')
        del read['delivery']['stages'][3]['engine_status']
        try:
            edges = edges_of(project(read))
        except Exception as error:      # an absent engine status must leave the edge out, not raise
            self.fail('an execution with no engine status raised %r' % error)
        self.assertNotIn('applies-through:tofu.engine>provider', edges)
        read['delivery']['stages'][3]['engine_status'] = 'failed'
        self.assertEqual(edges_of(project(read))['applies-through:tofu.engine>provider']['state'], 'unverified')

    def test_a_dispatch_with_no_verified_result_leaves_the_service_edge_unverified(self):
        read = operation_read('unknown')
        read['delivery']['stages'][3]['service_status'] = 500
        self.assertEqual(edges_of(project(read))['applies-through:provider>service']['state'], 'unverified')

    def test_an_execution_that_never_dispatched_establishes_no_apply_edge(self):
        read = operation_read('prepared')
        read['delivery']['stages'][3] = flow_tests.stage_row('execution', 'not_started', engine_status='succeeded_verified',
                                                             service_status=200)
        edges = edges_of(project(read))
        self.assertNotIn('applies-through:tofu.engine>provider', edges)
        self.assertNotIn('applies-through:provider>service', edges)

    def test_a_delivery_with_no_operation_establishes_no_execution_or_readback_edge(self):
        read = baseline()
        read['delivery'] = flow_tests.executed_delivery('verified')
        self.assertEqual(sorted(edges_of(project(read))), sorted(edges_of(project(baseline()))))


class StabilityTests(unittest.TestCase):
    """Geometry-free falsifier: a state change changes a state word and the revision, never the node set, its order or ids."""

    def state_sets(self):
        stale = with_intent(with_observation(baseline(), freshness='stale', freshness_reasons=['older_than_limit']), status='changed')
        no_pins = baseline()
        no_pins['setup_pins'] = {'error_code': 'integration_manifest_unreadable'}
        return [baseline(), stale, without_intent(baseline()), no_pins, operation_read('prepared'), operation_read('verified'),
                operation_read('unknown'), with_adoption(operation_read('verified'))]

    def test_the_node_set_ids_order_boundaries_kinds_and_layers_are_the_same_in_every_state(self):
        def shape(flow):
            return [(node['id'], node['kind'], node['boundary'], node['layer'], node['opens'] is None) for node in flow['nodes']]
        reference = shape(project(baseline()))
        for read in self.state_sets():
            flow = project(read)
            # Whether Enter opens something depends on the operation, a record; it is the only per-record difference.
            self.assertEqual([item[:4] for item in shape(flow)], [item[:4] for item in reference])
            self.assertEqual(flow['boundaries'], project(baseline())['boundaries'])

    def test_one_changed_record_changes_that_nodes_state_and_the_revision_and_no_other_node(self):
        before = project(baseline())
        after = project(with_observation(baseline(), freshness='stale', freshness_reasons=['older_than_limit']))
        changed = [identifier for identifier in NODE_IDS if states_of(before)[identifier] != states_of(after)[identifier]]
        self.assertEqual(changed, ['observation'])
        self.assertNotEqual(before['revision'], after['revision'])
        self.assertEqual([node['id'] for node in before['nodes']], [node['id'] for node in after['nodes']])

    def test_the_intent_status_changes_the_repository_nodes_and_leaves_the_manifest_and_service_nodes_alone(self):
        before, after = project(baseline()), project(with_intent(baseline(), status='changed'))
        changed = [identifier for identifier in NODE_IDS if states_of(before)[identifier] != states_of(after)[identifier]]
        self.assertEqual(changed, ['repo.source', 'atmos.component'])
        self.assertEqual(states_of(after)['tofu.engine'], 'configured')

    def test_a_node_is_never_omitted_for_the_want_of_a_record(self):
        empty = {'object_id': OBJECT, 'tenant_id': flow_tests.TENANT, 'states': {}}
        flow = project(empty)
        self.assertEqual([node['id'] for node in flow['nodes']], NODE_IDS)
        self.assertEqual(states_of(flow), {'repo.source': 'not_configured', 'atmos.component': 'not_configured',
                                           'tofu.engine': 'unknown', 'tofu.backend': 'not_configured', 'provider': 'unknown',
                                           'service': 'unknown', 'readback': 'unknown', 'observation': 'unknown'})
        self.assertEqual(flow['edges'], [])

    def test_every_state_word_has_a_screen_word_and_the_closed_set_is_unchanged(self):
        from intune_iac import system_map_projection as module
        self.assertEqual(set(module.STATES), STATES)
        self.assertEqual(set(module.STATE_WORDS), STATES)
        self.assertEqual(module.STATE_WORDS['not_configured'], 'not configured')
        for read in self.state_sets():
            for node in project(read)['nodes']:
                self.assertIn(node['state'], module.STATE_WORDS)

    def test_the_projection_does_not_change_its_input(self):
        for read in self.state_sets():
            before = copy.deepcopy(read)
            project(read)
            self.assertEqual(read, before)


class RealStoreTests(unittest.TestCase):
    """The real store, modeled service and maintenance engine: the read model's additive fields, then the projection."""
    setUp = flow_tests.RealStoreTests.setUp
    RESOURCE_ADDRESS = flow_tests.RealStoreTests.RESOURCE_ADDRESS
    import_intent = flow_tests.RealStoreTests.import_intent
    edit_description = flow_tests.RealStoreTests.edit_description
    prepare = flow_tests.RealStoreTests.prepare

    def read(self):
        from intune_iac import workbench
        read = workbench._system_map_read(self.store, flow_tests.OBJECT, service_root=self.service.root)
        return read, project(read)

    def test_a_policy_with_only_an_observation_has_no_repository_and_the_manifests_pins(self):
        from intune_iac import integration_manifest
        read, flow = self.read()
        self.assertIsNone(read['repository_record'])
        pinned = integration_manifest.load()['setup_context']['pinned']
        nodes = nodes_of(flow)
        self.assertEqual(nodes['tofu.engine']['identity'], {'engine': pinned['engine'], 'version': pinned['engine_version']})
        self.assertEqual(nodes['provider']['identity'], {'source': pinned['provider_source'], 'version': pinned['provider_version']})
        self.assertEqual(nodes['service']['identity']['service'], integration_manifest.load()['integration']['label'])
        self.assertEqual((nodes['repo.source']['state'], nodes['atmos.component']['state'], nodes['tofu.backend']['state']),
                         ('not_configured', 'not_configured', 'not_configured'))
        self.assertEqual(nodes['observation']['state'], 'recorded')
        self.assertEqual(sorted(edges_of(flow)), ['observes:service>observation'])

    def test_an_imported_intent_gives_the_repository_nodes_their_recorded_identity(self):
        from intune_iac import workbench
        intent = self.import_intent()
        raw = workbench._system_map_read(self.store, flow_tests.OBJECT, service_root=self.service.root)
        self.assertTrue({'object_id', 'tenant_id', 'states', 'attention', 'adoptions', 'delivery', 'review'} <= set(raw))
        read, flow = self.read()
        # The workflow map's own read values are all still there beside the two additive fields.
        self.assertTrue({'states', 'attention', 'adoptions', 'delivery', 'review'} <= set(read))
        self.assertIsNotNone(read['repository_record'])
        self.assertEqual(read['repository_record']['artifact_id'], intent['artifact_id'])
        self.assertEqual(read['repository_record']['effective_pointer'], intent['data']['effective_pointer'])
        self.assertEqual(read['repository_record']['resource_address'], self.RESOURCE_ADDRESS)
        self.assertTrue(read['repository_record']['sources'])
        nodes = nodes_of(flow)
        self.assertEqual(nodes['repo.source']['identity']['revision'], 'a' * 40)
        self.assertEqual(nodes['repo.source']['identity']['source_files'],
                         [row['path'] for row in intent['data']['resolution']['sources']])
        self.assertEqual(nodes['atmos.component']['identity'], {'stack': 'orgs/reference/dev', 'component': 'intune-reference'})
        self.assertEqual(nodes['tofu.backend']['identity'], {'backend': 'local'})
        self.assertEqual([nodes[name]['state'] for name in ('repo.source', 'atmos.component', 'tofu.backend')],
                         ['recorded'] * 3)
        self.assertIn('cites:repo.source>atmos.component', edges_of(flow))

    def test_a_repository_edit_makes_the_repository_nodes_stale_and_nothing_else_changes_state(self):
        self.import_intent()
        _, before = self.read()
        self.edit_description('Edited in the repository.')
        _, after = self.read()
        changed = [name for name in NODE_IDS if states_of(before)[name] != states_of(after)[name]]
        self.assertEqual(changed, ['repo.source', 'atmos.component'])
        self.assertEqual(states_of(after)['repo.source'], 'stale')
        self.assertEqual(edges_of(after)['cites:repo.source>atmos.component']['state'], 'stale')

    def test_the_newest_of_several_intents_is_the_one_the_repository_record_reads(self):
        self.prepare()      # imports, then refreshes: two intents for the policy
        read, flow = self.read()
        self.assertEqual(read['repository_record']['artifact_id'], self.intent['artifact_id'])
        self.assertEqual(nodes_of(flow)['repo.source']['identity']['revision'], 'b' * 40)

    def test_the_service_root_reaches_the_observation_check_and_the_system_map_command_returns_the_projection(self):
        from intune_iac import maintenance, workbench
        review = self.prepare()
        maintenance.execute(self.operation, approve_digest=review['approval_digest'])
        _, flow = self.read()
        observation = nodes_of(flow)['observation']
        # The execution moved the service: the observation is fresh by age and no longer current with its source.
        self.assertEqual((observation['state'], observation['reason']), ('stale', 'service_changed'))
        result = workbench._system_map(self.store, flow_tests.OBJECT, service_root=self.service.root)
        self.assertEqual(result, flow)
        self.assertEqual(result['schema_version'], 'system-map/1')

    def test_a_verified_change_establishes_the_apply_and_readback_edges_from_the_journal(self):
        from intune_iac import maintenance
        review = self.prepare()
        maintenance.execute(self.operation, approve_digest=review['approval_digest'])
        _, flow = self.read()
        edges = edges_of(flow)
        for name in ('applies-through:tofu.engine>provider', 'applies-through:provider>service', 'reads-back:service>readback'):
            self.assertIn(name, edges)
            self.assertEqual(edges[name]['state'], 'recorded', name)
            self.assertEqual(edges[name]['basis']['record_id'], review['operation_id'])
        self.assertEqual(nodes_of(flow)['readback']['state'], 'recorded')

    def test_a_lost_response_leaves_the_readback_unknown_and_the_service_edge_absent(self):
        from intune_iac import maintenance
        review = self.prepare()
        maintenance.execute(self.operation, approve_digest=review['approval_digest'], fault='lost-response')
        _, flow = self.read()
        self.assertEqual(nodes_of(flow)['readback']['state'], 'unknown')
        self.assertNotIn('reads-back:service>readback', edges_of(flow))

    def test_an_adopted_policy_has_the_generates_edge(self):
        self.import_intent()
        self.store.record_artifact('adoption', flow_tests.OBJECT, {
            'schema_version': 'workbench-adoption/1', 'tenant_id': flow_tests.TENANT, 'object_id': flow_tests.OBJECT,
            'binding': {'generated': {flow_tests.OBJECT: {'path': '/g', 'manifest_sha256': 'c' * 64}}}, 'binding_sha256': 'a' * 64,
            'maintenance_service_root': '/s', 'cloud_authority': False, 'execution_authorized': False})
        _, flow = self.read()
        self.assertIn('generates:atmos.component>tofu.engine', edges_of(flow))

    def test_reading_the_system_map_writes_nothing(self):
        import hashlib
        from pathlib import Path
        from intune_iac import workbench
        self.prepare()

        def tree(*roots):
            return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for root in roots
                    for path in sorted(Path(root).rglob('*')) if path.is_file()}
        before = tree(self.store.root, self.operation)
        result = workbench._system_map(self.store, flow_tests.OBJECT, service_root=self.service.root)
        self.assertEqual(result['schema_version'], 'system-map/1')
        self.assertEqual(tree(self.store.root, self.operation), before)

    def test_an_unreadable_manifest_is_carried_as_its_code(self):
        from unittest import mock
        from intune_iac.io import AppError
        with mock.patch('intune_iac.integration_manifest.load', side_effect=AppError('integration_manifest_unreadable', 'x')):
            read, flow = self.read()
        self.assertEqual(read['setup_pins'], {'error_code': 'integration_manifest_unreadable'})
        self.assertEqual(nodes_of(flow)['tofu.engine']['reason'], 'integration_manifest_unreadable')


if __name__ == '__main__':
    unittest.main()
