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
            for origin, name in [('gmail', '5306 House.mbox'),
                                 ('android', 'group_conversation_966.html'),
                                 ('android', 'group_conversation_966.smsbackup'),
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
            self.assertEqual(len(attachments), 1)
            self.assertEqual(next(iter(attachments.values()))['path'].resolve(), original.resolve())
            with output.with_suffix('.csv').open(encoding='utf-8-sig', newline='') as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 3)
            for row in rows:
                self.assertTrue((output.parent / row['archive_file']).is_file())
            compact = output.with_name('master_timeline_compact.md')
            href = re.search(r'\[file.txt\]\(([^)]+)\)',
                             compact.read_text(encoding='utf-8')).group(1)
            self.assertEqual((compact.parent / unquote(href)).resolve(), original.resolve())
            markdown = output.with_suffix('.md').read_text(encoding='utf-8')
            for name in ['5306%20House.mbox', 'group_conversation_966.html',
                         'group_conversation_966.smsbackup', 'iphone_darcy.pdf']:
                self.assertIn(name, markdown)
                self.assertNotIn(f'supporting source unavailable:** `{name}`', markdown)
