"""Offline HTML presentation for combine_timeline records."""

from html import escape
from importlib.resources import files as resource_files
from pathlib import Path
from urllib.parse import quote
import os
from datetime import datetime
from zoneinfo import ZoneInfo
import re
from email.utils import parseaddr, parsedate_to_datetime, getaddresses
import json
from property_timeline.email_signatures import strip_signature
from property_timeline.email_parsing import quoted_headers, reply_marker, message_boundary
from property_timeline.signature_attachments import is_signature_attachment
from property_timeline.attachment_inventory import validate_attachment


def participant_names(value):
    """Use supplied display names; keep addresses when no name was supplied."""
    if '@' not in value:
        return value.strip()
    value = re.sub(r'<mailto:[^>]+>', '', value)
    return ', '.join(name or address for name, address in getaddresses([value]) if name or address)


def email_sections(body):
    """Recognize explicit reply/forward markers, without inferring authorship."""
    lines = body.splitlines(keepends=True)
    boundaries = {}
    for i, line in enumerate(lines):
        plain = re.sub(r'^\s*(?:>\s*)*', '', line).strip()
        if re.match(r'^-{2,}\s*(?:Forwarded message|Original Message)\s*-*$', plain, re.I):
            boundaries[i] = 'Forwarded / earlier message'
        elif plain.startswith('From:') and message_boundary(lines, i):
            # Outlook chains often have no forward separator or quote glyphs.
            if i == 0 or not re.match(r'^-{2,}\s*(?:Forwarded message|Original Message)', re.sub(r'^\s*(?:>\s*)*', '', lines[i - 1]).strip(), re.I):
                boundaries[i] = 'Quoted / earlier message'
        elif (marker := reply_marker(lines, i)):
            boundaries[i] = marker[0]
        elif (re.match(r'^\s*>\s+', line)
              and not boundaries
              and not any(re.match(r'^\s*>\s+', earlier) for earlier in lines[:i])):
            # Standalone quoted material has no reliably identified author.
            boundaries[i] = 'Quoted material — speaker not identified by a reply header'
    if not boundaries:
        return body, []
    starts = sorted(boundaries)
    opening = ''.join(lines[:starts[0]])
    history = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(lines)
        label = boundaries[start]
        if label in ('Forwarded / earlier message', 'Quoted / earlier message'):
            forwarded_date = None
            for line in lines[start + 1:min(end, start + 8)]:
                plain = re.sub(r'^\s*(?:>\s*)*', '', line).strip()
                if plain.startswith('From:'):
                    label += ' · ' + plain
                elif plain.startswith('Date:'):
                    forwarded_date = plain[5:].strip()
            if forwarded_date:
                label += ' · Date as quoted: ' + forwarded_date
        history.append((label, ''.join(lines[start:end])))
    # A reply header may wrap only another forwarded message. It provides
    # nesting context, not an independently authored passage.
    merged = []
    index = 0
    while index < len(history):
        label, text = history[index]
        plain_text = ' '.join(re.sub(r'^\s*(?:>\s*)*', '', line).strip()
                              for line in text.splitlines()).strip()
        if (label.startswith('On ') and ' '.join(plain_text.split()) == ' '.join(label.split())
                and index + 1 < len(history)):
            next_label, next_text = history[index + 1]
            history[index + 1] = (next_label + ' · Enclosing reply header (no separate text): ' + label,
                                  text + next_text)
        else:
            merged.append((label, text))
        index += 1
    return opening, merged


def canonical_text(text):
    text = re.sub(r'<mailto:[^>]+>', '', text)
    return ' '.join(re.sub(r'^\s*(?:>\s*)*', '', line).strip()
                    for line in text.splitlines()).split()


def history_content(text):
    return quoted_headers(text)[3]


