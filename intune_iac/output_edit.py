"""Recognize an engineer's edit of the desired policy inside generated output.

Generated output is adoption evidence: verification compares it with what the
recorded source and context produce, so any edit makes that verification stale.
One edit is recognized as the engineer taking over the desired policy:
- the only changed file is the reference stack file, and the manifest is intact;
- the edited file still parses under the repository's literal rules (no duplicate
  keys, aliases, templates or unsupported scalars), so repository-import reads it
  the same way;
- its values differ from the generated ones only inside
  components.terraform.intune-reference.vars.policies.<key>, which holds exactly
  that one key in both.
Everything else is reported as another change, with the reason.

Read-only. The expected project is computed in memory exactly as generation
renders it; only the expected stack file is copied to a private temporary
directory to be parsed. The output is never written, regenerated or relabelled
as verified.
"""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import tempfile

VERSION = 'generated-output-edit/1'
STACK = 'stacks/orgs/reference/dev.yaml'
MANIFEST = 'generated-files.json'
POLICIES = ('components', 'terraform', 'intune-reference', 'vars', 'policies')
MAX_FILES = 4096


def _actual_files(output):
    from .io import AppError
    root = Path(output).absolute()
    if not root.is_dir() or any(p.is_symlink() for p in (root, *root.parents)):
        raise AppError('unsafe_output_path', 'Output must be a regular local directory.')
    files = {}
    for item in sorted(root.rglob('*')):
        if item.is_symlink():
            raise AppError('unsafe_output_path', 'Output contains a symbolic link.')
        if item.is_file():
            if len(files) >= MAX_FILES:
                raise AppError('unsafe_output_path', 'Output exceeds bounded local review limits.')
            files[item.relative_to(root).as_posix()] = hashlib.sha256(item.read_bytes()).hexdigest()
        elif not item.is_dir():
            raise AppError('unsafe_output_path', 'Output contains a special file.')
    return files


def _expected(input_path, context_path):
    """The generated project's files and object identity, computed in memory as generation renders them."""
    from reference.core import _json
    from .engine import _expected_files, _prepare
    raw, _, source, context, normalized = _prepare(input_path, context_path)
    files = dict(_expected_files(raw, source, context, normalized))
    hashes = {name: hashlib.sha256(text.encode('utf-8')).hexdigest() for name, text in sorted(files.items())}
    files[MANIFEST] = _json({'schema_version': '1.0.0', 'files': hashes})
    return files, normalized.get('object_id')


def _policies(document):
    node = document
    for key in POLICIES:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node if isinstance(node, dict) else None


def _without_policies(document):
    value = copy.deepcopy(document)
    node = value
    for key in POLICIES[:-1]:
        node = node[key]
    del node[POLICIES[-1]]
    return value


def _next_steps(key, object_id):
    from reference.core import RESOURCE
    return [
        'Generated output is adoption evidence, and this edit makes its verification stale. Nothing will regenerate '
        'over it or call it verified.',
        'Copy the edited project into the repository you maintain and commit it, then record that repository: '
        'workbench repository-import --root STORE --repo REPOSITORY --stack orgs/reference/dev --component '
        'intune-reference --object %s --pointer /vars/policies/%s --revision COMMIT --backend local '
        '--resource-address \'%s.policy["%s"]\'' % (object_id or 'OBJECT_ID', key, RESOURCE, key),
        'workbench repository-status then shows whether the repository still matches that intent, and '
        'propose-from-intent prepares the reviewed change.',
    ]


def classify(input_path, context_path, output_path):
    """What changed in a generated project since generation, and whether it is a repository-owned policy edit."""
    from .io import canonical
    from .repository import parse_stack_manifest
    from .workbench_diff import field_changes
    texts, object_id = _expected(input_path, context_path)
    expected = {name: hashlib.sha256(text.encode('utf-8')).hexdigest() for name, text in texts.items()}
    actual = _actual_files(output_path)
    changed = sorted(name for name in set(expected) & set(actual) if expected[name] != actual[name])
    added, removed = sorted(set(actual) - set(expected)), sorted(set(expected) - set(actual))
    result = {'schema_version': VERSION, 'output': str(Path(output_path).absolute()), 'object_id': object_id,
              'changed': changed, 'added': added, 'removed': removed,
              'execution_authorized': False, 'cloud_authority': False}
    if not (changed or added or removed):
        return dict(result, classification='unchanged', verification='current')
    other = dict(result, classification='other_change', verification='stale')
    if added or removed:
        return dict(other, reason='files_added_or_removed')
    if changed != [STACK]:
        return dict(other, reason='files_besides_the_stack_changed')
    edited = parse_stack_manifest(output_path, STACK)
    if edited['status'] != 'parsed':
        return dict(other, reason='stack_not_literal', blocker=edited['blocker'])
    with tempfile.TemporaryDirectory(prefix='intune-output-edit-') as temporary:
        path = Path(temporary) / STACK
        path.parent.mkdir(parents=True)
        path.write_bytes(texts[STACK].encode('utf-8'))
        generated = parse_stack_manifest(temporary, STACK)
    if generated['status'] != 'parsed':
        return dict(other, reason='generated_stack_not_literal', blocker=generated['blocker'])
    before, after = _policies(generated['value']), _policies(edited['value'])
    if before is None or after is None or len(before) != 1 or set(before) != set(after):
        return dict(other, reason='policy_keys_changed')
    if canonical(_without_policies(generated['value'])) != canonical(_without_policies(edited['value'])):
        return dict(other, reason='stack_changed_outside_the_policy')
    key = next(iter(before))
    return dict(result, classification='repository_owned_policy_edit', verification='stale', stack_file=STACK,
                policy_key=key, pointer='/vars/policies/' + key,
                values_changed=canonical(before[key]) != canonical(after[key]),
                field_changes=field_changes(before[key], after[key]), next_steps=_next_steps(key, object_id))
