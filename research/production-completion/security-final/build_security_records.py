#!/usr/bin/env python3
"""Build supplemental records from existing receipts; never run product/tests.

Only reads the explicit new-artifact/source inventory below. Does not inspect
environment values, home directories, credentials, SQLite stores, or processes.
"""
import ast
import hashlib
import io
import json
import re
import stat
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
PREFIX = 'research/production-completion/'
MAX_FILE = 32 * 1024 * 1024
MAX_MEMBER = 5 * 1024 * 1024
SOURCE_FILES = [
    'intune_iac/identity_binding.py', 'intune_iac/approval_authority.py',
    'intune_iac/blob_lease.py', 'intune_iac/provider_execution.py',
    'intune_iac/provider_journey.py', 'intune_iac/cli.py',
    'plugin_tests/test_identity_binding_v5.py', 'plugin_tests/test_approval_authority_v5.py',
    'plugin_tests/test_approval_independent_v5.py', 'plugin_tests/test_blob_lease_v5.py',
    'plugin_tests/test_blob_lease_independent_v5.py', 'plugin_tests/test_provider_execution_v5.py',
    'plugin_tests/test_provider_journey_v5.py',
    'docs/IDENTITY-BINDING.md', 'docs/SIGNED-APPROVAL.md', 'docs/BLOB-LEASE.md',
    'docs/PROVIDER-JOURNEY.md', 'docs/PRODUCTION-COMPLETION-PLAN.md',
    'docs/PRODUCTION-COMPLETION-ACCEPTANCE.md',
]

# Manually inspected source context, keyed by exact file and value hash. Raw
# candidate values are deliberately absent from this assessment record.
MANUAL_ASSESSMENTS = {
    ('plugin_tests/test_blob_lease_independent_v5.py', '2b9cc4a9db471dbe900f09fbe469af30efdd8a740f938e325120903fb274339d'):
        ('manually_confirmed_synthetic_fixture_literal', 'Literal Authorization value in test_timeout_cannot_reconnect_and_send_after_caller_returns; request destination is synthetic.invalid and transport is a fixture.'),
    ('plugin_tests/test_identity_binding_v5.py', '6d229884c1268bb0ab32d8da315d0fe52f9147228bd830a37bc9fb28a954940d'):
        ('manually_confirmed_synthetic_fixture_literal', 'Literal token in constructed ServiceResponse bytes in test_duplicate_headers_and_header_total_bound, passed only to bind_laboratory.'),
    ('research/production-completion/schemas/bom-1.6.schema.json', 'd04fe0e4256ec99c62b3c5ea44d500b53ecaa92f6dcd28daa5cda59b5d408900'):
        ('public_schema_description_false_positive', 'JSON path definitions.cryptoProperties.properties.relatedCryptoMaterialProperties.properties.type.meta:enum.password is descriptive schema prose, not a credential assignment.'),
    ('research/production-completion/schemas/bom-1.6.schema.json', '9af20aa15ca9ef39d4d6129997b59361c80aa50917fe5dd3246995ad66e44ced'):
        ('public_schema_description_false_positive', 'JSON path definitions.cryptoProperties.properties.relatedCryptoMaterialProperties.properties.type.meta:enum.token is descriptive schema prose, not a token assignment.'),
}


def sha(data): return hashlib.sha256(data).hexdigest()


