"""The companion's entry: write the page to a file, or serve it on this machine's loopback, from one read.

Requirement 17 UX-VIS, second slice. `run_companion(read, out=PATH)` writes a static page and says that it does not
update itself; `run_companion(read, serve=True, announce=print)` starts the loopback listener (companion_live),
announces its address and blocks until Ctrl+C, the idle limit or stop. Neither launches a browser: on a headless host
the engineer is told a file path or an address and opens it where a browser is. The workbench subcommand and the
actions menu are thin callers of this function and of start_live (a listener that does not block, for a frame).

`read()` is the caller's one way to the read model, called afresh for every page and snapshot so live mode sees change:
    {'value': <the relationships result for one object, with the selected repository if there is one>,
     'mode_class': <evidence class>, 'tenant': <tenant id>, 'names': {id: name}, 'states': {id: operation word},
     'freshness': <the observation's freshness word>}
Only 'value' is required. A read that cannot name the object raises AppError: a file is not written, and live mode
reports the snapshot unavailable (stale, no revision) and serves no page.
"""
from __future__ import annotations

import os
from pathlib import Path
import tempfile

from .companion_live import IDLE_SECONDS, POLL_SECONDS, LiveCompanion
from .companion_page import render_page, snapshot_record
from .graph_projection import project
from .io import AppError


def _read(read):
    snapshot = read()
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get('value'), dict):
        raise AppError('companion_snapshot_invalid', 'The companion needs a read that returns the relationships result as "value".')
    return snapshot


def _graph(snapshot):
    return project(snapshot['value'], names=snapshot.get('names'), states=snapshot.get('states'),
                   freshness=snapshot.get('freshness'))


def _observed(snapshot):
    value = snapshot['value'].get('observed_at')
    return value if isinstance(value, str) and value else None


def build_page(read, live=None):
    """The page for the current read, and its graph."""
    from .workbench_screens import relationship_lines
    snapshot = _read(read)
    graph = _graph(snapshot)
    try:
        tree = relationship_lines(snapshot['value'], 100, 'unicode')
    except (KeyError, TypeError, ValueError):
        tree = None
    page = render_page(graph, mode_class=snapshot.get('mode_class'), tenant=snapshot.get('tenant'),
                       observed_at=_observed(snapshot), tree_lines=tree, live=live)
    return page, graph


def snapshot_of(read):
    """The current snapshot's revision, evidence mode and observation time, or that the object cannot be read."""
    try:
        snapshot = _read(read)
    except AppError:
        return {'schema_version': 'workbench-companion-page/1', 'status': 'object_unavailable', 'revision': None,
                'mode': None, 'observed_at': None}
    return snapshot_record(_graph(snapshot), snapshot.get('mode_class'), _observed(snapshot))


def _invalid(message):
    return AppError('companion_out_invalid', message)


def write_static(read, out):
    """Write the page to `out` (an existing folder, not a link, not a folder), whole or not at all."""
    if not isinstance(out, str) or not out:
        raise _invalid('Give the path of the file to write.')
    path = Path(out).absolute()
    if path.is_symlink() or path.is_dir() or not path.parent.is_dir():
        raise _invalid('The companion file must be a new or existing regular file in an existing folder.')
    page, graph = build_page(read)
    data = page.encode('utf-8')
    descriptor, temporary = tempfile.mkstemp(prefix='.companion-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError:
        raise _invalid('The companion file could not be written.') from None
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    shown = str(path.resolve())
    return {'mode': 'file', 'path': shown, 'bytes': len(data), 'revision': graph['revision'],
            'notice': 'Wrote %s (revision %s). Open it in a browser on this machine; it does not update itself. '
                      'No browser was opened.' % (shown, graph['revision'][:12])}


def start_live(read, *, idle_seconds=IDLE_SECONDS, poll_seconds=POLL_SECONDS):
    """Start the loopback listener for `read` and return it (it has .address, .notice, .stop() and .wait()).

    It binds 127.0.0.1 only and enforces its own idle limit, so a caller that keeps the object and never calls wait()
    still gets it. There is no token argument: the path token is made inside, from 24 random bytes."""
    live = LiveCompanion(lambda settings: build_page(read, settings)[0], lambda: snapshot_of(read),
                         idle_seconds=idle_seconds, poll_seconds=poll_seconds)
    live.start()
    live.notice = ('Listening on %s (this machine only). This address is a secret: anyone on the same machine who has it can '
                   'read the page, because users of one machine are not isolated from each other, and the browser may keep it '
                   'in its history. Ctrl+C stops it; it also stops after %d minutes without a page request. '
                   'No browser was opened.' % (live.address, max(1, round(idle_seconds / 60))))
    return live


def run_companion(read, *, out=None, serve=False, announce=None, idle_seconds=IDLE_SECONDS, poll_seconds=POLL_SECONDS):
    """Write the static page (out=PATH) or serve it on loopback (serve=True, announce=callable taking the notice).

    Returns a result dict. A static result names the file; a live result says only how the listener ended
    ('interrupted' for Ctrl+C, 'idle', or 'stopped'), and never repeats the address or its token."""
    if bool(serve) == (out is not None):
        raise AppError('companion_target_required', 'Give either a file to write (out) or live mode (serve), not both and not neither.')
    if not serve:
        return write_static(read, out)
    if not callable(announce):
        raise AppError('companion_announce_required', 'Live mode needs a way to tell the engineer the address.')
    live = start_live(read, idle_seconds=idle_seconds, poll_seconds=poll_seconds)
    reason = 'interrupted'
    try:
        announce(live.notice)
        reason = live.wait()
    except KeyboardInterrupt:
        reason = 'interrupted'
    finally:
        live.stop()
    return {'mode': 'live', 'stopped': reason}
