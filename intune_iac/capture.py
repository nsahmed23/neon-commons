"""GET-only public Graph capture. Raw bytes are restricted; results contain safe codes."""
from __future__ import annotations

from contextlib import contextmanager

import errno
import hashlib
import math
import os
from pathlib import Path
import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit
from uuid import UUID

from .io import AppError, canonical, parse_json

GRAPH_ROOT = 'https://graph.microsoft.com/beta/deviceManagement/configurationPolicies'
MAX_PAGE_BYTES = 4 * 1024 * 1024
MAX_TOTAL_BYTES = 8 * 1024 * 1024
REQUEST_TIMEOUT = 20
MAX_ELAPSED_SECONDS = 120
RETRY_STATUSES = frozenset({429, 502, 503, 504})
MAX_ATTEMPTS_PER_PAGE = 10
MAX_RETRY_DELAY_SECONDS = 30


def _stamp():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


class _CaptureClock:
    """One capture's times: its start on the wall clock, every later time as that start plus monotonic elapsed time.

    A capture is one process, so its elapsed time is measured monotonically; a host clock that steps back during it
    cannot make it finish before it started (owner directive inbox/PRODUCT-TASK-12.md, section 3).
    """

    def __init__(self):
        # The start comes from _stamp, the one wall-clock seam the capture has always used.
        self.wall = datetime.fromisoformat(_stamp().replace('Z', '+00:00'))
        self.mono = time.monotonic()

    def stamp(self):
        return (self.wall + timedelta(seconds=time.monotonic() - self.mono)).isoformat().replace('+00:00', 'Z')


def _identity(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}', value):
        raise AppError('capture_identity_invalid', 'Capture requires nonzero tenant and policy UUIDs.')
    if not UUID(value).int:
        raise AppError('capture_identity_invalid', 'Capture requires nonzero tenant and policy UUIDs.')
    return value


def _trusted(url, root):
    if not isinstance(url, str) or not url or any(ord(c) < 32 or ord(c) >= 127 for c in url):
        return False
    try:
        parsed = urlsplit(url)
        return (parsed.scheme == 'https' and parsed.netloc == 'graph.microsoft.com'
                and parsed.path == urlsplit(root).path and not parsed.fragment
                and not parsed.username and not parsed.password)
    except ValueError:
        return False


def _http_transport(token):
    # This existing transport bounds DNS/connect/body wall time, shuts down
    # connected sockets on cancellation and prevents credential send after a
    # cancelled connect. It has no proxy, redirect or environment CA fallback.
    from .identity_binding import _NativeTransport, _Request
    native = _NativeTransport()
    def get(url, *, timeout):
        parsed = urlsplit(url)
        request = _Request('GET', 'graph.microsoft.com', parsed.path + ('?' + parsed.query if parsed.query else ''),
                           {'Authorization':'Bearer ' + token, 'Accept':'application/json', 'Accept-Encoding':'identity'})
        response = native(request, timeout=timeout, max_bytes=MAX_PAGE_BYTES)
        return response.status, response.body, response.headers
    return get


def _retry_delay(headers, attempt):
    """Return only numeric, inert guidance. Never echo a header or server body."""
    items = tuple(headers.items()) if isinstance(headers, dict) else headers
    if not isinstance(items, (tuple, list)) or len(items) > 100:
        return min(2 ** (attempt - 1), MAX_RETRY_DELAY_SECONDS), 'backoff'
    values = [v for pair in items if isinstance(pair, (tuple, list)) and len(pair) == 2
              for k, v in [pair] if isinstance(k, str) and k.lower() == 'retry-after']
    # Oversized or duplicate guidance cannot justify an earlier request. Stop
    # at the existing delay cap without interpreting or displaying its text.
    if len(values)>1 or len(values)==1 and isinstance(values[0],str) and len(values[0])>128:
        return MAX_RETRY_DELAY_SECONDS+1, 'retry_after_unusable'
    if len(values) == 1 and isinstance(values[0], str):
        value = values[0]
        if len(value) <= 128 and all(32 <= ord(c) < 127 for c in value):
            if re.fullmatch(r'[0-9]+', value.strip()):
                return int(value.strip()), 'retry_after_seconds'
            try:
                stamp = parsedate_to_datetime(value)
                if stamp.tzinfo is not None:
                    delay = max(0, stamp.astimezone(timezone.utc).timestamp() - time.time())
                    if math.isfinite(delay): return delay, 'retry_after_date'
            except (ValueError, OverflowError, TypeError):
                pass
    return min(2 ** (attempt - 1), MAX_RETRY_DELAY_SECONDS), 'backoff'


