"""Source framing, index completeness, and failed extraction publication contracts."""
from contextlib import redirect_stdout
import csv
from email.message import EmailMessage
import io
import json
import mailbox
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from property_timeline import gmail_archive as gmail
from property_timeline import archive_inventory as inventory
from property_timeline.combine_timeline import parse_archive, compact_record
from property_timeline.immutable_assets import publish_asset


class EnhancementPipelineTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / 'fixture.mbox'
        self.archive = self.root / 'property_emails_compact.md'
        self.index = self.root / 'property_email_source_index.csv'
        quiet = redirect_stdout(io.StringIO())
        quiet.__enter__()
        self.addCleanup(quiet.__exit__, None, None, None)

    def source_message(self, body='Fixture body.', attachment=b'old terms'):
        self.source.unlink(missing_ok=True)
        message = EmailMessage()
        message['Date'] = 'Fri, 01 May 2026 16:00:00 +0000'
        message['Subject'] = 'Fixture correspondence'
        message['From'], message['To'] = 'Author <author@example.com>', 'Reader <reader@example.com>'
        message['Message-ID'] = '<fixture@example.com>'
        message.set_content(body)
        message.add_attachment(attachment, maintype='text', subtype='plain', filename='terms.txt')
        box = mailbox.mbox(self.source)
        box.add(message)
        box.flush()
        box.close()

    def extract(self):
        with patch.object(sys, 'argv', ['gmail', str(self.source), '--output', str(self.archive), '--index', str(self.index)]):
            gmail.main()

    def records(self):
        return parse_archive(self.archive, 'gmail', ZoneInfo('America/New_York'))[0]

    def test_mbox_body_delimiters_never_create_source_records(self):
        body = ('Pasted example:\n\n## Email 002: Pasted entry\n\n'
                'Date: Fri, 1 May 2026 17:00:00 +0000\nFrom: Example <example@example.com>\n'
                'To: Reader <reader@example.com>\n\nPasted body.\n\n'
                '## Email 003 — 2026-05-01 18:00 UTC\n'
                '**From:** Pasted\n\n```\n---\n```\n')
        self.source_message(body)
        self.extract()
        records = self.records()
        rows = inventory.validate_index(self.archive, 'gmail', records)
        self.assertEqual(len(records), 1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[1]['message_id'], '<fixture@example.com>')
        self.assertIn('## Email 002: Pasted entry', compact_record(records[0], rows[1]))
        self.assertIn('## Email 003 —', compact_record(records[0], rows[1]))
        self.assertIn('```\n---\n```', records[0]['text'])

    def test_failed_extraction_never_changes_previously_referenced_assets(self):
        self.source_message()
        self.extract()
        rows = inventory.validate_index(self.archive, 'gmail', self.records())
        asset = self.archive.parent / json.loads(rows[1]['attachment_files_json'])[0]['relative_path']
        protected = {path: path.read_bytes() for path in [self.archive, self.index, inventory.provenance_path(self.archive), asset]}
        self.source_message(attachment=b'new terms')
        with patch.object(gmail, 'clean_body', side_effect=ValueError('Injected cleanup failure')):
            with self.assertRaisesRegex(ValueError, 'Injected'):
                self.extract()
        for path, contents in protected.items():
            self.assertEqual(path.read_bytes(), contents)
        self.extract()
        new_rows = inventory.validate_index(self.archive, 'gmail', self.records())
        new_asset = self.archive.parent / json.loads(new_rows[1]['attachment_files_json'])[0]['relative_path']
        self.assertNotEqual(asset, new_asset)
        self.assertEqual(asset.read_bytes(), b'old terms')
        self.assertEqual(new_asset.read_bytes(), b'new terms')

    def test_index_coverage_schema_and_generation_mismatches_fail(self):
        self.source_message()
        self.extract()
        records = self.records()
        original = self.index.read_bytes()
        with self.index.open(encoding='utf-8-sig', newline='') as stream:
            rows = list(csv.DictReader(stream))
        cases = [[], [rows[0], rows[0]], [{**rows[0], 'source_email_number': '2'}],
                 [{**rows[0], 'attachment_files_json': '{}'}],
                 [{**rows[0], 'attachment_files_json': '[1]'}]]
        for malformed in cases:
            with self.subTest(rows=malformed):
                with self.index.open('w', encoding='utf-8-sig', newline='') as stream:
                    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                    writer.writeheader()
                    writer.writerows(malformed)
                with self.assertRaises(ValueError):
                    inventory.validate_index(self.archive, 'gmail', records)
        self.index.write_bytes(original)
        self.archive.write_text(self.archive.read_text(encoding='utf-8') + '\nCurated note.\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'generation mismatch'):
            inventory.validate_index(self.archive, 'gmail', self.records())

    def test_binding_curated_legacy_archive_does_not_renumber_or_change_logical_text(self):
        self.archive.write_text('# Curated\nEmails represented: 1\n\n'
            '## Email 001 — 2026-05-01 16:00 UTC\n**From:** Author\n**To:** Reader\n\nCurated text.\n', encoding='utf-8')
        self.index.write_text('source_email_number,attachment_files_json\n1,[]\n', encoding='utf-8')
        old = [(r['id'], r['text']) for r in self.records()]
        with patch.object(sys, 'argv', ['inventory', 'bind', str(self.archive), '--origin', 'gmail', '--frame']):
            inventory.main()
        self.assertEqual(old, [(r['id'], r['text']) for r in self.records()])
        inventory.validate_index(self.archive, 'gmail', self.records())
        self.archive.write_text(self.archive.read_text(encoding='utf-8').replace('Curated text.', 'Intentional edit.'), encoding='utf-8')
        with patch.object(sys, 'argv', ['inventory', 'bind', str(self.archive), '--origin', 'gmail']):
            inventory.main()
        inventory.validate_index(self.archive, 'gmail', self.records())

    def test_immutable_assets_reuse_bytes_and_reject_collisions(self):
        first = publish_asset(self.root / 'assets', 'fixture.txt', b'unchanged')
        self.assertEqual(first, publish_asset(self.root / 'assets', 'fixture.txt', b'unchanged'))
        with self.assertRaisesRegex(ValueError, 'collides'):
            publish_asset(self.root / 'assets', 'fixture.txt', b'unchanged', [first])
        first.write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'differs'):
            publish_asset(self.root / 'assets', 'fixture.txt', b'unchanged')

    def test_recovery_updates_framing_and_generation_without_losing_curated_text(self):
        from property_timeline.archive_format import MARKER, frame_body
        from property_timeline.recover_email_quotes import recover
        self.source_message('Reply\nGarrett E. Lawton | Attorney\nSignature\n'
                            'On Tue, Jul 7, 2026 at 1:29 PM Seller <seller@example.com>\n'
                            'wrote:\n\nSeller accepted option 2.\n```\nExample fence.\n```')
        self.extract()
        self.archive.write_text(MARKER + '\nEmails represented: 1\n\n'
            '## Email 001 — 2026-05-01 16:00 UTC\n**From:** Author\n**To:** Reader\n\n' +
            frame_body('Curated reply.') + '\n', encoding='utf-8')
        with patch.object(sys, 'argv', ['inventory', 'bind', str(self.archive), '--origin', 'gmail']):
            inventory.main()
        manifest = self.root / 'recovery.json'
        self.assertEqual(len(recover(self.source, self.archive, self.index, manifest)), 1)
        records = self.records()
        self.assertEqual(len(records), 1)
        self.assertIn('Curated reply.', records[0]['text'])
        self.assertIn('Seller accepted option 2.', records[0]['text'])
        self.assertIn('```\nExample fence.\n```', records[0]['text'])
        inventory.validate_index(self.archive, 'gmail', records)
        before = self.archive.read_bytes(), self.index.read_bytes(), manifest.read_bytes()
        self.assertEqual(recover(self.source, self.archive, self.index, manifest), [])
        self.assertEqual(before, (self.archive.read_bytes(), self.index.read_bytes(), manifest.read_bytes()))

    def test_iphone_failed_rerun_preserves_previous_images(self):
        try:
            import pymupdf as fitz
            from PIL import Image
            from property_timeline import iphone_pdf_to_markdown as iphone
        except ImportError:
            self.skipTest('PyMuPDF/Pillow unavailable')
        source = self.root / 'iphone_fixture.pdf'
        archive = self.root / 'iphone_fixture_messages.md'
        def pdf(color):
            image = self.root / 'photo.png'
            Image.new('RGB', (400, 400), color).save(image)
            document = fitz.open()
            page = document.new_page()
            page.insert_text((60, 60), 'May 1, 2026 at 10:00 AM')
            page.insert_image(fitz.Rect(60, 120, 260, 320), filename=str(image))
            source.unlink(missing_ok=True)
            document.save(source)
            document.close()
        def extract():
            with patch.object(sys, 'argv', ['iphone', str(source), '--me', 'Fixture']):
                iphone.main()
        pdf('red')
        extract()
        files = {path: path.read_bytes() for path in self.root.rglob('*') if path.is_file()
                 and path not in (source, self.root / 'photo.png')}
        pdf('blue')
        with patch.object(iphone, 'message_body', side_effect=ValueError('Injected image failure')):
            with self.assertRaisesRegex(ValueError, 'Injected'):
                extract()
        for path, contents in files.items():
            self.assertEqual(path.read_bytes(), contents)
