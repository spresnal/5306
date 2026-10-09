#!/usr/bin/env python3
"""Convert a TextPort for iPhone SMS/iMessage PDF into evidence-friendly Markdown.

Preserves message text, sender, timestamps as shown in TextPort, source page
numbers, and attachment placeholders. It does NOT perform OCR or invent missing
attachments/timezones. The input PDF remains unchanged.

Requirements: pip install pymupdf

Example:
    python -m property_timeline.iphone_pdf_to_markdown "chat_Darcy.pdf" --me "Regina"

Outputs (next to the input by default):
    <source_stem>_messages.md
    <source_stem>_index.csv
    <source_stem>_assets/    (only if actual large images are embedded)
"""

import argparse
import csv
import hashlib
import json
import mimetypes
from property_timeline.output_safety import staged_outputs, distinct_paths
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pymupdf as fitz


TIME_PATTERN = (r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
                r"\s+\d{1,2},\s+\d{4}\s+at\s+\d{1,2}:\d{2}\s*[AP]M")
INCOMING = re.compile(r"^(.+?)\s+·\s+(" + TIME_PATTERN + r")$")
OUTGOING = re.compile(r"^(" + TIME_PATTERN + r")$")
DAY_HEADING = re.compile(r"^(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),"
                         r"\s+(?:January|February|March|April|May|June|July|August|"
                         r"September|October|November|December)\s+\d{1,2},\s+\d{4}$")
FOOTER = re.compile(r"^Page\s+\d+\s+of\s+\d+(?:\s+TP-[A-Z0-9-]+)?$|^TP-[A-Z0-9-]+$")
ATTACHMENT_REF = re.compile(
    r"\[(?:Image of |Screenshot of |Video(?: of )?|PDF Document|"
    r"Audio(?: Message)?|Attachment(?: of )?|.*?\bDocument\b[^\]]*|"
    r".*?\bImage\b[^\]]*)[^\]]*\]", flags=re.I
)


@dataclass
class Row:
    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    kind: str = "text"
    image_data: bytes = b""
    image_ext: str = "png"


@dataclass
class Message:
    no: int
    sender: str
    recipient: str
    timestamp_original: str
    timestamp_normalized: str
    page_start: int
    page_end: int
    rows: list = field(default_factory=list)
    attachments: list = field(default_factory=list)


def normalize_whitespace(text):
    return (text.replace("\u202f", " ").replace("\xa0", " ")
            .replace("\u200b", "").strip())


def normalized_time(original):
    try:
        dt = datetime.strptime(original, "%b %d, %Y at %I:%M %p")
        return dt.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return original


def layout_rows(page, page_no, min_image_width):
    """Use text glyph coordinates to restore interleaved emoji/text order."""
    spans = []
    embedded = []
    for block in page.get_text("dict")["blocks"]:
        if block["type"] == 0:
            for line in block["lines"]:
                for sp in line["spans"]:
                    t = normalize_whitespace(sp["text"])
                    # Preserve leading/trailing spaces from text to avoid merging
                    # words separated by inline emojis.
                    original = sp["text"].replace("\u202f", " ").replace("\xa0", " ")
                    if t:
                        spans.append((*sp["bbox"], original))
        elif block["type"] == 1:
            width, height = int(block["width"]), int(block["height"])
            if width >= min_image_width and height >= min_image_width:
                embedded.append(Row(page_no, *block["bbox"], "", kind="image",
                                    image_data=block["image"],
                                    image_ext=block.get("ext", "png")))

    # A text line can be split into several PyMuPDF blocks around an emoji.
    # Recombine by vertical glyph alignment first, then left-to-right.
    spans.sort(key=lambda p: (p[1], p[0]))
    groups = []
    for span in spans:
        if groups and abs(span[1] - groups[-1][0][1]) <= 1.0:
            groups[-1].append(span)
        else:
            groups.append([span])

    rows = []
    for group in groups:
        group.sort(key=lambda x: x[0])
        pieces, last_x1 = [], None
        for x0, y0, x1, y1, content in group:
            if last_x1 is not None and x0 > last_x1 + 5:
                # Preserve visible horizontal spacing in unusual text runs.
                if pieces and not pieces[-1].endswith(" ") and not content.startswith(" "):
                    pieces.append(" ")
            pieces.append(content)
            last_x1 = max(x1, last_x1) if last_x1 is not None else x1
        text = normalize_whitespace("".join(pieces))
        if text:
            rows.append(Row(page_no, min(g[0] for g in group),
                            min(g[1] for g in group), max(g[2] for g in group),
                            max(g[3] for g in group), text))

    rows.extend(embedded)
    return sorted(rows, key=lambda x: (x.y0, x.x0))