class _Reads:
    """One capture's bounded GET budget and immutable response/attempt records."""
    def __init__(self, write_raw, transport, native, max_pages, max_attempts, elapsed, delay, progress, stamp=_stamp):
        self.write_raw, self.transport, self.native = write_raw, transport, native
        self.stamp = stamp
        self.max_pages, self.max_attempts, self.max_delay = max_pages, max_attempts, delay
        self.deadline = time.monotonic() + elapsed
        self.progress = progress
        self.pages, self.attempts = [], []
        self.total_bytes = 0
        self.cancelled = False
        self.auth_stop = None  # token_expired / token_wrong_tenant once the service has said so

    def limit(self):
        if self.cancelled: return 'cancelled'
        if self.auth_stop: return self.auth_stop
        if len(self.attempts) >= self.max_pages: return 'page_limit'
        if self.total_bytes >= MAX_TOTAL_BYTES: return 'byte_limit'
        if time.monotonic() >= self.deadline: return 'time_limit'
        return None

    def read(self, url, kind, owner):
        for attempt_in_page in range(1, self.max_attempts + 1):
            reason = self.limit()
            if reason: return None, reason
            event = {'number':len(self.attempts)+1, 'kind':kind, 'owner_id':owner,
                     'request_url':url, 'method':'GET', 'attempt_in_page':attempt_in_page,
                     'captured_at':None, 'http_status':None, 'raw_path':None, 'error':None,
                     'retry':False, 'retry_delay_seconds':None, 'retry_delay_source':None,
                     'wait_completed':False}
            self.attempts.append(event)
            transient = False; response = None; headers = ()
            try:
                value = self.transport(url, timeout=min(REQUEST_TIMEOUT, self.deadline-time.monotonic())) if self.native else self.transport(url)
                if not isinstance(value, (tuple, list)) or len(value) not in (2, 3):
                    raise ValueError()
                status, raw = value[:2]
                headers = value[2] if len(value) == 3 else ()
                if type(status) is not int or not 100 <= status <= 599 or not isinstance(raw, bytes):
                    raise ValueError()
            except KeyboardInterrupt:
                self.cancelled = True; event['error'] = 'cancelled'
            except (TimeoutError, OSError):
                event['error'] = 'transport_failed'; transient = True
            except AppError as error:
                event['error'] = 'transport_failed'
                transient = error.code in {'identity_transport_deadline','identity_transport_unavailable'}
            except ValueError:
                event['error'] = 'invalid_transport_response'
            except Exception:
                event['error'] = 'transport_failed'
            event['captured_at'] = self.stamp()
            if event['error'] is None:
                denial = None
                if status in (401, 403):
                    # REDACTION POINT: an authentication denial is classified before anything is written. Its body can
                    # reflect a credential or claims, so only the status, a fixed code, the byte count and the body
                    # digest are kept; the body appears in neither raw/ nor the exported page.
                    from .target import classify_denial
                    denial = classify_denial(raw)
                    raw = canonical({'authentication_denial': {'http_status': status, 'code': denial or 'access_denied',
                                     'body_bytes': len(raw), 'body_sha256': hashlib.sha256(raw).hexdigest()}})
                available = min(MAX_PAGE_BYTES + 1, MAX_TOTAL_BYTES - self.total_bytes)
                stored = raw[:available]
                complete = len(raw) <= available and len(raw) <= MAX_PAGE_BYTES
                name = f'page-{len(self.pages):06d}.json'
                self.write_raw(name, stored)
                self.total_bytes += len(stored)
                record = {'kind':kind,'owner_id':owner,'request_url':url,'method':'GET',
                          'http_status':status,'captured_at':event['captured_at'],
                          'raw_path':'raw/'+name,'source_bytes':len(stored),
                          'source_byte_sha256':hashlib.sha256(stored).hexdigest(),
                          'raw_capture_complete':complete,'attempt_number':event['number'],'export_page':True}
                self.pages.append(record)
                if denial is not None:
                    # STOP POINT: the service says the token expired or belongs to another tenant. limit() now
                    # returns that reason, so no further request is made in any collection.
                    self.auth_stop = denial
                event.update(http_status=status,raw_path=record['raw_path'])
                response = (record, stored)
                transient = status in RETRY_STATUSES and complete
                if not complete: return response, 'byte_limit'
            if self.cancelled: return response, 'cancelled'
            if time.monotonic() >= self.deadline: return response, 'time_limit'
            if not transient: return response, event['error']
            if attempt_in_page >= self.max_attempts: return response, 'retry_exhausted'
            reason = self.limit()
            if reason: return response, reason
            delay, delay_source = _retry_delay(headers, attempt_in_page)
            if delay > self.max_delay: return response, 'retry_delay_limit'
            if delay >= self.deadline - time.monotonic(): return response, 'time_limit'
            event.update(retry=True,retry_delay_seconds=delay,retry_delay_source=delay_source)
            if response is not None: response[0]['export_page'] = False
            try:
                if self.progress is not None:
                    self.progress({'event':'capture_retry','kind':kind,'attempt':event['number'],
                                   'http_status':event['http_status'],'retry_in_seconds':delay,
                                   'delay_source':delay_source})
                time.sleep(delay)
                event['wait_completed'] = True
            except KeyboardInterrupt:
                self.cancelled = True
                return None, 'cancelled'
            except Exception:
                return None, 'progress_failed'
        raise AssertionError('Bounded retry loop must return.')


