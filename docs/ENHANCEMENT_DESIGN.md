# Repository enhancement design

Date: 2026-10-15  
Reviewed revision: `30ab0e01a2395d9b93e1c1501a20ec57303cee4c` plus the working tree  
Status: Implemented; the original assessment and rationale are retained below

## Implementation record — 2026-10-15

All eight recommendations are implemented. Runtime state remains schema version
1 with additive preparation/plan fields, so existing assessments are retained.
Legacy comparison completion is unverified until an exact plan is rebuilt;
matching task results can then be reused without deleting historical work.
No live model requests or automatic migration of the evidence archives were run.

| ID | Implementation |
| --- | --- |
| E1 | `review_runner` stores a deterministic exact task manifest/plan ID, derives active coverage from its required tasks, provides read-only `plan`, and supports `--max-cross-tasks`. |
| E2 | `archive_inventory` validates required schemas, exact row coverage, and attachment bytes. Extractors publish generation sidecars; explicit `check`/`bind` support legacy archives and intentional curation. |
| E3 | `immutable_assets` publishes extracted bytes under content-hash paths without replacing existing referenced files. Gmail and iPhone use it; old assets are retained. |
| E4 | Typed backend failures survive retries, stop both phases under manual skipping, and checkpoint a sanitized run-level reason. Task-local failures retain skip/retry behavior. |
| E5 | Accepted assessments store preparation version, supplied-evidence digest, extraction statuses/ranges, and truncation. `--refresh-review-gaps` and repeatable `--refresh-id` preserve accepted results until replacements validate. |
| E6 | The viewer validates and displays current/manual/retry/historical/unchecked failures, reasons, filters, counts, legacy preparation status, and plan-bound comparison coverage. |
| E7 | `python -m property_timeline.verify --strict` runs Python, Node, and real-browser synthetic checks, with optional read-only `--pdf HTML`. Windows/Linux CI use the same command and sparse checkout of code/tests. |
| E8 | MBOX extraction processes structured MIME records directly. New Gmail/Android/iPhone archives frame literal bodies reversibly; optional `bind --frame` migrates legacy archives without renumbering logical records. |

Validation: 88 Python tests discovered on Windows, 87 passed and one skipped
because symlinks were unavailable. All PDF fixtures, the expanded Node harness,
the real Chrome/Edge integration fixture, and existing PDF verification passed.
WSL ran the same 88 Python tests with seven dependency-related PDF skips and
81 passes. Read-only preflight validated all 880 live archive/index associations.
The GitHub workflow was created but was not executed on hosted runners here.
The real timeline was rebuilt to include the viewer controls, and its existing
880-record PDF passed verification afterward. Other generated text outputs were
unchanged. The rebuilt AI ZIP's file contents matched the prior ZIP exactly, so
its original bytes were retained to avoid timestamp-only archive changes.

The real-browser fixture uses the existing Chrome/Edge requirement and Python's
standard library; no browser automation package was needed. Existing multi-file
replacement remains nontransactional: generation checks detect mixed bundles,
and immutable paths preserve prior assets. No automated asset cleanup was added.
The new CLI workflows and migration behavior are documented in
[WORKFLOWS.md](WORKFLOWS.md) and [REVIEW_HARNESS.md](REVIEW_HARNESS.md).

## Decision

The remaining sections retain the assessment that guided implementation; the
implementation record above describes the resulting code and current checks.

Eight enhancements are highly recommended. The project does not need a rewrite:
its offline workflow, source preservation, attachment hashing, quotation
validation, and regression coverage provide a useful foundation. The remaining
work should strengthen completion claims, attachment completeness, failure
recovery, and the visibility of unfinished reviews.

Five recommendations address correctness or recovery before relying on a
completed review or refreshing source archives. Three improve the ability to
finish and verify the existing workflow. These are implementation proposals,
not claims that the current correspondence or PDF is corrupt.

| ID | Priority | Recommendation | Primary benefit |
| --- | --- | --- | --- |
| E1 | P1 | Bind cross-review completion to an exact task manifest | Prevent false completion after changing request budgets |
| E2 | P1 | Require complete archive/index associations before export | Prevent silent disappearance of attachments |
| E3 | P1 | Publish extracted assets without overwriting prior generations | Preserve the previous archive when extraction fails |
| E4 | P1 | Preserve fatal backend error categories across review phases | Stop quota/authentication failures without skipping every task |
| E8 | P1 | Separate email contents from archive record delimiters | Prevent body text from becoming a fabricated source record |
| E5 | P2 | Track prepared evidence and support targeted gap reassessment | Revisit successful assessments made with incomplete attachment text |
| E6 | P2 | Show manual-review failures and comparison coverage in the viewer | Make unfinished work actionable in the primary reading interface |
| E7 | P2 | Provide one offline verification command with explicit coverage | Include JavaScript checks and expose missing prerequisites |

