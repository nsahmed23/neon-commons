#!/usr/bin/env python3
"""Replay fixed TERM-01..16 local assertions; never certify enterprise acceptance."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import platform
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Selection is fixed reviewed code. No model, command, test or network endpoint
# is accepted in arguments. A passing selection does not close the listed gap.
CASES = {
 'TERM-01': (['test_hostile_model_cannot_promote_text_to_capability', 'test_composed_mcp_graph_request_cannot_read_an_outside_hardlink'], 'Hostile-model stub, not an actual model with OS-enforced capabilities.'),
 'TERM-02': (['test_protected_child_does_not_inherit_startup_or_loader_environment'], 'Protected native child only; native shell/Windows launch-chain qualification remains required.'),
 'TERM-03': (['test_regular_unusual_paths_remain_literal_and_usable', 'test_config_hook_extra_provider_and_interpolation_rejected'], 'No native PowerShell/MSYS argument-parsing evidence.'),
 'TERM-04': (['test_repository_discovery_never_runs_git_config_or_hook', 'test_dynamic_repository_rejected_before_native_launch'], 'Repository parser and admitted native resolver only; no general Git execution is supported.'),
 'TERM-05': (['test_substituted_binary_rejected', 'test_changed_provider_binary_is_refused', 'test_extra_provider_binary_or_installed_path_cannot_override_pin'], 'Pinned helper/lifecycle tests; clean packaged native provider RPC remains a separate gate.'),
 'TERM-06': (['test_hardlinked_outside_record_cannot_be_selected_by_hostile_model', 'test_after_open_identity_check_rejects_a_new_hardlink', 'test_repository_nested_hardlink_is_not_read', 'test_symlink_and_relative_path_denied', 'test_hardlinked_source_cannot_copy_outside_bytes_into_release'], 'Cooperative private POSIX filesystem; hostile same-UID ancestors, Windows reparse points and mount changes are unqualified.'),
 'TERM-07': (['test_cli_json_does_not_emit_active_terminal_sequences', 'test_plan_substitution_and_forged_boolean_rejected'], 'JSON presentation boundary and signed approval; no native terminal/clipboard implementation was exercised.'),
 'TERM-08': (['test_new_origin_wrong_path_and_loop_are_never_fetched', 'test_real_transport_uses_explicit_env_token_and_get_without_redirect_following', 'test_ambient_proxy_cannot_change_capture_route'], 'Instrumented request transport; no live Graph/service observations.'),
 'TERM-09': (['test_denied_relationship_retains_error_without_empty_success', 'test_denied_assignment_collection_is_unknown_not_empty_complete', 'test_duplicate_source_record_id_across_pages_is_partial_without_rewriting'], 'Synthetic collection truth, not tenant completeness certification.'),
 'TERM-10': (['test_plan_snapshot_survives_source_overwrite_and_cannot_be_written', 'test_changed_policy_plan_or_state_blocks_approved_dispatch', 'test_forged_receipt_wrong_signature_expiry_and_live_mode_rejected', 'test_operator_policy_changed_after_receipt_verification_blocks_execution'], 'Actual signature and sealed-memory mechanisms combined with modeled provider lifecycle.'),
 'TERM-11': (['test_final_snapshot_accounts_for_multiple_write_mechanisms', 'test_parse_failure_visible'], 'Snapshot inventory only; qualify-change-coverage.py separately exercises actual write mechanisms and offline authored package install. Native editor and host hook integration remain unqualified.'),
 'TERM-12': (['test_evidence_and_repr_never_contain_secrets_tokens_or_raw_identifiers', 'test_cli_json_does_not_emit_active_terminal_sequences', 'test_forged_verified_journal_is_not_evidence_of_completion'], 'No independent off-host anchor; same host owner can rewrite all artifacts.'),
 'TERM-13': (['test_provider_descendant_cannot_detach_then_write_after_supervisor_returns', 'test_output_and_deadline_are_bounded', 'test_expiring_host_permit_stops_running_process', 'test_closed_output_pipes_do_not_disable_authority_watchdog', 'test_network_denied_but_plugin_unix_socket_and_child_process_allowed', 'test_response_loss_on_renew_permanently_loses_capability'], 'AF_UNIX host availability is measured separately; aggregate descendant count/memory and filesystem containment require an OS deployment boundary.'),
 'TERM-14': (['test_lost_response_restarts_read_only_reconciliation_and_never_retries', 'test_forged_operation_journal_cannot_prove_exact_plan_returned', 'test_uncertain_generation_reconciles_existing_bytes_without_replay'], 'Modeled lost-response recovery; actual service eventual consistency is unqualified.'),
 'TERM-15': (['test_untrusted_json_cannot_mint_permit_or_live_guard', 'test_candidate_cannot_be_certified_by_severity', 'test_hostile_model_cannot_promote_text_to_capability'], 'Deterministic action authority only; real reviewer/grader attacks and Wally outcomes have separate evidence.'),
 'TERM-16': (['test_json_acknowledgement_syncs_renamed_file_and_created_directories', 'test_directory_sync_failure_cannot_be_acknowledged', 'test_runner_syncs_graph_namespace_before_success', 'test_runner_directory_failure_cannot_dispatch_or_claim_success', 'test_wizard_modes_require_lock_directory_durability_before_controller', 'test_capture_new_directory_sync_failure_prevents_transport', 'test_mutex_blocks_different_operations_for_same_object', 'test_dispatch_and_receipt_persistence_faults_do_not_refund_authority', 'test_journal_write_failure_prevents_provider_write'], 'Observed fsync ordering/faults and cooperative locks; no destructive power-cut or real disk-full host test.'),
}
MODULES = ['test_terminal_security_epoch', 'test_security_boundaries_completion', 'test_security_audit_completion',
           'test_identity_binding_v5', 'test_approval_authority_v5', 'test_provider_execution_v5',
           'test_provider_journey_v5', 'test_native_atmos_completion', 'test_capture', 'test_graph',
           'test_blob_lease_v5', 'test_journey_completion', 'test_release_audit']


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite): yield from flatten(item)
        else: yield item


class Result(unittest.TextTestResult):
    def __init__(self, *args):
        super().__init__(*args); self.records = {}
    def addSuccess(self, test):
        self.records.setdefault(test.id(), {'status': 'PASS'}); super().addSuccess(test)
    def addFailure(self, test, error):
        self.records[test.id()] = {'status': 'FAIL'}; super().addFailure(test, error)
    def addError(self, test, error):
        self.records[test.id()] = {'status': 'INFRA_ERROR'}; super().addError(test, error)
    def addSkip(self, test, reason):
        self.records[test.id()] = {'status': 'BLOCKED', 'reason': reason}; super().addSkip(test, reason)
    def addSubTest(self, test, subtest, error):
        if error: self.records[test.id()] = {'status': 'FAIL', 'subtest': str(subtest)}
        super().addSubTest(test, subtest, error)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output).absolute()
    if output.exists(): parser.error('Choose a fresh evidence directory; existing evidence is never overwritten.')
    output.mkdir(parents=True, mode=0o700)
    loaded = unittest.defaultTestLoader.loadTestsFromNames(['plugin_tests.' + name for name in MODULES])
    tests = {test.id(): test for test in flatten(loaded)}
    selected = {}; families = {}
    for family, (suffixes, gap) in CASES.items():
        ids = []
        for suffix in suffixes:
            matches = [ident for ident in tests if ident.endswith('.' + suffix)]
            if not matches: raise RuntimeError('Required assertion missing: ' + suffix)
            ids.extend(matches)
        for ident in ids: selected[ident] = tests[ident]
        families[family] = {'test_ids': ids, 'remaining_gap': gap, 'enterprise_assertion_status': 'INCONCLUSIVE'}
    started = datetime.now(timezone.utc).isoformat()
    log = io.StringIO()
    result = unittest.TextTestRunner(stream=log, verbosity=2, resultclass=Result).run(
        unittest.TestSuite(selected[ident] for ident in sorted(selected)))
    (output / 'tests.log').write_text(log.getvalue())
    for family in families.values():
        family['observations'] = {ident: result.records.get(ident, {'status': 'NOT_RUN'}) for ident in family['test_ids']}
        states = {value['status'] for value in family['observations'].values()}
        family['local_assertions_status'] = 'FAIL' if states & {'FAIL', 'INFRA_ERROR'} else 'BLOCKED' if states & {'BLOCKED', 'NOT_RUN'} else 'PASS'
    sources = sorted([*ROOT.glob('intune_iac/*.py'), *[ROOT / 'plugin_tests' / (name + '.py') for name in MODULES],
                      ROOT / 'scripts/build-release.py', ROOT / 'scripts/security-audit-local.py', Path(__file__).resolve()])
    document = {'schema_version': 'terminal-security-epoch/1', 'started_at': started,
        'finished_at': datetime.now(timezone.utc).isoformat(), 'command': [sys.executable, '-B', str(Path(__file__).resolve()), '--output', str(output)],
        'runtime': {'python': sys.version, 'platform': platform.platform()},
        'source_sha256': {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources},
        'tests': result.records, 'unique_tests': result.testsRun, 'families': families,
        'log_sha256': hashlib.sha256((output / 'tests.log').read_bytes()).hexdigest(),
        'status': 'FAIL' if not result.wasSuccessful() else 'BLOCKED' if result.skipped else 'PASS',
        'scope': 'Selected local deterministic and modeled/native-primitive assertions only',
        'enterprise_qualified': False, 'release_gate': 'BLOCKED',
        'required_external_gates': ['supported native hosts', 'full provider RPC and OS execution containment', 'organizational AppSec review', 'explicitly authorized tenant pilot']}
    (output / 'receipt.json').write_text(json.dumps(document, indent=2, ensure_ascii=True) + '\n')
    print(json.dumps({key: document[key] for key in ('status', 'unique_tests', 'enterprise_qualified', 'release_gate')}))
    return 0 if result.wasSuccessful() and not result.skipped else 1


if __name__ == '__main__': raise SystemExit(main())
