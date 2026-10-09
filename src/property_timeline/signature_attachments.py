"""Identify reviewed signature assets by exact bytes, never generic filenames."""
import hashlib
import json
from importlib.resources import files as resource_files

SIGNATURE_HASHES = json.loads(resource_files('property_timeline.resources').joinpath('signature_attachment_hashes.json').read_text())


def is_signature_attachment(item, source_directory):
    path = source_directory / item['relative_path']
    # Verify actual bytes rather than trusting stale extraction metadata.
    if not path.is_file():
        return False
    if item.get('sha256') not in SIGNATURE_HASHES:
        return False
    return hashlib.sha256(path.read_bytes()).hexdigest() in SIGNATURE_HASHES
