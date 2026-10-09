"""Shared fingerprints for review assessments and the offline viewer."""
import hashlib
import json

from property_timeline.attachment_inventory import validate_attachment
from property_timeline.signature_attachments import is_signature_attachment


def hashed(value):
    if not isinstance(value, str):
        value = json.dumps(value, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def evidence_hash(text, metadata, directory):
    excluded = []
    for item in json.loads(metadata.get('attachment_files_json') or '[]'):
        path = validate_attachment(item, directory)
        excluded.append(bool(path and is_signature_attachment(item, directory)))
    return hashed({'text': text, 'metadata': metadata, 'excluded': excluded})


def criteria_hash(brief, instructions):
    return hashed({'brief': brief, 'instructions': instructions, 'version': 1})
