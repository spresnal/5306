"""AI packages preserve evidence, associations, extraction gaps, and file limits."""
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from property_timeline.ai_export import export_review, extract_text, pack_sections
from property_timeline.combine_timeline import compact_record
from property_timeline.output_safety import staged_outputs


class AIExportTests(unittest.TestCase):
    def fixture(self, root, number, name, data, available=True):
        path = root / name
        if available:
            path.write_bytes(data)
        item = dict(relative_path=name, original_filename=name, available=available,
                    sha256=hashlib.sha256(data).hexdigest(), byte_size=len(data))
        archive = root / 'archive.md'
        archive.write_text('curated archive', encoding='utf-8')
        record = dict(id=f'gmail:{number:04d}', number=number, origin='gmail', path=archive,
                      utc=datetime(2026, 5, 1, 12, number, tzinfo=timezone.utc),
                      displayed='2026-05-01 12:00 UTC',
                      text=f'## Email {number:03d} — 2026-05-01 12:00 UTC\n'
                           '**From:** Seller <seller@example.com>\n**To:** Buyer\n'
                           f'**Attachment files:** [{name}]({name})\n**Type:** FULL\n\n'
                           'Option 2: +2%, $30.\n\n> Prior quotation remains.\n')
        return record, dict(attachment_files_json=json.dumps([item]))

    def test_deduplicates_bytes_preserves_body_and_reports_gaps(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixtures = [self.fixture(root, 1, 'terms.txt', b'Actual terms: +2%, $30.'),
                        self.fixture(root, 2, 'copy.txt', b'Actual terms: +2%, $30.'),
                        self.fixture(root, 3, 'photo.png', b'visual fixture'),
                        self.fixture(root, 4, 'missing.txt', b'missing', False),
                        self.fixture(root, 5, 'unreadable.txt', b'\xff\x00')]
            records = [f[0] for f in fixtures]
            indexes = {'gmail': {r['number']: m for r, m in fixtures}}
            destination = root / 'review.zip'
            summary = export_review(records, indexes, destination, compact_record, 'America/New_York')
            with zipfile.ZipFile(destination) as package:
                self.assertIsNone(package.testzip())
                self.assertLessEqual(len(package.namelist()), 10)
                timeline = package.read('timeline.txt').decode()
                self.assertEqual(timeline.count('Option 2: +2%, $30.\n\n> Prior quotation remains.'), 5)
                self.assertNotIn('](terms.txt)', timeline)
                rows = list(csv.DictReader(io.StringIO(package.read('attachment_index.csv').decode())))
                self.assertEqual(len(rows), 4)
                duplicate = next(r for r in rows if r['status'] == 'extracted')
                self.assertEqual(duplicate['message_ids'], 'gmail:0001;gmail:0002')
                self.assertEqual(json.loads(duplicate['original_filenames']), ['copy.txt', 'terms.txt'])
                associations = json.loads(duplicate['associations'])
                self.assertEqual({(a['message_id'], a['original_filename']) for a in associations},
                                 {('gmail:0001', 'terms.txt'), ('gmail:0002', 'copy.txt')})
                record_one = timeline.split('## gmail:0001', 1)[1].split('## gmail:0002', 1)[0]
                self.assertIn('(terms.txt)', record_one)
                self.assertNotIn('(copy.txt)', record_one)
                self.assertEqual({r['status'] for r in rows}, {'extracted', 'visual_review', 'unavailable', 'extraction_failed'})
                text = package.read(duplicate['text_files']).decode()
                self.assertEqual(text.count('Actual terms: +2%, $30.'), 1)
                self.assertIn('gmail:0001, gmail:0002', text)
                self.assertFalse(any(n.endswith('.png') for n in package.namelist()))
            self.assertIn('1 visual review', summary)

    def test_hash_mismatch_preserves_previous_package(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record, metadata = self.fixture(root, 1, 'terms.txt', b'original')
            destination = root / 'review.zip'
            destination.write_bytes(b'previous valid package')
            (root / 'terms.txt').write_bytes(b'replaced')
            with self.assertRaisesRegex(ValueError, 'differs'):
                with staged_outputs([destination]) as stages:
                    export_review([record], {'gmail': {1: metadata}}, stages[0], compact_record,
                                  'America/New_York', destination)
            self.assertEqual(destination.read_bytes(), b'previous valid package')

    def test_document_extraction_labels_pages_and_scans(self):
        try:
            import pymupdf
        except ImportError:
            self.skipTest('PyMuPDF is not installed')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'exhibit.pdf'
            with pymupdf.open() as document:
                document.new_page().insert_text((72, 72), 'Actual terms: +2%, $30.')
                document.new_page()
                document.save(path)
            status, detail, sections = extract_text(path)
            self.assertEqual(status, 'partial')
            self.assertIn('pages: 2', detail)
            self.assertEqual(sections[0][0], 'PDF page 1')
            self.assertIn('+2%, $30.', sections[0][1])
            self.assertIn('visual review or OCR', sections[1][1])

    def test_docx_and_html_preserve_visible_text(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            document = root / 'terms.docx'
            with zipfile.ZipFile(document, 'w') as package:
                package.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Option 2</w:t><w:tab/><w:t>+2%</w:t></w:r></w:p></w:body></w:document>')
            self.assertEqual(extract_text(document)[2][0][1], 'Option 2\t+2%')
            html = root / 'terms.html'
            html.write_text('<style>hidden</style><p>Option 2 &amp; +2%</p><script>ignored</script>')
            self.assertEqual(extract_text(html)[2][0][1], 'Option 2 & +2%')

    def test_large_attachment_text_has_labeled_continuations_and_bounded_files(self):
        header = '\n=== ATTACHMENT attachment:0001 ===\nFilename: terms.txt\nLocation: page 1'
        body = 'Substantive terms.\n' * 2000
        parts = pack_sections([header + '\n\n' + body], target_chars=300, max_parts=7)
        self.assertLessEqual(len(parts), 7)
        restored = ''
        for part in parts:
            self.assertIn('attachment:0001', part)
            self.assertIn('Location: page 1', part)
            restored += part.split('\n\n', 1)[1]
        self.assertEqual(restored, body)
