#!/usr/bin/env python3
"""Build separate runnable plugin and source/evaluation archives."""
import argparse
import contextlib
import fnmatch
import getpass
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from intune_iac import __version__
from intune_iac import build_identity

EXCLUDE={'.git','__pycache__','.venv','.intune-iac','.superpowers','dist','build'}
SOURCE_INVENTORY = 'release-source-files.txt'
# Names a release never carries, matched on the file's own name without regard to case. The older guard in source_files stays
# as it was; these are refused beside it.
SENSITIVE_NAMES = ('*.tfstate', '*.tfstate.*', '.env', '.env.*', '*.pem', '*.key', '*.pfx', '*.p12', 'id_rsa*', 'id_ed25519*',
                   'credentials.json', '.netrc', '.npmrc', '.pypirc')
# The content report. SHAPE_KINDS names the product detector's shapes (intune_iac.judge._SECRET_SHAPES) in their order.
ALLOWANCE_FILE = 'release-sensitive-allow.txt'
SHAPE_KINDS = ('jwt', 'bearer', 'private_key', 'vendor_token', 'entra_secret', 'url_password')
# These refuse the build unless the reviewed allowance file covers the file. The two weakest shapes (a Bearer word followed by
# token-like text, and user:password in a URL) match prose and examples about as often as secrets, so they are counted in the
# receipt and never refuse: an allowance entry for each would be a rubber stamp.
REFUSED_KINDS = ('private_key', 'jwt', 'vendor_token', 'entra_secret', 'host_home_path')
COUNTED_KINDS = ('bearer', 'url_password')
PRIVATE_KEY_MARKER = re.compile(r'-----BEGIN [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----')
CONTENT_LIMITS = ("This control matches fixed secret shapes, private-key block markers and the building host's own home path and "
                  "user name. It does not classify arbitrary content: a secret with no recognizable shape passes, and so does "
                  "the home path of another host.")


def git_environment():
    """The environment git runs in: the caller's, without the GIT_* variables that could point it at another repository."""
    return {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}


def git_state(detail=False):
    """The checkout's commit, tree and whether tracked files differ from them; nulls when that cannot be established.

    Only a checkout whose own top level is ROOT is described: a temporary tree that happens to sit inside another
    repository must not take that repository's commit. With detail=True the result also holds 'changes', git's own list of
    tracked modifications, so that two readings can be compared for any movement and not only for a change of the flag.
    """
    def git(*args):
        try:
            result = subprocess.run(['git', '-C', str(ROOT), *args], capture_output=True, text=True, timeout=60, env=git_environment())
        except (OSError, subprocess.SubprocessError):
            return None
        return result.stdout.strip() if result.returncode == 0 else None
    unknown = {'commit': None, 'tree': None, 'dirty': None}
    if detail:
        unknown['changes'] = None
    top = git('rev-parse', '--show-toplevel')
    if top is None or Path(top).resolve() != ROOT.resolve():
        return unknown
    commit, tree, status = git('rev-parse', 'HEAD'), git('rev-parse', 'HEAD^{tree}'), git('status', '--porcelain', '--untracked-files=no')
    if not all(isinstance(value, str) and re.fullmatch(r'[0-9a-f]{40}', value) for value in (commit, tree)) or status is None:
        return unknown
    state = {'commit': commit, 'tree': tree, 'dirty': bool(status)}
    if detail:
        state['changes'] = status
    return state


