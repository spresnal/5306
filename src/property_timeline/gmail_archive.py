#!/usr/bin/env python3
"""Compact a Gmail MBOX or a prior emails_for_chatgpt.md export.

Standard library only. Outputs:
  1. property_emails_compact.md  (email-numbered research copy)
  2. property_email_source_index.csv  (one row per original email)
  3. property_emails_compact_attachments/ (decoded MIME attachment files)
  4. property_emails_compact_attachment_manifest.csv (file provenance/hashes)

This is a derivative copy, not a replacement for the underlying email evidence.
"""

import argparse
import mailbox
import re
import html
import csv
import pathlib
from datetime import timezone
from email.utils import parsedate_to_datetime
from email.header import decode_header, make_header
from html.parser import HTMLParser
from collections import Counter
import json
import os
from urllib.parse import quote
from property_timeline.email_attachments import extract_attachments
from property_timeline.email_parsing import message_boundary
from property_timeline.output_safety import staged_outputs, distinct_paths
from property_timeline.archive_format import MARKER, frame_body, outside_body, decode_record
from property_timeline.archive_inventory import provenance_path, write_generation


class HTMLToText(HTMLParser):
    """Keep message order, including inline and forwarded content."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('style', 'script', 'head'):
            self.skip += 1
        elif not self.skip and tag in ('br', 'p', 'div', 'li', 'tr', 'blockquote', 'hr'):
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ('style', 'script', 'head'):
            self.skip = max(0, self.skip - 1)
        elif not self.skip and tag in ('p', 'div', 'li', 'tr', 'blockquote'):
            self.parts.append('\n')

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def decoded_header(msg, name):
    value = msg.get(name, '')
    try:
        return ' '.join(str(make_header(decode_header(str(value)))).split())
    except (ValueError, UnicodeError, LookupError, TypeError):
        return ' '.join(str(value).split())


def decoded_part(part):
    try:
        data = part.get_payload(decode=True)
    except Exception:
        data = None
    if data is None:
        return str(part.get_payload() or '')
    charset = part.get_content_charset() or 'utf-8'
    try:
        return data.decode(charset, errors='replace')
    except (LookupError, UnicodeError):
        return data.decode('utf-8', errors='replace')


def mbox_body(msg):
    plains, htmls = [], []
    def body_parts(part):
        if part.get_filename() or part.get_content_disposition() == 'attachment':
            return
        if part.is_multipart():
            for child in part.get_payload():
                yield from body_parts(child)
        else:
            yield part
    for part in body_parts(msg):
        if part.get_content_type() == 'text/plain':
            plains.append(decoded_part(part))
        elif part.get_content_type() == 'text/html':
            htmls.append(decoded_part(part))
    if plains:
        return '\n'.join(plains)
    if htmls:
        parser = HTMLToText()
        parser.feed('\n'.join(htmls))
        return ''.join(parser.parts)
    return ''


def records_from_mbox(path, attachment_directory=None, attachment_records=None, forbidden=()):
    """Keep actual MIME messages structured until the final serialization boundary."""
    archive = mailbox.mbox(str(path), create=False)
    messages = list(archive)
    archive.close()

    def sort_key(msg):
        try:
            date = parsedate_to_datetime(decoded_header(msg, 'Date'))
            return date.replace(tzinfo=date.tzinfo or timezone.utc).timestamp()
        except (TypeError, ValueError, OverflowError):
            return 0

    messages.sort(key=sort_key)
    records = []
    for index, msg in enumerate(messages, 1):
        if attachment_directory is not None:
            extracted = extract_attachments(msg, index, attachment_directory, forbidden)
            attachment_records.extend(extracted)
        attachments = []
        for part in msg.walk():
            name = part.get_filename()
            if name or part.get_content_disposition() == 'attachment':
                attachments.append(name or 'unnamed attachment')
        records.append({'num': index, 'subject': decoded_header(msg, 'Subject') or '(no subject)',
                        'date': decoded_header(msg, 'Date'), 'from': decoded_header(msg, 'From'),
                        'to': decoded_header(msg, 'To'), 'cc': decoded_header(msg, 'Cc'),
                        'id': decoded_header(msg, 'Message-ID'), 'attachments': ', '.join(attachments),
                        'body': mbox_body(msg).strip() or '[No readable message body]'})
    return records


def from_mbox(path, attachment_directory=None, attachment_records=None):
    """Compatibility display helper; the extractor does not reparse this Markdown."""
    records = records_from_mbox(path, attachment_directory, attachment_records)
    lines = ['# Email Archive', '', f'Total messages: {len(records)}', '']
    for record in records:
        lines.extend(['---', '', f"## Email {record['num']:03d}: {record['subject']}", '',
                      *[f'{name}: {record[key]}' for name, key in
                        [('Date', 'date'), ('From', 'from'), ('To', 'to'), ('Cc', 'cc'),
                         ('Message-ID', 'id'), ('Attachments', 'attachments')] if record[key]],
                      '', frame_body(record['body']), ''])
    return '\n'.join(lines)


# Explicit boilerplate starts. Match only a whole line at beginning, so we do
# not silently modify sentences embedded within substantive messages.
SIG_START = re.compile(r'''(?ix)
  ^\s*(?:
    Darcy\s+Knott\s*,\s*\*?CLHMS
    | Garrett\s+E\.?\s+Lawton\s*\|\s*Attorney
    | Leslie\s+Appel\s+Maher\s*,\s*CPRIA
    | Jessica\s+Eye\s*,\s*CPRIA
    | Official\s+Partner\s+of\s*$
    | The\s+content\s+of\s+this\s+email\s+is\s+confidential
    | CONFIDENTIALITY\s+NOTICE
    | Privileged\s+and/or\s+confidential\s+information\s+may\s+be\s+contained
    | Copyright\s+(?:©|&copy;).*?All\s+Rights\s+Reserved
    | For\s+Dotloop\s+product\s+support
    | Millions\s+of\s+real\s+estate\s+professionals\s+and\s+clients\s+trust\s+dotloop
    | The\s+better\s+way\s+to\s+get\s+real\s+estate\s+deals\s+done
    | This\s+email\s+and\s+any\s+attachments\s+are\s+confidential
    | This\s+message\s+and\s+any\s+attachments\s+are\s+intended\s+solely
    | (?:Jarrod\s+F\.\s+Hirschfeld|Ellen\s+Thornberry|Clay\s+T\.\s+Symington|Tracy\s+Mathis|Kevin\s+Paulin|Bill\s+Reid)\s*[*_]*\s*$
    | Sent\s+from\s+my\s+(?:iPhone|iPad|Android)
    | Get\s+Outlook\s+for\s+(?:iOS|Android)
  )''')
TOPIC_NOTICE = re.compile(r'(?i)(action required:|thanks for signing|packet complete:|has signed|have signed|requested you to sign|withdrew .*packet|withdrawn|signature request|completed: .*docusign|everyone has signed|inspection agreement for|your inspection report|your invoice|earnest money|payment alert|autopay|paperless billing|bill is available|bills are available|under review: your address|accepted: your address|delivery status notification|automatic reply:|cyber fraud video|appointment (?:confirmation|is scheduled)|scheduling reminder|invitation: appointment|congratulations on your purchase of fine nz wine|online account!|move-in ready)')
AUTO_EMAIL = re.compile(r'(?i)(dotloop\.com|earnnest\.com|hellosign\.com|noreply|no-reply|google-maps-noreply|smarthub\.coop|mail\.google\.com|serviceorders|inspectionsupport|municipalonlinepayment|centerpointenergy|chubb|mailer-daemon)')

# Known commercial/automated platform boilerplate headings.
PLATFORM_CUTOFF = re.compile(r'(?im)^\s*(?:The better way to get real estate deals done|Millions of real estate professionals and clients trust dotloop|Connect with our trusted service providers|For Dotloop product support|Copyright (?:©|&copy;)|Terms: https?://|Privacy Policy: https?://|FAQ: https?://)')


def get_segment(m, nxt, raw):
    contents=raw[m.end():nxt]
    contents=re.sub(r'\n\s*---\s*\Z','',contents)
    # Before Date is the possibly wrapped title.
    mt=re.search(r'\n\s*Date: ',contents)
    if mt is None:
        raise ValueError('Email ' + m.group(1) + ' has no recognized metadata header')
    subject=' '.join(contents[:mt.start()].split())
    rest=contents[mt.start():].lstrip()
    match=re.search(r'\n\s*\n',rest)
    if match is None:
        raise ValueError('Email ' + m.group(1) + ' has no recognized body section')
    meta=rest[:match.start()]
    body=rest[match.end():]
    fields={}
    last=None
    for line in meta.splitlines():
        nameval=re.match(r'^([\w-]+):\s*(.*)$',line)
        if nameval:
            last=nameval.group(1).lower()
            fields[last]=nameval.group(2).strip()
        elif last and line.startswith((' ','\t')):
            fields[last]+=' '+line.strip()
        else:
            raise ValueError((m.group(1),line,meta))
    return {
        'num':int(m.group(1)),'subject':subject,'date':fields.get('date',''),
        'from':fields.get('from',''),'to':fields.get('to',''),
        'cc':fields.get('cc',''),'id':fields.get('message-id',''),
        'attachments':fields.get('attachments',''), 'body':body
    }

def clean_body(txt, boundary=message_boundary):
    txt=html.unescape(txt).replace('\u00a0',' ').replace('\u200b','')
    txt=txt.replace('\r\n','\n').replace('\r','\n')
    # Drop hidden image references and PGP signatures, not messages.
    txt=re.sub(r'(?ims)^-----BEGIN PGP SIGNATURE-----.*?^-----END PGP SIGNATURE-----\s*','',txt)
    # Drop opaque public-key, encrypted-message and certificate blocks from the
    # analysis copy. They cannot be meaningfully searched as ordinary prose.
    txt=re.sub(
        r'(?ims)^-----BEGIN (PGP PUBLIC KEY BLOCK|PGP PRIVATE KEY BLOCK|PGP MESSAGE|CERTIFICATE|PKCS7)-----.*?^-----END \1-----\s*',
        '[cryptographic block omitted]\n', txt
    )
    txt=re.sub(r'(?im)^-----BEGIN PGP SIGNED MESSAGE-----\s*\n(?:Hash:[^\n]*\n)?','',txt)
    txt=re.sub(r'(?m)^\s*\[cid:[^\n]+\]\s*$', '',txt)
    # Replace enormous tracking URLs and remove naked URLs from bare footer lines.
    txt=re.sub(r'https?://\S{140,}', '[long link omitted]',txt)
    txt=re.sub(r'(?m)^\s*(?:<)?https?://(?:www\.)?(?:facebook|twitter|instagram)\.com/[^\n]*\s*$','',txt)
    # PRESERVE REPLY HISTORY.  It can contain the only surviving copy of an
    # outgoing offer or an earlier communication, especially inside forwarded
    # messages.  Never truncate the text at an "On ... wrote:" marker.
    #
    # Remove footers *per message section*, and resume whenever a nested
    # message begins.  This avoids losing a substantive original after a
    # signature or disclaimer in an outer message.
    lines = txt.split('\n')
    kept = []
    in_footer = False

    def unquote(line):
        # Normalize one or more Gmail quoting levels for marker detection,
        # while leaving quote indicators intact in the actual output.
        return re.sub(r'^\s*(?:>\s*)+', '', line).lstrip(' \t*_').strip()

    def boundary_at(i):
        return boundary(lines, i)

    footer_extra = re.compile(
        r'(?i)^(?:Be aware!\s*Online banking fraud|'
        r'IRS Circular 230 disclosure|'
        r'This email has been scanned for viruses|'
        r'NOTICE: This electronic mail transmission)'
    )
    for i, line in enumerate(lines):
        t = unquote(line)
        if boundary_at(i):
            in_footer = False
        if in_footer:
            continue
        if SIG_START.match(t) or PLATFORM_CUTOFF.match(t) or footer_extra.match(t):
            in_footer = True
            continue
        kept.append(line)

    txt = '\n'.join(kept)
    # Strip inline img/link rendering fragments without removing actual prose
    txt=re.sub(r'(?m)^\s*(?:\[image:[^\]]+\]|\[cid:[^\]]+\])\s*$','',txt)
    txt=re.sub(r'(?m)^\s*\*?Official Partner of\s*$','',txt)
    # 'follow us' links and social footers
    txt=re.sub(r'(?m)^\s*(?:Truebloodre\.com|darcy@TruebloodRE\.com\s*\||<https?://(?:twitter|instagram|facebook)\.com/).*$', '',txt)
    # Visually noisy separators
    txt=re.sub(r'(?m)^\s*[*=_]{6,}\s*$','',txt)
    txt=re.sub(r'(?m)^\s*<https?://www\.google\.com/maps/search/[^>]+>\s*$','',txt)
    # Common break tokens in mail; leave ordinary URLs alone
    txt=re.sub(r'(?m)^[ \t]*>+[ \t]*$', '',txt)
    txt=re.sub(r'(?m)[ \t]+$', '',txt)
    txt=re.sub(r'\n{3,}', '\n\n',txt)
    return txt.strip()

def extract_dotloop_note(txt):
    m=re.search(r'(?i)Notes from sender\s*\n(.*?)(?=\n\s*(?:Review and sign|Documents in this packet|Caution:)|\Z)',txt,re.S)
    if m: return clean_body(m.group(1))
    return ''

def meaningful_attachments(s):
    if not s: return ''
    vals=[v.strip() for v in s.split(',') if v.strip()]
    vals=[v for v in vals if not re.fullmatch(r'(?i)(image\d+|logo\d*|~WRD\d+)\.(?:png|jpg|jpeg|gif|bmp)',v)]
    vals=list(dict.fromkeys(vals))
    photos=[v for v in vals if re.search(r'\.(?:png|jpg|jpeg|webp|gif)$',v,re.I)]
    other=[v for v in vals if v not in photos]
    if len(photos)>4:
        other.append(f'{len(photos)} photos/images (filenames in source index)')
    else:
        other+=photos
    return ', '.join(other)

def short_date(s):
    try:
        dt=parsedate_to_datetime(s)
        if dt.tzinfo:
            dt=dt.astimezone(timezone.utc)
            return dt.strftime('%Y-%m-%d %H:%M UTC')
        return dt.strftime('%Y-%m-%d %H:%M (TZ unspecified)')
    except Exception:
        return s

def compact_subject(s):
    return re.sub(r'\s+',' ',s).strip()

def automation(rec,body):
    # Known notice bodies are essentially platform boilerplate, preserve the
    # triggering event and meaningful sender comments.
    subj=rec['subject'].lower()
    addr=rec['from'].lower()
    if 'dotloop.com' in addr or 'hellosign.com' in addr or 'docusign' in addr:
        note=extract_dotloop_note(body)
        if note:
            return 'EVENT', f'Signing-system notice. Sender note: {note}'
        return 'EVENT', 'Signing-system notification; event described in subject.'
    if 'earnnest.com' in addr:
        amount=re.search(r'\$[\d,]+(?:\.\d{2})?',body)
        if amount:
            return 'EVENT', f'Payment notification for {amount.group(0)}; stage described in subject.'
        return 'EVENT', 'Earnest-money platform notification; event described in subject.'
    if re.search(r'(?i)(mailer-daemon|mail delivery subsystem)',addr):
        # Delivery failures can affect notice/proven delivery, so keep details.
        if 'delivery status notification' in subj:
            return 'FULL',body
    if 'inspection agreement for' in subj or 'your inspection report' in subj or 'your invoice for the inspection' in subj:
        if re.search(r'(?i)(outsideininspections|inspectionsupport)',addr):
            return 'EVENT', 'Inspector system notice. Inspection/report or invoice referenced in subject; check original email for access links.'
    if ('reminder: schedule your chubb assessment' in subj or 'congratulations on your purchase of fine nz wine' in subj) and 'chubb' in addr:
        return 'EVENT','Insurance risk assessment scheduling reminder.'
    if 'your invoice from' in subj:
        return 'EVENT','Vendor invoice notification; amounts and underlying documents not included in this export.'
    if any(s in subj for s in ['under review: your address','accepted: your address','your bills are available','your internet bill is available','autopay','paperless billing','you have signed up for an online account','payment alert','get move-in ready','automatic reply:', 'congratulations on your purchase of fine nz wine']):
        return 'EVENT','Routine automated update; subject identifies event.'
    return 'FULL',body


def main():

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=pathlib.Path,
                        help='Gmail .mbox or emails_for_chatgpt.md')
    parser.add_argument('--output', type=pathlib.Path,
                        help='Output Markdown file (default next to source)')
    parser.add_argument('--index', type=pathlib.Path,
                        help='Output CSV source index (default next to output archive)')
    parser.add_argument('--attachments-dir', type=pathlib.Path,
                        help='Attachment directory (default: <output_stem>_attachments)')
    args = parser.parse_args()
    SRC = args.source.expanduser().resolve()
    if not SRC.is_file():
        parser.error(f'Input file does not exist: {SRC}')
    OUT = args.output or SRC.with_name('property_emails_compact.md')
    INDEX = args.index or OUT.with_name('property_email_source_index.csv')
    OUT = OUT.expanduser().resolve()
    INDEX = INDEX.expanduser().resolve()
    ATTACHMENTS = (args.attachments_dir or OUT.with_name(OUT.stem + '_attachments')).expanduser().resolve()
    manifest = OUT.with_name(OUT.stem + '_attachment_manifest.csv')
    provenance = provenance_path(OUT)
    distinct_paths([SRC], [OUT, INDEX, manifest, provenance])
    if SRC in (OUT, INDEX) or OUT == INDEX:
        parser.error('Source, Markdown output, and source index must use distinct paths.')
    attachment_records = []
    if SRC.suffix.lower() == '.mbox':
        inputs = records_from_mbox(SRC, ATTACHMENTS, attachment_records, [SRC, OUT, INDEX, manifest, provenance])
    elif SRC.suffix.lower() in ('.md', '.txt'):
        raw = SRC.read_text(encoding='utf-8-sig')
        print('WARNING: Markdown input may already have had quoted messages removed. To recover them, run this script on the ORIGINAL .mbox.')
        raw_lines = raw.splitlines(keepends=True)
        allowed = set(outside_body([line.rstrip('\r\n') for line in raw_lines]))
        offsets, offset = set(), 0
        for position, line in enumerate(raw_lines):
            if position in allowed:
                offsets.add(offset)
            offset += len(line)
        starts = [m for m in re.finditer(r'(?m)^## Email (\d+): ', raw) if m.start() in offsets]
        declared = re.search(r'(?m)^Total messages: (\d+)', raw)
        if not declared or int(declared[1]) != len(starts):
            parser.error('Ambiguous legacy Markdown boundaries/count; use the original MBOX or repair explicit body framing')
        inputs = [get_segment(m, starts[i + 1].start() if i + 1 < len(starts) else len(raw), raw)
                  for i, m in enumerate(starts)]
        if len({r['num'] for r in inputs}) != len(inputs):
            parser.error('Duplicate legacy email numbers; repair the source export')
        for record in inputs:
            record['body'] = decode_record(record['body'].splitlines())
    else:
        parser.error('Use a .mbox, .md, or .txt input file.')
    if not inputs:
        parser.error('No emails found in the input file.')

    records=[]
    for r in inputs:
        r['clean']=clean_body(r['body'])
        r['attachment_short']=meaningful_attachments(r['attachments'])
        typ, txt=automation(r, r['clean'])
        if typ=='FULL':
            # additional automatic/vendor platform messages whose content is routine
            subj=r['subject'].lower(); addr=r['from'].lower()
            routine_regex = r'(your appointment is scheduled|service estimate from|appointment confirmation|scheduling reminder|invitation: appointment|your auto.?pay enrollment|online customer service - residential start service)'
            if re.search(routine_regex,subj):
                # Keep anything vendor-related with a substantive description of
                # an issue; otherwise just event + attachment listing.
                if not re.search(r'(?i)\b(leak|bat|rodent|chimney|flue|roof|septic|mold|moisture|sump|damage|failed|repair|rust|guano|insurance claim|fraud|permit|easement)\b',txt):
                    typ='EVENT'; txt='Scheduling/service-system notice; event described in subject.'
        # No reason to keep empty reply references
        if not txt or txt=='[No readable message body]':
            typ='EVENT';txt='No substantive body in export; attachment(s) or subject may contain relevant content.'
        if typ=='FULL' and re.search(r'(?i)^fwd: reminder: schedule your chubb assessment',r['subject']):
            note=txt.split('---------- Forwarded message',1)[0].strip()
            typ='EVENT'
            txt=(note+' | ' if note else '')+'Forwarded Chubb insurance assessment scheduling reminder (original notice: Email 262).'
        # Unnecessary contact details, bank-routing instructions and wire references
        # are not useful for property-condition analysis, but original email
        # number/date/subject/attachment/source ID remain in index.
        if (re.search(r'(?i)purchase agreement and easement', r['subject'])
                and len(r['clean']) < 500
                and len(re.findall(r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b', r['clean'])) >= 2
                and re.search(r'(?i)\b(?:road|street|ave|parkway|blvd|pkwy|dr|lane)\b', r['clean'])):
            typ='EVENT';txt='Provided contact information to retained counsel (personal phone numbers and address omitted).'
        if re.search(r'(?i)wire for house purchase',r['subject']):
            typ='EVENT'
            if re.search(r'(?i)completed this afternoon|wire was completed',r['clean']):
                txt='Closing funds wire confirmed completed; bank and transaction identifiers omitted.'
            elif re.search(r'(?i)closing date is tomorrow|wire transfer today',r['clean']):
                txt='Requested closing wire in advance of scheduled closing; banking instructions omitted.'
            elif re.search(r'(?i)call to confirm the wire',r['clean']):
                txt='Followed up on wire verification call; bank details omitted.'
            else:
                txt='Closing funds/wire coordination; bank instructions, references, and staff contact details omitted.'
        r['type']=typ;r['text']=txt
        records.append(r)


    # Preserve forwarded content in the archive. Display-only repetition matching
    # is performed by the timeline viewer, never destructive shingle elision.

    # Format with source email number stable across source and reduced copy.
    lines=[MARKER,
        '# Property Correspondence — Compact Email Archive',
        '',
        f'Emails represented: {len(records)} (source email numbers are unchanged).',
        f'Source: `{SRC.name}` (compact derivative; original archive should be retained).',
        'Purpose: remove administrative boilerplate and footers while preserving substantive quoted replies and forwarded correspondence.',
        'Reply-history and forwarded content are retained. Repeated wording is collapsed only in the presentation copies. Check original MBOX for all exhibits.',
        'Automated notifications are shortened to event records; they are NOT verbatim quotations.',
        'Authored message text is substantially retained, but this is an automated analysis copy, not the original evidentiary record.',
        'An accompanying CSV maps every email number to its original Message-ID and full subject.',
        'IMPORTANT: Some messages involve legal counsel; review for attorney-client privilege before distribution.',
        ('Attachments are extracted MIME files; inline images are included. Links and a SHA-256 manifest associate files with source emails. External download links are not downloaded. Retain the original MBOX.'
         if SRC.suffix.lower() == '.mbox' else 'IMPORTANT: Markdown input contains attachment names only; extraction requires the original MBOX.'),
        '',
    ]
    for r in records:
        lines.extend([
          f"## Email {r['num']:03d} — {short_date(r['date'])}",
          f"**From:** {r['from']}  ",
          f"**To:** {r['to']}  ",
        ])
        if r['cc']:
            lines.append(f"**Cc:** {r['cc']}  ")
        lines.append(f"**Subject:** {r['subject']}")
        if r['attachment_short']:
            lines.append(f"**Attachments:** {r['attachment_short']}")
        files = [item for item in attachment_records if item['source_email_number'] == r['num']]
        for item in files:
            item['relative_path'] = pathlib.Path(os.path.relpath(ATTACHMENTS / item['saved_filename'], OUT.parent)).as_posix()
        r['attachment_files'] = files
        if files:
            links = ['[' + re.sub(r'[\[\]\r\n]', '_', item['original_filename']) + '](' + quote(item['relative_path'], safe='/') + ')' for item in files]
            lines.append('**Attachment files:** ' + ' · '.join(links))
        if r['type']=='EVENT':
            lines.append('**Type:** Shortened system/admin event')
        elif r['type']=='REFERENCE':
            lines.append('**Type:** Forwarded duplicate (original email preserved in source archive)')
        lines.extend(['',frame_body(r['text']),''])
    destinations = [OUT, INDEX, manifest, provenance]
    distinct_paths([SRC], destinations)
    with staged_outputs(destinations) as stages:
        stages[0].write_text('\n'.join(lines),encoding='utf-8')
        with stages[1].open('w',newline='',encoding='utf-8-sig') as f:
            w=csv.writer(f);w.writerow(['source_email_number','date_original','from','to','cc','full_subject','message_id','original_attachment_listing','representation','original_body_chars','output_body_chars','contains_reply_marker_review_original','attachment_files_json'])
            for r in records:
                body_lines = r['body'].splitlines()
                has_history = any(message_boundary(body_lines, i) for i in range(len(body_lines)))
                w.writerow([r['num'],r['date'],r['from'],r['to'],r['cc'],r['subject'],r['id'],r['attachments'],r['type'],len(r['body']),len(r['text']),has_history,json.dumps(r['attachment_files'],ensure_ascii=False)])
        with stages[2].open('w', newline='', encoding='utf-8-sig') as stream:
            fields = ['source_email_number', 'message_id', 'mime_part', 'original_filename', 'saved_filename',
                      'content_type', 'disposition', 'content_id', 'byte_size', 'sha256', 'relative_path']
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(attachment_records)
        write_generation(stages[-1], stages[0], stages[1], OUT, INDEX, 'gmail', SRC)


    s=Counter(r['type'] for r in records)
    print('Source emails',len(records))
    print('Quoted-reply markers in original:', sum(bool(re.search(r'(?im)^\s*(?:>\s*)*On\s+.{5,350}\bwrote:', r['body'])) for r in records))
    print('Review original emails with quoted text for potential parsing issues; see source index CSV.')
    print('Retained authored messages',s['FULL'])
    print('Shortened event entries',s['EVENT'])
    print('Cross-referenced forwarded copies',s['REFERENCE'])
    print('Cross references',[(r['num'],r.get('duplicate_of')) for r in records if r['type']=='REFERENCE'])
    print('Input bytes',SRC.stat().st_size)
    print('Compact bytes',OUT.stat().st_size)
    print('Source index bytes',INDEX.stat().st_size)
    print('Reduction',round(100*(1-OUT.stat().st_size/SRC.stat().st_size),1),'percent (input vs compact Markdown)')
    print('FILES',OUT,INDEX)


if __name__ == "__main__":
    main()
