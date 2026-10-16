"""orchestration-record/1: what the engineering view accepts from an orchestration source, and how it is cleaned.

The product never imports a controller's code and never opens its store. A source adapter reads a file the
controller wrote (the first one reads the evidence loop's `orchestration-export/1`) and hands this module's checks
every line. The checks are an allowlist: a field the contract does not name is dropped, a named field of the wrong
type makes the whole line a contract fault, and no free-text field is carried: a reason is reduced to the fact that one was recorded, and every other field is a closed list or a grammar. A correlation the
source did not record stays None; nothing here infers one.

Prompts, results, summaries, producer identities beyond the role, session ids and agent configuration are not in the
contract, so no code path can show them. Evidence path text is never carried: a reference is kept (as a digest and a
size) only when its path is inside a configured root, and is otherwise only counted. The view never opens a path.
"""
from __future__ import annotations

import re
import unicodedata

EXPORT_CONTRACT = 'orchestration-export/1'
RECORD_CONTRACT = 'orchestration-record/1'
MAX_TEXT = 200
MAX_PATH = 1024

# The loop's closed list of event types (loop/model.py EVENT_TYPES). An export line with any other type is a fault.
EVENT_TYPES = frozenset((
    'migration.attempts_imported', 'attempt.recorded', 'verification.completed', 'verification.corrected',
    'blocker.recorded', 'incident.opened', 'incident.updated', 'incident.resolved', 'packet.created',
    'claim.acquired', 'claim.released', 'claim.transferred', 'dispatch.queued', 'dispatch.started',
    'dispatch.completed', 'dispatch.failed', 'dispatch.timed_out', 'dispatch.cancel_requested',
    'dispatch.cancelled', 'dispatch.unknown', 'dispatch.unavailable', 'dispatch.refused', 'advisor.completed',
    'advisor.late_result', 'report.created', 'decision.requested', 'decision.delivered', 'decision.acknowledged',
    'work_order.approved', 'work_order.rejected', 'work_order.stale', 'approval.expired', 'repair.dispatch_started',
    'repair.reported', 'requirement.accepted', 'requirement.reopened', 'telemetry.degraded'))

# The loop's closed lists: loop/model.py ROLES and loop/runner.py SCHEMAS (the dispatch kinds).
ROLES = frozenset(('controller', 'verifier', 'watcher', 'runner', 'reporter', 'migration', 'telemetry'))
DISPATCH_KINDS = frozenset(('advisor', 'repair'))
# The loop mints a task id as 'T-' + uuid4().hex[:10] (loop/runner.py:96). Shorter ids are accepted so that a
# hand-written fixture can say T-1; anything that is not 'T-' and lower-case hex is a contract fault, never shown.
_TASK = re.compile(r'T-[0-9a-f]{1,32}')
_INCARNATION = re.compile(r'[0-9a-f]{1,32}')
ATTESTED = 'controller attested'
# Ids in the loop's formats. An event id is uuid4().hex (32, loop/model.py:140) or a sha256 det_id (64, model.py:86);
# an attempt id is uuid4().hex (32, attempt.py:73 and loop/ingest.py attempt_id); lower-case hex only.
_EVENT_ID = re.compile(r'[0-9a-f]{32}|[0-9a-f]{64}')
_ATTEMPT = re.compile(r'[0-9a-f]{32}')
_ROLE = re.compile(r'[a-z]{1,16}')
# Verification fields. outcome: loop/verify.py:266. requirement: the loop's REQ-nn ids. commit and tree: git object
# names in hex. gate: the fixed names of the loop's contract (contracts/intune-acceptance.json, REQ-12:
# aggregate-regression, temporal, frame-review) and work-order-verification (recorded in the loop's real export), plus
# journey-N, N of one to three digits: the loop adds a journey gate per journey (journey-13 to journey-32 so far) and a
# digit pattern cannot carry a name. Any other name is an unknown-gate fault and is never shown.
VERIFICATION_OUTCOMES = frozenset(('pass', 'fail', 'blocked', 'incomplete'))
_GATE = re.compile(r'aggregate-regression|temporal|frame-review|work-order-verification|journey-[0-9]{1,3}')
_REQUIREMENT = re.compile(r'REQ-[0-9A-Za-z._-]{1,32}')
_GIT_HEX = re.compile(r'[0-9a-f]{7,64}')

