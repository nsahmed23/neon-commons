"""The orchestration-record contract and the loop-export adapter (PKG-UXVIS-4 item 2)."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from plugin_tests.orchestration_fixtures import (DIGEST, event, header_for, lifecycle, write_export)

SENTINEL = 'SENTINEL-NEVER-SHOWN'
ESC = '\x1b[2J\x1b]0;owned\x07'


def read(directory, roots=()):
    from intune_iac.orchestration_export import read_export
    return read_export(directory, roots=roots)


class ExportAdapterTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.dir = self.root / 'records'

    def faults(self, result, code):
        return [item for item in result['faults'] if item['code'] == code]

    def test_a_whole_export_reads_with_its_header_agreeing(self):
        events = lifecycle('T-1', terminal='dispatch.completed') + lifecycle('T-2', start=10)
        write_export(self.dir, events)
        result = read(self.dir)
        self.assertEqual(result['check']['state'], 'ok')
        self.assertEqual([e['seq'] for e in result['events']], [1, 2, 3, 10, 11])
        self.assertEqual(result['faults'], [])
        self.assertEqual(result['header']['count'], 5)
        self.assertEqual(result['header']['state_digest'], DIGEST)
        first = result['events'][0]
        self.assertEqual((first['event_type'], first['task'], first['role'], first['data']),
                         ('dispatch.queued', 'T-1', 'runner', {'kind': 'advisor'}))

    def test_events_are_ordered_by_sequence_whatever_the_file_order(self):
        events = lifecycle('T-1', terminal='dispatch.completed')
        write_export(self.dir, list(reversed(events)))
        self.assertEqual([e['seq'] for e in read(self.dir)['events']], [1, 2, 3])
        self.assertEqual(read(self.dir)['check']['state'], 'ok')

    def test_an_export_cut_short_is_reported_as_truncated_or_changed(self):
        events = lifecycle('T-1', terminal='dispatch.completed')
        write_export(self.dir, events[:2], header=header_for(events))
        result = read(self.dir)
        self.assertEqual(result['check']['state'], 'mismatch')
        self.assertEqual((result['check']['header_count'], result['check']['read_count']), (3, 2))
        self.assertEqual((result['check']['header_last_seq'], result['check']['read_last_seq']), (3, 2))
        self.assertIn('truncated or changed', result['check']['message'])
        self.assertEqual([e['seq'] for e in result['events']], [1, 2])

    def test_an_export_with_more_events_than_its_header_is_also_a_mismatch(self):
        events = lifecycle('T-1', terminal='dispatch.completed')
        write_export(self.dir, events, header=header_for(events[:2]))
        self.assertEqual(read(self.dir)['check']['state'], 'mismatch')

    def test_a_missing_header_is_reported_and_the_events_are_still_read(self):
        write_export(self.dir, lifecycle('T-1'), header=False)
        result = read(self.dir)
        self.assertEqual(result['check']['state'], 'no_header')
        self.assertIsNone(result['header'])
        self.assertIn('truncated export cannot be told from a quiet system', result['check']['message'])
        self.assertEqual(len(result['events']), 2)

    def conflicted(self, first_seq=5, copy_seq=5):
        a = dict(event(first_seq, 'dispatch.queued', 'T-1', kind='advisor'), event_id='ev-a')
        return a, dict(a, seq=copy_seq, data={'kind': 'other'})

    def test_a_conflicted_id_keeps_its_sequence_claimed_so_a_later_id_on_it_is_not_folded(self):
        a, a_copy = self.conflicted()
        b = dict(event(5, 'dispatch.queued', 'T-2', kind='advisor'), event_id='ev-b')
        write_export(self.dir, [a, a_copy, b], header=header_for([a, b]))
        result = read(self.dir)
        self.assertEqual(result['events'], [])
        self.assertEqual(len(self.faults(result, 'event_conflict')), 1)
        self.assertEqual(len(self.faults(result, 'seq_reused')), 1)

    def test_a_conflicting_copy_on_another_sequence_contests_both_and_drops_the_id_already_holding_it(self):
        a, a_copy = self.conflicted(first_seq=5, copy_seq=6)
        c = dict(event(6, 'dispatch.queued', 'T-3', kind='advisor'), event_id='ev-c')
        d = dict(event(5, 'dispatch.queued', 'T-4', kind='advisor'), event_id='ev-d')
        write_export(self.dir, [a, c, a_copy, d], header=header_for([a, c, d]))
        result = read(self.dir)
        self.assertEqual(result['events'], [])
        self.assertEqual(len(self.faults(result, 'event_conflict')), 1)
        self.assertEqual(len(self.faults(result, 'seq_reused')), 2)

    def test_many_conflicts_are_read_in_time_that_does_not_grow_with_the_square_of_the_events(self):
        import time
        count = 20000
        lines = [json.dumps(dict(event(n, 'dispatch.queued', 'T-1', kind=kind), event_id='e%d' % n))
                 for kind in ('advisor', 'other') for n in range(1, count + 1)]
        write_export(self.dir, [], raw_lines=lines, header=header_for([]))
        started = time.monotonic()
        result = read(self.dir)
        elapsed = time.monotonic() - started
        self.assertEqual(len(self.faults(result, 'event_conflict')), count)
        self.assertLess(elapsed, 3.0, 'reading took %.1f s' % elapsed)

    def test_a_header_of_another_contract_or_with_bad_fields_is_not_a_header(self):
        events = lifecycle('T-1')
        for bad in (dict(header_for(events), contract='orchestration-export/2'),
                    dict(header_for(events), count='2'),
                    dict(header_for(events), last_seq=-1),
                    dict(header_for(events), state_digest='short'),
                    dict(header_for(events), source_id=7),
                    dict(header_for(events), exported_utc='yesterday')):
            write_export(self.dir, events, header=bad)
            result = read(self.dir)
            self.assertEqual(result['check']['state'], 'no_header', bad)
            self.assertIsNone(result['header'])
        (self.dir / 'header.json').write_text('{not json', encoding='utf-8')
        self.assertEqual(read(self.dir)['check']['state'], 'no_header')

    def test_a_duplicated_line_is_one_record_and_changes_nothing(self):
        events = lifecycle('T-1')
        write_export(self.dir, events)
        once = read(self.dir)
        write_export(self.dir, events, extra_lines=[json.dumps(events[1], sort_keys=True)] * 3)
        again = read(self.dir)
        self.assertEqual(again['events'], once['events'])
        self.assertEqual(again['faults'], [])
        self.assertEqual(again['check']['state'], 'ok')
        self.assertEqual(again['duplicate_lines'], 3)

    def test_the_same_id_with_a_different_body_is_a_contract_fault_and_is_never_folded(self):
        events = lifecycle('T-1')
        altered = dict(events[1], task='T-other')
        write_export(self.dir, events, extra_lines=[json.dumps(altered, sort_keys=True)])
        result = read(self.dir)
        conflict = self.faults(result, 'event_conflict')
        self.assertEqual(len(conflict), 1)
        self.assertEqual(conflict[0]['event_id'], 'ev-2')
        self.assertNotIn('ev-2', [e['event_id'] for e in result['events']])
        self.assertEqual(result['check']['state'], 'ok')  # the id is still one of the header's two events

    def test_a_difference_outside_the_allowlist_still_makes_the_bodies_different(self):
        events = lifecycle('T-1')
        altered = dict(events[1], hidden='changed after the first copy')
        write_export(self.dir, events, extra_lines=[json.dumps(altered, sort_keys=True)])
        self.assertEqual(len(self.faults(read(self.dir), 'event_conflict')), 1)

    def test_two_event_ids_on_one_sequence_are_a_contract_fault(self):
        events = lifecycle('T-1')
        other = dict(events[1], event_id='ev-other')
        write_export(self.dir, events, extra_lines=[json.dumps(other, sort_keys=True)], header=header_for(events))
        result = read(self.dir)
        self.assertEqual(len(self.faults(result, 'seq_reused')), 1)
        self.assertEqual([e['event_id'] for e in result['events']].count('ev-other'), 0)

    def test_a_third_claimant_of_a_contested_sequence_is_not_kept(self):
        events = lifecycle('T-1')
        first = dict(events[1], event_id='x1')
        third = dict(events[1], event_id='x2', task='T-9')
        write_export(self.dir, events, extra_lines=[json.dumps(first, sort_keys=True), json.dumps(third, sort_keys=True)],
                     header=header_for(events))
        result = read(self.dir)
        ids = [e['event_id'] for e in result['events']]
        self.assertEqual(ids, ['ev-1'])
        self.assertEqual(len(self.faults(result, 'seq_reused')), 2)
        self.assertNotIn('T-9', [e['task'] for e in result['events']])

    def test_only_allowlisted_fields_survive(self):
        events = lifecycle('T-1', terminal='dispatch.completed')
        poisoned = []
        for item in events:
            item = dict(item, prompt=SENTINEL, result={'text': SENTINEL}, agent_config=SENTINEL, session_id=SENTINEL)
            item['data'] = dict(item['data'], result={'text': SENTINEL}, summary=SENTINEL, prompt=SENTINEL,
                                handle=SENTINEL, route=SENTINEL, producer_id=SENTINEL)
            poisoned.append(item)
        write_export(self.dir, poisoned, header=header_for(events))
        result = read(self.dir)
        self.assertEqual(result['faults'], [])
        text = json.dumps(result, sort_keys=True)
        self.assertNotIn(SENTINEL, text)
        for record in result['events']:
            self.assertEqual(sorted(record), ['attempt', 'data', 'event_id', 'event_type', 'evidence', 'incarnation',
                                              'role', 'seq', 'task', 'wall_utc'])

    def test_a_free_text_reason_is_not_carried_only_the_fact_that_one_was_recorded(self):
        events = [event(1, 'dispatch.queued', 'T-1', kind='advisor'),
                  event(2, 'dispatch.failed', 'T-1', reason=ESC + 'x' * 500)]
        write_export(self.dir, events)
        data = read(self.dir)['events'][1]['data']
        self.assertEqual(data, {'reason_recorded': True, 'reason_attested': False})

    def test_an_identifier_with_control_characters_is_a_fault_and_never_reaches_a_record(self):
        events = [event(1, 'dispatch.queued', 'T-1', kind='advisor'),
                  dict(event(2, 'dispatch.started', 'T-1', adopted=False), task='T-' + ESC),
                  dict(event(3, 'dispatch.started', 'T-1', adopted=False), role='runner' + ESC),
                  dict(event(4, 'dispatch.started', 'T-1', adopted=False), wall_utc='soon' + ESC)]
        write_export(self.dir, events)
        result = read(self.dir)
        self.assertEqual([e['seq'] for e in result['events']], [1])
        self.assertEqual(len(self.faults(result, 'invalid_field')), 3)
        text = json.dumps(result)
        self.assertNotIn('\\u001b', text)
        self.assertNotIn('owned', text)

    def test_wrong_types_in_the_listed_fields_are_faults(self):
        events = [event(1, 'dispatch.queued', 'T-1', kind=['advisor']),
                  event(2, 'dispatch.started', 'T-1', adopted='yes'),
                  event(3, 'dispatch.cancelled', 'T-1', cleanup_confirmed=1)]
        write_export(self.dir, events)
        result = read(self.dir)
        self.assertEqual(result['events'], [])
        self.assertEqual(len(self.faults(result, 'invalid_field')), 3)

    def test_an_event_type_outside_the_closed_list_is_a_fault_and_is_not_folded(self):
        events = lifecycle('T-1') + [event(9, 'dispatch.teleported', 'T-1')]
        write_export(self.dir, events)
        result = read(self.dir)
        self.assertEqual(len(self.faults(result, 'unknown_event_type')), 1)
        self.assertEqual([e['seq'] for e in result['events']], [1, 2])

    def test_a_line_that_is_not_json_is_a_fault_with_its_number_and_without_its_text(self):
        good = [json.dumps(item) for item in lifecycle('T-1')]
        write_export(self.dir, [], raw_lines=[good[0], '{"event_id": ' + SENTINEL, '[1, 2]', good[1]],
                     header=header_for(lifecycle('T-1')))
        result = read(self.dir)
        self.assertEqual([item['line'] for item in self.faults(result, 'invalid_line')], [2, 3])
        self.assertNotIn(SENTINEL, json.dumps(result))
        self.assertEqual(len(result['events']), 2)

    def test_a_missing_or_unreadable_records_directory_is_an_error_not_an_empty_view(self):
        from intune_iac.orchestration_export import ExportUnreadable
        with self.assertRaises(ExportUnreadable):
            read(self.root / 'absent')
        (self.root / 'plain-file').write_text('x')
        with self.assertRaises(ExportUnreadable):
            read(self.root / 'plain-file')
        self.dir.mkdir()
        (self.dir / 'header.json').write_text('{}')
        with self.assertRaises(ExportUnreadable):  # a header and no events file
            read(self.dir)

    @unittest.skipUnless(hasattr(os, 'symlink'), 'needs symbolic links')
    def test_a_symbolic_link_in_place_of_the_events_file_is_refused(self):
        from intune_iac.orchestration_export import ExportUnreadable
        write_export(self.root / 'real', lifecycle('T-1'))
        self.dir.mkdir()
        os.symlink(self.root / 'real' / 'events.jsonl', self.dir / 'events.jsonl')
        with self.assertRaises(ExportUnreadable):
            read(self.dir)

    @unittest.skipUnless(hasattr(os, 'symlink'), 'needs symbolic links')
    def test_a_symbolic_link_is_refused_where_the_platform_has_no_no_follow_flag(self):
        from unittest import mock
        from intune_iac.orchestration_export import ExportUnreadable
        write_export(self.root / 'real', lifecycle('T-1'))
        self.dir.mkdir()
        os.symlink(self.root / 'real' / 'events.jsonl', self.dir / 'events.jsonl')
        with mock.patch.object(os, 'O_NOFOLLOW', 0, create=True):  # as on Windows
            with self.assertRaises(ExportUnreadable):
                read(self.dir)

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'needs named pipes')
    def test_a_named_pipe_in_place_of_a_file_is_refused_without_blocking(self):
        import subprocess
        import sys
        code = ('import sys\n'
                'from intune_iac.engineering_view import build_view\n'
                'try:\n'
                '    view = build_view(sys.argv[1], controller_log=sys.argv[2] if len(sys.argv) > 2 else None)\n'
                'except Exception as error:\n'
                '    print("REFUSED", type(error).__name__)\n'
                'else:\n'
                '    print("VIEW", [f["code"] for f in view["faults"]], view["source"]["check"]["state"])\n')
        events = lifecycle('T-1', terminal='dispatch.completed')

        def run(*extra):
            try:
                return subprocess.run([sys.executable, '-c', code, str(self.dir), *extra], capture_output=True,
                                      text=True, timeout=10, cwd=str(Path(__file__).resolve().parents[1])).stdout
            except subprocess.TimeoutExpired:
                self.fail('the view blocked on a named pipe')

        write_export(self.dir, events)
        os.remove(self.dir / 'header.json')
        os.mkfifo(self.dir / 'header.json')
        out = run()
        self.assertIn('VIEW', out)
        self.assertIn('invalid_header', out)
        self.assertIn('no_header', out)
        os.remove(self.dir / 'header.json')
        write_export(self.dir, events)
        os.remove(self.dir / 'events.jsonl')
        os.mkfifo(self.dir / 'events.jsonl')
        self.assertIn('REFUSED ExportUnreadable', run())
        os.remove(self.dir / 'events.jsonl')
        write_export(self.dir, events)
        os.mkfifo(self.root / 'controller.log')
        self.assertIn('REFUSED ControllerLogUnreadable', run(str(self.root / 'controller.log')))

    def test_an_oversized_line_is_a_fault_and_the_rest_still_reads(self):
        good = [json.dumps(item) for item in lifecycle('T-1')]
        write_export(self.dir, [], raw_lines=[good[0], '{"x": "' + 'a' * (2 * 1024 * 1024) + '"}', good[1]],
                     header=header_for(lifecycle('T-1')))
        result = read(self.dir)
        self.assertEqual(len(self.faults(result, 'invalid_line')), 1)
        self.assertEqual(len(result['events']), 2)


class EvidencePathTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.dir = Path(temporary.name) / 'records'

    def evidence(self, *paths):
        return [{'path': path, 'sha256': 'ab' * 32, 'bytes': 5} for path in paths]

    def read_with(self, paths, roots):
        write_export(self.dir, [event(1, 'dispatch.queued', 'T-1', evidence=self.evidence(*paths), kind='advisor')])
        return read(self.dir, roots=roots)

    def test_a_path_inside_a_configured_root_is_kept_relative_to_it(self):
        result = self.read_with(['C:/Dev/Projects/intune-rescue/lanes/a/r.md', 'C:\\Dev\\Projects\\intune-rescue\\lanes\\b.md'],
                                ['C:/Dev/Projects/intune-rescue'])
        kept = [ref['path'] for ref in result['events'][0]['evidence']]
        self.assertEqual(kept, ['intune-rescue/lanes/a/r.md', 'intune-rescue/lanes/b.md'])
        self.assertEqual(result['rejected_evidence'], 0)
        self.assertEqual(result['events'][0]['evidence'][0]['sha256'], 'ab' * 32)
        self.assertEqual(result['events'][0]['evidence'][0]['bytes'], 5)

    def test_paths_outside_every_root_are_rejected_and_counted_not_shown(self):
        hostile = ['C:/Dev/Projects/intune-rescue/../secret/key.pem', 'C:/Dev/Projects/intune-rescue/lanes/../../x',
                   'C:/Dev/Projects/other/r.md', '//server/share/r.md', 'relative/r.md', '../r.md',
                   'C:/Dev/Projects/intune-rescue', 'C:/Dev/Projects/intune-rescue-evil/r.md',
                   'C:/Dev/Projects/intune-rescue/' + '\x1b[31m' + 'r.md', 'C:/Dev/Projects/intune-rescue/a\x00b', '', 7]
        result = self.read_with(hostile, ['C:/Dev/Projects/intune-rescue'])
        self.assertEqual(result['events'][0]['evidence'], [])
        self.assertEqual(result['rejected_evidence'], len(hostile))
        text = json.dumps(result)
        for fragment in ('secret', 'key.pem', 'server', '[31m'):
            self.assertNotIn(fragment, text)

    def test_no_configured_root_means_no_path_is_shown(self):
        result = self.read_with(['C:/Dev/Projects/intune-rescue/r.md'], [])
        self.assertEqual(result['events'][0]['evidence'], [])
        self.assertEqual(result['rejected_evidence'], 1)

    def test_drive_letters_compare_without_case_and_other_paths_with_case(self):
        result = self.read_with(['c:/dev/projects/intune-rescue/r.md', '/home/u/Work/r.md', '/home/u/work/r.md'],
                                ['C:/Dev/Projects/intune-rescue', '/home/u/work'])
        self.assertEqual([ref['path'] for ref in result['events'][0]['evidence']],
                         ['intune-rescue/r.md', 'work/r.md'])
        self.assertEqual(result['rejected_evidence'], 1)

    def test_a_windows_root_also_accepts_the_same_directory_spelled_for_wsl(self):
        result = self.read_with(['/mnt/c/Dev/Projects/intune-rescue/r.md'], ['C:/Dev/Projects/intune-rescue'])
        self.assertEqual([ref['path'] for ref in result['events'][0]['evidence']], ['intune-rescue/r.md'])
        result = self.read_with(['D:/data/r.md'], ['/mnt/d/data'])
        self.assertEqual([ref['path'] for ref in result['events'][0]['evidence']], ['data/r.md'])

    def test_malformed_evidence_entries_are_dropped_with_a_fault_not_shown(self):
        write_export(self.dir, [event(1, 'dispatch.queued', 'T-1', kind='advisor',
                                      evidence=[{'path': 'C:/r/a.md', 'sha256': 'nothex', 'bytes': 'many'}])])
        result = read(self.dir, roots=['C:/r'])
        self.assertEqual(result['events'], [])
        self.assertEqual(len([f for f in result['faults'] if f['code'] == 'invalid_field']), 1)


class EscapeTextTests(unittest.TestCase):
    def test_controls_format_characters_and_line_separators_never_pass_through(self):
        from intune_iac.orchestration_contract import escape_text
        hostile = 'a\x1b[2Jb\x9bc\x07d\ne\tf\x7fg\u202eh\u2028i\u200bj\ud800k'
        out = escape_text(hostile)
        self.assertTrue(out.isprintable(), repr(out))
        for raw in ('\x1b', '\x9b', '\x07', '\n', '\t', '\x7f', '\u202e', '\u2028', '\u200b', '\ud800'):
            self.assertNotIn(raw, out)
        self.assertIn('\\x1b[2J', out)

    def test_ordinary_text_is_unchanged_long_text_is_cut_and_the_function_is_idempotent(self):
        from intune_iac.orchestration_contract import escape_text
        self.assertEqual(escape_text('route offline (fake): cannot start; caf\u00e9'), 'route offline (fake): cannot start; caf\u00e9')
        self.assertEqual(escape_text('x' * 300, limit=10), 'x' * 10 + '...')
        once = escape_text('\x1b[0m C:\\path')
        self.assertEqual(escape_text(once), once)
        self.assertEqual(escape_text(None), '')
        self.assertEqual(escape_text(12), '12')


if __name__ == '__main__':
    unittest.main()
