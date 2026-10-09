"""Stable conversation IDs and source-index lookup across phone archives."""
import re


def archive_namespace(path, origin):
    if origin == 'iphone' and path.name != 'iphone_darcy_messages.md':
        stem = path.stem.removesuffix('_messages')
        if not re.fullmatch(r'iphone_[a-z0-9_]+', stem):
            raise ValueError('Additional iPhone archives must use iphone_<name>_messages.md')
        return stem
    return origin


def record_metadata(index, record):
    if record['id'] in index:
        return index[record['id']]
    if record['id'] == f"{record['origin']}:{record['number']:04d}":
        return index.get(record['number'], {})
    return {}
