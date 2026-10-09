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
            with self.assertRaises(ValueError):
                runner.run(self.work(), self.args)
        work = self.work()
        self.assertEqual(work.coverage()['reviewed'], 7)
        self.assertEqual(work.coverage()['failed'], 7)
        with patch.object(runner, 'model_request', side_effect=self.fake_model):
            runner.run(work, self.args)
        self.assertEqual(self.work().coverage()['reviewed'], 14)
        self.assertEqual(self.work().coverage()['failed'], 0)

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

    def test_oversized_entry_never_silently_truncated_or_skipped(self):
        self.args.max_chars = 1
        with patch.object(runner, 'model_request') as model:
            with self.assertRaisesRegex(ValueError, 'exceeds --max-chars'):
                runner.run(self.work(), self.args)
            model.assert_not_called()

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
        self.args.max_chars = 6000
        self.args.max_cross_calls = 2
        supplied = []
        def fake(model, instructions, payload, schema, executable, timeout):
            supplied.append({r['id'] for r in payload['assessments']})
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
                   'quotes': [{'source_id': 'gmail:0001', 'text': 'The basement leaked.'}],
                   'questions': ['Same incident?']}
        invalid = {**finding, 'quotes': [{'source_id': 'gmail:0001', 'text': 'Invented quotation.'}]}
        with patch.object(runner, 'model_request', return_value=({'findings': [invalid]}, {})):
            with self.assertRaisesRegex(ValueError, 'Cross quotation'):
                runner.run(self.work(), self.args)
        with patch.object(runner, 'model_request', return_value=({'findings': [finding]}, {})):
            runner.run(self.work(), self.args)
        report = self.root / 'output/counsel_review.md'
        self.assertIn('Multiple reports', report.read_text())
        path = self.root / 'data/archives/gmail/property_emails_compact.md'
        path.write_text(path.read_text().replace('The basement leaked.', 'The basement flooded.', 1))
        runner.report(self.work())
        self.assertNotIn('Multiple reports', report.read_text())

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
