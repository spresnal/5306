# Maintenance workflows

[Back to the quick guide](../README.md) · [Reading and file reference](REFERENCE.md)

All commands and file paths below are relative to the **project root**, not this
`docs/` folder. Use Windows Python for PDF export and verification.

## Requirements

Use Python **3.11 or newer**. Gmail/Android extraction uses the standard library;
iPhone extraction and AI extraction of PDF attachments require PyMuPDF.
Combination can run without PyMuPDF, labeling PDF text extraction as unavailable.
PDF export requires PyMuPDF,
Pillow, and Windows Chrome/Edge. `tzdata` supplies IANA time zones on Windows.
Install the project and its dependencies in the Python environment used to run these commands (editable mode makes changes under `src/` immediately available):

```bash
python -m pip install -e .
```

## Refresh source files and regenerate everything

Use this workflow when you obtain newer Gmail, Android, or iPhone exports and
want to rebuild all archives, indexes, attachment extracts, and timeline outputs.
Run the commands from this project folder using Windows Python **3.11 or newer**
and Chrome or Edge, so extraction and PDF generation use the same environment.
In Windows PowerShell, open the folder with:

```powershell
Set-Location 'C:\Users\samgp\Desktop\5306'
python -m pip install -e .
```

1. **Back up the current project folder to a separate dated folder before
   replacing anything.** Include the original exports, edited Markdown archives,
   CSV indexes, attachment folders/manifests, recovery manifest, and generated
   timeline. The project does not automatically back up your latest work.
2. **Replace the source exports with complete updated exports**, using the names
   below. The extractors rebuild from the supplied export; they do not append
   new messages to the existing archive. An export containing only recent
   messages would therefore omit older messages from the rebuilt timeline.

   | Source | Files to replace together |
   | --- | --- |
   | Gmail | `data/originals/gmail/property_emails.mbox` from the updated Gmail export |
   | iPhone | `data/originals/iphone/iphone_darcy.pdf`, the updated TextPort conversation PDF |
   | Android | `data/originals/android/android_darcy_group.html` and its matching `data/originals/android/group_conversation_966_Attachments/` folder; retain the matching `data/originals/android/android_darcy_group.smsbackup` as the native original |

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
python -m property_timeline.gmail_archive "data/originals/gmail/property_emails.mbox" --output data/archives/gmail/property_emails_compact.md --index data/archives/gmail/property_email_source_index.csv --attachments-dir data/archives/gmail/property_emails_compact_attachments
python -m property_timeline.iphone_pdf_to_markdown "data/originals/iphone/iphone_darcy.pdf" --me Regina --other Darcy --output data/archives/iphone/iphone_darcy_messages.md --index data/archives/iphone/iphone_darcy_index.csv
python -m property_timeline.android_txt_to_markdown data/originals/android/android_darcy_group.html --me Sam --wife Regina --contact Darcy --conversation-id android_darcy_group --output data/archives/android/android_darcy_group_messages.md --index data/archives/android/android_darcy_group_index.csv

# Pause here to compare archives and reapply any manual edits.
python -m property_timeline.combine_timeline --phone-timezone America/New_York
python -m property_timeline.export_timeline_pdf
python -m property_timeline.export_timeline_pdf --verify-only
```

From WSL, run from `/mnt/c/Users/samgp/Desktop/5306` and prefix each `python`
command above with `cmd.exe /c` to use Windows Python
(including the dependency installation command). Dependencies installed in WSL
Python are separate from those installed in Windows Python.

The three extractors produce the source Markdown archives and CSV indexes,
Gmail attachment files and `data/archives/gmail/property_emails_compact_attachment_manifest.csv`,
and any qualifying iPhone images in `data/archives/iphone/iphone_darcy_messages_assets/`. Android
attachments remain in the original export folder. Combining regenerates all
four master Markdown/CSV/HTML outputs listed in the
[quick guide](../README.md#open-these-files); PDF export regenerates
`output/master_timeline.pdf` and its preview assets in `output/master_timeline_pdf_assets/`.
Combining also regenerates `output/master_timeline_ai.zip`, which the offline
viewer downloads through **Export for AI**. The control downloads the latest
generated package; it does not run Python or reflect the viewer's active filters.
Install PyMuPDF for PDF attachment extraction; a missing dependency is explicitly
reported as an extraction failure. See [AI review export](REFERENCE.md#ai-review-export).
Extraction does not guarantee that older, unreferenced attachment files are
removed; keep the indexes/manifests with the corresponding refreshed archives.

The quote-recovery command in the next section repairs older curated email archives; it is
not an incremental import command and is unnecessary after fresh extraction
with the current Gmail extractor. Move an old `data/archives/gmail/email_quote_recovery_manifest.json`
to the backup before re-extracting Gmail, so the rebuilt timeline does not link
historical recovery evidence as if it applied to the fresh archive.

After verification succeeds, open `output/master_timeline.html` and
`output/master_timeline.pdf`. Check the newest expected messages, source counts, dates,
participant names, and a few attachments against the updated originals. A
successful PDF check validates the generated bundle, not whether your exports
contain every message you intended to include. See
[Verification and publication](#verification-and-publication) for regression
tests and final review guidance.

## Recover quoted text in an edited email archive

The old extractor could drop replies after signatures when an `On … wrote:`
header wrapped across lines. The fixed extractor shares reply/header parsing
with the viewer. To repair the existing curated archive without overwriting
its edited text:

```bash
python -m property_timeline.recover_email_quotes
```

Recovery compares old and corrected extraction against the original MBOX by
Message-ID, appends only missing passages to FULL entries, and retains intentional
EVENT shortening. It is idempotent and records additions and hashes in
`data/archives/gmail/email_quote_recovery_manifest.json`. Existing numbering and edited text are
preserved. Refresh the master outputs afterward. The review remediation restored
passages in 34 records; the recovery manifest retains the added text and hashes.

## Verification and publication

```bash
python -m unittest discover -s tests -v
python -m property_timeline.export_timeline_pdf --self-test
python -m property_timeline.export_timeline_pdf --verify-only
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

[CODE_REVIEW.md](CODE_REVIEW.md) retains the original findings and their remediation status.

## Automated counsel triage

See [the review harness workflow](REVIEW_HARNESS.md) for a case-brief template,
20-entry pilot, automatic batch review, resumable cross-entry comparisons, and
coverage checks. The harness writes only separate review artifacts; refreshing
the timeline does not run Codex review or incorporate assessments into the PDF.
The runner requires Codex CLI signed in with ChatGPT; no API key is needed.
After completing review, rebuild the timeline to refresh its evidence/criteria
fingerprints, then use **Load review** in the HTML viewer to open
`data/reviews/entry_review.json`. **Clear review** removes the optional overlay.

The second pass rereads source evidence across topics, including routine entries.
Its linked findings and contextual priorities appear in the report and loaded
website review. Resume with `run --unattended` to run the expanded pass while
preserving unchanged first-pass assessments.
