"""Closed graph vocabulary and established relationship constraints.

This is a review contract, not an inference ontology or execution scheduler.
Declared and unknown relationships never acquire observed or derived authority.
"""
from dataclasses import dataclass

NODE_FIELDS = {
    'Tenant': 'cloud tenant_uuid identity_assurance',
    'Policy': 'cloud tenant_uuid tenant_id family object_uuid name',
    'SettingDefinition': 'definition_id',
    'SettingValue': 'policy_id setting_id definition_id value_digest normalized_instance mapping_status',
    'ProviderMapping': 'provider_source provider_version resource qualification',
    'Group': 'cloud tenant_uuid object_uuid reference_coverage',
    'Filter': 'cloud tenant_uuid object_uuid reference_coverage',
    'Assignment': 'policy_id assignment_uuid target_type group_uuid group_id filter_mode filter_uuid',
    'PlacementIntent': 'policy_id component stack_label target_verification',
    'ManifestDeclaration': 'source_artifact_id',
    'StackDeclaration': 'manifest_id stack_identity',
    'ComponentInstance': 'repository_scope_id stack_id name engine_type resolution_status',
    'ComponentDefinition': 'implementation_path engine_type repository_scope_id',
    'ImportOccurrence': 'manifest_id order literal_path resolution_status',
    'DependencyDeclaration': 'consumer_id component_selector stack_selector adapter resolution_status',
    'ConfigAssignment': 'component_id section key_digest',
    'EffectiveStack': 'repository_scope_id physical_stack resolution_status',
    'EffectiveConfiguration': 'component_id adapter source_fingerprint selection_fingerprint config_digest resolution_status dependency_context_digest',
    'ResolutionSource': 'configuration_id source_artifact_id',
    'EffectiveDependency': 'consumer_id configuration_id component_selector stack_selector resolution_status adapter selector_scope context_relation',
}
NODE_OPTIONAL_FIELDS = {'ComponentDefinition': {'implementation_presence', 'implementation_directory'},
                         'Assignment': {'capture_adapter', 'assignment_source', 'assignment_source_id'}}
_ENDPOINT_TYPES = {
    'inTenant': ({'Policy'}, {'Tenant'}),
    'ofPolicy': ({'SettingValue', 'Assignment'}, {'Policy'}),
    'hasDefinition': ({'SettingValue'}, {'SettingDefinition'}),
    'mappedBy': ({'SettingDefinition'}, {'ProviderMapping'}),
    'includesGroup': ({'Assignment'}, {'Group'}),
    'excludesGroup': ({'Assignment'}, {'Group'}),
    'usesFilter': ({'Assignment'}, {'Filter'}),
    'proposesPlacementOf': ({'PlacementIntent'}, {'Policy'}),
    'isDeclaredBy': ({'StackDeclaration'}, {'ManifestDeclaration'}),
    'belongsToStackDeclaration': ({'ComponentInstance'}, {'StackDeclaration'}),
    'usesImplementation': ({'ComponentInstance', 'EffectiveConfiguration'}, {'ComponentDefinition'}),
    'hasImport': ({'ManifestDeclaration'}, {'ImportOccurrence'}),
    'resolvesToManifest': ({'ImportOccurrence'}, {'ManifestDeclaration'}),
    'imports': ({'ManifestDeclaration'}, {'ManifestDeclaration'}),
    'inheritsConfigurationFrom': ({'ComponentInstance'}, {'ComponentInstance'}),
    'hasDependencyDeclaration': ({'ComponentInstance'}, {'DependencyDeclaration'}),
    'declaresDependencyOn': ({'ComponentInstance'}, {'ComponentInstance'}),
    'hasConfigDeclaration': ({'ComponentInstance'}, {'ConfigAssignment'}),
    'belongsToEffectiveStack': ({'ComponentInstance'}, {'EffectiveStack'}),
    'hasEffectiveConfiguration': ({'ComponentInstance'}, {'EffectiveConfiguration'}),
    'derivedFrom': ({'EffectiveConfiguration'}, {'ResolutionSource'}),
    'hasEffectiveDependency': ({'EffectiveConfiguration'}, {'EffectiveDependency'}),
    'dependsOn': ({'EffectiveDependency'}, {'ComponentInstance'}),
}


DERIVED_NODE_TYPES = frozenset({'EffectiveStack', 'EffectiveConfiguration', 'ResolutionSource', 'EffectiveDependency'})
DERIVED_PREDICATES = frozenset({'belongsToEffectiveStack', 'hasEffectiveConfiguration',
                              'derivedFrom', 'hasEffectiveDependency', 'dependsOn'})


@dataclass(frozen=True)
class PredicateContract:
    source_types: frozenset[str]
    target_types: frozenset[str]
    statuses: frozenset[str]


def _contract(predicate, endpoints):
    if predicate in DERIVED_PREDICATES:
        statuses = frozenset({'derived'})
    elif predicate == 'usesImplementation':
        statuses = frozenset({'observed', 'declared', 'derived'})
    else:
        statuses = frozenset({'observed', 'declared'})
    return PredicateContract(frozenset(endpoints[0]), frozenset(endpoints[1]), statuses)


PREDICATE_CONTRACTS = {name: _contract(name, endpoints) for name, endpoints in _ENDPOINT_TYPES.items()}

# Only cardinalities enforced by the existing graph validator are represented.
# None in the selector is unconditional; a string selects resolution_status.
# Assignment include/exclude/filter conditions require value-aware validation.
CARDINALITIES = {
    ('Policy', None): {'inTenant': (1, 1)},
    ('SettingValue', None): {'ofPolicy': (1, 1), 'hasDefinition': (1, 1)},
    ('Assignment', None): {'ofPolicy': (1, 1)},
    ('ComponentInstance', 'resolved'): {'belongsToEffectiveStack': (1, 1), 'hasEffectiveConfiguration': (1, 1)},
    ('ComponentInstance', 'unknown'): {'hasEffectiveConfiguration': (0, 0)},
    ('EffectiveConfiguration', None): {'usesImplementation': (1, 1), 'derivedFrom': (1, None)},
    ('EffectiveDependency', 'resolved'): {'dependsOn': (1, 1)},
    ('EffectiveDependency', 'unknown'): {'dependsOn': (0, 0)},
}