P1 means correctness/recovery work to address first. P2 means strongly
recommended follow-up for this repository's current use. These are engineering
priorities, not vulnerability severity ratings.

## Review scope and current state

The review covered the Python extraction, combination, AI export, PDF, review
runner, viewer resources, tests, packaging, and maintenance documentation. It
included independent focused reviews of the pipeline, review harness, and
viewer/tooling. Historical findings in [CODE_REVIEW.md](CODE_REVIEW.md) were
checked against their remediation notes rather than repeated as open issues.

The initial working tree contained four modified files under an existing
`backups/review_backups/` snapshot. They were left untouched. The runner, its
tests, and the harness documentation were committed at the reviewed revision.
No originals, curated archives, generated outputs, or live review state were
rewritten for this review. No live model requests were made. Reproductions used
sanitized temporary fixtures and mocked model responses.

Read-only checks produced the following snapshot:

| Item | Observed state |
| --- | --- |
| Timeline | 880 records: 281 Gmail, 215 Android, 384 iPhone |
| HTML freshness | All 880 IDs, source/evidence hashes, and the criteria hash match current runner inputs |
| First-pass review | 834 current assessments; 46 remaining, all flagged for manual review; no stale/orphaned assessments |
| Manual failures | 44 validation failures; two entries exceed the request budget |
| Accepted assessments with attachment gaps | 106 |
| Saved cross-review plan | 5,886 tasks; 81 completed; 103 failed/skipped; 46 entries excluded |
| Cross-review completion | False for both included scope and full coverage |
| Initialization inventory | 866 entries, compared with 880 in the current timeline |
| Existing PDF verification | 880 bodies/destinations; 302 pages; 199 embedded originals plus two manifests; 310 attachment annotations; hashes match |

These counts describe the state read during this review and can change as the
runner progresses. Cross-review counts use today's implementation; E1 explains
why they should not be treated as an independent proof of plan coverage.
The inventory difference is expected for an initialization snapshot: the harness
documents that `init` refreshes it and runs reread current archives. It is not
evidence that the 14 newer entries were omitted from the current timeline.
Attachment gaps also do not all represent bugs: unavailable originals and images
without readable text can legitimately require human inspection.

### Validation performed

| Check | Result |
| --- | --- |
| Windows Python 3.13.7 unit discovery | 73 discovered: 72 passed, one skipped because symlinks were unavailable |
| WSL Python 3.12.3 unit discovery | 73 discovered: 67 passed, six skipped because PyMuPDF was unavailable |
| Node overlay harness and generated HTML script compilation | Passed |
| Existing PDF `--verify-only` | Passed with the counts above |
| Read-only runner load and HTML fingerprint comparison | Passed |

Commands used from the repository root:

```bash
PYTHONPATH="$PWD/src" python3 -m unittest discover -s tests -v
cmd.exe /c python -m unittest discover -s tests -v
cmd.exe /c python -m property_timeline.export_timeline_pdf --verify-only
```

The JavaScript check ran through the installed Windows Node executable with
these arguments:

```text
node tests/review_viewer_test.cjs src/property_timeline/resources/review_viewer.js output/master_timeline.html
```

The absolute `PYTHONPATH` makes imports work in test subprocesses that change
directories; an initial relative-path run failed those imports and was corrected.
Windows executable access required a sandbox retry for Node. Passing the overlay
harness does not establish actual browser layout or all DOM interactions. The
existing PDF was verified, not regenerated or visually reviewed in Acrobat.

## E1 — Exact cross-review plan identity and completion

### Evidence and impact

In [review_runner.py](../src/property_timeline/review_runner.py), `snapshot()`
(lines 403–409) identifies assessments and scope. `cross_review()` builds blocks
from the request budget and hashes each supplied task (lines 647–677). Coverage
counts all successful tasks with the same snapshot (lines 381–391), while the
completion marker also identifies only that snapshot (lines 744–746).

Changing `--max-chars` changes the partition and task IDs without changing the
assessment snapshot. Historical task successes can then count toward a new
plan, and a previous completion marker can survive an incomplete new plan.

