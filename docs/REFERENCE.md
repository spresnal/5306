# Reading and file reference

[Back to the quick guide](../README.md) · [Maintenance workflows](WORKFLOWS.md)

File paths and commands below are relative to the **project root**.

This project combines the edited Gmail archive and Android/iPhone exports into
an Eastern-time chronology with origin-prefixed reference IDs. It provides an
offline HTML viewer, a PDF with embedded original attachments, Markdown reference
copies, and a CSV index. Retain the original exports and source indexes: the
compilation is a derivative, and some automated emails are shortened events.

## Project layout

```text
5306/
├── README.md
├── pyproject.toml                # Package metadata and dependencies
├── requirements.txt              # Dependency-only installation alternative
├── src/property_timeline/        # Python modules
│   └── resources/                # HTML template, PDF CSS, signature hashes
├── tests/                        # Sanitized regression and integration tests
├── data/
│   ├── originals/{gmail,android,iphone}/  # Original exports and Android files
│   └── archives/{gmail,android,iphone}/   # Curated Markdown, indexes, manifests
├── output/                       # Master timeline and PDF preview assets
└── docs/                         # Workflows, reference, and code review
```

Run all commands from this project folder. Install the package with
`python -m pip install -e .` before using the module commands below. Use Windows
Python for PDF export and verification; install the package in that environment
even if it is also installed in WSL.

Retain originals unchanged. Curated archives can contain manual edits and need
backups; extraction overwrites them. Archive indexes/manifests and Gmail or iPhone
attachment folders stay beside their Markdown archive. Android attachment bytes
stay with the original HTML export. `output/` can be rebuilt from those archives.

Raw export filenames use lowercase words separated by underscores, descriptive
source or conversation names, and their original file extensions:
`property_emails.mbox`, `android_darcy_group.html`,
`android_darcy_group.smsbackup`, `iphone_darcy.pdf`, `iphone_derrick.pdf`, and `iphone_sarah.pdf`. The Gmail export was
originally named `5306 House.mbox`; the Android exports were originally
`group_conversation_966.html` and `group_conversation_966.smsbackup`. Renaming
changed no original file contents. Keep the Android export's
`group_conversation_966_Attachments/` folder and attachment filenames unchanged
so its original HTML links continue to resolve. Extracted email attachments also
retain their source filenames and established manifest paths.

Python caches, build artifacts, and PDF preview assets are
ignored by Git; correspondence data and final outputs remain visible to Git.

## Timeline outputs and PDF appearance

