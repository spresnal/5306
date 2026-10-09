"""Stable conversation IDs and source-index lookup across phone archives."""
import re


def archive_namespace(path, origin):
    if origin == 'iphone':
        stem = path.stem.removesuffix('_messages')
        if not re.fullmatch(r'iphone_[a-z0-9_]+', stem):
            raise ValueError('iPhone archives must use iphone_<name>_messages.md')
        return stem
    return origin


def record_metadata(index, record):
    key = record['id'] if record['origin'] == 'iphone' else record['number']
    return index.get(key, {})
