"""The reducer, the plain command and the controller-log count (PKG-UXVIS-4 item 3)."""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from intune_iac.io import readable_time
from plugin_tests.orchestration_fixtures import (RUNNER_A, RUNNER_B, event, lifecycle, wall, write_export)

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'scripts/intune-iac.py'


class ReducerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.dir = Path(temporary.name) / 'records'

    def tasks(self, events):
        from intune_iac.orchestration_export import read_export
        from intune_iac.orchestration_reducer import reduce_events
        write_export(self.dir, events)
        return {item['task']: item for item in reduce_events(read_export(self.dir)['events'])['tasks']}

    def one(self, events, task='T-1'):
        return self.tasks(events)[task]

    def test_queued_reads_queued(self):
        row = self.one([event(1, 'dispatch.queued', 'T-1', kind='advisor')])
        self.assertEqual((row['state'], row['state_words']), ('queued', 'queued, no news since ' + wall(1)))
        self.assertEqual((row['kind'], row['role']), ('advisor', 'runner'))

    def test_started_from_an_export_is_never_running(self):
        row = self.one(lifecycle('T-1'))
        self.assertEqual(row['state'], 'started')
        self.assertEqual(row['state_words'], 'started, no news since ' + wall(2))
        self.assertEqual(row['no_news_since'], wall(2))
        self.assertEqual((row['last_event_type'], row['last_seq']), ('dispatch.started', 2))
        self.assertNotIn('running', row['words'])

    def test_timed_out_and_cancel_requested_read_cancellation_pending_never_cancelled(self):
        row = self.one(lifecycle('T-1', terminal='dispatch.timed_out'))
        self.assertEqual(row['state'], 'cancel_pending')
        self.assertEqual(row['state_words'], 'cancellation pending (timed out), no news since ' + wall(3))
        row = self.one(lifecycle('T-1', terminal='dispatch.cancel_requested'))
        self.assertEqual(row['state'], 'cancel_pending')
        self.assertEqual(row['state_words'], 'cancellation pending (cancel requested), no news since ' + wall(3))
        row = self.one(lifecycle('T-1', terminal='dispatch.timed_out') + [event(4, 'dispatch.cancel_requested', 'T-1')])
        self.assertEqual(row['state_words'],
                         'cancellation pending (timed out; cancel requested), no news since ' + wall(4))
        for words in (row['words'],):
            self.assertNotIn('cancelled', words)

    def test_completed_reads_completed_unverified(self):
        row = self.one(lifecycle('T-1', kind='repair', terminal='dispatch.completed'))
        self.assertEqual((row['state'], row['state_words']), ('completed', 'completed, unverified'))
        self.assertIsNone(row['no_news_since'])
        self.assertEqual(row['kind'], 'repair')

    def test_failed_and_unknown_keep_their_reason_apart_from_the_state_words(self):
        row = self.one(lifecycle('T-1', terminal='dispatch.failed', reason='schema_invalid'))
        self.assertEqual((row['state'], row['state_words'], row['reason_recorded']), ('failed', 'failed', True))
        row = self.one(lifecycle('T-1', terminal='dispatch.unknown', reason='cleanup not confirmed after cancel (deadline)'))
        self.assertEqual((row['state'], row['state_words']), ('unknown', 'unknown'))
        self.assertTrue(row['reason_recorded'])
        self.assertNotIn('cleanup not confirmed after cancel', json.dumps(row))

    def test_unavailable_and_refused_read_blocked_with_the_reason(self):
        row = self.one([event(1, 'dispatch.queued', 'T-1', kind='advisor'),
                        event(2, 'dispatch.unavailable', 'T-1', reason='route offline')])
        self.assertEqual((row['state'], row['state_words'], row['reason_recorded']), ('blocked', 'blocked', True))
        row = self.one([event(1, 'dispatch.refused', 'T-2', kind='advisor', reason='limit: 2 advisor tasks already running')],
                       'T-2')
        self.assertEqual((row['state'], row['kind'], row['reason_recorded']), ('blocked', 'advisor', True))

    def test_cancelled_reads_cancelled_only_with_cleanup_confirmed_by_the_route(self):
        row = self.one(lifecycle('T-1', terminal='dispatch.cancelled', cleanup_confirmed=True, reason='cleanup confirmed'))
        self.assertEqual((row['state'], row['state_words']), ('cancelled', 'cancelled'))
        row = self.one(lifecycle('T-1', terminal='dispatch.cancelled', cleanup_confirmed=True, reason='controller attested'))
        self.assertEqual((row['state'], row['state_words']), ('cancelled', 'cancelled (attested by the controller)'))
        row = self.one(lifecycle('T-1', terminal='dispatch.cancelled', cleanup_confirmed=False, reason='x'))
        self.assertEqual((row['state'], row['state_words']),
                         ('cancel_pending', 'cancellation pending (cancel recorded, cleanup not confirmed), no news since ' + wall(3)))

    def test_an_adopted_started_shows_the_adoption_count_and_the_current_incarnation(self):
        row = self.one(lifecycle('T-1') + [event(3, 'dispatch.started', 'T-1', adopted=True, incarnation=RUNNER_B)])
        self.assertEqual((row['adoptions'], row['incarnation']), (1, RUNNER_B))
        self.assertEqual(row['state'], 'started')
        row = self.one(lifecycle('T-1'))
        self.assertEqual((row['adoptions'], row['incarnation']), (0, RUNNER_A))

    def test_a_late_result_is_an_annotation_never_a_state_change(self):
        row = self.one(lifecycle('T-1', terminal='dispatch.failed', reason='x') + [event(4, 'advisor.late_result', 'T-1', role='controller')])
        self.assertTrue(row['late_result'])
        self.assertEqual(row['state'], 'failed')
        self.assertTrue(row['words'].endswith('late result recorded'), row['words'])
        self.assertEqual((row['last_event_type'], row['last_seq']), ('advisor.late_result', 4))
        self.assertFalse(self.one(lifecycle('T-9'), 'T-9')['late_result'])

    def test_tasks_are_ordered_by_their_first_sequence_and_events_without_a_task_make_none(self):
        events = lifecycle('T-b', start=5) + lifecycle('T-a', start=1) + [event(20, 'incident.opened')]
        tasks = self.tasks(events)
        self.assertEqual(list(tasks), ['T-a', 'T-b'])

    def test_a_task_row_says_whether_evidence_was_recorded_and_carries_no_path(self):
        from intune_iac.orchestration_export import read_export
        from intune_iac.orchestration_reducer import reduce_events
        ref = lambda name, digest: [{'path': 'C:/p/evidence/' + name, 'sha256': digest * 32, 'bytes': 7}]
        events = [event(1, 'dispatch.queued', 'T-1', kind='advisor', evidence=ref('a.md', 'ab')),
                  event(2, 'dispatch.started', 'T-1', adopted=False),
                  event(3, 'dispatch.completed', 'T-1', evidence=ref('b.md', 'cd'))]
        write_export(self.dir, events)
        row = reduce_events(read_export(self.dir, roots=['C:/p'])['events'])['tasks'][0]
        self.assertEqual((row['evidence_recorded'], row['evidence_sha256'], row['evidence_bytes']), (True, 'cd' * 32, 7))
        self.assertNotIn('evidence', row)
        self.assertNotIn('b.md', json.dumps(row))
        row = reduce_events(read_export(self.dir)['events'])['tasks'][0]
        self.assertEqual((row['evidence_recorded'], row['evidence_sha256'], row['evidence_bytes']), (False, None, None))


