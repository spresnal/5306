"""Exercise default CLI paths with originals separated from curated archives."""
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from urllib.parse import unquote

from property_timeline.pdf_attachments import collect_files


class ProjectLayoutTests(unittest.TestCase):
    def test_default_combine_preserves_source_and_attachment_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for origin in ('gmail', 'android', 'iphone'):
                (root / 'data/originals' / origin).mkdir(parents=True)
                (root / 'data/archives' / origin).mkdir(parents=True)
            for origin, name in [('gmail', 'property_emails.mbox'),
                                 ('android', 'android_darcy_group.html'),
                                 ('android', 'android_darcy_group.smsbackup'),
                                 ('iphone', 'iphone_darcy.pdf')]:
                (root / 'data/originals' / origin / name).write_bytes(b'original export fixture')

            android = root / 'data/archives/android'
            original = root / 'data/originals/android/group_conversation_966_Attachments/file.txt'
            original.parent.mkdir()
            original.write_bytes(b'original attachment fixture')
            relative = '../../originals/android/group_conversation_966_Attachments/file.txt'
            android.joinpath('android_darcy_group_messages.md').write_text(
                '# Android\n\n## Message 0001 — 2026-05-01 12:00\n'
                '**From:** Sam\n**To:** Darcy\n'
                f'**Attachment files:** [file.txt]({relative})\n\nAttachment fixture.\n',
                encoding='utf-8')
            with android.joinpath('android_darcy_group_index.csv').open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=['message_number', 'attachment_files_json'])
                writer.writeheader()
                writer.writerow(dict(message_number=1, attachment_files_json=json.dumps([dict(
                    relative_path=relative, original_filename='file.txt', available=True,
                    byte_size=original.stat().st_size,
                    sha256=hashlib.sha256(original.read_bytes()).hexdigest())])))
            root.joinpath('data/archives/iphone/iphone_darcy_messages.md').write_text(
                '# iPhone\n\n## Message 0001 — 2026-05-01 12:01\n'
                '**From:** Regina\n**To:** Darcy\n\niPhone fixture.\n', encoding='utf-8')
            iphone = root / 'data/archives/iphone'
            (root / 'data/originals/iphone/iphone_derrick.pdf').write_bytes(b'Derrick original fixture')
            iphone.joinpath('iphone_derrick_messages.md').write_text(
                '# Derrick\n\n## Message 0001 — 2026-05-01 12:03\n'
                '**From:** Derrick\n**To:** Regina\n\nDerrick fixture.\n', encoding='utf-8')
            derrick_file = iphone / 'derrick.txt'
            derrick_file.write_bytes(b'Derrick attachment fixture')
            for name, files in [('darcy', []), ('derrick', [dict(
                    relative_path='derrick.txt', original_filename='derrick.txt', available=True,
                    byte_size=derrick_file.stat().st_size,
                    sha256=hashlib.sha256(derrick_file.read_bytes()).hexdigest())])]:
                with iphone.joinpath(f'iphone_{name}_index.csv').open('w', newline='') as stream:
                    writer = csv.DictWriter(stream, fieldnames=['message_number', 'attachment_files_json'])
                    writer.writeheader()
                    writer.writerow(dict(message_number=1, attachment_files_json=json.dumps(files)))
            root.joinpath('data/archives/gmail/property_emails_compact.md').write_text(
                '# Gmail\n\n## Email 001 — 2026-05-01 16:02 UTC\n'
                '**From:** Darcy <darcy@example.com>\n**To:** Sam <sam@example.com>\n'
                '**Subject:** Fixture\n\nEmail fixture.\n', encoding='utf-8')

            result = subprocess.run([sys.executable, '-m', 'property_timeline.combine_timeline',
                                     '--phone-timezone', 'America/New_York'],
                                    cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            output = root / 'output/master_timeline.html'
            attachments = collect_files(output.read_text(encoding='utf-8'), output)
            self.assertIn('href="master_timeline_ai.zip"', output.read_text(encoding='utf-8'))
            self.assertIn('Export for AI', output.read_text(encoding='utf-8'))
            self.assertTrue(output.with_name('master_timeline_ai.zip').is_file())
            self.assertEqual(len(attachments), 2)
            self.assertEqual({item['path'].resolve() for item in attachments.values()},
                             {original.resolve(), derrick_file.resolve()})
            html = output.read_text(encoding='utf-8')
            self.assertIn('id="iphone_derrick:0001"', html)
            darcy_card = html.split('<article id="iphone:0001"', 1)[1].split('</article>', 1)[0]
            derrick_card = html.split('<article id="iphone_derrick:0001"', 1)[1].split('</article>', 1)[0]
            self.assertNotIn('derrick.txt', darcy_card)
            self.assertIn('derrick.txt', derrick_card)
            with output.with_suffix('.csv').open(encoding='utf-8-sig', newline='') as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 4)
            self.assertEqual({row['reference_id'] for row in rows},
                             {'gmail:0001', 'android:0001', 'iphone:0001', 'iphone_derrick:0001'})
            for row in rows:
                self.assertTrue((output.parent / row['archive_file']).is_file())
            compact = output.with_name('master_timeline_compact.md')
            href = re.search(r'\[file.txt\]\(([^)]+)\)',
                             compact.read_text(encoding='utf-8')).group(1)
            self.assertEqual((compact.parent / unquote(href)).resolve(), original.resolve())
            markdown = output.with_suffix('.md').read_text(encoding='utf-8')
            for name in ['property_emails.mbox', 'android_darcy_group.html',
                         'android_darcy_group.smsbackup', 'iphone_darcy.pdf', 'iphone_derrick.pdf']:
                self.assertIn(name, markdown)
                self.assertNotIn(f'supporting source unavailable:** `{name}`', markdown)
