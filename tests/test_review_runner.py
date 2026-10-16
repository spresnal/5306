"""Review persistence, coverage, and Codex isolation without inference calls."""
import argparse
from contextlib import redirect_stdout
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from property_timeline.combine_timeline import parse_archive
from property_timeline import review_runner as runner


def assessment(identifier, text='The basement leaked.'):
    return {'id': identifier, 'priority': 'high', 'topics': ['property_condition'],
            'summary': 'A reported leak.', 'relevance': 'Condition mentioned in the case brief.',
            'assertion': 'A leak was reported.', 'stance': 'context',
            'quotes': [{'source_id': identifier, 'text': text}], 'related_ids': [],
            'uncertainty': 'Knowledge and timing require review.', 'questions': ['Who knew?']}


class ReviewRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        rows = []
        for origin, filename, index_name, number_key in [
            ('gmail', 'property_emails_compact.md', 'property_email_source_index.csv', 'source_email_number'),
            ('android', 'android_darcy_group_messages.md', 'android_darcy_group_index.csv', 'message_number'),
            ('iphone', 'iphone_darcy_messages.md', 'iphone_darcy_index.csv', 'message_number')]:
            directory = self.root / 'data/archives' / origin
            directory.mkdir(parents=True)
            count = 21 if origin == 'gmail' else 1
            kind = 'Email' if origin == 'gmail' else 'Message'
            zone = ' UTC' if origin == 'gmail' else ''
            path = directory / filename
            path.write_text('# Fixture\n\n' + '\n\n'.join(
                f'## {kind} {number:04d} — 2026-01-01 12:{number:02d}{zone}\n'
                '**From:** Fixture\n\nThe basement leaked.' for number in range(1, count + 1)), encoding='utf-8')
            with (directory / index_name).open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=[number_key, 'attachment_files_json'])
                writer.writeheader()
                for number in range(1, count + 1):
                    writer.writerow({number_key: number, 'attachment_files_json': '[]'})
            records, _ = parse_archive(path, origin, ZoneInfo('America/New_York'))
            rows.extend({'reference_id': r['id'], 'origin': origin, 'datetime_eastern': r['displayed'],
                         'archive_file': '../' + str(path.relative_to(self.root)),
                         'archive_line_start': r['line_start'], 'archive_line_end': r['line_end']} for r in records)
        (self.root / 'output').mkdir()
        with (self.root / 'output/master_timeline.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        folder = self.root / 'data/reviews'
        folder.mkdir()
        (folder / 'case_brief.md').write_text('Review status: READY\nInvestigate reported basement leaks.', encoding='utf-8')
        self.args = argparse.Namespace(model='fixture-model', pilot=20, unattended=False, approve_pilot=False,
            max_batches=None, batch_size=7, attachment_chars=1000, max_chars=30000,
            retries=0, codex_bin='codex', codex_timeout=900, max_cross_calls=None)
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {'OPENAI_API_KEY': 'fixture-key', 'CODEX_API_KEY': 'fixture-key'}).start()
        quiet = redirect_stdout(io.StringIO())
        quiet.__enter__()
        self.addCleanup(quiet.__exit__, None, None, None)

    def work(self):
        work = runner.Workspace(self.root)
        work.load()
        return work

    def fake_model(self, model, instructions, payload, schema, executable, timeout):
        if schema == runner.CROSS_SCHEMA:
            return {'findings': []}, {'total_tokens': 1}
        return {'entries': [assessment(r['id']) for r in payload['entries']]}, {'total_tokens': 1}

    def test_loads_additional_iphone_conversation_with_its_own_index(self):
        directory = self.root / 'data/archives/iphone'
        path = directory / 'iphone_derrick_messages.md'
        path.write_text('# Derrick\n\n## Message 0001 — 2026-01-01 12:02\n'
                        '**From:** Derrick\n**To:** Regina\n\nDerrick evidence.', encoding='utf-8')
        (directory / 'iphone_derrick_index.csv').write_text(
            'message_number,attachment_files_json,sender\n1,[],Derrick\n', encoding='utf-8')
        record = parse_archive(path, 'iphone', ZoneInfo('America/New_York'))[0][0]
        timeline = self.root / 'output/master_timeline.csv'
        with timeline.open(newline='') as stream:
            rows = list(csv.DictReader(stream))
        rows.append(dict(reference_id=record['id'], origin='iphone', datetime_eastern=record['displayed'],
                         archive_file='../data/archives/iphone/' + path.name,
                         archive_line_start=record['line_start'], archive_line_end=record['line_end']))
        with timeline.open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        work = self.work()
        self.assertEqual(work.coverage()['total'], 24)
        derrick = next(r for r in work.records if r['id'] == 'iphone_derrick:0001')
        self.assertIn('Derrick evidence.', derrick['text'])
        self.assertEqual(derrick['review_hash'], runner.evidence_hash(
            record['text'], {'message_number': '1', 'attachment_files_json': '[]', 'sender': 'Derrick'}, directory))

    def test_pilot_resume_complete_and_sources_unchanged(self):
        inputs = {p: p.read_bytes() for p in (self.root / 'data/archives').rglob('*') if p.is_file()}
        inputs[self.root / 'output/master_timeline.csv'] = (self.root / 'output/master_timeline.csv').read_bytes()
        with patch.object(runner, 'model_request', side_effect=self.fake_model) as model:
            runner.run(self.work(), self.args)
            self.assertEqual(self.work().coverage()['reviewed'], 20)
            before = model.call_count
            runner.run(self.work(), self.args)
            self.assertEqual(model.call_count, before)
            self.args.pilot = None
            with self.assertRaisesRegex(ValueError, 'Inspect the pilot'):
                runner.run(self.work(), self.args)
            self.args.approve_pilot = True
            runner.run(self.work(), self.args)
            work = self.work()
            self.assertEqual(work.coverage()['reviewed'], 23)
            self.assertEqual(work.state['cross_complete_snapshot'], work.snapshot())
            before = model.call_count
            runner.run(self.work(), self.args)
            self.assertEqual(model.call_count, before)
        for path, original in inputs.items():
            self.assertEqual(path.read_bytes(), original)

    def test_rejects_missing_duplicate_and_fabricated_quotes(self):
        batch = [{'id': 'gmail:0001', 'evidence': {'gmail:0001': 'The basement leaked.'}}]
        for entries in ([], [assessment('gmail:0001')] * 2,
                        [assessment('gmail:0001', 'The seller admitted fraud.')]):
            with self.subTest(entries=entries), self.assertRaises(ValueError):
                runner.validate_entries({'entries': entries}, batch)
        valid = assessment('gmail:0001')
        valid['related_ids'] = ['gmail:9999']
        with self.assertRaisesRegex(ValueError, 'Related ID'):
            runner.validate_entries({'entries': [valid]}, batch)

    def test_unattended_completes_without_pilot_and_resumes_without_repeating(self):
        self.args.pilot = None
        self.args.unattended = True
        with patch.object(runner, 'model_request', side_effect=self.fake_model) as model:
            runner.run(self.work(), self.args)
            work = self.work()
            self.assertEqual(work.coverage()['reviewed'], 23)
            self.assertTrue(work.coverage()['cross_review_complete'])
            self.assertIsNone(work.state['pilot_approved'])
            before = model.call_count
            runner.run(self.work(), self.args)
            self.assertEqual(model.call_count, before)

    def test_failed_batch_preserves_completed_and_retries_on_resume(self):
        self.args.max_batches = 1
        with patch.object(runner, 'model_request', side_effect=self.fake_model):
            runner.run(self.work(), self.args)
        self.assertEqual(self.work().coverage()['reviewed'], 7)
        with patch.object(runner, 'model_request', return_value=({'entries': []}, {})):
            runner.run(self.work(), self.args)
        work = self.work()
        self.assertEqual(work.coverage()['reviewed'], 7)
        self.assertEqual(work.coverage()['failed'], 7)
        with patch.object(runner, 'model_request', side_effect=self.fake_model):
            runner.run(work, self.args)
        self.assertEqual(self.work().coverage()['reviewed'], 14)
        self.assertEqual(self.work().coverage()['failed'], 0)

    def test_rejected_quotes_are_skipped_and_later_batches_continue(self):
        self.args.pilot = None
        self.args.unattended = True
        self.args.retries = 1
        rejected = []
        def model(*args):
            result, usage = self.fake_model(*args)
            if args[3] == runner.SCHEMA and args[2]['entries'][0]['id'] == 'gmail:0001':
                rejected.append(True)
                result['entries'][0]['quotes'][0]['text'] = 'Invented words.'
            return result, usage
        inputs = {p: p.read_bytes() for p in (self.root / 'data/archives').rglob('*') if p.is_file()}
        with patch.object(runner, 'model_request', side_effect=model), patch.object(runner.time, 'sleep'):
            runner.run(self.work(), self.args)
        work = self.work()
        self.assertEqual(len(rejected), 2)
        self.assertEqual(work.coverage()['reviewed'], 22)
        self.assertEqual(work.coverage()['remaining'], 1)
        self.assertEqual(work.coverage()['failed'], 1)
        self.assertEqual(work.coverage()['manual_review'], 1)
        self.assertFalse(work.coverage()['cross_review_complete'])
        self.assertNotIn('gmail:0001', work.state['assessments'])
        self.assertEqual(work.state['failures']['gmail:0001']['kind'], 'validation')
        self.assertTrue(work.state['failures']['gmail:0001']['manual_review'])
        progress = json.loads((self.root / 'data/reviews/review_progress.json').read_text())
        self.assertEqual(progress['manual_review_ids'], ['gmail:0001'])
        self.assertIn('Quotation does not match supplied evidence',
                      (self.root / 'output/counsel_review.md').read_text())
        for p, original in inputs.items():
            self.assertEqual(p.read_bytes(), original)
        with patch.object(runner, 'model_request', side_effect=self.fake_model) as request:
            runner.run(self.work(), self.args)
            request.assert_not_called()
        self.args.retry_manual_review = True
        with patch.object(runner, 'model_request', side_effect=self.fake_model):
            runner.run(self.work(), self.args)
        self.assertEqual(self.work().coverage()['failed'], 0)
        self.assertTrue(self.work().coverage()['cross_review_complete'])

    def test_entry_validation_attributes_multiple_failures_and_keeps_valid_entries(self):
        work = self.work()
        batch = [work.prepare(record, 1000) for record in work.records[:3]]
        entries = [assessment(item['id']) for item in batch]
        entries[0]['quotes'][0]['text'] = 'Invented words.'
        entries[1]['priority'] = 'invalid category'
        with self.assertRaises(runner.EntryValidationError) as caught:
            runner.validate_entries({'entries': entries}, batch)
        self.assertEqual(set(caught.exception.failures), {'gmail:0001', 'gmail:0002'})
        self.assertEqual([entry['id'] for entry in caught.exception.result['entries']], ['gmail:0003'])

    def test_second_pass_can_exclude_manual_entries_and_resume_full_scope_later(self):
        self.args.pilot = None
        self.args.unattended = True
        self.args.skip_manual_review = True
        seen = set()
        def partial_model(*args):
            result, usage = self.fake_model(*args)
            if args[3] == runner.SCHEMA:
                for entry in result['entries']:
                    if entry['id'] == 'gmail:0001':
                        entry['quotes'][0]['text'] = 'Invented quotation.'
            else:
                seen.update(entry['id'] for entry in args[2]['entries'])
            return result, usage
        with patch.object(runner, 'model_request', side_effect=partial_model):
            runner.run(self.work(), self.args)
        work = self.work()
        self.assertEqual(work.coverage()['remaining'], 1)
        self.assertEqual(work.coverage()['cross_entries_excluded'], 1)
        self.assertTrue(work.coverage()['cross_review_complete_for_scope'])
        self.assertFalse(work.coverage()['cross_review_complete'])
        self.assertEqual(work.contextual_review()['excluded_ids'], ['gmail:0001'])
        self.assertEqual(seen, {r['id'] for r in work.records} - {'gmail:0001'})
        self.assertIn('1 manual-review entries excluded', (self.root / 'output/counsel_review.md').read_text())
        snapshot = work.snapshot()
        with patch.object(runner, 'model_request') as request:
            runner.run(self.work(), self.args)
            request.assert_not_called()
        self.args.skip_manual_review = False
        self.args.retry_manual_review = True
        with patch.object(runner, 'model_request', side_effect=self.fake_model):
            runner.run(self.work(), self.args)
        work = self.work()
        self.assertNotEqual(snapshot, work.snapshot())
        self.assertEqual(work.coverage()['cross_entries_excluded'], 0)
        self.assertTrue(work.coverage()['cross_review_complete'])

    def test_manual_review_flag_is_invalidated_by_changed_evidence_or_criteria(self):
        work = self.work()
        record = work.records[0]
        work.state['failures'][record['id']] = {
            'manual_review': True, 'review_hash': record['review_hash'], 'criteria_hash': work.criteria_hash}
        self.assertTrue(work.manual_review(record))
        self.assertFalse(work.manual_review({**record, 'review_hash': 'changed'}))
        work.criteria_hash = 'changed'
        self.assertFalse(work.manual_review(record))

    def test_codex_error_still_stops_run(self):
        with patch.object(runner, 'model_request', side_effect=runner.CodexError('Codex plan usage limit reached')):
            with self.assertRaisesRegex(ValueError, 'plan usage limit'):
                runner.run(self.work(), self.args)
        self.assertEqual(self.work().coverage()['reviewed'], 0)

    def test_cross_validation_failure_stays_pending_then_resumes(self):
        self.args.pilot = None
        self.args.unattended = True
        rejected = []
        def model(*args):
            if args[3] == runner.CROSS_SCHEMA and not rejected:
                rejected.append(True)
                return {'findings': [{'bad': 'shape'}]}, {}
            return self.fake_model(*args)
        with patch.object(runner, 'model_request', side_effect=model):
            runner.run(self.work(), self.args)
        work = self.work()
        self.assertEqual(work.coverage()['remaining'], 0)
        self.assertEqual(work.coverage()['cross_tasks_failed'], 1)
        self.assertFalse(work.coverage()['cross_review_complete'])
        self.assertIn('Failed cross-entry comparisons', (self.root / 'output/counsel_review.md').read_text())
        with patch.object(runner, 'model_request', side_effect=self.fake_model):
            runner.run(self.work(), self.args)
        self.assertEqual(self.work().coverage()['cross_tasks_failed'], 0)
        self.assertTrue(self.work().coverage()['cross_review_complete'])

    def test_skip_flag_bypasses_previous_cross_failures_and_later_tasks_continue(self):
        self.args.pilot = 23
        self.args.max_chars = 10000
        with patch.object(runner, 'model_request', side_effect=self.fake_model):
            runner.run(self.work(), self.args)
        self.args.pilot = None
        self.args.unattended = True
        with patch.object(runner, 'model_request', side_effect=runner.CodexError('Fixture execution error', category='task')):
            with self.assertRaisesRegex(ValueError, 'Fixture execution error'):
                runner.run(self.work(), self.args)
        previous = self.work()
        failure_key = next(iter(previous.state['cross_failures']))
        self.args.skip_manual_review = True
        with patch.object(runner, 'model_request', side_effect=self.fake_model) as request:
            runner.run(self.work(), self.args)
        work = self.work()
        self.assertGreater(request.call_count, 0)
        self.assertTrue(work.state['cross_failures'][failure_key]['skipped'])
        self.assertEqual(work.coverage()['cross_tasks_skipped'], 1)
        self.assertEqual(work.coverage()['cross_tasks_completed'] + 1, work.coverage()['cross_tasks_total'])
        self.assertFalse(work.coverage()['cross_review_complete_for_scope'])
        self.assertIn('Skipped for manual review', (self.root / 'output/counsel_review.md').read_text())
        with patch.object(runner, 'model_request') as request:
            runner.run(self.work(), self.args)
            request.assert_not_called()
        self.args.skip_manual_review = False
        with patch.object(runner, 'model_request', side_effect=self.fake_model) as request:
            runner.run(self.work(), self.args)
            self.assertEqual(request.call_count, 1)
        self.assertTrue(self.work().coverage()['cross_review_complete'])

    def test_skip_flag_records_new_cross_execution_errors_and_continues(self):
        self.args.pilot = None
        self.args.unattended = True
        self.args.skip_manual_review = True
        self.args.max_chars = 10000
        failures = []
        def model(*args):
            if args[3] == runner.CROSS_SCHEMA and not failures:
                failures.append(True)
                raise runner.CodexError('Fixture cross execution failure', category='task')
            return self.fake_model(*args)
        with patch.object(runner, 'model_request', side_effect=model):
            runner.run(self.work(), self.args)
        work = self.work()
        self.assertEqual(work.coverage()['cross_tasks_skipped'], 1)
        self.assertGreater(work.coverage()['cross_tasks_completed'], 0)
        self.assertFalse(work.coverage()['cross_review_complete_for_scope'])
        with patch.object(runner, 'model_request') as request:
            runner.run(self.work(), self.args)
            request.assert_not_called()

    def test_brief_and_source_changes_mark_stale(self):
        with patch.object(runner, 'model_request', side_effect=self.fake_model):
            runner.run(self.work(), self.args)
        path = self.root / 'data/archives/gmail/property_emails_compact.md'
        path.write_text(path.read_text().replace('The basement leaked.', 'The basement flooded.', 1))
        self.assertEqual(self.work().coverage()['stale'], 1)
        brief = self.root / 'data/reviews/case_brief.md'
        brief.write_text(brief.read_text() + '\nNew dispute criteria.')
        self.assertEqual(self.work().coverage()['stale'], 20)

    def test_instruction_changes_mark_stale(self):
        with patch.object(runner, 'model_request', side_effect=self.fake_model):
            runner.run(self.work(), self.args)
        (self.root / 'data/reviews/REVIEW_INSTRUCTIONS.md').write_text(runner.INSTRUCTIONS + '\nAdditional criteria.')
        self.assertEqual(self.work().coverage()['stale'], 20)

    def test_stale_csv_and_omitted_entries_rejected(self):
        path = self.root / 'output/master_timeline.csv'
        content = path.read_text()
        with path.open(newline='') as stream:
            rows = list(csv.DictReader(stream))
        rows[0]['archive_line_start'] = '999'
        with path.open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        with self.assertRaisesRegex(ValueError, 'CSV is stale'):
            self.work()
        # Remove one entry without modifying source archives.
        path.write_text('\n'.join(content.splitlines()[:-1]) + '\n')
        with self.assertRaisesRegex(ValueError, 'omits archive entries'):
            self.work()

    def test_impossible_prompt_budget_stops_without_flagging_entries(self):
        self.args.max_chars = 1
        with patch.object(runner, 'model_request') as model:
            with self.assertRaisesRegex(ValueError, 'too small for the case brief'):
                runner.run(self.work(), self.args)
            model.assert_not_called()
        self.assertEqual(self.work().coverage()['manual_review'], 0)

    def test_oversized_entry_is_flagged_and_later_entries_continue(self):
        self.args.pilot = None
        self.args.unattended = True
        path = self.root / 'data/archives/gmail/property_emails_compact.md'
        path.write_text(path.read_text().replace('The basement leaked.',
                        'The basement leaked. ' + 'Oversized evidence. ' * 4000, 1))
        work = self.work()
        original = path.read_bytes()
        with patch.object(runner, 'model_request', side_effect=self.fake_model) as model:
            runner.run(work, self.args)
        refreshed = self.work()
        self.assertEqual(refreshed.coverage()['reviewed'], 22)
        self.assertEqual(refreshed.coverage()['manual_review'], 1)
        failure = refreshed.state['failures']['gmail:0001']
        self.assertEqual(failure['kind'], 'oversized')
        self.assertGreater(failure['required_chars'], self.args.max_chars)
        self.assertFalse(refreshed.coverage()['cross_review_complete'])
        self.assertEqual(path.read_bytes(), original)
        for call in model.call_args_list:
            self.assertNotIn('gmail:0001', [item['id'] for item in call.args[2]['entries']])
        with patch.object(runner, 'model_request') as model:
            runner.run(refreshed, self.args)
            model.assert_not_called()
        self.args.retry_manual_review = True
        self.args.max_chars = 300000
        with patch.object(runner, 'model_request', side_effect=self.fake_model):
            runner.run(self.work(), self.args)
        self.assertEqual(self.work().coverage()['manual_review'], 0)
        self.assertTrue(self.work().coverage()['cross_review_complete'])

    def test_draft_fails_before_codex(self):
        brief = self.root / 'data/reviews/case_brief.md'
        brief.write_text(runner.BRIEF)
        with patch.object(runner, 'model_request') as model:
            with self.assertRaisesRegex(ValueError, 'READY'):
                runner.run(self.work(), self.args)
            model.assert_not_called()

    def test_lock_and_output_symlinks_rejected(self):
        work = self.work()
        with work.lock():
            with self.assertRaisesRegex(ValueError, 'already locked'):
                with self.work().lock():
                    pass
        target = self.root / 'data/archives/gmail/property_emails_compact.md'
        report = self.root / 'output/counsel_review.md'
        try:
            report.symlink_to(target)
        except OSError:
            self.skipTest('Symlinks unavailable')
        original = target.read_bytes()
        with self.assertRaisesRegex(ValueError, 'redirect'):
            runner.report(work)
        self.assertEqual(target.read_bytes(), original)

    def test_attachment_text_truncation_and_hash_mismatch(self):
        work = self.work()
        record = work.records[0]
        path = self.root / 'data/archives/gmail/document.txt'
        path.write_text('Attachment evidence ' * 100)
        metadata = {'available': True, 'relative_path': 'document.txt',
                    'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'byte_size': path.stat().st_size}
        record['attachments'] = [{'source_id': record['id'] + '/attachment:0001',
                                  'path': path, 'metadata': metadata, 'excluded': False}]
        prepared = work.prepare(record, 10)
        self.assertEqual(len(prepared['attachments'][0]['text']), 10)
        self.assertIn('truncated', prepared['review_gaps'][0])
        path.write_text('changed')
        with self.assertRaisesRegex(ValueError, 'differs'):
            runner.validate_attachment(metadata, path.parent)

    def test_cross_pass_compares_block_boundaries_and_resumes(self):
        self.args.pilot = 23
        with patch.object(runner, 'model_request', side_effect=self.fake_model):
            runner.run(self.work(), self.args)
        self.args.pilot = None
        self.args.approve_pilot = True
        self.args.max_chars = 10000
        self.args.max_cross_calls = 2
        supplied = []
        def fake(model, instructions, payload, schema, executable, timeout):
            supplied.append({r['id'] for r in payload['entries']})
            return self.fake_model(model, instructions, payload, schema, executable, timeout)
        with patch.object(runner, 'model_request', side_effect=fake):
            runner.run(self.work(), self.args)
            self.assertFalse(self.work().coverage()['cross_review_complete'])
            self.args.max_cross_calls = None
            runner.run(self.work(), self.args)
        self.assertTrue(self.work().coverage()['cross_review_complete'])
        ids = {r['id'] for r in self.work().records}
        for first in ids:
            for second in ids:
                self.assertTrue(any({first, second} <= block for block in supplied))
        self.assertEqual(len(supplied), len({frozenset(block) for block in supplied}))

    def test_cross_findings_citations_and_stale_report(self):
        self.args.pilot = 23
        with patch.object(runner, 'model_request', side_effect=self.fake_model):
            runner.run(self.work(), self.args)
        self.args.pilot = None
        self.args.approve_pilot = True
        finding = {'title': 'Multiple reports', 'analysis': 'Two entries mention a leak; timing needs review.',
                   'kind': 'context', 'entry_ids': ['gmail:0001', 'gmail:0002'],
                   'quotes': [{'source_id': 'gmail:0001', 'text': 'The basement leaked.'},
                              {'source_id': 'gmail:0002', 'text': 'The basement leaked.'}],
                   'questions': ['Same incident?'], 'contextual_priority': 'high'}
        invalid = {**finding, 'quotes': [{'source_id': 'gmail:0001', 'text': 'Invented quotation.'}]}
        with patch.object(runner, 'model_request', return_value=({'findings': [invalid]}, {})):
            runner.run(self.work(), self.args)
        self.assertFalse(self.work().coverage()['cross_review_complete'])
        self.assertIn('Cross quotation', (self.root / 'output/counsel_review.md').read_text())
        with patch.object(runner, 'model_request', return_value=({'findings': [finding]}, {})):
            runner.run(self.work(), self.args)
        report = self.root / 'output/counsel_review.md'
        self.assertIn('Multiple reports', report.read_text())
        path = self.root / 'data/archives/gmail/property_emails_compact.md'
        path.write_text(path.read_text().replace('The basement leaked.', 'The basement flooded.', 1))
        runner.report(self.work())
        self.assertNotIn('Multiple reports', report.read_text())

    def test_cross_pass_reads_unselected_evidence_across_topics_and_promotes_context(self):
        self.args.pilot = None
        self.args.unattended = True
        seen_ids = set()
        def fake(model, instructions, payload, schema, executable, timeout):
            if schema == runner.SCHEMA:
                entries = [assessment(item['id']) for item in payload['entries']]
                for item in entries:
                    item['priority'] = 'low'
                    item['topics'] = ['routine'] if item['id'] != 'gmail:0002' else ['inspection']
                return {'entries': entries}, {}
            seen_ids.update(item['id'] for item in payload['entries'])
            by_id = {item['id']: item for item in payload['entries']}
            if not {'gmail:0001', 'gmail:0002'} <= set(by_id):
                return {'findings': []}, {}
            self.assertIn('**From:** Fixture', by_id['gmail:0001']['evidence']['gmail:0001'])
            return {'findings': [{'title': 'Context changes importance', 'analysis': 'Review these entries together.',
                'kind': 'context', 'entry_ids': ['gmail:0001', 'gmail:0002'], 'contextual_priority': 'high',
                'quotes': [{'source_id': id, 'text': '**From:** Fixture'} for id in ('gmail:0001', 'gmail:0002')],
                'questions': ['Does this context affect the claim?']}]}, {}
        with patch.object(runner, 'model_request', side_effect=fake):
            runner.run(self.work(), self.args)
        work = self.work()
        self.assertEqual(seen_ids, {record['id'] for record in work.records})
        self.assertEqual(work.state['assessments']['gmail:0001']['priority'], 'low')
        context = work.state['contextual_review']
        self.assertTrue(context['complete'])
        self.assertEqual(context['findings'][0]['contextual_priority'], 'high')
        self.assertEqual(set(context['entry_hashes']), seen_ids)
        self.assertIn('effective priority: high; first pass: low', (self.root / 'output/counsel_review.md').read_text())

    def test_cross_evidence_parts_keep_all_attachment_text(self):
        work = self.work()
        work.state['assessments'] = {r['id']: assessment(r['id']) for r in work.records}
        record = work.records[0]
        path = self.root / 'data/archives/gmail/large.txt'
        text = 'First section\n' + 'Long attachment evidence.\n' * 1000 + 'Last section.'
        path.write_text(text, encoding='utf-8', newline='')
        record['attachments'] = [{'source_id': record['id'] + '/attachment:0001', 'path': path,
            'metadata': {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'original_filename': 'large.txt'},
            'excluded': False}]
        units = runner.cross_evidence_units(work, 1500)
        sections = [unit['evidence'][record['id'] + '/attachment:0001'] for unit in units
                    if record['id'] + '/attachment:0001' in unit['evidence']]
        self.assertGreater(len(sections), 1)
        self.assertIn('Last section.', ''.join(sections))
        self.assertEqual(''.join(sections), 'File text\n' + text)
        self.assertTrue(all(len(json.dumps(unit, ensure_ascii=False)) <= 1500 for unit in units))

    def codex_process(self, command, **kwargs):
        import subprocess
        if 'login' in command:
            return subprocess.CompletedProcess(command, 0, '', 'Logged in using ChatGPT')
        answer_path = Path(command[command.index('--output-last-message') + 1])
        answer_path.write_text('{"entries": []}', encoding='utf-8')
        return subprocess.CompletedProcess(command, 0,
            '{"type":"turn.completed","usage":{"input_tokens":100,"output_tokens":10}}', '')

    def test_codex_uses_chatgpt_isolation_schema_and_stdin(self):
        with patch.object(runner.shutil, 'which', return_value='/fixture/codex'), patch.object(
                runner.subprocess, 'run', side_effect=self.codex_process) as process:
            result, usage = runner.model_request(None, 'Instructions', {'evidence': 'Fixture text'},
                                                 runner.SCHEMA, 'codex', 900)
        self.assertEqual(result, {'entries': []})
        self.assertEqual(usage['input_tokens'], 100)
        command = process.call_args.args[0]
        options = process.call_args.kwargs
        self.assertIn('forced_login_method="chatgpt"', command)
        self.assertIn('features.shell_tool=false', command)
        self.assertIn('--ignore-user-config', command)
        self.assertIn('--ignore-rules', command)
        self.assertIn('--ephemeral', command)
        self.assertEqual(command[command.index('--sandbox') + 1], 'read-only')
        self.assertIn('Fixture text', options['input'])
        self.assertNotIn('Fixture text', ' '.join(command))
        self.assertNotIn('OPENAI_API_KEY', options['env'])
        self.assertNotIn('CODEX_API_KEY', options['env'])
        self.assertNotEqual(Path(options['cwd']), self.root)
        self.assertNotIn('--model', command)

    def test_api_login_is_rejected_without_exposing_key(self):
        import subprocess
        with patch.object(runner.shutil, 'which', return_value='/fixture/codex'), patch.object(
                runner.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '',
                     'Logged in using an API key fixture-secret')) as process:
            with self.assertRaisesRegex(runner.CodexError, 'signed in with ChatGPT') as error:
                runner.model_request(None, '', {}, runner.SCHEMA, 'codex', 900)
        self.assertNotIn('fixture-secret', str(error.exception))
        self.assertEqual(process.call_count, 1)

    def test_codex_missing_timeout_and_invalid_response(self):
        import subprocess
        with patch.object(runner.shutil, 'which', return_value=None):
            with self.assertRaisesRegex(runner.CodexError, 'not found'):
                runner.model_request(None, '', {}, runner.SCHEMA, 'codex', 900)
        def timeout(command, **kwargs):
            if 'login' in command:
                return self.codex_process(command, **kwargs)
            raise subprocess.TimeoutExpired(command, 900)
        with patch.object(runner.shutil, 'which', return_value='/fixture/codex'), patch.object(
                runner.subprocess, 'run', side_effect=timeout):
            with self.assertRaisesRegex(runner.CodexError, 'timed out'):
                runner.model_request(None, '', {}, runner.SCHEMA, 'codex', 900)
        def incomplete(command, **kwargs):
            if 'login' in command:
                return self.codex_process(command, **kwargs)
            return subprocess.CompletedProcess(command, 0, '', '')
        with patch.object(runner.shutil, 'which', return_value='/fixture/codex'), patch.object(
                runner.subprocess, 'run', side_effect=incomplete):
            with self.assertRaisesRegex(runner.CodexError, 'did not complete'):
                runner.model_request(None, '', {}, runner.SCHEMA, 'codex', 900)

    def test_codex_usage_limit_stops_without_automatic_retries(self):
        self.args.retries = 2
        with patch.object(runner, 'model_request', side_effect=runner.CodexError(
                'Codex plan usage limit reached')) as request, patch.object(runner.time, 'sleep') as sleep:
            with self.assertRaisesRegex(ValueError, 'plan usage limit'):
                runner.ask(self.args, '', {}, runner.SCHEMA, lambda result: None)
        self.assertEqual(request.call_count, 1)
        sleep.assert_not_called()


if __name__ == '__main__':
    unittest.main()
