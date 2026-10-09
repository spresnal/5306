# Automated correspondence review

[Quick guide](../README.md) · [Maintenance workflows](WORKFLOWS.md)

The review runner processes the current timeline in bounded batches and stores
assessments separately from correspondence. It does not modify originals,
curated archives, or the existing timeline outputs. It writes under
`data/reviews/` and generates only `output/counsel_review.md` outside that folder.
Each batch runs through Codex CLI using ChatGPT sign-in, in a temporary read-only
workspace with the shell tool disabled. Only the harness publishes review files.

## Set up and run a pilot

Run from the project root. Install the package in the Python environment you use:

```powershell
python -m pip install -e .
python -m property_timeline.review_runner init
```

Initialization performs no network requests and creates:

| File | Purpose |
| --- | --- |
| `data/reviews/case_brief.md` | Your allegations, established facts, roles, dates, and counsel questions |
| `data/reviews/REVIEW_INSTRUCTIONS.md` | Editable assessment instructions |
| `data/reviews/review_inventory.json` | Entry IDs, text/evidence hashes, archive paths, and line ranges at initialization |
| `data/reviews/entry_review.json` | Authoritative assessments, accepted-call usage, failures, pilot approval, and cross-entry results |
| `data/reviews/review_progress.json` | Derived coverage counts and pending IDs |

Complete the brief, distinguish allegations from established facts, and change
`Review status: DRAFT` to `Review status: READY`. Initialization preserves existing
briefs, instructions, and assessments. Re-running `init` refreshes the inventory.
Each run also re-reads current sources, so it does not rely on an old inventory.

