import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from signature_attachments import is_signature_attachment


class SignatureAttachmentTests(unittest.TestCase):
    def test_only_reviewed_unchanged_bytes_are_excluded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, 'image001.png')
            path.write_bytes(b'reviewed signature logo')
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            item = dict(relative_path=path.name, sha256=digest)
            with patch.dict('signature_attachments.SIGNATURE_HASHES', {digest: 'fixture'}, clear=True):
                self.assertTrue(is_signature_attachment(item, Path(directory)))
                path.write_bytes(b'substantive replacement')
                self.assertFalse(is_signature_attachment(item, Path(directory)))

    def test_generic_names_and_secure_payload_are_kept(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ('image001.png', 'logo.jpeg', 'lock.gif', 'SecureMessageAtt.html'):
                path = Path(directory, name)
                path.write_bytes(b'substantive fixture ' + name.encode())
                item = dict(relative_path=name, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
                self.assertFalse(is_signature_attachment(item, Path(directory)))