def reject_dot_segments(destination):
    """Refuse a literal '.' or '..' component in the ORIGINAL path string.

    pathlib silently drops '.' segments, so this must run before any Path is built from the string. One helper, called by
    _new_directory and by the sign-in preflight (signin.check_new_output), so both refuse the same paths.
    """
    text = os.fspath(destination)
    if any(piece in ('.', '..') for piece in text.replace(os.sep, '/').split('/')):
        raise AppError('capture_output_unsafe', 'Use a new output directory beneath an existing regular directory.')


def output_conflict(message, cause, number=None):
    """The capture_output_conflict refusal, carrying the condition the failed check found (cause) beside the message.

    The message and the code are what the JSON forms print and stay as they were; cause is an attribute only the text screen
    reads, so it reaches no JSON. number is the errno of the failed call, kept as its symbolic name for the 'unchecked' cause.
    """
    error = AppError('capture_output_conflict', message)
    error.cause = cause
    error.cause_errno = errno.errorcode.get(number) if isinstance(number, int) else None
    return error


def classify_output_failure(error):
    """Which condition a failed call on the output path found, read from that call's errno alone; never from a later lookup.

    ELOOP from an open with O_NOFOLLOW is the one errno that establishes a symbolic link. ENOTDIR (what Linux returns for a
    link or a plain file under O_DIRECTORY|O_NOFOLLOW) does not tell them apart, so it is told neutrally. Anything not listed is
    'unchecked'.
    """
    number = getattr(error, 'errno', None)
    if number == errno.ENAMETOOLONG:
        return 'name_too_long'
    if number == errno.EEXIST:
        return 'exists'
    if number in (errno.EACCES, errno.EPERM, errno.EROFS):
        return 'permission_denied'
    if number == errno.ENOENT:
        return 'ancestor_missing'
    if number == errno.ELOOP:
        return 'ancestor_symlink'
    if number == errno.ENOTDIR:
        return 'ancestor_not_real_directory'
    return 'unchecked'


def _new_directory(destination):
    """Open every ancestor without following links; create only one new child."""
    reject_dot_segments(destination)
    path = Path(destination).absolute()
    if path == Path('/') or any(piece in {'.', '..'} for piece in path.parts[1:]):
        raise AppError('capture_output_unsafe', 'Use a new output directory beneath an existing regular directory.')
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    parent_fd = os.open('/', flags)
    output_fd = None
    try:
        for piece in path.parts[1:-1]:
            next_fd = os.open(piece, flags, dir_fd=parent_fd)
            os.close(parent_fd); parent_fd = next_fd
        os.mkdir(path.name, mode=0o700, dir_fd=parent_fd)
        output_fd = os.open(path.name, flags, dir_fd=parent_fd)
        os.fchmod(output_fd, 0o700)
        os.fsync(output_fd); os.fsync(parent_fd)
        return path, output_fd
    except OSError as error:
        if output_fd is not None: os.close(output_fd)
        raise output_conflict('Capture requires a new directory with no symlinked ancestors; existing files are preserved.',
                              classify_output_failure(error), error.errno) from None
    finally:
        os.close(parent_fd)


