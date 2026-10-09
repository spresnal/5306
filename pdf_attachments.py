"""Collect validated original files and their expected displayed references."""
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit
from attachment_inventory import validate_attachment
from html import escape
import hashlib
import os

PREFIX = 'https://timeline.invalid/attachment/'


def collect_files(html, source):
    class Reader(HTMLParser):
        def __init__(self):
            super().__init__()
            self.record = None
            self.files = {}
            self.counts = {}

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == 'article':
                self.record = attrs.get('id')
            if tag != 'a' or 'file-link' not in attrs.get('class', '').split():
                return
            href = attrs['href']
            url = urlsplit(href)
            if url.scheme or url.netloc or self.record is None:
                raise ValueError('Attachment reference must belong to a record and a local file')
            expected = dict(relative_path=unquote(url.path), sha256=attrs.get('data-sha256'),
                            byte_size=attrs.get('data-byte-size'))
            path = validate_attachment(expected, source.parent)
            digest = expected['sha256']
            item = self.files.setdefault(digest, dict(path=path, type=attrs.get('data-file-type', ''),
                                                     name=attrs.get('data-filename', path.name),
                                                     hrefs=set(), records=set(), references={}))
            item['hrefs'].add(href)
            item['records'].add(self.record)
            item['references'][self.record] = item['references'].get(self.record, 0) + 1

        def handle_endtag(self, tag):
            if tag == 'article':
                self.record = None
    reader = Reader()
    reader.feed(html)
    return reader.files


def tokenize_file_links(html, source, output):
    """Give every displayed attachment occurrence its own verifiable token."""
    class Renderer(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=False)
            self.record = None
            self.output = []
            self.targets = {}

        def handle_starttag(self, tag, attrs):
            values = dict(attrs)
            if tag == 'article':
                self.record = values['id']
            if tag == 'a' and 'file-link' in values.get('class', '').split():
                href = values['href']
                token = hashlib.sha256((self.record + '\0' + href + '\0' + str(len(self.targets))).encode()).hexdigest()
                self.targets[token] = dict(path=os.path.relpath(source.parent / unquote(href), output.parent),
                                           record=self.record, digest=values['data-sha256'])
                attrs = [(key, PREFIX + token if key == 'href' else value) for key, value in attrs]
                self.output.append('<a' + ''.join(' ' + key + ('="' + escape(value, quote=True) + '"' if value is not None else '') for key, value in attrs) + '>')
            else:
                self.output.append(self.get_starttag_text())

        def handle_endtag(self, tag):
            self.output.append('</' + tag + '>')
            if tag == 'article':
                self.record = None

        def handle_startendtag(self, tag, attrs):
            self.output.append(self.get_starttag_text())

        def handle_data(self, value):
            self.output.append(value)

        def handle_entityref(self, name):
            self.output.append('&' + name + ';')

        def handle_charref(self, name):
            self.output.append('&#' + name + ';')

        def handle_decl(self, value):
            self.output.append('<!' + value + '>')
    renderer = Renderer()
    renderer.feed(html)
    return ''.join(renderer.output), renderer.targets
