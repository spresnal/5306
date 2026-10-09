"""Restore lost quoted passages by Message-ID without replacing curated bodies."""
import argparse
import csv
import difflib
import hashlib
import json
import mailbox
from pathlib import Path
import re
from property_timeline.gmail_archive import clean_body, mbox_body
from property_timeline.email_parsing import normalized_passage
from property_timeline.combine_timeline import parse_archive
from property_timeline.output_safety import staged_outputs, distinct_paths
from zoneinfo import ZoneInfo


def legacy_boundary(lines, i):
    plain = re.sub(r'^\s*(?:>\s*)+', '', lines[i]).lstrip(' \t*_').strip()
    if re.match(r'^-{3,}\s*(?:Forwarded message|Original Message)\s*-{2,}', plain, re.I):
        return True
    if re.match(r'^On\s+.{5,350}\bwrote:\s*$', plain, re.I):
        return True
    if plain.startswith('From:'):
        following = '\n'.join(re.sub(r'^\s*(?:>\s*)+', '', line).lstrip(' \t*_').strip()
                              for line in lines[i + 1:i + 7])
        return bool(re.search(r'(?im)^(Sent:|Date:|To:|Subject:)\s', following))
    return False


def missing_blocks(raw):
    # Compare exactly the old boundary recognition with the fixed extraction.
    old = clean_body(raw, boundary=legacy_boundary).splitlines(keepends=True)
    new = clean_body(raw).splitlines(keepends=True)
    old_keys = [normalized_passage(line) for line in old]
    new_keys = [normalized_passage(line) for line in new]
    blocks = []
    for operation, _, _, start, end in difflib.SequenceMatcher(None, old_keys, new_keys, autojunk=False).get_opcodes():
        if operation in ('insert', 'replace'):
            text = ''.join(new[start:end]).strip()
            if text:
                blocks.append(text)
    return blocks


def recover(mbox, archive, index, manifest):
    distinct_paths([mbox], [archive, index, manifest])
    with index.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        columns = reader.fieldnames
        rows = list(reader)
    metadata = {int(row['source_email_number']): row for row in rows}
    if len(metadata) != len(rows):
        raise ValueError('Duplicate source email numbers')
    wanted = {row['message_id'] for row in rows}
    originals = {}
    box = mailbox.mbox(str(mbox), create=False)
    try:
        for message in box:
            identifier = str(message.get('Message-ID', '')).strip()
            if identifier in wanted:
                if identifier in originals:
                    raise ValueError('Ambiguous original Message-ID: ' + identifier)
                originals[identifier] = message
    finally:
        box.close()
    records, _ = parse_archive(archive, 'gmail', ZoneInfo('America/New_York'))
    lines = archive.read_text(encoding='utf-8-sig').splitlines(keepends=True)
    changes, modifications = [], []
    for record in records:
        row = metadata[record['number']]
        if row['representation'] != 'FULL':
            continue  # Retain intentional shortening/redaction decisions.
        identifier = row['message_id']
        if identifier not in originals:
            raise ValueError('Original email unavailable: ' + identifier)
        additions = []
        represented = normalized_passage(record['text'])
        for block in missing_blocks(mbox_body(originals[identifier])):
            # Recovery is idempotent and never overwrites existing edited text.
            content = normalized_passage(block)
            if content and content not in represented:
                additions.append(block)
                represented += ' ' + content
        if not additions:
            continue
        addition = '\n\n' + '\n\n'.join(additions) + '\n'
        position = record['line_end']
        modifications.append((position, addition))
        row['output_body_chars'] = str(int(row['output_body_chars']) + len(addition))
        if 'contains_reply_marker_review_original' in row:
            row['contains_reply_marker_review_original'] = 'True'
        changes.append(dict(reference_id=record['id'], message_id=identifier,
                            recovered_blocks=additions, recovered_sha256=hashlib.sha256(addition.encode()).hexdigest()))
    if not changes:
        return []
    for position, addition in reversed(modifications):
        lines.insert(position, addition)
    previous = json.loads(manifest.read_text()) if manifest.exists() else dict(recoveries=[])
    previous['recoveries'].extend(changes)
    with mbox.open('rb') as stream:
        previous['mbox_sha256'] = hashlib.file_digest(stream, 'sha256').hexdigest()
    with staged_outputs([archive, index, manifest]) as stages:
        stages[0].write_text(''.join(lines), encoding='utf-8')
        with stages[1].open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
        stages[2].write_text(json.dumps(previous, ensure_ascii=False, indent=2), encoding='utf-8')
    return changes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mbox', type=Path, default=Path('data/originals/gmail/property_emails.mbox'))
    parser.add_argument('--archive', type=Path, default=Path('data/archives/gmail/property_emails_compact.md'))
    parser.add_argument('--index', type=Path, default=Path('data/archives/gmail/property_email_source_index.csv'))
    parser.add_argument('--manifest', type=Path, default=Path('data/archives/gmail/email_quote_recovery_manifest.json'))
    args = parser.parse_args()
    changes = recover(args.mbox, args.archive, args.index, args.manifest)
    print('Recovered quoted text in', len(changes), 'records:', ', '.join(change['reference_id'] for change in changes))


if __name__ == '__main__':
    main()