def _write(directory_fd, name, data):
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o600, dir_fd=directory_fd)
    with os.fdopen(fd, 'wb') as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(data); stream.flush(); os.fsync(stream.fileno())


class _PosixFiles:
    def __init__(self,output,descriptor,raw):
        self.output,self.descriptor,self.raw=output,descriptor,raw
    def write_raw(self,name,data):_write(self.raw,name,data)
    def write(self,name,data):_write(self.descriptor,name,data)
    def finish(self):os.fsync(self.raw);os.fsync(self.descriptor)


@contextmanager
def _posix_output(destination):
    output,descriptor=_new_directory(destination);raw=None;primary=None
    try:
        os.mkdir('raw',0o700,dir_fd=descriptor)
        raw=os.open('raw',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=descriptor)
        os.fchmod(raw,0o700)
        yield _PosixFiles(output,descriptor,raw)
    except BaseException as error:primary=error;raise
    finally:
        failures=[]
        for handle in (raw,descriptor):
            if handle is not None:
                try:os.close(handle)
                except BaseException as error:failures.append(error)
        if failures:
            if primary is not None:
                primary.capture_cleanup_failures=[type(error).__name__ for error in failures]
                if hasattr(primary,'add_note'):primary.add_note('Capture descriptor cleanup also failed; preserve the primary failure and retained output.')
            else:raise failures[0]


def capture(tenant_id, policy_id, output_path, token_env='INTUNE_GRAPH_TOKEN',
            max_pages=100, transport=None, *, token=None, max_attempts_per_page=3,
            max_elapsed_seconds=MAX_ELAPSED_SECONDS,
            max_retry_delay_seconds=MAX_RETRY_DELAY_SECONDS, progress=None,
            source_is_synthetic=False):
    """Persist a caller-asserted capture; optional test transport returns response bytes.

    ``max_pages`` retains its total-attempt meaning, including retries across all
    three collections. The native transport bounds each complete network attempt
    by the remaining monotonic budget. Injected callables are trusted laboratory
    seams, not a supported arbitrary-code timeout boundary. Retry-After beyond
    the delay cap/deadline stops partial; it is never shortened to retry early.
    Low-level source provenance remains caller-declared. A typed laboratory
    reader explicitly sets source_is_synthetic=True; a transport callable or
    caller label alone never establishes authenticated Graph provenance.
    """
    if (os.name != 'posix' or not hasattr(os, 'O_DIRECTORY') or not hasattr(os, 'O_NOFOLLOW')
            or not {os.open, os.mkdir} <= os.supports_dir_fd):
        raise AppError('capture_platform_unavailable', 'Secure capture persistence is unavailable on this platform; use a supported POSIX host.')
    return _capture(tenant_id,policy_id,output_path,token_env,max_pages,transport,token=token,
        max_attempts_per_page=max_attempts_per_page,max_elapsed_seconds=max_elapsed_seconds,
        max_retry_delay_seconds=max_retry_delay_seconds,progress=progress,
        source_is_synthetic=source_is_synthetic,output_factory=_posix_output)