def write(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def test_index():
    result = {}
    for relative in SOURCE_FILES:
        if not relative.startswith('plugin_tests/'): continue
        tree = ast.parse((ROOT / relative).read_text())
        for cls in tree.body:
            if isinstance(cls, ast.ClassDef):
                for fn in cls.body:
                    if isinstance(fn, ast.FunctionDef) and fn.name.startswith('test_'):
                        result[(relative, fn.name)] = relative[:-3].replace('/', '.') + '.' + cls.name + '.' + fn.name
    return result


TESTS = test_index()


def tests(file, *names):
    relative = 'plugin_tests/' + file + '.py'
    return [{'file': relative, 'test': TESTS[(relative, name)]} for name in names]


def evidence(*paths):
    result = []
    for relative in paths:
        relative = PREFIX + relative
        path = ROOT / relative
        if not path.is_file() or path.is_symlink(): raise ValueError('Missing regular evidence: ' + relative)
        result.append({'path': relative, 'sha256': sha(path.read_bytes())})
    return result


def finding(key, title, severity, invariant, control, test_refs, evidence_refs, classes, limits):
    return {'id': key, 'title': title, 'status': 'repaired_with_scoped_evidence',
        'origin': 'new_0_5_implementation_review_not_claimed_inherited_defect',
        'severity': severity, 'severity_basis': 'Supplemental qualitative impact assessment; no CVSS score or live exploit claim.',
        'invariant': invariant, 'control': control, 'tests': test_refs, 'evidence': evidence_refs,
        'evidence_classes': classes, 'limits': limits}


findings = [
    finding('SEC05-A1', 'Approval expired or was revoked during a host callback', 'high',
        'Authority must remain active after each bounded host recheck.',
        ['approval_authority.ApprovedExecution._check rechecks time and revocation after callback'],
        tests('test_approval_independent_v5', 'test_expiry_during_guard_recheck_denies_context_entry', 'test_expiry_during_active_guard_recheck_denies_active_permit'),
        evidence('approval/review-independent-red.log', 'approval/review-independent-final.log', 'approval/review-summary.json'),
        ['real_crypto_and_private_store', 'deterministic_clock'], ['No cloud issuer or live operation was involved.']),
    finding('SEC05-A2', 'Child process launched before the first active-authority check', 'high',
        'Expired or rejected authority must prevent child startup.',
        ['provider_execution._supervise checks authority before Popen'],
        tests('test_approval_independent_v5', 'test_native_launcher_checks_authority_before_spawning'),
        evidence('approval/review-independent-red.log', 'approval/review-independent-final.log', 'final-review/targeted-replay.txt'),
        ['native_local_process'], ['Harmless local marker process; no provider or cloud mutation.']),
    finding('SEC05-A3', 'Installed weak Ed25519 identity key accepted a static signature forgery', 'high_conditional',
        'Installed issuer keys must be canonical, non-small-order, main-subgroup points.',
        ['approval_authority._valid_public_key uses pinned native validator and documented subgroup workaround'],
        tests('test_approval_independent_v5', 'test_low_order_identity_public_key_cannot_authorize_static_forgery', 'test_validator_rejects_weak_noncanonical_and_mixed_order_points'),
        evidence('approval/review-weak-key-red.log', 'approval/review-independent-final.log', 'approval/review-summary.json'),
        ['real_crypto_and_private_store'], ['Requires installing an invalid weak trusted key; valid generated issuer keys were not demonstrated forgeable.']),
    finding('SEC05-A4', 'Recycled loader descriptor pathname selected a previously loaded validator image', 'high_conditional',
        'Executed validator bytes must match the selected pin.',
        ['approval_authority._valid_public_key loads verified bytes through a unique private pathname and bounded content cache'],
        tests('test_approval_independent_v5', 'test_validator_dlopen_does_not_reuse_a_recycled_descriptor_path'),
        evidence('approval/review-validator-red.log', 'approval/review-independent-final.log'),
        ['native_local_dynamic_loader'], ['Protected loader, native dependencies and interpreter remain trusted.']),
    finding('SEC05-A5', 'Missing validator escaped the fixed application-error contract', 'low',
        'Unavailable verifier dependencies must fail closed with a fixed diagnostic.',
        ['approval_authority._valid_public_key translates unavailable dependency failures'],
        tests('test_approval_independent_v5', 'test_validator_wrong_pin_and_missing_dependency_fail_closed'),
        evidence('approval/review-validator-red.log', 'approval/review-independent-final.log'),
        ['native_local_dependency_failure'], ['Pre-fix behavior already denied authorization; this was diagnostic/API consistency.']),
    finding('SEC05-T1', 'Caller interruption could leave a delayed identity credential dispatch running', 'high_conditional',
        'Caller cancellation must prevent a not-yet-dispatched credential request.',
        ['identity_binding._NativeTransport cancels on BaseException and checks cancellation after connect'],
        tests('test_identity_binding_v5', 'test_caller_interrupt_cancels_delayed_connect_before_credentials_send') + tests('test_blob_lease_independent_v5', 'test_identity_caller_interrupt_cancels_delayed_connect'),
        evidence('leases/review-independent.json', 'leases/review-independent-green.txt', 'identity/verification.json'),
        ['mock_native_connection', 'real_stdlib_orchestration'], ['Identity counterpart was fixed before combined independent RED log; no persisted identity RED log is claimed. Already-sent bytes cannot be undone.']),
    finding('SEC05-T2', 'Automatic HTTP reconnect could dispatch after a timeout closed the first connection', 'high_conditional',
        'A cancelled request must not reconnect and send credentials or lease operations.',
        ['identity_binding._NativeTransport and blob_lease._LeaseTransport disable auto_open after explicit connect'],
        tests('test_identity_binding_v5', 'test_timeout_closure_never_auto_reconnects_before_request_send') + tests('test_blob_lease_independent_v5', 'test_timeout_cannot_reconnect_and_send_after_caller_returns'),
        evidence('leases/review-independent-red.txt', 'leases/review-independent-green.txt', 'leases/review-independent.json'),
        ['real_stdlib_with_mock_socket'], ['Combined RED demonstrates lease counterpart; identity repair preceded that run. No live endpoint or credential exfiltration demonstrated.']),
    finding('SEC05-T3', 'Detached HTTP response socket kept a worker alive past its deadline', 'medium',
        'Body cancellation must terminate the response stream and release bounded worker capacity.',
        ['Both transports retain the connected socket for shutdown and close HTTPResponse in worker cleanup'],
        tests('test_identity_binding_v5', 'test_detached_connection_close_body_socket_is_shutdown_on_deadline') + tests('test_blob_lease_independent_v5', 'test_connection_close_response_cannot_keep_worker_after_deadline'),
        evidence('leases/review-independent-red.txt', 'leases/review-independent-green.txt', 'leases/review-independent.json', 'final-review/targeted-replay.txt'),
        ['mock_native_connection', 'native_local_socketpair_real_http_parser'], ['Positive path asserts socketpair creation, stdlib detach, body read, and joined workers. This does not qualify TLS or remote Azure.']),
    finding('SEC05-L1', 'Lease renewal/release token stage exceeded remaining ownership lifetime', 'medium',
        'OAuth and lease work must share the remaining conservative lease deadline.',
        ['blob_lease caps token acquisition by request deadline and prior lease expiry'],
        tests('test_blob_lease_independent_v5', 'test_renew_token_exchange_budget_cannot_exceed_remaining_lease', 'test_release_token_exchange_budget_cannot_exceed_remaining_lease'),
        evidence('leases/review-independent-red.txt', 'leases/review-independent-green.txt', 'leases/review-independent.json'),
        ['recorded_service_responses_and_clock'], ['Pre-fix code rejected lease writes after noticing expiry; excess blocking was reproduced, not an expired-owner Graph write.']),
    finding('SEC05-L2', 'Renewal after release overwrote terminal receipt state', 'low',
        'Terminal lease states must remain terminal and cannot recover authority.',
        ['blob_lease preserves terminal release state on rejected renewal'],
        tests('test_blob_lease_v5', 'test_no_renew_after_release_preserves_terminal_receipt'),
        evidence('leases/terminal-state-red.log', 'leases/tests-green-combined.log', 'leases/implementation-summary.json'),
        ['recorded_service_responses_and_clock'], ['No live Blob service operation was performed.']),
    finding('SEC05-J1', 'Writable journal and converged state could manufacture a verified journey outcome', 'high',
        'A journal, spent approval or converged state alone cannot prove exact saved-plan execution.',
        ['ProviderJourney requires exact durable authority consumption', 'Verified restart requires private dispatch/outcome hash and exact_plan_returned plus saved-plan/state validation', 'Read-only convergence without prior execution remains unconfirmed'],
        tests('test_provider_journey_v5', 'test_unsigned_journal_cannot_authorize_reconciliation', 'test_consumed_approval_and_convergence_do_not_prove_saved_plan_executed', 'test_forged_verified_journal_is_not_evidence_of_completion'),
        evidence('identity/verification.json', 'approval/receipt-provenance.log', 'final-review/targeted-replay.txt', 'final-review/final-review.md'),
        ['real_crypto_and_private_store', 'modeled_provider_commands'], ['Current-source regressions and final replay retained; no standalone persisted initial journey RED log is claimed. Same-account private-store modification is outside this boundary.']),
    finding('SEC05-J2', 'Path-only credential descriptor leaked its duplicate during cleanup', 'low',
        'Every duplicate credential descriptor must close even if flag operations fail.',
        ['provider_journey.read_credential_fd rejects O_PATH and uses nested-finally closure'],
        tests('test_provider_journey_v5', 'test_path_only_descriptor_is_rejected_without_leak', 'test_pipe_requires_eof_within_deadline_and_restores_flags'),
        evidence('identity/verification.json'), ['native_local_file_descriptors'],
        ['No retained initial RED log; the existing regression and integrated scoped test receipt are the retained evidence. No actual credential store was read.']),
    finding('SEC05-I1', 'Injected response validation omitted the aggregate header bound', 'low',
        'All admitted response paths must enforce the documented header budget.',
        ['identity_binding._Observer.read enforces aggregate header length in addition to native transport checks'],
        tests('test_identity_binding_v5', 'test_duplicate_headers_and_header_total_bound'),
        evidence('identity/verification.json'), ['recorded_service_responses'],
        ['Native transport already had a 64 KiB aggregate check; this finding concerns the shared/injected response-validation path.']),
]

gaps = [
    ('G01', 'Native provider RPC and lifecycle qualification remains blocked', 'high',
     'Native init passed; schema and validate were blocked and AF_UNIX socket creation returned errno 1.',
     ['provider-execution/native-smoke.json', 'provider-execution/evidence-manifest.json'],
     ['Qualify provider RPC, Configure, schema, import, update and readback on a host meeting the required boundary.']),
    ('G02', 'No live identity, RBAC, TLS, Graph, ARM or Blob qualification', 'high',
     'Recorded identities/leases prove contract logic only; no real tenant or live service calls occurred.',
     ['identity/verification.json', 'leases/review-independent.json'],
     ['Provision explicit protected credentials and independently observe real service targets, permissions, failures and readback.']),
    ('G03', 'Live identity, Azure backend and provider execution are not joined', 'high',
     'Provider uses local state with IP denial; a separately acquired state-blob lease conflicts with OpenTofu acquiring its own backend lease.',
     ['final-review/final-review.md', 'provider-execution/native-smoke.json', 'leases/implementation-notes.md'],
     ['Design and qualify native Azure backend locking and same-credential target linkage without double lease ownership.']),
    ('G04', 'IP denial is not a complete execution sandbox', 'high',
     'Allowed Unix endpoints and filesystem access need a qualified host boundary.',
     ['final-review/final-review.md', 'final-review/review-snapshot.json'],
     ['Enforce and positively test filesystem and Unix endpoint isolation on the deployment host; do not remove IP denial to obtain a pass.']),
    ('G05', 'Blob leases and cooperative locks do not fence Graph writers', 'high',
     'Azure Blob lease scope and same-store mutexes cannot exclude unrelated Intune/Graph writers.',
     ['leases/review-independent.json', 'approval/review-findings.md', 'final-review/final-review.md'],
     ['Qualify deployment-wide ownership and service-specific concurrency controls before any live mutation.']),
    ('G06', 'Organizational issuer and protected-store operations remain deployment gates', 'high',
     'Fixture private keys exercise mechanics; they do not establish organizational approver identity or durable trust operations.',
     ['approval/review-findings.md', 'approval/review-summary.json'],
     ['Provision independent issuer trust, policy custody, revocation, backup/recovery, and protected durable store controls.']),
    ('G07', 'Capture-to-generated-configuration admission is not fully qualified', 'high',
     'The journey accepts a separately admitted generated executor; source/admission hashes are bindings, not proof of complete semantic admission.',
     ['final-review/final-review.md', 'provider-execution/evidence-manifest.json'],
     ['Retain independent end-to-end admission and preservation evidence for the supported capture/configuration slice.']),
]

gap_rows = [{'id': k, 'title': title, 'status': 'open_qualification_gap', 'severity': severity,
             'observation': observation, 'evidence': evidence(*refs), 'closure_requirement': closure,
             'not_a_confirmed_exploit': True} for k, title, severity, observation, refs, closure in gaps]

boundary = [
    'Protected Python interpreter, same-account credential-holding process, operator policy/store and native trust dependencies remain trusted.',
    'A malicious same-account writer or compromised interpreter can alter private capabilities/store; no security-domain isolation claim is made.',
    'Separate review agents share filesystem/context; review is neither blinded nor organizational AppSec certification.',
    'No live-service call, real credential retrieval, production mutation, test rerun or environment inspection is performed by this supplemental builder.',
]

matrix = []
for row in findings:
    matrix.append({'threat_id': row['id'], 'threat': row['title'], 'invariant': row['invariant'],
                   'controls': row['control'], 'tests': row['tests'], 'evidence': row['evidence'],
                   'evidence_classes': row['evidence_classes'], 'status': row['status'], 'limits': row['limits']})
matrix.extend([
    {'threat_id': 'CTRL-I2', 'threat': 'Opaque tokens or imported JSON substituted for live principal authority',
     'invariant': 'Only a successful explicit fixed-service constructor creates a live identity capability.',
     'controls': ['identity_binding.bind_live fixed native transport', 'require_live_binding exact type; laboratory factory remains distinct', 'Tenant-specific OAuth and service-principal self read; no token JWT decoding'],
     'tests': tests('test_identity_binding_v5', 'test_json_and_direct_construction_cannot_create_live_authority', 'test_graph_client_object_and_enabled_are_exact', 'test_arm_wrong_tenant_subscription_or_disabled'),
     'evidence': evidence('identity/verification.json'), 'evidence_classes': ['recorded_service_responses'],
     'status': 'implemented_locally_tested_live_unqualified', 'limits': ['G02', 'G03']},
    {'threat_id': 'CTRL-I3', 'threat': 'Ambient credentials, cross-origin routes or wrong backend handle silently replace explicit inputs',
     'invariant': 'Use the same explicit role handle, fixed origins and exact scopes without fallback.',
     'controls': ['Separate provider/backend handles and token exchanges', 'Fixed request route allowlist', 'Exact four-key in-memory provider environment', 'Bounded read-only inherited FD input and immediate handle closure'],
     'tests': tests('test_identity_binding_v5', 'test_provider_environment_uses_same_handle_and_no_inheritance', 'test_storage_resource_or_cross_origin_endpoint_mismatch', 'test_backend_access_requires_exact_handle_and_returns_redacted_expiring_token') + tests('test_provider_journey_v5', 'test_explicit_fd_credentials_strict_config_and_redacted_output'),
     'evidence': evidence('identity/verification.json', 'leases/review-independent.json'),
     'evidence_classes': ['recorded_service_responses', 'native_local_file_descriptors'], 'status': 'implemented_locally_tested_live_unqualified', 'limits': ['G02', 'G03']},
    {'threat_id': 'CTRL-P1', 'threat': 'Approved saved-plan bytes change in place after hash validation',
     'invariant': 'Dispatch the exact approved immutable bytes, not a mutable inode.',
     'controls': ['provider_execution._sealed_plan creates a write-sealed anonymous snapshot', 'Fixed pinned tool/provider/schema/configuration and implementation hashes'],
     'tests': [], 'evidence': evidence('provider-execution/native-sealed-plan.json'),
     'evidence_classes': ['native_opentofu_local_outputs'], 'status': 'native_local_control_verified',
     'limits': ['Receipt records actual init/plan/apply/show with changed original file, denied descriptor write and truncate.', 'This is not provider RPC or service qualification; no pre-fix defect repro is inferred.']},
    {'threat_id': 'CTRL-S1', 'threat': 'Persisted approval flags or navigation reuse authority',
     'invariant': 'Approval stays in memory and is discarded on suspension, edit, back and restart.',
     'controls': ['ProviderJourney strict hash-only session', 'Typed ApprovedExecution required; real receipt re-verification after review'],
     'tests': tests('test_provider_journey_v5', 'test_suspend_resume_discards_approval_and_requires_review', 'test_back_cancel_edit_and_review_discard_in_memory_approval', 'test_session_flags_or_changed_prepared_bytes_cannot_resume_authority'),
     'evidence': evidence('identity/verification.json'), 'evidence_classes': ['real_crypto_and_private_store', 'modeled_provider_commands'],
     'status': 'implemented_locally_tested', 'limits': ['Protected process/store boundary applies.']},
    {'threat_id': 'CTRL-L3', 'threat': 'Unknown lease responses or expired owners regain authority and retry writes',
     'invariant': 'Uncertain acquire/renew/release remains terminal locally; stale owners never release a replacement owner.',
     'controls': ['blob_lease process-held state machine and conservative expiry', 'Exact credential handle and typed live/laboratory factories'],
     'tests': tests('test_blob_lease_independent_v5', 'test_successful_remote_acquire_with_lost_response_is_terminal_locally', 'test_successful_remote_renew_with_lost_response_never_restores_local_authority', 'test_expired_local_owner_cannot_release_new_remote_owner', 'test_same_role_concurrency_permits_one_acquisition_attempt'),
     'evidence': evidence('leases/review-independent.json', 'leases/review-independent-green.txt'),
     'evidence_classes': ['independent_modeled_owner_service'], 'status': 'implemented_locally_tested_live_unqualified', 'limits': ['G02', 'G03', 'G05']},
])
for gap in gap_rows:
    matrix.append({'threat_id': gap['id'], 'threat': gap['title'], 'invariant': gap['observation'],
                   'controls': ['Fail-closed scope and explicit qualification gate'], 'tests': [],
                   'evidence': gap['evidence'], 'evidence_classes': ['documented_boundary_or_blocked_native_probe'],
                   'status': gap['status'], 'limits': gap['closure_requirement']})


def scan():
    paths = {ROOT / p for p in SOURCE_FILES}
    paths.update(p for p in (ROOT / 'labs/production-lifecycle').rglob('*') if p.is_file())
    paths.update(p for p in (ROOT / PREFIX).rglob('*') if p.is_file() and not p.is_relative_to(OUT))
    # Narrow fixture allowlist is built only from visibly synthetic source
    # literals. A test-file location alone never dismisses a high-entropy key.
    fixtures = set()
    for relative in SOURCE_FILES:
        if not relative.startswith('plugin_tests/'): continue
        for node in ast.walk(ast.parse((ROOT / relative).read_text())):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                value = node.value
                if re.match(r'^(synthetic|fixture|opaque|modeled|recorded|ambient|wrong|fake|attacker|not-)', value, re.I):
                    fixtures.add(value)
    rules = {
        'private_key_header': re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----'),
        'jwt_triplet': re.compile(rb'eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}'),
        'aws_access_key': re.compile(rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
        'github_token': re.compile(rb'\b(?:ghp_|github_pat_)[A-Za-z0-9_]{20,}\b'),
        'openai_key_shape': re.compile(rb'\bsk-[A-Za-z0-9_-]{20,}\b'),
        'azure_sas_signature': re.compile(rb'[?&]sig=([A-Za-z0-9%+/=]{16,})'),
        'bearer_literal': re.compile(rb'Bearer[ \t]+([A-Za-z0-9._~+/=-]{8,})'),
        'secret_assignment_literal': re.compile(rb'''(?i)(?:client_secret|M365_CLIENT_SECRET|ARM_CLIENT_SECRET|AZURE_CLIENT_SECRET|password|access_token|api[_-]?key|token)\s*['"]?\s*[:=]\s*['"]([^'"\r\n]{4,})'''),
        'canary_marker': re.compile(rb'(?i)\b(?:canary|honeytoken|private[_-]?holdout)[A-Za-z0-9_.:-]*'),
    }
    inventory, matches, skips = [], [], []

    def inspect(data, relative, member=None):
        for rule, pattern in rules.items():
            for match in pattern.finditer(data):
                value = match.group(1) if match.lastindex else match.group()
                decoded = value.decode('ascii', 'replace')
                manual = MANUAL_ASSESSMENTS.get((relative, sha(value))) if member is None else None
                if manual:
                    assessment = manual[0]
                elif decoded in fixtures:
                    assessment = 'known_synthetic_fixture_literal_not_real_credential'
                elif rule == 'canary_marker' and decoded.lower().rstrip('.:') in ('canary', 'honeytoken', 'private_holdout', 'private-holdout'):
                    assessment = 'marker_word_or_boundary_reference_not_canary_payload'
                else: assessment = 'requires_manual_assessment'
                matches.append({'path': relative, 'member': member, 'line': data[:match.start()].count(b'\n') + 1,
                    'rule': rule, 'matched_value_sha256': sha(value), 'matched_value_bytes': len(value),
                    'assessment': assessment, 'assessment_basis': manual[1] if manual else None, 'raw_match_retained': False})

    for path in sorted(paths):
        relative = path.relative_to(ROOT).as_posix()
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode): skips.append({'path': relative, 'reason': 'not_regular_no_follow'}); continue
        if before.st_size > MAX_FILE: skips.append({'path': relative, 'reason': 'file_size_bound'}); continue
        data = path.read_bytes(); after = path.stat()
        unstable = (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns)
        inventory.append({'path': relative, 'bytes': len(data), 'sha256': sha(data), 'changed_during_read': unstable})
        inspect(data, relative)
        if zipfile.is_zipfile(io.BytesIO(data)):
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                rows = archive.infolist()
                if len(rows) > 256:
                    skips.append({'path': relative, 'reason': 'zip_member_count_bound'}); continue
                total = 0
                for row in rows:
                    if row.is_dir(): continue
                    total += row.file_size
                    if row.file_size > MAX_MEMBER or total > MAX_FILE or row.flag_bits & 1:
                        skips.append({'path': relative, 'member': row.filename, 'reason': 'zip_size_or_encryption_bound'}); continue
                    inspect(archive.read(row), relative, row.filename)
    return {'schema_version': 'supplemental-artifact-leak-scan/1.0', 'snapshot_at': datetime.now(timezone.utc).isoformat(),
        'scope': {'explicit_files': SOURCE_FILES, 'trees': ['labs/production-lifecycle', PREFIX.rstrip('/')],
                  'excluded': ['research/production-completion/security-final (self-generated outputs)', 'all other repository paths', 'environment values', 'credential stores', 'home directories', 'process memory', 'files created after inventory enumeration']},
        'rules': list(rules), 'bounds': {'file_bytes': MAX_FILE, 'zip_member_bytes': MAX_MEMBER, 'zip_members': 256, 'zip_total_bytes': MAX_FILE},
        'files_scanned': len(inventory), 'inventory': inventory, 'skipped': skips,
        'matches': matches, 'match_counts': dict(Counter(m['rule'] for m in matches)),
        'assessment_counts': dict(Counter(m['assessment'] for m in matches)),
        'unresolved_candidates': sum(m['assessment'] == 'requires_manual_assessment' for m in matches),
        'conclusion': 'No real credential or canary payload leakage confirmed within this bounded heuristic scan; this is not proof of absence.',
        'raw_secret_values_written_or_printed': False,
        'limits': ['Heuristic pattern scan, not a complete secret detector or DLP audit.',
                   'No known real-secret/canary corpus was loaded; unknown credential formats, encrypted data and opaque binary encodings may evade detection.',
                   'A synthetic-literal match is assessed only against explicitly synthetic literals in the new test sources.',
                   'Files and final verification outputs can be written concurrently; inventory hashes describe only this point-in-time scan.',
                   'No production tests or service calls are executed. No source artifacts are changed.']}


scan_result = scan()
write('artifact-leak-scan.json', scan_result)
write('findings-ledger.json', {'schema_version': 'security-findings-ledger/1.0', 'release_candidate': '0.5.0',
    'prepared_at': datetime.now(timezone.utc).isoformat(), 'acceptance': 'BLOCKED_FOR_ENTERPRISE_PRODUCTION',
    'finding_count': len(findings), 'open_qualification_gap_count': len(gap_rows), 'findings': findings,
    'open_gaps': gap_rows, 'threat_boundary': boundary,
    'evidence_provenance': ['Historical RED/GREEN logs retain their own source snapshot and are not presented as new reruns.',
        'Final-review snapshot replayed six existing methods, zero skips; this is not six newly authored tests.',
        'Approval receipt-provenance.log records 34 passing methods but no command/method list; no finer attribution is invented.',
        'Owner final integrated test run, clean extraction and archive hashes are separate release gates. No success is inferred from an in-progress run.'],
    'supplemental_process': {'new_test_methods': 0, 'test_commands_executed': 0, 'live_service_calls': 0,
        'credential_store_reads': 0, 'environment_value_reads': 0},
    'evidence': evidence('final-review/review-snapshot.json', 'final-review/final-review.md')})
write('threat-control-matrix.json', {'schema_version': 'threat-invariant-control-test-evidence/1.0',
    'release_candidate': '0.5.0', 'rows': matrix, 'threat_boundary': boundary,
    'qualification_rule': 'Mocked responses, real crypto, native local tools, local socketpair HTTP, and live services are distinct evidence classes. No local class promotes a live-service gate.'})
print(json.dumps({'findings': len(findings), 'open_gaps': len(gap_rows), 'matrix_rows': len(matrix),
                  'scanned_files': scan_result['files_scanned'], 'matches': len(scan_result['matches']),
                  'assessments': scan_result['assessment_counts'], 'skipped': len(scan_result['skipped'])}))
