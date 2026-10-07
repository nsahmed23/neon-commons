#!/usr/bin/env python3
"""Build separate runnable plugin and source/evaluation archives."""
import argparse
import contextlib
import hashlib
import json
import os
import stat
import sys
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from intune_iac import __version__

EXCLUDE={'.git','__pycache__','.venv','.intune-iac','.superpowers','dist','build'}
SOURCE_INVENTORY = 'release-source-files.txt'


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


def source_files(inventory_bytes=None):
    """Only reviewed inventory entries enter the source distribution.

    This is a selection boundary, not a content/credential scanner. Adding
    files requires deliberate review and editing the inventory in source control.
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
        names.append(name)
    if SOURCE_INVENTORY not in names:
        raise ValueError('Source inventory must include itself.')
    return sorted(names)


def runtime_files():
    names=['plugin.json','.codex-plugin/plugin.json','.claude-plugin/plugin.json','.agents/plugins/marketplace.json',
           'README.md','RELEASE-VERIFICATION.md','THIRD-PARTY-NOTICES.md','requirements-runtime.txt',
           'requirements-runtime-linux-x86_64-cp312.lock','dependency-lock.json','scripts/verify-dependencies.py',
           'scripts/intune-iac.py','examples/context.json','examples/supported/input/export.json','examples/clm-config.json',
           'contracts/journey-actions.json','contracts/journey-semantics.json']
    for folder,pattern in [('intune_iac','*.py'),('reference','*.py'),('contracts','*.schema.json'),
                           ('corrections/contracts','*.json'),('corrections/models','*.py'),('skills','*')]:
        names.extend(p.relative_to(ROOT).as_posix() for p in (ROOT/folder).rglob(pattern) if allowed(p))
    names.extend('docs/'+name for name in ['HOSTS.md','WIZARD.md','GRAPH.md','RUNNER.md','CAPTURE.md','CLM.md','MCP.md','REPOSITORY.md','PRODUCTION-MAPPING.md','PRODUCT-STATUS.md','DATA-HANDLING.md','LABS.md','WORKFLOW.md','TARGET.md','EXECUTION.md','DEPENDENCIES.md','ENTERPRISE-GOAL.md','ENTERPRISE-EXECUTION-LEDGER.md','CI.md'])
    names.extend('docs/'+name for name in ['JOURNEY.md','PROTECTED-EXECUTION.md','SECURITY-ASSURANCE.md','SYNTHETIC-LABS.md','COMPLETION-ACCEPTANCE.md'])
    names.extend('docs/'+name for name in ['IDENTITY-BINDING.md','SIGNED-APPROVAL.md','PROVIDER-JOURNEY.md','BLOB-LEASE.md','PRODUCTION-COMPLETION-ACCEPTANCE.md'])
    names.extend('docs/'+name for name in ['EPOCH-ACCEPTANCE.md','OPERATIONS-EPOCH.md','TERMINAL-SECURITY-QUALIFICATION.md','POWERSHELL-PREVIEW-QUALIFICATION.md','WORKBENCH.md','CONTINUATION-R3.md','EXTERNAL-QUALIFICATION-R3.md','VENDOR-REFERENCE-LINEAGE.md'])
    return sorted(set(names))


def write_archive(destination,names,prefix):
    if destination.is_symlink():
        raise ValueError('Archive destination must not be a symlink.')
    for name in names:
        safe_name(name)
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
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',required=True)
    args=parser.parse_args();out=Path(args.output_dir).resolve()
    root = ROOT.resolve()
    if root==out or root in out.parents:raise ValueError('Use an output directory outside the source checkout.')
    runtime=runtime_files()
    for name in runtime:
        safe_name(name)
        if not allowed(ROOT/name):raise ValueError('Missing or unsafe required runtime member: '+name)
    with source_reader() as read:
        if not allowed(ROOT/SOURCE_INVENTORY):
            raise ValueError('A regular reviewed source inventory is required.')
        inventory_bytes = read(SOURCE_INVENTORY)
        source = source_files(inventory_bytes)
        if not set(runtime).issubset(source):
            raise ValueError('Runtime members must be included in the reviewed source inventory.')
        snapshot = {name: inventory_bytes if name == SOURCE_INVENTORY else read(name) for name in source}
    targets = [out/f'Intune_IaC_Plugin_{__version__}.zip',
               out/f'Intune_IaC_Plugin_{__version__}_Source.zip',
               out/'Intune_IaC_Plugin_Archive_Receipt.json']
    if any(path.exists() or path.is_symlink() for path in targets):
        raise ValueError('Release outputs already exist; use a fresh output directory.')
    out.mkdir(parents=True,exist_ok=True)
    receipts=[write_archive(out/f'Intune_IaC_Plugin_{__version__}.zip',
                            {name: snapshot[name] for name in runtime},'intune-iac'),
              write_archive(out/f'Intune_IaC_Plugin_{__version__}_Source.zip',snapshot,'intune-iac-source')]
    receipt={'version':__version__,'archives':receipts,
             'source_inventory_sha256':hashlib.sha256(inventory_bytes).hexdigest(),
             'source_selection':'Explicit reviewed file inventory; unlisted local files are excluded. Contents are not automatically classified for secrets.',
             'runtime_excludes':['tests','golden output projects','historical research','upstream clones','model weights']}
    with (out/'Intune_IaC_Plugin_Archive_Receipt.json').open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))

if __name__=='__main__':main()