def _capture(tenant_id, policy_id, output_path, token_env='INTUNE_GRAPH_TOKEN',
            max_pages=100, transport=None, *, token=None, max_attempts_per_page=3,
            max_elapsed_seconds=MAX_ELAPSED_SECONDS,
            max_retry_delay_seconds=MAX_RETRY_DELAY_SECONDS, progress=None,
            source_is_synthetic=False, output_factory):
    tenant_id = _identity(tenant_id); policy_id = _identity(policy_id)
    if type(max_pages) is not int or not 1 <= max_pages <= 10000:
        raise AppError('capture_limit_invalid', 'Capture page limit must be an integer from 1 through 10000.')
    if (type(max_attempts_per_page) is not int or not 1 <= max_attempts_per_page <= MAX_ATTEMPTS_PER_PAGE
            or type(max_elapsed_seconds) not in (int,float) or not 0 < max_elapsed_seconds <= MAX_ELAPSED_SECONDS or not math.isfinite(max_elapsed_seconds)
            or type(max_retry_delay_seconds) not in (int,float) or not 0 <= max_retry_delay_seconds <= MAX_RETRY_DELAY_SECONDS or not math.isfinite(max_retry_delay_seconds)
            or progress is not None and not callable(progress)):
        raise AppError('capture_limit_invalid', 'Capture retry, deadline or progress contract is invalid.')
    native = transport is None
    if type(source_is_synthetic) is not bool:
        raise AppError('capture_provenance_invalid', 'Capture provenance must be a literal boolean; it grants no authentication or execution authority.')
    if transport is None:
        if token is None:
            # The environment-variable route; a token handed in (the descriptor route) skips it entirely.
            if not isinstance(token_env, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', token_env):
                raise AppError('capture_token_env_invalid', 'Token environment variable name is invalid.')
            token = os.environ.get(token_env)
        if not token or not isinstance(token, str):
            raise AppError('capture_token_missing', 'Set the explicitly selected token environment variable before capture.')
        if any(ord(c) < 33 or ord(c) >= 127 for c in token):
            raise AppError('capture_token_invalid', 'The selected token has an invalid encoding.')
        # STOP POINT (before any call, before the output directory exists): a token whose own claims name another
        # tenant, or that has expired. The claims are unverified: they may cause this early refusal and never permit a call.
        from .target import token_problem
        problem = token_problem(token, tenant_id, datetime.fromisoformat(_stamp().replace('Z', '+00:00')))
        if problem is not None:
            raise AppError('capture_' + problem['code'], problem['message'] + ' ' + problem['next_step'])
        transport = _http_transport(token)
    if not callable(transport):
        raise AppError('capture_transport_invalid', 'Capture transport must be callable.')

    try:
        with output_factory(output_path) as files:
            output=files.output
            clock = _CaptureClock()
            started = clock.stamp()
            reads = _Reads(files.write_raw,transport,native,max_pages,max_attempts_per_page,
                           max_elapsed_seconds,max_retry_delay_seconds,progress,stamp=clock.stamp)
            collections = []
            for kind, owner, root in [('policies', None, GRAPH_ROOT),
                                      ('settings', policy_id, GRAPH_ROOT+'/'+policy_id+'/settings'),
                                      ('assignments', policy_id, GRAPH_ROOT+'/'+policy_id+'/assignments')]:
                pages = []; reason = None; coverage = 'partial'; url = root; seen = set()
                record_ids = set(); selected_matches = 0; observed_rows = 0; declared_counts = []
                while url is not None:
                    reason = reads.limit()
                    if reason: break
                    if not _trusted(url, root):
                        reason = 'untrusted_continuation'; break
                    if url in seen:
                        reason = 'duplicate_or_looped_page'; break
                    seen.add(url)
                    response, reason = reads.read(url, kind, owner)
                    if response is None: break
                    record, stored = response
                    status = record['http_status']; captured_at = record['captured_at']
                    complete_bytes = record['raw_capture_complete']
                    body = {}; parsed = False
                    if complete_bytes:
                        try:
                            decoded = parse_json(stored.decode('utf-8'))
                            if isinstance(decoded, dict): body = decoded; parsed = True
                        except (AppError, UnicodeError):
                            pass
                    pages.append({'request_url':url,'method':'GET','http_status':status,
                                  'captured_at':captured_at,'body':body})
                    if reason: break
                    if not complete_bytes:
                        reason = 'byte_limit'; break
                    if status != 200:
                        reason = reads.auth_stop or ('access_denied' if status in {401,403} else 'http_error')
                        coverage = 'access_denied' if status in {401,403} else 'partial'; break
                    if not parsed:
                        reason = 'malformed_json'; break
                    if 'error' in body:
                        reason = 'error_envelope'; break
                    if not isinstance(body.get('value'), list) or any(not isinstance(v,dict) for v in body['value']):
                        reason = 'invalid_collection_body'; break
                    if '@odata.count' in body:
                        count = body['@odata.count']
                        if type(count) is not int or count < 0:
                            reason = 'invalid_collection_count'; break
                        declared_counts.append(count)
                    observed_rows += len(body['value'])
                    duplicate = False; missing = False
                    for record in body['value']:
                        record_id = record.get('id')
                        if not isinstance(record_id, str) or not record_id:
                            missing = True; continue
                        # UUID spelling is not identity for policy/assignment records.
                        # Setting IDs remain opaque strings; source bytes are untouched.
                        comparison_id = record_id
                        if (kind in {'policies', 'assignments'}
                                and re.fullmatch(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}', record_id)):
                            comparison_id = str(UUID(record_id))
                        if comparison_id in record_ids: duplicate = True
                        record_ids.add(comparison_id)
                        if kind == 'policies' and record_id.lower() == policy_id.lower(): selected_matches += 1
                    if missing:
                        reason = 'missing_record_identity'; break
                    if duplicate:
                        reason = 'duplicate_record_identity'; break
                    if '@odata.nextLink' in body:
                        next_url = body['@odata.nextLink']
                        if not isinstance(next_url, str) or not next_url:
                            reason = 'invalid_continuation'; break
                        url = next_url
                    else:
                        url = None; coverage = 'complete'
                if coverage == 'complete' and any(count != observed_rows for count in declared_counts):
                    coverage = 'partial'; reason = 'collection_count_mismatch'
                if kind == 'policies' and coverage == 'complete' and selected_matches != 1:
                    coverage = 'partial'; reason = 'selected_policy_missing' if not selected_matches else 'duplicate_record_identity'
                collections.append({'kind':kind,'owner_id':owner,'coverage':coverage,
                                    'reason':reason,'pages':pages})
            export = {'schema_version':'1.0.0','synthetic':source_is_synthetic,'tenant_id':tenant_id,
                      'cloud':'public','captured_at':started,
                      'exporter':{'id':'intune-iac-settings-catalog-graph','version':'1.0.0'},
                      'collections':collections,'references':[],'ownership':[]}
            # Version 2.0.0 selects the current local qualification pins (pin_profiles.py); the pin fields stay out because
            # the toolchain is not observed here (context_assurance below says so).
            context = {'schema_version':'2.0.0','tenant_id':tenant_id,'selected_policy_id':policy_id,
                       'cloud':'public','provider_source':'deploymenttheory/microsoft365',
                       'engine':'tofu','component':'intune-reference','stack':'reference-dev',
                       'authorization':'emit_only','source_is_synthetic':source_is_synthetic}
            export_bytes = canonical(export)+b'\n'; context_bytes = canonical(context)+b'\n'
            files.write('export.json', export_bytes)
            files.write('context.json', context_bytes)
            receipt = {'schema_version':'1.1.0','adapter':export['exporter'],
                       'tenant_id':tenant_id,'selected_policy_id':policy_id,'cloud':'public','api_version':'beta',
                       'tenant_assurance':'caller_asserted','started_at':started,'finished_at':clock.stamp(),
                       'target_assurance':'proposed_reference_labels_only',
                       'source_is_synthetic':source_is_synthetic,
                       'source_provenance_assurance':'caller_declared',
                       'context_assurance':'proposed_emit_only_labels_not_observed_toolchain',
                       'toolchain_observed':False,
                       'limits':{'max_pages':max_pages,'max_page_bytes':MAX_PAGE_BYTES,
                                 'max_total_bytes':MAX_TOTAL_BYTES,'request_timeout_seconds':REQUEST_TIMEOUT,
                                 'max_elapsed_seconds':max_elapsed_seconds,
                                 'max_attempts_per_page':max_attempts_per_page,
                                 'max_retry_delay_seconds':max_retry_delay_seconds},
                       'pages':reads.pages,'attempt_count':len(reads.attempts),'attempts':reads.attempts,
                       'cancelled':reads.cancelled,
                       'export_byte_sha256':hashlib.sha256(export_bytes).hexdigest(),
                       'context_byte_sha256':hashlib.sha256(context_bytes).hexdigest(),
                       'source_authenticity_verified':False,'provider_qualified':False,
                       'execution_authorized':False}
            files.write('capture-receipt.json', canonical(receipt)+b'\n')
            files.finish()
            complete = all(c['coverage']=='complete' for c in collections)
            problem = None
            if reads.auth_stop:
                from .target import service_denial
                problem = service_denial(reads.auth_stop, token, tenant_id)
            return {'status':'captured' if complete else 'partial','output':str(output),
                    'export':str(output/'export.json'),'context':str(output/'context.json'),
                    'receipt':str(output/'capture-receipt.json'),'page_count':len(reads.pages),
                    'attempt_count':len(reads.attempts),'retry_count':sum(a['retry'] for a in reads.attempts),
                    'cancelled':reads.cancelled,
                    'coverage':[{'kind':c['kind'],'coverage':c['coverage'],'reason':c['reason']} for c in collections],
                    'tenant_assurance':'caller_asserted','source_authenticity_verified':False,
                    'provider_qualified':False,'execution_authorized':False,
                    **({'credential_problem':problem} if problem else {})}
    except OSError:
        raise AppError('capture_write_failed', 'Capture persistence failed; inspect the restricted output before retrying.') from None