Install a current [Codex CLI](https://developers.openai.com/codex/cli) and sign in
with ChatGPT in the same Windows or WSL environment where you run Python:

```powershell
codex login
codex login status
python -m property_timeline.review_runner run --pilot 20
```

`codex login status` must report **Logged in using ChatGPT**. The runner enforces
ChatGPT authentication and removes API-key environment variables from its child
process. It does not call the billed OpenAI API backend or require API credits.
Review runs consume your Codex/ChatGPT plan allowance and are subject to its usage
limits. See [Codex authentication](https://developers.openai.com/codex/auth) and
[non-interactive execution](https://developers.openai.com/codex/noninteractive).
Private/counsel text is sent to Codex, with the data-handling policies of your
ChatGPT account/workspace.

The model is optional: omit `--model` to use Codex's built-in default. To select
an available Codex model, supply `--model MODEL_ID` or set `CODEX_REVIEW_MODEL`.
The old `OPENAI_REVIEW_MODEL` variable is ignored. API-specific model availability
and pricing do not determine what your signed-in Codex plan can use.

If `codex` is not on PATH, set `CODEX_REVIEW_BIN` or pass `--codex-bin` with the
full executable path. The VS Code extension can bundle a CLI even when it is not
on PATH; use its `bin/windows-x86_64/codex.exe` for Windows Python or
`bin/linux-x86_64/codex` for WSL Python. For example:

```powershell
python -m property_timeline.review_runner run --pilot 20 --codex-bin 'C:\path\to\codex.exe'
```

Each batch starts a fresh ephemeral Codex session. It receives its evidence over
stdin, uses an output JSON schema, ignores user configuration and execution rules,
and disables shell access. It does not execute inside the correspondence project.
Your stored ChatGPT login is still used. Raw Codex logs are not copied into the
review files or printed, because they may contain correspondence or auth details.

The first 20 entries follow the existing master CSV's chronological order;
unknown-zone entries retain the timeline's separate ordering. Read
`output/counsel_review.md` and inspect the JSON assessments. Confirm that the
priority, exact quotations, and relevance explanations fit your intended criteria.
Revise the brief/instructions if needed and repeat the pilot. A repeated pilot
resumes the same initial entries and never advances beyond its requested limit.

## Continue automatically

To review everything and inspect the results at the end, complete the brief and
use unattended mode:

```powershell
python -m property_timeline.review_runner run --unattended
```

This starts from the next pending/stale entry, skips the pilot-approval pause,
and runs the cross-entry pass after all entries have current assessments. It
does not prompt between batches. Repeat the same command after an interruption
to resume. Omit `--max-batches` and `--max-cross-calls` to run to completion.
Authentication failures, plan limits, oversized entries, or failures after the
configured retries still stop the run and preserve progress.

At the end, check `output/counsel_review.md` and run `status`: `remaining` should
be zero and `cross_review_complete` should be true. Attachment review gaps still
need human examination even after the automated passes finish.

For the alternative workflow with a human-reviewed pilot:

After checking the pilot:

```powershell
python -m property_timeline.review_runner run --resume --approve-pilot
```

The runner requires current assessments for the first 20 entries (or every entry
if the timeline has fewer than 20). `--approve-pilot` records your approval for
the current criteria. Subsequent resumes can omit it:

```powershell
python -m property_timeline.review_runner run --resume
python -m property_timeline.review_runner status
python -m property_timeline.review_runner report
```

Successful batches are checkpointed before moving on. You can interrupt with
Ctrl+C and resume. If interrupted before a response is saved, that batch is
requested again and consumes additional plan allowance. Failed batches stop the run and
remain pending; completed batches are preserved. There are two retries by default.
Accepted-call usage is saved, but failed/retried request usage may not be available.
The usage log does not establish your remaining subscription allowance.

### Authentication, plan limits, and retry behavior

A missing CLI, API-key sign-in, or expired login stops the run with instructions
for checking `codex login status` or signing in using `codex login`. API-key
sign-in is rejected, even if API credentials happen to be present.

Codex plan-limit errors stop instead of being repeatedly retried. Wait for your
plan allowance to reset, then repeat the same pilot/resume command. Temporary
process timeouts or invalid structured responses may be retried with backoff.
There is no automatic fallback to an API-key backend.

The old HTTP 429 API error came from the previous API implementation; no API
billing change is needed to use this Codex runner. To make smaller requests:

```powershell
python -m property_timeline.review_runner run --pilot 20 --batch-size 5
```

`status` and `report` are local commands requiring no Codex sign-in. `report`
regenerates the report using only current assessments, with explicit pending,
stale, and attachment-incomplete counts. `cross_review_complete` in status tracks
whether the cross-entry pass has finished for the current assessment snapshot.

## Batch and call limits

Defaults are at most 40 entries and approximately 100,000 input characters per
entry-review request, 12,000 extracted characters per attachment, and 900 seconds
per Codex batch. Codex manages its output-token allowance. Character counts are a planning bound, not a model token count.
An oversized message stops the run instead of silently truncating correspondence.
Long attachment text is truncated with a saved human-review gap.

For smaller requests and a bounded amount of work per invocation:

```powershell
python -m property_timeline.review_runner run --resume --batch-size 10 --max-chars 60000 --max-batches 3 --max-cross-calls 5
```

Other controls: `--attachment-chars`, `--codex-timeout`, `--codex-bin`,
`--retries`, and `--model`. The former API-only `--max-output-tokens` flag was removed. Use `--root PATH` **before** the command when running from another
folder. From WSL, prefix Python commands with `cmd.exe /c` if using Windows Python;
the invoked Codex executable must be signed in with ChatGPT in that environment.

After entry review finishes, the runner automatically compares assessments
sharing a topic. It partitions long topic groups into bounded blocks and compares
every block pair, including internal comparisons. This can require many requests:
a topic with B blocks takes B × (B + 1) / 2 calls. `--max-cross-calls` limits new
cross-entry requests per invocation; resume to finish. Cross-entry results are
checkpointed individually. Changing request bounds may create new task partitions.

## What is checked and what remains for counsel

Each response must assess every requested ID exactly once, use valid categories,
and quote exact contiguous supplied text. High-priority assessments require
quotations. Related IDs must have been supplied as entries or boundary context.
Cross-entry findings require at least two supplied entry IDs and matching evidence
quotations. These checks do not establish that the model's interpretation is correct.

Attachments are validated against extraction hashes/sizes before review. Missing
required files or changed bytes stop the run. Unavailable files, extraction
failures, partial text, truncation, and visual-review limitations remain explicit.
No OCR is performed. Original attachment files stay unchanged. Cross-entry review
uses the initial assessments and their selected quotations, so it cannot recover
an important fact missed in that first pass. Relationships across different topics
and material present only in images still need human review.

Changing a brief or instructions invalidates all previous assessments and pilot
approval. Changing an entry or its indexed evidence invalidates its assessment;
cross-entry results are tied to the entire assessment snapshot. Stale assessments
remain in the JSON until replaced but are excluded from the current report.
If source numbering changes, existing IDs may refer to different entries: hashes
trigger re-review rather than assuming a citation still identifies the same content.

## Load the review into the offline viewer

Rebuild the timeline after source, case-brief, or instruction changes so the HTML
contains the current evidence and criteria fingerprints:

```powershell
python -m property_timeline.combine_timeline --phone-timezone America/New_York
```

Open `output/master_timeline.html`, choose **Load review**, and select
`data/reviews/entry_review.json`. The file is read locally by the browser. It is
not uploaded or saved in browser storage. Expand a card's **AI review** panel for
its priority, topics, relevance, evidence quotations, related entries, uncertainty,
questions for counsel, and attachment gaps. Use the priority/topic/status filters
alongside the existing correspondence search, source, and date filters.

Entries whose text, indexed evidence, or criteria fingerprints differ are marked
**Review outdated**. Their previous assessments remain available for inspection,
but are excluded from current priority/topic filters. Unreviewed entries and IDs
absent from the viewer are counted. If the HTML was generated without both brief
and instructions, assessments are marked **Criteria unchecked** and are also
excluded from current priority/topic filters; rebuild with the review workspace.
Checks compare against the files at HTML generation time, so rebuild after edits.

**Clear review** removes annotations and review filters immediately, retaining
your correspondence search/date/source selections. **Reset** clears all filters
while retaining the loaded annotations. Reloading or closing the tab discards the
loaded review. Review overlays are excluded from printing and the generated PDF
and AI ZIP. The generated counsel report links to existing timeline cards.

Deleting `data/reviews/` and `output/counsel_review.md` removes the saved review;
clear the review or reload any already-open viewer tab as well. Back up review
artifacts before deleting them if you want to retain corrections or history.

Only one runner may operate on a workspace at a time. A hard process termination
can leave `data/reviews/.runner.lock`; remove it only after confirming that no
runner is active. `entry_review.json` is authoritative if an interruption occurred
between its atomic replacement and the progress-file replacement; the next run
recomputes coverage from saved assessments.
