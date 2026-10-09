# Code review — correspondence timeline

Reviewed 2026-10-08. Scope: all Python modules, the HTML/CSS/JavaScript viewer,
the documented workflow, source indexes, and the current PDF's existing checks.
The findings below describe the pre-fix baseline. Resolution details and current
validation results are recorded in the remediation section at the end.

## Findings

### 1. High: extraction drops replies after signatures when the reply header wraps

Location: `gmail_archive.py:268–297`.

`clean_body()` enters footer mode at a signature. It exits for a single-line
`On … wrote:` header, but does not recognize the common two-line form ending
in `wrote:` on the next line. The reply and its text remain in footer mode and
are discarded until another recognized boundary.

Reproduced against the original MBOX: adding wrapped-header recognition in memory
recovers additional text in 36 source emails. The current compact archive is
missing the recovered fee-agreement passages in gmail:0023 and gmail:0026, and
the recovered confirmation passage in gmail:0027. This is substantive text loss,
not merely a display problem. The original MBOX remains intact.

Fix: share a bounded, multiline reply-boundary parser between extraction and
presentation; test signature followed by both single-line and wrapped replies.
Recover affected text by Message-ID while retaining the existing edited archive
and source numbering, rather than blindly replacing it with a fresh extraction.

### 2. High: forwarded-copy deduplication ignores single-digit numbers and signs

Location: `gmail_archive.py:423–451`.

`word_shingles()` removes URLs, punctuation, and all tokens shorter than two
characters. Therefore changing “option 1” to “option 2”, or “1%” to “2%”, can
produce identical shingle sets. The 99.9% coverage threshold does not protect
against information already removed by normalization. A forwarded message with
an important numerical change can be replaced by a reference to the earlier
version, losing the changed term from the derivative archive.

Reproduced a 400+ character passage with 89 shingles: changing both the option
number and percentage still yields 100% coverage. Current source-index rows are
223 FULL and 58 EVENT, with no REFERENCE entries, so this destructive branch is
not currently reflected in those representation rows.

Fix: use a normalization that preserves numbers, signs, and meaningful punctuation;
prefer exact normalized passage equality over set containment for destructive
elision. Retain or explicitly display conflicting headers and changed terms.

### 3. Medium: quoted-header parsing can consume message text as a header

Location: `timeline_html.py:140–146`; PDF header removal at
`export_timeline_pdf.py:106–108`.

After a header, every nonblank line is treated as a continuation, regardless of
indentation. A valid Outlook-style header followed immediately by
`Seller accepted the change.` produces `Subject: Title Work Seller accepted the
change.` and an empty body. In HTML the sentence appears as subject metadata;
The prose is rendered as header metadata rather than a message body, and this
prevents accurate body matching. No current long header-only passage
was detected by the targeted dataset check; the parser failure was reproduced
with a small fixture.

Fix: recognize actual header continuation syntax, stop at unindented prose, and
preserve uncertain lines as body content. Keep one parser for both header
display and `history_content()` so their interpretations cannot diverge.

### 4. High: missing or changed source attachments can pass PDF export checks

Location: `pdf_attachment_appendix.py:27–35`;
`pdf_embedded_attachments.py:62–69`.

`collect_files()` silently skips a missing file. It also computes its expected
hash from whatever bytes are currently on disk, rather than the extraction
index's recorded hash. The final verifier compares embedded bytes with that
newly collected set. A missing attachment therefore disappears from both the
export and the expected set; a replaced attachment can establish its own new
expected hash. Reproduced the missing-file case: a required `missing.pdf` link
returns an empty collection without an error.

Current-state check: all 422 source-index attachment references resolve, and
their available recorded hashes match. The current files are consistent; the
failure is in detecting future missing/changed files.

Fix: collect expected files, sizes, hashes, and source associations from the
indexes, apply the explicit signature exclusions, and fail on unexplained
missing files or hash changes. Intentionally unavailable Android files should
remain explicitly recorded as unavailable.

### 5. High: output paths can overwrite originals, and fresh PDF saves are not atomic

Locations: `iphone_pdf_to_markdown.py:196–204,303–305`;
`export_timeline_pdf.py:47–48,197–205`.

The iPhone converter lacks the distinct-path checks used by the Android and
combination scripts. `--output iphone_darcy.pdf` can replace its input PDF with
Markdown; equal Markdown/CSV destinations overwrite one another. The PDF
exporter likewise allows its output to equal the input HTML. Fresh exports save
directly over the prior PDF before final verification, so an interrupted save
or failed verification can leave the prior successful artifact replaced.

Fix: reject collisions with inputs and companion outputs; save to a temporary
destination, verify it, and replace the final output only after success. Apply
the same publication pattern to the related Markdown/CSV/HTML bundle.

### 6. Medium: long quotation matching ignores differing message headers

Location: `timeline_html.py:196–203`; omission behavior in
`timeline_pdf_readability.py:19–24`.