def bind_to_commit(snapshot, state):
    """Hold the files the archives will contain to the commit the identity names; return the names that differ from it.

    Every inventoried path must be in that commit. An untracked, ignored or newly added path would be shipped although the
    commit the record names does not hold it, so it is refused. A captured file whose bytes differ from the commit's blob makes
    the build dirty even when git's own status shows nothing (assume-unchanged, skip-worktree). With no commit (a tree outside
    a checkout) there is nothing to bind to and the identity names none.
    """
    commit = state['commit']
    if commit is None:
        return []
    # The commit that was captured, never the symbolic HEAD, which can move between the last reading of the checkout and this one.
    if not isinstance(commit, str) or re.fullmatch(r'[0-9a-f]{40}', commit) is None:
        raise ValueError('The commit the identity names is not a full object name.')
    try:
        listing = subprocess.run(['git', '-C', str(ROOT), 'ls-tree', '-r', '-z', commit], capture_output=True, timeout=120,
                                 env=git_environment())
    except (OSError, subprocess.SubprocessError):
        raise ValueError('The commit the identity names cannot be listed.')
    if listing.returncode != 0:
        raise ValueError('The commit the identity names cannot be listed.')
    tracked = {}
    for entry in listing.stdout.split(b'\0'):
        if entry:
            meta, _, path = entry.partition(b'\t')
            _, kind, blob = meta.decode().split(' ')
            tracked[path.decode('utf-8', 'surrogateescape')] = (kind, blob)
    missing = [name for name in sorted(snapshot) if tracked.get(name, (None, None))[0] != 'blob']
    if missing:
        raise ValueError('Inventoried path is untracked, ignored or not committed: ' + ', '.join(missing[:20]))
    return [name for name, data in sorted(snapshot.items())
            if hashlib.sha1(b'blob %d\0' % len(data) + data, usedforsecurity=False).hexdigest() != tracked[name][1]]


def build_time():
    """UTC build time in whole seconds; SOURCE_DATE_EPOCH, when set, makes a rebuild name the same moment."""
    epoch = os.environ.get('SOURCE_DATE_EPOCH')
    moment = datetime.fromtimestamp(int(epoch) if epoch else datetime.now(timezone.utc).timestamp(), timezone.utc)
    return moment.strftime('%Y-%m-%dT%H:%M:%SZ')


def content_digests(snapshot, runtime):
    """The content_sha256 that the runtime and the source archive's BUILD-IDENTITY.json record, from the captured files alone.

    The runtime digest covers the runtime members and the source digest every captured member, each without the identity record
    and without SHA256SUMS, which are written afterwards. --check-only reports these and the build embeds them, so an extracted
    source tree (which has no .git) can show that it holds everything the runtime archive was made from.
    """
    def digest(names):
        return build_identity.content_digest({name: hashlib.sha256(snapshot[name]).hexdigest() for name in names})
    return digest(sorted(runtime)), digest(sorted(snapshot))


def with_identity(content, identity):
    """The archive members plus BUILD-IDENTITY.json, and the content digest the record holds.

    The record is added before SHA256SUMS is written, so SHA256SUMS lists it and any edit of it is caught.
    """
    if build_identity.IDENTITY_FILE in content:
        raise ValueError('The build identity file name is reserved.')
    digest = build_identity.content_digest({name: hashlib.sha256(data).hexdigest() for name, data in content.items()})
    record = dict(identity, schema_version=build_identity.SCHEMA, file_count=len(content), content_sha256=digest)
    return dict(content, **{build_identity.IDENTITY_FILE: (json.dumps(record, indent=2, sort_keys=True) + '\n').encode()}), digest


def safe_name(name):
    """Archive paths are portable, root-relative POSIX file names."""
    if (not isinstance(name, str) or not name or '\\' in name or ':' in name
            or name == 'SHA256SUMS' or name.startswith('/')
            or any(part in {'', '.', '..'} for part in name.split('/'))):
        raise ValueError('Unsafe release member path.')
    return name


def allowed(path):
    relative=path.relative_to(ROOT)
    parents = [ROOT.joinpath(*relative.parts[:index]) for index in range(1, len(relative.parts) + 1)]
    return (path.is_file() and not any(item.is_symlink() for item in parents)
            and not set(relative.parts)&EXCLUDE and path.suffix!='.pyc')