Reproduction: complete the sanitized 23-entry fixture with a 30,000-character
budget, producing one task. Resume with a 10,000-character budget, producing
15 tasks, and reject one new response. The result reports 15 completed of 15,
one failed task, and `cross_review_complete=true`: 14 new successes plus one
historical success satisfy the count. This is a completion-accounting defect,
even though the current real review is already marked incomplete.

### Proposed design

Persist a deterministic `plan_id`, assessment/evidence snapshot, algorithm
version, included/excluded entry IDs, and exact required task ID manifest.
Derive active progress by membership in that manifest. A task counts once only
when its required ID has an accepted result. Completion requires every required
task to succeed; required failed/skipped tasks prevent completion. Full coverage
also requires every entry to have a current assessment and no excluded entries.

Recompute completion whenever the plan changes. Retain historical results for
audit and reuse only results whose exact task identity matches. Legacy results
without a verifiable manifest remain historical; an old completion marker alone
must not establish completion. Publish the same plan identity and coverage in
the report and contextual viewer payload.

Add a read-only plan preview showing included/excluded counts, blocks, required
tasks, reusable successes, failures, and remaining external calls before a run.
Block-pair work grows as `B * (B + 1) / 2`; the saved 5,886-task plan makes that
visibility useful. Preserve `--max-cross-calls`; an optional total-task ceiling
can reject an unexpectedly large plan without adding an interactive approval
pause. Estimates should state that retries can increase actual calls.

### Acceptance criteria

- Change budgets both upward and downward across resumes; historical tasks never
  inflate current progress, and partial new plans never inherit completion.
- Failed/skipped required tasks prevent completion, including after interruption.
- Identical plans reuse accepted tasks without repeating model requests.
- Legacy state migration cannot infer completion from aggregate counts.
- CLI, JSON, report, and viewer agree on the same plan and scope.

## E2 — Complete archive/index associations before export

### Evidence and impact

[combine_timeline.py](../src/property_timeline/combine_timeline.py) loads source
indexes only when the supporting files exist (lines 199–218). Missing metadata
falls back to an empty mapping. The HTML and AI exporters then treat a missing
`attachment_files_json` value as an empty attachment list:
[timeline_html.py](../src/property_timeline/timeline_html.py), lines 289 and
303–304, and [ai_export.py](../src/property_timeline/ai_export.py), lines 169–170.

Reproduction: a sanitized Gmail record with one indexed `terms.txt` attachment
produces one HTML file link and one AI attachment-index row. Replace the source
CSV with its header and zero rows. Combination succeeds, but both attachment
counts become zero while the original file still exists. Hash validation cannot
detect an association omitted before the expected attachment set is collected.

This was reproduced with fixtures; the current live runner and HTML consistency
checks did not establish this defect in the actual generated bundle.

### Proposed design

Introduce shared preflight validation for each archive and its required index.
Require the relevant schema, valid unique source numbers, and exact coverage of
parsed record IDs. Join iPhone rows within their conversation namespace. Reject
missing rows and unexplained extra rows before staging any final outputs.
Represent unavailable attachments explicitly in valid rows; distinguish them
from an absent index or malformed metadata.

Use the validated inventory in combination, rendering, AI export, and review
loading so these consumers agree on the expected set. Bind new archive/index
generations through a sidecar manifest containing source, archive, index, and
attachment hashes. Because archives are intentionally curated, provide a local
validation/rebind operation for reviewed edits; never force re-extraction as the
way to acknowledge curation.

For existing archives, validate associations immediately and introduce generation
binding through an explicit migration. If legacy text-only exports remain useful,
make them an explicit mode and carry the provenance gap into every exported
format. Do not silently interpret missing metadata as proof of no attachments.

### Acceptance criteria

- Missing files/rows, duplicates, malformed attachment JSON, and wrong-conversation
  rows fail before publishing; the previous successful outputs remain unchanged.
- An explicitly unavailable attachment remains represented with its reason.
- Valid curated archives retain current IDs, text, and attachment exclusions.
- HTML, AI ZIP, PDF expectations, and review loading agree on record/file mappings.
- Generation mismatches are actionable; an intentional curation/rebind path is tested.

## E3 — Preserve prior asset bytes during failed extraction

### Evidence and impact