def quoted_identity(text):
    """Read explicit sender and minute; never infer identity from body wording."""
    fields, wrappers, _, _ = quoted_headers(text)
    sender = fields.get('From', '')
    date = fields.get('Sent') or fields.get('Date', '')
    if not sender and wrappers:
        wrapper = re.sub(r'<mailto:[^>]+>', '', wrappers[-1])
        match = re.fullmatch(r'On (.+?\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AP]M)?(?:\s+[+-]\d{4})?) (.+? <[^>]+>) wrote:', wrapper, re.I)
        if match:
            date, sender = match.groups()
    address = parseaddr(re.sub(r'<mailto:[^>]+>', '', sender))[1].casefold()
    date = ' '.join(date.replace(' at ', ' ').split())
    # Gmail mobile replies put a comma between the year and clock time.
    # Normalize that separator before parsing; retain the AM/PM marker.
    date = re.sub(r'(\b\d{4}),\s*(?=\d{1,2}:\d{2})', r'\1 ', date)
    stamp = None
    for fmt in ('%a, %b %d, %Y %I:%M %p', '%A, %B %d, %Y %I:%M %p',
                '%a, %d %B %Y %H:%M:%S', '%A, %d %B %Y %H:%M:%S'):
        try:
            stamp = datetime.strptime(date, fmt)
            break
        except ValueError:
            pass
    if stamp is None and not re.search(r'\b(?:AM|PM)\b', date, re.I):
        # RFC parsing ignores AM/PM; use it only for 24-hour header dates.
        try:
            stamp = parsedate_to_datetime(date)
        except (ValueError, TypeError, IndexError):
            pass
    if stamp is not None and stamp.tzinfo is not None:
        stamp = stamp.astimezone(ZoneInfo('America/New_York')).replace(tzinfo=None)
    return address, stamp.replace(second=0, microsecond=0) if stamp else None


def prior_quote(text, earlier_emails):
    match = matched_quote(text, earlier_emails)
    return match[0] if match else None


def matched_quote(text, earlier_emails):
    content = ' '.join(canonical_text(strip_signature(history_content(text))))
    if not content:
        return None
    sender, minute = quoted_identity(text)
    fields, _, _, _ = quoted_headers(text)
    name = ' '.join(fields.get('From', '').strip('"\' ').casefold().split())
    # Outlook sometimes supplies only a full display name. Resolve it only
    # when earlier records associate that exact name with one email address.
    addresses = {entry['sender'] for entry in earlier_emails
                 if name and entry.get('sender_name') == name and '@' in entry['sender']}
    if '@' not in sender and len(addresses) == 1:
        sender = next(iter(addresses))
    for earlier in earlier_emails:
        passages = earlier.get('passages')
        if passages is None:
            passages = [dict(text=earlier['opening'], sender=earlier['sender'],
                             minute=earlier['minute'], fields=earlier.get('fields', {}))]
        for passage in passages:
            if not ('@' in sender and minute and passage['minute']
                    and sender == passage['sender']
                    and abs((minute - passage['minute']).total_seconds()) <= 60
                    and content == passage['text']):
                continue
            if any(normalized_header(k, v) != normalized_header(k, passage['fields'][k])
                   for k, v in fields.items() if k in ('Subject', 'To', 'Cc') and k in passage['fields']):
                continue
            return earlier['id'], passage
    return None


def normalized_header(key, value):
    value = re.sub(r'<mailto:[^>]+>', '', value)
    if key in ('To', 'Cc'):
        return tuple(sorted(address.casefold() for _, address in getaddresses([value])))
    return re.sub(r'^(?:(?:re|fw|fwd):\s*)+', '', value.strip(), flags=re.I).casefold()


def attachment_preview(item, href, context=False):
    name = escape(item['original_filename'])
    url = escape(href, quote=True)
    kind = item.get('content_type', '')
    visual = '<span class="file-icon">' + ('PDF' if kind == 'application/pdf' else 'FILE') + '</span>'
    if kind in ('image/png', 'image/jpeg', 'image/gif', 'image/webp'):
        visual = f'<img class="attachment-thumb" src="{url}" alt="Preview of {name}" loading="lazy">'
    pdf = ''
    if kind == 'application/pdf':
        pdf = f'<details class="pdf-preview"><summary>Preview PDF</summary><iframe data-src="{url}#page=1&view=FitH" title="PDF preview: {name}" loading="lazy"></iframe><span>Browser preview; open the file if unavailable.</span></details>'
    return '<div class="attachment-preview' + (' contextual' if context else '') + '"><a class="file-link" data-sha256="' + escape(item['sha256'], quote=True) + '" data-byte-size="' + str(item['byte_size']) + '" data-file-type="' + escape(kind, quote=True) + '" data-filename="' + escape(item['original_filename'], quote=True) + '" href="' + url + '">' + visual + '<span>' + name + '<small>' + str(item['byte_size']) + ' bytes · Click to view</small></span></a>' + pdf + '</div>'