FLAG, REASON = 'flag', 'reason'
# The only `data` fields shown, by event type, with the type each must have. A REASON is free text from the loop
# (it can hold agent configuration, a user name or a path): it is never carried, only the fact that one was recorded
# (and whether it was the controller's attestation, the one value the view reads).
DATA_FIELDS = {
    'dispatch.queued': {'kind': DISPATCH_KINDS},
    'dispatch.refused': {'kind': DISPATCH_KINDS, 'reason': REASON},
    'dispatch.started': {'adopted': FLAG, 'awaiting_controller': FLAG},
    'dispatch.failed': {'reason': REASON},
    'dispatch.unknown': {'reason': REASON},
    'dispatch.unavailable': {'reason': REASON},
    'dispatch.cancelled': {'cleanup_confirmed': FLAG, 'reason': REASON},
    'dispatch.completed': {'tree': _GIT_HEX},
    'repair.reported': {'tree': _GIT_HEX},
    'verification.completed': {'outcome': VERIFICATION_OUTCOMES, 'requirement': _REQUIREMENT, 'gate': _GATE,
                               'commit': _GIT_HEX, 'tree': _GIT_HEX},
    'verification.corrected': {'corrects': _EVENT_ID, 'replaced_by': _EVENT_ID},
}

_STAMP = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z')
_HEX64 = re.compile(r'[0-9a-f]{64}')
_UNSAFE = frozenset(('Cc', 'Cf', 'Cs', 'Co', 'Cn', 'Zl', 'Zp'))


class ContractFault(ValueError):
    """One line or the header breaks the contract. `detail` names the field or rule, never the offending value."""

    def __init__(self, code, detail, **extra):
        super().__init__('%s: %s' % (code, detail))
        self.code, self.detail, self.extra = code, detail, extra


class InvalidRoot(ValueError):
    """A configured evidence root is not a plain absolute directory path."""


def _unsafe(char):
    category = unicodedata.category(char)
    return category in _UNSAFE or (category.startswith('Z') and char != ' ')


def escape_text(value, limit=MAX_TEXT):
    """A string safe to print on a terminal: control, format, separator and unassigned characters become \\xNN, \\uNNNN
    or \\UNNNNNNNN; the result is cut after `limit` characters with '...'. Backslash is left alone, so the function is
    idempotent. None is the empty string; a non-string is its str()."""
    text = '' if value is None else value if isinstance(value, str) else str(value)
    pieces, size = [], 0
    for char in text[:limit * 4 + 4]:
        if _unsafe(char):
            code = ord(char)
            piece = '\\x%02x' % code if code < 0x100 else '\\u%04x' % code if code < 0x10000 else '\\U%08x' % code
        else:
            piece = char
        if size + len(piece) > limit:
            return ''.join(pieces) + '...'
        pieces.append(piece)
        size += len(piece)
    return ''.join(pieces) + ('...' if len(text) > limit * 4 + 4 else '')



# -- evidence paths ------------------------------------------------------------------------------------------------
def _segments(path):
    """(drive or None, segments) for an absolute path, or None when the path is not a plain absolute path: relative,
    network or device, with '..', a control or format character, or a segment Windows would read differently."""
    if not isinstance(path, str) or not path or len(path) > MAX_PATH or any(_unsafe(c) for c in path):
        return None
    text = path.replace('\\', '/')
    match = re.match(r'([A-Za-z]):/(.*)\Z', text, re.S)
    if match:
        drive, rest = match.group(1).lower(), match.group(2)
    elif text.startswith('//') or not text.startswith('/'):
        return None
    else:
        drive, rest = None, text[1:]
    segments = [part for part in rest.split('/') if part not in ('', '.')]
    for part in segments:
        if part == '..' or ':' in part or part.endswith((' ', '.')):
            return None
    return drive, tuple(segments)


def normalize_roots(roots):
    """[(drive, segments, name)]. Each root is also listed in its other spelling, because the controller records
    Windows paths and the product may run under WSL: C:/a/b and /mnt/c/a/b name one directory. A root that is not a
    plain absolute path, or that has no directory below the drive, raises InvalidRoot."""
    out = []
    for root in roots or ():
        parsed = _segments(root)
        if parsed is None or not parsed[1]:
            raise InvalidRoot('an evidence root must be an absolute directory path below a drive or "/"')
        drive, segments = parsed
        name = segments[-1]
        out.append((drive, segments, name))
        if drive is not None:
            out.append((None, ('mnt', drive) + segments, name))
        elif len(segments) > 2 and segments[0] == 'mnt' and len(segments[1]) == 1:
            out.append((segments[1].lower(), segments[2:], name))
    return out


def evidence_inside_root(path, roots):
    """True when the path is a plain absolute path strictly inside a configured root. `roots` is the result of
    normalize_roots. Only the yes or no leaves this function: the segments below the root can hold a name, a
    configuration word or a secret, so no part of the path is ever returned or shown."""
    parsed = _segments(path)
    if parsed is None:
        return False
    drive, segments = parsed
    for root_drive, root_segments, _name in roots:
        if root_drive != drive or len(segments) <= len(root_segments):
            continue
        head = segments[:len(root_segments)]
        if [a.lower() for a in head] == [b.lower() for b in root_segments] if drive else head == root_segments:
            return True
    return False