Gmail extracts deterministic attachment filenames before cleaning and staging
the archive/index: [gmail_archive.py](../src/property_timeline/gmail_archive.py),
lines 122–124, 364–378, and 461–475. The actual overwrite occurs in
[email_attachments.py](../src/property_timeline/email_attachments.py), lines 31–33.
iPhone image extraction similarly writes final asset paths at
[iphone_pdf_to_markdown.py](../src/property_timeline/iphone_pdf_to_markdown.py),
lines 270–276, before staging Markdown/CSV at line 333.

Reproduction: rerun a temporary MBOX with changed attachment bytes and inject a
later `clean_body()` failure. The previous Markdown and CSV remain byte-for-byte
unchanged, but their referenced attachment has already changed. The documented
staging guarantee therefore does not cover extracted assets. iPhone has the
same ordering by static inspection; its failure case was not separately reproduced.

### Proposed design

Extract into a new staging generation. Store published assets under immutable
content-hash or generation-qualified paths, retaining original filenames in
metadata. Validate the new archive, indexes, and asset hashes before publishing
their references. Never overwrite a file referenced by the prior generation.
If a hash-named asset already exists, verify its bytes before reuse.

A failed extraction may leave an unreferenced staging directory or immutable
asset; it must leave prior referenced bytes intact. Keep old assets until a
separate explicit cleanup verifies they are unreferenced by retained archives
and backups. Do not automatically delete old asset paths during migration.

This removes pre-publication asset corruption. It does not turn the existing
multi-file `os.replace()` loop into a filesystem transaction; interrupted bundle
publication still requires generation validation/recovery as described in E2.

### Acceptance criteria

- Inject failures after asset extraction and before archive/index publication for
  both Gmail and iPhone; every file referenced by the old generation is unchanged.
- Successful reruns publish matching paths, sizes, hashes, and manifests.
- Same-content assets can be reused; changed bytes use a different published path.
- Cleanup cannot delete assets referenced by a retained archive or backup.

## E4 — Stop backend-wide failures without skipping the whole plan

### Evidence and impact

[review_runner.py](../src/property_timeline/review_runner.py) recognizes
nonretryable `CodexError` instances inside `ask()`, then converts them to ordinary
`ValueError` at line 498. The cross pass catches that error and, with
`--skip-manual-review`, records and skips the task (lines 726–737). A quota,
authentication, executable, or configuration failure can affect every request;
it is not an evidence problem requiring manual review of each comparison.

Reproduction: finish fixture first-pass assessments, enable manual skipping,
and inject `CodexError('Codex plan usage limit reached')` into a 15-task cross
plan. The runner makes 15 failed requests, records 15 skipped tasks, and returns
normally. The first-pass quota-stop test does not exercise this second-pass path.

### Proposed design

Preserve structured categories through `ask()`: backend-wide fatal failures,
transient execution failures, response-validation failures, and task-local
failures. Stop with a failing exit status on quota, authentication, missing
executable, or invalid configuration regardless of the manual-skip flag.
Checkpoint prior successes and a sanitized run-level stop reason, leaving
unattempted tasks pending. Preserve bounded retry/skip behavior for failures
whose scope is actually local to a request or its evidence.

Keep existing raw-log suppression. Unknown error classifications should stop
with an actionable sanitized reason rather than mass-classify evidence as
needing manual review. Revisit historical skipped execution failures without
discarding accepted results; do not infer their category solely from old prose.

### Acceptance criteria

- Under manual skipping, injected quota/auth/configuration failures stop after
  the first request and preserve later tasks as pending.
- Existing successes survive; resume retries the stopped work after recovery.
- Genuine local validation failures may still be skipped while later tasks run.
- Error categories and failing exit status are tested in both review phases.

## E5 — Prepared evidence identity and targeted gap reassessment

### Evidence and impact

`Workspace.current()` compares raw evidence/index and criteria hashes:
[review_runner.py](../src/property_timeline/review_runner.py), lines 358–361.
`prepare()` performs local extraction and truncation later (lines 431–468).
The accepted assessment does not identify the exact extracted/truncated evidence
that reached the model. Run eligibility skips current assessments (lines 504–506).

Reproduction: assess an indexed text attachment with `attachment_chars=10`.
Raise the limit to 20,000 and enable `retry_manual_review`. The next pilot makes
zero model requests and retains the original truncation gap. These are accepted
assessments with gaps, so the manual-failure retry flag does not select them.
Repairing an extractor or installing a missing extraction dependency has the
same identity gap by inspection. There are currently 106 accepted assessments
with attachment gaps, although some need human review rather than re-extraction.

### Proposed design