def referenced_attachments(text, files):
    matches = []
    for item, href in files:
        name = item['original_filename']
        cid = item.get('content_id', '').strip('<>')
        if (len(name) >= 5 and re.search(r'(?<![\w.])' + re.escape(name) + r'(?![\w.])', text, re.I)) or (cid and ('cid:' + cid).casefold() in text.casefold()):
            matches.append(attachment_preview(item, href, context=True))
    return '<div class="referenced-files"><div class="history-note">Referenced files</div>' + ''.join(matches) + '</div>' if matches else ''


def email_body_html(body, sender, event=False, earlier_email_text=(), files=(), controls_html='', attachments_html=''):
    opening, history = email_sections(body)
    opening = strip_signature(opening)
    rendered = '<div class="email-opening">' + ('<div class="speaker-label">Shortened event record</div>' if event else '')
    rendered += '<div class="body email-segment">' + escape(opening) + '</div>' + referenced_attachments(opening, files) + '</div>'
    rendered += attachments_html
    if history or controls_html:
        rendered += '<div class="email-utilities">'
    if history:
        unseen = []
        prior_references = []
        for _, text in history:
            prior = prior_quote(text, earlier_email_text)
            prior_references.append(prior)
            unseen.append(prior is None)
        open_attribute = ' open' if any(unseen) else ''
        rendered += f'<details class="email-history"{open_attribute}><summary>Quoted / forwarded messages · {len(history)}</summary>'
        for (label, text), is_unseen, prior in zip(history, unseen, prior_references):
            fields, wrappers, header_text, message_text = quoted_headers(text)
            message_text = strip_signature(message_text)
            # Keep the original glyphs in the DOM/source while suppressing
            # repetitive quote prefixes in the reading and print views.
            readable = ''.join(
                ('<span class="quote-marker" aria-hidden="true">' + escape(match.group()) + '</span>' + escape(line[match.end():]))
                if (match := re.match(r'^\s*(?:> ?)+', line)) else escape(line)
                for line in message_text.splitlines(keepends=True))
            readable = '<span class="quoted-raw-prefix" aria-hidden="true">' + escape(header_text) + '</span>' + readable
            heading = participant_names(fields['From']) if fields.get('From') else label
            context = '<div class="quoted-metadata">' + ''.join('<div><strong>' + escape(k) + ':</strong> ' + escape(participant_names(v) if k in ('To', 'Cc') else v) + (' (as quoted; zone unverified)' if k in ('Date', 'Sent') else '') + '</div>' for k, v in fields.items() if k != 'From') + '</div>'
            context += ''.join('<div class="history-note">Enclosing header: ' + escape(wrapper) + '</div>' for wrapper in wrappers) if fields else ''
            raw_headers = '<details class="original-headers"><summary>Original quoted headers</summary><pre>' + escape(header_text) + '</pre></details>' if header_text.strip() else ''
            passage = '<section class="quoted-passage"><div class="speaker-label">' + escape(heading) + '</div>' + context + '<div class="body email-segment">' + readable + '</div>' + referenced_attachments(text, files) + raw_headers + '</section>'
            if prior:
                _, quoted_minute = quoted_identity(text)
                _, previous = matched_quote(text, earlier_email_text)
                discrepancy = ' · Quoted time differs by one minute from referenced passage' if quoted_minute != previous['minute'] else ''
                quoted_sender, _ = quoted_identity(text)
                if '@' not in quoted_sender:
                    discrepancy += ' · Sender matched by full display name; quoted header has no address'
                rendered += '<details class="repeated-history" data-prior="' + escape(prior, quote=True) + '" data-match-note="' + escape(discrepancy, quote=True) + '"><summary>Previously shown · <a href="#' + escape(prior, quote=True) + '">' + escape(prior) + '</a>' + escape(discrepancy) + ' · expand original quotation</summary>' + passage + '</details>'
            else:
                rendered += passage
        rendered += '</details>'
    if history or controls_html:
        rendered += controls_html + '</div>'
    return rendered


