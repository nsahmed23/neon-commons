"""Runtime entry point to the independently checked bounded reference mapping."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .io import AppError, file_sha, load_json, parse_json, read_bytes


def _prepare(input_path, context_path):
    from reference.core import normalize
    from reference.invariants import compare
    from reference.validation import schema_errors
    raw = read_bytes(input_path)
    context_raw = read_bytes(context_path)
    source = parse_json(raw); context = parse_json(context_raw)
    if not isinstance(source, dict) or schema_errors('export-intake', source):
        raise AppError('invalid_capture', 'Input does not satisfy the versioned capture contract.')
    if not isinstance(context, dict): raise AppError('invalid_context', 'Context must be a JSON object.')
    try:
        from .production import accepts, normalize as normalize_production
        if accepts(source):
            from .production_oracle import compare as production_compare
            normalized = normalize_production(source, context)
            errors = production_compare(raw, normalized, context=context)
        else:
            normalized = normalize(source, context['selected_policy_id'], context['tenant_id'])
            errors = compare(raw, normalized)
    except AppError:
        raise
    except (ValueError, TypeError, KeyError, IndexError, AttributeError):
        raise AppError('invalid_capture', 'Capture or target context failed independent validation.') from None
    if errors: raise AppError('preservation_failed', 'Independent source preservation verification failed.')
    return raw, context_raw, source, context, normalized


def inspect_source(input_path, context_path):
    raw, context_raw, source, context, normalized = _prepare(input_path, context_path)
    return {
        'status': 'ready' if normalized['offline_mapping_complete'] else 'blocked',
        'policy_id': normalized['object_id'], 'tenant_id': normalized['tenant_id'],
        'normalized': normalized, 'blockers': normalized['blockers'],
        'source_sha256': hashlib.sha256(raw).hexdigest(),
        'context_sha256': hashlib.sha256(context_raw).hexdigest(),
        'source_mode': normalized.get('source_mode', 'synthetic' if source['synthetic'] else 'unqualified_capture'),
        'preservation_verified': True, 'execution_authorized': False,
    }


def _render(value):
    return json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n'


def _expected_files(raw, source, context, normalized):
    from reference.core import generate_files
    if normalized.get('source_mode') == 'plugin_graph_capture':
        from .production import generate_files as production_files
        files=production_files(normalized,context)
    elif source['synthetic'] is True:
        files=generate_files(normalized,context)
    else:
        files={
            'README.md':'# Capture review\n\nThis exporter is not qualified for infrastructure generation. No active IaC or command is emitted.\n',
            'review/normalized.json':_render(normalized),
            'BLOCKED.json':_render({'execution_allowed':False,'blockers':normalized['blockers']}),
            'commands/command-cards.json':_render({'schema_version':'1.0.0','cards':[]}),
        }
    files['adoption/source-receipt.json']=_render({'schema_version':'1.0.0',
        'source_byte_sha256':hashlib.sha256(raw).hexdigest(),
        'source_canonical_sha256':normalized['source_canonical_sha256']})
    return files


def verify_project(input_path, context_path, output_path):
    """Read-only verification; a saved manifest or session is not an oracle."""
    from reference.invariants import compare
    from reference.core import _safe_relative
    raw, context_raw, source, context, normalized = _prepare(input_path, context_path)
    output = Path(output_path).absolute()
    try:
        if not output.is_dir() or any(p.is_symlink() for p in [output,*output.parents]):
            raise ValueError('path')
        manifest = load_json(output/'generated-files.json')
        if not isinstance(manifest,dict) or set(manifest)!={'schema_version','files'} or manifest['schema_version']!='1.0.0' or not isinstance(manifest['files'],dict):
            raise ValueError('manifest')
        actual=set()
        for item in output.rglob('*'):
            if item.is_symlink():raise ValueError('symlink')
            if item.is_file():actual.add(item.relative_to(output).as_posix())
            elif not item.is_dir():raise ValueError('special')
        if actual != set(manifest['files']) | {'generated-files.json'}:raise ValueError('closure')
        files={}
        for name, expected in manifest['files'].items():
            _safe_relative(name)
            data=read_bytes(output/name)
            if hashlib.sha256(data).hexdigest()!=expected:raise ValueError('hash')
            files[name]=data.decode('utf-8')
        if normalized.get('source_mode') == 'plugin_graph_capture':
            from .production_oracle import compare as production_compare
            saved=parse_json(files['review/normalized.json'])
            errors=production_compare(raw,saved,files=files,context=context)
            if saved!=normalized:raise ValueError('review changed')
        elif source['synthetic']:
            errors=compare(raw,normalized,files=files,context=context)
        else:
            allowed={'README.md','review/normalized.json','BLOCKED.json','commands/command-cards.json','adoption/source-receipt.json'}
            if set(files)!=allowed:raise ValueError('review closure')
            saved=parse_json(files['review/normalized.json'])
            errors=compare(raw,saved)
            if saved!=normalized:raise ValueError('review changed')
            if parse_json(files['commands/command-cards.json'])!={'schema_version':'1.0.0','cards':[]}:raise ValueError('commands')
            if parse_json(files['BLOCKED.json'])!={'execution_allowed':False,'blockers':normalized['blockers']}:raise ValueError('blockers')
        receipt=parse_json(files['adoption/source-receipt.json'])
        if receipt!={'schema_version':'1.0.0','source_byte_sha256':hashlib.sha256(raw).hexdigest(),'source_canonical_sha256':normalized['source_canonical_sha256']}:raise ValueError('source')
        if errors:raise ValueError('oracle')
        # The independent oracle establishes preservation. Exact regeneration
        # additionally detects edits to auxiliary prose or command documentation
        # that are intentionally outside the oracle's semantic checks.
        if files!=_expected_files(raw,source,context,normalized):raise ValueError('file bytes changed')
        if read_bytes(input_path)!=raw or read_bytes(context_path)!=context_raw:raise ValueError('changed')
        return {'preservation_verified':True,'manifest_sha256':file_sha(output/'generated-files.json'),
                'output':str(output),'file_count':len(files)+1,'execution_authorized':False}
    except (ValueError,TypeError,KeyError,OSError,UnicodeError):
        raise AppError('postcondition_failed','Output does not match independently derived source expectations.') from None


def generate(input_path, context_path, output_path):
    from reference.core import write_project
    from reference.invariants import compare
    raw, context_raw, source, context, normalized = _prepare(input_path, context_path)
    review_only = source['synthetic'] is not True
    try:
        files = _expected_files(raw,source,context,normalized)
        if normalized.get('source_mode') == 'plugin_graph_capture':
            from .production_oracle import compare as production_compare
            errors = production_compare(raw, normalized, files=files, context=context)
        else:
            errors = compare(raw, normalized, files=None if review_only else files, context=None if review_only else context)
        if errors: raise AppError('preservation_failed', 'Independent generated-project verification failed.')
        # Recheck source and context just before the owned-directory transaction.
        if read_bytes(input_path) != raw or read_bytes(context_path) != context_raw:
            raise AppError('evidence_changed', 'Source or context changed during generation.')
        output = Path(output_path).absolute()
        status = write_project(files, output)
        expected = {name:hashlib.sha256(text.encode()).hexdigest() for name,text in files.items()}
        manifest = load_json(output/'generated-files.json')
        if manifest != {'schema_version':'1.0.0','files':expected}:
            raise AppError('postcondition_failed', 'Generated manifest failed verification.')
        for name, wanted in expected.items():
            if file_sha(output/name) != wanted:
                raise AppError('postcondition_failed', 'Generated file failed verification.')
        disk_files = {name:(output/name).read_text(encoding='utf-8') for name in files}
        if normalized.get('source_mode') == 'plugin_graph_capture':
            errors = production_compare(raw, parse_json(disk_files['review/normalized.json']), files=disk_files, context=context)
        elif review_only:
            errors = compare(raw, parse_json(disk_files['review/normalized.json']))
        else:
            errors = compare(raw, normalized, files=disk_files, context=context)
        if errors: raise AppError('postcondition_failed', 'Written project failed independent preservation verification.')
        verify_project(input_path,context_path,output)
        return {'status':status,'outcome':'succeeded_verified','output':str(output),
                'file_count':len(files)+1,'manifest_sha256':file_sha(output/'generated-files.json'),
                'source_sha256':hashlib.sha256(raw).hexdigest(),'context_sha256':hashlib.sha256(context_raw).hexdigest(),
                'preservation_verified':True,'offline_mapping_complete':normalized['offline_mapping_complete'],
                'candidate_mapping_complete':normalized.get('candidate_mapping_complete',normalized['offline_mapping_complete']),
                'blocker_codes':sorted({b['code'] for b in normalized['blockers']}),
                'execution_authorized':False}
    except FileExistsError:
        raise AppError('output_conflict', 'Existing output or lock cannot be safely replaced; inspect it or choose a new directory.') from None
    except AppError: raise
    except (ValueError, TypeError, KeyError, OSError):
        raise AppError('generation_failed', 'Generation failed; inspect the local destination before retrying.') from None
