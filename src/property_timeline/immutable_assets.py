"""Publish immutable extracted bytes without changing previously referenced assets."""
import hashlib
import os
from pathlib import Path
import tempfile


def publish_asset(directory, filename, payload, forbidden=()):
    digest = hashlib.sha256(payload).hexdigest()
    directory = Path(directory).resolve()
    target = directory / digest / filename
    forbidden = {Path(p).resolve() for p in forbidden}
    if target.resolve() != target or target in forbidden or any(p in target.parents for p in forbidden):
        raise ValueError('Extracted asset path collides with a source or output')
    if target.exists():
        if not target.is_file() or target.read_bytes() != payload:
            raise ValueError('Immutable asset differs from its content hash: ' + str(target))
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=target.parent, prefix='.asset-')
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(payload)
        try:
            os.link(temporary, target)  # Atomic create; never replaces an existing path.
        except FileExistsError:
            if target.read_bytes() != payload:
                raise ValueError('Immutable asset collision: ' + str(target)) from None
    finally:
        Path(temporary).unlink(missing_ok=True)
    return target
