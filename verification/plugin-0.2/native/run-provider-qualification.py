"""Verify pinned provider bytes, then run local-only schema/validation checks."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile

r = Path(__file__).resolve().parent
archive = r / 'provider-retry.zip'
filename = 'terraform-provider-microsoft365_1.0.0_linux_amd64.zip'
actual = hashlib.sha256(archive.read_bytes()).hexdigest()
expected = next(line.split()[0] for line in (r / 'terraform-provider-microsoft365_1.0.0_SHA256SUMS').read_text().splitlines() if line.endswith(filename))
registry = json.loads((r / 'provider-registry-download-metadata.json').read_text())
assert actual == expected == registry['shasum'] == '412f6594404eacbbf61e11c289231a1089e6955e8fe80d081ee1aa6596da4281'
signature = json.loads((r / 'provider-gpg-verification.json').read_text())[-1]
assert signature['returncode'] == 0 and 'VALIDSIG 93C35A0678D1F851B477D95C2BC5232BA17AB08A' in signature['stdout']
with zipfile.ZipFile(archive) as z:
    binaries = [name for name in z.namelist() if name.startswith('terraform-provider-microsoft365') and not name.endswith('/')]
    assert len(binaries) == 1
    binaryhash = hashlib.sha256(z.read(binaries[0])).hexdigest()
(r / 'provider-checksum-verification.json').write_text(json.dumps({
    'version': '1.0.0', 'archive_sha256': actual, 'binary_member': binaries[0], 'binary_sha256': binaryhash,
    'matches_release_checksums': True, 'matches_github_asset_digest': True, 'matches_registry_checksum': True,
    'gpg_signature_verified': True, 'signer_fingerprint': '93C35A0678D1F851B477D95C2BC5232BA17AB08A',
    'gpg_trust': 'Registry-distributed public key; independent identity/key certification not established'}, indent=2))
mirror = r / 'provider-mirror/registry.opentofu.org/deploymenttheory/microsoft365'
mirror.mkdir(parents=True, exist_ok=True)
shutil.copyfile(archive, mirror / filename)
cli = r / 'provider-mirror.tofurc'
cli.write_text('provider_installation {\n  filesystem_mirror {\n    path = "' + str(r / 'provider-mirror') + '"\n  }\n}\n')
env = json.loads((r / 'tofu-version.json').read_text())['environment']
env['TF_CLI_CONFIG_FILE'] = str(cli)
source = Path('/workspace/scratch/26b6d364cfda/repository-qualification-integrated/candidate/candidates/components/terraform/policy')
fixture = r / 'fixtures/provider-candidate'
fixture.mkdir(exist_ok=True)
source_manifest = []
for name in ['main.tf.txt', 'configuration.json', 'settings.json']:
    data = (source / name).read_bytes()
    target = fixture / ('main.tf' if name == 'main.tf.txt' else name)
    target.write_bytes(data)
    source_manifest.append({'source_path': str(source / name), 'fixture_path': str(target), 'sha256': hashlib.sha256(data).hexdigest()})
(r / 'provider-candidate-source-manifest.json').write_text(json.dumps(source_manifest, indent=2))
for name, args in [
    ('provider-init', ['init', '-backend=false', '-input=false', '-no-color', '-get=false']),
    ('provider-schema', ['providers', 'schema', '-json']),
    ('provider-candidate-validate', ['validate', '-json']),
    ('provider-candidate-fmt', ['fmt', '-check', '-no-color']),
]:
    cmd = [sys.executable, str(r / 'unix-only-exec.py'), str(r / 'bin/tofu'), *args]
    p = subprocess.run(cmd, cwd=fixture, env=env, capture_output=True, text=True, timeout=60, close_fds=True)
    result = {'argv': cmd, 'cwd': str(fixture), 'environment': env, 'returncode': p.returncode,
              'stdout': p.stdout, 'stderr': p.stderr,
              'network': 'Child seccomp denies all non-AF_UNIX socket creation; managed base runtime separately denies AF_UNIX.',
              'credentials_inherited': False, 'fixture_source_manifest': 'provider-candidate-source-manifest.json'}
    (r / (name + '.json')).write_text(json.dumps(result, indent=2))
    print(json.dumps({'name': name, 'returncode': p.returncode, 'stdout': p.stdout[:1500], 'stderr': p.stderr[:1800]}), flush=True)