# -- header and events ---------------------------------------------------------------------------------------------
def _count(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def parse_header(raw):
    """The six header fields of orchestration-export/1, or ContractFault."""
    if not isinstance(raw, dict):
        raise ContractFault('invalid_header', 'the header is not an object')
    if raw.get('contract') != EXPORT_CONTRACT:
        raise ContractFault('invalid_header', 'contract is not %s' % EXPORT_CONTRACT)
    for field in ('source_id', 'state_digest'):
        if not (isinstance(raw.get(field), str) and _HEX64.fullmatch(raw[field])):
            raise ContractFault('invalid_header', '%s is not a sha256 digest' % field)
    if not (isinstance(raw.get('exported_utc'), str) and _STAMP.fullmatch(raw['exported_utc'])):
        raise ContractFault('invalid_header', 'exported_utc is not a UTC time')
    for field in ('count', 'last_seq'):
        if not _count(raw.get(field)):
            raise ContractFault('invalid_header', '%s is not a non-negative integer' % field)
    return {key: raw[key] for key in ('contract', 'source_id', 'exported_utc', 'count', 'last_seq', 'state_digest')}


def _bad(field):
    return ContractFault('invalid_field', field)


def ident(raw, field, grammar, required=False, allowed=None):
    """A string that matches `grammar` (and is in `allowed` when given), or ContractFault naming only the field."""
    value = raw.get(field)
    if value is None and not required:
        return None
    if not (isinstance(value, str) and grammar.fullmatch(value)) or (allowed is not None and value not in allowed):
        raise _bad(field)
    return value


def _data(kind, raw):
    spec = DATA_FIELDS.get(kind, {})
    data = raw.get('data')
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise _bad('data')
    out = {}
    for name, how in spec.items():
        value = data.get(name)
        if how == FLAG:
            if value is not None and not isinstance(value, bool):
                raise _bad('data.' + name)
            out[name] = value is True
        elif how == REASON:
            if value is not None and not isinstance(value, str):
                raise _bad('data.' + name)
            out[name + '_recorded'], out[name + '_attested'] = value is not None, value == ATTESTED
        else:  # a closed list (frozenset) or a grammar (compiled pattern); any other value is a contract fault
            if value is not None and not (isinstance(value, str) and (
                    value in how if isinstance(how, frozenset) else how.fullmatch(value))):
                if name == 'gate':
                    raise ContractFault('invalid_field', 'data.gate: unknown gate (not shown)')
                raise _bad('data.' + name)
            out[name] = value
    return out


def _evidence(raw, roots):
    """(kept refs, rejected count). A ref outside every root is counted and dropped; a ref with a wrong type is a fault."""
    refs = raw.get('evidence')
    if refs is None:
        refs = []
    if not isinstance(refs, list):
        raise _bad('evidence')
    kept, rejected = [], 0
    for ref in refs:
        if not isinstance(ref, dict):
            raise _bad('evidence')
        digest, size = ref.get('sha256'), ref.get('bytes')
        if digest is not None and not (isinstance(digest, str) and _HEX64.fullmatch(digest)):
            raise _bad('evidence.sha256')
        if size is not None and not _count(size):
            raise _bad('evidence.bytes')
        if evidence_inside_root(ref.get('path'), roots):
            kept.append({'sha256': digest, 'bytes': size})  # no path text is carried
        else:
            rejected += 1
    return kept, rejected


def event_key(raw):
    """(event_id, seq) of one export line, or ContractFault. Checked first, so a faulty line is still counted."""
    seq = raw.get('seq')
    if not (isinstance(seq, int) and not isinstance(seq, bool) and seq >= 1):
        raise _bad('seq')
    return ident(raw, 'event_id', _EVENT_ID, required=True), seq


def parse_event(raw, roots=()):
    """(record, rejected evidence count) for one export line, or ContractFault. `roots` is from normalize_roots."""
    event_id, seq = event_key(raw)
    kind = raw.get('event_type')
    if not isinstance(kind, str) or kind not in EVENT_TYPES:
        raise ContractFault('unknown_event_type', 'event_type is not in the contract list')
    stamp = raw.get('wall_utc')
    if not (isinstance(stamp, str) and _STAMP.fullmatch(stamp)):
        raise _bad('wall_utc')
    evidence, rejected = _evidence(raw, roots)
    record = {'seq': seq, 'event_id': event_id, 'event_type': kind,
              'role': ident(raw, 'role', _ROLE, required=True, allowed=ROLES), 'task': ident(raw, 'task', _TASK),
              'attempt': ident(raw, 'attempt', _ATTEMPT), 'incarnation': ident(raw, 'incarnation', _INCARNATION),
              'wall_utc': stamp,
              'evidence': evidence, 'data': _data(kind, raw)}
    return record, rejected