class ViewTests(unittest.TestCase):
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

    def test_the_text_opens_with_the_source_header_then_one_line_per_task(self):
        events = lifecycle('T-1', terminal='dispatch.completed') + lifecycle('T-2', start=10, kind='repair')
        model, text = self.view(events)
        lines = text.splitlines()
        self.assertIn('read-only', lines[0])
        self.assertIn('orchestration-export/1', text)
        self.assertIn('5 events, last sequence 11', text)
        self.assertIn('the header agrees with what was read', text)
        by_task = {line.split()[0]: line for line in lines if line.startswith('T-')}
        self.assertEqual(sorted(by_task), ['T-1', 'T-2'])
        self.assertIn('completed, unverified', by_task['T-1'])
        self.assertIn('last dispatch.completed seq 3', by_task['T-1'])
        self.assertIn('started, no news since ' + readable_time(wall(11)), by_task['T-2'])
        self.assertIn('repair', by_task['T-2'])
        self.assertIn('adoptions 0', by_task['T-2'])

    def test_an_export_cut_after_a_started_prints_the_mismatch_and_the_task_still_reads_started(self):
        from plugin_tests.orchestration_fixtures import header_for
        events = lifecycle('T-1', terminal='dispatch.completed')
        model, text = self.view(events[:2], export={'header': header_for(events)})
        self.assertIn('truncated or changed', text)
        self.assertIn('MISMATCH', text)
        self.assertIn('started, no news since ' + readable_time(wall(2)), text)
        self.assertEqual(model['source']['check']['state'], 'mismatch')

    def test_a_missing_header_says_so_in_plain_words(self):
        model, text = self.view(lifecycle('T-1'), export={'header': False})
        self.assertIn('no usable header', text)
        self.assertIn('truncated export cannot be told from a quiet system', text)

    def test_contract_faults_are_listed_without_the_offending_text(self):
        events = lifecycle('T-1')
        altered = dict(events[1], task='T-other')
        model, text = self.view(events, export={'extra_lines': [json.dumps(altered, sort_keys=True)]})
        self.assertIn('Contract faults (1)', text)
        self.assertIn('event_conflict', text)
        self.assertNotIn('T-other', text)

    def test_the_controller_log_is_counted_not_modelled(self):
        log = self.root / 'events.jsonl'
        rows = [{'kind': 'dispatch', 'summary': 'x'}] * 5 + [{'kind': 'decision'}] * 3 + [{'kind': 'dispatch'}]
        log.write_text('\n'.join(json.dumps(row) for row in rows) + '\nnot json\n[1]\n', encoding='utf-8', newline='\n')
        model, text = self.view(lifecycle('T-1') + lifecycle('T-2', start=10), controller_log=log)
        self.assertEqual(model['controller_log'], {'dispatch_lines': 6, 'loop_tasks': 2, 'only_in_controller_log': 4,
                                                   'unreadable_lines': 2})
        self.assertIn('4 dispatches recorded only in the controller log; not modelled', text)
        self.assertIn('6 dispatch lines', text)
        self.assertIn('no line is matched to a task', text)

    def test_the_count_never_goes_negative_and_no_log_means_no_line(self):
        log = self.root / 'events.jsonl'
        log.write_text(json.dumps({'kind': 'dispatch'}) + '\n', encoding='utf-8', newline='\n')
        model, text = self.view(lifecycle('T-1') + lifecycle('T-2', start=10), controller_log=log)
        self.assertEqual(model['controller_log']['only_in_controller_log'], 0)
        model, text = self.view(lifecycle('T-1'))
        self.assertIsNone(model['controller_log'])
        self.assertNotIn('controller log', text)

    def test_an_unreadable_controller_log_is_an_error_not_a_zero(self):
        from intune_iac.engineering_view import ControllerLogUnreadable
        with self.assertRaises(ControllerLogUnreadable):
            self.view(lifecycle('T-1'), controller_log=self.root / 'absent.jsonl')

    def test_nothing_in_the_text_can_move_or_rewrite_the_terminal(self):
        hostile = '\x1b[2J\x1b]0;owned\x07\u202e'
        events = [event(1, 'dispatch.queued', 'T-1', kind='advisor'),
                  event(2, 'dispatch.failed', 'T-1', reason='bad ' + hostile)]
        model, text = self.view(events)
        self.assertNotIn('owned', text)
        self.assertTrue(all(c == '\n' or c.isprintable() for c in text), repr(text))
        self.assertTrue(all(c == '\n' or c.isprintable() for c in json.dumps(model, ensure_ascii=False)))

    def test_the_json_form_carries_the_same_rows(self):
        model, text = self.view(lifecycle('T-1', terminal='dispatch.completed'))
        self.assertEqual(model['tasks'][0]['task'], 'T-1')
        json.dumps(model)  # plain data only


class CommandTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def cli(self, *args):
        return subprocess.run([sys.executable, str(CLI), 'engineering', *map(str, args)], text=True,
                              capture_output=True, cwd='/tmp')

    def test_with_no_records_path_it_says_so_in_a_sentence_and_exits_zero(self):
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Engineering records are not configured', ' '.join(result.stdout.split()))
        self.assertIn('--records', result.stdout)
        result = self.cli('--json')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['engineering'], 'not_configured')

    def test_the_command_prints_the_view_of_an_export(self):
        events = lifecycle('T-1', terminal='dispatch.completed') + lifecycle('T-2', start=10)
        write_export(self.root / 'records', events)
        result = self.cli('--records', self.root / 'records')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('T-1', result.stdout)
        self.assertIn('completed, unverified', result.stdout)
        self.assertIn('started, no news since', result.stdout)

    def test_json_prints_one_document_with_the_rows(self):
        write_export(self.root / 'records', lifecycle('T-1', terminal='dispatch.completed'))
        result = self.cli('--records', self.root / 'records', '--json')
        self.assertEqual(result.returncode, 0, result.stderr)
        document = json.loads(result.stdout)
        self.assertEqual([row['task'] for row in document['tasks']], ['T-1'])
        self.assertEqual(document['source']['check']['state'], 'ok')

    def test_evidence_roots_and_the_controller_log_are_options(self):
        events = [event(1, 'dispatch.queued', 'T-1', kind='advisor',
                        evidence=[{'path': 'C:/p/evidence/a.md', 'sha256': 'ab' * 32, 'bytes': 1}])]
        write_export(self.root / 'records', events)
        log = self.root / 'controller.jsonl'
        log.write_text(json.dumps({'kind': 'dispatch'}) + '\n' + json.dumps({'kind': 'dispatch'}) + '\n', encoding='utf-8')
        result = self.cli('--records', self.root / 'records', '--evidence-root', 'C:/p', '--controller-log', log)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('evidence recorded inside a configured root', result.stdout)
        self.assertNotIn('a.md', result.stdout)
        self.assertIn('1 dispatches recorded only in the controller log; not modelled', result.stdout)
        result = self.cli('--records', self.root / 'records')
        self.assertNotIn('a.md', result.stdout)

    def test_a_records_path_that_cannot_be_read_is_an_error_with_a_nonzero_exit(self):
        result = self.cli('--records', self.root / 'absent')
        self.assertEqual(result.returncode, 3)
        self.assertEqual(json.loads(result.stderr)['error']['code'], 'engineering_records_unreadable')
        self.assertEqual(result.stdout, '')
        write_export(self.root / 'records', lifecycle('T-1'))
        result = self.cli('--records', self.root / 'records', '--evidence-root', 'relative/dir')
        self.assertEqual(result.returncode, 3)
        self.assertEqual(json.loads(result.stderr)['error']['code'], 'engineering_root_invalid')

    def test_the_command_writes_nothing_into_the_records_directory(self):
        write_export(self.root / 'records', lifecycle('T-1'))
        before = sorted((p.name, p.stat().st_mtime_ns, p.stat().st_size) for p in (self.root / 'records').iterdir())
        self.cli('--records', self.root / 'records')
        after = sorted((p.name, p.stat().st_mtime_ns, p.stat().st_size) for p in (self.root / 'records').iterdir())
        self.assertEqual(before, after)

    def test_help_lists_the_command(self):
        result = subprocess.run([sys.executable, str(CLI), '--help'], text=True, capture_output=True, cwd='/tmp')
        self.assertIn('engineering', result.stdout)



