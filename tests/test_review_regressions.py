"""Sanitized fixtures for extraction, preservation, and attachment contracts."""
import csv
import hashlib
import json
import mailbox
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo

from property_timeline.android_html_export import read_export
from property_timeline.android_txt_to_markdown import parse_gilapps_text as parse_text
from property_timeline.combine_timeline import compact_record, parse_archive
from property_timeline.email_parsing import normalized_passage, quoted_headers
from property_timeline.gmail_archive import clean_body, from_mbox
from property_timeline.output_safety import distinct_paths, staged_outputs
from property_timeline.pdf_attachments import collect_files, tokenize_file_links
from property_timeline.recover_email_quotes import recover
from property_timeline.timeline_html import write_html

ROOT = Path(__file__).parent


class ReviewRegressionTests(unittest.TestCase):
    def test_multiline_reply_after_signature_is_retained(self):
        raw = ('New reply\nGarrett E. Lawton | Attorney\nSignature text\n'
               'On Tue, Jul 7, 2026 at 1:29 PM Seller <seller@example.com>\n'
               'wrote:\n\nSeller accepted option 2 at 2%.')
        self.assertIn('Seller accepted option 2 at 2%.', clean_body(raw))
        self.assertNotIn('Signature text', clean_body(raw))

    def test_unindented_prose_is_not_a_header(self):
        fields, _, _, body = quoted_headers('From: Seller <seller@example.com>\n'
                                            'Subject: Title Work\nSeller accepted the change.')
        self.assertEqual(fields['Subject'], 'Title Work')
        self.assertEqual(body, 'Seller accepted the change.')

    def test_folded_recipient_header_is_retained(self):
        fields, _, _, body = quoted_headers('> To: Sam <sam@example.com>,\n'
                                            '>  Regina <regina@example.com>\n> Subject: Offer\n> Body')
        self.assertIn('regina@example.com', fields['To'])
        self.assertEqual(body, '> Body')

    def test_normalization_preserves_changed_terms(self):
        base = 'Option 1: +2%, $30 at https://example.com/1'
        for changed in (base.replace('1:', '2:'), base.replace('+', '-'),
                        base.replace('2%', '1%'), base.replace('/1', '/2')):
            self.assertNotEqual(normalized_passage(base), normalized_passage(changed))
        self.assertEqual(normalized_passage('> Option 1:\n> +2%'), 'Option 1: +2%')

    def test_gmail_import_has_no_cli_side_effects(self):
        result = subprocess.run([sys.executable, '-c', 'import property_timeline.gmail_archive', '--unknown'],
                                cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '')

    def test_unzoned_sorting_uses_reproducible_utc_order(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory, 'dates.mbox')
            box = mailbox.mbox(source)
            for subject, date in (('Aware', 'Fri, 01 May 2026 13:00:00 +0000'),
                                  ('Naive', 'Fri, 01 May 2026 12:00:00')):
                message = EmailMessage()
                message['Subject'], message['Date'] = subject, date
                message.set_content('Date fixture')
                box.add(message)
            box.close()
            output = from_mbox(source)
            self.assertLess(output.index('Naive'), output.index('Aware'))

    def test_forwarded_numeric_change_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            source = directory / 'fixture.mbox'
            box = mailbox.mbox(source)
            for day, option in ((1, 1), (2, 2)):
                message = EmailMessage()
                message['From'] = 'Seller <seller@example.com>'
                message['To'] = 'Buyer <buyer@example.com>'
                message['Date'] = f'Fri, {day:02d} May 2026 12:00:00 +0000'
                message['Message-ID'] = f'<fixture-{day}@example.com>'
                message['Subject'] = 'Offer' if day == 1 else 'Fwd: Offer'
                message.set_content('Terms ' * 100 + f'option {option}, rate {option}%.' )
                box.add(message)
            box.close()
            output = directory / 'emails.md'
            result = subprocess.run([sys.executable, '-m', 'property_timeline.gmail_archive', str(source),
                                     '--output', str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('option 1, rate 1%', output.read_text())
            self.assertIn('option 2, rate 2%', output.read_text())

    def test_staged_failure_preserves_all_existing_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory, 'a.md'), Path(directory, 'b.csv')]
            for path in paths:
                path.write_text('previous valid artifact')
            with self.assertRaises(RuntimeError):
                with staged_outputs(paths) as stages:
                    stages[0].write_text('new artifact')
                    raise RuntimeError('failed validation')
            self.assertTrue(all(path.read_text() == 'previous valid artifact' for path in paths))
            self.assertEqual(set(Path(directory).iterdir()), set(paths))
            with self.assertRaises(ValueError):
                distinct_paths(paths[:1], paths)
            with self.assertRaises(ValueError):
                distinct_paths([], [paths[0], paths[0]])

    def test_android_nested_headers_and_ordinary_link(self):
        html = ('<div class="header_text"><b>Friday, May 01, 2026</b></div>'
                '<div class="chat_box"><div class="res_title"><b>Darcy Real estate</b></div>'
                '<div class="time"><span>10:00 AM</span></div>'
                '<p>See <a href="https://example.com/report"><b>the report</b></a> today.</p></div>')
        with tempfile.TemporaryDirectory() as directory:
            messages, anomalies, files = read_export(html, Path(directory, 'export.html'), parse_text)
            self.assertEqual(len(messages), 1)
            self.assertFalse(anomalies)
            self.assertEqual(files[1], [])
            self.assertEqual(messages[0].body, 'See the report (https://example.com/report) today.')

    def test_attachment_hash_missing_file_and_every_occurrence(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            path = directory / 'document.pdf'
            path.write_bytes(b'original fixture bytes')
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            anchor = (f'<a class="file-link" data-sha256="{digest}" data-byte-size="{path.stat().st_size}" '
                      'href="document.pdf">Document</a>')
            html = '<article id="gmail:0001">' + anchor * 2 + '</article>'
            source, output = directory / 'timeline.html', directory / 'timeline.pdf'
            files = collect_files(html, source)
            self.assertEqual(files[digest]['references'], {'gmail:0001': 2})
            _, targets = tokenize_file_links(html, source, output)
            self.assertEqual(len(targets), 2)
            self.assertTrue(all(target['record'] == 'gmail:0001' for target in targets.values()))
            path.write_bytes(b'modified')
            with self.assertRaisesRegex(ValueError, 'differs'):
                collect_files(html, source)
            path.unlink()
            with self.assertRaisesRegex(ValueError, 'missing'):
                collect_files(html, source)

    def test_iphone_files_reach_html_attachment_pipeline(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            image = directory / 'phone.jpg'
            image.write_bytes(b'fixture image')
            item = dict(relative_path=image.name, original_filename=image.name, content_type='image/jpeg',
                        byte_size=image.stat().st_size, sha256=hashlib.sha256(image.read_bytes()).hexdigest())
            record = dict(id='iphone:0001', origin='iphone', number=1, path=directory / 'iphone.md',
                          utc=datetime(2026, 5, 1, 14, tzinfo=timezone.utc), displayed='2026-05-01 10:00',
                          line_start=1, line_end=6, text='## Message 0001 — 2026-05-01 10:00\n'
                          '**From:** Regina\n**To:** Darcy\n\nSee photo.')
            destination = directory / 'timeline.html'
            write_html([record], {}, 'America/New_York', destination, compact_record,
                       iphone_index={1: dict(attachment_files_json=json.dumps([item]))})
            html = destination.read_text()
            self.assertIn('attachment-thumb', html)
            self.assertEqual(len(collect_files(html, destination)), 1)

    def test_recovery_preserves_curated_text_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            source = directory / 'original.mbox'
            box = mailbox.mbox(source)
            message = EmailMessage()
            message['Message-ID'] = '<original@example.com>'
            message.set_content('Original reply\nGarrett E. Lawton | Attorney\nSignature\n'
                                'On Tue, Jul 7, 2026 at 1:29 PM Seller <seller@example.com>\n'
                                'wrote:\n\nSeller accepted option 2.')
            box.add(message)
            box.close()
            archive, index, manifest = [directory / name for name in ('emails.md', 'index.csv', 'recovery.json')]
            prefix = '## Email 0001 — 2026-07-07 14:00 UTC\n**From:** Buyer\n\nCurated reply.'
            archive.write_text(prefix + '\n', encoding='utf-8')
            with index.open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=['source_email_number', 'message_id', 'representation', 'output_body_chars'])
                writer.writeheader()
                writer.writerow(dict(source_email_number=1, message_id='<original@example.com>', representation='FULL', output_body_chars=14))
            changes = recover(source, archive, index, manifest)
            self.assertEqual(len(changes), 1)
            self.assertTrue(archive.read_text(encoding='utf-8').startswith(prefix))
            self.assertIn('Seller accepted option 2.', archive.read_text(encoding='utf-8'))
            before = archive.read_bytes(), index.read_bytes(), manifest.read_bytes()
            self.assertEqual(recover(source, archive, index, manifest), [])
            self.assertEqual(before, (archive.read_bytes(), index.read_bytes(), manifest.read_bytes()))
            records, _ = parse_archive(archive, 'gmail', ZoneInfo('America/New_York'))
            self.assertEqual([record['id'] for record in records], ['gmail:0001'])
