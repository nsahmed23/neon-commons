"""Inactive append-only native navigation context over the existing validator.

No receipt/approval/queued command is restored. Native host qualification and
explicit Workspace/command-engine integration remain separate requirements.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
from pathlib import PureWindowsPath
import re
from types import SimpleNamespace
import uuid

from .io import AppError, canonical, parse_json
from . import windows_directory as wd, windows_storage as ws
from .workbench_tui import Workspace

SCHEMA = 'intune-native-workspace-context-history/1'
MAX_GENERATIONS = 256
MAX_BYTES = 128 * 1024
_NAME = re.compile(r'^workspace-context-([0-9]{10})-([0-9a-f]{64})\.json$')


def _fail(code):
    raise AppError(code, 'The inactive native navigation context contract was not established.') from None


class _NativeFiles:
    def __init__(self, store):
        self.root, self.api = str(store.root), store._filesystem.api

    @contextmanager
    def lock(self):
        with ws._lock(self.root, 'workspace-context.lock', self.api):
            yield

    def names(self):
        with wd._pin(self.root, self.api) as pin:
            result = self.api.names(pin._identities[-1]['final_path'])
            pin.revalidate()
            return result

    def read(self, name):
        name = ws._leaf(name)
        with wd._pin(self.root, self.api) as pin:
            path = pin._identities[-1]['final_path'].rstrip('\\') + '\\' + name
            with ws._owned_handle(self.api, self.api.open_read_guard(path)) as handle:
                before = ws._bound_file(self.api, handle, pin)
                if not 0 < before['bytes'] <= MAX_BYTES:
                    _fail('native_context_file_bound')
                data = self.api.read(handle)
                after = ws._bound_file(self.api, handle, pin)
                if (before != after or len(data) != before['bytes'] or len(data) > MAX_BYTES
                        or data != self.api.read(handle)):
                    _fail('native_context_file_changed')
                pin.revalidate()
                return data

    def publish(self, destination, data):
        if len(data) > MAX_BYTES: _fail('native_context_file_bound')
        stage = 'workspace-context-stage-' + uuid.uuid4().hex + '.json'
        ws._create_file(self.root, stage, data, self.api)
        return ws._publish(self.root, stage, destination, hashlib.sha256(data).hexdigest(), self.api)


class _ContextCore:
    def __init__(self, store, files):
        self.store, self.files = store, files

    def _validate(self, value):
        # Exactly the reference UI validator; no second parser or policy.
        Workspace._validate_context(SimpleNamespace(store=self.store), value)

    def _history(self):
        names = self.files.names()
        if (type(names) is not list or any(type(name) is not str for name in names)
                or len(names) != len(set(names))):
            _fail('native_context_namespace_invalid')
        selected = []
        for name in names:
            if name.startswith('workspace-context-') and not name.startswith('workspace-context-stage-'):
                match = _NAME.fullmatch(name)
                if match is None: _fail('native_context_generation_name')
                selected.append((int(match.group(1)), match.group(2), name))
        if len(selected) > MAX_GENERATIONS: _fail('native_context_generation_bound')
        result, previous = [], None
        for expected, (generation, sha, name) in enumerate(sorted(selected), start=1):
            if generation != expected: _fail('native_context_chain_gap_or_fork')
            raw = self.files.read(name)
            if (type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES
                    or hashlib.sha256(raw).hexdigest() != sha):
                _fail('native_context_generation_digest')
            record = parse_json(raw)
            if (type(record) is not dict or set(record) != {'schema_version', 'generation', 'previous_sha256', 'context_sha256', 'context'}
                    or record['schema_version'] != SCHEMA or type(record['generation']) is not int
                    or record['generation'] != generation or record['previous_sha256'] != previous
                    or hashlib.sha256(canonical(record['context'])).hexdigest() != record['context_sha256']):
                _fail('native_context_chain_changed')
            self._validate(record['context'])
            result.append((sha, record)); previous = sha
        return result

    def load(self):
        with self.files.lock():
            history = self._history()
            return parse_json(canonical(history[-1][1]['context'])) if history else None

    def save(self, value):
        self._validate(value)
        context = parse_json(canonical(value))
        with self.files.lock():
            history = self._history()
            if history and history[-1][1]['context'] == context:
                return {'changed': False, 'generation': len(history), 'sha256': history[-1][0], 'navigation_only': True}
            if len(history) >= MAX_GENERATIONS: _fail('native_context_generation_bound')
            generation = len(history) + 1
            record = {'schema_version': SCHEMA, 'generation': generation,
                      'previous_sha256': history[-1][0] if history else None,
                      'context_sha256': hashlib.sha256(canonical(context)).hexdigest(), 'context': context}
            raw = canonical(record)
            if len(raw) > MAX_BYTES: _fail('native_context_file_bound')
            sha = hashlib.sha256(raw).hexdigest()
            name = 'workspace-context-%010d-%s.json' % (generation, sha)
            self.files.publish(name, raw)
            # Independent re-enumeration and byte/chain readback before claiming
            # a saved navigation generation. Uncertain publication is retained.
            observed = self._history()
            if len(observed) != generation or observed[-1] != (sha, record):
                _fail('native_context_publication_changed')
            return {'changed': True, 'generation': generation, 'sha256': sha, 'navigation_only': True,
                    'native_qualified': False}


class WindowsWorkspaceContext(_ContextCore):
    def __init__(self, store):
        from .windows_workbench import WindowsWorkbenchStore
        if type(store) is not WindowsWorkbenchStore:
            _fail('native_context_store_capability_required')
        if type(store.root) is not PureWindowsPath:
            _fail('native_context_store_path_required')
        super().__init__(store, _NativeFiles(store))