Keep source freshness separate from assessment-input completeness. Persist a
versioned preparation profile, per-source extraction status, supplied character
ranges/truncation details, and a digest of the exact supplied evidence. Include
the preparation/extraction implementation version without conflating it with
the case-brief hash. Record the selected backend/model for audit, but do not
invalidate every assessment merely because a default model might change.

Add explicit selectors for refreshing gap-bearing assessments or selected entry
IDs. A refresh prepares evidence, compares its digest, and reassesses affected
entries while preserving the prior accepted result until a replacement validates.
Unchanged evidence can be reused unless the user explicitly requests a new
assessment. Updated accepted inputs invalidate dependent cross-review plans.

Mark legacy preparation provenance as unknown without deleting useful saved
assessments or forcing a full live-model rerun. Explain which gaps are repairable
by extraction and which still require inspecting the original.

### Acceptance criteria

- Raising the attachment limit plus selecting gap refresh reassesses affected
  entries only; ordinary unchanged resumes do not repeat work.
- A repaired extractor changes prepared evidence and makes targeted refresh useful.
- A failed reassessment does not destroy the previous accepted result.
- Updated assessment evidence invalidates dependent contextual results.
- Source files remain unchanged; legacy preparation status is explicit.

## E6 — Actionable failure visibility in the offline viewer

### Evidence and impact

[review_viewer.js](../src/property_timeline/resources/review_viewer.js) validates
assessments but ignores saved failures (lines 2–23). An entry without an assessment
becomes `none` (lines 25–29), and the Review gaps filter excludes it (lines 94–97).
The load summary counts current/outdated/unreviewed/unchecked assessments only
(lines 204–229). Cross findings show complete/in-progress and excluded-entry
counts, without failed/skipped comparison counts (lines 73–75).

Consequently, the 46 current manual-review failures appear as ordinary unreviewed
cards. Their saved reasons cannot be inspected or selected in the viewer's
review-gap workflow. The report/JSON have more actionable information.

### Proposed design

Import validated failures alongside assessments. Distinguish manual review,
retry pending, and never attempted; keep attachment gaps on accepted assessments
as a separate dimension. Render saved reasons with `textContent`, add filters,
and show counts matching runner semantics. A valid current assessment takes
precedence over an older failure. Fingerprint-mismatched failures are historical
and must not create a current failure label. Older unbound failures need an
explicit unchecked status rather than an invented freshness guarantee.

Include a plan-bound coverage summary in `contextual_review`: required,
successful, failed/skipped tasks, excluded entries, and both scope/full completion.
Reuse E1's exact plan accounting rather than trusting a separate progress JSON.
Preserve local-only loading, clear/reset behavior, and stale-assessment guards.

### Acceptance criteria

- Current synthetic manual failures show a reason, card label, count, and filter.
- Stale failures never appear current; valid accepted assessments take precedence.
- Runner/report/viewer counts match for the same input and plan snapshot.
- Excluded entries and skipped comparisons remain visibly incomplete.
- Imported reasons render as text, and clear/reset restores normal browsing.

## E7 — One verification entry point with explicit coverage

### Evidence and impact

[WORKFLOWS.md](WORKFLOWS.md), lines 130–138, describes Python discovery and the
PDF exporter's `--self-test` as the full suite. That self-test uses only Python
discovery: [export_timeline_pdf.py](../src/property_timeline/export_timeline_pdf.py),
lines 55–61. The Python viewer test verifies hashes and script presence; it does
not execute the separate [Node harness](../tests/review_viewer_test.cjs).

The Node harness passed when invoked explicitly during this review. Its fake DOM
also stores one callback per event, whereas real DOM listeners accumulate, so it
cannot establish all interactions between the base viewer and overlay controls.
Python runs can report success while required PDF tests are skipped, as the WSL
run demonstrates. The current docs mention skips, but there is no single coverage
gate for a release/share check.

### Proposed design

Add one local verification entry point that runs Python discovery, JavaScript
syntax/overlay tests, and an optional existing-bundle/PDF verification stage.
Report each component as passed, failed, or unavailable. Provide a strict mode
that fails when a required component is unavailable; keep source-test verification
usable without real correspondence. Resolve test/resource paths independently
of the caller's working directory.

Document Node and PDF prerequisites. Run sanitized tests in a Windows job with
PyMuPDF/Pillow and Node, plus a Linux job for portability. Add a small real-browser
fixture for integrated load/filter/reset/hash-navigation/clear behavior, rather
than expanding the fake DOM into an imitation browser. Browser fixture/tooling
dependencies should be development-only. No verification command should submit
evidence to a model or regenerate production archives as a side effect.

