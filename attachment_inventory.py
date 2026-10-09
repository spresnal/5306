"""Validate attachments against extraction metadata before rendering/embedding."""
import hashlib
from pathlib import Path


def validate_attachment(item, directory):
    path = (directory / item['relative_path']).resolve()
    if not item.get('available', True):
        return None
    if not path.is_file():
        raise ValueError('Required attachment is missing: ' + str(path))
    if not item.get('sha256') or item.get('byte_size') is None:
        raise ValueError('Attachment has no extraction hash/size: ' + str(path))
    if path.stat().st_size != int(item['byte_size']) or hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
        raise ValueError('Attachment differs from extraction metadata: ' + str(path))
    return path
