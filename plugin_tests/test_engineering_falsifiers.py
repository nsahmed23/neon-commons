"""The engineering view's falsifiers (PKG-UXVIS-4 item 4): each one is a way the view could show progress the records
do not hold. See lanes/product-scope-02/advisor-engineering-view/DECISION.md, "First slice and its falsifiers".

Attempts come only from an explicit attempt id. A task whose events name none has one implicit attempt. An event that
names no attempt, on a task that has two explicit attempts, is an annotation and changes nothing.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from plugin_tests.orchestration_fixtures import RUNNER_B, attempt_id, eid, event, header_for, lifecycle, wall, write_export

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'scripts/intune-iac.py'
REAL = ROOT / 'plugin_tests/fixtures/orchestration/real-export'
REAL_TASK = 'T-f445e27aa6'
TREE_X, TREE_Y = 'a' * 40, 'b' * 40
SENTINEL = 'SENTINEL-RESULT-TEXT'


class Base(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.dir = self.root / 'records'

    def view(self, events, **kwargs):
        from intune_iac.engineering_view import build_view, render_lines
        write_export(self.dir, events, **kwargs.pop('export', {}))
        model = build_view(self.dir, **kwargs)
        return model, '\n'.join(render_lines(model))

    def row(self, events, task='T-1', **kwargs):
        model, _ = self.view(events, **kwargs)
        return {item['task']: item for item in model['tasks']}[task]

    def cli(self, *args):
        return subprocess.run([sys.executable, str(CLI), 'engineering', *map(str, args)], text=True,
                              capture_output=True, cwd='/tmp')


class RealExportTests(Base):
    def real_events(self):
        return [json.loads(line) for line in (REAL / 'events.jsonl').read_text(encoding='utf-8').splitlines()]

    def test_the_real_task_reads_unknown_later_cancelled_attested_late_result_recorded_and_not_cancelled(self):
        model, text = self.view(self.real_events(), export={'header': json.loads((REAL / 'header.json').read_text())})
        row = {item['task']: item for item in model['tasks']}[REAL_TASK]
        self.assertEqual(row['words'], 'unknown; later cancelled (attested by the controller); late result recorded')
        self.assertEqual(row['state'], 'unknown')
        self.assertTrue(row['late_result'])
        self.assertEqual(model['source']['check']['state'], 'ok')
        line = next(item for item in text.splitlines() if item.startswith(REAL_TASK))
        self.assertIn('unknown; later cancelled (attested by the controller); late result recorded', line)

    def test_the_command_prints_that_line_for_the_real_fixture(self):
        result = self.cli('--records', REAL, '--evidence-root', 'C:/Dev/Projects/intune-rescue')
        self.assertEqual(result.returncode, 0, result.stderr)
        line = next(item for item in result.stdout.splitlines() if item.startswith(REAL_TASK))
        self.assertIn('unknown; later cancelled (attested by the controller); late result recorded', line)
        self.assertIn('Export check: OK', result.stdout)

    def test_a_duplicated_export_line_changes_nothing(self):
        events = self.real_events()
        header = json.loads((REAL / 'header.json').read_text())
        plain, _ = self.view(events, export={'header': header})
        duplicate = json.dumps(events[28], sort_keys=True)  # line 29, the started of the real task
        twice, _ = self.view(events, export={'header': header, 'extra_lines': [duplicate]})
        self.assertEqual(plain['tasks'], twice['tasks'])
        self.assertEqual(plain['faults'], twice['faults'])
        self.assertEqual(plain['source'], twice['source'])
        self.assertEqual(twice['read']['duplicate_lines'], plain['read']['duplicate_lines'] + 1)

    def test_an_export_cut_after_a_started_prints_the_header_mismatch_and_started_no_news_since(self):
        events = self.real_events()
        header = json.loads((REAL / 'header.json').read_text())
        model, text = self.view(events[:29], export={'header': header})
        self.assertEqual(model['source']['check']['state'], 'mismatch')
        self.assertIn('MISMATCH', text)
        self.assertIn('truncated or changed', text)
        row = {item['task']: item for item in model['tasks']}[REAL_TASK]
        self.assertEqual(row['state_words'], 'started, no news since ' + events[28]['wall_utc'])


class TerminalOrderTests(Base):
    def test_a_later_terminal_event_is_an_annotation_and_never_changes_the_state(self):
        for terminal, words in (('dispatch.completed', 'later completed'), ('dispatch.failed', 'later failed')):
            row = self.row(lifecycle('T-1', terminal='dispatch.unknown', reason='r') + [event(4, terminal, 'T-1')])
            self.assertEqual((row['state'], row['words']), ('unknown', 'unknown; ' + words), terminal)
        row = self.row(lifecycle('T-1', terminal='dispatch.completed')
                       + [event(4, 'dispatch.cancelled', 'T-1', cleanup_confirmed=True, reason='cleanup confirmed')])
        self.assertEqual((row['state'], row['words']), ('completed', 'completed, unverified; later cancelled'))

    def test_a_later_cancel_without_confirmed_cleanup_is_not_a_cancellation(self):
        row = self.row(lifecycle('T-1', terminal='dispatch.unknown', reason='r')
                       + [event(4, 'dispatch.cancelled', 'T-1', cleanup_confirmed=False, reason='x')])
        self.assertEqual(row['state'], 'unknown')
        self.assertIn('later cancel recorded, cleanup not confirmed', row['words'])

    def test_completed_then_claim_released_keeps_completed(self):
        row = self.row(lifecycle('T-1', terminal='dispatch.completed') + [event(4, 'claim.released', 'T-1')])
        self.assertEqual((row['state'], row['words']), ('completed', 'completed, unverified'))
        self.assertEqual((row['last_event_type'], row['last_seq']), ('claim.released', 4))

    def test_cancel_requested_then_completed_is_not_a_cancellation(self):
        row = self.row(lifecycle('T-1', terminal='dispatch.cancel_requested') + [event(4, 'dispatch.completed', 'T-1')])
        self.assertEqual((row['state'], row['state_words']), ('completed', 'completed, unverified'))
        self.assertNotIn('cancelled', row['words'])
        self.assertNotIn('cancellation', row['words'])

    def test_a_completed_repair_reads_completed_unverified(self):
        row = self.row(lifecycle('T-1', kind='repair', terminal='dispatch.completed') + [event(4, 'repair.reported', 'T-1')])
        self.assertEqual((row['kind'], row['state_words']), ('repair', 'completed, unverified'))


class AttemptTests(Base):
    A, B = attempt_id('A1'), attempt_id('B1')

    def two_attempts(self):
        return [event(1, 'dispatch.queued', 'T-1', kind='advisor'),
                event(2, 'dispatch.started', 'T-1', attempt=self.A, adopted=False),
                event(3, 'dispatch.timed_out', 'T-1', attempt=self.A),
                event(4, 'dispatch.started', 'T-1', attempt=self.B, adopted=False)]

    def test_attempt_a_times_out_b_starts_a_completes_late_and_b_is_unchanged(self):
        before = self.row(self.two_attempts())
        self.assertEqual(before['state_words'], 'started, no news since ' + wall(4))
        late = self.row(self.two_attempts() + [event(5, 'dispatch.completed', 'T-1', attempt=self.A)])
        self.assertEqual((late['state'], late['state_words']), ('started', 'started, no news since ' + wall(4)))
        self.assertEqual(late['no_news_since'], wall(4))
        self.assertIn('attempt %s recorded dispatch.completed after attempt %s started: not applied to the current attempt' % (self.A, self.B),
                      late['words'])
        self.assertNotIn('completed, unverified', late['state_words'])

    def test_an_event_without_an_attempt_after_a_second_attempt_started_is_not_attributed(self):
        events = self.two_attempts() + [event(5, 'dispatch.completed', 'T-1')]
        row = self.row(events)
        self.assertEqual((row['state'], row['state_words']), ('started', 'started, no news since ' + wall(4)))
        self.assertIn('dispatch.completed recorded without an attempt after attempt %s started: not attributed' % self.B,
                      row['words'])
        self.assertEqual((row['last_event_type'], row['last_seq']), ('dispatch.completed', 5))

    def test_a_late_result_without_an_attempt_after_a_second_attempt_started_is_not_attributed(self):
        row = self.row(self.two_attempts() + [event(5, 'advisor.late_result', 'T-1', role='controller')])
        self.assertFalse(row['late_result'])
        self.assertIn('advisor.late_result recorded without an attempt after attempt %s started: not attributed' % self.B,
                      row['words'])

    def test_with_one_explicit_attempt_an_event_without_an_attempt_applies_to_it(self):
        events = [event(1, 'dispatch.queued', 'T-1', kind='advisor'),
                  event(2, 'dispatch.started', 'T-1', attempt=self.A, adopted=False),
                  event(3, 'dispatch.completed', 'T-1')]
        self.assertEqual(self.row(events)['state'], 'completed')

    def test_a_task_with_no_attempt_id_has_one_implicit_attempt(self):
        events = lifecycle('T-1') + [event(3, 'dispatch.started', 'T-1', adopted=True, incarnation=RUNNER_B),
                                     event(4, 'dispatch.completed', 'T-1', incarnation=RUNNER_B)]
        row = self.row(events)
        self.assertEqual((row['state'], row['adoptions'], row['incarnation']), ('completed', 1, RUNNER_B))

    def test_a_different_incarnation_alone_never_makes_a_new_attempt(self):
        events = lifecycle('T-1') + [event(3, 'dispatch.completed', 'T-1', incarnation=RUNNER_B)]
        row = self.row(events)
        self.assertEqual(row['state'], 'completed')
        self.assertNotIn('not attributed', row['words'])
        self.assertNotIn('not applied', row['words'])

    def test_a_second_attempt_starts_afresh_after_the_first_ended(self):
        events = [event(1, 'dispatch.queued', 'T-1', kind='advisor'),
                  event(2, 'dispatch.started', 'T-1', attempt=self.A, adopted=False),
                  event(3, 'dispatch.failed', 'T-1', attempt=self.A, reason='x'),
                  event(4, 'dispatch.started', 'T-1', attempt=self.B, adopted=False)]
        row = self.row(events)
        self.assertEqual((row['state'], row['state_words']), ('started', 'started, no news since ' + wall(4)))

    def test_an_event_without_an_attempt_after_an_unnamed_first_attempt_ended_is_not_credited_to_the_retry(self):
        events = [event(1, 'dispatch.queued', 'T-1', kind='advisor'),
                  event(2, 'dispatch.started', 'T-1', adopted=False),
                  event(3, 'dispatch.failed', 'T-1', reason='x'),
                  event(4, 'dispatch.started', 'T-1', attempt=self.B, adopted=False)]
        before = self.row(events)
        self.assertEqual((before['state'], before['state_words']), ('started', 'started, no news since ' + wall(4)))
        for kind in ('dispatch.cancelled', 'dispatch.completed'):
            row = self.row(events + [event(5, kind, 'T-1', cleanup_confirmed=True)])
            self.assertEqual((row['state'], row['state_words']), ('started', 'started, no news since ' + wall(4)), kind)
            self.assertIn('%s recorded without an attempt after attempt %s started: not attributed' % (kind, self.B), row['words'])


class VerificationTests(Base):
    def done(self, tree=TREE_X, first=1, kind='repair'):
        events = lifecycle('T-1', start=first, kind=kind)
        events.append(event(first + 2, 'dispatch.completed', 'T-1', tree=tree))
        return events

    def verification(self, seq, tree=TREE_X, task='T-1', outcome='pass'):
        return event(seq, 'verification.completed', task, outcome=outcome, gate='temporal', requirement='REQ-1',
                     commit='c' * 40, tree=tree)

    def test_a_passing_verification_of_the_exact_tree_reads_verified(self):
        row = self.row(self.done() + [self.verification(4)])
        self.assertEqual(row['state'], 'verified')
        self.assertIn('verified', row['state_words'])
        self.assertNotIn('unverified', row['state_words'])
        self.assertIn(TREE_X[:12], row['state_words'])

    def test_a_verification_of_tree_x_does_not_verify_tree_y(self):
        row = self.row(self.done(tree=TREE_Y) + [self.verification(4, tree=TREE_X)])
        self.assertEqual((row['state'], row['state_words']), ('completed', 'completed, unverified'))

    def test_a_failing_or_blocked_verification_does_not_verify(self):
        for outcome in ('fail', 'blocked', 'incomplete'):
            row = self.row(self.done() + [self.verification(4, outcome=outcome)])
            self.assertEqual(row['state'], 'completed', outcome)

    def test_a_completion_that_names_no_tree_cannot_be_verified(self):
        row = self.row(self.done(tree=None) + [self.verification(4)])
        self.assertEqual(row['state_words'], 'completed, unverified')

    def test_a_verification_that_names_no_task_attaches_to_nothing(self):
        model, text = self.view(self.done() + [self.verification(4, task=None)])
        self.assertEqual(model['tasks'][0]['state'], 'completed')
        self.assertEqual(model['verifications'], {'records': 1, 'unattached': 1})
        self.assertIn('1 verification records, none attached to a task', text)

    def test_a_corrected_pass_no_longer_reads_verified(self):
        events = self.done() + [self.verification(4), event(5, 'verification.corrected', 'T-1', corrects=eid('ev-4'))]
        row = self.row(events)
        self.assertEqual((row['state'], row['state_words']), ('completed', 'completed, unverified'))

    def test_a_correction_of_a_record_the_export_does_not_hold_is_shown_not_dropped(self):
        model, text = self.view(self.done() + [event(4, 'verification.corrected', None, corrects=eid('ev-999'))])
        self.assertIn('correction at sequence 4 names verification %s, which this export does not hold' % eid('ev-999'), text)
        self.assertEqual(model['tasks'][0]['state'], 'completed')

    def test_verification_does_not_apply_before_the_task_completed(self):
        row = self.row(lifecycle('T-1') + [self.verification(3)])
        self.assertEqual(row['state'], 'started')

    def test_a_late_completion_in_a_superseded_attempt_is_not_verified_by_the_current_tree(self):
        events = [event(1, 'dispatch.queued', 'T-1', kind='repair'),
                  event(2, 'dispatch.started', 'T-1', attempt=attempt_id('A1'), adopted=False),
                  event(3, 'dispatch.started', 'T-1', attempt=attempt_id('A2'), adopted=False),
                  event(4, 'dispatch.completed', 'T-1', attempt=attempt_id('A1'), tree=TREE_X), self.verification(5)]
        self.assertEqual(self.row(events)['state'], 'started')

    def test_a_tree_from_an_unattributed_repair_report_does_not_verify_the_current_attempt(self):
        events = [event(1, 'dispatch.queued', 'T-1', kind='repair'),
                  event(2, 'dispatch.started', 'T-1', attempt=attempt_id('A1'), adopted=False),
                  event(3, 'dispatch.started', 'T-1', attempt=attempt_id('A2'), adopted=False),
                  event(4, 'repair.reported', 'T-1', tree=TREE_X),
                  event(5, 'dispatch.completed', 'T-1', attempt=attempt_id('A2'), tree=None), self.verification(6)]
        row = self.row(events)
        self.assertEqual((row['state'], row['state_words']), ('completed', 'completed, unverified'))
        self.assertIn('repair.reported recorded without an attempt after attempt %s started: not attributed' % attempt_id('A2'), row['words'])

    def test_an_unattributed_claim_event_does_not_move_the_current_attempts_no_news_clock(self):
        events = [event(1, 'dispatch.queued', 'T-1', kind='repair'),
                  event(2, 'dispatch.started', 'T-1', attempt=attempt_id('A1'), adopted=False),
                  event(3, 'dispatch.started', 'T-1', attempt=attempt_id('A2'), adopted=False),
                  event(5, 'claim.released', 'T-1')]
        row = self.row(events)
        self.assertEqual(row['state_words'], 'started, no news since ' + wall(3))

    def test_a_repair_report_after_the_completion_never_changes_the_tree_the_completion_recorded(self):
        events = self.done(tree=TREE_X) + [event(4, 'repair.reported', 'T-1', tree=TREE_Y), self.verification(5, tree=TREE_Y)]
        row = self.row(events)
        self.assertEqual((row['state'], row['state_words']), ('completed', 'completed, unverified'))
        self.assertIn('later repair reported', row['words'])
        row = self.row(self.done(tree=TREE_X) + [event(4, 'repair.reported', 'T-1', tree=TREE_Y), self.verification(5)])
        self.assertEqual(row['state'], 'verified')
        self.assertIn(TREE_X[:12], row['state_words'])


class UnopenedAttemptTests(Base):
    def test_an_unknown_attempt_id_on_a_claim_event_opens_nothing(self):
        events = lifecycle('T-1', terminal='dispatch.completed') + [event(4, 'claim.released', 'T-1', attempt=attempt_id('A1'))]
        row = self.row(events)
        self.assertEqual((row['state'], row['state_words']), ('completed', 'completed, unverified'))
        self.assertIn('claim.released names attempt %s, which no started record opened: not attributed' % attempt_id('A1'), row['words'])

    def test_an_unknown_attempt_id_opens_a_new_attempt_only_for_queued_or_started(self):
        events = [event(1, 'dispatch.queued', 'T-1', kind='advisor'),
                  event(2, 'dispatch.started', 'T-1', attempt=attempt_id('A1'), adopted=False),
                  event(3, 'dispatch.failed', 'T-1', attempt=attempt_id('A1'), reason='x'),
                  event(4, 'dispatch.completed', 'T-1', attempt=attempt_id('A9'))]
        row = self.row(events)
        self.assertEqual(row['state'], 'failed')
        self.assertIn('dispatch.completed names attempt %s, which no started record opened: not attributed' % attempt_id('A9'), row['words'])


class StartedAfterTerminalTests(Base):
    def test_an_adopted_started_after_unknown_is_counted_and_noted_and_unknown_stays_unknown(self):
        events = lifecycle('T-1', terminal='dispatch.unknown', reason='r') + [
            event(4, 'dispatch.started', 'T-1', adopted=True, incarnation=RUNNER_B)]
        row = self.row(events)
        self.assertEqual((row['state'], row['adoptions'], row['incarnation']), ('unknown', 1, RUNNER_B))
        self.assertEqual(row['words'], 'unknown; later started (adopted)')

    def test_a_plain_started_after_a_terminal_event_is_noted_without_an_adoption(self):
        row = self.row(lifecycle('T-1', terminal='dispatch.failed', reason='r') + [event(4, 'dispatch.started', 'T-1', adopted=False)])
        self.assertEqual((row['state'], row['adoptions']), ('failed', 0))
        self.assertEqual(row['words'], 'failed; later started')


class RedactionTests(Base):
    def test_a_sentinel_in_a_result_field_never_appears_in_any_output(self):
        events = lifecycle('T-1', terminal='dispatch.completed')
        raw = []
        for item in events:
            item = dict(item, prompt=SENTINEL, result={'text': SENTINEL}, summary=SENTINEL, session_id=SENTINEL,
                        agent_config=SENTINEL)
            item['data'] = dict(item['data'], result={'text': SENTINEL}, prompt=SENTINEL, summary=SENTINEL,
                                result_path='C:/' + 'Users/someone/' + SENTINEL)
            raw.append(json.dumps(item, sort_keys=True))
        write_export(self.dir, events, raw_lines=raw, header=header_for(events))
        for args in ((), ('--json',)):
            result = self.cli('--records', self.dir, *args)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('T-1', result.stdout)
            self.assertNotIn(SENTINEL, result.stdout + result.stderr)

    def test_a_hostile_evidence_path_or_escape_sequence_neither_escapes_the_roots_nor_reaches_the_terminal(self):
        refs = [{'path': 'C:/p/evidence/../../secret/key.txt', 'sha256': 'ab' * 32, 'bytes': 1},
                {'path': 'C:/p/evidence/ok\x1b[2J.md', 'sha256': 'ab' * 32, 'bytes': 1},
                {'path': '//server/share/x.md', 'sha256': 'ab' * 32, 'bytes': 1},
                {'path': 'C:/other/evidence/x.md', 'sha256': 'ab' * 32, 'bytes': 1}]
        events = [event(1, 'dispatch.queued', 'T-1', kind='advisor', evidence=refs),
                  event(2, 'dispatch.failed', 'T-1', reason='bad \x1b]0;owned\x07 \u202e text')]
        model, text = self.view(events, evidence_roots=['C:/p'])
        self.assertTrue(all(c == '\n' or c.isprintable() for c in text), repr(text))
        for forbidden in ('secret', 'key.txt', 'server', 'other/evidence', 'owned\x07'):
            self.assertNotIn(forbidden, text)
        self.assertEqual(model['read']['rejected_evidence'], 4)
        self.assertNotIn('owned', text)  # a reason is free text: it is not rendered at all
        self.assertTrue(all(c == '\n' or c.isprintable() for c in json.dumps(model, ensure_ascii=False)))

    def test_a_free_text_reason_is_never_rendered_only_the_fact_that_one_was_recorded(self):
        reasons = [
            'refusing C:\\' + 'Users\\someone\\AppData\\Roaming\\npm\\codex.CMD: a shim; set LOOP_CODEX',
            'executable:C:\\' + 'Users\\Alice\\AppData\\Roaming\\npm\\codex.CMD',
            'home C:\\' + 'Users\\Some One',
            'label:\\\\?\\C:\\' + 'Users\\Bob Jones\\x',
            '/home/someone/.config/agent/codex.toml',
            'LOOP_CODEX uses codex.CMD with profile nsahm']
        for number, reason in enumerate(reasons):
            for terminal in ('dispatch.unavailable', 'dispatch.failed', 'dispatch.unknown'):
                events = [event(1, 'dispatch.queued', 'T-1', kind='advisor'), event(2, terminal, 'T-1', reason=reason)]
                model, text = self.view(events)
                shown = text + json.dumps(model)
                for forbidden in ('someone', 'Alice', 'Some One', 'Bob', 'Jones', 'codex', 'CMD', 'AppData', 'LOOP_CODEX',
                                  'nsahm', '.config', 'profile'):
                    self.assertNotIn(forbidden, shown, (number, terminal, forbidden))
                self.assertIn('reason recorded (free text, not shown)', text)
                row = model['tasks'][0]
                self.assertTrue(row['reason_recorded'])
                self.assertNotIn('reason', row)
        events = [event(1, 'dispatch.queued', 'T-1', kind='advisor'), event(2, 'dispatch.failed', 'T-1')]
        model, text = self.view(events)
        self.assertFalse(model['tasks'][0]['reason_recorded'])
        self.assertNotIn('reason recorded', text)

    def test_a_task_named_like_a_user_is_a_contract_fault_and_is_not_shown(self):
        events = [dict(event(1, 'dispatch.unavailable', 'nsahm', reason='LOOP_CODEX uses codex.CMD with profile nsahm'),
                       role='developer')]
        model, text = self.view(events)
        self.assertEqual(model['tasks'], [])
        self.assertEqual(sorted(f['code'] for f in model['faults']), ['invalid_field'])
        self.assertIn('invalid_field', text)
        self.assertNotIn('nsahm', text + json.dumps(model))
        self.assertNotIn('codex', text + json.dumps(model))

    def test_the_task_identifier_must_match_the_loop_grammar(self):
        # runner.py mints 'T-' + uuid4().hex[:10]; the real export fixture holds T-f445e27aa6
        for good in ('T-f445e27aa6', 'T-1', 'T-' + 'a' * 32):
            model, _ = self.view([event(1, 'dispatch.queued', good, kind='advisor')])
            self.assertEqual([r['task'] for r in model['tasks']], [good])
        for bad in ('nsahm', 'T-', 'T-ABC', 'T-nsahm', 't-abc', 'T-' + 'a' * 33, 'T-abc def', 'C:\\' + 'Users\\x'):
            model, text = self.view([event(1, 'dispatch.queued', bad, kind='advisor')])
            self.assertEqual(model['tasks'], [], bad)
            self.assertEqual([f['code'] for f in model['faults']], ['invalid_field'], bad)
            self.assertNotIn(bad, text + json.dumps(model))

    def test_a_role_outside_the_loops_closed_list_is_a_contract_fault(self):
        for good in ('controller', 'verifier', 'watcher', 'runner', 'reporter', 'migration', 'telemetry'):
            self.assertEqual(self.view([event(1, 'dispatch.queued', 'T-1', kind='advisor', role=good)])[0]['faults'], [])
        model, text = self.view([event(1, 'dispatch.queued', 'T-1', kind='advisor', role='nsahm')])
        self.assertEqual(model['tasks'], [])
        self.assertEqual([f['code'] for f in model['faults']], ['invalid_field'])
        self.assertNotIn('nsahm', text + json.dumps(model))

    def test_no_data_field_is_generic_text_and_no_path_scrubber_remains(self):
        from intune_iac import orchestration_contract as contract
        self.assertFalse(hasattr(contract, 'TEXT'))
        self.assertFalse(hasattr(contract, 'scrub_paths'))
        for kind, fields in contract.DATA_FIELDS.items():
            for name, how in fields.items():
                self.assertIn(how if isinstance(how, str) else type(how).__name__,
                              (contract.FLAG, contract.REASON, 'frozenset', 'Pattern'), (kind, name))

    def test_a_verification_field_that_carries_a_path_or_a_name_is_a_contract_fault(self):
        good = {'outcome': 'pass', 'requirement': 'REQ-12', 'gate': 'temporal', 'commit': 'f' * 40, 'tree': 'a' * 40}
        model, _ = self.view([event(1, 'verification.completed', None, role='verifier', **good)])
        self.assertEqual(model['faults'], [])
        hostile = {'outcome': ['nsahm', 'label:C:\\' + 'Users\\Some One', 'ok\x1b[2J'],
                   'requirement': ['nsahm', 'REQ-12 label:C:\\' + 'Users\\Alice', '\\\\?\\C:\\' + 'Users\\Bob'],
                   'gate': ['nsahm', 'C:\\' + 'Users\\Some One\\gate', '../../etc/passwd', 'Gate With Space'],
                   'commit': ['nsahm', 'C:\\' + 'Users\\x', 'F' * 40],
                   'tree': ['nsahm', '\\\\?\\C:\\' + 'Users\\Some One', 'a' * 65]}
        for field, values in hostile.items():
            for value in values:
                model, text = self.view([event(1, 'verification.completed', None, role='verifier', **dict(good, **{field: value}))])
                self.assertEqual([f['code'] for f in model['faults']], ['invalid_field'], (field, value))
                self.assertEqual(model['verifications'], {'records': 0, 'unattached': 0}, (field, value))
                for forbidden in ('nsahm', 'Some One', 'Alice', 'Bob', 'Users', 'passwd'):
                    self.assertNotIn(forbidden, text + json.dumps(model), (field, value))
        for terminal in ('dispatch.completed', 'repair.reported'):
            model, text = self.view([event(1, 'dispatch.queued', 'T-1', kind='advisor'),
                                     event(2, terminal, 'T-1', tree='label:C:\\' + 'Users\\Some One')])
            self.assertEqual([f['code'] for f in model['faults']], ['invalid_field'], terminal)
            self.assertNotIn('Some One', text + json.dumps(model))

    def test_an_event_id_or_attempt_must_be_lower_case_hex_of_the_loops_length(self):
        # event ids: uuid4().hex (32, model.py:140) or a sha256 det_id (64, model.py:86); attempts: uuid4().hex (32)
        for good in ('a' * 32, 'b' * 64):
            self.assertEqual(self.view([dict(event(1, 'dispatch.queued', 'T-1', kind='advisor'), event_id=good)])[0]['faults'], [])
        self.assertEqual(self.view([event(1, 'dispatch.queued', 'T-1', kind='advisor', attempt='c' * 32)])[0]['faults'], [])
        for bad in ('nsahm', 'ev-1', 'A' * 32, 'a' * 31, 'a' * 33, 'a' * 63, 'a' * 65, 'C:\\' + 'Users\\x'):
            model, text = self.view([dict(event(1, 'dispatch.queued', 'T-1', kind='advisor'), event_id=bad)])
            self.assertEqual(model['tasks'], [], bad)
            self.assertEqual([f['code'] for f in model['faults']], ['invalid_field'], bad)
            self.assertNotIn(bad, text + json.dumps(model))
        for bad in ('nsahm', 'A1', 'a' * 31, 'a' * 33, 'A' * 32):
            model, text = self.view([event(1, 'dispatch.queued', 'T-1', kind='advisor', attempt=bad)])
            self.assertEqual(model['tasks'], [], bad)
            self.assertEqual([f['code'] for f in model['faults']], ['invalid_field'], bad)
            self.assertNotIn(bad, text + json.dumps(model))

    def test_a_correction_must_name_event_ids_in_the_loop_format(self):
        for field in ('corrects', 'replaced_by'):
            model, text = self.view([event(1, 'verification.corrected', None, role='verifier', **{field: 'nsahm'})])
            self.assertEqual([f['code'] for f in model['faults']], ['invalid_field'], field)
            self.assertNotIn('nsahm', text + json.dumps(model))

    def test_a_gate_outside_the_loops_gate_set_is_a_contract_fault_that_does_not_show_it(self):
        good = {'outcome': 'pass', 'requirement': 'REQ-12', 'commit': 'f' * 40, 'tree': 'a' * 40}
        accepted = ('aggregate-regression', 'temporal', 'frame-review', 'work-order-verification', 'journey-1',
                    'journey-28', 'journey-32', 'journey-999')
        for gate in accepted:
            model, _ = self.view([event(1, 'verification.completed', None, role='verifier', gate=gate, **good)])
            self.assertEqual(model['faults'], [], gate)
        for gate in ('nsahm', 'alice-gate', 'journey-1000', 'journey-', 'journey-ab', 'journey-1a', 'journey-28 x', 'Temporal'):
            model, text = self.view([event(1, 'verification.completed', None, role='verifier', gate=gate, **good)])
            self.assertEqual([f['code'] for f in model['faults']], ['invalid_field'], gate)
            self.assertIn('unknown gate (not shown)', text)
            self.assertNotIn(gate, text + json.dumps(model))

    def test_a_dispatch_kind_outside_the_loops_closed_list_is_a_contract_fault(self):
        for kind in ('dispatch.queued', 'dispatch.refused'):
            model, text = self.view([event(1, kind, 'T-1', kind='nsahm')])
            self.assertEqual(model['tasks'], [])
            self.assertEqual([f['code'] for f in model['faults']], ['invalid_field'])
            self.assertNotIn('nsahm', text + json.dumps(model))

    def test_evidence_inside_a_root_shows_a_fixed_phrase_and_never_a_path_segment(self):
        from intune_iac import orchestration_contract as contract
        self.assertFalse(hasattr(contract, 'evidence_display'))
        path = 'C:\\exports\\Alice\\LOOP_CODEX=codex.CMD\\sk_live_abc'
        events = [event(1, 'dispatch.queued', 'T-1', kind='advisor',
                        evidence=[{'path': path, 'sha256': 'ab' * 32, 'bytes': 9}])]
        model, text = self.view(events, evidence_roots=['C:/exports'])
        shown = text + json.dumps(model)
        for forbidden in ('Alice', 'LOOP_CODEX', 'codex', 'sk_live', 'exports'):
            self.assertNotIn(forbidden, shown)
        self.assertIn('evidence recorded inside a configured root', text)
        row = model['tasks'][0]
        self.assertEqual((row['evidence_recorded'], row['evidence_sha256'], row['evidence_bytes']), (True, 'ab' * 32, 9))
        self.assertNotIn('evidence', row)
        model, text = self.view(events)  # no configured root: the reference is outside every root
        self.assertFalse(model['tasks'][0]['evidence_recorded'])
        self.assertIn('evidence none', text)
        self.assertNotIn('Alice', text + json.dumps(model))

    def test_an_event_type_that_is_an_array_or_an_object_is_a_fault_shown_in_the_view(self):
        from intune_iac.engineering_view import build_view, render_lines
        for bad in (['dispatch.queued'], {'a': 'b'}, 7, None):
            good = event(1, 'dispatch.queued', 'T-1', kind='advisor')
            broken = dict(event(2, 'dispatch.started', 'T-1', adopted=False), event_type=bad)
            write_export(self.dir, [good], raw_lines=[json.dumps(good), json.dumps(broken)],
                         header=header_for([good, broken]))
            model = build_view(self.dir)
            text = '\n'.join(render_lines(model))
            self.assertEqual([f['code'] for f in model['faults']], ['unknown_event_type'], repr(bad))
            self.assertIn('unknown_event_type', text)
            self.assertEqual(len(model['tasks']), 1)


if __name__ == '__main__':
    unittest.main()
