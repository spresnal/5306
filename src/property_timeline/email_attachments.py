"""Extract MIME attachment bytes with deterministic filenames and provenance."""
import hashlib
import mimetypes
import re
from email.header import decode_header, make_header
from property_timeline.immutable_assets import publish_asset


def extract_attachments(message, email_number, directory, forbidden=()):
    results = []

    def visit(part, mime_path):
        filename = part.get_filename()
        attachment = (filename is not None or part.get_content_disposition() == 'attachment'
                      or (part.get('Content-ID') and part.get_content_maintype() != 'text'))
        if attachment:
            if filename:
                try:
                    filename = str(make_header(decode_header(filename)))
                except (ValueError, LookupError, UnicodeError):
                    filename = str(filename)
            original = filename or ('attached_message.eml' if part.get_content_type() == 'message/rfc822'
                                    else 'unnamed' + (mimetypes.guess_extension(part.get_content_type()) or '.bin'))
            safe = re.sub(r'[^\w. -]', '_', original.replace('\\', '/').split('/')[-1]).strip(' .')[:150] or 'attachment.bin'
            payload = part.get_payload(decode=True)
            if payload is None and part.get_content_type() == 'message/rfc822':
                nested = part.get_payload()
                if isinstance(nested, list):
                    payload = b'\n'.join(item.as_bytes() for item in nested)
            if payload is None:
                raise ValueError(f'Unable to decode attachment in email {email_number}, MIME part {mime_path}')
            suffix = '.' + safe.rsplit('.', 1)[-1][:10] if '.' in safe else ''
            display = safe[:45] + suffix if len(safe) > 55 else safe
            saved = publish_asset(directory, f'email_{email_number:04d}_part_{mime_path.replace(".", "_")[:16]}_{display}',
                                  payload, forbidden)
            results.append(dict(source_email_number=email_number, message_id=str(message.get('Message-ID', '')),
                                mime_part=mime_path, original_filename=original,
                                saved_filename=saved.relative_to(directory.resolve()).as_posix(),
                                content_type=part.get_content_type(), disposition=part.get_content_disposition() or '',
                                content_id=str(part.get('Content-ID', '')), byte_size=len(payload),
                                sha256=hashlib.sha256(payload).hexdigest()))
            return  # Attached .eml is a file, not another outer-message body.
        if part.is_multipart():
            for index, child in enumerate(part.get_payload(), 1):
                visit(child, f'{mime_path}.{index}')

    visit(message, '1')
    return results
