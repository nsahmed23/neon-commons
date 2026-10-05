"""Bounded, inert resolution of a documented literal subset of Atmos v1.199.0.

This is repository-local configuration analysis, not an Atmos execution adapter.
The public projection deliberately omits configuration values. See docs/REPOSITORY.md.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat

import yaml
from yaml.events import AliasEvent
from yaml.nodes import MappingNode, ScalarNode, SequenceNode

from .io import digest

MAX_FILES = 512
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 16 * 1024 * 1024
MAX_ENTRIES = 20000
MAX_NODES = 100000
MAX_DEPTH = 64
MAX_HISTORY_ENTRIES = 800000
_STANDARD = 'tag:yaml.org,2002:'
_NAME = re.compile(r'[A-Za-z0-9_.\-/]{1,256}\Z')
_SECTIONS = ('vars', 'env', 'settings', 'providers')
_SKIP_DIRS = {'.git', '.terraform', '.cache', 'node_modules', '__pycache__'}
_ADAPTER = 'atmos-literal/1.0'


class _Blocked(Exception):
    def __init__(self, code, path=None, pointer=None):
        self.item = {'code': code, 'status': 'unknown'}
        if path is not None:
            self.item['path'] = path
        if pointer is not None:
            self.item['pointer'] = pointer
        super().__init__(code)


@dataclass
class _Value:
    value: object
    history: list


def _pointer(base, key):
    return base + '/' + str(key).replace('~', '~0').replace('/', '~1')


def _plain(value):
    if isinstance(value.value, dict):
        return {key: _plain(child) for key, child in value.value.items()}
    if isinstance(value.value, list):
        return [_plain(child) for child in value.value]
    return value.value


def _empty():
    return _Value({}, [])


def _fail(code, value=None):
    origin = value.history[-1] if value is not None and value.history else {}
    raise _Blocked(code, origin.get('path'), origin.get('pointer'))


def _mapping(value):
    if not isinstance(value.value, dict):
        _fail('expected_mapping', value)
    return value.value


def _literal_path(value, allow_dot=False):
    if not isinstance(value, str) or not _NAME.fullmatch(value):
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and '..' not in path.parts and (allow_dot or value != '.')


def _check_keys(value, allowed, code):
    for key, child in _mapping(value).items():
        if key not in allowed:
            _fail(code, child)


def _glob_regex(pattern):
    # Deliberately bounded glob dialect: *, ** and ?. No brace/class/extglob syntax.
    if not isinstance(pattern, str) or not pattern or len(pattern) > 256 or pattern.startswith('/') or '..' in PurePosixPath(pattern).parts:
        raise _Blocked('unsupported_discovery_pattern')
    if any(x in pattern for x in ('[', ']', '{', '}', '\\', '!', '(', ')')):
        raise _Blocked('unsupported_discovery_pattern')
    out = ''; i = 0
    while i < len(pattern):
        if pattern[i:i+3] == '**/':
            out += '(?:.*/)?'; i += 3
        elif pattern[i:i+2] == '**':
            out += '.*'; i += 2
        elif pattern[i] == '*':
            out += '[^/]*'; i += 1
        elif pattern[i] == '?':
            out += '[^/]'; i += 1
        else:
            out += re.escape(pattern[i]); i += 1
    return re.compile(out + r'\Z')


class _Repository:
    def __init__(self, root):
        self.root = Path(root).absolute()
        self.sources = {}
        self.data = {}
        self.parsed = {}
        self.imported = {}
        self.total = 0
        self.nodes = 0
        self.operations = 0
        self.history_entries = 0
        self.entries = 0
        self.blockers = []
        self.config = _empty()
        self.stack_base = self.root / 'stacks'
        self.component_bases = {}
        self.selected = {}
        try:
            self._initialize()
        except _Blocked as error:
            self.blockers.append(error.item)
        except (OSError, ValueError, RecursionError):
            self.blockers.append({'code': 'repository_unreadable', 'status': 'unknown'})

    def _contained(self, path):
        if not path.is_relative_to(self.root):
            raise _Blocked('unsafe_path')
        # Reject symlinks in every existing path component, including the selected root.
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise _Blocked('unsafe_symlink', path.relative_to(self.root).as_posix())
        if not path.resolve().is_relative_to(self.root.resolve()):
            raise _Blocked('unsafe_path')
        return path

    def _read(self, path):
        self._contained(path)
        relative = path.relative_to(self.root).as_posix()
        if relative in self.data:
            return self.data[relative]
        if len(self.sources) >= MAX_FILES:
            raise _Blocked('repository_limit', relative)
        flags = os.O_RDONLY | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_NOFOLLOW', 0)
        try:
            fd = os.open(path, flags)
            with os.fdopen(fd, 'rb') as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode):
                    raise _Blocked('nonregular_source', relative)
                if info.st_nlink != 1:
                    raise _Blocked('unsafe_hardlink', relative)
                data = stream.read(MAX_FILE_BYTES + 1)
        except OSError:
            raise _Blocked('source_unreadable', relative) from None
        if len(data) > MAX_FILE_BYTES or self.total + len(data) > MAX_TOTAL_BYTES:
            raise _Blocked('repository_limit', relative)
        self.total += len(data)
        self.sources[relative] = hashlib.sha256(data).hexdigest()
        self.data[relative] = data
        return data

    def _scan(self, base, source_kind):
        self._contained(base)
        if not base.exists():
            return
        if not base.is_dir():
            raise _Blocked('invalid_source_directory', base.relative_to(self.root).as_posix())
        pending = [(base, 0)]
        while pending:
            directory, depth = pending.pop()
            if depth > MAX_DEPTH:
                raise _Blocked('repository_limit')
            with os.scandir(directory) as iterator:
                entries = []
                for entry in iterator:
                    self.entries += 1
                    if self.entries > MAX_ENTRIES:
                        raise _Blocked('repository_limit')
                    entries.append(entry)
            entries.sort(key=lambda item: item.name)
            for entry in entries:
                path = Path(entry.path)
                if entry.name in _SKIP_DIRS:
                    continue
                if entry.is_symlink():
                    raise _Blocked('unsafe_symlink', path.relative_to(self.root).as_posix())
                if entry.is_dir(follow_symlinks=False):
                    pending.append((path, depth + 1))
                elif (source_kind == 'stack' and entry.name.endswith(('.yaml', '.yml', '.yaml.tmpl', '.yml.tmpl'))) or (source_kind == 'component' and (entry.name.endswith(('.tf', '.tf.json')) or entry.name == '.terraform.lock.hcl')):
                    self._read(path)

    def _parse(self, path):
        relative = path.relative_to(self.root).as_posix()
        if relative in self.parsed:
            return self.parsed[relative]
        if relative.endswith('.tmpl'):
            raise _Blocked('template_manifest', relative)
        data = self._read(path)
        try:
            for event in yaml.parse(data, Loader=yaml.SafeLoader):
                if isinstance(event, AliasEvent):
                    raise _Blocked('yaml_alias', relative)
            tree = yaml.compose(data, Loader=yaml.SafeLoader)
        except (yaml.YAMLError, UnicodeError, RecursionError):
            raise _Blocked('invalid_yaml', relative) from None
        if tree is None:
            raise _Blocked('empty_manifest', relative)

        def convert(node, pointer='', depth=0):
            self.nodes += 1
            if self.nodes > MAX_NODES or depth > MAX_DEPTH:
                raise _Blocked('repository_limit', relative)
            origin = {'path': relative, 'pointer': pointer, 'line': node.start_mark.line+1, 'column': node.start_mark.column+1}
            tag = node.tag.removeprefix(_STANDARD)
            if not node.tag.startswith(_STANDARD) or tag not in {'map', 'seq', 'str', 'int', 'float', 'bool', 'null'}:
                raise _Blocked('unsupported_yaml_tag', relative, pointer)
            if isinstance(node, MappingNode):
                result = {}
                for key, child in node.value:
                    if not isinstance(key, ScalarNode) or key.tag != _STANDARD+'str':
                        raise _Blocked('unsupported_yaml_key', relative, pointer)
                    if any(token in key.value for token in ('{{', '{%', '${')):
                        raise _Blocked('dynamic_value', relative, pointer)
                    if key.value in result:
                        raise _Blocked('duplicate_yaml_key', relative, pointer)
                    result[key.value] = convert(child, _pointer(pointer, key.value), depth+1)
            elif isinstance(node, SequenceNode):
                result = [convert(child, _pointer(pointer, index), depth+1) for index, child in enumerate(node.value)]
            else:
                if any(token in node.value for token in ('{{', '{%', '${')):
                    raise _Blocked('dynamic_value', relative, pointer)
                if tag == 'str':
                    result = node.value
                elif tag == 'null':
                    result = None
                elif tag == 'bool' and node.value.lower() in ('true', 'false'):
                    result = node.value.lower() == 'true'
                elif tag == 'int' and re.fullmatch(r'-?(?:0|[1-9][0-9]*)', node.value):
                    result = int(node.value)
                    if abs(result) > 9007199254740991:
                        raise _Blocked('unsupported_yaml_scalar', relative, pointer)
                elif tag == 'float' and re.fullmatch(r'-?(?:0|[1-9][0-9]*)\.[0-9]+(?:[eE][+-]?[0-9]+)?', node.value):
                    result = float(node.value)
                    if not math.isfinite(result):
                        raise _Blocked('unsupported_yaml_scalar', relative, pointer)
                else:
                    # YAML 1.1 yes/no, timestamps and exotic numbers need qualification.
                    raise _Blocked('unsupported_yaml_scalar', relative, pointer)
            return _Value(result, [origin])
        result = convert(tree)
        _mapping(result)
        self.parsed[relative] = result
        return result

    def _path_setting(self, parent, value, default):
        name = _plain(value) if value is not None else default
        if not _literal_path(name, allow_dot=True):
            _fail('unsafe_path', value)
        return self._contained(parent / name)

    def _initialize(self):
        self._contained(self.root)
        if not self.root.is_dir():
            raise _Blocked('invalid_repository_root')
        if not (self.root/'atmos.yaml').exists():
            raise _Blocked('missing_atmos_config', 'atmos.yaml')
        self.config = self._parse(self.root/'atmos.yaml')
        _check_keys(self.config, {'base_path', 'stacks', 'components', 'settings'}, 'unsupported_cli_config')
        cfg = self.config.value
        base = self._path_setting(self.root, cfg.get('base_path'), '.')
        stackcfg = cfg.get('stacks', _empty())
        _check_keys(stackcfg, {'base_path', 'included_paths', 'excluded_paths', 'name_pattern'}, 'unsupported_stack_config')
        self.stack_base = self._path_setting(base, stackcfg.value.get('base_path'), 'stacks')
        settings = cfg.get('settings', _empty())
        _check_keys(settings, {'list_merge_strategy'}, 'unsupported_cli_config')
        if _plain(settings).get('list_merge_strategy', 'replace') != 'replace':
            _fail('unsupported_list_merge_strategy', settings)
        componentcfg = cfg.get('components', _empty())
        _check_keys(componentcfg, {'terraform', 'helmfile'}, 'unsupported_component_kind')
        for kind in ('terraform', 'helmfile'):
            options = componentcfg.value.get(kind, _empty())
            _check_keys(options, {'base_path', 'command', 'apply_auto_approve', 'auto_generate_backend_file'}, 'unsupported_cli_component_config')
            for option in ('apply_auto_approve', 'auto_generate_backend_file'):
                if option in options.value and type(options.value[option].value) is not bool:
                    _fail('unsupported_cli_component_config', options.value[option])
            self.component_bases[kind] = self._path_setting(base, options.value.get('base_path'), 'components/'+kind)
        self._scan(self.stack_base, 'stack')
        for directory in self.component_bases.values():
            self._scan(directory, 'component')
        patterns = {}
        for key, default in (('included_paths', ['**/*']), ('excluded_paths', [])):
            value = stackcfg.value.get(key)
            raw = _plain(value) if value is not None else default
            if not isinstance(raw, list):
                _fail('unsupported_discovery_pattern', value)
            patterns[key] = [_glob_regex(pattern) for pattern in raw]
        for relative in sorted(self.sources):
            path = self.root/relative
            if not path.is_relative_to(self.stack_base) or not relative.endswith(('.yaml', '.yml', '.yaml.tmpl', '.yml.tmpl')):
                continue
            local = path.relative_to(self.stack_base).as_posix()
            selector = re.sub(r'\.(?:yaml|yml)(?:\.tmpl)?$', '', local)
            if any(pattern.fullmatch(local) or pattern.fullmatch(selector) for pattern in patterns['included_paths']) and not any(pattern.fullmatch(local) or pattern.fullmatch(selector) for pattern in patterns['excluded_paths']):
                if selector in self.selected:
                    raise _Blocked('ambiguous_stack_selector', relative)
                self.selected[selector] = path

    def merge(self, first, later):
        self.operations += 1
        if self.operations > MAX_NODES * 4:
            raise _Blocked('repository_limit')
        old, new = first.value, later.value
        if isinstance(old, dict) and isinstance(new, dict):
            result = dict(old)
            for key, child in new.items():
                result[key] = self.merge(result[key], child) if key in result else child
            return _Value(result, self._history(first, later))
        # Native 1.199.0 fixtures qualify both directions of null transitions.
        # Empty maps preserve children; empty lists/scalars replace, as above/below.
        if old is None or new is None:
            return _Value(new, self._history(first, later))
        if type(old) is not type(new):
            _fail('merge_type_conflict', later)
        return _Value(new, self._history(first, later))

    def _history(self, first, later):
        history = first.history + later.history
        self.history_entries += len(history)
        if len(history) > 2048 or self.history_entries > MAX_HISTORY_ENTRIES:
            raise _Blocked('repository_limit')
        return history

    def _import_path(self, importer, item):
        value = item.value
        if isinstance(value, dict):
            _check_keys(item, {'path'}, 'unsupported_import_options')
            value = _plain(value.get('path', _Value(None, [])))
        if not _literal_path(value):
            _fail('unsupported_import_path', item)
        base = importer.parent if value.startswith('./') else self.stack_base
        candidate = self._contained(base/value)
        if candidate.suffix == '':
            choices = [Path(str(candidate)+suffix) for suffix in ('.yaml', '.yml', '.yaml.tmpl', '.yml.tmpl')]
            candidate = next((p for p in choices if p.relative_to(self.root).as_posix() in self.data), choices[0])
        elif candidate.suffix in ('.yaml', '.yml'):
            template = Path(str(candidate)+'.tmpl')
            if template.relative_to(self.root).as_posix() in self.data:
                candidate = template
        else:
            _fail('unsupported_import_path', item)
        if candidate.relative_to(self.root).as_posix() not in self.data:
            _fail('missing_import', item)
        return candidate

    def manifest(self, path, active=()):
        if path in active:
            raise _Blocked('import_cycle', path.relative_to(self.root).as_posix())
        if len(active) >= MAX_DEPTH:
            raise _Blocked('repository_limit')
        if path in self.imported:
            return self.imported[path]
        doc = self._parse(path)
        _check_keys(doc, {'import', 'vars', 'env', 'settings', 'terraform', 'helmfile', 'components'}, 'unsupported_manifest_field')
        result = _empty()
        imports = doc.value.get('import', _Value([], []))
        if not isinstance(imports.value, list):
            _fail('unsupported_import_shape', imports)
        for item in imports.value:
            result = self.merge(result, self.manifest(self._import_path(path, item), active+(path,)))
        own = _Value({key:value for key,value in doc.value.items() if key != 'import'}, doc.history)
        result = self.merge(result, own)
        self.imported[path] = result
        return result

    def _validate_component(self, component, kind):
        allowed = {'vars', 'env', 'settings', 'metadata', 'command', 'overrides'}
        if kind == 'terraform':
            allowed.add('providers')
        _check_keys(component, allowed, 'unsupported_component_field')
        metadata = component.value.get('metadata', _empty())
        _check_keys(metadata, {'component', 'inherits', 'type'}, 'unsupported_metadata_field')
        if 'type' in metadata.value and _plain(metadata.value['type']) not in ('abstract', 'real'):
            _fail('unsupported_metadata_type', metadata.value['type'])
        for section in _SECTIONS:
            if section in component.value:
                _mapping(component.value[section])
        for settings in [component.value.get('settings')]:
            if settings is not None and any(key in settings.value for key in ('integrations', 'spacelift')):
                _fail('unsupported_settings_transform', settings)
        overrides = component.value.get('overrides', _empty())
        _check_keys(overrides, allowed-{'metadata', 'overrides'}, 'unsupported_component_override')
        for section in _SECTIONS:
            if section in overrides.value:
                _mapping(overrides.value[section])
        return metadata

    def _direct_sections(self, value, kind):
        result = {}
        for key in (*_SECTIONS, 'command'):
            if key not in value.value:
                continue
            child = value.value[key]
            if key == 'providers' and kind != 'terraform':
                _fail('unsupported_component_field', child)
            if key == 'command':
                if not isinstance(child.value, str) or not child.value:
                    _fail('unsupported_command', child)
            else:
                _mapping(child)
                if key == 'settings' and any(k in child.value for k in ('integrations', 'spacelift')):
                    _fail('unsupported_settings_transform', child)
            result[key] = child
        return _Value(result, value.history)

    def resolve(self, stack, component):
        result = self.base_report()
        result.update({'status': 'blocked', 'stack': stack, 'component': component, 'kind': None, 'implementation': None, 'provenance': {}})
        if self.blockers:
            return result
        try:
            if not _literal_path(stack) or stack.endswith(('.yaml', '.yml')):
                raise _Blocked('invalid_stack_selector')
            if not _literal_path(component):
                raise _Blocked('invalid_component_selector')
            if stack not in self.selected:
                raise _Blocked('stack_not_discovered')
            doc = self.manifest(self.selected[stack])
            components = doc.value.get('components', _empty())
            _check_keys(components, {'terraform', 'helmfile'}, 'unsupported_component_kind')
            kinds = [kind for kind, entries in components.value.items() if component in _mapping(entries)]
            if not kinds:
                raise _Blocked('component_not_found')
            if len(kinds) != 1:
                raise _Blocked('ambiguous_component')
            kind = kinds[0]; entries = components.value[kind].value
            current = entries[component]
            metadata = self._validate_component(current, kind)
            result['kind'] = kind
            implementation = _plain(metadata.value['component']) if 'component' in metadata.value else component
            if not _literal_path(implementation):
                _fail('unsafe_implementation_path', metadata)
            result['implementation'] = implementation
            physical = self._contained(self.component_bases[kind]/implementation)
            result['implementation_path'] = physical.relative_to(self.root).as_posix()
            result['implementation_exists'] = physical.is_dir()
            scope = doc.value.get(kind, _empty())
            allowed_scope = {'vars', 'env', 'settings', 'command'} | ({'providers'} if kind == 'terraform' else set())
            _check_keys(scope, allowed_scope, 'unsupported_type_global_field')
            effective = self._direct_sections(doc, kind)
            effective = self.merge(effective, self._direct_sections(scope, kind))
            command_config = self.config.value.get('components', _empty()).value.get(kind, _empty()).value.get('command')
            command = command_config or _Value(kind, [{'path': 'atmos-literal/1.0', 'pointer': '/defaults/command', 'line': 0, 'column': 0}])
            if not isinstance(command.value, str) or not command.value:
                _fail('unsupported_command', command)
            effective = self.merge(_Value({'command': command}, []), effective)
            def inherited(name, active):
                if name in active:
                    raise _Blocked('inheritance_cycle')
                if len(active) >= MAX_DEPTH:
                    raise _Blocked('repository_limit')
                if name not in entries:
                    raise _Blocked('missing_parent')
                candidate = entries[name]
                info = self._validate_component(candidate, kind)
                merged = _empty()
                parents = info.value.get('inherits', _Value([], []))
                if not isinstance(parents.value, list):
                    _fail('unsupported_inheritance', parents)
                for parent in parents.value:
                    if not _literal_path(parent.value):
                        _fail('unsupported_inheritance', parent)
                    merged = self.merge(merged, inherited(parent.value, active+(name,)))
                # Base overrides and base metadata deliberately do not propagate.
                return self.merge(merged, self._direct_sections(candidate, kind))
            inherited_configuration = inherited(component, ())
            effective = self.merge(effective, inherited_configuration)
            effective = self.merge(effective, self._direct_sections(current.value.get('overrides', _empty()), kind))
            effective.value['metadata'] = metadata
            for section in ('vars', 'env', 'settings'):
                effective.value.setdefault(section, _empty())
            if kind == 'terraform':
                effective.value.setdefault('providers', _empty())
            provenance = {}
            def collect(value, pointer=''):
                if pointer and value.history:
                    provenance[pointer] = {'winner': value.history[-1], 'history': value.history}
                if isinstance(value.value, dict):
                    for key, child in value.value.items():
                        collect(child, _pointer(pointer, key))
                elif isinstance(value.value, list):
                    for index, child in enumerate(value.value):
                        collect(child, _pointer(pointer, index))
            collect(effective)
            result.update({'status': 'resolved', 'effective': _plain(effective), 'provenance': provenance, 'abstract': _plain(metadata).get('type') == 'abstract',
                           'selection_fingerprint': digest([self.fingerprint(), stack, kind, component,
                                                            result['implementation_path'], result['implementation_exists']])})
        except _Blocked as error:
            result['blockers'].append(error.item)
        except (OSError, ValueError, RecursionError):
            result['blockers'].append({'code': 'repository_unreadable', 'status': 'unknown'})
        return result

    def fingerprint(self):
        return digest({'adapter': _ADAPTER, 'sources': self.source_list()})

    def source_list(self):
        return [{'path': path, 'sha256': sha} for path, sha in sorted(self.sources.items())]

    def base_report(self):
        return {'schema_version': '1.0', 'adapter': _ADAPTER, 'root': str(self.root), 'source_fingerprint': self.fingerprint(), 'sources': self.source_list(), 'blockers': list(self.blockers), 'execution_authorized': False, 'stack_identity': 'physical_manifest_selector', 'logical_stack_identity': 'unknown', 'tenant_verification': 'not_established', 'runtime_config_layers': 'not_evaluated', 'evaluation_scope': 'repository_local_literal_configuration'}


def resolve_component(root, stack, component):
    """Return literal effective configuration internally; never execute Atmos or HCL.

    Configuration may contain secrets. Use public_resolution for CLI/MCP/UI output.
    The stack is a physical manifest selector relative to stacks.base_path, no extension.
    """
    return _Repository(root).resolve(stack, component)


def discover_repository(root):
    """Discover physical manifests/components without returning arbitrary config values."""
    repository = _Repository(root)
    report = repository.base_report()
    report.update({'status': 'blocked' if repository.blockers else 'discovered', 'stacks': []})
    if repository.blockers:
        return report
    for stack, path in sorted(repository.selected.items()):
        entry = {'stack': stack, 'manifest': path.relative_to(repository.root).as_posix(), 'components': [], 'blockers': []}
        try:
            doc = repository.manifest(path)
            components = doc.value.get('components', _empty())
            _check_keys(components, {'terraform', 'helmfile'}, 'unsupported_component_kind')
            for kind, values in sorted(components.value.items()):
                for name in sorted(_mapping(values)):
                    if not _literal_path(name):
                        _fail('invalid_component_selector', values)
                    resolved = repository.resolve(stack, name)
                    entry['components'].append({'name': name, 'kind': kind, 'status': resolved['status'], 'implementation': resolved['implementation'],
                                                'implementation_path': resolved.get('implementation_path'),
                                                'implementation_exists': resolved.get('implementation_exists'),
                                                'selectable': resolved['status'] == 'resolved' and not resolved.get('abstract', False), 'blockers': resolved['blockers']})
        except _Blocked as error:
            entry['blockers'].append(error.item)
        entry['status'] = 'blocked' if entry['blockers'] or any(c['status'] == 'blocked' for c in entry['components']) else 'discovered'
        report['stacks'].append(entry)
    return report


def public_resolution(report):
    """Copy a resolution report into a value-free, serializable public summary."""
    result = {key: value for key, value in report.items() if key != 'effective'}
    if 'effective' in report:
        result['configuration_sha256'] = digest(report['effective'])
        result['effective_fields'] = sorted(report['provenance'])
    return result
