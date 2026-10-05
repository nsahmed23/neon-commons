#!/usr/bin/env python3
"""S05: actual fixed write mechanisms versus independent source snapshots.

No external packages or lifecycle scripts execute. The authored local npm
fixture installs offline with scripts disabled into a disposable evidence tree.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('security_inventory', ROOT / 'scripts/security-audit-local.py')
audit = importlib.util.module_from_spec(spec); spec.loader.exec_module(audit)


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024): digest.update(chunk)
    return digest.hexdigest()


def snapshot(root):
    records = {}
    for count, path in enumerate(sorted(root.rglob('*'))):
        if count > 1000: raise RuntimeError('Fixture entry limit')
        info = path.lstat(); relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            records[relative] = {'kind': 'symlink', 'target': os.readlink(path)}
        elif stat.S_ISDIR(info.st_mode):
            records[relative] = {'kind': 'directory', 'device': info.st_dev, 'inode': info.st_ino}
        elif stat.S_ISREG(info.st_mode) and info.st_size < 1024 * 1024:
            records[relative] = {'kind': 'file', 'device': info.st_dev, 'inode': info.st_ino,
                                 'links': info.st_nlink, 'bytes': info.st_size, 'sha256': sha(path)}
        else: raise RuntimeError('Fixture nonregular or oversized entry')
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output).absolute()
    if output.exists(): parser.error('A fresh evidence directory is required.')
    output.mkdir(parents=True, mode=0o700)
    fixture = output / 'fixture'; fixture.mkdir()
    home = output / 'home'; home.mkdir()
    cache = output / 'npm-cache'; cache.mkdir()
    tools = {name: shutil.which(name) for name in ('apply_patch', 'bash', 'sed', 'node', 'npm')}
    records = []; missing = [name for name, path in tools.items() if path is None]
    environment = {'PATH': str(Path(tools['node']).parent) + ':/usr/bin:/bin' if tools['node'] else '/usr/bin:/bin',
                   'HOME': str(home), 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
                   'npm_config_cache': str(cache), 'npm_config_offline': 'true',
                   'npm_config_audit': 'false', 'npm_config_fund': 'false', 'npm_config_update_notifier': 'false'}
    def run(label, command, data=None, cwd=fixture):
        before = snapshot(fixture); started = datetime.now(timezone.utc).isoformat()
        try:
            result = subprocess.run(command, input=data, cwd=cwd, env=environment, capture_output=True,
                                    text=True, timeout=25, stdin=None if data is not None else subprocess.DEVNULL)
            row = {'id': label, 'command': command, 'cwd': str(cwd), 'started_at': started,
                   'exit_code': result.returncode, 'stdout': result.stdout[:65536], 'stderr': result.stderr[:65536],
                   'status': 'PASS' if result.returncode == 0 else 'FAIL',
                   'output_truncated': len(result.stdout) > 65536 or len(result.stderr) > 65536}
        except (OSError, subprocess.TimeoutExpired) as error:
            row = {'id': label, 'command': command, 'cwd': str(cwd), 'started_at': started,
                   'status': 'BLOCKED', 'error_type': type(error).__name__, 'error': str(error)}
        after = snapshot(fixture)
        row.update(before=before, after=after, changed_paths=[path for path in sorted(set(before) | set(after)) if before.get(path) != after.get(path)])
        records.append(row)
    initial = snapshot(fixture)
    if tools['apply_patch']:
        run('S05-APPLY-PATCH', [tools['apply_patch']], '*** Begin Patch\n*** Add File: patched.py\n+value = 1\n*** End Patch\n')
    if tools['bash']:
        run('S05-SHELL-REDIRECT-HEREDOC', [tools['bash'], '--noprofile', '--norc', '-c',
            "printf 'value = 2\\n' > redirected.py\ncat > heredoc.py <<'END'\nvalue = 3\nEND\n"])
    if tools['sed']:
        run('S05-SED', [tools['sed'], '-i', 's/2/4/', 'redirected.py'])
    run('S05-PYTHON-WRITE', [sys.executable, '-I', '-S', '-c', "from pathlib import Path;Path('python-write.py').write_text('value = 5\\n')"])
    if tools['node']:
        run('S05-NODE-WRITE', [tools['node'], '-e', "require('fs').writeFileSync('node-write.js','const value = 6;\\n')"])
    run('S05-GENERATOR', [sys.executable, '-I', '-S', '-c', "import json;from pathlib import Path;Path('generated.json').write_text(json.dumps({'generated':[{'id':x,'enabled':True} for x in range(5)]}))"])
    run('S05-RENAME', [sys.executable, '-I', '-S', '-c', "from pathlib import Path;Path('heredoc.py').rename('renamed.py')"])
    if tools['npm']:
        # Authored fixture only: no dependencies, source history or downloaded packages.
        dep = fixture / 'local-dependency'; dep.mkdir()
        nested = fixture / 'nested-package'; nested.mkdir()
        (dep / 'index.js').write_text('module.exports = 7;\n')
        (dep / 'package.json').write_text(json.dumps({'name': 'fixture-local', 'version': '1.0.0',
            'scripts': {'preinstall': 'node -e "require(\'fs\').writeFileSync(\'INSTALL_SCRIPT_RAN\',\'forbidden\')"'}}))
        (nested / 'package.json').write_text(json.dumps({'name': 'coverage-fixture', 'version': '1.0.0',
            'private': True, 'dependencies': {'fixture-local': 'file:../local-dependency'}}))
        run('S05-OFFLINE-PACKAGE-INSTALL', [tools['npm'], 'install', '--offline', '--ignore-scripts', '--install-links=true',
            '--no-audit', '--no-fund', '--no-progress'], cwd=nested)
        if (nested / 'package-lock.json').exists():
            run('S05-LOCKFILE-CHANGE', [sys.executable, '-I', '-S', '-c',
                "import json;from pathlib import Path;p=Path('package-lock.json');d=json.loads(p.read_text());d['name']='coverage-fixture-renamed';p.write_text(json.dumps(d,sort_keys=True))"], cwd=nested)
    final = snapshot(fixture)
    scans = {'root': audit.inventory(fixture)}
    installed = fixture / 'nested-package/node_modules'
    if installed.is_dir(): scans['installed-fixture'] = audit.inventory(installed)
    scanned = {}
    for name, scan in scans.items():
        prefix = '' if name == 'root' else 'nested-package/node_modules/'
        for row in scan['files']: scanned[prefix + row['path']] = row['sha256']
    changed_files = {path: row for path, row in final.items() if row['kind'] == 'file' and initial.get(path) != row}
    omissions = {path: 'not_scanned' if path not in scanned else 'hash_mismatch' for path, row in changed_files.items()
                 if scanned.get(path) != row['sha256']}
    canaries = [str(path.relative_to(fixture)) for path in fixture.rglob('INSTALL_SCRIPT_RAN')]
    failures = [row['id'] for row in records if row['status'] != 'PASS' or row.get('output_truncated')]
    receipt = {'schema_version': 'source-change-coverage/1', 'status': 'FAIL' if failures or omissions or canaries else 'BLOCKED' if missing else 'PASS',
        'scope': 'Actual fixed local write mechanisms, independent final inode/content snapshots and bundled scanner accounting',
        'tools': {name: {'path': value, 'sha256': sha(Path(value)) if value else None} for name, value in tools.items()},
        'source_sha256': {'harness': sha(Path(__file__).resolve()), 'scanner': sha(ROOT / 'scripts/security-audit-local.py')},
        'records': records, 'initial': initial, 'final': final, 'changed_files': sorted(changed_files), 'scanned_files': scanned,
        'scanner_results': scans, 'omissions': omissions, 'forbidden_install_script_markers': canaries, 'failed_mechanisms': failures,
        'missing_tools': missing, 'side_effect_scope': {'fixture': str(fixture), 'npm_cache': str(cache), 'temporary_home': str(home)},
        'remaining_gaps': ['No native editor host exposed; editor integration NOT_RUN', 'No Guardian or other host scanner hook installed; this tests snapshot-based change accounting',
                           'No third-party package or package lifecycle script executed; install scripts are deliberately disabled', 'Scanned does not mean vulnerability-free'],
        'enterprise_qualified': False}
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2, ensure_ascii=True) + '\n')
    print(json.dumps({'status': receipt['status'], 'mechanisms': len(records), 'changed_files': len(changed_files),
                      'omissions': len(omissions), 'canaries': len(canaries), 'output': str(output)}))
    return 0 if receipt['status'] == 'PASS' else 1


if __name__ == '__main__': raise SystemExit(main())
