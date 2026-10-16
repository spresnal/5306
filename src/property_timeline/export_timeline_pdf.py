#!/usr/bin/env python3
"""Export the complete HTML chronology directly to PDF using Chrome/Edge.

Run with Windows Python and PyMuPDF. Original attachments are embedded.
"""
from importlib.resources import files as resource_files
import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile
from html import escape, unescape
from urllib.parse import unquote
import pymupdf as fitz
from PIL import Image, ImageOps
from property_timeline.pdf_attachments import collect_files, PREFIX, tokenize_file_links
from property_timeline.timeline_pdf_readability import collapse_repeated_quotes
import hashlib
from property_timeline.pdf_embedded_attachments import embed_attachments, verify_embedded
from property_timeline.output_safety import distinct_paths, staged_outputs
from property_timeline.pdf_validation import verify_record_bodies, fix_record_destinations, verify_destination_targets


def preview_path(path, assets, variant):
    return assets / (hashlib.sha256(path.read_bytes()).hexdigest() + '_' + variant + '.png')


def image_preview(path, assets):
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image)
        image.thumbnail((280, 280))
        target = preview_path(path, assets, 'small')
        image.convert('RGBA').save(target)
    return target


def render_previews(document, pages, directory):
    if not pages:
        return
    if any(number < 1 or number > len(document) for number in pages):
        raise ValueError('Preview pages must fall within the PDF page count')
    directory.mkdir(parents=True, exist_ok=True)
    for number in pages:
        document[number - 1].get_pixmap(matrix=fitz.Matrix(1.4, 1.4), alpha=False).save(
            directory / f'preview_page_{number:04d}.png')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('html', nargs='?', type=Path, default=Path('output/master_timeline.html'))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--verify-only', action='store_true', help='Check the existing PDF and original-file links')
    parser.add_argument('--self-test', action='store_true', help='Run regression tests, including PyMuPDF tests when installed')
    parser.add_argument('--preview-pages', type=int, nargs='+', help='Save selected 1-based pages as PNGs in the PDF assets folder for visual review')
    args = parser.parse_args()
    if args.self_test:
        from property_timeline.verify import main as verify
        raise SystemExit(verify())
    source = args.html.resolve()
    output = (args.output or source.with_suffix('.pdf')).resolve()
    distinct_paths([source], [output])
    if output.suffix.lower() != '.pdf':
        parser.error('PDF output must use the .pdf extension')
    if args.verify_only:
        html = source.read_text(encoding='utf-8')
        ids = re.findall(r'<article id="([^"]+)"', html)
        with fitz.open(output) as document:
            destinations = verify_record_bodies(document, collapse_repeated_quotes(html))
            verify_destination_targets(document, destinations)
            links = [link for page in document for link in page.get_links()]
            if any(link.get('uri', '').startswith(PREFIX) for link in links):
                raise ValueError('Unresolved attachment links')
            if any(not 0 <= link['page'] < len(document) for link in links if link['kind'] == fitz.LINK_GOTO):
                raise ValueError('Invalid internal destination')
            readable = collapse_repeated_quotes(html)
            files = collect_files(readable, source)
            _, targets = tokenize_file_links(readable, source, output)
            count = verify_embedded(document, files, targets)
            render_previews(document, args.preview_pages, output.with_name(output.stem + '_pdf_assets'))
            print(f'Verified {len(ids)} record bodies and destinations, {len(document)} pages, {len(files)} embedded originals and two manifests, {count} paperclip annotations; all attachment hashes match')
        return
    candidates = [Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')) / 'Google/Chrome/Application/chrome.exe',
                  Path(os.environ.get('PROGRAMFILES(X86)', 'C:/Program Files (x86)')) / 'Microsoft/Edge/Application/msedge.exe']
    browser = next((p for p in candidates if p.exists()), None)
    if browser is None:
        parser.error('Chrome or Edge is required; run this script with Windows Python.')
    text = source.read_text(encoding='utf-8')
    ids = re.findall(r'<article id="([^"]+)"', text)
    collect_files(text, source)  # Check every referenced original, including collapsed history.
    text = collapse_repeated_quotes(text)
    attachment_files = collect_files(text, source)
    distinct_paths([source, *[item['path'] for item in attachment_files.values()]], [output])
    # Render all records and histories independent of the live viewer state.
    text = re.sub(r'<details([^>]*class="(?:email-history|attachment-links|email-details|source-details|intro)"[^>]*)>',
                  lambda m: '<details' + m.group(1) + ('>' if re.search(r'\bopen\b', m.group(1)) else ' open>'), text)
    text = text.replace('loading="lazy"', 'loading="eager"')
    def reflow_body(match):
        inner = re.sub(r'<span class="(?:quote-marker|quoted-raw-prefix)"[^>]*>.*?</span>', '', match.group(2), flags=re.S)
        plain = unescape(inner)
        paragraphs = []
        for paragraph in re.split(r'\n\s*\n', plain):
            lines = paragraph.splitlines()
            output_lines = []
            for line in lines:
                line = line.strip()
                if not output_lines or re.match(r'^(?:[-*•]|\d+[.)])\s', line):
                    output_lines.append(line)
                else:
                    output_lines[-1] += ' ' + line
            paragraphs.append('\n'.join(output_lines))
        return match.group(1) + escape('\n\n'.join(paragraphs)) + '</div>'
    text = re.sub(r'(<div class="body(?: email-segment)?">)(.*?)</div>', reflow_body, text, flags=re.S)
    assets = output.with_name(output.stem + '_pdf_assets')
    assets.mkdir(parents=True, exist_ok=True)
    previews = {}
    for href in set(re.findall(r'href="([^"]+\.pdf)"', text, re.I)):
        path = source.parent / unquote(href)
        if path.resolve() == output or not path.is_file():
            continue
        target = preview_path(path, assets, 'page1')
        try:
            with fitz.open(path) as document:
                if not document.is_encrypted and len(document):
                    document[0].get_pixmap(matrix=fitz.Matrix(.4, .4), alpha=False).save(target)
                    previews[href] = target.as_uri()
        except (RuntimeError, ValueError) as exc:
            print(f'Preview unavailable: {path.name}: {exc}')
    for href, preview in previews.items():
        text = text.replace('href="' + href + '"><span class="file-icon">PDF</span>',
                            'href="' + href + '"><img class="attachment-thumb" src="' + preview + '" alt="PDF first-page preview">')
    for src in set(re.findall(r'<img[^>]*src="([^"]+)"', text)):
        if src.startswith(('data:', 'file:', 'https:', 'http:')):
            continue
        path = source.parent / unquote(src)
        if not path.is_file():
            continue
        try:
            target = image_preview(path, assets)
            text = text.replace('src="' + src + '"', 'src="' + target.as_uri() + '"')
        except (OSError, ValueError):
            pass
    text, link_targets = tokenize_file_links(text, source, output)
    style = '<style>' + resource_files('property_timeline.resources').joinpath('timeline_pdf.css').read_text(encoding='utf-8') + '</style>'
    text = text.replace('</head>', style + '</head>')
    text = text.replace('<p class="intro">A chronological', '<p class="intro">Complete PDF export. Original attachments are included inside this PDF. Double-click a paperclip beside an attachment entry, or use Acrobat\'s Attachments panel to open or save the file. Thumbnails are previews; embedded files retain their original bytes.</p><p class="intro">A chronological')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='timeline-pdf-') as temporary:
        # Keep the render input next to the HTML so local file links resolve.
        render = source.with_name('.' + output.stem + '_pdf_render.html')
        raw_pdf = Path(temporary) / 'render.pdf'
        try:
            render.write_text(text, encoding='utf-8')
            subprocess.run([str(browser), '--headless=new', '--disable-gpu', '--no-pdf-header-footer',
                            '--allow-file-access-from-files', '--no-first-run', '--no-default-browser-check',
                            '--user-data-dir=' + str(Path(temporary) / 'profile'), '--virtual-time-budget=15000',
                            '--print-to-pdf=' + str(raw_pdf), render.as_uri()], check=True, timeout=180,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            with fitz.open(raw_pdf) as document:
                destinations = verify_record_bodies(document, text)
                bookmarks = []
                for number, page in enumerate(document, 1):
                    page_text = page.get_text()
                    for line in page_text.splitlines():
                        if re.fullmatch(r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday), [A-Z][a-z]+ \d{1,2}, \d{4}', line):
                            bookmarks.append([1, line, number])
                resolved = embed_attachments(document, attachment_files, source, output, link_targets)
                fix_record_destinations(document, destinations)
                for number, page in enumerate(document, 1):
                    page.insert_text((45, page.rect.height - 25), f'5306 correspondence | Page {number} of {len(document)}', fontsize=8, color=(.35, .4, .45))
                if bookmarks:
                    document.set_toc(bookmarks)
                document.set_metadata({'title':'5306 Property Correspondence Chronology', 'subject':'Complete correspondence reference; retain original exports and attachments'})
                with staged_outputs([output]) as stages:
                    document.save(stages[0], garbage=4, deflate=True)
                    with fitz.open(stages[0]) as verified:
                        for page in verified:
                            for link in page.get_links():
                                if link.get('uri', '').startswith(PREFIX):
                                    raise ValueError('Unresolved attachment link in final PDF')
                                if link['kind'] == fitz.LINK_GOTO and not 0 <= link['page'] < len(verified):
                                    raise ValueError('Invalid internal PDF link destination')
                        verify_embedded(verified, attachment_files, link_targets)
                        verify_destination_targets(verified, verify_record_bodies(verified, text))
                        render_previews(verified, args.preview_pages, assets)
                        print(f'Verified {verified.embfile_count()} embedded files including two manifests')
                print(f'Exported {len(ids)} records, {len(document)} pages, {resolved} embedded attachment paperclips: {output}')
        finally:
            render.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
