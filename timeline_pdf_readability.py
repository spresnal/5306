"""Keep explicit references in place of repeated quotations in PDF exports."""
from html import escape
from html.parser import HTMLParser


def collapse_repeated_quotes(html):
    class Renderer(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=False)
            self.output = []
            self.depth = 0

        def handle_starttag(self, tag, attrs):
            if self.depth:
                if tag == 'details':
                    self.depth += 1
                return
            attrs = dict(attrs)
            if tag == 'details' and 'repeated-history' in attrs.get('class', '').split():
                prior = escape(attrs['data-prior'], quote=True)
                note = escape(attrs.get('data-match-note', ''))
                self.output.append(f'<div class="repeat-reference">Repeated quotation shown in <a href="#{prior}">{prior}</a>{note}. Full quotation remains in the HTML and source archive.</div>')
                self.depth = 1
            else:
                self.output.append(self.get_starttag_text())

        def handle_endtag(self, tag):
            if self.depth:
                if tag == 'details':
                    self.depth -= 1
            else:
                self.output.append(f'</{tag}>')

        def handle_startendtag(self, tag, attrs):
            if not self.depth:
                self.output.append(self.get_starttag_text())

        def handle_data(self, data):
            if not self.depth:
                self.output.append(data)

        def handle_entityref(self, name):
            self.handle_data(f'&{name};')

        def handle_charref(self, name):
            self.handle_data(f'&#{name};')

        def handle_decl(self, decl):
            if not self.depth:
                self.output.append(f'<!{decl}>')

    renderer = Renderer()
    renderer.feed(html)
    renderer.close()
    if renderer.depth:
        raise ValueError('Unclosed repeated quotation')
    return ''.join(renderer.output)