def busy_events():
    """A task read as unknown, cancelled by attestation, with a late result, adopted once: the widest row."""
    return (lifecycle('T-1001', kind='repair', terminal='dispatch.completed')
            + lifecycle('T-1002', start=10, kind='advisor', terminal='dispatch.timed_out')
            + [event(13, 'dispatch.cancelled', 'T-1002', cleanup_confirmed=True, reason='controller attested'),
               event(14, 'dispatch.started', 'T-1002', adopted=True, incarnation=RUNNER_B),
               event(15, 'advisor.late_result', 'T-1002', role='controller')])


class ReadableTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.dir = self.root / 'records'
        write_export(self.dir, busy_events())

    def model(self):
        from intune_iac.engineering_view import build_view
        return build_view(self.dir)

    def lines(self, width):
        from intune_iac.engineering_view import render_lines
        return render_lines(self.model(), width)

    def tokens(self, lines):
        return sorted(word for line in lines for word in line.split() if word != '|')

    def test_no_line_is_wider_than_the_width_and_no_token_is_split(self):
        whole = self.tokens(self.lines(None))
        for width in (80, 60, 40):
            lines = self.lines(width)
            self.assertEqual([line for line in lines if len(line) > width], [], width)
            self.assertEqual(self.tokens(lines), whole, width)

    def test_a_narrow_width_puts_one_field_per_line_under_the_task_id(self):
        lines = self.lines(60)
        index = next(i for i, line in enumerate(lines) if line.startswith('T-1002'))
        self.assertNotIn(' | ', lines[index])
        following = []
        for line in lines[index + 1:]:
            if not line.startswith(' '):
                break
            following.append(line.strip())
        self.assertTrue(any(line.startswith('last advisor.late_result seq 15') for line in following), following)
        self.assertTrue(any(line.startswith('adoptions 1, incarnation ' + RUNNER_B) for line in following), following)
        self.assertTrue(any(line.startswith('evidence none') for line in following), following)

    def test_a_wide_width_breaks_only_at_a_field_boundary_with_a_hanging_indent(self):
        lines = self.lines(100)
        index = next(i for i, line in enumerate(lines) if line.startswith('T-1002'))
        self.assertTrue(lines[index + 1].startswith('    '), lines[index:index + 2])
        self.assertFalse(lines[index].endswith(('adoptions', 'seq', 'last')), lines[index])

    def test_a_number_never_starts_a_line_alone_from_its_word(self):
        for width in (60, 45):
            for line in self.lines(width):
                self.assertFalse(re.match(r'\s*\d+\b', line) and line.strip().split()[0].isdigit(), (width, line))

    def test_the_read_only_statement_is_the_last_line_and_appears_once(self):
        for width in (None, 80, 60):
            lines = self.lines(width)
            self.assertEqual(' '.join(' '.join(lines).split()).count('cannot dispatch, approve or cancel anything'), 1, width)
            self.assertIn('cannot dispatch, approve or cancel anything', ' '.join(' '.join(lines[-2:]).split()), width)
            self.assertIn('read-only', lines[0])
        self.assertEqual(self.lines(None)[-1], 'This view is read-only: it cannot dispatch, approve or cancel anything.')

    def test_times_read_as_the_workbench_writes_them_and_json_keeps_the_exact_value(self):
        write_export(self.dir, busy_events() + lifecycle('T-1003', start=20))
        text = '\n'.join(self.lines(None))
        self.assertIn('exported ' + readable_time(wall(500)), text)
        self.assertIn('no news since ' + readable_time(wall(21)), text)
        self.assertIsNone(re.search(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d', text), text)
        model = self.model()
        self.assertEqual(model['source']['header']['exported_utc'], wall(500))
        self.assertIn(wall(21), json.dumps(model))

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(CLI), 'engineering', *map(str, args)], text=True,
                              capture_output=True, cwd='/tmp')

    def test_json_from_the_command_keeps_the_exact_times(self):
        document = json.loads(self.run_cli('--records', self.dir, '--json').stdout)
        self.assertEqual(document['source']['header']['exported_utc'], wall(500))

    def test_the_not_configured_sentence_says_loopctl_export_is_typed_in_a_shell(self):
        result = self.run_cli()
        text = ' '.join(result.stdout.split())
        self.assertIn('`loopctl export` (a command typed in a shell)', text)
        self.assertEqual([line for line in result.stdout.splitlines() if len(line) > 80], [])
        self.assertEqual(json.loads(self.run_cli('--json').stdout)['engineering'], 'not_configured')

    def test_piped_output_is_wrapped_to_80_columns(self):
        result = self.run_cli('--records', self.dir)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([line for line in result.stdout.splitlines() if len(line) > 80], [])
        self.assertIn('cannot dispatch, approve or cancel anything', ' '.join(' '.join(result.stdout.splitlines()[-2:]).split()))


if __name__ == '__main__':
    unittest.main()