@contextlib.contextmanager
def source_reader():
    """Read bounded regular files beneath one anchored checkout descriptor.

    Release building requires POSIX no-follow directory opens. The distributed
    plugin runtime does not inherit this release-tool platform restriction.
    """
    if os.open not in os.supports_dir_fd or not all(hasattr(os, name) for name in ('O_NOFOLLOW', 'O_DIRECTORY')):
        raise ValueError('Release building requires no-follow directory descriptor support.')
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    root_fd = os.open(ROOT, directory_flags)
    def read(name):
        safe_name(name)
        parent_fd = os.dup(root_fd)
        try:
            parts = name.split('/')
            for part in parts[:-1]:
                child_fd = os.open(part, directory_flags, dir_fd=parent_fd)
                os.close(parent_fd)
                parent_fd = child_fd
            fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | getattr(os, 'O_NONBLOCK', 0), dir_fd=parent_fd)
            with os.fdopen(fd, 'rb') as stream:
                before = os.fstat(stream.fileno())
                if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                    raise ValueError('Source release member must be a regular file with one link.')
                data = stream.read(32 * 1024 * 1024 + 1)
                after = os.fstat(stream.fileno())
                if (after.st_nlink != 1 or len(data) > 32 * 1024 * 1024 or len(data) != before.st_size
                        or (before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                        != (after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
                    raise ValueError('Source release member is oversized or changed while reading.')
                return data
        finally:
            os.close(parent_fd)
    try:
        yield read
    finally:
        os.close(root_fd)


def sensitive_name(name):
    """Whether the file's own name is one a release never carries."""
    own = Path(name).name.lower()
    return any(fnmatch.fnmatchcase(own, pattern) for pattern in SENSITIVE_NAMES)


def source_files(inventory_bytes=None):
    """Only reviewed inventory entries enter the source distribution.

    This is a selection boundary: it refuses sensitive names. The bytes of what is selected are looked at by scan_content.
    Adding files requires deliberate review and editing the inventory in source control.
    """
    inventory = ROOT / SOURCE_INVENTORY
    if not allowed(inventory):
        raise ValueError('A regular reviewed source inventory is required.')
    names = []
    if inventory_bytes is None:
        with source_reader() as read:
            inventory_bytes = read(SOURCE_INVENTORY)
    for line in inventory_bytes.decode('utf-8').splitlines():
        if not line or line.startswith('#'):
            continue
        name = safe_name(line)
        if name in names or not allowed(ROOT / name):
            raise ValueError('Duplicate, missing or unsafe source inventory member: ' + name)
        if Path(name).name == '.env' or '.tfstate' in Path(name).name or Path(name).suffix in {'.key', '.pem'}:
            raise ValueError('Sensitive artifact name is not allowed in a release: ' + name)
        if sensitive_name(name):
            raise ValueError('Sensitive artifact name is not allowed in a release: ' + name)
        names.append(name)
    if SOURCE_INVENTORY not in names:
        raise ValueError('Source inventory must include itself.')
    return sorted(names)


def runtime_files():
    names=['plugin.json','.codex-plugin/plugin.json','.claude-plugin/plugin.json','.agents/plugins/marketplace.json',
           'README.md','RELEASE-VERIFICATION.md','THIRD-PARTY-NOTICES.md','requirements-runtime.txt',
           'requirements-runtime-linux-x86_64-cp312.lock','dependency-lock.json','scripts/verify-dependencies.py',
           'scripts/intune-iac.py','examples/context.json','examples/supported/input/export.json','examples/clm-config.json',
           'contracts/journey-actions.json','contracts/journey-semantics.json',
           # The families view reads the table and the integration manifest; without them it reports "not packaged".
           'contracts/integration-manifest.json','family-coverage.csv']
    for folder,pattern in [('intune_iac','*.py'),('reference','*.py'),('contracts','*.schema.json'),
                           ('corrections/contracts','*.json'),('corrections/models','*.py'),('skills','*')]:
        names.extend(p.relative_to(ROOT).as_posix() for p in (ROOT/folder).rglob(pattern) if allowed(p))
    names.extend('docs/'+name for name in ['HOSTS.md','WIZARD.md','GRAPH.md','RUNNER.md','CAPTURE.md','CLM.md','MCP.md','REPOSITORY.md','PRODUCTION-MAPPING.md','PRODUCT-STATUS.md','DATA-HANDLING.md','LABS.md','WORKFLOW.md','TARGET.md','EXECUTION.md','DEPENDENCIES.md','ENTERPRISE-GOAL.md','ENTERPRISE-EXECUTION-LEDGER.md','CI.md'])
    names.extend(['docs/CANDIDATE-GUIDE.md','scripts/demo-clean-install.sh'])
    names.extend('docs/'+name for name in ['JOURNEY.md','PROTECTED-EXECUTION.md','SECURITY-ASSURANCE.md','SYNTHETIC-LABS.md','COMPLETION-ACCEPTANCE.md'])
    names.extend('docs/'+name for name in ['IDENTITY-BINDING.md','SIGNED-APPROVAL.md','PROVIDER-JOURNEY.md','BLOB-LEASE.md','PRODUCTION-COMPLETION-ACCEPTANCE.md'])
    names.extend('docs/'+name for name in ['EPOCH-ACCEPTANCE.md','OPERATIONS-EPOCH.md','TERMINAL-SECURITY-QUALIFICATION.md','POWERSHELL-PREVIEW-QUALIFICATION.md','WORKBENCH.md','CONTINUATION-R3.md','EXTERNAL-QUALIFICATION-R3.md','VENDOR-REFERENCE-LINEAGE.md'])
    # Operational documentation and explicit host launchers are part of the
    # delivered application routes. Relay source plus its documented build
    # recipe are included; compiled tools and private runtime artifacts are not.
    names.extend('docs/'+name for name in [
        'ARTIFACT-ARCHIVAL-R4.md','AUTHENTICATED-OBSERVATION-R4.md','AZURE-BACKEND-R4.md',
        'CONTINUATION-R4-CHECKPOINT.md','CONTINUATION-R4-LEDGER.json',
        'DICTIONARY-PROVENANCE-R4.md','NATIVE-WINDOWS-R4.md','OPERATING-PROFILE-R4.md',
        'PROTECTED-WORKER-R4.md','STRICT-CONTINUATION-CONTRACT-R4.md',
        'VISUAL-WORKSPACE-R4.md','WORKBENCH-QUEUE-R4.md','WORKBENCH-VIEWS-R4.md',
        'WORKER-BROKER-R4.md','WORKER-HOST-R4.md','WORKER-PROVIDER-R4.md',
        'HOST-CAPABILITIES-R4.md','WINDOWS-STORAGE-ADAPTER-R4.md',
        'EXTERNAL-GATES-R4.md','SERVICE-VIEWS-R4.md','WORKER-PRECONDITION-R4.md',
        'WORKER-RECOVERY-R4.md','WORKER-SERVICE-R4.md','WORKER-STATE-R4.md',
        'WINDOWS-DIRECTORY-COMPONENT-R4.md','WINDOWS-STORAGE-COMPONENT-R4.md',
        'WINDOWS-SQLITE-COMPONENT-R4.md','WINDOWS-WORKBENCH-ADAPTER-R4.md',
        'DESCRIPTION-RECOVERY-R4.md',
        'WORKER-LEASE-RECOVERY-R4.md',
        'CAPTURE-PROVENANCE-R4.md',
        'WINDOWS-READERS-R4.md',
        'WINDOWS-OBSERVATION-R4.md',
        'NATIVE-WINDOWS-CONSOLE-R4.md',
        'WINDOWS-OBSERVER-JOB-R4.md',
        'WINDOWS-FOUR-VIEWS-R4.md',
        'QUALIFICATION-TOOLS-R4.md',
        'WINDOWS-REPOSITORY-R4.md',
        'WORKER-ADOPTION-STATE-R4.md',
        'WINDOWS-SOURCE-R4.md',
        'WORKER-ADOPTION-R4.md',
        'WORKER-ADOPTION-RECOVERY-R4.md',
        'WORKER-ADOPTION-RECOVERY-PLAN-R4.md',
        'WINDOWS-SOURCE-EDIT-R4.md',
        'WORKER-SOURCE-INTENT-R4.md','NATIVE-PLAN-EVIDENCE-R4.md','EVIDENCE-SNAPSHOT-R4.md',
        'WORKER-ADOPTION-PLAN-RECOVERY-R4.md','ADOPTION-PLAN-SUCCESSOR-R4.md',
        'WORKER-ADOPTION-PLAN-OBSERVATION-R4.md',
        'ADOPTION-UNACQUIRED-PLAN-R4.md','PUBLIC-SERVICE-READS-R4.md',
        'WORKER-EVIDENCE-R4.md','WINDOWS-WORKER-EVIDENCE-R4.md',
        'EXECUTION-SEQUENCE-R4.md',
        'WINDOWS-READONLY-CONTINUATION-R4.md','WORKER-COMMITTED-STATE-RECOVERY-R4.md',
        'WORKER-PARTIAL-RECOVERY-R4.md',
        'EVIDENCE-PRODUCTION-R4.md',
        'PACKAGE-QUALIFICATION-R4.md',
        'DELIVERY-TRANSFER-R4.md',
        'COMPLETE-LAYER-RESTORATION-R4.md','EVIDENCE-RESTORATION-R4.md',
        'CONTINUATION-LAYERS-R4.template.json'])
    names.extend(['scripts/intune-workbench.sh','scripts/intune-workbench.ps1',
                  'scripts/qualify-windows-workbench.py','native/worker-relay/relay.c',
                  'scripts/qualify-windows-directory.py','scripts/qualify-windows-storage.py',
                  'scripts/qualify-windows-sqlite.py','scripts/qualify-windows-store.py',
                  'scripts/intune-windows-inspect.py','scripts/qualify-windows-readers.py',
                  'scripts/qualify-windows-observation.py',
                  'scripts/qualify-native-console.py',
                  'scripts/intune-windows-observer.py','scripts/qualify-windows-observer-job.py',
                  'scripts/prepare-ci-validator.py',
                  'scripts/download-complete-layers.py','scripts/stage-release-git.py',
                  'scripts/qualification_tools.py','scripts/prepare-qualification-tools.py',
                  'native/worker-relay/relay-v2.c',
                  'scripts/qualify-windows-repository.py',
                  'scripts/qualify-windows-source.py',
                  'scripts/qualify-windows-source-edit.py',
                  'scripts/intune-windows-source.py',
                  'scripts/intune-worker-evidence.py','scripts/intune-windows-evidence.py',
                  'scripts/qualify-windows-worker-evidence.py',
                  'scripts/restore-evidence-layer.py','scripts/restore-complete-layers.py',
                  'scripts/build-evidence-layer.py','scripts/verify-source-linkage.py',
                  'scripts/verify-release-artifact.py'])
    return sorted(set(names))


def host_identity():
    """The building host's home folder and user name: the two things a release must not carry by accident."""
    try:
        user = getpass.getuser()
    except (KeyError, OSError):
        user = ''
    return os.environ.get('HOME') or str(Path.home()), user


def mask(value):
    """Enough of a value to find the place, not enough to use it: its first four characters and its length."""
    return value[:4] + '*' * 8 + f' ({len(value)} characters)'


def read_allowances(data):
    """The reviewed allowance file: one 'path | sha256 | kind | reason' per line; blank lines and # comments are skipped.

    An entry covers one kind of finding in one file with exactly these bytes, so editing the file ends the allowance.
    """
    entries = {}
    for number, line in enumerate(data.decode('utf-8').splitlines(), 1):
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        parts = [part.strip() for part in line.split(' | ', 3)]
        valid = (len(parts) == 4 and re.fullmatch(r'[0-9a-f]{64}', parts[1]) is not None and parts[2] in REFUSED_KINDS
                 and 0 < len(parts[3]) <= 300)
        try:
            valid = valid and safe_name(parts[0]) == parts[0]
        except ValueError:
            valid = False
        key = tuple(parts[:3])
        if not valid or key in entries:
            raise ValueError(f'{ALLOWANCE_FILE} line {number} is not a new "path | sha256 | kind | reason" entry '
                             f'with a known kind ({", ".join(REFUSED_KINDS)}) and a one-line reason.')
        entries[key] = parts[3]
    return entries


def scan_content(snapshot):
    """Look at the bytes about to be archived for what a source tree should not carry.

    Returns (findings, counted, scanned_bytes). A finding is one kind in one file: its path, the sha256 of the captured bytes,
    the kind, how many matches, the first line and the first match masked; the value itself is never kept. The kinds are the
    product's own secret shapes (intune_iac.judge), private-key block markers and the building host's home path and user name.
    The two weakest shapes are only counted.
    """
    from intune_iac import judge
    if len(judge._SECRET_SHAPES) != len(SHAPE_KINDS):
        raise ValueError('The product secret detector changed; update SHAPE_KINDS in this script before building.')
    home, user = host_identity()
    host = []
    if len(home) > 1:
        host.append((re.compile(re.escape(home.encode()) + rb'(?![A-Za-z0-9_.-])'), '<home>'))
    if len(user) >= 3 and user != 'root':
        host.append((re.compile(rb'(?<=[/\\])' + re.escape(user.encode()) + rb'(?![A-Za-z0-9_.-])'), '<user>'))
    findings, counted, scanned = [], {kind: {'files': 0, 'matches': 0} for kind in COUNTED_KINDS}, 0
    for name, data in sorted(snapshot.items()):
        scanned += len(data)
        text = data.decode('utf-8', errors='replace')
        found = {}
        for kind, shape in zip(SHAPE_KINDS, judge._SECRET_SHAPES):
            found.setdefault(kind, {}).update({match.start(): (text.count('\n', 0, match.start()) + 1, mask(match.group(0)))
                                               for match in shape.finditer(text)})
        found['private_key'].update({match.start(): (text.count('\n', 0, match.start()) + 1, mask(match.group(0)))
                                     for match in PRIVATE_KEY_MARKER.finditer(text)})
        found['host_home_path'], covered_spans = {}, []
        for pattern, label in host:     # the home path first: a user name inside it is the same occurrence, not a second one
            for match in pattern.finditer(data):
                if not any(start <= match.start() and match.end() <= end for start, end in covered_spans):
                    found['host_home_path'][match.start()] = (data.count(b'\n', 0, match.start()) + 1, label)
                    covered_spans.append((match.start(), match.end()))
        digest = hashlib.sha256(data).hexdigest()
        for kind in COUNTED_KINDS:
            if found[kind]:
                counted[kind]['files'] += 1
                counted[kind]['matches'] += len(found[kind])
        for kind in REFUSED_KINDS:
            if found[kind]:
                first = found[kind][min(found[kind])]
                findings.append({'path': name, 'sha256': digest, 'kind': kind, 'count': len(found[kind]), 'line': first[0],
                                 'masked': first[1]})
    return findings, counted, scanned


def write_archive(destination,names,prefix):
    if destination.is_symlink():
        raise ValueError('Archive destination must not be a symlink.')
    for name in names:
        safe_name(name)
        # The generated build identity record has no file in the checkout; with_identity is its only producer.
        if name == build_identity.IDENTITY_FILE and isinstance(names, dict):
            continue
        if not allowed(ROOT / name):
            raise ValueError('Release member changed or is unsafe: ' + name)
    if isinstance(names, dict):
        content = dict(names)
        if any(not isinstance(data, bytes) for data in content.values()):
            raise ValueError('Archive snapshot must contain bytes.')
    else:
        with source_reader() as read:
            content = {name: read(name) for name in names}
    hashes={name:hashlib.sha256(data).hexdigest() for name,data in content.items()}
    content['SHA256SUMS']=''.join(f'{value}  {name}\n' for name,value in sorted(hashes.items())).encode()
    with zipfile.ZipFile(destination,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for name,data in sorted(content.items()):
            if Path(name).is_absolute() or '..' in Path(name).parts:raise ValueError('unsafe member')
            info=zipfile.ZipInfo(prefix+'/'+name,date_time=(2026,9,30,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=(stat.S_IFREG|0o644)<<16
            archive.writestr(info,data)
    return {'filename':destination.name,'files':len(content),'listed_hashes':len(hashes),
            'bytes':destination.stat().st_size,'sha256':hashlib.sha256(destination.read_bytes()).hexdigest()}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--output-dir',help='Create exact runtime/source archives in a new external output directory')
    mode.add_argument('--check-only',action='store_true',help='Read and validate the complete reviewed source/runtime snapshot without creating archives, and report the content digests the archives would record')
    args=parser.parse_args();out=None if args.check_only else Path(args.output_dir).resolve()
    root = ROOT.resolve()
    if out is not None and (root==out or root in out.parents):raise ValueError('Use an output directory outside the source checkout.')
    runtime=runtime_files()
    for name in runtime:
        safe_name(name)
        if not allowed(ROOT/name):raise ValueError('Missing or unsafe required runtime member: '+name)
    # The checkout is read before and after the snapshot and must not have moved; the identity then describes the files captured.
    before = git_state(detail=True)
    with source_reader() as read:
        if not allowed(ROOT/SOURCE_INVENTORY):
            raise ValueError('A regular reviewed source inventory is required.')
        inventory_bytes = read(SOURCE_INVENTORY)
        source = source_files(inventory_bytes)
        if not set(runtime).issubset(source):
            raise ValueError('Runtime members must be included in the reviewed source inventory.')
        snapshot = {name: inventory_bytes if name == SOURCE_INVENTORY else read(name) for name in source}
    # The reviewed allowance file is one of the captured files and is never read a second time: the bytes that are archived, bound to
    # the commit, parsed and named in the receipt are the same bytes. A file that exists but is not in the inventory is refused.
    if ALLOWANCE_FILE not in snapshot and allowed(ROOT / ALLOWANCE_FILE):
        raise ValueError(f'{ALLOWANCE_FILE} exists but is not in the reviewed inventory ({SOURCE_INVENTORY}): list it there, so that the '
                         'reviewed file is the one that is archived and bound to the commit, or remove it.')
    allowance_bytes = snapshot.get(ALLOWANCE_FILE)
    after = git_state(detail=True)
    if before != after:
        raise ValueError('The checkout changed while the snapshot was read (its commit, tree or tracked modifications); '
                         'build again from a checkout that is not being edited.')
    differing = bind_to_commit(snapshot, after)
    state = {key: after[key] for key in ('commit', 'tree', 'dirty')}
    if differing:
        state['dirty'] = True
    # Archives are made only from a known, clean Git state in which every captured file, the reviewed allowance file included, is
    # the committed one: a reviewed allowance must come from the commit the receipt names. --check-only may report any state.
    if not args.check_only:
        if state['commit'] is None:
            raise ValueError('Archives are made only from a known Git state: this folder is not the top level of a Git checkout, '
                             'or git could not be run. Use --check-only to look at a tree that has no commit.')
        if state['dirty']:
            reasons = (['git reports tracked modifications'] if after['dirty'] else []) + (
                ['captured files that differ from the commit: ' + ', '.join(differing[:20])] if differing else [])
            raise ValueError('Archives are made only from a clean checkout of the commit they name (' + '; '.join(reasons)
                             + '); commit or discard the changes. A reviewed allowance counts only as the committed one.')
    # The content digests the identity records will hold, worked out once from the captured files: --check-only reports them and the
    # build checks the digests it embeds against them.
    expected_runtime, expected_source = content_digests(snapshot, runtime)
    # What is about to be archived is looked at once, here, before anything is written.
    allowances = read_allowances(allowance_bytes) if allowance_bytes is not None else {}
    findings, counted, scanned_bytes = scan_content(snapshot)
    covered = {key for key in allowances if any(key == (item['path'], item['sha256'], item['kind']) for item in findings)}
    uncovered = [item for item in findings if (item['path'], item['sha256'], item['kind']) not in allowances]
    if uncovered:
        raise ValueError(f'Sensitive content is not covered by the reviewed {ALLOWANCE_FILE} (path, sha256 of these bytes, kind, '
                         'one-line reason): ' + '; '.join(f"{item['path']} ({item['kind']}, line {item['line']}, {item['count']} "
                                                          f"match{'es' if item['count'] != 1 else ''})" for item in uncovered[:20])
                         + (f'; and {len(uncovered) - 20} more' if len(uncovered) > 20 else ''))
    sensitive = {'scanned_files': len(snapshot), 'scanned_bytes': scanned_bytes, 'kinds_refused': list(REFUSED_KINDS),
                 'kinds_counted_only': list(COUNTED_KINDS), 'allowance_file': ALLOWANCE_FILE,
                 'allowance_file_sha256': hashlib.sha256(allowance_bytes).hexdigest() if allowance_bytes is not None else None,
                 'allowance_entries': len(allowances), 'allowance_unused': len(allowances) - len(covered),
                 'findings': [dict(item, allowed=True) for item in findings], 'counted_only': counted, 'limits': CONTENT_LIMITS}
    if args.check_only:
        source_hashes={name:hashlib.sha256(data).hexdigest() for name,data in sorted(snapshot.items())}
        report={'status':'PASS','mode':'inventory_validation_only','version':__version__,
            'source_files':len(source),'runtime_files':len(runtime),'source_bytes':sum(map(len,snapshot.values())),
            'source_inventory_sha256':hashlib.sha256(inventory_bytes).hexdigest(),
            'source_snapshot_sha256':hashlib.sha256(json.dumps(source_hashes,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
            'runtime_in_reviewed_source':True,'archives_created':False,'sensitive_content':sensitive,
            'runtime_content_sha256':expected_runtime,'source_content_sha256':expected_source,
            'checkout':{'commit':state['commit'],'tree':state['tree'],'dirty':state['dirty'],'differing_files':differing[:20],
                        'differing_count':len(differing),
                        'archives':'refused unless the commit is known and the checkout is clean'},
            'qualification':'Selection and bounded no-follow file validation only; no package, security, platform or production acceptance.',
            'required_follow_up':'Freeze exact source revision, build reproducibly, verify and independently qualify the exact final archives.'}
        print(json.dumps(report,indent=2))
        return report
    targets = [out/f'Intune_IaC_Plugin_{__version__}.zip',
               out/f'Intune_IaC_Plugin_{__version__}_Source.zip',
               out/'Intune_IaC_Plugin_Archive_Receipt.json']
    if any(path.exists() or path.is_symlink() for path in targets):
        raise ValueError('Release outputs already exist; use a fresh output directory.')
    out.mkdir(parents=True,exist_ok=True)
    build=dict(state,built_at=build_time())
    def identity(kind,companion):
        return dict(build,archive_kind=kind,product_version=__version__,companion=companion)
    # Each archive names the other: the runtime archive by the source content digest (known before either is
    # written), the source archive by the runtime archive's own digest (the runtime archive is written first).
    source_digest=expected_source
    runtime_content,runtime_digest=with_identity({name: snapshot[name] for name in runtime},
        identity('runtime',{'archive_kind':'source','content_sha256':source_digest}))
    if runtime_digest != expected_runtime:
        raise ValueError('The runtime content digest embedded in the archive differs from the one --check-only reports.')
    runtime_receipt=dict(write_archive(out/f'Intune_IaC_Plugin_{__version__}.zip',runtime_content,'intune-iac'),
                         content_sha256=runtime_digest)
    source_content,source_digest=with_identity(snapshot,identity('source',
        {'archive_kind':'runtime','archive_sha256':runtime_receipt['sha256']}))
    if source_digest != expected_source:
        raise ValueError('The source content digest embedded in the archive differs from the one --check-only reports.')
    source_receipt=dict(write_archive(out/f'Intune_IaC_Plugin_{__version__}_Source.zip',source_content,'intune-iac-source'),
                        content_sha256=source_digest)
    receipts=[runtime_receipt,source_receipt]
    receipt={'version':__version__,'build':build,'archives':receipts,
             'source_inventory_sha256':hashlib.sha256(inventory_bytes).hexdigest(),
             'source_selection':'Explicit reviewed file inventory; unlisted local files are excluded. The bytes are scanned for fixed secret shapes, private-key block markers and the building host\'s home path before anything is written (see sensitive_content); that is not a classification of arbitrary content.',
             'sensitive_content':sensitive,
             'runtime_excludes':['tests','golden output projects','historical research','upstream clones','model weights']}
    with (out/'Intune_IaC_Plugin_Archive_Receipt.json').open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))

if __name__=='__main__':main()
