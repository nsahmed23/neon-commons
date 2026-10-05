"""Static Atmos declarations. YAML nodes are composed, never constructed/executed.

This is deliberately not an Atmos resolver: no overlay merge, discovery identity,
functions, templates, backend access, workflow execution, or binary invocation.
"""
from __future__ import annotations
import hashlib
from pathlib import Path, PurePosixPath
import re
import yaml
from yaml.nodes import MappingNode, ScalarNode, SequenceNode
from .io import AppError, digest, read_bytes

_SAFE = re.compile(r'[A-Za-z0-9_.\-/]{1,256}\Z')
_STANDARD = 'tag:yaml.org,2002:'


def _identity(kind, *parts):
    return kind + ':' + digest(list(parts))


def _scalar(node):
    if not isinstance(node, ScalarNode) or node.tag != _STANDARD + 'str': return None
    value = node.value
    return value if _SAFE.fullmatch(value) and '..' not in PurePosixPath(value).parts and not value.startswith('/') else None


def _mapping(node):
    if not isinstance(node, MappingNode) or node.tag != _STANDARD + 'map': return {}
    result = {}
    for k,v in node.value:
        if not isinstance(k, ScalarNode) or k.tag != _STANDARD + 'str': continue
        # Duplicate declaration keys are ambiguous; fail instead of accepting last value.
        if k.value in result: raise AppError('ambiguous_atmos_yaml', 'Atmos YAML contains duplicate declaration keys.')
        result[k.value] = v
    return result


def _sequence(node):
    return node.value if isinstance(node, SequenceNode) and node.tag == _STANDARD + 'seq' else []


def _literal_mapping_keys(node):
    """Check original YAML keys before a filtered mapping can lose evidence."""
    return (isinstance(node, MappingNode) and node.tag == _STANDARD + 'map' and
            all(isinstance(key, ScalarNode) and key.tag == _STANDARD + 'str' for key, _ in node.value))