def write_html(records, email_index, phone_zone, destination, compact_record, android_index=None, iphone_index=None, pdf_destination=None, ai_destination=None, ai_summary='Refresh the timeline to generate the AI review package.'):
    cards = []
    earlier_email_text = []
    subject_groups = {}
    email_subjects = {}
    for record in records:
        if record['origin'] == 'gmail':
            metadata = email_index.get(record['number'], {})
            subject = metadata.get('full_subject', '')
            if not subject:
                match = re.search(r'^\*\*Subject:\*\*\s*(.*)', record['text'], re.M)
                subject = match.group(1) if match else ''
            normalized = re.sub(r'^(?:(?:re|fw|fwd):\s*)+', '', subject.strip(), flags=re.I).casefold()
            if normalized:
                subject_groups.setdefault(normalized, []).append(record['id'])
                email_subjects[record['id']] = normalized
    for record in records:
        metadata = email_index.get(record["number"], {}) if record["origin"] == "gmail" else {}
        compact = compact_record(record, metadata).splitlines()
        split = compact.index("")
        fields = compact[1:split]
        field_map = dict(field.split(': ', 1) for field in fields)
        sender = field_map.get('From', 'Unknown sender')
        subject = field_map.get('Subject', 'Group message' if record['origin'] == 'android' else 'Text message')
        body = "\n".join(compact[split + 1:])
        local = record['utc'].astimezone(ZoneInfo('America/New_York')) if record['utc'] else None
        day = local.strftime('%Y-%m-%d') if local else record['displayed'][:10]
        stamp = local.strftime('%H:%M %Z') if local else record['displayed']
        source = quote(Path(os.path.relpath(record["path"], destination.parent)).as_posix(), safe="/")
        display_name = parseaddr(sender)[0] or sender
        speaker = {'Sam': 'sam', 'Regina': 'regina', 'Darcy': 'darcy'}.get(display_name.split()[0] if display_name.split() else '', 'other')
        metadata_html = ''.join('<dt>' + escape(field.split(': ', 1)[0]) + '</dt><dd>' + escape(field.split(': ', 1)[1]) + '</dd>' for field in fields)
        preview_files = []
        attachments_html = ''
        if record['origin'] != 'gmail':
            metadata_html = '<div class="sms-participants"><strong>' + escape(sender) + '</strong> → ' + escape(field_map.get('To', '')) + '</div>'
        else:
            metadata_html = '<details class="email-details"><summary class="sms-participants email-participants"><span class="participant-disclosure" aria-hidden="true">▶</span><strong>' + escape(participant_names(sender)) + '</strong> → ' + escape(participant_names(field_map.get('To', '')))
            if field_map.get('Cc'):
                metadata_html += '<span class="email-cc">Cc: ' + escape(participant_names(field_map['Cc'])) + '</span>'
            metadata_html += '</summary><div class="email-people"><strong>From: ' + escape(sender) + '</strong><span>To: ' + escape(field_map.get('To', '')) + '</span>' + ('<span>Cc: ' + escape(field_map['Cc']) + '</span>' if field_map.get('Cc') else '') + '</div>'
            extras = {k: v for k, v in field_map.items() if k not in ('From', 'To', 'Cc', 'Subject', 'Attachment files', 'Attachments')}
            if extras:
                metadata_html += '<dl>' + ''.join('<dt>' + escape(k) + '</dt><dd>' + escape(v) + '</dd>' for k, v in extras.items()) + '</dl>'
            metadata_html += '</details>'
            files = json.loads(metadata.get('attachment_files_json') or '[]')
            for item in files:
                validate_attachment(item, record['path'].parent)
            files = [item for item in files if not is_signature_attachment(item, record['path'].parent)]
            if files:
                attachments_html += '<details class="attachment-links" open><summary>Attached files · ' + str(len(files)) + '</summary><div class="attachment-grid">'
                for item in files:
                    path = record['path'].parent / item['relative_path']
                    href = quote(Path(os.path.relpath(path, destination.parent)).as_posix(), safe='/')
                    preview_files.append((item, href))
                    attachments_html += attachment_preview(item, href)
                attachments_html += '</div></details>'
        body_html = '<div class="body">' + escape(body) + '</div>'
        if record['origin'] in ('android', 'iphone'):
            index = (android_index if record['origin'] == 'android' else iphone_index) or {}
            files = json.loads(index.get(record['number'], {}).get('attachment_files_json') or '[]')
            if files:
                body_html += '<div class="sms-attachments">'
                for item in files:
                    validate_attachment(item, record['path'].parent)
                    path = record['path'].parent / item['relative_path']
                    href = quote(Path(os.path.relpath(path, destination.parent)).as_posix(), safe='/')
                    if item.get('available', True):
                        body_html += attachment_preview(item, href, context=True)
                    else:
                        body_html += '<div class="history-note">File unavailable: ' + escape(item['original_filename']) + '</div>'
                body_html += '</div>'
        if record['origin'] == 'gmail' and record['utc'] is not None:
            opening, _ = email_sections(body)
            passages = [dict(text=' '.join(canonical_text(strip_signature(opening))),
                             sender=parseaddr(sender)[1].casefold(), minute=local.replace(tzinfo=None, second=0, microsecond=0),
                             fields={'Subject': subject, 'To': field_map.get('To', ''), 'Cc': field_map.get('Cc', '')})]
            for _, quoted in email_sections(body)[1]:
                quoted_sender, minute = quoted_identity(quoted)
                quoted_fields = quoted_headers(quoted)[0]
                if '@' not in quoted_sender:
                    name = participant_names(quoted_fields.get('From', '')).casefold()
                    known = {entry['sender'] for entry in earlier_email_text if entry['sender_name'] == name}
                    if len(known) == 1:
                        quoted_sender = next(iter(known))
                passages.append(dict(text=' '.join(canonical_text(strip_signature(history_content(quoted)))),
                                     sender=quoted_sender, minute=minute, fields=quoted_fields))
            earlier_email_text.append(dict(id=record['id'], text=passages[0]['text'], passages=passages,
                                           opening=' '.join(canonical_text(strip_signature(opening))),
                                           sender=parseaddr(sender)[1].casefold(),
                                           sender_name=' '.join(parseaddr(sender)[0].casefold().split()),
                                           minute=local.replace(tzinfo=None, second=0, microsecond=0)))
        navigation_html = ''
        if record['id'] in email_subjects:
            related = subject_groups[email_subjects[record['id']]]
            position = related.index(record['id'])
            links = []
            if position > 0:
                links.append(f'<a href="#{related[position - 1]}">Earlier: {related[position - 1]}</a>')
            if position + 1 < len(related):
                links.append(f'<a href="#{related[position + 1]}">Later: {related[position + 1]}</a>')
            if links:
                navigation_html = '<nav class="subject-links" aria-label="Same-subject emails">Same subject · ' + ' · '.join(links) + '</nav>'
        source_html = (f'Archived time: {escape(record["displayed"])} · '
                       f'<a href="{escape(source, quote=True)}">{escape(record["path"].name)}</a>, '
                       f'lines {record["line_start"]}–{record["line_end"]}')
        if record['origin'] == 'gmail':
            source_html = '<details class="source-details"><summary>Source details</summary><div>' + source_html + '</div></details>'
            # Match only against earlier records, excluding the entry just indexed.
            prior_emails = earlier_email_text[:-1] if record['utc'] is not None else earlier_email_text
            body_html = email_body_html(body, sender, 'Shortened' in field_map.get('Type', ''),
                                        prior_emails, preview_files, navigation_html + source_html, attachments_html)
            attachments_html = ''
            navigation_html = ''
            footer_html = ''
        else:
            footer_html = '<footer>' + source_html + '</footer>'
        cards.append(f'''<article id="{record['id']}" data-date="{day}" data-origin="{record['origin']}" class="card {record['origin']} speaker-{speaker}">
<header class="record-top"><span class="badge">{record['origin']}</span><a class="id" href="#{record['id']}">{record['id']}</a><time>{escape(stamp)}</time></header>
{('<h3>' + escape(subject) + '</h3>') if record['origin'] == 'gmail' else ''}
{metadata_html}
{body_html}
{attachments_html}
{navigation_html}
{footer_html}
</article>''')
    document = resource_files('property_timeline.resources').joinpath('timeline_viewer.html').read_text(encoding='utf-8')
    content = []
    unknown_started = False
    current_group = None
    conversation_open = False
    previous = None
    for record, card in zip(records, cards):
        local = record['utc'].astimezone(ZoneInfo('America/New_York')) if record['utc'] else None
        day = local.strftime('%Y-%m-%d') if local else record['displayed'][:10]
        continues = (previous is not None and record['origin'] != 'gmail'
                     and previous['origin'] == record['origin']
                     and previous['path'] == record['path']
                     and previous['utc'] is not None and record['utc'] is not None
                     and previous['utc'].astimezone(ZoneInfo('America/New_York')).strftime('%Y-%m-%d') == day
                     and (record['utc'] - previous['utc']).total_seconds() <= 3600)
        email_continues = (previous is not None and record['origin'] == previous['origin'] == 'gmail'
                           and record['utc'] is not None and previous['utc'] is not None
                           and previous['utc'].astimezone(ZoneInfo('America/New_York')).strftime('%Y-%m-%d') == day
                           and record['id'] in email_subjects and previous['id'] in email_subjects
                           and email_subjects[record['id']] == email_subjects[previous['id']])
        continues = continues or email_continues
        if conversation_open and not continues:
            content.append('</div>')
            conversation_open = False
        if record["utc"] is None:
            if not unknown_started:
                if current_group is not None:
                    content.append('</section>')
                    current_group = None
                content.append('<div id="unknown" class="section"><h2>Emails with unspecified time zones</h2>Displayed dates only; placement relative to the chronology is unknown.</div>')
                unknown_started = True
            card = card.replace('data-origin=', 'data-unknown="true" data-origin=', 1)
        group = (record['utc'] is None, day)
        if group != current_group:
            if current_group is not None:
                content.append('</section>')
            title = datetime.strptime(day, '%Y-%m-%d').strftime('%A, %B %d, %Y').replace(' 0', ' ')
            content.append(f'<section class="day-group"><div class="day"><h2>{title}</h2><span class="day-count">{"Time zone unspecified" if local is None else "Eastern time"}</span></div>')
            current_group = group
        if record['origin'] != 'gmail' and not conversation_open:
            label = 'Android group conversation' if record['origin'] == 'android' else 'iPhone conversation'
            content.append(f'<div class="conversation"><div class="conversation-title">{label}</div>')
            conversation_open = True
        elif record['origin'] == 'gmail' and record['utc'] is not None and not conversation_open:
            subject = email_index.get(record['number'], {}).get('full_subject', '')
            if not subject:
                match = re.search(r'^\*\*Subject:\*\*\s*(.*)', record['text'], re.M)
                subject = match.group(1) if match else 'Email correspondence'
            title = re.sub(r'^(?:(?:re|fw|fwd):\s*)+', '', subject, flags=re.I)
            content.append('<div class="conversation email-conversation"><div class="conversation-title">Email conversation · ' + escape(title) + '</div>')
            conversation_open = True
        content.append(card)
        previous = record
    if conversation_open:
        content.append('</div>')
    if current_group is not None:
        content.append('</section>')
    # Replace template markers in one pass so source text cannot become a marker.
    values = {"COUNT": str(len(records)), "ZONE": escape(phone_zone), "CONTENT": "\n".join(content), 'PDF_URL': quote((pdf_destination or destination.with_suffix('.pdf')).name),
              'AI_URL': quote((ai_destination or destination.with_name(destination.stem + '_ai.zip')).name),
              'AI_SUMMARY': escape(ai_summary)}
    document = re.sub(r"\b(?:COUNT|ZONE|CONTENT|PDF_URL|AI_URL|AI_SUMMARY)\b", lambda match: values[match.group()], document)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(document, encoding="utf-8")
