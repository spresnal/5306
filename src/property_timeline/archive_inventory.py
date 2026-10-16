"""Shared archive/index preflight and explicit generation binding for curation."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re

from property_timeline.attachment_inventory import validate_attachment
from property_timeline.output_safety import distinct_paths, staged_outputs


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def provenance_path(archive):
    return archive.with_name(archive.stem + '_provenance.json')


def index_path_for(archive, origin):
    name = {'gmail': 'property_email_source_index.csv',
            'android': 'android_darcy_group_index.csv'}.get(origin)
    return archive.with_name(name or archive.stem.removesuffix('_messages') + '_index.csv')


def read_rows(index, origin, directory):
    column = 'source_email_number' if origin == 'gmail' else 'message_number'
    with index.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if not {column, 'attachment_files_json'} <= set(reader.fieldnames or ()):
            raise ValueError(f'Required source-index columns missing in {index}')
        rows = list(reader)
    numbers = []
    for row in rows:
        if None in row or any(value is None for value in row.values()):
            raise ValueError('Malformed source-index row in ' + str(index))
        if not re.fullmatch(r'\d+', row[column]) or int(row[column]) < 1:
            raise ValueError('Invalid source number in ' + str(index))
        numbers.append(int(row[column]))
        try:
            files = json.loads(row['attachment_files_json'])
        except (TypeError, ValueError):
            raise ValueError('Malformed attachment JSON in ' + str(index)) from None
        if not isinstance(files, list):
            raise ValueError('Attachment metadata must be an array in ' + str(index))
        for item in files:
            if (not isinstance(item, dict) or not isinstance(item.get('relative_path'), str)
                    or not item['relative_path'] or not isinstance(item.get('original_filename'), str)
                    or not item['original_filename'] or not isinstance(item.get('available', True), bool)):
                raise ValueError('Malformed attachment metadata in ' + str(index))
            if item.get('available', True):
                if (not isinstance(item.get('sha256'), str) or not re.fullmatch('[a-f0-9]{64}', item['sha256'])
                        or isinstance(item.get('byte_size'), bool)
                        or not isinstance(item.get('byte_size'), int) or item['byte_size'] < 0):
                    raise ValueError('Attachment requires a valid extraction hash and size in ' + str(index))
            validate_attachment(item, directory)
    if len(set(numbers)) != len(numbers):
        raise ValueError('Duplicate source index numbers in ' + str(index))
    return dict(zip(numbers, rows))


def validate_index(archive, origin, records, index=None, check_generation=True):
    index = index or index_path_for(archive, origin)
    if not index.is_file():
        raise ValueError('Required source index missing: ' + str(index))
    rows = read_rows(index, origin, archive.parent)
    expected = {record['number'] for record in records}
    if set(rows) != expected:
        raise ValueError(f'Source index coverage differs for {archive.name}: '
                         f'missing {sorted(expected - set(rows))}, extra {sorted(set(rows) - expected)}')
    manifest = provenance_path(archive)
    if check_generation and manifest.exists():
        value = json.loads(manifest.read_text(encoding='utf-8'))
        if (not isinstance(value, dict) or value.get('version') != 1 or value.get('archive_name') != archive.name
                or value.get('index_name') != index.name or value.get('origin') != origin
                or value.get('archive_sha256') != digest(archive) or value.get('index_sha256') != digest(index)):
            raise ValueError('Archive/index generation mismatch: ' + str(archive) +
                             '; restore a matching generation or validate and bind intentional curation')
    return rows


def generation(archive_stage, index_stage, archive, index, origin, source=None):
    rows = read_rows(index_stage, origin, archive.parent)
    return {'version': 1, 'origin': origin, 'archive_name': archive.name, 'index_name': index.name,
            'archive_sha256': digest(archive_stage), 'index_sha256': digest(index_stage),
            'source': ({'path': Path(os.path.relpath(source, archive.parent)).as_posix(),
                        'sha256': digest(source)} if source else None),
            'source_numbers': sorted(rows),
            'attachments': {str(number): json.loads(row['attachment_files_json']) for number, row in rows.items()}}


def write_generation(stage, archive_stage, index_stage, archive, index, origin, source=None):
    value = generation(archive_stage, index_stage, archive, index, origin, source)
    existing = provenance_path(archive)
    if source is None and existing.exists():
        previous = json.loads(existing.read_text(encoding='utf-8'))
        if isinstance(previous, dict):
            value['source'] = previous.get('source')
    stage.write_text(json.dumps(value,
                                indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['check', 'bind'])
    parser.add_argument('archive', type=Path)
    parser.add_argument('--origin', choices=['gmail', 'android', 'iphone'], required=True)
    parser.add_argument('--index', type=Path)
    parser.add_argument('--source', type=Path, help='Original export to fingerprint during explicit binding')
    parser.add_argument('--frame', action='store_true', help='Bind and frame legacy bodies without changing logical record text')
    args = parser.parse_args()
    from property_timeline.combine_timeline import parse_archive
    from property_timeline.archive_format import MARKER, frame_body
    from zoneinfo import ZoneInfo
    archive = args.archive.resolve()
    index = (args.index or index_path_for(archive, args.origin)).resolve()
    records, preamble = parse_archive(archive, args.origin, ZoneInfo('America/New_York'))
    validate_index(archive, args.origin, records, index, check_generation=args.command == 'check')
    if args.command == 'check':
        if args.frame:
            parser.error('--frame is only available with bind')
        print('Validated', len(records), 'archive/index associations;',
              'generation bound' if provenance_path(archive).exists() else 'legacy generation unbound')
        return
    manifest = provenance_path(archive)
    source = args.source.resolve() if args.source else None
    distinct_paths([archive, index, *([source] if source else [])], [manifest])
    if args.frame and source is not None:
        distinct_paths([source, index], [archive, manifest])
    destinations = [archive, manifest] if args.frame else [manifest]
    with staged_outputs(destinations) as stages:
        archive_stage = archive
        if args.frame:
            chunks = [MARKER, preamble.removeprefix(MARKER).lstrip('\n'), '']
            for record in records:
                metadata, separator, body = record['text'].partition('\n\n')
                if not separator:
                    raise ValueError('Record lacks a separate body section: ' + record['id'])
                chunks.extend([metadata, '', frame_body(body), ''])
            stages[0].write_text('\n'.join(chunks), encoding='utf-8')
            archive_stage = stages[0]
        write_generation(stages[-1], archive_stage, index, archive, index, args.origin, source)
    print('Bound validated generation;', 'archive framing updated; regenerate timeline' if args.frame else 'curated text unchanged')


if __name__ == '__main__':
    main()
