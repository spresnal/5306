"""Verify native record destinations, rendered body text, and file references."""
from html.parser import HTMLParser
import re
import unicodedata
from urllib.parse import unquote


def normalized_text(value):
    value = unicodedata.normalize('NFKC', value).replace('\u00ad', '').replace('\u200b', '')
    return ''.join(re.findall(r'\w+', value))


def expected_bodies(html):
    class Reader(HTMLParser):
        def __init__(self):
            super().__init__()
            self.record = None
            self.records = {}
            self.body_depth = 0
            self.hidden = 0
            self.parts = []

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == 'article':
                self.record = attrs['id']
                if self.record in self.records:
                    raise ValueError('Duplicate record ID: ' + self.record)
                self.records[self.record] = []
            if tag == 'div' and (self.body_depth or 'body' in attrs.get('class', '').split()):
                self.body_depth += 1
            if tag == 'span' and (self.hidden or any(name in attrs.get('class', '').split()
                                                     for name in ('quote-marker', 'quoted-raw-prefix'))):
                self.hidden += 1

        def handle_data(self, data):
            if self.body_depth and not self.hidden:
                self.parts.append(data)

        def handle_endtag(self, tag):
            if tag == 'span' and self.hidden:
                self.hidden -= 1
            if tag == 'div' and self.body_depth:
                self.body_depth -= 1
                if not self.body_depth:
                    self.records[self.record].append(''.join(self.parts))
                    self.parts = []
    reader = Reader()
    reader.feed(html)
    return reader.records


def record_destinations(document, identifiers):
    names = {unquote(name): value for name, value in document.resolve_names().items()}
    missing = set(identifiers) - set(names)
    if missing:
        raise ValueError('Missing native PDF record destinations: ' + ', '.join(sorted(missing)[:8]))
    result = {}
    for number, page in enumerate(document):
        for link in page.get_links():
            identifier = unquote(link.get('nameddest', ''))
            if identifier not in names or identifier not in identifiers or identifier in result:
                continue
            label = normalized_text(page.get_text(clip=link['from']))
            if label != normalized_text(identifier):
                continue  # Same-subject navigation labels include Earlier/Later.
            result[identifier] = dict(page=number, to=(link['from'].x0, link['from'].y0))
    missing = set(identifiers) - set(result)
    if missing:
        raise ValueError('Missing record header links: ' + ', '.join(sorted(missing)[:8]))
    return result


def fix_record_destinations(document, destinations):
    import pymupdf as fitz
    # Chromium's named destinations may use its layout coordinates rather than
    # physical PDF coordinates. Rebuild them from the actual record header links.
    entries = []
    for identifier, value in sorted(destinations.items()):
        page = document[value['page']]
        x, y = value['to']
        entries.append(fitz.get_pdf_str(identifier) + f' [{page.xref} 0 R /XYZ {x} {page.rect.height - y} null]')
    destination_xref = document.get_new_xref()
    document.update_object(destination_xref, '<</Names [' + ' '.join(entries) + ']>>')
    kind, value = document.xref_get_key(document.pdf_catalog(), 'Names')
    if kind == 'xref':
        document.xref_set_key(int(value.split()[0]), 'Dests', f'{destination_xref} 0 R')
    else:
        document.xref_set_key(document.pdf_catalog(), 'Names/Dests', f'{destination_xref} 0 R')


def verify_destination_targets(document, destinations):
    names = {unquote(name): value for name, value in document.resolve_names().items()}
    for identifier, header in destinations.items():
        target = names.get(identifier, {})
        point = target.get('to')
        if point is not None and target.get('page') == header['page']:
            # resolve_names returns PDF bottom-origin coordinates; extracted
            # link rectangles use PyMuPDF's top-origin page coordinates.
            import pymupdf as fitz
            point = fitz.Point(*point[:2]) * document[header['page']].transformation_matrix
        if (target.get('page') != header['page'] or point is None
                or any(abs(a - b) > 2 for a, b in zip(point[:2], header['to']))):
            raise ValueError('PDF reference does not point to its record header: ' + identifier
                             + ' target=' + str(target) + ' header=' + str(header))


def verify_record_bodies(document, html):
    records = expected_bodies(html)
    destinations = record_destinations(document, records)
    items = list(records)
    previous = None
    for index, identifier in enumerate(items):
        start = destinations[identifier]
        end = destinations[items[index + 1]] if index + 1 < len(items) else None
        position = (start['page'], start['to'][1])
        if previous is not None and position < previous:
            raise ValueError('Record destinations are out of chronology: ' + identifier)
        previous = position
        pages = []
        last_page = end['page'] if end else len(document) - 1
        for page_number in range(start['page'], last_page + 1):
            page = document[page_number]
            top = max(0, start['to'][1] - 2) if page_number == start['page'] else 0
            bottom = min(page.rect.height, end['to'][1]) if end and page_number == end['page'] else page.rect.height
            if bottom > top:
                text = page.get_text(clip=(0, top, page.rect.width, bottom), sort=True)
                text = re.sub(r'5306 correspondence\s*\|\s*Page \d+ of \d+', '', text)
                pages.append(text)
        rendered = normalized_text('\n'.join(pages))
        for body in records[identifier]:
            expected = normalized_text(body)
            if expected and expected not in rendered:
                raise ValueError('Missing or altered rendered body in ' + identifier + ': ' + body[:80])
    return destinations
