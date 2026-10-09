# Property correspondence timeline

This project combines Gmail and Android/iPhone correspondence into one searchable
timeline. It reads curated archives, preserves source IDs, and produces HTML,
PDF, Markdown, and CSV copies. Times display in Eastern time (`America/New_York`).

## Open these files

| File | Use it for |
| --- | --- |
| [Timeline viewer](output/master_timeline.html) | Search messages and preview attachments |
| [Timeline PDF](output/master_timeline.pdf) | Read or share a standalone copy with embedded attachments |
| [Compact Markdown](output/master_timeline_compact.md) | Ask ChatGPT questions using references such as `gmail:0163` |
| [Full Markdown](output/master_timeline.md) | Check archive references, hashes, and notices |
| [CSV index](output/master_timeline.csv) | Look up record IDs, timestamps, and source locations |
| [AI review package](output/master_timeline_ai.zip) | Upload timeline and extracted attachment text to ChatGPT or Gemini |

The archives contain edited correspondence and shortened system events. Keep the
original exports for checking complete source content. Review private/counsel
material before sharing; the compact copy does not redact it.

## Where things live

```text
data/originals/    Original Gmail, Android, and iPhone exports
data/archives/     Curated Markdown, source indexes, manifests, extracted files
output/            Generated timeline copies and PDF preview assets
src/               Python code and viewer/PDF resources
tests/             Regression and integration tests
docs/              Detailed workflows and reference information
```

**Keep originals and curated archives.** The archives can contain manual edits;
re-extracting overwrites them. Generated files in `output/` can be rebuilt.

## Refresh after editing an archive

Run these commands from the project folder using **Windows Python 3.11+**, with
Chrome or Edge installed. Install once, or after dependencies change:

```powershell
python -m pip install -e .
```

Then run each command after the previous one succeeds:

```powershell
python -m property_timeline.combine_timeline --phone-timezone America/New_York
python -m property_timeline.export_timeline_pdf
python -m property_timeline.export_timeline_pdf --verify-only
```

From WSL, prefix each command with `cmd.exe /c` to use Windows Python. Combining
reads the curated archives; it does not import new messages from the originals.
The viewer's **Export PDF** button opens the existing PDF; it does not rebuild it.
Combining also rebuilds the **Export for AI** ZIP. Extract it and upload its text
files; originals stay separate, and images/scanned pages are labeled for review.
See [AI export details](docs/REFERENCE.md#ai-review-export) for contents and limits.

## When you have new exports

Back up the current project, replace the originals with **complete exports**,
re-extract, compare with your backup, and reapply manual edits before combining.
Use the [full refresh instructions](docs/WORKFLOWS.md#refresh-source-files-and-regenerate-everything)
for exact filenames and extraction commands. Existing citations may change if
source numbering or ordering changes.

## Sharing and further details

The PDF includes its attachments and can be shared alone. To share the HTML,
include `output/` and `data/` with their relative folder layout intact.

- [Maintenance workflows](docs/WORKFLOWS.md): importing exports, quote recovery, tests, and verification.
- [Reading and file reference](docs/REFERENCE.md): filenames, extraction behavior, quotations, attachments, and PDF details.
- [Code review](docs/CODE_REVIEW.md): original findings and remediation status.

## Automated review for counsel

The optional [review harness](docs/REVIEW_HARNESS.md) assesses entries in resumable
batches, validates evidence quotations, and produces a separate counsel report.
It keeps review state in `data/reviews/` and leaves correspondence unchanged.
Start locally with `python -m property_timeline.review_runner init`, complete the
case brief, then run a 20-entry pilot before approving automatic continuation.
Review runs use Codex CLI signed in with ChatGPT and consume your plan allowance.
No API key or API billing setup is required.
After review, open the timeline viewer, choose **Load review**, and select
`data/reviews/entry_review.json` to show removable annotations and review filters.
