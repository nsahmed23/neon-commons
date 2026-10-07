"""Inactive exact native presentation/store composition; no CLI activates it.

Only existing read-only Workbench commands are admitted by this first native
console profile. The complete parser remains shared; service/worker/mutation
routes are explicitly unsupported until their native capabilities are reviewed.
"""
from __future__ import annotations

import os
from pathlib import PureWindowsPath

from .io import AppError

READ_ONLY_COMMANDS = frozenset({'quit', 'exit', 'help', 'overview', 'next', 'previous', 'back', 'cancel',
    'search', 'search-page', 'select', 'inspect', 'settings', 'relationships', 'health', 'health-page',
    'dictionary', 'dictionary-page', 'collections', 'history', 'history-recent', 'views', 'views-page'})


def _fail(code):
    raise AppError(code, 'The inactive native Workspace capability or command route was not established.') from None


def admit_store(root, store):
    from .windows_workbench import WindowsWorkbenchStore
    if (type(store) is not WindowsWorkbenchStore or type(store.root) is not PureWindowsPath
            or type(root) not in (str, PureWindowsPath) or str(root) != str(store.root)):
        _fail('native_workspace_store_capability_required')
    # Each actual store method retains and verifies native private handles.
    # This exact type check does not replace that storage contract or activate
    # an otherwise unsupported host profile.
    return store


def require_command(name):
    if name not in READ_ONLY_COMMANDS:
        _fail('native_workspace_command_unimplemented')


class NativeWorkspaceBinding:
    def __init__(self, store):
        from .windows_terminal import NativeConsole
        from .windows_workspace_context import WindowsWorkspaceContext
        self.store = admit_store(getattr(store, 'root', None), store)
        self.context = WindowsWorkspaceContext(store)
        self.console = NativeConsole()
        self.pid = os.getpid()

    def __reduce_ex__(self, protocol):
        raise TypeError('Native Workspace bindings cannot be serialized.')

    def check(self, root):
        from .windows_terminal import NativeConsole
        from .windows_workspace_context import WindowsWorkspaceContext
        admit_store(root, self.store)
        if (self.pid != os.getpid() or type(self.console) is not NativeConsole
                or type(self.context) is not WindowsWorkspaceContext or self.context.store is not self.store):
            _fail('native_workspace_binding_changed')


def run_native_workspace(store, *, theme='dark', no_color=False, reduced_motion=True):
    """Private Python seam for reviewed native-host qualification; inactive CLI."""
    from .workbench_tui import Workspace
    from .workbench import run_terminal
    if theme not in ('dark', 'light'): _fail('workspace_theme_invalid')
    binding = NativeWorkspaceBinding(store)
    workspace = Workspace(store.root, theme=theme, no_color=no_color, reduced_motion=reduced_motion,
                          stdout=binding.console, _native_binding=binding)
    with binding.console.session():
        return run_terminal(store.root, input_fn=workspace.input, output_fn=lambda line: None,
                            result_fn=workspace.receive, _store_capability=store)