PDF export includes the complete timeline regardless of HTML filters. The HTML
**Export PDF** control opens the existing PDF; refresh it after archive or viewer
changes using the [maintenance commands](../README.md#refresh-after-editing-an-archive).

PDF layout follows the HTML viewer: the timeline rail and date markers,
conversation panels, rounded message cards, blue/green participant colors,
quoted-message panels, and attachment thumbnails are retained. Letter-page
spacing and page-break rules keep short cards together while allowing long
emails to continue across pages. Full email addresses and source references
remain available in smaller secondary text. Export styles live in
`src/property_timeline/resources/timeline_pdf.css`; no browser print dialog is required.

For visual checks, save selected PDF pages as images without rebuilding it:

```bash
python -m property_timeline.export_timeline_pdf --verify-only --preview-pages 1 2 12
```

Images are written as `output/master_timeline_pdf_assets/preview_page_0001.png`, etc.

| Output | Purpose |
| --- | --- |
| `output/master_timeline.html` | Searchable offline chronology with attachment previews |
| `output/master_timeline.pdf` | Complete chronology, daily bookmarks, page numbers, embedded files |
| `output/master_timeline.md` | Edited archive entries, source locations, hashes, and notices |
| `output/master_timeline.csv` | Record references, source locations, UTC and Eastern timestamps |
| `output/master_timeline_compact.md` | Smaller copy for timeline questions in ChatGPT |

The compact copy keeps all records, participants, subjects, attachment references,
and substantive archive text, including quotations. It removes reference
bookkeeping and repeated notices. It does not redact private/counsel material.
Ask for answers citing identifiers such as `gmail:0163` and check them against
the source references.

## Source extraction details

The Android source is `data/originals/android/android_darcy_group.html`, with
`data/originals/android/group_conversation_966_Attachments/` and the native `.smsbackup` retained. The
older TXT input is still supported, but cannot provide original attachment
bytes. Ordinary hyperlinks remain message text; attachment-specific links
become structured file references.

Gmail extraction saves MIME attachments (including attached emails as `.eml`)
in `data/archives/gmail/property_emails_compact_attachments/`. The source index and attachment manifest
record Message-IDs, MIME parts, original filenames, sizes, and SHA-256 hashes.
It retains forwarded text rather than deleting similar copies. Recognized
boilerplate is cleaned and certain system messages become explicit EVENT entries.
Unzoned original email dates use UTC solely for reproducible extraction ordering;
they remain explicitly unzoned in the archive and master chronology.

The iPhone converter preserves text and attachment descriptions from TextPort.
It recognizes both named outgoing headers and older timestamp-only outgoing
headers. Use `--me Regina --other Darcy` to display the exported contact
“Darcy Carmel” as “Darcy” while retaining the original PDF.
For Derrick, use `--me Regina --other Derrick` with `iphone_derrick.pdf`.
For Sarah, use `--me Regina --other Sarah` with `iphone_sarah.pdf`.
Combining discovers all `data/archives/iphone/iphone_*_messages.md` archives;
repeat `--iphone PATH` to select specific conversations. Darcy IDs use
`iphone_darcy:0001`, Derrick IDs use `iphone_derrick:0001`, and Sarah IDs use
`iphone_sarah:0001`. All appear
under the website's iPhone source filter and are included in the review harness.
Actual large embedded images are extracted to `data/archives/iphone/iphone_darcy_messages_assets/`
and registered in `data/archives/iphone/iphone_darcy_index.csv` for HTML previews and PDF embedding.
Bracketed descriptions alone are not the original attachments.

The combining command discovers the established source-index filenames beside
each input archive. Original exports are found under `data/originals/<source>/`;
a supporting export beside its archive takes precedence. Optional paths:
`--android`, `--iphone`, `--gmail`, `--originals-dir`, `--output`, and
`--compact-output`. The master CSV records archive paths relative to its folder. Use `--help` for extraction options and alternate paths.

## AI review export

**Export for AI** downloads `output/master_timeline_ai.zip`, generated as part of
the combining command. It includes the full chronology regardless of HTML filters.
The button downloads an existing file; refresh the timeline after changing archives.
All extraction runs locally, without an AI service or network requests.

Extract the ZIP and upload its files directly to ChatGPT or Gemini:

| File | Contents |
| --- | --- |
| `START_HERE.txt` | Extraction counts, limitations, upload instructions, suggested citation prompt |
| `timeline.txt` | Readable UTF-8 compact correspondence, including quotations and message IDs |
| `attachment_index.csv` | Attachment IDs, original filenames, message associations, hashes, source paths, extraction status, text-file locations |
| `attachment_text_01.txt`, etc. | Document text labeled with attachment IDs, filenames, message IDs, and page/location references |

The ZIP contains at most ten files: three core files and up to seven attachment
text parts. Parts target about 150,000 characters; larger collections increase
part size to maintain the file-count limit. An oversized section is split with
repeated identification and location headers. Files can still exceed a model's
usable context; focus questions on smaller date/topic ranges when needed.

Repeated archive bookkeeping and attachment links are removed from `timeline.txt`.
Participants, subjects, dates, timezone labels, shortened-event labels, substantive
text, and quotations remain. Text is not summarized or rewritten. Local attachment
links become package attachment IDs. These IDs identify this package version;
message IDs retain the original archive numbering, and hashes identify file bytes.

Identical attachment bytes are extracted once. The CSV retains each specific
message/filename/source-path association, including aliases. Source paths are
relative to the ZIP's location under `output/`, for retrieving originals from the
project; they do not provide the AI access to local files. Reviewed decorative
signature assets remain indexed as `excluded_signature`.

Supported extraction includes PDF text, DOCX document/header/footer/notes text,
visible HTML text, attached email headers/body, and UTF-8/UTF-16 plain text files
(including Markdown, CSV, JSON, XML, and calendar files). PDF pages are individually
labeled. DOCX and other text formats do not have reliable page numbers.

No OCR is performed. Images, scanned pages, missing source files, encrypted files,
unsupported formats, and extraction errors are explicitly labeled. Some extracted
documents still require visual review for images, signatures, layout, tracked
changes, or interactive content. Nested email attachments are not extracted.
Attachment hash/size mismatches fail the combine operation and preserve the
previous generated outputs; individual text-extraction failures are recorded in
the package so readable files remain available.

Original binary attachments are omitted to keep uploads small. Upload relevant
original PDFs/images separately when reviewing visual details or extraction gaps.
The package includes private/counsel content without redaction, just like the
existing compact archive; review it before sharing.

## Reading and reference conventions

Timeline headings use `America/New_York` with EDT/EST as applicable. This phone
time zone was supplied by the user; it is not recorded in the exports. Unknown-zone
emails are listed separately. Equal-minute ordering does not establish which
message came first. Original printed timestamps remain in source references.

Consecutive SMS from the same source/day with gaps up to one hour share a
conversation block. Adjacent same-subject emails on the same Eastern day also
share a block. Intervening sources end blocks. These groups aid reading and do
not establish a verified reply relationship; every record retains its own ID.

Email cards use sender → recipients / Cc. Click that participant line for full
addresses. Explicit reply headers identify quoted speakers; uncertain attribution
stays visible. A quotation collapses only when its **complete cleaned passage**
matches an earlier passage, sender address and timestamp minute agree (within
one minute), and supplied recipient/subject headers do not conflict. An exact
full display name can resolve to a unique earlier address. Specific discrepancies
are noted. Missing/unparseable attribution and changed numbers, signs, URLs,
headers, or content stay expanded. The PDF substitutes references for matched
quotations; Markdown retains the edited archive text.

Recognized signatures and routine footers are omitted from reading views.
Original archive text is retained separately; original exports are the reference
for unabridged source content. Reviewed decorative attachments are excluded using
`src/property_timeline/resources/signature_attachment_hashes.json`, with actual bytes checked. Generic filenames
and inline disposition alone are insufficient. `SecureMessageAtt.html` remains
included because it contains the secure-message payload.

## Attachments and sharing

HTML previews use local originals. When sharing the HTML, include `output/` and
`data/` with their relative folder layout intact; archive references and attachment
links cross those folders. The PDF embeds its attachments and can be shared alone. Images open in a modal; PDFs can use browser
previews; other formats use their file links. Previews beside quoted passages
require an explicit filename or Content-ID reference; generic "see attached"
wording does not infer a file association. Unavailable files remain labeled.

The PDF embeds identical original bytes once and places native paperclips beside
each displayed file reference. Double-click a paperclip in Adobe Acrobat/Reader,
or use its Attachments panel to open/save the original. Files can then be opened
in their normal viewers. File-type and viewer restrictions may require saving
first. No external attachment folders or appendix are required for the PDF.

Two embedded JSON manifests preserve filenames, source IDs/paths, SHA-256 hashes,
and expected clickable references. Export fails on unexplained missing files or
changes to extraction hashes/sizes. Previews are keyed by content hash and variant;
image orientation follows EXIF metadata. Embedded originals are not converted.
