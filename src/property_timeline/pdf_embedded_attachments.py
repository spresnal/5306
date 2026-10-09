"""Embed original attachment bytes and attach native PDF paperclip annotations."""
import hashlib
import json
from pathlib import Path
from urllib.parse import unquote
import pymupdf as fitz


def embed_attachments(document, files, source, output, token_targets=None):
    specifications, by_path, manifest = {}, {}, []
    for digest, item in files.items():
        name = item['name']
        embedded_name = digest[:12] + '__' + name
        data = item['path'].read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError('Attachment changed during export: ' + name)
        stream = document.embfile_add(embedded_name, data, filename=name, ufilename=name,
                                     desc='Source records: ' + ', '.join(sorted(item['records'])))
        specification = document.get_new_xref()
        document.update_object(specification, '<</Type/Filespec/F' + fitz.get_pdf_str(name)
                               + '/UF' + fitz.get_pdf_str(name)
                               + f'/EF<</F {stream} 0 R/UF {stream} 0 R>>>>')
        specifications[digest] = specification
        for href in item['hrefs']:
            by_path[str((source.parent / unquote(href)).resolve()).casefold()] = digest
        manifest.append(dict(embedded_name=embedded_name, filename=name, sha256=digest,
                             source_records=sorted(item['records']), source_paths=sorted(item['hrefs'])))
    count = 0
    for page in document:
        for link in page.get_links():
            digest = None
            if link.get('file'):
                path = unquote(link['file'])
                if len(path) > 3 and path[0] == '/' and path[2] == ':':
                    path = path[1:]
                digest = by_path.get(str((output.parent / path).resolve()).casefold())
            elif link.get('uri', '').startswith('https://timeline.invalid/attachment/'):
                token = link['uri'].rsplit('/', 1)[1]
                target = (token_targets or {})[token]
                path = target['path']
                digest = by_path.get(str((output.parent / path).resolve()).casefold())
                if digest != target['digest']:
                    raise ValueError('Attachment token disagrees with validated file')
            if digest is None:
                continue
            item = files[digest]
            rectangle = link['from']
            page.delete_link(link)
            annotation = page.add_file_annot(fitz.Point(max(3, rectangle.x0 - 20), rectangle.y0),
                                             b'reference', item['name'], ufilename=item['name'],
                                             desc=item['name'] + ' | Source records: ' + ', '.join(sorted(item['records'])),
                                             icon='Paperclip')
            document.xref_set_key(annotation.xref, 'FS', f'{specifications[digest]} 0 R')
            annotation.set_colors(stroke=(.2, .4, .65))
            annotation.update()
            if link.get('uri', '').startswith('https://timeline.invalid/attachment/'):
                document.xref_set_key(annotation.xref, 'TimelineReference', fitz.get_pdf_str(token))
                document.xref_set_key(annotation.xref, 'TimelineRecord', fitz.get_pdf_str(target['record']))
            count += 1
    document.embfile_add('timeline_attachment_manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8'),
                         filename='timeline_attachment_manifest.json', desc='Source associations and SHA-256 hashes of embedded originals')
    document.embfile_add('timeline_attachment_references.json', json.dumps(token_targets or {}, sort_keys=True).encode(),
                         filename='timeline_attachment_references.json', desc='Expected clickable reference tokens and source associations')
    document.xref_set_key(document.pdf_catalog(), 'PageMode', '/UseAttachments')
    if files and not count:
        raise ValueError('No paperclip attachment annotations created')
    return count


def verify_embedded(document, files, token_targets=None):
    expected = set(files)
    actual = set()
    for name in document.embfile_names():
        if name not in ('timeline_attachment_manifest.json', 'timeline_attachment_references.json'):
            actual.add(hashlib.sha256(document.embfile_get(name)).hexdigest())
    if expected != actual:
        raise ValueError('Embedded originals do not match attachment hashes')
    expected_manifest = [dict(embedded_name=digest[:12] + '__' + item['name'], filename=item['name'],
                              sha256=digest, source_records=sorted(item['records']), source_paths=sorted(item['hrefs']))
                         for digest, item in files.items()]
    if json.loads(document.embfile_get('timeline_attachment_manifest.json')) != expected_manifest:
        raise ValueError('Embedded attachment provenance manifest differs from HTML')
    count = 0
    seen = set()
    for page in document:
        for annotation in page.annots() or []:
            if annotation.type[0] != fitz.PDF_ANNOT_FILE_ATTACHMENT:
                continue
            digest = hashlib.sha256(annotation.get_file()).hexdigest()
            if digest not in expected:
                raise ValueError('Paperclip refers to an unexpected file')
            if token_targets is not None:
                _, token = document.xref_get_key(annotation.xref, 'TimelineReference')
                _, record = document.xref_get_key(annotation.xref, 'TimelineRecord')
                target = token_targets.get(token)
                if target is None or target['digest'] != digest or target['record'] != record:
                    raise ValueError('Paperclip has the wrong source record or payload')
                seen.add(token)
            count += 1
    if files and not count:
        raise ValueError('No clickable file attachments')
    if token_targets is not None and seen != set(token_targets):
        raise ValueError('Missing clickable attachment occurrences: ' + str(len(set(token_targets) - seen)))
    if token_targets is not None:
        embedded = json.loads(document.embfile_get('timeline_attachment_references.json'))
        if embedded != token_targets:
            raise ValueError('Embedded attachment reference manifest differs from HTML')
    return count