For text of at least 80 characters, matching ignores sender, date, recipients,
and subject. A quotation with a different sender/date/subject but identical
template text still links to an earlier record. HTML collapses it, and PDF
removes the quoted passage including those potentially new headers. Thus a
previously unseen message can be treated as repeated text and its distinct
attribution omitted from the PDF. Reproduced with conflicting explicit headers.

Fix: distinguish repeated wording from a repeated message. Keep new/conflicting
headers visible even when the body is represented elsewhere; only remove a
whole quotation when attribution agrees or is explicitly preserved alongside
the reference. Compare individual passages, rather than concatenating different
quoted messages into one searchable body.

### 7. Medium: verification checks record IDs, not complete message visibility

Locations: `export_timeline_pdf.py:82–90,175–179`;
`pdf_embedded_attachments.py:70–79`.

An ID occurring anywhere in PDF text satisfies the record check—even if it only
appears in another message's reference. A card whose body is empty or clipped
also passes if its ID remains. Attachment checks establish that every embedded
payload is expected and that at least one paperclip exists; they do not require
a clickable reference for every intended attachment occurrence.

Fix: validate record destinations and expected rendered body text per record
(accounting for explicit signature/quotation omissions), and validate attachment
annotations against the expected reference-to-file mapping. Avoid `assert` for
runtime validation, because optimized Python disables those checks.

### 8. Medium: Android HTML treats ordinary hyperlinks as attachment files

Location: `android_html_export.py:27–28,43–54,82–87`.

Every anchor inside a message becomes an attachment. A normal web link such as
`https://example.com/report` then fails the local-relative-attachment check and
aborts conversion. Text nodes from `See <a>the report</a> today` are stored
separately and joined with newlines, changing normal inline prose. Both behaviors
were reproduced with a small HTML fixture.

Fix: identify attachment-specific anchors, preserve ordinary link text/URLs as
body content, and accumulate inline text without inserting paragraph breaks at
every HTML text node. Verify dates/timestamps after nested formatting too.

### 9. Medium: extracted iPhone images do not reach the HTML/PDF attachment pipeline

Locations: `iphone_pdf_to_markdown.py:246–254`;
`timeline_html.py:329–340`.

The iPhone converter saves actual embedded images and inserts Markdown image
links. The HTML builder escapes that Markdown as text and only loads phone
attachment metadata for Android. Reproduced an iPhone embedded-image record:
it produces neither an image nor a `file-link`. The PDF attachment collector
therefore never embeds it. This concerns actual extracted images, not bracketed
descriptions of unavailable original attachments.

Fix: write structured iPhone attachment metadata with paths, sizes, and hashes,
and feed it through the same preview and embedding pipeline as Android.

### 10. Medium: preview filenames can collide across attachments

Location: `export_timeline_pdf.py:129,149`.

PDF and image previews are named from `path.stem` only. Distinct attachments in
different directories, or same-stem images with different extensions, overwrite
the same preview file. Multiple cards can then show the wrong preview even
though the embedded originals are correct. This is an input-dependent defect;
no collision in the current output was established.

Fix: key cached preview filenames by the attachment SHA-256 and preview variant.
Apply EXIF orientation to image thumbnails as well.

## Improvements to make after content-preservation fixes

- Make `gmail_archive.py` import-safe with a `main()` entry point. It currently
  parses arguments and processes files at import time, obstructing unit tests.
- Put shared email segmentation, header parsing, and normalization in one module;
  the extraction and rendering parsers currently recognize different boundaries.
- Replace dataset-dependent attachment tests with small sanitized fixture files;
  add extraction, Android HTML, iPhone attachment, and Windows PDF integration tests.
- Consolidate the README: its first Android command references a nonexistent
  `gilapps_android_txt_to_markdown.py`, and old printing/attachment instructions
  remain alongside later superseding guidance. Document the curated archive
  regeneration process and Python/PyMuPDF/Pillow requirements in one place.
- Separate active attachment collection from the unused appendix implementation,
  and remove stale CSS/CLI paths where they no longer support the documented flow.
- Make source numbering reproducible for unzoned email dates: the extractor's
  `.timestamp()` sorting uses the host timezone for naive dates. Changing UTC to
  Eastern did not change IDs in the current MBOX, but mixed-zone inputs can.

## Validation and limits

- All 19 existing tests pass.
- Current PDF passes its existing verifier: 771 IDs, 228 pages, 195 embedded
  originals plus manifest, 305 attachment paperclips.
- Original MBOX has 281 messages; Message-IDs align with all 281 source-index rows.
- Current Gmail/Android attachment indexes: 422 references, no missing files or
  mismatched recorded hashes.
- Additional reproductions used in-memory fixtures or temporary directories.
  No correspondence code, source archive, or timeline output was changed.
- Passing existing checks does not establish complete PDF body preservation;
  finding 7 describes that limitation. Browser interaction and independent
  rendering in Adobe Acrobat were not exercised during this review.


