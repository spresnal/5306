"""Read GilApps HTML exports, retaining message order and local attachment links."""
from html.parser import HTMLParser
from pathlib import Path
from datetime import datetime
from urllib.parse import unquote, urlsplit
import hashlib
import mimetypes


class ExportParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.messages = []
        self.current = None
        self.day = ''
        self.days = []
        self.day_parts = []
        self.pending_link = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get('class', '').split()
        if 'header_text' in classes:
            self.day_parts = []
        if 'chat_box' in classes:
            if self.current is not None:
                raise ValueError('Nested message box')
            self.current = dict(day=self.day, sender='', time='', body=[], files=[], line=self.getpos()[0])
        if self.current is not None:
            if tag == 'a' and attrs.get('href'):
                self.pending_link = dict(path=attrs['href'], attached=False, body_start=len(self.current['body']))
            elif tag == 'img' and 'attachment' in classes:
                name = attrs.get('alt', '')
                if self.pending_link:
                    self.current['files'].append(dict(path=self.pending_link['path'], name=name))
                    self.pending_link['attached'] = True
                elif not attrs.get('src', '').startswith('data:'):
                    self.current['files'].append(dict(path=attrs.get('src', ''), name=name))
                else:
                    raise ValueError('Embedded attachment without original-file link')
                self.current['body'].append('\n📄 ' + name + '\n')
            elif tag in ('br', 'p', 'li'):
                self.current['body'].append('\n')
        if tag not in ('img', 'br', 'hr', 'meta', 'link', 'input'):
            self.stack.append((tag, classes))

    def handle_data(self, text):
        classes = [value for _, values in self.stack for value in values]
        if 'header_text' in classes:
            self.day_parts.append(text)
        elif self.current is not None:
            if 'res_title' in classes or 'sent_title' in classes:
                self.current['sender'] += text
            elif 'time' in classes:
                self.current['time'] += text
            elif text.strip():
                self.current['body'].append(text)

    def handle_endtag(self, tag):
        if tag in ('img', 'br', 'hr', 'meta', 'link', 'input'):
            return
        if not self.stack or self.stack[-1][0] != tag:
            raise ValueError(f'Unbalanced HTML at line {self.getpos()[0]}: {tag}')
        _, classes = self.stack.pop()
        if tag == 'a' and self.pending_link and self.current:
            link = self.pending_link
            if not link['attached']:
                label = ''.join(self.current['body'][link['body_start']:])
                if link['path'] not in label:
                    self.current['body'].append(' (' + link['path'] + ')')
            self.pending_link = None
        if 'header_text' in classes:
            self.day = ''.join(self.day_parts).strip()
            self.days.append(self.day)
        if tag in ('p', 'li') and self.current:
            self.current['body'].append('\n')
        if 'chat_box' in classes:
            self.current['end_line'] = self.getpos()[0]
            self.messages.append(self.current)
            self.current = None


def read_export(raw, source, parse_text):
    parser = ExportParser()
    parser.feed(raw)
    if parser.stack or parser.current:
        raise ValueError('Incomplete HTML export')
    synthetic = []
    previous_day = None
    files = {}
    for number, item in enumerate(parser.messages, 1):
        if item['day'] != previous_day:
            datetime.strptime(item['day'], '%A, %b %d, %Y')
            synthetic.append('--- ' + item['day'] + ' ---')
            previous_day = item['day']
        synthetic.extend([item['sender'].strip() + ' (' + item['time'].strip() + ')', ''.join(item['body']).strip(), ''])
        files[number] = []
        for attachment in item['files']:
            url = urlsplit(attachment['path'])
            if url.scheme or url.netloc:
                raise ValueError('Attachment must be a local relative path')
            path = (source.parent / unquote(url.path)).resolve()
            if not path.is_relative_to(source.parent):
                raise ValueError('Attachment path leaves export directory')
            available = path.is_file()
            files[number].append(dict(original_filename=attachment['name'] or path.name,
                                      relative_path=path.relative_to(source.parent).as_posix(),
                                      content_type=mimetypes.guess_type(path.name)[0] or 'application/octet-stream',
                                      byte_size=path.stat().st_size if available else 0,
                                      sha256=hashlib.sha256(path.read_bytes()).hexdigest() if available else '',
                                      available=available))
    messages, anomalies = parse_text('\n'.join(synthetic))
    if len(messages) != len(parser.messages):
        raise ValueError('HTML message count mismatch')
    for message, item in zip(messages, parser.messages):
        message.header_line = item['line']
        message.body_line_start = item['line']
        message.body_line_end = item['end_line']
    return messages, anomalies, files
