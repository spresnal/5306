# Property correspondence timeline

This project combines the edited Gmail archive and Android/iPhone exports into
an Eastern-time chronology with origin-prefixed reference IDs. It provides an
offline HTML viewer, a PDF with embedded original attachments, Markdown reference
copies, and a CSV index. Retain the original exports and source indexes: the
compilation is a derivative, and some automated emails are shortened events.

## Refresh the existing timeline

Use the existing edited archives to retain their curation and numbering:
run these commands from the project folder. If you have replaced the original
MBOX or phone exports, follow [Refresh source files and regenerate everything](#refresh-source-files-and-regenerate-everything)
instead; combining alone does not re-read the original exports.

```bash
python combine_timeline.py --phone-timezone America/New_York
python export_timeline_pdf.py
python export_timeline_pdf.py --verify-only
```

Run PDF export with **Windows Python**, with Chrome or Edge installed. From WSL,
use `cmd.exe /c python export_timeline_pdf.py`. The HTML **Export PDF** control
opens the generated PDF; it does not regenerate it. Refresh the PDF after each
archive or viewer change. HTML filters do not affect PDF export.

PDF layout follows the HTML viewer: the timeline rail and date markers,
conversation panels, rounded message cards, blue/green participant colors,
quoted-message panels, and attachment thumbnails are retained. Letter-page
spacing and page-break rules keep short cards together while allowing long
emails to continue across pages. Full email addresses and source references
remain available in smaller secondary text. Export styles live in
`timeline_pdf.css`; no browser print dialog is required.

For visual checks, save selected PDF pages as images without rebuilding it:

```bash
python export_timeline_pdf.py --verify-only --preview-pages 1 2 12
```

Images are written as `master_timeline_pdf_assets/preview_page_0001.png`, etc.

| Output | Purpose |
| --- | --- |
| `master_timeline.html` | Searchable offline chronology with attachment previews |
| `master_timeline.pdf` | Complete chronology, daily bookmarks, page numbers, embedded files |
| `master_timeline.md` | Edited archive entries, source locations, hashes, and notices |
| `master_timeline.csv` | Record references, source locations, UTC and Eastern timestamps |
| `master_timeline_compact.md` | Smaller copy for timeline questions in ChatGPT |

The compact copy keeps all records, participants, subjects, attachment references,
and substantive archive text, including quotations. It removes reference
bookkeeping and repeated notices. It does not redact private/counsel material.
Ask for answers citing identifiers such as `gmail:0163` and check them against
the source references.

## Requirements

Use Python **3.11 or newer**. Gmail/Android extraction and combination use the
standard library; iPhone extraction requires PyMuPDF. PDF export requires PyMuPDF,
Pillow, and Windows Chrome/Edge. `tzdata` supplies IANA time zones on Windows.
Install dependencies in the Python environment used to run these commands:

```bash
python -m pip install -r requirements.txt
```

## Refresh source files and regenerate everything

Use this workflow when you obtain newer Gmail, Android, or iPhone exports and
want to rebuild all archives, indexes, attachment extracts, and timeline outputs.
Run the commands from this project folder using Windows Python **3.11 or newer**
and Chrome or Edge, so extraction and PDF generation use the same environment.
In Windows PowerShell, open the folder with:

```powershell
Set-Location 'C:\Users\samgp\Desktop\5306'
python -m pip install -r requirements.txt
```

1. **Back up the current project folder to a separate dated folder before
   replacing anything.** Include the original exports, edited Markdown archives,
   CSV indexes, attachment folders/manifests, recovery manifest, and generated
   timeline. `review_backups/` contains historical review copies, not an automatic
   backup of your latest work.
2. **Replace the source exports with complete updated exports**, using the names
   below. The extractors rebuild from the supplied export; they do not append
   new messages to the existing archive. An export containing only recent
   messages would therefore omit older messages from the rebuilt timeline.

   | Source | Files to replace together |
   | --- | --- |
   | Gmail | `5306 House.mbox` from the updated Gmail export |
   | iPhone | `iphone_darcy.pdf`, the updated TextPort conversation PDF |
   | Android | `group_conversation_966.html` and its matching `group_conversation_966_Attachments/` folder; retain the matching `group_conversation_966.smsbackup` as the native original |

   Keep the Android HTML and attachment folder from the same export together;
   the HTML's attachment links must resolve to the supplied files. If the export
   uses a different filename/folder, use its actual HTML filename in the command
   below and preserve its linked folder names. The explicit output names and
   conversation ID keep the downstream filenames consistent.
3. **Re-extract all three archives** using the commands below. These replace
   derivative archives and indexes, including manual edits. Compare fresh output
   with your backup and reapply any required curation before combining. IDs follow
   source numbering and remain stable only while the source set and ordering
   stay fixed; check existing citations after refreshing.
4. **Combine, export, and verify** using the remaining commands. Run each command
   only after the previous one succeeds. If you reapply edits after combining,
   repeat the combine/export/verify steps.

```powershell
python gmail_archive.py "5306 House.mbox" --output property_emails_compact.md --index property_email_source_index.csv --attachments-dir property_emails_compact_attachments
python iphone_pdf_to_markdown.py "iphone_darcy.pdf" --me Regina --output iphone_darcy_messages.md --index iphone_darcy_index.csv
python android_txt_to_markdown.py group_conversation_966.html --me Sam --wife Regina --contact Darcy --conversation-id android_darcy_group --output android_darcy_group_messages.md --index android_darcy_group_index.csv

# Pause here to compare archives and reapply any manual edits.
python combine_timeline.py --phone-timezone America/New_York
python export_timeline_pdf.py
python export_timeline_pdf.py --verify-only
```

From WSL, run from `/mnt/c/Users/samgp/Desktop/5306` and prefix each `python`
command above with `cmd.exe /c` to use Windows Python
(including the dependency installation command). Dependencies installed in WSL
Python are separate from those installed in Windows Python.

The three extractors produce the source Markdown archives and CSV indexes,
Gmail attachment files and `property_emails_compact_attachment_manifest.csv`,
and any qualifying iPhone images in `iphone_darcy_messages_assets/`. Android
attachments remain in the original export folder. Combining regenerates all
four master Markdown/CSV/HTML outputs listed above; PDF export regenerates
`master_timeline.pdf` and its preview assets in `master_timeline_pdf_assets/`.
Extraction does not guarantee that older, unreferenced attachment files are
removed; keep the indexes/manifests with the corresponding refreshed archives.

The quote-recovery command below repairs older curated email archives; it is
not an incremental import command and is unnecessary after fresh extraction
with the current Gmail extractor. Move an old `email_quote_recovery_manifest.json`
to the backup before re-extracting Gmail, so the rebuilt timeline does not link
historical recovery evidence as if it applied to the fresh archive.

After verification succeeds, open `master_timeline.html` and
`master_timeline.pdf`. Check the newest expected messages, source counts, dates,
participant names, and a few attachments against the updated originals. A
successful PDF check validates the generated bundle, not whether your exports
contain every message you intended to include. See
[Verification and publication](#verification-and-publication) for regression
tests and final review guidance.

### Source extraction details

The Android source is `group_conversation_966.html`, with
`group_conversation_966_Attachments/` and the native `.smsbackup` retained. The
older TXT input is still supported, but cannot provide original attachment
bytes. Ordinary hyperlinks remain message text; attachment-specific links
become structured file references.

Gmail extraction saves MIME attachments (including attached emails as `.eml`)
in `property_emails_compact_attachments/`. The source index and attachment manifest
record Message-IDs, MIME parts, original filenames, sizes, and SHA-256 hashes.
It retains forwarded text rather than deleting similar copies. Recognized
boilerplate is cleaned and certain system messages become explicit EVENT entries.
Unzoned original email dates use UTC solely for reproducible extraction ordering;
they remain explicitly unzoned in the archive and master chronology.

The iPhone converter preserves text and attachment descriptions from TextPort.
Actual large embedded images are extracted to `iphone_darcy_messages_assets/`
and registered in `iphone_darcy_index.csv` for HTML previews and PDF embedding.
Bracketed descriptions alone are not the original attachments. The current
source PDF contains no qualifying embedded images.

The combining command discovers the established source-index filenames beside
each input archive. Optional paths: `--android`, `--iphone`, `--gmail`, `--output`,
and `--compact-output`. Use `--help` for extraction options and alternate paths.

## Recover quoted text in an edited email archive

The old extractor could drop replies after signatures when an `On … wrote:`
header wrapped across lines. The fixed extractor shares reply/header parsing
with the viewer. To repair the existing curated archive without overwriting
its edited text:

```bash
python recover_email_quotes.py
```

Recovery compares old and corrected extraction against the original MBOX by
Message-ID, appends only missing passages to FULL entries, and retains intentional
EVENT shortening. It is idempotent and records additions and hashes in
`email_quote_recovery_manifest.json`. Existing numbering and edited text are
preserved. Refresh the master outputs afterward. The review remediation restored
passages in 34 records; the pre-recovery archive/index copies are in
`review_backups/`.

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
`signature_attachment_hashes.json`, with actual bytes checked. Generic filenames
and inline disposition alone are insufficient. `SecureMessageAtt.html` remains
included because it contains the secure-message payload.

## Attachments and sharing

HTML previews use local originals. Keep Gmail, Android, and any iPhone attachment
folders with the HTML when sharing. Images open in a modal; PDFs can use browser
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

## Verification and publication

```bash
python -m unittest discover -v
python export_timeline_pdf.py --self-test
python export_timeline_pdf.py --verify-only
```

The Windows `--self-test` command runs the full suite, including sanitized PDF,
iPhone image extraction, preview orientation, and embedding fixtures. Interpreters
without PyMuPDF skip PDF tests. Attachment tests do not depend on case files.

PDF verification checks native source-header destinations, rendered body text
within each record, original file hashes, both manifests, and every expected
clickable attachment occurrence. Text comparison accounts for line wrapping,
Unicode normalization, explicit signature omissions, and repeated-quotation
references. It verifies letters/numbers, not punctuation, emoji, or visual layout.
Use Acrobat for a final visual review before sharing.

Outputs are staged and checked before publication; each final replacement is
atomic. The multi-file bundle is not a filesystem transaction. Original/input
path collisions are rejected. A failed PDF verification preserves the previous
successful PDF. Rebuild from source after interruption during multi-file replacement.

`CODE_REVIEW.md` retains the original findings and their remediation status.