def inspect_atmos(root):
    root = Path(root).resolve()
    if not root.is_dir(): raise AppError('invalid_atmos_root', 'Atmos root must be a local directory.')
    scope = _identity('repository-scope', str(root))
    graph = {'nodes': [], 'edges': [], 'sources': [], 'coverage': [], 'issues': [],
             'atmos': {'adapter': 'static-declarations/1.0', 'resolution_status': 'unknown',
                       'effective_config': 'not_resolved', 'tenant_verification': 'not_established',
                       'execution_order': 'not_established'}}
    ids = set(); trees = {}; sources = {}; manifests = {}; instances = {}; import_edges = []; inherits_edges = []
    def add(kind, key, **fields):
        if key not in ids:
            graph['nodes'].append({'id': key, 'type': kind, **fields}); ids.add(key)
        return key
    def origin(path, node, pointer=''):
        return {'artifact_id': sources[path], 'pointer': pointer,
                'line': node.start_mark.line + 1, 'column': node.start_mark.column + 1}
    def issue(code, path, node, pointer=''):
        graph['issues'].append({'code': code, 'status': 'unknown', 'origin': origin(path, node, pointer)})
    def edge(source, predicate, target, evidence, **fields):
        graph['edges'].append({'id': _identity('edge', source,predicate,target,evidence,fields),
                              'source':source,'predicate':predicate,'target':target,
                              'status':'declared','origin':evidence, **fields})
    # File inventory is bounded and remains inside the selected root.
    files = sorted(set(root.rglob('*.yaml')) | set(root.rglob('*.yml')))
    if len(files) > 512: raise AppError('atmos_limit', 'Atmos static inspection exceeds the 512-file limit.')
    total = 0
    for path in files:
        if path.is_symlink() or any(p.is_symlink() for p in path.relative_to(root).parents if (root/p).exists()):
            continue
        data = read_bytes(path); total += len(data)
        if len(data) > 2*1024*1024 or total > 16*1024*1024:
            raise AppError('atmos_limit', 'Atmos source exceeds static inspection limits.')
        try:
            tree = yaml.compose(data, Loader=yaml.SafeLoader)
        except (yaml.YAMLError, RecursionError, UnicodeError):
            raise AppError('invalid_atmos_yaml', 'Atmos source could not be parsed safely.') from None
        if tree is None: continue
        sha = hashlib.sha256(data).hexdigest()
        source = _identity('source', scope, path.relative_to(root).as_posix(), sha)
        sources[path] = source; trees[path] = tree
        graph['sources'].append({'id':source,'type':'SourceArtifact','kind':'atmos_yaml',
                                 'path':path.relative_to(root).as_posix(),'sha256':sha})
        # Traversal guards recursive aliases, deep input, huge node graphs and non-scalar keys.
        seen = set(); stack = [(tree,0)]; count = 0
        while stack:
            node, depth = stack.pop(); count += 1
            if depth > 64 or count > 100000:
                raise AppError('atmos_limit', 'Atmos YAML exceeds static node limits.')
            if id(node) in seen:
                issue('atmos_alias_unresolved',path,node); continue
            seen.add(id(node))
            if not node.tag.startswith(_STANDARD) or (isinstance(node,ScalarNode) and any(t in node.value for t in ('{{','{%','${'))):
                issue('atmos_dynamic_value',path,node, 'opaque:' + digest([node.start_mark.index,node.end_mark.index])); continue
            if isinstance(node,ScalarNode) and node.tag == _STANDARD + 'merge':
                issue('atmos_merge_unresolved',path,node)
            if isinstance(node,MappingNode):
                _mapping(node)
                stack.extend((v,depth+1) for pair in node.value for v in pair)
            elif isinstance(node,SequenceNode): stack.extend((v,depth+1) for v in node.value)
    config_path = root/'atmos.yaml'
    config = _mapping(trees.get(config_path))
    stack_config = _mapping(config.get('stacks'))
    # A literal import is relative to both configured base paths. An unknown
    # path must never silently fall back to an existing but unrelated manifest.
    configured_base = _scalar(config['base_path']) if 'base_path' in config else '.'
    stack_base = _scalar(stack_config['base_path']) if 'base_path' in stack_config else 'stacks'
    if config_path in trees and (not isinstance(trees[config_path], MappingNode) or trees[config_path].tag != _STANDARD + 'map'):
        configured_base = None
    if 'stacks' in config and (not isinstance(config['stacks'], MappingNode) or config['stacks'].tag != _STANDARD + 'map'):
        stack_base = None
    base_dir = root/configured_base/stack_base if configured_base is not None and stack_base is not None else None
    # Treat source manifests as stack declarations; filename is not resolved stack identity.
    for path, tree in trees.items():
        doc = _mapping(tree)
        if path == config_path or not any(k in doc for k in ('components','import','vars','settings','env')): continue
        manifest = add('ManifestDeclaration', _identity('manifest',scope,path.relative_to(root).as_posix()),
                       source_artifact_id=sources[path], status='declared', origin=origin(path,tree))
        manifests[path] = manifest
        stack = add('StackDeclaration', _identity('stack-declaration',scope,path.relative_to(root).as_posix()),
                    manifest_id=manifest, stack_identity='unknown', status='declared', origin=origin(path,tree))
        edge(stack,'isDeclaredBy',manifest,origin(path,tree))
        graph['coverage'].append({'subject_id':stack,'aspect':'atmos_effective_resolution','status':'unknown','origin':origin(path,tree)})
        for kind, kind_node in _mapping(doc.get('components')).items():
            if kind not in ('terraform','helmfile'): continue
            for name, component_node in _mapping(kind_node).items():
                if not _SAFE.fullmatch(name):
                    issue('atmos_component_name_unresolved',path,component_node); continue
                metadata = _mapping(_mapping(component_node).get('metadata'))
                impl = _scalar(metadata.get('component'))
                if 'component' not in metadata: impl = name
                instance = add('ComponentInstance', _identity('component-instance',scope,stack,kind,name),
                    repository_scope_id=scope, stack_id=stack, name=name, engine_type=kind,
                    resolution_status='unknown', status='declared', origin=origin(path,component_node,f'/components/{kind}/{name}'))
                instances[(path,kind,name)] = instance
                edge(instance,'belongsToStackDeclaration',stack,origin(path,component_node))
                if impl:
                    definition = add('ComponentDefinition',_identity('component-definition',scope,kind,impl),
                        implementation_path=impl, engine_type=kind, repository_scope_id=scope, status='declared',
                        origin=origin(path,metadata.get('component',component_node)))
                    edge(instance,'usesImplementation',definition,origin(path,metadata.get('component',component_node)))
                else: issue('atmos_implementation_unresolved',path,component_node)
    for path, manifest in manifests.items():
        doc = _mapping(trees[path])
        imports = doc.get('import')
        if imports is not None and not isinstance(imports,SequenceNode): issue('atmos_import_unresolved',path,imports)
        for index, import_node in enumerate(_sequence(imports)):
            im = _mapping(import_node)
            literal = _scalar(im.get('path')) if im else _scalar(import_node)
            occurrence = add('ImportOccurrence', _identity('import',manifest,index),
                manifest_id=manifest, order=index, literal_path=literal, resolution_status='unknown',
                status='declared', origin=origin(path,import_node,f'/import/{index}'))
            edge(manifest,'hasImport',occurrence,origin(path,import_node),order=index)
            if literal is None:
                issue('atmos_import_unresolved',path,import_node); continue
            if im and (not _literal_mapping_keys(import_node) or set(im) != {'path'}):
                issue('atmos_import_evaluation_unqualified',path,import_node); continue
            import_base = path.parent if literal.startswith('./') else base_dir
            if import_base is None:
                issue('atmos_import_base_unresolved',path,import_node); continue
            candidates = [import_base/literal]
            if not Path(literal).suffix:
                candidates += [candidates[0].with_suffix('.yaml'),candidates[0].with_suffix('.yml')]
            resolved = next((p.resolve() for p in candidates if p.resolve() in manifests and not p.is_symlink() and p.resolve().is_relative_to(root)),None)
            if resolved:
                edge(occurrence,'resolvesToManifest',manifests[resolved],origin(path,import_node), resolution='literal_file')
                edge(manifest,'imports',manifests[resolved],origin(path,import_node),order=index)
                import_edges.append((manifest,manifests[resolved]))
            else: issue('atmos_import_unresolved',path,import_node)
        for (instance_path,kind,name), instance in instances.items():
            if instance_path != path: continue
            cn = _mapping(_mapping(doc.get('components')).get(kind))[name]
            component = _mapping(cn); metadata = _mapping(component.get('metadata'))
            parents = metadata.get('inherits')
            if parents is not None and not isinstance(parents,SequenceNode): issue('atmos_inheritance_unresolved',path,parents)
            for index,parent in enumerate(_sequence(parents)):
                parent_name = _scalar(parent); target = instances.get((path,kind,parent_name))
                if target:
                    edge(instance,'inheritsConfigurationFrom',target,origin(path,parent),order=index)
                    inherits_edges.append((instance,target))
                else: issue('atmos_inheritance_unresolved',path,parent)
            if 'component' in component:
                # Legacy component syntax differs by adapter; keep declaration unresolved.
                issue('atmos_legacy_component_unqualified',path,component['component'])
            if 'depends_on' in metadata: issue('atmos_metadata_depends_on_unrecognized',path,metadata['depends_on'])
            depends = _mapping(component.get('settings')).get('depends_on')
            if depends is not None:
                if not isinstance(depends,MappingNode): issue('atmos_dependency_unresolved',path,depends)
                for index,dep_node in enumerate(_mapping(depends).values()):
                    selector = _mapping(dep_node)
                    component_name = _scalar(selector.get('component'))
                    explicit_stack = _scalar(selector.get('stack'))
                    occurrence = add('DependencyDeclaration',_identity('dependency',instance,index),
                        consumer_id=instance, component_selector=component_name, stack_selector=explicit_stack,
                        adapter='settings.depends_on/v1.199.0', resolution_status='unknown',
                        status='declared', origin=origin(path,dep_node))
                    edge(instance,'hasDependencyDeclaration',occurrence,origin(path,dep_node))
                    target = instances.get((path,kind,component_name)) if _literal_mapping_keys(dep_node) and set(selector) == {'component'} else None
                    if target:
                        edge(instance,'declaresDependencyOn',target,origin(path,dep_node), qualification='same_manifest_literal_selector')
                    else: issue('atmos_dependency_unresolved',path,dep_node)
            if 'dependencies' in component:
                issue('atmos_current_dependency_adapter_unqualified',path,component['dependencies'])
            # Config declarations store only opaque keys and digests; no env/auth/custom payload escapes.
            for section in ('vars','env','settings','auth','backend','providers'):
                section_node = component.get(section)
                for index,(key,value_node) in enumerate(_mapping(section_node).items()):
                    assignment = add('ConfigAssignment',_identity('config-assignment',instance,section,index),
                        component_id=instance, section=section, key_digest=digest(key), status='declared',
                        origin=origin(path,value_node,'opaque:' + digest([section,index,key])))
                    edge(instance,'hasConfigDeclaration',assignment,origin(path,value_node,'opaque:' + digest([section,index,key])))
    def mark_cycles(pairs, code):
        adjacency = {}
        for source,target in pairs: adjacency.setdefault(source,[]).append(target)
        # Iterative path traversal avoids recursion on large repositories.
        active = set(); done = set()
        for start in adjacency:
            if start in done: continue
            pending = [(start,False)]
            while pending:
                current, exiting = pending.pop()
                if exiting: active.discard(current); done.add(current); continue
                if current in active:
                    graph['issues'].append({'code':code,'subject_id':current,'status':'unknown'}); continue
                if current in done: continue
                active.add(current); pending.append((current,True))
                pending.extend((target,False) for target in reversed(adjacency.get(current,[])))
    mark_cycles(import_edges,'atmos_import_cycle')
    mark_cycles(inherits_edges,'atmos_inheritance_cycle')
    return graph
