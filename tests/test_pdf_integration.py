"""Small PDF fixtures; run with Windows Python through --self-test."""
import hashlib
import tempfile
import csv
import json
import subprocess
import sys
import unittest
from pathlib import Path
try:
    import pymupdf as fitz
except ImportError:
    fitz = None

from property_timeline.pdf_attachments import collect_files, tokenize_file_links, PREFIX


@unittest.skipIf(fitz is None, 'PyMuPDF not installed in this interpreter')
class PDFIntegrationTests(unittest.TestCase):
    def test_iphone_named_speakers_and_contact_display_name(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'phone.pdf'
            document = fitz.open()
            page = document.new_page()
            lines = [
                'Messages exported from: Regina', 'With: Darcy Carmel',
                'Regina · May 1, 2026 at 10:00 AM', 'Outgoing named message.',
                'Darcy Carmel · May 1, 2026 at 10:01 AM', 'Incoming message.',
                'May 1, 2026 at 10:02 AM', 'Legacy outgoing message.',
            ]
            for index, line in enumerate(lines):
                page.insert_text((60, 60 + index * 25), line)
            document.save(source)
            document.close()
            original = source.read_bytes()
            for display_name in ('Darcy', 'Darcy Carmel'):
                command = [sys.executable, '-m', 'property_timeline.iphone_pdf_to_markdown',
                           str(source), '--me', 'Regina']
                if display_name == 'Darcy':
                    command += ['--other', display_name]
                result = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                with source.with_name('phone_index.csv').open(encoding='utf-8-sig', newline='') as stream:
                    rows = list(csv.DictReader(stream))
                self.assertEqual([(row['sender'], row['recipient']) for row in rows],
                                 [('Regina', display_name), (display_name, 'Regina'),
                                  ('Regina', display_name)])
                archive = source.with_name('phone_messages.md').read_text(encoding='utf-8')
                self.assertNotIn('Messages exported from:', archive)
                self.assertIn('Outgoing named message.', archive)
                self.assertIn('Incoming message.', archive)
                self.assertEqual(source.read_bytes(), original)

    def test_iphone_extraction_registers_actual_image_and_guards_source(self):
        from PIL import Image
        from property_timeline.attachment_inventory import validate_attachment
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            photo = directory / 'photo.png'
            Image.new('RGB', (400, 400), 'blue').save(photo)
            source = directory / 'phone.pdf'
            document = fitz.open()
            page = document.new_page()
            page.insert_text((60, 60), 'May 1, 2026 at 10:00 AM')
            page.insert_text((60, 90), 'Attached photo.')
            page.insert_image(fitz.Rect(60, 120, 260, 320), filename=str(photo))
            document.save(source)
            document.close()
            result = subprocess.run([sys.executable, '-m', 'property_timeline.iphone_pdf_to_markdown', str(source), '--me', 'Regina'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            with source.with_name('phone_index.csv').open(encoding='utf-8-sig', newline='') as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 1)
            files = json.loads(rows[0]['attachment_files_json'])
            self.assertEqual(len(files), 1)
            validate_attachment(files[0], directory)
            original = source.read_bytes()
            result = subprocess.run([sys.executable, '-m', 'property_timeline.iphone_pdf_to_markdown', str(source), '--output', str(source)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(source.read_bytes(), original)

    def test_previews_preserve_orientation_and_avoid_stem_collisions(self):
        from PIL import Image
        from property_timeline.export_timeline_pdf import image_preview, preview_path
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            a, b, assets = [directory / name for name in ('a', 'b', 'assets')]
            for path in (a, b, assets):
                path.mkdir()
            first, second = a / 'image.jpg', b / 'image.jpg'
            image = Image.new('RGB', (80, 40), 'red')
            exif = image.getexif()
            exif[274] = 6
            image.save(first, exif=exif)
            Image.new('RGB', (80, 40), 'blue').save(second)
            self.assertNotEqual(preview_path(first, assets, 'small'), preview_path(second, assets, 'small'))
            self.assertNotEqual(preview_path(first, assets, 'small'), preview_path(first, assets, 'page1'))
            with Image.open(image_preview(first, assets)) as preview:
                self.assertEqual(preview.size, (40, 80))

    def test_every_attachment_occurrence_and_payload_verified(self):
        from property_timeline.pdf_embedded_attachments import embed_attachments, verify_embedded
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            path = directory / 'fixture.txt'
            path.write_bytes(b'original fixture payload')
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            anchor = f'<a class="file-link" data-sha256="{digest}" data-byte-size="{path.stat().st_size}" href="fixture.txt">Fixture</a>'
            source, output = directory / 'timeline.html', directory / 'timeline.pdf'
            html = '<article id="gmail:0001">' + anchor + '</article><article id="iphone_darcy:0001">' + anchor + '</article>'
            files = collect_files(html, source)
            _, targets = tokenize_file_links(html, source, output)
            document = fitz.open()
            page = document.new_page()
            for index, token in enumerate(targets):
                page.insert_link({'kind': fitz.LINK_URI, 'from': fitz.Rect(60, 60 + index * 50, 160, 90 + index * 50), 'uri': PREFIX + token})
            document = fitz.open(stream=document.tobytes(), filetype='pdf')
            self.assertEqual(embed_attachments(document, files, source, output, targets), 2)
            document.save(output)
            document.close()
            with fitz.open(output) as verified:
                self.assertEqual(verify_embedded(verified, files, targets), 2)
                self.assertEqual(verified.embfile_count(), 3)  # one original, two manifests
                page = verified[0]
                annotation = next(page.annots())
                page.delete_annot(annotation)
                with self.assertRaisesRegex(ValueError, 'Missing clickable'):
                    verify_embedded(verified, files, targets)

    def test_record_body_and_corrected_destinations(self):
        from property_timeline.pdf_validation import fix_record_destinations, verify_record_bodies, verify_destination_targets
        document = fitz.open()
        page = document.new_page()
        positions = {'gmail:0001': dict(page=0, to=(60, 49)), 'gmail:0002': dict(page=0, to=(60, 149))}
        for index, identifier in enumerate(positions):
            y = 60 + index * 100
            page.insert_text((60, y), identifier)
            page.insert_text((60, y + 30), f'Complete substantive body {index + 1}.')
            rectangle = page.search_for(identifier)[0]
            page.insert_link({'kind': fitz.LINK_URI, 'from': rectangle, 'uri': identifier})
        document = fitz.open(stream=document.tobytes(), filetype='pdf')
        for link in document[0].get_links():
            document.xref_set_key(link['xref'], 'A', '<</S/GoTo/D' + fitz.get_pdf_str(link['uri']) + '>>')
        fix_record_destinations(document, positions)
        document = fitz.open(stream=document.tobytes(), filetype='pdf')
        html = ''.join(f'<article id="gmail:000{n}"><div class="body">Complete substantive body {n}.</div></article>' for n in (1, 2))
        destinations = verify_record_bodies(document, html)
        self.assertEqual(set(destinations), set(positions))
        verify_destination_targets(document, destinations)
        wrong = dict(destinations)
        wrong['gmail:0001'] = dict(page=0, to=(60, 300))
        with self.assertRaisesRegex(ValueError, 'does not point to its record header'):
            verify_destination_targets(document, wrong)
        with self.assertRaisesRegex(ValueError, 'Missing or altered rendered body'):
            verify_record_bodies(document, html.replace('body 2', 'body 9'))
        with self.assertRaisesRegex(ValueError, 'Missing native PDF record destinations'):
            verify_record_bodies(document, html + '<article id="gmail:0003"><div class="body">Missing card</div></article>')