def cleanup_row_text(row):
    return normalize_whitespace(row.text)


def message_body(msg):
    lines = []
    last = None
    for r in msg.rows:
        if r.kind == "image":
            # This placeholder was replaced with a Markdown file link when
            # writing assets. If no extraction was requested it remains an
            # explicit note rather than silently being omitted.
            txt = r.text or "[Embedded image in PDF]"
            if lines and lines[-1]:
                lines.append("")
            lines.append(txt)
            lines.append("")
            last = None
            continue

        txt = cleanup_row_text(r)
        if not txt:
            continue
        if not lines:
            lines.append(txt)
        elif last is not None:
            visual_gap = r.y0 - last.y1 if r.page == last.page else None
            if (visual_gap is not None and visual_gap < 6
                    and not re.match(r"^(?:[-*] |\d+[.)] )", txt)):
                # Line-wrap within a message, not a new SMS bubble.
                lines[-1] = lines[-1].rstrip() + " " + txt
            else:
                if lines[-1] != "":
                    lines.append("")
                lines.append(txt)
        else:
            lines.append(txt)
        last = r

    result = "\n".join(lines).strip()
    # Preserve all words without treating markdown headings or blockquote
    # glyphs in the source as instructions to this extractor.
    return re.sub(r"\n{3,}", "\n\n", result)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pdf", type=Path, help="TextPort conversation PDF")
    parser.add_argument("--me", default="You", help='Outgoing speaker name; e.g. "Regina"')
    parser.add_argument("--other", help="Incoming contact name (default: PDF contact)")
    parser.add_argument("--output", type=Path, help="Markdown output path")
    parser.add_argument("--index", type=Path, help="CSV index output path")
    parser.add_argument("--min-image-size", type=int, default=300,
                        help="Minimum width AND height of embedded image to extract."
                             " Ignore tiny emoji, default: 300")
    args = parser.parse_args()

    source = args.pdf.expanduser().resolve()
    if not source.is_file():
        parser.error(f"Cannot find PDF: {source}")
    out = args.output or source.with_name(source.stem + "_messages.md")
    idx = args.index or source.with_name(source.stem + "_index.csv")
    out = out.expanduser().resolve()
    idx = idx.expanduser().resolve()
    distinct_paths([source], [out, idx])
    out.parent.mkdir(parents=True, exist_ok=True)
    idx.parent.mkdir(parents=True, exist_ok=True)
    assets_dir = out.parent / (out.stem + "_assets")

    pdf = fitz.open(source)
    if pdf.is_encrypted:
        parser.error("The PDF is encrypted; unlock it first.")
    if len(pdf) == 0:
        parser.error("Empty PDF.")

    contact = args.other
    if not contact:
        m = re.search(r"(?m)^With:\s*(.+)$", pdf[0].get_text())
        contact = m.group(1).strip() if m else "Contact"
    messages = []
    unassigned = []
    skipped = []
    current = None
    extracted_images = 0
    files_by_message = {}

    for pno, page in enumerate(pdf, 1):
        for row in layout_rows(page, pno, args.min_image_size):
            txt = normalize_whitespace(row.text)
            if row.kind == "text":
                if not txt or txt == "With: " + contact or txt.startswith("PDF generated on "):
                    continue
                if FOOTER.fullmatch(txt) or DAY_HEADING.fullmatch(txt):
                    continue
                if txt.startswith("With:") and pno == 1:
                    continue
                incoming = INCOMING.fullmatch(txt)
                outgoing = OUTGOING.fullmatch(txt) if not incoming else None
                if incoming or outgoing:
                    sender = incoming.group(1) if incoming else args.me
                    recipient = args.me if incoming else contact
                    ts = normalize_whitespace(incoming.group(2) if incoming else outgoing.group(1))
                    current = Message(len(messages) + 1, sender, recipient, ts,
                                      normalized_time(ts), pno, pno)
                    messages.append(current)
                    continue

            if current is None:
                unassigned.append((pno, txt or "[image]"))
                continue
            current.page_end = pno
            if row.kind == "image":
                extracted_images += 1
                assets_dir.mkdir(parents=True, exist_ok=True)
                ext = re.sub(r"[^a-z0-9]+", "", row.image_ext.lower()) or "png"
                filename = f"message_{current.no:04d}_page_{pno:03d}_image_{extracted_images:03d}.{ext}"
                asset = assets_dir / filename
                asset.write_bytes(row.image_data)
                rel = asset.relative_to(out.parent).as_posix()
                row.text = f"![Embedded attachment from PDF page {pno}]({rel})"
                current.attachments.append(f"Embedded image: {rel}")
                files_by_message.setdefault(current.no, []).append(dict(
                    relative_path=rel, original_filename=filename,
                    content_type=mimetypes.guess_type(filename)[0] or 'application/octet-stream',
                    byte_size=len(row.image_data), sha256=hashlib.sha256(row.image_data).hexdigest(), available=True))
            else:
                current.attachments.extend(ATTACHMENT_REF.findall(row.text))
            current.rows.append(row)

    if not messages:
        parser.error("No TextPort message timestamp headers detected. "
                     "This script does not support arbitrary scanned PDFs.")

    archive = [
        f"# SMS / iMessage archive — {contact}",
        "",
        f"**Source PDF:** `{source.name}`",
        f"**Messages represented:** {len(messages)}",
        f"**Conversation:** {args.me} ↔ {contact}",
        "**Order:** As exported by TextPort, earliest first",
        "**Time zone:** Not specified in the PDF; do not assume UTC",
        "**Evidence note:** TextPort may repeat rounded timestamps across distinct messages. "
        "No exact seconds or missing timestamps have been inferred.",
        "**Attachment note:** Bracketed image/document descriptions are preserved, "
        "but are not the actual original attachments. The PDF may omit their content.",
        "**Provenance:** Keep the original PDF and, preferably, the native phone export.",
        "",
    ]

    csv_rows = []
    for msg in messages:
        body = message_body(msg)
        archive += [
            "---", "",
            f"## Message {msg.no:04d} — {msg.timestamp_normalized}",
            f"**From:** {msg.sender}  ",
            f"**To:** {msg.recipient}  ",
            f"**Source:** PDF page{'s' if msg.page_start != msg.page_end else ''} "
            f"{msg.page_start}" + (f"–{msg.page_end}" if msg.page_end != msg.page_start else ""),
            "",
            body or "[No readable message body in PDF]", "",
        ]
        csv_rows.append({
            "message_number": msg.no,
            "timestamp_as_printed": msg.timestamp_original,
            "datetime_no_timezone": msg.timestamp_normalized,
            "sender": msg.sender,
            "recipient": msg.recipient,
            "pdf_page_start": msg.page_start,
            "pdf_page_end": msg.page_end,
            "attachment_references": " | ".join(dict.fromkeys(msg.attachments)),
            "body_characters": len(body),
            "attachment_files_json": json.dumps(files_by_message.get(msg.no, [])),
        })
    with staged_outputs([out, idx]) as stages:
        stages[0].write_text("\n".join(archive), encoding="utf-8")
        fields = list(csv_rows[0])
        with stages[1].open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(csv_rows)

    print(f"Source PDF: {source.name} ({len(pdf)} pages)")
    print(f"Contact: {contact}; outgoing sender: {args.me}")
    print(f"Messages: {len(messages)}; embedded large images saved: {extracted_images}")
    print(f"Attachment placeholders: {sum(bool(x['attachment_references']) for x in csv_rows)} messages")
    print(f"Markdown: {out} ({out.stat().st_size:,} bytes)")
    print(f"Index CSV: {idx} ({idx.stat().st_size:,} bytes)")
    if unassigned:
        print(f"WARNING: {len(unassigned)} unassigned lines before first message marker: {unassigned[:4]}")
    if skipped:
        print("WARNING: Possible skipped entries:", skipped)


if __name__ == "__main__":
    main()