## Remediation — 2026-10-08

All ten findings have been addressed. Original findings and baseline measurements
above are retained so the changes remain traceable.

| Finding | Resolution |
| --- | --- |
| 1 — dropped wrapped replies | `email_parsing.py` supplies shared multiline boundaries. `recover_email_quotes.py` restored missing quoted passages in 34 FULL records by Message-ID, preserving existing edited text and IDs. EVENT shortening remains unchanged. Recovery is idempotent, recorded in `email_quote_recovery_manifest.json`; the historical pre-recovery copies were removed after verification. |
| 2 — lossy forwarded-copy deduplication | Removed destructive forwarded-copy elimination from Gmail extraction. Display matching requires complete normalized passage equality; digits, signs, URLs, and changed terms are retained. |
| 3 — prose swallowed by headers | Shared `quoted_headers()` recognizes folded headers and stops at unindented prose. Header display and matching use the same parser. |
| 4 — missing/replaced attachments | `attachment_inventory.py` validates extraction sizes/hashes. Generated file links carry those expectations; `pdf_attachments.py` fails on missing or altered originals. Embedding rechecks bytes and verifies both embedded manifests. |
| 5 — collisions and incomplete publication | Extraction/combination/export reject input/output collisions. `output_safety.py` stages related outputs; the PDF is verified before atomic replacement. A failed validation retains existing successful outputs. |
| 6 — conflicting attribution hidden | All quote lengths require complete individual-passage equality, sender identity, and a timestamp match. Explicit subject/recipient conflicts remain expanded. Matching can reference a passage inside an earlier email without concatenating different messages. Discrepancy notes use that passage's own time. |
| 7 — inadequate PDF verification | `pdf_validation.py` requires native record headers/destinations and expected rendered bodies within each record. PDF destinations are rebuilt from physical header coordinates. Unique occurrence tokens and annotation source/payload checks require every displayed attachment reference. Runtime checks use exceptions. |
| 8 — Android links and formatting | Only attachment-specific images/anchors become files. Ordinary link text/URLs remain inline. Nested date, speaker, and timestamp text accumulates correctly. All 215 current Android bodies remain identical to the existing archive. |
| 9 — iPhone images omitted downstream | iPhone extraction writes structured attachment paths/types/sizes/hashes in its CSV. Combination and HTML rendering load that index for the same preview/embedding flow as Android. A synthetic PDF test exercises actual image extraction. The current source has no qualifying embedded-image references. |
| 10 — preview collisions/orientation | Preview paths use content SHA-256 plus variant. Image previews apply EXIF orientation. Tests cover identical stems in different directories and rotated photographs. |

The additional improvements are also implemented: Gmail has an import-safe main
entry point; email boundary/header handling is shared; tests use sanitized fixtures;
the README is consolidated with current source names, curated archive recovery,
dependencies, and direct PDF export instructions. The old appendix module is a
small compatibility import for validated collection, with no appendix generation.
Obsolete PDF CLI branches and unused sender CSS are removed. Naive email dates
use UTC for deterministic extraction sorting, while remaining explicitly unzoned
in the timeline.

### Post-fix validation

- Windows Python: all 36 regression tests pass, including actual iPhone image
  extraction, PDF attachment/annotation checks, native destinations/body checks,
  and preview collision/orientation fixtures.
- WSL Python: 32 tests pass; four PDF tests are skipped because PyMuPDF is installed
  in the Windows interpreter. All modules compile.
- All 281 curated email IDs and pre-existing edited record text are preserved;
  recovery adds missing passages only. Repeating recovery produces no changes.
- All 215 Android message bodies match the existing archive. The complete timeline
  still has 771 records: 281 Gmail, 275 iPhone, and 215 Android.
- All 422 Gmail/Android source attachment references validate against their
  extraction metadata; no source files were replaced or deleted.
- Refreshed HTML, Markdown, CSV, compact Markdown, and PDF include the corrected
  correspondence. The 237-page PDF includes 195 unique original files, two JSON manifests,
  and 306 paperclips; every expected displayed attachment occurrence is checked.

### Remaining verification limits

Each destination replacement is atomic; a multi-file bundle is not a filesystem
transaction. Rendered-body verification normalizes letters/numbers and wrapping;
it does not establish punctuation, emoji, or graphical fidelity. Automated PDF
checks do not replace a visual review in Adobe Acrobat. Quotation matching remains
a conservative reading aid, not authentication of authorship or reply relationships.

### Subsequent PDF design update

PDF export now uses `timeline_pdf.css` to retain the HTML timeline rail, date
markers, conversation panels, rounded cards, participant colors, shaded quoted
passages, and attachment cards. Short cards stay together where possible;
long records can continue across pages. The refreshed design uses 285 pages
with the same 771 records, 195 embedded originals, two manifests, and 306
paperclips. Sample pages were rendered for visual inspection; all 36 regression
tests and the export's content/destination/attachment checks pass.