### Acceptance criteria

- A JavaScript syntax/harness failure causes the unified command to fail.
- Missing Node or required PDF support is visible and fails strict verification.
- Integrated browser tests exercise correspondence and review controls together.
- Synthetic tests need no private case data or live model services.
- Optional real-bundle verification reads existing artifacts without modifying them.

## E8 — Keep source text separate from record delimiters

### Evidence and impact

`from_mbox()` serializes real messages and arbitrary bodies into an intermediate
Markdown string: [gmail_archive.py](../src/property_timeline/gmail_archive.py),
lines 102–148. `main()` then searches the whole string for `^## Email (\d+):`
and reparses those positions as actual records (lines 370–377).

Reproduction: a one-message temporary MBOX contains a pasted archive example
beginning `## Email 002: Pasted entry`, followed by Date/From/To and body lines.
The extractor succeeds with two source-index rows. The original Message-ID is
present on the first row and blank on the second. Body material has acquired
independent source identity and attribution. This establishes an input-dependent
defect, not evidence of fabricated records in the current checked-in dataset.

### Proposed design

Make MBOX ingestion return structured records containing original headers,
Message-ID, body, source order, and attachments. Apply cleanup/event classification
to those records directly, then serialize once. Source count and identity must
come from actual MBOX messages, never a regex over message bodies.

Keep the legacy Markdown importer separate with explicit format and count/identity
validation. Also define reversible body framing for generated archives and make
the downstream parser understand it; fixing the intermediate representation alone
does not protect every later heading-based parser from heading-like body text.
For example, literal-body fences can be chosen longer than any delimiter in the
body, with record headings recognized only outside those fences. The readable
archive and renderer must preserve original body text after decoding.

Migrate existing curated archives without renumbering or re-extracting them.
Detect ambiguous legacy boundaries for explicit repair rather than silently
inventing entries. Preserve the existing intentional EVENT classification and
quote-recovery behavior; this change concerns framing and source identity.

### Acceptance criteria

- One actual MBOX message always yields one source-index row, including when its
  body contains archive headings, metadata-looking lines, separators, or fences.
- Original Message-IDs and authors remain attached to the original records.
- Heading-like body content survives extraction, combination, and rendering as
  message content, with no extra timeline IDs.
- Existing curated IDs/text survive migration; cleanup/event regression tests pass.

## Implementation sequence and migration

1. **Fix review accounting and failure propagation: E1, E4.** Add regression
   fixtures first. Version persisted plan metadata and treat unverifiable legacy
   completion as historical. Do not erase accepted assessments or source hashes.
2. **Protect archive refreshes: E2, E3, E8.** Share index preflight, add immutable
   asset publication and structured MBOX ingestion, and validate existing source
   associations. Back up before a real refresh; retain the documented ability
   to preserve manual archive edits.
3. **Make gaps repairable and visible: E5, E6.** Extend assessment provenance and
   the viewer payload with backward-compatible readers or an explicit migration.
   Reuse the canonical plan accounting from E1.
4. **Make verification routine: E7.** Put new regression cases behind the unified
   command and add sanitized automation. Do not publish private artifacts from CI.

Each phase should be independently reviewable. Use temporary fixtures for
failure injection, plan migration, and interruption tests. Migrate a copied
review workspace before changing the live state; a design review should not
automatically restart a potentially expensive model run.

## Changes not currently justified

- A database, hosted service, frontend framework, or broad rewrite. Local files
  and an offline viewer fit the documented workflow; the failures above can be
  addressed within that architecture.
- Reopening the ten historical content-preservation findings. Their fixes are
  present, and relevant current regression/PDF checks pass.
- Treating all 106 attachment gaps as failures that code can resolve. Scanned,
  graphical, and unavailable evidence can require human review; E5 should make
  that distinction explicit.
- Replacing exhaustive comparisons with heuristic retrieval immediately. A local
  plan preview and correct coverage accounting come first. Any later optimized
  comparison strategy needs an evaluation set and explicit coverage semantics.
- Ignoring/deleting originals, curated archives, review results, or backups to
  simplify Git. These are intentional project artifacts in the current workflow.
- Promising punctuation, image fidelity, or visual layout from passing PDF text
  checks. Keep the documented manual visual review before sharing.

The recommended outcome is a sequence of focused reliability changes with
preserved evidence and resumable state. No product expansion is required.
